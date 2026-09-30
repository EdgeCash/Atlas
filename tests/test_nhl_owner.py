"""The NHL on the owner's board (docs/MODEL_PLAN_NHL.md, step 6): every book's moneyline, puck line and total
priced by the grid pulled toward the market, the picks logged once and graded, and the same legs in the parlays
and on the exchanges. Synthetic."""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pytest

from atlas.live import probability
from atlas.owner import nhl_board, parlays, sealed, trading
from atlas.sources import bettingpros as bp

KEY = "correct horse battery staple"
NOW = datetime(2026, 10, 1, 16, 0, tzinfo=UTC)                  # noon ET
G = "401891781"                                                  # Sabres at Blue Jackets, 7 PM ET
NAMES = {G: "Sabres @ Jackets"}


def _row(market, participant, book, cost, line=0.0, selection=None, updated="2026-10-01 15:00:00"):
    return {"captured_at": "2026-10-01T15:05:00+00:00", "sport": "nhl", "event_id": 77001, "market": market,
            "selection": selection or participant, "participant": participant, "book_id": book, "line": line,
            "cost": float(cost), "updated": updated, "is_off": False, "open_line": line, "open_cost": float(cost),
            "open_book": 12.0, "open_created": "2026-09-29 08:00:00", "game_id": G}


def _lines():
    rows = [
        _row("moneyline", "CBJ", 0, -115), _row("moneyline", "BUF", 0, -105),
        _row("moneyline", "CBJ", 12, -115), _row("moneyline", "BUF", 12, -105),
        _row("moneyline", "CBJ", 19, -120), _row("moneyline", "BUF", 19, -110),
        _row("moneyline", "CLB", 68, -112), _row("moneyline", "BUF", 68, -102),   # Kalshi spells the home side its way
        # The puck line: the home side +1.5 here. BetMGM spells it another way; its other quote says whose it is.
        _row("spread", "CBJ", 0, -250, 1.5), _row("spread", "BUF", 0, 205, -1.5),
        _row("spread", "CBJ", 12, -250, 1.5), _row("spread", "BUF", 12, 205, -1.5),
        _row("spread", "COL", 19, -240, 1.5), _row("spread", "BUF", 19, 200, -1.5),
        # The total: DraftKings at the consensus's 6.5; BetMGM at 5.5, where the consensus says nothing.
        _row("total", None, 0, -110, 6.5, "over"), _row("total", None, 0, -110, 6.5, "under"),
        _row("total", None, 12, -105, 6.5, "over"), _row("total", None, 12, -115, 6.5, "under"),
        _row("total", None, 19, -160, 5.5, "over"), _row("total", None, 19, 130, 5.5, "under"),
    ]
    return pd.DataFrame(rows, columns=[*bp.LINE_COLUMNS, "game_id"])


def _events():
    return pd.DataFrame([{"event_id": 77001, "sport": "nhl", "scheduled": pd.Timestamp("2026-10-01 23:00", tz="UTC"),
                          "season": 2026, "week": None, "status": "scheduled", "home_abbr": "CBJ",
                          "visitor_abbr": "BUF", "stadium_type": None, "forecast_wind": float("nan"),
                          "forecast_temp": float("nan"), "game_id": G}])


def _projections(p_home=0.60):
    return pd.DataFrame([{"game_id": int(G), "season": 2026, "kickoff": "2026-10-01T23:00:00+00:00",
                          "p_home": p_home, "p_home_minus_1_5": 0.32, "p_away_minus_1_5": 0.30,
                          "p_over_4.5": 0.78, "p_over_5.5": 0.60, "p_over_6.5": 0.42, "p_over_7.5": 0.25,
                          "total_mean": 6.2, "refreshed_at": "2026-10-01T08:00:00+00:00"}])


def _calibration(n=600, wins=330, sport="nhl"):
    return pd.DataFrame({"sport": sport, "market": "moneyline", "abs_edge": 10.0, "claimed": 0.60,
                         "won": [1] * wins + [0] * (n - wins)})


def test_the_share_of_disagreement_is_fitted_on_the_nhl_moneyline_record_and_defaults_when_thin():
    assert nhl_board.share(None) == nhl_board.DEFAULT_SHARE
    assert nhl_board.share(_calibration(n=400, wins=220)) == nhl_board.DEFAULT_SHARE            # too thin
    assert nhl_board.share(_calibration(sport="nfl")) == nhl_board.DEFAULT_SHARE                  # not the NHL's
    # Atlas claimed 60% where the market said 50%; its side won 55%: half its disagreement was real.
    assert nhl_board.share(_calibration()) == pytest.approx(0.5)
    assert nhl_board.share(_calibration(wins=240)) == 0.0                                         # clipped


