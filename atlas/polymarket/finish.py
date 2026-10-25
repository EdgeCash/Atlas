"""The finish-line rule: buy the decided side between the final whistle and the venue's settlement.

When a game is over, its winner's contract will pay a dollar, but the venue
settles it some minutes later, and until then some holders sell it for 98 or
99 cents to have their money back. The venue's own tape showed that ask in
43% of 8,016 settled games, with the loser priced as the winner after the
finish in 4 of 9,273 (``reports/Polymarket US worker edge survey.md``). At
those prices the taker fee is a tenth of a cent, so the cent or two left is
the one gap on this venue a slow taker can collect after the fee.

This module takes paper positions only; orders go through the live step
(`atlas/polymarket/orders.py`) under the rule name ``finish`` and nothing is
sent unless its secrets say so and ``LIVE_RULES`` names the rule.

* **Final.** The venue says the game is over: the event's ``ended`` flag, or
  its period reading full time (``FT``). End of regulation (``End P3``,
  ``End Q4``) is not final: a tied game goes on.
* **Position.** The side whose ask sits between :data:`FLOOR` and
  :data:`CEILING` on a market still accepting orders, once per contract, at
  that ask plus the fee, with the depth behind it read from the book. The
  paper record keeps the wider band so the record can say which prices pay;
  only a position the market itself calls decided (:func:`decided`: the
  ask at or under 99 cents and the bid at or over 98) goes to the live step.
* **Grade.** Every tick reads the settlement of the open positions, so the
  record carries the payout, the profit against the cost, and the minutes
  from the position to the settlement - the capital lock the research could
  not measure.

The record is ``tracking/finish.csv``, in the clear: a rule on public prices.
The always-on worker (`atlas/polymarket/worker.py`) runs it; the scheduled
runs only show it on the owner page.
"""

from __future__ import annotations

import math
from datetime import datetime

import pandas as pd

from atlas.polymarket import favorites, pricing, source
from atlas.util import get_logger, offline

LOG = get_logger(__name__)

TABLE = "finish"
TAB = "Finish line"
#: The band of asks a paper position is taken in, and the stricter one the live step takes.
FLOOR = 0.90
CEILING = 0.99
DECIDED_ASK = 0.99
DECIDED_BID = 0.98
#: The venue's period strings that mean the game is over. "End P3" and "End Q4" are not among them.
FINAL_PERIODS = frozenset({"FT", "VFT", "F", "FINAL", "F/OT", "FT/OT", "AOT", "AET", "FINAL/OT"})
#: Settlement reads per tick, over the open positions.
SETTLEMENT_READS = 20
COLUMNS = ["formed_at", "sport", "game_id", "event_id", "event_slug", "game_start", "label", "side", "long",
           "market_slug", "token_id", "ask", "bid", "spread", "ask_shares", "fee_rate", "fee", "cost", "decided",
           "period", "score", "finished_at", "minutes_after_finish", "payout", "won", "profit", "settled_at",
           "minutes_to_settle"]
GRADED = ("payout", "won", "profit", "settled_at", "minutes_to_settle")


def _truthy(value) -> bool:
    return str(value).strip().lower() in ("true", "1", "1.0", "yes")


def _stamp(now: datetime) -> str:
    t = pd.Timestamp(now)
    t = t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")
    return t.replace(microsecond=0).isoformat()


def venue_final(stub: dict) -> bool:
    """Whether the venue says the game is over: its ended flag, or its period reading full time."""
    if stub.get("ended") is True or _truthy(stub.get("ended")):
        return True
    return str(stub.get("period") or "").strip().upper() in FINAL_PERIODS


def finals(events: dict[str, list[dict]]) -> dict[str, dict]:
    """The events the venue says are over, by event id, with their period, score and finish time."""
    out = {}
    for stubs in (events or {}).values():
        for e in stubs or []:
            if venue_final(e):
                out[str(e.get("id"))] = {"period": str(e.get("period") or ""), "score": str(e.get("score") or ""),
                                         "finished_at": e.get("finishedTimestamp") or None}
    return out


