"""Assemble the NBA warehouse: ``data/warehouse/nba.duckdb``.

    python -m atlas.staging.nba.build              # 2007-08 to the current season
    python -m atlas.staging.nba.build --seasons 2024 2025

Tables:

* ``research_games`` - one row per game (`games.py`): the schedule, the
                       final, rest, and the archive's closing lines where it
                       has them, in the column conventions every Atlas model
                       reads;
* ``team_games``     - each team's box score per game with a possessions
                       estimate;
* ``player_games``   - each player's box score per game, 2015-16 on
                       (`players.py`), the props model's history.

Every row is a fact about a finished game or the schedule. What a projection
may see before the tip is decided by the model, which only ever reads games
before the one it prices.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pandas as pd

from atlas import config
from atlas.sources import nba
from atlas.staging.nba import games as games_stage
from atlas.staging.nba import players as players_stage
from atlas.util import get_logger, write_parquet

LOG = get_logger(__name__)


def warehouse_path(warehouse: Path | None = None) -> Path:
    return (warehouse or config.paths().warehouse) / "nba.duckdb"


def build(seasons: list[int] | None = None, *, raw: Path | None = None, warehouse: Path | None = None,
          staging: Path | None = None) -> pd.DataFrame:
    paths = config.paths().ensure()
    raw = raw or paths.raw
    warehouse = warehouse or paths.warehouse
    staging = staging or paths.staging
    seasons = seasons or list(range(nba.FIRST_SEASON, nba.current_season() + 1))
    games = games_stage.build_games(raw, seasons)
    teams = games_stage.team_games(raw, seasons)
    players = players_stage.build_players(raw, [s for s in seasons if s >= nba.PROPS_FIRST_SEASON])
    (staging / "nba").mkdir(parents=True, exist_ok=True)
    write_parquet(games, staging / "nba" / "research_games.parquet")
    write_parquet(teams, staging / "nba" / "team_games.parquet")
    write_parquet(players, staging / "nba" / "player_games.parquet")
    db = warehouse_path(warehouse)
    con = duckdb.connect(str(db))
    try:
        con.register("frame", games)
        con.execute("CREATE OR REPLACE TABLE research_games AS SELECT * FROM frame")
        con.register("teams", teams)
        con.execute("CREATE OR REPLACE TABLE team_games AS SELECT * FROM teams")
        con.register("players", players)
        con.execute("CREATE OR REPLACE TABLE player_games AS SELECT * FROM players")
    finally:
        con.close()
    manifest = {"generated_at": datetime.now(UTC).isoformat(timespec="seconds"), "seasons": seasons,
                "games": int(len(games)), "completed": int(games["completed"].sum()) if len(games) else 0,
                "with_close": int(games["closing_spread"].notna().sum()) if len(games) else 0,
                "player_games": int(len(players))}
    (warehouse / "NBA_MANIFEST.json").write_text(json.dumps(manifest, indent=1) + "\n")
    LOG.info("nba warehouse -> %s (%d games, %d completed, %d with a close)", db, len(games), manifest["completed"],
             manifest["with_close"])
    return games


def main() -> None:
    ap = argparse.ArgumentParser(description="Build the NBA warehouse")
    ap.add_argument("--seasons", type=int, nargs="*", help="start years; default 2007 to the current season")
    args = ap.parse_args()
    build(args.seasons or None)


if __name__ == "__main__":
    main()
