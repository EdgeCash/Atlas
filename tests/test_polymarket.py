"""Atlas on Polymarket: the quotes read and kept, the games matched, the contracts priced, the positions."""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pytest

from atlas.live import probability
from atlas.owner import crypto, sealed
from atlas.polymarket import match, page, positions, pricing, report, source
from atlas.testing import polymarket_us as us

KEY = "correct horse battery staple"
NOW = datetime(2026, 10, 24, 14, 4, tzinfo=UTC)                  # Saturday 10:04 ET
START = "2026-10-24 19:30:00+00"
KICKOFF = "2026-10-24T19:30Z"
NFL = source.LEAGUES["nfl"]
NCAAF = source.LEAGUES["ncaaf"]


CHIEFS = us.team(12, "Kansas City Chiefs", "KC Chiefs", "kc")
SEAHAWKS = us.team(26, "Seattle Seahawks", "SEA Seahawks", "sea")


def _event(eid="1001", slug="nfl-kc-sea-2026-10-24", away=CHIEFS, home=SEAHAWKS, markets=None):
    return us.event(eid, slug, away, home, markets if markets is not None else [
        us.moneyline(1, "football", away, home, 0.42, 0.43, start=START),
        us.spread(2, "football", away, home, -1.5, 0.39, 0.41, start=START),        # the Chiefs named, at -1.5
        us.spread(3, "football", home, away, -2.5, 0.41, 0.43, start=START),        # the Seahawks named, at -2.5
        us.total(4, "football", away, home, 44.5, 0.49, 0.51, start=START),
        us.total(5, "football", away, home, 50.5, 0.29, 0.31, start=START),
        us.prop(6, "football_player_passing_yards", "Patrick Mahomes", 250, 0.01, 0.97, team=away, start=START),
    ], start=START)


def _games():
    return pd.DataFrame([
        {"game_id": "401", "season": 2026, "week": 8, "kickoff": KICKOFF, "home_team": "Seattle Seahawks",
         "away_team": "Kansas City Chiefs", "home_team_id": 26, "away_team_id": 12, "status": "STATUS_SCHEDULED",
         "completed": False, "home_score": 0.0, "away_score": 0.0, "sport": "nfl"},
        {"game_id": "402", "season": 2026, "week": 8, "kickoff": KICKOFF, "home_team": "Texas Tech Red Raiders",
         "away_team": "Oklahoma State Cowboys", "home_team_id": 1, "away_team_id": 2, "status": "STATUS_SCHEDULED",
         "completed": False, "home_score": 0.0, "away_score": 0.0, "sport": "ncaaf"},
        {"game_id": "403", "season": 2026, "week": 8, "kickoff": KICKOFF, "home_team": "Texas Longhorns",
         "away_team": "Oklahoma Sooners", "home_team_id": 3, "away_team_id": 4, "status": "STATUS_SCHEDULED",
         "completed": False, "home_score": 0.0, "away_score": 0.0, "sport": "ncaaf"},
    ])


def _projections(margin=-3.0, total=47.0):
    return pd.DataFrame([{"game_id": 401, "sport": "nfl", "season": 2026, "week": 8, "kickoff": KICKOFF,
                          "margin_mean": margin, "margin_sd": 13.0, "total_mean": total, "total_sd": 13.0,
                          "total_over_shrink": 0.35, "total_over_sd": 13.0, "p_home": 0.41,
                          "model_version": "m1", "refreshed_at": "2026-10-24T08:00:00+00:00"}])


def _calibration(n=1200, k=1.0, seed=1, k_margin=None):
    """A record on which Atlas's claimed probability is worth ``k`` of itself against the close on totals,
    and ``k_margin`` (``k`` unless given) on margins."""
    def rows(market, share, seed):
        rng = np.random.default_rng(seed)
        claimed = rng.uniform(0.35, 0.65, n)
        won = (rng.uniform(size=n) < 0.5 + share * (claimed - 0.5)).astype(float)
        return pd.DataFrame({"game_id": range(n), "sport": "nfl", "season": 2024, "week": 1, "season_type": "regular",
                             "market": market, "abs_edge": rng.uniform(0.0, 12.0, n), "claimed": claimed, "won": won,
                             "kickoff": KICKOFF})
    total = rows("total", k, seed)
    margin = rows("margin", k if k_margin is None else k_margin, seed + 100).assign(game_id=lambda d: d["game_id"] + n)
    return pd.concat([total, margin], ignore_index=True)


# ---------------------------------------------------------------------------
# Reading the venue
# ---------------------------------------------------------------------------