def decided(ask, bid) -> bool:
    """The market calls the side decided: an ask at or under 99 cents with a bid at or over 98."""
    try:
        a, b = float(ask), float(bid)
    except (TypeError, ValueError):
        return False
    return math.isfinite(a) and math.isfinite(b) and a <= DECIDED_ASK + 1e-9 and b >= DECIDED_BID - 1e-9


def clean(record: pd.DataFrame | None, *, quiet: bool = False) -> pd.DataFrame:
    """The record as positions: lines that are not one dropped, ids as text, one row per contract - the
    first taken, with whichever copy's grade. ``quiet`` when the input is several copies laid together."""
    if record is None or record.empty:
        return pd.DataFrame(columns=COLUMNS)
    r = record.reindex(columns=COLUMNS).copy()
    for c in ("token_id", "game_id", "event_id"):
        r[c] = r[c].map(favorites.ident).astype(object)
    when = pd.to_datetime(r["formed_at"], utc=True, errors="coerce", format="ISO8601")
    keep = when.notna() & r["token_id"].notna()
    r = r[keep].assign(_t=when[keep]).sort_values("_t", kind="stable")
    if r.duplicated("token_id").any():
        if not quiet:
            LOG.warning("finish: %d positions held twice; one kept", int(r.duplicated("token_id").sum()))
        first = r.drop_duplicates("token_id", keep="first").set_index("token_id")
        graded = r[pd.to_numeric(r["payout"], errors="coerce").notna()].drop_duplicates("token_id").set_index("token_id")
        for c in GRADED:
            first[c] = first[c].astype(object)
            first.loc[graded.index, c] = graded[c].astype(object)
        r = first.reset_index()
    return r.drop(columns="_t", errors="ignore").reindex(columns=COLUMNS).reset_index(drop=True)


def merge(*records: pd.DataFrame) -> pd.DataFrame:
    """Several copies of the record as one: every position any of them holds, once."""
    parts = [r.reindex(columns=COLUMNS) for r in records if r is not None and len(r)]
    return clean(pd.concat(parts, ignore_index=True) if parts else None, quiet=True)


def take(record: pd.DataFrame, quotes: pd.DataFrame, events: dict[str, list[dict]], now: datetime,
         depth=None) -> tuple[pd.DataFrame, int]:
    """The record with a position on each side of a finished game whose ask sits in the band, once per
    contract, at that ask plus the fee; ``depth(market_slug, long)`` reads the shares behind the ask
    (:func:`source.depth`; none offline). New positions come at the end."""
    record = clean(record)
    over = finals(events)
    if quotes is None or quotes.empty or not over:
        return record, 0
    q = quotes[quotes["market"].astype(str).eq("moneyline") & quotes["event_id"].astype(str).isin(over)].copy()
    ask = pd.to_numeric(q["ask"], errors="coerce")
    q = q[q["accepting"].map(_truthy) & ask.between(FLOOR - 1e-9, CEILING + 1e-9)]
    have = set(record["token_id"]) if len(record) else set()
    q = q[~q["token_id"].map(favorites.ident).isin(have)]
    if q.empty:
        return record, 0
    if depth is None and not offline():
        depth = source.depth
    stamp = _stamp(now)
    rows = []
    for x in q.itertuples(index=False):
        e = over[str(x.event_id)]
        a, b = float(x.ask), source._num(x.bid)
        rate = source._num(x.fee_rate)
        fee = pricing.fee(a, rate if math.isfinite(rate) else 0.0)
        fee = fee if math.isfinite(fee) else 0.0
        shares = float("nan")
        if depth is not None:
            try:
                shares = float(depth(str(x.market_slug), _truthy(x.long)).get("ask_shares", float("nan")))
            except Exception as error:  # noqa: BLE001 - a book not read is a position without its depth
                LOG.info("finish: no book for a contract (%s)", type(error).__name__)
        finished = pd.to_datetime(e["finished_at"], utc=True, errors="coerce")
        after = (pd.Timestamp(stamp) - finished).total_seconds() / 60.0 if pd.notna(finished) else float("nan")
        rows.append({
            "formed_at": stamp, "sport": x.sport, "game_id": favorites.ident(x.game_id),
            "event_id": str(x.event_id), "event_slug": x.event_slug, "game_start": x.game_start,
            "label": f"{x.away} @ {x.home}", "side": x.side, "long": _truthy(x.long),
            "market_slug": x.market_slug, "token_id": favorites.ident(x.token_id), "ask": a, "bid": b,
            "spread": source._num(x.spread), "ask_shares": shares, "fee_rate": rate, "fee": fee, "cost": a + fee,
            "decided": decided(a, b), "period": e["period"], "score": e["score"],
            "finished_at": finished.isoformat() if pd.notna(finished) else None,
            "minutes_after_finish": round(after, 1) if math.isfinite(after) else float("nan"),
            "payout": float("nan"), "won": float("nan"), "profit": float("nan"), "settled_at": None,
            "minutes_to_settle": float("nan")})
    new = pd.DataFrame(rows, columns=COLUMNS)
    out = pd.concat([record, new], ignore_index=True) if len(record) else new
    LOG.info("finish: %d positions taken (%d decided by the market)", len(new), int(new["decided"].sum()))
    return out, len(new)


