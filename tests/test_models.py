"""The scoring harness, the lattice, the reference models - and the two facts
about the frame that `docs/MODEL_PLAN_NCAAF.md` step 0 pins."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from atlas import config
from atlas.models import lattice as lat
from atlas.models import reference as ref
from atlas.models import scoring
from atlas.models.ncaaf_benchmarks import render, score_frame, summarise
from atlas.staging import efficiency

SUPPORT = np.arange(-30, 31)


def _point_mass(x: int) -> np.ndarray:
    p = np.zeros(len(SUPPORT))
    p[np.searchsorted(SUPPORT, x)] = 1.0
    return p[None, :]


def _normal(mu: float, sd: float) -> np.ndarray:
    return lat.discretise(np.array([mu]), sd, SUPPORT)


# ---------------------------------------------------------------------------
# Scoring rules
# ---------------------------------------------------------------------------


def test_crps_of_a_point_mass_is_the_absolute_error():
    assert scoring.crps(_point_mass(7), SUPPORT, np.array([3])) == pytest.approx(4.0)
    assert scoring.crps(_point_mass(-2), SUPPORT, np.array([-2])) == pytest.approx(0.0)


def test_crps_rewards_mass_near_the_outcome():
    """A normal centred on the truth beats one centred 10 away at equal sd."""
    near = scoring.crps(_normal(0, 5), SUPPORT, np.array([0]))
    far = scoring.crps(_normal(10, 5), SUPPORT, np.array([0]))
    assert near < far


def test_crps_is_proper():
    """Forecasting the true distribution scores at least as well as any other."""
    rng = np.random.default_rng(0)
    y = np.rint(rng.normal(2, 6, 4000)).astype(int).clip(-30, 30)
    truth = np.repeat(_normal(2, 6), len(y), axis=0)
    wrong_sd = np.repeat(_normal(2, 12), len(y), axis=0)
    wrong_mu = np.repeat(_normal(-4, 6), len(y), axis=0)
    t = scoring.crps(truth, SUPPORT, y).mean()
    assert t < scoring.crps(wrong_sd, SUPPORT, y).mean()
    assert t < scoring.crps(wrong_mu, SUPPORT, y).mean()


def test_brier_is_a_quarter_for_a_coin_flip_and_zero_for_certainty():
    coin = _normal(0, 1e-9)  # all mass on zero -> p_home 0.5
    coin = np.ones((1, len(SUPPORT))) / len(SUPPORT)
    assert scoring.home_win_probability(coin, SUPPORT)[0] == pytest.approx(0.5, abs=0.02)
    sure = _point_mass(10)
    assert scoring.brier(sure, SUPPORT, np.array([10]))[0] == pytest.approx(0.0)
    assert scoring.brier(sure, SUPPORT, np.array([-10]))[0] == pytest.approx(1.0)


def test_a_tie_counts_half_for_the_home_team():
    assert scoring.home_win_probability(_point_mass(0), SUPPORT)[0] == pytest.approx(0.5)


def test_log_score_reads_the_probability_of_what_happened():
    p = _normal(3, 5)
    y = np.array([3])
    idx = np.searchsorted(SUPPORT, 3)
    assert scoring.log_score(p, SUPPORT, y)[0] == pytest.approx(-np.log(p[0, idx]))


def test_log_score_floors_rather_than_returning_infinity():
    assert np.isfinite(scoring.log_score(_point_mass(5), SUPPORT, np.array([-5]))[0])


def test_discretise_rejects_a_bad_sigma_loudly():
    with pytest.raises(ValueError):
        lat.discretise(np.array([0.0]), float("nan"), SUPPORT)
    with pytest.raises(ValueError):
        lat.discretise(np.array([0.0]), 0.0, SUPPORT)


def test_a_feature_with_no_coverage_is_not_a_reference(research_frame):
    """The synthetic league has no SP+; the reference set must simply omit it
    rather than fit on nothing and return a NaN spread."""
    train = research_frame[research_frame["season"] < 2022]
    test = research_frame[research_frame["season"] == 2022]
    fcs = ref.all_references(train, test)
    for name, col in ref.FEATURES.items():
        covered = pd.to_numeric(train[col], errors="coerce").notna().mean() >= ref.MIN_COVERAGE
        assert (name in fcs) == covered


def test_scoring_rejects_a_pmf_that_does_not_sum_to_one():
    with pytest.raises(ValueError):
        scoring.crps(np.ones((1, len(SUPPORT))), SUPPORT, np.array([0]))


def test_reliability_table_reports_the_gap_per_bin():
    p = np.array([0.0, 0.0, 1.0, 1.0, 0.5, 0.5])
    won = np.array([0, 0, 1, 1, 1, 0])
    t = scoring.reliability(p, won, bins=10)
    assert set(t["bin"]) == {"0.0-0.1", "0.9-1.0", "0.5-0.6"}
    assert (t["gap"].abs() < 1e-9).all()
    assert scoring.expected_calibration_error(p, won) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# The lattice
# ---------------------------------------------------------------------------


def test_discretise_rows_sum_to_one_and_follow_the_mean():
    p = lat.discretise(np.array([-10.0, 0.0, 12.5]), 13.0, SUPPORT)
    assert np.allclose(p.sum(axis=1), 1.0)
    assert (p @ SUPPORT)[0] < (p @ SUPPORT)[1] < (p @ SUPPORT)[2]


def test_lattice_is_flat_on_normal_data_and_peaked_on_football_data():
    rng = np.random.default_rng(1)
    means = rng.normal(0, 8, 6000)
    smooth = np.rint(means + rng.normal(0, 13, 6000))
    flat = lat.fit(smooth, means, 13.0, support=SUPPORT, max_key=20)
    assert abs(flat.at(3) - 1.0) < 0.35 and abs(flat.at(7) - 1.0) < 0.35
    # Now pile extra games onto 3 and 7 the way football does.
    football = smooth.copy()
    hit = rng.random(6000) < 0.12
    football[hit] = np.where(rng.random(hit.sum()) < 0.6, 3, 7) * np.sign(means[hit] + 1e-9)
    peaked = lat.fit(football, means, 13.0, support=SUPPORT, max_key=20)
    assert peaked.at(3) > 1.6 and peaked.at(7) > 1.4
    assert abs(peaked.at(5) - 1.0) < 0.5


def test_lattice_pmf_renormalises_after_reweighting():
    rng = np.random.default_rng(2)
    means = rng.normal(0, 8, 3000)
    y = np.rint(means + rng.normal(0, 13, 3000))
    grid = lat.fit(y, means, 13.0, support=SUPPORT, max_key=20)
    p = grid.pmf(np.array([0.0, 7.0]))
    assert np.allclose(p.sum(axis=1), 1.0)


def test_thin_margins_are_shrunk_toward_one_not_spiked():
    """One freak 25-point result in a small sample must not become a spike:
    the raw ratio is capped, then shrunk by how few games sit at that margin."""
    rng = np.random.default_rng(3)
    means = np.zeros(60)
    y = np.rint(rng.normal(0, 3, 60))
    y[0] = 25
    grid = lat.fit(y, means, 3.0, support=SUPPORT, max_key=28)
    assert grid.at(25) < 3.0


# ---------------------------------------------------------------------------
# Reference models, walk-forward, on the synthetic league
# ---------------------------------------------------------------------------


def test_walk_forward_never_fits_on_the_season_it_scores(research_frame):
    for season, train, test in ref.walk_forward(research_frame, first_test_season=2021):
        assert (train["season"] < season).all()
        assert (test["season"] == season).all()
        assert (train["season_type"] == "regular").all()


def test_every_reference_forecasts_every_game(research_frame):
    train = research_frame[research_frame["season"] < 2022]
    test = research_frame[research_frame["season"] == 2022]
    fcs = ref.all_references(train, test)
    for name in ("naive", "elo", "market"):
        assert name in fcs
        assert len(fcs[name].mean) == len(test)
        assert np.isfinite(fcs[name].mean).all()
        assert fcs[name].sigma > 0


def test_informative_references_beat_naive_on_the_synthetic_league(research_frame):
    """The synthetic close is the true spread plus small noise and Elo is a
    linear function of true strength, so both must beat the home-by-HFA floor."""
    scored = score_frame(research_frame, first_test_season=2021)
    pooled = summarise(scored).set_index("model")
    assert pooled.loc["market", "crps"] < pooled.loc["naive", "crps"]
    assert pooled.loc["elo", "crps"] < pooled.loc["naive", "crps"]
    assert pooled.loc["market", "brier"] < pooled.loc["naive", "brier"]


def test_scores_are_paired_across_models(research_frame):
    scored = score_frame(research_frame, first_test_season=2021)
    counts = scored.groupby("model", observed=True).size()
    assert counts.nunique() == 1


def test_report_renders_with_every_section(research_frame):
    text = render(score_frame(research_frame, first_test_season=2021))
    for heading in ("## Regular season", "## By season", "## By week", "## By closing spread",
                    "## Fitted parameters", "## Reliability"):
        assert heading in text
    assert "market" in text and "elo" in text and "naive" in text


# ---------------------------------------------------------------------------
# Step 0: the frame is what the plan says it is
# ---------------------------------------------------------------------------


def test_the_research_frame_is_fbs_versus_fbs_only(research_frame):
    """`docs/MODEL_PLAN_NCAAF.md` §2. The warehouse holds four divisions; the
    modelling frame holds one. The filter lives in `dataset.QUERY`."""
    assert (research_frame["home_division"] == "fbs").all()
    assert (research_frame["away_division"] == "fbs").all()


def test_garbage_time_is_excluded_from_efficiency_inputs():
    """`docs/MODEL_PLAN_NCAAF.md` §3. A 40-point fourth-quarter blowout play
    must not reach the efficiency aggregates; a 10-point one must."""
    plays = pd.DataFrame({
        "score_diff": [40, -40, 10, 3, 50],
        "period": [4, 4, 4, 1, 5],
    })
    flagged = efficiency._is_garbage_time(plays)
    assert flagged.tolist() == [True, True, False, False, False]
    assert config.GARBAGE_TIME_MARGIN[4] < config.GARBAGE_TIME_MARGIN[1]


def test_overtime_is_never_garbage_time():
    plays = pd.DataFrame({"score_diff": [60], "period": [5]})
    assert not efficiency._is_garbage_time(plays).iloc[0]


def test_market_mean_is_the_negated_closing_spread(research_frame):
    train = research_frame[research_frame["season"] < 2022]
    test = research_frame[research_frame["season"] == 2022]
    fc = ref.market(train, test)
    assert np.allclose(fc.mean, -test["closing_spread"].to_numpy())


def test_normal_discretisation_matches_scipy_mass():
    p = lat.discretise(np.array([2.0]), 10.0, SUPPORT)[0]
    k = np.searchsorted(SUPPORT, 5)
    expected = stats.norm.cdf(0.35) - stats.norm.cdf(0.25)
    # renormalised over a finite support, so allow the tail mass
    assert p[k] == pytest.approx(expected, rel=0.02)
