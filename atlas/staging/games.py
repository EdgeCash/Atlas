"""Canonical game table plus the long (one row per team-game) view.

The long view is what every point-in-time feature is accumulated over: it
includes games against non-FBS opponents, because those games really were
played and a team's form before week 5 depends on them.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from atlas import config
from atlas.sources import sportsdataverse as sdv
from atlas.util import get_logger, write_parquet

LOG = get_logger(__name__)

GAME_COLUMNS = [
    "game_id",
    "season",
    "week",
    "season_type",
    "kickoff",
    "date",
    "away_team_id",
    "away_team",
    "away_division",
    "away_conference",
    "home_team_id",
    "home_team",
    "home_division",
    "home_conference",
    "away_score",
    "home_score",
    "margin",
    "total_points",
    "home_win",
    "neutral_site",
    "conference_game",
    "venue_id",
    "venue",
    "home_pregame_elo",
    "away_pregame_elo",
]


def build_games(raw: Path, staging: Path, seasons: list[int]) -> pd.DataFrame:
    frames = []
    for season in seasons:
        path = sdv.schedules_path(raw, season)
        if not path.exists():
            LOG.warning("no schedule for %s", season)
            continue
        frames.append(pd.read_parquet(path))
    if not frames:
        raise FileNotFoundError("no schedules found - run atlas.ingest first")
    raw_games = pd.concat(frames, ignore_index=True)
    games = _normalise(raw_games)
    write_parquet(games, staging / "games.parquet")

    long = to_long(games)
    write_parquet(long, staging / "team_games.parquet")
    return games


def _normalise(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out = out[out["season_type"].isin(config.SEASON_TYPES)]
    out = out[out["completed"].fillna(False).astype(bool)]
    out = out.dropna(subset=["home_points", "away_points", "start_date"])

    out["game_id"] = out["game_id"].astype("int64")
    out["season"] = out["season"].astype("int64")
    out["week"] = out["week"].astype("int64")
    out["kickoff"] = pd.to_datetime(out["start_date"], utc=True, format="ISO8601")
    out["date"] = out["kickoff"].dt.date.astype("string")

    out["home_score"] = out["home_points"].astype("int64")
    out["away_score"] = out["away_points"].astype("int64")
    out["margin"] = out["home_score"] - out["away_score"]
    out["total_points"] = out["home_score"] + out["away_score"]
    out["home_win"] = (out["margin"] > 0).astype("int8")

    out["home_team_id"] = out["home_id"].astype("int64")
    out["away_team_id"] = out["away_id"].astype("int64")
    out["neutral_site"] = out["neutral_site"].fillna(False).astype(bool)
    out["conference_game"] = out["conference_game"].fillna(False).astype(bool)

    # Ties are dropped from the home_win definition only; they remain in the
    # table because they still carry a margin and a total.
    out = out.sort_values(["kickoff", "game_id"]).reset_index(drop=True)
    cols = [c for c in GAME_COLUMNS if c in out.columns]
    games = out[cols].drop_duplicates("game_id", keep="last").reset_index(drop=True)
    LOG.info(
        "games: %d rows, seasons %s-%s",
        len(games),
        games["season"].min(),
        games["season"].max(),
    )
    return games


def to_long(games: pd.DataFrame) -> pd.DataFrame:
    """One row per team per game, from that team's own perspective."""
    base = [
        "game_id",
        "season",
        "week",
        "season_type",
        "kickoff",
        "neutral_site",
        "venue_id",
    ]
    home = games[base].copy()
    home["team_id"] = games["home_team_id"]
    home["team"] = games["home_team"]
    home["opponent_id"] = games["away_team_id"]
    home["opponent"] = games["away_team"]
    home["is_home"] = True
    home["points_for"] = games["home_score"]
    home["points_against"] = games["away_score"]
    home["opponent_division"] = games["away_division"]

    away = games[base].copy()
    away["team_id"] = games["away_team_id"]
    away["team"] = games["away_team"]
    away["opponent_id"] = games["home_team_id"]
    away["opponent"] = games["home_team"]
    away["is_home"] = False
    away["points_for"] = games["away_score"]
    away["points_against"] = games["home_score"]
    away["opponent_division"] = games["home_division"]

    long = pd.concat([home, away], ignore_index=True)
    long["margin"] = long["points_for"] - long["points_against"]
    long = long.sort_values(["team_id", "kickoff", "game_id"]).reset_index(drop=True)
    long["game_number"] = long.groupby(["team_id", "season"]).cumcount() + 1
    long["days_rest"] = (
        long.groupby(["team_id", "season"])["kickoff"].diff().dt.total_seconds() / 86400.0
    )
    long["days_rest"] = long["days_rest"].replace([np.inf, -np.inf], np.nan)
    return long


def load(staging: Path) -> pd.DataFrame:
    return pd.read_parquet(staging / "games.parquet")


def load_long(staging: Path) -> pd.DataFrame:
    return pd.read_parquet(staging / "team_games.parquet")


def main() -> None:
    paths = config.paths().ensure()
    build_games(paths.raw, paths.staging, config.seasons())


if __name__ == "__main__":
    main()
