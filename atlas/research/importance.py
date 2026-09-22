"""Research Task 2: which variables actually carry information.

Four complementary views, because any single one is easy to fool:

standalone
    Fit each candidate variable on its own (leave-one-season-out) and measure
    how much MAE it takes off a constant baseline. Answers "does this know
    anything at all?"
marginal over market
    Refit market-plus-candidate against market-alone. Answers the only
    question that matters for a market-facing model: "does this know anything
    the closing line does not already know?"
permutation
    Out-of-sample permutation importance inside one full gradient-boosted
    model, so correlated variables compete against each other instead of each
    taking credit for the same signal.
direction
    Standardised ridge coefficients, purely so the report can say which way a
    variable pushes.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from atlas import config
from atlas.research import models
from atlas.research.benchmarks import STRUCTURAL
from atlas.research.dataset import Candidate, available_features, candidates, feature_matrix
from atlas.util import get_logger

LOG = get_logger(__name__)

MARKET = {"margin": ["closing_spread"], "total": ["closing_total"]}
TARGETS = {"margin": "actual_margin", "total": "actual_total"}


def _features_for(cand: Candidate, target: str) -> list[str]:
    return cand.margin_features if target == "margin" else cand.total_features


def _baseline_mae(df: pd.DataFrame, target_col: str) -> float:
    """MAE of predicting each season from the other seasons' mean."""
    y = pd.to_numeric(df[target_col], errors="coerce")
    seasons = df["season"]
    errs = []
    for season in seasons.unique():
        train = y[(seasons != season) & y.notna()]
        test = y[(seasons == season) & y.notna()]
        if len(train) == 0 or len(test) == 0:
            continue
        errs.append(np.abs(test - train.mean()))
    return float(pd.concat(errs).mean()) if errs else float("nan")


