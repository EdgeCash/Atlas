"""The NHL warehouse's staging (docs/MODEL_PLAN_NHL.md, step 1): the score as sixty minutes left it, rest,
the geometry and strength of every shot, and the team-game totals for and against. Synthetic data."""

from __future__ import annotations

import numpy as np
import pandas as pd

from atlas.staging.nhl import build as nhl_build
from atlas.staging.nhl import games as games_stage
from atlas.staging.nhl import shots as shots_stage

CODE = {1: "NJD", 2: "NYI", 53: "ARI", 27: "PHX"}


def _raw_games():
    return pd.DataFrame([
        # a regulation win, an overtime win, a shootout win, a playoff second overtime, one unplayed
        {"game_id": 1, "season": 2025, "game_type": 2, "date": "2025-10-08", "start_et": "2025-10-08T19:00:00",
         "home_id": 1, "away_id": 2, "home_score": 4, "away_score": 2, "period": 3, "state": 7},
        {"game_id": 2, "season": 2025, "game_type": 2, "date": "2025-10-09", "start_et": "2025-10-09T19:00:00",
         "home_id": 2, "away_id": 1, "home_score": 3, "away_score": 2, "period": 4, "state": 7},
        {"game_id": 3, "season": 2025, "game_type": 2, "date": "2025-10-12", "start_et": "2025-10-12T19:00:00",
         "home_id": 1, "away_id": 53, "home_score": 2, "away_score": 3, "period": 5, "state": 7},
        {"game_id": 4, "season": 2025, "game_type": 3, "date": "2026-04-20", "start_et": "2026-04-20T19:00:00",
         "home_id": 2, "away_id": 1, "home_score": 1, "away_score": 2, "period": 5, "state": 7},
        {"game_id": 5, "season": 2025, "game_type": 2, "date": "2026-04-30", "start_et": "2026-04-30T19:00:00",
         "home_id": 1, "away_id": 2, "home_score": 0, "away_score": 0, "period": None, "state": 1},
    ])


def test_the_final_the_regulation_score_and_how_it_was_decided():
    g = games_stage.normalise(_raw_games(), {1: "NJD", 2: "NYI", 53: "UTA"}).set_index("game_id")
    assert g["decision"].tolist()[:4] == ["REG", "OT", "SO", "OT"]            # a playoff fifth period is overtime
    assert (g.loc[2, "reg_home"], g.loc[2, "reg_away"]) == (2, 2)           # overtime's single goal off
    assert (g.loc[3, "home_goals"], g.loc[3, "away_goals"]) == (2, 2)       # the shootout goal off
    assert (g.loc[3, "reg_home"], g.loc[3, "reg_away"]) == (2, 2)
    assert g.loc[3, "actual_margin"] == 0 and g.loc[1, "actual_margin"] == 2 and g.loc[1, "actual_total"] == 6
    assert g.loc[4, "season_type"] == "postseason" and (g.loc[4, "reg_home"], g.loc[4, "reg_away"]) == (1, 1)
    assert not g.loc[5, "completed"] and pd.isna(g.loc[5, "actual_margin"]) and pd.isna(g.loc[5, "decision"])
    assert str(g.loc[1, "kickoff"]) == "2025-10-08 23:00:00+00:00"                      # Eastern to UTC
    assert g.loc[3, "away_team"] == "UTA" and g.loc[1, "home_team_id"] == games_stage.TEAM_ID["NJD"]


def test_rest_and_the_second_night_of_a_back_to_back():
    g = games_stage.normalise(_raw_games(), {1: "NJD", 2: "NYI", 53: "UTA"}).set_index("game_id")
    assert pd.isna(g.loc[1, "home_days_rest"]) and not g.loc[1, "home_b2b"]
    assert g.loc[2, "home_days_rest"] == 1 and g.loc[2, "home_b2b"] and g.loc[2, "away_b2b"]
    assert g.loc[3, "home_days_rest"] == 3 and not g.loc[3, "home_b2b"]


def test_the_strength_state_from_the_shooting_side():
    s = shots_stage.strength(own_sk=[5, 5, 4, 6, 5, 4], opp_sk=[5, 4, 5, 5, 6, 4], own_g=[1, 1, 1, 0, 1, 1],
                             opp_g=[1, 1, 1, 1, 0, 1])
    assert s.tolist() == ["5v5", "PP", "SH", "ENA", "EN", "EV"]


