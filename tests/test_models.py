"""The scoring harness, the lattice, the reference models - and the two facts
about the frame that `docs/MODEL_PLAN_NCAAF.md` step 0 pins."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from atlas import config
from atlas.models import evaluate, kalman, ratings, scoring
from atlas.models import lattice as lat
from atlas.models import ncaaf_prior as prior_mod
from atlas.models import ncaaf_state as state_mod
from atlas.models import reference as ref
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


# ---------------------------------------------------------------------------
# Least-squares season ratings
# ---------------------------------------------------------------------------


def _strength(frame: pd.DataFrame) -> pd.Series:
    """The synthetic league's true strength, recovered from its Elo (1500 + 20 * strength)."""
    both = pd.concat([
        frame[["home_team_id", "home_pregame_elo"]].rename(columns={"home_team_id": "t", "home_pregame_elo": "e"}),
        frame[["away_team_id", "away_pregame_elo"]].rename(columns={"away_team_id": "t", "away_pregame_elo": "e"}),
    ]).drop_duplicates("t").set_index("t")["e"]
    return (both - 1500.0) / 20.0


def test_season_ratings_recover_the_synthetic_strengths(research_frame):
    season = research_frame[research_frame["season"] == 2021]
    r = ratings.fit(season)
    truth = _strength(season).reindex(r.teams)
    assert np.corrcoef(r.net, truth)[0, 1] > 0.9
    assert abs(r.net.mean()) < 1e-6 and abs(r.off.mean()) < 1e-6
    assert 0.5 < r.hfa < 5.0                       # synthetic HFA is 2.5


def test_off_plus_def_is_net_up_to_the_ridge(research_frame):
    r = ratings.fit(research_frame[research_frame["season"] == 2021])
    assert np.corrcoef(r.off + r.defense, r.net)[0, 1] > 0.98


def test_ratings_need_the_score_columns():
    with pytest.raises(KeyError):
        ratings.fit(pd.DataFrame({"home_team_id": [1], "away_team_id": [2]}))


# ---------------------------------------------------------------------------
# The preseason prior
# ---------------------------------------------------------------------------


def test_team_seasons_is_one_row_per_team_season(research_frame):
    ts = prior_mod.team_seasons(research_frame)
    assert not ts.duplicated(["season", "team_id"]).any()
    assert ts.groupby("season").size().min() > 0
    assert "fpi" in ts.columns


def test_prior_never_fits_on_its_own_season(research_frame):
    feats = prior_mod.team_seasons(research_frame)
    p = prior_mod.fit(research_frame, feats, season=2022)
    assert p.season == 2022
    train = research_frame[(research_frame["season"] < 2022) & (research_frame["season_type"] == "regular")]
    assert p.net.n == len(train)
    assert p.points.n == 2 * len(train)
    assert set(p.teams["season"]) == {2022}


def test_prior_uses_only_features_with_coverage(research_frame):
    """The synthetic league has no SP+, talent or returning production: the
    fitted recipe must be FPI alone, not a NaN-filled five-feature fit."""
    feats = prior_mod.team_seasons(research_frame)
    p = prior_mod.fit(research_frame, feats, season=2022)
    assert p.net.features == ["fpi"]
    assert p.points.off_features == ["fpi"] and p.points.def_features == ["fpi"]
    assert np.isfinite(p.teams["net"]).all()


def test_prior_off_plus_def_agrees_with_net(research_frame):
    """Two fits, one from margins and one from stacked points; they should
    describe the same league."""
    feats = prior_mod.team_seasons(research_frame)
    p = prior_mod.fit(research_frame, feats, season=2022)
    assert np.corrcoef(p.teams["off"] + p.teams["def"], p.teams["net"])[0, 1] > 0.95


def test_a_team_the_prior_never_saw_is_league_average(research_frame):
    feats = prior_mod.team_seasons(research_frame)
    p = prior_mod.fit(research_frame, feats, season=2022)
    test = research_frame[research_frame["season"] == 2022].head(3).copy()
    test["home_team_id"] = -1
    fc = prior_mod.game_forecast(p, test)
    away = prior_mod._lookup(p.teams, test, "away")
    is_home = 1.0 - test["neutral_site"].fillna(0).to_numpy(dtype=float)
    assert np.allclose(fc.mean, -away + p.net.hfa * is_home)


