"""The NFL state model: a Kalman filter over every team's offence and
defence, carried across seasons.

    python -m atlas.models.nfl_state            # -> reports/nfl_state.md

Step 3 of `docs/MODEL_PLAN_NFL.md`. The filter is the college one
(:mod:`atlas.models.kalman`): two point totals per game, a full covariance
that is the opponent adjustment, strictly in kickoff order. What differs is
the prior. College re-opens every season from a preseason regression on
ratings, talent and recruiting; the NFL has none of that and does not need
it - last season's team, regressed toward the mean, is the best preseason
guess there is (Glickman & Stern's AR(1); the plan's factor 4). So the
state runs continuously from 2011: at each new season every team's offence
and defence are multiplied by ``phi`` and their variance grows by the
between-season innovation, and the games take it from there.

Hyperparameters - process noise per week ``q``, between-season ``phi`` and
innovation variance ``p_season``, observation sd ``sigma`` - are chosen per
test season by walk-forward: the filter is run from 2011 and scored by
Gaussian predictive log-likelihood on the three most recent training
seasons. Home advantage and the league scoring level are the training
window's own means. No quarterback yet: that is step 4, and the quarterback
test in the report says how much it is missing.
"""

from __future__ import annotations

import argparse
import itertools
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from atlas import config
from atlas.models import elo, evaluate, kalman, scoring
from atlas.models import lattice as lat
from atlas.models import nfl_benchmarks as nb
from atlas.models import reference as ref
from atlas.research.nfl_dataset import load_nfl_frame, research_sample
from atlas.util import get_logger

LOG = get_logger(__name__)

FIRST_TEST_SEASON = 2020
REPORT_SEASONS = nb.REPORT_SEASONS
TUNING_SEASONS = 3
WINDOW_SEASONS = 3            # seasons behind the test season that set base points and home advantage

GRID = {
    "q": (0.0, 0.25, 0.5, 1.0, 2.0),
    "phi": (0.3, 0.4, 0.5, 0.67),
    "p_season": (5.0, 10.0, 25.0),
    "sigma": (7.5, 8.5, 9.5),
}

#: Step 4: the quarterback state. ``p0`` is a new quarterback's prior
#: variance and ``new_mean`` its prior mean in points against the team's
#: offence - the flat backup penalty, as a prior rather than a rule; the
#: filter replaces it with the player's own record as it accumulates.
#: v1.1 adds ``k_epa``: points of prior per unit of the player's own career
#: EPA per dropback above the league, shrunk by ``EPA_SHRINK`` dropbacks.
#: v1.2 adds ``k_obs``: the quarterback's own observation channel. After each
#: game the quarterback of record's EPA per dropback in it, above the league,
#: is a second measurement of his state alone - ``k_obs`` points per unit,
#: with noise variance ``k_obs**2 * play_var / dropbacks`` - so the
#: quarterback/offence split is identified from more than the points.
#: v1.3 adds ``k_draft``: points of prior per unit of draft score (see
#: :func:`draft_score`), weighted by how little NFL record the quarterback
#: has, so it speaks for a rookie and fades as his own dropbacks arrive. It
#: is tuned in a second pass beside ``new_mean``, the others held.
QB_GRID = {"p0": (4.0, 9.0, 16.0), "new_mean": (0.0, -2.0, -4.0), "k_epa": (0.0, 15.0, 30.0),
           "k_obs": (0.0, 10.0, 20.0, 30.0), "k_draft": (0.0, 0.4, 0.8, 1.2)}
EPA_SHRINK = 100.0
OBS_MIN_DROPBACKS = 10  # fewer is a cameo, not a measurement of the starter
#: Undrafted prices as the last pick: measured on 128 debuts 2011-26 with 100+
#: early dropbacks, day-three picks and undrafted both open about 0.165 EPA per
#: dropback below the league, first-rounders 0.084.
UNDRAFTED_PICK = 260.0
DRAFT_CENTRE = float(np.log(64.0))   # the end of round two scores zero


def draft_score(pick: float | None) -> float:
    """``log(64) - log(pick)``: +4.2 for the first pick, 0 at 64, -1.4 undrafted."""
    pick = UNDRAFTED_PICK if pick is None or pd.isna(pick) else min(float(pick), UNDRAFTED_PICK)
    return DRAFT_CENTRE - float(np.log(max(pick, 1.0)))
QB_Q = 0.05            # process variance per week on a quarterback
QB_PHI = 0.9           # between-season regression on a quarterback
QB_P_SEASON = 1.0      # between-season innovation on a quarterback
HFA_P0 = 1.0           # prior variance on the fitted home advantage
HFA_P_SEASON = 0.5     # how much the home advantage may drift between seasons
ORDER = ("naive", "elo", "atlas_epa", "state", "state_qb", "market")


@dataclass(frozen=True)
class Choice:
    q: float
    phi: float
    p_season: float
    sigma: float
    loglik: float
    seasons: tuple[int, ...]