def grade(record: pd.DataFrame, now: datetime, fetch=None, limit: int = SETTLEMENT_READS) -> tuple[pd.DataFrame, int]:
    """The record with the venue's settlement read for open positions, at most ``limit`` a tick: the payout
    per contract, whether it won, the profit against the cost, and the minutes from the position to the
    settlement (to the tick that first saw it)."""
    if record.empty or offline():
        return record, 0
    out = record.copy()
    pending = out[pd.to_numeric(out["payout"], errors="coerce").isna()]
    if pending.empty:
        return out, 0
    fetch = fetch or source.settlement
    stamp = _stamp(now)
    graded = 0
    for i, x in pending.head(limit).iterrows():
        try:
            px = float(fetch(str(x["market_slug"])))
        except Exception as error:  # noqa: BLE001 - a settlement not read is read next tick
            LOG.info("finish: no settlement for a market (%s)", type(error).__name__)
            continue
        if not math.isfinite(px):
            continue
        paid = px if _truthy(x["long"]) else 1.0 - px
        formed = pd.to_datetime(x["formed_at"], utc=True, errors="coerce")
        out.loc[i, "payout"] = paid
        out.loc[i, "won"] = 1.0 if paid >= 0.999 else 0.0
        out.loc[i, "profit"] = paid - float(x["cost"])
        out.loc[i, "settled_at"] = stamp
        out.loc[i, "minutes_to_settle"] = round((pd.Timestamp(stamp) - formed).total_seconds() / 60.0, 1) \
            if pd.notna(formed) else float("nan")
        graded += 1
    if graded:
        LOG.info("finish: %d positions settled", graded)
    return out, graded


def as_positions(rows: pd.DataFrame) -> pd.DataFrame:
    """The rule's positions in the shape the live step takes: one order's worth each, the stake the whole
    bankroll so the per-order cap decides the size."""
    from atlas.polymarket import positions

    if rows is None or rows.empty:
        return pd.DataFrame(columns=positions.COLUMNS)
    out = pd.DataFrame({
        "position_id": [f"fin:{favorites.ident(t)}" for t in rows["token_id"]],
        "formed_at": rows["formed_at"], "day": [positions.day_of(t) for t in rows["formed_at"]],
        "year": [positions.iso_week(t)[0] for t in rows["formed_at"]],
        "week": [positions.iso_week(t)[1] for t in rows["formed_at"]],
        "game_id": rows["game_id"], "sport": rows["sport"], "kickoff": rows["game_start"], "label": rows["label"],
        "market": "moneyline", "side": rows["side"], "long": rows["long"], "line": 0.0,
        "token_id": rows["token_id"], "market_slug": rows["market_slug"], "event_slug": rows["event_slug"],
        "ask": rows["ask"], "fee_rate": rows["fee_rate"], "fee": rows["fee"], "cost": rows["cost"], "stake": 1.0,
        "spread": rows["spread"]})
    return out.reindex(columns=positions.COLUMNS)


