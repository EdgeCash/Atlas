"""The finish-line rule (atlas/polymarket/finish.py): the final signal, the positions, the settlement, the
live step's gate, and the worker's part."""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import pandas as pd

from atlas.live.store import Store
from atlas.polymarket import finish, source, worker
from atlas.testing import polymarket_us as us

NOW = datetime(2026, 10, 25, 3, 40, tzinfo=UTC)
START = "2026-10-25T00:00:00Z"
FINISHED = "2026-10-25T03:37:00Z"
TEAMS = [(us.team(i, f"Away {i}", f"Away {i}", f"a{i}"), us.team(100 + i, f"Home {i}", f"Home {i}", f"h{i}"))
         for i in range(1, 7)]


def _stub(i, bid, ask, *, ended=True, period="FT", live=False, status=us.OPEN):
    """An event as the league listing carries it: the moneyline (the away team the long side) and the venue's
    own state of the game."""
    away, home = TEAMS[i - 1]
    m = us.moneyline(i, "basketball", away, home, bid, ask, start=START, status=status,
                     side_ids=(f"{i}001", f"{i}002"), slug=f"aec-nba-g{i}")
    e = us.event(str(i), f"nba-g{i}", away, home, [m], start=START)
    return {**e, "ended": ended, "live": live, "period": period, "score": "101-99",
            "finishedTimestamp": FINISHED if ended else None}


EVENTS = {"nba": [
    _stub(1, 0.98, 0.99),                                   # away won: its ask 0.99, bid 0.98 - decided
    _stub(2, 0.01, 0.02),                                   # home won: its ask 1 - 0.01 = 0.99, bid 0.98 - decided
    _stub(3, 0.98, 0.99, ended=False, period="End P3", live=True),   # end of regulation: not over
    _stub(4, 0.99, 0.995),                                  # away won, but its ask 0.995 is over the ceiling
    _stub(5, 0.93, 0.95),                                   # away won at 0.95: the wider band, not decided
    _stub(6, 0.98, 0.99, status="MARKET_STATUS_CLOSED"),    # not accepting orders
]}


def _quotes(events=EVENTS):
    return source.capture(NOW, events=events)


def test_the_venue_says_a_game_is_over_by_its_flag_or_full_time_and_never_at_the_end_of_regulation():
    assert finish.venue_final({"ended": True, "period": "Q4"})
    assert finish.venue_final({"ended": False, "period": "FT"}) and finish.venue_final({"period": "vft"})
    for period in ("End P3", "End Q4", "OT", "Q4", "HT", "NS", ""):
        assert not finish.venue_final({"ended": False, "period": period})
    assert set(finish.finals(EVENTS)) == {"1", "2", "4", "5", "6"}
    assert finish.pending(EVENTS) == 4                      # over, with the moneyline still open
    assert finish.decided(0.99, 0.98) and not finish.decided(0.995, 0.99) and not finish.decided(0.95, 0.93)
    assert not finish.decided(float("nan"), 0.98)


def test_a_position_is_taken_on_the_decided_side_once_with_its_depth_and_distance_from_the_finish():
    reads = []
    depth = lambda slug, long: reads.append((slug, long)) or {"ask_shares": 250.0}  # noqa: E731
    record, added = finish.take(pd.DataFrame(), _quotes(), EVENTS, NOW, depth=depth)
    by = record.set_index("event_id")
    assert added == 3 and set(by.index) == {"1", "2", "5"}
    one, two, five = by.loc["1"], by.loc["2"], by.loc["5"]
    assert one["side"] == "away" and bool(one["long"]) and one["ask"] == 0.99 and bool(one["decided"])
    assert two["side"] == "home" and not bool(two["long"]) and two["ask"] == 0.99 and bool(two["decided"])
    assert five["ask"] == 0.95 and not bool(five["decided"])
    assert math.isclose(one["cost"], 0.99 + 0.0695 * 0.99 * 0.01) and one["ask_shares"] == 250.0
    assert one["minutes_after_finish"] == 3.0 and one["period"] == "FT" and one["score"] == "101-99"
    assert set(reads) == {("aec-nba-g1", True), ("aec-nba-g2", False), ("aec-nba-g5", True)}
    # The same tick again: nothing new.
    again, added = finish.take(record, _quotes(), EVENTS, NOW + timedelta(seconds=45), depth=depth)
    assert added == 0 and len(again) == 3
    # No game over, no quotes: nothing.
    assert finish.take(record, _quotes(), {"nba": [EVENTS["nba"][2]]}, NOW)[1] == 0
    assert finish.take(record, pd.DataFrame(), EVENTS, NOW)[1] == 0


def test_the_settlement_grades_each_position_with_the_minutes_it_was_held(monkeypatch):
    monkeypatch.delenv("ATLAS_OFFLINE", raising=False)
    record, _ = finish.take(pd.DataFrame(), _quotes(), EVENTS, NOW, depth=lambda *a: {})
    paid = {"aec-nba-g1": 1.0, "aec-nba-g2": 0.0, "aec-nba-g5": float("nan")}   # game 5 not settled yet
    out, graded = finish.grade(record, NOW + timedelta(minutes=12), fetch=lambda slug: paid[slug])
    by = out.set_index("event_id")
    assert graded == 2
    assert by.loc["1", "won"] == 1.0 and math.isclose(by.loc["1", "profit"], 1.0 - by.loc["1", "cost"])
    assert by.loc["2", "payout"] == 1.0 and by.loc["2", "won"] == 1.0                # the home side, short
    assert by.loc["1", "minutes_to_settle"] == 12.0 and pd.isna(by.loc["5", "payout"])
    # A settlement that went the other way: the whole cost lost.
    out2, _ = finish.grade(record, NOW, fetch=lambda slug: 0.0)
    assert out2.set_index("event_id").loc["1", "profit"] < -0.99
    s = finish.summary(out, by=("sport",)).iloc[0]
    assert s["taken"] == 3 and s["settled"] == 2 and s["win_rate"] == 1.0 and s["minutes_to_settle"] == 12.0
    sec = finish.section(out, NOW)
    assert sec["tab"] == finish.TAB and "2 of 3 settled" in sec["title"] and len(sec["tables"]) == 3


