"""A joint Kalman filter over every team's offensive and defensive strength.

The state is one vector holding ``off`` and ``def`` for every team, in points
above league average, with a full covariance matrix. That covariance is the
opponent adjustment: beating a team the filter is unsure about moves you less
than beating one it knows, and a result against a common opponent tightens
both teams at once. Glickman & Stern (1998) fit this by MCMC; Elvidge (2025)
runs it as a filter whose gain replaces Elo's fixed K. This is the filter.

Observations are points scored, two per game:

    home_pts = base + off_home - def_away + boost + e_home
    away_pts = base + off_away - def_home         + e_away

Each ``e`` has variance ``sigma**2`` and the two are correlated by ``rho``:
pace, weather and game script move both teams' points together, so a game
that runs high on both sides is partly a high-scoring game and not two good
offences. The pair is assimilated as its margin (noise ``2 sigma**2 (1 -
rho)``) and its total (noise ``2 sigma**2 (1 + rho)``), which are
uncorrelated, so two scalar updates are exact.

``def`` is points *prevented* (positive is good), so a margin is
``off_h + def_h - off_a - def_a + boost``. Each game is processed strictly in
kickoff order: the forecast for a game uses only games that kicked off
before it, which is the point-in-time rule the rest of Atlas keeps. Games
sharing a kickoff are all forecast before any of them is assimilated.

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
    rho: float = 0.0     # correlation between the two teams' point noise in one game

    @property
    def margin_noise(self) -> float:
        """Variance of the margin's noise: ``2 sigma² (1 - rho)``."""
        return 2.0 * self.sigma ** 2 * (1.0 - self.rho)

    @property
    def total_noise(self) -> float:
        """Variance of the total's noise: ``2 sigma² (1 + rho)``."""
        return 2.0 * self.sigma ** 2 * (1.0 + self.rho)


@dataclass
class State:
    teams: np.ndarray                      # team ids, in index order
    x: np.ndarray                          # (2N,): off for team i at i, def at N + i
    P: np.ndarray                          # (2N, 2N)
    week: int | None = None
    index: dict = field(default_factory=dict)
    kickoff: pd.Timestamp | None = None    # the latest kickoff forecast from this state

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
        return pd.DataFrame({"team_id": self.teams, "off": self.x[:n], "def": self.x[n:2 * n],
                             "net": self.x[:n] + self.x[n:2 * n],
                             "sd_off": sd[:n], "sd_def": sd[n:2 * n]})

    # -- extra state elements (quarterbacks, a home advantage) ---------------
    # Anything past index 2N is an extra element with its own key in ``extra``.

    @property
    def extra(self) -> dict:
        if not hasattr(self, "_extra"):
            object.__setattr__(self, "_extra", {})
        return self._extra

    def add(self, key, mean: float, variance: float) -> int:
        """Append one state element, uncorrelated with everything, and return its index."""
        if key in self.extra:
            raise KeyError(f"{key!r} is already in the state")
        k = len(self.x)
        self.x = np.append(self.x, float(mean))
        P = np.zeros((k + 1, k + 1))
        P[:k, :k] = self.P
        P[k, k] = float(variance)
        self.P = P
        self.extra[key] = k
        return k

    def value(self, key) -> float:
        return float(self.x[self.extra[key]])

    def variance(self, key) -> float:
        i = self.extra[key]
        return float(self.P[i, i])


def initialise(teams: np.ndarray, off: np.ndarray, defense: np.ndarray, spec: Spec) -> State:
    """A state at week 1: the prior's means, diagonal prior variance."""
    teams = np.asarray(teams)
    n = len(teams)
    x = np.r_[np.asarray(off, dtype=float), np.asarray(defense, dtype=float)]
    P = np.diag(np.r_[np.full(n, spec.p0_off, dtype=float), np.full(n, spec.p0_def, dtype=float)])
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
    var = float(sign @ sub_P @ sign) + spec.margin_noise
    return float(mh - ma), float(np.sqrt(var)), float(mh), float(ma)


def total_sd(state: State, home, away, spec: Spec) -> float:
    """The sd of one game's total: the state's uncertainty plus the total's noise."""
    n = state.n
    h, a = state.index[home], state.index[away]
    # total row: +off_h -def_a +off_a -def_h
    idx = np.array([h, n + a, a, n + h])
    sign = np.array([1.0, -1.0, 1.0, -1.0])
    return float(np.sqrt(float(sign @ state.P[np.ix_(idx, idx)] @ sign) + spec.total_noise))