def test_quotes_read_sides_lines_prices_and_fees_by_the_venues_conventions():
    q = source.quotes([_event()], NFL, NOW).set_index(["market", "side", "line"])
    assert len(q) == 10                                                          # the prop is not a game market
    ml = q.loc[("moneyline", "away", 0.0)]
    assert ml["bid"] == 0.42 and ml["ask"] == 0.43 and ml["mid"] == 0.425 and ml["long"]   # the away team is the long side
    home = q.loc[("moneyline", "home", 0.0)]
    assert home["bid"] == pytest.approx(0.57) and home["ask"] == pytest.approx(0.58) and home["mid"] == 0.575
    assert q.loc[("spread", "away", -1.5)]["mid"] == 0.40 and q.loc[("spread", "home", 1.5)]["mid"] == 0.60
    assert q.loc[("spread", "home", -2.5)]["mid"] == 0.42 and q.loc[("spread", "away", 2.5)]["mid"] == 0.58
    assert q.loc[("total", "over", 50.5)]["ask"] == 0.31 and q.loc[("total", "under", 50.5)]["ask"] == pytest.approx(0.71)
    assert (q["fee_rate"] == 0.0695).all() and (q["away"] == "Kansas City Chiefs").all() \
        and (q["home"] == "Seattle Seahawks").all()
    assert q["liquidity"].isna().all() and (q["spread"].round(3) == 0.02).sum() == 8      # depth is read from the book
    assert q["game_start"].iloc[0] == "2026-10-24T19:30:00+00:00" and q["captured_at"].iloc[0] == "2026-10-24T14:04:00+00:00"
    assert q["market_slug"].iloc[0] == "m1" and set(q.reset_index()["token_id"]) >= {"s1a", "s1b"}
    free = _event(markets=[us.moneyline(9, "football", CHIEFS, SEAHAWKS, 0.49, 0.51, fee=0.0)])
    assert (source.quotes([free], NFL, NOW)["fee_rate"] == 0.0).all()
    assert source.fee_rate({"feeCoefficient": "0.1"}) == 0.1 and source.fee_rate({}) == 0.0
    assert source.team_name({"name": "Bulls", "safeName": "Chicago"}) == "Chicago Bulls"
    assert source.team_name({"name": "Blackhawks", "safeName": "Chicago Blackhawks"}) == "Chicago Blackhawks"
    assert source.team_name({"name": "North Carolina Central", "safeName": "North Carolina Central"}) == "North Carolina Central"


def test_a_side_on_a_team_the_event_does_not_list_is_not_read():
    odd = _event(markets=[us.market(7, "football_team_full_game_spread", "Will Someone cover 3.5?", "+3.50", "-3.50",
                                    0.49, 0.51, line=3.5, long_team=999, short_team=998)])
    assert source.quotes([odd], NFL, NOW).empty
    assert not source.is_game({"markets": [us.prop(8, "football_player_passing_yards", "x", 1, 0.4, 0.6)]})
    closed = _event(markets=[us.moneyline(9, "football", CHIEFS, SEAHAWKS, 0.49, 0.51, status="MARKET_STATUS_CLOSED")])
    assert not source.quotes([closed], NFL, NOW)["accepting"].any()


def test_the_record_appends_on_change_and_keeps_the_close():
    first = source.quotes([_event()], NFL, NOW)
    record, added = source.fold(pd.DataFrame(), first)
    assert added == 10
    later = source.quotes([_event()], NFL, datetime(2026, 10, 24, 15, 4, tzinfo=UTC))
    later.loc[later["market_id"] == "1", "liquidity"] = 99.0
    record, added = source.fold(record, later)
    assert added == 0 and len(record) == 10                                       # nothing moved: no new row
    row = record[record["market_id"] == "1"].iloc[0]
    assert row["last_seen_at"] == "2026-10-24T15:04:00+00:00" and row["liquidity"] == 99.0
    moved = source.quotes([_event()], NFL, datetime(2026, 10, 24, 18, 0, tzinfo=UTC))
    moved.loc[(moved["market_id"] == "1") & (moved["side"] == "away"), ["bid", "ask", "mid"]] = [0.45, 0.46, 0.455]
    record, added = source.fold(record, moved)
    assert added == 1 and len(record) == 11
    latest = source.latest(record).set_index("token_id")
    assert latest.loc["s1a", "mid"] == 0.455 and latest.loc["s1b", "mid"] == 0.575
    assert source.close(record, "s1a", pd.Timestamp(START)) == 0.455
    assert source.close(record, "s1a", pd.Timestamp("2026-10-24 15:00:00+00")) == 0.425   # before the move
    assert math.isnan(source.close(record, "nope", pd.Timestamp(START)))


