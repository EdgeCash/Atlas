"""Polymarket US's game markets, read from its public API and kept as a timestamped record.

Polymarket US (``polymarket.us``) is the CFTC-regulated exchange: dollar
contracts on a central order book, one instrument per market whose Yes is
bought at the ask and whose No is the same instrument sold, so a No costs one
less the bid. Its public gateway (``gateway.polymarket.us``) needs no key:

* ``/v2/leagues/{slug}/events`` lists a league's games, fifty a page, each
  with its teams, its start and its market counts but only its headline
  market;
* ``/v1/events?slug=`` returns one game with every market on it: the
  moneyline, the ladders of spreads and totals, the periods and team
  totals, and the player props (`atlas/polymarket/props.py`);
* ``/v1/markets/{slug}/book`` is one market's book, every price level with
  the shares resting there (:func:`depth`), ``/v1/price-history`` its stored
  prices (:func:`history`) and ``/v1/markets/{slug}/settlement`` what it
  settled at (:func:`settlement`).

Every quote is written to ``tracking/polymarket_quotes.csv`` in the clear,
append-on-change (`fold`): a row per contract per observed price, with the
time it was first seen and last seen. That table is the point-in-time archive
the research never had - the market as it stood when Atlas spoke - and the
close every position is graded against.

Conventions, checked against the API on 23 October 2026 and pinned by tests:
an event's ``teams`` are listed away first, as its title reads "Away vs.
Home"; a winner's or a spread's sides carry the team's id, and a spread's
long side is the team the question names at the handicap its description
shows ("+15.50"), the other side the opponent at its negative; a total's
sides are Over and Under at the market's ``line``; ``bestBidQuote`` and
``bestAskQuote`` are the long side's, so the short side's are their
complements; the taker fee per contract is ``coefficient x price x (1 -
price)``, the coefficient (0.0695 on every market that day) read from the
market itself. A side's id is the contract's handle in the record, the
market's slug its handle on the API.
"""

from __future__ import annotations

import math
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd

from atlas.util import get_logger, http_get, session

LOG = get_logger(__name__)

GATEWAY = "https://gateway.polymarket.us"
PAGE = 50
#: Games read each run: from a few hours ago (a game under way keeps its close) to this far ahead.
BEHIND = timedelta(hours=6)
HORIZON = timedelta(days=3)
#: Between requests: the gateway allows 25 a second, and a poll needs no more than a few a second.
PAUSE = 0.06


@dataclass(frozen=True)
class League:
    sport: str          # Atlas's name
    slug: str           # the league's slug on the gateway
    word: str           # the sport's word in its market types ("basketball_team_full_game_winner")


#: The gateway's leagues on 23 October 2026.
LEAGUES = {
    "nfl": League("nfl", "nfl", "football"),
    "nhl": League("nhl", "nhl", "hockey"),
    "ncaaf": League("ncaaf", "cfb", "football"),
    "nba": League("nba", "nba", "basketball"),
}
#: What the always-on worker (`atlas/polymarket/worker.py`) reads besides: leagues Atlas has no model for, so
#: the scheduled capture does not read their games in full, but whose games the favorites and finish-line
#: rules take on the venue's prices alone. College basketball was the largest source of finished games on
#: the venue's tape (``reports/Polymarket US worker edge survey.md``); its season's games list from early
#: November 2026 under ``basketball_team_full_game_*`` market types, as the NBA's do this season (last
#: season's were the bare ``moneyline``, which this module does not read).
WORKER_LEAGUES = {
    **LEAGUES,
    "ncaab": League("ncaab", "cbb", "basketball"),
}
#: The tail of a game market's ``sportsMarketType`` to Atlas's market.
GAME_MARKETS = {"team_full_game_winner": "moneyline", "team_full_game_spread": "spread",
                "team_full_game_total": "total"}
HANDICAP = re.compile(r"^\s*([-+]?\d+(?:\.\d+)?)\s*$")
OPEN = "MARKET_STATUS_OPEN"