def pair_update(state: State, home: tuple[list[int], list[int]], away: tuple[list[int], list[int]],
                y_home: float, y_away: float, r: float, rho: float = 0.0) -> None:
    """Assimilate one game's two point observations. In place.

    ``home`` and ``away`` are each observation row's (plus, minus) indices;
    ``y_*`` the points net of anything outside the state; ``r`` one team's
    noise variance and ``rho`` the correlation between the two. With rho = 0
    this is two independent scalar updates, exactly as before; otherwise the
    margin and the total are assimilated, which are independent.
    """
    (hp, hm), (ap, am) = home, away
    if rho == 0.0:
        row_update(state, hp, hm, y_home, r)
        row_update(state, ap, am, y_away, r)
        return
    row_update(state, hp + am, hm + ap, y_home - y_away, 2.0 * r * (1.0 - rho))
    row_update(state, hp + ap, hm + am, y_home + y_away, 2.0 * r * (1.0 + rho))


def _sparse_update(state: State, plus: int, minus: int, y: float, r: float) -> None:
    """Scalar Kalman update for an observation row with +1 at ``plus`` and -1 at ``minus``.

    ``P @ row`` is just two columns of P, so the gain costs O(N), and only the
    rank-one covariance update is O(N²) - one BLAS call. This is what makes a
    season of ~750 games over ~270 states take well under a second.
    """
    row_update(state, [plus], [minus], y, r)


def row_update(state: State, plus: list[int], minus: list[int], y: float, r: float) -> None:
    """Scalar Kalman update for a row with +1 at each of ``plus`` and -1 at each of ``minus``.

    The general form of :func:`_sparse_update`: a home team's points are its
    offence plus its quarterback plus the home advantage minus the opposing
    defence, and every term is a column of P.
    """
    P = state.P
    Ph = P[:, plus].sum(axis=1) - (P[:, minus].sum(axis=1) if minus else 0.0)
    s = float(Ph[plus].sum() - Ph[minus].sum()) + r
    k = Ph / s
    innovation = y - float(state.x[plus].sum() - state.x[minus].sum())
    state.x += k * innovation
    joseph(P, k, Ph, s)


def joseph(P: np.ndarray, k: np.ndarray, Ph: np.ndarray, s: float) -> None:
    """The Joseph-form covariance update for a scalar observation. In place.

    ``P+ = (I - k h') P (I - k h')' + r k k'``, expanded for a sparse row so
    it stays O(N²). With ``v = P h`` and the innovation variance
    ``s = h' P h + r``:

        P+ = P - (k v' + v k') + s k k'

    The textbook ``P - k v'`` is the same matrix in exact arithmetic, but it
    is not symmetric by construction, and when an observation is much sharper
    than the state (a small ``r``, as in the quarterback EPA channel) its
    rounding can leave P with a negative eigenvalue. Every term here is
    symmetric by construction, and the form stays positive semi-definite for
    any gain, the optimal one included.
    """
    # c + c' = k v' + v k' - s k k', summed before it touches P so both
    # triangles take the same rounding.
    c = np.outer(k, Ph - 0.5 * s * k)
    c += c.T
    P -= c


def row_forecast(state: State, plus: list[int], minus: list[int]) -> tuple[float, float]:
    """Mean and variance of ``sum(x[plus]) - sum(x[minus])`` under the state."""
    idx = np.array([*plus, *minus])
    sign = np.r_[np.ones(len(plus)), -np.ones(len(minus))]
    sub = state.P[np.ix_(idx, idx)]
    return float(state.x[plus].sum() - state.x[minus].sum()), float(sign @ sub @ sign)


def update(state: State, home, away, home_pts: float, away_pts: float, is_home: float,
           spec: Spec) -> None:
    """Assimilate one game's two point totals. In place."""
    n = state.n
    h, a = state.index[home], state.index[away]
    pair_update(state, ([h], [n + a]), ([a], [n + h]), home_pts - spec.base - spec.boost * is_home,
                away_pts - spec.base, spec.sigma ** 2, spec.rho)


def effective_weeks(games: pd.DataFrame, state: State | None = None) -> np.ndarray:
    """Week numbers that only ever move forward through a season.

    Postseason weeks restart at 1, which would read as the state going back
    in time and add no process noise across the month before the bowls. A
    postseason game is placed after the last regular-season week by the
    whole weeks elapsed since the last regular-season kickoff - or, when
    ``games`` holds no regular-season game, since the ``state``'s own last
    kickoff (a projection of the bowls from a state carried to December).
    """
    weeks = games["week"].to_numpy(dtype=int).copy()
    if "season_type" not in games:
        return weeks
    post = (games["season_type"] == "postseason").to_numpy()
    if not post.any():
        return weeks
    kick = pd.to_datetime(games["kickoff"], utc=True, errors="coerce")
    if (~post).any():
        last_week, last_kick = int(weeks[~post].max()), kick[~post].max()
    elif state is not None and state.week is not None and state.kickoff is not None:
        last_week, last_kick = int(state.week), state.kickoff
    else:
        return weeks
    days = (kick[post] - last_kick).dt.days.fillna(7).to_numpy()
    weeks[post] = last_week + np.maximum(1, np.ceil(days / 7.0)).astype(int)
    return weeks


