"""BettingPros partner API: every book's line on every game, for the owner's board.

    python -m atlas.sources.bettingpros          # this weekend's multi-book totals and spreads, to the terminal

The public site anchors to one book, DraftKings, through ESPN's scoreboard.
This reads the whole market: the consensus line, a dozen or more books'
current main lines and prices with the time each was updated, and each
selection's opening line. It exists for the owner's board alone
(`atlas/owner/board.py`): nothing it returns is written in the clear into
git or onto a public page. The board's snapshots are sealed with the owner
key (`atlas/owner/market.py`), and the response's ``_parameters`` block,
which echoes the request and its credentials, is dropped before anything is
kept.

Credentials come from the environment: ``BP_API_KEY`` (the partner key, sent
as the ``x-api-key`` header on every call) and, for premium-tier fields,
``BP_USER_ID`` and ``BP_USER_KEY`` (sent together as ``auth=user``). The
board needs only the partner key. Without it every function here returns
empty and the board is not built. Budget: 5 requests a second, 5,000 a day;
a poll costs about fifteen.

Market ids and the book catalogue were read from the API on 26 September
2026 and are fixed here rather than fetched on every run.
"""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from datetime import UTC, datetime

import pandas as pd

from atlas.util import get_logger, http_get, session

LOG = get_logger(__name__)

BASE = "https://api.bettingpros.com/v3"
KEY = "BP_API_KEY"
USER_ID = "BP_USER_ID"
USER_KEY = "BP_USER_KEY"

#: The game-odds markets, by sport, as the API numbers them.
MARKETS = {
    "ncaaf": {"spread": 200, "total": 199, "moneyline": 198},
    "nfl": {"spread": 3, "total": 2, "moneyline": 1},
}
SPORT_NAMES = {"ncaaf": "NCAAF", "nfl": "NFL"}
#: The consensus pseudo-book: the reference line, never a book to take.
CONSENSUS = 0
#: Prediction markets quote in their own way (a -99900 "cost" is a filled market); they are
#: recorded, never counted as a book to take or in the consensus.
PREDICTION_MARKETS = frozenset({38, 60, 68, 73, 75})
BOOKS = {
    0: "Consensus", 10: "FanDuel", 12: "DraftKings", 13: "Caesars", 14: "Fanatics", 18: "BetRivers",
    19: "BetMGM", 24: "bet365", 32: "Borgata", 33: "theScore Bet", 35: "Betsafe", 37: "PrizePicks",
    38: "ProphetX", 39: "Book 39", 43: "BetFred", 45: "Betr", 49: "Hard Rock", 50: "BetMGM Casino",
    53: "Dabble", 60: "Novig", 62: "BetMGM Poker", 64: "Kutt", 67: "Bally Bet", 68: "Kalshi",
    73: "Polymarket", 75: "Polymarket US", 77: "Bet105", 80: "ClubWPT Gold",
}
#: Events per offers request. The API takes a colon-delimited list; a dozen keeps one page.
BATCH = 12
LOCATION = "ALL"
EVENT_COLUMNS = ["event_id", "sport", "scheduled", "season", "week", "status", "home_abbr", "visitor_abbr",
                 "home_school", "visitor_school", "home_mascot", "visitor_mascot", "home_conference",
                 "visitor_conference", "stadium_type", "forecast_wind", "forecast_temp"]
LINE_COLUMNS = ["captured_at", "sport", "event_id", "market", "selection", "participant", "book_id", "line", "cost",
                "updated", "is_off", "open_line", "open_cost", "open_book", "open_created"]


def configured() -> bool:
    return bool(os.environ.get(KEY, "").strip())


def book_name(book_id) -> str:
    try:
        return BOOKS.get(int(book_id), f"Book {int(book_id)}")
    except (TypeError, ValueError):
        return "?"


