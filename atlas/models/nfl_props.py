"""Atlas's own player projections for the NFL's props, walk-forward.

    python -m atlas.models.nfl_props            # walk forward and score; reports/nfl_props.md
    python -m atlas.models.nfl_props --tune     # tune the half-lives first, and save them

A player's stat is his **opportunity** times his **rate** times the **game**:

* **opportunity**: his share of his team's pass attempts (targets, or a
  quarterback's attempts) or rush attempts (carries), exponentially weighted
  over the games he played and shrunk toward his position's share for anyone
  new, times the team's weighted attempts a game before the kickoff;
* **rate**: yards per target, receptions per target, yards per carry, yards
  and touchdowns per attempt, touchdowns per touch - weighted the same way
  and shrunk toward the position's league rate the season before by a few
  dozen opportunities' worth of it;
* **the game**: a Poisson regression a season at a time on the three seasons
  before it, the opportunity times the rate as its offset, on home field, the
  opponent's allowance of the stat (its weighted stat allowed over the
  league's) and the team total the line implied over the league's. In the
  walk-forward the implied total is the closing line's; ahead, it is Atlas's
  own projection of the game.

Each count is a negative binomial about Atlas's mean at the dispersion
measured on the same three seasons (a Poisson where that is one or below),
which is what prices "at least N": P(over N - 1/2). An opportunity the
venue writes a market on (attempts, completions, carries) is a stat whose
rate per opportunity is one; scrimmage yards (:data:`COMBINED`) is the sum
of rushing and receiving, with its own dispersion fitted on the sum.

**The test**: P(over) at the common lines against a Poisson on the player's
season mean so far, on regular-season player-games with :data:`MIN_PRIOR`
games of the season behind them, from :data:`FIRST_REPORT`; the half-lives
and priors tuned once on :data:`TUNE`. The heavy refresh writes every
active player's state into ``data/warehouse/nfl_props_state.json``, which
the Polymarket US pricing reads (`atlas/polymarket/props.py`).
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from atlas import config
from atlas.models.nhl_props import _ew, logpmf, p_over, poisson_fit
from atlas.util import get_logger

LOG = get_logger(__name__)

VERSION = "nfl-props-v2"
#: The counts a prop is written on. The last three are opportunities priced as stats: an attempt's rate per
#: attempt is one, so the state carries them without a special case, and the layer fits the game on top.
STATS = ("receiving_yards", "receptions", "rushing_yards", "passing_yards", "touchdowns", "passing_tds",
         "completions", "attempts", "carries")
#: Stats the venue writes on a sum of others: the expectation is the sum of the parts', the spread its own.
COMBINED = {"scrimmage_yards": ("rushing_yards", "receiving_yards")}
#: What each stat is a rate of.
OPPORTUNITY = {"receiving_yards": "targets", "receptions": "targets", "rushing_yards": "carries",
               "passing_yards": "attempts", "passing_tds": "attempts", "touchdowns": "touches",
               "completions": "attempts", "attempts": "attempts", "carries": "carries", "scrimmage_yards": "touches"}
#: Each opportunity's share is of the team's pass or rush attempts.
OF_TEAM = {"targets": "pass_attempts", "attempts": "pass_attempts", "carries": "rush_attempts"}
TOUCHDOWNS = ("touchdowns", "passing_tds")
OPPORTUNITIES = ("targets", "carries", "attempts", "touches")
LINES = {"receiving_yards": (24.5, 49.5, 74.5), "receptions": (2.5, 4.5, 6.5), "rushing_yards": (24.5, 49.5, 74.5),
         "passing_yards": (199.5, 249.5, 299.5), "touchdowns": (0.5, 1.5), "passing_tds": (0.5, 1.5, 2.5),
         "completions": (17.5, 22.5, 27.5), "attempts": (24.5, 29.5, 34.5), "carries": (9.5, 14.5, 19.5),
         "scrimmage_yards": (49.5, 74.5, 99.5)}
WINDOW = 3
MIN_PRIOR = 3
TUNE = (2014, 2015, 2016)
FIRST_REPORT = 2017
#: A player is carried into the games ahead when his latest game is this recent.
ACTIVE_DAYS = 400
GRID = {"h_share": (1.0, 2.0, 4.0, 8.0, 16.0), "k_share": (0.25, 0.5, 1.0, 2.0, 4.0), "h_rate": (5.0, 10.0, 20.0, 40.0),
        "k_rate": (5.0, 20.0, 50.0, 150.0), "h_team": (4.0, 8.0, 16.0, 32.0, 64.0), "k_td": (1.0, 5.0, 20.0, 50.0)}
POSITIONS = ("QB", "RB", "WR", "TE")


@dataclass(frozen=True)
class Spec:
    h_share: float = 8.0        # games: the shares' half-life
    h_rate: float = 20.0        # games: the rates'
    k_rate: float = 50.0        # opportunities of the position's rate as the prior on a player's
    k_share: float = 2.0        # games of the position's share as the prior on a player's
    h_team: float = 8.0         # games: the teams' attempts and what they allow
    k_td: float = 1.0           # the touchdown rates' prior, as a multiple of k_rate: a rare event needs more


def spec_path(root: Path) -> Path:
    return root / "reports" / "nfl_props_spec.json"


def load_spec(root: Path) -> Spec:
    p = spec_path(root)
    if not p.exists():
        return Spec()
    raw = json.loads(p.read_text())
    return Spec(**{k: float(v) for k, v in raw.items() if k in Spec.__dataclass_fields__})


# ---------------------------------------------------------------------------
# The teams: attempts, and what each allows
# ---------------------------------------------------------------------------

TEAM_COLS = ["pass_attempts", "rush_attempts", *[f"allow_{s}" for s in STATS]]


def league_levels(teams: pd.DataFrame) -> pd.DataFrame:
    """The league's attempts, stats allowed and implied total per team-game, the season before."""
    g = teams.groupby("season")[[*TEAM_COLS, "implied_total"]].mean()
    first = g.iloc[[0]].copy()
    g.index = g.index + 1
    return pd.concat([first, g]).groupby(level=0).last()


