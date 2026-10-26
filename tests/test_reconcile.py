"""The audit trail reconciled against the venue's account activity (atlas/polymarket/reconcile.py): the read,
the match by trade id, what does not reconcile, and once a day into the trail."""

from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from atlas.polymarket import account, audit, orders, reconcile

SECRET = base64.b64encode(bytes(range(32))).decode()
KEY = "correct horse battery staple"
DAY = "2026-10-24"
MORNING = datetime(2026, 10, 25, 11, 0, tzinfo=UTC)               # 07:00 Eastern the next day


def _trade(tid, at, qty=50.0, price=0.40, state="TRADE_STATE_CLEARED", slug="m1"):
    return {"id": tid, "marketSlug": slug, "state": state, "createTime": at, "updateTime": at,
            "price": {"value": f"{price:.4f}", "currency": "USD"}, "qty": str(int(qty)), "qtyDecimal": f"{qty}",
            "isAggressor": True}


def _filled(trail, position_id, executions, order_id="ord-1", slug="m1"):
    """A live order's answer in the trail, with its executions as the venue sends them."""
    trail.add("response", position_id=position_id, market_slug=slug, request_id=audit.request_id(),
              path=orders.ORDERS, ok=True, order_id=order_id,
              response={"id": order_id, "executions": [
                  {"id": f"x-{tid}", "tradeId": tid, "lastShares": f"{qty}", "transactTime": at,
                   "lastPx": {"value": f"{px:.4f}", "currency": "USD"}} for tid, at, qty, px in executions]})


def _trail(tmp_path, executions_by_order):
    trail = audit.Trail(KEY, tmp_path, mode="live", rule="finish", clock=lambda: datetime(2026, 10, 24, 18, tzinfo=UTC))
    for i, executions in enumerate(executions_by_order):
        _filled(trail, f"p{i}", executions, order_id=f"ord-{i}")
    trail.flush()
    return audit.load(KEY, tmp_path)


class _Pages:
    """The venue's activity, newest first, in pages of two; remembers each request."""

    def __init__(self, trades):
        self.trades = sorted(trades, key=lambda t: t["createTime"], reverse=True)
        self.calls = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append({"url": url, "params": params, "headers": headers})
        cursor = int(dict(params).get("cursor") or 0)
        page = self.trades[cursor:cursor + 2]
        body = {"activities": [{"type": reconcile.TRADE, "trade": t} for t in page],
                "nextCursor": str(cursor + 2), "eof": cursor + 2 >= len(self.trades)}
        return type("R", (), {"raise_for_status": lambda self: None, "json": lambda self: body})()


def test_the_venue_is_read_page_by_page_signed_on_the_path_alone_until_the_pages_pass_the_day():
    signer = account.Signer("key-1", SECRET)
    start, end = reconcile.window(DAY)
    trades = [_trade(f"t{i}", (start + timedelta(hours=3 * i)).isoformat()) for i in range(-3, 10)]
    sess = _Pages(trades)
    got = reconcile.fetch(signer, start, end, sess)
    assert sorted(t["id"] for t in got) == [f"t{i}" for i in range(8)]          # inside the day, nothing else
    first = sess.calls[0]
    assert first["url"] == account.API + reconcile.ACTIVITIES
    assert ("types", reconcile.TRADE) in first["params"] and ("sortOrder", "SORT_ORDER_DESCENDING") in first["params"]
    assert first["headers"]["X-PM-Access-Key"] == "key-1"
    assert len(sess.calls) == 6 and ("cursor", "10") in sess.calls[-1]["params"]   # stopped once a page passed the start
    assert reconcile.window("2026-11-01")[1] - reconcile.window("2026-11-01")[0] == pd.Timedelta(hours=25)


def test_a_day_reconciles_by_trade_id_and_names_everything_that_does_not(tmp_path):
    start, end = reconcile.window(DAY)
    near_midnight = (end - timedelta(milliseconds=1)).isoformat()
    trail = _trail(tmp_path, [
        [("t1", "2026-10-24T18:00:00Z", 50.0, 0.40)],
        [("t2", "2026-10-24T19:00:00Z", 10.0, 0.985), ("t3", "2026-10-24T19:00:00Z", 5.0, 0.99)],
        [("t4", near_midnight, 20.0, 0.97)],                                       # the venue stamps it after midnight
        [("t5", "2026-10-24T20:00:00Z", 8.0, 0.50)],                               # the venue never shows it
        [("t6", "2026-10-24T21:00:00Z", 8.0, 0.60)],                               # busted after the answer
    ])
    venue = reconcile.venue([
        _trade("t1", "2026-10-24T18:00:00.004Z"),
        _trade("t2", "2026-10-24T19:00:00Z", qty=10.0, price=0.985),
        _trade("t3", "2026-10-24T19:00:00Z", qty=4.0, price=0.99),                 # a quantity that disagrees
        _trade("t4", (end + timedelta(milliseconds=2)).isoformat(), qty=20.0, price=0.97),
        _trade("t6", "2026-10-24T21:00:00Z", qty=8.0, price=0.60, state="TRADE_STATE_BUSTED"),
        _trade("t7", "2026-10-24T22:00:00Z", qty=3.0, price=0.25, slug="m7"),       # made by hand in the app
    ])
    result = reconcile.compare(venue, reconcile.ours(trail, start - reconcile.MARGIN, end + reconcile.MARGIN), DAY)
    assert (result["venue"], result["ours"], result["matched"]) == (5, 6, 5)
    assert result["differ"] == [{"trade_id": "t3", "field": "qty", "venue": 4.0, "ours": 5.0, "order_id": "ord-1"}]
    assert [x["trade_id"] for x in result["venue_only"]] == ["t7"] and result["venue_only"][0]["market_slug"] == "m7"
    assert [x["trade_id"] for x in result["ours_only"]] == ["t5"] and result["ours_only"][0]["order_id"] == "ord-3"
    assert [x["trade_id"] for x in result["busted"]] == ["t6"] and result["busted"][0]["order_id"] == "ord-4"
    assert not result["ok"]
    line = reconcile.describe(result)
    assert line.startswith(f"Reconciled {DAY}") and "MISMATCH: 1 differ in quantity or price, 1 on the account" in line
    clean = reconcile.compare(venue[venue["trade_id"].isin(["t1", "t2"])],
                              reconcile.ours(trail, start, end).query("trade_id in ['t1', 't2']"), DAY)
    assert clean["ok"] and reconcile.describe(clean).endswith("everything agrees.")
    assert reconcile.describe(None).startswith("Not reconciled")


