"""nflverse: the NFL's open data, cached one file per season, no key.

    python -m atlas.sources.nflverse                # 2011 to the current season
    python -m atlas.sources.nflverse --seasons 2024 2025

Step 0 of `docs/MODEL_PLAN_NFL.md`. Every file is a parquet on a GitHub
release of ``nflverse/nflverse-data``, verified fetchable without a key:

* ``pbp``           - play-by-play with EPA, WP, CPOE, drives and the closing
                      line, 372 columns; trimmed to :data:`PBP_COLUMNS` on
                      the way in, as the college play-by-play is
* ``schedules``     - one file, every game 1999 on: result, spread, total,
                      moneylines, the quarterbacks of record, coaches, rest,
                      roof, surface, weather
* ``injuries``      - weekly reports, 2009 on
* ``depth_charts``  - who is QB1 this week, 2001 on
* ``snap_counts``   - offence/defence/special-teams snaps per player-game, 2012 on
* ``weekly_rosters``- status and experience per player-week, 2002 on
* ``stats_player``  - every player's box score per week, 1999 on: passing,
                      rushing, receiving, targets, air yards, target share -
                      the raw material of the DFS player model
                      (`docs/MODEL_PLAN_DFS.md`)

Cached exactly as ``data/raw/cfbd`` is: a completed season is fetched once
and kept; the current season is re-fetched on every ingest because its
files change weekly. Nothing here is point-in-time - the schedules file
carries the quarterback who *did* start, the pbp the closing line - and
what the model may see before kickoff is decided in staging, not here.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from atlas import config
from atlas.util import download, get_logger, read_parquet, write_parquet

LOG = get_logger(__name__)

RELEASES = "https://github.com/nflverse/nflverse-data/releases/download"

#: The walk-forward in the plan starts here; the state model needs history
#: behind its first test season and Elo needs a decade to settle.
FIRST_SEASON = 2011

#: First season each per-season release exists for.
FIRST_AVAILABLE = {"pbp": 1999, "injuries": 2009, "depth_charts": 2001, "snap_counts": 2012, "weekly_rosters": 2002,
                   "stats_player": 1999}

#: The play-by-play columns Atlas keeps. Everything the staging table, the
#: drive model and the score-state tables need, and nothing per-tackler.
PBP_COLUMNS = [
    # keys and clock
    "play_id", "game_id", "old_game_id", "season", "season_type", "week", "game_date", "start_time",
    "home_team", "away_team", "posteam", "posteam_type", "defteam", "qtr", "time", "quarter_seconds_remaining",
    "half_seconds_remaining", "game_seconds_remaining", "game_half", "play_type", "play_type_nfl", "special",
    "play", "aborted_play", "play_deleted", "order_sequence",
    # situation
    "down", "ydstogo", "yardline_100", "goal_to_go", "side_of_field", "shotgun", "no_huddle", "qb_dropback",
    "qb_kneel", "qb_spike", "qb_scramble", "posteam_timeouts_remaining", "defteam_timeouts_remaining",
    "posteam_score", "defteam_score", "score_differential", "posteam_score_post", "defteam_score_post",
    "score_differential_post", "total_home_score", "total_away_score",
    # what happened
    "yards_gained", "pass", "rush", "pass_attempt", "rush_attempt", "complete_pass", "incomplete_pass",
    "sack", "interception", "fumble", "fumble_lost", "touchdown", "pass_touchdown", "rush_touchdown",
    "return_touchdown", "safety", "penalty", "penalty_team", "penalty_yards", "first_down", "third_down_converted",
    "third_down_failed", "fourth_down_converted", "fourth_down_failed", "field_goal_attempt", "field_goal_result",
    "kick_distance", "extra_point_attempt", "extra_point_result", "two_point_attempt", "two_point_conv_result",
    "punt_attempt", "kickoff_attempt", "air_yards", "yards_after_catch", "pass_length", "pass_location",
    "run_location", "run_gap",
    # the model's inputs
    "ep", "epa", "qb_epa", "air_epa", "yac_epa", "success", "wp", "wpa", "vegas_wp", "vegas_home_wp", "home_wp",
    "cp", "cpoe", "xpass", "pass_oe", "series", "series_success", "series_result",
    # drives
    "drive", "fixed_drive", "fixed_drive_result", "drive_ended_with_score", "drive_play_count",
    "drive_time_of_possession", "drive_first_downs", "drive_inside20", "drive_start_transition",
    "drive_end_transition", "drive_start_yard_line", "drive_end_yard_line", "drive_quarter_start",
    "drive_quarter_end", "drive_game_clock_start", "drive_game_clock_end",
    # people
    "passer_player_id", "passer_player_name", "passer_id", "passer", "rusher_player_id", "rusher_player_name",
    "receiver_player_id", "receiver_player_name",
    # game context carried on every play
    "home_score", "away_score", "result", "total", "spread_line", "total_line", "div_game", "roof", "surface",
    "temp", "wind", "location", "stadium", "stadium_id", "home_coach", "away_coach", "weather",
]


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------


def nfl_dir(raw: Path) -> Path:
    return raw / "nfl"


def pbp_path(raw: Path, season: int) -> Path:
    return nfl_dir(raw) / f"pbp_{season}.parquet"


def schedules_path(raw: Path) -> Path:
    return nfl_dir(raw) / "schedules.parquet"


def injuries_path(raw: Path, season: int) -> Path:
    return nfl_dir(raw) / f"injuries_{season}.parquet"


def depth_charts_path(raw: Path, season: int) -> Path:
    return nfl_dir(raw) / f"depth_charts_{season}.parquet"


def snap_counts_path(raw: Path, season: int) -> Path:
    return nfl_dir(raw) / f"snap_counts_{season}.parquet"


def rosters_path(raw: Path, season: int) -> Path:
    return nfl_dir(raw) / f"rosters_{season}.parquet"


def player_stats_path(raw: Path, season: int) -> Path:
    return nfl_dir(raw) / f"stats_player_{season}.parquet"


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------


def _release(tag: str, filename: str) -> str:
    return f"{RELEASES}/{tag}/{filename}"


def _fresh(dest: Path, refresh: bool) -> None:
    """Drop a cached file so :func:`atlas.util.download` fetches it again."""
    if refresh and dest.exists():
        dest.unlink()


def fetch_play_by_play(raw: Path, season: int, *, refresh: bool = False, keep_full: bool = False) -> Path:
    """One season of play-by-play, trimmed to :data:`PBP_COLUMNS`.

    The 20 MB source file is deleted after trimming unless ``keep_full`` is
    set, so sixteen seasons cost a few hundred megabytes of transient disk
    and a few tens permanent.
    """
    dest = pbp_path(raw, season)
    _fresh(dest, refresh)
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    full = nfl_dir(raw) / f"_full_play_by_play_{season}.parquet"
    full.unlink(missing_ok=True)
    download(_release("pbp", f"play_by_play_{season}.parquet"), full)
    write_parquet(_read_available_columns(full, PBP_COLUMNS), dest)
    if not keep_full:
        full.unlink(missing_ok=True)
    return dest


def fetch_schedules(raw: Path, *, refresh: bool = True) -> Path:
    """Every game, 1999 on, in one file. Refreshed by default: it carries
    this week's results and lines."""
    dest = schedules_path(raw)
    _fresh(dest, refresh)
    return download(_release("schedules", "games.parquet"), dest)


