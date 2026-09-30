"""Atlas's own player projections for the NHL's props, walk-forward (docs/MODEL_PLAN_NHL.md, step 8).

    python -m atlas.models.nhl_props           # tune on 2017-20, report 2022-23 on; reports/nhl_props.{json,md}

Before each game, from the player's own games and the teams', every one of them earlier than it:

* **ice time**: the player's exponentially weighted time on ice (reliability 0.99 in §3: the most
  projectable number in the sport);
* **rates per second of ice** of shots on goal, assists, blocked shots and hits: exponentially weighted,
  shrunk toward the position's league rate (forward or defenceman, the season before) by a few games'
  worth of it;
* **shooting percentage**: goals over shots on the same terms, shrunk far harder (reliability 0.46);
* **the opponent**: its weighted shots on goal against (for shots), goals against (goals and assists) and
  shot attempts (for blocks); the team's own goals for (assists);
* **the arena**: the home team's scorekeeper, its home games' totals over its road games', the two seasons
  before (hits 0.81 to 1.30 of the league's in §3; shots and blocks less);
* **home or road**.

Each stat's expectation is ice time times rate times each factor to a power, and the powers and a level are
fitted by a Poisson regression (the ice time and rate as its offset) a season at a time on the three before
it, as the expected goals are. Goals are the expected shots times the shooting percentage; points are
goals and assists. A goalie's **saves**, given he starts, are the opponent's weighted shots on goal times
the team's shots against over the league's, times his own save percentage shrunk hard toward the league's,
fitted the same way. Each count is a negative binomial around Atlas's mean at the dispersion measured
around it on the same three seasons (a Poisson where that is one or below).

**The test** (§7 of the plan): P(over) at the common lines against a Poisson on the player's season mean
so far, on regular-season player-games with five games of the season behind them, 2022-23 on; the
half-lives and the prior weights tuned once on 2017-18 to 2019-20. Against the market only on the prop
lines the owner capture has recorded since opening night, when there are enough of them.

Shown beside the market's fair value in the pick'em (`atlas/owner/pickem.py`), never instead of it,
until a walk-forward says it is better than the market.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass, replace
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as sps

from atlas import config
from atlas.util import get_logger

LOG = get_logger(__name__)

VERSION = "nhl-props-v1"
WINDOW = 3
FIRST_REPORT = 2022
TUNE = (2017, 2018, 2019)
MIN_PRIOR = 5
#: The skater stats (the pick'em's names), and the lines each is scored at.
SKATER = ("shots", "goals", "assists", "points", "blocks", "hits")
LINES = {"shots": (1.5, 2.5, 3.5), "goals": (0.5,), "assists": (0.5,), "points": (0.5, 1.5), "blocks": (0.5, 1.5),
         "hits": (1.5, 2.5), "saves": (24.5, 25.5, 26.5, 27.5)}
#: Each stat's factors, by the columns :func:`features` makes.
FACTORS = {"shots": ("opp_sa", "arena_sog"), "assists": ("team_gf", "opp_ga"), "blocks": ("opp_cf", "arena_blk"),
           "hits": ("arena_hits",), "goals": ("opp_ga",), "saves": ()}


@dataclass(frozen=True)
class Spec:
    """Tuned on 2017-18 to 2019-20 (reports/nhl_props.md): a light prior on the rates (players differ, hits most),
    the ice time recent."""
    h_toi: float = 5.0          # games: the ice time's half-life
    h_rate: float = 40.0        # games: the rates'
    k_rate: float = 5.0         # games of the position's rate as the prior
    h_sh: float = 150.0         # games: the shooting percentage's
    k_sh: float = 100.0         # shots of the position's shooting percentage as its prior
    h_team: float = 25.0        # games: the teams'
    h_sv: float = 60.0          # games: a goalie's save percentage's
    k_sv: float = 3000.0        # shots of the league's save percentage as its prior
    k_arena: float = 40.0       # games that pull an arena's factor halfway to one


def json_path(root: Path) -> Path:
    return root / "reports" / "nhl_props.json"


def report_path(root: Path) -> Path:
    return root / "reports" / "nhl_props.md"


# ---------------------------------------------------------------------------
# Weighted sums, every one strictly before the game
# ---------------------------------------------------------------------------


def _alpha(h: float) -> float:
    return 1.0 - 0.5 ** (1.0 / h)


def _ew(frame: pd.DataFrame, key: str, cols: list[str], h: float, *, prior: bool = True) -> pd.DataFrame:
    """Exponentially weighted sums of ``cols`` within ``key`` (rows in time order), the latest game weighted
    one: before each row (``prior``), or through it (the state for the next game)."""
    inc = frame.groupby(key, sort=False)[cols].ewm(alpha=_alpha(h), adjust=True).sum()
    inc = inc.reset_index(level=0, drop=True).sort_index()
    if not prior:
        return inc
    return inc.groupby(frame[key]).shift(1).fillna(0.0)


def season_of(game_id) -> pd.Series:
    return (pd.to_numeric(game_id) // 1_000_000).astype(int)


def game_type(game_id) -> pd.Series:
    return ((pd.to_numeric(game_id) // 10_000) % 100).astype(int)


# ---------------------------------------------------------------------------
# The teams and the arenas
# ---------------------------------------------------------------------------


def team_frame(team_games: pd.DataFrame) -> pd.DataFrame:
    """One row per team-game: shots on goal for and against, shot attempts for, goals for and against."""
    t = team_games.copy()
    pick = lambda prefix: [c for c in t.columns if c.startswith(prefix)]  # noqa: E731
    out = pd.DataFrame({"game_id": t["game_id"], "team": t["team"], "opponent": t["opponent"],
                        "kickoff": pd.to_datetime(t["kickoff"], utc=True, errors="coerce"),
                        "sf": t[pick("sog_")].sum(axis=1), "sa": t[pick("soga_")].sum(axis=1),
                        "cf": t[pick("corsi_")].sum(axis=1), "gf": t[pick("goals_")].sum(axis=1),
                        "ga": t[pick("goalsa_")].sum(axis=1)})
    out["season"] = season_of(out["game_id"])
    return out.sort_values(["team", "kickoff", "game_id"]).reset_index(drop=True)


def team_state(teams: pd.DataFrame, spec: Spec, *, prior: bool = True) -> pd.DataFrame:
    """Each team's weighted shots for and against, attempts for, goals for and against per game."""
    cols = ["sf", "sa", "cf", "gf", "ga"]
    ew = _ew(teams.assign(one=1.0), "team", ["one", *cols], spec.h_team, prior=prior)
    n = ew["one"].replace(0.0, np.nan)
    return pd.DataFrame({c: ew[c] / n for c in cols}, index=teams.index)


