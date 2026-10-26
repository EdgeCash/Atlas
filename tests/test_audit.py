"""The live step's audit trail (atlas/polymarket/audit.py): every call to the venue and every position
declined before it, stamped to the millisecond, the submit on disk before a live order goes, and the trail
sealed and merged by event."""

from __future__ import annotations

import base64
import math
from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from atlas.owner import sealed
from atlas.polymarket import account, audit, orders, positions

SECRET = base64.b64encode(bytes(range(32))).decode()
KEY = "correct horse battery staple"
NOW = datetime(2026, 10, 24, 14, 0, tzinfo=UTC)


def _positions(rows):
    base = {**dict.fromkeys(positions.COLUMNS), "sport": "nfl", "day": "2026-10-24", "year": 2026, "week": 43,
            "label": "A @ B", "away": "A", "home": "B", "kickoff": "2026-10-25T17:00:00Z", "market": "moneyline",
            "side": "home", "line": float("nan"), "stake": 0.02, "fee_rate": 0.0695, "long": True, "ask": 0.40,
            "market_slug": "m1", "token_id": "t1", "tick": 0.01}
    return pd.DataFrame([{**base, **r} for r in rows], columns=positions.COLUMNS)


class _HTTPError(Exception):
    def __init__(self, status, text):
        super().__init__(f"{status}")
        self.response = type("R", (), {"status_code": status, "text": text})()


class _Session:
    """Answers the balance, the preview and the order; ``seen`` is called with each order request as it
    arrives, before the answer, and ``refuse`` makes the venue reject orders."""

    def __init__(self, seen=None, refuse=False):
        self.calls, self.seen, self.refuse = [], seen, refuse

    def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append(url)
        if self.seen and url.endswith(orders.ORDERS):
            self.seen(json)
        if self.refuse and url.endswith(orders.ORDERS):
            raise _HTTPError(400, '{"error": "price not on tick"}')
        req = json["request"] if "request" in json else json
        qty = req["quantity"]
        order = {"avgPx": {"value": req["price"]["value"], "currency": "USD"}, "cumQuantity": qty, "quantity": qty,
                 "state": "ORDER_STATE_FILLED", "transactTime": "2026-10-24T14:00:00.123456Z",
                 "commissionNotionalTotalCollected": {"value": "0.3300", "currency": "USD"}}
        body = {"order": order} if url.endswith(account.PREVIEW) else \
            {"id": "ord-9", "executions": [{"id": "exec-1", "lastPx": req["price"], "lastShares": qty, "order": order}]}
        return type("R", (), {"raise_for_status": lambda self: None, "json": lambda self: body})()

    def get(self, url, headers=None, timeout=None):
        self.calls.append(url)
        body = {"balances": [{"currentBalance": 900.0, "assetNotional": 100.0, "currency": "USD"}]}
        return type("R", (), {"raise_for_status": lambda self: None, "json": lambda self: body})()


@pytest.fixture
def env(monkeypatch):
    for name in (orders.MODE, orders.ARMED, orders.BANKROLL, orders.RULES, orders.KILL, "ATLAS_OFFLINE",
                 *orders.CAPS):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv(account.KEY_ID, "key-1")
    monkeypatch.setenv(account.SECRET_KEY, SECRET)
    monkeypatch.setenv(orders.BANKROLL, "1000")
    monkeypatch.setattr(orders, "branch_kill", None)
    return monkeypatch


def test_a_dry_run_records_the_balance_and_each_previews_request_and_answer(env, tmp_path):
    env.setenv(orders.MODE, "dry")
    pos = _positions([{"position_id": "p1"}, {"position_id": "p2", "token_id": "t2", "market_slug": "m2",
                                              "long": False, "ask": 0.30}])
    orders.place(pos, KEY, NOW, where=tmp_path / "live", sess=_Session())
    trail = audit.load(KEY, tmp_path / "polymarket_audit")
    assert list(trail["kind"]) == ["balance", "submit", "response", "submit", "response"]
    assert (trail["mode"] == "dry").all() and (trail["rule"] == "model").all() and trail["event_id"].is_unique
    balance = trail.iloc[0]
    assert balance["path"] == orders.BALANCES and balance["ok"] and balance["equity"] == 1000.0
    for submit, response in ((trail.iloc[1], trail.iloc[2]), (trail.iloc[3], trail.iloc[4])):
        assert submit["request_id"] == response["request_id"] and submit["path"] == account.PREVIEW
        assert response["sent_at"] == submit["at"] and response["received_at"] == response["at"]
        assert response["latency_ms"] >= 0 and response["ok"] and response["response"]["state"] == "ORDER_STATE_FILLED"
    assert trail.iloc[1]["request"]["price"]["value"] == "0.40" and trail.iloc[3]["request"]["price"]["value"] == "0.70"
    assert trail.iloc[3]["position_id"] == "p2" and trail.iloc[3]["request"]["intent"] == "ORDER_INTENT_BUY_SHORT"
    assert all(len(t) == len("2026-10-24T14:00:00.000+00:00") for t in trail["at"])      # to the millisecond


