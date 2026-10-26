"""Polymarket US with the owner's key: order previews, and nothing else.

Nothing here places an order. The one path this module can reach is the
venue's order preview (``POST /v1/order/preview``), which validates an
order and says what it would fill at - the average price, the contracts
filled and left, the commission - without entering it. :func:`post` refuses
any other path, and a test holds it to that.

The day's paper positions are previewed once, as they are logged
(`atlas/polymarket/positions.py`): a limit at the quoted ask for the
stake's worth of contracts at a nominal bankroll, immediate-or-cancel, so
the preview shows what the book would fill at that price right then. The
answer goes into the sealed record beside the paper price, which is what
the paper record has assumed all along: that a position fills at the ask
for the size meant. The gap between the two is the cost the record did not
pay.

The key is two repository secrets, the key id and the secret key from
polymarket.us/developer (``POLYMARKET_US_KEY_ID``, ``POLYMARKET_US_SECRET``);
without them the step does nothing. Each request carries the venue's three
headers: the key id, a millisecond timestamp, and an Ed25519 signature of
the timestamp, method and path. A failure is logged against the position
and never fails the run.
"""

from __future__ import annotations

import base64
import math
import os
import time
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

import pandas as pd
import requests

from atlas.util import get_logger, offline

LOG = get_logger(__name__)

API = "https://api.polymarket.us"
#: The only path this module may call.
PREVIEW = "/v1/order/preview"
KEY_ID = "POLYMARKET_US_KEY_ID"
SECRET_KEY = "POLYMARKET_US_SECRET"
#: The nominal bankroll a preview sizes the stake against, in dollars.
BANKROLL = "ATLAS_PREVIEW_BANKROLL"
DEFAULT_BANKROLL = 1000.0
MIN_QUANTITY = 0.01
#: The finest tick the record's prices are kept to (three decimals), taken when a market's own is unknown.
FINEST_TICK = Decimal("0.001")
TIMEOUT = 20
USER_AGENT = "Atlas sports research (github.com/EdgeCash/Atlas; previews only)"
#: What a preview writes into the sealed record, beside the paper price.
COLUMNS = ["previewed_at", "preview_qty", "preview_px", "preview_filled", "preview_fee", "preview_state"]


def configured() -> bool:
    return bool(os.environ.get(KEY_ID, "").strip()) and bool(os.environ.get(SECRET_KEY, "").strip())


class Signer:
    """The venue's request signature: Ed25519 over ``timestamp + method + path`` with the secret key."""

    def __init__(self, key_id: str, secret: str):
        from cryptography.hazmat.primitives.asymmetric import ed25519

        self.key_id = key_id
        self._key = ed25519.Ed25519PrivateKey.from_private_bytes(base64.b64decode(secret)[:32])

    @classmethod
    def from_env(cls) -> Signer | None:
        if not configured():
            return None
        return cls(os.environ[KEY_ID].strip(), os.environ[SECRET_KEY].strip())

    def public_key(self) -> bytes:
        from cryptography.hazmat.primitives import serialization

        return self._key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)

    def headers(self, method: str, path: str, now_ms: int | None = None) -> dict[str, str]:
        timestamp = str(now_ms if now_ms is not None else int(time.time() * 1000))
        signature = base64.b64encode(self._key.sign(f"{timestamp}{method}{path}".encode())).decode()
        return {"X-PM-Access-Key": self.key_id, "X-PM-Timestamp": timestamp, "X-PM-Signature": signature,
                "Content-Type": "application/json", "User-Agent": USER_AGENT}


def quantity(row, bankroll: float) -> float:
    """The stake's worth of contracts at the paper price, to the hundredth the venue trades in."""
    ask = float(row.ask)
    if not math.isfinite(ask) or ask <= 0:
        return MIN_QUANTITY
    return max(MIN_QUANTITY, round(float(row.stake) * bankroll / ask, 2))


def price_text(price: float, tick=None) -> str:
    """A limit price as the venue takes it: on the market's tick (``orderPriceMinTickSize``: a cent on most
    markets, a quarter cent on NFL moneylines, half a cent on college football's, a tenth on some), to the
    tick's own decimals and no fewer than two. The nearest tick, not the one below: the record keeps prices
    to three decimals, so an NFL ask of 0.9975 comes back as 0.997 and only the nearest tick restores it.
    A tick unknown (a record from before it was kept) is taken as the tenth of a cent the record holds."""
    try:
        step = Decimal(str(float(tick)))
    except (TypeError, ValueError):
        step = Decimal("NaN")
    if not step.is_finite() or step <= 0:
        step = FINEST_TICK
    snapped = (Decimal(str(price)) / step).to_integral_value(rounding=ROUND_HALF_UP) * step
    snapped = min(max(snapped, step), 1 - step)
    places = max(2, -step.normalize().as_tuple().exponent)
    text = f"{snapped:.{places}f}"
    while text.endswith("0") and len(text.split(".")[1]) > 2:
        text = text[:-1]
    return text