def _shots():
    base = {"season": 2025, "period": 1, "period_type": "REG", "shot_type": "wrist", "goalie_id": 30,
            "home_score": 0, "away_score": 0, "prev_event": "faceoff", "prev_x": 0, "prev_y": 0, "prev_seconds": 0,
            "blocker_id": None, "penalty_type": None, "penalty_minutes": None}
    return pd.DataFrame([
        # home (NJD) defends the right end, so attacks the net at x = -89
        {**base, "game_id": 1, "event_id": 1, "sort_order": 1, "seconds": 30, "situation": "1551",
         "event": "shot-on-goal", "team_id": 1, "x": -79, "y": 0, "shooter_id": 10, "home_defends": "right",
         "prev_team_id": 2},
        {**base, "game_id": 1, "event_id": 2, "sort_order": 2, "seconds": 32, "situation": "1551", "event": "goal",
         "team_id": 1, "x": -86, "y": 3, "shooter_id": 11, "home_defends": "right", "prev_event": "shot-on-goal",
         "prev_team_id": 1, "prev_x": -79, "prev_y": 0, "prev_seconds": 30},
        # the away side on the power play, shooting at x = +89
        {**base, "game_id": 1, "event_id": 3, "sort_order": 3, "seconds": 200, "situation": "1541",
         "event": "missed-shot", "team_id": 2, "x": 59, "y": -30, "shooter_id": 20, "home_defends": "right",
         "home_score": 1, "prev_team_id": 1},
        # an older game with no side in the feed: read from where the team's attempts cluster
        {**base, "game_id": 2, "event_id": 1, "sort_order": 1, "seconds": 50, "situation": "1551",
         "event": "shot-on-goal", "team_id": 2, "x": 70, "y": 10, "shooter_id": 20, "home_defends": None,
         "prev_team_id": 1},
        {**base, "game_id": 2, "event_id": 2, "sort_order": 2, "seconds": 90, "situation": "0651",
         "event": "blocked-shot", "team_id": 2, "x": 60, "y": 0, "shooter_id": 20, "blocker_id": 12,
         "home_defends": None, "prev_team_id": 1},
    ])


def _staged():
    games = games_stage.normalise(_raw_games(), {1: "NJD", 2: "NYI", 53: "UTA"})
    roster = pd.DataFrame({"game_id": [1, 1, 1, 2, 2], "player_id": [10, 11, 20, 20, 12],
                           "team": ["NJD", "NJD", "NYI", "NYI", "NJD"]})
    return games, shots_stage.features(_shots(), games, roster, {1: "NJD", 2: "NYI"})


def test_every_attempt_gets_its_geometry_and_state():
    _, f = _staged()
    a = f.set_index(["game_id", "event_id"])
    assert a.loc[(1, 1), "distance"] == 10 and a.loc[(1, 1), "angle"] == 0
    assert np.isclose(a.loc[(1, 2), "distance"], np.hypot(3, 3)) and a.loc[(1, 2), "rebound"]
    assert np.isclose(a.loc[(1, 3), "distance"], np.hypot(30, 30)) and a.loc[(1, 3), "strength"] == "PP"
    assert a.loc[(1, 3), "score_diff"] == -1 and not a.loc[(1, 3), "is_home"]
    assert a.loc[(2, 1), "distance"] == np.hypot(19, 10)                           # the side read from the cluster
    blocked = a.loc[(2, 2)]
    assert blocked["shooting_team"] == "NYI" and not blocked["unblocked"] and blocked["strength"] == "EN"   # at home: the away net is empty


def test_team_games_count_for_and_against_in_mirrored_states():
    games, f = _staged()
    f = f.assign(xg=[0.1, 0.4, 0.05, 0.08, 0.0])
    toi = shots_stage.toi(pd.DataFrame({"game_id": [1, 1], "season": 2025, "situation": ["1551", "1541"],
                                        "seconds": [3480, 120]}), games)
    pens = pd.DataFrame({"game_id": [1], "team": ["NJD"], "penalties": [1], "pim": [2]})
    t = nhl_build.team_games(f, toi, games, pens).set_index(["game_id", "team"])
    njd, nyi = t.loc[(1, "NJD")], t.loc[(1, "NYI")]
    assert njd["goals_5v5"] == 1 and njd["sog_5v5"] == 2 and np.isclose(njd["xg_5v5"], 0.5)
    assert nyi["fenwick_PP"] == 1 and njd["fenwicka_SH"] == 1 and np.isclose(njd["xga_SH"], 0.05)
    assert njd["toi_SH"] == 120 and nyi["toi_PP"] == 120 and njd["toi_5v5"] == 3480
    assert njd["penalties"] == 1 and nyi["drawn"] == 1 and njd["goals_for"] == 4 and nyi["goals_against"] == 4


def test_the_archive_matches_games_a_day_either_way():
    games = games_stage.normalise(_raw_games(), {1: "NJD", 2: "NYI", 53: "UTA"})
    raw = pd.DataFrame([{"season": 2025, "date": "2025-10-10", "home": "NYI", "away": "NJD", "home_ml_close": -120},
                        {"season": 2025, "date": "2025-10-12", "home": "NJD", "away": "ARI", "home_ml_close": 110}])

    class Raw:
        pass

    import atlas.staging.nhl.build as b

    original = b.games_stage.load
    b.games_stage.load = lambda raw_, kind, seasons: raw
    try:
        out = b.odds(Raw(), [2025], games)
    finally:
        b.games_stage.load = original
    assert out.set_index("date")["game_id"].to_dict() == {"2025-10-10": 2, "2025-10-12": 3}
