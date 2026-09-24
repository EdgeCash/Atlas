"""The DFS model's public record: what it projected, and what happened.

Step 7 of `docs/MODEL_PLAN_DFS.md`. Every slate's public projections go
into the tracking store (``tracking/dfs_projections.csv``), rewritten by
each refresh until the slate's first kickoff and never after - the record
is the projection a reader could have seen, not one revised once games were
played. After the games, each player is graded against the DraftKings
points he recorded (zero for a player who recorded nothing: the public
projection is an expectation that includes the chance of not playing).

Two records sit on the public page:

* the **walk-forward history**, 2015-2025 (`reports/dfs_record.json`, written
  by `python -m atlas.dfs.model`): the model's out-of-sample accuracy and
  its ranges' coverage, beside DraftKings' salary where salaries exist;
* the **live record**, from the tracking store, once slates are graded.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from atlas import config
from atlas.util import get_logger

LOG = get_logger(__name__)

COLUMNS = ["draft_group_id", "slate", "starts_at", "season", "week", "player_id_dk", "player_id", "name",
           "position", "team", "opponent", "salary", "status", "projection", "low", "high", "p_play",
           "projected_at"]


def record_path() -> Path:
    return config.paths().root / "reports" / "dfs_record.json"


def save(projected: pd.DataFrame, slate: pd.Series, store, *, now: datetime | None = None) -> int:
    """The slate's projections into the store - only before its first kickoff."""
    now = now or datetime.now(timezone.utc)
    start = pd.Timestamp(slate["starts_at"])
    start = start.tz_localize("UTC") if start.tzinfo is None else start
    if start <= pd.Timestamp(now):
        LOG.info("slate %s has started; its record is frozen", slate["draft_group_id"])
        return 0
    rows = projected.dropna(subset=["projection"]).assign(
        draft_group_id=int(slate["draft_group_id"]), slate=slate["label"], starts_at=str(slate["starts_at"]),
        projected_at=now.replace(microsecond=0).isoformat())
    for c in ("projection", "low", "high"):
        rows[c] = rows[c].round(2)
    rows["p_play"] = rows["p_play"].round(3)
    return store.upsert("dfs_projections", rows.reindex(columns=COLUMNS))


def actuals(player_games: pd.DataFrame, dst_games: pd.DataFrame) -> pd.DataFrame:
    """DraftKings points per (season, week, player_id), defenses as ``DST-<team>``,
    and the team-weeks that have been played."""
    pg = player_games[player_games["season_type"] == "REG"]
    off = pg[["season", "week", "player_id", "dk_points"]].rename(columns={"dk_points": "actual"})
    d = dst_games[dst_games["season_type"] == "REG"]
    dst = pd.DataFrame({"season": d["season"], "week": d["week"], "player_id": "DST-" + d["team"],
                        "actual": d["dk_points"]})
    return pd.concat([off, dst], ignore_index=True)


def graded(projections: pd.DataFrame, player_games: pd.DataFrame, dst_games: pd.DataFrame) -> pd.DataFrame:
    """Projections whose team's game has been played, with the points scored."""
    if projections.empty:
        return projections.assign(actual=pd.Series(dtype=float))
    p = projections.copy()
    p["season"], p["week"] = p["season"].astype("Int64"), p["week"].astype("Int64")
    played = dst_games[dst_games["season_type"] == "REG"][["season", "week", "team"]].drop_duplicates()
    played = played.astype({"season": "Int64", "week": "Int64"})
    p = p.merge(played, on=["season", "week", "team"], how="inner")
    got = actuals(player_games, dst_games).astype({"season": "Int64", "week": "Int64"})
    p = p.merge(got, on=["season", "week", "player_id"], how="left")
    p["actual"] = p["actual"].fillna(0.0)          # recorded nothing: DraftKings scores him zero
    return p


def summary(g: pd.DataFrame) -> dict:
    """The live record in a few numbers."""
    if g.empty:
        return {"slates": 0}
    inside = (g["actual"] >= g["low"]) & (g["actual"] <= g["high"])
    ranks = []
    for _, s in g.groupby(["draft_group_id", "position"]):
        if len(s) >= 5 and s["projection"].nunique() > 1:
            ranks.append(s["projection"].rank().corr(s["actual"].rank()))
    return {"slates": int(g["draft_group_id"].nunique()), "players": len(g),
            "mae": float(np.mean(np.abs(g["actual"] - g["projection"]))),
            "coverage": float(inside.mean()),
            "rank": float(np.nanmean(ranks)) if ranks else float("nan")}


def live(store=None, warehouse=None) -> dict:
    """The live record from the tracking store and the NFL warehouse's DFS tables."""
    if store is None:
        from atlas.live.store import Store

        store = Store.open()
    projections = store.read("dfs_projections")
    if projections.empty:
        return {"slates": 0}
    try:
        import duckdb

        from atlas.staging.nfl.build import warehouse_path

        con = duckdb.connect(str(warehouse_path(warehouse or config.paths().warehouse)), read_only=True)
        try:
            pg = con.execute("SELECT season, week, season_type, player_id, dk_points FROM dfs_player_games").df()
            dst = con.execute("SELECT season, week, season_type, team, dk_points FROM dfs_dst_games").df()
        finally:
            con.close()
    except Exception as error:  # noqa: BLE001 - no DFS tables yet: nothing is graded
        LOG.info("dfs record: no DFS tables in the warehouse (%s)", type(error).__name__)
        return {"slates": 0}
    return summary(graded(projections, pg, dst))


def history() -> dict | None:
    """The walk-forward history `atlas.dfs.model` writes."""
    path = record_path()
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None
