"""The NHL game model (docs/MODEL_PLAN_NHL.md, steps 3 to 5): the filters, the league's rates, the expected
starter, the point-in-time walk, and the score grid. Synthetic data."""

from __future__ import annotations

import numpy as np
import pandas as pd

from atlas.models import nhl_grid as grid
from atlas.models import nhl_model
from atlas.models import nhl_state as st


def test_a_filter_moves_toward_what_it_sees_and_stays_symmetric():
    f = st.Filter.empty()
    a, b = f.add("a", 1.0), f.add("b", 1.0)
    f.update([a, b], [1.0, -1.0], 2.0, 1.0)
    assert f.x[a] > 0 > f.x[b] and np.isclose(f.x[a], -f.x[b])
    assert np.allclose(f.P, f.P.T) and np.all(np.linalg.eigvalsh(f.P) > 0)
    assert f.P[a, a] < 1.0 and f.P[a, b] > 0                          # learning the gap ties the two together


def test_the_league_rate_is_a_ratio_of_sums_not_a_mean_of_ratios():
    lg = st.League()
    base = {"toi_5v5": 2880, "toi_PP": 240, "toi_EV": 0, "opp_toi_PP": 240, "goals_5v5": 2, "goals_PP": 1,
            "goals_SH": 0, "goals_EV": 0, "fenwick_5v5": 40, "fenwick_PP": 8, "drawn": 2, "penalties": 2,
            "fenwicka_all": 45, "hours": 1.0, "reg_hours": 1.0}
    for i in range(3000):
        # half the games one goal from a trickle of expected goals, half none from plenty
        lg.learn({**base, "goals_all": 1 if i % 2 else 0, "xg_all": 0.2 if i % 2 else 2.0})
    assert np.isclose(lg.kappa, 1 / 2.2, rtol=0.02)                   # a mean of ratios would say about 2.5
    assert np.isclose(lg.rate5, 2 / 0.8, rtol=0.01) and np.isclose(lg.pp_per_pen, 2.0, rtol=0.01)


def test_the_goalie_who_started_last_night_is_marked_down():
    m = st.Model.new(st.Spec(b2b_starter=0.25))
    m.starts["NJD"] = {1: 0.7, 2: 0.3}
    m.last_start["NJD"] = (pd.Timestamp("2025-10-10"), 1)
    rested = m.starter_probs("NJD", pd.Timestamp("2025-10-12"))
    second = m.starter_probs("NJD", pd.Timestamp("2025-10-11"))
    assert np.isclose(rested[1], 0.7) and np.isclose(second[1], 0.7 * 0.25 / (0.7 * 0.25 + 0.3))


def _league(n_days=120):
    """Four teams; ``AAA`` makes twice the expected goals of anyone else at 5-on-5."""
    teams = ["AAA", "BBB", "CCC", "DDD"]
    games, team_games, goalies = [], [], []
    gid = 0
    for d in range(n_days):
        day = pd.Timestamp("2021-10-01", tz="UTC") + pd.Timedelta(days=d)
        for h, a in ((teams[d % 4], teams[(d + 1) % 4]), (teams[(d + 2) % 4], teams[(d + 3) % 4])):
            gid += 1
            games.append({"game_id": gid, "season": 2021, "season_type": "regular", "kickoff": day,
                          "home_team": h, "away_team": a, "home_b2b": False, "away_b2b": False, "completed": True})
            for team, opp in ((h, a), (a, h)):
                xg = 2.4 if team == "AAA" else 1.2 if opp == "AAA" else 1.8
                row = {"game_id": gid, "team": team}
                for k in ("5v5", "PP", "SH", "EV", "EN", "ENA"):
                    row.update({f"xg_{k}": 0.0, f"goals_{k}": 0, f"fenwick_{k}": 0, f"fenwicka_{k}": 0, f"toi_{k}": 0})
                row.update(xg_5v5=xg, goals_5v5=round(xg), fenwick_5v5=30, fenwicka_5v5=30, toi_5v5=2880, toi_PP=240,
                           xg_PP=0.6, goals_PP=1, fenwick_PP=6, penalties=2, drawn=2)
                team_games.append(row)
                goalies.append({"game_id": gid, "player_id": 100 + teams.index(team), "team": team, "started": 1,
                                "toi": 3600, "unblocked_faced": 36, "ga_pbp": 2, "xga": 2.0})
    return pd.DataFrame(games), pd.DataFrame(team_games), pd.DataFrame(goalies)


