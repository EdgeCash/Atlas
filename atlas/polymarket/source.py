"""Polymarket's game markets, read from its public APIs and kept as a timestamped record.

Two services, neither needing a key:

* **Gamma** (``gamma-api.polymarket.com``) lists events and their markets.
  A game is one event (``nfl-kc-sea-2026-10-26``, "Chiefs vs. Seahawks")
  carrying a moneyline, a ladder of spreads and a ladder of totals, each a
  two-outcome market with a best bid and ask, a midpoint per outcome, the
  book's depth in dollars and its fee schedule. Player props, halves,
  quarters and exact margins hang off separate events and are not read.
* **CLOB** (``clob.polymarket.com``) is the order book itself: the depth at
  the best ask for a contract about to be bought (:func:`book`), and the
  price history that stands in for a close the poll missed
  (:func:`history`).

Every quote is written to ``tracking/polymarket_quotes.csv`` in the clear,
append-on-change (`fold`): a row per contract per observed price, with the
time it was first seen and last seen. That table is the point-in-time archive
the research never had - the market as it stood when Atlas spoke - and the
close every position is graded against.

Conventions, checked against the API on 23 October 2026 and pinned by tests:
the first outcome of a moneyline or spread is the **away** side (the
league's ``ordering`` is ``away`` for all three; the title reads "Away vs.
Home"); a spread's ``line`` is the handicap of the team its question names
("Spread: Chiefs (-1.5)"), and the other side's is its negative; a total's
``line`` is the total and its outcomes are Over and Under; ``bestBid`` and
``bestAsk`` are the first outcome's, so the second's are their complements;
the taker fee per contract is ``rate x price x (1 - price)`` (the docs'
formula), ``rate`` read from the market's own ``feeSchedule``.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from datetime import datetime

import numpy as np
import pandas as pd

from atlas.util import get_logger, http_get, session

LOG = get_logger(__name__)

GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"
PAGE = 100


@dataclass(frozen=True)
class League:
    sport: str          # Atlas's name
    series: int         # Gamma's series id for the league's games
    tag: int            # Gamma's tag id
    slug: str           # the prefix of a game event's slug
    ordering: str = "away"   # which side the first outcome is


#: Gamma's ``/sports`` on 23 October 2026.
LEAGUES = {
    "nfl": League("nfl", 12185, 450, "nfl"),
    "nhl": League("nhl", 10346, 899, "nhl"),
    "ncaaf": League("ncaaf", 12756, 100351, "cfb"),
    "nba": League("nba", 10345, 745, "nba"),
}
#: Polymarket's ``sportsMarketType`` to Atlas's market.
GAME_MARKETS = {"moneyline": "moneyline", "spreads": "spread", "totals": "total"}
SPREAD_QUESTION = re.compile(r"^Spread:\s*(?P<team>.+?)\s*\((?P<line>[-+]?\d+(?:\.\d+)?)\)\s*$")

QUOTE_COLUMNS = [
    "captured_at", "last_seen_at", "sport", "game_id", "event_id", "event_slug", "game_start", "away", "home",
    "market_id", "condition_id", "token_id", "market", "side", "line", "bid", "ask", "mid", "last", "spread",
    "liquidity", "fee_rate", "accepting", "min_size", "tick",
]
#: A contract's stream in the record, and what has to change to earn a new row.
STREAM = "token_id"
QUOTE = ["bid", "ask", "mid", "last"]
#: Refreshed in place on the latest row when the quote has not moved.
SIGHTING = ["last_seen_at", "liquidity", "accepting", "game_id"]


# ---------------------------------------------------------------------------
# Gamma
# ---------------------------------------------------------------------------


def _get(url: str, params: dict | None = None, sess=None, **kw):
    return http_get(url, params=params, sess=sess, timeout=kw.pop("timeout", 30), **kw).json()


def fetch_events(league: League, sess=None, *, closed: bool = False) -> list[dict]:
    """Every open event of the league's series, paged."""
    sess = sess or session()
    out: list[dict] = []
    offset = 0
    while True:
        page = _get(f"{GAMMA}/events", {"series_id": league.series, "active": "true",
                                        "closed": "true" if closed else "false", "limit": PAGE, "offset": offset,
                                        "order": "startDate", "ascending": "true"}, sess)
        if not isinstance(page, list):
            break
        out.extend(page)
        if len(page) < PAGE:
            break
        offset += PAGE
    return out


def fetch_event(slug: str, sess=None) -> dict | None:
    found = _get(f"{GAMMA}/events", {"slug": slug}, sess)
    return found[0] if isinstance(found, list) and found else None


def _list(value) -> list:
    if value is None:
        return []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return []
    return list(value) if isinstance(value, list) else []


def _num(value) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return float("nan")
    return v if math.isfinite(v) else float("nan")


