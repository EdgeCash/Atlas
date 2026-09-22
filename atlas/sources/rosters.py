"""Season rosters from the sportsdataverse mirror.

Used to classify a quarterback rather than merely name him: a roster carries
class year (so a freshman is identifiable) and team membership across seasons
(so a transfer is identifiable by appearing on a different team than last
year). Both are pre-season facts, known before a snap is taken.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from atlas.sources.sportsdataverse import RAW_BASE
from atlas.util import download, get_logger

LOG = get_logger(__name__)

KEEP = ["athlete_id", "first_name", "last_name", "team", "position", "year", "season"]


def roster_path(raw: Path, season: int) -> Path:
    return raw / "rosters" / f"rosters_{season}.parquet"


def fetch(raw: Path, season: int) -> Path:
    return download(
        f"{RAW_BASE}/rosters/parquet/cfb_rosters_{season}.parquet", roster_path(raw, season)
    )


def load(raw: Path, seasons: list[int], *, position: str | None = None) -> pd.DataFrame:
    frames = []
    for season in seasons:
        path = roster_path(raw, season)
        if not path.exists():
            continue
        df = pd.read_parquet(path)
        df = df[[c for c in KEEP if c in df.columns]].copy()
        if "season" not in df.columns:
            df["season"] = season
        frames.append(df)
    if not frames:
        return pd.DataFrame(columns=KEEP)
    out = pd.concat(frames, ignore_index=True)
    if position:
        out = out[out["position"] == position]
    out["player"] = (
        out["first_name"].fillna("").str.strip() + " " + out["last_name"].fillna("").str.strip()
    ).str.strip()
    return out