def test_the_record_read_back_from_disk_takes_the_next_capture(tmp_path):
    """Written and read as CSV a game id is a number; the next capture's text id must still fold onto it."""
    from atlas.live.store import Store

    store = Store.open(tmp_path)
    first = source.quotes([_event()], NFL, NOW).assign(game_id="401")
    store.write("polymarket_quotes", first)
    back = store.read("polymarket_quotes")
    assert back["game_id"].dtype != object                                        # the point: it came back numeric
    later = source.quotes([_event()], NFL, datetime(2026, 10, 24, 15, 4, tzinfo=UTC)).assign(game_id="401")
    record, added = source.fold(back, later)
    assert added == 0 and (record["game_id"].astype(str) == "401").all()
    assert record["last_seen_at"].iloc[0] == "2026-10-24T15:04:00+00:00"
    assert source.close(record, "s1a", pd.Timestamp(START)) == 0.425
    store.write("polymarket_quotes", record)
    assert len(store.read("polymarket_quotes")) == 10


def test_the_record_keeps_the_moneyline_and_the_line_nearest_even():
    q = source.quotes([_event()], NFL, NOW)
    kept = source.main_lines(q)
    # The home side priced at 42% is nearer even than the one at 60%: that spread market, both of its sides.
    assert set(zip(kept["market"], kept["line"], strict=True)) == {("moneyline", 0.0), ("spread", -2.5), ("spread", 2.5),
                                                                   ("total", 44.5)}
    assert len(kept) == 6


# ---------------------------------------------------------------------------
# Which game is which
# ---------------------------------------------------------------------------


def test_names_match_by_their_words_and_an_exact_team_beats_a_longer_one():
    assert match.score("Texas", "Texas Longhorns") == 2 and match.score("Texas", "Texas Tech Red Raiders") == 1
    assert match.score("Oklahoma", "Oklahoma State Cowboys") == 1 and match.score("Chiefs", "Kansas City Chiefs") == 2
    assert match.agrees("Miami (FL)", "Miami Hurricanes") and not match.agrees("Miami (FL)", "Miami (OH) RedHawks")
    assert match.agrees("UMass", "Massachusetts Minutemen") and match.agrees("San Jose State", "San José State Spartans")
    assert match.agrees("Louisiana-Monroe", "UL Monroe Warhawks") and not match.agrees("Seahawks", "Kansas City Chiefs")


def test_events_match_the_right_game_on_the_right_sides():
    oklahoma, texas = us.team(4, "Oklahoma"), us.team(3, "Texas")
    events = [_event(), _event("1002", "cfb-okl-tx-2026-10-24", oklahoma, texas, markets=[
        us.moneyline(21, "football", oklahoma, texas, 0.49, 0.51, start=START)]),
        _event("1003", "nfl-sea-kc-2026-10-24", SEAHAWKS, CHIEFS, markets=[
            us.moneyline(31, "football", SEAHAWKS, CHIEFS, 0.49, 0.51, start=START)])]
    q = pd.concat([source.quotes(events[:1], NFL, NOW), source.quotes(events[1:2], NCAAF, NOW),
                   source.quotes(events[2:], NFL, NOW)], ignore_index=True)
    up = match.upcoming(_games(), NOW, _projections(), None)
    pairs = match.match(q, up).set_index("event_id")
    assert pairs.loc["1001", "game_id"] == "401" and pairs.loc["1001", "label"] == "Kansas City Chiefs @ Seattle Seahawks"
    assert pairs.loc["1002", "game_id"] == "403"                               # Texas, not Texas Tech
    assert "1003" not in pairs.index                                            # the sides swapped: left unmatched
    attached = match.attach(q, pairs.reset_index())
    assert attached.loc[attached["event_id"] == "1001", "game_id"].eq("401").all()
    assert attached.loc[attached["event_id"] == "1003", "game_id"].isna().all()


def test_upcoming_games_take_their_sport_from_the_projection_when_the_scoreboard_has_none():
    g = _games().assign(sport=[None, "ncaaf", "ncaaf"])
    up = match.upcoming(g, NOW, _projections(), None)
    assert up.set_index("game_id").loc["401", "sport"] == "nfl"
    assert match.upcoming(g, datetime(2026, 11, 20, tzinfo=UTC), _projections(), None).empty


# ---------------------------------------------------------------------------
# Pricing
# ---------------------------------------------------------------------------


def _priced(calibration=None, projections=None, markets=None):
    q = source.quotes([_event(markets=markets)], NFL, NOW)
    pairs = match.match(q, match.upcoming(_games(), NOW, _projections(), None))
    return pricing.price(match.attach(q, pairs), projections if projections is not None else _projections(), None,
                         {}, calibration)


