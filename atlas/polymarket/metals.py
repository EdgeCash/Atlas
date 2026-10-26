"""The gold and silver 15-minute rule, in practice: paper positions only.

Polymarket US lists a gold and a silver Up/Down market every fifteen minutes
(series ``gold-updown-15m``, ``silver-updown-15m``): Up settles to a dollar
when the Chainlink spot price at the window's end is at or above the price at
its start (``priceToBeat``), one value each, read about a minute after the
end. The research (``research_notes/Polymarket US category survey/
commodities.md``) found the books priced to the model in the middle of a
window and one place where they lag: in the last few minutes, the side the
spot price has all but decided is sometimes still offered at 91-97 cents.
On the venue's own history that paid +0.8 to +2.9 cents a contract after the
fee, mostly from one trading day, and a live sample saw one such side lose
(silver, 26 October 00:00Z). This module is the test of it, on paper.

* **When.** The last :data:`FINAL` seconds of each window, polled every
  :data:`POLL` seconds by the always-on worker between its own ticks
  (`atlas/polymarket/worker.py`), until :data:`LAST_CALL` seconds before
  the end.
* **What it reads.** The commodities listing (``/v2/tags/commodities/
  events``, not edge-cached): each open window with its terms and top of
  book. The venue's own Chainlink feed (``/v1/asset-prices/history``, not
  edge-cached): the latest one-second price, and an hour of five-second
  candles for the volatility. Where a position is taken, the market's full
  book, read with a unique query so the 30-second edge cache neither serves
  an old book nor the "not found" it cached before the window opened.
* **The model.** Driftless lognormal: P(Up) = Phi(ln(S / S0) / (sigma *
  sqrt(tau))), with S the spot now, S0 the price to beat, tau the seconds
  left and sigma the per-second volatility of the last hour's five-second
  log returns (at least :data:`MIN_RETURNS` of them).
* **A position.** A side the model puts at or above a threshold
  (:data:`THRESHOLDS`, each recorded separately so the record can say
  which pays), whose ask is at or under :data:`CAP`, and whose model
  probability beats the ask plus the fee by more than :data:`MIN_EDGE`:
  once per side per threshold per window, at the ask, with the shares the
  book holds at the ask and at or under the cap.
* **Grade.** The venue's settlement of the market, read once the window
  has been over :data:`GRADE_AFTER`.

The record is ``tracking/metals.csv``, in the clear: a rule on public
prices. Nothing here places, previews or sizes an order; the live step
(`atlas/polymarket/orders.py`) does not know this rule.
"""

from __future__ import annotations

import math
import os
import time
from datetime import UTC, datetime, timedelta

import pandas as pd

from atlas.polymarket import favorites, pricing, source
from atlas.util import get_logger, offline

LOG = get_logger(__name__)

TABLE = "metals"
TAB = "Metals 15m"
LISTING = "/v2/tags/commodities/events"
SPOT = "/v1/asset-prices/history"
SERIES = ("gold-updown-15m", "silver-updown-15m")
#: The rule's switch for the worker: ``practice`` (unset) or ``off``.
MODE = "METALS_RULE"
WINDOW = 900
#: The final seconds of a window the rule watches, how often it reads them, and the last moment it takes a side.
FINAL = 300
POLL = 10
LAST_CALL = 5
THRESHOLDS = (0.95, 0.97, 0.99)
CAP = 0.97
MIN_EDGE = 0.01
VOL_LOOKBACK = 3600
MIN_RETURNS = 60
GRADE_AFTER = timedelta(seconds=75)
SETTLEMENT_READS = 20
COLUMNS = ["formed_at", "metal", "event_slug", "market_slug", "window_start", "window_end", "seconds_left",
           "price_to_beat", "spot", "sigma", "p_side", "threshold", "side", "long", "ask", "bid", "fee_rate", "fee",
           "cost", "edge", "shares_at_ask", "shares_under_cap", "tick", "payout", "won", "profit", "settled_at"]
GRADED = ("payout", "won", "profit", "settled_at")


def on() -> bool:
    return os.environ.get(MODE, "practice").strip().lower() != "off"


def _stamp(t: datetime) -> str:
    t = pd.Timestamp(t)
    t = t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")
    return t.replace(microsecond=0).isoformat()


def _epoch(value) -> float:
    t = pd.to_datetime(value, utc=True, errors="coerce")
    return t.timestamp() if pd.notna(t) else float("nan")