@dataclass
class Client:
    """One session, the partner key on every call, the echo of the request dropped from every answer."""

    key: str
    user_id: str | None = None
    user_key: str | None = None

    def __post_init__(self) -> None:
        self.sess = session()
        self.sess.headers["x-api-key"] = self.key
        self.calls = 0

    @classmethod
    def from_env(cls) -> Client | None:
        key = os.environ.get(KEY, "").strip()
        if not key:
            return None
        return cls(key, os.environ.get(USER_ID, "").strip() or None, os.environ.get(USER_KEY, "").strip() or None)

    def get(self, path: str, *, premium: bool = False, **params) -> dict:
        if premium and self.user_id and self.user_key:
            params.update(auth="user", user=self.user_id, key=self.user_key)
        response = http_get(f"{BASE}{path}", sess=self.sess, params=params, timeout=30, retries=2)
        self.calls += 1
        body = response.json()
        # The API echoes the request, credentials included. It is never kept, logged or returned.
        body.pop("_parameters", None)
        return body

    def paged(self, path: str, key: str, **params) -> list[dict]:
        """Every page of a list endpoint."""
        out: list[dict] = []
        page = 1
        while True:
            body = self.get(path, page=page, limit=100, **params)
            out.extend(body.get(key) or [])
            pages = int((body.get("_pagination") or {}).get("total_pages") or 1)
            if page >= pages:
                return out
            page += 1


def _text(value) -> str | None:
    return str(value) if value not in (None, "") else None


def events(client: Client, sport: str, season: int, week: int) -> pd.DataFrame:
    """The week's games as the API lists them, with each side's school and mascot for matching."""
    rows = []
    for e in client.paged("/events", "events", sport=SPORT_NAMES[sport], season=season, week=week):
        sides = {}
        for p in e.get("participants") or []:
            team = p.get("team") or {}
            sides[str(p.get("id"))] = {"school": _text(team.get("city")) or _text(team.get("name")),
                                       "mascot": _text(p.get("name")), "conference": _text(team.get("conference"))}
        home, visitor = str(e.get("home")), str(e.get("visitor"))
        h, v = sides.get(home, {}), sides.get(visitor, {})
        weather = e.get("weather") or {}
        rows.append({
            "event_id": int(e["id"]), "sport": sport,
            "scheduled": pd.Timestamp(e.get("scheduled")).tz_localize("UTC") if e.get("scheduled") else pd.NaT,
            "season": e.get("season"), "week": e.get("week"), "status": e.get("status"),
            "home_abbr": home, "visitor_abbr": visitor,
            "home_school": h.get("school"), "visitor_school": v.get("school"),
            "home_mascot": h.get("mascot"), "visitor_mascot": v.get("mascot"),
            "home_conference": h.get("conference"), "visitor_conference": v.get("conference"),
            "stadium_type": (e.get("venue") or {}).get("stadium_type"),
            "forecast_wind": pd.to_numeric(weather.get("forecast_wind_speed"), errors="coerce"),
            "forecast_temp": pd.to_numeric(weather.get("forecast_temp"), errors="coerce"),
        })
    return pd.DataFrame(rows, columns=EVENT_COLUMNS)


def _current(lines: list[dict]) -> dict | None:
    """The book's main line as it stands: active, not replaced; the newest such line."""
    live = [ln for ln in lines if ln.get("active", True) and not ln.get("replaced")]
    main = [ln for ln in live if ln.get("main")] or live
    if not main:
        return None
    return max(main, key=lambda ln: str(ln.get("updated") or ""))


