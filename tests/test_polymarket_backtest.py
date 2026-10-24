"""The favorites rule replayed on the venue's tape: the games read, the crossings, the stale fills, the summary."""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import pandas as pd

from atlas.polymarket import backtest

START = pd.Timestamp("2026-01-10T00:00:00Z")
FINISH = START + timedelta(minutes=150)


def _closed_event(eid="39470", slug="nba-chi-mil-2026-01-09", result=("1", "0"), long_team=1, ordering=True):
    teams = [{"id": 1, "name": "Chicago", "safeName": "Chicago", "alias": "Bulls", "ordering": "away" if ordering else None},
             {"id": 2, "name": "Milwaukee", "safeName": "Milwaukee", "alias": "Bucks", "ordering": "home" if ordering else None}]
    return {"id": eid, "slug": slug, "title": "Chicago vs. Milwaukee", "startTime": START.isoformat(),
            "finishedTimestamp": FINISH.isoformat(), "closed": True, "ended": True, "teams": teams,
            "markets": [{"id": "9", "slug": f"aec-{slug}", "sportsMarketType": "moneyline", "feeCoefficient": 0.0695,
                         "gameStartTime": START.isoformat(),
                         "marketSides": [{"id": "a", "long": True, "teamId": long_team, "price": result[0]},
                                         {"id": "b", "long": False, "teamId": 3 - long_team, "price": result[1]}]},
                        {"id": "10", "slug": "x", "sportsMarketType": "futures", "marketSides": []}]}


def _tape(long_path: list[float], *, before: list[float] | None = None, step: int = 1) -> pd.DataFrame:
    """A minute-by-minute tape: ``before`` pregame asks ending at the start, then ``long_path`` in play, the
    short side's ask one less the long's plus a cent of spread."""
    before = before if before is not None else [0.60] * 5
    at = [START - timedelta(minutes=step * (len(before) - i)) for i in range(len(before))]
    at += [START + timedelta(minutes=step * i) for i in range(len(long_path))]
    long_ = [*before, *long_path]
    return pd.DataFrame({"at": at, "long": long_, "short": [round(1.01 - x, 2) for x in long_]})


def test_a_closed_event_is_read_as_a_game_with_its_sides_and_settled_price():
    g = backtest.game(_closed_event())
    assert g["league"] == "nba" and g["away"] == "Chicago" and g["home"] == "Milwaukee" and g["label"] == "Chicago @ Milwaukee"
    assert g["long_side"] == "away" and g["result_long"] == 1.0 and g["fee_rate"] == 0.0695
    assert g["market_slug"] == "aec-nba-chi-mil-2026-01-09" and g["finished"] == FINISH
    # The home team as the long side, the teams listed without an ordering, a void result.
    g = backtest.game(_closed_event(long_team=2, ordering=False, result=("0.5", "0.5")))
    assert g["long_side"] == "home" and g["result_long"] == 0.5
    assert backtest.game({"id": "1", "slug": "nba-x", "teams": [], "markets": []}) is None
    assert backtest.league_of({"slug": "aec-cfb-osu-mich-2025-11-29"}) == "cfb"
    # The cache keeps the event cut down to what is read, and the game read from it is the same.
    thin = backtest.slim(_closed_event())
    assert set(thin) <= {*backtest.EVENT_FIELDS, "markets"} and len(thin["markets"]) == 1
    assert backtest.game(thin) == backtest.game(_closed_event())
    frame = backtest.games([_closed_event(), _closed_event(eid="2", slug="cbb-duke-unc-2026-02-01")], ("nba",))
    assert list(frame["league"]) == ["nba"]


