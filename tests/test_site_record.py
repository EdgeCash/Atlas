"""The public model record: projections made before kickoff, graded against the final score."""

from __future__ import annotations

import pandas as pd
import pytest

from atlas.site import record, render


def _proj(game, made, *, sport="ncaaf", home=30.0, away=20.0, version="v1", kickoff="2026-09-26T16:00:00Z"):
    return {"sport": sport, "game_id": game, "season": 2026, "week": 4, "kickoff": kickoff, "home_mean": home,
            "away_mean": away, "margin_mean": home - away, "total_mean": home + away, "model_version": version,
            "refreshed_at": made}


def test_only_a_projection_made_before_kickoff_counts():
    projections = pd.DataFrame([
        _proj(1, "2026-09-25T08:00:00+00:00", home=31.0),                   # the last one before kickoff
        _proj(1, "2026-09-24T08:00:00+00:00", home=40.0, version="v0"),
        _proj(1, "2026-09-26T17:00:00+00:00", home=99.0, version="v2"),     # made during the game: never counts
        _proj(2, "2026-09-26T17:00:00+00:00"),                               # nothing before kickoff: not graded
        {**_proj(3, "2026-09-25T08:00:00+00:00"), "sport": None},           # rows from before sport was kept
    ])
    got = record.before_kickoff(projections).set_index("game_id")
    assert got.loc[1, "home_mean"] == 31.0 and 2 not in got.index and got.loc[3, "sport"] == "ncaaf"


def test_every_game_is_graded_and_the_market_beside_it_on_the_same_games():
    projections = pd.DataFrame([_proj(1, "2026-09-25T08:00:00+00:00", home=30.0, away=20.0),
                                _proj(2, "2026-09-25T08:00:00+00:00", home=24.0, away=21.0)])
    finals = pd.DataFrame({"game_id": ["1", "2"], "final_home": [27.0, 17.0], "final_away": [20.0, 24.0]})
    market = pd.DataFrame({"game_id": ["1"], "market_margin": [3.0], "market_total": [47.0]})
    g = record.graded(projections, finals, market, {"1": ("Georgia", "Oklahoma")}).set_index("game_id")
    assert g.loc["1", "margin_miss"] == 3.0 and g.loc["1", "total_miss"] == 3.0     # 10 vs 7; 50 vs 47
    assert g.loc["1", "market_margin_miss"] == 4.0 and g.loc["1", "market_total_miss"] == 0.0
    assert g.loc["1", "winner_right"] == 1.0 and g.loc["2", "winner_right"] == 0.0 # 24-21 home; 17-24 final
    assert (g.loc["1", "home"], g.loc["1", "away"]) == ("Georgia", "Oklahoma")
    s = record.summary(g.reset_index())
    assert s["games"] == 2 and s["with_market"] == 1 and s["atlas_closer"] == 1 and s["closer_of"] == 1
    assert s["margin_miss"] == pytest.approx((3.0 + 10.0) / 2)


def test_the_page_states_facts_and_says_nothing_of_what_to_do():
    empty = render.record_page({}, since="with the week of 24 September 2026")
    assert "No game is graded yet" in empty and 'href="record.csv"' in empty
    summary = {"games": 2, "margin_miss": 6.5, "total_miss": 4.0, "winner_right": 0.5, "winner_games": 2,
               "with_market": 1, "atlas_margin_miss_there": 3.0, "market_margin_miss": 4.0, "atlas_closer": 1,
               "closer_of": 1, "with_market_total": 1, "atlas_total_miss_there": 3.0, "market_total_miss": 0.0}
    game = {"away": "Oklahoma", "home": "Georgia", "proj_away": 20.0, "proj_home": 30.0, "final_away": 20,
            "final_home": 27, "margin_miss": 3.0, "total_miss": 3.0, "market_margin_miss": 4.0,
            "market_total_miss": 0.0}
    week = {"season": 2026, "week": 4, "games": 2, "margin_miss": 6.5, "total_miss": 4.0, "winner_right": 0.5,
            "market_margin_miss": 4.0, "market_total_miss": 0.0}
    page = render.record_page({"ncaaf": {"summary": summary, "weekly": [week], "latest": [game]}}, since="today")
    assert "Oklahoma @ Georgia" in page and "projected 20.0–30.0 · final 20–27" in page and "3.0 · 3.0" in page
    assert "Atlas's was the closer of the two in 1 of 1" in page
    for word in (" bet", "pick", "wager", "lock", "units"):
        assert word not in page.lower()


def test_a_refresh_never_projects_a_game_that_has_kicked_off():
    from atlas.live.__main__ import _before_kickoff

    rows = pd.DataFrame({"game_id": [1, 2], "kickoff": ["2026-09-24T23:30:00Z", "2026-09-26T16:00:00Z"]})
    kept = _before_kickoff(rows, "2026-09-25T00:53:43+00:00")
    assert list(kept["game_id"]) == [2]                   # the game in progress keeps its pre-kickoff number
