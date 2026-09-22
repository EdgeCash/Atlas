"""Research Task 1: benchmark the established predictors.

Four required benchmarks - Market, SP+, FPI, SP+ & FPI - plus the extra
reference points Atlas can build from its own warehouse. Every fitted
benchmark gets the same treatment: leave-one-season-out, MAE and RMSE, for
both margin and total.

Two notes on fairness:

* The market's closing spread is already a margin forecast, so it is reported
  twice - once used raw (``-closing_spread``), once refitted like the others.
  If the refit beats the raw line by more than noise, the market line is
  biased, which is itself a finding.
* Ratings such as SP+ and FPI are neutral-field point differentials. Turning
  one into a prediction for a real game needs home-field advantage, so every
  fitted margin benchmark also gets ``neutral_site_flag`` and fits its own
  intercept. Without that the ratings would be handicapped for a reason that
  has nothing to do with their information content.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from atlas.research import models
from atlas.research.dataset import available_features
from atlas.util import get_logger

LOG = get_logger(__name__)

STRUCTURAL = ["neutral_site_flag"]

EFFICIENCY_MARGIN = [
    "off_epa_diff",
    "def_epa_diff",
    "success_rate_diff",
    "def_success_rate_diff",
    "explosiveness_diff",
    "def_explosiveness_diff",
    "havoc_diff",
    "finishing_drives_diff",
    "pace_diff",
    "plays_per_game_diff",
]
EFFICIENCY_TOTAL = [
    "off_epa_sum",
    "def_epa_sum",
    "success_rate_sum",
    "def_success_rate_sum",
    "explosiveness_sum",
    "def_explosiveness_sum",
    "havoc_sum",
    "finishing_drives_sum",
    "pace_sum",
    "plays_per_game_sum",
]

BENCHMARKS: dict[str, dict[str, list[str]]] = {
    "Market Only": {
        "margin": ["closing_spread"],
        "total": ["closing_total"],
    },
    "SP+ Only": {
        "margin": ["sp_plus_diff"],
        "total": ["sp_plus_sum"],
    },
    "FPI Only": {
        "margin": ["fpi_diff"],
        "total": ["fpi_sum"],
    },
    "SP+ + FPI": {
        "margin": ["sp_plus_diff", "fpi_diff"],
        "total": ["sp_plus_sum", "fpi_sum"],
    },
    # --- Atlas extensions beyond the four required benchmarks ---------------
    "Elo Only": {
        "margin": ["elo_diff"],
        "total": ["elo_sum"],
    },
    "FPI Game Projection": {
        "margin": ["fpi_home_win_prob"],
        "total": [],
    },
    "Efficiency Only": {
        "margin": EFFICIENCY_MARGIN,
        "total": EFFICIENCY_TOTAL,
    },
    "Ratings + Efficiency (no market)": {
        "margin": ["sp_plus_diff", "fpi_diff", "elo_diff", *EFFICIENCY_MARGIN],
        "total": ["sp_plus_sum", "fpi_sum", "elo_sum", *EFFICIENCY_TOTAL],
    },
    "Market + Efficiency": {
        "margin": ["closing_spread", *EFFICIENCY_MARGIN],
        "total": ["closing_total", *EFFICIENCY_TOTAL],
    },
    "Market + Everything": {
        "margin": [
            "closing_spread",
            "spread_movement",
            "sp_plus_diff",
            "fpi_diff",
            "fpi_home_win_prob",
            "elo_diff",
            *EFFICIENCY_MARGIN,
            "recruiting_rank_diff",
            "talent_diff",
            "returning_production_diff",
            "rest_diff",
            "travel_distance",
            "weather_temp",
            "weather_wind",
            "weather_precip",
        ],
        "total": [
            "closing_total",
            "total_movement",
            "sp_plus_sum",
            "fpi_sum",
            "elo_sum",
            *EFFICIENCY_TOTAL,
            "talent_sum",
            "returning_production_sum",
            "rest_abs",
            "travel_distance",
            "weather_temp",
            "weather_wind",
            "weather_precip",
        ],
    },
}

TARGETS = {"margin": "actual_margin", "total": "actual_total"}


def raw_market_baseline(df: pd.DataFrame) -> pd.DataFrame:
    """The closing line used as-is, with no fitting at all."""
    rows = []
    for target, pred_col, truth in (
        ("margin", "market_margin", "actual_margin"),
        ("total", "closing_total", "actual_total"),
    ):
        mask = df[pred_col].notna() & df[truth].notna()
        fold = models.FoldPredictions(
            df.loc[mask, truth].to_numpy(dtype=float),
            df.loc[mask, pred_col].to_numpy(dtype=float),
            df.loc[mask, "season"].to_numpy(),
            [pred_col],
        )
        rows.append(
            {
                "benchmark": "Market Closing Line (raw, unfitted)",
                "target": target,
                "available": True,
                "features_used": pred_col,
                "missing_features": "",
                **models.metrics(fold),
            }
        )
    return pd.DataFrame(rows)


def run_benchmarks(df: pd.DataFrame, *, model_factory=models.ridge) -> pd.DataFrame:
    rows = [*raw_market_baseline(df).to_dict("records")]
    for name, spec in BENCHMARKS.items():
        for target, target_col in TARGETS.items():
            wanted = spec.get(target, [])
            if not wanted:
                continue
            feats = available_features(df, [*wanted, *STRUCTURAL] if target == "margin" else wanted)
            declared = available_features(df, wanted)
            missing = [f for f in wanted if f not in declared]
            if not declared:
                rows.append(
                    {
                        "benchmark": name,
                        "target": target,
                        "available": False,
                        "features_used": "",
                        "missing_features": ", ".join(missing),
                        "n": 0,
                        "mae": np.nan,
                        "rmse": np.nan,
                        "r2": np.nan,
                        "bias": np.nan,
                    }
                )
                continue
            fold = models.leave_one_season_out(df, feats, target_col, model_factory=model_factory)
            rows.append(
                {
                    "benchmark": name,
                    "target": target,
                    "available": True,
                    "features_used": ", ".join(fold.features),
                    "missing_features": ", ".join(missing),
                    **models.metrics(fold),
                }
            )
    out = pd.DataFrame(rows)
    return out.sort_values(["target", "mae"], na_position="last").reset_index(drop=True)


def benchmark_by_season(df: pd.DataFrame, name: str, target: str) -> pd.DataFrame:
    spec = BENCHMARKS[name]
    feats = available_features(
        df, [*spec[target], *STRUCTURAL] if target == "margin" else spec[target]
    )
    fold = models.leave_one_season_out(df, feats, TARGETS[target])
    return models.season_metrics(fold)


def market_edge_report(df: pd.DataFrame) -> pd.DataFrame:
    """Can any benchmark beat the closing line on its own terms?

    For each benchmark this reports the out-of-sample hit rate of siding with
    the model against the market line. 52.4% is the break-even rate at -110.
    """
    rows = []
    for name, spec in BENCHMARKS.items():
        for target, target_col in TARGETS.items():
            wanted = spec.get(target, [])
            if not wanted or not available_features(df, wanted):
                continue
            feats = available_features(
                df, [*wanted, *STRUCTURAL] if target == "margin" else wanted
            )
            fold = models.leave_one_season_out(df, feats, target_col)
            if len(fold.y_true) == 0:
                continue
            line_col = "market_margin" if target == "margin" else "closing_total"
            mask = df[target_col].notna() & df[line_col].notna()
            line = df.loc[mask, line_col].to_numpy(dtype=float)
            if len(line) != len(fold.y_true):
                continue
            rows.append(
                {
                    "benchmark": name,
                    "target": target,
                    **models.directional_accuracy(fold, line),
                }
            )
    return pd.DataFrame(rows)
