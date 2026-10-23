"""The live step (atlas/polymarket/orders.py), armed off: the mode and the arming phrase, the caps and the
stop, a dry run that previews and never sends, a live run that sends only when armed, the ledger sealed
and graded, and the owner page's section."""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from atlas.polymarket import account, orders, positions

SECRET = base64.b64encode(bytes(range(32))).decode()
KEY = "correct horse battery staple"
NOW = datetime(2026, 10, 24, 14, 0, tzinfo=UTC)


def _positions(rows):
    base = {**dict.fromkeys(positions.COLUMNS), "sport": "nfl", "day": "2026-10-24", "year": 2026, "week": 43,
            "label": "A @ B", "away": "A", "home": "B", "kickoff": "2026-10-25T17:00:00Z", "market": "moneyline",
            "side": "home", "line": float("nan"), "stake": 0.02, "fee_rate": 0.0695, "long": True, "ask": 0.40,
            "market_slug": "m1", "token_id": "t1"}
    return pd.DataFrame([{**base, **r} for r in rows], columns=positions.COLUMNS)


class _Session:
    def __init__(self, fill=None, fail=False):
        self.calls, self.fill, self.fail = [], fill, fail

    def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append({"url": url, "json": json})
        if self.fail:
            raise RuntimeError("venue down")
        req = json["request"] if "request" in json else json
        qty = req["quantity"]
        filled = min(qty, self.fill) if self.fill is not None else qty
        px = float(req["price"]["value"]) + 0.01
        order = {"avgPx": {"value": f"{px:.4f}", "currency": "USD"}, "cumQuantity": filled, "quantity": qty,
                 "leavesQuantity": qty - filled, "state": "ORDER_STATE_FILLED" if filled == qty else "ORDER_STATE_CANCELED",
                 "commissionNotionalTotalCollected": {"value": f"{0.0695 * px * (1 - px) * filled:.4f}", "currency": "USD"}}
        body = {"order": order} if url.endswith(account.PREVIEW) else {"id": "ord-1", "executions": [{"id": "x1", "order": order}]}
        return _Response(body)


class _Response:
    def __init__(self, body):
        self.body = body

    def raise_for_status(self):
        return None

    def json(self):
        return self.body


@pytest.fixture
def env(monkeypatch):
    for name in (orders.MODE, orders.ARMED, orders.BANKROLL, account.KEY_ID, account.SECRET_KEY, "ATLAS_OFFLINE", *orders.CAPS):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv(account.KEY_ID, "key-1")
    monkeypatch.setenv(account.SECRET_KEY, SECRET)
    return monkeypatch


def test_the_mode_and_the_arming_phrase(env):
    assert orders.mode() == "off" and not orders.armed()
    env.setenv(orders.MODE, "DRY")
    assert orders.mode() == "dry" and not orders.armed()
    env.setenv(orders.MODE, "live")
    assert orders.mode() == "live" and not orders.armed()                                  # no phrase
    env.setenv(orders.ARMED, "place real orders")
    assert not orders.armed()                                                          # not the phrase
    env.setenv(orders.ARMED, orders.PHRASE)
    assert orders.armed()
    env.setenv(orders.MODE, "nonsense")
    assert orders.mode() == "off" and not orders.armed()
    assert orders.caps()["MAX_ORDER_DOLLARS"] == 25.0 and orders.bankroll() == 0.0
    env.setenv("MAX_ORDER_DOLLARS", "10")
    env.setenv(orders.BANKROLL, "500")
    assert orders.caps()["MAX_ORDER_DOLLARS"] == 10.0 and orders.bankroll() == 500.0