def kickoff_groups(kickoffs) -> list[np.ndarray]:
    """Positions of each run of equal kickoffs, in order. Games at the same
    kickoff cannot see each other's results, so each run is forecast before
    any of it is assimilated."""
    keys = pd.Series(kickoffs).astype(str).to_numpy()
    if len(keys) == 0:
        return []
    starts = np.r_[0, np.flatnonzero(keys[1:] != keys[:-1]) + 1, len(keys)]
    return [np.arange(s, e) for s, e in zip(starts[:-1], starts[1:], strict=True)]


def run_season(games: pd.DataFrame, state: State, spec: Spec) -> pd.DataFrame:
    """Forecast every game before it is played, then learn from it.

    ``games`` must carry ``home_team_id``, ``away_team_id``, ``week``,
    ``kickoff``, ``actual_margin``, ``actual_total``, ``neutral_site``. Rows
    are processed in kickoff order; process noise is added whenever the week
    advances. Returns one row per game with the pre-kickoff forecast. A game
    without a result is forecast and not assimilated.
    """
    g = games.sort_values(["kickoff", "week"])
    idx = g.index.to_numpy()
    weeks = effective_weeks(g, state)
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
    tsds = np.full(len(g), np.nan)
    known = state.index
    for group in kickoff_groups(g["kickoff"].to_numpy()):
        week = int(weeks[group].max())
        if state.week is None:
            state.week = week
        elif week > state.week:
            advance(state, week - state.week, spec)
            state.week = week
        state.kickoff = pd.to_datetime(g["kickoff"].iloc[group[0]], utc=True, errors="coerce")
        played = [i for i in group if homes[i] in known and aways[i] in known]
        for i in played:
            means[i], sds[i], hps[i], aps[i] = forecast(state, homes[i], aways[i],
                                                        0.0 if neutral[i] else 1.0, spec)
            tsds[i] = total_sd(state, homes[i], aways[i], spec)
        for i in played:
            m, t = margins[i], totals[i]
            if np.isnan(m) or np.isnan(t):
                continue
            update(state, homes[i], aways[i], (t + m) / 2.0, (t - m) / 2.0,
                   0.0 if neutral[i] else 1.0, spec)
    out = pd.DataFrame({"mean": means, "sd": sds, "home_pts": hps, "away_pts": aps, "total_sd": tsds},
                       index=idx)
    return out.reindex(games.index)


#: Bounds on the fitted noise correlation. Pace pushes it up; a negative one
#: (one team scoring at the other's expense beyond the margin) is allowed but
#: implausible past -0.5, and past 0.8 the margin's noise would all but vanish.
RHO_BOUNDS = (-0.5, 0.8)


def noise_correlation(forecasts: pd.DataFrame, margins: np.ndarray, totals: np.ndarray,
                      spec: Spec) -> float:
    """The correlation between the two teams' point noise, from one-step forecasts.

    ``forecasts`` are :func:`run_season`'s rows (``mean``, ``sd``,
    ``home_pts``, ``away_pts``, ``total_sd``) made under ``spec``. Each
    residual's variance is the state's own uncertainty plus the noise; taking
    the state's part out leaves ``2 sigma² (1 - rho)`` on the margin and
    ``2 sigma² (1 + rho)`` on the total, whose ratio is rho whatever sigma is.
    """
    f = forecasts
    ok = f["mean"].notna() & f["total_sd"].notna() & np.isfinite(margins) & np.isfinite(totals)
    if ok.sum() < 30:
        return 0.0
    rm = (margins - f["mean"].to_numpy(dtype=float))[ok.to_numpy()]
    rt = (totals - (f["home_pts"] + f["away_pts"]).to_numpy(dtype=float))[ok.to_numpy()]
    state_m = f["sd"].to_numpy(dtype=float)[ok.to_numpy()] ** 2 - spec.margin_noise
    state_t = f["total_sd"].to_numpy(dtype=float)[ok.to_numpy()] ** 2 - spec.total_noise
    noise_m = float(np.var(rm) - state_m.mean())
    noise_t = float(np.var(rt) - state_t.mean())
    if noise_m <= 0 or noise_t <= 0:
        return 0.0
    return float(np.clip((noise_t - noise_m) / (noise_t + noise_m), *RHO_BOUNDS))


def with_correlation(spec: Spec, rho: float) -> Spec:
    """``spec`` with noise correlation ``rho``, its margin noise unchanged.

    The margin's noise is what the tuning measured; holding it fixed while
    rho moves means the correlation only changes what the filter believes
    about totals and how it splits a result between the two sides.
    """
    from dataclasses import replace

    sigma = spec.sigma * np.sqrt((1.0 - spec.rho) / (1.0 - rho))
    return replace(spec, sigma=float(sigma), rho=float(rho))