def test_the_fee_is_the_venues_formula_and_the_market_probability_is_normalised():
    assert pricing.fee(0.5, 0.03) == pytest.approx(0.0075) and pricing.fee(0.4, 0.05) == pytest.approx(0.012)
    p = _priced().set_index(["market", "side", "line"])
    assert p.loc[("moneyline", "away", 0.0), "p_market"] == pytest.approx(0.425)
    assert p.loc[("total", "over", 44.5), "cost"] == pytest.approx(0.51 + 0.0695 * 0.51 * 0.49)


def test_with_nothing_on_the_record_atlas_is_priced_as_the_market_and_nothing_clears_the_fee():
    p = _priced(calibration=None)
    football = p[p["market"] != "total"]
    assert (football["share"] == 0.0).all()
    assert np.allclose(football["p"], football["p_market"])
    assert (p["ev"] < 0).all()                                                 # a fee on a fair price


def test_the_share_is_fitted_through_the_market_and_clipped():
    k, n = pricing.share(_calibration(k=1.0), "nfl", "total")
    assert n == 1200 and 0.8 < k <= 1.0
    k, _ = pricing.share(_calibration(k=0.0, seed=2), "nfl", "total")
    assert k < 0.25
    k, _ = pricing.share(_calibration(k=-1.0, seed=3), "nfl", "spread")
    assert k == 0.0                                                            # never priced against itself
    assert pricing.share(_calibration(n=100), "nfl", "total") == (0.0, 100)     # thin: the market
    assert pricing.share(_calibration(), "nhl", "moneyline") == (0.0, 0)


def test_a_total_is_priced_off_the_records_hit_rate_by_gap_at_one_centre_for_the_whole_ladder():
    cal = _calibration(k=1.0)
    curve = pricing.edge_curve(cal, "nfl")
    assert curve is not None and 0.5 <= curve(0.0) <= curve(6.0) <= 1.0 and curve(100.0) == curve(12.0)
    assert pricing.edge_curve(_calibration(k=-1.0, seed=3), "nfl")(8.0) == 0.5    # a losing record reads as even
    p = _priced(calibration=cal, projections=_projections(total=49.0))           # Atlas above the market's ~44.6
    t = p[p["market"] == "total"].set_index(["side", "line"])
    assert (t["share"] == 1.0).all() and t["centre_market"].iloc[0] == pytest.approx(44.5, abs=1.5)
    assert t["centre_atlas"].iloc[0] == 49.0 and t["centre_market"].iloc[0] < t["centre"].iloc[0] < 49.0
    assert t.loc[("over", 44.5), "p"] > t.loc[("over", 44.5), "p_market"]
    assert t.loc[("over", 50.5), "p"] > t.loc[("over", 50.5), "p_market"]      # the whole ladder moves together
    assert t.loc[("under", 44.5), "p"] == pytest.approx(1.0 - t.loc[("over", 44.5), "p"], abs=1e-6)
    assert t["p_ladder"].notna().all()
    # Atlas below the market moves the ladder the other way.
    down = _priced(calibration=cal, projections=_projections(total=40.0))
    d = down[down["market"] == "total"].set_index(["side", "line"])
    assert d.loc[("under", 44.5), "p"] > d.loc[("under", 44.5), "p_market"]


def test_a_margin_is_pulled_toward_atlas_by_the_share_and_the_moneyline_is_the_margin_at_zero():
    cal = _calibration(k=1.0)
    p = _priced(calibration=cal, projections=_projections(margin=-10.0))      # Atlas: the away side by ten
    m = p[p["market"] != "total"].set_index(["market", "side", "line"])
    assert (m["share"] > 0.8).all()
    assert m.loc[("moneyline", "away", 0.0), "p"] > m.loc[("moneyline", "away", 0.0), "p_market"]
    assert m.loc[("spread", "away", -1.5), "p"] > m.loc[("spread", "away", -1.5), "p_market"]
    assert m.loc[("spread", "home", 1.5), "p"] < m.loc[("spread", "home", 1.5), "p_market"]
    assert m.loc[("moneyline", "away", 0.0), "p_raw"] > 0.7                      # Atlas's own reading, unanchored


