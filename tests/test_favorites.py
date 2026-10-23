"""The favorites rule (atlas/polymarket/favorites.py): positions taken at each threshold's first crossing,
graded by the venue's settlement, and summed against the break-even rate."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from atlas.polymarket import favorites, source

NOW = datetime(2026, 10, 24, 1, 0, tzinfo=UTC)


def _quote(token, ask, *, start="2026-10-24T00:00:00Z", long=True, accepting=True, sport="nba", market="moneyline",
           slug="m1", side="home", event="e1"):
    return {**dict.fromkeys(source.QUOTE_COLUMNS), "captured_at": NOW.isoformat(), "sport": sport, "game_id": "901",
            "event_id": event, "event_slug": f"nba-{event}", "game_start": start, "away": "LAL", "home": "BOS",
            "market_id": slug, "market_slug": slug, "token_id": token, "market": market, "side": side, "long": long,
            "line": float("nan"), "bid": ask - 0.02, "ask": ask, "mid": ask - 0.01, "spread": 0.02, "liquidity": 500.0,
            "fee_rate": 0.0695, "accepting": accepting}


def test_a_position_is_taken_at_each_thresholds_first_crossing_and_never_revised():
    q = pd.DataFrame([_quote("t1", 0.86), _quote("t2", 0.14, long=False, side="away"), _quote("t3", 0.91, accepting=False),
                      _quote("t4", 0.99), _quote("t5", 0.82, start="2026-10-25T00:00:00Z", event="e2", slug="m2"),
                      _quote("t6", 0.95, market="spread", slug="m3")])
    record, added = favorites.take(pd.DataFrame(columns=favorites.COLUMNS), q, NOW)
    assert added == 3 and list(record.columns) == favorites.COLUMNS
    by = record.set_index(["token_id", "threshold"])
    assert set(by.index) == {("t1", 0.80), ("t1", 0.85), ("t5", 0.80)}   # 0.14 no, not accepting no, 0.99 no, a spread no
    one = by.loc[("t1", 0.85)]
    assert one["phase"] == "in_play" and one["minutes_in"] == 60.0 and one["ask"] == 0.86 and one["long"]
    assert one["fee"] == pytest.approx(0.0695 * 0.86 * 0.14) and one["cost"] == pytest.approx(0.86 + one["fee"])
    assert one["label"] == "LAL @ BOS" and pd.isna(one["payout"]) and pd.isna(one["won"])
    assert by.loc[("t5", 0.80)]["phase"] == "pregame" and by.loc[("t5", 0.80)]["minutes_in"] < 0
    # Later, higher: only the new thresholds; the first crossing's ask stands.
    later = pd.DataFrame([_quote("t1", 0.93), _quote("t5", 0.82, start="2026-10-25T00:00:00Z", event="e2", slug="m2")])
    record, added = favorites.take(record, later, NOW + timedelta(minutes=15))
    assert added == 1 and record.set_index(["token_id", "threshold"]).loc[("t1", 0.90)]["ask"] == 0.93
    assert record.set_index(["token_id", "threshold"]).loc[("t1", 0.85)]["ask"] == 0.86
    assert favorites.take(record, pd.DataFrame(columns=source.QUOTE_COLUMNS), NOW)[1] == 0
    assert favorites.candidates(None, NOW).empty


def test_settlement_grades_positions_once_the_game_is_gone(monkeypatch):
    monkeypatch.delenv("ATLAS_OFFLINE", raising=False)
    q = pd.DataFrame([_quote("t1", 0.86), _quote("t2", 0.84, long=False, side="away", slug="m2"),
                      _quote("t3", 0.90, start="2026-10-24T06:00:00Z", slug="m3", event="e3")])
    record, _ = favorites.take(pd.DataFrame(columns=favorites.COLUMNS), q, NOW)
    reads = []

    def fetch(slug):
        reads.append(slug)
        return {"m1": 1.0, "m2": 1.0, "m3": 1.0}[slug]            # m2's long side won: the short position lost

    # Too soon: nothing read.
    assert favorites.grade(record, NOW + timedelta(hours=1), fetch=fetch)["won"].isna().all() and not reads
    out = favorites.grade(record, NOW + timedelta(hours=4), fetch=fetch)
    assert sorted(reads) == ["m1", "m2"]                                            # m3 is not four hours gone
    by = out.set_index(["token_id", "threshold"])
    t1, t2, t3 = by.loc[("t1", 0.85)], by.loc[("t2", 0.80)], by.loc[("t3", 0.90)]
    assert t1["won"] == 1.0 and t1["payout"] == 1.0 and t1["profit"] == pytest.approx(1.0 - t1["cost"])
    assert t2["won"] == 0.0 and t2["payout"] == 0.0 and t2["profit"] == pytest.approx(-t2["cost"])
    assert pd.isna(t3["won"]) and str(t1["graded_at"]).startswith("2026-10-24T05:00")
    # Pending stays pending when the venue has not settled, and a graded row is not read again.
    again = favorites.grade(out, NOW + timedelta(hours=8), fetch=lambda s: float("nan")).set_index(["token_id", "threshold"])
    assert pd.isna(again.loc[("t3", 0.90), "won"]) and again.loc[("t2", 0.80), "won"] == 0.0
    limited = favorites.grade(record, NOW + timedelta(hours=4), fetch=fetch, limit=1)
    assert limited["won"].notna().sum() == 2                                        # one market, two thresholds
    monkeypatch.setenv("ATLAS_OFFLINE", "1")
    assert favorites.grade(record, NOW + timedelta(hours=4), fetch=fetch)["won"].isna().all()


def test_the_summary_is_the_win_rate_against_the_break_even_rate():
    rows = []
    for i in range(10):
        rows.append({**dict.fromkeys(favorites.COLUMNS), "token_id": f"t{i}", "threshold": 0.85, "phase": "in_play",
                     "sport": "nba", "ask": 0.86, "cost": 0.87, "won": 1.0 if i < 9 else 0.0,
                     "profit": (1.0 - 0.87) if i < 9 else -0.87})
    rows.append({**dict.fromkeys(favorites.COLUMNS), "token_id": "p", "threshold": 0.85, "phase": "in_play",
                 "sport": "nba", "ask": 0.86, "cost": 0.87})                        # pending
    rows.append({**dict.fromkeys(favorites.COLUMNS), "token_id": "q", "threshold": 0.80, "phase": "pregame",
                 "sport": "nfl", "ask": 0.81, "cost": 0.82, "won": 0.0, "profit": -0.82})
    record = pd.DataFrame(rows, columns=favorites.COLUMNS)
    s = favorites.summary(record).set_index(["phase", "threshold"])
    live = s.loc[("in_play", 0.85)]
    assert live["taken"] == 11 and live["graded"] == 10 and live["win_rate"] == pytest.approx(0.9)
    assert live["break_even"] == pytest.approx(0.87) and live["edge"] == pytest.approx(0.03)
    assert live["se"] == pytest.approx((0.9 * 0.1 / 10) ** 0.5)
    assert live["profit_per_dollar"] == pytest.approx((9 * 0.13 - 0.87) / 8.7)
    pre = s.loc[("pregame", 0.80)]
    assert pre["graded"] == 1 and pre["win_rate"] == 0.0 and pd.isna(pre["se"])
    assert favorites.summary(pd.DataFrame(columns=favorites.COLUMNS)).empty
    sec = favorites.section(record, NOW)
    assert sec["title"] == "Favorites rule (11 of 12 graded)" and sec["tab"] == "Favorites" and len(sec["tables"]) == 2
    assert sec["tables"][0]["rows"][0][:3] == ["in play", "85%", "11 / 10"] and json.dumps(sec)
    assert sec["tables"][1]["title"].startswith("By sport, at the 80%")
    text = favorites.text(record)
    assert "| in play | 85% | 11 | 10 | 90.0% | 87.0% | +3.0 ± 9.5 | " in text
    assert favorites.text(pd.DataFrame(columns=favorites.COLUMNS)) == "No favorites positions yet."


def test_refresh_keeps_the_record_in_the_store(tmp_path, monkeypatch):
    from atlas.live.store import Store

    monkeypatch.setenv("ATLAS_OFFLINE", "1")
    store = Store.open(tmp_path / "tracking")
    q = pd.DataFrame([_quote("t1", 0.86), _quote("t2", 0.5)])
    record, sec = favorites.refresh(store, q, NOW)
    assert len(record) == 2 and len(store.read("favorites")) == 2 and sec["title"] == "Favorites rule (0 of 2 graded)"
    record, sec = favorites.refresh(store, q, NOW + timedelta(minutes=15))
    assert len(record) == 2
    empty, sec = favorites.refresh(store, pd.DataFrame(columns=source.QUOTE_COLUMNS), NOW)
    assert len(empty) == 2 and json.dumps(sec)
