"""Phase 1B: does opponent adjustment buy anything?

Three questions, in ascending order of how much they matter:

1. Do adjusted metrics predict **margin** and **total** better than raw ones?
   Interesting, but a model that predicts margin well has mostly rediscovered
   the closing line.
2. Do they beat the published adjusted ratings (SP+, FPI) that already do this?
3. Do they explain the **market residual** - what the closing line got wrong?
   This is the only one that could justify Atlas Alpha, and it is the one
   Phase 1A found nothing for.

Every comparison is leave-one-season-out, and every claimed gain is paired
game-by-game against its baseline so it carries a standard error. Phase 1A
learned that lesson the hard way: over ~5,700 games a 0.01 MAE improvement is
indistinguishable from zero.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from atlas.research import models
from atlas.research.benchmarks import STRUCTURAL
from atlas.research.dataset import available_features
from atlas.util import get_logger

LOG = get_logger(__name__)

TARGETS = {
    "margin": "actual_margin",
    "total": "actual_total",
    "residual_margin": "market_residual_margin",
    "residual_total": "market_residual_total",
}

#: Targets whose do-nothing baseline is "the market is right", not "the mean".
RESIDUAL_TARGETS = ("residual_margin", "residual_total")

MATERIAL_T = 2.0


# ---------------------------------------------------------------------------
# Feature sets
# ---------------------------------------------------------------------------

def _diffs(metrics: list[str]) -> list[str]:
    return [f"{m}_diff" for m in metrics]


def _sums(metrics: list[str]) -> list[str]:
    return [f"{m}_sum" for m in metrics]


#: The nine concepts that exist in both raw and adjusted form, so the headline
#: comparison is like-for-like rather than a bigger feature set beating a
#: smaller one.
MATCHED_RAW = [
    "off_epa", "def_epa", "success_rate", "def_success_rate",
    "explosiveness", "def_explosiveness", "havoc", "finishing_drives", "pace",
]
MATCHED_ADJ = [
    "adj_off_epa", "adj_def_epa", "adj_success_rate", "adj_def_success_rate",
    "adj_explosiveness", "adj_def_explosiveness", "adj_havoc",
    "adj_finishing_drives", "adj_pace",
]
#: Everything the adjustment solve produces, including the sides raw
#: efficiency never had (havoc allowed, defensive finishing, defensive pace).
FULL_ADJ = MATCHED_ADJ + ["adj_havoc_allowed", "adj_def_finishing_drives", "adj_def_pace"]

#: The per-metric head-to-heads the brief asks for by name.
METRIC_PAIRS: dict[str, tuple[list[str], list[str]]] = {
    "EPA": (["off_epa", "def_epa"], ["adj_off_epa", "adj_def_epa"]),
    "Success Rate": (["success_rate", "def_success_rate"],
                     ["adj_success_rate", "adj_def_success_rate"]),
    "Explosiveness": (["explosiveness", "def_explosiveness"],
                      ["adj_explosiveness", "adj_def_explosiveness"]),
    "Havoc": (["havoc"], ["adj_havoc", "adj_havoc_allowed"]),
    "Finishing Drives": (["finishing_drives"],
                         ["adj_finishing_drives", "adj_def_finishing_drives"]),
    "Pace": (["pace"], ["adj_pace", "adj_def_pace"]),
    "Full efficiency model": (MATCHED_RAW, MATCHED_ADJ),
}


def feature_set(metrics: list[str], target: str) -> list[str]:
    """Difference form for margin-like targets, sum form for total-like ones."""
    if target in ("total", "residual_total"):
        return _sums(metrics)
    return _diffs(metrics)


def structural_for(target: str) -> list[str]:
    # Home advantage is already priced into the closing line, so a residual
    # model must not refit it; a from-scratch margin model must.
    return STRUCTURAL if target == "margin" else []


# ---------------------------------------------------------------------------
# Core evaluation
# ---------------------------------------------------------------------------


def evaluate(df: pd.DataFrame, features: list[str], target: str) -> dict:
    """Leave-one-season-out fit plus its paired gain over the right baseline."""
    target_col = TARGETS[target]
    feats = available_features(df, [*features, *structural_for(target)])
    declared = available_features(df, features)
    if not declared:
        return {"available": False, "n": 0, "mae": np.nan, "rmse": np.nan, "r2": np.nan,
                "gain": np.nan, "gain_t": np.nan, "material": False, "n_features": 0}

    fold = models.leave_one_season_out(df, feats, target_col)
    metrics = models.metrics(fold)
    baseline = baseline_fold(df, target)
    paired = models.paired_mae_gain(baseline, fold)
    return {
        "available": True,
        "n_features": len(declared),
        **metrics,
        "gain": paired["mae_gain"],
        "gain_se": paired["gain_se"],
        "gain_t": paired["gain_t"],
        "material": bool(np.isfinite(paired["gain_t"]) and paired["gain_t"] > MATERIAL_T),
    }


def baseline_fold(df: pd.DataFrame, target: str) -> models.FoldPredictions:
    constant = 0.0 if target in RESIDUAL_TARGETS else None
    return models.null_fold(df, TARGETS[target], constant=constant)


def baseline_metrics(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for target in TARGETS:
        fold = baseline_fold(df, target)
        label = "market is exactly right" if target in RESIDUAL_TARGETS else "season mean"
        rows.append({"target": target, "baseline": label, **models.metrics(fold)})
    return pd.DataFrame(rows)


def raw_vs_adjusted(df: pd.DataFrame) -> pd.DataFrame:
    """Head-to-head for every metric family the brief names, on every target."""
    rows = []
    for name, (raw_metrics, adj_metrics) in METRIC_PAIRS.items():
        for target in TARGETS:
            raw = evaluate(df, feature_set(raw_metrics, target), target)
            adj = evaluate(df, feature_set(adj_metrics, target), target)
            improvement = (
                raw["mae"] - adj["mae"]
                if np.isfinite(raw["mae"]) and np.isfinite(adj["mae"])
                else np.nan
            )
            rows.append(
                {
                    "metric": name,
                    "target": target,
                    "raw_mae": raw["mae"],
                    "adj_mae": adj["mae"],
                    "mae_improvement": improvement,
                    "raw_rmse": raw["rmse"],
                    "adj_rmse": adj["rmse"],
                    "raw_r2": raw["r2"],
                    "adj_r2": adj["r2"],
                    "adjustment_helps": bool(np.isfinite(improvement) and improvement > 0),
                }
            )
    return pd.DataFrame(rows)


def paired_raw_vs_adjusted(df: pd.DataFrame) -> pd.DataFrame:
    """Is the raw-to-adjusted improvement bigger than its own noise?"""
    rows = []
    for name, (raw_metrics, adj_metrics) in METRIC_PAIRS.items():
        for target in TARGETS:
            raw_feats = available_features(
                df, [*feature_set(raw_metrics, target), *structural_for(target)]
            )
            adj_feats = available_features(
                df, [*feature_set(adj_metrics, target), *structural_for(target)]
            )
            if not raw_feats or not adj_feats:
                continue
            raw_fold = models.leave_one_season_out(df, raw_feats, TARGETS[target])
            adj_fold = models.leave_one_season_out(df, adj_feats, TARGETS[target])
            paired = models.paired_mae_gain(raw_fold, adj_fold)
            rows.append(
                {
                    "metric": name,
                    "target": target,
                    "mae_gain": paired["mae_gain"],
                    "gain_se": paired["gain_se"],
                    "gain_t": paired["gain_t"],
                    "material": bool(
                        np.isfinite(paired["gain_t"]) and paired["gain_t"] > MATERIAL_T
                    ),
                    "n_paired": paired["n_paired"],
                }
            )
    return pd.DataFrame(rows)


def method_comparison(df: pd.DataFrame) -> pd.DataFrame:
    """Method A vs B vs C, on the same feature concepts."""
    rows = []
    for method, suffix in (("simple (A)", "_simple"), ("iterative (B)", "_iterative"),
                           ("network (C)", "")):
        metrics = [f"{m}{suffix}" for m in MATCHED_ADJ]
        for target in TARGETS:
            result = evaluate(df, feature_set(metrics, target), target)
            rows.append({"method": method, "target": target, **result})
    return pd.DataFrame(rows)


def benchmark_ladder(df: pd.DataFrame) -> pd.DataFrame:
    """Adjusted efficiency against everything Phase 1A already measured."""
    ladder = {
        "Raw efficiency": MATCHED_RAW,
        "Adjusted efficiency (matched)": MATCHED_ADJ,
        "Adjusted efficiency (full)": FULL_ADJ,
        "SP+": ["sp_plus", "sp_plus_off", "sp_plus_def"],
        "FPI": ["fpi"],
        "Elo": ["elo"],
        "Raw + Adjusted": MATCHED_RAW + MATCHED_ADJ,
        "Adjusted + SP+ + FPI": FULL_ADJ + ["sp_plus", "sp_plus_off", "sp_plus_def", "fpi"],
    }
    rows = []
    for name, metrics in ladder.items():
        for target in TARGETS:
            features = feature_set(metrics, target)
            # SP+/FPI/Elo are ratings, not per-side metrics: they only have
            # diff and sum forms, which feature_set already produces.
            rows.append({"model": name, "target": target,
                         **evaluate(df, features, target)})
    return pd.DataFrame(rows)


def market_plus(df: pd.DataFrame) -> pd.DataFrame:
    """Does adjusted efficiency add anything on top of the closing line?"""
    market = {"margin": ["closing_spread"], "total": ["closing_total"]}
    rows = []
    for target in ("margin", "total"):
        base_feats = available_features(
            df, [*market[target], *structural_for(target)]
        )
        base_fold = models.leave_one_season_out(df, base_feats, TARGETS[target])
        for name, metrics in (
            ("market + raw efficiency", MATCHED_RAW),
            ("market + adjusted efficiency", MATCHED_ADJ),
            ("market + adjusted (full)", FULL_ADJ),
        ):
            feats = available_features(
                df, [*base_feats, *feature_set(metrics, target)]
            )
            fold = models.leave_one_season_out(df, feats, TARGETS[target])
            paired = models.paired_mae_gain(base_fold, fold)
            rows.append(
                {
                    "model": name,
                    "target": target,
                    "market_mae": models.metrics(base_fold)["mae"],
                    "combined_mae": models.metrics(fold)["mae"],
                    "mae_gain": paired["mae_gain"],
                    "gain_t": paired["gain_t"],
                    "material": bool(
                        np.isfinite(paired["gain_t"]) and paired["gain_t"] > MATERIAL_T
                    ),
                }
            )
    return pd.DataFrame(rows)


def residual_study(df: pd.DataFrame) -> pd.DataFrame:
    """The central question: what explains what the closing line got wrong?

    Everything is scored against "the market is exactly right" (predict zero),
    which is the honest null for a residual.
    """
    candidates = {
        "Raw efficiency": MATCHED_RAW,
        "Adjusted efficiency (matched)": MATCHED_ADJ,
        "Adjusted efficiency (full)": FULL_ADJ,
        "Adjusted net EPA only": ["adj_off_epa", "adj_def_epa"],
        "SP+": ["sp_plus", "sp_plus_off", "sp_plus_def"],
        "FPI": ["fpi"],
        "Elo": ["elo"],
        "Adjusted + ratings": FULL_ADJ + ["sp_plus", "sp_plus_off", "sp_plus_def", "fpi", "elo"],
    }
    rows = []
    for target in RESIDUAL_TARGETS:
        for name, metrics in candidates.items():
            rows.append({"model": name, "target": target,
                         **evaluate(df, feature_set(metrics, target), target)})
    extra = {
        "Weather (wind/temp/precip)": ["weather_wind_effective", "weather_wind_sq",
                                       "weather_temp_effective", "weather_precip_effective",
                                       "weather_humidity"],
        "Line movement": ["spread_movement", "total_movement"],
        "Rest + travel": ["rest_diff", "travel_distance"],
    }
    for target in RESIDUAL_TARGETS:
        for name, features in extra.items():
            rows.append({"model": name, "target": target, **evaluate(df, features, target)})
    return pd.DataFrame(rows)


def weather_study(df: pd.DataFrame) -> pd.DataFrame:
    """What the free weather data is actually worth, per target."""
    sets = {
        "Wind only (dome-corrected)": ["weather_wind_effective"],
        "Wind + wind squared": ["weather_wind_effective", "weather_wind_sq"],
        "Temperature only": ["weather_temp_effective"],
        "Precipitation only": ["weather_precip_effective"],
        "All weather": ["weather_wind_effective", "weather_wind_sq", "weather_temp_effective",
                        "weather_precip_effective", "weather_humidity"],
    }
    rows = []
    for name, features in sets.items():
        for target in TARGETS:
            rows.append({"features": name, "target": target,
                         **evaluate(df, features, target)})
    return pd.DataFrame(rows)


def wind_buckets(df: pd.DataFrame) -> pd.DataFrame:
    """Observed totals by wind band - the simplest possible look at the claim."""
    sub = df.dropna(subset=["weather_wind_effective", "actual_total", "closing_total"]).copy()
    if sub.empty:
        return pd.DataFrame()
    bands = [-0.1, 0.1, 5, 10, 15, 20, 100]
    labels = ["dome / calm", "0-5 mph", "5-10 mph", "10-15 mph", "15-20 mph", "20+ mph"]
    sub["band"] = pd.cut(sub["weather_wind_effective"], bins=bands, labels=labels)
    out = (
        sub.groupby("band", observed=True)
        .agg(
            games=("game_id", "size"),
            mean_total=("actual_total", "mean"),
            mean_closing_total=("closing_total", "mean"),
            mean_residual=("market_residual_total", "mean"),
            over_rate=("over_hit", "mean"),
            settled=("over_hit", "count"),
        )
        .reset_index()
    )
    # A 44.8% over rate on 245 games looks like an edge and is not one. Carry
    # the z-score so the table cannot be read without its error bar.
    out["over_rate_z"] = (out["over_rate"] - 0.5) / np.sqrt(
        0.25 / out["settled"].clip(lower=1)
    )
    out["significant"] = out["over_rate_z"].abs() > 2
    return out


def schedule_strength_impact(strength: pd.DataFrame, stream: str = "epa") -> pd.DataFrame:
    """How unbalanced schedules actually are.

    If every team faced the same quality of opposition, opponent adjustment
    could not change any ranking. This is the descriptive check that the
    premise holds - and it uses end-of-season opponent ratings, so it is a
    description of the past, never a feature.
    """
    sub = strength[strength["stream"] == stream] if "stream" in strength else strength
    if sub.empty:
        return pd.DataFrame()
    return (
        sub.groupby("season")
        .agg(
            teams=("team_id", "nunique"),
            mean_opponent=("mean_opponent_rating", "mean"),
            sd_opponent=("mean_opponent_rating", "std"),
            easiest=("mean_opponent_rating", "min"),
            hardest=("mean_opponent_rating", "max"),
        )
        .reset_index()
        .assign(spread=lambda d: d["hardest"] - d["easiest"])
    )


#: Individual metrics, raw and adjusted, for the ranking table.
SINGLE_METRICS: list[tuple[str, str]] = [
    *[(m, "raw") for m in MATCHED_RAW],
    *[(m, "adjusted") for m in FULL_ADJ],
]


def feature_rankings(df: pd.DataFrame) -> pd.DataFrame:
    """Rank every raw and adjusted metric on its own, per target.

    Standalone power, not marginal value: this says what each metric knows,
    and the ranking is what the brief asks for. Whether any of it survives the
    closing line is :func:`residual_study`'s job.
    """
    rows = []
    for metric, kind in SINGLE_METRICS:
        for target in TARGETS:
            result = evaluate(df, feature_set([metric], target), target)
            rows.append({"metric": metric, "kind": kind, "target": target, **result})
    out = pd.DataFrame(rows)
    out["rank"] = out.groupby("target")["gain"].rank(ascending=False, method="min")
    return out.sort_values(["target", "gain"], ascending=[True, False], na_position="last")
