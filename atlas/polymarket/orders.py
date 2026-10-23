"""Live orders on Polymarket US, armed off.

The one module that can place an order, and it will not until three things
hold at once: the mode secret says ``live``, the arming secret carries the
exact phrase :data:`PHRASE`, and the ledger's loss stop is not in force.
Without the mode secret the step does nothing at all; with it set to ``dry``
the step walks the whole path - the sizing, the caps, the stop, the venue's
own preview of the order - and writes what it would have sent to the ledger
without sending it. That is the state this ships in.

What it orders is what the paper rule chose: as the day's positions are
logged (`atlas/polymarket/positions.py`), each becomes a limit order at the
ask it was logged at, immediate-or-cancel, for the stake's worth of
contracts at the live bankroll (``ATLAS_LIVE_BANKROLL``, dollars). Never a
market order, never a resting one. Each order is checked against the caps
before it goes - dollars per order, dollars per day, dollars open across
unsettled positions - and against the stop: when the orders settled over
the trailing :data:`LOSS_WINDOW_DAYS` days have lost more than
:data:`LOSS_STOP_DOLLARS`, nothing is placed until that window clears. The
caps and the stop are constants here, overridable by environment for the
owner, never widened by anything the venue or the market says.

Every order, sent or not, is a row in the ledger, sealed with the owner
key beside the positions record (``tracking/polymarket_live/``): the order
id, the state, what filled at what price and fee, and later the settlement
and the profit. The owner page sums it. A failure marks its row and never
fails the run.
"""

from __future__ import annotations

import json
import math
import os
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import requests

from atlas import config
from atlas.owner import sealed
from atlas.polymarket import account, source
from atlas.util import get_logger, offline

LOG = get_logger(__name__)

#: ``off`` (unset), ``dry`` or ``live``.
MODE = "POLYMARKET_US_LIVE"
#: For ``live``, this secret must carry :data:`PHRASE` exactly.
ARMED = "POLYMARKET_US_ARMED"
PHRASE = "place real orders on polymarket us"
#: The bankroll the stakes are sized against, in dollars; none, and nothing is sized.
BANKROLL = "ATLAS_LIVE_BANKROLL"
#: The only path this module may call to place an order.
ORDERS = "/v1/orders"
#: The caps, in dollars, and the stop's window in days. Environment overrides for the owner.
CAPS = {"MAX_ORDER_DOLLARS": 25.0, "MAX_DAY_DOLLARS": 100.0, "MAX_OPEN_DOLLARS": 250.0, "LOSS_STOP_DOLLARS": 50.0}
LOSS_WINDOW_DAYS = 3
SETTLEMENT_READS = 20
BLOCK_SECONDS = "10"
COLUMNS = ["order_id", "placed_at", "mode", "day", "year", "week", "position_id", "sport", "game_id", "kickoff",
           "label", "market", "side", "long", "line", "market_slug", "token_id", "ask", "price", "quantity", "cost",
           "state", "filled", "avg_px", "fee", "paid", "payout", "profit", "graded_at", "note"]
TAB = "Live"


def mode() -> str:
    value = os.environ.get(MODE, "").strip().lower()
    return value if value in ("dry", "live") else "off"


def armed() -> bool:
    """Live, and the arming secret carries the phrase exactly."""
    return mode() == "live" and os.environ.get(ARMED, "") == PHRASE


def caps() -> dict[str, float]:
    out = {}
    for name, default in CAPS.items():
        try:
            out[name] = float(os.environ.get(name, default))
        except ValueError:
            out[name] = default
    return out


def bankroll() -> float:
    try:
        return max(0.0, float(os.environ.get(BANKROLL, "0") or 0.0))
    except ValueError:
        return 0.0


def path() -> Path:
    return config.paths().root / "tracking" / "polymarket_live"


def load(passphrase: str, where: Path | None = None) -> pd.DataFrame:
    rows = sealed.load(where or path(), passphrase)
    return pd.DataFrame(rows, columns=COLUMNS) if rows else pd.DataFrame(columns=COLUMNS)


def seal(ledger: pd.DataFrame, passphrase: str, weeks: set, where: Path | None = None) -> list[Path]:
    where = where or path()
    out = []
    for year, week in sorted(weeks):
        part = ledger[(pd.to_numeric(ledger["year"]) == year) & (pd.to_numeric(ledger["week"]) == week)]
        rows = json.loads(part.reindex(columns=COLUMNS).to_json(orient="records"))
        out.append(sealed.seal(rows, passphrase, sealed.week_file(where, year, week),
                               names=[r.get("label") for r in rows]))
    return out


