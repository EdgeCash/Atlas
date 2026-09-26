"""Sports trading: exchange contracts priced against the consensus after fees, positions sized, logged once, graded."""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
import pytest

from atlas.live import probability
from atlas.owner import sealed, trading
from atlas.sources import bettingpros as bp

KEY = "correct horse battery staple"
NOW = datetime(2026, 9, 26, 14, 4, tzinfo=UTC)                  # Saturday 10:04 ET
A, B = "401866429", "401856700"                                  # Sat 9 PM ET, Sat 7:30 PM ET
NAMES = {A: "UMass @ Sacramento St.", B: "Wyoming @ Oklahoma State"}


def _row(game, event, market, participant, book, cost, line=0.0, selection=None, off=False,
         updated="2026-09-26 13:00:00"):
    return {"captured_at": "2026-09-26T13:05:00+00:00", "sport": "ncaaf", "event_id": event, "market": market,
            "selection": selection or participant, "participant": participant, "book_id": book, "line": line,
            "cost": float(cost), "updated": updated, "is_off": off, "open_line": line, "open_cost": float(cost),
            "open_book": 10.0, "open_created": "2026-09-22 08:00:00", "game_id": game}


def _lines():
    rows = [
        # Game A, the total: consensus 44.5 at -110 both ways; Kalshi's over at +105 is a long way under fair.
        _row(A, 32187, "total", None, 0, -110, 44.5, "over"), _row(A, 32187, "total", None, 0, -110, 44.5, "under"),
        _row(A, 32187, "total", None, 68, 105, 44.5, "over"), _row(A, 32187, "total", None, 68, -125, 44.5, "under"),
        _row(A, 32187, "total", None, 60, -99900, 49.5, "over"),                     # Novig: filled, and not a venue
        # Game A, the moneyline: Polymarket US's away price clears too, but one position a game.
        _row(A, 32187, "moneyline", "CSUS", 0, -150), _row(A, 32187, "moneyline", "UMASS", 0, 130),
        _row(A, 32187, "moneyline", "CSUS", 75, -160), _row(A, 32187, "moneyline", "UMASS", 75, 150),
        # Game B, the moneyline only. Kalshi spells the home side another way; the global Polymarket pays best.
        _row(B, 32200, "moneyline", "OKST", 0, -150), _row(B, 32200, "moneyline", "WYO", 0, 130),
        _row(B, 32200, "moneyline", "OSU", 68, -140), _row(B, 32200, "moneyline", "WYO", 68, 135),
        _row(B, 32200, "moneyline", "OKST", 75, -160), _row(B, 32200, "moneyline", "WYO", 75, 155),
        _row(B, 32200, "moneyline", "OKST", 73, -170), _row(B, 32200, "moneyline", "WYO", 73, 160),
        _row(B, 32200, "moneyline", "OKST", 68, -110, off=True),                   # off: never a quote
    ]
    return pd.DataFrame(rows, columns=[*bp.LINE_COLUMNS, "game_id"])


def _events():
    base = {"sport": "ncaaf", "season": 2026, "week": 4, "status": "scheduled", "stadium_type": "outdoor",
            "forecast_wind": float("nan"), "forecast_temp": 70.0}
    return pd.DataFrame([
        {**base, "event_id": 32187, "game_id": A, "scheduled": pd.Timestamp("2026-09-27 01:00", tz="UTC"),
         "home_abbr": "CSUS", "visitor_abbr": "UMASS"},
        {**base, "event_id": 32200, "game_id": B, "scheduled": pd.Timestamp("2026-09-26 23:30", tz="UTC"),
         "home_abbr": "OKST", "visitor_abbr": "WYO"},
    ])


def _projections():
    return pd.DataFrame([{"game_id": int(A), "sport": "ncaaf", "season": 2026, "week": 4,
                          "kickoff": "2026-09-27T01:00:00Z", "total_mean": 50.0, "total_sd": 16.0,
                          "total_over_shrink": 0.35, "total_over_sd": 15.8, "margin_mean": -3.0, "margin_sd": 15.0,
                          "model_version": "m1", "refreshed_at": "2026-09-26T08:00:00+00:00"}])


