"""The audit trail checked against the venue's own record of the account, once a day.

    python -m atlas.polymarket.reconcile                  # yesterday (Eastern), printed; recorded when due
    python -m atlas.polymarket.reconcile --day 2026-11-03 # any day, printed, not recorded

The audit trail (`atlas/polymarket/audit.py`) is what the live step says it
did. Polymarket US keeps its own account history
(``GET /v1/portfolio/activities``): every trade on the account with the
exchange's trade id, market, price, quantity, time and state. Each morning,
from :data:`HOUR` Eastern, the previous Eastern day is reconciled: every
venue trade is matched by its trade id to an execution the trail recorded
in an order's answer (``executions[].tradeId``), and the two are compared.
What does not reconcile:

* ``differ`` - a trade both hold whose quantity or price disagrees;
* ``venue_only`` - a trade on the account the trail never recorded: a trade
  made by hand in the app, or an answer the trail lost;
* ``ours_only`` - a fill the trail recorded that the venue does not show;
* ``busted`` - a trade the venue holds as busted or rejected: undone after
  the answer said it filled.

The same read checks the ledger's grades (`atlas/polymarket/orders.py`).
Each settlement the venue made of the account's positions on the day
(``ACTIVITY_TYPE_POSITION_RESOLUTION``) is set beside the ledger's filled
live orders on that market: the contracts the position held going in
against the contracts the ledger filled, and the payout per contract -
read off the position as the realized profit the settlement added plus the
cost the position carried, over its contracts - against the payout the
ledger graded. What does not reconcile:

* ``settle_differ`` - the contracts or the payout disagree (the venue's own
  record of the position is kept with it);
* ``settled_not_graded`` - the venue settled a market the ledger holds and
  has not graded yet;
* ``graded_not_settled`` - the ledger graded a market on the day that the
  account shows no settlement of (read :data:`LOOKBACK` back, since the
  ledger grades after the venue settles);
* ``settled_not_ours`` - a settlement of a position the ledger does not
  hold: one bought by hand in the app.

The result is an event in the audit trail itself (``kind`` ``reconcile``),
so the trail carries its own checks, and the owner page shows the latest.
A day is reconciled once; a read that fails is recorded and tried again an
hour later. Trades are matched over the day with :data:`MARGIN` either side,
so a fill stamped a few milliseconds apart across midnight still matches,
and only what falls inside the day is reported.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta

import pandas as pd
import requests

from atlas.polymarket import account, audit
from atlas.util import get_logger, offline

LOG = get_logger(__name__)

ACTIVITIES = "/v1/portfolio/activities"
TRADE = "ACTIVITY_TYPE_TRADE"
RESOLUTION = "ACTIVITY_TYPE_POSITION_RESOLUTION"
#: Each activity type's record inside the activity, and the time it is read by.
KINDS = {TRADE: ("trade", "createTime"), RESOLUTION: ("positionResolution", "updateTime")}
#: Settlements are read this far before the day as well: the ledger grades a market after the venue settles
#: it, so a market graded on the day may have settled the day before.
LOOKBACK = timedelta(days=3)
#: A payout per contract agrees within this: the venue's realized figures are to the cent.
PAYOUT_TOLERANCE = 0.01
UNDONE = ("TRADE_STATE_BUSTED", "TRADE_STATE_REJECTED")
EASTERN = "America/New_York"
#: The Eastern hour from which the previous day is reconciled: the night's games are over and settled.
HOUR = 6
#: Matched over the day with this either side; reported only inside it.
MARGIN = timedelta(minutes=10)
#: A failed read is tried again after this.
RETRY = timedelta(hours=1)
PAGE = 100
#: At most this many pages a read: ten thousand trades a day is not this account.
PAGES = 100
#: Quantities and prices agree within this.
TOLERANCE = 1e-6


def window(day: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    """The Eastern day, as UTC times: its midnight to the next."""
    midnight = pd.Timestamp(day).normalize()
    start, end = (t.tz_localize(EASTERN) for t in (midnight, midnight + pd.Timedelta(days=1)))
    return start.tz_convert("UTC"), end.tz_convert("UTC")                 # 23 or 25 hours when the clocks change


def yesterday(now: datetime) -> str:
    local = pd.Timestamp(now).tz_convert(EASTERN)
    return (local - pd.Timedelta(days=1)).strftime("%Y-%m-%d")


def _num(value) -> float:
    if isinstance(value, dict):
        value = value.get("value")
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def _time(value) -> pd.Timestamp:
    return pd.to_datetime(value, utc=True, errors="coerce")


# ---------------------------------------------------------------------------
# The two sides
# ---------------------------------------------------------------------------


def fetch(signer: account.Signer, start, end, sess: requests.Session | None = None, kind: str = TRADE) -> list[dict]:
    """The account's activities of ``kind`` (trades, or settlements: :data:`KINDS`) from ``start`` to ``end``,
    newest first, read page by page until the pages pass ``start``. The signature covers the path alone, the
    query sent beside it (as the venue's own client does)."""
    sess = sess or requests.Session()
    field, when = KINDS[kind]
    out: list[dict] = []
    cursor = None
    for _ in range(PAGES):
        params: list[tuple[str, str]] = [("limit", str(PAGE)), ("types", kind), ("sortOrder", "SORT_ORDER_DESCENDING")]
        if cursor:
            params.append(("cursor", cursor))
        r = sess.get(account.API + ACTIVITIES, params=params, headers=signer.headers("GET", ACTIVITIES),
                     timeout=account.TIMEOUT)
        r.raise_for_status()
        page = r.json() or {}
        trades = [a.get(field) or {} for a in page.get("activities") or [] if a.get("type") == kind]
        out.extend(t for t in trades if start <= _time(t.get(when)) < end)
        oldest = min((_time(t.get(when)) for t in trades), default=pd.NaT)
        cursor = page.get("nextCursor")
        if page.get("eof") or not cursor or not trades or (pd.notna(oldest) and oldest < start):
            return out
    LOG.warning("reconcile: stopped after %d pages; the day may be read in part", PAGES)
    return out


def venue(trades: list[dict]) -> pd.DataFrame:
    """The venue's trades, a row each: id, market, time, quantity, price, whether the account took, state."""
    rows = [{"trade_id": str(t.get("id") or ""), "market_slug": t.get("marketSlug"), "at": _time(t.get("createTime")),
             "qty": _num(t.get("qtyDecimal") if t.get("qtyDecimal") is not None else t.get("qty")),
             "price": _num(t.get("price")), "aggressor": t.get("isAggressor"), "state": str(t.get("state") or "")}
            for t in trades]
    return pd.DataFrame(rows, columns=["trade_id", "market_slug", "at", "qty", "price", "aggressor", "state"])


def ours(trail: pd.DataFrame, start, end) -> pd.DataFrame:
    """The fills the trail recorded from ``start`` to ``end``: each execution with a trade id in the answer to a
    live order, with its order id and position."""
    cols = ["trade_id", "order_id", "position_id", "market_slug", "at", "qty", "price"]
    if trail is None or trail.empty or "kind" not in trail:
        return pd.DataFrame(columns=cols)
    t = trail.reindex(columns=[*trail.columns.union(["mode", "ok"], sort=False)])
    answers = t[(t["kind"] == "response") & (t["mode"] == "live") & t["ok"].map(lambda v: v is True)]
    rows = []
    for x in answers.to_dict("records"):
        response = x.get("response") or {}
        for e in response.get("executions") or [] if isinstance(response, dict) else []:
            if not e.get("tradeId"):
                continue
            at = _time(e.get("transactTime") or x.get("at"))
            if pd.isna(at) or not start <= at < end:
                continue
            rows.append({"trade_id": str(e["tradeId"]), "order_id": response.get("id"), "position_id": x.get("position_id"),
                         "market_slug": x.get("market_slug"), "at": at, "qty": _num(e.get("lastShares")),
                         "price": _num(e.get("lastPx"))})
    return pd.DataFrame(rows, columns=cols)


# ---------------------------------------------------------------------------
# The comparison
# ---------------------------------------------------------------------------


def _brief(row: dict, keys) -> dict:
    return {k: (row[k].isoformat() if isinstance(row.get(k), pd.Timestamp) else row.get(k)) for k in keys}


def compare(theirs: pd.DataFrame, mine: pd.DataFrame, day: str) -> dict:
    """The day reconciled: counts, and every trade that does not reconcile, by kind. ``ok`` when none."""
    start, end = window(day)
    inside = lambda frame: frame[(frame["at"] >= start) & (frame["at"] < end)]  # noqa: E731
    v = theirs.drop_duplicates("trade_id").set_index("trade_id", drop=False)
    o = mine.drop_duplicates("trade_id").set_index("trade_id", drop=False)
    both = v.index.intersection(o.index)
    differ, busted = [], []
    for t in both:
        a, b = v.loc[t], o.loc[t]
        if a["state"] in UNDONE:
            busted.append({**_brief(a.to_dict(), ("trade_id", "market_slug", "at", "state")), "order_id": b["order_id"]})
        for field in ("qty", "price"):
            if not abs(float(a[field]) - float(b[field])) <= TOLERANCE:
                differ.append({"trade_id": t, "field": field, "venue": float(a[field]), "ours": float(b[field]),
                               "order_id": b["order_id"]})
    venue_only = inside(v[~v.index.isin(both)])
    ours_only = inside(o[~o.index.isin(both)])
    busted += [_brief(r, ("trade_id", "market_slug", "at", "state")) for r in
               venue_only[venue_only["state"].isin(UNDONE)].to_dict("records")]
    venue_only = venue_only[~venue_only["state"].isin(UNDONE)]
    keys = ("trade_id", "market_slug", "at", "qty", "price")
    result = {"day": day, "venue": int(len(inside(v))), "ours": int(len(inside(o))), "matched": int(len(both)),
              "differ": differ,
              "venue_only": [{**_brief(r, keys), "aggressor": r.get("aggressor")} for r in venue_only.to_dict("records")],
              "ours_only": [{**_brief(r, keys), "order_id": r.get("order_id"), "position_id": r.get("position_id")}
                            for r in ours_only.to_dict("records")],
              "busted": busted}
    result["ok"] = not (result["differ"] or result["venue_only"] or result["ours_only"] or result["busted"])
    return result


# ---------------------------------------------------------------------------
# Settlements: the venue's against the ledger's
# ---------------------------------------------------------------------------


def settlements(records: list[dict]) -> pd.DataFrame:
    """The venue's settlements of the account's positions, a row each: the market, when, the contracts held
    going in (the position's size, its sign set aside), and the payout per contract, read off the position as
    (realized profit added at settlement + the cost the position carried) / contracts - the side held either
    way, since what a contract paid is what was realized on it over what it cost."""
    rows = []
    for r in records:
        before, after = r.get("beforePosition") or {}, r.get("afterPosition") or {}
        held = before.get("netPositionDecimal") if before.get("netPositionDecimal") is not None \
            else before.get("netPosition")
        qty = abs(_num(held))
        paid = _num(after.get("realized")) - _num(before.get("realized")) + _num(before.get("cost"))
        rows.append({"market_slug": r.get("marketSlug"), "at": _time(r.get("updateTime")), "qty": qty,
                     "payout": paid / qty if qty > 0 else float("nan"), "side": r.get("side"),
                     "trade_id": r.get("tradeId"), "raw": r})
    return pd.DataFrame(rows, columns=["market_slug", "at", "qty", "payout", "side", "trade_id", "raw"])


def held(ledger: pd.DataFrame) -> pd.DataFrame:
    """The ledger's filled live orders, a row per market: the contracts filled, the payout per contract the
    ledger graded (nan while ungraded; the first, where its orders disagree), when it was graded, the orders."""
    cols = ["market_slug", "qty", "payout", "graded_at", "order_ids", "payouts"]
    if ledger is None or ledger.empty:
        return pd.DataFrame(columns=cols)
    filled = pd.to_numeric(ledger["filled"], errors="coerce")
    live = ledger[(ledger["mode"].astype(str) == "live") & (filled > 0)].copy()
    if live.empty:
        return pd.DataFrame(columns=cols)
    live["filled"] = pd.to_numeric(live["filled"], errors="coerce")
    live["payout"] = pd.to_numeric(live["payout"], errors="coerce")
    live["graded"] = pd.to_datetime(live["graded_at"], utc=True, errors="coerce")
    rows = []
    for slug, g in live.groupby(live["market_slug"].astype(str), sort=True):
        payouts = sorted(set(g["payout"].dropna().round(6)))
        rows.append({"market_slug": slug, "qty": float(g["filled"].sum()),
                     "payout": payouts[0] if payouts and g["payout"].notna().all() else float("nan"),
                     "graded_at": g["graded"].max() if g["graded"].notna().all() else pd.NaT,
                     "order_ids": [str(o) for o in g["order_id"] if str(o)], "payouts": payouts})
    return pd.DataFrame(rows, columns=cols)


def settle(theirs: pd.DataFrame, ledger: pd.DataFrame, day: str) -> dict:
    """The day's settlements reconciled against the ledger: each settlement the venue made on the day, by
    market, beside the ledger's orders there, and each market the ledger graded on the day beside the venue's
    settlement of it (read back :data:`LOOKBACK`). ``settle_ok`` when nothing is named."""
    start, end = window(day)
    mine = held(ledger).set_index("market_slug", drop=False)
    on_day = theirs[(theirs["at"] >= start) & (theirs["at"] < end)].drop_duplicates("market_slug", keep="last")
    differ, not_graded, not_ours = [], [], []
    for r in on_day.to_dict("records"):
        slug = r["market_slug"]
        brief = {"market_slug": slug, "at": _brief(r, ("at",))["at"], "venue_qty": r["qty"],
                 "venue_payout": None if pd.isna(r["payout"]) else round(float(r["payout"]), 6)}
        if slug not in mine.index:
            not_ours.append(brief)
            continue
        m = mine.loc[slug]
        if pd.isna(m["payout"]):
            not_graded.append({**brief, "order_ids": m["order_ids"]})
            continue
        if not abs(float(r["qty"]) - float(m["qty"])) <= TOLERANCE:
            differ.append({**brief, "field": "qty", "ledger": float(m["qty"]), "order_ids": m["order_ids"]})
        if len(m["payouts"]) > 1 or not abs(float(r["payout"]) - float(m["payout"])) <= PAYOUT_TOLERANCE:
            differ.append({**brief, "field": "payout", "ledger": m["payouts"], "order_ids": m["order_ids"],
                           "venue_record": r["raw"]})
    settled = set(theirs["market_slug"])
    graded = mine[(mine["graded_at"] >= start) & (mine["graded_at"] < end)] if len(mine) else mine
    not_settled = [{"market_slug": g["market_slug"], "graded_at": g["graded_at"].isoformat(),
                    "ledger_payout": g["payout"], "order_ids": g["order_ids"]}
                   for g in graded.to_dict("records") if g["market_slug"] not in settled]
    out = {"settled": int(len(on_day)), "settled_matched": int(len(on_day)) - len(not_ours) - len(not_graded),
           "settle_differ": differ, "settled_not_graded": not_graded, "graded_not_settled": not_settled,
           "settled_not_ours": not_ours}
    out["settle_ok"] = not (differ or not_graded or not_settled or not_ours)
    return out


#: What does not reconcile, by kind, in the words the owner page uses.
NAMED = (("differ", "trades differ in quantity or price"), ("venue_only", "trades on the account and not in the trail"),
         ("ours_only", "fills in the trail and not on the account"), ("busted", "trades busted or rejected by the venue"),
         ("settle_differ", "settlements differ from the ledger in contracts or payout"),
         ("settled_not_graded", "settled by the venue and not yet graded in the ledger"),
         ("graded_not_settled", "graded in the ledger with no settlement on the account"),
         ("settled_not_ours", "settlements of positions the ledger does not hold"))


def describe(result: dict | None) -> str:
    """One line for the owner page and the log."""
    if not result:
        return "Not reconciled against the venue's account activity yet."
    if result.get("error"):
        return f"Reconciling {result['day']} failed ({result['error']}); it is tried again within the hour."
    head = (f"Reconciled {result['day']} against the venue's account activity: {result['venue']} trades on the "
            f"account, {result['ours']} in the audit trail, {result['matched']} matched")
    if "settled" in result:
        head += f"; {result['settled']} settlements, {result['settled_matched']} beside the ledger"
    if result.get("ok"):
        return head + "; everything agrees."
    parts = [f"{len(result[k])} {label}" for k, label in NAMED if result.get(k)]
    return head + ". MISMATCH: " + ", ".join(parts) + "."


# ---------------------------------------------------------------------------
# Once a day
# ---------------------------------------------------------------------------


def latest(trail: pd.DataFrame, day: str | None = None) -> dict | None:
    """The latest reconcile event in the trail (for ``day``, when given), or None."""
    if trail is None or trail.empty or "kind" not in trail:
        return None
    r = trail[trail["kind"] == "reconcile"]
    if day is not None and "day" in r:
        r = r[r["day"] == day]
    return r.sort_values("at", kind="stable").iloc[-1].to_dict() if len(r) else None


def due(trail: pd.DataFrame, now: datetime) -> str | None:
    """The day to reconcile now: yesterday, once it is :data:`HOUR` Eastern, unless the trail already holds
    its result or a failed read of it within :data:`RETRY`; None otherwise."""
    if pd.Timestamp(now).tz_convert(EASTERN).hour < HOUR:
        return None
    day = yesterday(now)
    last = latest(trail, day)
    if last is None:
        return day
    if last.get("error") and pd.Timestamp(now) - _time(last.get("at")) >= RETRY:
        return day
    return None


def check(day: str, trail: pd.DataFrame, signer: account.Signer, sess: requests.Session | None = None,
          fetch_=None, ledger: pd.DataFrame | None = None) -> dict:
    """``day`` reconciled: the venue's trades read over the day and its margins, set beside the trail's fills;
    and, given the ``ledger``, its settlements read back :data:`LOOKBACK` as well, set beside the ledger's."""
    start, end = window(day)
    read = fetch_ or fetch
    theirs = venue(read(signer, start - MARGIN, end + MARGIN, sess, kind=TRADE))
    result = compare(theirs, ours(trail, start - MARGIN, end + MARGIN), day)
    if ledger is not None:
        result.update(settle(settlements(read(signer, start - LOOKBACK, end + MARGIN, sess, kind=RESOLUTION)),
                             ledger, day))
        result["ok"] = bool(result["ok"] and result["settle_ok"])
    return result


def daily(passphrase: str, now: datetime, *, signer: account.Signer | None = None,
          sess: requests.Session | None = None, where=None, ledger_where=None, fetch_=None) -> dict | None:
    """The previous Eastern day reconciled when :func:`due` - trades against the trail, settlements against the
    ledger (`atlas/polymarket/orders.py`) - its result recorded in the trail; the result, or None when nothing
    was due (or there is no key). Never raises."""
    from atlas.polymarket import orders

    if offline() or not passphrase:
        return None
    signer = signer or account.Signer.from_env()
    if signer is None:
        return None
    try:
        trail_ = audit.load(passphrase, where)
        day = due(trail_, now)
        if day is None:
            return None
        # Stamped at the run's own time, the one :func:`due` measures the retry from.
        trail = audit.Trail(passphrase, where, mode="reconcile", rule="", clock=lambda: now)
        sent = trail.now()
        try:
            result = check(day, trail_, signer, sess, fetch_, ledger=orders.load(passphrase, ledger_where))
            trail.add("reconcile", path=ACTIVITIES, sent_at=sent, **result)
        except Exception as error:  # noqa: BLE001 - the type only; the body could quote the account
            result = {"day": day, "error": type(error).__name__}
            trail.add("reconcile", path=ACTIVITIES, sent_at=sent, ok=False, **result, **{
                k: v for k, v in audit.failure(error).items() if k not in ("ok", "error")})
        trail.flush()
    except Exception as error:  # noqa: BLE001 - a reconciliation never stops the run
        LOG.error("reconcile: not run (%s)", type(error).__name__)
        return None
    (LOG.info if result.get("ok") else LOG.warning)("reconcile: %s", describe(result))
    return result


def main() -> None:
    from datetime import UTC

    from atlas.owner import crypto

    ap = argparse.ArgumentParser(description="The audit trail reconciled against the venue's account activity")
    ap.add_argument("--day", help="an Eastern day, YYYY-MM-DD; printed, not recorded")
    args = ap.parse_args()
    import os

    passphrase = os.environ.get(crypto.SECRET, "").strip()
    signer = account.Signer.from_env()
    if not passphrase or signer is None:
        raise SystemExit(f"reconcile: set {crypto.SECRET}, {account.KEY_ID} and {account.SECRET_KEY}")
    now = datetime.now(UTC)
    if args.day:
        from atlas.polymarket import orders

        result = check(args.day, audit.load(passphrase), signer, ledger=orders.load(passphrase))
    else:
        result = daily(passphrase, now, signer=signer) or latest(audit.load(passphrase), yesterday(now))
    print(describe(result))
    if result:
        print(json.dumps({k: result[k] for k, _ in NAMED if k in result}, indent=2, default=str))


if __name__ == "__main__":
    main()
