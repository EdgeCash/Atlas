"""Measuring effects on the market residual.

Phase 1C stops asking "does this predict football?" and asks only "does this
move `actual - closing`?". Every track reduces to the same few measurements,
so they live here once.

Two things this module insists on, because Phase 1C is a hypothesis hunt and
hypothesis hunts generate false positives:

* **Every effect carries a standard error and a t-statistic.** A 2-point mean
  on 90 games is not a finding.
* **Every p-value goes into a single pool for Benjamini-Hochberg correction.**
  Run sixty tests at p < 0.05 and three will look significant by construction.
  The synthesis report corrects across all of them at once, so a track cannot
  launder a marginal result by being one of many.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

#: Break-even win rate at -110.
BREAK_EVEN = 0.5238

RESIDUAL_MARGIN = "market_residual_margin"
RESIDUAL_TOTAL = "market_residual_total"


def _summarise(values: pd.Series) -> dict[str, float]:
    clean = pd.to_numeric(values, errors="coerce").dropna()
    n = len(clean)
    if n < 2:
        return {"n": n, "mean": np.nan, "sd": np.nan, "se": np.nan, "t": np.nan,
                "p": np.nan, "median": np.nan}
    mean = float(clean.mean())
    sd = float(clean.std(ddof=1))
    se = sd / np.sqrt(n)
    t = mean / se if se > 0 else np.nan
    p = float(2 * stats.t.sf(abs(t), df=n - 1)) if np.isfinite(t) else np.nan
    return {"n": n, "mean": mean, "sd": sd, "se": se, "t": t, "p": p,
            "median": float(clean.median())}


def _rate(values: pd.Series) -> dict[str, float]:
    clean = pd.to_numeric(values, errors="coerce").dropna()
    n = len(clean)
    if n == 0:
        return {"settled": 0, "rate": np.nan, "rate_z": np.nan, "beats_vig": False}
    rate = float(clean.mean())
    z = (rate - 0.5) / np.sqrt(0.25 / n)
    return {
        "settled": n,
        "rate": rate,
        "rate_z": float(z),
        "beats_vig": bool(rate > BREAK_EVEN and abs(z) > 2),
    }


def effect_by_group(
    df: pd.DataFrame,
    group: str,
    *,
    target: str = RESIDUAL_MARGIN,
    outcome: str | None = "home_cover",
    min_games: int = 30,
) -> pd.DataFrame:
    """Mean residual per group, with error bars and the matching hit rate."""
    rows = []
    for name, block in df.groupby(group, observed=True, dropna=False):
        summary = _summarise(block[target])
        if summary["n"] < min_games:
            continue
        row = {"group": name, **summary}
        if outcome and outcome in block:
            row.update(_rate(block[outcome]))
        rows.append(row)
    out = pd.DataFrame(rows)
    return out.sort_values("t", key=lambda s: s.abs(), ascending=False) if not out.empty else out


def binary_effect(
    df: pd.DataFrame,
    flag: str,
    *,
    target: str = RESIDUAL_MARGIN,
    outcome: str | None = "home_cover",
    label: str | None = None,
) -> dict:
    """Residual when a flag is on versus off, plus the difference between them."""
    mask = df[flag].fillna(False).astype(bool)
    on = _summarise(df.loc[mask, target])
    off = _summarise(df.loc[~mask, target])
    diff = on["mean"] - off["mean"] if np.isfinite(on["mean"]) and np.isfinite(off["mean"]) else np.nan
    se = (
        np.sqrt(on["se"] ** 2 + off["se"] ** 2)
        if np.isfinite(on["se"]) and np.isfinite(off["se"])
        else np.nan
    )
    t = diff / se if np.isfinite(se) and se > 0 else np.nan
    p = float(2 * stats.norm.sf(abs(t))) if np.isfinite(t) else np.nan
    row = {
        "effect": label or flag,
        "n_on": on["n"],
        "n_off": off["n"],
        "mean_on": on["mean"],
        "mean_off": off["mean"],
        "difference": diff,
        "se": se,
        "t": t,
        "p": p,
    }
    if outcome and outcome in df:
        row.update({f"on_{k}": v for k, v in _rate(df.loc[mask, outcome]).items()})
    return row


def signed_effect(
    df: pd.DataFrame,
    signed: str,
    *,
    target: str = RESIDUAL_MARGIN,
    label: str | None = None,
) -> dict:
    """Effect of a -1/0/+1 event, folded onto one side.

    A home-team event and an away-team event are the same phenomenon with
    opposite sign, so folding them doubles the sample and halves the noise.
    ``signed`` is +1 when the event favours the home side in residual terms.
    """
    sub = df[df[signed].fillna(0) != 0]
    folded = pd.to_numeric(sub[target], errors="coerce") * np.sign(sub[signed])
    summary = _summarise(folded)
    return {"effect": label or signed, **summary}


def disagreement_curve(
    df: pd.DataFrame,
    prediction: str,
    line: str,
    outcome: str,
    *,
    thresholds: tuple[float, ...] = (0, 1, 2, 3, 4, 6, 8, 10),
) -> pd.DataFrame:
    """Hit rate as a function of how far a model sits from the market.

    This is the test a marginal-MAE study cannot do. A model can be worse than
    the market on average and still be right about the games it disagrees on
    most, which is exactly the shape a real edge takes. The rate has to *rise*
    with the threshold; a flat curve at 50% is noise however pretty one cut
    looks.
    """
    sub = df.dropna(subset=[prediction, line, outcome]).copy()
    if sub.empty:
        return pd.DataFrame()
    sub["edge"] = sub[prediction] - sub[line]
    sub["model_over"] = sub["edge"] > 0
    truth = pd.to_numeric(sub[outcome], errors="coerce")

    rows = []
    for threshold in thresholds:
        live = sub[sub["edge"].abs() >= threshold]
        if live.empty:
            continue
        picked_over = live["edge"] > 0
        hit = np.where(picked_over, truth.loc[live.index], 1 - truth.loc[live.index])
        stats_ = _rate(pd.Series(hit))
        rows.append({"threshold": threshold, "bets": len(live), **stats_})
    return pd.DataFrame(rows)


def fdr_adjust(p_values: pd.Series, alpha: float = 0.05) -> pd.DataFrame:
    """Benjamini-Hochberg across a pool of tests.

    Returns the adjusted (q) values and whether each survives at ``alpha``.
    Phase 1C runs enough tests that the uncorrected p-values are decorative.
    """
    p = pd.to_numeric(p_values, errors="coerce")
    valid = p.notna()
    out = pd.DataFrame({"p": p, "q": np.nan, "survives_fdr": False})
    if not valid.any():
        return out
    ordered = p[valid].sort_values()
    m = len(ordered)
    ranks = np.arange(1, m + 1)
    q_raw = ordered.to_numpy() * m / ranks
    q = np.minimum.accumulate(q_raw[::-1])[::-1]
    out.loc[ordered.index, "q"] = q
    out.loc[ordered.index, "survives_fdr"] = q <= alpha
    return out


def bootstrap_ci(
    values: pd.Series, *, statistic=np.mean, n_boot: int = 2000, seed: int = 20180101
) -> tuple[float, float]:
    """Percentile bootstrap interval, for effects whose distribution is skewed."""
    clean = pd.to_numeric(values, errors="coerce").dropna().to_numpy()
    if len(clean) < 30:
        return (np.nan, np.nan)
    rng = np.random.default_rng(seed)
    draws = rng.choice(clean, size=(n_boot, len(clean)), replace=True)
    estimates = statistic(draws, axis=1)
    return (float(np.percentile(estimates, 2.5)), float(np.percentile(estimates, 97.5)))
