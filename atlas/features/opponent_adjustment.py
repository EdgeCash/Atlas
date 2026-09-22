"""Opponent-adjusted efficiency.

Every efficiency number in Phase 1A was a raw average: a team's EPA per play
was whatever it happened to produce, against whoever it happened to play. That
conflates being good with playing badly-defended opponents. SP+ and FPI both
adjust for this, and Phase 1A found they beat raw efficiency, so Phase 1B asks
how much of that gap is recovered by doing the same.

The model
--------

Every metric is treated as one *stream* of observations in which an **actor**
produces a value against an **opponent**:

    value = mu + actor_effect + opponent_effect + hfa * (home - 0.5)

For EPA the actor is the offense and the opponent is the defense, so the fit
yields both ``adj_off_epa`` (what a team produces against an average defence)
and ``adj_def_epa`` (what a team allows to an average offence). For havoc the
roles are reversed - the defence is the actor - and the same solve produces
havoc generated and havoc allowed.

Three methods, as specified
---------------------------

``simple`` (Method A)
    One pass. Subtract each opponent's raw average from every observation,
    then average. Cheap, transparent, and it under-corrects: the opponent
    averages it subtracts are themselves unadjusted.
``iterative`` (Method B)
    Alternate between solving actor effects given opponent effects and the
    reverse, until nothing moves. This is Gauss-Seidel on the additive model,
    and it is what "schedule strength" iteration means in practice.
``network`` (Method C)
    Solve the whole connected system at once by ridge least squares - the
    Massey/SRS construction. Handles unbalanced schedules and disconnected
    corners of the graph in one step rather than by iterating toward them.

All three shrink toward a **prior**: the previous season's final ratings,
falling back to the league average. That is what makes a week-1 rating usable
without looking forward, and it is the same device Phase 1A used for raw
metrics, so raw and adjusted are compared on equal footing.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from atlas.util import get_logger

LOG = get_logger(__name__)

METHODS = ("simple", "iterative", "network")

#: Ridge weight, in units of "equivalent games". A team with this many games
#: played is pulled halfway back toward its prior.
DEFAULT_RIDGE = 4.0

#: Gauss-Seidel stopping rule.
MAX_ITERATIONS = 100
TOLERANCE = 1e-7


@dataclass(frozen=True)
class Prior:
    """Centred actor/opponent effects carried in from the previous season."""

    actor: dict[int, float] = field(default_factory=dict)
    opponent: dict[int, float] = field(default_factory=dict)
    league_mean: float = 0.0
    hfa: float = 0.0

    def is_empty(self) -> bool:
        return not self.actor and not self.opponent


@dataclass(frozen=True)
class Adjustment:
    """Result of one fit: ratings on the metric's own scale."""

    ratings: pd.DataFrame  # team_id, actor_rating, opponent_rating
    league_mean: float
    hfa: float
    iterations: int
    converged: bool
    n_observations: int

    def to_prior(self) -> Prior:
        centred_actor = dict(
            zip(self.ratings["team_id"], self.ratings["actor_rating"] - self.league_mean,
                strict=False)
        )
        centred_opponent = dict(
            zip(self.ratings["team_id"], self.ratings["opponent_rating"] - self.league_mean,
                strict=False)
        )
        return Prior(centred_actor, centred_opponent, self.league_mean, self.hfa)


# ---------------------------------------------------------------------------
# Fitting
# ---------------------------------------------------------------------------


def fit(
    obs: pd.DataFrame,
    *,
    method: str = "network",
    ridge: float = DEFAULT_RIDGE,
    prior: Prior | None = None,
) -> Adjustment:
    """Fit one metric stream.

    ``obs`` needs ``team_id`` (the actor), ``opponent_id``, ``value``, and
    optionally ``is_home`` and ``weight``.
    """
    if method not in METHODS:
        raise ValueError(f"unknown method {method!r}; expected one of {METHODS}")
    prior = prior or Prior()

    frame = obs.dropna(subset=["value"]).copy()
    teams = _team_index(frame, prior)
    if frame.empty or not teams:
        return _prior_only(teams, prior)

    league_mean = float(np.average(frame["value"], weights=_weights(frame)))
    hfa = _estimate_hfa(frame)
    home = frame["is_home"].astype(float).to_numpy() if "is_home" in frame else np.full(len(frame), 0.5)
    z = frame["value"].to_numpy(dtype=float) - league_mean - hfa * (home - 0.5)

    actor_idx = frame["team_id"].map(teams).to_numpy()
    opp_idx = frame["opponent_id"].map(teams).to_numpy()
    weights = _weights(frame)

    prior_actor = np.array([prior.actor.get(t, 0.0) for t in teams], dtype=float)
    prior_opponent = np.array([prior.opponent.get(t, 0.0) for t in teams], dtype=float)

    if method == "simple":
        a, d, iters, converged = _fit_simple(
            z, actor_idx, opp_idx, weights, len(teams), ridge, prior_actor, prior_opponent
        )
    elif method == "iterative":
        a, d, iters, converged = _fit_iterative(
            z, actor_idx, opp_idx, weights, len(teams), ridge, prior_actor, prior_opponent
        )
    else:
        a, d, iters, converged = _fit_network(
            z, actor_idx, opp_idx, weights, len(teams), ridge, prior_actor, prior_opponent
        )

    ratings = pd.DataFrame(
        {
            "team_id": list(teams),
            "actor_rating": league_mean + a,
            "opponent_rating": league_mean + d,
        }
    )
    return Adjustment(ratings, league_mean, hfa, iters, converged, len(frame))