def team_state(teams: pd.DataFrame, spec: Spec, *, prior: bool = True) -> pd.DataFrame:
    """Each team's weighted attempts a game and stats allowed, before each game (``prior``) or through it:
    the attempts as counts, the allowances as factors over the league's level the season before."""
    t = teams.assign(one=1.0)
    ew = _ew(t, "team", ["one", *TEAM_COLS], spec.h_team, prior=prior)
    level = league_levels(teams).reindex(teams["season"]).set_index(teams.index)
    out = pd.DataFrame(index=teams.index)
    n = ew["one"]
    for c in TEAM_COLS:
        per_game = (ew[c] + 10.0 * level[c]) / (n + 10.0)         # a team with no history is the league
        out[c + "_hat"] = per_game.fillna(level[c])
        if c.startswith("allow_"):
            out["f_" + c] = (per_game / level[c]).fillna(1.0)
    out["total_factor"] = (pd.to_numeric(teams["implied_total"], errors="coerce") / level["implied_total"]).fillna(1.0)
    return out


# ---------------------------------------------------------------------------
# The players
# ---------------------------------------------------------------------------


def position_priors(p: pd.DataFrame) -> pd.DataFrame:
    """Per season and position, the league's rates per opportunity and shares of the team's attempts the
    season before, among player-games with an opportunity."""
    reg = p[p["played"] & (p["season_type"] == "regular")]
    g = reg.groupby(["season", "position"])
    # A position with no opportunity of a stat (no quarterback was targeted) has a rate of none of it.
    out = pd.DataFrame({s: (g[s].sum() / g[OPPORTUNITY[s]].sum().replace(0, np.nan)).fillna(0.0) for s in STATS})
    for opp, team_col in OF_TEAM.items():
        share = reg[opp] / reg[team_col].replace(0, np.nan)
        out[f"share_{opp}"] = share.groupby([reg["season"], reg["position"]]).mean()
    out = out.reset_index()
    first = out[out["season"] == out["season"].min()].copy()
    out["season"] += 1
    return pd.concat([first, out], ignore_index=True).drop_duplicates(["season", "position"], keep="last")