def test_the_grid_reads_each_side_at_its_own_line_and_nowhere_else():
    pr = _projections().iloc[0]
    assert nhl_board.atlas_prob(pr, "moneyline", "home", 0.0) == pytest.approx(0.60)
    assert nhl_board.atlas_prob(pr, "moneyline", "away", 0.0) == pytest.approx(0.40)
    assert nhl_board.atlas_prob(pr, "spread", "home", -1.5) == pytest.approx(0.32)               # by two or more
    assert nhl_board.atlas_prob(pr, "spread", "home", 1.5) == pytest.approx(0.70)                # not losing by two
    assert nhl_board.atlas_prob(pr, "spread", "away", -1.5) == pytest.approx(0.30)
    assert nhl_board.atlas_prob(pr, "spread", "away", 1.5) == pytest.approx(0.68)
    assert nhl_board.atlas_prob(pr, "total", "over", 5.5) == pytest.approx(0.60)
    assert nhl_board.atlas_prob(pr, "total", "under", 6.5) == pytest.approx(0.58)
    assert np.isnan(nhl_board.atlas_prob(pr, "total", "over", 6.0))                              # a whole goal
    assert np.isnan(nhl_board.atlas_prob(pr, "spread", "home", -2.5))


def test_every_book_is_valued_against_the_consensus_at_its_line_with_the_grid_pulled_toward_it():
    k = 0.5
    t = nhl_board.legs(_lines(), _events(), _projections(), k)
    assert set(t["book_id"]) == {12, 19} and set(t["sport"]) == {"nhl"}                           # never the consensus
    assert t["season"].eq(2026).all() and t["week"].eq(40).all()                                  # ISO week of puck drop
    ml = t[t["market"] == "moneyline"].set_index(["book_id", "side"])
    fair = probability.no_vig(-115, -105)
    assert ml.loc[(12, "home"), "p_fair"] == pytest.approx(fair)
    assert ml.loc[(12, "home"), "p_atlas"] == pytest.approx(fair + k * (0.60 - fair))
    assert ml.loc[(12, "home"), "ev_atlas"] == pytest.approx(ml.loc[(12, "home"), "p_atlas"] * (1 + 100 / 115) - 1)
    assert ml["line"].eq(0.0).all() and ml["home_abbr"].eq("CBJ").all()
    pl = t[t["market"] == "spread"].set_index(["book_id", "side"])
    assert pl.loc[(19, "home"), "line"] == 1.5                                                     # found by complement
    assert pl.loc[(19, "home"), "p_raw"] == pytest.approx(0.70)
    tot = t[t["market"] == "total"]
    assert set(tot["book_id"]) == {12}                                                            # BetMGM's 5.5 left out
    over = tot[tot["side"] == "over"].iloc[0]
    assert over["p_fair"] == pytest.approx(0.5) and over["p_raw"] == pytest.approx(0.42)
    quotes = nhl_board.quotes(_lines(), _events(), _projections(), k)
    assert list(quotes.columns) == trading.QUOTE_COLUMNS and set(quotes["book_id"]) == {68}
    assert set(quotes["side"]) == {"home", "away"}                                                # Kalshi's CLB is home


def test_nothing_is_priced_without_a_projection_or_a_consensus():
    assert nhl_board.legs(_lines(), _events(), _projections().iloc[0:0], 0.5).empty
    no_cons = _lines()[_lines()["book_id"] != bp.CONSENSUS]
    assert nhl_board.legs(no_cons, _events(), _projections(), 0.5).empty


def test_picks_are_logged_once_sealed_by_week_and_graded_on_the_final_and_the_close(tmp_path):
    where = tmp_path / "owner_nhl"
    empty = pd.DataFrame(columns=["game_id", "final_margin", "final_total"])
    closes = pd.DataFrame(columns=[*bp.LINE_COLUMNS, "game_id"])
    secs, table, k = nhl_board.build(_lines(), _events(), _projections(), None, empty, closes, NAMES, KEY, NOW,
                                     where=where)
    assert k == nhl_board.DEFAULT_SHARE and len(table)
    record = nhl_board.load(KEY, where)
    # The moneyline's home side at DraftKings (-115 beats BetMGM's -120), and the under; the puck line clears nowhere.
    assert sorted(record["market"]) == ["moneyline", "total"] and record["pick_id"].is_unique
    ml = record[record["market"] == "moneyline"].iloc[0]
    assert (ml["side"], int(ml["book_id"]), ml["cost"], ml["home_abbr"]) == ("home", 12, -115.0, "CBJ")
    files = list(where.glob("*.enc.json"))
    assert [f.name for f in files] == ["nhl-2026-W40.enc.json"]
    assert "Jackets" not in files[0].read_text() and "DraftKings" not in files[0].read_text()
    with pytest.raises(sealed.Unreadable):
        nhl_board.load("not the key", where)
    assert secs[0]["title"] == f"NHL picks now ({len(record)})" and secs[0]["tab"] == "Board"
    assert "Jackets to win (-115)" in str(secs[0]["tables"][0]["rows"])

    nhl_board.build(_lines(), _events(), _projections(p_home=0.62), None, empty, closes, NAMES, KEY, NOW, where=where)
    again = nhl_board.load(KEY, where)
    assert len(again) == len(record) and again["p_raw"].tolist() == record["p_raw"].tolist()      # never revised

    # A 3-2 shootout win for the home side: the books settle it as a one-goal win and a total of five.
    finals = pd.DataFrame({"game_id": [G], "final_margin": [1.0], "final_total": [5.0]})
    close = _lines()[_lines()["book_id"] == bp.CONSENSUS].copy()
    close.loc[(close["market"] == "moneyline") & (close["participant"] == "CBJ"), "cost"] = -135.0
    close.loc[(close["market"] == "moneyline") & (close["participant"] == "BUF"), "cost"] = 115.0
    g = nhl_board.grade(again, finals, close).set_index("market")
    assert g.loc["moneyline", "outcome"] == "win"
    assert g.loc["moneyline", "profit"] == pytest.approx(100 / 115)
    assert g.loc["moneyline", "clv_prob"] == pytest.approx(probability.no_vig(-135, 115) - ml["p_fair"], abs=1e-4)
    assert g.loc["total", "outcome"] == "win" and g.loc["total", "clv_prob"] == pytest.approx(0.0)
    record_card = nhl_board.sections(nhl_board.best(table), nhl_board.picks(nhl_board.best(table)), g.reset_index(),
                                     NAMES, NOW, k)[-1]
    assert record_card["title"] == "NHL board record"