# ---------------------------------------------------------------------------
# The clock
# ---------------------------------------------------------------------------


def next_poll(now: datetime) -> float:
    """Seconds until the rule should read again: :data:`POLL` inside a window's final stretch, else until the
    stretch of the window under way begins (or the next one's, past this one's last call)."""
    t = pd.Timestamp(now).timestamp()
    end = (t // WINDOW + 1) * WINDOW
    left = end - t
    if LAST_CALL < left <= FINAL:
        return float(POLL)
    if left <= LAST_CALL:
        return left + WINDOW - FINAL
    return left - FINAL


# ---------------------------------------------------------------------------
# What it reads
# ---------------------------------------------------------------------------


def windows(events: list[dict], now: datetime) -> list[dict]:
    """The open gold and silver 15-minute windows in their final stretch, each with what the rule needs: the
    metal, the slugs, the window, the price to beat, the market's tick and fee, and the long (Up) side's best
    bid and ask."""
    t = pd.Timestamp(now).timestamp()
    out = []
    for e in events or []:
        if str(e.get("seriesSlug") or "") not in SERIES:
            continue
        for m in e.get("markets") or []:
            terms = m.get("assetPriceTerms") or {}
            start, end = _epoch(terms.get("windowStart")), _epoch(terms.get("windowEnd"))
            beat = source._num(terms.get("priceToBeat"))
            left = end - t
            if not source.accepting(m) or not math.isfinite(beat) or not LAST_CALL < left <= FINAL:
                continue
            out.append({"metal": str((terms.get("asset") or {}).get("symbol") or e["seriesSlug"].split("-")[0]),
                        "event_slug": e.get("slug"), "market_slug": m.get("slug"), "start": start, "end": end,
                        "left": left, "beat": beat, "tick": source._num(m.get("orderPriceMinTickSize")),
                        "fee_rate": source.fee_rate(m), "bid": source._num(m.get("bestBidQuote")),
                        "ask": source._num(m.get("bestAskQuote"))})
    return out


def listing(sess=None) -> list[dict]:
    found = source._get(LISTING, {"limit": 100}, sess)
    return (found or {}).get("events") or [] if isinstance(found, dict) else []


def candles(metal: str, start: float, bucket: str, sess=None) -> list[tuple[float, float]]:
    """(time, close) of the metal's Chainlink candles from ``start`` to now, oldest first; empty ones dropped."""
    raw = source._get(SPOT, {"assets": f"commodity:{metal}", "from": int(start), "to": 0,
                             "bucket": f"ASSET_PRICE_BUCKET_{bucket}"}, sess)
    series = (raw or {}).get("series") or []
    rows = series[0].get("candles") or [] if series else []
    out = [(float(c["timestamp"]), source._num(c.get("close"))) for c in rows if int(c.get("tickCount") or 0) > 0]
    return sorted((t, p) for t, p in out if math.isfinite(p) and p > 0)


def volatility(closes: list[tuple[float, float]], step: float = 5.0) -> float:
    """Per-second volatility from consecutive five-second log returns; nan with fewer than :data:`MIN_RETURNS`."""
    r = [math.log(b / a) for (s, a), (t, b) in zip(closes, closes[1:], strict=False) if abs(t - s - step) < 1e-9]
    if len(r) < MIN_RETURNS:
        return float("nan")
    return math.sqrt(sum(x * x for x in r) / len(r) / step)


def p_up(spot: float, beat: float, sigma: float, left: float) -> float:
    """The driftless lognormal's probability that the end price is at or above the price to beat."""
    if not all(math.isfinite(v) for v in (spot, beat, sigma, left)) or spot <= 0 or beat <= 0 or left <= 0:
        return float("nan")
    if sigma <= 0:
        return 1.0 if spot >= beat else 0.0
    z = math.log(spot / beat) / (sigma * math.sqrt(left))
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def book_depth(market_slug: str, up: bool, ask: float, sess=None) -> tuple[float, float]:
    """(shares at the side's ask, shares at or under :data:`CAP`) from the market's full book, read with a unique
    query past the edge cache. The Down side's offers are the long side's bids, one less."""
    raw = (source._get(f"/v1/markets/{market_slug}/book", {"fresh": int(time.time() * 1000)}, sess) or {})
    md = raw.get("marketData") or {}
    levels = source._levels(md.get("offers") or md.get("asks"), "low") if up else \
        [(round(1.0 - px, 6), q) for px, q in source._levels(md.get("bids"), "high")]
    at = sum(q for px, q in levels if abs(px - ask) < 1e-9)
    under = sum(q for px, q in levels if px <= CAP + 1e-9)
    return float(at), float(under)


# ---------------------------------------------------------------------------
# The record
# ---------------------------------------------------------------------------


def clean(record: pd.DataFrame | None) -> pd.DataFrame:
    """The record as positions: one per market, side and threshold, the first taken, with any copy's grade."""
    if record is None or record.empty:
        return pd.DataFrame(columns=COLUMNS)
    r = record.reindex(columns=COLUMNS).copy()
    when = pd.to_datetime(r["formed_at"], utc=True, errors="coerce", format="ISO8601")
    r = r[when.notna() & r["market_slug"].notna()].assign(_t=when).sort_values("_t", kind="stable")
    r["_key"] = r["market_slug"].astype(str) + "|" + r["side"].astype(str) + "|" + \
        pd.to_numeric(r["threshold"], errors="coerce").round(2).astype(str)
    if r["_key"].duplicated().any():
        first = r.drop_duplicates("_key", keep="first").set_index("_key")
        graded = r[pd.to_numeric(r["payout"], errors="coerce").notna()].drop_duplicates("_key").set_index("_key")
        for c in GRADED:
            first[c] = first[c].astype(object)
            first.loc[graded.index, c] = graded[c].astype(object)
        r = first.reset_index()
    return r.drop(columns=["_t", "_key"], errors="ignore").reindex(columns=COLUMNS).reset_index(drop=True)


def merge(*records: pd.DataFrame) -> pd.DataFrame:
    parts = [r.reindex(columns=COLUMNS) for r in records if r is not None and len(r)]
    return clean(pd.concat(parts, ignore_index=True) if parts else None)


def take(record: pd.DataFrame, now: datetime, *, events=None, spot=None, depth=None, sess=None) -> tuple[pd.DataFrame, int]:
    """The record with a position for each side and threshold the rule now takes. ``events`` is the listing
    (read when not given); ``spot(metal)`` returns (price now, per-second volatility); ``depth(slug, up, ask)``
    the shares at the ask and under the cap. New positions come at the end."""
    record = clean(record)
    events = events if events is not None else listing(sess)
    open_ = windows(events, now)
    if not open_:
        return record, 0
    if spot is None:
        def spot(metal):
            t = pd.Timestamp(now).timestamp()
            last = candles(metal, t - 15, "1S", sess)
            return (last[-1][1] if last else float("nan"), volatility(candles(metal, t - VOL_LOOKBACK, "5S", sess)))
    depth = depth or (lambda slug, up, ask: book_depth(slug, up, ask, sess))
    have = set(zip(record["market_slug"].astype(str), record["side"].astype(str),
                   pd.to_numeric(record["threshold"], errors="coerce").round(2), strict=True)) if len(record) else set()
    stamp = _stamp(now)
    rows = []
    prices: dict[str, tuple[float, float]] = {}
    for w in open_:
        if w["metal"] not in prices:
            prices[w["metal"]] = spot(w["metal"])
        s, sigma = prices[w["metal"]]
        up = p_up(s, w["beat"], sigma, w["left"])
        if not math.isfinite(up):
            continue
        for side, p, ask, bid in (("up", up, w["ask"], w["bid"]),
                                  ("down", 1.0 - up, 1.0 - w["bid"], 1.0 - w["ask"])):
            ask, bid = source._round(ask), source._round(bid)
            if not math.isfinite(ask) or not 0 < ask <= CAP + 1e-9:
                continue
            fee = pricing.fee(ask, w["fee_rate"])
            fee = fee if math.isfinite(fee) else 0.0
            for th in THRESHOLDS:
                if p < th or p - ask - fee <= MIN_EDGE or (str(w["market_slug"]), side, round(th, 2)) in have:
                    continue
                if not rows or rows[-1]["market_slug"] != w["market_slug"] or rows[-1]["side"] != side:
                    try:
                        at, under = depth(w["market_slug"], side == "up", ask)
                    except Exception as error:  # noqa: BLE001 - a book not read is a position without its depth
                        LOG.info("metals: no book for a window (%s)", type(error).__name__)
                        at, under = float("nan"), float("nan")
                rows.append({
                    "formed_at": stamp, "metal": w["metal"], "event_slug": w["event_slug"],
                    "market_slug": w["market_slug"], "window_start": _stamp(datetime.fromtimestamp(w["start"], UTC)),
                    "window_end": _stamp(datetime.fromtimestamp(w["end"], UTC)), "seconds_left": round(w["left"], 1),
                    "price_to_beat": w["beat"], "spot": s, "sigma": sigma, "p_side": round(p, 5), "threshold": th,
                    "side": side, "long": side == "up", "ask": ask, "bid": bid, "fee_rate": w["fee_rate"], "fee": fee,
                    "cost": ask + fee, "edge": round(p - ask - fee, 5), "shares_at_ask": at, "shares_under_cap": under,
                    "tick": w["tick"], "payout": float("nan"), "won": float("nan"), "profit": float("nan"),
                    "settled_at": None})
    if not rows:
        return record, 0
    new = pd.DataFrame(rows, columns=COLUMNS)
    LOG.info("metals: %d practice positions taken", len(new))
    return (pd.concat([record, new], ignore_index=True) if len(record) else new), len(new)


def grade(record: pd.DataFrame, now: datetime, fetch=None, limit: int = SETTLEMENT_READS) -> tuple[pd.DataFrame, int]:
    """The record with the venue's settlement read for positions whose window has been over :data:`GRADE_AFTER`:
    the payout per contract on the side taken, whether it won, and the profit against the cost."""
    if record.empty or offline():
        return record, 0
    out = record.copy()
    out["settled_at"] = out["settled_at"].astype(object)      # read back all-blank as floats
    ends = pd.to_datetime(out["window_end"], utc=True, errors="coerce")
    pending = out[pd.to_numeric(out["payout"], errors="coerce").isna() & (ends <= pd.Timestamp(now) - GRADE_AFTER)]
    if pending.empty:
        return out, 0
    fetch = fetch or source.settlement
    cache: dict[str, float] = {}
    graded = 0
    for i, x in pending.iterrows():
        slug = str(x["market_slug"])
        if slug not in cache:
            if len(cache) >= limit:
                break
            try:
                cache[slug] = float(fetch(slug))
            except Exception as error:  # noqa: BLE001 - a settlement not read is read next time
                LOG.info("metals: no settlement for a window (%s)", type(error).__name__)
                cache[slug] = float("nan")
        px = cache[slug]
        if not math.isfinite(px):
            continue
        paid = px if favorites._truthy(x["long"]) else 1.0 - px
        out.loc[i, "payout"] = paid
        out.loc[i, "won"] = 1.0 if paid >= 0.999 else 0.0
        out.loc[i, "profit"] = paid - float(x["cost"])
        out.loc[i, "settled_at"] = _stamp(now)
        graded += 1
    return out, graded


def step(store, now: datetime, *, sess=None, events=None, spot=None, depth=None, fetch=None) -> dict:
    """One read: positions taken in any window's final stretch, settled ones graded, the record written.
    Returns what happened. Never raises."""
    if not on() or offline():
        return {"added": 0, "graded": 0}
    try:
        held = store.read(TABLE)
        record, added = take(held, now, events=events, spot=spot, depth=depth, sess=sess)
        record, graded = grade(record, now, fetch=fetch)
        if added or graded or len(record) != len(held):
            store.write(TABLE, record)
        return {"added": int(added), "graded": int(graded)}
    except Exception as error:  # noqa: BLE001 - the type only
        LOG.error("metals not run: %s", type(error).__name__)
        return {"added": 0, "graded": 0}


# ---------------------------------------------------------------------------
# The owner page
# ---------------------------------------------------------------------------


def summary(record: pd.DataFrame, by=("threshold",)) -> pd.DataFrame:
    """Per group: positions taken and settled, losses, the win rate against the break-even (mean cost), the edge
    per contract with a window-clustered standard error, and what a one-dollar order would have made: a dollar's
    worth of contracts at the ask, its fee rounded to the cent (a fee under half a cent is no fee)."""
    cols = [*by, "taken", "settled", "losses", "win_rate", "break_even", "edge", "se", "dollar_orders"]
    if record is None or record.empty:
        return pd.DataFrame(columns=cols)
    from atlas.polymarket import backtest

    rows = []
    for key, g in clean(record).groupby(list(by), sort=True, dropna=False):
        key = key if isinstance(key, tuple) else (key,)
        done = g[pd.to_numeric(g["payout"], errors="coerce").notna()]
        n = len(done)
        won, cost = pd.to_numeric(done["won"], errors="coerce"), pd.to_numeric(done["cost"], errors="coerce")
        ask, rate = pd.to_numeric(done["ask"], errors="coerce"), pd.to_numeric(done["fee_rate"], errors="coerce")
        contracts = 1.0 / ask
        fee = (rate * contracts * ask * (1 - ask)).round(2)
        dollar = float((won * contracts - 1.0 - fee).sum()) if n else float("nan")
        rows.append({**dict(zip(by, key, strict=True)), "taken": int(len(g)), "settled": n,
                     "losses": int((won == 0).sum()), "win_rate": float(won.mean()) if n else float("nan"),
                     "break_even": float(cost.mean()) if n else float("nan"),
                     "edge": float((won - cost).mean()) if n else float("nan"),
                     "se": backtest.cluster_se(won - cost, done["market_slug"]) if n > 1 else float("nan"),
                     "dollar_orders": dollar})
    return pd.DataFrame(rows, columns=cols)


def section(record: pd.DataFrame, now: datetime) -> dict:
    """The owner page's section: the practice record by threshold and by metal, and the latest positions."""
    record = clean(record)
    n = len(record)
    settled = int(pd.to_numeric(record["payout"], errors="coerce").notna().sum()) if n else 0
    tables = []

    def table(s: pd.DataFrame, keys: list[str], title: str) -> dict:
        rows = []
        for x in s.itertuples(index=False):
            rows.append([*[str(getattr(x, k)) for k in keys], f"{x.taken} / {x.settled}", str(x.losses),
                         f"{x.win_rate:.1%}" if x.settled else "", f"{x.break_even:.1%}" if x.settled else "",
                         (f"{100 * x.edge:+.2f} ± {100 * x.se:.2f}" if math.isfinite(x.se) else f"{100 * x.edge:+.2f}")
                         if x.settled else "", f"{x.dollar_orders:+.2f}" if x.settled else ""])
        return {"title": title, "head": [*[k.title() for k in keys], "Taken / settled", "Losses", "Win rate",
                                         "Break-even", "Edge (¢ a contract)", "$1 orders ($)"], "stack": True, "rows": rows}
    if n:
        tables.append(table(summary(record, ("threshold",)), ["threshold"], "By model threshold"))
        tables.append(table(summary(record, ("metal", "threshold")), ["metal", "threshold"], "By metal"))
        latest = record.sort_values("formed_at", kind="stable").tail(25).iloc[::-1]
        rows = []
        for x in latest.itertuples():
            payout = pd.to_numeric(pd.Series([x.payout]), errors="coerce").iloc[0]
            state = "open" if pd.isna(payout) else ("won" if payout >= 0.999 else "lost")
            under = pd.to_numeric(pd.Series([x.shares_under_cap]), errors="coerce").iloc[0]
            rows.append([[f"{x.metal} {str(x.window_end)[11:16]}Z", f"{x.side}, model {float(x.p_side):.3f}"],
                         f"{float(x.threshold):.2f}", f"{float(x.ask):.2f}", f"{float(x.seconds_left):.0f}",
                         f"{under:,.0f}" if pd.notna(under) else "", state])
        tables.append({"title": f"Latest positions ({len(rows)})", "head": ["Window", "Threshold", "Ask",
                                                                             "Seconds left", "Shares ≤ cap", "Result"],
                       "stack": True, "rows": rows})
    return {"title": f"Metals 15m, practice ({settled} of {n} settled)", "tab": TAB, "tables": tables, "notes": [
        f"Paper positions only: nothing is ordered. In each gold and silver 15-minute window's last {FINAL // 60} "
        f"minutes, the side a lognormal on the venue's own Chainlink price puts at or above a threshold, offered at "
        f"or under {CAP:.2f} and beating the ask and fee by more than {MIN_EDGE * 100:.0f}¢, at that ask plus the "
        "fee, graded by the venue's settlement about a minute after the window.",
        "Each threshold is recorded on its own, so a window can count once at each it reached. The research found "
        "+0.8 to +2.9¢ a contract on one trading day and one live loss at 0.95; a single loss at 0.95 costs about "
        "twenty wins, so the edge column needs a few hundred settled windows before it means anything.",
        "$1 orders: what a dollar's worth of contracts at the ask would have made in all, the fee rounded to the cent "
        "as the venue rounds it (under half a cent is nothing)."]}