def _state(p: pd.DataFrame, spec: Spec, *, prior: bool) -> pd.DataFrame:
    """Each player's shares of his team's attempts and rates per opportunity: before each game (``prior``)
    or through it. Games he did not appear in carry no weight: the state passes through them unchanged."""
    played = p[p["played"]]
    opps = list(OF_TEAM)
    vol = _ew(played.assign(one=1.0), "player_id", ["one", *opps, "pass_attempts", "rush_attempts"], spec.h_share,
              prior=prior)
    rate = _ew(played.assign(one=1.0), "player_id", list(dict.fromkeys(["one", *opps, "touches", *STATS])),
               spec.h_rate, prior=prior)
    pr = p[["season", "position"]].merge(position_priors(p), on=["season", "position"], how="left").set_index(p.index)
    st = pd.DataFrame(index=played.index)
    st["n"] = vol["one"]
    for opp in opps:
        team_col = OF_TEAM[opp]
        # His share of the team's attempts in the games he played, pulled toward his position's share.
        games = vol["one"]
        share = vol[opp] / vol[team_col].replace(0.0, np.nan)
        st[f"share_{opp}"] = (share.fillna(0.0) * games + spec.k_share * pr.loc[played.index, f"share_{opp}"]) \
            / (games + spec.k_share)
    for s in STATS:
        den = rate[OPPORTUNITY[s]]
        k = spec.k_rate * (spec.k_td if s in TOUCHDOWNS else 1.0)
        st[f"{s}_rate"] = (rate[s] + k * pr.loc[played.index, s]) / (den + k)
    out = st.reindex(p.index).groupby(p["player_id"]).ffill()
    out["n"] = out["n"].fillna(0.0)
    for opp in opps:
        out[f"share_{opp}"] = out[f"share_{opp}"].fillna(pr[f"share_{opp}"])
    for s in STATS:
        out[f"{s}_rate"] = out[f"{s}_rate"].fillna(pr[s])
    return out


def features(players: pd.DataFrame, teams: pd.DataFrame, spec: Spec) -> pd.DataFrame:
    """Every player-game with what was known before it: the player's shares and rates, his team's attempts,
    the opponent's allowances, home, the implied total's factor, and the season mean so far for the naive
    baseline."""
    p = players.sort_values(["player_id", "kickoff", "game_id"], kind="stable").reset_index(drop=True)
    p = p.assign(position=p["position"].where(p["position"].isin(POSITIONS), "WR"))
    # A count cannot be negative: a game of minus three rushing yards is a game of none to the model.
    for s in STATS:
        p[s] = pd.to_numeric(p[s], errors="coerce").fillna(0.0).clip(lower=0.0)
    t = teams.sort_values(["team", "kickoff", "game_id"], kind="stable").reset_index(drop=True)
    ts = pd.concat([t[["game_id", "team"]], team_state(t, spec, prior=True)], axis=1)
    # The team's actual attempts in each game, for the shares the state takes.
    actual = t[["game_id", "team", "pass_attempts", "rush_attempts"]]
    p = p.merge(actual, on=["game_id", "team"], how="left")
    p[["pass_attempts", "rush_attempts"]] = p[["pass_attempts", "rush_attempts"]].fillna(0.0)
    p = pd.concat([p, _state(p, spec, prior=True)], axis=1)
    own = ts[["game_id", "team", "pass_attempts_hat", "rush_attempts_hat", "total_factor"]]
    opp = ts.rename(columns={"team": "opponent", **{f"f_allow_{s}": f"opp_{s}" for s in STATS}})
    opp = opp[["game_id", "opponent", *[f"opp_{s}" for s in STATS]]]
    p = p.merge(own, on=["game_id", "team"], how="left").merge(opp, on=["game_id", "opponent"], how="left")
    p["pass_attempts_hat"] = p["pass_attempts_hat"].fillna(32.0)
    p["rush_attempts_hat"] = p["rush_attempts_hat"].fillna(26.0)
    p["total_factor"] = p["total_factor"].fillna(1.0).clip(0.5, 1.8)
    p["targets_hat"] = p["share_targets"] * p["pass_attempts_hat"]
    p["attempts_hat"] = p["share_attempts"] * p["pass_attempts_hat"]
    p["carries_hat"] = p["share_carries"] * p["rush_attempts_hat"]
    p["touches_hat"] = p["targets_hat"] + p["carries_hat"]
    for s in STATS:
        p[f"opp_{s}"] = p[f"opp_{s}"].fillna(1.0).clip(0.6, 1.6)
        p[f"base_{s}"] = p[f"{OPPORTUNITY[s]}_hat"] * p[f"{s}_rate"]
    p["home"] = p["home"].astype(float)
    for name, parts in COMBINED.items():
        p[name] = sum(p[s] for s in parts)
    played = p[p["played"]]
    cols = list(dict.fromkeys([*STATS, *COMBINED, *OPPORTUNITIES]))
    cum = played.groupby(["player_id", "season"])[cols].cumsum() - played[cols]
    cnt = played.groupby(["player_id", "season"]).cumcount()
    for s in cols:
        p.loc[played.index, f"naive_{s}"] = cum[s] / cnt.replace(0, np.nan)
    p.loc[played.index, "n_season"] = cnt.to_numpy(dtype=float)
    p["n_season"] = p["n_season"].fillna(0.0)
    return p