def test_a_live_orders_submit_is_on_disk_before_it_is_sent_and_its_answer_after(env, tmp_path):
    env.setenv(orders.MODE, "live")
    env.setenv(orders.ARMED, orders.PHRASE)
    on_disk = []

    def seen(body):
        written = audit.load(KEY, tmp_path / "polymarket_audit")
        on_disk.append(written[written["kind"] == "submit"]["request"].tolist())
    ledger = orders.place(_positions([{"position_id": "p1"}]), KEY, NOW, where=tmp_path / "live",
                          sess=_Session(seen=seen))
    sent = ledger.set_index("position_id").loc["p1"]
    assert on_disk and on_disk[0][0]["marketSlug"] == "m1"           # the trace was there when the order went
    trail = audit.load(KEY, tmp_path / "polymarket_audit")
    response = trail[trail["kind"] == "response"].iloc[0]
    assert response["path"] == orders.ORDERS and response["order_id"] == "ord-9" == sent["order_id"]
    assert response["response"]["executions"][0]["id"] == "exec-1"
    assert response["response"]["executions"][0]["order"]["transactTime"] == "2026-10-24T14:00:00.123456Z"
    assert response["state"] == "filled" and response["filled"] == sent["filled"] and response["fee"] == 0.33


def test_no_trace_no_order_and_a_rejection_is_kept_with_its_status_and_body(env, tmp_path):
    env.setenv(orders.MODE, "live")
    env.setenv(orders.ARMED, orders.PHRASE)
    sess = _Session()

    def broken(self):
        raise OSError("disk full")
    with env.context() as m:
        m.setattr(audit.Trail, "flush", broken)
        ledger = orders.place(_positions([{"position_id": "p1"}]), KEY, NOW, where=tmp_path / "live", sess=sess)
    row = ledger.set_index("position_id").loc["p1"]
    assert row["state"] == "refused" and row["note"] == "audit: the submit was not written (OSError)"
    assert not any(url.endswith(orders.ORDERS) for url in sess.calls)      # the balance read, and nothing sent
    refused = orders.place(_positions([{"position_id": "p2", "token_id": "t2"}]), KEY, NOW, where=tmp_path / "live",
                           sess=_Session(refuse=True))
    assert refused.set_index("position_id").loc["p2", "state"] == "error"
    trail = audit.load(KEY, tmp_path / "polymarket_audit")
    answer = trail[trail["kind"] == "response"].iloc[-1]
    assert not answer["ok"] and answer["error"] == "_HTTPError" and answer["http_status"] == 400
    assert answer["error_body"] == '{"error": "price not on tick"}'


def test_every_position_declined_before_the_venue_is_kept_with_why(env, tmp_path):
    env.setenv(orders.MODE, "live")
    env.setenv(orders.ARMED, orders.PHRASE)
    env.setenv(orders.KILL, "incident")
    sess = _Session()
    orders.place(_positions([{"position_id": "p1"}, {"position_id": "p2", "token_id": "t2"}]), KEY, NOW,
                 where=tmp_path / "live", sess=sess)
    env.delenv(orders.KILL)
    env.setenv(orders.ARMED, "wrong")
    orders.place(_positions([{"position_id": "p3", "token_id": "t3"}]), KEY, NOW, where=tmp_path / "live", sess=sess)
    trail = audit.load(KEY, tmp_path / "polymarket_audit")
    refused = trail[trail["kind"] == "refused"]
    assert list(refused["position_id"]) == ["p1", "p2", "p3"]
    assert refused.iloc[0]["note"] == f"kill: {orders.KILL} is set (incident)" and refused.iloc[2]["note"] == "not armed"
    assert refused.iloc[0]["request"]["marketSlug"] == "m1"                  # the order it would have been
    assert sess.calls == [account.API + orders.BALANCES]                      # killed: no balance read either


def test_the_trail_is_sealed_a_file_per_week_and_only_grows(tmp_path):
    clock = iter([NOW, NOW + timedelta(days=7), NOW + timedelta(days=7, seconds=1)])
    trail = audit.Trail(KEY, tmp_path, mode="live", rule="finish", clock=lambda: next(clock))
    trail.add("balance", equity=float("nan"), shares=pd.Series([3]).iloc[0])
    trail.add("refused", note="throttle")
    assert trail.flush() == 2 and trail.flush() == 0
    files = sorted(p.name for p in tmp_path.glob("*.enc.json"))
    assert files == ["2026-43.enc.json", "2026-44.enc.json"]
    first = sealed.open_text((tmp_path / "2026-43.enc.json").read_text(), KEY)
    assert first[0]["equity"] is None and first[0]["shares"] == 3 and first[0]["rule"] == "finish"
    again = audit.Trail(KEY, tmp_path, clock=lambda: NOW + timedelta(days=7, seconds=2))
    again.add("refused", note="cap")
    again.flush()
    assert len(sealed.open_text((tmp_path / "2026-44.enc.json").read_text(), KEY)) == 2
    assert audit.plain({"a": [float("inf"), NOW]}) == {"a": [None, "2026-10-24T14:00:00.000+00:00"]}
    assert math.isclose(audit.answered({"at": "2026-10-24T14:00:00.000+00:00", "request_id": "r", "path": "/p"},
                                       "2026-10-24T14:00:00.250+00:00")["latency_ms"], 250.0)
