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
import binascii
import math
import os
import re
import time
from datetime import UTC, datetime

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
TIMEOUT = 20
USER_AGENT = "Atlas sports research (github.com/EdgeCash/Atlas; previews only)"
#: What a preview writes into the sealed record, beside the paper price.
COLUMNS = ["previewed_at", "preview_qty", "preview_px", "preview_filled", "preview_fee", "preview_state"]


def configured() -> bool:
    return bool(os.environ.get(KEY_ID, "").strip()) and bool(os.environ.get(SECRET_KEY, "").strip())


#: The DER prefix of a PKCS#8 Ed25519 private key; the 32-byte seed follows it.
_PKCS8 = bytes.fromhex("302e020100300506032b657004220420")


def decode_secret(secret: str) -> bytes:
    """The 32-byte Ed25519 seed from the secret as the portal shows it. The venue's own sample is
    ``base64.b64decode(secret)[:32]``: standard base64 of the seed, or of the seed and the public key. A
    key pasted without its padding, in the URL-safe alphabet, as hex, or as a PEM or DER block is read
    too. Anything else raises ValueError, with the decoded lengths and never the key."""
    s = str(secret or "").strip().strip("\"'").strip()
    if "-----BEGIN" in s:
        from cryptography.hazmat.primitives import serialization

        key = serialization.load_pem_private_key(s.encode(), password=None)
        return key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                                 serialization.NoEncryption())
    s = "".join(s.split())
    candidates: list[bytes] = []
    if re.fullmatch(r"(?:[0-9a-fA-F]{64}|[0-9a-fA-F]{128})", s):
        candidates.append(bytes.fromhex(s))
    b = s.replace("-", "+").replace("_", "/")
    try:
        candidates.append(base64.b64decode(b + "=" * (-len(b) % 4), validate=True))
    except (binascii.Error, ValueError):
        pass
    for raw in candidates:
        if len(raw) in (32, 64):
            return raw[:32]
        if len(raw) == 48 and raw.startswith(_PKCS8):
            return raw[16:]
    lengths = ",".join(str(len(r)) for r in candidates) or "none"
    raise ValueError(f"the secret key does not decode to an Ed25519 key ({len(s)} characters; {lengths} bytes)")


class Signer:
    """The venue's request signature: Ed25519 over ``timestamp + method + path`` with the secret key."""

    def __init__(self, key_id: str, secret: str):
        from cryptography.hazmat.primitives.asymmetric import ed25519

        self.key_id = key_id
        self._key = ed25519.Ed25519PrivateKey.from_private_bytes(decode_secret(secret))

    @classmethod
    def from_env(cls) -> Signer | None:
        """The signer from the two secrets; None when they are not set. A secret that is set but is not a
        key raises ValueError: the caller decides whether that stops the run or is written down."""
        if not configured():
            return None
        return cls(os.environ[KEY_ID].strip(), os.environ[SECRET_KEY].strip())

    @classmethod
    def try_env(cls) -> tuple[Signer | None, str | None]:
        """(the signer, None), (None, None) with no key set, or (None, why) when the key is set but bad."""
        try:
            return cls.from_env(), None
        except Exception as error:  # noqa: BLE001 - the type and the lengths only; never the key
            return None, f"bad key: {error}" if isinstance(error, ValueError) else f"bad key: {type(error).__name__}"

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


def order(row, qty: float) -> dict:
    """The order the position would be: a limit at the quoted ask, immediate-or-cancel. The venue prices
    every order on the long side, so a short position's price is one less its ask."""
    long_ = bool(row.long) if str(row.long).lower() not in ("false", "0", "nan", "") else False
    ask = float(row.ask)
    return {"marketSlug": str(row.market_slug), "type": "ORDER_TYPE_LIMIT",
            "price": {"value": f"{(ask if long_ else 1.0 - ask):.2f}", "currency": "USD"}, "quantity": qty,
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
    if signer is None:
        signer, why = Signer.try_env()
        if why:
            LOG.error("account: no previews; %s", why)
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


def check(sess: requests.Session | None = None) -> int:
    """Say whether the key in the environment is one the venue accepts: the key id's shape, whether the
    secret decodes, and one signed read of the account's balances. Prints a line per step and nothing
    from the key itself; returns 0 when every step passes."""
    key_id = os.environ.get(KEY_ID, "").strip()
    print(f"{KEY_ID}: {'set, ' + str(len(key_id)) + ' characters' if key_id else 'not set'}")
    if not configured():
        print(f"{SECRET_KEY}: {'set' if os.environ.get(SECRET_KEY, '').strip() else 'not set'}")
        return 1
    signer, why = Signer.try_env()
    if signer is None:
        print(f"{SECRET_KEY}: {why}")
        return 1
    print(f"{SECRET_KEY}: decodes to an Ed25519 key")
    if offline():
        print("offline: the venue was not asked")
        return 0
    sess = sess or requests.Session()
    r = sess.get(API + "/v1/account/balances", headers=signer.headers("GET", "/v1/account/balances"),
                 timeout=TIMEOUT)
    print(f"GET /v1/account/balances: HTTP {r.status_code}"
          + (" - the venue accepts the key" if r.ok else " - the venue does not accept the key"))
    return 0 if r.ok else 2


if __name__ == "__main__":
    raise SystemExit(check())