def parse_offers(body: dict, sport: str, market: str, captured_at: str) -> pd.DataFrame:
    """One row per selection and book: the current main line and price, when it was updated, and the
    selection's opening line. Links and the request echo are not read."""
    rows = []
    for offer in body.get("offers") or []:
        event_id = offer.get("event_id")
        for sel in offer.get("selections") or []:
            name = str(sel.get("selection") or "").lower()
            participant = _text(sel.get("participant"))
            selection = name if market == "total" else (participant or name)
            opening = sel.get("opening_line") or {}
            for book in sel.get("books") or []:
                current = _current(book.get("lines") or [])
                if current is None:
                    continue
                rows.append({
                    "captured_at": captured_at, "sport": sport, "event_id": int(event_id) if event_id else None,
                    "market": market, "selection": selection, "participant": participant,
                    "book_id": int(book.get("id")),
                    # A moneyline has no line: 0, so the row survives and compares equal to itself.
                    "line": 0.0 if market == "moneyline" else pd.to_numeric(current.get("line"), errors="coerce"),
                    "cost": pd.to_numeric(current.get("cost"), errors="coerce"), "updated": _text(current.get("updated")),
                    "is_off": bool(current.get("is_off")),
                    "open_line": pd.to_numeric(opening.get("line"), errors="coerce"),
                    "open_cost": pd.to_numeric(opening.get("cost"), errors="coerce"),
                    "open_book": pd.to_numeric(opening.get("book_id"), errors="coerce"),
                    "open_created": _text(opening.get("created")),
                })
    out = pd.DataFrame(rows, columns=LINE_COLUMNS)
    return out.dropna(subset=["event_id", "line"])


def offers(client: Client, sport: str, event_ids: list[int], markets: tuple[str, ...] = ("total", "spread"),
           captured_at: str | None = None) -> pd.DataFrame:
    """Every book's current line on each market for the events given, a batch at a time."""
    captured_at = captured_at or datetime.now(UTC).replace(microsecond=0).isoformat()
    parts = []
    ids = [int(i) for i in event_ids]
    for market in markets:
        market_id = MARKETS[sport][market]
        for start in range(0, len(ids), BATCH):
            batch = ids[start:start + BATCH]
            try:
                # The offers endpoint caps ``limit`` at 50; a batch of a dozen events is one page.
                body = client.get("/offers", sport=SPORT_NAMES[sport], market_id=market_id,
                                  event_id=":".join(str(i) for i in batch), location=LOCATION, limit=50)
            except Exception as error:  # noqa: BLE001 - one batch's failure keeps the rest of the board
                LOG.warning("bettingpros: %s %s offers batch not fetched (%s)", sport, market, type(error).__name__)
                continue
            parts.append(parse_offers(body, sport, market, captured_at))
    if not parts:
        return pd.DataFrame(columns=LINE_COLUMNS)
    out = pd.concat(parts, ignore_index=True)
    LOG.info("bettingpros: %d lines on %d %s events, %d markets, %d calls so far", len(out), len(ids), sport,
             len(markets), client.calls)
    return out


def takeable(lines: pd.DataFrame) -> pd.Series:
    """Rows that are a book's real, current price: not the consensus, not a prediction market, not off."""
    if lines.empty:
        return pd.Series(dtype=bool)
    return (~lines["book_id"].isin([CONSENSUS, *PREDICTION_MARKETS])) & (~lines["is_off"].astype(bool)) \
        & lines["cost"].notna() & (lines["cost"].abs() < 5000)


# ---------------------------------------------------------------------------
# Player props: which books quote them (a probe, counts only)
# ---------------------------------------------------------------------------

#: The player-prop markets the probe asks for, by the slug BettingPros gives them.
PROP_PROBE_SLUGS = ("passing-yards", "rushing-yards", "receiving-yards", "receptions")
#: The pick'em apps in the book catalogue: a line against fixed payouts, not a price.
PICKEM = {37: "PrizePicks", 53: "Dabble", 45: "Betr"}


def markets(client: Client, sport: str) -> list[dict]:
    """The sport's market catalogue: id, slug and category for each market."""
    return list(client.get("/markets", sport=SPORT_NAMES[sport]).get("markets") or [])