def standalone_power(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for target, target_col in TARGETS.items():
        base = _baseline_mae(df, target_col)
        for cand in candidates():
            wanted = _features_for(cand, target)
            usable = available_features(df, wanted)
            if not usable:
                rows.append({
                    "variable": cand.name, "target": target, "available": False,
                    "n_features": 0, "mae": np.nan, "mae_gain": np.nan, "note": cand.note,
                })
                continue
            feats = usable + (STRUCTURAL if target == "margin" else [])
            fold = models.leave_one_season_out(df, feats, target_col)
            m = models.metrics(fold)
            rows.append({
                "variable": cand.name, "target": target, "available": True,
                "n_features": len(usable), "mae": m["mae"], "mae_gain": base - m["mae"],
                "rmse": m["rmse"], "r2": m["r2"], "note": cand.note,
            })
    out = pd.DataFrame(rows)
    out.attrs["baseline_mae"] = {t: _baseline_mae(df, c) for t, c in TARGETS.items()}
    return out.sort_values(["target", "mae_gain"], ascending=[True, False], na_position="last")


def marginal_over_market(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for target, target_col in TARGETS.items():
        market = available_features(df, MARKET[target])
        struct = STRUCTURAL if target == "margin" else []
        base_fold = models.leave_one_season_out(df, market + struct, target_col)
        base_mae = models.metrics(base_fold)["mae"]
        for cand in candidates():
            if cand.name.startswith("Market"):
                continue
            usable = available_features(df, _features_for(cand, target))
            if not usable:
                rows.append({
                    "variable": cand.name, "target": target, "available": False,
                    "market_mae": base_mae, "combined_mae": np.nan, "mae_gain": np.nan,
                })
                continue
            fold = models.leave_one_season_out(df, market + struct + usable, target_col)
            mae = models.metrics(fold)["mae"]
            rows.append({
                "variable": cand.name, "target": target, "available": True,
                "market_mae": base_mae, "combined_mae": mae, "mae_gain": base_mae - mae,
            })
    return pd.DataFrame(rows).sort_values(
        ["target", "mae_gain"], ascending=[True, False], na_position="last"
    )


def permutation_importance(
    df: pd.DataFrame, features: list[str], target_col: str, *, repeats: int = 3
) -> pd.DataFrame:
    """Out-of-sample permutation importance, averaged over season folds."""
    feats = available_features(df, features)
    X, used = feature_matrix(df, feats)
    y = pd.to_numeric(df[target_col], errors="coerce").to_numpy(dtype=float)
    seasons = df["season"].to_numpy()
    valid = np.isfinite(y)
    if not used:
        return pd.DataFrame(columns=["feature", "mae_increase"])

    rng = np.random.default_rng(config.SEED)
    totals = np.zeros(len(used))
    weights = 0.0
    for season in np.unique(seasons):
        train = valid & (seasons != season)
        test = valid & (seasons == season)
        if train.sum() < 200 or test.sum() < 50:
            continue
        model = models.gbm()
        model.fit(X[train], y[train])
        base = float(np.mean(np.abs(model.predict(X[test]) - y[test])))
        Xt = X[test]
        for j in range(len(used)):
            increases = []
            for _ in range(repeats):
                shuffled = Xt.copy()
                shuffled[:, j] = rng.permutation(shuffled[:, j])
                increases.append(float(np.mean(np.abs(model.predict(shuffled) - y[test]))) - base)
            totals[j] += np.mean(increases) * test.sum()
        weights += test.sum()
    if weights == 0:
        return pd.DataFrame(columns=["feature", "mae_increase"])
    return pd.DataFrame({"feature": used, "mae_increase": totals / weights}).sort_values(
        "mae_increase", ascending=False
    )


def ridge_directions(df: pd.DataFrame, features: list[str], target_col: str) -> pd.DataFrame:
    feats = available_features(df, features)
    X, used = feature_matrix(df, feats)
    y = pd.to_numeric(df[target_col], errors="coerce").to_numpy(dtype=float)
    valid = np.isfinite(y)
    if not used:
        return pd.DataFrame(columns=["feature", "coef_std"])
    model = models.ridge()
    model.fit(X[valid], y[valid])
    coefs = model.named_steps["model"].coef_
    return pd.DataFrame({"feature": used, "coef_std": coefs}).sort_values(
        "coef_std", key=lambda s: s.abs(), ascending=False
    )


def classification_power(df: pd.DataFrame, features: list[str], target_col: str) -> dict[str, float]:
    """Out-of-sample ATS / over-under classification, LOSO."""
    feats = available_features(df, features)
    X, used = feature_matrix(df, feats)
    y = pd.to_numeric(df[target_col], errors="coerce").to_numpy(dtype=float)
    seasons = df["season"].to_numpy()
    valid = np.isfinite(y)
    empty = {"n": 0, "accuracy": float("nan"), "log_loss": float("nan"),
             "base_rate": float("nan")}
    if not used or valid.sum() < 200:
        return empty

    preds = np.full(len(df), np.nan)
    for season in np.unique(seasons):
        train = valid & (seasons != season)
        test = valid & (seasons == season)
        if train.sum() < 200 or test.sum() == 0:
            continue
        clf = Pipeline([
            ("scale", StandardScaler()),
            ("model", LogisticRegression(max_iter=2000, C=1.0)),
        ])
        clf.fit(X[train], y[train])
        preds[test] = clf.predict_proba(X[test])[:, 1]

    keep = valid & np.isfinite(preds)
    if keep.sum() == 0:
        return empty
    p = np.clip(preds[keep], 1e-6, 1 - 1e-6)
    truth = y[keep]
    return {
        "n": int(keep.sum()),
        "accuracy": float(((p > 0.5).astype(float) == truth).mean()),
        "log_loss": float(-np.mean(truth * np.log(p) + (1 - truth) * np.log(1 - p))),
        "base_rate": float(truth.mean()),
    }


def rank_variables(df: pd.DataFrame) -> pd.DataFrame:
    """The mission's ranked list: one row per candidate variable per target."""
    standalone = standalone_power(df).rename(
        columns={"mae": "standalone_mae", "mae_gain": "standalone_gain"}
    )
    marginal = marginal_over_market(df).rename(
        columns={"mae_gain": "gain_over_market", "combined_mae": "market_plus_mae"}
    )
    merged = standalone.merge(
        marginal[["variable", "target", "gain_over_market", "market_plus_mae"]],
        on=["variable", "target"],
        how="left",
    )
    merged["rank_standalone"] = merged.groupby("target")["standalone_gain"].rank(
        ascending=False, method="min"
    )
    merged["rank_over_market"] = merged.groupby("target")["gain_over_market"].rank(
        ascending=False, method="min"
    )
    return merged.sort_values(
        ["target", "standalone_gain"], ascending=[True, False], na_position="last"
    ).reset_index(drop=True)