@dataclass(frozen=True)
class QBChoice:
    p0: float
    new_mean: float
    loglik: float
    seasons: tuple[int, ...]
    k_epa: float = 0.0
    k_obs: float = 0.0
    k_draft: float = 0.0


class PasserRecord:
    """A passer's career dropbacks and EPA per dropback *before* a kickoff,
    and his line in each game *after* it.

    Built once from the staged passer log; queried when the state meets a
    quarterback for the first time (strictly prior games only, by date) and,
    with v1.2, after every game he was the quarterback of record in.
    """

    def __init__(self, passers: pd.DataFrame | None, players: pd.DataFrame | None = None) -> None:
        self.by_passer: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
        self.by_game: dict[tuple[str, str], tuple[float, float]] = {}
        self.names: dict[str, str] = {}
        self.draft: dict[str, float] = {}
        self.league = 0.0
        self.play_var = 0.0
        if players is not None and not players.empty:
            self.draft = {str(pid): draft_score(pick)
                          for pid, pick in zip(players["passer_id"], players["draft_number"], strict=True)}
            if "name" in players:
                self.names.update(dict(zip(players["passer_id"].astype(str), players["name"].astype(str),
                                           strict=True)))
        if passers is None or passers.empty:
            return
        p = passers.dropna(subset=["passer_id", "game_date"]).copy()
        p["date"] = pd.to_datetime(p["game_date"], errors="coerce")
        p = p.dropna(subset=["date"]).sort_values("date")
        weights = p["dropbacks"].to_numpy(dtype=float)
        epa = p["qb_epa_per_dropback"].fillna(0).to_numpy(dtype=float)
        self.league = float(np.average(epa, weights=weights))
        # Per-dropback variance implied by the game lines: a game's mean over
        # n dropbacks has variance play_var / n, so its noise scales with the
        # sample the way a measurement should.
        self.play_var = float(np.mean(weights * (epa - self.league) ** 2))
        if "game_id" in p.columns:
            self.by_game = {(str(pid), str(gid)): (float(n), float(e - self.league))
                            for pid, gid, n, e in zip(p["passer_id"], p["game_id"], weights, epa, strict=True)}
        if "passer_name" in p.columns:
            self.names.update(dict(zip(p["passer_id"].astype(str), p["passer_name"].astype(str), strict=True)))
        for pid, g in p.groupby("passer_id"):
            n = g["dropbacks"].to_numpy(dtype=float)
            self.by_passer[str(pid)] = (g["date"].to_numpy(), np.cumsum(n),
                                        np.cumsum(n * g["qb_epa_per_dropback"].fillna(0).to_numpy(dtype=float)))

    def before(self, passer_id, kickoff) -> tuple[float, float]:
        """(dropbacks, mean EPA per dropback above league) strictly before ``kickoff``."""
        rec = self.by_passer.get(str(passer_id))
        if rec is None:
            return 0.0, 0.0
        dates, n, s = rec
        k = int(np.searchsorted(dates, np.datetime64(pd.Timestamp(kickoff).tz_localize(None).normalize()), side="left"))
        if k == 0:
            return 0.0, 0.0
        return float(n[k - 1]), float(s[k - 1] / n[k - 1] - self.league)

    def draft_of(self, passer_id) -> float:
        """The quarterback's draft score; 0 (the centre) when the rosters never listed him."""
        return self.draft.get(str(passer_id), 0.0)

    def game(self, passer_id, game_id) -> tuple[float, float]:
        """(dropbacks, EPA per dropback above league) for one passer in one game; zeros if absent."""
        return self.by_game.get((str(passer_id), str(game_id)), (0.0, 0.0))


HFA_KEY = "__hfa__"


def choices_path(root: Path) -> Path:
    """Where the tuned hyperparameters go, so the total and the projector reuse them."""
    return root / "reports" / "nfl_state_choices.json"