def league(teams: pd.DataFrame) -> pd.DataFrame:
    """Per season, the league's per-team-game means; each season's row is the season before's (the level a
    game is measured against, known before it)."""
    reg = teams[game_type(teams["game_id"]) == 2]
    means = reg.groupby("season")[["sf", "sa", "cf", "gf", "ga"]].mean()
    means.index = means.index + 1
    first = means.index.min() - 1
    if first in reg["season"].values:
        means.loc[first] = reg[reg["season"] == first][["sf", "sa", "cf", "gf", "ga"]].mean()
    return means.sort_index()


def arenas(skaters: pd.DataFrame, teams: pd.DataFrame, spec: Spec) -> pd.DataFrame:
    """Per season and home team, its scorekeeper: the game totals of hits, blocked shots and shots on goal in its
    home games over those in its road games, the two seasons before, pulled toward one by
    :attr:`Spec.k_arena` games."""
    totals = skaters.groupby("game_id")[["hits", "blocks"]].sum()
    shots = teams.groupby("game_id")["sf"].sum()
    home = skaters[skaters["home_road"] == "H"].drop_duplicates("game_id").set_index("game_id")["team"]
    road = skaters[skaters["home_road"] == "R"].drop_duplicates("game_id").set_index("game_id")["team"]
    g = pd.DataFrame({"hits": totals["hits"], "blocks": totals["blocks"], "sog": shots}).join(
        home.rename("home"), how="inner").join(road.rename("road"), how="inner")
    g = g[game_type(g.index.to_series()) == 2]
    g["season"] = season_of(g.index.to_series())
    rows = []
    seasons = sorted(g["season"].unique())
    for s in [*seasons, seasons[-1] + 1]:
        past = g[g["season"].isin([s - 1, s - 2])]
        if past.empty:
            continue
        for team in sorted(set(past["home"]) | set(past["road"])):
            at_home, away = past[past["home"] == team], past[past["road"] == team]
            n = min(len(at_home), len(away))
            row = {"season": s, "arena": team}
            for stat in ("hits", "blocks", "sog"):
                if n == 0 or away[stat].mean() <= 0:
                    row[f"arena_{stat}"] = 1.0
                    continue
                ratio = at_home[stat].mean() / away[stat].mean()
                row[f"arena_{stat}"] = 1.0 + (ratio - 1.0) * n / (n + spec.k_arena)
            rows.append(row)
    out = pd.DataFrame(rows).rename(columns={"arena_blocks": "arena_blk"})
    return out


# ---------------------------------------------------------------------------
# The skaters' features
# ---------------------------------------------------------------------------


def skater_frame(skater_games: pd.DataFrame) -> pd.DataFrame:
    s = skater_games.copy()
    s["season"] = season_of(s["game_id"])
    s["gtype"] = game_type(s["game_id"])
    s["pos"] = np.where(s["position"].astype(str) == "D", "D", "F")
    for c in ("toi", "shots", "goals", "assists", "points", "blocks", "hits"):
        s[c] = pd.to_numeric(s[c], errors="coerce").fillna(0.0)
    return s.sort_values(["player_id", "date", "game_id"]).reset_index(drop=True)