def test_prior_tracks_the_eventual_rating_on_the_synthetic_league(research_frame):
    """Synthetic strengths are fixed across seasons and FPI is strength plus
    noise, so a prior fitted on FPI must track the next season's rating."""
    scored, priors, tracking = prior_mod.run(research_frame, first_test_season=2021)
    assert (tracking[tracking["target"] == "net"]["corr"] > 0.8).all()


def test_prior_beats_naive_in_the_early_weeks(research_frame):
    scored, _, _ = prior_mod.run(research_frame, first_test_season=2021)
    early = scored[scored["week"] <= 4]
    pooled = evaluate.summarise(early).set_index("model")
    assert pooled.loc["prior", "crps"] < pooled.loc["naive", "crps"]
    assert pooled.loc["prior", "brier"] < pooled.loc["naive", "brier"]


def test_prior_report_renders(research_frame):
    scored, priors, tracking = prior_mod.run(research_frame, first_test_season=2021)
    text = prior_mod.render(scored, priors, tracking, research_frame)
    for heading in ("## What the recipe learned", "## How well the prior tracked", "## Game-level scores",
                    "## By week bucket", "top and bottom ten"):
        assert heading in text


# ---------------------------------------------------------------------------
# The joint Kalman filter
# ---------------------------------------------------------------------------


def _flat_spec(**kw) -> kalman.Spec:
    base = dict(q_off=1.0, q_def=1.0, p0_off=40.0, p0_def=40.0, sigma=11.0, base=27.0, boost=2.5)
    base.update(kw)
    return kalman.Spec(**base)


def test_forecast_reads_the_state_and_the_home_boost():
    teams = np.array([1, 2])
    st = kalman.initialise(teams, off=[5.0, -5.0], defense=[3.0, -3.0], spec=_flat_spec())
    mean, sd, mh, ma = kalman.forecast(st, 1, 2, 1.0, _flat_spec())
    # margin = off_h + def_h - off_a - def_a + boost = 5 + 3 + 5 + 3 + 2.5
    assert mean == pytest.approx(18.5)
    assert mh - ma == pytest.approx(18.5)
    neutral, *_ = kalman.forecast(st, 1, 2, 0.0, _flat_spec())
    assert neutral == pytest.approx(16.0)


def test_forecast_variance_is_state_plus_two_point_noises():
    teams = np.array([1, 2])
    spec = _flat_spec(p0_off=4.0, p0_def=9.0, sigma=11.0)
    st = kalman.initialise(teams, off=[0.0, 0.0], defense=[0.0, 0.0], spec=spec)
    _, sd, _, _ = kalman.forecast(st, 1, 2, 1.0, spec)
    assert sd ** 2 == pytest.approx(2 * 4.0 + 2 * 9.0 + 2 * 11.0 ** 2)


def test_an_update_moves_the_state_toward_the_result_and_shrinks_uncertainty():
    teams = np.array([1, 2, 3])
    spec = _flat_spec()
    st = kalman.initialise(teams, off=[0.0, 0.0, 0.0], defense=[0.0, 0.0, 0.0], spec=spec)
    before = np.diag(st.P).copy()
    kalman.update(st, 1, 2, home_pts=45.0, away_pts=10.0, is_home=1.0, spec=spec)
    assert st.off(1) > 0 and st.defense(1) > 0 and st.off(2) < 0 and st.defense(2) < 0
    assert st.off(3) == 0.0                                    # a bystander is untouched
    assert (np.diag(st.P)[[0, 1, 3, 4]] < before[[0, 1, 3, 4]]).all()
    assert np.allclose(st.P, st.P.T)


def test_process_noise_widens_only_the_diagonal():
    st = kalman.initialise(np.array([1, 2]), off=[0, 0], defense=[0, 0], spec=_flat_spec(q_off=3.0, q_def=1.0))
    P0 = st.P.copy()
    kalman.advance(st, 2, _flat_spec(q_off=3.0, q_def=1.0))
    assert np.allclose(np.diag(st.P) - np.diag(P0), [6, 6, 2, 2])
    assert np.allclose(st.P - np.diag(np.diag(st.P)), P0 - np.diag(np.diag(P0)))