def _team_index(frame: pd.DataFrame, prior: Prior) -> dict[int, int]:
    ids = set()
    if not frame.empty:
        ids |= set(frame["team_id"].astype("int64"))
        ids |= set(frame["opponent_id"].astype("int64"))
    ids |= set(prior.actor) | set(prior.opponent)
    return {team: i for i, team in enumerate(sorted(ids))}


def _weights(frame: pd.DataFrame) -> np.ndarray:
    """Observation weights, normalised so the mean game weighs exactly 1.

    Weighting by play count is right - a 40-play game says less than an
    80-play one - but the raw counts would silently rescale ``ridge``. Since
    ridge is specified in *games*, and a game carries ~56 plays, leaving the
    counts unnormalised would shrink a week-1 rating by 0.07 games instead of
    4 and hand back a wildly noisy rating. Normalising keeps ridge in the same
    units as the raw features' shrinkage, which is also what makes the
    raw-versus-adjusted comparison fair.
    """
    if "weight" not in frame:
        return np.ones(len(frame))
    w = pd.to_numeric(frame["weight"], errors="coerce").to_numpy(dtype=float)
    w = np.nan_to_num(w, nan=0.0, posinf=0.0, neginf=0.0)
    w = np.where(w > 0, w, np.nan)
    mean = np.nanmean(w) if np.isfinite(w).any() else 1.0
    if not np.isfinite(mean) or mean <= 0:
        return np.ones(len(frame))
    return np.nan_to_num(w / mean, nan=1.0)


def _estimate_hfa(frame: pd.DataFrame) -> float:
    """Home advantage on this metric, as a plain difference of means."""
    if "is_home" not in frame:
        return 0.0
    home = frame.loc[frame["is_home"].astype(bool), "value"]
    away = frame.loc[~frame["is_home"].astype(bool), "value"]
    if len(home) < 20 or len(away) < 20:
        return 0.0
    return float(home.mean() - away.mean())


def _prior_only(teams: dict[int, int], prior: Prior) -> Adjustment:
    """No games yet: the rating *is* the prior. This is what keeps week 1 honest."""
    ratings = pd.DataFrame(
        {
            "team_id": list(teams),
            "actor_rating": [prior.league_mean + prior.actor.get(t, 0.0) for t in teams],
            "opponent_rating": [prior.league_mean + prior.opponent.get(t, 0.0) for t in teams],
        }
    )
    return Adjustment(ratings, prior.league_mean, prior.hfa, 0, True, 0)


def _group_sums(values: np.ndarray, idx: np.ndarray, size: int) -> np.ndarray:
    out = np.zeros(size)
    np.add.at(out, idx, values)
    return out


def _fit_simple(z, actor_idx, opp_idx, w, n_teams, ridge, prior_a, prior_d):
    """Method A: subtract each opponent's raw average, then average."""
    actor_w = _group_sums(w, actor_idx, n_teams)
    opp_w = _group_sums(w, opp_idx, n_teams)

    raw_actor = _group_sums(w * z, actor_idx, n_teams) / np.maximum(actor_w, 1e-9)
    raw_opp = _group_sums(w * z, opp_idx, n_teams) / np.maximum(opp_w, 1e-9)
    raw_actor = np.where(actor_w > 0, raw_actor, prior_a)
    raw_opp = np.where(opp_w > 0, raw_opp, prior_d)

    a = (_group_sums(w * (z - raw_opp[opp_idx]), actor_idx, n_teams) + ridge * prior_a) / (
        actor_w + ridge
    )
    d = (_group_sums(w * (z - raw_actor[actor_idx]), opp_idx, n_teams) + ridge * prior_d) / (
        opp_w + ridge
    )
    return a, d, 1, True


def _fit_iterative(z, actor_idx, opp_idx, w, n_teams, ridge, prior_a, prior_d):
    """Method B: alternate actor and opponent solves until nothing moves."""
    actor_w = _group_sums(w, actor_idx, n_teams)
    opp_w = _group_sums(w, opp_idx, n_teams)
    a = prior_a.copy()
    d = prior_d.copy()

    for iteration in range(1, MAX_ITERATIONS + 1):
        new_a = (_group_sums(w * (z - d[opp_idx]), actor_idx, n_teams) + ridge * prior_a) / (
            actor_w + ridge
        )
        new_d = (_group_sums(w * (z - new_a[actor_idx]), opp_idx, n_teams) + ridge * prior_d) / (
            opp_w + ridge
        )
        shift = max(np.abs(new_a - a).max(), np.abs(new_d - d).max())
        a, d = new_a, new_d
        if shift < TOLERANCE:
            return a, d, iteration, True
    return a, d, MAX_ITERATIONS, False