def position_rates(s: pd.DataFrame) -> pd.DataFrame:
    """Per season and position, the league's per-second rates, ice time and shooting percentage the season
    before."""
    reg = s[s["gtype"] == 2]
    g = reg.groupby(["season", "pos"])
    out = pd.DataFrame({"toi": g["toi"].mean(), "shots": g["shots"].sum() / g["toi"].sum(),
                        "assists": g["assists"].sum() / g["toi"].sum(), "blocks": g["blocks"].sum() / g["toi"].sum(),
                        "hits": g["hits"].sum() / g["toi"].sum(), "sh": g["goals"].sum() / g["shots"].sum()})
    out = out.reset_index()
    first = out[out["season"] == out["season"].min()].copy()
    out["season"] += 1
    return pd.concat([first, out], ignore_index=True).drop_duplicates(["season", "pos"], keep="last")


#: The counts a scorekeeper moves, and the arena factor that neutralises each.
KEPT = {"shots": "arena_sog", "blocks": "arena_blk", "hits": "arena_hits"}


def _state(s: pd.DataFrame, spec: Spec, *, prior: bool) -> pd.DataFrame:
    """Each player's ice time, rates and shooting percentage: before each game (``prior``), or after it. Shots,
    blocks and hits are counted as a neutral scorekeeper would have (each game's over its arena's factor), so a
    player's home rink is not in his rate and then again in the game's factor."""
    neutral = s.assign(one=1.0, **{c: s[c] / s[f] for c, f in KEPT.items()})
    t = _ew(neutral, "player_id", ["one", "toi"], spec.h_toi, prior=prior)
    r = _ew(neutral, "player_id", ["one", "toi", "shots", "assists", "blocks", "hits"], spec.h_rate, prior=prior)
    sh = _ew(s, "player_id", ["shots", "goals"], spec.h_sh, prior=prior)
    pr = s[["season", "pos"]].merge(position_rates(s), on=["season", "pos"], how="left").set_index(s.index)
    prior_t = spec.k_rate * pr["toi"]
    out = pd.DataFrame(index=s.index)
    out["n"] = r["one"]
    out["toi_hat"] = (t["toi"] / t["one"].replace(0.0, np.nan)).fillna(0.8 * pr["toi"])
    for c in ("shots", "assists", "blocks", "hits"):
        out[f"{c}_rate"] = (r[c] + prior_t * pr[c]) / (r["toi"] + prior_t)
    out["sh"] = (sh["goals"] + spec.k_sh * pr["sh"]) / (sh["shots"] + spec.k_sh)
    return out


def features(tables: dict, spec: Spec) -> pd.DataFrame:
    """Every skater-game with its base expectations (ice time times rate) and its factors, all known before
    the game; and the Poisson baseline (the season mean so far)."""
    s = skater_frame(tables["skater_games"])
    teams = team_frame(tables["team_games"])
    s["home"] = (s["home_road"] == "H").astype(float)
    s["arena"] = np.where(s["home"] == 1.0, s["team"], s["opponent"])
    s = s.merge(arenas(s, teams, spec), on=["season", "arena"], how="left")
    for c in KEPT.values():
        s[c] = s[c].fillna(1.0)
    s = s.sort_values(["player_id", "date", "game_id"]).reset_index(drop=True)
    s = pd.concat([s, _state(s, spec, prior=True)], axis=1)
    ts = pd.concat([teams[["game_id", "team", "season"]], team_state(teams, spec)], axis=1)
    lg = league(teams)
    # The player's own team, and the opponent's, each as it stood before the game, over the league's level.
    own = ts.rename(columns={c: f"own_{c}" for c in ("sf", "sa", "cf", "gf", "ga")})
    opp = ts.rename(columns={"team": "opponent", **{c: f"opp_{c}" for c in ("sf", "sa", "cf", "gf", "ga")}})
    s = s.merge(own.drop(columns="season"), on=["game_id", "team"], how="left")
    s = s.merge(opp.drop(columns="season"), on=["game_id", "opponent"], how="left")
    level = lg.reindex(s["season"]).set_index(s.index)
    s["opp_sa"] = (s["opp_sa"] / level["sa"]).fillna(1.0)
    s["opp_ga"] = (s["opp_ga"] / level["ga"]).fillna(1.0)
    s["opp_cf"] = (s["opp_cf"] / level["cf"]).fillna(1.0)
    s["team_gf"] = (s["own_gf"] / level["gf"]).fillna(1.0)
    for c in ("shots", "assists", "blocks", "hits"):
        s[f"base_{c}"] = s["toi_hat"] * s[f"{c}_rate"]
    g = s.groupby(["player_id", "season"], sort=False)
    s["n_season"] = g.cumcount()
    for c in ("shots", "goals", "assists", "points", "blocks", "hits"):
        s[f"naive_{c}"] = (g[c].cumsum() - s[c]) / s["n_season"].replace(0, np.nan)
    return s


# ---------------------------------------------------------------------------
# The goalies' features
# ---------------------------------------------------------------------------