def test_only_decided_positions_go_to_the_live_step_and_only_when_the_rule_is_named(monkeypatch):
    from atlas.polymarket import orders, positions

    placed = []
    monkeypatch.setattr(orders, "place", lambda pos, passphrase, now, **kw: placed.append((pos, kw)))
    monkeypatch.setenv(orders.MODE, "dry")
    record, _ = finish.take(pd.DataFrame(), _quotes(), EVENTS, NOW, depth=lambda *a: {})
    finish.order(record, "key", NOW)
    (pos, kw), = placed
    assert kw == {"rule": "finish"} and list(pos.columns) == positions.COLUMNS
    assert sorted(pos["position_id"]) == ["fin:1001", "fin:2002"] and (pos["stake"] == 1.0).all()
    monkeypatch.setenv(orders.MODE, "")
    finish.order(record, "key", NOW)
    assert len(placed) == 1                                                        # off: nothing
    monkeypatch.delenv(orders.RULES, raising=False)
    assert "finish" not in orders.rules()                                          # opt-in, never by default
    monkeypatch.setenv(orders.RULES, "favorites,finish")
    assert orders.rules() == ("favorites", "finish")


def test_the_live_step_gets_the_markets_tick_so_a_half_cent_ask_is_ordered_at_itself(monkeypatch):
    # College football ticks at half a cent: a 0.985 ask on either side is ordered at 0.985 on the long side's
    # grid (0.015 for the short), not rounded to the cent where it would sit under the ask and never fill.
    from atlas.polymarket import account, orders

    placed = []
    monkeypatch.setattr(orders, "place", lambda pos, passphrase, now, **kw: placed.append(pos))
    monkeypatch.setenv(orders.MODE, "dry")
    away, home = TEAMS[0]
    events = {"ncaaf": [{**us.event("7", "cfb-g7", away, home, [
        us.moneyline(7, "football", away, home, 0.015, 0.02, start=START, side_ids=("7001", "7002"),
                     slug="aec-cfb-g7", tick=0.005)], start=START), "ended": True, "live": False, "period": "FT",
        "score": "10-31", "finishedTimestamp": FINISHED}]}
    record, added = finish.take(pd.DataFrame(), source.capture(NOW, events=events), events, NOW, depth=lambda *a: {})
    assert added == 1 and record["tick"].iloc[0] == 0.005
    finish.order(record, "key", NOW)
    (pos,) = placed
    row = next(pos.itertuples(index=False))
    assert row.tick == 0.005 and account.order(row, 10)["price"]["value"] == "0.015"


def test_two_copies_of_the_record_merge_into_one_position_per_contract_keeping_the_grade(monkeypatch):
    monkeypatch.delenv("ATLAS_OFFLINE", raising=False)
    record, _ = finish.take(pd.DataFrame(), _quotes(), EVENTS, NOW, depth=lambda *a: {})
    graded, _ = finish.grade(record, NOW + timedelta(minutes=5), fetch=lambda slug: 1.0)
    later = record.assign(formed_at=(NOW + timedelta(minutes=1)).isoformat())
    merged = finish.merge(later, graded, record)
    assert len(merged) == 3 and pd.to_numeric(merged["payout"]).notna().all()
    assert (merged["formed_at"] == record["formed_at"].iloc[0]).all()               # the first taken
    assert finish.clean(pd.DataFrame([{"formed_at": "=======", "token_id": None}])).empty


def test_the_worker_runs_the_rule_each_tick_and_keeps_its_quick_pace_while_games_await_settlement(tmp_path, monkeypatch):
    monkeypatch.setenv("ATLAS_OFFLINE", "1")
    store = Store.open(tmp_path / "tracking")
    out = worker.tick(store, NOW, None, events=EVENTS)
    assert out["added"] >= 3 and out["finish_open"] == 3
    assert out["live"] == 1 + 4                    # the End P3 game in play, and four over but unsettled
    assert len(store.read(finish.TABLE)) == 3
    again = worker.tick(store, NOW + timedelta(seconds=45), None, events=EVENTS)
    assert len(store.read(finish.TABLE)) == 3 and again["finish_open"] == 3
    assert "tracking/finish.csv" in worker.FILES


def test_a_record_read_back_from_its_csv_is_graded(tmp_path, monkeypatch):
    # Read back with no settlement yet, settled_at is a column of blank floats; pandas 3 refuses text in it.
    monkeypatch.delenv("ATLAS_OFFLINE", raising=False)
    store = Store.open(tmp_path / "tracking")
    record, _ = finish.take(pd.DataFrame(), _quotes(), EVENTS, NOW, depth=lambda *a: {})
    store.write(finish.TABLE, record)
    graded, n = finish.grade(store.read(finish.TABLE), NOW + timedelta(minutes=5), fetch=lambda slug: 1.0)
    assert n == 3 and graded["settled_at"].notna().all()
