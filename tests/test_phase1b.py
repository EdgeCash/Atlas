"""Phase 1B staging, weather and study plumbing."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from atlas.research import adjustment_study as study
from atlas.research import models
from atlas.staging import adjusted_efficiency as adjusted_stage
from atlas.staging import weather as weather_stage
from atlas.warehouse import schema

# --- adjusted efficiency staging -------------------------------------------


def test_every_required_adjusted_metric_is_produced(synthetic_build):
    table = synthetic_build["tables"]["adjusted_efficiency_metrics"]
    assert schema.check("adjusted_efficiency_metrics", table.columns) == []


def test_all_three_methods_are_stored(synthetic_build):
    adjusted = adjusted_stage.load(synthetic_build["paths"].staging)
    for column in adjusted_stage.all_adjusted_columns():
        assert column in adjusted.columns, column


def test_adjusted_differences_are_consistent(synthetic_build):
    table = synthetic_build["tables"]["adjusted_efficiency_metrics"].dropna(
        subset=["home_adj_off_epa", "away_adj_off_epa"]
    )
    np.testing.assert_allclose(
        table["adj_off_epa_diff"],
        table["home_adj_off_epa"] - table["away_adj_off_epa"],
        rtol=1e-9,
    )


def test_adjusted_rating_is_constant_within_a_team_week(synthetic_build):
    """A week's rating is one number per team, whoever they play that week."""
    adjusted = adjusted_stage.load(synthetic_build["paths"].staging)
    counts = adjusted.groupby(["season", "week", "team_id"])["adj_off_epa"].nunique()
    assert counts.max() <= 1


def test_schedule_strength_is_written(synthetic_build):
    strength = adjusted_stage.load_schedule_strength(synthetic_build["paths"].staging)
    assert not strength.empty
    assert {"season", "team_id", "mean_opponent_rating", "stream"}.issubset(strength.columns)


# --- weather ---------------------------------------------------------------


def test_weather_is_matched_from_cached_station_files(synthetic_build):
    weather = weather_stage.load(synthetic_build["paths"].staging)
    matched = weather["weather_temp"].notna()
    assert matched.mean() > 0.8
    assert weather["weather_station_miles"].dropna().max() < 60


def test_weather_units_are_plausible(synthetic_build):
    weather = weather_stage.load(synthetic_build["paths"].staging).dropna(
        subset=["weather_temp"]
    )
    assert weather["weather_temp"].between(-40, 130).all()
    assert weather["weather_wind"].between(0, 100).all()
    assert weather["weather_humidity"].between(0, 100).all()


def test_domes_have_no_effective_wind(synthetic_build):
    weather = weather_stage.load(synthetic_build["paths"].staging)
    indoors = weather[weather["venue_dome"].fillna(False).astype(bool)]
    if indoors.empty:
        pytest.skip("synthetic league has no domes")
    assert (indoors["weather_wind_effective"] == 0).all()


def test_weather_degrades_to_empty_without_a_station_catalogue(tmp_path, monkeypatch):
    """A missing weather source must never fail the warehouse build."""
    monkeypatch.setenv("ATLAS_OFFLINE", "1")
    games = pd.DataFrame(
        {
            "game_id": [1, 2],
            "season": [2021, 2021],
            "kickoff": pd.to_datetime(["2021-09-04", "2021-09-11"], utc=True),
            "venue_id": [10, 11],
            "home_division": ["fbs", "fbs"],
            "away_division": ["fbs", "fbs"],
        }
    )
    teams = pd.DataFrame(
        {
            "season": [2021],
            "team_id": [1],
            "venue_id": [10],
            "venue_name": ["x"],
            "latitude": [33.0],
            "longitude": [-87.0],
            "elevation": [50.0],
            "dome": [False],
            "school": ["X"],
        }
    )
    out = weather_stage.build_weather(tmp_path, tmp_path, games, teams)
    assert len(out) == 2
    assert out["weather_temp"].isna().all()


# --- study plumbing --------------------------------------------------------


def test_residual_target_baseline_is_the_market_not_the_mean(research_frame):
    baselines = study.baseline_metrics(research_frame).set_index("target")
    assert baselines.loc["residual_margin", "baseline"] == "market is exactly right"
    assert baselines.loc["margin", "baseline"] == "season mean"


def test_residual_target_is_actual_minus_market(research_frame):
    df = research_frame.dropna(subset=["market_residual_margin", "closing_spread"])
    np.testing.assert_allclose(
        df["market_residual_margin"],
        df["actual_margin"] + df["closing_spread"],
        rtol=1e-9,
    )


def test_null_fold_with_a_constant_predicts_that_constant(research_frame):
    fold = models.null_fold(research_frame, "market_residual_margin", constant=0.0)
    assert (fold.y_pred == 0).all()
    assert models.metrics(fold)["mae"] == pytest.approx(
        research_frame["market_residual_margin"].abs().mean(), rel=1e-6
    )


def test_feature_set_uses_sums_for_totals_and_diffs_for_margin():
    assert study.feature_set(["adj_off_epa"], "margin") == ["adj_off_epa_diff"]
    assert study.feature_set(["adj_off_epa"], "total") == ["adj_off_epa_sum"]
    assert study.feature_set(["adj_off_epa"], "residual_total") == ["adj_off_epa_sum"]


def test_residual_models_do_not_refit_home_advantage():
    """The closing line already prices HFA; a residual model must not re-add it."""
    assert study.structural_for("margin") == ["neutral_site_flag"]
    assert study.structural_for("residual_margin") == []


def test_unavailable_features_are_reported_not_dropped(research_frame):
    df = research_frame.copy()
    df["adj_off_epa_diff"] = np.nan
    df["adj_def_epa_diff"] = np.nan
    result = study.evaluate(df, ["adj_off_epa_diff", "adj_def_epa_diff"], "margin")
    assert result["available"] is False


def test_wind_buckets_carry_their_error_bars(research_frame):
    buckets = study.wind_buckets(research_frame)
    if buckets.empty:
        pytest.skip("no weather in the synthetic sample")
    assert {"over_rate_z", "significant"}.issubset(buckets.columns)
    expected = (buckets["over_rate"] - 0.5) / np.sqrt(0.25 / buckets["settled"])
    np.testing.assert_allclose(buckets["over_rate_z"], expected, rtol=1e-9)