QUOTE_COLUMNS = [
    "captured_at", "last_seen_at", "sport", "game_id", "event_id", "event_slug", "game_start", "away", "home",
    "market_id", "market_slug", "token_id", "market", "side", "long", "line", "bid", "ask", "mid", "last", "spread",
    "liquidity", "fee_rate", "accepting", "min_size", "tick",
]
#: A contract's stream in the record, and what has to change to earn a new row.
STREAM = "token_id"
QUOTE = ["bid", "ask", "mid", "last"]
#: Refreshed in place on the latest row when the quote has not moved.
SIGHTING = ["last_seen_at", "liquidity", "accepting", "game_id"]


# ---------------------------------------------------------------------------
# The gateway
# ---------------------------------------------------------------------------


def _get(path: str, params: dict | None = None, sess=None, **kw):
    return http_get(f"{GATEWAY}{path}", params=params, sess=sess, timeout=kw.pop("timeout", 60), **kw).json()


def _utc(value):
    t = pd.to_datetime(value, utc=True, errors="coerce")
    return t if pd.notna(t) else pd.NaT


def fetch_listing(league: League, sess=None) -> list[dict]:
    """The league's games as the gateway lists them: a stub per event, its headline market only."""
    sess = sess or session()
    out: list[dict] = []
    offset = 0
    while True:
        page = _get(f"/v2/leagues/{league.slug}/events", {"limit": PAGE, "offset": offset}, sess)
        events = page.get("events") if isinstance(page, dict) else None
        if not events:
            break
        out.extend(events)
        if len(events) < PAGE:
            break
        offset += PAGE
        time.sleep(PAUSE)
    return out


def fetch_event(slug: str, sess=None) -> dict | None:
    """One game with every market on it."""
    found = _get("/v1/events", {"slug": slug}, sess)
    events = found.get("events") if isinstance(found, dict) else None
    return events[0] if events else None


def start_of(event: dict):
    return _utc(event.get("startTime") or event.get("startDate"))


def fetch_events(league: League, sess=None, *, now: datetime | None = None, behind: timedelta = BEHIND,
                 horizon: timedelta = HORIZON) -> list[dict]:
    """Every game of the league inside the window, each read in full."""
    sess = sess or session()
    now = pd.Timestamp(now or datetime.now(UTC))
    now = now.tz_localize("UTC") if now.tzinfo is None else now.tz_convert("UTC")
    out: list[dict] = []
    for stub in fetch_listing(league, sess):
        start = start_of(stub)
        if pd.isna(start) or start < now - behind or start > now + horizon:
            continue
        full = fetch_event(str(stub.get("slug")), sess)
        if full:
            out.append(full)
        time.sleep(PAUSE)
    return out


def _num(value) -> float:
    if isinstance(value, dict):
        value = value.get("value")
    try:
        v = float(value)
    except (TypeError, ValueError):
        return float("nan")
    return v if math.isfinite(v) else float("nan")


def _round(value: float) -> float:
    """To the record's precision (`atlas/live/store.py` writes three decimals), so a quote read back from
    the record compares equal to the same quote read from the API."""
    return round(value, 3) if math.isfinite(value) else value


def market_kind(market: dict, league: League) -> str | None:
    """Atlas's market for a full-game market of the league's sport; None for anything else."""
    kind = str(market.get("sportsMarketType") or "")
    prefix = f"{league.word}_"
    if not kind.startswith(prefix):
        return None
    return GAME_MARKETS.get(kind[len(prefix):])


def game_markets(event: dict, league: League) -> list[dict]:
    return [m for m in event.get("markets") or [] if market_kind(m, league)]


def is_game(event: dict, league: League | None = None) -> bool:
    """A game event: it carries a full-game market."""
    leagues = [league] if league else list(LEAGUES.values())
    return any(game_markets(event, lg) for lg in leagues)


def team_name(team: dict) -> str:
    """The team's full name as the scoreboard would have it: "Chicago Bulls" from a nickname and a city,
    "Pittsburgh Steelers" or "North Carolina Central" from a name that is already whole."""
    name, safe = str(team.get("name") or "").strip(), str(team.get("safeName") or "").strip()
    if " " in name or not safe:
        return name or safe
    return safe if name.lower() in safe.lower() else f"{safe} {name}"