def fetch_injuries(raw: Path, season: int, *, refresh: bool = False) -> Path:
    dest = injuries_path(raw, season)
    _fresh(dest, refresh)
    return download(_release("injuries", f"injuries_{season}.parquet"), dest)


def fetch_depth_charts(raw: Path, season: int, *, refresh: bool = False) -> Path:
    dest = depth_charts_path(raw, season)
    _fresh(dest, refresh)
    return download(_release("depth_charts", f"depth_charts_{season}.parquet"), dest)


def fetch_snap_counts(raw: Path, season: int, *, refresh: bool = False) -> Path:
    dest = snap_counts_path(raw, season)
    _fresh(dest, refresh)
    return download(_release("snap_counts", f"snap_counts_{season}.parquet"), dest)


def fetch_rosters(raw: Path, season: int, *, refresh: bool = False) -> Path:
    dest = rosters_path(raw, season)
    _fresh(dest, refresh)
    return download(_release("weekly_rosters", f"roster_weekly_{season}.parquet"), dest)


def fetch_player_stats(raw: Path, season: int, *, refresh: bool = False) -> Path:
    dest = player_stats_path(raw, season)
    _fresh(dest, refresh)
    return download(_release("stats_player", f"stats_player_week_{season}.parquet"), dest)


FETCHERS = {
    "pbp": fetch_play_by_play,
    "injuries": fetch_injuries,
    "depth_charts": fetch_depth_charts,
    "snap_counts": fetch_snap_counts,
    "weekly_rosters": fetch_rosters,
    "stats_player": fetch_player_stats,
}