# ---------------------------------------------------------------------------
# The layer: the game around the base expectation
# ---------------------------------------------------------------------------


def design(frame: pd.DataFrame, stat: str) -> np.ndarray:
    return np.column_stack([np.ones(len(frame)), frame["home"].to_numpy(float),
                            np.log(frame[f"opp_{stat}"].to_numpy(float)),
                            np.log(frame["total_factor"].to_numpy(float))])


def offset(frame: pd.DataFrame, stat: str) -> np.ndarray:
    return np.log(np.clip(frame[f"base_{stat}"].to_numpy(float), 1e-3, None))


def mean(frame: pd.DataFrame, stat: str, layer: dict) -> np.ndarray:
    beta = np.asarray(layer[stat]["beta"])
    return np.exp(np.clip(offset(frame, stat) + design(frame, stat) @ beta, -30, 30))


def fit_season(p: pd.DataFrame, season: int) -> dict:
    """The layer for ``season`` from the three seasons before it: each stat's coefficients and its dispersion
    about the fitted mean, on the player-games whose position carries the stat.

    Fitted on the player-games with :data:`MIN_PRIOR` games of their season behind them - the ones the model
    is scored on and a main line is priced on. The first weeks of a season are left out because a role
    changes between seasons and the state carried over does not know it yet: a quarterback who lost his job
    throws nothing against last year's share, and an intercept fitted through those games would take a
    twentieth off every starter's number (it did: 6% low on passing yards walk-forward)."""
    seasons = range(max(season - WINDOW, int(p["season"].min())), season)
    if not len(seasons):
        seasons = [season]
    train = p[p["season"].isin(list(seasons)) & (p["season_type"] == "regular") & p["played"]
              & (p["n_season"] >= MIN_PRIOR)]
    if len(train) < 200:
        train = p[p["season"].isin(list(seasons)) & (p["season_type"] == "regular") & p["played"] & (p["n"] >= 1)]
    out: dict = {}
    for stat in STATS:
        rows = train[train[f"base_{stat}"] > 0.05]
        if len(rows) < 200:
            rows = train
        x, y = design(rows, stat), rows[stat].to_numpy(float)
        beta = poisson_fit(x, y, offset(rows, stat))
        mu = np.exp(np.clip(offset(rows, stat) + x @ beta, -30, 30))
        out[stat] = {"beta": beta.tolist(), "dispersion": float(max(1.0, ((y - mu) ** 2).sum() / mu.sum()))}
    for name, parts in COMBINED.items():
        rows = train[train[f"base_{parts[0]}"] + train[f"base_{parts[1]}"] > 0.05]
        if len(rows) < 200:
            rows = train
        mu = sum(mean(rows, s, out) for s in parts)
        y = sum(rows[s].to_numpy(float) for s in parts)
        out[name] = {"dispersion": float(max(1.0, ((y - mu) ** 2).sum() / mu.sum()))}
    return out