def order(new: pd.DataFrame, passphrase: str, now: datetime) -> None:
    """The positions just taken that the market calls decided, to the live step, which does nothing unless
    its secrets say so and ``LIVE_RULES`` names this rule."""
    from atlas.polymarket import orders

    if new is None or new.empty or orders.mode() == "off":
        return
    new = new[new["decided"].map(_truthy)]
    if new.empty:
        return
    try:
        orders.place(as_positions(new), passphrase, now, rule="finish")
    except Exception as error:  # noqa: BLE001 - the type only
        LOG.error("finish: live orders not placed: %s", type(error).__name__)


def step(store, quotes: pd.DataFrame, events: dict[str, list[dict]], now: datetime, passphrase: str | None,
         *, depth=None, fetch=None) -> dict:
    """The rule's part of a worker tick: take, grade, write, and hand the decided positions to the live
    step. Returns what happened. Never raises."""
    try:
        held = store.read(TABLE)
        record, added = take(held, quotes, events, now, depth=depth)
        new = record.tail(added) if added else record.iloc[0:0]
        record, graded = grade(record, now, fetch=fetch)
        repaired = len(record) - added != len(held)
        if added or graded or repaired:
            store.write(TABLE, record)
        if added and passphrase:
            order(new, passphrase, now)
        return {"added": int(added), "graded": int(graded) + int(repaired), "open": int(
            pd.to_numeric(record["payout"], errors="coerce").isna().sum()) if len(record) else 0}
    except Exception as error:  # noqa: BLE001 - the type only
        LOG.error("finish not run: %s", type(error).__name__)
        return {"added": 0, "graded": 0, "open": 0}


def pending(events: dict[str, list[dict]]) -> int:
    """Games the venue says are over whose moneyline is still open: the worker keeps its quick pace for
    these, since the rule's window is the minutes between the finish and the settlement."""
    n = 0
    for stubs in (events or {}).values():
        for e in stubs or []:
            if venue_final(e) and any(str(m.get("status") or "") == source.OPEN for m in e.get("markets") or []):
                n += 1
    return n


# ---------------------------------------------------------------------------
# The owner page
# ---------------------------------------------------------------------------


def summary(record: pd.DataFrame, by=("sport",)) -> pd.DataFrame:
    """Per group: positions taken and settled, the win rate, the break-even rate (the mean cost), the edge
    with a game-clustered standard error, the profit per dollar, and the median minutes to settlement."""
    cols = [*by, "taken", "settled", "win_rate", "break_even", "edge", "se", "profit_per_dollar", "minutes_to_settle"]
    if record is None or record.empty:
        return pd.DataFrame(columns=cols)
    from atlas.polymarket import backtest

    r = record.copy()
    rows = []
    for key, g in r.groupby(list(by), sort=True, dropna=False):
        key = key if isinstance(key, tuple) else (key,)
        done = g[pd.to_numeric(g["payout"], errors="coerce").notna()]
        n = len(done)
        won, cost = pd.to_numeric(done["won"], errors="coerce"), pd.to_numeric(done["cost"], errors="coerce")
        rows.append({**dict(zip(by, key, strict=True)), "taken": int(len(g)), "settled": n,
                     "win_rate": float(won.mean()) if n else float("nan"),
                     "break_even": float(cost.mean()) if n else float("nan"),
                     "edge": float((won - cost).mean()) if n else float("nan"),
                     "se": backtest.cluster_se(won - cost, done["event_id"]) if n > 1 else float("nan"),
                     "profit_per_dollar": float(pd.to_numeric(done["profit"]).sum() / cost.sum()) if n and cost.sum() > 0
                     else float("nan"),
                     "minutes_to_settle": float(pd.to_numeric(done["minutes_to_settle"], errors="coerce").median())
                     if n else float("nan")})
    return pd.DataFrame(rows, columns=cols)