def test_the_walk_forecasts_before_it_learns_and_finds_the_strong_team():
    games, team_games, goalies = _league()
    f, model = st.walk(games, team_games, goalies, st.Spec())
    first = f.iloc[0]
    assert np.isclose(first["off_home"], 0) and np.isclose(first["off_away"], 0)     # nothing seen yet
    k = model.five.index[("off", "AAA")]
    others = [model.five.x[model.five.index[("off", t)]] for t in ("BBB", "CCC", "DDD")]
    assert model.five.x[k] > max(others) + 0.3
    late = f.merge(games, on="game_id").tail(40)
    aaa_home = late[late["home_team"] == "AAA"]
    assert (aaa_home["lambda_home"] > aaa_home["lambda_away"]).all()
    assert model.starts["AAA"][100] > 0.9                                            # the only starter


def _layer():
    late = {m: np.full((4, 4), 1 / 16) for m in range(-3, 4)}
    return grid.Season(late=late, tie=0.12, early=0.93, stretch=1.2, ot_intercept=0.04, ot_slope=0.3)


def test_the_grid_gives_overtime_its_one_goal_and_agrees_with_the_fast_path():
    layer = _layer()
    s = grid.summary(3.3, 2.8, layer, edge=0.2)
    fin = s["grid"]
    assert np.isclose(fin.sum(), 1.0) and np.isclose(np.trace(fin), 0.0)             # no final is level
    assert 0.5 < s["p_home"] < 0.75 and 0.1 < s["p_ot"] < 0.35
    assert np.isclose(s["p_reg_home"] + s["p_reg_away"] + s["p_ot"], 1.0)
    assert s["p_home_minus_1_5"] < s["p_reg_home"] and s["p_over_5.5"] > s["p_over_6.5"]
    lh, la = grid.stretched(3.3, 2.8, layer.stretch, 0.2)
    assert np.isclose(lh + la, 6.1) and np.isclose(float(grid.p_home_fast([lh], [la], layer)[0]), s["p_home"],
                                                   atol=1e-3)


def test_the_stretch_widens_the_teams_gap_and_leaves_home_ice_alone():
    lh, la = grid.stretched(3.2, 3.0, 1.5, 0.2)
    assert np.isclose(lh, 3.2) and np.isclose(la, 3.0)                  # the whole gap is home ice
    lh, la = grid.stretched(3.6, 2.8, 1.5, 0.2)
    assert np.isclose(lh - la, 0.2 + 1.5 * 0.6) and np.isclose(lh + la, 6.4)


def test_the_late_table_is_fitted_from_the_score_at_55_minutes():
    games = pd.DataFrame({"game_id": [1, 2, 3], "season": 2020, "season_type": "regular", "completed": True,
                          "reg_home": [3, 2, 2], "reg_away": [1, 2, 1]})
    goals = pd.DataFrame({"game_id": [1, 1, 1, 1, 2, 2, 2, 2, 3, 3, 3],
                          "period": 3, "seconds": [100, 200, 3000, 3500, 100, 200, 300, 3550, 100, 200, 3400],
                          "is_home": [True, True, False, True, True, False, True, False, True, False, True]})
    at = grid.score_at(goals, games)
    assert at.loc[1].tolist() == [2, 1] and at.loc[2].tolist() == [2, 1] and at.loc[3].tolist() == [1, 1]
    table = grid.fit_late(at, games, [2020])
    assert all(np.isclose(t.sum(), 1.0) for t in table.values())
    assert table[1][1, 0] > table[1][0, 0] and table[1][0, 1] > table[1][0, 0]      # an empty-netter, a tying goal


def test_the_scores_rank_a_sharp_forecast_above_a_blunt_one():
    outcome = np.array([0, 2, 1, 0])
    sharp = nhl_model.rps3(np.array([0.8, 0.1, 0.2, 0.7]), np.array([0.1, 0.1, 0.6, 0.2]), outcome)
    blunt = nhl_model.rps3(np.full(4, 0.4), np.full(4, 0.2), outcome)
    assert sharp < blunt
    support = np.arange(10)
    step = (support >= 5).astype(float)
    assert nhl_model.crps_discrete([step], support, np.array([5])) == 0.0
