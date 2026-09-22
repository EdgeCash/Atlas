"""Kickoff weather from free Meteostat station observations.

For each game Atlas takes the hourly observation from the station nearest the
venue, matched to the kickoff hour (nearest observation within two hours).

Domes are carried explicitly rather than silently: the observed values stay,
and an ``_effective`` pair is derived that models what the players actually
experience - no wind and room temperature indoors. Research can then test
whether outdoor readings matter, indoor-corrected readings matter, or neither.
"""

from __future__ import annotations

import concurrent.futures as cf
from pathlib import Path

import numpy as np
import pandas as pd

from atlas import config
from atlas.sources import meteostat
from atlas.staging import teams as teams_mod
from atlas.util import get_logger, write_parquet

LOG = get_logger(__name__)

#: Nearest observation within this many hours of kickoff is accepted.
MATCH_TOLERANCE = pd.Timedelta("2h")

#: A closed roof is roughly this, whatever the sky is doing outside.
DOME_TEMP_F = 72.0
DOME_HUMIDITY_PCT = 50.0

WEATHER_COLUMNS = [
    "game_id",
    "weather_temp",
    "weather_wind",
    "weather_precip",
    "weather_humidity",
    "weather_temp_effective",
    "weather_wind_effective",
    "weather_precip_effective",
    "venue_dome",
    "weather_station_id",
    "weather_station_miles",
]


def build_weather(
    raw: Path,
    staging: Path,
    games: pd.DataFrame,
    teams: pd.DataFrame,
    *,
    workers: int = 8,
    fbs_only: bool = True,
) -> pd.DataFrame:
    scope = _in_scope(games, fbs_only)
    venues = teams_mod.venues(teams)
    venues = venues[venues["venue_id"].isin(scope["venue_id"].dropna().unique())]
    if venues.empty:
        LOG.warning("no venue coordinates available - weather will be empty")
        return _empty(games, staging)

    try:
        stations = meteostat.fetch_stations(raw)
    except Exception as exc:  # noqa: BLE001 - weather is enrichment, never a blocker
        LOG.warning("station catalogue unavailable (%s) - weather will be empty", exc)
        return _empty(games, staging)
    seasons = sorted(games["season"].unique())
    mapping = meteostat.assign_stations(
        venues,
        stations,
        needs_from=f"{min(seasons)}-08-01",
        needs_to=f"{max(seasons) - 1}-12-31",
    )

    needed = sorted(mapping["station_id"].unique())
    LOG.info("fetching %d station histories", len(needed))
    _fetch_all(raw, needed, workers=workers)

    observations = _load_observations(raw, needed)
    if observations.empty:
        LOG.warning("no station observations downloaded - weather will be empty")
        return _empty(games, staging)

    matched = _match_kickoffs(scope, venues, mapping, observations)
    out = games[["game_id"]].merge(matched, on="game_id", how="left")
    out = _apply_dome(out, venues)
    out = out[[c for c in WEATHER_COLUMNS if c in out.columns]]
    write_parquet(out, staging / "weather.parquet")
    return out


def _in_scope(games: pd.DataFrame, fbs_only: bool) -> pd.DataFrame:
    scope = games[["game_id", "season", "kickoff", "venue_id"]].copy()
    if fbs_only:
        mask = games["home_division"].isin(config.FBS_DIVISIONS) | games["away_division"].isin(
            config.FBS_DIVISIONS
        )
        scope = scope[mask.to_numpy()]
    scope["venue_id"] = pd.to_numeric(scope["venue_id"], errors="coerce").astype("Int64")
    return scope.dropna(subset=["venue_id", "kickoff"])


def _fetch_all(raw: Path, station_ids: list[str], *, workers: int) -> None:
    def one(station_id: str) -> None:
        try:
            meteostat.fetch_station_hourly(raw, station_id)
        except Exception as exc:  # noqa: BLE001 - a missing station is not fatal
            LOG.warning("station %s unavailable: %s", station_id, exc)

    with cf.ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(one, station_ids))


def _load_observations(raw: Path, station_ids: list[str]) -> pd.DataFrame:
    frames = []
    for station_id in station_ids:
        path = meteostat.station_hourly_path(raw, station_id)
        if path.exists():
            frames.append(pd.read_parquet(path))
    if not frames:
        return pd.DataFrame()
    obs = pd.concat(frames, ignore_index=True)
    return obs.sort_values("observed_at").reset_index(drop=True)


def _match_kickoffs(
    scope: pd.DataFrame,
    venues: pd.DataFrame,
    mapping: pd.DataFrame,
    observations: pd.DataFrame,
) -> pd.DataFrame:
    need = scope.merge(mapping, on="venue_id", how="inner")
    need["kickoff"] = pd.to_datetime(need["kickoff"], utc=True)
    need = need.sort_values("kickoff").reset_index(drop=True)

    matched = pd.merge_asof(
        need,
        observations,
        left_on="kickoff",
        right_on="observed_at",
        by="station_id",
        tolerance=MATCH_TOLERANCE,
        direction="nearest",
    )
    hit_rate = matched["temp_f"].notna().mean()
    LOG.info("kickoff weather matched for %.1f%% of in-scope games", 100 * hit_rate)

    return pd.DataFrame(
        {
            "game_id": matched["game_id"],
            "weather_temp": matched["temp_f"],
            "weather_wind": matched["wind_mph"],
            "weather_precip": matched["precip_in"].fillna(0.0).where(matched["temp_f"].notna()),
            "weather_humidity": matched["humidity_pct"],
            "weather_station_id": matched["station_id"],
            "weather_station_miles": matched["station_miles"],
            "venue_id": matched["venue_id"],
        }
    )


def _apply_dome(out: pd.DataFrame, venues: pd.DataFrame) -> pd.DataFrame:
    dome = venues[["venue_id", "dome"]].drop_duplicates("venue_id") if "dome" in venues else None
    if dome is None:
        out["venue_dome"] = False
    else:
        out = out.merge(dome, on="venue_id", how="left")
        out["venue_dome"] = out["dome"].fillna(False).astype(bool)
        out = out.drop(columns=["dome"])
    indoors = out["venue_dome"].to_numpy()
    out["weather_temp_effective"] = np.where(indoors, DOME_TEMP_F, out["weather_temp"])
    out["weather_wind_effective"] = np.where(indoors, 0.0, out["weather_wind"])
    out["weather_precip_effective"] = np.where(indoors, 0.0, out["weather_precip"])
    return out.drop(columns=["venue_id"], errors="ignore")


def _empty(games: pd.DataFrame, staging: Path) -> pd.DataFrame:
    out = games[["game_id"]].copy()
    for column in WEATHER_COLUMNS[1:]:
        out[column] = pd.NA
    write_parquet(out, staging / "weather.parquet")
    return out


def load(staging: Path) -> pd.DataFrame:
    return pd.read_parquet(staging / "weather.parquet")
