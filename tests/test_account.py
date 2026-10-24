"""Polymarket US with the owner's key (atlas/polymarket/account.py): the signature, the order a position
would be, the preview folded into the sealed record, and the one path the module may call."""

from __future__ import annotations

import base64
import json
import math
from datetime import UTC, datetime

import pandas as pd
import pytest

from atlas.polymarket import account, positions

SECRET = base64.b64encode(bytes(range(32))).decode()
NOW = datetime(2026, 10, 24, 14, 0, tzinfo=UTC)


def _record(rows):
    base = {**dict.fromkeys(positions.COLUMNS), "sport": "nfl", "day": "2026-10-24", "year": 2026, "week": 43,
            "label": "A @ B", "away": "A", "home": "B", "kickoff": "2026-10-25T17:00:00Z", "market": "moneyline",
            "side": "home", "line": float("nan"),
            "stake": 0.02, "fee_rate": 0.0695}
    return pd.DataFrame([{**base, **r} for r in rows], columns=positions.COLUMNS)


class _Session:
    """A session that answers the preview with a fill, and remembers what it was asked."""

    def __init__(self, fill=None, fail=False):
        self.calls, self.fill, self.fail = [], fill, fail

    def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append({"url": url, "json": json, "headers": headers})
        req = json["request"]
        qty = req["quantity"]
        if self.fail:
            raise RuntimeError("venue down")
        filled = min(qty, self.fill) if self.fill is not None else qty
        px = float(req["price"]["value"]) + (0.01 if req["intent"] == "ORDER_INTENT_BUY_LONG" else -0.01)
        body = {"order": {"marketSlug": req["marketSlug"], "avgPx": {"value": f"{px:.4f}", "currency": "USD"},
                          "cumQuantity": filled, "leavesQuantity": qty - filled, "quantity": qty,
                          "commissionNotionalTotalCollected": {"value": f"{0.0695 * px * (1 - px) * filled:.4f}",
                                                               "currency": "USD"},
                          "state": "ORDER_STATE_FILLED" if filled == qty else "ORDER_STATE_CANCELED"}}
        return _Response(body)


class _Response:
    def __init__(self, body):
        self.body = body

    def raise_for_status(self):
        return None

    def json(self):
        return self.body


def test_the_signature_is_the_venues_over_timestamp_method_and_path():
    from cryptography.hazmat.primitives.asymmetric import ed25519

    signer = account.Signer("key-1", SECRET)
    h = signer.headers("POST", account.PREVIEW, now_ms=1_761_000_000_000)
    assert h["X-PM-Access-Key"] == "key-1" and h["X-PM-Timestamp"] == "1761000000000"
    public = ed25519.Ed25519PublicKey.from_public_bytes(signer.public_key())
    public.verify(base64.b64decode(h["X-PM-Signature"]), b"1761000000000POST/v1/order/preview")   # raises if not
    with pytest.raises(Exception):  # noqa: B017 - any failure: the message is not the one signed
        public.verify(base64.b64decode(h["X-PM-Signature"]), b"1761000000000POST/v1/orders")
    assert account.Signer("k", SECRET).headers("GET", "/x")["X-PM-Timestamp"].isdigit()


def test_the_secret_is_read_as_the_portal_shows_it_and_a_bad_one_says_so_without_quoting_it():
    seed = bytes(range(32))
    pem = ("-----BEGIN PRIVATE KEY-----\n"
           + base64.b64encode(bytes.fromhex("302e020100300506032b657004220420") + seed).decode()
           + "\n-----END PRIVATE KEY-----\n")
    for form in (base64.b64encode(seed).decode(),                          # the venue's sample
                 base64.b64encode(seed + bytes(32)).decode(),              # seed and public key
                 base64.b64encode(seed).decode().rstrip("="),              # pasted without its padding
                 base64.urlsafe_b64encode(seed).decode(),                  # the URL-safe alphabet
                 seed.hex(), seed.hex().upper(),                            # hex
                 f'"{base64.b64encode(seed).decode()}"\n',                   # quoted, with a newline
                 base64.b64encode(bytes.fromhex("302e020100300506032b657004220420") + seed).decode(),  # DER
                 pem):
        assert account.decode_secret(form) == seed, form[:12]
        assert account.Signer("k", form).public_key() == account.Signer("k", SECRET).public_key()
    for bad in ("", "zqxjwvkp-is-no-key", base64.b64encode(b"short").decode(), "zz" * 16, "12345678-1234-1234-1234-123456789abc"):
        with pytest.raises(ValueError) as caught:
            account.decode_secret(bad)
        assert "does not decode" in str(caught.value)
        assert not bad or bad[:4] not in str(caught.value).replace("characters", "")