def test_the_nhl_grid_is_anchored_in_probability_space():
    nhl = source.LEAGUES["nhl"]
    col, utah = us.team(21, "Avalanche", "Colorado Avalanche"), us.team(22, "Mammoth", "Utah Mammoth")
    ev = _event("2001", "nhl-col-utah-2026-10-24", col, utah, markets=[
        us.moneyline(41, "hockey", col, utah, 0.49, 0.51, fee=0.05, start=START),
        us.spread(42, "hockey", col, utah, -1.5, 0.29, 0.31, fee=0.05, start=START),
        us.total(43, "hockey", col, utah, 6.5, 0.49, 0.51, fee=0.05, start=START)])
    q = source.quotes([ev], nhl, NOW).assign(game_id="501", kickoff=KICKOFF, label="Colorado Avalanche @ Utah Mammoth")
    grid = pd.DataFrame([{"game_id": 501, "kickoff": KICKOFF, "p_home": 0.40, "p_home_minus_1_5": 0.2,
                          "p_away_minus_1_5": 0.4, "p_over_6.5": 0.6, "model_version": "n1",
                          "refreshed_at": "2026-10-24T08:00:00+00:00"}])
    cal = pd.DataFrame({"game_id": range(600), "sport": "nhl", "season": 2025, "week": 1, "season_type": "regular",
                        "market": "moneyline", "abs_edge": 10.0, "claimed": 0.6, "won": [1.0] * 600, "kickoff": KICKOFF})
    p = pricing.price(q, None, grid, {}, cal).set_index(["market", "side"])
    assert p.loc[("moneyline", "away"), "p_raw"] == pytest.approx(0.6) and p.loc[("spread", "away"), "p_raw"] == 0.4
    assert p.loc[("total", "over"), "p_raw"] == 0.6
    k = p.loc[("moneyline", "away"), "share"]
    assert 0.9 < k <= 1.0 and p.loc[("moneyline", "away"), "p"] == pytest.approx(0.5 + k * 0.1)
    assert p.loc[("moneyline", "away"), "fee"] == pytest.approx(0.05 * 0.51 * 0.49)


# ---------------------------------------------------------------------------
# Positions
# ---------------------------------------------------------------------------


def _board():
    """Atlas four points over the market's total, with a record that backs totals and not margins; every
    book read for its depth."""
    cal = _calibration(k=1.0, k_margin=0.0)
    p = _priced(calibration=cal, projections=_projections(total=49.0))
    p["liquidity"] = 12_000.0
    return p


def test_depth_is_the_shares_at_the_best_price_from_the_full_book_not_the_whole_side(monkeypatch):
    # /bbo's askShares is every offer summed (770,000 against 380,259 at the best ask on 26 October 2026), so
    # the depth is read from /book's levels: the shares at the one best price, the levels in any order.
    asked = []
    book = {"marketData": {"marketSlug": "m1", "state": "MARKET_STATE_OPEN",
                           "bids": [{"px": {"value": "0.7500", "currency": "USD"}, "qty": "19379.84"},
                                    {"px": {"value": "0.7600", "currency": "USD"}, "qty": "310648.18"}],
                           "offers": [{"px": {"value": "0.7800", "currency": "USD"}, "qty": "19502.83"},
                                      {"px": {"value": "0.7700", "currency": "USD"}, "qty": "380259.44"},
                                      {"px": {"value": "0.9900", "currency": "USD"}, "qty": "0"}]}}
    monkeypatch.setattr(source, "_get", lambda path, params=None, sess=None, **kw: asked.append(path) or book)
    long_ = source.depth("m1", True)
    assert asked == ["/v1/markets/m1/book"]
    assert (long_["bid"], long_["ask"], long_["spread"]) == (0.76, 0.77, 0.01)
    assert long_["ask_shares"] == pytest.approx(380259.44) and long_["ask_dollars"] == pytest.approx(380259.44 * 0.77)
    short = source.depth("m1", False)                       # the short side's ask is one less the long bid
    assert (short["bid"], short["ask"]) == (0.23, 0.24) and short["ask_shares"] == pytest.approx(310648.18)
    monkeypatch.setattr(source, "_get", lambda *a, **kw: {"marketData": {"bids": [], "offers": []}})
    empty = source.depth("m1", True)
    assert math.isnan(empty["ask"]) and math.isnan(empty["ask_shares"]) and math.isnan(empty["ask_dollars"])


def test_depth_is_read_from_the_book_for_the_candidates_only():
    p = _priced(calibration=_calibration(k=1.0, k_margin=0.0), projections=_projections(total=49.0))
    assert p["liquidity"].isna().all()
    asked = []

    def fetch(slug, long):
        asked.append((slug, long))
        return {"ask_dollars": 5_000.0, "spread": 0.03}
    out = positions.deepen(p, NOW, fetch=fetch)
    read = out[out["liquidity"].notna()]
    assert len(read) == len(asked) >= 1 and (read["ev"] >= positions.MIN_EV).all() and (read["spread"] == 0.03).all()
    assert out.loc[out["ev"] < positions.MIN_EV, "liquidity"].isna().all()
    assert (read["market"] == "total").all() and set(read["side"]) == {"over"}
    assert positions.positions(out, NOW)["liquidity"].iloc[0] == 5_000.0
    assert positions.positions(p, NOW).empty                                        # unread depth takes nothing