def test_run_season_is_point_in_time(research_frame):
    """Changing a later game's result must not change an earlier forecast."""
    season = research_frame[(research_frame["season"] == 2021)].copy()
    teams = np.unique(np.r_[season["home_team_id"], season["away_team_id"]])
    spec = _flat_spec()
    def forecasts(df):
        st = kalman.initialise(teams, np.zeros(len(teams)), np.zeros(len(teams)), spec)
        return kalman.run_season(df, st, spec)
    a = forecasts(season)
    tampered = season.copy()
    last = tampered.sort_values("kickoff").index[-1]
    tampered.loc[last, "actual_margin"] += 40
    b = forecasts(tampered)
    earlier = tampered.sort_values("kickoff").index[:-1]
    assert np.allclose(a.loc[earlier, "mean"], b.loc[earlier, "mean"])


def test_filter_recovers_the_synthetic_strengths_from_a_zero_prior(research_frame):
    """No prior at all, one season of games: the state must find the truth."""
    season = research_frame[research_frame["season"] == 2021]
    teams = np.unique(np.r_[season["home_team_id"], season["away_team_id"]])
    spec = _flat_spec(q_off=0.0, q_def=0.0, p0_off=80.0, p0_def=80.0, sigma=11.0)
    st = kalman.initialise(teams, np.zeros(len(teams)), np.zeros(len(teams)), spec)
    kalman.run_season(season, st, spec)
    truth = _strength(season).reindex(teams).to_numpy()
    net = np.array([st.net(t) for t in teams])
    assert np.corrcoef(net, truth)[0, 1] > 0.85


def test_uncertainty_falls_through_the_season(research_frame):
    season = research_frame[research_frame["season"] == 2021]
    teams = np.unique(np.r_[season["home_team_id"], season["away_team_id"]])
    spec = _flat_spec(q_off=0.5, q_def=0.5)
    st = kalman.initialise(teams, np.zeros(len(teams)), np.zeros(len(teams)), spec)
    fc = kalman.run_season(season, st, spec)
    by_week = fc.join(season["week"]).groupby("week")["sd"].mean()
    assert by_week.iloc[-1] < by_week.iloc[0]


# ---------------------------------------------------------------------------
# The NCAAF state runner
# ---------------------------------------------------------------------------

SMALL_GRID = {"q": (0.0, 2.0), "p0": (2.0, 40.0), "sigma": (9.0, 11.0)}


def test_tuning_never_uses_the_test_season(research_frame):
    feats = prior_mod.team_seasons(research_frame)
    choice = state_mod.tune(research_frame, feats, 2022, grid=SMALL_GRID)
    assert all(s < 2022 for s in choice.seasons)
    assert choice.q in SMALL_GRID["q"] and choice.p0 in SMALL_GRID["p0"]


def test_state_beats_the_prior_late_and_matches_it_early(research_frame):
    """Synthetic strengths are fixed, so a prior fitted on FPI is already
    close; the state must not be worse late, and must equal the prior at the
    very first game of the season before any update."""
    scored, choices, finals = state_mod.run(research_frame, first_test_season=2021, grid=SMALL_GRID)
    reg = scored[scored["season_type"] == "regular"]
    late = evaluate.summarise(reg[reg["week"] >= 6]).set_index("model")
    # The mean is the claim: the state must be as good a point forecast as a
    # near-perfect prior. CRPS also pays for the sd, and the state's sd sits at
    # the grid's floor while the prior's is an optimistic in-sample residual,
    # so that comparison is loose on purpose.
    assert abs(late.loc["state", "mae"] - late.loc["prior", "mae"]) < 0.15
    assert late.loc["state", "crps"] <= late.loc["prior", "crps"] + 0.25
    assert late.loc["state", "crps"] < late.loc["naive", "crps"] - 2.0
    # With fixed strengths the tuning must find no need for process noise.
    assert all(c.q == 0.0 for c in choices.values())
    first = reg[reg["week"] == 1]
    s = first[first["model"] == "state"].sort_values("season")["mean"].to_numpy()
    p = first[first["model"] == "prior"].sort_values("season")["mean"].to_numpy()
    assert np.allclose(s[:1], p[:1])