def teams(event: dict, league: League | None = None) -> tuple[str | None, str | None]:
    """(away, home): the event's teams, listed away first, as its title reads "Away vs. Home"."""
    listed = event.get("teams") or []
    if len(listed) == 2:
        return team_name(listed[0]), team_name(listed[1])
    title = str(event.get("title") or "")
    parts = re.split(r"\s+vs\.?\s+", title, maxsplit=1, flags=re.IGNORECASE)
    return (parts[0].strip(), parts[1].strip()) if len(parts) == 2 else (None, None)


def team_ids(event: dict) -> tuple[int | None, int | None]:
    listed = event.get("teams") or []
    if len(listed) != 2:
        return None, None
    ids = []
    for t in listed:
        raw = t.get("id")
        ids.append(int(raw) if raw is not None and str(raw).isdigit() else None)
    return ids[0], ids[1]


def fee_rate(market: dict) -> float:
    """The market's taker fee coefficient, from the market itself."""
    rate = _num(market.get("feeCoefficient"))
    return rate if math.isfinite(rate) else 0.0


def game_start(market: dict, event: dict):
    for raw in (market.get("gameStartTime"), event.get("startTime"), event.get("startDate")):
        if raw:
            t = _utc(raw)
            if pd.notna(t):
                return t
    return pd.NaT


def side_of(side: dict, kind: str, event: dict) -> str | None:
    """Which side of the game a market side is: over or under, or the away or home team by the team id the
    side carries, else by its name."""
    label = str(side.get("description") or "").strip().lower()
    if kind == "total":
        return {"over": "over", "under": "under"}.get(label)
    away_id, home_id = team_ids(event)
    raw = side.get("teamId")
    tid = int(raw) if raw is not None and str(raw).isdigit() else None
    if tid is not None and tid == away_id:
        return "away"
    if tid is not None and tid == home_id:
        return "home"
    away, home = teams(event)
    for name, which in ((away, "away"), (home, "home")):
        if name and label and (label == name.lower() or label in name.lower().split()):
            return which
    return None


def accepting(market: dict) -> bool:
    return str(market.get("status") or "") == OPEN and bool(market.get("active", True)) and not bool(market.get("closed"))


