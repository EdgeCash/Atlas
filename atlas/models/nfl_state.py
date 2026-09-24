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
    "q": (0.0, 0.5, 1.0, 2.0, 4.0),
    "phi": (0.5, 0.67, 0.85),
    "p_season": (10.0, 25.0, 50.0),
    "sigma": (8.5, 9.5, 10.5),
}
ORDER = ("naive", "elo", "atlas_epa", "state", "market")


@dataclass(frozen=True)
class Choice:
    q: float
    phi: float
    p_season: float
    sigma: float
    loglik: float
    seasons: tuple[int, ...]


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


def new_season(state: kalman.State, phi: float, p_season: float) -> None:
    """Regress every strength toward the mean and widen its uncertainty. In place."""
    state.x *= phi
    state.P *= phi ** 2
    state.P[np.diag_indices_from(state.P)] += p_season
    state.week = None


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
                 min_train_seasons: int = 2):
    """Tune on the past, forecast the season, score beside the references."""
    frame = nb.with_qb_change(elo.attach(frame)).sort_values(["kickoff", "game_id"]).reset_index(drop=True)
    all_seasons = [int(s) for s in sorted(frame["season"].unique())]
    scored, choices, finals = [], {}, {}
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
        s = evaluate.score(test, {**keep, "state": state_fc}, grid_, season=season)
        s["qb_change"] = np.tile(test["qb_change"].to_numpy(), len(keep) + 1)
        scored.append(s)
        LOG.info("season %s: q=%.1f phi=%.2f p_season=%.0f sigma=%.1f (tuned on %s); base %.1f hfa %.2f; %d games",
                 season, choice.q, choice.phi, choice.p_season, choice.sigma, choice.seasons,
                 levels[season][0], levels[season][1], len(test))
    return pd.concat(scored, ignore_index=True), choices, finals, frame


def render(scored: pd.DataFrame, choices: dict[int, Choice], finals: dict[int, kalman.State],
           frame: pd.DataFrame) -> str:
    md, fmt, summarise = evaluate.markdown, evaluate.formatted, evaluate.summarise
    cols = ["crps", "brier", "log_margin", "mae", "ece"]
    seasons = sorted(choices)
    reg = scored[scored["season_type"] == "regular"]
    window = reg[reg["season"].isin(REPORT_SEASONS)]
    parts = [
        "# NFL state model", "",
        f"Walk-forward, seasons {seasons[0]}-{seasons[-1]}. The filter runs continuously from 2011; each new "
        "season regresses every team's offence and defence toward the mean by `phi` and widens their "
        "uncertainty by `p_season`, and every game is forecast strictly before kickoff and then assimilated "
        "(`atlas/models/kalman.py`). Hyperparameters are chosen on the earlier seasons only. No quarterback "
        "state yet. Same lattice and scoring as the benchmarks.", "",
        "## Hyperparameters chosen, per season", "",
        md(pd.DataFrame([{"season": s, "q per week": c.q, "phi": c.phi, "p_season": c.p_season,
                          "sigma (pts)": c.sigma, "tuned on": ", ".join(map(str, c.seasons))}
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
                  "Without a quarterback state the model should lose about what Elo loses on these games; "
                  "step 4 is judged on closing that gap.", "",
                  md(fmt(summarise(q, ["quarterback"], order=ORDER), cols)), ""]
    playoffs = scored[scored["season_type"] != "regular"]
    if not playoffs.empty:
        parts += ["## Playoffs (never fitted, always scored)", "", md(fmt(summarise(playoffs, order=ORDER), cols)), ""]
    parts += ["## Reliability, home-win probability (regular season)", ""]
    for name in ("state", "elo", "market"):
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
    scored, choices, finals, frame = walk_forward(frame, first_test_season=args.first_test_season)
    out = args.out or (paths.root / "reports" / "nfl_state.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(scored, choices, finals, frame))
    window = scored[(scored["season_type"] == "regular") & scored["season"].isin(REPORT_SEASONS)]
    LOG.info("wrote %s\n%s", out, evaluate.summarise(window, order=ORDER).to_string(index=False))


if __name__ == "__main__":
    main()
