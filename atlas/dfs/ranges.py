"""Each projection's range: its 10th and 90th percentiles.

Step 4 of `docs/MODEL_PLAN_DFS.md`. DraftKings points are lopsided - a
floor near zero and a long tail of touchdown weeks - so a range drawn as a
normal curve around the projection puts too little room below and too much
above. Instead each end of the range is fitted directly: per position, a
linear quantile regression of the model's miss (actual minus projection) on
the projection itself, at the 10th and 90th percentiles. A higher
projection earns a wider range, and the two ends move independently.

The misses are the model's own out-of-sample ones: each season's ranges
are fitted on the seasons before it, each of which the model predicted
from the seasons before that. The gate (plan §7, step 4): the 80% ranges
cover 76-84% of outcomes.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import minimize

LOW, HIGH = 0.10, 0.90
GATE = (0.76, 0.84)


def quantile_line(x: np.ndarray, y: np.ndarray, q: float) -> tuple[float, float]:
    """The line a + b x minimising the pinball loss at quantile ``q``.

    Two parameters and a convex loss: a simplex search over every row is
    exact enough and far quicker than the full linear program."""
    def loss(p: np.ndarray) -> float:
        r = y - p[0] - p[1] * x
        return float(np.mean(np.maximum(q * r, (q - 1) * r)))

    start = np.array([float(np.quantile(y, q)), 0.0])
    res = minimize(loss, start, method="Nelder-Mead", options={"xatol": 1e-5, "fatol": 1e-9, "maxiter": 4000})
    return float(res.x[0]), float(res.x[1])


def fit(oos: pd.DataFrame) -> dict[tuple[str, float], tuple[float, float]]:
    """Per position and quantile: (a, b) with the quantile of the miss = a + b x projection."""
    out = {}
    for position, g in oos.dropna(subset=["model", "target"]).groupby("position"):
        if len(g) < 100:
            continue
        x = g["model"].to_numpy(dtype=float)
        miss = (g["target"] - g["model"]).to_numpy(dtype=float)
        for q in (LOW, HIGH):
            out[(position, q)] = quantile_line(x, miss, q)
    return out


def apply(rows: pd.DataFrame, lines: dict) -> pd.DataFrame:
    """``model_lo`` and ``model_hi`` for ``rows``, from :func:`fit`'s lines."""
    out = pd.DataFrame(index=rows.index)
    x = rows["model"].to_numpy(dtype=float)
    for q, col in ((LOW, "model_lo"), (HIGH, "model_hi")):
        a = rows["position"].map(lambda p, q=q: lines.get((p, q), (np.nan, np.nan))[0]).to_numpy(dtype=float)
        b = rows["position"].map(lambda p, q=q: lines.get((p, q), (np.nan, np.nan))[1]).to_numpy(dtype=float)
        out[col] = x + a + b * x
    out["model_hi"] = np.maximum(out["model_hi"], out["model_lo"])
    return out


def walk_forward(oos: pd.DataFrame, *, first: int) -> pd.DataFrame:
    """Ranges for every season from ``first``, each fitted on the seasons before it."""
    parts = []
    for season in sorted(int(s) for s in oos["season"].unique()):
        if season < first:
            continue
        lines = fit(oos[oos["season"] < season])
        test = oos[oos["season"] == season]
        parts.append(pd.concat([test[["season", "week", "player_id"]], apply(test, lines)], axis=1))
    return pd.concat(parts, ignore_index=True)


def coverage(scored: pd.DataFrame, by: list[str] | None = None) -> pd.DataFrame:
    """Share of outcomes inside the range, below it and above it, and its width."""
    s = scored.dropna(subset=["model_lo", "model_hi", "target"])
    s = s.assign(inside=(s["target"] >= s["model_lo"]) & (s["target"] <= s["model_hi"]),
                 below=s["target"] < s["model_lo"], above=s["target"] > s["model_hi"],
                 width=s["model_hi"] - s["model_lo"])
    groups = s.groupby(by) if by else [((), s)]
    rows = []
    for key, g in groups:
        key = key if isinstance(key, tuple) else (key,)
        rows.append({**dict(zip(by or [], key, strict=True)), "player-weeks": len(g),
                     "coverage": g["inside"].mean(), "below": g["below"].mean(), "above": g["above"].mean(),
                     "width": g["width"].mean()})
    return pd.DataFrame(rows)