# ---------------------------------------------------------------------------
# The walk-forward
# ---------------------------------------------------------------------------


def walk(players: pd.DataFrame, teams: pd.DataFrame, spec: Spec, seasons) -> tuple[pd.DataFrame, dict]:
    """Atlas's expectation for every regular-season player-game of ``seasons``, each from its own layer."""
    f = features(players, teams, spec)
    layers, parts = {}, []
    for season in seasons:
        layer = fit_season(f, season)
        layers[season] = layer
        rows = f[(f["season"] == season) & (f["season_type"] == "regular") & f["played"]].copy()
        for stat in STATS:
            rows[f"mu_{stat}"] = mean(rows, stat, layer)
        for name, of in COMBINED.items():
            rows[f"mu_{name}"] = sum(rows[f"mu_{s}"] for s in of)
        parts.append(rows)
    return (pd.concat(parts, ignore_index=True) if parts else f.iloc[0:0]), layers


#: The opportunities a game a player must have averaged so far in the season for a stat of his to be
#: scored: a quarterback is not scored on receiving yards, nor a fourth receiver on touchdowns. On the
#: season's record, not on Atlas's expectation, so the half-lives do not choose the rows they are judged on.
SCORED_OPPORTUNITY = {"targets": 2.0, "carries": 3.0, "attempts": 10.0, "touches": 5.0}


def _scored(rows: pd.DataFrame, stat: str) -> pd.DataFrame:
    """The player-games a stat is scored on: enough of the season behind them, and a real chance of the
    stat (:data:`SCORED_OPPORTUNITY`)."""
    opp = OPPORTUNITY[stat]
    return rows[(rows["n_season"] >= MIN_PRIOR) & rows[f"naive_{stat}"].notna()
                & (rows[f"naive_{opp}"] >= SCORED_OPPORTUNITY[opp])]


def score(rows: pd.DataFrame, layers: dict) -> pd.DataFrame:
    """Per stat and line: Brier and log loss of P(over) by Atlas and by a Poisson on the season mean so far,
    each one's mean against the rate observed, and the mean absolute error of each expectation."""
    out = []
    for stat, lines in LINES.items():
        f = _scored(rows, stat)
        if f.empty:
            continue
        y_val = f[stat].to_numpy(float)
        mae = {"atlas": float(np.abs(y_val - f[f"mu_{stat}"].to_numpy(float)).mean()),
               "naive": float(np.abs(y_val - f[f"naive_{stat}"].to_numpy(float)).mean())}
        for line in lines:
            y = (y_val > line).astype(float)
            p_atlas = np.empty(len(f))
            for season in f["season"].unique():
                m = (f["season"] == season).to_numpy()
                p_atlas[m] = p_over(f[f"mu_{stat}"].to_numpy(float)[m], line, layers[season][stat]["dispersion"])
            p_naive = p_over(f[f"naive_{stat}"].to_numpy(float), line, 1.0)
            row = {"stat": stat, "line": line, "n": int(len(f)), "observed": float(y.mean()),
                   "mae_atlas": mae["atlas"], "mae_naive": mae["naive"]}
            for name, p in (("atlas", p_atlas), ("naive", p_naive)):
                q = np.clip(p, 1e-6, 1 - 1e-6)
                row[f"brier_{name}"] = float(((p - y) ** 2).mean())
                row[f"logloss_{name}"] = float(-(y * np.log(q) + (1 - y) * np.log(1 - q)).mean())
                row[f"mean_{name}"] = float(p.mean())
            out.append(row)
    return pd.DataFrame(out)


def loglik(rows: pd.DataFrame, layers: dict) -> float:
    total, n = 0.0, 0
    for stat in STATS:
        f = _scored(rows, stat)
        for season in f["season"].unique():
            m = (f["season"] == season).to_numpy()
            ll = logpmf(f[stat].to_numpy(float)[m], f[f"mu_{stat}"].to_numpy(float)[m],
                        layers[season][stat]["dispersion"])
            total += float(np.sum(ll))
            n += int(m.sum())
    return total / max(n, 1)