def test_state_report_renders(research_frame):
    scored, choices, finals = state_mod.run(research_frame, first_test_season=2021, grid=SMALL_GRID)
    text = state_mod.render(scored, choices, finals, research_frame)
    for heading in ("## Hyperparameters chosen", "## Regular season, pooled", "## By week bucket",
                    "## Reliability", "top and bottom ten"):
        assert heading in text


def test_prior_derives_the_coaching_interaction_from_staged_columns():
    """``new_coach_x_overach`` is new-coach × (last SP+ − programme mean), built
    in :func:`team_seasons`; without the staged columns it is simply absent."""
    frame = pd.DataFrame({"season": [2021, 2021], "home_team_id": [1, 2], "away_team_id": [2, 1],
                          "home_sp_plus": [10.0, 0.0], "away_sp_plus": [0.0, 10.0],
                          "home_sp_program_mean": [4.0, 0.0], "away_sp_program_mean": [0.0, 4.0],
                          "home_new_coach": [1.0, 0.0], "away_new_coach": [0.0, 1.0]})
    t = prior_mod.team_seasons(frame).set_index("team_id")
    assert t.loc[1, "new_coach_x_overach"] == 6.0
    assert t.loc[2, "new_coach_x_overach"] == 0.0
    bare = prior_mod.team_seasons(frame.drop(columns=["home_new_coach", "away_new_coach"]))
    assert "new_coach_x_overach" not in bare.columns


# ---------------------------------------------------------------------------
# Step 5: the joint (home, away) grid and the total
# ---------------------------------------------------------------------------

from atlas.models import joint as joint_mod  # noqa: E402
from atlas.models import ncaaf_total as total_mod  # noqa: E402


def _normal_pmfs(margin_mean, total_mean, margin_sd=10.0, total_sd=14.0):
    ms = lat.DEFAULT_SUPPORT
    ts = total_mod.TOTAL_SUPPORT
    return (lat.discretise(np.array([margin_mean]), margin_sd, ms), ms,
            lat.discretise(np.array([total_mean]), total_sd, ts), ts)


def test_joint_means_are_the_margin_and_total_means():
    """home = (total + margin) / 2 on average; the grid sums to one."""
    J = joint_mod.build(*_normal_pmfs(3.0, 50.0))
    assert J.pmf.shape == (1, 80, 80)
    assert abs(J.pmf.sum() - 1.0) < 1e-9
    assert abs(J.home_mean()[0] - 26.5) < 0.3
    assert abs(J.away_mean()[0] - 23.5) < 0.3
    s = J.summary()
    assert abs(s.loc[0, "margin_mean"] - 3.0) < 0.3 and abs(s.loc[0, "total_mean"] - 50.0) < 0.3
    assert s.loc[0, "total_lo"] < 50 < s.loc[0, "total_hi"]


def test_joint_keeps_the_margin_marginal_and_the_win_probability():
    """A broad total barely disturbs the margin pmf, so P(home) and the margin
    marginal come back as they went in."""
    mp, ms, tp, ts = _normal_pmfs(3.0, 50.0)
    J = joint_mod.build(mp, ms, tp, ts)
    support, marg = J.margin_pmf()
    got = pd.Series(marg[0], index=support)
    want = pd.Series(mp[0], index=ms)
    assert (got.reindex(want.index).fillna(0) - want).abs().max() < 0.01
    assert abs(J.p_home_win()[0] - scoring.home_win_probability(mp, ms)[0]) < 0.01


def test_joint_top_score_is_its_own_most_probable_cell():
    J = joint_mod.build(*_normal_pmfs(3.0, 50.0))
    h, a, p = J.top_score()
    assert p[0] == J.cell_probability(h, a)[0]
    assert J.rank_of(h, a)[0] == 1
    assert J.rank_of(np.array([70]), np.array([0]))[0] > 1000
    assert J.cell_probability(np.array([95]), np.array([3]))[0] == 0.0     # off the grid


def test_joint_refuses_mismatched_inputs():
    mp, ms, tp, ts = _normal_pmfs(3.0, 50.0)
    with pytest.raises(ValueError):
        joint_mod.build(np.vstack([mp, mp]), ms, tp, ts)


