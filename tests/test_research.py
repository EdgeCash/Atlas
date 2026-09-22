"""Research plumbing: honest folds, working metrics, a report that renders."""

from __future__ import annotations

import numpy as np
import pandas as pd

from atlas.research import benchmarks, importance, models, report, validation
from atlas.research.dataset import available_features, candidates, feature_matrix


def test_leave_one_season_out_never_trains_on_the_held_out_season():
    """A feature that only works in one season must not help in that season."""
    rng = np.random.default_rng(0)
    n = 900
    season = rng.choice([2020, 2021, 2022], size=n)
    giveaway = np.where(season == 2022, rng.normal(0, 1, n), 0.0)
    y = np.where(season == 2022, giveaway * 10, rng.normal(0, 10, n))
    df = pd.DataFrame({"season": season, "giveaway": giveaway, "y": y})

    fold = models.leave_one_season_out(df, ["giveaway"], "y")
    held_out = fold.season == 2022
    # In 2022 the relationship is real but was never visible in training, so
    # the out-of-sample fit must not capture it.
    corr = np.corrcoef(fold.y_pred[held_out], fold.y_true[held_out])[0, 1]
    assert abs(corr) < 0.3


def test_metrics_are_arithmetically_right():
    fold = models.FoldPredictions(
        np.array([0.0, 10.0]), np.array([2.0, 12.0]), np.array([2021, 2021]), ["x"]
    )
    m = models.metrics(fold)
    assert m["mae"] == 2.0
    assert m["rmse"] == 2.0
    assert m["bias"] == 2.0
    assert m["n"] == 2


def test_feature_matrix_imputes_and_drops_empty_columns():
    df = pd.DataFrame({"a": [1.0, np.nan, 3.0], "b": [np.nan] * 3, "c": [5.0, 5.0, 5.0]})
    X, cols = feature_matrix(df, ["a", "b", "c", "missing"])
    assert cols == ["a"]  # b is empty, c is constant, missing does not exist
    assert not np.isnan(X).any()


def test_benchmarks_mark_unavailable_variables_rather_than_dropping_them(research_frame):
    df = research_frame.copy()
    df["sp_plus_diff"] = np.nan
    out = benchmarks.run_benchmarks(df)
    sp = out[(out["benchmark"] == "SP+ Only") & (out["target"] == "margin")].iloc[0]
    assert sp["available"] is False or sp["available"] == False  # noqa: E712
    assert "sp_plus_diff" in sp["missing_features"]


def test_ranking_is_ordered_by_measured_gain(research_frame):
    ranked = importance.rank_variables(research_frame)
    margin = ranked[(ranked["target"] == "margin") & ranked["available"]]
    gains = margin["standalone_gain"].to_numpy()
    assert (np.diff(gains) <= 1e-9).all(), "ranking must be sorted by standalone gain"
    assert margin.iloc[0]["rank_standalone"] == 1


def test_a_pure_noise_variable_earns_no_gain(research_frame):
    rng = np.random.default_rng(7)
    df = research_frame.copy()
    df["noise"] = rng.normal(0, 1, len(df))
    fold = models.leave_one_season_out(df, ["noise"], "actual_margin")
    noise_mae = models.metrics(fold)["mae"]
    baseline = importance._baseline_mae(df, "actual_margin")
    # Fitting noise can only match the baseline, never beat it by anything real.
    assert noise_mae >= baseline - 0.25


def test_leakage_scan_catches_an_outcome_in_disguise(research_frame):
    df = research_frame.copy()
    df["cheating_feature"] = df["actual_margin"] + 0.001
    scan = validation.leakage_scan(df, ["cheating_feature"], ["actual_margin"])
    assert bool(scan.iloc[0]["suspicious"]) is True


def test_real_features_are_not_flagged_as_leaking(research_frame):
    feats = available_features(
        research_frame, sorted({f for c in candidates() for f in c.margin_features})
    )
    scan = validation.leakage_scan(research_frame, feats, ["actual_margin", "actual_total"])
    assert not scan["suspicious"].any()


def test_classification_reports_a_sane_base_rate(research_frame):
    out = importance.classification_power(research_frame, ["closing_spread"], "home_cover")
    assert 0.3 < out["base_rate"] < 0.7
    assert 0.0 <= out["accuracy"] <= 1.0


def test_report_renders_end_to_end(synthetic_build, research_frame):
    path = report.write_report(
        seed_frame=report.load_research_frame(synthetic_build["paths"].warehouse)
    )
    text = path.read_text()
    for heading in (
        "## Section 1 - Data Coverage",
        "## Section 2 - Market Performance",
        "## Section 3 - SP+ Performance",
        "## Section 4 - FPI Performance",
        "## Section 5 - Feature Importance Ranking",
        "## Section 6 - Preliminary Conclusions",
    ):
        assert heading in text
    assert "nan" not in text.lower().replace("unavailable", "")
    tables = path.parent / "tables"
    assert (tables / "benchmarks.csv").exists()
    assert (tables / "ranking.csv").exists()
