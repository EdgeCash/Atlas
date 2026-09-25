"""The adjustment engine: does it recover what it claims to, without leaking?"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from atlas.features.opponent_adjustment import (
    DEFAULT_RIDGE,
    METHODS,
    Prior,
    fit,
    point_in_time_ratings,
    schedule_strength,
)


def _synthetic_league(
    *, teams: int = 40, games_per_team: int = 12, unbalanced: bool = False, seed: int = 11
) -> tuple[pd.DataFrame, np.ndarray, np.ndarray]:
    """A league with known actor/opponent effects, optionally with biased schedules."""
    rng = np.random.default_rng(seed)
    actor = rng.normal(0, 0.20, teams)
    opponent = rng.normal(0, 0.15, teams)
    rows = []
    for _ in range(teams * games_per_team // 2):
        a = int(rng.integers(0, teams))
        if unbalanced:
            # Strong teams disproportionately draw *tough* opponents (low
            # opponent effect) and weak teams draw soft ones. That compresses
            # raw averages toward each other, which is exactly the distortion
            # opponent adjustment exists to undo.
            weights = np.exp(-4 * opponent) if actor[a] > 0 else np.exp(4 * opponent)
            weights[a] = 0
            d = int(rng.choice(teams, p=weights / weights.sum()))
        else:
            d = int(rng.choice([t for t in range(teams) if t != a]))
        home = int(rng.integers(0, 2))
        value = 0.05 + actor[a] + opponent[d] + 0.06 * (home - 0.5) + rng.normal(0, 0.22)
        rows.append({"team_id": a, "opponent_id": d, "is_home": bool(home), "value": value})
    return pd.DataFrame(rows), actor, opponent


@pytest.mark.parametrize("method", METHODS)
def test_every_method_recovers_the_true_effects(method):
    obs, actor, _ = _synthetic_league()
    result = fit(obs, method=method)
    ratings = result.ratings.sort_values("team_id")
    estimated = ratings["actor_rating"].to_numpy() - result.league_mean
    assert np.corrcoef(estimated, actor)[0, 1] > 0.8


def test_adjustment_beats_raw_averages_when_schedules_are_unbalanced():
    """The premise of the whole phase, stated as a test."""
    obs, actor, _ = _synthetic_league(unbalanced=True, games_per_team=16)
    raw = obs.groupby("team_id")["value"].mean().sort_index().to_numpy()
    raw_corr = np.corrcoef(raw, actor[: len(raw)])[0, 1]

    result = fit(obs, method="network")
    ratings = result.ratings.sort_values("team_id")
    adjusted = ratings["actor_rating"].to_numpy() - result.league_mean
    adj_corr = np.corrcoef(adjusted, actor[: len(adjusted)])[0, 1]

    assert adj_corr > raw_corr


def test_iterative_and_network_solve_the_same_system():
    obs, _, _ = _synthetic_league()
    a = fit(obs, method="iterative").ratings.sort_values("team_id")
    b = fit(obs, method="network").ratings.sort_values("team_id")
    np.testing.assert_allclose(a["actor_rating"], b["actor_rating"], atol=1e-4)
    np.testing.assert_allclose(a["opponent_rating"], b["opponent_rating"], atol=1e-4)


def test_iteration_converges():
    obs, _, _ = _synthetic_league()
    result = fit(obs, method="iterative")
    assert result.converged
    assert 1 < result.iterations < 100


def test_with_no_games_the_rating_is_exactly_the_prior():
    prior = Prior(actor={7: 0.5}, opponent={7: -0.25}, league_mean=0.1)
    result = fit(pd.DataFrame(columns=["team_id", "opponent_id", "value"]), prior=prior)
    row = result.ratings.set_index("team_id").loc[7]
    assert row["actor_rating"] == pytest.approx(0.6)
    assert row["opponent_rating"] == pytest.approx(-0.15)


def test_weights_are_normalised_so_ridge_stays_in_units_of_games():
    """Play-count weights must not silently rescale the shrinkage.

    Unnormalised, a 4-game prior against ~56 plays per game would be worth
    0.07 of a game. The two fits below differ only by a constant factor on the
    weights, so they must agree.
    """
    obs, _, _ = _synthetic_league()
    small = obs.assign(weight=1.0)
    large = obs.assign(weight=56.0)
    a = fit(small, method="network", ridge=DEFAULT_RIDGE).ratings.sort_values("team_id")
    b = fit(large, method="network", ridge=DEFAULT_RIDGE).ratings.sort_values("team_id")
    np.testing.assert_allclose(a["actor_rating"], b["actor_rating"], atol=1e-9)


def test_point_in_time_ratings_never_use_the_current_week():
    obs, _, _ = _synthetic_league(teams=20, games_per_team=20, seed=5)
    obs["season"] = 2021
    obs["week"] = np.tile(np.arange(1, 11), len(obs) // 10 + 1)[: len(obs)]

    base = point_in_time_ratings(obs, method="network")
    tampered = obs.copy()
    late = tampered["week"] >= 6
    tampered.loc[late, "value"] = tampered.loc[late, "value"] + 50.0
    after = point_in_time_ratings(tampered, method="network")

    early = base[base["week"] <= 6].sort_values(["week", "team_id"]).reset_index(drop=True)
    early_after = after[after["week"] <= 6].sort_values(["week", "team_id"]).reset_index(drop=True)
    pd.testing.assert_frame_equal(early, early_after)


def test_week_one_has_no_in_season_observations():
    obs, _, _ = _synthetic_league(teams=20, games_per_team=10, seed=6)
    obs["season"] = 2021
    obs["week"] = np.tile(np.arange(1, 6), len(obs) // 5 + 1)[: len(obs)]
    ratings = point_in_time_ratings(obs)
    assert (ratings.loc[ratings["week"] == 1, "n_prior_observations"] == 0).all()
    assert (ratings.loc[ratings["week"] > 1, "n_prior_observations"] > 0).all()


def test_prior_season_carries_forward():
    obs, _, _ = _synthetic_league(teams=16, games_per_team=10, seed=7)
    obs["week"] = np.tile(np.arange(1, 6), len(obs) // 5 + 1)[: len(obs)]
    two_seasons = pd.concat(
        [obs.assign(season=2020), obs.assign(season=2021)], ignore_index=True
    )
    ratings = point_in_time_ratings(two_seasons)
    week_one_2021 = ratings[(ratings["season"] == 2021) & (ratings["week"] == 1)]
    # Nothing has been played in 2021, yet the ratings are not all identical:
    # they are last season's, which is the point of the prior.
    assert week_one_2021["actor_rating"].std() > 0


def test_schedule_strength_reports_one_row_per_team_season():
    obs, _, _ = _synthetic_league(teams=20, games_per_team=10, seed=8)
    obs["season"] = 2021
    obs["week"] = np.tile(np.arange(1, 6), len(obs) // 5 + 1)[: len(obs)]
    ratings = point_in_time_ratings(obs)
    strength = schedule_strength(obs, ratings)
    assert strength.groupby(["season", "team_id"]).size().eq(1).all()
    assert strength["mean_opponent_rating"].notna().any()


def test_unknown_method_is_rejected():
    obs, _, _ = _synthetic_league(teams=8, games_per_team=4)
    with pytest.raises(ValueError, match="unknown method"):
        fit(obs, method="magic")


def test_the_bowls_stay_out_of_the_regular_seasons_ratings(tmp_path, monkeypatch):
    """Postseason weeks restart at 1. A week-2 rating must not see December."""
    from atlas.staging import adjusted_efficiency as adj

    rows, eff = [], []
    teams = [1, 2, 3, 4]
    games = [(101, 1, "regular", 1, 2), (102, 1, "regular", 3, 4),
             (201, 2, "regular", 1, 3), (202, 2, "regular", 2, 4),
             (301, 1, "postseason", 1, 4)]
    for gid, week, kind, home, away in games:
        for team, opp, is_home in ((home, away, True), (away, home, False)):
            rows.append({"game_id": gid, "season": 2024, "week": week, "season_type": kind,
                         "kickoff": pd.Timestamp("2024-09-01", tz="UTC"), "team_id": team,
                         "opponent_id": opp, "is_home": is_home})
            # Every regular-season game is dead level; only the bowl is not.
            eff.append({"game_id": gid, "team_id": team, "off_epa": 5.0 if (kind == "postseason" and team == 1)
                        else 0.0, "off_plays": 60})
    monkeypatch.setattr(adj.games_stage, "load_long", lambda staging: pd.DataFrame(rows))
    monkeypatch.setattr(adj.efficiency_stage, "load", lambda staging: pd.DataFrame(eff))
    out = adj.build_adjusted(tmp_path, tmp_path, methods=(adj.PRIMARY_METHOD,))
    week2 = out[(out["week"] == 2) & (out["team_id"] == 1)]
    assert len(week2) and week2["adj_off_epa"].abs().max() < 1e-9
    assert set(teams) >= set(out["team_id"])
