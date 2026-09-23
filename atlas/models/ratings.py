"""Least-squares team ratings: what a team actually was, in points.

The preseason prior needs a target - a number per team-season that says how
good the team turned out to be, in the units the model forecasts in. This is
the classic Massey / Glickman-Stern least-squares fit, done twice:

* **net** - ``margin = r_home - r_away + hfa``, one rating per team.
* **off / def** - ``home_pts = o_home - d_away + h`` and
  ``away_pts = o_away - d_home``, two ratings per team. A positive ``def``
  means points *prevented*, so ``net = off + def``.

Ratings are centred (sum to zero) and lightly ridged so a team with two games
does not get a rating of forty. Nothing here is point-in-time: it is fitted on
a whole season and is used only as the *target* for the prior regression,
never as a feature.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

#: Ridge toward zero, in games-worth of evidence. Small on purpose: this is a
#: description of a season, not a forecast, and heavy shrinkage would make the
#: prior regression learn to undo it.
RIDGE = 1.0


@dataclass(frozen=True)
class Ratings:
    teams: np.ndarray              # team ids, in rating order
    net: np.ndarray
    off: np.ndarray
    defense: np.ndarray            # points prevented; net == off + defense
    hfa: float                     # home advantage on the margin
    home_boost: float              # home advantage on points scored (half of hfa, roughly)
    games: int

    def frame(self) -> pd.DataFrame:
        return pd.DataFrame({"team_id": self.teams, "net": self.net, "off": self.off,
                             "def": self.defense})


def _design(home: np.ndarray, away: np.ndarray, teams: np.ndarray) -> tuple[np.ndarray, dict]:
    index = {t: i for i, t in enumerate(teams)}
    n, k = len(home), len(teams)
    X = np.zeros((n, k))
    X[np.arange(n), [index[t] for t in home]] = 1.0
    X[np.arange(n), [index[t] for t in away]] -= 1.0
    return X, index


def _solve(X: np.ndarray, y: np.ndarray, extra: np.ndarray | None, ridge: float) -> np.ndarray:
    """Ridge least squares with a sum-to-zero constraint on the team block.

    The constraint is imposed by appending one pseudo-observation that says
    the ratings sum to zero, weighted heavily
    the ridge is a diagonal on the
    team block only, never on the intercept-like ``extra`` columns.
    """
    k = X.shape[1]
    cols = [X] if extra is None else [X, extra]
    A = np.column_stack(cols)
    A = np.vstack([A, np.r_[np.full(k, 100.0), np.zeros(A.shape[1] - k)]])
    b = np.r_[y, 0.0]
    penalty = np.zeros(A.shape[1])
    penalty[:k] = ridge
    lhs = A.T @ A + np.diag(penalty)
    rhs = A.T @ b
    return np.linalg.solve(lhs, rhs)


def fit(games: pd.DataFrame, *, ridge: float = RIDGE) -> Ratings:
    """Fit net and off/def ratings on one season's games.

    ``games`` needs ``home_team_id``, ``away_team_id``, ``actual_margin``,
    ``actual_total`` and ``neutral_site`` (0/1). Home advantage is fitted, not
    assumed, and is zero at a neutral site.
    """
    g = games.dropna(subset=["home_team_id", "away_team_id", "actual_margin", "actual_total"])
    home = g["home_team_id"].to_numpy()
    away = g["away_team_id"].to_numpy()
    teams = np.unique(np.r_[home, away])
    is_home = 1.0 - pd.to_numeric(g.get("neutral_site", 0), errors="coerce").fillna(0).to_numpy(dtype=float)
    margin = g["actual_margin"].to_numpy(dtype=float)
    total = g["actual_total"].to_numpy(dtype=float)
    home_pts = (total + margin) / 2.0
    away_pts = (total - margin) / 2.0
    k = len(teams)

    # Net: margin = r_h - r_a + hfa*home
    X, _ = _design(home, away, teams)
    beta = _solve(X, margin, is_home[:, None], ridge)
    net, hfa = beta[:k], float(beta[k])

    # Off/def: stack home and away scoring rows.
    #   home_pts = o_h - d_a + boost*home
    #   away_pts = o_a - d_h
    idx = {t: i for i, t in enumerate(teams)}
    n = len(g)
    Xo = np.zeros((2 * n, 2 * k))
    rows = np.arange(n)
    Xo[rows, [idx[t] for t in home]] = 1.0                 # home offence
    Xo[rows, k + np.array([idx[t] for t in away])] = -1.0  # away defence
    Xo[n + rows, [idx[t] for t in away]] = 1.0             # away offence
    Xo[n + rows, k + np.array([idx[t] for t in home])] = -1.0
    extra = np.r_[is_home, np.zeros(n)][:, None]
    y = np.r_[home_pts, away_pts]
    # Two sum-to-zero constraints (offence block and defence block) plus an
    # intercept for league-average points, which is what centring leaves.
    intercept = np.ones((2 * n, 1))
    A = np.column_stack([Xo, extra, intercept])
    con = np.zeros((2, A.shape[1]))
    con[0, :k] = 100.0
    con[1, k:2 * k] = 100.0
    A = np.vstack([A, con])
    b = np.r_[y, 0.0, 0.0]
    penalty = np.zeros(A.shape[1])
    penalty[:2 * k] = ridge
    sol = np.linalg.solve(A.T @ A + np.diag(penalty), A.T @ b)
    off, defense, boost = sol[:k], sol[k:2 * k], float(sol[2 * k])
    return Ratings(teams=teams, net=net, off=off, defense=defense, hfa=hfa,
                   home_boost=boost, games=int(n))
