"""Assemble the NFL warehouse: ``data/warehouse/nfl.duckdb``.

    python -m atlas.staging.nfl.build              # 2011 to the current season
    python -m atlas.staging.nfl.build --seasons 2023 2024

One research table, ``research_games``, one row per game, with the same
column conventions as the college ``research_games`` so
:mod:`atlas.models` reads it unchanged:

* the game as scheduled and as it finished (`games.py`);
* each side's opponent-adjusted efficiency as it stood before the week
  (``home_adj_off_epa`` and so on), from the college network solve;
* each side's season-to-date raw metrics shrunk toward last season
  (``home_off_epa_pit`` and so on), from the college point-in-time builder;
* the depth chart's QB1 for the week (``home_qb1_id``), which is what was
  knowable before kickoff, beside the quarterback of record
  (``home_qb_id``), which was not;
* the injury report's count of players Out or Doubtful, and whether one of
  them was the QB1.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from atlas import config
from atlas.features.opponent_adjustment import point_in_time_ratings
from atlas.features.point_in_time import add_point_in_time_features
from atlas.sources import nflverse
from atlas.staging.adjusted_efficiency import STREAMS, _observations
from atlas.staging.nfl import efficiency as eff_stage
from atlas.staging.nfl import games as games_stage
from atlas.staging.nfl.games import team_id
from atlas.util import get_logger, write_parquet

LOG = get_logger(__name__)

PIT_METRICS = ["off_epa", "def_epa", "success_rate", "def_success_rate", "explosiveness", "def_explosiveness",
               "havoc", "pace", "plays_per_game", "points_per_drive", "td_rate", "net_epa"]
ADJUSTED_METHOD = "network"


def warehouse_path(warehouse: Path | None = None) -> Path:
    return (warehouse or config.paths().warehouse) / "nfl.duckdb"


def build(seasons: list[int] | None = None, *, include_scheduled: bool = True) -> pd.DataFrame:
    paths = config.paths().ensure()
    seasons = seasons or list(range(nflverse.FIRST_SEASON, nflverse.current_season() + 1))
    staging = paths.staging / "nfl"
    staging.mkdir(parents=True, exist_ok=True)

    games = games_stage.build_games(paths.raw, staging.parent, seasons, include_scheduled=include_scheduled)
    eff = eff_stage.build_efficiency(paths.raw, staging.parent, seasons)
    frame = assemble(games, eff, qb1=depth_chart_qb1(paths.raw, seasons, games=games),
                     injuries=injury_counts(paths.raw, seasons))
    write_parquet(frame, staging / "research_games.parquet")

    db = warehouse_path(paths.warehouse)
    con = duckdb.connect(str(db))
    try:
        con.register("frame", frame)
        con.execute("CREATE OR REPLACE TABLE research_games AS SELECT * FROM frame")
        con.register("games", games)
        con.execute("CREATE OR REPLACE TABLE games AS SELECT * FROM games")
        con.register("eff", eff)
        con.execute("CREATE OR REPLACE TABLE team_game_efficiency AS SELECT * FROM eff")
    finally:
        con.close()
    manifest = {"generated_at": datetime.now(UTC).isoformat(timespec="seconds"), "seasons": seasons,
                "games": int(len(frame)), "completed": int(frame["completed"].sum()),
                "columns": int(frame.shape[1])}
    (paths.warehouse / "NFL_MANIFEST.json").write_text(json.dumps(manifest, indent=1) + "\n")
    LOG.info("nfl warehouse -> %s (%d games, %d completed)", db, len(frame), manifest["completed"])
    return frame


def assemble(games: pd.DataFrame, eff: pd.DataFrame, *, qb1: pd.DataFrame | None = None,
             injuries: pd.DataFrame | None = None) -> pd.DataFrame:
    """The research table from staged games and efficiency (no files)."""
    long = games_stage.to_long(games)
    completed = games[games["completed"] == 1]
    base = long[long["game_id"].isin(completed["game_id"])][
        ["game_id", "season", "week", "kickoff", "team_id", "opponent_id", "is_home"]]

    # --- opponent-adjusted, point-in-time by week ---------------------------
    scheduled_weeks = games[["season", "week"]].drop_duplicates()
    adjusted = games[["season", "week"]].drop_duplicates().merge(
        long[["season", "week", "team_id"]].drop_duplicates(), on=["season", "week"])
    for stream in STREAMS:
        obs = _observations(base, eff, stream)
        if obs.empty:
            LOG.warning("nfl stream %s has no observations", stream.name)
            continue
        ratings = point_in_time_ratings(obs, method=ADJUSTED_METHOD, extra_weeks=scheduled_weeks)
        ratings = ratings.rename(columns={"actor_rating": stream.actor_output, "opponent_rating": stream.opponent_output})
        adjusted = adjusted.merge(ratings[["season", "week", "team_id", stream.actor_output, stream.opponent_output]],
                                  on=["season", "week", "team_id"], how="left")
    adj_cols = [c for c in adjusted.columns if c.startswith("adj_")]

    # --- season-to-date raw metrics, shrunk toward last season --------------
    team_games = long.merge(eff[["game_id", "team_id", *[m for m in PIT_METRICS if m in eff.columns]]],
                            on=["game_id", "team_id"], how="left")
    metrics = [m for m in PIT_METRICS if m in team_games.columns]
    pit = add_point_in_time_features(team_games, metrics)
    pit_cols = [f"{m}_pit" for m in metrics] + ["n_prior_games"]

    out = games.copy()
    for side in ("home", "away"):
        key = f"{side}_team_id"
        a = adjusted.rename(columns={"team_id": key, **{c: f"{side}_{c}" for c in adj_cols}})
        out = out.merge(a, on=["season", "week", key], how="left")
        p = pit[["game_id", "team_id", *pit_cols]].rename(
            columns={"team_id": key, **{c: f"{side}_{c}" for c in pit_cols}})
        out = out.merge(p, on=["game_id", key], how="left")
    for c in adj_cols + pit_cols:
        out[f"{c}_diff"] = out[f"home_{c}"] - out[f"away_{c}"]
    out["adj_net_epa_diff"] = (out["home_adj_off_epa"] - out["home_adj_def_epa"]) - (out["away_adj_off_epa"] - out["away_adj_def_epa"]) \
        if "home_adj_off_epa" in out and "home_adj_def_epa" in out else np.nan
    out["min_prior_games"] = out[["home_n_prior_games", "away_n_prior_games"]].min(axis=1)

    # --- the quarterback: expected (QB1) beside of record --------------------
    if qb1 is not None and not qb1.empty:
        for side in ("home", "away"):
            q = qb1.rename(columns={"team_id": f"{side}_team_id", "qb1_id": f"{side}_qb1_id", "qb1_name": f"{side}_qb1_name"})
            out = out.merge(q, on=["season", "week", f"{side}_team_id"], how="left")
    else:
        for side in ("home", "away"):
            out[f"{side}_qb1_id"] = pd.NA
            out[f"{side}_qb1_name"] = pd.NA
    if injuries is not None and not injuries.empty:
        for side in ("home", "away"):
            i = injuries.rename(columns={"team_id": f"{side}_team_id", "injured_out": f"{side}_injured_out",
                                         "qb1_out": f"{side}_qb1_out"})
            out = out.merge(i, on=["season", "week", f"{side}_team_id"], how="left")
    else:
        for side in ("home", "away"):
            out[f"{side}_injured_out"] = np.nan
            out[f"{side}_qb1_out"] = np.nan
    out = out.sort_values(["kickoff", "game_id"]).reset_index(drop=True)
    LOG.info("nfl research_games: %d rows, %d columns", len(out), out.shape[1])
    return out


def depth_chart_qb1(raw: Path, seasons: list[int], games: pd.DataFrame | None = None) -> pd.DataFrame:
    """The QB listed first on each team's depth chart for the week.

    nflverse changed the depth-chart feed in 2025: to 2024 a file is one row
    per (season, week, team, position, depth); from 2025 it is a daily
    snapshot (``dt``, ``team``, ``pos_abb``, ``pos_rank``) with no week. The
    snapshot form is mapped to weeks by taking, for each team's game, the
    latest snapshot before its kickoff - which is exactly what was knowable
    then. ``games`` is needed for that; without it the snapshot seasons are
    skipped with a warning.
    """
    frames = []
    for season in seasons:
        path = nflverse.depth_charts_path(raw, season)
        if not path.exists():
            continue
        d = pd.read_parquet(path)
        if "dt" in d.columns and "pos_rank" in d.columns:
            if games is None:
                LOG.warning("depth charts %s are daily snapshots; pass games to map them to weeks", season)
                continue
            frames.append(_snapshot_qb1(d, games[games["season"] == season]))
            continue
        d = d[(d["position"].astype(str) == "QB") & (d["depth_team"].astype(str) == "1")].copy()
        d["team_id"] = team_id(d["club_code"])
        d["week"] = pd.to_numeric(d["week"], errors="coerce")
        d = d.dropna(subset=["team_id", "week"])
        d = d.drop_duplicates(["season", "week", "team_id"])
        frames.append(pd.DataFrame({"season": d["season"].astype(int), "week": d["week"].astype(int),
                                    "team_id": d["team_id"].astype("Int64"),
                                    "qb1_id": d["gsis_id"].astype("string"), "qb1_name": d["player_name" if "player_name" in d else "full_name"].astype("string")}))
    frames = [f for f in frames if f is not None and not f.empty]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(
        columns=["season", "week", "team_id", "qb1_id", "qb1_name"])


def _snapshot_qb1(snapshots: pd.DataFrame, games: pd.DataFrame) -> pd.DataFrame:
    """Daily depth-chart snapshots to one QB1 per team-week: the latest snapshot before kickoff."""
    q = snapshots[(snapshots["pos_abb"].astype(str) == "QB") & (pd.to_numeric(snapshots["pos_rank"], errors="coerce") == 1)].copy()
    q["team_id"] = team_id(q["team"])
    q["dt"] = pd.to_datetime(q["dt"], errors="coerce", utc=True)
    q = q.dropna(subset=["team_id", "dt"]).sort_values("dt")
    q = q.drop_duplicates(["team_id", "dt"], keep="last")[["team_id", "dt", "gsis_id", "player_name"]]
    long = games_stage.to_long(games)[["season", "week", "team_id", "kickoff"]].copy()
    long["kickoff"] = pd.to_datetime(long["kickoff"], utc=True)
    long = long.dropna(subset=["kickoff"]).sort_values("kickoff")
    q["team_id"] = q["team_id"].astype("int64")
    long["team_id"] = long["team_id"].astype("int64")
    merged = pd.merge_asof(long, q.rename(columns={"dt": "snapshot_at"}), left_on="kickoff", right_on="snapshot_at",
                           by="team_id", direction="backward")
    out = merged.dropna(subset=["gsis_id"]).drop_duplicates(["season", "week", "team_id"])
    return pd.DataFrame({"season": out["season"].astype(int), "week": out["week"].astype(int),
                         "team_id": out["team_id"].astype("Int64"), "qb1_id": out["gsis_id"].astype("string"),
                         "qb1_name": out["player_name"].astype("string")})


def injury_counts(raw: Path, seasons: list[int]) -> pd.DataFrame:
    """Players reported Out or Doubtful per team-week, and whether a QB was."""
    frames = []
    for season in seasons:
        path = nflverse.injuries_path(raw, season)
        if not path.exists():
            continue
        i = pd.read_parquet(path)
        i["team_id"] = team_id(i["team"])
        i["week"] = pd.to_numeric(i["week"], errors="coerce")
        i = i.dropna(subset=["team_id", "week"])
        out_flag = i["report_status"].astype("string").isin(["Out", "Doubtful"])
        i = i.assign(out=out_flag.astype(float), qb_out=(out_flag & (i["position"].astype(str) == "QB")).astype(float))
        g = i.groupby(["season", "week", "team_id"], as_index=False).agg(injured_out=("out", "sum"), qb1_out=("qb_out", "max"))
        g["season"], g["week"] = g["season"].astype(int), g["week"].astype(int)
        frames.append(g)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(
        columns=["season", "week", "team_id", "injured_out", "qb1_out"])


def main() -> None:
    ap = argparse.ArgumentParser(description="Build the NFL warehouse")
    ap.add_argument("--seasons", type=int, nargs="*", default=None)
    ap.add_argument("--completed-only", action="store_true", help="leave scheduled games out")
    args = ap.parse_args()
    build(args.seasons, include_scheduled=not args.completed_only)


if __name__ == "__main__":
    main()