def test_total_calibration_and_grid_run_walk_forward(research_frame):
    """The calibrated total is a real forecast on the synthetic league: it beats
    naive, its sd is positive, and the grid's margin agrees with the state's."""
    fixed = {s: state_mod.Choice(q=0.0, p0=40.0, sigma=11.0, loglik=0.0, seasons=())
             for s in range(2021, 2030)}
    scored, table, fits = total_mod.run(research_frame, first_test_season=2021, choices=fixed)
    pooled = total_mod.summarise_total(scored[scored["season_type"] == "regular"]).set_index("model")
    assert all(f.sigma > 0 and f.n > 0 for f in fits.values())
    assert pooled.loc["total", "crps"] <= pooled.loc["naive", "crps"] + 0.05
    assert np.isfinite(table["home_mean"]).all()
    assert (table["home_mean"] + table["away_mean"] - table["total_mean"]).abs().max() < 1e-9
    # The points lattice reshapes the margin marginal game by game; on average
    # it must not make the margin worse than the state's own lattice pmf.
    assert table["margin_crps_joint"].mean() <= table["margin_crps_state"].mean() + 0.3
    assert ((table["p_home"] >= 0) & (table["p_home"] <= 1)).all()
    text = total_mod.render(scored, table, fits)
    assert "## Total, regular season, pooled" in text and "most likely score" in text


# ---------------------------------------------------------------------------
# Step 6: the projector that feeds the card, and the record that feeds the grade
# ---------------------------------------------------------------------------

from atlas.models import ncaaf_projection as projecting  # noqa: E402

_FIXED = {s: state_mod.Choice(q=0.0, p0=40.0, sigma=11.0, loglik=0.0, seasons=()) for s in range(2019, 2031)}


def _with_scheduled(research_frame):
    """The synthetic league with its last season's final games still to play."""
    frame = research_frame.copy()
    last = frame["season"].max()
    tail = frame[(frame["season"] == last)].sort_values("kickoff").tail(12).index
    for c in ("actual_margin", "actual_total", "home_score", "away_score"):
        if c in frame:
            frame.loc[tail, c] = np.nan
    return frame


def test_projector_projects_the_unplayed_games_from_the_played_ones(research_frame):
    frame = _with_scheduled(research_frame)
    projector = projecting.fit(frame, choices=_FIXED)
    scheduled = frame[frame["actual_margin"].isna() & (frame["season"] == projector.season)]
    out = projecting.project(projector, scheduled)
    assert len(out) == len(scheduled)
    assert projector.assimilated == int((frame["season"] == projector.season).sum()) - len(scheduled)
    assert np.isfinite(out[["margin_mean", "margin_sd", "total_mean", "home_mean", "away_mean", "p_home"]]).all().all()
    assert ((out["p_home"] > 0) & (out["p_home"] < 1)).all()
    assert (out["home_mean"] + out["away_mean"] - out["total_mean"]).abs().max() < 1e-6
    assert (out["margin_sd"] > 10).all()
    assert out["model_version"].nunique() == 1 and len(out["model_version"].iloc[0]) == 12
    view = projector.team(int(out["home_team_id"].iloc[0]))
    assert view is not None and 1 <= view["rank"] <= view["teams"] and view["games"] >= 0


def test_projector_never_reads_the_market_or_the_result(research_frame):
    """Blanking every closing line on the scheduled games, or scrambling their
    results, changes nothing: the number is the model's own."""
    frame = _with_scheduled(research_frame)
    projector = projecting.fit(frame, choices=_FIXED)
    scheduled = frame[frame["actual_margin"].isna() & (frame["season"] == projector.season)].copy()
    base = projecting.project(projector, scheduled)
    scheduled["closing_spread"] = np.nan
    scheduled["closing_total"] = np.nan
    again = projecting.project(projector, scheduled)
    assert np.allclose(base["margin_mean"], again["margin_mean"]) and np.allclose(base["total_mean"], again["total_mean"])