def test_the_caps_and_the_stop():
    ledger = pd.DataFrame([
        {**dict.fromkeys(orders.COLUMNS), "mode": "live", "day": "2026-10-24", "cost": 20.0, "filled": 50.0, "paid": 20.4,
         "payout": float("nan"), "profit": float("nan")},
        {**dict.fromkeys(orders.COLUMNS), "mode": "live", "day": "2026-10-24", "cost": 20.0, "filled": 50.0, "paid": 20.4,
         "payout": 0.0, "profit": -20.4, "graded_at": "2026-10-24T12:00:00+00:00"},
        {**dict.fromkeys(orders.COLUMNS), "mode": "live", "day": "2026-10-20", "cost": 20.0, "filled": 50.0, "paid": 20.4,
         "payout": 0.0, "profit": -40.0, "graded_at": "2026-10-20T12:00:00+00:00"},         # outside the window
        {**dict.fromkeys(orders.COLUMNS), "mode": "dry", "day": "2026-10-24", "cost": 500.0, "filled": 500.0, "paid": 500.0},
    ], columns=orders.COLUMNS)
    assert orders.open_dollars(ledger) == pytest.approx(20.4)                           # the dry row does not count
    assert orders.day_dollars(ledger, "2026-10-24") == pytest.approx(40.0)
    assert orders.window_profit(ledger, NOW) == pytest.approx(-20.4)
    assert orders.stopped(ledger, NOW) is None
    assert orders.check(30.0, ledger, "2026-10-24", NOW).startswith("cap:order")
    assert orders.check(20.0, ledger, "2026-10-24", NOW) is None
    assert orders.check(20.0, ledger, "2026-10-24", NOW + timedelta(days=0)) is None
    assert orders.check(10.0, pd.concat([ledger] * 3, ignore_index=True), "2026-10-24", NOW).startswith("cap:day")
    big = ledger.copy()
    big.loc[0, "paid"] = 245.0
    assert orders.check(10.0, big, "2026-10-25", NOW).startswith("cap:open")
    lost = ledger.copy()
    lost.loc[1, "profit"] = -60.0
    assert orders.check(1.0, lost, "2026-10-25", NOW).startswith("stop:loss")
    assert orders.stopped(lost, NOW + timedelta(days=4)) is None                        # the window clears
    assert orders.check(1.0, pd.DataFrame(columns=orders.COLUMNS), "2026-10-25", NOW) is None


def test_off_does_nothing_and_dry_previews_without_sending(env, tmp_path):
    where = tmp_path / "live"
    pos = _positions([{"position_id": "p1"}, {"position_id": "p2", "long": False, "ask": 0.30, "token_id": "t2", "market_slug": "m2"}])
    sess = _Session()
    assert orders.place(pos, KEY, NOW, where=where, sess=sess).empty and not sess.calls and not where.exists()
    env.setenv(orders.MODE, "dry")
    env.setenv(orders.BANKROLL, "1000")
    ledger = orders.place(pos, KEY, NOW, where=where, sess=sess)
    assert len(ledger) == 2 and all(c["url"].endswith(account.PREVIEW) for c in sess.calls) and len(sess.calls) == 2
    by = ledger.set_index("position_id")
    assert by.loc["p1", "mode"] == "dry" and by.loc["p1", "state"] == "dry" and by.loc["p1", "note"] == "preview filled"
    assert by.loc["p1", "quantity"] == 50.0 and by.loc["p1", "cost"] == pytest.approx(20.0) and by.loc["p1", "price"] == 0.40
    assert by.loc["p1", "filled"] == 50.0 and by.loc["p1", "avg_px"] == pytest.approx(0.41) and by.loc["p1", "order_id"] == ""
    assert by.loc["p2", "price"] == pytest.approx(0.70) and by.loc["p2", "avg_px"] == pytest.approx(1 - 0.71)
    assert where.exists() and len(orders.load(KEY, where)) == 2                           # sealed, and read back
    with pytest.raises(Exception):  # noqa: B017 - the wrong key does not open it
        orders.load("wrong", where)
    # A dry run obeys the caps too: an order over the cap is refused and written as such.
    env.setenv("MAX_ORDER_DOLLARS", "5")
    again = orders.place(_positions([{"position_id": "p3", "token_id": "t3"}]), KEY, NOW, where=where, sess=sess)
    assert len(again) == 3 and again.set_index("position_id").loc["p3", "state"] == "refused"
    assert again.set_index("position_id").loc["p3", "note"].startswith("cap:order") and len(sess.calls) == 2
    # No bankroll: sized at nothing, refused, nothing called.
    env.delenv(orders.BANKROLL)
    env.setenv("MAX_ORDER_DOLLARS", "25")
    none = orders.place(_positions([{"position_id": "p4", "token_id": "t4"}]), KEY, NOW, where=where, sess=sess)
    assert none.set_index("position_id").loc["p4", "note"] == "no bankroll" and len(sess.calls) == 2


