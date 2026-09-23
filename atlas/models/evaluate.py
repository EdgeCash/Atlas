"""Score a set of forecasts on a test frame, the same way every time.

The benchmark report and every candidate model call this, so a difference
between two reports is a difference between models and never a difference
in how they were scored. One row per (game, model), every score per game,
so callers can slice by season, week or spread before averaging.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from atlas.models import scoring
from atlas.models.lattice import Lattice
from atlas.models.reference import ORDER, Forecast

WEEK_BUCKETS = [(1, 2), (3, 4), (5, 8), (9, 12), (13, 99)]
SPREAD_BUCKETS = [(0, 3), (3, 7), (7, 14), (14, 21), (21, 99)]
SCORES = ["crps", "brier", "log_margin", "mae", "ece"]


def score(test: pd.DataFrame, forecasts: dict[str, Forecast], grid: Lattice,
          season: int | None = None) -> pd.DataFrame:
    y = test["actual_margin"].to_numpy(dtype=int)
    rows = []
    for name, fc in forecasts.items():
        pmf = grid.pmf(fc.mean, fc.sigma)
        rows.append(pd.DataFrame({
            "season": season if season is not None else test["season"].to_numpy(),
            "week": test["week"].to_numpy(),
            "season_type": test["season_type"].to_numpy() if "season_type" in test else "regular",
            "abs_spread": test["closing_spread"].abs().to_numpy() if "closing_spread" in test else np.nan,
            "model": name,
            "mean": fc.mean,
            "sigma": fc.sigma,
            "coefficient": fc.coefficient,
            "hfa": fc.hfa,
            "p_home": scoring.home_win_probability(pmf, grid.support),
            "won": (y > 0).astype(float) + 0.5 * (y == 0),
            "crps": scoring.crps(pmf, grid.support, y),
            "brier": scoring.brier(pmf, grid.support, y),
            "log_margin": scoring.log_score(pmf, grid.support, y),
            "mae": scoring.mae(fc.mean, y),
        }))
    return pd.concat(rows, ignore_index=True)


def summarise(scored: pd.DataFrame, by: list[str] | None = None,
              order: tuple[str, ...] = ORDER) -> pd.DataFrame:
    keys = ["model", *(by or [])]
    out = scored.groupby(keys, observed=True).agg(
        games=("crps", "size"), crps=("crps", "mean"), brier=("brier", "mean"),
        log_margin=("log_margin", "mean"), mae=("mae", "mean"),
    ).reset_index()
    ece = scored.groupby(keys, observed=True).apply(
        lambda d: scoring.expected_calibration_error(d["p_home"], d["won"]), include_groups=False
    ).rename("ece").reset_index()
    out = out.merge(ece, on=keys)
    seen = [m for m in order if m in set(out["model"])]
    extra = sorted(set(out["model"]) - set(seen))
    out["model"] = pd.Categorical(out["model"], categories=[*seen, *extra], ordered=True)
    return out.sort_values(keys).reset_index(drop=True)


def bucket(values: pd.Series, buckets: list[tuple[int, int]], label: str) -> pd.Series:
    edges = [b[0] for b in buckets] + [buckets[-1][1]]
    labels = [f"{label} {lo}-{hi}" if hi < 99 else f"{label} {lo}+" for lo, hi in buckets]
    return pd.cut(values, bins=edges, labels=labels, right=False, include_lowest=True)


def formatted(df: pd.DataFrame, cols: list[str] = SCORES) -> pd.DataFrame:
    out = df.copy()
    for c in cols:
        if c in out:
            digits = 2 if c == "mae" else 3
            out[c] = [("" if pd.isna(v) else f"{v:.{digits}f}") for v in out[c]]
    return out


def markdown(df: pd.DataFrame) -> str:
    """A GitHub-flavoured table from a frame whose cells are already formatted."""
    cols = list(df.columns)
    lines = ["| " + " | ".join(str(c) for c in cols) + " |", "|" + "|".join(["---"] * len(cols)) + "|"]
    # ``iterrows`` upcasts a row to one dtype, which turns an int season into
    # 2021.000 next to a float; object rows keep each cell's own type.
    for _, row in df.astype(object).iterrows():
        cells = []
        for c in cols:
            v = row[c]
            if isinstance(v, (int, np.integer)):
                cells.append(str(int(v)))
            elif isinstance(v, (float, np.floating)):
                cells.append("" if pd.isna(v) else f"{v:.3f}")
            else:
                cells.append(str(v))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)