def _fit_network(z, actor_idx, opp_idx, w, n_teams, ridge, prior_a, prior_d):
    """Method C: one ridge least-squares solve over the whole schedule graph.

    Minimises ``sum w (z - a_actor - d_opponent)^2 + ridge * ||b - prior||^2``.
    The penalty toward the prior is what makes an under-determined corner of
    the schedule graph resolve to last season rather than to nonsense.
    """
    size = 2 * n_teams
    xtx = np.zeros((size, size))
    xtz = np.zeros(size)

    off = opp_idx + n_teams
    np.add.at(xtx, (actor_idx, actor_idx), w)
    np.add.at(xtx, (off, off), w)
    np.add.at(xtx, (actor_idx, off), w)
    np.add.at(xtx, (off, actor_idx), w)
    np.add.at(xtz, actor_idx, w * z)
    np.add.at(xtz, off, w * z)

    prior_b = np.concatenate([prior_a, prior_d])
    lhs = xtx + ridge * np.eye(size)
    rhs = xtz + ridge * prior_b
    try:
        b = np.linalg.solve(lhs, rhs)
    except np.linalg.LinAlgError:  # pragma: no cover - ridge makes this ~impossible
        b = np.linalg.lstsq(lhs, rhs, rcond=None)[0]
    return b[:n_teams], b[n_teams:], 1, True


# ---------------------------------------------------------------------------
# Point-in-time application
# ---------------------------------------------------------------------------


def point_in_time_ratings(
    obs: pd.DataFrame,
    *,
    method: str = "network",
    ridge: float = DEFAULT_RIDGE,
    extra_weeks: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Ratings as they stood before each week of each season.

    For season *S* week *w* the fit uses only games from season *S* played in
    weeks strictly before *w*, shrunk toward season *S-1*'s final ratings.
    Week boundaries are the unit of time because every game in a week can
    kick off before any other - solving per week cannot see sideways.

    ``extra_weeks`` (columns ``season``, ``week``) asks for a rating row at
    weeks that carry no observations of their own - which is what a week whose
    games have not kicked off yet looks like. The fit is identical: strictly
    prior weeks only. It is used by the live tracker and left unset by the
    research build, whose weeks all contain played games.

    Returns one row per (season, week, team_id).
    """
    required = {"season", "week", "team_id", "opponent_id", "value"}
    missing = required - set(obs.columns)
    if missing:
        raise KeyError(f"observations missing columns: {sorted(missing)}")

    wanted: dict[int, set[int]] = {}
    if extra_weeks is not None and not extra_weeks.empty:
        for season, week in extra_weeks[["season", "week"]].drop_duplicates().to_numpy():
            wanted.setdefault(int(season), set()).add(int(week))

    frames = []
    prior = Prior()
    for season in sorted(set(obs["season"].unique()) | set(wanted)):
        season_obs = obs[obs["season"] == season]
        weeks = sorted(set(season_obs["week"].unique()) | wanted.get(int(season), set()))
        for week in weeks:
            window = season_obs[season_obs["week"] < week]
            result = fit(window, method=method, ridge=ridge, prior=prior)
            block = result.ratings.copy()
            block["season"] = season
            block["week"] = week
            block["n_prior_observations"] = result.n_observations
            frames.append(block)
        if season_obs.empty:
            continue
        # End-of-season fit becomes next season's prior, trimmed to teams that
        # actually played. Without the trim the team index grows every season
        # and the network solve slows to a crawl on teams that no longer exist.
        final = fit(season_obs, method=method, ridge=ridge, prior=prior)
        active = set(season_obs["team_id"]) | set(season_obs["opponent_id"])
        prior = _trim(final.to_prior(), active)

    if not frames:
        return pd.DataFrame(
            columns=["season", "week", "team_id", "actor_rating", "opponent_rating",
                     "n_prior_observations"]
        )
    out = pd.concat(frames, ignore_index=True)
    return out[["season", "week", "team_id", "actor_rating", "opponent_rating",
                "n_prior_observations"]]


def _trim(prior: Prior, keep: set[int]) -> Prior:
    return Prior(
        {t: v for t, v in prior.actor.items() if t in keep},
        {t: v for t, v in prior.opponent.items() if t in keep},
        prior.league_mean,
        prior.hfa,
    )


def schedule_strength(obs: pd.DataFrame, ratings: pd.DataFrame) -> pd.DataFrame:
    """Average opponent rating faced, per team-season.

    This is the quantity the whole phase is about: if schedules were balanced,
    adjustment could not matter.
    """
    final = ratings.sort_values(["season", "week"]).groupby(["season", "team_id"]).last()
    final = final.reset_index()[["season", "team_id", "opponent_rating"]]
    faced = obs.merge(
        final.rename(columns={"team_id": "opponent_id", "opponent_rating": "faced_rating"}),
        on=["season", "opponent_id"],
        how="left",
    )
    return (
        faced.groupby(["season", "team_id"])
        .agg(opponents=("faced_rating", "size"), mean_opponent_rating=("faced_rating", "mean"))
        .reset_index()
    )