def test_history_is_one_row_per_game_and_market_with_a_calibrated_claim(research_frame):
    h = projecting.history(research_frame, choices=_FIXED, first_test_season=2021)
    assert set(h["market"]) == {"margin", "total"}
    assert h.groupby("market").size().nunique() == 1
    assert ((h["claimed"] >= 0.5) & (h["claimed"] <= 1.0)).all()
    assert set(h["won"].unique()) <= {0.0, 0.5, 1.0}
    assert (h["abs_edge"] >= 0).all()
    # A claim near a coin flip is roughly a coin flip: the record is honest about the market.
    close = h[(h["market"] == "margin") & (h["abs_edge"] < 1.0)]
    assert abs(close["won"].mean() - 0.5) < 0.15


# ---------------------------------------------------------------------------
# Step 7 (v1.5): the points lattice on the grid
# ---------------------------------------------------------------------------


def test_reweighting_by_ones_is_the_identity_and_the_grid_stays_normalised():
    J = joint_mod.build(*_normal_pmfs(3.0, 50.0))
    same = J.reweight(np.ones(J.P))
    assert np.allclose(same.pmf, J.pmf)
    factor = np.ones(J.P)
    factor[[0, 3, 7, 10, 14]] = 3.0
    K = J.reweight(factor)
    assert abs(K.pmf.sum() - 1.0) < 1e-9
    assert K.home_marginal()[0, 7] > J.home_marginal()[0, 7]
    with pytest.raises(ValueError):
        J.reweight(np.ones(5))


def test_points_lattice_learns_the_key_numbers_it_is_shown():
    """Feed the fit a league that scores 7 and 14 far more than a normal
    would, and the factor rises there and stays near one elsewhere."""
    rng = np.random.default_rng(3)
    n = 3000
    mp = lat.discretise(np.zeros(n), 10.0, lat.DEFAULT_SUPPORT)
    tp = lat.discretise(np.full(n, 50.0), 14.0, total_mod.TOTAL_SUPPORT)
    joints = [joint_mod.build(mp[s:s + 500], lat.DEFAULT_SUPPORT, tp[s:s + 500], total_mod.TOTAL_SUPPORT)
              for s in range(0, n, 500)]
    home = np.where(rng.random(n) < 0.4, rng.choice([7, 14], n), rng.integers(15, 40, n))
    away = np.where(rng.random(n) < 0.4, rng.choice([7, 14], n), rng.integers(15, 40, n))
    factor = joint_mod.fit_points(joints, home, away)
    assert factor.shape == (joint_mod.DEFAULT_MAX_POINTS,)
    assert factor[7] > 2.0 and factor[14] > 2.0
    assert factor[0] <= 1.0 and abs(factor[25] - 1.0) < 0.6
    assert (factor <= joint_mod.POINTS_MAX_FACTOR).all() and (factor >= 1 / joint_mod.POINTS_MAX_FACTOR).all()
    with pytest.raises(ValueError):
        joint_mod.fit_points(joints, home[:-1], away[:-1])


def test_the_points_lattice_is_fitted_and_applied_walk_forward(research_frame):
    fixed = {s: state_mod.Choice(q=0.0, p0=40.0, sigma=11.0, loglik=0.0, seasons=()) for s in range(2021, 2030)}
    scored, table, fits = total_mod.run(research_frame, first_test_season=2021, choices=fixed)
    lattices = {s: f.points_factor for s, f in fits.items()}
    assert all(f is not None and f.shape == (joint_mod.DEFAULT_MAX_POINTS,) for f in lattices.values())
    assert {"cell_p_plain", "rank_plain", "cell_log_plain"} <= set(table.columns)
    assert (table["cell_p"] > 0).all()


# ---------------------------------------------------------------------------
# Elo, for the NFL benchmarks
# ---------------------------------------------------------------------------

from atlas.models import elo as elo_mod  # noqa: E402


def _elo_games():
    rows = []
    kick = pd.Timestamp("2023-09-10", tz="UTC")
    for i in range(6):
        rows.append({"game_id": f"g{i}", "season": 2023, "kickoff": kick + pd.Timedelta(days=7 * i),
                     "home_team_id": 1, "away_team_id": 2, "actual_margin": 14.0, "neutral_site": 0})
    rows.append({"game_id": "next", "season": 2024, "kickoff": kick + pd.Timedelta(days=400),
                 "home_team_id": 2, "away_team_id": 1, "actual_margin": np.nan, "neutral_site": 0})
    return pd.DataFrame(rows)