def _round(value: float) -> float:
    """To the record's precision (`atlas/live/store.py` writes three decimals), so a quote read back from
    the record compares equal to the same quote read from the API."""
    return round(value, 3) if math.isfinite(value) else value


def game_markets(event: dict) -> list[dict]:
    return [m for m in event.get("markets") or [] if m.get("sportsMarketType") in GAME_MARKETS]


def is_game(event: dict) -> bool:
    """A game event, as opposed to its props, halves or exact margins: it carries a game market."""
    return bool(game_markets(event))


def teams(event: dict, league: League) -> tuple[str | None, str | None]:
    """(away, home) from the title "Away vs. Home", by the league's ordering."""
    title = str(event.get("title") or "")
    parts = re.split(r"\s+vs\.?\s+", title, maxsplit=1, flags=re.IGNORECASE)
    if len(parts) != 2:
        return None, None
    first, second = parts[0].strip(), parts[1].strip()
    return (first, second) if league.ordering == "away" else (second, first)


def fee_rate(market: dict) -> float:
    """The market's taker fee rate, from its own schedule; zero on a fee-free market."""
    if not market.get("feesEnabled"):
        return 0.0
    schedule = market.get("feeSchedule") or {}
    rate = _num(schedule.get("rate"))
    if math.isfinite(rate):
        return rate
    bps = _num(market.get("takerBaseFee"))
    return bps / 10_000.0 if math.isfinite(bps) else 0.0


def _game_start(market: dict, event: dict):
    for key in ("gameStartTime", "endDate"):
        raw = market.get(key) or event.get(key)
        if raw:
            t = pd.to_datetime(raw, utc=True, errors="coerce")
            if pd.notna(t):
                return t
    return pd.NaT


def _sides(kind: str, outcomes: list, away: str | None, home: str | None, ordering: str) -> list[str | None]:
    if kind == "total":
        return [{"over": "over", "under": "under"}.get(str(o).strip().lower()) for o in outcomes]
    names = [str(o).strip().lower() for o in outcomes]
    by_name = []
    for n in names:
        if away and n == away.lower():
            by_name.append("away")
        elif home and n == home.lower():
            by_name.append("home")
        else:
            by_name.append(None)
    if sorted(x for x in by_name if x) == ["away", "home"]:
        return by_name
    first = "away" if ordering == "away" else "home"
    second = "home" if first == "away" else "away"
    return [first, second]


def _lines(kind: str, market: dict, outcomes: list) -> list[float]:
    line = _num(market.get("line"))
    if kind == "moneyline":
        return [0.0, 0.0]
    if kind == "total":
        return [line, line]
    m = SPREAD_QUESTION.match(str(market.get("question") or ""))
    if m is None:
        return [float("nan"), float("nan")]
    named, handicap = m.group("team").strip().lower(), _num(m.group("line"))
    if not math.isfinite(handicap):
        handicap = line
    names = [str(o).strip().lower() for o in outcomes]
    if named == names[0]:
        return [handicap, -handicap]
    if named == names[1]:
        return [-handicap, handicap]
    return [float("nan"), float("nan")]


