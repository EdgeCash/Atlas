"""Open mirrors of CollegeFootballData published by the sportsdataverse project.

These are free and need no API key, which keeps the Atlas rebuild reproducible
for anyone who clones the repo:

* ``schedules``  - CFBD ``/games`` per season (results, venue, pregame Elo)
* ``team_info``  - CFBD ``/teams`` per season (venue lat/lon, classification)
* ``odds``       - historical betting market: opening + closing spread, total
                   and moneyline, per sportsbook
* ``play_by_play`` - cfbfastR play-by-play with EPA/success attached

Only the columns Atlas needs are retained from play-by-play; the published
files carry 362 columns and ~110 MB per season.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from atlas.util import download, get_logger, read_parquet, write_parquet

LOG = get_logger(__name__)

RAW_BASE = "https://raw.githubusercontent.com/sportsdataverse/cfbfastR-data/main"
PBP_RELEASE = (
    "https://github.com/sportsdataverse/sportsdataverse-data/releases/download/cfbfastR_cfb_pbp"
)

#: Play-by-play columns Atlas keeps. Anything missing from a season's file is
#: silently skipped (the published schema has drifted slightly over the years).
PBP_COLUMNS = [
    # identity / context
    "game_id",
    "year",
    "season",
    "week",
    "season_type",
    "start_date",
    "pos_team",
    "def_pos_team",
    "home",
    "away",
    "home_team_id",
    "away_team_id",
    "neutral_site",
    "completed",
    # market snapshot carried on the play rows (used to validate our own lines)
    "spread",
    "formatted_spread",
    "over_under",
    # play-level efficiency inputs
    "EPA",
    "success",
    "rush",
    "pass",
    "yards_gained",
    "down",
    "distance",
    "yards_to_goal",
    "period",
    "TimeSecsRem",
    "play_type",
    "penalty_no_play",
    "kickoff_play",
    "punt_play",
    "fg_inds",
    "sack",
    "int",
    "turnover",
    "fumble_vec",
    "stuffed_run",
    "pass_breakup_player_name",
    "fumble_forced_player_name",
    "score_diff",
    "scoring_opp",
    "rz_play",
    # drive level (finishing drives + pace)
    "drive_id",
    "drive_start_yards_to_goal",
    "drive_pts",
    "drive_number",
    "drive_time_minutes_elapsed",
    "drive_time_seconds_elapsed",
]


def schedules_path(raw: Path, season: int) -> Path:
    return raw / "schedules" / f"schedules_{season}.parquet"


def team_info_path(raw: Path, season: int) -> Path:
    return raw / "team_info" / f"team_info_{season}.parquet"


def odds_path(raw: Path) -> Path:
    return raw / "odds" / "cfb_line_odds.parquet"


def pbp_path(raw: Path, season: int) -> Path:
    return raw / "pbp" / f"pbp_{season}.parquet"


def fetch_schedules(raw: Path, season: int) -> Path:
    return download(f"{RAW_BASE}/schedules/parquet/cfb_schedules_{season}.parquet",
                    schedules_path(raw, season))


def fetch_team_info(raw: Path, season: int) -> Path:
    return download(f"{RAW_BASE}/team_info/parquet/cfb_team_info_{season}.parquet",
                    team_info_path(raw, season))


def fetch_odds(raw: Path) -> Path:
    return download(f"{RAW_BASE}/betting/parquet/cfb_line_odds.parquet", odds_path(raw))


def fetch_play_by_play(raw: Path, season: int, *, keep_full: bool = False) -> Path:
    """Download one season of play-by-play and persist a trimmed copy.

    The full 110 MB source file is deleted after trimming unless ``keep_full``
    is set, so a nine-season rebuild needs ~1 GB of transient disk rather than
    ~1 GB of permanent disk.
    """
    dest = pbp_path(raw, season)
    if dest.exists() and dest.stat().st_size > 0:
        LOG.debug("cached trimmed pbp %s", season)
        return dest
    full = raw / "pbp" / f"_full_play_by_play_{season}.parquet"
    download(f"{PBP_RELEASE}/play_by_play_{season}.parquet", full)
    df = _read_available_columns(full, PBP_COLUMNS)
    write_parquet(df, dest)
    if not keep_full:
        full.unlink(missing_ok=True)
    return dest


def _read_available_columns(path: Path, wanted: list[str]) -> pd.DataFrame:
    import pyarrow.parquet as pq

    present = set(pq.ParquetFile(path).schema_arrow.names)
    cols = [c for c in wanted if c in present]
    missing = [c for c in wanted if c not in present]
    if missing:
        LOG.warning("%s: missing pbp columns %s", path.name, missing)
    return read_parquet(path, columns=cols)