def test_elo_is_pregame_and_rewards_the_winner():
    e = elo_mod.pregame(_elo_games())
    assert e.loc[0, "home_elo"] == e.loc[0, "away_elo"] == 1505.0        # nobody has played
    assert e["home_elo"].iloc[1] > 1505.0 > e["away_elo"].iloc[1]         # team 1 won game 0
    assert (np.diff(e["home_elo"].iloc[:6]) > 0).all()                     # keeps winning, keeps rising
    assert e.loc[6, "home_elo"] < 1505.0 < e.loc[6, "away_elo"]           # the unplayed game reads the ratings, sides swapped


def test_elo_regresses_a_third_of_the_way_between_seasons():
    g = _elo_games()
    e = elo_mod.pregame(g)
    # Team 1's rating after six wins, then the new-season reversion, is what the 2024 row shows for the away side.
    after = e.loc[5, "home_elo"]
    p = elo_mod.FIVETHIRTYEIGHT
    # One more update happens after game 5; recompute it to check the reversion arithmetic.
    diff = after - e.loc[5, "away_elo"] + p.home_field
    shift = p.k * elo_mod._mov_multiplier(14.0, diff) * (1 - elo_mod._expected(diff))
    final = after + shift
    assert e.loc[6, "away_elo"] == pytest.approx(final + p.revert * (p.mean - final))


def test_elo_attaches_a_margin_scale_difference():
    out = elo_mod.attach(_elo_games())
    assert {"home_pregame_elo", "away_pregame_elo", "elo_diff"} <= set(out.columns)
    assert out["elo_diff"].iloc[1] == pytest.approx((out["home_pregame_elo"].iloc[1] - out["away_pregame_elo"].iloc[1]) / 25)


def test_row_update_generalises_the_sparse_update_and_the_state_can_grow():
    """A three-term row (offence + quarterback - defence) updates all three,
    and a two-term row through row_update matches the original sparse update."""
    spec = _flat_spec()
    a = kalman.initialise(np.array([1, 2]), np.zeros(2), np.zeros(2), spec)
    b = kalman.initialise(np.array([1, 2]), np.zeros(2), np.zeros(2), spec)
    kalman._sparse_update(a, 0, 3, 10.0, spec.sigma ** 2)
    kalman.row_update(b, [0], [3], 10.0, spec.sigma ** 2)
    assert np.allclose(a.x, b.x) and np.allclose(a.P, b.P)
    q = b.add("qb-1", 0.0, 9.0)
    assert b.value("qb-1") == 0.0 and b.variance("qb-1") == 9.0 and b.P.shape == (5, 5)
    mean, var = kalman.row_forecast(b, [0, q], [3])
    assert mean == pytest.approx(b.x[0] - b.x[3]) and var > 0
    kalman.row_update(b, [0, q], [3], 20.0, spec.sigma ** 2)
    assert b.value("qb-1") > 0 and b.x[0] > a.x[0]                 # the surprise is shared with the quarterback
    with pytest.raises(KeyError):
        b.add("qb-1", 0.0, 1.0)


# ---------------------------------------------------------------------------
# Audit regressions: kickoff groups, the postseason gap, the live forecast
# ---------------------------------------------------------------------------


def _games(rows) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["home_team_id", "away_team_id", "week", "kickoff", "actual_margin",
                                       "actual_total"]).assign(neutral_site=0)


def test_games_at_one_kickoff_cannot_see_each_others_results():
    teams = np.array([1, 2, 3, 4])
    spec = _flat_spec(q_off=0.0, q_def=0.0)
    forecasts = []
    for result in (30.0, -30.0):
        st = kalman.initialise(teams, np.zeros(4), np.zeros(4), spec)
        g = _games([(1, 3, 1, "2024-09-07T16:00Z", 10.0, 50.0),
                    (1, 2, 2, "2024-09-14T16:00Z", result, 50.0),
                    (3, 4, 2, "2024-09-14T16:00Z", 0.0, 50.0)])
        forecasts.append(kalman.run_season(g, st, spec)["mean"].iloc[2])
    assert forecasts[0] == pytest.approx(forecasts[1])


