"""Roster talent: recruiting rankings and returning production.

Both are pre-season facts - recruiting classes sign in February and returning
production is fixed once the roster is set - so the **same** season's value is
point-in-time safe, unlike SP+/FPI.

Both come only from CFBD. Without ``CFBD_API_KEY`` the columns exist but are
null, and the research report says so rather than quietly dropping the
variables.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from atlas.sources import cfbd
from atlas.util import get_logger, write_parquet

LOG = get_logger(__name__)


def build_talent(raw: Path, staging: Path, games: pd.DataFrame, teams: pd.DataFrame) -> pd.DataFrame:
    seasons = sorted(games["season"].unique())
    out = games[["game_id", "season", "home_team_id", "away_team_id"]].copy()

    recruiting = _season_table(raw, teams, seasons, "recruiting", value_col="rank")
    out = _attach(out, recruiting, "recruiting_rank")

    talent = _season_table(raw, teams, seasons, "talent", value_col="talent")
    out = _attach(out, talent, "talent")

    returning = _season_table(raw, teams, seasons, "returning", value_col="percentPPA")
    out = _attach(out, returning, "returning_production")

    if not cfbd.available():
        LOG.warning("talent/recruiting/returning-production are CFBD-only and will be null")

    write_parquet(out, staging / "talent.parquet")
    return out


def _season_table(
    raw: Path, teams: pd.DataFrame, seasons: list[int], name: str, *, value_col: str
) -> pd.DataFrame:
    name_to_id = (
        teams.dropna(subset=["school"])
        .drop_duplicates(["season", "school"])
        .set_index(["season", "school"])["team_id"]
    )
    frames = []
    for season in seasons:
        path = raw / "cfbd" / f"{name}_{season}.parquet"
        if not path.exists():
            continue
        df = pd.read_parquet(path)
        if df.empty or value_col not in df.columns or "team" not in df.columns:
            continue
        df = df.dropna(subset=["team"])
        idx = pd.MultiIndex.from_arrays([[season] * len(df), df["team"]])
        df["team_id"] = name_to_id.reindex(idx).to_numpy()
        df = df.dropna(subset=["team_id"])
        frames.append(
            pd.DataFrame(
                {
                    "season": season,
                    "team_id": df["team_id"].astype("int64"),
                    "value": pd.to_numeric(df[value_col], errors="coerce"),
                }
            )
        )
    if not frames:
        return pd.DataFrame(columns=["season", "team_id", "value"])
    return pd.concat(frames, ignore_index=True).dropna(subset=["value"])


def _attach(out: pd.DataFrame, table: pd.DataFrame, name: str) -> pd.DataFrame:
    if table.empty:
        out[f"home_{name}"] = pd.NA
        out[f"away_{name}"] = pd.NA
        out[f"{name}_diff"] = pd.NA
        return out
    home = table.rename(columns={"team_id": "home_team_id", "value": f"home_{name}"})
    away = table.rename(columns={"team_id": "away_team_id", "value": f"away_{name}"})
    out = out.merge(home, on=["season", "home_team_id"], how="left")
    out = out.merge(away, on=["season", "away_team_id"], how="left")
    # For a rank, "home minus away" is inverted so that positive always means
    # the home side is the stronger one.
    if name.endswith("rank"):
        out[f"{name}_diff"] = out[f"away_{name}"] - out[f"home_{name}"]
    else:
        out[f"{name}_diff"] = out[f"home_{name}"] - out[f"away_{name}"]
    return out


def load(staging: Path) -> pd.DataFrame:
    return pd.read_parquet(staging / "talent.parquet")
