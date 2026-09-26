"""Kickoff wind for games not yet played, from Open-Meteo's free forecast.

The college total is fitted and scored on the wind observed at kickoff
(`atlas/staging/weather.py`, Meteostat): about -0.15 points per mph, on 89%
of the history. A game not yet played has no observation, so the live
projection's wind term fell back to the training mean, which is no term at
all - the backtest saw the wind and the card did not. This fills the gap
the only way it can be filled before kickoff: with a forecast.

Open-Meteo's forecast endpoint needs no key and gives hourly 10-metre wind
up to sixteen days out, in the unit asked for. One request per venue with a
game inside the horizon, a few dozen a day. A forecast is a noisier reading
than the observation the model was fitted on, and it is read the same way:
the hour nearest kickoff, zero indoors. Games beyond the horizon, and any
game the request fails for, keep no forecast, which is exactly the fallback
they had.

Nothing here touches the model's fit. The forecast is an input to the
projection of a scheduled game, recorded beside it (``wind_mph`` in
``tracking/projections.csv``) so the number can be traced to the wind it
assumed.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd

from atlas.util import get_logger, http_get, session

LOG = get_logger(__name__)

URL = "https://api.open-meteo.com/v1/forecast"
#: Games this far ahead are asked for; the endpoint serves up to sixteen days.
HORIZON_DAYS = 8
#: The forecast hour must be this close to kickoff, as the observation had to be.
TOLERANCE = pd.Timedelta("2h")


def hourly_wind(latitude: float, longitude: float, days: int, *, sess=None, http=http_get) -> pd.DataFrame:
    """The hourly 10-metre wind forecast at one point, in mph, indexed by UTC hour."""
    params = {"latitude": round(float(latitude), 4), "longitude": round(float(longitude), 4),
              "hourly": "wind_speed_10m", "wind_speed_unit": "mph", "timezone": "UTC",
              "forecast_days": int(min(max(days, 1), 16))}
    payload = http(URL, sess=sess, params=params, timeout=30).json()
    hourly = payload.get("hourly") or {}
    times = pd.to_datetime(hourly.get("time") or [], utc=True, errors="coerce")
    speeds = pd.to_numeric(pd.Series(hourly.get("wind_speed_10m") or []), errors="coerce")
    return pd.DataFrame({"at": times, "wind_mph": speeds.to_numpy()}).dropna(subset=["at"])


def kickoff_wind(games: pd.DataFrame, venues: pd.DataFrame, now: datetime | None = None,
                 *, horizon_days: int = HORIZON_DAYS, http=http_get) -> pd.DataFrame:
    """``game_id``, ``wind_mph`` and ``forecast_at`` for each game inside the horizon.

    ``games`` needs ``game_id``, ``kickoff`` and ``venue_id`` (``venue_dome``
    when known); ``venues`` needs ``venue_id``, ``latitude``, ``longitude``
    (``dome`` when known). A dome is 0 mph without a request. A venue whose
    request fails is logged and left out; the caller's fallback stands.
    """
    columns = ["game_id", "wind_mph", "forecast_at"]
    if games is None or games.empty or venues is None or venues.empty:
        return pd.DataFrame(columns=columns)
    now = now or datetime.now(UTC)
    g = games[["game_id", "kickoff", "venue_id", *[c for c in ("venue_dome",) if c in games]]].copy()
    g["kickoff"] = pd.to_datetime(g["kickoff"], utc=True, errors="coerce")
    g["venue_id"] = pd.to_numeric(g["venue_id"], errors="coerce")
    g = g.dropna(subset=["kickoff", "venue_id"])
    g = g[(g["kickoff"] > pd.Timestamp(now)) & (g["kickoff"] <= pd.Timestamp(now) + timedelta(days=horizon_days))]
    if g.empty:
        return pd.DataFrame(columns=columns)
    v = venues.dropna(subset=["venue_id", "latitude", "longitude"]).copy()
    v["venue_id"] = pd.to_numeric(v["venue_id"], errors="coerce")
    v = v.drop_duplicates("venue_id").set_index("venue_id")
    g = g[g["venue_id"].isin(v.index)]
    if g.empty:
        return pd.DataFrame(columns=columns)
    dome = g["venue_dome"].fillna(False).astype(bool) if "venue_dome" in g else pd.Series(False, index=g.index)
    if "dome" in v:
        dome = dome | g["venue_id"].map(v["dome"]).fillna(False).astype(bool)
    stamp = now.replace(microsecond=0).isoformat()
    rows = [{"game_id": gid, "wind_mph": 0.0, "forecast_at": stamp} for gid in g.loc[dome, "game_id"]]
    outdoors = g[~dome]
    sess = session()
    days = int(np.ceil((outdoors["kickoff"].max() - pd.Timestamp(now)) / pd.Timedelta(days=1))) + 1 \
        if not outdoors.empty else 0
    for venue_id, part in outdoors.groupby("venue_id"):
        try:
            hours = hourly_wind(v.loc[venue_id, "latitude"], v.loc[venue_id, "longitude"], days, sess=sess, http=http)
        except Exception as error:  # noqa: BLE001 - one venue's failure keeps the rest
            LOG.warning("forecast: venue %s not fetched (%s)", venue_id, type(error).__name__)
            continue
        if hours.empty:
            continue
        hours = hours.sort_values("at")
        for row in part.itertuples():
            nearest = hours.iloc[(hours["at"] - row.kickoff).abs().argsort().iloc[0]]
            if abs(nearest["at"] - row.kickoff) > TOLERANCE or pd.isna(nearest["wind_mph"]):
                continue
            rows.append({"game_id": row.game_id, "wind_mph": float(nearest["wind_mph"]), "forecast_at": stamp})
    out = pd.DataFrame(rows, columns=columns)
    LOG.info("forecast: kickoff wind for %d of %d games inside %d days", len(out), len(g), horizon_days)
    return out


def attach(scheduled: pd.DataFrame, venues: pd.DataFrame, now: datetime | None = None, *,
           http=http_get) -> pd.DataFrame:
    """``scheduled`` with ``weather_wind_effective`` set from the forecast where one was found, and
    ``wind_mph`` carrying the value used (NaN where the fallback stands). Never raises."""
    out = scheduled.copy()
    out["wind_mph"] = np.nan
    try:
        wind = kickoff_wind(out, venues, now, http=http)
    except Exception as error:  # noqa: BLE001 - the projection stands without it
        LOG.warning("forecast: not attached (%s)", type(error).__name__)
        return out
    if wind.empty:
        return out
    found = wind.set_index("game_id")["wind_mph"]
    got = out["game_id"].map(found)
    out["wind_mph"] = got.to_numpy()
    if "weather_wind_effective" not in out:
        out["weather_wind_effective"] = np.nan
    out["weather_wind_effective"] = np.where(got.notna(), got, pd.to_numeric(out["weather_wind_effective"],
                                                                             errors="coerce"))
    return out
