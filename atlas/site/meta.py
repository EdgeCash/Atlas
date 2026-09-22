"""Game metadata from ESPN's public scoreboard.

The warehouse knows how teams play. It does not know what the stadium is
called, who is televising the game or what colour the uniforms are, and a
premium card needs all three. This is the only network call the site build
makes, it is cached to disk, and the site degrades to the warehouse's own
fields when it is unavailable.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

from atlas import config
from atlas.live.provider import SCOREBOARD
from atlas.util import _guard_offline, get_logger, http_get, session

LOG = get_logger(__name__)

#: ESPN's FBS group. Without it the feed is mostly FCS noise.
FBS_GROUP = "80"

#: Metadata changes on the order of days, not minutes.
CACHE_HOURS = 6


def cache_path() -> Path:
    return config.paths().data / "site" / "espn_meta.json"


def _fresh(path: Path) -> bool:
    if not path.exists():
        return False
    age = datetime.now().timestamp() - path.stat().st_mtime
    return age < CACHE_HOURS * 3600


def fetch(days: list[date], *, refresh: bool = False) -> dict[int, dict]:
    """One record per game: venue, broadcast, colours, records, rank."""
    path = cache_path()
    if not refresh and _fresh(path):
        cached = json.loads(path.read_text())
        LOG.info("espn metadata: %d games from cache", len(cached))
        return {int(k): v for k, v in cached.items()}

    _guard_offline(SCOREBOARD)
    sess = session()
    out: dict[int, dict] = {}
    for day in days:
        payload = http_get(
            SCOREBOARD, sess=sess, timeout=30,
            params={"limit": 200, "groups": FBS_GROUP, "dates": day.strftime("%Y%m%d")},
        ).json()
        for event in payload.get("events", []) or []:
            record = _event(event)
            if record:
                out[record["game_id"]] = record

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({str(k): v for k, v in out.items()}, indent=1, sort_keys=True))
    LOG.info("espn metadata: %d games fetched", len(out))
    return out


def _event(event: dict) -> dict | None:
    competitions = event.get("competitions") or []
    if not competitions:
        return None
    comp = competitions[0]
    sides = {c.get("homeAway"): c for c in comp.get("competitors", [])}
    home, away = sides.get("home"), sides.get("away")
    if not home or not away:
        return None

    venue = comp.get("venue") or {}
    address = venue.get("address") or {}
    broadcasts = comp.get("broadcasts") or []
    names = [n for b in broadcasts for n in (b.get("names") or [])]

    return {
        "game_id": int(event["id"]),
        "kickoff": event.get("date"),
        "venue": venue.get("fullName"),
        "city": address.get("city"),
        "state": address.get("state"),
        "indoor": bool(venue.get("indoor", False)),
        "tv": names[0] if names else None,
        "neutral": bool(comp.get("neutralSite", False)),
        "conference_game": bool(comp.get("conferenceCompetition", False)),
        "home": _side(home),
        "away": _side(away),
        "moneyline": _moneyline(comp),
    }


def _moneyline(comp: dict) -> dict:
    """Moneyline open and current, where a book posts one at all.

    Books do not price a moneyline on a forty-point spread. The field stays
    empty rather than being derived from the spread, because a derived price
    is Atlas's opinion wearing the market's clothes.
    """
    for odds in comp.get("odds", []) or []:
        block = odds.get("moneyline") or {}
        out = {"book": (odds.get("provider") or {}).get("name")}
        for side in ("home", "away"):
            for when in ("open", "close"):
                value = ((block.get(side) or {}).get(when) or {}).get("odds")
                text = str(value).strip() if value is not None else ""
                out[f"{side}_{when}"] = text if text and text.upper() != "OFF" else None
        if any(out[k] for k in out if k != "book"):
            return out
    return {}


def _side(side: dict) -> dict:
    team = side.get("team") or {}
    records = {r.get("abbreviation", r.get("name")): r.get("summary")
               for r in (side.get("records") or [])}
    rank = (side.get("curatedRank") or {}).get("current")
    return {
        "id": int(team.get("id") or 0) or None,
        "name": team.get("displayName"),
        "short": team.get("shortDisplayName"),
        "location": team.get("location"),
        "abbr": team.get("abbreviation"),
        "colour": f"#{team['color']}" if team.get("color") else None,
        "alt_colour": f"#{team['alternateColor']}" if team.get("alternateColor") else None,
        "record": records.get("overall"),
        # ESPN uses 99 for "unranked", which would otherwise print as #99.
        "rank": int(rank) if rank and int(rank) < 99 else None,
    }


def days_ahead(horizon: int = 8) -> list[date]:
    today = datetime.now().date()
    return [today + timedelta(days=i) for i in range(horizon)]