def _priced():
    return trading.priced(trading.quotes(_lines(), _events(), _projections(), {}, NOW, None))


def test_the_fee_is_the_venues_formula_and_ev_is_fair_over_cost():
    assert trading.fee(0.5, 0.07) == pytest.approx(0.0175)                         # Kalshi at 50c: 1.75c
    assert trading.fee(0.4, 0.05) == pytest.approx(0.012)
    p = _priced().set_index(["game_id", "market", "side", "book_id"])
    x = p.loc[(B, "moneyline", "away", 75)]                                        # Polymarket US, WYO +155
    fair = 1 - probability.no_vig(-150, 130)
    ask = 100 / 255
    cost = ask + 0.05 * ask * (1 - ask)
    assert x["ask"] == pytest.approx(ask) and x["fee"] == pytest.approx(cost - ask) and x["price"] == pytest.approx(cost)
    assert x["p"] == pytest.approx(fair) and x["ev"] == pytest.approx(fair / cost - 1)
    assert x["kelly"] == pytest.approx((fair - cost) / (1 - cost))
    assert p.loc[(B, "moneyline", "home", 68)]["ev"] < 0                             # fees turn a near-fair price negative


def test_moneyline_sides_survive_another_spelling_and_off_or_filled_quotes_are_not_quotes():
    p = _priced()
    kalshi_b = p[(p["game_id"] == B) & (p["book_id"] == 68)].set_index("side")
    assert set(kalshi_b.index) == {"home", "away"}                                  # OSU read as OKST, by complement
    assert kalshi_b.loc["home", "cost"] == -140                                     # not the off -110
    assert not (p["book_id"] == 60).any()                                           # Novig is not a venue here
    assert set(p["venue"]) == {"Kalshi", "Polymarket US", "Polymarket"}


def test_positions_take_one_a_game_at_the_best_tradeable_venue_under_the_caps():
    chosen = trading.positions(_priced(), _events(), NAMES, NOW)
    got = chosen.set_index("game_id")
    assert set(got.index) == {A, B}                                                 # one a game
    assert got.loc[A, "market"] == "total" and got.loc[A, "venue"] == "Kalshi" and got.loc[A, "side"] == "over"
    # Game B: the global Polymarket pays more, but US accounts can only close there; Polymarket US is the venue.
    assert got.loc[B, "venue"] == "Polymarket US" and got.loc[B, "side"] == "away"
    assert (chosen["ev"] >= trading.MIN_EV).all() and (chosen["stake"] <= trading.MAX_STAKE).all()
    assert chosen["stake"].sum() <= trading.DAILY_CAP
    assert got.loc[B, "stake"] == pytest.approx(trading.KELLY_FRACTION * got.loc[B, "kelly"], abs=1e-4)
    assert got.loc[B, "home_abbr"] == "OKST" and got.loc[B, "label"] == NAMES[B]
    assert trading.contract("moneyline", "away", 0.0, NAMES[B]) == "Wyoming to win"
    assert trading.contract("spread", "home", -3.5, NAMES[B]) == "Oklahoma State -3.5"
    assert trading.contract("total", "over", 44.5, NAMES[A]) == "Over 44.5"


def test_the_daily_cap_scales_every_stake_down_together():
    many = pd.concat([_priced().assign(game_id=f"g{i}", kelly=0.5) for i in range(8)], ignore_index=True)
    chosen = trading.positions(many, _events(), NAMES, NOW)
    assert chosen["stake"].sum() == pytest.approx(trading.DAILY_CAP, abs=1e-3)
    assert chosen["stake"].nunique() == 1                                           # all at the cap, scaled together