def test_crossings_take_the_first_minute_at_or_over_each_threshold_in_each_phase():
    g = backtest.game(_closed_event())
    # Pregame the Bulls sit at 0.60; in play they climb to 0.86 at minute 3, 0.91 at 5, 0.96 at 7, then settle.
    path = [0.70, 0.75, 0.80, 0.86, 0.88, 0.91, 0.93, 0.96, 0.97, 0.97, 1.0, 1.0]
    rows = pd.DataFrame(backtest.crossings(g, _tape(path, step=10)))
    long_ = rows[rows["long"]]
    assert set(long_["phase"]) == {"in_play"}                      # never over 0.80 before the start
    by = long_.set_index("threshold")
    assert by.loc[0.80, "minutes_in"] == 20 and by.loc[0.80, "price"] == 0.80
    assert by.loc[0.85, "minutes_in"] == 30 and by.loc[0.85, "price"] == 0.86
    assert by.loc[0.90, "price"] == 0.91 and by.loc[0.95, "price"] == 0.96 and by.loc[0.97, "price"] == 0.97
    assert by.loc[0.85, "minutes_left"] == 120 and by.loc[0.85, "bucket"] == "over 60 min left"
    assert by.loc[0.97, "minutes_left"] == 70 and by.loc[0.97, "side"] == "away"
    assert (long_["won"] == 1.0).all()
    fee = 0.0695 * 0.86 * 0.14
    assert math.isclose(by.loc[0.85, "cost"], 0.86 + fee) and math.isclose(by.loc[0.85, "profit"], 1 - 0.86 - fee)
    assert math.isclose(by.loc[0.85, "spread"], 0.01, abs_tol=1e-6) and by.loc[0.85, "price_at_start"] == 0.60
    # The Bucks' ask never reached 0.80 (one less 0.70 plus a cent is 0.31 at best, pregame 0.41).
    assert not rows[~rows["long"]].shape[0]
    # A game the venue has not settled, or with no tape, gives nothing.
    assert backtest.crossings({**g, "result_long": float("nan")}, _tape(path)) == []
    assert backtest.crossings(g, pd.DataFrame(columns=["at", "long", "short"])) == []


def test_a_pregame_crossing_is_its_own_position_and_a_loser_is_graded_so():
    g = backtest.game(_closed_event(result=("0", "1")))                     # the Bulls (long) lost
    rows = pd.DataFrame(backtest.crossings(g, _tape([0.90, 0.90, 0.0, 0.0], before=[0.70, 0.82, 0.86])))
    pre = rows[(rows["phase"] == "pregame") & rows["long"]].set_index("threshold")
    assert pre.loc[0.80, "price"] == 0.82 and pre.loc[0.85, "price"] == 0.86 and pre.loc[0.80, "bucket"] == "pregame"
    live = rows[(rows["phase"] == "in_play") & rows["long"]].set_index("threshold")
    assert set(live.index) == {0.80, 0.85, 0.90} and (live["won"] == 0.0).all()
    assert math.isclose(live.loc[0.90, "profit"], -(0.90 + 0.0695 * 0.9 * 0.1))
    # The Bucks' settled ask of 1.0 is over the ceiling, so no position is taken on a decided market.
    assert not rows[~rows["long"]].shape[0]


def test_a_stale_limit_fills_only_when_the_ask_has_not_risen():
    idx = pd.DatetimeIndex([START + timedelta(minutes=i) for i in range(6)])
    end = START + timedelta(minutes=10)
    rising = pd.Series([0.85, 0.87, 0.89, 0.91, 0.93, 0.95], index=idx)
    falling = pd.Series([0.85, 0.84, 0.82, 0.80, 0.78, 0.76], index=idx)
    flat = pd.Series([0.85] * 6, index=idx)
    assert math.isnan(backtest.stale_fill(rising, idx[0], 0.85, 1, end))
    assert backtest.stale_fill(falling, idx[0], 0.85, 1, end) == 0.84          # fills at the lower ask
    assert backtest.stale_fill(falling, idx[0], 0.85, 5, end) == 0.76
    assert backtest.stale_fill(flat, idx[0], 0.85, 1, end) == 0.85
    assert math.isnan(backtest.stale_fill(flat, idx[0], 0.85, 15, end))        # nothing on the tape that late
    settled = pd.Series([0.85, 1.0, 1.0], index=idx[:3])
    assert math.isnan(backtest.stale_fill(settled, idx[0], 0.85, 1, end))      # a settled market is no fill
    assert math.isnan(backtest.stale_fill(flat, idx[0], 0.85, 1, START))       # the game had ended


