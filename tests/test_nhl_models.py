"""The NHL's models (docs/MODEL_PLAN_NHL.md, step 2): expected goals fitted walk-forward a season at a time,
and the benchmarks the game model must beat. Synthetic data."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from atlas.models import nhl_benchmarks as bench
from atlas.models import nhl_xg


def _shots(seasons=(2010, 2011, 2012, 2013), n=4000, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for season in seasons:
        d = rng.uniform(3, 70, n)
        a = rng.uniform(0, 80, n)
        p = 1 / (1 + np.exp(-(-0.5 - 0.07 * d)))
        rows.append(pd.DataFrame({
            "season": season, "distance": d, "angle": a, "shot_type": rng.choice(["wrist", "snap", "slap", None], n),
            "rebound": rng.random(n) < 0.05, "rush": rng.random(n) < 0.03,
            "strength": rng.choice(["5v5", "PP", "SH", "EN"], n, p=[0.8, 0.15, 0.03, 0.02]),
            "unblocked": rng.random(n) < 0.75, "goal": rng.random(n) < p}))
    return pd.concat(rows, ignore_index=True)


def test_each_season_is_fitted_on_the_three_before_it():
    assert nhl_xg.training(2010) == (2010, 2011, 2012) == nhl_xg.training(2012)    # the burn-in
    assert nhl_xg.training(2013) == (2010, 2011, 2012) and nhl_xg.training(2026) == (2023, 2024, 2025)


def test_expected_goals_fall_with_distance_and_a_blocked_attempt_has_none(tmp_path):
    shots = _shots()
    model = nhl_xg.ensure(shots, None, tmp_path)
    assert sorted(model["by_season"]) == ["2010", "2011", "2012", "2013"]
    assert (tmp_path / "reports" / "nhl_xg.json").exists()
    params = model["by_season"]["2013"]
    assert params["coef"][params["columns"].index("d")] < 0 or params["coef"][params["columns"].index("logd")] < 0
    test = pd.DataFrame({"season": 2013, "distance": [5.0, 50.0, 5.0, 30.0], "angle": [10.0, 10.0, 10.0, 0.0],
                         "shot_type": ["wrist"] * 4, "rebound": False, "rush": False,
                         "strength": ["5v5", "5v5", "5v5", "EN"], "unblocked": [True, True, False, True]})
    xg = nhl_xg.predict(test, model)
    assert xg[0] > xg[1] > 0 and xg[2] == 0.0 and 0 < xg[3] < 1


def test_a_season_is_fitted_once_and_a_later_one_borrows_the_latest(tmp_path):
    shots = _shots()
    model = nhl_xg.ensure(shots, None, tmp_path)
    stamp = json.dumps(model["by_season"]["2012"])
    again = nhl_xg.ensure(_shots(seed=5), model, tmp_path)
    assert json.dumps(again["by_season"]["2012"]) == stamp                     # never refitted
    assert nhl_xg.params_for(model, 2030) is model["by_season"]["2013"]
    assert nhl_xg.params_for({"by_season": {}}, 2020) is None
    blank = nhl_xg.apply(shots.head(3), None)
    assert blank["xg"].isna().all()


def _games():
    rows = []
    for season in (2015, 2016, 2017):
        for i in range(40):
            home_wins = i % 5 != 0
            rows.append({"game_id": season * 1000 + i, "season": season, "season_type": "regular",
                         "kickoff": pd.Timestamp(f"{season}-11-01", tz="UTC") + pd.Timedelta(days=i),
                         "home_team": "AAA" if i % 2 else "BBB", "away_team": "BBB" if i % 2 else "AAA",
                         "home_team_id": 1 if i % 2 else 2, "away_team_id": 2 if i % 2 else 1,
                         "home_score": 3 if home_wins else 1, "away_score": 1 if home_wins else 3,
                         "reg_home": 3 if home_wins else 1, "reg_away": 1 if home_wins else 3, "completed": True})
    return pd.DataFrame(rows)


def test_the_naive_rate_is_the_seasons_before():
    g = _games()
    n = bench.naive(g)
    assert np.isclose(n[g["season"] == 2016].iloc[0], 0.8) and np.isclose(n[g["season"] == 2015].iloc[0], 0.537)


def test_the_poisson_grid_and_the_market_without_its_margin():
    p = bench.grid_probabilities(np.array([3.0, 3.5]), np.array([3.0, 2.5]), ot_home=0.5)
    assert np.isclose(p[0], 0.5, atol=1e-4) and p[1] > 0.6          # twelve goals a side: 3e-5 left out
    g = pd.DataFrame({"game_id": [1, 2]})
    odds = pd.DataFrame({"game_id": [1], "home_ml_close": [-150.0], "away_ml_close": [130.0]})
    m = bench.market(g, odds)
    assert np.isclose(m[0], 0.6 / (0.6 + 100 / 230)) and pd.isna(m[1])


def test_elo_learns_the_team_that_keeps_winning():
    g = _games()
    g.loc[g["home_team"] == "AAA", ["home_score", "away_score"]] = [4, 1]
    g.loc[g["away_team"] == "AAA", ["home_score", "away_score"]] = [1, 4]
    from atlas.models import elo

    p = bench.elo_forecast(g, elo.Params(k=8, home_field=30, mean=1505, revert=0.3))
    late = g["season"] == 2017
    aaa_home = late & (g["home_team"] == "AAA")
    assert p[aaa_home].mean() > 0.6 and p[late & ~aaa_home].mean() < 0.4