def test_positions_are_logged_once_at_ten_eastern_sealed_and_graded(tmp_path):
    where = tmp_path / "owner_trading"
    empty = pd.DataFrame(columns=["game_id", "final_margin", "final_total"])
    closes = pd.DataFrame(columns=[*bp.LINE_COLUMNS, "game_id"])
    early = datetime(2026, 9, 26, 13, 30, tzinfo=UTC)                               # 09:30 ET: shown, not logged
    trading.build(_lines(), _events(), _projections(), {}, None, empty, closes, NAMES, KEY, early, where=where)
    assert not where.exists()
    sec = trading.build(_lines(), _events(), _projections(), {}, None, empty, closes, NAMES, KEY, NOW, where=where)
    record = trading.load(KEY, where)
    assert len(record) == 2 and set(record["day"]) == {"2026-09-26"}
    text = (where / "2026-04.enc.json").read_text()
    assert "Wyoming" not in text and "Kalshi" not in text
    with pytest.raises(sealed.Unreadable):
        trading.load("not the key", where)
    later = datetime(2026, 9, 26, 15, 4, tzinfo=UTC)
    sec = trading.build(_lines(), _events(), _projections(), {}, None, empty, closes, NAMES, KEY, later, where=where)
    assert len(trading.load(KEY, where)) == 2                                        # once a day
    assert all(r[6].endswith("· logged") for r in sec[0]["tables"][0]["rows"])

    # Final scores: A goes over (50 points); B's away side wins outright. The consensus closed with B tighter.
    finals = pd.DataFrame({"game_id": [A, B], "final_margin": [3.0, -7.0], "final_total": [50.0, 41.0]})
    closes = _lines()[_lines()["book_id"] == bp.CONSENSUS].copy()
    closes.loc[(closes["game_id"] == B) & (closes["participant"] == "OKST"), "cost"] = -130.0
    closes.loc[(closes["game_id"] == B) & (closes["participant"] == "WYO"), "cost"] = 110.0
    g = trading.grade(record, finals, closes, {}).set_index("game_id")
    assert g.loc[A, "outcome"] == "win" and g.loc[B, "outcome"] == "win"
    assert g.loc[B, "profit"] == pytest.approx((1 - g.loc[B, "price"]) / g.loc[B, "price"])
    assert g.loc[B, "pnl"] == pytest.approx(g.loc[B, "stake"] * g.loc[B, "profit"])
    close_away = 1 - probability.no_vig(-130, 110)
    assert g.loc[B, "clv_prob"] == pytest.approx(close_away - g.loc[B, "p_fair"], abs=1e-4)   # the close moved toward it
    assert g.loc[B, "clv_prob"] > 0


def test_outcomes_follow_the_contract_and_a_push_is_refunded():
    assert trading.outcome("moneyline", "home", 0.0, 3.0, 40.0) == "win"
    assert trading.outcome("moneyline", "away", 0.0, 3.0, 40.0) == "loss"
    assert trading.outcome("moneyline", "home", 0.0, 0.0, 40.0) == "push"
    assert trading.outcome("spread", "away", 3.0, 3.0, 40.0) == "push"                # lost by 3, +3: refunded
    assert trading.outcome("total", "under", 44.5, 0.0, 44.0) == "win"
    assert trading.outcome("total", "over", 44.5, float("nan"), float("nan")) == "open"
    record = trading.positions(_priced(), _events(), NAMES, NOW).reindex(columns=trading.COLUMNS)
    finals = pd.DataFrame({"game_id": [A, B], "final_margin": [0.0, 0.0], "final_total": [44.0, 44.0]})
    g = trading.grade(record, finals, pd.DataFrame(), {}).set_index("game_id")
    assert g.loc[A, "outcome"] == "loss" and g.loc[A, "profit"] == -1.0
    assert g.loc[B, "outcome"] == "push" and g.loc[B, "profit"] == 0.0


