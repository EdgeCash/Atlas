"""Free historical weather from Meteostat bulk files.

Phase 1A could not measure weather: CFBD's ``/games/weather`` sits behind a
paid tier. Open-Meteo's archive API is free but metered per IP, and a shared
egress address exhausts the daily quota before a nine-season backfill gets
anywhere.

Meteostat publishes the same underlying station observations as **static bulk
files** - no API key, no quota, one gzipped CSV per station covering its whole
history. Atlas maps each stadium to its nearest station with hourly coverage
and reads the kickoff hour out of that station's file.

Source units are metric (°C, km/h, mm); Atlas converts to the units the
warehouse already uses (°F, mph, inches) so the columns stay comparable with
the CFBD weather schema they replace.
"""

from __future__ import annotations

import gzip
import io
import json
from pathlib import Path

import numpy as np
import pandas as pd

from atlas.util import download, get_logger, write_parquet

LOG = get_logger(__name__)

BULK = "https://bulk.meteostat.net/v2"
STATIONS_URL = f"{BULK}/stations/lite.json.gz"

#: Column layout of a bulk hourly file. The files carry no header row.
HOURLY_COLUMNS = [
    "date", "hour", "temp", "dwpt", "rhum", "prcp", "snow",
    "wdir", "wspd", "wpgt", "pres", "tsun", "coco",
]

#: Countries whose stations can plausibly host an FBS game.
COUNTRIES = ("US", "CA", "MX", "IE", "GB", "DE", "AU", "JP", "BS", "PR")


def stations_path(raw: Path) -> Path:
    return raw / "weather" / "stations.parquet"


def station_hourly_path(raw: Path, station_id: str) -> Path:
    return raw / "weather" / "hourly" / f"{station_id}.parquet"


def fetch_stations(raw: Path) -> pd.DataFrame:
    """Station catalogue with coordinates and hourly-coverage windows."""
    dest = stations_path(raw)
    if dest.exists():
        return pd.read_parquet(dest)
    archive = raw / "weather" / "stations_lite.json.gz"
    download(STATIONS_URL, archive)
    with gzip.open(archive, "rt", encoding="utf-8") as fh:
        payload = json.load(fh)

    rows = []
    for station in payload:
        if station.get("country") not in COUNTRIES:
            continue
        location = station.get("location") or {}
        hourly = (station.get("inventory") or {}).get("hourly") or {}
        if not hourly.get("start") or not hourly.get("end"):
            continue
        rows.append(
            {
                "station_id": station["id"],
                "name": (station.get("name") or {}).get("en"),
                "country": station.get("country"),
                "region": station.get("region"),
                "latitude": location.get("latitude"),
                "longitude": location.get("longitude"),
                "elevation": location.get("elevation"),
                "hourly_start": pd.Timestamp(hourly["start"]),
                "hourly_end": pd.Timestamp(hourly["end"]),
            }
        )
    df = pd.DataFrame(rows).dropna(subset=["latitude", "longitude"])
    write_parquet(df, dest)
    return df


def fetch_station_hourly(raw: Path, station_id: str, *, since: str = "2017-01-01") -> Path:
    """Download and trim one station's hourly history.

    The bulk file spans decades; Atlas keeps only the seasons it models, which
    turns a ~4 MB gzipped CSV into a few hundred KB of parquet.
    """
    dest = station_hourly_path(raw, station_id)
    if dest.exists():
        return dest
    archive = raw / "weather" / "_bulk" / f"{station_id}.csv.gz"
    download(f"{BULK}/hourly/{station_id}.csv.gz", archive)
    with open(archive, "rb") as fh:
        raw_bytes = fh.read()
    frame = pd.read_csv(
        io.BytesIO(gzip.decompress(raw_bytes)),
        names=HOURLY_COLUMNS,
        header=None,
        dtype={"date": "string", "hour": "Int16"},
    )
    frame = frame[frame["date"] >= since]
    observed = pd.to_datetime(frame["date"], format="%Y-%m-%d", errors="coerce")
    frame["observed_at"] = (
        observed + pd.to_timedelta(frame["hour"].fillna(0).astype(int), unit="h")
    ).dt.tz_localize("UTC")
    frame = frame.dropna(subset=["observed_at"])
    out = pd.DataFrame(
        {
            "station_id": station_id,
            "observed_at": frame["observed_at"],
            "temp_f": frame["temp"] * 9 / 5 + 32,
            "humidity_pct": frame["rhum"],
            "precip_in": frame["prcp"] / 25.4,
            "wind_mph": frame["wspd"] * 0.621371,
            "wind_gust_mph": frame["wpgt"] * 0.621371,
            "pressure_hpa": frame["pres"],
            "condition_code": frame["coco"],
        }
    )
    write_parquet(out, dest)
    archive.unlink(missing_ok=True)
    return dest


EARTH_RADIUS_MILES = 3958.7613


def _haversine(lat1, lon1, lat2, lon2) -> np.ndarray:
    lat1, lon1, lat2, lon2 = (np.radians(np.asarray(x, dtype=float)) for x in (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_MILES * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def assign_stations(
    venues: pd.DataFrame,
    stations: pd.DataFrame,
    *,
    needs_from: str,
    needs_to: str,
    max_miles: float = 60.0,
) -> pd.DataFrame:
    """Nearest station to each venue that actually covers the seasons modelled.

    A station three miles away whose records stop in 2019 is useless for a
    2024 game, so coverage is a filter and distance only breaks ties among
    stations that qualify.
    """
    start, end = pd.Timestamp(needs_from), pd.Timestamp(needs_to)
    covering = stations[
        (stations["hourly_start"] <= start) & (stations["hourly_end"] >= end)
    ]
    if covering.empty:
        LOG.warning("no station covers %s..%s; falling back to any hourly station",
                    needs_from, needs_to)
        covering = stations

    rows = []
    s_lat = covering["latitude"].to_numpy()
    s_lon = covering["longitude"].to_numpy()
    s_id = covering["station_id"].to_numpy()
    for _, venue in venues.iterrows():
        miles = _haversine(venue["latitude"], venue["longitude"], s_lat, s_lon)
        best = int(np.argmin(miles))
        rows.append(
            {
                "venue_id": int(venue["venue_id"]),
                "station_id": str(s_id[best]),
                "station_miles": float(miles[best]),
                "within_tolerance": bool(miles[best] <= max_miles),
            }
        )
    out = pd.DataFrame(rows)
    LOG.info(
        "mapped %d venues to %d stations (median %.1f miles, %d beyond %.0f miles)",
        len(out), out["station_id"].nunique(), out["station_miles"].median(),
        int((~out["within_tolerance"]).sum()), max_miles,
    )
    return out
