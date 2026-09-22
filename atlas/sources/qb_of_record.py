"""Quarterback of record per team-game, derived from play-by-play.

**This is not a point-in-time source and never becomes a warehouse column.**
It records who actually threw the passes, which is knowable at kickoff at the
earliest. Phase 1B established that a quarterback change is the only signal in
the programme that moves the market residual; Phase 1C measures it properly,
and that measurement needs the retrospective truth.

The boundary is enforced two ways: nothing here is imported by
:mod:`atlas.warehouse.build`, and a test asserts no warehouse table carries a
``qb_`` column.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from atlas.sources import sportsdataverse as sdv
from atlas.util import download, get_logger, write_parquet

LOG = get_logger(__name__)

PASSER_COLUMNS = [
    "game_id", "year", "week", "pos_team", "home", "away",
    "home_team_id", "away_team_id", "passer_player_name", "EPA",
]


def qb_path(raw: Path, season: int) -> Path:
    return raw / "qb" / f"qb_{season}.parquet"


def build_season(raw: Path, season: int) -> pd.DataFrame:
    """Starter, attempts and share for every team-game in a season.

    The "starter" is the passer with the most attempts, which is the
    quarterback of record rather than literally the first snap. ``qb_share``
    says how clear-cut that was, so committees can be separated from a team
    that lost its starter in the first quarter.
    """
    dest = qb_path(raw, season)
    if dest.exists():
        return pd.read_parquet(dest)

    full = raw / "qb" / f"_pbp_full_{season}.parquet"
    download(f"{sdv.PBP_RELEASE}/play_by_play_{season}.parquet", full)
    import pyarrow.parquet as pq

    present = set(pq.ParquetFile(full).schema_arrow.names)
    pbp = pd.read_parquet(full, columns=[c for c in PASSER_COLUMNS if c in present])
    full.unlink(missing_ok=True)

    if "passer_player_name" not in pbp.columns:
        LOG.warning("season %s carries no passer column", season)
        return write_parquet(pd.DataFrame(), dest) and pd.DataFrame()

    passes = pbp.dropna(subset=["passer_player_name", "game_id", "pos_team"]).copy()
    passes["game_id"] = passes["game_id"].astype("int64")
    is_home = passes["pos_team"].astype("string") == passes["home"].astype("string")
    passes["team_id"] = np.where(is_home, passes["home_team_id"], passes["away_team_id"])
    passes = passes.dropna(subset=["team_id"])
    passes["team_id"] = passes["team_id"].astype("int64")

    by_passer = (
        passes.groupby(["game_id", "team_id", "passer_player_name"], dropna=False)
        .agg(attempts=("passer_player_name", "size"), qb_epa=("EPA", "mean"))
        .reset_index()
        .sort_values(["game_id", "team_id", "attempts"], ascending=[True, True, False])
    )
    starters = by_passer.groupby(["game_id", "team_id"], as_index=False).first()
    starters = starters.rename(columns={"passer_player_name": "qb", "attempts": "qb_attempts"})

    totals = (
        by_passer.groupby(["game_id", "team_id"], as_index=False)
        .agg(team_pass_attempts=("attempts", "sum"), passers_used=("attempts", "size"))
    )
    out = starters.merge(totals, on=["game_id", "team_id"], how="left")
    out["qb_share"] = out["qb_attempts"] / out["team_pass_attempts"]
    out["season"] = season
    write_parquet(out, dest)
    return out


def build(raw: Path, seasons: list[int]) -> pd.DataFrame:
    frames = []
    for season in seasons:
        try:
            frame = build_season(raw, season)
            if not frame.empty:
                frames.append(frame)
        except Exception as exc:  # noqa: BLE001 - a missing season is a finding
            LOG.warning("quarterback extraction failed for %s: %s", season, exc)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def load(raw: Path, seasons: list[int]) -> pd.DataFrame:
    frames = [
        pd.read_parquet(qb_path(raw, s)) for s in seasons if qb_path(raw, s).exists()
    ]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
