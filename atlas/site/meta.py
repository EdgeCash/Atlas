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
from atlas.live.books import canonical
from atlas.live.provider import SCOREBOARD
from atlas.util import _guard_offline, get_logger, http_get, session

LOG = get_logger(__name__)

#: ESPN's FBS group. Without it the feed is mostly FCS noise.
FBS_GROUP = "80"

#: Metadata changes on the order of days, not minutes.
CACHE_HOURS = 6


SCOREBOARDS = {
    "ncaaf": SCOREBOARD,
    "nfl": "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard",
}


def cache_path(sport: str = "ncaaf") -> Path:
    name = "espn_meta.json" if sport == "ncaaf" else f"espn_meta_{sport}.json"
    return config.paths().data / "site" / name


def _fresh(path: Path) -> bool:
    if not path.exists():
        return False
    age = datetime.now().timestamp() - path.stat().st_mtime
    return age < CACHE_HOURS * 3600


def fetch(days: list[date], *, refresh: bool = False, sport: str = "ncaaf") -> dict[int, dict]:
    """One record per game: venue, broadcast, colours, records, rank."""
    path = cache_path(sport)
    if not refresh and _fresh(path):
        cached = json.loads(path.read_text())
        LOG.info("espn metadata (%s): %d games from cache", sport, len(cached))
        return {int(k): v for k, v in cached.items()}

    url = SCOREBOARDS[sport]
    _guard_offline(url)
    sess = session()
    out: dict[int, dict] = {}
    for day in days:
        params = {"limit": 200, "dates": day.strftime("%Y%m%d")}
        if sport == "ncaaf":
            params["groups"] = FBS_GROUP
        payload = http_get(url, sess=sess, timeout=30, params=params).json()
        for event in payload.get("events", []) or []:
            record = _event(event)
            if record:
                out[record["game_id"]] = record

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({str(k): v for k, v in out.items()}, indent=1, sort_keys=True))
    LOG.info("espn metadata (%s): %d games fetched", sport, len(out))
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
        out = {"book": canonical((odds.get("provider") or {}).get("name"))}
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
        "logo": team.get("logo"),
        "alt_colour": f"#{team['alternateColor']}" if team.get("alternateColor") else None,
        "record": records.get("overall"),
        # ESPN uses 99 for "unranked", which would otherwise print as #99.
        "rank": int(rank) if rank and int(rank) < 99 else None,
    }


def days_ahead(horizon: int = 8) -> list[date]:
    today = datetime.now().date()
    return [today + timedelta(days=i) for i in range(horizon)]


# ---------------------------------------------------------------------------
# Logos
# ---------------------------------------------------------------------------

#: Humans read a logo faster than a team name, so the board leans on them.
#: They are downloaded once and served from the site rather than hot-linked:
#: a card that waits on a third-party CDN is not a fast card.
LOGO_SIZE = 200


def cache_logos(records: dict[int, dict], out: Path, *, prefix: str = "") -> dict[int, str]:
    """Download each team's logo into ``out``. Returns team id -> filename.

    ``prefix`` keeps two sports apart: ESPN numbers NFL and college teams from
    one, so Buffalo and Auburn are both team 2.
    """
    out.mkdir(parents=True, exist_ok=True)
    wanted: dict[int, str] = {}
    for record in records.values():
        for side in ("home", "away"):
            team = record.get(side) or {}
            if team.get("id") and team.get("logo"):
                wanted[int(team["id"])] = team["logo"]

    sess = session()
    saved: dict[int, str] = {}
    for team_id, url in sorted(wanted.items()):
        name = f"{prefix}{team_id}.png"
        path = out / name
        if not path.exists():
            try:
                _guard_offline(url)
                path.write_bytes(http_get(url, sess=sess, timeout=20).content)
            except Exception as error:  # noqa: BLE001 - a logo is never fatal
                LOG.warning("logo %s unavailable: %s", team_id, error)
                continue
        saved[team_id] = name
    LOG.info("logos: %d cached in %s", len(saved), out)
    return saved