def test_positions_take_one_a_game_under_the_rule_and_the_record_logs_once_at_ten_eastern(tmp_path):
    p = _board()
    chosen = positions.positions(p, NOW)
    assert len(chosen) == 1 and chosen["market"].iloc[0] == "total" and chosen["side"].iloc[0] == "over"
    assert chosen["ev"].iloc[0] >= positions.MIN_EV and chosen["stake"].iloc[0] <= positions.MAX_STAKE
    assert chosen["day"].iloc[0] == "2026-10-24" and (chosen["year"].iloc[0], chosen["week"].iloc[0]) == (2026, 43)
    assert positions.contract("total", "over", 44.5, "Chiefs", "Seahawks") == "Over 44.5"
    assert positions.contract("spread", "home", 1.5, "Chiefs", "Seahawks") == "Seahawks +1.5"
    assert positions.contract("moneyline", "away", 0.0, "Chiefs", "Seahawks") == "Chiefs to win"
    where = tmp_path / "polymarket_positions"
    finals = pd.DataFrame(columns=["game_id", "final_margin", "final_total"])
    quotes = source.quotes([_event()], NFL, NOW)
    early = datetime(2026, 10, 24, 13, 30, tzinfo=UTC)                           # 09:30 ET: shown, not logged
    positions.run(p, finals, quotes, KEY, early, where=where)
    assert not where.exists()
    chosen, graded = positions.run(p, finals, quotes, KEY, NOW, where=where)
    files = list(where.glob("*.enc.json"))
    assert [f.name for f in files] == ["2026-43.enc.json"] and len(graded) == 1 and graded["outcome"].iloc[0] == "open"
    assert "Chiefs" not in files[0].read_text()
    # Logged once: a better price later does not revise it, and the same day is not logged twice.
    later = p.copy()
    later["ask"] = later["ask"] - 0.05
    chosen2, graded2 = positions.run(later, finals, quotes, KEY, datetime(2026, 10, 24, 16, 0, tzinfo=UTC), where=where)
    assert len(graded2) == 1 and graded2["ask"].iloc[0] == graded["ask"].iloc[0]
    # Graded on the final and against the close, which the record holds.
    done = pd.DataFrame([{"game_id": "401", "final_margin": -3.0, "final_total": 51.0}])
    moved = quotes.copy()
    moved["captured_at"] = "2026-10-24T19:00:00+00:00"
    moved.loc[moved["token_id"] == graded["token_id"].iloc[0], "mid"] = 0.60
    record, _ = source.fold(quotes, moved)
    after = datetime(2026, 10, 25, 2, 0, tzinfo=UTC)
    _, g = positions.run(later, done, record, KEY, after, where=where)
    x = g.iloc[0]
    assert x["outcome"] == "win" and x["profit"] == pytest.approx((1 - x["cost"]) / x["cost"])
    assert x["pnl"] == pytest.approx(x["stake"] * x["profit"]) and x["close"] == 0.60
    assert x["clv"] == pytest.approx(0.60 - x["ask"])
    assert positions.outcome("spread", "home", 1.5, -1.0, 40.0) == "win"
    assert positions.outcome("total", "under", 44.0, 0.0, 44.0) == "push"
    assert positions.outcome("moneyline", "away", 0.0, float("nan"), float("nan")) == "open"


def test_the_exchanges_settlement_grades_a_position_over_the_score(monkeypatch):
    p = _board()
    chosen = positions.positions(p, NOW)
    record = chosen.assign(position_id="x")
    after = datetime(2026, 10, 25, 2, 0, tzinfo=UTC)
    finals = pd.DataFrame([{"game_id": "401", "final_margin": -3.0, "final_total": 40.0}])   # the under on the score
    quotes = source.quotes([_event()], NFL, NOW)
    monkeypatch.setenv("ATLAS_OFFLINE", "1")
    assert positions.grade(record, finals, quotes, after)["outcome"].iloc[0] == "loss"
    monkeypatch.setenv("ATLAS_OFFLINE", "0")
    asked = []

    def settlement(slug):
        asked.append(slug)
        return 1.0
    monkeypatch.setattr(source, "settlement", settlement)
    g = positions.grade(record, finals, quotes, after)
    x = g.iloc[0]
    assert asked == [x["market_slug"]] and x["outcome"] == "win" and x["profit"] == pytest.approx((1 - x["cost"]) / x["cost"])
    # A settle at the last fair price pays that price; the short side pays one less it.
    monkeypatch.setattr(source, "settlement", lambda slug: 0.6)
    x = positions.grade(record, finals, quotes, after).iloc[0]
    assert x["outcome"] == "settled" and x["profit"] == pytest.approx(0.6 / x["cost"] - 1) and x["pnl"] == pytest.approx(x["stake"] * x["profit"])
    short = positions.grade(record.assign(long=False), finals, quotes, after).iloc[0]
    assert short["profit"] == pytest.approx(0.4 / short["cost"] - 1)
    # Not started: the settlement is not asked for; not settled: the score decides.
    asked.clear()
    monkeypatch.setattr(source, "settlement", settlement)
    none = pd.DataFrame(columns=["game_id", "final_margin", "final_total"])
    assert positions.grade(record, none, quotes, NOW)["outcome"].iloc[0] == "open" and asked == []
    monkeypatch.setattr(source, "settlement", lambda slug: float("nan"))
    assert positions.grade(record, finals, quotes, after)["outcome"].iloc[0] == "loss"
    secs = page.record_section(positions.grade(record.assign(long=False), finals, quotes, after).assign(close=0.5, clv=0.0))
    assert secs is None or secs["tables"][0]["rows"][1][1] == "1"