def tune(players: pd.DataFrame, teams: pd.DataFrame, base: Spec | None = None) -> tuple[Spec, list[dict]]:
    """One coordinate at a time over :data:`GRID`, on the tuning seasons' log-likelihood."""
    spec, trials = base or Spec(), []
    for name, values in GRID.items():
        best = None
        for v in values:
            trial = replace(spec, **{name: v})
            rows, layers = walk(players, teams, trial, TUNE)
            ll = loglik(rows, layers)
            trials.append({**asdict(trial), "loglik": ll})
            LOG.info("nfl props tune: %s=%g loglik %.5f", name, v, ll)
            if best is None or ll > best[0]:
                best = (ll, trial)
        spec = best[1]
    return spec, trials


# ---------------------------------------------------------------------------
# The games ahead
# ---------------------------------------------------------------------------

PLAYER_STATE = ["player_id", "player", "position", "team", "kickoff", "n", "n_season", "share_targets",
                "share_carries", "share_attempts", *[f"{s}_rate" for s in STATS]]
TEAM_STATE = ["team", "pass_attempts_hat", "rush_attempts_hat", *[f"f_allow_{s}" for s in STATS]]


def snapshot(players: pd.DataFrame, teams: pd.DataFrame, now, spec: Spec | None = None) -> dict:
    """Everything a game ahead needs, as it stands after the latest game: each active player's shares and
    rates on the team he last played for, each team's attempts and allowances, the league's implied total,
    and the season's layer."""
    spec = spec or Spec()
    t = pd.Timestamp(now)
    t = t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")
    season = t.year if t.month >= 8 else t.year - 1
    f = features(players, teams, spec)
    layer = fit_season(f, season)
    p = players.sort_values(["player_id", "kickoff", "game_id"], kind="stable").reset_index(drop=True)
    p = p.assign(position=p["position"].where(p["position"].isin(POSITIONS), "WR"))
    tt = teams.sort_values(["team", "kickoff", "game_id"], kind="stable").reset_index(drop=True)
    p = p.merge(tt[["game_id", "team", "pass_attempts", "rush_attempts"]], on=["game_id", "team"], how="left")
    p[["pass_attempts", "rush_attempts"]] = p[["pass_attempts", "rush_attempts"]].fillna(0.0)
    after = pd.concat([p, _state(p, spec, prior=False)], axis=1)
    played = after[after["played"]]
    season_n = played[played["season"] == season].groupby("player_id").size()
    latest = after.groupby("player_id", sort=False).tail(1).copy()
    latest["n_season"] = latest["player_id"].map(season_n).fillna(0.0)
    recent = pd.to_datetime(latest["kickoff"], utc=True) >= (t - pd.Timedelta(days=ACTIVE_DAYS))
    latest = latest[recent & (latest["n"] > 0)]
    ts = pd.concat([tt[["team", "season"]], team_state(tt, spec, prior=False)], axis=1)
    team_now = ts.groupby("team", sort=False).tail(1)
    lv = league_levels(teams)
    level = lv.loc[season] if season in lv.index else lv.iloc[-1]
    return {"version": VERSION, "season": int(season), "built_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
            "players": latest[PLAYER_STATE].reset_index(drop=True), "teams": team_now[TEAM_STATE].reset_index(drop=True),
            "level": {"implied_total": float(level["implied_total"])}, "layer": layer, "spec": asdict(spec)}


#: ESPN's injury statuses, lowercased, to the chance the player takes the field. Stated, not fitted: the
#: capture (atlas/sources/nba_availability.py, the NFL's feed) is building the archive to fit them on.
AVAILABILITY = {"out": 0.02, "doubtful": 0.1, "injured reserve": 0.0, "suspension": 0.0, "questionable": 0.75}