# ---------------------------------------------------------------------------
# The ledger's arithmetic: what is open, what the day has spent, what the window has lost
# ---------------------------------------------------------------------------


def _num(series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def open_dollars(ledger: pd.DataFrame) -> float:
    """What is paid and not yet settled."""
    if ledger.empty:
        return 0.0
    paid, payout, filled = _num(ledger["paid"]), _num(ledger["payout"]), _num(ledger["filled"])
    sent = ledger["mode"].astype(str) == "live"
    return float(paid[sent & (filled > 0) & payout.isna()].sum())


def day_dollars(ledger: pd.DataFrame, day: str) -> float:
    """What the day's sent orders cost at the ask, filled or not (the cap is on what was risked)."""
    if ledger.empty:
        return 0.0
    sent = (ledger["mode"].astype(str) == "live") & (ledger["day"].astype(str) == str(day))
    return float(_num(ledger["cost"])[sent].sum())


def window_profit(ledger: pd.DataFrame, now: datetime, days: int = LOSS_WINDOW_DAYS) -> float:
    """The realised profit of the orders settled in the trailing window; a loss is negative."""
    if ledger.empty:
        return 0.0
    graded = pd.to_datetime(ledger["graded_at"], utc=True, errors="coerce")
    since = pd.Timestamp(now) - timedelta(days=days)
    sent = ledger["mode"].astype(str) == "live"
    return float(_num(ledger["profit"])[sent & graded.notna() & (graded >= since)].sum())


def stopped(ledger: pd.DataFrame, now: datetime) -> str | None:
    """The loss stop, in force when the window has lost more than the cap: the reason, or None."""
    lost = -window_profit(ledger, now)
    cap = caps()["LOSS_STOP_DOLLARS"]
    if lost > cap:
        return f"stop:loss ${lost:.2f} over {LOSS_WINDOW_DAYS} days exceeds ${cap:.0f}"
    return None


def check(cost: float, ledger: pd.DataFrame, day: str, now: datetime) -> str | None:
    """Why an order of ``cost`` dollars may not go: a cap or the stop; None when it may."""
    c = caps()
    if cost > c["MAX_ORDER_DOLLARS"]:
        return f"cap:order ${cost:.2f} exceeds ${c['MAX_ORDER_DOLLARS']:.0f}"
    if day_dollars(ledger, day) + cost > c["MAX_DAY_DOLLARS"]:
        return f"cap:day ${day_dollars(ledger, day) + cost:.2f} exceeds ${c['MAX_DAY_DOLLARS']:.0f}"
    if open_dollars(ledger) + cost > c["MAX_OPEN_DOLLARS"]:
        return f"cap:open ${open_dollars(ledger) + cost:.2f} exceeds ${c['MAX_OPEN_DOLLARS']:.0f}"
    return stopped(ledger, now)


# ---------------------------------------------------------------------------
# The order
# ---------------------------------------------------------------------------


def order(row, qty: float) -> dict:
    """The paper position as an order: :func:`atlas.polymarket.account.order` (a limit at the ask,
    immediate-or-cancel), held until it fills or cancels so the answer comes back in the response."""
    return {**account.order(row, qty), "synchronousExecution": True, "maxBlockTime": BLOCK_SECONDS}


def post_order(body: dict, signer: account.Signer, sess: requests.Session | None = None,
               path_: str = ORDERS) -> dict:
    """Place the order. Refuses any path but :data:`ORDERS`, and refuses unless :func:`armed`."""
    if path_ != ORDERS:
        raise ValueError(f"live: {path_} is not the orders path")
    if not armed():
        raise RuntimeError("live: not armed")
    sess = sess or requests.Session()
    r = sess.post(account.API + path_, json=body, headers=signer.headers("POST", path_), timeout=account.TIMEOUT)
    r.raise_for_status()
    return r.json() or {}


def read(response: dict, row, qty: float) -> dict:
    """What the venue said, in the position's own terms."""
    executions = response.get("executions") or []
    filled_order = (executions[-1].get("order") if executions and isinstance(executions[-1], dict) else None) or {}
    long_ = str(row.long).strip().lower() in ("true", "1", "1.0", "yes")
    avg = account._amount(filled_order.get("avgPx"))
    filled = float(filled_order.get("cumQuantity") or 0.0)
    fee = account._amount(filled_order.get("commissionNotionalTotalCollected"))
    px = (avg if long_ else 1.0 - avg) if math.isfinite(avg) and filled > 0 else float("nan")
    state = str(filled_order.get("state") or "").replace("ORDER_STATE_", "").lower()
    if not state:
        state = "sent" if response.get("id") else "unknown"
    elif filled > 0 and filled < qty:
        state = "partial"
    paid = (px * filled + (fee if math.isfinite(fee) else 0.0)) if filled > 0 else 0.0
    return {"order_id": str(response.get("id") or ""), "state": state, "filled": filled, "avg_px": px,
            "fee": fee if math.isfinite(fee) else float("nan"), "paid": paid}


def _stamp(now: datetime) -> str:
    t = pd.Timestamp(now)
    t = t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")
    return t.replace(microsecond=0).isoformat()


def place(positions_: pd.DataFrame, passphrase: str, now: datetime, *, where: Path | None = None,
          signer: account.Signer | None = None, sess: requests.Session | None = None) -> pd.DataFrame:
    """The ledger with an order for each of ``positions_`` (rows of the positions record, just logged):
    sent when live and armed, previewed and written as ``dry`` when dry, nothing when off. Each row says
    what happened; a cap, the stop, or a failure marks it and the rest go on."""
    m = mode()
    if m == "off" or positions_ is None or positions_.empty or offline():
        return pd.DataFrame(columns=COLUMNS)
    ledger = load(passphrase, where)
    signer = signer or account.Signer.from_env()
    sess = sess or requests.Session()
    roll = bankroll()
    stamp = _stamp(now)
    rows = []
    for x in positions_.itertuples(index=False):
        ask = float(x.ask)
        qty = account.quantity(x, roll) if roll > 0 else 0.0
        cost = round(qty * ask, 2)
        row = {**dict.fromkeys(COLUMNS), "order_id": "", "placed_at": stamp, "mode": m, "day": x.day, "year": x.year,
               "week": x.week, "position_id": x.position_id, "sport": x.sport, "game_id": x.game_id,
               "kickoff": x.kickoff, "label": x.label, "market": x.market, "side": x.side, "long": bool(x.long),
               "line": x.line, "market_slug": x.market_slug, "token_id": x.token_id, "ask": ask,
               "price": float(account.order(x, 1.0)["price"]["value"]), "quantity": qty, "cost": cost,
               "state": "", "filled": 0.0, "avg_px": float("nan"), "fee": float("nan"), "paid": 0.0,
               "payout": float("nan"), "profit": float("nan"), "graded_at": None, "note": ""}
        why = "no bankroll" if roll <= 0 else (None if signer else "no key")
        why = why or check(cost, pd.concat([ledger, pd.DataFrame(rows, columns=COLUMNS)], ignore_index=True)
                           if rows else ledger, str(x.day), now)
        if why:
            row["state"], row["note"] = "refused", why
        elif m == "dry":
            try:
                seen = account.read(account.post(account.order(x, qty), signer, sess), x)
                row.update({"state": "dry", "filled": seen["preview_filled"], "avg_px": seen["preview_px"],
                            "fee": seen["preview_fee"], "note": f"preview {seen['preview_state']}"})
            except Exception as error:  # noqa: BLE001 - the type only
                row["state"], row["note"] = "dry", f"preview error:{type(error).__name__}"
        elif not armed():
            row["state"], row["note"] = "refused", "not armed"
        else:
            try:
                row.update(read(post_order(order(x, qty), signer, sess), x, qty))
            except Exception as error:  # noqa: BLE001 - the type only; the body could quote the account
                row["state"], row["note"] = "error", f"error:{type(error).__name__}"
        rows.append(row)
    new = pd.DataFrame(rows, columns=COLUMNS)
    out = pd.concat([ledger, new], ignore_index=True) if len(ledger) else new
    weeks = {(int(y), int(w)) for y, w in new[["year", "week"]].drop_duplicates().itertuples(index=False)}
    seal(out, passphrase, weeks, where)
    sent = int(((new["mode"] == "live") & new["state"].isin(["filled", "partial", "canceled", "sent"])).sum())
    LOG.info("live (%s): %d orders written, %d sent, %d refused", m, len(new), sent,
             int((new["state"] == "refused").sum()))
    return out


def grade(ledger: pd.DataFrame, passphrase: str, now: datetime, *, where: Path | None = None, fetch=None,
          limit: int = SETTLEMENT_READS) -> pd.DataFrame:
    """The ledger with the venue's settlement applied to filled orders whose game has started: the payout
    per contract, and the profit against what was paid. Sealed when anything changed."""
    if ledger.empty or offline():
        return ledger
    out = ledger.copy()
    filled, payout = _num(out["filled"]), _num(out["payout"])
    kick = pd.to_datetime(out["kickoff"], utc=True, errors="coerce")
    pending = out[(filled > 0) & payout.isna() & (kick <= pd.Timestamp(now) - timedelta(hours=4))]
    if pending.empty:
        return out
    fetch = fetch or source.settlement
    cache: dict[str, float] = {}
    weeks: set = set()
    for i, x in pending.iterrows():
        slug = str(x["market_slug"])
        if slug not in cache:
            if len(cache) >= limit:
                break
            try:
                cache[slug] = float(fetch(slug))
            except Exception as error:  # noqa: BLE001 - the type only
                LOG.info("live: no settlement for a market (%s)", type(error).__name__)
                cache[slug] = float("nan")
        px = cache[slug]
        if not math.isfinite(px):
            continue
        long_ = str(x["long"]).strip().lower() in ("true", "1", "1.0", "yes")
        paid_each = px if long_ else 1.0 - px
        out.loc[i, "payout"] = paid_each
        out.loc[i, "profit"] = paid_each * float(x["filled"]) - float(x["paid"])
        out.loc[i, "graded_at"] = _stamp(now)
        weeks.add((int(x["year"]), int(x["week"])))
    if weeks:
        seal(out, passphrase, weeks, where)
        LOG.info("live: %d orders graded", len(weeks))
    return out


# ---------------------------------------------------------------------------
# The owner page
# ---------------------------------------------------------------------------


def section(ledger: pd.DataFrame, now: datetime) -> dict:
    """The live step's state and ledger: mode and arming, the caps, what is open, what the window has
    made or lost, and the latest orders."""
    m = mode()
    c = caps()
    stop = stopped(ledger, now) if len(ledger) else None
    status = {"off": "Off: the mode secret is not set; nothing is sized, previewed or sent.",
              "dry": "Dry run: every position is sized, checked and previewed, and written here as if sent. "
                     "Nothing is sent.",
              "live": "Live and armed: orders are sent." if armed() else
                      "Live but not armed: the arming secret does not carry the phrase; nothing is sent."}[m]
    notes = [status,
             f"Caps: ${c['MAX_ORDER_DOLLARS']:.0f} an order, ${c['MAX_DAY_DOLLARS']:.0f} a day, "
             f"${c['MAX_OPEN_DOLLARS']:.0f} open; the stop holds while the orders settled over the last "
             f"{LOSS_WINDOW_DAYS} days have lost more than ${c['LOSS_STOP_DOLLARS']:.0f}. "
             f"Bankroll ${bankroll():,.0f}.",
             "Every order is a limit at the ask the position was logged at, immediate-or-cancel, for the stake's "
             "worth of contracts; never a market order, never a resting one."]
    if stop:
        notes.insert(1, f"STOPPED: {stop}.")
    tables = []
    if len(ledger):
        sent = ledger[ledger["mode"].astype(str) == "live"]
        head = [["Open (unsettled, $)", f"{open_dollars(ledger):.2f}"],
                [f"Settled, last {LOSS_WINDOW_DAYS} days ($)", f"{window_profit(ledger, now):+.2f}"],
                ["Orders sent / written", f"{int(len(sent))} / {int(len(ledger))}"],
                ["Refused", f"{int((ledger['state'].astype(str) == 'refused').sum())}"]]
        tables.append({"title": "Ledger", "head": ["", ""], "stack": False, "rows": head})
        latest = ledger.sort_values("placed_at", kind="stable").tail(25).iloc[::-1]
        rows = []
        for x in latest.itertuples():
            filled = float(x.filled) if pd.notna(x.filled) else 0.0
            px = float(x.avg_px) if pd.notna(x.avg_px) else float("nan")
            profit = float(x.profit) if pd.notna(x.profit) else float("nan")
            rows.append([[str(x.label), f"{str(x.sport).upper()} · {x.market} {x.side}"], str(x.mode),
                         f"{float(x.quantity):g} @ {float(x.ask):.2f}",
                         f"{filled:g} @ {px:.2f}" if filled > 0 and math.isfinite(px) else "none",
                         f"{profit:+.2f}" if math.isfinite(profit) else "", f"{x.state} {x.note or ''}".strip()])
        tables.append({"title": "Latest orders", "head": ["Position", "Mode", "Order", "Filled", "Profit", "State"],
                       "stack": True, "rows": rows})
    return {"title": f"Live orders ({m}{', armed' if armed() else ''})", "tab": TAB, "tables": tables, "notes": notes}
