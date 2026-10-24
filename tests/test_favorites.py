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
           slug="m1", side="home", event="e1", spread=0.02):
    return {**dict.fromkeys(source.QUOTE_COLUMNS), "captured_at": NOW.isoformat(), "sport": sport, "game_id": "901",
            "event_id": event, "event_slug": f"nba-{event}", "game_start": start, "away": "LAL", "home": "BOS",
            "market_id": slug, "market_slug": slug, "token_id": token, "market": market, "side": side, "long": long,
            "line": float("nan"), "bid": ask - spread, "ask": ask, "mid": ask - spread / 2, "spread": spread, "liquidity": 500.0,
            "fee_rate": 0.0695, "accepting": accepting}


def test_a_position_is_taken_at_each_thresholds_first_crossing_and_never_revised():
    q = pd.DataFrame([_quote("t1", 0.86), _quote("t2", 0.14, long=False, side="away"), _quote("t3", 0.91, accepting=False),
                      _quote("t4", 0.99), _quote("t5", 0.82, start="2026-10-25T00:00:00Z", event="e2", slug="m2"),
                      _quote("t6", 0.95, market="spread", slug="m3"),
                      # An ask with nothing near it on the other side is an empty book, not a price: declined,
                      # as is a quote with no spread to read.
                      _quote("t7", 0.90, slug="m4", spread=0.05), _quote("t8", 0.90, slug="m5", spread=float("nan"))])
    record, added = favorites.take(pd.DataFrame(columns=favorites.COLUMNS), q, NOW)
    assert added == 3 and list(record.columns) == favorites.COLUMNS
    by = record.set_index(["token_id", "threshold"])
    assert set(by.index) == {("t1", 0.80), ("t1", 0.85), ("t5", 0.80)}   # 0.14 no, not accepting no, 0.99 no, a spread no, wide no
    assert favorites.MAX_SPREAD == 0.04
    # At the bar exactly, the crossing is taken.
    at_bar = pd.DataFrame([_quote("t9", 0.90, slug="m6", spread=0.04)])
    assert favorites.take(record, at_bar, NOW)[1] == 3
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
    assert sec["title"] == "Poly Snipe: the favorites rule (11 of 12 positions graded)" and sec["tab"] == "Poly Snipe"
    assert len(sec["tables"]) == 4 and sec["tables"][0]["title"] == "By phase and threshold"
    assert sec["tables"][0]["rows"][0][:3] == ["in play", "85%", "11 / 10"] and json.dumps(sec)
    assert sec["tables"][1]["title"].startswith("By stage of the game") and sec["tables"][1]["rows"][0][0] == "in play early"
    assert sec["tables"][2]["title"].startswith("By sport, at the 80%")
    assert sec["tables"][3]["title"] == "Latest positions (12 sides)" and len(sec["tables"][3]["rows"]) == 12
    assert {r[5] for r in sec["tables"][3]["rows"]} == {"won", "lost", "pending"}
    text = favorites.text(record)
    assert "| in play | 85% | 11 | 10 | 90.0% | 87.0% | +3.0 ± 9.5 | " in text
    assert favorites.text(pd.DataFrame(columns=favorites.COLUMNS)) == "No favorites positions yet."


def test_refresh_keeps_the_record_in_the_store(tmp_path, monkeypatch):
    from atlas.live.store import Store

    monkeypatch.setenv("ATLAS_OFFLINE", "1")
    store = Store.open(tmp_path / "tracking")
    q = pd.DataFrame([_quote("t1", 0.86), _quote("t2", 0.5), _quote("t7", 0.81, start="2026-10-25T00:00:00Z", slug="m7")])
    record, sec = favorites.refresh(store, q, NOW)
    assert len(record) == 3 and len(store.read("favorites")) == 3
    assert sec["title"] == "Poly Snipe: the favorites rule (0 of 3 positions graded)"
    rows = sec["tables"][-1]["rows"]
    assert sec["tables"][-1]["title"] == "Latest positions (2 sides)" and {r[5] for r in rows} == {"pending"}
    by = {r[0][0] + r[1] + r[2]: r for r in rows}
    assert by["LAL @ BOS" + "home" + "0.86"][3] == "in play, 60'" and by["LAL @ BOS" + "home" + "0.81"][3] == "pregame, 23.0h out"
    assert rows[0][4].startswith("Fri") and rows[0][0] == ["LAL @ BOS", "NBA"]
    record, sec = favorites.refresh(store, q, NOW + timedelta(minutes=15))
    assert len(record) == 3
    empty, sec = favorites.refresh(store, pd.DataFrame(columns=source.QUOTE_COLUMNS), NOW)
    assert len(empty) == 3 and json.dumps(sec)