def quotes(events: list[dict], league: League, captured_at: datetime | str) -> pd.DataFrame:
    """One row per contract (an outcome of a game market) across the events, as of ``captured_at``."""
    stamp = pd.Timestamp(captured_at)
    stamp = (stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC"))
    stamp = stamp.replace(microsecond=0).isoformat()
    rows = []
    for event in events:
        markets = game_markets(event)
        if not markets:
            continue
        away, home = teams(event, league)
        for m in markets:
            kind = GAME_MARKETS[m["sportsMarketType"]]
            outcomes, prices, tokens = _list(m.get("outcomes")), _list(m.get("outcomePrices")), _list(m.get("clobTokenIds"))
            if len(outcomes) != 2 or len(tokens) != 2:
                continue
            sides = _sides(kind, outcomes, away, home, league.ordering)
            lines = _lines(kind, m, outcomes)
            if None in sides or any(not math.isfinite(x) for x in lines):
                continue
            bid0, ask0 = _round(_num(m.get("bestBid"))), _round(_num(m.get("bestAsk")))
            bids = [bid0, _round(1.0 - ask0) if math.isfinite(ask0) else float("nan")]
            asks = [ask0, _round(1.0 - bid0) if math.isfinite(bid0) else float("nan")]
            mids = [_round(_num(prices[i])) if i < len(prices) else float("nan") for i in range(2)]
            last0 = _round(_num(m.get("lastTradePrice")))
            lasts = [last0, _round(1.0 - last0) if math.isfinite(last0) else float("nan")]
            start = _game_start(m, event)
            accepting = bool(m.get("acceptingOrders")) and bool(m.get("active", True)) and not bool(m.get("closed"))
            for i in range(2):
                rows.append({
                    "captured_at": stamp, "last_seen_at": stamp, "sport": league.sport, "game_id": None,
                    "event_id": str(event.get("id")), "event_slug": event.get("slug"),
                    "game_start": start.isoformat() if pd.notna(start) else None, "away": away, "home": home,
                    "market_id": str(m.get("id")), "condition_id": m.get("conditionId"), "token_id": str(tokens[i]),
                    "market": kind, "side": sides[i], "line": lines[i], "bid": bids[i], "ask": asks[i],
                    "mid": mids[i], "last": lasts[i], "spread": _round(_num(m.get("spread"))),
                    "liquidity": _num(m.get("liquidityNum", m.get("liquidity"))), "fee_rate": fee_rate(m),
                    "accepting": accepting, "min_size": _num(m.get("orderMinSize")),
                    "tick": _num(m.get("orderPriceMinTickSize")),
                })
    return pd.DataFrame(rows, columns=QUOTE_COLUMNS)


def capture_events(leagues=None, sess=None) -> dict[str, list[dict]]:
    """Every open event of every league, by sport. A league that fails is logged and skipped."""
    sess = sess or session()
    out: dict[str, list[dict]] = {}
    for league in (leagues or LEAGUES.values()):
        try:
            out[league.sport] = fetch_events(league, sess)
        except Exception as error:  # noqa: BLE001 - one league's outage is not the run's
            LOG.warning("polymarket: %s not read (%s)", league.sport, type(error).__name__)
    return out


def capture(now: datetime, leagues=None, sess=None, events: dict[str, list[dict]] | None = None) -> pd.DataFrame:
    """Every open game contract of every league, quoted as of ``now``, from ``events`` (fetched here when
    not given). A league that fails is logged and skipped: the others' quotes stand."""
    events = events if events is not None else capture_events(leagues, sess)
    parts = []
    for league in (leagues or LEAGUES.values()):
        if league.sport not in events:
            continue
        q = quotes(events[league.sport], league, now)
        LOG.info("polymarket: %s, %d events, %d game markets quoted", league.sport,
                 sum(1 for e in events[league.sport] if is_game(e)), len(q) // 2)
        parts.append(q)
    parts = [p for p in parts if len(p)]
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=QUOTE_COLUMNS)


# ---------------------------------------------------------------------------
# CLOB
# ---------------------------------------------------------------------------


def book(token_id: str, sess=None) -> dict:
    """The order book for one contract: best bid and ask with their sizes, and the dollars resting on the
    ask side within five cents of the best. What a position can actually be filled at."""
    raw = _get(f"{CLOB}/book", {"token_id": str(token_id)}, sess)
    bids = sorted(((_num(b.get("price")), _num(b.get("size"))) for b in raw.get("bids") or []), reverse=True)
    asks = sorted((_num(a.get("price")), _num(a.get("size"))) for a in raw.get("asks") or [])
    best_bid = bids[0] if bids else (float("nan"), 0.0)
    best_ask = asks[0] if asks else (float("nan"), 0.0)
    near = sum(p * s for p, s in asks if math.isfinite(p) and p <= best_ask[0] + 0.05) if asks else 0.0
    return {"bid": best_bid[0], "bid_size": best_bid[1], "ask": best_ask[0], "ask_size": best_ask[1],
            "ask_dollars_near": near}


def history(token_id: str, sess=None, *, interval: str = "max", fidelity: int = 60) -> pd.DataFrame:
    """The contract's price history: (``at``, ``price``), oldest first."""
    raw = _get(f"{CLOB}/prices-history", {"market": str(token_id), "interval": interval, "fidelity": fidelity}, sess)
    rows = [{"at": pd.Timestamp(int(h["t"]), unit="s", tz="UTC"), "price": _num(h.get("p"))}
            for h in raw.get("history") or [] if "t" in h]
    return pd.DataFrame(rows, columns=["at", "price"]).sort_values("at").reset_index(drop=True)


# ---------------------------------------------------------------------------
# The record
# ---------------------------------------------------------------------------


def main_lines(q: pd.DataFrame) -> pd.DataFrame:
    """What the record keeps of a game: its moneyline, and the spread and the total at the line the market
    prices nearest to even (both sides of each) - the closing line, as a sportsbook's would be read. The
    rest of the ladder is read every run for pricing and not kept."""
    if q.empty:
        return q
    mid = pd.to_numeric(q["mid"], errors="coerce")
    first = q["side"].isin(["home", "over"])
    off = (mid - 0.5).abs().where(first)
    nearest = off.groupby([q["event_id"], q["market"]]).transform("min")
    chosen = q["market_id"].where(first & (off == nearest))
    main = chosen.groupby([q["event_id"], q["market"]]).transform("first")
    keep = (q["market"] == "moneyline") | (q["market_id"] == main)
    return q[keep.fillna(False)].reset_index(drop=True)


def _same(a, b) -> bool:
    a, b = pd.to_numeric(a, errors="coerce"), pd.to_numeric(b, errors="coerce")
    return bool(pd.isna(a) and pd.isna(b)) or bool(a == b)


#: Identifiers, kept as text: read back from the record a game id is a number, and a number's column
#: cannot take the text the next capture brings.
IDS = ("game_id", "event_id", "market_id", "condition_id", "token_id")


def _text_ids(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    for c in IDS:
        if c in out:
            v = out[c]
            num = pd.to_numeric(v, errors="coerce")
            whole = num.notna() & (num == np.floor(num.fillna(0)))
            text = v.astype(object).where(v.notna(), None)
            text = text.where(~whole, num.where(whole).map(lambda x: str(int(x)) if pd.notna(x) else None))
            out[c] = text.astype(object)
    return out


def fold(existing: pd.DataFrame, incoming: pd.DataFrame, cols: list[str] | None = None) -> tuple[pd.DataFrame, int]:
    """Append each contract's quote only when it differs from the latest stored; a repeat sighting moves
    ``last_seen_at`` (and the depth, the acceptance flag and the matched game) on the stored row and
    nothing else. Returns (the record, rows appended). ``cols`` is the table's columns (the game quotes'
    by default; the props' are `atlas/polymarket/props.py`'s)."""
    cols = cols or QUOTE_COLUMNS
    history_ = _text_ids(existing.reindex(columns=cols)).reset_index(drop=True) if len(existing) \
        else pd.DataFrame(columns=cols)
    incoming = _text_ids(incoming) if len(incoming) else incoming
    if incoming.empty:
        return history_, 0
    latest: dict[str, int] = {}
    if len(history_):
        when = pd.to_datetime(history_["captured_at"], utc=True, errors="coerce")
        order = history_.assign(_t=when).sort_values("_t", kind="stable")
        latest = {str(k): int(i) for k, i in zip(order[STREAM], order.index, strict=True)}
    obs = incoming.reindex(columns=cols)
    obs = obs.assign(_t=pd.to_datetime(obs["captured_at"], utc=True, errors="coerce")).sort_values("_t", kind="stable")
    appended: list[dict] = []
    pending: dict[str, dict] = {}
    for row in obs.drop(columns="_t").to_dict("records"):
        key = str(row[STREAM])
        held = pending.get(key)
        held_row = held if held is not None else (history_.loc[latest[key]].to_dict() if key in latest else None)
        if held_row is not None and all(_same(held_row.get(c), row.get(c)) for c in QUOTE):
            for c in [c for c in SIGHTING if c in cols]:
                value = row.get(c)
                if c == "game_id" and (value is None or (isinstance(value, float) and math.isnan(value))):
                    continue
                if held is not None:
                    held[c] = value
                else:
                    history_.at[latest[key], c] = value
            continue
        new = dict(row)
        appended.append(new)
        pending[key] = new
    if appended:
        new = pd.DataFrame(appended).reindex(columns=cols)
        history_ = new if history_.empty else pd.concat([history_, new], ignore_index=True)
    history_ = history_.drop_duplicates(subset=[STREAM, "captured_at"], keep="first")
    return history_.reset_index(drop=True), len(appended)


def latest(record: pd.DataFrame) -> pd.DataFrame:
    """The latest quote per contract."""
    if record.empty:
        return record
    r = record.assign(_t=pd.to_datetime(record["captured_at"], utc=True, errors="coerce"))
    return r.sort_values("_t", kind="stable").drop_duplicates(STREAM, keep="last").drop(columns="_t") \
        .reset_index(drop=True)


def close(record: pd.DataFrame, token_id: str, start) -> float:
    """The contract's last midpoint seen before the game started; nan when the record has none."""
    if record.empty:
        return float("nan")
    r = record[record[STREAM].astype(str) == str(token_id)]
    if r.empty:
        return float("nan")
    seen = pd.to_datetime(r["last_seen_at"].fillna(r["captured_at"]), utc=True, errors="coerce")
    first = pd.to_datetime(r["captured_at"], utc=True, errors="coerce")
    cutoff = pd.Timestamp(start)
    cutoff = cutoff.tz_localize("UTC") if cutoff.tzinfo is None else cutoff.tz_convert("UTC")
    before = r[first <= cutoff].assign(_t=first[first <= cutoff], _seen=seen[first <= cutoff])
    if before.empty:
        return float("nan")
    last = before.sort_values("_t", kind="stable").iloc[-1]
    mid = _num(last["mid"])
    if math.isfinite(mid):
        return mid
    bid, ask = _num(last["bid"]), _num(last["ask"])
    return (bid + ask) / 2.0 if math.isfinite(bid) and math.isfinite(ask) else float("nan")
