"""Team-game efficiency, drives and the quarterback of record, from play-by-play.

The same shape as the college table so the opponent adjustment and the
point-in-time builder read it unchanged: one row per (game, team) with
offensive and defensive EPA, success and explosiveness, havoc, pace, plays,
points, plus what the NFL has that college lacks - drive outcomes by type,
QB EPA per dropback and CPOE for the passer who threw most, which is what
the QB state in step 4 is built from.

Garbage time is excluded from the efficiency metrics by the same
quarter-by-margin thresholds as college (``config.GARBAGE_TIME_MARGIN``);
drives and points are counted whole.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from atlas import config
from atlas.sources import nflverse
from atlas.staging.nfl.games import team_id
from atlas.util import get_logger, write_parquet

LOG = get_logger(__name__)

METRIC_COLUMNS = [
    "off_epa", "success_rate", "explosiveness", "off_plays", "plays_per_game", "pace",
    "def_epa", "def_success_rate", "def_explosiveness", "havoc", "def_plays",
    "drives", "points_per_drive", "td_rate", "fg_rate", "punt_rate", "turnover_rate", "finishing_drives",
    "points_for", "points_against", "qb_id", "qb_name", "qb_dropbacks", "qb_epa_per_dropback", "qb_cpoe",
    "net_epa",
]

DRIVE_RESULTS = {
    "Touchdown": "td", "Field goal": "fg", "Punt": "punt", "Turnover": "turnover",
    "Turnover on downs": "downs", "Missed field goal": "missed_fg", "End of half": "end_half",
    "Opp touchdown": "opp_td", "Safety": "safety",
}


def build_efficiency(raw: Path, staging: Path, seasons: list[int]) -> pd.DataFrame:
    frames, passers = [], []
    for season in seasons:
        path = nflverse.pbp_path(raw, season)
        if not path.exists():
            LOG.warning("no NFL play-by-play for %s", season)
            continue
        pbp = pd.read_parquet(path)
        frames.append(season_efficiency(pbp, season))
        passers.append(passer_games(pbp, season))
    if not frames:
        raise FileNotFoundError("no NFL play-by-play found - run `make nfl-ingest` first")
    eff = pd.concat(frames, ignore_index=True)
    write_parquet(eff, staging / "nfl" / "team_game_efficiency.parquet")
    write_parquet(pd.concat(passers, ignore_index=True), staging / "nfl" / "passer_games.parquet")
    return eff


def passer_games(pbp: pd.DataFrame, season: int) -> pd.DataFrame:
    """Every passer's dropbacks in every game: the quarterback's own record.

    The quarterback of record is one row of this; the backup who threw
    eleven mop-up passes is another, and those eleven are the only evidence
    a new starter's prior can be built from. Garbage time is kept - a backup's
    record is mostly garbage time.
    """
    pbp = pbp.dropna(subset=["game_id", "posteam"]).copy()
    plays = _scrimmage_plays(pbp)
    drop = plays[(plays["qb_dropback"].fillna(0) == 1) & plays["passer_player_id"].notna()].copy()
    drop["team_id"] = team_id(drop["posteam"])
    out = drop.groupby(["game_id", "team_id", "passer_player_id"], as_index=False).agg(
        dropbacks=("epa", "size"), qb_epa_per_dropback=("qb_epa", "mean"), qb_cpoe=("cpoe", "mean"),
        passer_name=("passer_player_name", "first"))
    out = out.rename(columns={"passer_player_id": "passer_id"})
    out["season"] = season
    weeks = pbp.drop_duplicates("game_id").set_index("game_id")
    out["week"] = out["game_id"].map(pd.to_numeric(weeks["week"], errors="coerce")).astype("Int64")
    out["game_date"] = out["game_id"].map(weeks["game_date"].astype(str)) if "game_date" in weeks else pd.NA
    return out[["game_id", "season", "week", "game_date", "team_id", "passer_id", "passer_name", "dropbacks",
                "qb_epa_per_dropback", "qb_cpoe"]]


def load_passers(staging: Path) -> pd.DataFrame:
    return pd.read_parquet(staging / "nfl" / "passer_games.parquet")


def season_efficiency(pbp: pd.DataFrame, season: int) -> pd.DataFrame:
    pbp = pbp.dropna(subset=["game_id", "posteam", "defteam"]).copy()
    pbp["game_id"] = pbp["game_id"].astype(str)
    pbp["off_team_id"] = team_id(pbp["posteam"])
    pbp["def_team_id"] = team_id(pbp["defteam"])
    pbp["week"] = pd.to_numeric(pbp["week"], errors="coerce")

    plays = _scrimmage_plays(pbp)
    clean = plays[~_is_garbage_time(plays)]

    offense = _offense_aggregates(clean)
    defense = _defense_aggregates(clean)
    drives = _drive_aggregates(pbp)
    pace = _pace(pbp, plays)
    qb = _quarterback(plays)

    eff = offense.merge(defense, on=["game_id", "team_id"], how="outer")
    for extra in (drives, pace, qb):
        eff = eff.merge(extra, on=["game_id", "team_id"], how="left")
    eff["net_epa"] = eff["off_epa"] - eff["def_epa"]
    eff["season"] = season
    weeks = pbp.drop_duplicates("game_id").set_index("game_id")["week"]
    eff["week"] = eff["game_id"].map(weeks).astype("Int64")
    LOG.info("nfl season %s: efficiency rows %d", season, len(eff))
    return eff[["game_id", "season", "week", "team_id", *[c for c in METRIC_COLUMNS if c in eff.columns]]]


def _scrimmage_plays(pbp: pd.DataFrame) -> pd.DataFrame:
    is_scrimmage = (pbp["rush"].fillna(0) == 1) | (pbp["pass"].fillna(0) == 1)
    no_play = pbp["play_type"].astype("string").fillna("") == "no_play"
    return pbp[is_scrimmage & ~no_play & pbp["epa"].notna()].copy()


def _is_garbage_time(plays: pd.DataFrame) -> pd.Series:
    margin = pd.to_numeric(plays["score_differential"], errors="coerce").abs()
    period = pd.to_numeric(plays["qtr"], errors="coerce").fillna(1).astype(int)
    threshold = period.map(config.GARBAGE_TIME_MARGIN)
    return threshold.notna() & (margin > threshold)


def _offense_aggregates(plays: pd.DataFrame) -> pd.DataFrame:
    grp = plays.groupby(["game_id", "off_team_id"])
    out = grp.agg(off_epa=("epa", "mean"), success_rate=("success", "mean"), off_plays=("epa", "size"))
    out["plays_per_game"] = out["off_plays"].astype(float)
    successful = plays[plays["success"].fillna(0) == 1]
    out["explosiveness"] = successful.groupby(["game_id", "off_team_id"])["epa"].mean()
    return out.reset_index().rename(columns={"off_team_id": "team_id"})


def _defense_aggregates(plays: pd.DataFrame) -> pd.DataFrame:
    plays = plays.copy()
    plays["havoc_play"] = ((plays["sack"].fillna(0) == 1) | (plays["interception"].fillna(0) == 1)
                           | (plays["fumble_lost"].fillna(0) == 1)).astype(float)
    grp = plays.groupby(["game_id", "def_team_id"])
    out = grp.agg(def_epa=("epa", "mean"), def_success_rate=("success", "mean"), havoc=("havoc_play", "mean"),
                  def_plays=("epa", "size"))
    successful = plays[plays["success"].fillna(0) == 1]
    out["def_explosiveness"] = successful.groupby(["game_id", "def_team_id"])["epa"].mean()
    return out.reset_index().rename(columns={"def_team_id": "team_id"})


def _drive_aggregates(pbp: pd.DataFrame) -> pd.DataFrame:
    """Drive outcomes per team-game from nflverse's ``fixed_drive_result``."""
    d = pbp.dropna(subset=["fixed_drive"]).drop_duplicates(["game_id", "fixed_drive"])
    d = d[["game_id", "off_team_id", "fixed_drive_result", "drive_inside20", "drive_ended_with_score"]].copy()
    d["result"] = d["fixed_drive_result"].map(DRIVE_RESULTS).fillna("other")
    counts = d.pivot_table(index=["game_id", "off_team_id"], columns="result", values="fixed_drive_result",
                           aggfunc="size", fill_value=0)
    for key in ("td", "fg", "punt", "turnover", "downs", "missed_fg", "end_half"):
        if key not in counts.columns:
            counts[key] = 0
    drives = counts.sum(axis=1).rename("drives")
    out = pd.DataFrame({"drives": drives})
    out["td_rate"] = counts["td"] / drives
    out["fg_rate"] = counts["fg"] / drives
    out["punt_rate"] = counts["punt"] / drives
    out["turnover_rate"] = (counts["turnover"] + counts["downs"]) / drives
    inside = d[d["drive_inside20"].fillna(0) == 1].groupby(["game_id", "off_team_id"])
    scored = inside["drive_ended_with_score"].mean()
    out["finishing_drives"] = scored
    # Points for and against from the final score carried on every play.
    last = pbp.sort_values(["game_id", "play_id"]).drop_duplicates("game_id", keep="last")
    home_pts = last.set_index("game_id")["home_score"]
    away_pts = last.set_index("game_id")["away_score"]
    home_id = team_id(last.set_index("game_id")["home_team"])
    out = out.reset_index().rename(columns={"off_team_id": "team_id"})
    is_home = out["team_id"].to_numpy() == out["game_id"].map(home_id).to_numpy()
    out["points_for"] = np.where(is_home, out["game_id"].map(home_pts), out["game_id"].map(away_pts)).astype(float)
    out["points_against"] = np.where(is_home, out["game_id"].map(away_pts), out["game_id"].map(home_pts)).astype(float)
    out["points_per_drive"] = out["points_for"] / out["drives"]
    return out