def goalie_features(tables: dict, spec: Spec) -> pd.DataFrame:
    """Every goalie-game with the base expectation of saves (the opponent's shots on goal for, times the team's
    shots against over the league's, times his shrunk save percentage), the baseline, and home or road."""
    g = tables["goalie_games"].copy()
    g["season"] = season_of(g["game_id"])
    g["gtype"] = game_type(g["game_id"])
    for c in ("saves", "shots_against"):
        g[c] = pd.to_numeric(g[c], errors="coerce").fillna(0.0)
    g = g.sort_values(["player_id", "date", "game_id"]).reset_index(drop=True)
    sv = _ew(g, "player_id", ["saves", "shots_against"], spec.h_sv, prior=True)
    reg = g[g["gtype"] == 2]
    lg_sv = (reg.groupby("season")["saves"].sum() / reg.groupby("season")["shots_against"].sum())
    lg_sv.index = lg_sv.index + 1
    lg_sv.loc[lg_sv.index.min() - 1] = lg_sv.iloc[0]
    league_sv = lg_sv.reindex(g["season"]).to_numpy()
    g["sv_hat"] = (sv["saves"].to_numpy() + spec.k_sv * league_sv) / (sv["shots_against"].to_numpy() + spec.k_sv)
    teams = team_frame(tables["team_games"])
    ts = pd.concat([teams[["game_id", "team"]], team_state(teams, spec)], axis=1)
    lg = league(teams)
    g = g.merge(ts[["game_id", "team", "sa"]].rename(columns={"sa": "own_sa"}), on=["game_id", "team"], how="left")
    g = g.merge(ts[["game_id", "team", "sf"]].rename(columns={"team": "opponent", "sf": "opp_sf"}),
                on=["game_id", "opponent"], how="left")
    level = lg.reindex(g["season"]).set_index(g.index)
    shots = (g["opp_sf"] * g["own_sa"] / level["sf"]).fillna(level["sf"])
    g["base_saves"] = shots * g["sv_hat"]
    g["home"] = (g["home_road"].astype(str) == "H").astype(float)
    started = g[g["started"].astype(bool)].copy()
    grp = started.groupby(["player_id", "season"], sort=False)
    started["n_season"] = grp.cumcount()
    started["naive_saves"] = (grp["saves"].cumsum() - started["saves"]) / started["n_season"].replace(0, np.nan)
    return started


# ---------------------------------------------------------------------------
# The fitted layer: a Poisson regression with the base as offset
# ---------------------------------------------------------------------------


def poisson_fit(x: np.ndarray, y: np.ndarray, offset: np.ndarray, iters: int = 30) -> np.ndarray:
    """Newton's method for log E[y] = offset + x @ beta."""
    beta = np.zeros(x.shape[1])
    for _ in range(iters):
        mu = np.exp(np.clip(offset + x @ beta, -30, 30))
        grad = x.T @ (y - mu)
        hess = x.T @ (x * mu[:, None]) + 1e-6 * np.eye(x.shape[1])
        step = np.linalg.solve(hess, grad)
        beta += step
        if np.max(np.abs(step)) < 1e-9:
            break
    return beta


def design(frame: pd.DataFrame, stat: str) -> np.ndarray:
    cols = [np.ones(len(frame)), frame["home"].to_numpy(float)]
    cols += [np.log(np.clip(frame[f].to_numpy(float), 0.2, 5.0)) for f in FACTORS[stat]]
    return np.column_stack(cols)


def offset(frame: pd.DataFrame, stat: str, fitted: dict | None = None) -> np.ndarray:
    """The log of the base expectation; goals' is the fitted shots' times the shooting percentage."""
    if stat == "goals":
        shots = mean(frame, "shots", fitted) if fitted else frame["base_shots"].to_numpy(float)
        return np.log(np.clip(shots * frame["sh"].to_numpy(float), 1e-6, None))
    return np.log(np.clip(frame[f"base_{stat}"].to_numpy(float), 1e-6, None))


def mean(frame: pd.DataFrame, stat: str, fitted: dict) -> np.ndarray:
    """Atlas's expectation of the stat for each row, from one season's fitted layer."""
    if stat == "points":
        return mean(frame, "goals", fitted) + mean(frame, "assists", fitted)
    beta = np.asarray(fitted[stat]["beta"])
    return np.exp(np.clip(offset(frame, stat, fitted) + design(frame, stat) @ beta, -30, 30))


def _training(frame: pd.DataFrame, seasons) -> pd.DataFrame:
    return frame[frame["season"].isin(list(seasons)) & (frame["gtype"] == 2) & (frame["n"] >= 1)]