def order(row, qty: float) -> dict:
    """The order the position would be: a limit at the quoted ask, immediate-or-cancel, on the market's tick
    (:func:`price_text`). The venue prices every order on the long side, so a short position's price is one
    less its ask."""
    long_ = bool(row.long) if str(row.long).lower() not in ("false", "0", "nan", "") else False
    ask = float(row.ask)
    return {"marketSlug": str(row.market_slug), "type": "ORDER_TYPE_LIMIT",
            "price": {"value": price_text(ask if long_ else 1.0 - ask, getattr(row, "tick", None)),
                      "currency": "USD"}, "quantity": qty,
            "tif": "TIME_IN_FORCE_IMMEDIATE_OR_CANCEL",
            "intent": "ORDER_INTENT_BUY_LONG" if long_ else "ORDER_INTENT_BUY_SHORT",
            "manualOrderIndicator": "MANUAL_ORDER_INDICATOR_AUTOMATIC"}


def post(body: dict, signer: Signer, sess: requests.Session | None = None, path: str = PREVIEW) -> dict:
    """The preview request. Any path but :data:`PREVIEW` is refused: this module does not trade."""
    if path != PREVIEW:
        raise ValueError(f"account: {path} is not the preview; nothing else is called from here")
    sess = sess or requests.Session()
    r = sess.post(API + path, json={"request": body}, headers=signer.headers("POST", path), timeout=TIMEOUT)
    r.raise_for_status()
    return r.json().get("order") or {}


def _amount(value) -> float:
    try:
        return float((value or {}).get("value"))
    except (TypeError, ValueError, AttributeError):
        return float("nan")


def read(previewed: dict, row) -> dict:
    """What the preview said, in the position's own terms: the fill price on its side, the contracts filled,
    the commission, and the state."""
    long_ = bool(row.long) if str(row.long).lower() not in ("false", "0", "nan", "") else False
    avg = _amount(previewed.get("avgPx"))
    filled = float(previewed.get("cumQuantity") or 0.0)
    return {"preview_px": (avg if long_ else 1.0 - avg) if math.isfinite(avg) and filled > 0 else float("nan"),
            "preview_filled": filled, "preview_fee": _amount(previewed.get("commissionNotionalTotalCollected")),
            "preview_state": str(previewed.get("state") or "").replace("ORDER_STATE_", "").lower() or "unknown"}


def preview(record: pd.DataFrame, ids, now: datetime, *, signer: Signer | None = None,
            sess: requests.Session | None = None, bankroll: float | None = None) -> pd.DataFrame:
    """The record with the positions in ``ids`` previewed, where the key is set; unchanged otherwise. Each
    position's row gets :data:`COLUMNS`; a request that fails is marked so, and the rest go on."""
    out = record.copy()
    for c in COLUMNS:
        if c not in out:
            out[c] = float("nan")
    if out.empty or not ids:
        return out
    signer = signer or Signer.from_env()
    if signer is None or offline():
        return out
    bankroll = float(bankroll if bankroll is not None else os.environ.get(BANKROLL) or DEFAULT_BANKROLL)
    sess = sess or requests.Session()
    stamp = pd.Timestamp(now).tz_convert("UTC").replace(microsecond=0).isoformat() if pd.Timestamp(now).tzinfo \
        else pd.Timestamp(now).tz_localize("UTC").isoformat()
    todo = out[out["position_id"].isin(set(ids))]
    done, failed = 0, 0
    for i, row in zip(todo.index, todo.itertuples(index=False), strict=True):
        qty = quantity(row, bankroll)
        try:
            values = read(post(order(row, qty), signer, sess), row)
            done += 1
        except Exception as error:  # noqa: BLE001 - the type only; the body could quote the account
            values = {"preview_px": float("nan"), "preview_filled": float("nan"), "preview_fee": float("nan"),
                      "preview_state": f"error:{type(error).__name__}"}
            failed += 1
        out.loc[i, "previewed_at"] = stamp
        out.loc[i, "preview_qty"] = qty
        for k, v in values.items():
            out.loc[i, k] = v
    LOG.info("account: %d positions previewed, %d failed", done, failed)
    return out


def summary(record: pd.DataFrame, day: str) -> dict | None:
    """The day's previews in one line's worth of numbers: how many filled in full at the quoted ask, the mean
    fill against the ask, the fees; None when none were taken."""
    if record.empty or "previewed_at" not in record:
        return None
    r = record[record["day"].astype(str) == str(day)]
    r = r[r["previewed_at"].notna()]
    if r.empty:
        return None
    qty = pd.to_numeric(r["preview_qty"], errors="coerce")
    filled = pd.to_numeric(r["preview_filled"], errors="coerce")
    px = pd.to_numeric(r["preview_px"], errors="coerce")
    ask = pd.to_numeric(r["ask"], errors="coerce")
    whole = int(((filled >= qty - 1e-9) & qty.notna()).sum())
    gap = (px - ask)[px.notna()]
    return {"n": int(len(r)), "whole": whole, "errors": int(r["preview_state"].astype(str).str.startswith("error").sum()),
            "gap": float(gap.mean()) if len(gap) else float("nan"),
            "fee": float(pd.to_numeric(r["preview_fee"], errors="coerce").sum()),
            "cost": float((qty * ask).sum())}


def now_utc() -> datetime:
    return datetime.now(UTC)
