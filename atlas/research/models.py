"""Model plumbing shared by the benchmark and importance studies.

Every number Atlas reports is out-of-sample. Folds are whole seasons
(leave-one-season-out), because a random split would let a model learn a
season's own scoring environment from its other games - the closest thing to
leakage that survives a clean warehouse.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from atlas import config
from atlas.research.dataset import feature_matrix


def ridge() -> Pipeline:
    return Pipeline(
        [("scale", StandardScaler()), ("model", Ridge(alpha=1.0, random_state=None))]
    )


def gbm() -> HistGradientBoostingRegressor:
    return HistGradientBoostingRegressor(
        max_depth=3,
        max_iter=300,
        learning_rate=0.05,
        l2_regularization=1.0,
        random_state=config.SEED,
    )


@dataclass
class FoldPredictions:
    y_true: np.ndarray
    y_pred: np.ndarray
    season: np.ndarray
    features: list[str]
    #: Positional indices of the rows kept, so two runs over the same frame
    #: can be paired game-by-game for a significance test.
    index: np.ndarray | None = None

    @property
    def abs_error(self) -> np.ndarray:
        return np.abs(self.y_pred - self.y_true)


def leave_one_season_out(
    df: pd.DataFrame,
    features: list[str],
    target: str,
    *,
    model_factory=ridge,
) -> FoldPredictions:
    """Fit on every season but one, predict the held-out season, repeat."""
    y = pd.to_numeric(df[target], errors="coerce").to_numpy(dtype=float)
    X, used = feature_matrix(df, features)
    seasons = df["season"].to_numpy()
    positions = np.arange(len(df))
    valid = np.isfinite(y)
    if not used or valid.sum() == 0:
        return FoldPredictions(
            y[valid], np.full(valid.sum(), np.nan), seasons[valid], used, positions[valid]
        )

    preds = np.full(len(df), np.nan)
    for season in np.unique(seasons):
        train = valid & (seasons != season)
        test = valid & (seasons == season)
        if train.sum() < 100 or test.sum() == 0:
            continue
        model = model_factory()
        model.fit(X[train], y[train])
        preds[test] = model.predict(X[test])

    keep = valid & np.isfinite(preds)
    return FoldPredictions(y[keep], preds[keep], seasons[keep], used, positions[keep])


def metrics(fold: FoldPredictions) -> dict[str, float]:
    if len(fold.y_true) == 0 or not np.isfinite(fold.y_pred).any():
        return {"n": 0, "mae": float("nan"), "rmse": float("nan"), "r2": float("nan"),
                "bias": float("nan")}
    err = fold.y_pred - fold.y_true
    ss_res = float(np.sum(err**2))
    ss_tot = float(np.sum((fold.y_true - fold.y_true.mean()) ** 2))
    return {
        "n": int(len(fold.y_true)),
        "mae": float(np.mean(np.abs(err))),
        "rmse": float(np.sqrt(np.mean(err**2))),
        "r2": float(1 - ss_res / ss_tot) if ss_tot > 0 else float("nan"),
        "bias": float(np.mean(err)),
    }


def season_metrics(fold: FoldPredictions) -> pd.DataFrame:
    rows = []
    for season in np.unique(fold.season):
        mask = fold.season == season
        sub = FoldPredictions(
            fold.y_true[mask], fold.y_pred[mask], fold.season[mask], fold.features
        )
        rows.append({"season": int(season), **metrics(sub)})
    return pd.DataFrame(rows)


def directional_accuracy(
    fold: FoldPredictions, line: np.ndarray, *, higher_is_over: bool = True
) -> dict[str, float]:
    """How often a prediction lands on the correct side of a market line.

    ``line`` is the market's number on the same scale as the prediction, so
    for margin pass ``-closing_spread`` and for totals ``closing_total``.
    """
    if len(fold.y_true) == 0:
        return {"picks": 0, "hit_rate": float("nan")}
    pred_side = np.sign(fold.y_pred - line)
    true_side = np.sign(fold.y_true - line)
    live = (pred_side != 0) & (true_side != 0)
    if live.sum() == 0:
        return {"picks": 0, "hit_rate": float("nan")}
    hits = (pred_side[live] == true_side[live]).mean()
    return {"picks": int(live.sum()), "hit_rate": float(hits if higher_is_over else 1 - hits)}


def paired_mae_gain(base: FoldPredictions, other: FoldPredictions) -> dict[str, float]:
    """Per-game paired comparison of two out-of-sample fits.

    Reports how much MAE ``other`` removes relative to ``base`` on the games
    both scored, together with the standard error of that difference and its
    t-statistic. A gain smaller than its own noise is not a finding, and the
    only honest way to say so is to carry the error bar alongside it.
    """
    if base.index is None or other.index is None:
        return {"mae_gain": float("nan"), "gain_se": float("nan"), "gain_t": float("nan"),
                "n_paired": 0}
    common, a_pos, b_pos = np.intersect1d(base.index, other.index, return_indices=True)
    if len(common) < 50:
        return {"mae_gain": float("nan"), "gain_se": float("nan"), "gain_t": float("nan"),
                "n_paired": int(len(common))}
    diff = base.abs_error[a_pos] - other.abs_error[b_pos]
    gain = float(diff.mean())
    se = float(diff.std(ddof=1) / np.sqrt(len(diff)))
    return {
        "mae_gain": gain,
        "gain_se": se,
        "gain_t": float(gain / se) if se > 0 else float("nan"),
        "n_paired": int(len(diff)),
    }


def null_fold(df: pd.DataFrame, target: str, *, constant: float | None = None) -> FoldPredictions:
    """The do-nothing model, folded the same way as everything else.

    With ``constant=None`` each season is predicted by the other seasons' mean,
    which is the right baseline for margin and total. With ``constant=0`` the
    prediction is "the market is exactly right", which is the right baseline
    for a residual target - and the one Phase 1B has to beat.
    """
    y = pd.to_numeric(df[target], errors="coerce").to_numpy(dtype=float)
    seasons = df["season"].to_numpy()
    positions = np.arange(len(df))
    valid = np.isfinite(y)

    preds = np.full(len(df), np.nan)
    if constant is not None:
        preds[valid] = constant
    else:
        for season in np.unique(seasons):
            train = valid & (seasons != season)
            test = valid & (seasons == season)
            if train.sum() == 0 or test.sum() == 0:
                continue
            preds[test] = y[train].mean()

    keep = valid & np.isfinite(preds)
    return FoldPredictions(y[keep], preds[keep], seasons[keep], ["<null>"], positions[keep])