def test_the_rule_declines_wide_thin_tail_or_self_disagreeing_quotes():
    p = _board()
    ok = positions.eligible(p, NOW)
    assert ok.any()
    wide = p.copy()
    wide["spread"] = 0.08
    assert not positions.eligible(wide, NOW).any()
    thin = p.copy()
    thin["liquidity"] = 500.0
    assert not positions.eligible(thin, NOW).any()
    tail = p.copy()
    tail["p"] = 0.05
    assert not positions.eligible(tail, NOW).any()
    off = p.copy()
    off["p_ladder"] = off["p_market"] + 0.2
    assert not positions.eligible(off, NOW).any()
    started = p.copy()
    assert not positions.eligible(started, datetime(2026, 10, 24, 20, 0, tzinfo=UTC)).any()
    assert positions.positions(p[p["ev"] < positions.MIN_EV], NOW).empty


def test_the_daily_cap_scales_every_stake_down_together():
    p = _board()
    many = pd.concat([p.assign(game_id=f"g{i}", kelly=0.5) for i in range(8)], ignore_index=True)
    chosen = positions.positions(many, NOW)
    assert chosen["stake"].sum() == pytest.approx(positions.DAILY_CAP, abs=1e-3) and chosen["stake"].nunique() == 1


def test_the_close_falls_back_to_the_venues_history_only_when_online(monkeypatch):
    record = pd.DataFrame([{"token_id": "t", "market_slug": "m", "side": "away", "long": True,
                            "captured_at": "2026-10-24T20:00:00+00:00", "last_seen_at": "2026-10-24T20:00:00+00:00",
                            "mid": float("nan"), "bid": float("nan"), "ask": float("nan")}])
    monkeypatch.setenv("ATLAS_OFFLINE", "1")
    assert math.isnan(positions.closing(pd.DataFrame(), "t", pd.Timestamp(START)))
    assert math.isnan(positions.closing(record, "t", pd.Timestamp(START)))
    monkeypatch.setenv("ATLAS_OFFLINE", "0")
    monkeypatch.setattr(source, "history", lambda slug, sess=None, **kw: pd.DataFrame(
        {"at": [pd.Timestamp("2026-10-24 18:00+00"), pd.Timestamp("2026-10-24 20:00+00")],
         "long": [0.44, 0.9], "short": [0.56, 0.1]}))
    assert positions.closing(record, "t", pd.Timestamp(START)) == 0.44
    assert positions.closing(record.assign(long=False, side="home"), "t", pd.Timestamp(START)) == 0.56
    assert math.isnan(positions.closing(record, "nope", pd.Timestamp(START)))


# ---------------------------------------------------------------------------
# The page and the report
# ---------------------------------------------------------------------------


def test_the_sections_and_the_report_say_what_they_hold(tmp_path):
    p = _board()
    chosen, graded = positions.run(p, pd.DataFrame(columns=["game_id", "final_margin", "final_total"]),
                                   source.quotes([_event()], NFL, NOW), KEY, NOW, where=tmp_path / "pos")
    secs = page.sections(p, chosen, graded, NOW)
    assert [s["title"] for s in secs] == ["Positions for Sat Oct 24 (1)", "Polymarket US board",
                                          "Polymarket US record (paper)"]
    assert secs[0]["tab"] == "Polymarket" and secs[2]["tab"] == "Record"
    row = secs[0]["tables"][0]["rows"][0]
    assert row[0][0] == "Kansas City Chiefs @ Seattle Seahawks" and row[1][1] == "NFL" and row[4][1] == "logged"
    assert row[1][0].startswith("Over ")                                            # Atlas's side, at the line that pays best
    assert json.dumps(crypto.clean(secs))                                         # strict JSON for the browser
    out = report.write(p, match.upcoming(_games(), NOW, _projections(), None), _calibration(k=1.0), NOW,
                       where=tmp_path / "polymarket_model.md")
    text = out.read_text()
    assert "| NFL | 1 | 1 | 10 |" in text and "the record's hit rate by gap" in text
    assert "EV" not in text and "Over 44.5" not in text and "Kelly" not in text


