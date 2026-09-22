"""Phase 3 market-aware mechanics.

Two of these tests exist because the measurements they cover were wrong first:
the CLV tautology (grading a side taken at the open against a distance measured
to the close) and the CLV push (grading a line that never moved as a loss).
Both produced large, believable, false results.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from atlas.research import market_aware as ma


def _scored(n: int = 1200, *, skill: float = 0.0, move_skill: float = 0.0,
            seed: int = 11) -> pd.DataFrame:
    """A synthetic book: an opening line, a close that drifts, and a model.

    ``skill`` is how much the model knows about the *result*; ``move_skill`` is
    how much it knows about the market's *revision*. The two are independent,
    which is the distinction Track 4 exists to measure.
    """
    rng = np.random.default_rng(seed)
    opening = rng.normal(52, 7, n).round(1)
    move = rng.choice([-2.0, -1.0, -0.5, 0.0, 0.5, 1.0, 2.0], size=n)
    closing = opening + move
    truth = closing + rng.normal(0, 14, n)
    prediction = (
        closing
        + skill * (truth - closing)
        + move_skill * move * 6
        + rng.normal(0, 5, n)
    )
    return pd.DataFrame(
        {
            "game_id": np.arange(n),
            "season": rng.choice([2021, 2022, 2023, 2024], size=n),
            "week": rng.integers(1, 15, n),
            "prediction": prediction,
            "closing_total": closing,
            "opening_total": opening,
            "actual_total": truth,
            "over_hit": (truth > closing).astype(float),
            "model_sd": 14.0,
        }
    )


MARKET = ma.total_market(["a"])


# ---------------------------------------------------------------------------
# Blending and the fitted weight
# ---------------------------------------------------------------------------


def test_blend_weight_is_on_the_market_not_the_model():
    """``w`` names the market's share. Inverting it silently flips every
    conclusion in Track 1, and both ends of the range look plausible."""
    df = _scored()
    assert ma.blend(df, MARKET, 1.0).equals(pd.to_numeric(df["closing_total"]))
    assert ma.blend(df, MARKET, 0.0).equals(pd.to_numeric(df["prediction"]))


def test_fitted_weight_recovers_a_known_blend():
    """If the truth really is 70% market and 30% model, the regression has to
    say so - otherwise the headline number is just a fitting artefact."""
    rng = np.random.default_rng(5)
    n = 8000
    line = rng.normal(52, 7, n)
    model = line + rng.normal(0, 8, n)
    truth = 0.7 * line + 0.3 * model + rng.normal(0, 10, n)
    df = pd.DataFrame(
        {"prediction": model, "closing_total": line, "actual_total": truth}
    )
    fitted = ma.fit_optimal_weight(df, MARKET)
    assert fitted["model_weight"] == pytest.approx(0.3, abs=0.05)
    assert fitted["market_weight"] == pytest.approx(0.7, abs=0.05)


def test_pure_market_is_perfectly_calibrated_by_construction():
    """At w=1 the blend sits on the line, so every probability is 0.5 and the
    Brier score is exactly the market's 0.25. A deviation means the
    probability construction has drifted off the line it is measured from."""
    df = _scored()
    probs = ma.to_probability(df, MARKET, 1.0)
    assert probs.dropna().eq(0.5).all()
    scores = ma.calibration_scores(probs, df["over_hit"])
    assert scores["brier"] == pytest.approx(0.25, abs=1e-9)


# ---------------------------------------------------------------------------
# The CLV tautology and the CLV push
# ---------------------------------------------------------------------------


def test_clv_is_bucketed_by_distance_to_the_open_not_the_close():
    """The regression test for the tautology.

    The side is taken at the opening number, so the bucket must be measured
    there too. Bucketing by distance to the *close* means a model that simply
    sits on the close is scored as having called every move correctly - which
    read as a 77% beat rate before it was caught.
    """
    assert ma.CLV_BUCKET_COLUMN == "edge_at_open"

    on_the_close = _scored()
    on_the_close["prediction"] = on_the_close["closing_total"]
    audit = ma.clv_audit(on_the_close, MARKET)

    # Graded honestly this model is a tautology and says so: 100% everywhere.
    assert audit["clv_beat_rate"].min() == pytest.approx(1.0)
    # And it lands in the low buckets, because at the OPEN it barely disagrees.
    assert audit["bucket"].iloc[0] == "0-1"


def test_a_line_that_never_moved_is_a_push_not_a_loss():
    """The regression test for the push.

    ``clv_points == 0`` means there was no closing number to beat. Counting
    those as losses dragged the measured beat rate roughly six points below
    its true value and flipped the margin conclusion.
    """
    df = _scored()
    df.loc[df.index[:600], "opening_total"] = df.loc[df.index[:600], "closing_total"]
    frame = ma.add_clv(df, MARKET)

    pushes = frame[frame["clv_push"]]
    assert len(pushes) >= 600
    assert pushes["clv_positive"].isna().all()

    summary = ma.clv_summary(frame).iloc[0]
    assert summary["graded"] == summary["n"] - summary["pushes"]
    graded = frame["clv_positive"].dropna()
    assert summary["beat_rate"] == pytest.approx(graded.mean())


def test_clv_beat_rate_separates_move_skill_from_result_skill():
    """A model that knows where the line is going scores CLV; a model that
    knows the result does not. If these were not separable, Track 4 would be
    measuring the thing Phases 1 and 2 already ruled out."""
    mover = ma.clv_summary(ma.add_clv(_scored(move_skill=1.0), MARKET)).iloc[0]
    picker = ma.clv_summary(ma.add_clv(_scored(skill=0.9), MARKET)).iloc[0]
    assert mover["beat_rate"] > 0.65
    assert picker["beat_rate"] == pytest.approx(0.5, abs=0.06)


def test_placebo_predictors_do_not_beat_the_close():
    """The whole CLV finding rests on this: a predictor that knows nothing
    must fail the same test the real model passes."""
    df = _scored(move_skill=1.0)
    placebo = ma.clv_placebo(df, MARKET).set_index("group")
    assert placebo.loc["Atlas model", "beat_rate"] > 0.65
    for label in placebo.index:
        if label.startswith(("Constant", "Predictions shuffled", "Opening line")):
            assert placebo.loc[label, "beat_rate"] == pytest.approx(0.5, abs=0.06)
    # The known tautology is carried as a scale marker and must read 100%.
    assert placebo.loc["Closing line (known tautology)", "beat_rate"] == pytest.approx(1.0)


def test_won_at_open_settles_against_the_number_actually_taken():
    """A bet struck at the opening line settles at the opening line. Settling
    it at the close mixes the two windows again."""
    df = _scored()
    frame = ma.add_clv(df, MARKET)
    taken_over = frame[frame["side"] > 0]
    expected = (taken_over["actual_total"] > taken_over["opening_total"]).astype(float)
    assert taken_over["won_at_open"].equals(expected.astype(float).rename("won_at_open"))


# ---------------------------------------------------------------------------
# Calibration and the edge audit
# ---------------------------------------------------------------------------


def test_calibration_table_detects_a_planted_overconfidence():
    """An honest model's realised rate tracks its claim; an overconfident one
    sits below the diagonal. The table has to tell them apart."""
    rng = np.random.default_rng(9)
    n = 6000
    honest = rng.uniform(0.5, 0.8, n)
    outcomes = (rng.uniform(size=n) < honest).astype(float)
    good = ma.calibration_table(pd.Series(honest), pd.Series(outcomes))
    # Per-bucket noise is ~3.5pp at these counts, so the claim is about the
    # average bucket, not the worst one.
    assert abs(good["gap"].mean()) < 0.03

    inflated = np.clip(honest + 0.15, 0, 0.99)
    bad = ma.calibration_table(pd.Series(inflated), pd.Series(outcomes))
    assert bad["gap"].mean() < -0.08


def test_edge_audit_excludes_clv():
    """CLV belongs to the opening line and this table is measured at the
    close. Putting them in one table is how the tautology arose."""
    audit = ma.edge_audit(_scored(), MARKET)
    assert not any(column.startswith("clv") for column in audit.columns)


def test_participation_study_keeps_the_no_filter_row_first():
    """Every filter is read against the unfiltered baseline, so it has to be
    the first row and it has to keep every game."""
    study = ma.participation_study(_scored(), MARKET)
    assert study.iloc[0]["filter"].startswith("No filter")
    assert study.iloc[0]["kept"] == pytest.approx(1.0)


def test_detection_sample_size_matches_the_textbook_formula():
    assert ma.detection_sample_size(0.55) == pytest.approx(0.25 * (1.96 / 0.05) ** 2)
    assert np.isinf(ma.detection_sample_size(0.5))


def test_clv_economics_converts_points_to_probability():
    """One point of line is worth phi(0)/sd of win probability. Getting this
    backwards would turn a sub-vig signal into a profitable-looking one."""
    df = _scored()
    econ = ma.clv_economics(df, MARKET, 1.0)
    assert econ["prob_per_point"] == pytest.approx(0.3989 / econ["residual_sd"], rel=1e-3)
    assert econ["implied_win_rate"] == pytest.approx(0.5 + econ["prob_gain"])
    assert ma.clv_economics(df, MARKET, 0.0)["implied_win_rate"] == pytest.approx(0.5)


def test_reliability_svg_keeps_every_mark_inside_the_canvas():
    """A static figure in a report has no scroll: a point outside the viewBox
    is simply invisible, and the chart lies by omission."""
    width, height = 660, 470
    table = pd.DataFrame(
        {"claimed": [0.51, 0.55, 0.60, 0.69], "actual": [0.50, 0.52, 0.49, 0.50],
         "n": [100, 400, 900, 2000]}
    )
    svg = ma.reliability_svg({"margin": table, "total": table}, width=width, height=height)
    assert svg.startswith("<svg") and svg.rstrip().endswith("</svg>")
    import re

    for cx, cy, r in re.findall(
        r'<circle cx="([\d.]+)" cy="([\d.]+)" r="([\d.]+)"', svg
    ):
        assert 0 <= float(cx) - float(r) and float(cx) + float(r) <= width
        assert 0 <= float(cy) - float(r) and float(cy) + float(r) <= height