def fit_season(skaters: pd.DataFrame, goalies: pd.DataFrame, season: int) -> dict:
    """The layer for ``season``: each stat's powers and level, and its dispersion around the fitted mean, from
    the three seasons before it."""
    seasons = range(max(season - WINDOW, int(skaters["season"].min())), season)
    if not len(seasons):
        seasons = [season]
    train = _training(skaters, seasons)
    out: dict = {}
    for stat in ("shots", "assists", "blocks", "hits", "goals"):
        x, y = design(train, stat), train[stat].to_numpy(float)
        out[stat] = {"beta": poisson_fit(x, y, offset(train, stat, out if stat == "goals" else None)).tolist()}
    for stat in (*SKATER, ):
        mu = mean(train, stat, out)
        y = train[stat].to_numpy(float)
        out.setdefault(stat, {})["dispersion"] = float(max(1.0, ((y - mu) ** 2).sum() / mu.sum()))
    gt = goalies[goalies["season"].isin(list(seasons)) & (goalies["gtype"] == 2)]
    x, y = design(gt, "saves"), gt["saves"].to_numpy(float)
    out["saves"] = {"beta": poisson_fit(x, y, offset(gt, "saves")).tolist()}
    mu = mean(gt, "saves", out)
    out["saves"]["dispersion"] = float(max(1.0, ((y - mu) ** 2).sum() / mu.sum()))
    # Saves lean left, not right: a pulled starter's night ends early. Their shape is the ratio's own quantiles.
    out["saves"]["ratio"] = [round(float(q), 4) for q in np.quantile(y / mu, RATIO_PROBS)]
    return out


# ---------------------------------------------------------------------------
# Probabilities
# ---------------------------------------------------------------------------


RATIO_PROBS = np.linspace(0.0, 1.0, 101)


def p_over(mu, line: float, dispersion: float, ratio=None) -> np.ndarray:
    """P(count > line) for a negative binomial with mean ``mu`` and variance ``dispersion`` times it (a Poisson at
    one); or, given ``ratio`` (the quantiles of the count over its expectation at :data:`RATIO_PROBS`), that
    empirical shape scaled by ``mu``."""
    mu = np.clip(np.asarray(mu, dtype=float), 1e-6, None)
    if ratio is not None:
        q = np.asarray(ratio, dtype=float)
        values, idx = np.unique(q, return_index=True)
        cdf = RATIO_PROBS[np.r_[idx[1:] - 1, len(q) - 1]]
        return 1.0 - np.interp(line / mu, values, cdf, left=0.0, right=1.0)
    k = math.floor(line)
    if dispersion <= 1.0 + 1e-9:
        return sps.poisson.sf(k, mu)
    p = 1.0 / dispersion
    n = mu * p / (1.0 - p)
    return sps.nbinom.sf(k, n, p)


def logpmf(y, mu, dispersion: float) -> np.ndarray:
    mu = np.clip(np.asarray(mu, dtype=float), 1e-6, None)
    if dispersion <= 1.0 + 1e-9:
        return sps.poisson.logpmf(y, mu)
    p = 1.0 / dispersion
    return sps.nbinom.logpmf(y, mu * p / (1.0 - p), p)


# ---------------------------------------------------------------------------
# The walk-forward
# ---------------------------------------------------------------------------