def test_live_sends_only_when_armed_and_records_the_fill(env, tmp_path):
    where = tmp_path / "live"
    env.setenv(orders.MODE, "live")
    env.setenv(orders.BANKROLL, "1000")
    pos = _positions([{"position_id": "p1"}])
    sess = _Session(fill=30.0)
    unarmed = orders.place(pos, KEY, NOW, where=where, sess=sess)
    assert unarmed.set_index("position_id").loc["p1", "note"] == "not armed" and not sess.calls
    signer = account.Signer("key-1", SECRET)
    with pytest.raises(RuntimeError):
        orders.post_order({}, signer, sess)
    with pytest.raises(ValueError):
        orders.post_order({}, signer, sess, path_=account.PREVIEW)
    env.setenv(orders.ARMED, orders.PHRASE)
    ledger = orders.place(_positions([{"position_id": "p2", "token_id": "t2"}]), KEY, NOW, where=where, sess=sess)
    assert len(sess.calls) == 1 and sess.calls[0]["url"] == account.API + orders.ORDERS
    body = sess.calls[0]["json"]
    assert body["type"] == "ORDER_TYPE_LIMIT" and body["tif"] == "TIME_IN_FORCE_IMMEDIATE_OR_CANCEL"
    assert body["synchronousExecution"] is True and body["intent"] == "ORDER_INTENT_BUY_LONG" and body["quantity"] == 50.0
    row = ledger.set_index("position_id").loc["p2"]
    assert row["mode"] == "live" and row["order_id"] == "ord-1" and row["state"] == "partial"
    assert row["filled"] == 30.0 and row["avg_px"] == pytest.approx(0.41) and row["paid"] == pytest.approx(0.41 * 30 + row["fee"])
    assert json.dumps(json.loads(ledger.to_json(orient="records")))
    # A venue failure marks the row; the day's cap counts what was sent at the ask.
    failed = orders.place(_positions([{"position_id": "p3", "token_id": "t3"}]), KEY, NOW, where=where, sess=_Session(fail=True))
    assert failed.set_index("position_id").loc["p3", "state"] == "error"
    assert orders.day_dollars(failed, "2026-10-24") == pytest.approx(60.0)
    # The settlement grades the filled order; the loss stop then reads the window.
    soon = orders.grade(failed, KEY, NOW + timedelta(days=1, hours=4), where=where, fetch=lambda slug: 0.0)
    assert pd.isna(soon.set_index("position_id").loc["p2", "payout"])                 # kickoff not four hours gone
    graded = orders.grade(failed, KEY, NOW + timedelta(days=2), where=where, fetch=lambda slug: 0.0)
    r = graded.set_index("position_id").loc["p2"]
    assert r["payout"] == 0.0 and r["profit"] == pytest.approx(-row["paid"]) and str(r["graded_at"]).startswith("2026-10-26")
    assert pd.isna(graded.set_index("position_id").loc["p3", "payout"])              # nothing filled, nothing to grade
    assert orders.window_profit(graded, NOW + timedelta(days=2, hours=1)) == pytest.approx(-row["paid"])
    assert len(orders.load(KEY, where)) == 3


def test_the_owner_page_section_states_the_mode_and_sums_the_ledger(env):
    sec = orders.section(pd.DataFrame(columns=orders.COLUMNS), NOW)
    assert sec["title"] == "Live orders (off)" and sec["tab"] == "Live" and sec["notes"][0].startswith("Off")
    assert sec["tables"] == [] and json.dumps(sec)
    env.setenv(orders.MODE, "dry")
    ledger = pd.DataFrame([
        {**dict.fromkeys(orders.COLUMNS), "mode": "dry", "placed_at": "2026-10-24T14:00:00+00:00", "label": "A @ B",
         "sport": "nfl", "market": "moneyline", "side": "home", "quantity": 50.0, "ask": 0.4, "filled": 50.0,
         "avg_px": 0.41, "state": "dry", "note": "preview filled", "cost": 20.0, "paid": 0.0},
        {**dict.fromkeys(orders.COLUMNS), "mode": "live", "placed_at": "2026-10-23T14:00:00+00:00", "label": "C @ D",
         "sport": "nba", "market": "spread", "side": "away", "quantity": 20.0, "ask": 0.5, "filled": 20.0,
         "avg_px": 0.5, "state": "filled", "note": "", "cost": 10.0, "paid": 10.2, "payout": 1.0, "profit": 9.8,
         "graded_at": "2026-10-24T04:00:00+00:00"},
    ], columns=orders.COLUMNS)
    sec = orders.section(ledger, NOW)
    assert sec["title"] == "Live orders (dry)" and sec["notes"][0].startswith("Dry run")
    assert sec["tables"][0]["rows"][1] == ["Settled, last 3 days ($)", "+9.80"] and sec["tables"][0]["rows"][2][1] == "1 / 2"
    assert sec["tables"][1]["rows"][0][0] == ["A @ B", "NFL · moneyline home"] and sec["tables"][1]["rows"][1][4] == "+9.80"
    env.setenv(orders.MODE, "live")
    env.setenv(orders.ARMED, orders.PHRASE)
    assert orders.section(ledger, NOW)["title"] == "Live orders (live, armed)"
    lost = ledger.copy()
    lost.loc[1, "profit"] = -80.0
    assert orders.section(lost, NOW)["notes"][1].startswith("STOPPED: stop:loss")
