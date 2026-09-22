"""Situational context: rest, travel, venue and weather.

All of it is knowable before kickoff. Rest comes from the schedule, travel is
the great-circle distance from a team's own stadium to the game venue, and
weather is the CFBD kickoff observation (null without an API key).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from atlas.sources import cfbd
from atlas.staging import teams as teams_mod
from atlas.util import get_logger, write_parquet

LOG = get_logger(__name__)

EARTH_RADIUS_MILES = 3958.7613


def haversine_miles(
    lat1: np.ndarray, lon1: np.ndarray, lat2: np.ndarray, lon2: np.ndarray
) -> np.ndarray:
    lat1, lon1, lat2, lon2 = (np.radians(np.asarray(x, dtype=float)) for x in (lat1, lon1, lat2, lon2))
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_MILES * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def build_context(
    raw: Path,
    staging: Path,
    games: pd.DataFrame,
    team_games: pd.DataFrame,
    teams: pd.DataFrame,
    weather: pd.DataFrame | None = None,
) -> pd.DataFrame:
    out = games[["game_id", "season", "home_team_id", "away_team_id", "neutral_site"]].copy()

    rest = team_games[["game_id", "team_id", "days_rest"]]
    home_rest = rest.rename(columns={"team_id": "home_team_id", "days_rest": "home_days_rest"})
    away_rest = rest.rename(columns={"team_id": "away_team_id", "days_rest": "away_days_rest"})
    out = out.merge(home_rest, on=["game_id", "home_team_id"], how="left")
    out = out.merge(away_rest, on=["game_id", "away_team_id"], how="left")
    out["rest_diff"] = out["home_days_rest"] - out["away_days_rest"]

    out = _add_travel(out, games, teams)
    out = _add_weather(raw, out, weather)

    write_parquet(out, staging / "context.parquet")
    return out


def _add_travel(out: pd.DataFrame, games: pd.DataFrame, teams: pd.DataFrame) -> pd.DataFrame:
    venues = teams_mod.venues(teams).set_index("venue_id")
    sites = teams_mod.home_sites(teams)

    g = games[["game_id", "season", "venue_id", "home_team_id", "away_team_id"]].copy()
    g["venue_id"] = pd.to_numeric(g["venue_id"], errors="coerce").astype("Int64")
    g = g.merge(
        venues[["latitude", "longitude"]].rename(
            columns={"latitude": "venue_lat", "longitude": "venue_lon"}
        ),
        left_on="venue_id",
        right_index=True,
        how="left",
    )
    for side in ("home", "away"):
        side_sites = sites.rename(
            columns={
                "team_id": f"{side}_team_id",
                "home_lat": f"{side}_lat",
                "home_lon": f"{side}_lon",
            }
        )[["season", f"{side}_team_id", f"{side}_lat", f"{side}_lon"]]
        g = g.merge(side_sites, on=["season", f"{side}_team_id"], how="left")
        g[f"{side}_travel_distance"] = haversine_miles(
            g[f"{side}_lat"], g[f"{side}_lon"], g["venue_lat"], g["venue_lon"]
        )
    # The mission's single `travel_distance` is the visiting side's trip.
    g["travel_distance"] = g["away_travel_distance"]
    g["travel_distance_diff"] = g["away_travel_distance"] - g["home_travel_distance"]
    keep = ["game_id", "travel_distance", "home_travel_distance", "away_travel_distance",
            "travel_distance_diff"]
    return out.merge(g[keep], on="game_id", how="left")


def _add_weather(
    raw: Path, out: pd.DataFrame, weather: pd.DataFrame | None = None
) -> pd.DataFrame:
    """Prefer the free station observations; fall back to CFBD if present.

    Phase 1A could not measure weather at all - CFBD's endpoint needs a paid
    tier. Phase 1B replaces it with Meteostat bulk station data, which is free
    and unmetered, so the CFBD path is now only a fallback.
    """
    if weather is not None and not weather.empty and weather["weather_temp"].notna().any():
        columns = [c for c in weather.columns if c != "game_id"]
        return out.merge(weather[["game_id", *columns]], on="game_id", how="left")

    frames = []
    for path in sorted((raw / "cfbd").glob("weather_*.parquet")) if (raw / "cfbd").exists() else []:
        df = pd.read_parquet(path)
        if df.empty:
            continue
        frames.append(df)
    if not frames:
        reason = cfbd.unavailable_reason(raw, "weather")
        if reason:
            LOG.warning("weather columns will be null: %s", reason)
        elif not cfbd.available():
            LOG.warning("weather is CFBD-only and will be null (set CFBD_API_KEY)")
        else:
            LOG.warning("weather columns will be null: no CFBD weather files on disk")
        out["weather_temp"] = pd.NA
        out["weather_wind"] = pd.NA
        out["weather_precip"] = pd.NA
        return out
    weather = pd.concat(frames, ignore_index=True)
    id_col = "id" if "id" in weather.columns else "gameId"
    weather = weather.rename(
        columns={
            id_col: "game_id",
            "temperature": "weather_temp",
            "windSpeed": "weather_wind",
            "precipitation": "weather_precip",
        }
    )
    cols = [c for c in ["game_id", "weather_temp", "weather_wind", "weather_precip"]
            if c in weather.columns]
    weather = weather[cols].drop_duplicates("game_id")
    weather["game_id"] = weather["game_id"].astype("int64")
    return out.merge(weather, on="game_id", how="left")


def load(staging: Path) -> pd.DataFrame:
    return pd.read_parquet(staging / "context.parquet")
