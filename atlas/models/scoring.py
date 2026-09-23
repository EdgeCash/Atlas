"""Proper scoring rules for a discrete distribution over integer margins.

Every function takes the same shape: ``pmf`` is an ``(n, K)`` array of
probabilities over the integer ``support`` (length K), one row per game, and
``y`` is the ``(n,)`` vector of realised integer margins. Each returns a
per-game score so callers can slice by season, week or spread before
averaging; ``lower is better`` for all of them.

Why these four and not accuracy:

* **CRPS** integrates squared distance between the forecast CDF and the
  realised step function. It rewards putting mass *near* the outcome, so it
  is the right whole-distribution score for a margin. A point forecast's CRPS
  is its absolute error, which makes CRPS directly comparable to MAE.
* **Brier** on the home-win probability is calibration plus discrimination in
  one number; 0.25 is a coin flip.
* **Log score** on the exact margin is local - it only looks at the
  probability placed on what happened - which is exactly what an exact-score
  claim is graded on, and it is the score that punishes ignoring the lattice.
* **Expected calibration error** is the reliability diagram reduced to one
  number: how far "60%" is from happening 60% of the time.

Gneiting & Raftery (2007) is the reference for all of them being proper.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _check(pmf: np.ndarray, support: np.ndarray, y: np.ndarray) -> None:
    pmf = np.asarray(pmf)
    if pmf.ndim != 2 or pmf.shape[1] != len(support):
        raise ValueError(f"pmf must be (n, {len(support)}); got {pmf.shape}")
    if len(y) != pmf.shape[0]:
        raise ValueError("one realised outcome per pmf row")
    rowsum = pmf.sum(axis=1)
    if not np.allclose(rowsum, 1.0, atol=1e-6):
        raise ValueError("each pmf row must sum to one")


def crps(pmf: np.ndarray, support: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Continuous ranked probability score, per game, on the integer lattice.

    ``sum_k (F(k) - 1[y <= k])^2`` over the support. For a point mass at ``x``
    this is ``|y - x|``, so a CRPS of 7.1 reads as "about as good as a point
    forecast that misses by 7.1".
    """
    _check(pmf, support, y)
    cdf = np.cumsum(pmf, axis=1)
    step = (support[None, :] >= np.asarray(y)[:, None]).astype(float)
    return ((cdf - step) ** 2).sum(axis=1)


def home_win_probability(pmf: np.ndarray, support: np.ndarray) -> np.ndarray:
    """Mass above zero plus half the mass on zero (a tie counts half)."""
    pos = pmf[:, support > 0].sum(axis=1)
    tie = pmf[:, support == 0].sum(axis=1)
    return pos + 0.5 * tie


def brier(pmf: np.ndarray, support: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Squared error of the home-win probability against the outcome."""
    _check(pmf, support, y)
    p = home_win_probability(pmf, support)
    won = (np.asarray(y) > 0).astype(float) + 0.5 * (np.asarray(y) == 0)
    return (p - won) ** 2


def log_score(pmf: np.ndarray, support: np.ndarray, y: np.ndarray,
              floor: float = 1e-6) -> np.ndarray:
    """Negative log probability of the exact realised margin, in nats.

    ``floor`` keeps a model that put zero mass on the outcome from scoring
    infinity; it is a penalty, not a kindness, at -log(1e-6) = 13.8 nats.
    """
    _check(pmf, support, y)
    idx = np.searchsorted(support, np.asarray(y))
    inside = (idx < len(support)) & (support[np.minimum(idx, len(support) - 1)] == np.asarray(y))
    p = np.where(inside, pmf[np.arange(len(y)), np.minimum(idx, len(support) - 1)], 0.0)
    return -np.log(np.maximum(p, floor))


def mae(mean: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Absolute error of the point forecast. Reported beside CRPS as a courtesy."""
    return np.abs(np.asarray(mean, dtype=float) - np.asarray(y, dtype=float))


def reliability(p: np.ndarray, won: np.ndarray, bins: int = 10) -> pd.DataFrame:
    """The reliability diagram as a table: per bin, mean forecast vs. mean outcome.

    ``won`` may be 0/1 or carry 0.5 for a tie. Empty bins are dropped rather
    than reported as zero, because an empty bin says nothing about calibration.
    """
    p = np.asarray(p, dtype=float)
    won = np.asarray(won, dtype=float)
    edges = np.linspace(0.0, 1.0, bins + 1)
    which = np.clip(np.digitize(p, edges[1:-1]), 0, bins - 1)
    rows = []
    for b in range(bins):
        m = which == b
        if not m.any():
            continue
        rows.append({
            "bin": f"{edges[b]:.1f}-{edges[b + 1]:.1f}",
            "n": int(m.sum()),
            "forecast": float(p[m].mean()),
            "observed": float(won[m].mean()),
        })
    out = pd.DataFrame(rows)
    out["gap"] = out["observed"] - out["forecast"]
    return out


def expected_calibration_error(p: np.ndarray, won: np.ndarray, bins: int = 10) -> float:
    """Count-weighted mean absolute gap between forecast and observed frequency."""
    table = reliability(p, won, bins)
    if table.empty:
        return float("nan")
    return float((table["gap"].abs() * table["n"]).sum() / table["n"].sum())