def test_the_summary_measures_the_rule_and_clusters_its_error_by_game():
    rows = []
    for game_id, won in (("g1", 1.0), ("g2", 1.0), ("g3", 0.0), ("g4", 1.0)):
        for t in (0.85, 0.90):
            px = t + 0.01
            rows.append({"event_id": game_id, "phase": "in_play", "threshold": t, "price": px, "fee": 0.0695 * px * (1 - px),
                         "cost": px + 0.0695 * px * (1 - px), "payout": won, "won": won,
                         "profit": won - px - 0.0695 * px * (1 - px), "fill_1": px - 0.01 if game_id != "g1" else float("nan")})
    p = pd.DataFrame(rows)
    s = backtest.summary(p).set_index(("phase", "threshold") and ["phase", "threshold"])
    r = s.loc[("in_play", 0.85)]
    assert r["taken"] == 4 and r["filled"] == 4 and r["win_rate"] == 0.75
    assert math.isclose(r["break_even"], 0.86 + 0.0695 * 0.86 * 0.14) and math.isclose(r["edge"], r["win_rate"] - r["break_even"])
    assert math.isclose(r["profit_per_dollar"], p[p["threshold"] == 0.85]["profit"].sum() / p[p["threshold"] == 0.85]["cost"].sum())
    # Clustered: the two thresholds of one game move together, so pooling them does not shrink the error.
    pooled = backtest.summary(p, by=("phase",)).iloc[0]
    one = backtest.summary(p[p["threshold"] == 0.85], by=("phase",)).iloc[0]
    assert pooled["taken"] == 8 and pooled["se"] > one["se"] / math.sqrt(2) * 1.2
    # At a latency the positions are the fills, at the price they filled at.
    s1 = backtest.summary(p, latency=1).set_index(["phase", "threshold"]).loc[("in_play", 0.85)]
    assert s1["taken"] == 4 and s1["filled"] == 3
    assert math.isclose(s1["break_even"], 0.85 + 0.0695 * 0.85 * 0.15) and math.isclose(s1["win_rate"], 2 / 3)
    assert backtest.summary(pd.DataFrame()).empty


def test_the_report_says_what_it_holds(tmp_path):
    g = backtest.game(_closed_event())
    gs = pd.DataFrame([g], columns=backtest.GAME_COLUMNS)
    positions = pd.DataFrame(backtest.crossings(g, _tape([0.70, 0.86, 0.91, 0.96, 1.0], before=[0.86] * 3)),
                             columns=backtest.POSITION_COLUMNS)
    text, tables = backtest.report(gs, positions, now=datetime(2026, 10, 24, tzinfo=UTC))
    assert "| NBA | 1 | 1 |" in text and "## In play, all leagues" in text and "## Before the game" in text
    assert {"in_play_by_time_left", "in_play_tight_by_time_left", "in_play_by_league", "in_play_by_latency",
            "pregame_by_league"} <= set(tables)
    assert "tight book" in text and tables["in_play_tight_by_time_left"]["taken"].sum() <= tables["in_play_by_time_left"]["taken"].sum()
    assert set(tables["in_play_by_latency"]["latency"]) == set(backtest.LATENCIES)
    out = backtest.write(gs, positions, reports=tmp_path, raw=tmp_path / "raw")
    assert out.read_text().splitlines()[4:] == text.splitlines()[4:]          # the same but for the build time
    assert (tmp_path / "tables" / "favorites_backtest_in_play_by_league.csv").exists()
    assert (tmp_path / "raw" / "favorites_backtest_positions.csv").exists()
    text, _ = backtest.report(gs, pd.DataFrame(columns=backtest.POSITION_COLUMNS))
    assert "No positions" in text


def test_the_closed_listing_is_read_to_its_end_in_pages_and_resumed_from_the_cache(tmp_path):
    # Forty-one hundred events, in pages that are not all full (the listing filters after it paginates), so
    # the walk advances by what each page held and dedupes by id; an empty page is the end.
    total = 4_100
    seen: list[int] = []

    def fetch(offset):
        seen.append(offset)
        n = backtest.PAGE - (1 if offset % 1500 == 0 else 0)
        return [{"id": str(i), "slug": f"nba-x-y-{i}"} for i in range(offset, min(offset + n, total))]

    cache = tmp_path / "closed.json"
    events = backtest.closed_events(cache=cache, fetch=fetch)
    assert len(events) == total and cache.exists()
    assert min(seen) == 0 and max(seen) >= total
    # A rerun starts near the end of the cache, not at the beginning, and keeps everything it had.
    seen.clear()
    again = backtest.closed_events(cache=cache, fetch=fetch)
    assert len(again) == total and min(seen) == total - backtest.OVERLAP
    seen.clear()
    backtest.closed_events(cache=cache, fetch=fetch, refresh=True)
    assert min(seen) == 0