def test_a_bad_secret_stops_the_previews_and_is_written_as_the_refusal_not_raised(monkeypatch, tmp_path):
    from atlas.polymarket import orders

    monkeypatch.delenv("ATLAS_OFFLINE", raising=False)
    monkeypatch.setenv(account.KEY_ID, "key-1")
    monkeypatch.setenv(account.SECRET_KEY, "12345678-1234-1234-1234-123456789abc")   # the key id, pasted twice
    signer, why = account.Signer.try_env()
    assert signer is None and why.startswith("bad key: the secret key does not decode")
    record = _record([{"position_id": "p1", "market_slug": "m1", "long": True, "ask": 0.40}])
    out = account.preview(record, {"p1"}, NOW)                                    # no raise, nothing previewed
    assert pd.isna(out.set_index("position_id").loc["p1", "previewed_at"])
    monkeypatch.setenv(orders.MODE, "live")
    monkeypatch.setenv(orders.BANKROLL, "124")
    ledger = orders.place(record, "pass", NOW, where=tmp_path / "live", rule="model")
    assert list(ledger["state"]) == ["refused"] and ledger.iloc[0]["note"].startswith("bad key: the secret key")
    assert "1234" not in ledger.iloc[0]["note"].replace("characters", "")


def test_the_key_check_says_what_is_set_and_what_decodes(monkeypatch, capsys):
    monkeypatch.setenv("ATLAS_OFFLINE", "1")
    monkeypatch.delenv(account.KEY_ID, raising=False)
    monkeypatch.delenv(account.SECRET_KEY, raising=False)
    assert account.check() == 1 and "not set" in capsys.readouterr().out
    monkeypatch.setenv(account.KEY_ID, "key-1")
    monkeypatch.setenv(account.SECRET_KEY, "nope")
    assert account.check() == 1 and "bad key" in capsys.readouterr().out
    monkeypatch.setenv(account.SECRET_KEY, SECRET)
    assert account.check() == 0
    out = capsys.readouterr().out
    assert "decodes to an Ed25519 key" in out and "offline" in out and SECRET[:8] not in out


def test_the_key_comes_from_the_environment_and_without_it_nothing_is_signed(monkeypatch):
    monkeypatch.delenv(account.KEY_ID, raising=False)
    monkeypatch.delenv(account.SECRET_KEY, raising=False)
    assert not account.configured() and account.Signer.from_env() is None
    monkeypatch.setenv(account.KEY_ID, "key-1")
    monkeypatch.setenv(account.SECRET_KEY, SECRET)
    assert account.configured() and account.Signer.from_env().key_id == "key-1"


def test_the_order_is_a_limit_at_the_ask_on_the_long_side_immediate_or_cancel():
    long_ = _record([{"position_id": "p1", "market_slug": "nfl-kc-buf-ml", "long": True, "ask": 0.42}]).iloc[0]
    short = _record([{"position_id": "p2", "market_slug": "nfl-kc-buf-ml", "long": False, "ask": 0.42}]).iloc[0]
    o = account.order(long_, 47.62)
    assert o["marketSlug"] == "nfl-kc-buf-ml" and o["type"] == "ORDER_TYPE_LIMIT" and o["quantity"] == 47.62
    assert o["price"] == {"value": "0.42", "currency": "USD"} and o["intent"] == "ORDER_INTENT_BUY_LONG"
    assert o["tif"] == "TIME_IN_FORCE_IMMEDIATE_OR_CANCEL" and o["manualOrderIndicator"].endswith("AUTOMATIC")
    s = account.order(short, 10)
    assert s["price"]["value"] == "0.58" and s["intent"] == "ORDER_INTENT_BUY_SHORT"       # the long side's price
    assert account.quantity(long_, 1000.0) == pytest.approx(round(0.02 * 1000 / 0.42, 2))
    assert account.quantity(_record([{"position_id": "p3", "ask": float("nan")}]).iloc[0], 1000.0) == account.MIN_QUANTITY


def test_only_the_preview_path_can_be_called():
    signer = account.Signer("key-1", SECRET)
    with pytest.raises(ValueError):
        account.post({}, signer, _Session(), path="/v1/orders")
    with pytest.raises(ValueError):
        account.post({}, signer, _Session(), path="/v1/order/close-position")
    sess = _Session()
    account.post(account.order(_record([{"position_id": "p1", "market_slug": "m", "long": True, "ask": 0.5}]).iloc[0], 1),
                 signer, sess)
    assert sess.calls[0]["url"] == account.API + account.PREVIEW and "X-PM-Signature" in sess.calls[0]["headers"]
    assert json.dumps(sess.calls[0]["json"])                                          # a JSON body, as sent