def _table(s: pd.DataFrame, keys: list[str], title: str) -> dict:
    rows = []
    for x in s.itertuples(index=False):
        cells = [str(getattr(x, k)).upper() if k == "sport" else ("decided" if getattr(x, k) is True or
                 str(getattr(x, k)) == "True" else "wider band") if k == "decided" else str(getattr(x, k))
                 for k in keys]
        rows.append([*cells, f"{x.taken} / {x.settled}", f"{x.win_rate:.1%}" if x.settled else "",
                     f"{x.break_even:.1%}" if x.settled else "",
                     (f"{100 * x.edge:+.2f} ± {100 * x.se:.2f}" if math.isfinite(x.se) else f"{100 * x.edge:+.2f}")
                     if x.settled else "", f"{x.profit_per_dollar:+.2%}" if x.settled else "",
                     f"{x.minutes_to_settle:.0f}" if x.settled and math.isfinite(x.minutes_to_settle) else ""])
    return {"title": title, "head": [*[k.replace("_", " ").title() for k in keys], "Taken / settled", "Win rate",
                                     "Break-even", "Edge (pts)", "Profit per $", "Minutes to settle"],
            "stack": True, "rows": rows}


def section(record: pd.DataFrame, now: datetime) -> dict:
    """The owner page's section: the rule's record by sport and by price band, and the latest positions."""
    record = clean(record)
    n = len(record)
    settled = int(pd.to_numeric(record["payout"], errors="coerce").notna().sum()) if n else 0
    tables = []
    if n:
        tables.append(_table(summary(record, by=("sport",)), ["sport"], "By sport"))
        tables.append(_table(summary(record, by=("decided",)), ["decided"],
                             "Decided by the market (ask ≤ 99¢, bid ≥ 98¢) against the wider band"))
        latest = record.sort_values("formed_at", kind="stable").tail(25).iloc[::-1]
        rows = []
        for x in latest.itertuples():
            payout = pd.to_numeric(pd.Series([x.payout]), errors="coerce").iloc[0]
            state = "open" if pd.isna(payout) else ("won" if payout >= 0.999 else ("lost" if payout <= 0.001
                                                                                   else f"settled {payout:.2f}"))
            after = pd.to_numeric(pd.Series([x.minutes_after_finish]), errors="coerce").iloc[0]
            shares = pd.to_numeric(pd.Series([x.ask_shares]), errors="coerce").iloc[0]
            rows.append([[str(x.label), str(x.sport).upper()], str(x.side), f"{float(x.ask):.3f}",
                         f"{shares:,.0f}" if pd.notna(shares) else "", f"{after:.1f}" if pd.notna(after) else "", state])
        tables.append({"title": f"Latest positions ({len(rows)})", "head": ["Game", "Side", "Ask", "Shares at the ask",
                                                                             "Minutes after the finish", "Result"],
                       "stack": True, "rows": rows})
    return {"title": f"Finish line: the decided side before settlement ({settled} of {n} settled)", "tab": TAB,
            "tables": tables, "notes": [
        "A paper position on the side of a finished game whose ask sits between 90 and 99 cents, at that ask plus "
        "the fee, graded by the venue's settlement. The research behind it (reports/Polymarket US worker edge "
        "survey.md) found such an ask after the finish in 43% of settled games, with the loser priced as the "
        "winner in 4 of 9,273.",
        "Only positions the market calls decided (ask at or under 99 cents, bid at or over 98) go to the live step, "
        "and only when LIVE_RULES names the rule (finish). Minutes to settle is the capital lock: from the position "
        "to the first tick that saw the settlement.",
        "At these prices a cent of profit is the whole edge and one loss erases fifty to a hundred wins: the edge "
        "column needs hundreds of settled positions before it means anything."]}
