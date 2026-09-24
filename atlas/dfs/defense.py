"""A defense's DraftKings points, built from its parts.

Step 4 of `docs/MODEL_PLAN_DFS.md`. A defense scores from a handful of
events and one step function, so its projection is built the way it is
scored:

* **sacks, takeaways and return touchdowns** - each a Poisson count whose
  rate is fitted (a Poisson regression, lightly penalised) on the defense's
  own form, the form of the offense it faces - what that offense has given
  up to earlier defenses - and the game: both sides' projected points, as
  Atlas's game model and the line see them;
* **safeties, blocked kicks and returned conversions** - rare enough that
  the league's rate per game is the honest estimate;
* **points allowed** - a line on the opponent's projected points, with the
  training seasons' own misses around it as the spread, mapped through
  DraftKings' points-allowed table. The table is a step function, so the
  expected bonus is the average over those misses, not the bonus at the
  expected score.

The sum is ``dst_parts``: a defense's expected points, walk-forward (each
season fitted on the seasons before it), which the player model reads as
one more input for defenses.
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
from sklearn.linear_model import PoissonRegressor

from atlas.dfs import scoring

#: Each count, its DraftKings weight, and whether it gets its own rate model.
COUNTS = {"sacks": (1.0, True), "takeaways": (2.0, True), "tds": (6.0, True), "safeties": (2.0, False),
          "blocked_kicks": (2.0, False), "conversion_returns": (2.0, False)}
RATE_FEATURES = ["sacks_trend", "takeaways_trend", "points_allowed_trend", "opp_sacks_taken_trend",
                 "opp_giveaways_trend", "opp_dst_points_trend", "team_pts", "opp_pts", "mkt_pts", "mkt_opp", "home"]
ALLOWED_FEATURES = ["opp_pts", "mkt_opp", "points_allowed_trend", "opp_dst_points_trend"]
MISSES = 2000                      # misses sampled for the points-allowed bonus
FIRST = 2012                       # the first season with a season before it


class _Standard:
    """Standardise with the training rows' means; a missing value is the mean."""

    def __init__(self, X: np.ndarray):
        self.mu = np.nanmean(X, axis=0)
        self.mu = np.where(np.isnan(self.mu), 0.0, self.mu)
        self.sd = np.nanstd(X, axis=0)
        self.sd = np.where((self.sd > 0) & ~np.isnan(self.sd), self.sd, 1.0)

    def __call__(self, X: np.ndarray) -> np.ndarray:
        return (np.where(np.isnan(X), self.mu, X) - self.mu) / self.sd


def _x(rows: pd.DataFrame, cols: list[str]) -> np.ndarray:
    return rows.reindex(columns=cols).to_numpy(dtype=float)


def fit_predict(train: pd.DataFrame, test: pd.DataFrame, *, seed: int = 0) -> pd.DataFrame:
    """Expected parts and points for ``test``'s defenses, from ``train``'s."""
    train = train.dropna(subset=["points_allowed"])
    out = pd.DataFrame(index=test.index)
    total = np.zeros(len(test))
    scale = _Standard(_x(train, RATE_FEATURES))
    for name, (weight, modelled) in COUNTS.items():
        y = train[name].to_numpy(dtype=float)
        if modelled:
            with warnings.catch_warnings():   # scikit-learn logs a zero count's log on the way; harmless
                warnings.simplefilter("ignore", RuntimeWarning)
                glm = PoissonRegressor(alpha=1e-3, max_iter=300).fit(scale(_x(train, RATE_FEATURES)), y)
            rate = glm.predict(scale(_x(test, RATE_FEATURES)))
        else:
            rate = np.full(len(test), float(np.mean(y)))
        out[f"exp_{name}"] = rate
        total += weight * rate
    # Points allowed: a line on the opponent's projection, and the misses around it.
    pa_scale = _Standard(_x(train, ALLOWED_FEATURES))
    Xa = np.column_stack([np.ones(len(train)), pa_scale(_x(train, ALLOWED_FEATURES))])
    coef, *_ = np.linalg.lstsq(Xa, train["points_allowed"].to_numpy(dtype=float), rcond=None)
    misses = train["points_allowed"].to_numpy(dtype=float) - Xa @ coef
    misses = np.random.default_rng(seed).choice(misses, size=min(MISSES, len(misses)), replace=False)
    mean_pa = np.column_stack([np.ones(len(test)), pa_scale(_x(test, ALLOWED_FEATURES))]) @ coef
    draws = np.clip(mean_pa[:, None] + misses[None, :], 0, None)
    bonus = scoring.points_allowed_score(pd.Series(draws.ravel())).to_numpy().reshape(draws.shape).mean(axis=1)
    out["exp_points_allowed"] = mean_pa
    out["exp_pa_bonus"] = bonus
    out["dst_parts"] = total + bonus
    return out


def walk_forward(frame: pd.DataFrame, *, first: int = FIRST) -> pd.DataFrame:
    """``fit_predict`` for every season from ``first``, each on the seasons before it."""
    parts = []
    for season in sorted(int(s) for s in frame["season"].unique()):
        if season < first:
            continue
        train, test = frame[frame["season"] < season], frame[frame["season"] == season]
        if len(train.dropna(subset=["points_allowed"])) < 100 or test.empty:
            continue
        parts.append(fit_predict(train, test))
    return pd.concat(parts) if parts else pd.DataFrame(columns=["dst_parts"])


def components(dst_games: pd.DataFrame) -> pd.DataFrame:
    """The counts each defense recorded per game, keyed like the model's rows."""
    d = dst_games[dst_games["season_type"] == "REG"]
    return pd.DataFrame({
        "season": d["season"], "week": d["week"], "player_id": "DST-" + d["team"],
        "sacks": d["sacks"], "takeaways": d["interceptions"] + d["fumble_recoveries"], "tds": d["tds"],
        "safeties": d["safeties"], "blocked_kicks": d["blocked_kicks"],
        "conversion_returns": d["conversion_returns"], "points_allowed": d["points_allowed"]})
