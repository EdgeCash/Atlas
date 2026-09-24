"""Whether a player records a stat at all this week.

Step 5 of `docs/MODEL_PLAN_DFS.md`. The player model is fitted on the
player-weeks where a player recorded a stat, so its projection is what he
scores *if he plays*. A slate's pool is every player DraftKings prices,
down to the third tight end, and many of those will not touch the ball; to
the optimizer, a cheap player's conditional projection looks like a
bargain. The number a lineup should be built on is the expectation:

    expected points = P(records a stat) x points if he does

This model is the first factor. Its denominator is every quarterback,
running back, receiver and tight end on his team's depth chart that week;
the outcome is whether he recorded a stat. Inputs, all known before
kickoff: position, depth-chart rank, the injury report's status, how many
games he has played, his snap share going in, and how long since his last
game. A player DraftKings prices who is not on the depth chart at all is
read as one rank below the deepest listing.

Walk-forward like everything else: each season scored by a model fitted on
the seasons before it.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier

from atlas import config
from atlas.dfs import context
from atlas.sources import nflverse

POSITIONS = ("QB", "RB", "WR", "TE")
FEATURES = ["is_qb", "is_rb", "is_wr", "is_te", "depth_rank", "status", "games_before", "snap_after",
            "weeks_since", "is_qb1"]
UNLISTED_RANK = 5.0                 # not on the depth chart: below its deepest listing
PARAMS = dict(max_iter=150, learning_rate=0.05, max_leaf_nodes=15, min_samples_leaf=100, l2_regularization=1.0,
              random_state=0)
FIRST_TEST = 2015


def _order(season, week) -> np.ndarray:
    return np.asarray(season, dtype="int64") * 100 + np.asarray(week, dtype="int64")


def history(player_games: pd.DataFrame, rows: pd.DataFrame) -> pd.DataFrame:
    """For each (season, week, player_id) in ``rows``: games played before it,
    his snap share going out of his last game, and weeks since that game."""
    g = player_games[player_games["season_type"] == "REG"].sort_values(["player_id", "season", "week"]).copy()
    by = g.groupby("player_id", sort=False)
    g["games_after"] = by.cumcount() + 1
    g["snap_after"] = by["snap_pct"].transform(lambda s: s.ewm(halflife=4.0, ignore_na=True).mean())
    g["order"] = _order(g["season"], g["week"])
    g["last_order"] = g["order"]
    g["player_id"] = g["player_id"].astype(str)
    r = rows[["season", "week", "player_id"]].copy()
    r["player_id"] = r["player_id"].astype(str)
    r["order"] = _order(r["season"], r["week"])
    r["_i"] = np.arange(len(r))
    got = pd.merge_asof(r.sort_values("order"), g[["player_id", "order", "games_after", "snap_after", "last_order"]]
                        .sort_values("order"), on="order", by="player_id", direction="backward",
                        allow_exact_matches=False).sort_values("_i")
    last = got["last_order"]
    weeks = (got["order"] // 100 - last // 100) * 18 + (got["order"] % 100 - last % 100)
    return pd.DataFrame({"games_before": got["games_after"].fillna(0).to_numpy(),
                         "snap_after": got["snap_after"].to_numpy(),
                         "weeks_since": weeks.fillna(99).clip(upper=99).to_numpy()}, index=rows.index)


def features(rows: pd.DataFrame, player_games: pd.DataFrame) -> pd.DataFrame:
    """``rows`` (season, week, player_id, position, depth_rank, status, is_qb1) with the model's inputs."""
    f = rows.copy()
    for p in POSITIONS:
        f[f"is_{p.lower()}"] = (f["position"] == p).astype(int)
    f["depth_rank"] = f["depth_rank"].fillna(UNLISTED_RANK)
    f["status"] = f["status"].fillna(0)
    f["is_qb1"] = f.get("is_qb1", pd.Series(0, index=f.index)).fillna(0)
    return f.join(history(player_games, f))


def table(raw: Path | None = None, staging: Path | None = None) -> pd.DataFrame:
    """Every depth-chart listing of a team that played that week, and whether he recorded a stat."""
    raw = raw or config.paths().raw
    staging = staging or config.paths().staging / "nfl"
    pg = pd.read_parquet(staging / "dfs_player_games.parquet")
    pg = pg[pg["season_type"] == "REG"]
    seasons = sorted(int(s) for s in pg["season"].unique())
    chart = context.depth(raw, seasons)
    played_weeks = pg[["season", "week", "team"]].drop_duplicates()
    chart = chart.merge(played_weeks, on=["season", "week", "team"], how="inner")
    master = pd.read_parquet(nflverse.players_path(raw))[["gsis_id", "position"]].rename(
        columns={"gsis_id": "player_id"})
    master["position"] = master["position"].replace({"FB": "RB", "HB": "RB"})
    chart = chart.merge(master, on="player_id", how="left")
    chart = chart[chart["position"].isin(POSITIONS)]
    report = context.injuries(raw, seasons)
    chart = chart.merge(report, on=["season", "week", "team", "player_id"], how="left")
    news = pd.read_parquet(context.path(staging))[["season", "week", "player_id", "is_qb1"]]
    chart = chart.merge(news, on=["season", "week", "player_id"], how="left")
    stat = pg[["season", "week", "player_id"]].drop_duplicates().assign(played=1)
    chart = chart.merge(stat, on=["season", "week", "player_id"], how="left")
    chart["played"] = chart["played"].fillna(0).astype(int)
    return features(chart.reset_index(drop=True), pg)


def fit(train: pd.DataFrame) -> HistGradientBoostingClassifier:
    return HistGradientBoostingClassifier(**PARAMS).fit(train[FEATURES].to_numpy(dtype=float),
                                                        train["played"].to_numpy(dtype=int))


def predict(model: HistGradientBoostingClassifier, rows: pd.DataFrame) -> np.ndarray:
    return model.predict_proba(rows[FEATURES].to_numpy(dtype=float))[:, 1]


def walk_forward(t: pd.DataFrame, *, first: int = FIRST_TEST) -> pd.DataFrame:
    parts = []
    for season in sorted(int(s) for s in t["season"].unique()):
        if season < first:
            continue
        test = t[t["season"] == season]
        parts.append(test.assign(p_play=predict(fit(t[t["season"] < season]), test)))
    return pd.concat(parts)


def reliability(scored: pd.DataFrame, bins: int = 10) -> pd.DataFrame:
    """Predicted against observed, by tenths of the prediction."""
    s = scored.assign(bin=np.minimum((scored["p_play"] * bins).astype(int), bins - 1))
    out = s.groupby("bin").agg(listings=("played", "size"), predicted=("p_play", "mean"),
                               observed=("played", "mean")).reset_index(drop=True)
    return out


def brier(scored: pd.DataFrame) -> float:
    return float(np.mean((scored["p_play"] - scored["played"]) ** 2))



def by_depth(t: pd.DataFrame, *, first: int = FIRST_TEST) -> pd.Series:
    """The simple alternative, walk-forward: the share of earlier seasons'
    listings at the same position and depth who recorded a stat."""
    out = pd.Series(np.nan, index=t.index)
    for season in sorted(int(s) for s in t["season"].unique()):
        if season < first:
            continue
        rate = t[t["season"] < season].groupby(["position", "depth_rank"])["played"].mean()
        m = t["season"] == season
        keys = pd.MultiIndex.from_frame(t.loc[m, ["position", "depth_rank"]])
        out[m] = rate.reindex(keys).to_numpy()
    return out