def save_choices(choices: dict[int, Choice], qb_choices: dict[int, dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {str(s): {**asdict(c), "qb": qb_choices.get(s)} for s, c in sorted(choices.items())}
    path.write_text(json.dumps(payload, indent=1) + "\n")


def load_choices(path: Path) -> tuple[dict[int, Choice], dict[int, QBChoice]] | None:
    if not path.exists():
        return None
    raw = json.loads(path.read_text())
    choices = {int(s): Choice(q=c["q"], phi=c["phi"], p_season=c["p_season"], sigma=c["sigma"], loglik=c["loglik"],
                              seasons=tuple(int(x) for x in c["seasons"])) for s, c in raw.items()}
    qb = {int(s): QBChoice(p0=c["qb"]["p0"], new_mean=c["qb"]["new_mean"], loglik=c["qb"]["loglik"],
                           seasons=tuple(int(x) for x in c["qb"]["seasons"]), k_epa=c["qb"].get("k_epa", 0.0),
                           k_obs=c["qb"].get("k_obs", 0.0), k_draft=c["qb"].get("k_draft", 0.0))
          for s, c in raw.items() if c.get("qb")}
    return choices, qb


def _levels(train: pd.DataFrame, season: int) -> tuple[float, float]:
    """League points per team-game and home advantage on the margin, from the
    most recent training seasons, regular season, true home games."""
    recent = train[(train["season"] >= season - WINDOW_SEASONS) & (train["season_type"] == "regular")]
    if recent.empty:
        recent = train
    base = float(recent["actual_total"].mean() / 2.0)
    home = recent[pd.to_numeric(recent.get("neutral_site", 0), errors="coerce").fillna(0) == 0]
    return base, float(home["actual_margin"].mean())


def _spec(q: float, sigma: float, base: float, hfa: float) -> kalman.Spec:
    return kalman.Spec(q_off=q, q_def=q, p0_off=0.0, p0_def=0.0, sigma=sigma, base=base, boost=hfa)


def _fresh(teams: np.ndarray, phi: float, p_season: float, spec: kalman.Spec) -> kalman.State:
    """Every team at league average with the AR(1)'s stationary variance."""
    stationary = p_season / max(1.0 - phi ** 2, 1e-6)
    spec0 = kalman.Spec(**{**asdict(spec), "p0_off": stationary, "p0_def": stationary})
    return kalman.initialise(teams, np.zeros(len(teams)), np.zeros(len(teams)), spec0)


def new_season(state: kalman.State, phi: float, p_season: float, *, qb_phi: float = QB_PHI,
               qb_p_season: float = QB_P_SEASON, hfa_p_season: float = HFA_P_SEASON) -> None:
    """Regress every strength toward the mean and widen its uncertainty. In place.

    Team offences and defences use ``phi``/``p_season``; quarterbacks their own,
    slower, regression; a fitted home advantage keeps its mean and drifts.
    """
    n2 = 2 * state.n
    shrink = np.full(len(state.x), qb_phi)
    shrink[:n2] = phi
    add = np.full(len(state.x), qb_p_season)
    add[:n2] = p_season
    if HFA_KEY in state.extra:
        i = state.extra[HFA_KEY]
        shrink[i], add[i] = 1.0, hfa_p_season
    state.x *= shrink
    state.P *= np.outer(shrink, shrink)
    state.P[np.diag_indices_from(state.P)] += add
    state.week = None


# ---------------------------------------------------------------------------
# Step 4: the quarterback state and a fitted home advantage
# ---------------------------------------------------------------------------


def _advance_qb(state: kalman.State, weeks: int, spec: kalman.Spec, qb_q: float) -> None:
    """Process noise for teams (``spec``) and quarterbacks (``qb_q``); none on the home advantage."""
    if weeks <= 0:
        return
    n2 = 2 * state.n
    diag = np.full(len(state.x), qb_q * weeks)
    diag[:state.n] = spec.q_off * weeks
    diag[state.n:n2] = spec.q_def * weeks
    if HFA_KEY in state.extra:
        diag[state.extra[HFA_KEY]] = 0.0
    state.P[np.diag_indices_from(state.P)] += diag


def run_season_qb(games: pd.DataFrame, state: kalman.State, spec: kalman.Spec, *, p0: float, new_mean: float,
                  qb_q: float = QB_Q, first_season: bool = False, starters: dict | None = None,
                  k_epa: float = 0.0, record: PasserRecord | None = None, k_obs: float = 0.0,
                  k_draft: float = 0.0) -> pd.DataFrame:
    """Forecast every game with each side's expected starter, then learn from the one who played.

    The expected starter is the depth chart's QB1 for the week (knowable
    before kickoff) - unless the injury report lists him Out or Doubtful,
    when it is the QB2 - else the last quarterback of record for that team.
    The update uses the quarterback of record. A quarterback the state has
    not seen enters at ``new_mean`` plus ``k_epa`` times his own career EPA
    per dropback above the league before that kickoff, shrunk by
    ``EPA_SHRINK`` dropbacks, with variance ``p0`` - except in the first
    season, where every starter is an incumbent and enters at zero.
    ``starters`` carries each team's last quarterback of record across
    seasons and is updated in place. With ``k_obs`` (v1.2) the quarterback
    of record's own EPA per dropback in the game, from ``record``, is a
    second measurement of his state after the points have been assimilated.
    With ``k_draft`` (v1.3) a new quarterback's prior also carries his draft
    score, weighted by the share of ``EPA_SHRINK`` his record has not filled.
    """
    g = games.sort_values(["kickoff", "week"])
    n = state.n
    starters = {} if starters is None else starters
    if HFA_KEY not in state.extra:
        state.add(HFA_KEY, spec.boost, HFA_P0)
    hfa = state.extra[HFA_KEY]
    for c in ("home_qb2_id", "away_qb2_id", "home_qb1_out", "away_qb1_out"):
        if c not in g.columns:
            g = g.assign(**{c: pd.NA})
    cols = {c: g[c].to_numpy() for c in ("home_team_id", "away_team_id", "home_qb_id", "away_qb_id", "home_qb1_id",
                                          "away_qb1_id", "home_qb2_id", "away_qb2_id", "home_qb1_out", "away_qb1_out",
                                          "actual_margin", "actual_total")}
    kickoffs = g["kickoff"].to_numpy()
    game_ids = g["game_id"].to_numpy() if "game_id" in g.columns else np.full(len(g), None)
    observe = bool(k_obs) and record is not None and bool(record.by_game)
    weeks = g["week"].to_numpy(dtype=int)
    neutral = pd.to_numeric(g["neutral_site"], errors="coerce").fillna(0).to_numpy(dtype=float) \
        if "neutral_site" in g else np.zeros(len(g))
    means, sds, hps, aps = (np.full(len(g), np.nan) for _ in range(4))
    r = spec.sigma ** 2

    def qb_index(qb, team, kickoff=None) -> int | None:
        if pd.isna(qb):
            qb = starters.get(team)
        if qb is None:
            return None
        key = ("qb", str(qb))
        if key not in state.extra:
            mean = 0.0
            if not first_season:
                mean = new_mean
                if record is not None and kickoff is not None and (k_epa or k_draft):
                    n, epa = record.before(qb, kickoff)
                    w = n / (n + EPA_SHRINK)
                    mean += k_epa * epa * w + k_draft * record.draft_of(qb) * (1.0 - w)
            state.add(key, mean, p0)
        return state.extra[key]

    def expected(side: str, i: int, team):
        """The QB1 unless the report says he is out and a QB2 is listed."""
        qb1, qb2, out = cols[f"{side}_qb1_id"][i], cols[f"{side}_qb2_id"][i], cols[f"{side}_qb1_out"][i]
        if not pd.isna(out) and float(out) == 1.0 and not pd.isna(qb2):
            return qb2
        return qb1

    for i in range(len(g)):
        week = int(weeks[i])
        if state.week is None:
            state.week = week
        elif week > state.week:
            _advance_qb(state, week - state.week, spec, qb_q)
            state.week = week
        h, a = cols["home_team_id"][i], cols["away_team_id"][i]
        if h not in state.index or a not in state.index:
            continue
        ih, ia = state.index[h], state.index[a]
        is_home = 0.0 if neutral[i] else 1.0
        qh = qb_index(expected("home", i, h), h, kickoffs[i])
        qa = qb_index(expected("away", i, a), a, kickoffs[i])
        home_plus = [ih] + ([qh] if qh is not None else []) + ([hfa] if is_home else [])
        away_plus = [ia] + ([qa] if qa is not None else [])
        mh, _ = kalman.row_forecast(state, home_plus, [n + ia])
        ma, _ = kalman.row_forecast(state, away_plus, [n + ih])
        _, var = kalman.row_forecast(state, home_plus + [n + ih], away_plus + [n + ia])
        means[i], sds[i] = mh - ma, np.sqrt(var + 2.0 * r)
        hps[i], aps[i] = spec.base + mh, spec.base + ma
        m, t = cols["actual_margin"][i], cols["actual_total"][i]
        if np.isnan(m) or np.isnan(t):
            continue
        # Learn from who actually played.
        rh, ra = cols["home_qb_id"][i], cols["away_qb_id"][i]
        qh_rec = qb_index(rh, h, kickoffs[i]) if not pd.isna(rh) else qh
        qa_rec = qb_index(ra, a, kickoffs[i]) if not pd.isna(ra) else qa
        if not pd.isna(rh):
            starters[h] = rh
        if not pd.isna(ra):
            starters[a] = ra
        home_plus = [ih] + ([qh_rec] if qh_rec is not None else []) + ([hfa] if is_home else [])
        away_plus = [ia] + ([qa_rec] if qa_rec is not None else [])
        kalman.row_update(state, home_plus, [n + ia], (t + m) / 2.0 - spec.base, r)
        kalman.row_update(state, away_plus, [n + ih], (t - m) / 2.0 - spec.base, r)
        if observe:
            for qb, q_idx in ((rh, qh_rec), (ra, qa_rec)):
                if q_idx is None or pd.isna(qb):
                    continue
                n_db, epa = record.game(qb, game_ids[i])
                if n_db >= OBS_MIN_DROPBACKS:
                    kalman.row_update(state, [q_idx], [], k_obs * epa, k_obs ** 2 * record.play_var / n_db)
    out = pd.DataFrame({"mean": means, "sd": sds, "home_pts": hps, "away_pts": aps}, index=g.index)
    return out.reindex(games.index)


def run_qb(frame: pd.DataFrame, seasons: list[int], *, choice: Choice, p0: float, new_mean: float,
           levels: dict[int, tuple[float, float]], state: kalman.State | None = None,
           starters: dict | None = None, teams: np.ndarray | None = None, k_epa: float = 0.0,
           record: PasserRecord | None = None, k_obs: float = 0.0, k_draft: float = 0.0):
    """Like :func:`run`, with the quarterback state and the fitted home advantage."""
    if teams is None:
        teams = np.unique(np.r_[frame["home_team_id"], frame["away_team_id"]])
    starters = {} if starters is None else starters
    forecasts = {}
    first = state is None
    for i, season in enumerate(seasons):
        base, hfa = levels[season]
        spec = _spec(choice.q, choice.sigma, base, hfa)
        if state is None:
            state = _fresh(teams, choice.phi, choice.p_season, spec)
        elif i > 0 or state.week is not None:
            new_season(state, choice.phi, choice.p_season)
        forecasts[season] = run_season_qb(frame[frame["season"] == season], state, spec, p0=p0, new_mean=new_mean,
                                          first_season=(first and i == 0), starters=starters, k_epa=k_epa,
                                          record=record, k_obs=k_obs, k_draft=k_draft)
    return forecasts, state, starters


def tune_qb(frame: pd.DataFrame, season: int, choice: Choice, levels: dict[int, tuple[float, float]], *,
            grid: dict = QB_GRID, record: PasserRecord | None = None) -> QBChoice:
    """Pick the quarterback prior on the training seasons, given the season's team hyperparameters."""
    seasons = [int(s) for s in sorted(frame["season"].unique()) if s < season]
    scored = seasons[-TUNING_SEASONS:]
    train = frame[frame["season"] < season]
    teams = np.unique(np.r_[train["home_team_id"], train["away_team_id"]])
    best = None
    k_grid = grid.get("k_epa", (0.0,)) if record is not None else (0.0,)
    obs_grid = grid.get("k_obs", (0.0,)) if record is not None and record.by_game else (0.0,)
    for p0, new_mean, k_epa, k_obs in itertools.product(grid["p0"], grid["new_mean"], k_grid, obs_grid):
        fcs, _, _ = run_qb(train, seasons, choice=choice, p0=p0, new_mean=new_mean, levels=levels, teams=teams,
                           k_epa=k_epa, record=record, k_obs=k_obs)
        ll = sum(_loglik(fcs[s], train[train["season"] == s]) for s in scored)
        if best is None or ll > best.loglik:
            best = QBChoice(p0, new_mean, ll, tuple(scored), k_epa, k_obs)
    # Second pass: the draft score beside the intercept it shifts, the rest held.
    draft_grid = grid.get("k_draft", (0.0,)) if record is not None and record.draft else (0.0,)
    if any(draft_grid):
        held = best
        for new_mean, k_draft in itertools.product(grid["new_mean"], draft_grid):
            if not k_draft and new_mean == held.new_mean:
                continue
            fcs, _, _ = run_qb(train, seasons, choice=choice, p0=held.p0, new_mean=new_mean, levels=levels,
                               teams=teams, k_epa=held.k_epa, record=record, k_obs=held.k_obs, k_draft=k_draft)
            ll = sum(_loglik(fcs[s], train[train["season"] == s]) for s in scored)
            if ll > best.loglik:
                best = QBChoice(held.p0, new_mean, ll, tuple(scored), held.k_epa, held.k_obs, k_draft)
    return best


def run(frame: pd.DataFrame, seasons: list[int], *, q: float, phi: float, p_season: float, sigma: float,
        levels: dict[int, tuple[float, float]], state: kalman.State | None = None,
        teams: np.ndarray | None = None) -> tuple[dict[int, pd.DataFrame], kalman.State]:
    """Run the filter through ``seasons`` in order, from ``state`` or from scratch.

    ``levels`` gives (base points, home advantage) per season. Returns the
    pre-kickoff forecasts per season and the state after the last one.
    """
    if teams is None:
        teams = np.unique(np.r_[frame["home_team_id"], frame["away_team_id"]])
    forecasts = {}
    for i, season in enumerate(seasons):
        base, hfa = levels[season]
        spec = _spec(q, sigma, base, hfa)
        if state is None:
            state = _fresh(teams, phi, p_season, spec)
        elif i > 0 or state.week is not None:
            new_season(state, phi, p_season)
        games = frame[frame["season"] == season]
        forecasts[season] = kalman.run_season(games, state, spec)
    return forecasts, state


def _loglik(fc: pd.DataFrame, games: pd.DataFrame) -> float:
    reg = games["season_type"] == "regular"
    r = games.loc[reg, "actual_margin"].to_numpy(dtype=float) - fc.loc[reg, "mean"].to_numpy()
    v = fc.loc[reg, "sd"].to_numpy() ** 2
    return float(np.sum(-0.5 * np.log(2 * np.pi * v) - r ** 2 / (2 * v)))


def tune(frame: pd.DataFrame, season: int, levels: dict[int, tuple[float, float]], *, grid: dict = GRID,
         min_train_seasons: int = 2) -> Choice:
    """Pick hyperparameters on the training seasons before ``season``.

    Every candidate runs the filter from the first season in the frame; only
    the most recent training seasons are scored, by Gaussian predictive
    log-likelihood of the regular-season margins. The test season never
    touches its own hyperparameters.
    """
    seasons = [int(s) for s in sorted(frame["season"].unique()) if s < season]
    if len(seasons) < min_train_seasons:
        raise ValueError(f"need {min_train_seasons} training seasons before {season}")
    scored = seasons[-TUNING_SEASONS:]
    train = frame[frame["season"] < season]
    teams = np.unique(np.r_[train["home_team_id"], train["away_team_id"]])
    best = None
    for q, phi, p_season, sigma in itertools.product(grid["q"], grid["phi"], grid["p_season"], grid["sigma"]):
        fcs, _ = run(train, seasons, q=q, phi=phi, p_season=p_season, sigma=sigma, levels=levels, teams=teams)
        ll = sum(_loglik(fcs[s], train[train["season"] == s]) for s in scored)
        if best is None or ll > best.loglik:
            best = Choice(q, phi, p_season, sigma, ll, tuple(scored))
    return best


def walk_forward(frame: pd.DataFrame, *, first_test_season: int = FIRST_TEST_SEASON, grid: dict = GRID,
                 min_train_seasons: int = 2, qb: bool = True, qb_grid: dict = QB_GRID,
                 passers: pd.DataFrame | None = None, players: pd.DataFrame | None = None):
    """Tune on the past, forecast the season, score beside the references.

    With ``qb`` the quarterback model (step 4) is tuned and scored too, as
    ``state_qb``, on the same team hyperparameters as ``state``.
    """
    frame = nb.with_qb_change(elo.attach(frame)).sort_values(["kickoff", "game_id"]).reset_index(drop=True)
    for c in ("home_qb_id", "away_qb_id", "home_qb1_id", "away_qb1_id", "home_qb2_id", "away_qb2_id",
              "home_qb1_out", "away_qb1_out"):
        if c not in frame.columns:
            frame[c] = pd.NA
    record = PasserRecord(passers, players) if passers is not None else None
    all_seasons = [int(s) for s in sorted(frame["season"].unique())]
    scored, choices, finals = [], {}, {}
    qb_choices, qb_finals = {}, {}
    for season, train, test in ref.walk_forward(frame, first_test_season=first_test_season,
                                                min_train_seasons=min_train_seasons):
        levels = {s: _levels(frame[frame["season"] < max(s, all_seasons[0] + 1)], s) for s in all_seasons}
        choice = tune(frame, season, levels, grid=grid, min_train_seasons=min_train_seasons)
        choices[season] = choice
        history = [s for s in all_seasons if s < season]
        _, state = run(frame[frame["season"] < season], history, q=choice.q, phi=choice.phi,
                       p_season=choice.p_season, sigma=choice.sigma, levels=levels)
        fcs, state = run(frame, [season], q=choice.q, phi=choice.phi, p_season=choice.p_season,
                         sigma=choice.sigma, levels=levels, state=state)
        fc = fcs[season]
        finals[season] = state
        refs = ref.all_references(train, test)
        grid_ = lat.fit(train["actual_margin"].to_numpy(), -train["closing_spread"].to_numpy(), refs["market"].sigma)
        keep = {k: refs[k] for k in ("naive", "elo", "atlas_epa", "market") if k in refs}
        state_fc = ref.Forecast("state", fc["mean"].to_numpy(dtype=float), fc["sd"].to_numpy(dtype=float),
                                hfa=levels[season][1])
        models = {**keep, "state": state_fc}
        if qb:
            qb_choice = tune_qb(frame, season, choice, levels, grid=qb_grid, record=record)
            qb_choices[season] = qb_choice
            _, qstate, starters = run_qb(frame[frame["season"] < season], history, choice=choice, p0=qb_choice.p0,
                                         new_mean=qb_choice.new_mean, levels=levels, k_epa=qb_choice.k_epa,
                                         record=record, k_obs=qb_choice.k_obs, k_draft=qb_choice.k_draft)
            qfcs, qstate, _ = run_qb(frame, [season], choice=choice, p0=qb_choice.p0, new_mean=qb_choice.new_mean,
                                     levels=levels, state=qstate, starters=starters, k_epa=qb_choice.k_epa,
                                     record=record, k_obs=qb_choice.k_obs, k_draft=qb_choice.k_draft)
            qfc = qfcs[season]
            qb_finals[season] = qstate
            models["state_qb"] = ref.Forecast("state_qb", qfc["mean"].to_numpy(dtype=float),
                                              qfc["sd"].to_numpy(dtype=float), hfa=qstate.value(HFA_KEY))
        s = evaluate.score(test, models, grid_, season=season)
        s["qb_change"] = np.tile(test["qb_change"].to_numpy(), len(models))
        scored.append(s)
        LOG.info("season %s: q=%.2f phi=%.2f p_season=%.0f sigma=%.1f (tuned on %s); base %.1f hfa %.2f; %d games%s",
                 season, choice.q, choice.phi, choice.p_season, choice.sigma, choice.seasons,
                 levels[season][0], levels[season][1], len(test),
                 f"; qb p0={qb_choices[season].p0:.0f} new={qb_choices[season].new_mean:+.0f} "
                 f"k_epa={qb_choices[season].k_epa:.0f} k_obs={qb_choices[season].k_obs:.0f} "
                 f"k_draft={qb_choices[season].k_draft:.1f} "
                 f"hfa fitted {qb_finals[season].value(HFA_KEY):.2f}" if qb else "")
    out = pd.concat(scored, ignore_index=True)
    out.attrs["qb_choices"] = {s: asdict(c) for s, c in qb_choices.items()}
    out.attrs["hfa_fitted"] = {s: st.value(HFA_KEY) for s, st in qb_finals.items()}
    if qb_finals:
        out.attrs["quarterbacks"] = quarterbacks(qb_finals[max(qb_finals)], record)
    return out, choices, finals, frame


def quarterbacks(state: kalman.State, record: PasserRecord | None = None) -> pd.DataFrame:
    """Every quarterback the state carries: his points against the offence and the filter's sd."""
    rows = [{"passer_id": key[1], "quarterback": (record.names.get(key[1]) if record else None) or key[1],
             "points": float(state.x[i]), "sd": float(np.sqrt(state.P[i, i]))}
            for key, i in state.extra.items() if isinstance(key, tuple) and key[0] == "qb"]
    return pd.DataFrame(rows, columns=["passer_id", "quarterback", "points", "sd"]).sort_values("points", ascending=False)


def render(scored: pd.DataFrame, choices: dict[int, Choice], finals: dict[int, kalman.State],
           frame: pd.DataFrame) -> str:
    md, fmt, summarise = evaluate.markdown, evaluate.formatted, evaluate.summarise
    cols = ["crps", "brier", "log_margin", "mae", "ece"]
    seasons = sorted(choices)
    qb_choices = scored.attrs.get("qb_choices", {})
    hfa_fitted = scored.attrs.get("hfa_fitted", {})
    reg = scored[scored["season_type"] == "regular"]
    window = reg[reg["season"].isin(REPORT_SEASONS)]
    parts = [
        "# NFL state model", "",
        f"Walk-forward, seasons {seasons[0]}-{seasons[-1]}. The filter runs continuously from 2011; each new "
        "season regresses every team's offence and defence toward the mean by `phi` and widens their "
        "uncertainty by `p_season`, and every game is forecast strictly before kickoff and then assimilated "
        "(`atlas/models/kalman.py`). Hyperparameters are chosen on the earlier seasons only. `state` is the "
        "team model alone (step 3); `state_qb` adds a quarterback state carried by the player and a fitted, "
        "slowly drifting home advantage (step 4), forecast with the depth chart's QB1 and updated with the "
        "quarterback of record, whose own EPA per dropback in the game is a second measurement of him "
        "(v1.2, `pts per EPA/dropback, observed`); a quarterback with little NFL record also opens on his "
        "draft slot (v1.3, `pts per draft score`, where the score is log 64 minus log pick). Same lattice and "
        "scoring as the benchmarks.", "",
        "## Hyperparameters chosen, per season", "",
        md(pd.DataFrame([{"season": s, "q per week": c.q, "phi": c.phi, "p_season": c.p_season,
                          "sigma (pts)": c.sigma, "tuned on": ", ".join(map(str, c.seasons)),
                          **({"QB prior var": qb_choices[s]["p0"], "new QB prior": qb_choices[s]["new_mean"],
                              "pts per EPA/dropback": qb_choices[s].get("k_epa", 0.0),
                              "pts per EPA/dropback, observed": qb_choices[s].get("k_obs", 0.0),
                              "pts per draft score": qb_choices[s].get("k_draft", 0.0),
                              "HFA fitted": round(hfa_fitted[s], 2)} if s in qb_choices else {})}
                         for s, c in choices.items()])), "",
        f"## Reporting window, regular season {REPORT_SEASONS[0]}-{REPORT_SEASONS[-1]}", "",
        "The bar (`docs/MODEL_PLAN_NFL.md` §6): beat Elo on every row.", "",
        md(fmt(summarise(window, order=ORDER), cols)), "",
        "## Regular season, every scored season pooled", "",
        md(fmt(summarise(reg, order=ORDER), cols)), "",
        "## By season, regular", "",
        md(fmt(summarise(reg, ["season"], order=ORDER), cols)), "",
        "## By week bucket, regular season", "",
    ]
    r = reg.copy()
    r["week_bucket"] = evaluate.bucket(r["week"], nb.WEEK_BUCKETS, "wk")
    parts += [md(fmt(summarise(r, ["week_bucket"], order=ORDER), cols)), "",
              "## By closing spread, regular season", ""]
    r["spread_bucket"] = evaluate.bucket(r["abs_spread"], nb.SPREAD_BUCKETS, "|spread|")
    parts += [md(fmt(summarise(r, ["spread_bucket"], order=ORDER), cols)), ""]
    q = reg.dropna(subset=["qb_change"]).copy()
    if not q.empty:
        q["quarterback"] = np.where(q["qb_change"] == 1, "a side changed QB", "same quarterbacks")
        parts += ["## The quarterback test, regular season", "",
                  "Without a quarterback state the model loses about what Elo loses on these games; "
                  "step 4 (`state_qb`) is judged on closing that gap.", "",
                  md(fmt(summarise(q, ["quarterback"], order=ORDER), cols)), ""]
        qbs = scored.attrs.get("quarterbacks")
        if qbs is not None and not qbs.empty:
            show = pd.concat([qbs.head(8), qbs.tail(8)])[["quarterback", "points", "sd"]]
            show["points"], show["sd"] = show["points"].map("{:+.1f}".format), show["sd"].map("{:.1f}".format)
            parts += [f"### The quarterback states at the end of {seasons[-1]}", "",
                      f"{len(qbs)} quarterbacks carried; sd of their means {qbs['points'].std(ddof=1):.2f} points, "
                      f"middle 90% from {qbs['points'].quantile(0.05):+.1f} to {qbs['points'].quantile(0.95):+.1f}. "
                      "A quarterback's number is points per game against his team's offence; the top and bottom eight.",
                      "", md(show), ""]
    playoffs = scored[scored["season_type"] != "regular"]
    if not playoffs.empty:
        parts += ["## Playoffs (never fitted, always scored)", "", md(fmt(summarise(playoffs, order=ORDER), cols)), ""]
    parts += ["## Reliability, home-win probability (regular season)", ""]
    for name in ("state", "state_qb", "elo", "market"):
        d = reg[reg["model"] == name]
        if d.empty:
            continue
        t = scoring.reliability(d["p_home"], d["won"])
        parts += [f"### {name}", "", md(t.assign(forecast=t["forecast"].map("{:.3f}".format),
                                                 observed=t["observed"].map("{:.3f}".format),
                                                 gap=t["gap"].map("{:+.3f}".format))), ""]
    names = pd.concat([frame[["home_team_id", "home_team"]].rename(columns={"home_team_id": "team_id", "home_team": "team"}),
                       frame[["away_team_id", "away_team"]].rename(columns={"away_team_id": "team_id", "away_team": "team"})]
                      ).drop_duplicates("team_id", keep="last").set_index("team_id")["team"]
    last = finals[seasons[-1]].frame()
    last["team"] = last["team_id"].map(names)
    last = last.sort_values("net", ascending=False)
    show = pd.concat([last.head(8), last.tail(8)])[["team", "net", "off", "def", "sd_off", "sd_def"]]
    for c in ("net", "off", "def"):
        show[c] = show[c].map("{:+.1f}".format)
    for c in ("sd_off", "sd_def"):
        show[c] = show[c].map("{:.1f}".format)
    parts += [f"## End of {seasons[-1]}: the state's top and bottom eight by net", "",
              "`sd_*` is the filter's remaining uncertainty about the team, in points.", "", md(show), ""]
    return "\n".join(parts).rstrip() + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description="NFL state model, walk-forward")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--first-test-season", type=int, default=FIRST_TEST_SEASON)
    args = ap.parse_args()
    paths = config.paths()
    frame = research_sample(load_nfl_frame(paths.warehouse))
    from atlas.research.nfl_dataset import load_passer_games, load_players
    try:
        passers = load_passer_games(paths.warehouse)
    except Exception as error:  # noqa: BLE001 - an older warehouse has no passer log
        LOG.warning("no passer log in the warehouse (%s); new quarterbacks get the flat prior", error)
        passers = None
    scored, choices, finals, frame = walk_forward(frame, first_test_season=args.first_test_season, passers=passers,
                                                  players=load_players(paths.warehouse))
    out = args.out or (paths.root / "reports" / "nfl_state.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(scored, choices, finals, frame))
    save_choices(choices, scored.attrs.get("qb_choices", {}),
                 choices_path(paths.root) if args.out is None else out.with_suffix(".choices.json"))
    window = scored[(scored["season_type"] == "regular") & scored["season"].isin(REPORT_SEASONS)]
    LOG.info("wrote %s\n%s", out, evaluate.summarise(window, order=ORDER).to_string(index=False))


if __name__ == "__main__":
    main()