def adjust(snap: dict, availability: pd.DataFrame | None) -> dict:
    """The snapshot with the injury report applied: each player gets ``p_play``, his chance of taking the
    field, and ``status`` as listed, found by name on the team the report lists him on. The snapshot given
    is not changed."""
    from atlas.models.nba_props import name_key
    from atlas.staging.nfl.games import code_of

    players = snap["players"].copy()
    players["p_play"] = 1.0
    players["status"] = ""
    if availability is None or len(availability) == 0 or players.empty:
        return {**snap, "players": players}
    listed: dict[tuple[str, str], str] = {}
    for r in availability.itertuples(index=False):
        status = str(r.status or "").strip().lower()
        if status in AVAILABILITY:
            listed[(code_of(getattr(r, "team_abbr", None)), name_key(r.player))] = status
    if not listed:
        return {**snap, "players": players}
    keys = [(str(t), name_key(n)) for t, n in zip(players["team"], players["player"], strict=True)]
    status = pd.Series([listed.get(k, "") for k in keys], index=players.index)
    players["status"] = status
    players["p_play"] = status.map(lambda x: AVAILABILITY.get(x, 1.0)).astype(float)
    return {**snap, "players": players}


def expect(snap: dict, player, team: str, opponent: str, home: bool, implied_total: float | None = None) -> dict[str, float]:
    """Atlas's expectation of each stat for one player (a :data:`PLAYER_STATE` row) on ``team`` against
    ``opponent``, at ``implied_total`` (the team's, from Atlas's projection; the league's when unknown);
    nan when a team is not known."""
    teams = snap["teams"].set_index("team")
    if team not in teams.index or opponent not in teams.index:
        return _nothing()
    own, opp = teams.loc[team], teams.loc[opponent]
    level = float(snap["level"]["implied_total"]) or 22.0
    factor = float(np.clip((implied_total if implied_total is not None else level) / level, 0.5, 1.8))
    targets = float(player["share_targets"]) * float(own["pass_attempts_hat"])
    attempts = float(player["share_attempts"]) * float(own["pass_attempts_hat"])
    carries = float(player["share_carries"]) * float(own["rush_attempts_hat"])
    opportunity = {"targets": targets, "attempts": attempts, "carries": carries, "touches": targets + carries}
    layer = snap["layer"]
    # A stat the snapshot does not carry yet (one written before the stat was added) is nan, not an error.
    stats = [s for s in STATS if s in layer and f"f_allow_{s}" in opp.index and f"{s}_rate" in player]
    f = pd.DataFrame([{"home": 1.0 if home else 0.0, "total_factor": factor,
                       **{f"opp_{s}": float(np.clip(opp[f"f_allow_{s}"], 0.6, 1.6)) for s in stats},
                       **{f"base_{s}": opportunity[OPPORTUNITY[s]] * float(player[f"{s}_rate"]) for s in stats}}])
    out = _nothing()
    out.update({s: float(mean(f, s, layer)[0]) for s in stats})
    for name, parts in COMBINED.items():
        out[name] = float(sum(out[s] for s in parts))
    return out


def _nothing() -> dict[str, float]:
    return dict.fromkeys([*STATS, *COMBINED], float("nan"))


def prob(mean_: float, line: float, side: str, dispersion: float) -> float:
    """Atlas's probability of ``side`` (over or under) at ``line``; a tie on a whole-number line is neither."""
    whole = float(line).is_integer()
    over = float(p_over([mean_], line, dispersion)[0])
    under = 1.0 - float(p_over([mean_], line - 1 if whole else line, dispersion)[0])
    return over if side == "over" else under


def dispersion(snap: dict, stat: str) -> float:
    """The negative binomial's dispersion for ``stat``; nan where the snapshot has none for it."""
    return float((snap["layer"].get(stat) or {}).get("dispersion", float("nan")))


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------


def state_path(warehouse: Path | None = None) -> Path:
    return (warehouse or config.paths().warehouse) / "nfl_props_state.json"


