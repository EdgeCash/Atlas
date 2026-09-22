"""Team reference table: identity, classification and venue geography."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from atlas import config
from atlas.sources import sportsdataverse as sdv
from atlas.util import get_logger, write_parquet

LOG = get_logger(__name__)

KEEP = [
    "team_id",
    "school",
    "abbreviation",
    "conference",
    "classification",
    "venue_id",
    "venue_name",
    "city",
    "state",
    "latitude",
    "longitude",
    "elevation",
    "dome",
]


def build_teams(raw: Path, staging: Path, seasons: list[int]) -> pd.DataFrame:
    frames = []
    for season in seasons:
        path = sdv.team_info_path(raw, season)
        if not path.exists():
            continue
        df = pd.read_parquet(path)
        df = df[[c for c in KEEP if c in df.columns]].copy()
        df["season"] = season
        frames.append(df)
    if not frames:
        raise FileNotFoundError("no team_info files found - run atlas.ingest first")
    teams = pd.concat(frames, ignore_index=True)
    teams["team_id"] = teams["team_id"].astype("int64")
    teams = teams.drop_duplicates(["season", "team_id"], keep="last")
    write_parquet(teams, staging / "teams.parquet")
    return teams


def venues(teams: pd.DataFrame) -> pd.DataFrame:
    """One row per venue with the best available coordinates."""
    cols = ["venue_id", "venue_name", "latitude", "longitude", "elevation", "dome"]
    v = teams[[c for c in cols if c in teams.columns]].dropna(subset=["venue_id"]).copy()
    v["venue_id"] = v["venue_id"].astype("int64")
    v = v.dropna(subset=["latitude", "longitude"])
    return v.drop_duplicates("venue_id", keep="last")


def home_sites(teams: pd.DataFrame) -> pd.DataFrame:
    """Each team's home coordinates per season (origin for travel distance)."""
    cols = ["season", "team_id", "latitude", "longitude", "elevation"]
    t = teams[[c for c in cols if c in teams.columns]].copy()
    return t.rename(
        columns={"latitude": "home_lat", "longitude": "home_lon", "elevation": "home_elev"}
    )


def load(staging: Path) -> pd.DataFrame:
    return pd.read_parquet(staging / "teams.parquet")


def main() -> None:
    paths = config.paths().ensure()
    build_teams(paths.raw, paths.staging, config.seasons())


if __name__ == "__main__":
    main()
