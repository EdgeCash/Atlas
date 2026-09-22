"""Signal validation: an attempt to falsify the selective-totals candidate.

Phases 1A-1C found every public variable priced except one candidate, and that
candidate was measured in a way that flatters it: eight thresholds scanned on
the full sample, then the best one reported. This module removes that bias.

The discipline here is the product:

* the model is frozen and no feature may be added;
* the threshold is chosen inside the **training** seasons only, by a rule
  fixed in advance (`docs/SIGNAL_PREREGISTRATION.md`);
* each holdout is scored exactly **once**;
* the pass/fail criteria are constants in this file, committed before any
  holdout season was scored.

If the constants below were edited after seeing a result, the phase would be
worthless. The git history is the audit trail.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from atlas.research.dataset import available_features, feature_matrix
from atlas.util import get_logger

LOG = get_logger(__name__)

SEED = 20180101

# ---------------------------------------------------------------------------
# Frozen configuration - see docs/SIGNAL_PREREGISTRATION.md
# ---------------------------------------------------------------------------

#: The threshold grid searched inside training data only.
THRESHOLD_GRID: tuple[float, ...] = (1, 2, 3, 4, 5, 6, 7, 8)

#: Minimum training bets a threshold must produce to be selectable. Without a
#: floor the rule would drift to the sparsest, noisiest cut.
MIN_TRAINING_BETS = 500

#: American odds -> (break-even win rate, units returned by a win).
JUICE: dict[int, tuple[float, float]] = {
    -105: (105 / 205, 100 / 105),
    -110: (110 / 210, 100 / 110),
    -115: (115 / 215, 100 / 115),
    -120: (120 / 220, 100 / 120),
}
BREAK_EVEN = JUICE[-110][0]

N_BOOTSTRAP = 10_000

# --- pre-registered pass/fail criteria -------------------------------------

#: 1. Pooled holdout win rate must exceed break-even at -110.
CRITERION_WIN_RATE = BREAK_EVEN
#: 2. Lower bound of the 95% bootstrap CI must exceed a coin flip.
CRITERION_CI_LOWER = 0.50
#: 3. This many of the seven walk-forward seasons must clear break-even.
CRITERION_MIN_POSITIVE_SEASONS = 5
CRITERION_TOTAL_SEASONS = 7
#: 4. Expected units at -115 must be positive.
CRITERION_JUICE = -115

#: Deployment criteria, applied only if the four above all pass.
DEPLOY_MAX_DRAWDOWN_UNITS = 40.0
DEPLOY_MIN_PROFIT_FACTOR = 1.05
DEPLOY_MIN_PROB_ABOVE_53 = 0.50


# ---------------------------------------------------------------------------
# Experiments
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Experiment:
    name: str
    label: str
    train_seasons: tuple[int, ...]
    test_seasons: tuple[int, ...]


def experiments(seasons: tuple[int, ...] = tuple(range(2018, 2026))) -> list[Experiment]:
    return [
        Experiment("A", "train 2018-2024, test 2025", tuple(range(2018, 2025)), (2025,)),
        Experiment("B", "train 2018-2023, test 2024", tuple(range(2018, 2024)), (2024,)),
        Experiment("C", "train 2019-2025, test 2018", tuple(range(2019, 2026)), (2018,)),
    ]


def walk_forward_folds(
    seasons: tuple[int, ...] = tuple(range(2018, 2026)),
) -> list[Experiment]:
    """Fit on every prior season, predict the next. The honest ordering."""
    folds = []
    for i in range(1, len(seasons)):
        train = seasons[:i]
        test = (seasons[i],)
        folds.append(
            Experiment(
                f"WF{test[0]}",
                f"train {train[0]}-{train[-1]}, test {test[0]}",
                train,
                test,
            )
        )
    return folds


# ---------------------------------------------------------------------------
# Model - frozen
# ---------------------------------------------------------------------------


def _model() -> Pipeline:
    return Pipeline([("scale", StandardScaler()), ("model", Ridge(alpha=1.0))])


def fit_predict(
    df: pd.DataFrame,
    features: list[str],
    target: str,
    train_seasons: tuple[int, ...],
    test_seasons: tuple[int, ...],
) -> pd.DataFrame:
    """Fit on the training seasons only; predict the test seasons."""
    feats = available_features(df, features)
    X, used = feature_matrix(df, feats)
    y = pd.to_numeric(df[target], errors="coerce").to_numpy(dtype=float)
    seasons = df["season"].to_numpy()
    valid = np.isfinite(y)

    train = valid & np.isin(seasons, train_seasons)
    test = valid & np.isin(seasons, test_seasons)
    if train.sum() < 200 or test.sum() == 0 or not used:
        return pd.DataFrame()

    model = _model()
    model.fit(X[train], y[train])
    out = df.loc[test].copy()
    out["prediction"] = model.predict(X[test])
    return out


def inner_cv_predictions(
    df: pd.DataFrame, features: list[str], target: str, train_seasons: tuple[int, ...]
) -> pd.DataFrame:
    """Leave-one-season-out *inside* the training set.

    This is what the threshold is chosen on. The holdout contributes nothing.
    """
    frames = []
    for held in train_seasons:
        rest = tuple(s for s in train_seasons if s != held)
        block = fit_predict(df, features, target, rest, (held,))
        if not block.empty:
            frames.append(block)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def score_bets(
    scored: pd.DataFrame, threshold: float, *, line: str = "closing_total",
    outcome: str = "over_hit",
) -> pd.DataFrame:
    """The bets a threshold produces, with each one's win/loss.

    Pushes - where the total landed exactly on the number - carry a null
    outcome upstream and are dropped here as no action.
    """
    sub = scored.dropna(subset=["prediction", line, outcome]).copy()
    if sub.empty:
        return sub
    sub["edge"] = sub["prediction"] - sub[line]
    sub = sub[sub["edge"].abs() >= threshold]
    if sub.empty:
        return sub
    truth = pd.to_numeric(sub[outcome], errors="coerce")
    sub["pick"] = np.where(sub["edge"] > 0, "over", "under")
    sub["win"] = np.where(sub["edge"] > 0, truth, 1 - truth)
    return sub


def summarise(bets: pd.DataFrame, juice: int = -110) -> dict:
    """Win rate, units and ROI at a given price."""
    if bets.empty:
        return {"bets": 0, "wins": 0, "win_rate": np.nan, "units": np.nan,
                "roi": np.nan, "z": np.nan}
    break_even, win_return = JUICE[juice]
    wins = float(bets["win"].sum())
    n = int(len(bets))
    rate = wins / n
    units = wins * win_return - (n - wins)
    return {
        "bets": n,
        "wins": int(wins),
        "win_rate": rate,
        "units": float(units),
        "roi": float(units / n),
        "z": float((rate - 0.5) / np.sqrt(0.25 / n)),
        "break_even": break_even,
        "clears_break_even": bool(rate > break_even),
    }


def select_threshold(
    df: pd.DataFrame, features: list[str], target: str, train_seasons: tuple[int, ...]
) -> tuple[float, pd.DataFrame]:
    """Choose one threshold on training data, by the pre-registered rule.

    Maximise expected units at -110 over the grid, subject to at least
    ``MIN_TRAINING_BETS`` bets; ties break to the lower threshold.
    """
    inner = inner_cv_predictions(df, features, target, train_seasons)
    rows = []
    for threshold in THRESHOLD_GRID:
        bets = score_bets(inner, threshold)
        summary = summarise(bets)
        rows.append({"threshold": threshold, **summary})
    table = pd.DataFrame(rows)
    eligible = table[table["bets"] >= MIN_TRAINING_BETS]
    if eligible.empty:
        LOG.warning("no threshold met the %d-bet floor; falling back to the lowest",
                    MIN_TRAINING_BETS)
        eligible = table
    best = eligible.sort_values(["units", "threshold"], ascending=[False, True]).iloc[0]
    table["selected"] = table["threshold"] == best["threshold"]
    return float(best["threshold"]), table


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------


def bootstrap_win_rate(
    wins: pd.Series, *, n_boot: int = N_BOOTSTRAP, seed: int = SEED
) -> dict:
    """Resample the individual bets, not the seasons. Each bet is one trial."""
    values = pd.to_numeric(wins, errors="coerce").dropna().to_numpy(dtype=float)
    n = len(values)
    if n < 50:
        return {"n": n}
    rng = np.random.default_rng(seed)
    draws = rng.choice(values, size=(n_boot, n), replace=True).mean(axis=1)
    return {
        "n": n,
        "observed": float(values.mean()),
        "mean": float(draws.mean()),
        "ci_low": float(np.percentile(draws, 2.5)),
        "ci_high": float(np.percentile(draws, 97.5)),
        "p_above_break_even": float((draws > BREAK_EVEN).mean()),
        "p_above_53": float((draws > 0.530).mean()),
        "p_above_54": float((draws > 0.540).mean()),
        "p_above_55": float((draws > 0.550).mean()),
        "p_above_50": float((draws > 0.500).mean()),
    }
