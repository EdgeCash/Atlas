"""Live odds capture.

Atlas needs a source that publishes, for an upcoming game, both the number a
book opened on and the number it is quoting right now. ESPN's public
scoreboard does exactly that, and the book it quotes - DraftKings - is one of
the four that Phase 4 found ever posts an opening number at all
(`reports/opening_line_feasibility.md`). That is not a coincidence worth
relying on forever, so the provider is an interface with one implementation
rather than a hard-coded fetch.

Orientation matches the rest of Atlas: ``margin`` is home-oriented, so a home
favourite by 7 is ``+7``, and a total is a total.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Protocol

import pandas as pd

from atlas.util import _guard_offline, get_logger, http_get, session

LOG = get_logger(__name__)

SCOREBOARD = (
    "https://site.api.espn.com/apis/site/v2/sports/football/college-football/scoreboard"
)
SCOREBOARDS = {
    "ncaaf": SCOREBOARD,
    "nfl": "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard",
}

#: ESPN groups: 80 is all FBS. Without it the feed is mostly FCS noise.
FBS_GROUP = "80"


class OddsProvider(Protocol):
    """Anything that can report the current and opening line for a game."""

    name: str

    def fetch(self, days: list[date]) -> pd.DataFrame:  # pragma: no cover - protocol
        ...


def _to_float(value: object) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace("+", "")
    if text in ("", "EVEN", "even", "OFF", "off", "None", "nan"):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _line_block(block: dict | None, key: str) -> tuple[float | None, float | None]:
    """Pull (line, price) out of one of ESPN's open/close sub-blocks."""
    if not isinstance(block, dict):
        return None, None
    inner = block.get(key)
    if not isinstance(inner, dict):
        return None, None
    raw_line = inner.get("line")
    if isinstance(raw_line, str):
        raw_line = raw_line.lstrip("ou")
    return _to_float(raw_line), _to_float(inner.get("odds"))


@dataclass(frozen=True)
class EspnScoreboard:
    """ESPN's public scoreboard. No key, no quota, one book.

    The same feed serves college (``sport="ncaaf"``, FBS only) and the NFL;
    event ids are ESPN's and unique across the two.
    """

    name: str = "espn"
    group: str = FBS_GROUP

    sport: str = "ncaaf"

    def __post_init__(self) -> None:
        if self.sport not in SCOREBOARDS:
            raise KeyError(f"unknown sport {self.sport!r}; have {sorted(SCOREBOARDS)}")
        # A frozen dataclass: the derived fields go in through the back door.
        object.__setattr__(self, "name", "espn" if self.sport == "ncaaf" else f"espn-{self.sport}")

    @property
    def url(self) -> str:
        return SCOREBOARDS[self.sport]

    def fetch(self, days: list[date]) -> pd.DataFrame:
        _guard_offline(self.url)
        sess = session()
        rows: list[dict] = []
        for day in days:
            params = {"limit": 200, "dates": day.strftime("%Y%m%d")}
            if self.sport == "ncaaf":
                params["groups"] = self.group
            payload = http_get(self.url, sess=sess, params=params, timeout=30).json()
            captured = datetime.now(UTC).replace(microsecond=0).isoformat()
            rows.extend(self._events(payload, captured))
        frame = pd.DataFrame(rows)
        LOG.info("%s: %d quotes over %d days", self.name, len(frame), len(days))
        return frame

    def _events(self, payload: dict, captured: str) -> list[dict]:
        out = []
        for event in payload.get("events", []) or []:
            competitions = event.get("competitions") or []
            if not competitions:
                continue
            comp = competitions[0]
            teams = {c.get("homeAway"): c for c in comp.get("competitors", [])}
            home, away = teams.get("home"), teams.get("away")
            if not home or not away:
                continue

            status = (comp.get("status", {}).get("type", {}) or {}).get("name", "")
            base = {
                "captured_at": captured,
                "game_id": int(event["id"]),
                "kickoff": event.get("date"),
                "season": int((event.get("season") or {}).get("year") or 0) or None,
                "week": int((event.get("week") or {}).get("number") or 0) or None,
                "home_team": (home.get("team") or {}).get("displayName"),
                "away_team": (away.get("team") or {}).get("displayName"),
                "home_team_id": int((home.get("team") or {}).get("id") or 0) or None,
                "away_team_id": int((away.get("team") or {}).get("id") or 0) or None,
                "home_score": _to_float(home.get("score")),
                "away_score": _to_float(away.get("score")),
                "status": status,
                "completed": bool((comp.get("status", {}).get("type", {}) or {})
                                  .get("completed", False)),
            }

            for odds in comp.get("odds", []) or []:
                book = ((odds.get("provider") or {}).get("name") or "unknown")
                spread = odds.get("pointSpread") or {}
                total = odds.get("total") or {}

                # ESPN quotes the spread from each side; the home block is the
                # home handicap, so the home-oriented margin is its negation.
                home_now, home_price = _line_block(spread.get("home"), "close")
                home_open, home_open_price = _line_block(spread.get("home"), "open")
                if home_now is not None or home_open is not None:
                    out.append({
                        **base, "book": book, "market": "margin",
                        "line": -home_now if home_now is not None else None,
                        "price": home_price,
                        "open_line": -home_open if home_open is not None else None,
                        "open_price": home_open_price,
                    })

                over_now, over_price = _line_block(total.get("over"), "close")
                over_open, over_open_price = _line_block(total.get("over"), "open")
                if over_now is not None or over_open is not None:
                    out.append({
                        **base, "book": book, "market": "total",
                        "line": over_now, "price": over_price,
                        "open_line": over_open, "open_price": over_open_price,
                    })
        return out


PROVIDERS: dict[str, OddsProvider] = {"espn": EspnScoreboard(sport="ncaaf"), "espn-nfl": EspnScoreboard(sport="nfl")}

#: What one poll captures: every sport Atlas publishes a card for.
POLLED: tuple[str, ...] = ("espn", "espn-nfl")


def get_provider(name: str = "espn") -> OddsProvider:
    if name not in PROVIDERS:
        raise KeyError(f"unknown odds provider {name!r}; have {sorted(PROVIDERS)}")
    return PROVIDERS[name]
