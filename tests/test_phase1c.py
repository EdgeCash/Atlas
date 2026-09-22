"""Phase 1C: the guards that stop a post-hoc measurement being read as a signal."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from atlas.research import qb_features, tracks
from atlas.research import residual_tools as rt
from atlas.warehouse import schema

# --- the boundary: post-kickoff data must never reach the warehouse --------


def test_no_warehouse_table_carries_quarterback_data(synthetic_build):
    """The quarterback of record is known at kickoff at the earliest.

    Phase 1B kept it out of the warehouse on purpose and Phase 1C proved why:
    contemporaneous quarterback variables measure the consequences of a game,
    not information about it. A column like this sitting among point-in-time
    features would be picked up by a feature search and look wonderful.
    """
    for name, table in synthetic_build["tables"].items():
        leaked = [c for c in table.columns if c.startswith("qb_") or "_qb_" in c]
        assert leaked == [], f"{name} leaked quarterback columns: {leaked}"
    for required in schema.REQUIRED.values():
        assert not any(c.startswith("qb_") for c in required)


def test_qb_sources_are_not_imported_by_the_warehouse_build():
    import atlas.warehouse.build as build_module

    source = build_module.__file__
    with open(source) as fh:
        text = fh.read()
    assert "qb_of_record" not in text
    assert "qb_features" not in text


# --- multiple testing ------------------------------------------------------


def test_fdr_is_monotone_and_never_below_p():
    p = pd.Series([0.001, 0.02, 0.04, 0.3, 0.9])
    out = rt.fdr_adjust(p)
    assert (out["q"] >= out["p"] - 1e-12).all()
    assert out["q"].is_monotonic_increasing


def test_fdr_rejects_pure_noise():
    """50 null tests should yield essentially no survivors."""
    rng = np.random.default_rng(0)
    p = pd.Series(rng.uniform(0, 1, 50))
    out = rt.fdr_adjust(p)
    assert out["survives_fdr"].sum() <= 1


def test_pool_excludes_post_hoc_tests_from_the_correction():
    blocks = {
        "a": pd.DataFrame(
            {"effect": ["real", "artefact"], "n": [100, 100], "mean": [1.0, 9.0],
             "t": [2.0, 9.0], "p": [0.04, 1e-12], "pre_kickoff": [True, False]}
        )
    }
    pooled = tracks.pool_tests(**blocks)
    artefact = pooled[pooled["test"] == "artefact"].iloc[0]
    assert artefact["pre_kickoff"] is False or artefact["pre_kickoff"] == False  # noqa: E712
    assert not bool(artefact["survives_fdr"])
    assert pd.isna(artefact["q"])


# --- the disagreement curve ------------------------------------------------


def test_disagreement_curve_detects_a_planted_edge():
    rng = np.random.default_rng(3)
    n = 4000
    line = rng.normal(50, 8, n)
    truth = line + rng.normal(0, 14, n)
    # A model that knows a little of the noise should win more as it disagrees.
    prediction = line + 0.45 * (truth - line) + rng.normal(0, 4, n)
    df = pd.DataFrame(
        {"line": line, "prediction": prediction, "over": (truth > line).astype(float)}
    )
    curve = rt.disagreement_curve(df, "prediction", "line", "over", thresholds=(0, 4, 8))
    assert curve["rate"].iloc[-1] > curve["rate"].iloc[0]
    assert curve["rate"].iloc[-1] > 0.55


def test_disagreement_curve_stays_flat_on_a_useless_model():
    rng = np.random.default_rng(4)
    n = 4000
    line = rng.normal(50, 8, n)
    truth = line + rng.normal(0, 14, n)
    prediction = line + rng.normal(0, 6, n)  # pure noise
    df = pd.DataFrame(
        {"line": line, "prediction": prediction, "over": (truth > line).astype(float)}
    )
    curve = rt.disagreement_curve(df, "prediction", "line", "over", thresholds=(0, 4, 8))
    assert (curve["rate"] - 0.5).abs().max() < 0.05


# --- effect measurement ----------------------------------------------------


def test_signed_effect_folds_both_sides():
    df = pd.DataFrame(
        {
            "flag": [1, -1, 0],
            "market_residual_margin": [4.0, -4.0, 99.0],
        }
    )
    out = rt.signed_effect(df, "flag")
    assert out["n"] == 2
    assert out["mean"] == pytest.approx(4.0)


def test_binary_effect_difference_is_on_minus_off():
    df = pd.DataFrame(
        {
            "flag": [True] * 60 + [False] * 60,
            "market_residual_margin": [2.0] * 60 + [0.0] * 60,
        }
    )
    out = rt.binary_effect(df, "flag")
    assert out["difference"] == pytest.approx(2.0)


def test_bootstrap_ci_brackets_the_mean():
    rng = np.random.default_rng(5)
    values = pd.Series(rng.normal(2.0, 10.0, 2000))
    low, high = rt.bootstrap_ci(values)
    assert low < values.mean() < high


# --- quarterback feature construction --------------------------------------


def test_lagged_events_cannot_see_the_current_game():
    frame = pd.DataFrame(
        {
            "team_id": [1, 1, 1],
            "season": [2021, 2021, 2021],
            "qb_change": [False, True, False],
            "new_starter": [True, True, False],
            "returning_starter": [False, False, False],
            "first_year_player": [False, False, False],
            "inexperienced_starter": [False, False, False],
            "transfer_starter": [False, False, False],
            "backup_start": [False, False, False],
            "committee_game": [False, False, False],
            "planned_change": [False, False, False],
            "in_game_rotation": [False, False, False],
            "qb_share": [1.0, 0.5, 1.0],
            "passers_used": [1, 2, 1],
            "qb_continuity": [np.nan, 0.0, 0.5],
        }
    )
    out = qb_features._add_lagged_events(frame)
    assert pd.isna(out["prior_qb_change"].iloc[0])
    assert out["prior_qb_change"].iloc[2] is True or out["prior_qb_change"].iloc[2] == True  # noqa: E712
    # The lag of row 1 is row 0's value, never row 1's own.
    assert not bool(out["prior_qb_change"].iloc[1])


def test_planned_change_requires_the_replacement_to_take_the_snaps():
    """The distinction the whole track rests on."""
    frame = pd.DataFrame(
        {
            "qb_change": [True, True],
            "qb_share": [0.95, 0.40],
        }
    )
    planned = frame["qb_change"] & (frame["qb_share"].fillna(0) >= 0.9)
    assert planned.tolist() == [True, False]


def test_normalise_name_is_stable_across_punctuation_case_and_accents():
    values = pd.Series(["Ja'Marr O'Brien", "jamarr obrien", "  JaMarr   OBrien ", "Jámarr Obrien"])
    out = qb_features._normalise_name(values)
    assert out.nunique() == 1
    assert out.iloc[0] == "jamarr obrien"


def test_normalise_name_keeps_genuinely_different_names_apart():
    out = qb_features._normalise_name(pd.Series(["Will Rogers", "Will Rogers III"]))
    assert out.nunique() == 2