def test_once_a_day_from_six_eastern_into_the_trail_and_a_failed_read_retried_hourly(tmp_path, monkeypatch):
    monkeypatch.delenv("ATLAS_OFFLINE", raising=False)
    _trail(tmp_path, [[("t1", "2026-10-24T18:00:00Z", 50.0, 0.40)]])
    signer = account.Signer("key-1", SECRET)
    reads = []

    def fetch(signer_, start, end, sess=None):
        reads.append((start, end))
        return [_trade("t1", "2026-10-24T18:00:00Z")]
    early = datetime(2026, 10, 25, 9, 0, tzinfo=UTC)                     # 05:00 Eastern: not yet
    assert reconcile.daily(KEY, early, signer=signer, where=tmp_path, fetch_=fetch) is None and not reads
    result = reconcile.daily(KEY, MORNING, signer=signer, where=tmp_path, fetch_=fetch)
    assert result["ok"] and result["day"] == DAY and result["matched"] == 1
    start, end = reconcile.window(DAY)
    assert reads == [(start - reconcile.MARGIN, end + reconcile.MARGIN)]
    trail = audit.load(KEY, tmp_path)
    recorded = reconcile.latest(trail)
    assert recorded["kind"] == "reconcile" and recorded["ok"] is True and recorded["path"] == reconcile.ACTIVITIES
    assert reconcile.daily(KEY, MORNING + timedelta(hours=3), signer=signer, where=tmp_path, fetch_=fetch) is None
    assert len(reads) == 1                                                  # a day is reconciled once

    def down(*a, **kw):
        raise ConnectionError("venue down")
    next_day = MORNING + timedelta(days=1)
    failed = reconcile.daily(KEY, next_day, signer=signer, where=tmp_path, fetch_=down)
    assert failed == {"day": "2026-10-25", "error": "ConnectionError"}
    assert reconcile.daily(KEY, next_day + timedelta(minutes=30), signer=signer, where=tmp_path, fetch_=fetch) is None
    retried = reconcile.daily(KEY, next_day + timedelta(minutes=61), signer=signer, where=tmp_path, fetch_=fetch)
    # The read returns the 24th's trade again; outside the 25th, it is neither matched nor reported.
    assert retried["day"] == "2026-10-25" and retried["ok"] and retried["venue"] == 0 and retried["venue_only"] == []
    assert reconcile.daily("", MORNING, signer=signer, where=tmp_path, fetch_=fetch) is None


def test_the_owner_page_states_the_latest_reconciliation(monkeypatch):
    monkeypatch.setenv(orders.MODE, "dry")
    monkeypatch.delenv(orders.KILL, raising=False)
    monkeypatch.setattr(orders, "branch_kill", None)
    empty = pd.DataFrame(columns=orders.COLUMNS)
    assert "Not reconciled against the venue's account activity yet." in orders.section(empty, MORNING)["notes"]
    done = {"day": DAY, "venue": 2, "ours": 2, "matched": 2, "differ": [], "venue_only": [], "ours_only": [],
            "busted": [], "ok": True}
    notes = orders.section(empty, MORNING, done)["notes"]
    assert any(n.startswith(f"Reconciled {DAY}") and n.endswith("everything agrees.") for n in notes)
    monkeypatch.setenv(orders.MODE, "")
    assert not any("econcil" in n for n in orders.section(empty, MORNING)["notes"])        # off: not mentioned


@pytest.mark.parametrize("hour, expected", [(5, None), (6, DAY)])
def test_due_waits_for_six_eastern(hour, expected):
    now = pd.Timestamp(f"2026-10-25 {hour:02d}:30", tz=reconcile.EASTERN).to_pydatetime()
    assert reconcile.due(pd.DataFrame(), now) == expected
