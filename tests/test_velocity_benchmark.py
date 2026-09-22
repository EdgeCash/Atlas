"""Phase 2 benchmark mechanics."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from atlas.research import velocity_benchmark as vb


def _scored(n: int = 800, *, skill: float = 0.0, seed: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    line = rng.normal(52, 7, n)
    truth = line + rng.normal(0, 14, n)
    prediction = line + skill * (truth - line) + rng.normal(0, 6, n)
    return pd.DataFrame(
        {
            "season": rng.choice([2021, 2022, 2023, 2024], size=n),
            "prediction": prediction,
            "closing_total": line,
            "actual_total": truth,
            "over_hit": (truth > line).astype(float),
        }
    )


def test_model_versus_market_sign_is_market_minus_model():
    """Positive means the model is better; the sign is easy to invert."""
    df = _scored(skill=0.9)
    out = vb.model_versus_market(df, "closing_total", "actual_total")
    assert out["model_better_by"] == pytest.approx(
        out["market_mae"] - out["model_mae"], rel=1e-9
    )
    assert out["model_better_by"] > 0

    useless = _scored(skill=0.0)
    assert vb.model_versus_market(useless, "closing_total", "actual_total")[
        "model_better_by"
    ] < 0


def test_selection_curve_percentiles_are_taken_within_season():
    """A model whose disagreements grow over time must not have its 'top 1%'
    land entirely in one season and call that selection."""
    df = _scored()
    df.loc[df["season"] == 2024, "prediction"] += 40  # huge disagreements, one year
    curve = vb.selection_curve(df, "closing_total", "over_hit")
    top = curve[curve["top_pct"] == 25].iloc[0]
    # With within-season ranking, every season contributes to the cut.
    df2 = df.copy()
    df2["abs_edge"] = (df2["prediction"] - df2["closing_total"]).abs()
    df2["pct"] = df2.groupby("season")["abs_edge"].rank(pct=True) * 100
    selected = df2[df2["pct"] >= 75]
    assert selected["season"].nunique() == df["season"].nunique()
    assert top["bets"] == len(selected)


def test_selection_curve_detects_a_real_skill_gradient():
    """If the curve could not rise for a genuinely skilful model, its
    flat reading on Atlas would mean nothing."""
    curve = vb.selection_curve(_scored(n=4000, skill=0.8), "closing_total", "over_hit")
    assert curve.loc[curve["top_pct"] == 5, "win_rate"].iloc[0] > curve.loc[
        curve["top_pct"] == 100, "win_rate"
    ].iloc[0]


def test_selection_curve_stays_flat_for_a_useless_model():
    curve = vb.selection_curve(_scored(n=4000, skill=0.0), "closing_total", "over_hit")
    assert (curve["win_rate"] - 0.5).abs().max() < 0.08


def test_win_column_follows_the_side_of_the_disagreement():
    df = pd.DataFrame(
        {
            "season": [2021, 2021],
            "prediction": [70.0, 30.0],
            "closing_total": [50.0, 50.0],
            "over_hit": [1.0, 1.0],
        }
    )
    curve = vb.selection_curve(df, "closing_total", "over_hit")
    # One over pick (wins) and one under pick (loses) => 50%.
    assert curve.loc[curve["top_pct"] == 100, "win_rate"].iloc[0] == pytest.approx(0.5)


def test_selection_by_season_covers_every_season():
    out = vb.selection_by_season(_scored(n=2000), "closing_total", "over_hit", top_pct=25)
    assert set(out["season"]) == {2021, 2022, 2023, 2024}
    assert (out["bets"] > 0).all()


def test_empty_input_returns_empty_frames():
    empty = pd.DataFrame(columns=["season", "prediction", "closing_total", "over_hit"])
    assert vb.selection_curve(empty, "closing_total", "over_hit").empty
    assert vb.selection_by_season(empty, "closing_total", "over_hit").empty
    assert vb.model_versus_market(empty, "closing_total", "actual_total") == {}


# --- the quoted Velocity record --------------------------------------------


def test_quoted_velocity_tables_are_well_formed():
    """These are quoted figures, not computed ones; the test guards typos."""
    card = vb.VELOCITY_NCAAF_CARD
    assert card["share_of_stake"].sum() == pytest.approx(0.87, abs=0.01)
    assert card.loc[card["market"] == "Moneyline", "bets"].iloc[0] == 66

    adverse = vb.VELOCITY_ADVERSE_SELECTION
    assert len(adverse) == 4
    # The finding itself: the highest-edge bucket has the worst CLV.
    assert adverse["clv"].iloc[-1] == adverse["clv"].min()
    assert adverse["clv"].iloc[0] == adverse["clv"].max()

    versus = vb.VELOCITY_MODEL_VS_CLOSE
    assert not versus["model_wins"].all()
    assert versus["model_wins"].any()
