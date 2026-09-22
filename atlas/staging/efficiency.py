"""Per-team, per-game efficiency from play-by-play.

Every metric here is a *box score of one game*, not a rating. Turning these
into a pre-kickoff feature is the job of :mod:`atlas.features.point_in_time`,
which only ever averages games a team had already played.

Definitions (chosen to match the conventional college-football advanced-stats
vocabulary so the numbers are comparable to published SP+/FEI style figures):

scrimmage play
    ``rush`` or ``pass``, excluding plays wiped out by penalty. Kickoffs,
    punts and field goals are not efficiency plays.
garbage time
    Dropped before aggregation, using the standard per-quarter margin
    thresholds (38/28/22/16). Overtime is never garbage time.
off_epa / def_epa
    Mean expected points added per scrimmage play, on offense and allowed on
    defense. Lower ``def_epa`` is better.
success_rate
    Share of plays flagged successful (50% of needed yards on 1st down, 70%
    on 2nd, 100% on 3rd/4th).
explosiveness
    Mean EPA on *successful* plays only (IsoPPP). It separates "how often"
    from "how big".
havoc
    Share of defensive scrimmage plays with a tackle for loss on a run, a
    sack, an interception, a pass breakup or a forced fumble.
finishing_drives
    Points per scoring opportunity, where a scoring opportunity is a drive
    that reached the opponent's 40-yard line.
pace
    Seconds of game clock consumed per offensive scrimmage play.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from atlas import config
from atlas.sources import sportsdataverse as sdv
from atlas.util import get_logger, write_parquet

LOG = get_logger(__name__)

METRIC_COLUMNS = [
    "off_epa",
    "def_epa",
    "success_rate",
    "def_success_rate",
    "explosiveness",
    "def_explosiveness",
    "havoc",
    "finishing_drives",
    "pace",
    "plays_per_game",
    "points_for",
    "points_against",
]


def build_efficiency(raw: Path, staging: Path, seasons: list[int]) -> pd.DataFrame:
    frames = []
    for season in seasons:
        path = sdv.pbp_path(raw, season)
        if not path.exists():
            LOG.warning("no play-by-play for %s", season)
            continue
        frames.append(_season_efficiency(pd.read_parquet(path), season))
    if not frames:
        raise FileNotFoundError("no play-by-play found - run atlas.ingest first")
    eff = pd.concat(frames, ignore_index=True)
    write_parquet(eff, staging / "team_game_efficiency.parquet")
    return eff


def _season_efficiency(pbp: pd.DataFrame, season: int) -> pd.DataFrame:
    pbp = pbp.dropna(subset=["game_id", "pos_team", "def_pos_team"]).copy()
    pbp["game_id"] = pbp["game_id"].astype("int64")
    pbp["season"] = season

    # Resolve the offensive/defensive team ids from the team names.
    home_name = pbp["home"].astype("string")
    pbp["off_team_id"] = np.where(
        pbp["pos_team"].astype("string") == home_name,
        pbp["home_team_id"],
        pbp["away_team_id"],
    )
    pbp["def_team_id"] = np.where(
        pbp["pos_team"].astype("string") == home_name,
        pbp["away_team_id"],
        pbp["home_team_id"],
    )

    plays = _scrimmage_plays(pbp)
    plays = plays[~_is_garbage_time(plays)]

    offense = _offense_aggregates(plays)
    defense = _defense_aggregates(plays)
    drives = _drive_aggregates(pbp)

    eff = offense.merge(defense, on=["game_id", "team_id"], how="outer")
    eff = eff.merge(drives, on=["game_id", "team_id"], how="left")
    eff["season"] = season
    LOG.info("season %s: efficiency rows %d", season, len(eff))
    return eff


def _scrimmage_plays(pbp: pd.DataFrame) -> pd.DataFrame:
    is_scrimmage = (pbp["rush"].fillna(0) == 1) | (pbp["pass"].fillna(0) == 1)
    no_play = pbp["penalty_no_play"].fillna(False).astype(bool)
    return pbp[is_scrimmage & ~no_play & pbp["EPA"].notna()].copy()


def _is_garbage_time(plays: pd.DataFrame) -> pd.Series:
    margin = plays["score_diff"].abs()
    period = plays["period"].fillna(1).astype(int)
    threshold = period.map(config.GARBAGE_TIME_MARGIN)
    # Overtime (period > 4) has no threshold and is never garbage time.
    return threshold.notna() & (margin > threshold)


def _offense_aggregates(plays: pd.DataFrame) -> pd.DataFrame:
    grp = plays.groupby(["game_id", "off_team_id"])
    out = grp.agg(
        off_epa=("EPA", "mean"),
        success_rate=("success", "mean"),
        off_plays=("EPA", "size"),
    )
    # Plays per game is a clock-free pace proxy; the drive clock is missing
    # for a sizeable minority of games in recent seasons.
    out["plays_per_game"] = out["off_plays"].astype(float)
    successful = plays[plays["success"].fillna(0) == 1]
    out["explosiveness"] = successful.groupby(["game_id", "off_team_id"])["EPA"].mean()
    return out.reset_index().rename(columns={"off_team_id": "team_id"})


def _defense_aggregates(plays: pd.DataFrame) -> pd.DataFrame:
    plays = plays.copy()
    plays["havoc_play"] = (
        (plays["stuffed_run"].fillna(0) == 1)
        | (plays["sack"].fillna(0) == 1)
        | (plays["int"].fillna(0) == 1)
        | plays["pass_breakup_player_name"].notna()
        | plays["fumble_forced_player_name"].notna()
    ).astype(float)
    grp = plays.groupby(["game_id", "def_team_id"])
    out = grp.agg(
        def_epa=("EPA", "mean"),
        def_success_rate=("success", "mean"),
        havoc=("havoc_play", "mean"),
        def_plays=("EPA", "size"),
    )
    successful = plays[plays["success"].fillna(0) == 1]
    out["def_explosiveness"] = successful.groupby(["game_id", "def_team_id"])["EPA"].mean()
    return out.reset_index().rename(columns={"def_team_id": "team_id"})


def _drive_aggregates(pbp: pd.DataFrame) -> pd.DataFrame:
    """Finishing drives and pace, computed on drives rather than plays."""
    cols = [
        "game_id",
        "off_team_id",
        "drive_number",
        "yards_to_goal",
        "drive_pts",
        "drive_time_minutes_elapsed",
        "drive_time_seconds_elapsed",
    ]
    if not set(cols).issubset(pbp.columns):
        return pd.DataFrame(columns=["game_id", "team_id", "finishing_drives", "pace"])

    scrimmage = _scrimmage_plays(pbp)
    plays_per_drive = (
        scrimmage.groupby(["game_id", "off_team_id", "drive_number"]).size().rename("plays")
    )

    drives = pbp[cols].copy()
    grouped = drives.groupby(["game_id", "off_team_id", "drive_number"])
    summary = grouped.agg(
        closest_to_goal=("yards_to_goal", "min"),
        drive_points=("drive_pts", "max"),
        drive_minutes=("drive_time_minutes_elapsed", "max"),
        drive_seconds=("drive_time_seconds_elapsed", "max"),
    )
    summary = summary.join(plays_per_drive, how="left")
    summary["elapsed"] = summary["drive_minutes"].fillna(0) * 60 + summary["drive_seconds"].fillna(0)
    summary["is_scoring_opp"] = (
        summary["closest_to_goal"] <= config.SCORING_OPPORTUNITY_YARDS_TO_GOAL
    )
    summary = summary.reset_index()

    opps = summary[summary["is_scoring_opp"]]
    finishing = opps.groupby(["game_id", "off_team_id"]).agg(
        scoring_opps=("is_scoring_opp", "sum"),
        scoring_opp_points=("drive_points", "sum"),
    )
    finishing["finishing_drives"] = (
        finishing["scoring_opp_points"] / finishing["scoring_opps"]
    ).replace([np.inf, -np.inf], np.nan)

    # Pace uses only drives with a sane clock reading. Per-drive seconds per
    # play outside [5, 90] means the clock fields are corrupt for that drive.
    paced = summary[(summary["plays"].fillna(0) >= 2) & summary["elapsed"].between(1, 900)].copy()
    paced["sec_per_play"] = paced["elapsed"] / paced["plays"]
    paced = paced[paced["sec_per_play"].between(5, 90)]
    pace = paced.groupby(["game_id", "off_team_id"]).apply(
        lambda d: d["elapsed"].sum() / d["plays"].sum(), include_groups=False
    )
    out = finishing.join(pace.rename("pace"), how="outer").reset_index()
    return out.rename(columns={"off_team_id": "team_id"})


def load(staging: Path) -> pd.DataFrame:
    return pd.read_parquet(staging / "team_game_efficiency.parquet")


def main() -> None:
    paths = config.paths().ensure()
    build_efficiency(paths.raw, paths.staging, config.seasons())


if __name__ == "__main__":
    main()
