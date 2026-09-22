"""The validation machinery. These tests guard the phase's one real claim:
that the holdout was never touched during threshold selection."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from atlas.research import signal_validation as sv


def _synthetic(edge: float = 0.0, *, seasons=range(2018, 2026), seed: int = 1) -> pd.DataFrame:
    """A league whose totals model has a known, controllable edge."""
    rng = np.random.default_rng(seed)
    rows = []
    game = 0
    for season in seasons:
        for _ in range(700):
            line = rng.normal(54, 7)
            signal = rng.normal(0, 6)
            truth = line + signal + rng.normal(0, 13)
            rows.append(
                {
                    "game_id": game,
                    "season": season,
                    "kickoff": pd.Timestamp(f"{season}-09-01", tz="UTC")
                    + pd.Timedelta(days=game % 100),
                    "closing_total": line,
                    "actual_total": truth,
                    "feature_a": signal * edge + rng.normal(0, 1) * (1 - edge),
                    "feature_b": rng.normal(0, 1),
                    "over_hit": float(truth > line),
                }
            )
            game += 1
    return pd.DataFrame(rows)


FEATURES = ["feature_a", "feature_b"]


# --- the leakage guard -----------------------------------------------------


def test_fit_predict_never_trains_on_the_test_season():
    """A season-specific relationship must be invisible when that season is held out."""
    rng = np.random.default_rng(0)
    n = 4000
    season = rng.choice([2018, 2019, 2020, 2021], size=n)
    # The feature varies everywhere, but only *predicts* in the held-out
    # season. A model fitted on the other three has no way to know that.
    feature = rng.normal(0, 1, n)
    y = np.where(season == 2021, feature * 30, rng.normal(0, 10, n))
    df = pd.DataFrame({"season": season, "feature_a": feature,
                       "feature_b": rng.normal(0, 1, n), "actual_total": y})
    out = sv.fit_predict(df, ["feature_a", "feature_b"], "actual_total",
                         (2018, 2019, 2020), (2021,))
    corr = np.corrcoef(out["prediction"], out["actual_total"])[0, 1]
    assert abs(corr) < 0.3


def test_inner_cv_uses_only_training_seasons():
    df = _synthetic()
    inner = sv.inner_cv_predictions(df, FEATURES, "actual_total", (2018, 2019, 2020))
    assert set(inner["season"].unique()) == {2018, 2019, 2020}


def test_threshold_selection_is_blind_to_the_holdout():
    """Corrupting only the holdout season must not change the frozen threshold."""
    df = _synthetic(edge=0.6)
    train = tuple(range(2018, 2025))
    clean, _ = sv.select_threshold(df, FEATURES, "actual_total", train)

    tampered = df.copy()
    holdout = tampered["season"] == 2025
    tampered.loc[holdout, "actual_total"] = tampered.loc[holdout, "actual_total"] + 500
    tampered.loc[holdout, "feature_a"] = -tampered.loc[holdout, "feature_a"]
    after, _ = sv.select_threshold(tampered, FEATURES, "actual_total", train)

    assert clean == after


# --- the selection rule ----------------------------------------------------


def test_selection_respects_the_bet_floor():
    df = _synthetic(edge=0.5)
    _, grid = sv.select_threshold(df, FEATURES, "actual_total", tuple(range(2018, 2025)))
    chosen = grid[grid["selected"]].iloc[0]
    if grid["bets"].max() >= sv.MIN_TRAINING_BETS:
        assert chosen["bets"] >= sv.MIN_TRAINING_BETS


def test_selection_breaks_ties_to_the_lower_threshold():
    df = _synthetic()
    _, grid = sv.select_threshold(df, FEATURES, "actual_total", tuple(range(2018, 2025)))
    best_units = grid[grid["bets"] >= sv.MIN_TRAINING_BETS]["units"].max()
    tied = grid[(grid["bets"] >= sv.MIN_TRAINING_BETS) & (grid["units"] == best_units)]
    chosen = grid[grid["selected"]]["threshold"].iloc[0]
    assert chosen == tied["threshold"].min()


def test_short_training_windows_fall_back_to_the_grid_minimum():
    df = _synthetic()
    threshold, grid = sv.select_threshold(df, FEATURES, "actual_total", (2018,))
    assert threshold == min(sv.THRESHOLD_GRID)
    assert not bool(grid["selectable"].iloc[0])


# --- scoring ---------------------------------------------------------------


def test_scoring_picks_the_side_of_the_disagreement():
    scored = pd.DataFrame(
        {
            "prediction": [60.0, 40.0],
            "closing_total": [50.0, 50.0],
            "over_hit": [1.0, 1.0],
        }
    )
    bets = sv.score_bets(scored, 5)
    assert bets["pick"].tolist() == ["over", "under"]
    assert bets["win"].tolist() == [1.0, 0.0]


def test_pushes_are_no_action():
    scored = pd.DataFrame(
        {"prediction": [60.0], "closing_total": [50.0], "over_hit": [np.nan]}
    )
    assert sv.score_bets(scored, 5).empty


def test_units_use_the_right_price():
    bets = pd.DataFrame({"win": [1.0] * 52 + [0.0] * 48})
    at_110 = sv.summarise(bets, -110)
    assert at_110["win_rate"] == pytest.approx(0.52)
    # 52 wins at 100/110 minus 48 losses.
    assert at_110["units"] == pytest.approx(52 * (100 / 110) - 48)
    assert not at_110["clears_break_even"]

    winning = pd.DataFrame({"win": [1.0] * 60 + [0.0] * 40})
    assert sv.summarise(winning, -110)["clears_break_even"]


def test_break_even_rates_are_the_textbook_values():
    assert sv.JUICE[-110][0] == pytest.approx(0.523809, abs=1e-5)
    assert sv.JUICE[-105][0] == pytest.approx(0.512195, abs=1e-5)
    assert sv.JUICE[-115][0] == pytest.approx(0.534883, abs=1e-5)
    assert sv.JUICE[-120][0] == pytest.approx(0.545454, abs=1e-5)


# --- bootstrap and criteria ------------------------------------------------


def test_bootstrap_interval_brackets_the_observed_rate():
    wins = pd.Series([1.0] * 520 + [0.0] * 480)
    boot = sv.bootstrap_win_rate(wins, n_boot=2000)
    assert boot["ci_low"] < boot["observed"] < boot["ci_high"]
    assert 0 <= boot["p_above_break_even"] <= 1


def test_bootstrap_of_a_coin_flip_gives_no_confidence():
    rng = np.random.default_rng(2)
    wins = pd.Series(rng.integers(0, 2, 3000).astype(float))
    boot = sv.bootstrap_win_rate(wins, n_boot=2000)
    assert boot["p_above_break_even"] < 0.2
    assert boot["ci_low"] < 0.50 < boot["ci_high"]


def test_criteria_pass_only_when_every_condition_holds():
    strong = pd.DataFrame({"win": [1.0] * 600 + [0.0] * 400})
    walk = pd.DataFrame({"clears_break_even": [True] * 7})
    boot = sv.bootstrap_win_rate(strong["win"], n_boot=2000)
    out = sv.evaluate_criteria(strong, walk, boot)
    assert out["passes"].all()

    weak_seasons = pd.DataFrame({"clears_break_even": [True] * 2 + [False] * 5})
    out = sv.evaluate_criteria(strong, weak_seasons, boot)
    assert not out["passes"].all()


def test_capital_metrics_track_a_known_sequence():
    bets = pd.DataFrame({"win": [0.0] * 5 + [1.0] * 5})
    metrics = sv.capital_metrics(bets)
    assert metrics["longest_losing_streak"] == 5
    assert metrics["max_drawdown"] == pytest.approx(5.0)
    assert metrics["profit_factor"] == pytest.approx(5 * (100 / 110) / 5)


def test_pooled_holdout_never_counts_a_season_twice():
    """Experiments A and B duplicate walk-forward folds; pooling all four would
    double-count 2024 and 2025."""
    assert "A" not in sv.PRIMARY_POOL
    assert "B" not in sv.PRIMARY_POOL
    covered = [e for e in sv.PRIMARY_POOL if e.startswith("WF")]
    assert len(covered) == 7
    assert "C" in sv.PRIMARY_POOL


# --- the machinery detects a real edge when one exists ---------------------


def test_the_whole_pipeline_finds_a_planted_edge():
    """If the validator could not detect a genuine signal, its NO would be worthless."""
    df = _synthetic(edge=0.95, seed=9)
    results = sv.run_all(df, FEATURES)
    pooled = sv.pooled_bets(results)
    assert pooled["win"].mean() > sv.BREAK_EVEN


def test_the_whole_pipeline_rejects_a_pure_noise_model():
    df = _synthetic(edge=0.0, seed=10)
    results = sv.run_all(df, FEATURES)
    pooled = sv.pooled_bets(results)
    boot = sv.bootstrap_win_rate(pooled["win"], n_boot=2000)
    criteria = sv.evaluate_criteria(pooled, results["walk_forward"], boot)
    assert not criteria["passes"].all()
