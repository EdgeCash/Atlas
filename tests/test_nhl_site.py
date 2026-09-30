"""The NHL in the product (docs/MODEL_PLAN_NHL.md, step 6): the grade's record, the market's close from the
poll, a confirmed starter re-pricing a game, and the board and cards passing the site's audit. Synthetic."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from atlas.live.store import Store
from atlas.models import nhl_grid as grid
from atlas.models import nhl_projection as proj
from atlas.site import grade as grading
from atlas.site import nhl as nhl_site

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 10, 1, 16, 0, tzinfo=UTC)


def test_the_record_scores_the_side_atlas_rated_above_the_market():
    history = pd.DataFrame({"game_id": [1, 2, 3], "season": 2020, "season_type": "regular", "completed": True,
                            "kickoff": pd.to_datetime(["2020-10-01", "2020-10-09", "2020-10-20"], utc=True),
                            "p_home": [0.60, 0.40, 0.52], "home_score": [3, 3, 1], "away_score": [2, 1, 4]})
    market = pd.DataFrame({"game_id": [1, 2, 3], "p_market": [0.55, 0.45, 0.52]})
    cal = proj.calibration(history, market).set_index("game_id")
    assert cal.loc[1, "abs_edge"] == 5.0 and cal.loc[1, "claimed"] == 0.60 and cal.loc[1, "won"] == 1
    assert cal.loc[2, "claimed"] == 0.60 and cal.loc[2, "won"] == 0              # Atlas's side was the away side
    assert cal.loc[3, "abs_edge"] == 0.0 and cal.loc[3, "won"] == 0
    assert cal["week"].tolist() == [1, 2, 3] and set(cal["market"]) == {"moneyline"} and set(cal["sport"]) == {"nhl"}


def test_the_close_is_the_last_moneyline_before_puck_drop():
    games = pd.DataFrame({"game_id": [10, 11], "sport": ["nhl", "nfl"], "kickoff": ["2026-10-01T23:00Z"] * 2})
    snaps = pd.DataFrame({"game_id": [10, 10, 10, 11], "market": "moneyline",
                          "captured_at": ["2026-10-01T20:00Z", "2026-10-01T22:45Z", "2026-10-01T23:30Z",
                                          "2026-10-01T22:00Z"],
                          "price": [-120.0, -150.0, -400.0, -110.0], "other_price": [100.0, 130.0, 300.0, -110.0]})
    c = proj.closes(snaps, games)
    assert c["game_id"].tolist() == [10]
    assert np.isclose(c["p_market"].iloc[0], (150 / 250) / (150 / 250 + 100 / 230))


def _layer():
    late = {m: np.full((4, 4), 1 / 16) for m in range(-3, 4)}
    return grid.Season(late=late, tie=0.1, early=0.93, stretch=1.3, ot_intercept=0.04, ot_slope=0.3)


def _projection(p_home=0.55):
    return {"game_id": 401000001, "nhl_game_id": 2026020020, "season": 2026, "kickoff": "2026-10-02T23:00:00+00:00",
            "home_team": "PHI", "away_team": "PIT", "home_b2b": False, "away_b2b": True, "lambda_home": 3.1,
            "lambda_away": 2.8, "home_edge": 0.24, "home_mean": 3.2, "away_mean": 2.9, "total_mean": 6.1,
            "p_home": p_home, "p_reg_home": 0.42, "p_reg_away": 0.36, "p_ot": 0.22, "p_ot_home": 0.52,
            "p_home_minus_1_5": 0.31, "p_away_minus_1_5": 0.26, "p_over_4.5": 0.75, "p_over_5.5": 0.55,
            "p_over_6.5": 0.44, "p_over_7.5": 0.25, "top": json.dumps([[3, 2, 0.07], [2, 3, 0.06]]),
            "off_home": 0.1, "def_home": 0.2, "pp_home": -0.3, "pk_home": 0.5, "finish_home": 0.02, "goalie_home": 0.1,
            "off_away": 0.05, "def_away": 0.0, "pp_away": 0.2, "pk_away": -0.1, "finish_away": -0.03, "goalie_away": -0.05,
            "home_goalies": json.dumps([{"id": 1, "name": "Home One", "p": 0.9, "gsax": 0.1},
                                        {"id": 2, "name": "Home Two", "p": 0.1, "gsax": -0.2}]),
            "away_goalies": json.dumps([{"id": 3, "name": "Away One", "p": 0.4, "gsax": 0.2},
                                        {"id": 4, "name": "Away Two", "p": 0.6, "gsax": -0.2}]),
            "model_version": proj.VERSION, "refreshed_at": "2026-10-01T08:00:00+00:00"}


def test_a_confirmed_starter_moves_the_other_sides_goals_by_the_gap():
    p = _projection()
    p["goalie_away"] = 0.4 * 0.2 + 0.6 * -0.2                                  # the expectation, -0.04
    base = proj.reprice(p, _layer())
    better = proj.reprice(p, _layer(), away_starter=3)                          # the away side's better goalie
    assert better["p_home"] < base["p_home"] and better["away_starter"] == 3
    worse = proj.reprice(p, _layer(), away_starter=4)
    assert worse["p_home"] > base["p_home"]


def _store(tmp_path) -> Store:
    store = Store.open(tmp_path / "tracking")
    store.write("nhl_projections", pd.DataFrame([_projection()]))
    store.write("games", pd.DataFrame([{"game_id": 401000001, "sport": "nhl", "season": 2026,
                                        "kickoff": "2026-10-02T23:00Z", "home_team": "Philadelphia Flyers",
                                        "away_team": "Pittsburgh Penguins"},
                                       {"game_id": 401000000, "sport": "nhl", "season": 2026,
                                        "kickoff": "2026-09-30T23:00Z", "home_team": "Boston Bruins",
                                        "away_team": "Chicago Blackhawks"}]))
    store.write("snapshots", pd.DataFrame([
        {"captured_at": "2026-10-01T12:00:00+00:00", "game_id": 401000001, "book": "DraftKings", "market": "moneyline",
         "price": -130.0, "other_price": 110.0, "open_price": -125.0},
        {"captured_at": "2026-10-01T12:00:00+00:00", "game_id": 401000001, "book": "DraftKings", "market": "margin",
         "line": 1.5, "price": 190.0, "other_price": -230.0},
        {"captured_at": "2026-10-01T12:00:00+00:00", "game_id": 401000001, "book": "DraftKings", "market": "total",
         "line": 6.5, "price": 105.0, "other_price": -125.0, "open_line": 6.5}]))
    return store


def _bands():
    return {label: grading.Band(label, 500, 0.52 + 0.01 * i, 0.51, -0.01 - 0.01 * i, 10, 6)
            for i, label in enumerate(("0-1", "1-2", "2-4", "4-6", "6-8", "8-10", "10+"))}


def test_the_cards_are_graded_in_points_of_win_probability_and_pass_the_audit(tmp_path):
    store = _store(tmp_path)
    curve = grading.Curve(a=0.015, p=0.47, games=3500, r=0.7, seasons=10)
    cards = nhl_site.build_cards(store, {}, {}, NOW, bands=_bands(), curve=curve)
    assert len(cards) == 1
    card = cards[0]
    assert card.title == "Penguins at Flyers" and card.path == "nhl/pittsburgh-penguins-at-philadelphia-flyers.html"
    market = (130 / 230) / (130 / 230 + 100 / 210)
    assert np.isclose(card.market_home, market) and np.isclose(card.disagreement, 100 * (0.55 - market))
    assert card.grade is not None and "points of win probability" in " ".join(card.grade.lesson)
    assert card.week == 1
    out = tmp_path / "site"
    (out / "assets").mkdir(parents=True)
    paths = nhl_site.write(out, cards, bands=_bands(), overall_band=grading.overall(_bands()),
                           freshness={"projection": "Oct 1, 4:00 AM ET", "market": "Oct 1, 12:00 PM ET"})
    assert paths == ["nhl.html", card.path]
    page = (out / card.path).read_text()
    assert "not a recommendation" in page and "Flyers −1.5" in page and "Home One" in page
    assert "second night of a back-to-back" in page
    sys.path.insert(0, str(ROOT / "scripts"))
    import audit_site

    blocking, advisory = audit_site.audit(out)
    assert not any(blocking.values()), blocking
    assert not any(v for k, v in advisory.items() if k != "missing canonical"), advisory


def test_a_game_with_no_moneyline_stands_ungraded_and_says_why(tmp_path):
    store = _store(tmp_path)
    store.write("snapshots", pd.DataFrame(columns=store.read("snapshots").columns))
    cards = nhl_site.build_cards(store, {}, {}, NOW, bands=_bands(),
                                 curve=grading.Curve(a=0.015, p=0.47, games=3500, r=0.7, seasons=10))
    assert cards[0].grade is None and cards[0].market_home is None
    page = nhl_site.card_page(cards[0])
    assert "No moneyline is posted yet" in page and "not a recommendation" in page


def test_a_game_underway_leaves_the_board(tmp_path):
    store = _store(tmp_path)
    assert nhl_site.build_cards(store, {}, {}, datetime(2026, 10, 2, 23, 5, tzinfo=UTC)) == []
    board = nhl_site.board_page([])
    assert "No NHL game in the next eight days" in board