def test_refresh_offline_keeps_the_record_and_seals_the_page_when_the_key_is_set(tmp_path, monkeypatch):
    from atlas.live.store import Store
    from atlas.owner import page as owner_page
    from atlas.polymarket import __main__ as cli

    monkeypatch.setenv("ATLAS_OFFLINE", "1")
    monkeypatch.setenv("ATLAS_TRACKING_DIR", str(tmp_path / "tracking"))
    monkeypatch.setenv("ATLAS_DATA_DIR", str(tmp_path / "data"))                 # no NBA props snapshot here
    monkeypatch.delenv("ATLAS_COUNTER_URL", raising=False)
    monkeypatch.setattr("atlas.research.dataset.load_research_frame", lambda: pd.DataFrame(
        {"game_id": [401], "actual_margin": [3.0], "actual_total": [41.0]}))
    store = Store.open(tmp_path / "tracking")
    store.write("games", _games())
    store.write("projections", _projections())
    store.write("calibration", _calibration())
    store.write("polymarket_quotes", source.quotes([_event()], NFL, NOW).assign(game_id="401"))
    where = tmp_path / "page.enc.json"
    monkeypatch.setattr(owner_page, "page_path", lambda: where)
    monkeypatch.setattr(report, "path", lambda: tmp_path / "polymarket_model.md")
    monkeypatch.setattr(positions, "path", lambda: tmp_path / "positions")
    monkeypatch.delenv(crypto.SECRET, raising=False)
    assert cli.refresh(now=NOW, store=store) == []
    assert owner_page.read(where)["box"] is None and "key" in owner_page.read(where)["reason"]
    monkeypatch.setenv(crypto.SECRET, KEY)
    secs = cli.refresh(now=NOW, store=store)
    assert [s["tab"] for s in secs] == ["Polymarket", "Polymarket", "Props", "Poly Snipe", "Finish line", "Metals 15m", "Live"]  # offline: no positions
    assert "snapshot" in secs[2]["notes"][0]                                      # props wait for the heavy refresh
    box = owner_page.read(where)["box"]
    data = json.loads(crypto.decrypt(box, KEY))
    assert [s["title"] for s in data["sections"]][:2] == ["Positions for Sat Oct 24 (0)", "Polymarket US board"]
    assert len(store.read("polymarket_quotes")) == 10                             # the record as it was
    assert (tmp_path / "polymarket_model.md").exists()
    assert sealed.load(tmp_path / "positions", KEY) == []


def test_default_shapes_price_a_football_line_when_the_fitted_ones_are_missing():
    shape = probability.default_shape("nfl", "margin")
    assert pricing.line_prob(shape, -3.0, "moneyline", "away", 0.0) > 0.5
    assert pricing.line_prob(shape, 0.0, "spread", "home", -3.5) < 0.5 < pricing.line_prob(shape, 0.0, "spread", "home", 3.5)
    assert math.isnan(pricing.line_prob(shape, float("nan"), "total", "over", 44.5))


def test_the_owner_page_carries_one_box_and_the_old_address_forwards():
    from atlas.site import render

    html = render.owner_page({"built_at": "2026-10-24T14:04:00+00:00", "box": {"v": 1, "ct": "abc", "iv": "i",
                                                                              "salt": "s", "iterations": 1}})
    assert '<script type="application/json" id="owner-box">{"box": {"v": 1' in html
    assert 'name="robots" content="noindex, nofollow"' in html and "owner.js" in html
    assert "DFS" not in html and "lineup" not in html
    empty = render.owner_page(None)
    assert "Nothing has been built yet." in empty
    forward = render.forward_page("../owner/")
    assert 'http-equiv="refresh" content="0; url=../owner/"' in forward and "noindex" in forward


def test_a_settlement_is_read_past_the_edge_cache_and_not_found_means_unsettled(monkeypatch):
    # The edge cache keeps serving the "not found" it stored before the market settled, past its max-age.
    asked = []

    def get(path, params=None, sess=None, **kw):
        asked.append((path, dict(params or {})))
        if path.endswith("/m2/settlement"):
            raise RuntimeError("404 Settlement not found")
        return {"slug": "m1", "settlement": 1}
    monkeypatch.setattr(source, "_get", get)
    assert source.settlement("m1") == 1.0 and math.isnan(source.settlement("m2"))
    assert source.settlement("m1") == 1.0
    paths = [p for p, _ in asked]
    keys = [q.get("fresh") for _, q in asked]
    assert paths[0] == "/v1/markets/m1/settlement" and all(keys) and len(set(keys)) == len(keys)   # unique each read