def book_counts(body: dict) -> tuple[int, dict[int, int]]:
    """(offers, {book id: selections it quotes a current line on}) for an offers response. Lines are
    counted, never read."""
    counts: dict[int, int] = {}
    offers = body.get("offers") or []
    for offer in offers:
        for sel in offer.get("selections") or []:
            for book in sel.get("books") or []:
                current = _current(book.get("lines") or [])
                if current is None or current.get("is_off"):
                    continue
                bid = int(book.get("id"))
                counts[bid] = counts.get(bid, 0) + 1
    return len(offers), counts


def probe_props(client: Client, sport: str, event_ids: list[int], max_pages: int = 3) -> dict:
    """Which books quote the probe's player-prop markets on these events, and how many props each."""
    listed = markets(client, sport)
    categories: dict[str, int] = {}
    for m in listed:
        c = str(m.get("category") or "?")
        categories[c] = categories.get(c, 0) + 1
    wanted = [m for m in listed if str(m.get("slug") or "") in PROP_PROBE_SLUGS]
    out = {"sport": sport, "listed": len(listed), "categories": categories,
           "markets": [str(m.get("slug")) for m in wanted], "events": len(event_ids), "offers": 0, "books": {},
           "prop_slugs": sorted({str(m.get("slug")) for m in listed if "prop" in str(m.get("category") or "")})[:12]}
    if not wanted or not event_ids:
        return out
    ids = ":".join(str(int(m["id"])) for m in wanted)
    events = ":".join(str(int(e)) for e in event_ids[:BATCH])
    for page in range(1, max_pages + 1):
        body = client.get("/offers", sport=SPORT_NAMES[sport], market_id=ids, event_id=events, location=LOCATION,
                          limit=50, page=page)
        n, counts = book_counts(body)
        out["offers"] += n
        for bid, c in counts.items():
            out["books"][bid] = out["books"].get(bid, 0) + c
        if page >= int((body.get("_pagination") or {}).get("total_pages") or 1):
            break
    return out


def describe_probe(result: dict) -> str:
    """One log line: the markets asked, the props found, the pick'em apps by name, the books that quote."""
    books = result["books"]
    pickem = ", ".join(f"{name} {books.get(bid, 0)}" for bid, name in PICKEM.items())
    top = sorted(((c, b) for b, c in books.items() if b not in PICKEM and b != CONSENSUS), reverse=True)[:8]
    quoting = ", ".join(f"{book_name(b)} {c}" for c, b in top) or "none"
    if not result["markets"]:
        return (f"props probe: {result['sport']}: none of {', '.join(PROP_PROBE_SLUGS)} among {result['listed']} "
                f"markets listed {result['categories']}; prop slugs listed: {', '.join(result['prop_slugs']) or 'none'}")
    return (f"props probe: {result['sport']}: {', '.join(result['markets'])} on {result['events']} events: "
            f"{result['offers']} player props; pick'em: {pickem}; books quoting: {quoting}")


def main() -> None:
    ap = argparse.ArgumentParser(description="This weekend's multi-book lines from BettingPros")
    ap.add_argument("--sport", default="ncaaf", choices=sorted(MARKETS))
    ap.add_argument("--season", type=int, required=True)
    ap.add_argument("--week", type=int, required=True)
    args = ap.parse_args()
    client = Client.from_env()
    if client is None:
        raise SystemExit(f"{KEY} is not set")
    ev = events(client, args.sport, args.season, args.week)
    print(ev[["event_id", "scheduled", "visitor_school", "home_school", "stadium_type", "forecast_wind"]].to_string())
    lines = offers(client, args.sport, ev["event_id"].tolist()[:BATCH])
    lines["book"] = lines["book_id"].map(book_name)
    with pd.option_context("display.width", 200, "display.max_rows", 200):
        print(lines[["event_id", "market", "selection", "book", "line", "cost", "updated", "open_line"]].to_string())
    print(f"{client.calls} calls")


if __name__ == "__main__":
    main()