def test_a_moneyline_and_a_puck_line_on_one_game_are_one_view_and_the_total_another():
    priced = pd.DataFrame({"game_id": ["1", "1", "1", "2"], "market": ["moneyline", "spread", "total", "spread"],
                           "side": ["home", "home", "over", "away"], "ev_atlas": [0.03, 0.05, 0.01, -0.01]})
    chosen = nhl_board.picks(priced)
    assert chosen[["game_id", "market"]].values.tolist() == [["1", "spread"], ["1", "total"]]


def test_outcomes_settle_as_the_books_do():
    assert nhl_board.outcome("moneyline", "away", 0.0, -1.0, 5.0) == "win"
    assert nhl_board.outcome("spread", "home", -1.5, 1.0, 5.0) == "loss"
    assert nhl_board.outcome("spread", "away", 1.5, 1.0, 5.0) == "win"
    assert nhl_board.outcome("total", "under", 5.5, 1.0, 5.0) == "win"
    assert nhl_board.outcome("total", "over", 6.0, 0.0, 6.0) == "push"
    assert nhl_board.outcome("moneyline", "home", 0.0, float("nan"), float("nan")) == "open"


def test_nhl_legs_ride_in_the_parlays_on_atlas_and_a_moneyline_leg_settles_on_the_winner():
    t = nhl_board.legs(_lines(), _events(), _projections(), 0.5)
    football = t.iloc[:1].assign(sport="ncaaf", market="spread", ev_price=-0.01, ev_atlas=0.5, game_id="1")
    c = parlays.candidates(pd.concat([t, football], ignore_index=True), NOW)
    nhl = c[c["sport"] == "nhl"]
    assert (nhl["score"] == nhl["ev_atlas"]).all() and (nhl["p"] == nhl["p_atlas"]).all()
    assert "1" not in set(c["game_id"])                              # a football spread is still the price edge
    leg = {"game_id": G, "market": "moneyline", "side": "home", "line": 0.0, "cost": -115.0, "p": 0.55,
           "label": NAMES[G]}
    finals = pd.DataFrame({"game_id": [G], "final_margin": [1.0], "final_total": [5.0]})
    assert parlays.leg_outcome(leg, finals) == "win"
    assert parlays.leg_outcome({**leg, "side": "away"}, finals) == "loss"
    assert parlays._leg_text(leg) == "Sabres @ Jackets: home to win (-115) · P 55%"


def test_the_exchanges_price_the_nhl_on_atlas_and_read_its_close_by_its_own_codes():
    q = nhl_board.quotes(_lines(), _events(), _projections(), 0.5)
    p = trading.priced(q)
    assert (p["p"] == p["p_atlas"]).all()
    pos = p.assign(home_abbr="CBJ", visitor_abbr="BUF").iloc[0]
    close = _lines()[_lines()["book_id"] == bp.CONSENSUS]
    want = probability.no_vig(-115, -105)
    assert trading.close_prob(pos, close, {}) == pytest.approx(want if pos["side"] == "home" else 1 - want)
    total = pos.copy()
    total["market"], total["side"], total["line"] = "total", "under", 6.5
    assert trading.close_prob(total, close, {}) == pytest.approx(0.5)
    total["line"] = 5.5
    assert np.isnan(trading.close_prob(total, close, {}))                         # the close says nothing there


def test_a_broken_projection_costs_the_nhl_board_and_says_so(tmp_path):
    bad = _projections().drop(columns=["kickoff"])
    secs, table, k = nhl_board.build(_lines(), _events(), bad, None, pd.DataFrame(), pd.DataFrame(), NAMES, KEY,
                                     NOW, where=tmp_path / "owner_nhl")
    assert table.empty and k == nhl_board.DEFAULT_SHARE
    assert "could not build the NHL board" in secs[0]["notes"][0]