def test_the_preview_is_folded_into_the_record_for_the_new_positions_only(monkeypatch):
    monkeypatch.delenv("ATLAS_OFFLINE", raising=False)
    record = _record([
        {"position_id": "old", "market_slug": "m0", "long": True, "ask": 0.40, "previewed_at": "2026-10-23T14:00:00+00:00",
         "preview_qty": 50.0, "preview_px": 0.40, "preview_filled": 50.0, "preview_fee": 0.8, "preview_state": "filled"},
        {"position_id": "p1", "market_slug": "m1", "long": True, "ask": 0.40},
        {"position_id": "p2", "market_slug": "m2", "long": False, "ask": 0.30},
    ])
    signer = account.Signer("key-1", SECRET)
    sess = _Session(fill=30.0)
    out = account.preview(record, {"p1", "p2"}, NOW, signer=signer, sess=sess, bankroll=1000.0)
    assert len(sess.calls) == 2 and [c["json"]["request"]["marketSlug"] for c in sess.calls] == ["m1", "m2"]
    by = out.set_index("position_id")
    assert by.loc["old", "previewed_at"] == "2026-10-23T14:00:00+00:00" and by.loc["old", "preview_px"] == 0.40
    assert by.loc["p1", "previewed_at"] == "2026-10-24T14:00:00+00:00" and by.loc["p1", "preview_qty"] == 50.0
    assert by.loc["p1", "preview_px"] == pytest.approx(0.41) and by.loc["p1", "preview_filled"] == 30.0  # a cent worse
    assert by.loc["p1", "preview_state"] == "canceled" and by.loc["p1", "preview_fee"] > 0
    # The short side: the venue answered on the long side (0.70 less a cent), read back as the position's price.
    assert by.loc["p2", "preview_qty"] == pytest.approx(round(0.02 * 1000 / 0.30, 2))
    assert by.loc["p2", "preview_px"] == pytest.approx(1.0 - 0.69)
    # A failure marks the row and the rest go on; no key, or offline, and the record is left as it was.
    failed = account.preview(record, {"p1"}, NOW, signer=signer, sess=_Session(fail=True))
    assert failed.set_index("position_id").loc["p1", "preview_state"] == "error:RuntimeError"
    assert math.isnan(failed.set_index("position_id").loc["p1", "preview_px"])
    monkeypatch.delenv(account.KEY_ID, raising=False)
    monkeypatch.delenv(account.SECRET_KEY, raising=False)
    untouched = account.preview(record, {"p1"}, NOW)
    assert pd.isna(untouched.set_index("position_id").loc["p1", "previewed_at"])
    monkeypatch.setenv("ATLAS_OFFLINE", "1")
    assert pd.isna(account.preview(record, {"p1"}, NOW, signer=signer, sess=sess).set_index("position_id").loc["p1", "previewed_at"])
    assert len(sess.calls) == 2


def test_the_days_previews_are_summed_for_the_owner_page():
    from atlas.polymarket import page

    record = _record([
        {"position_id": "p1", "market_slug": "m1", "long": True, "ask": 0.40, "previewed_at": "2026-10-24T14:00:00+00:00",
         "preview_qty": 50.0, "preview_px": 0.41, "preview_filled": 50.0, "preview_fee": 0.8, "preview_state": "filled"},
        {"position_id": "p2", "market_slug": "m2", "long": False, "ask": 0.30, "previewed_at": "2026-10-24T14:00:00+00:00",
         "preview_qty": 66.67, "preview_px": 0.31, "preview_filled": 20.0, "preview_fee": 0.3, "preview_state": "canceled"},
        {"position_id": "p3", "market_slug": "m3", "long": True, "ask": 0.50, "previewed_at": "2026-10-24T14:00:00+00:00",
         "preview_qty": 40.0, "preview_px": float("nan"), "preview_filled": float("nan"), "preview_fee": float("nan"),
         "preview_state": "error:HTTPError"},
        {"position_id": "p4", "market_slug": "m4", "long": True, "ask": 0.50},
    ])
    s = account.summary(record, "2026-10-24")
    assert s["n"] == 3 and s["whole"] == 1 and s["errors"] == 1 and s["gap"] == pytest.approx(0.01)
    assert s["fee"] == pytest.approx(1.1) and s["cost"] == pytest.approx(50 * 0.4 + 66.67 * 0.3 + 40 * 0.5)
    assert account.summary(record, "2026-10-23") is None and account.summary(record.iloc[0:0], "2026-10-24") is None
    table = page.preview_table(record, "2026-10-24")
    assert table["title"].startswith("Order previews: 1 of 3 would fill in full at the ask; mean fill +1.0¢")
    assert "1 failed" in table["title"] and len(table["rows"]) == 3
    assert table["rows"][1][2] == "0.31" and table["rows"][1][3] == "20 of 66.67" and table["rows"][2][3] == "failed: HTTPError"
    assert json.dumps(table)
    assert page.preview_table(record, "2026-10-23") is None
