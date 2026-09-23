"""A joint distribution over (home points, away points), from a margin pmf
and a total pmf.

The margin carries the key-number lattice; the total is a discretised normal.
Their residuals are close to independent - correlation 0.03-0.07 in both
sports once strength is accounted for - so the joint is their product on the
pairs they both allow: ``home = (total + margin) / 2`` and
``away = (total - margin) / 2``, which are integers exactly when the two share
parity, and a margin and total from the same game always do.

Every headline number is a mean of this grid, to one decimal: 31.7-24.2,
total 55.9. The most probable exact score is a different, much smaller,
number and is reported as such.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

#: Cells 0..79 on each axis. No FBS team has scored 80 since 2018.
DEFAULT_MAX_POINTS = 80


@dataclass(frozen=True)
class Joint:
    points: np.ndarray            # (P,) the points each axis can take
    pmf: np.ndarray               # (n, P, P) indexed [game, home, away]

    @property
    def n(self) -> int:
        return self.pmf.shape[0]

    @property
    def P(self) -> int:
        return len(self.points)

    def home_mean(self) -> np.ndarray:
        return np.einsum("nha,h->n", self.pmf, self.points)

    def away_mean(self) -> np.ndarray:
        return np.einsum("nha,a->n", self.pmf, self.points)

    def _aggregate(self, key: np.ndarray, size: int) -> np.ndarray:
        """Sum cells by an integer key in 0..size-1."""
        S = np.zeros((self.P * self.P, size))
        S[np.arange(self.P * self.P), key] = 1.0
        return self.pmf.reshape(self.n, -1) @ S

    def margin_pmf(self) -> tuple[np.ndarray, np.ndarray]:
        """(support, (n, K)) over home - away."""
        H, A = np.meshgrid(self.points, self.points, indexing="ij")
        support = np.arange(-(self.P - 1), self.P)
        return support, self._aggregate((H - A).ravel() + self.P - 1, len(support))

    def total_pmf(self) -> tuple[np.ndarray, np.ndarray]:
        """(support, (n, K)) over home + away."""
        H, A = np.meshgrid(self.points, self.points, indexing="ij")
        support = np.arange(0, 2 * self.P - 1)
        return support, self._aggregate((H + A).ravel(), len(support))

    def p_home_win(self) -> np.ndarray:
        """P(home > away) plus half of P(tie), the convention scoring uses."""
        H, A = np.meshgrid(self.points, self.points, indexing="ij")
        win = (H > A).astype(float) + 0.5 * (H == A)
        return np.einsum("nha,ha->n", self.pmf, win)

    def top_score(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """(home, away, probability) of the single most probable exact score."""
        flat = self.pmf.reshape(self.n, -1)
        k = flat.argmax(axis=1)
        return self.points[k // self.P], self.points[k % self.P], flat[np.arange(self.n), k]

    def cell_probability(self, home: np.ndarray, away: np.ndarray) -> np.ndarray:
        """The probability the grid gave an actual (home, away) score; 0 off-grid."""
        home = np.asarray(home, dtype=int)
        away = np.asarray(away, dtype=int)
        on = (home >= 0) & (home < self.P) & (away >= 0) & (away < self.P)
        out = np.zeros(self.n)
        idx = np.where(on)[0]
        out[idx] = self.pmf[idx, home[idx], away[idx]]
        return out

    def rank_of(self, home: np.ndarray, away: np.ndarray) -> np.ndarray:
        """How many cells the grid rated at least as likely as the actual score (1 = the top cell)."""
        p = self.cell_probability(home, away)
        flat = self.pmf.reshape(self.n, -1)
        return (flat >= p[:, None]).sum(axis=1)

    def summary(self, lo: float = 0.1, hi: float = 0.9) -> pd.DataFrame:
        """One row per game: the decimal means, P(home), a central total range and the top exact score."""
        support, tp = self.total_pmf()
        cdf = np.cumsum(tp, axis=1)
        q_lo = support[np.argmax(cdf >= lo, axis=1)]
        q_hi = support[np.argmax(cdf >= hi, axis=1)]
        th, ta, tp_ = self.top_score()
        h, a = self.home_mean(), self.away_mean()
        return pd.DataFrame({"home_mean": h, "away_mean": a, "total_mean": h + a, "margin_mean": h - a,
                             "p_home": self.p_home_win(), "total_lo": q_lo, "total_hi": q_hi,
                             "top_home": th, "top_away": ta, "top_p": tp_})


def _lookup(pmf: np.ndarray, support: np.ndarray, values: np.ndarray) -> np.ndarray:
    """``pmf[:, support == v]`` for every v, zero where v is outside the support."""
    idx = np.searchsorted(support, values)
    idx_c = np.minimum(idx, len(support) - 1)
    valid = support[idx_c] == values
    return pmf[:, idx_c] * valid[None, :]


def build(margin_pmf: np.ndarray, margin_support: np.ndarray, total_pmf: np.ndarray,
          total_support: np.ndarray, max_points: int = DEFAULT_MAX_POINTS) -> Joint:
    """The product joint on the ``max_points``² grid, renormalised.

    ``margin_pmf`` and ``total_pmf`` are ``(n, K)`` over their integer
    supports, as :func:`atlas.models.lattice.discretise` and
    :meth:`atlas.models.lattice.Lattice.pmf` return them. Mass the grid cannot
    hold (a 90-point game) is dropped by the renormalisation.
    """
    margin_pmf, total_pmf = np.asarray(margin_pmf, dtype=float), np.asarray(total_pmf, dtype=float)
    if margin_pmf.shape[0] != total_pmf.shape[0]:
        raise ValueError("margin and total pmfs describe different numbers of games")
    points = np.arange(max_points)
    H, A = np.meshgrid(points, points, indexing="ij")
    pm = _lookup(margin_pmf, np.asarray(margin_support), (H - A).ravel())
    pt = _lookup(total_pmf, np.asarray(total_support), (H + A).ravel())
    joint = pm * pt
    mass = joint.sum(axis=1, keepdims=True)
    if np.any(mass <= 0):
        raise ValueError("a game has no mass on the grid; check its means")
    joint /= mass
    return Joint(points=points, pmf=joint.reshape(-1, max_points, max_points))
