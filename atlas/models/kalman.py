"""A joint Kalman filter over every team's offensive and defensive strength.

The state is one vector holding ``off`` and ``def`` for every team, in points
above league average, with a full covariance matrix. That covariance is the
opponent adjustment: beating a team the filter is unsure about moves you less
than beating one it knows, and a result against a common opponent tightens
both teams at once. Glickman & Stern (1998) fit this by MCMC; Elvidge (2025)
runs it as a filter whose gain replaces Elo's fixed K. This is the filter.

Observations are points scored, two per game:

    home_pts = base + off_home - def_away + boost + e
    away_pts = base + off_away - def_home         + e

``def`` is points *prevented* (positive is good), so a margin is
``off_h + def_h - off_a - def_a + boost``. Each game is processed strictly in
kickoff order: the forecast for a game uses only games that kicked off
before it, which is the point-in-time rule the rest of Atlas keeps.

Nothing in this file knows about football beyond that. Sport-specific
choices - the prior, the hyperparameters, what to compare against - live in
the sport's runner.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Spec:
    """Hyperparameters. ``q_*`` are process variances per week, ``p0_*`` the
    prior variance on a team's strength at week 1, ``sigma`` the sd of the
    noise on one team's points in one game."""

    q_off: float
    q_def: float
    p0_off: float
    p0_def: float
    sigma: float
    base: float          # league-average points per team-game
    boost: float         # home advantage on the home team's points (== hfa on the margin)


@dataclass
class State:
    teams: np.ndarray                      # team ids, in index order
    x: np.ndarray                          # (2N,): off for team i at i, def at N + i
    P: np.ndarray                          # (2N, 2N)
    week: int | None = None
    index: dict = field(default_factory=dict)

    @property
    def n(self) -> int:
        return len(self.teams)

    def off(self, team) -> float:
        return float(self.x[self.index[team]])

    def defense(self, team) -> float:
        return float(self.x[self.n + self.index[team]])

    def net(self, team) -> float:
        return self.off(team) + self.defense(team)

    def frame(self) -> pd.DataFrame:
        n = self.n
        sd = np.sqrt(np.diag(self.P))
        return pd.DataFrame({"team_id": self.teams, "off": self.x[:n], "def": self.x[n:],
                             "net": self.x[:n] + self.x[n:],
                             "sd_off": sd[:n], "sd_def": sd[n:]})


def initialise(teams: np.ndarray, off: np.ndarray, defense: np.ndarray, spec: Spec) -> State:
    """A state at week 1: the prior's means, diagonal prior variance."""
    teams = np.asarray(teams)
    n = len(teams)
    x = np.r_[np.asarray(off, dtype=float), np.asarray(defense, dtype=float)]
    P = np.diag(np.r_[np.full(n, spec.p0_off), np.full(n, spec.p0_def)])
    return State(teams=teams, x=x, P=P, week=None, index={t: i for i, t in enumerate(teams)})


def advance(state: State, weeks: int, spec: Spec) -> None:
    """Add ``weeks`` of process noise. In place."""
    if weeks <= 0:
        return
    n = state.n
    diag = np.r_[np.full(n, spec.q_off), np.full(n, spec.q_def)] * weeks
    state.P[np.diag_indices_from(state.P)] += diag


def _rows(state: State, home, away) -> tuple[np.ndarray, np.ndarray]:
    """Observation rows for home points and away points."""
    n = state.n
    h, a = state.index[home], state.index[away]
    rh = np.zeros(2 * n)
    rh[h] = 1.0            # home offence
    rh[n + a] = -1.0       # away defence
    ra = np.zeros(2 * n)
    ra[a] = 1.0            # away offence
    ra[n + h] = -1.0       # home defence
    return rh, ra


def forecast(state: State, home, away, is_home: float, spec: Spec) -> tuple[float, float, float, float]:
    """(mean margin, sd margin, mean home points, mean away points) for one game."""
    n = state.n
    h, a = state.index[home], state.index[away]
    x, P = state.x, state.P
    mh = spec.base + x[h] - x[n + a] + spec.boost * is_home
    ma = spec.base + x[a] - x[n + h]
    # margin row: +off_h +def_h -off_a -def_a  ->  indices (h, n+h) plus, (a, n+a) minus
    idx = np.array([h, n + h, a, n + a])
    sign = np.array([1.0, 1.0, -1.0, -1.0])
    sub_P = P[np.ix_(idx, idx)]
    var = float(sign @ sub_P @ sign) + 2.0 * spec.sigma ** 2
    return float(mh - ma), float(np.sqrt(var)), float(mh), float(ma)


def _sparse_update(state: State, plus: int, minus: int, y: float, r: float) -> None:
    """Scalar Kalman update for an observation row with +1 at ``plus`` and -1 at ``minus``.

    ``P @ row`` is just two columns of P, so the gain costs O(N), and only the
    rank-one covariance update is O(N²) - one BLAS call. This is what makes a
    season of ~750 games over ~270 states take well under a second.
    """
    P = state.P
    Ph = P[:, plus] - P[:, minus]
    s = float(Ph[plus] - Ph[minus]) + r
    k = Ph / s
    innovation = y - (state.x[plus] - state.x[minus])
    state.x += k * innovation
    P -= np.outer(k, Ph)


def update(state: State, home, away, home_pts: float, away_pts: float, is_home: float,
           spec: Spec) -> None:
    """Assimilate one game's two point totals. In place."""
    n = state.n
    h, a = state.index[home], state.index[away]
    r = spec.sigma ** 2
    _sparse_update(state, h, n + a, home_pts - spec.base - spec.boost * is_home, r)
    _sparse_update(state, a, n + h, away_pts - spec.base, r)


def run_season(games: pd.DataFrame, state: State, spec: Spec) -> pd.DataFrame:
    """Forecast every game before it is played, then learn from it.

    ``games`` must carry ``home_team_id``, ``away_team_id``, ``week``,
    ``kickoff``, ``actual_margin``, ``actual_total``, ``neutral_site``. Rows
    are processed in kickoff order; process noise is added whenever the week
    advances. Returns one row per game with the pre-kickoff forecast.
    """
    g = games.sort_values(["kickoff", "week"])
    idx = g.index.to_numpy()
    weeks = g["week"].to_numpy(dtype=int)
    homes = g["home_team_id"].to_numpy()
    aways = g["away_team_id"].to_numpy()
    neutral = pd.to_numeric(g["neutral_site"], errors="coerce").fillna(0).to_numpy(dtype=float) \
        if "neutral_site" in g else np.zeros(len(g))
    margins = g["actual_margin"].to_numpy(dtype=float)
    totals = g["actual_total"].to_numpy(dtype=float)
    means = np.full(len(g), np.nan)
    sds = np.full(len(g), np.nan)
    hps = np.full(len(g), np.nan)
    aps = np.full(len(g), np.nan)
    known = state.index
    for i in range(len(g)):
        week = int(weeks[i])
        if state.week is None:
            state.week = week
        elif week > state.week:
            advance(state, week - state.week, spec)
            state.week = week
        h, a = homes[i], aways[i]
        if h not in known or a not in known:
            continue
        is_home = 0.0 if neutral[i] else 1.0
        means[i], sds[i], hps[i], aps[i] = forecast(state, h, a, is_home, spec)
        m, t = margins[i], totals[i]
        update(state, h, a, (t + m) / 2.0, (t - m) / 2.0, is_home, spec)
    out = pd.DataFrame({"mean": means, "sd": sds, "home_pts": hps, "away_pts": aps}, index=idx)
    return out.reindex(games.index)