def test_the_section_shows_positions_the_exchange_board_coverage_and_the_record():
    p = _priced()
    chosen = trading.positions(p, _events(), NAMES, NOW)
    finals = pd.DataFrame({"game_id": [A, B], "final_margin": [3.0, -7.0], "final_total": [50.0, 41.0]})
    graded = trading.grade(chosen.reindex(columns=trading.COLUMNS), finals, pd.DataFrame(), {})
    sec = trading.section(p, chosen, graded, NAMES, NOW)[0]
    assert sec["tab"] == "Trading" and sec["title"] == "Sports trading: Kalshi and Polymarket"
    titles = [t["title"] for t in sec["tables"]]
    assert titles[0] == "Positions for Sat Sep 26: 2"
    assert titles[1].startswith("Exchange board") and titles[2] == "Quotes this run (sides priced)"
    assert "Record (paper)" in titles and "Latest graded" in titles
    board_rows = sec["tables"][1]["rows"]
    assert any(r[2] == "Polymarket (reference)" for r in board_rows)
    cover = {r[0]: r[1:] for r in sec["tables"][2]["rows"]}
    assert cover["Kalshi"] == ["2", "0", "2"] and cover["Polymarket US"] == ["0", "0", "4"]
    assert cover["Polymarket (reference)"] == ["0", "0", "2"]
    buy = sec["tables"][0]["rows"][0][3]
    assert buy.endswith("fee") and "¢ + " in buy                                       # a fresh quote is not marked
    stale = trading.section(p, chosen, graded, NAMES, datetime(2026, 9, 26, 16, 0, tzinfo=UTC))[0]
    assert "min old" in stale["tables"][0]["rows"][0][3]                              # three hours on: marked
    empty = trading.section(p.iloc[0:0], chosen.iloc[0:0], graded.iloc[0:0], NAMES, NOW)[0]
    assert empty["tables"][0]["rows"][0][0].startswith("Nothing clears +2% after fees")


def test_a_moneyline_offer_parses_with_no_line_and_appends_on_change_like_any_other():
    from atlas.owner import market as market_store

    def book(bid, cost):
        return {"id": bid, "lines": [{"main": True, "active": True, "replaced": False, "is_off": False, "cost": cost,
                                      "line": None, "updated": "2026-09-26 13:00:00"}]}
    body = {"_parameters": {"key": "SECRET-MUST-NOT-SURVIVE"},
            "offers": [{"event_id": 32200, "selections": [
                {"selection": "", "participant": "OKST", "opening_line": {"line": None, "cost": -140, "book_id": 10},
                 "books": [book(0, -150), book(68, -140)]},
                {"selection": "", "participant": "WYO", "opening_line": {"line": None, "cost": 120, "book_id": 10},
                 "books": [book(0, 130), book(68, 135)]}]}]}
    rows = bp.parse_offers(body, "ncaaf", "moneyline", "2026-09-26T13:05:00+00:00")
    assert len(rows) == 4 and (rows["line"] == 0.0).all() and set(rows["participant"]) == {"OKST", "WYO"}
    rows = rows.assign(game_id=B)
    record, added = market_store.append(rows.iloc[0:0], rows)
    assert len(added) == 4
    _, again = market_store.append(record, rows)
    assert again.empty                                                              # unchanged: no new rows


def test_the_bar_is_two_percent_after_fees():
    """Polymarket US at +150 against a -150/+130 consensus is +1.98% after its fee: shown, not taken."""
    assert trading.MIN_EV == 0.02
    lines = _lines()
    lines.loc[(lines["game_id"] == B) & (lines["book_id"] == 75) & (lines["participant"] == "WYO"), "cost"] = 150.0
    p = trading.priced(trading.quotes(lines, _events(), _projections(), {}, NOW, None))
    x = p.set_index(["game_id", "market", "side", "book_id"]).loc[(B, "moneyline", "away", 75)]
    assert 0.019 < x["ev"] < 0.02
    chosen = trading.positions(p, _events(), NAMES, NOW)
    assert B not in set(chosen["game_id"])                                            # under the bar; the global
    board = trading.section(p, chosen, chosen.iloc[0:0].assign(outcome=[], pnl=[], clv_prob=[]), NAMES, NOW)[0]
    assert any(r[0].startswith(NAMES[B]) for r in board["tables"][1]["rows"])        # Polymarket still on the board