def current_season(today: datetime | None = None) -> int:
    """The NFL season in progress: it starts in September and ends in February."""
    today = today or datetime.now(UTC)
    return today.year if today.month >= 8 else today.year - 1


def fetch_all(raw: Path, seasons: list[int], *, current: int | None = None) -> dict[str, list[Path]]:
    """Fetch every nflverse file Atlas uses for ``seasons``.

    ``current`` (default: the season in progress) is re-fetched whole; every
    other season is served from the cache. One dataset's failure for one
    season is logged and skipped, never fatal: a release that does not yet
    have this week's file must not stop the rest.
    """
    current = current_season() if current is None else current
    out: dict[str, list[Path]] = {"schedules": []}
    try:
        out["schedules"].append(fetch_schedules(raw, refresh=True))
    except Exception as exc:  # noqa: BLE001 - logged, the rest still runs
        LOG.warning("nflverse schedules failed: %s", exc)
    for name, fn in FETCHERS.items():
        got = []
        for season in seasons:
            if season < FIRST_AVAILABLE[name]:
                continue
            try:
                got.append(fn(raw, season, refresh=(season == current)))
            except Exception as exc:  # noqa: BLE001 - one season must not kill the run
                LOG.warning("nflverse %s %s failed: %s", name, season, exc)
        out[name] = got
    return out


def _read_available_columns(path: Path, wanted: list[str]) -> pd.DataFrame:
    import pyarrow.parquet as pq

    present = set(pq.ParquetFile(path).schema_arrow.names)
    cols = [c for c in wanted if c in present]
    missing = [c for c in wanted if c not in present]
    if missing:
        LOG.warning("%s: missing pbp columns %s", path.name, missing)
    return read_parquet(path, columns=cols)


def load_schedules(raw: Path, seasons: list[int] | None = None) -> pd.DataFrame:
    df = read_parquet(schedules_path(raw))
    return df if seasons is None else df[df["season"].isin(seasons)].reset_index(drop=True)


def main() -> None:
    ap = argparse.ArgumentParser(description="Fetch and cache nflverse data")
    ap.add_argument("--seasons", type=int, nargs="*", default=None,
                    help=f"default {FIRST_SEASON} to the current season")
    ap.add_argument("--current", type=int, default=None, help="the season to re-fetch whole")
    args = ap.parse_args()
    paths = config.paths().ensure()
    seasons = args.seasons or list(range(FIRST_SEASON, current_season() + 1))
    got = fetch_all(paths.raw, seasons, current=args.current)
    for name, files in got.items():
        LOG.info("%s: %d files", name, len(files))


if __name__ == "__main__":
    main()