def _pace(pbp: pd.DataFrame, plays: pd.DataFrame) -> pd.DataFrame:
    """Seconds of possession per offensive play, from the drive clock."""
    d = pbp.dropna(subset=["fixed_drive"]).drop_duplicates(["game_id", "fixed_drive"])
    top = d["drive_time_of_possession"].astype("string").fillna("0:00")
    parts = top.str.split(":", expand=True)
    seconds = pd.to_numeric(parts[0], errors="coerce").fillna(0) * 60 + pd.to_numeric(parts[1], errors="coerce").fillna(0)
    possession = seconds.groupby([d["game_id"], d["off_team_id"]]).sum()
    n_plays = plays.groupby(["game_id", "off_team_id"]).size()
    pace = (possession / n_plays).rename("pace").reset_index().rename(columns={"off_team_id": "team_id"})
    return pace[pace["pace"].between(5, 90)]


def _quarterback(plays: pd.DataFrame) -> pd.DataFrame:
    """The passer with the most dropbacks, and their EPA per dropback and CPOE."""
    drop = plays[(plays["qb_dropback"].fillna(0) == 1) & plays["passer_player_id"].notna()]
    per = drop.groupby(["game_id", "off_team_id", "passer_player_id"]).agg(
        qb_dropbacks=("epa", "size"), qb_epa_per_dropback=("qb_epa", "mean"), qb_cpoe=("cpoe", "mean"),
        qb_name=("passer_player_name", "first")).reset_index()
    per = per.sort_values(["game_id", "off_team_id", "qb_dropbacks"], ascending=[True, True, False])
    top = per.drop_duplicates(["game_id", "off_team_id"])
    return top.rename(columns={"off_team_id": "team_id", "passer_player_id": "qb_id"})


def load(staging: Path) -> pd.DataFrame:
    return pd.read_parquet(staging / "nfl" / "team_game_efficiency.parquet")