def test_the_rules_positions_reach_the_live_step_at_the_order_threshold(tmp_path, monkeypatch):
    from atlas.live.store import Store
    from atlas.polymarket import orders, positions

    monkeypatch.setenv("ATLAS_OFFLINE", "1")
    monkeypatch.setenv(orders.MODE, "dry")
    monkeypatch.setenv(favorites.ORDER_PHASE, "any")        # the mechanics, whatever the phase; late is the default
    store = Store.open(tmp_path / "tracking")
    placed = []
    monkeypatch.setattr(orders, "place", lambda pos, passphrase, now, **kw: placed.append((pos, passphrase, kw)))
    q = pd.DataFrame([_quote("t1", 0.86), _quote("t2", 0.81, slug="m2"), _quote("t3", 0.5, slug="m3")])
    favorites.refresh(store, q, NOW)                                                   # no key: nothing placed
    assert not placed
    store2 = Store.open(tmp_path / "tracking2")
    record, _ = favorites.refresh(store2, q, NOW, passphrase="key")
    assert len(placed) == 1
    pos, passphrase, kw = placed[0]
    assert passphrase == "key" and kw == {"rule": "favorites"} and list(pos.columns) == positions.COLUMNS
    assert list(pos["position_id"]) == ["fav:t1:0.85"] and pos["ask"].iloc[0] == 0.86 and pos["stake"].iloc[0] == 1.0
    assert pos["day"].iloc[0] == "2026-10-23" and pos["kickoff"].iloc[0] == "2026-10-24T00:00:00Z" and pos["label"].iloc[0] == "LAL @ BOS"
    assert bool(pos["long"].iloc[0]) and pos["market_slug"].iloc[0] == "m1" and pos["sport"].iloc[0] == "nba"
    # Nothing new on the next poll, nothing placed; off, nothing placed either.
    favorites.refresh(store2, q, NOW + timedelta(minutes=15), passphrase="key")
    assert len(placed) == 1
    monkeypatch.delenv(orders.MODE)
    favorites.refresh(store2, pd.DataFrame([_quote("t9", 0.9, slug="m9")]), NOW + timedelta(minutes=30), passphrase="key")
    assert len(placed) == 1
    assert favorites.as_positions(pd.DataFrame(columns=favorites.COLUMNS)).empty


def _games(rows):
    return pd.DataFrame([{"game_id": "901", "sport": "nba", "status": "STATUS_IN_PROGRESS", **r} for r in rows])


def test_each_position_carries_where_the_game_stood_and_whether_it_was_late():
    q = pd.DataFrame([_quote("t1", 0.86), _quote("t2", 0.90, start="2026-10-25T00:00:00Z", slug="m2")])
    q.loc[1, "game_id"] = "902"                                                       # tomorrow's game, not on the board
    record, _ = favorites.take(pd.DataFrame(columns=favorites.COLUMNS), q, NOW, _games([{"period": 4, "clock": "3:21"}]))
    by = record.set_index(["token_id", "threshold"])
    late = by.loc[("t1", 0.85)]
    assert late["period"] == 4.0 and late["clock"] == "3:21" and bool(late["late"])
    pre = by.loc[("t2", 0.85)]
    assert pd.isna(pre["period"]) and not bool(pre["late"])                         # pregame: no state, not late
    early, _ = favorites.take(pd.DataFrame(columns=favorites.COLUMNS), q, NOW, _games([{"period": 2, "clock": "5:00"}]))
    assert not bool(early.set_index(["token_id", "threshold"]).loc[("t1", 0.85)]["late"])
    overtime, _ = favorites.take(pd.DataFrame(columns=favorites.COLUMNS), q, NOW, _games([{"period": 5, "clock": "2:00"}]))
    assert bool(overtime.set_index(["token_id", "threshold"]).loc[("t1", 0.85)]["late"])
    none, _ = favorites.take(pd.DataFrame(columns=favorites.COLUMNS), q, NOW, None)
    assert pd.isna(none["period"]).all() and not none["late"].map(bool).any()
    assert favorites.is_late("nhl", 3, "in_play") and not favorites.is_late("nhl", 2, "in_play")
    assert not favorites.is_late("nba", 4, "pregame") and not favorites.is_late("mls", 2, "in_play")
    assert list(favorites.stage(record)) == ["in play late", "in play late", "pregame", "pregame", "pregame"][:len(record)]
    s = favorites.summary(record, by=("stage", "threshold"))
    assert set(s["stage"]) == {"in play late", "pregame"}
    sec = favorites.section(record, NOW)
    row = next(r for r in sec["tables"][-1]["rows"] if r[2] == "0.86")
    assert row[3] == "in play, P4 3:21"


def test_the_late_switch_confines_the_live_step(tmp_path, monkeypatch):
    from atlas.live.store import Store
    from atlas.polymarket import orders

    monkeypatch.setenv("ATLAS_OFFLINE", "1")
    monkeypatch.setenv(orders.MODE, "dry")
    monkeypatch.delenv(favorites.ORDER_PHASE, raising=False)                         # late is the default
    placed = []
    monkeypatch.setattr(orders, "place", lambda pos, passphrase, now, **kw: placed.append(pos))
    store = Store.open(tmp_path / "tracking")
    store.write("games", pd.DataFrame([{"game_id": "901", "sport": "nba", "status": "STATUS_IN_PROGRESS", "period": 2,
                                        "clock": "5:00", "kickoff": "2026-10-24T00:00:00Z"}]))
    favorites.refresh(store, pd.DataFrame([_quote("t1", 0.86)]), NOW, passphrase="key")
    assert not placed                                                                # second quarter: held back
    store.write("games", pd.DataFrame([{"game_id": "901", "sport": "nba", "status": "STATUS_IN_PROGRESS", "period": 4,
                                        "clock": "1:00", "kickoff": "2026-10-24T00:00:00Z"}]))
    favorites.refresh(store, pd.DataFrame([_quote("t2", 0.88, slug="m2")]), NOW + timedelta(minutes=15), passphrase="key")
    assert len(placed) == 1 and list(placed[0]["position_id"]) == ["fav:t2:0.85"]
    monkeypatch.setenv(favorites.ORDER_PHASE, "any")
    favorites.refresh(store, pd.DataFrame([_quote("t3", 0.87, slug="m3", start="2026-10-25T00:00:00Z")]),
                      NOW + timedelta(minutes=30), passphrase="key")
    assert len(placed) == 2                                                          # any phase: pregame goes too
