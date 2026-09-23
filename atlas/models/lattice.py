"""The key-number lattice: turning a normal on the margin into football.

A normal with the right standard deviation is an excellent model of a football
margin *except* that scores land on 3s and 7s. Empirically |margin| = 3 in
14.4% of NFL games and 8.1% of college games; a normal puts about 3.6% there.
The fix, from the college spread-to-probability literature and re-derived on
Atlas's own data, is to multiply each integer's normal probability by an
empirical factor and renormalise. The factors are a property of the sport's
scoring, not of any model, so the same table is applied to every model's
normal and the comparison between models stays a comparison of means and
standard deviations.

The factors drift with the rules - two-point conversions, kickoff changes,
fourth-down culture - so they are refit on the training window every time,
never transcribed.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import stats

#: Integer margins the lattice covers; outside it the factor is one.
DEFAULT_SUPPORT = np.arange(-80, 81)

#: Past this |margin| the empirical count is too thin to trust and the factor
#: is held at one. Chosen so a bucket has dozens of games, not a handful.
DEFAULT_MAX_KEY = 28

#: Below this many training games at a margin the factor is shrunk toward one
#: rather than estimated - a single 41-point game must not become a spike.
MIN_GAMES_AT_MARGIN = 15

#: No key number is remotely this peaked (3 is ~2.9 in the NFL, 2.7 in college),
#: so anything above it is a thin-sample artifact and is capped before shrinkage.
MAX_FACTOR = 5.0


@dataclass(frozen=True)
class Lattice:
    support: np.ndarray
    factor: np.ndarray          # same length as support
    sigma: float                # the normal sd the factors were fit against
    games: int

    def at(self, margin: int) -> float:
        i = np.searchsorted(self.support, margin)
        if i < len(self.support) and self.support[i] == margin:
            return float(self.factor[i])
        return 1.0

    def pmf(self, mean: np.ndarray, sigma: float | np.ndarray | None = None) -> np.ndarray:
        """``(n, K)`` probabilities over the support for each game's mean.

        Each integer gets the normal mass on ``[k - 0.5, k + 0.5)``, times its
        factor, renormalised per row. ``sigma`` defaults to the fitted one;
        a per-game vector is allowed for models that carry their own spread.
        """
        return discretise(np.asarray(mean, dtype=float), sigma if sigma is not None else self.sigma,
                          self.support, self.factor)


def discretise(mean: np.ndarray, sigma: float | np.ndarray, support: np.ndarray,
               factor: np.ndarray | None = None) -> np.ndarray:
    mean = np.atleast_1d(mean).astype(float)
    sigma = np.broadcast_to(np.asarray(sigma, dtype=float), mean.shape)
    if not np.all(np.isfinite(sigma)) or np.any(sigma <= 0):
        raise ValueError("sigma must be finite and positive")
    if not np.all(np.isfinite(mean)):
        raise ValueError("every mean must be finite")
    hi = stats.norm.cdf((support[None, :] + 0.5 - mean[:, None]) / sigma[:, None])
    lo = stats.norm.cdf((support[None, :] - 0.5 - mean[:, None]) / sigma[:, None])
    p = hi - lo
    if factor is not None:
        p = p * factor[None, :]
    total = p.sum(axis=1, keepdims=True)
    return p / np.where(total > 0, total, 1.0)


def fit(margins: np.ndarray, means: np.ndarray, sigma: float, *,
        support: np.ndarray = DEFAULT_SUPPORT, max_key: int = DEFAULT_MAX_KEY) -> Lattice:
    """Fit the factor at every integer margin from a training set.

    ``factor[k] = observed share of games at k / mean normal probability at k``,
    where the normal is centred on each game's own ``mean``. Using the per-game
    mean rather than a single pooled normal is what makes the factor a lattice
    effect and not a strength effect: a 20-point favourite's normal already
    puts little mass at 3, and the factor only says how much *more* than the
    normal expects lands there.
    """
    margins = np.asarray(margins, dtype=float)
    means = np.asarray(means, dtype=float)
    if len(margins) != len(means):
        raise ValueError("one mean per margin")
    base = discretise(means, sigma, support)          # (n, K) normal, no factor
    expected = base.mean(axis=0)                      # mean normal prob at each k
    observed = np.array([(margins == k).mean() for k in support])
    counts = np.array([(margins == k).sum() for k in support])
    raw = np.where(expected > 0, observed / np.where(expected > 0, expected, 1.0), 1.0)
    raw = np.minimum(raw, MAX_FACTOR)
    # Shrink thin margins toward one in proportion to how thin they are.
    weight = np.clip(counts / MIN_GAMES_AT_MARGIN, 0.0, 1.0)
    factor = 1.0 + weight * (raw - 1.0)
    factor = np.where(np.abs(support) > max_key, 1.0, factor)
    return Lattice(support=support, factor=factor, sigma=float(sigma), games=int(len(margins)))
