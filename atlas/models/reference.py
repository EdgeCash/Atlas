"""The reference models every candidate is scored beside.

`docs/MODEL_FOUNDATION.md` §6: a plan is not finished until the model beats
the first two of these and is within reach of the third. They are deliberately
simple - each is a mean and a standard deviation, fitted walk-forward on the
seasons before the one being scored - because their job is to be a floor and
a ceiling, not to be good.

* ``naive``     - the home team by the fitted home advantage, league sd.
* ``prior_fpi`` - last season's FPI difference, one coefficient plus HFA.
* ``prior_sp``  - last season's SP+ difference, the same way.
* ``elo``       - the point-in-time pregame Elo difference, the same way. In
                  college this is the strongest single external predictor
                  late in the season, which makes it the floor that matters.
* ``atlas_epa`` - Atlas's own point-in-time opponent-adjusted net EPA
                  difference, the same way. Where the current inputs stand.
* ``market``    - the closing line as the mean, residual sd from training.
                  The ceiling.

Every model produces a normal on the margin; the lattice (fit once per
training window, on the market's means) is applied to all of them identically
downstream, so a difference in score is a difference in mean and sd, nothing
else.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

#: Feature used by each single-coefficient reference model.
FEATURES = {
    "prior_fpi": "fpi_diff",
    "prior_sp": "sp_plus_diff",
    "elo": "elo_diff",
    "atlas_epa": "adj_net_epa_diff",
}

ORDER = ("naive", "prior_fpi", "prior_sp", "elo", "atlas_epa", "market")

#: A feature model needs its feature on at least this share of training games;
#: below it the fit is not a reference, it is noise with a name.
MIN_COVERAGE = 0.5


@dataclass(frozen=True)
class Forecast:
    """One model's normal on the margin for each game in a frame."""

    name: str
    mean: np.ndarray
    sigma: float
    coefficient: float | None = None     # the feature's points per unit, if any
    hfa: float | None = None             # fitted home advantage, points


def _home(frame: pd.DataFrame) -> np.ndarray:
    """1 for a true home game, 0 at a neutral site."""
    neutral = pd.to_numeric(frame.get("neutral_site", 0), errors="coerce").fillna(0).astype(float)
    return 1.0 - neutral.to_numpy()


def _ols(y: np.ndarray, columns: list[np.ndarray]) -> np.ndarray:
    X = np.column_stack([np.ones(len(y)), *columns])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    return beta


def naive(train: pd.DataFrame, test: pd.DataFrame) -> Forecast:
    y = train["actual_margin"].to_numpy(dtype=float)
    beta = _ols(y, [_home(train)])
    mean_train = beta[0] + beta[1] * _home(train)
    sigma = float(np.std(y - mean_train, ddof=2))
    return Forecast("naive", beta[0] + beta[1] * _home(test), sigma, hfa=float(beta[1]))


def single_feature(name: str, train: pd.DataFrame, test: pd.DataFrame) -> Forecast:
    """``margin ~ intercept + coef * feature + hfa * home``, fitted on train.

    Rows with a missing feature fall back to the naive mean, so every game in
    the test frame gets a forecast and the comparison stays paired.
    """
    col = FEATURES[name]
    tr = train.dropna(subset=[col])
    if len(tr) < 30:
        raise ValueError(f"{name}: only {len(tr)} training games carry {col}")
    y = tr["actual_margin"].to_numpy(dtype=float)
    x = pd.to_numeric(tr[col], errors="coerce").to_numpy(dtype=float)
    beta = _ols(y, [x, _home(tr)])
    resid = y - (beta[0] + beta[1] * x + beta[2] * _home(tr))
    sigma = float(np.std(resid, ddof=3))
    fallback = naive(train, test).mean
    xt = pd.to_numeric(test[col], errors="coerce").to_numpy(dtype=float)
    mean = beta[0] + beta[1] * xt + beta[2] * _home(test)
    mean = np.where(np.isnan(mean), fallback, mean)
    return Forecast(name, mean, sigma, coefficient=float(beta[1]), hfa=float(beta[2]))


def market(train: pd.DataFrame, test: pd.DataFrame) -> Forecast:
    """The closing spread as the mean (home-oriented, so negated), train residual sd."""
    resid = train["actual_margin"].to_numpy(dtype=float) + train["closing_spread"].to_numpy(dtype=float)
    sigma = float(np.std(resid, ddof=1))
    return Forecast("market", -test["closing_spread"].to_numpy(dtype=float), sigma)


def all_references(train: pd.DataFrame, test: pd.DataFrame) -> dict[str, Forecast]:
    out = {"naive": naive(train, test)}
    for name, col in FEATURES.items():
        if col not in train.columns or col not in test.columns:
            continue
        coverage = pd.to_numeric(train[col], errors="coerce").notna().mean()
        if coverage < MIN_COVERAGE:
            continue
        out[name] = single_feature(name, train, test)
    out["market"] = market(train, test)
    return out


def walk_forward(frame: pd.DataFrame, *, first_test_season: int, min_train_seasons: int = 2,
                 fit_regular_only: bool = True):
    """Yield ``(season, train, test)`` with train strictly before test.

    Bowls and playoffs (``season_type != 'regular'``) are scored but never
    fitted: opt-outs and motivation make them a different game, and a
    reference fitted on them would be a worse reference.
    """
    seasons = sorted(int(s) for s in frame["season"].unique())
    for s in seasons:
        if s < first_test_season:
            continue
        train = frame[frame["season"] < s]
        if fit_regular_only and "season_type" in train.columns:
            train = train[train["season_type"] == "regular"]
        if train["season"].nunique() < min_train_seasons:
            continue
        yield s, train, frame[frame["season"] == s]
