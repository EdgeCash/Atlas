"""CollegeFootballData collector (optional, API-key gated).

CFBD is the mission's priority source, but every CFBD endpoint requires a free
API key. Atlas therefore treats CFBD as an *enrichment* layer: the warehouse
builds end-to-end without it from the open mirrors, and setting
``CFBD_API_KEY`` fills in the fields that exist nowhere else:

* SP+ ratings (``/ratings/sp``)
* FPI ratings (``/ratings/fpi``) - a second opinion next to the ESPN feed
* recruiting rankings (``/recruiting/teams``) and roster talent (``/talent``)
* returning production (``/player/returning``)
* kickoff weather (``/games/weather``) - **paid CFBD tier only**

All of these are season-level. Atlas joins season ``S-1`` values onto season
``S`` games so the rating is known before kickoff; weather is the exception,
it is a kickoff observation and is used as-is.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from atlas.util import get_logger, http_get, session, write_parquet

LOG = get_logger(__name__)

BASE = "https://api.collegefootballdata.com"


def api_key() -> str | None:
    key = os.environ.get("CFBD_API_KEY", "").strip()
    return key or None


def available() -> bool:
    return api_key() is not None


class CfbdTierError(RuntimeError):
    """The key is valid but the endpoint needs a paid CFBD subscription."""


def _get(endpoint: str, params: dict[str, Any], *, retries: int = 4) -> list[dict]:
    key = api_key()
    if not key:
        raise RuntimeError("CFBD_API_KEY is not set")
    try:
        resp = http_get(
            f"{BASE}{endpoint}",
            sess=session(),
            params=params,
            headers={"Authorization": f"Bearer {key}"},
            retries=retries,
        )
    except requests.HTTPError as exc:
        _raise_for_tier(exc.response, endpoint)
        raise
    payload = resp.json()
    return payload if isinstance(payload, list) else []


def _raise_for_tier(response: Any, endpoint: str) -> None:
    """Turn CFBD's paid-tier 401 into a distinct, non-retryable error.

    A 401 here does not mean the key is bad - every other endpoint works with
    the same key. Retrying it four times per season only makes the ingest slow
    and the log misleading.
    """
    if response is None or getattr(response, "status_code", None) != 401:
        return
    try:
        message = response.json().get("message", "")
    except Exception:  # noqa: BLE001 - a non-JSON 401 is still just a 401
        message = ""
    if "Patreon" in message or "Tier" in message:
        raise CfbdTierError(f"{endpoint}: {message}")


def _cached(raw: Path, name: str, season: int, endpoint: str, params: dict[str, Any]) -> Path:
    dest = raw / "cfbd" / f"{name}_{season}.parquet"
    if dest.exists():
        return dest
    rows = _get(endpoint, params)
    return write_parquet(pd.json_normalize(rows), dest)


def fetch_sp_plus(raw: Path, season: int) -> Path:
    return _cached(raw, "sp_plus", season, "/ratings/sp", {"year": season})


def fetch_fpi(raw: Path, season: int) -> Path:
    return _cached(raw, "fpi", season, "/ratings/fpi", {"year": season})


def fetch_talent(raw: Path, season: int) -> Path:
    return _cached(raw, "talent", season, "/talent", {"year": season})


def fetch_recruiting(raw: Path, season: int) -> Path:
    return _cached(raw, "recruiting", season, "/recruiting/teams", {"year": season})


def fetch_returning_production(raw: Path, season: int) -> Path:
    return _cached(raw, "returning", season, "/player/returning", {"year": season})


def fetch_weather(raw: Path, season: int) -> Path:
    """Kickoff weather. Free CFBD keys cannot reach this endpoint."""
    dest = raw / "cfbd" / f"weather_{season}.parquet"
    if dest.exists():
        return dest
    rows: list[dict] = []
    for season_type in ("regular", "postseason"):
        try:
            rows.extend(
                _get("/games/weather", {"year": season, "seasonType": season_type}, retries=0)
            )
        except CfbdTierError as exc:
            record_status(raw, "weather", str(exc))
            raise
        except Exception as exc:  # noqa: BLE001 - one bad season must not kill the run
            LOG.warning("CFBD weather unavailable for %s/%s: %s", season, season_type, exc)
    return write_parquet(pd.json_normalize(rows), dest)


def record_status(raw: Path, dataset: str, reason: str) -> None:
    """Persist *why* a dataset is missing, so the report can say so exactly."""
    path = raw / "cfbd" / "STATUS.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    status: dict[str, str] = {}
    if path.exists():
        try:
            status = json.loads(path.read_text())
        except json.JSONDecodeError:
            status = {}
    status[dataset] = reason
    path.write_text(json.dumps(status, indent=2, sort_keys=True) + "\n")


def unavailable_reason(raw: Path, dataset: str) -> str | None:
    path = raw / "cfbd" / "STATUS.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text()).get(dataset)
    except json.JSONDecodeError:
        return None


FETCHERS = {
    "sp_plus": fetch_sp_plus,
    "fpi": fetch_fpi,
    "talent": fetch_talent,
    "recruiting": fetch_recruiting,
    "returning": fetch_returning_production,
    "weather": fetch_weather,
}


def fetch_all(raw: Path, seasons: list[int]) -> dict[str, list[Path]]:
    """Fetch every CFBD dataset Atlas can use. No-op when no key is present."""
    if not available():
        LOG.warning("CFBD_API_KEY not set - skipping CFBD enrichment entirely")
        return {}
    out: dict[str, list[Path]] = {}
    for name, fn in FETCHERS.items():
        paths = []
        for season in seasons:
            try:
                paths.append(fn(raw, season))
            except CfbdTierError as exc:
                LOG.warning("CFBD %s needs a paid tier, skipping entirely: %s", name, exc)
                break
            except Exception as exc:  # noqa: BLE001 - one bad season must not kill the run
                LOG.warning("CFBD %s %s failed: %s", name, season, exc)
        out[name] = paths
    return out
