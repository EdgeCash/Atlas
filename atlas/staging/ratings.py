"""Published ratings, oriented to the home team and checked for leakage.

Atlas carries four rating families, and they are *not* equally safe:

``fpi``
    ESPN Football Power Index on a net-points scale. Atlas joins the **previous
    season's final** FPI onto a game, because ESPN only publishes an
    end-of-season value per season and using the same season's number would
    tell the model how the season turned out.
``fpi_win_prob``
    ESPN's pre-game FPI projection for that specific matchup. Published before
    kickoff, so it is used as-is and is the point-in-time-correct FPI signal.
``elo``
    CFBD pre-game Elo carried on the schedule feed. Pre-game by construction.
``sp_plus``
    SP+ from CFBD, previous season only, for the same reason as FPI. Requires
    ``CFBD_API_KEY``; the columns are present but null without it.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from atlas.sources import cfbd, espn
from atlas.staging import teams as teams_stage
from atlas.util import get_logger, write_parquet

LOG = get_logger(__name__)


def build_ratings(raw: Path, staging: Path, games: pd.DataFrame, teams: pd.DataFrame) -> pd.DataFrame:
    out = games[["game_id", "season", "home_team_id", "away_team_id"]].copy()

    fpi = _prior_season_fpi(raw, sorted(games["season"].unique()))
    out = _attach_team_rating(out, fpi, "fpi")

    for column, name in SP_PLUS_COLUMNS.items():
        sp = _prior_season_sp_plus(raw, sorted(games["season"].unique()), teams, column)
        out = _attach_team_rating(out, sp, name)

    pred = _predictors(raw, sorted(games["season"].unique()))
    out = out.merge(pred, on="game_id", how="left")

    elo = games[["game_id", "home_pregame_elo", "away_pregame_elo"]].copy()
    out = out.merge(elo, on="game_id", how="left")
    out["elo_diff"] = out["home_pregame_elo"] - out["away_pregame_elo"]

    write_parquet(out, staging / "ratings.parquet")
    return out


def _attach_team_rating(out: pd.DataFrame, ratings: pd.DataFrame, name: str) -> pd.DataFrame:
    """Join a (season, team_id, value) frame on as home_<name>/away_<name>."""
    if ratings.empty:
        out[f"home_{name}"] = pd.NA
        out[f"away_{name}"] = pd.NA
        out[f"{name}_diff"] = pd.NA
        return out
    home = ratings.rename(columns={"team_id": "home_team_id", "value": f"home_{name}"})
    away = ratings.rename(columns={"team_id": "away_team_id", "value": f"away_{name}"})
    out = out.merge(home, on=["season", "home_team_id"], how="left")
    out = out.merge(away, on=["season", "away_team_id"], how="left")
    out[f"{name}_diff"] = out[f"home_{name}"] - out[f"away_{name}"]
    return out


def _prior_season_fpi(raw: Path, seasons: list[int]) -> pd.DataFrame:
    frames = []
    for season in seasons:
        path = espn.season_fpi_path(raw, season - 1)
        if not path.exists():
            continue
        df = pd.read_parquet(path)
        if df.empty or "fpi" not in df.columns:
            continue
        frames.append(
            pd.DataFrame(
                {
                    "season": season,
                    "team_id": df["team_id"].astype("int64"),
                    "value": pd.to_numeric(df["fpi"], errors="coerce"),
                }
            )
        )
    if not frames:
        LOG.warning("no ESPN FPI files found")
        return pd.DataFrame(columns=["season", "team_id", "value"])
    return pd.concat(frames, ignore_index=True).dropna(subset=["value"])


#: SP+ fields Atlas carries. The overall rating drives the margin benchmark;
#: the offence/defence split is what a totals model actually needs, since a
#: sum of two overall ratings says nothing about the scoring environment.
SP_PLUS_COLUMNS = {
    "rating": "sp_plus",
    "offense.rating": "sp_plus_off",
    "defense.rating": "sp_plus_def",
}


def _prior_season_sp_plus(
    raw: Path, seasons: list[int], teams: pd.DataFrame, column: str = "rating"
) -> pd.DataFrame:
    resolve = teams_stage.name_resolver(teams)
    frames = []
    for season in seasons:
        path = raw / "cfbd" / f"sp_plus_{season - 1}.parquet"
        if not path.exists():
            continue
        df = pd.read_parquet(path)
        if df.empty or column not in df.columns:
            continue
        df = df.dropna(subset=["team"])
        df["team_id"] = resolve(season - 1, df["team"])
        df = df.dropna(subset=["team_id"])
        frames.append(
            pd.DataFrame(
                {
                    "season": season,
                    "team_id": df["team_id"].astype("int64"),
                    "value": pd.to_numeric(df[column], errors="coerce"),
                }
            )
        )
    if not frames:
        if not cfbd.available():
            LOG.warning("SP+ unavailable: set CFBD_API_KEY to populate sp_plus columns")
        return pd.DataFrame(columns=["season", "team_id", "value"])
    return pd.concat(frames, ignore_index=True).dropna(subset=["value"])


def _predictors(raw: Path, seasons: list[int]) -> pd.DataFrame:
    frames = []
    for season in seasons:
        path = espn.predictor_path(raw, season)
        if path.exists():
            frames.append(pd.read_parquet(path))
    if not frames:
        return pd.DataFrame(columns=["game_id", "fpi_home_win_prob"])
    df = pd.concat(frames, ignore_index=True)
    df["game_id"] = df["game_id"].astype("int64")
    return df[["game_id", "fpi_home_win_prob"]].drop_duplicates("game_id")


def load(staging: Path) -> pd.DataFrame:
    return pd.read_parquet(staging / "ratings.parquet")