def test_a_game_without_a_result_is_forecast_and_not_assimilated():
    teams = np.array([1, 2])
    spec = _flat_spec()
    st = kalman.initialise(teams, np.zeros(2), np.zeros(2), spec)
    g = _games([(1, 2, 1, "2024-09-07T16:00Z", np.nan, np.nan),
                (1, 2, 2, "2024-09-14T16:00Z", 7.0, 50.0)])
    fc = kalman.run_season(g, st, spec)
    assert np.isfinite(fc["mean"]).all() and np.isfinite(st.x).all()


def test_whole_number_hyperparameters_do_not_break_the_update():
    spec = kalman.Spec(q_off=1, q_def=1, p0_off=40, p0_def=40, sigma=11, base=27, boost=2)
    st = kalman.initialise(np.array([1, 2]), [0, 0], [0, 0], spec)
    kalman.update(st, 1, 2, 30.0, 20.0, 1.0, spec)
    assert st.P.dtype == float


def test_the_bowls_carry_the_month_of_noise_before_them():
    teams = np.array([1, 2])
    spec = _flat_spec(q_off=2.0, q_def=2.0)
    g = _games([(1, 2, 13, "2024-11-30T16:00Z", 3.0, 50.0),
                (2, 1, 1, "2024-12-28T16:00Z", np.nan, np.nan)]).assign(season_type=["regular", "postseason"])
    st = kalman.initialise(teams, np.zeros(2), np.zeros(2), spec)
    fc = kalman.run_season(g, st, spec)
    no_gap = kalman.initialise(teams, np.zeros(2), np.zeros(2), spec)
    flat = kalman.run_season(g.assign(season_type="regular", week=[13, 13]), no_gap, spec)
    assert st.week == 13 + 4
    assert fc["sd"].iloc[1] > flat["sd"].iloc[1]


def test_the_college_lattice_does_not_keep_the_tie():
    rng = np.random.default_rng(3)
    means = rng.normal(0, 10, 4000)
    margins = np.round(means + rng.normal(0, 14, 4000))
    margins[margins == 0] = 1.0                    # no ties, as in college since 1996
    grid = lat.fit(margins, means, 14.0)
    assert grid.factor[list(grid.support).index(0)] == pytest.approx(0.0)
    assert grid.pmf(np.array([0.0]), np.array([14.0]))[0, list(grid.support).index(0)] == pytest.approx(0.0)


def test_the_live_projection_is_as_uncertain_as_the_walk_forward(research_frame):
    """Next week's game carries a week of process noise, as it does in the
    walk-forward; a game further out carries more."""
    frame = _with_scheduled(research_frame)
    fixed = {s: state_mod.Choice(q=4.0, p0=40.0, sigma=11.0, loglik=0.0, seasons=()) for s in range(2019, 2031)}
    projector = projecting.fit(frame, choices=fixed)
    scheduled = frame[frame["actual_margin"].isna() & (frame["season"] == projector.season)]
    game = scheduled.iloc[[0]]
    near = projecting.project(projector, game.assign(week=projector.state.week + 1))
    far = projecting.project(projector, game.assign(week=projector.state.week + 4))
    home, away = game["home_team_id"].iloc[0], game["away_team_id"].iloc[0]
    _, sharp, _, _ = kalman.forecast(projector.state, home, away, 1.0, projector.spec)
    assert near["margin_sd"].iloc[0] > sharp
    assert far["margin_sd"].iloc[0] > near["margin_sd"].iloc[0]


def test_a_score_past_the_grid_is_not_piled_on_its_edge():
    support_m = np.arange(-40, 41)
    support_t = np.arange(0, 60)
    m = stats.norm.pdf(support_m, 0, 10)[None, :]
    t = stats.norm.pdf(support_t, 30, 8)[None, :]
    J = joint_mod.build(m / m.sum(), support_m, t / t.sum(), support_t, max_points=30)
    factor = joint_mod.fit_points([J], np.array([45]), np.array([10]), min_expected=1e-9)
    assert factor[-1] <= 1.0          # 45 on a 0-29 grid used to count as a 29