def quotes(events: list[dict], league: League, captured_at: datetime | str) -> pd.DataFrame:
    """One row per contract (a side of a full-game market) across the events, as of ``captured_at``."""
    stamp = pd.Timestamp(captured_at)
    stamp = (stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC"))
    stamp = stamp.replace(microsecond=0).isoformat()
    rows = []
    for event in events:
        markets = game_markets(event, league)
        if not markets:
            continue
        away, home = teams(event, league)
        for m in markets:
            kind = market_kind(m, league)
            sides = m.get("marketSides") or []
            if len(sides) != 2 or kind is None:
                continue
            long_, short = (sides[0], sides[1]) if sides[0].get("long", True) else (sides[1], sides[0])
            which = [side_of(long_, kind, event), side_of(short, kind, event)]
            if kind == "moneyline":
                lines = [0.0, 0.0]
            elif kind == "total":
                line = _num(m.get("line"))
                lines = [line, line]
            else:
                hm = HANDICAP.match(str(long_.get("description") or ""))
                handicap = _num(hm.group(1)) if hm else float("nan")
                if not math.isfinite(handicap):
                    handicap = _num(m.get("line"))
                lines = [handicap, -handicap]
            if None in which or sorted(which) not in (["away", "home"], ["over", "under"]) \
                    or any(not math.isfinite(x) for x in lines):
                continue
            bid0, ask0 = _round(_num(m.get("bestBidQuote"))), _round(_num(m.get("bestAskQuote")))
            bids = [bid0, _round(1.0 - ask0) if math.isfinite(ask0) else float("nan")]
            asks = [ask0, _round(1.0 - bid0) if math.isfinite(bid0) else float("nan")]
            mids = [_round((b + a) / 2.0) if math.isfinite(b) and math.isfinite(a) else float("nan")
                    for b, a in zip(bids, asks, strict=True)]
            spread = _round(ask0 - bid0) if math.isfinite(ask0) and math.isfinite(bid0) else float("nan")
            start = game_start(m, event)
            open_ = accepting(m)
            for i, side in enumerate((long_, short)):
                rows.append({
                    "captured_at": stamp, "last_seen_at": stamp, "sport": league.sport, "game_id": None,
                    "event_id": str(event.get("id")), "event_slug": event.get("slug"),
                    "game_start": start.isoformat() if pd.notna(start) else None, "away": away, "home": home,
                    "market_id": str(m.get("id")), "market_slug": m.get("slug"), "token_id": str(side.get("id")),
                    "market": kind, "side": which[i], "long": i == 0, "line": lines[i], "bid": bids[i], "ask": asks[i],
                    "mid": mids[i], "last": float("nan"), "spread": spread, "liquidity": float("nan"),
                    "fee_rate": fee_rate(m), "accepting": open_, "min_size": _num(m.get("minimumTradeQty")),
                    "tick": _num(m.get("orderPriceMinTickSize")),
                })
    return pd.DataFrame(rows, columns=QUOTE_COLUMNS)


def capture_events(leagues=None, sess=None, *, now: datetime | None = None) -> dict[str, list[dict]]:
    """Every game inside the window of every league, read in full, by sport. A league that fails is logged
    and skipped."""
    sess = sess or session()
    out: dict[str, list[dict]] = {}
    for league in (leagues or LEAGUES.values()):
        try:
            out[league.sport] = fetch_events(league, sess, now=now)
        except Exception as error:  # noqa: BLE001 - one league's outage is not the run's
            LOG.warning("polymarket: %s not read (%s)", league.sport, type(error).__name__)
    return out


def capture(now: datetime, leagues=None, sess=None, events: dict[str, list[dict]] | None = None) -> pd.DataFrame:
    """Every full-game contract of every league, quoted as of ``now``, from ``events`` (fetched here when
    not given). A league that fails is logged and skipped: the others' quotes stand."""
    events = events if events is not None else capture_events(leagues, sess, now=now)
    parts = []
    for league in (leagues or LEAGUES.values()):
        if league.sport not in events:
            continue
        q = quotes(events[league.sport], league, now)
        LOG.info("polymarket: %s, %d events, %d game markets quoted", league.sport,
                 sum(1 for e in events[league.sport] if is_game(e, league)), len(q) // 2)
        parts.append(q)
    parts = [p for p in parts if len(p)]
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=QUOTE_COLUMNS)


# ---------------------------------------------------------------------------
# One market's book, prices and settlement
# ---------------------------------------------------------------------------


def _levels(raw, best) -> list[tuple[float, float]]:
    """A side of the book as (price, shares) levels, best first; levels that do not read are dropped."""
    out = [(_num(level.get("px")), _num(level.get("qty"))) for level in raw or [] if isinstance(level, dict)]
    out = [(px, qty) for px, qty in out if math.isfinite(px) and math.isfinite(qty) and qty > 0]
    return sorted(out, key=lambda level: level[0], reverse=best == "high")


def depth(market_slug: str, side_long: bool, sess=None) -> dict:
    """The top of the market's book for one side: its bid and ask, the spread, and the dollars that can be
    bought at the ask (the shares resting at that one price times the price). The short side is the long one
    inverted: its ask is one less the long bid, with the shares bid there.

    Read from the full book (``/v1/markets/{slug}/book``), not the top-of-book endpoint: ``/bbo``'s
    ``askShares`` and ``bidShares`` are the whole side of the book, every level summed (on 26 October 2026 an
    NBA moneyline's ``askShares`` read 770,000 with 380,259 at the best ask), so a depth read from them
    overstates what one price will fill. Both endpoints are edge-cached for 30 seconds."""
    raw = (_get(f"/v1/markets/{market_slug}/book", sess=sess) or {}).get("marketData") or {}
    bids = _levels(raw.get("bids"), "high")
    offers = _levels(raw.get("offers") or raw.get("asks"), "low")
    bid, bid_shares = bids[0] if bids else (float("nan"), float("nan"))
    ask, ask_shares = offers[0] if offers else (float("nan"), float("nan"))
    if not side_long:
        bid, ask = (1.0 - ask if math.isfinite(ask) else float("nan")), (1.0 - bid if math.isfinite(bid) else float("nan"))
        ask_shares, bid_shares = bid_shares, ask_shares
    dollars = ask_shares * ask if math.isfinite(ask_shares) and math.isfinite(ask) else float("nan")
    return {"bid": _round(bid), "ask": _round(ask),
            "spread": _round(ask - bid) if math.isfinite(ask) and math.isfinite(bid) else float("nan"),
            "ask_shares": ask_shares, "ask_dollars": dollars, "state": raw.get("state")}


def history(market_slug: str, sess=None, *, start=None, end=None, interval: str = "INTERVAL_ALL",
            fidelity: int = 180) -> pd.DataFrame:
    """The market's stored prices: (``at``, ``long``, ``short``), oldest first. A ``start`` and ``end``
    (within a day of each other) read that window minute by minute; otherwise ``interval`` at ``fidelity``."""
    params: dict = {"symbol": market_slug}
    if start is not None and end is not None:
        params.update({"timestamp.startTimestamp": int(pd.Timestamp(start).timestamp()),
                       "timestamp.endTimestamp": int(pd.Timestamp(end).timestamp()), "fidelity": 1})
    else:
        params.update({"fixedInterval": interval, "fidelity": fidelity})
    raw = _get("/v1/price-history", params, sess)
    rows = [{"at": pd.Timestamp(int(h["timestamp"]), unit="s", tz="UTC"), "long": _num(h.get("longPrice")),
             "short": _num(h.get("shortPrice"))} for h in (raw.get("history") or []) if "timestamp" in h]
    return pd.DataFrame(rows, columns=["at", "long", "short"]).sort_values("at").reset_index(drop=True)


def settlement(market_slug: str, sess=None) -> float:
    """What the market settled at, one or zero for the long side (or the last fair price where its rules say
    so); nan when it has not settled.

    Read with a unique query, past the edge cache: before a market settles the endpoint answers "not found",
    and the cache keeps serving that answer well past its 30-second max-age (a gold window settled Up on 26
    October 2026 still read "not found" from the cache 197 seconds on), so every rule's grade would lag the
    venue's settlement by minutes. A rule reads a market's settlement once a tick at most."""
    try:
        raw = _get(f"/v1/markets/{market_slug}/settlement", {"fresh": time.time_ns()}, sess=sess)
    except Exception:  # noqa: BLE001 - not settled, or not found: the same answer
        return float("nan")
    data = raw if isinstance(raw, dict) else {}
    data = data.get("marketData") or data
    for key in ("settlement", "settlementPx", "settlementPrice"):
        v = _num(data.get(key))
        if math.isfinite(v):
            return v
    return float("nan")


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
IDS = ("game_id", "event_id", "market_id", "token_id")


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
                if c == "liquidity" and (value is None or (isinstance(value, float) and math.isnan(value))):
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


def venue_close(record: pd.DataFrame, token_id: str, start, sess=None) -> float:
    """The close from the venue's own price history when the record has none: the last stored price of the
    contract's side in the two hours before the start."""
    r = record[record[STREAM].astype(str) == str(token_id)] if len(record) else record
    if r.empty:
        return float("nan")
    row = r.iloc[-1]
    cutoff = pd.Timestamp(start)
    cutoff = cutoff.tz_localize("UTC") if cutoff.tzinfo is None else cutoff.tz_convert("UTC")
    h = history(str(row["market_slug"]), sess, start=cutoff - timedelta(hours=2), end=cutoff)
    if h.empty:
        return float("nan")
    before = h[h["at"] <= cutoff]
    if before.empty:
        return float("nan")
    column = "long" if _truthy(row.get("long")) else "short"
    return float(before[column].iloc[-1])


def _truthy(value) -> bool:
    return str(value).strip().lower() in ("true", "1", "1.0")