def save_state(snap: dict, where: Path | None = None) -> Path:
    where = where or state_path()
    where.parent.mkdir(parents=True, exist_ok=True)
    data = {**snap, "players": json.loads(snap["players"].to_json(orient="records", date_format="iso")),
            "teams": json.loads(snap["teams"].to_json(orient="records"))}
    where.write_text(json.dumps(data) + "\n")
    return where


def load_state(where: Path | None = None) -> dict | None:
    where = where or state_path()
    if not where.exists():
        return None
    raw = json.loads(where.read_text())
    return {**raw, "players": pd.DataFrame(raw["players"], columns=PLAYER_STATE),
            "teams": pd.DataFrame(raw["teams"], columns=TEAM_STATE)}


def load_tables(warehouse: Path | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    from atlas.research.nfl_dataset import load_table

    return load_table("player_games", warehouse), load_table("team_weeks", warehouse)


def publish(now, *, root: Path | None = None, warehouse: Path | None = None) -> int:
    """The heavy refresh's step: the snapshot written where the pricing reads it. Returns the players in it."""
    root = root or config.paths().root
    players, teams = load_tables(warehouse)
    snap = snapshot(players, teams, now, load_spec(root))
    save_state(snap, state_path(warehouse))
    return int(len(snap["players"]))


def write_report(spec: Spec, table: pd.DataFrame, root: Path) -> Path:
    lines = ["# NFL player projections, walk-forward", "",
             f"Regular season, {FIRST_REPORT} to the last complete season, player-games with at least {MIN_PRIOR} "
             "games of the season behind them and a real chance of the stat (two targets, three carries, ten pass "
             "attempts or five touches a game so far that season). Atlas is opportunity times a rate "
             "times the game (`atlas/models/nfl_props.py`); the baseline is a Poisson on the player's season "
             "mean so far. Brier and log loss of P(over) at each line, and the mean absolute error of each "
             "expectation.", "",
             f"Half-lives: shares {spec.h_share:g} games with a prior of {spec.k_share:g} games of the position's "
             f"share, rates {spec.h_rate:g} games with a prior of {spec.k_rate:g} opportunities of the position's "
             f"rate ({spec.k_td:g} times that for the touchdown rates), the teams {spec.h_team:g} games.", "",
             "| stat | line | n | observed | mean_atlas | mean_naive | brier_atlas | brier_naive | logloss_atlas | "
             "logloss_naive | mae_atlas | mae_naive |", "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in table.itertuples():
        lines.append(f"| {r.stat} | {r.line:g} | {r.n} | {100 * r.observed:.1f} | {100 * r.mean_atlas:.1f} | "
                     f"{100 * r.mean_naive:.1f} | {r.brier_atlas:.4f} | {r.brier_naive:.4f} | {r.logloss_atlas:.4f} | "
                     f"{r.logloss_naive:.4f} | {r.mae_atlas:.3f} | {r.mae_naive:.3f} |")
    better = int((table["brier_atlas"] < table["brier_naive"]).sum())
    lines += ["", f"Atlas's Brier beats the season-mean Poisson's at {better} of {len(table)} stat-lines.", ""]
    out = root / "reports" / "nfl_props.md"
    out.write_text("\n".join(lines))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="NFL player projections, walk-forward")
    ap.add_argument("--tune", action="store_true", help="tune the half-lives on the tuning seasons first, and save them")
    ap.add_argument("--raw", action="store_true", help="build the tables from the nflverse cache, not the warehouse")
    args = ap.parse_args(argv)
    root = config.paths().root
    if args.raw:
        from atlas.staging.nfl import players as staging

        players, teams = staging.build(config.paths().raw)
    else:
        players, teams = load_tables()
    spec = load_spec(root)
    if args.tune:
        spec, _ = tune(players, teams, spec)
        spec_path(root).write_text(json.dumps(asdict(spec), indent=1) + "\n")
        LOG.info("nfl props: tuned %s", asdict(spec))
    last = int(players.loc[players["season_type"] == "regular", "season"].max())
    seasons = range(FIRST_REPORT, last)                        # complete seasons only
    rows, layers = walk(players, teams, spec, seasons)
    table = score(rows, layers)
    print(table.to_string())
    print("wrote", write_report(spec, table, root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