def walk(tables: dict, spec: Spec, seasons) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Atlas's expectation for every scored player-game of ``seasons``, each season from its own layer.
    Returns (skaters, starting goalies, layers)."""
    sk = features(tables, spec)
    gk = goalie_features(tables, spec)
    layers, parts, gparts = {}, [], []
    for season in seasons:
        layer = fit_season(sk, gk, season)
        layers[season] = layer
        rows = sk[(sk["season"] == season) & (sk["gtype"] == 2)].copy()
        for stat in SKATER:
            rows[f"mu_{stat}"] = mean(rows, stat, layer)
        parts.append(rows)
        g = gk[(gk["season"] == season) & (gk["gtype"] == 2)].copy()
        g["mu_saves"] = mean(g, "saves", layer)
        gparts.append(g)
    return pd.concat(parts, ignore_index=True), pd.concat(gparts, ignore_index=True), layers


def score(sk: pd.DataFrame, gk: pd.DataFrame, layers: dict) -> pd.DataFrame:
    """Per stat and line, on player-games with :data:`MIN_PRIOR` games of the season behind them: Brier and log
    loss of P(over) by Atlas and by a Poisson on the season mean so far, and each one's mean P against the
    rate observed."""
    rows = []
    for stat, lines in LINES.items():
        frame = gk if stat == "saves" else sk
        f = frame[(frame["n_season"] >= MIN_PRIOR) & frame[f"naive_{stat}"].notna()]
        if f.empty:
            continue
        for line in lines:
            y = (f[stat].to_numpy(float) > line).astype(float)
            p_atlas = np.empty(len(f))
            for season in f["season"].unique():
                m = (f["season"] == season).to_numpy()
                layer = layers[season][stat]
                p_atlas[m] = p_over(f[f"mu_{stat}"].to_numpy(float)[m], line, layer["dispersion"], layer.get("ratio"))
            p_naive = p_over(f[f"naive_{stat}"].to_numpy(float), line, 1.0)
            row = {"stat": stat, "line": line, "n": int(len(f)), "observed": float(y.mean())}
            for name, p in (("atlas", p_atlas), ("naive", p_naive)):
                q = np.clip(p, 1e-6, 1 - 1e-6)
                row[f"brier_{name}"] = float(((p - y) ** 2).mean())
                row[f"logloss_{name}"] = float(-(y * np.log(q) + (1 - y) * np.log(1 - q)).mean())
                row[f"mean_{name}"] = float(p.mean())
            rows.append(row)
    return pd.DataFrame(rows)


def loglik(sk: pd.DataFrame, gk: pd.DataFrame, layers: dict, stats=(*SKATER, "saves")) -> float:
    """The mean log-likelihood of the counts under Atlas, over every stat (the tuning's objective)."""
    total, n = 0.0, 0
    for stat in stats:
        frame = gk if stat == "saves" else sk
        f = frame[frame["n_season"] >= MIN_PRIOR]
        for season, part in f.groupby("season"):
            ll = logpmf(part[stat].to_numpy(float), part[f"mu_{stat}"].to_numpy(float),
                        layers[season][stat]["dispersion"])
            total += float(ll.sum())
            n += len(part)
    return total / max(n, 1)


GRID = {"k_rate": (2.0, 5.0, 10.0, 20.0), "h_rate": (25.0, 40.0, 80.0), "h_toi": (5.0, 8.0, 15.0),
        "k_sh": (100.0, 200.0, 400.0), "h_team": (15.0, 25.0, 50.0), "k_sv": (750.0, 1500.0, 3000.0)}


def tune(tables: dict, base: Spec | None = None) -> tuple[Spec, list[dict]]:
    """One coordinate at a time over :data:`GRID`, on the tuning seasons' log-likelihood."""
    spec, trials = base or Spec(), []
    for name, values in GRID.items():
        best = None
        for v in values:
            trial = replace(spec, **{name: v})
            sk, gk, layers = walk(tables, trial, TUNE)
            ll = loglik(sk, gk, layers)
            trials.append({**asdict(trial), "loglik": ll})
            LOG.info("nhl props tune: %s=%g loglik %.5f", name, v, ll)
            if best is None or ll > best[0]:
                best = (ll, trial)
        spec = best[1]
    return spec, trials


# ---------------------------------------------------------------------------
# The games ahead
# ---------------------------------------------------------------------------

#: The pick'em's market slugs (`atlas/owner/pickem.py`), to the stat each projects.
MARKETS = {"shots": "shots", "shots-on-goal": "shots", "points": "points", "goals": "goals", "assists": "assists",
           "saves": "saves", "blocked-shots": "blocks", "hits": "hits"}
#: A player is carried into the season ahead when his latest game is this recent.
ACTIVE_DAYS = 450
SKATER_STATE = ["player_id", "name", "position", "team", "date", "toi_hat", "shots_rate", "assists_rate",
                "blocks_rate", "hits_rate", "sh"]


def _last(frame: pd.DataFrame, key: str) -> pd.DataFrame:
    return frame.groupby(key, sort=False).tail(1).set_index(key)


def snapshot(tables: dict, now, spec: Spec | None = None) -> dict:
    """Everything the expectation for a game ahead needs, as it stands after the latest game in the warehouse:
    each active skater's ice time, rates and shooting percentage; each goalie's save percentage; each team's
    weighted shots, attempts and goals per game and the league's level; the arenas' factors; and the season's
    fitted layer. The pick'em reads it at puck drop's distance, for the player BettingPros lists on the team
    it lists him on (a summer's signings included), against that night's opponent."""
    spec = spec or Spec()
    sk_all = features(tables, spec)
    gk_all = goalie_features(tables, spec)
    t = pd.Timestamp(now)
    t = t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")
    season = t.year if t.month >= 8 else t.year - 1
    layer = fit_season(sk_all, gk_all, season)

    s = skater_frame(tables["skater_games"])
    teams = team_frame(tables["team_games"])
    s["home"] = (s["home_road"] == "H").astype(float)
    s["arena"] = np.where(s["home"] == 1.0, s["team"], s["opponent"])
    arena = arenas(s, teams, spec)
    s = s.merge(arena, on=["season", "arena"], how="left")
    for c in KEPT.values():
        s[c] = s[c].fillna(1.0)
    s = s.sort_values(["player_id", "date", "game_id"]).reset_index(drop=True)
    s = pd.concat([s, _state(s, spec, prior=False)], axis=1)
    players = _last(s, "player_id").reset_index()
    recent = pd.to_datetime(players["date"]) >= (t.tz_localize(None) - pd.Timedelta(days=ACTIVE_DAYS))
    players = players[recent][SKATER_STATE]

    after = pd.concat([teams[["team"]], team_state(teams, spec, prior=False)], axis=1)
    team_now = _last(after, "team").reset_index()
    lg = league(teams)
    level = lg.loc[season] if season in lg.index else lg.iloc[-1]

    g = tables["goalie_games"].copy()
    for c in ("saves", "shots_against"):
        g[c] = pd.to_numeric(g[c], errors="coerce").fillna(0.0)
    g = g.sort_values(["player_id", "date", "game_id"]).reset_index(drop=True)
    sv = _ew(g, "player_id", ["saves", "shots_against"], spec.h_sv, prior=False)
    reg = g[game_type(g["game_id"]) == 2]
    league_sv = float(reg["saves"].sum() / max(reg["shots_against"].sum(), 1.0))
    g = g.assign(sv_hat=(sv["saves"] + spec.k_sv * league_sv) / (sv["shots_against"] + spec.k_sv))
    goalies = _last(g, "player_id").reset_index()
    goalies = goalies[pd.to_datetime(goalies["date"]) >= (t.tz_localize(None) - pd.Timedelta(days=ACTIVE_DAYS))]
    return {"season": season, "skaters": players.reset_index(drop=True),
            "goalies": goalies[["player_id", "name", "team", "date", "sv_hat"]].reset_index(drop=True),
            "teams": team_now[["team", "sf", "sa", "cf", "gf", "ga"]],
            "level": {k: float(v) for k, v in level.items()}, "league_sv": league_sv,
            "arenas": arena[arena["season"] == season].drop(columns="season").reset_index(drop=True),
            "layer": layer, "spec": asdict(spec)}


def expect(snap: dict, player, team: str, opponent: str, home_team: str, stat: str, *, goalie=None) -> float:
    """Atlas's expectation of ``stat`` for one player (a :data:`SKATER_STATE` row, or a goalie's) on ``team``
    against ``opponent`` in ``home_team``'s arena; nan when a team is not known."""
    teams = snap["teams"].set_index("team")
    if team not in teams.index or opponent not in teams.index:
        return float("nan")
    own, opp, level, layer = teams.loc[team], teams.loc[opponent], snap["level"], snap["layer"]
    home = 1.0 if team == home_team else 0.0
    if stat == "saves":
        f = pd.DataFrame({"home": [home], "base_saves": [float(opp["sf"] * own["sa"] / level["sf"])
                                                         * float(goalie["sv_hat"])]})
        return float(mean(f, "saves", layer)[0])
    arena = snap["arenas"].set_index("arena")
    at = arena.loc[home_team] if home_team in arena.index else None
    f = pd.DataFrame([{"home": home, "opp_sa": float(opp["sa"] / level["sa"]), "opp_ga": float(opp["ga"] / level["ga"]),
                       "opp_cf": float(opp["cf"] / level["cf"]), "team_gf": float(own["gf"] / level["gf"]),
                       **{c: float(at[c]) if at is not None else 1.0 for c in KEPT.values()},
                       "sh": float(player["sh"]),
                       **{f"base_{c}": float(player["toi_hat"]) * float(player[f"{c}_rate"])
                          for c in ("shots", "assists", "blocks", "hits")}}])
    return float(mean(f, stat, layer)[0])


def shape(snap: dict, stat: str) -> tuple[float, list | None]:
    layer = snap["layer"][stat]
    return float(layer["dispersion"]), layer.get("ratio")


def prob(mean_: float, line: float, side: str, dispersion: float, ratio=None) -> float:
    """Atlas's probability of ``side`` (over or under) at ``line``; a tie on a whole-number line is neither."""
    whole = float(line).is_integer()
    if ratio:
        over = float(p_over([mean_], line + 0.5 if whole else line, dispersion, ratio)[0])
        under = 1.0 - float(p_over([mean_], line - 0.5 if whole else line, dispersion, ratio)[0])
    else:
        over = float(p_over([mean_], line, dispersion)[0])
        under = 1.0 - float(p_over([mean_], line - 1 if whole else line, dispersion)[0])
    return over if side == "over" else under


def players_path() -> Path:
    from atlas.live.store import tracking_dir

    return tracking_dir() / "owner_nhl_players" / "state.enc.json"


def _records(frame: pd.DataFrame) -> list[dict]:
    return json.loads(frame.to_json(orient="records", date_format="iso"))


def seal(snap: dict, passphrase: str, where: Path | None = None) -> Path:
    """The snapshot, for the owner's pick'em only: sealed, one file, rewritten each heavy refresh."""
    from atlas.owner import sealed

    rows = [{"kind": kind, **r} for kind in ("skaters", "goalies", "teams", "arenas") for r in _records(snap[kind])]
    rows.append({"kind": "meta", "season": snap["season"], "level": snap["level"], "league_sv": snap["league_sv"],
                 "layer": snap["layer"], "spec": snap["spec"]})
    return sealed.seal(rows, passphrase, where or players_path())


def load(passphrase: str, where: Path | None = None) -> dict | None:
    """The sealed snapshot, or None when there is none yet."""
    from atlas.owner import sealed

    where = where or players_path()
    if not where.exists():
        return None
    rows = sealed.open_text(where.read_text(), passphrase)
    meta = next((r for r in rows if r["kind"] == "meta"), None)
    if meta is None:
        return None
    frames = {kind: pd.DataFrame([{k: v for k, v in r.items() if k != "kind"} for r in rows if r["kind"] == kind])
              for kind in ("skaters", "goalies", "teams", "arenas")}
    return {**frames, "season": meta["season"], "level": meta["level"], "league_sv": meta["league_sv"],
            "layer": {k: v for k, v in meta["layer"].items()}, "spec": meta["spec"]}


def publish(now, passphrase: str, *, tables: dict | None = None, where: Path | None = None) -> int:
    """The heavy refresh's step: the snapshot sealed. Returns the players in it."""
    snap = snapshot(tables or load_tables(), now)
    seal(snap, passphrase, where)
    return len(snap["skaters"]) + len(snap["goalies"])


# ---------------------------------------------------------------------------
# Tables and the report
# ---------------------------------------------------------------------------


def load_tables() -> dict:
    from atlas.staging.nhl import build

    return {t: build.load(t) for t in ("skater_games", "goalie_games", "team_games")}


def write_report(spec: Spec, table: pd.DataFrame, by_season: pd.DataFrame, layers: dict, root: Path) -> Path:
    out = {"version": VERSION, "spec": asdict(spec), "scores": table.to_dict("records"),
           "by_season": by_season.to_dict("records"),
           "layers": {str(k): v for k, v in layers.items()}}
    json_path(root).write_text(json.dumps(out, indent=1) + "\n")
    lines = ["# NHL player projections (step 8)", "",
             f"`python -m atlas.models.nhl_props`. Walk-forward, every layer fitted on the three seasons before the one "
             f"it scores; half-lives and priors tuned once on {TUNE[0]}-{TUNE[0] + 1 - 2000:02d} to "
             f"{TUNE[-1]}-{TUNE[-1] + 1 - 2000:02d}. Scored on regular-season player-games from "
             f"{FIRST_REPORT}-{FIRST_REPORT + 1 - 2000:02d} with {MIN_PRIOR} games of the season behind them, "
             "against a Poisson on the player's season mean so far (the plan's baseline).", "",
             "## P(over) at the common lines", "",
             "| Stat | Line | Player-games | Observed | Atlas mean P | Baseline mean P | Brier, Atlas | Brier, baseline | "
             "Log loss, Atlas | Log loss, baseline |", "|---|---|---|---|---|---|---|---|---|---|"]
    for r in table.itertuples():
        lines.append(f"| {r.stat} | {r.line:g} | {r.n:,} | {r.observed:.3f} | {r.mean_atlas:.3f} | {r.mean_naive:.3f} | "
                     f"**{r.brier_atlas:.4f}** | {r.brier_naive:.4f} | {r.logloss_atlas:.4f} | {r.logloss_naive:.4f} |")
    lines += ["", "## By season (Brier at each stat's first line)", "",
              "| Season | Stat | Line | Atlas | Baseline |", "|---|---|---|---|---|"]
    for r in by_season.itertuples():
        lines.append(f"| {r.season}-{(r.season + 1) % 100:02d} | {r.stat} | {r.line:g} | {r.brier_atlas:.4f} | "
                     f"{r.brier_naive:.4f} |")
    last = layers[max(layers)]
    lines += ["", f"## The {max(layers)}-{(max(layers) + 1) % 100:02d} layer", "",
              "| Stat | Level | Home | Factors (powers) | Dispersion |", "|---|---|---|---|---|"]
    for stat in (*SKATER, "saves"):
        layer = last.get(stat, {})
        beta = layer.get("beta")
        powers = ", ".join(f"{f} {b:+.2f}" for f, b in zip(FACTORS.get(stat, ()), beta[2:], strict=False)) \
            if beta else "goals + assists"
        lines.append(f"| {stat} | {math.exp(beta[0]):.3f} | {math.exp(beta[1]):.3f} | {powers or '–'} | "
                     f"{layer.get('dispersion', float('nan')):.2f} |" if beta else
                     f"| {stat} | – | – | {powers} | {layer.get('dispersion', float('nan')):.2f} |")
    lines += ["", f"Spec: {', '.join(f'{k} {v:g}' for k, v in asdict(spec).items())}.", ""]
    report_path(root).write_text("\n".join(lines))
    return report_path(root)


def run(tables: dict, spec: Spec, seasons) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    sk, gk, layers = walk(tables, spec, seasons)
    table = score(sk, gk, layers)
    per = []
    for season in seasons:
        t = score(sk[sk["season"] == season], gk[gk["season"] == season], layers)
        if len(t):
            per.append(t.drop_duplicates("stat").assign(season=season))           # each stat's first line
    return table, pd.concat(per, ignore_index=True), layers


def main() -> None:
    ap = argparse.ArgumentParser(description="NHL player projections, walk-forward")
    ap.add_argument("--no-tune", action="store_true", help="score the default spec")
    args = ap.parse_args()
    tables = load_tables()
    spec, _ = (Spec(), []) if args.no_tune else tune(tables)
    # Complete seasons only: the one under way is scored when it is over.
    last = int(season_of(tables["skater_games"]["game_id"]).max())
    seasons = range(FIRST_REPORT, last)
    table, per, layers = run(tables, spec, seasons)
    print(table.to_string())
    write_report(spec, table, per, layers, config.paths().root)


if __name__ == "__main__":
    main()
