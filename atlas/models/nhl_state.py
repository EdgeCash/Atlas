"""The NHL state: each team's expected goals at 5-on-5 and on special teams, each goalie's goals saved.

    (run and scored end to end by `python -m atlas.models.nhl_model`)

Steps 3 and 4 of `docs/MODEL_PLAN_NHL.md`. Three filters, walked forward
day by day through every game since 2010-11, each state carried across
seasons:

* **5-on-5** - for every team ``off`` (expected goals for per 60 minutes at
  5-on-5, above the league) and ``def`` (expected goals against per 60
  prevented), jointly, with a full covariance: the opponent adjustment. Each
  game is two observations, one per side: that side's 5-on-5 expected goals
  over its 5-on-5 time, noise shrinking as the time grows. The home side's
  rate carries a fitted home term.
* **Special teams** - ``pp`` and ``pk`` alike, from power-play time.
* **The goalie** - each goalie's goals saved above expected per 60 minutes at
  the league's shot volume, a filter of one, carried across teams and
  seasons and shrunk hard (its reliability is 0.31): every game a goalie
  plays is an observation of expected goals faced minus goals allowed.

Expected goals are the model's (`atlas/models/nhl_xg.py`) scaled to the
league's goals: the ratio of goals to expected goals over the season before
and this one so far, so the state is in goals whatever the scoring year.

Between seasons every team state is carried at ``phi`` of itself plus fresh
variance, a goalie's at ``phi_goalie``. Within a season a slow random walk.

**A game's expected goals** (regulation, net of the empty net, for each
side) are the league's rate in each state plus the teams' terms, times the
time each state is expected to take - 5-on-5 from the league's share, the
power play from both teams' penalty rates - less the expected starter's
goals saved, and a back-to-back term fitted on the training seasons. The
expected starter is each of the team's goalies weighted by recent starts,
with a goalie who started the night before marked down. When the starter
is confirmed the price is re-read with that goalie.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from atlas.util import get_logger

LOG = get_logger(__name__)

TUNE = range(2017, 2020)
REPORT_FROM = 2020
VERSION = "nhl-state-v1"
HOUR = 3600.0
#: Starts over which a goalie's share of a team's starts is read (exponential weight).
START_WEIGHT = 0.12


@dataclass(frozen=True)
class Spec:
    q5: float = 0.0004          # daily process variance of a team's 5-on-5 terms, (goals / 60)^2
    q_st: float = 0.0015        # daily process variance of power play and penalty kill
    q_g: float = 0.0002         # daily process variance of a goalie
    p0_5: float = 0.06          # prior variance, a team new to the league
    p0_st: float = 0.5
    p0_g: float = 0.03
    phi: float = 0.7            # share of a team's state carried over a summer
    phi_g: float = 0.6
    season_var5: float = 0.02   # fresh variance each summer
    season_var_st: float = 0.2
    season_var_g: float = 0.01
    r5: float = 0.9             # noise variance of one hour of 5-on-5 expected goals, per team
    r_st: float = 2.5           # of one hour of power-play expected goals
    r_g: float = 1.1            # of one hour of a goalie's goals saved above expected
    b2b_starter: float = 0.3    # a goalie who started last night: his start weight times this
    blend: float = 1.0          # the observation: this share expected goals, the rest unblocked attempts at the league's rate
    q_f: float = 0.0002         # daily process variance of a team's finishing
    p0_f: float = 0.02          # prior variance of finishing
    season_var_f: float = 0.01
    r_f: float = 2.5            # noise of one hour of goals over expected goals, all situations


@dataclass
class Filter:
    """A block of the state: means, covariance and the index of each key."""

    x: np.ndarray
    P: np.ndarray
    index: dict

    @classmethod
    def empty(cls) -> Filter:
        return cls(np.zeros(0), np.zeros((0, 0)), {})

    def add(self, key, variance: float) -> int:
        k = len(self.x)
        self.x = np.append(self.x, 0.0)
        P = np.zeros((k + 1, k + 1))
        P[:k, :k] = self.P
        P[k, k] = variance
        self.P = P
        self.index[key] = k
        return k

    def ensure(self, key, variance: float) -> int:
        return self.index[key] if key in self.index else self.add(key, variance)

    def update(self, idx: list[int], coef: list[float], y: float, r: float) -> None:
        """Scalar observation ``y = sum(coef * x[idx]) + e``, ``e`` of variance ``r``. Joseph form."""
        idx = np.asarray(idx)
        c = np.asarray(coef, float)
        Ph = self.P[:, idx] @ c
        s = float(c @ Ph[idx]) + r
        k = Ph / s
        self.x = self.x + k * (y - float(c @ self.x[idx]))
        corr = np.outer(k, Ph - 0.5 * s * k)
        self.P -= corr + corr.T

    def mean_var(self, idx: list[int], coef: list[float]) -> tuple[float, float]:
        idx = np.asarray(idx)
        c = np.asarray(coef, float)
        return float(c @ self.x[idx]), float(c @ self.P[np.ix_(idx, idx)] @ c)


#: Each league rate as (numerator, denominator) of a team-game row, both exponentially weighted: a
#: ratio of weighted sums, never a weighted mean of per-game ratios, which runs high (a game with little
#: power-play time and one goal is a huge rate).
RATES = {
    "rate5": ("goals_5v5", "h_5v5"),              # 5-on-5 goals per 60, per team
    "rate_pp": ("goals_PP", "h_PP"),              # power-play goals per 60
    "rate_sh": ("goals_SH", "h_opp_PP"),          # short-handed goals per 60 of the other side's power play
    "rate_ev": ("goals_EV", "h_EV"),              # other even strength (4-on-4, 3-on-3)
    "share5": ("h_5v5", "reg_hours"),             # share of regulation at 5-on-5
    "share_ev": ("h_EV", "reg_hours"),
    "fen5": ("goals_5v5", "fenwick_5v5"),         # goals per unblocked attempt at 5-on-5
    "fen_pp": ("goals_PP", "fenwick_PP"),
    "pp_per_pen": ("min_PP", "drawn"),            # power-play minutes per penalty drawn
    "pens": ("penalties", "one"),                 # penalties per team-game
    "kappa": ("goals_all", "xg_all"),             # goals per expected goal
    "fen60": ("fenwicka_all", "hours"),           # unblocked attempts faced per 60 minutes
}
PRIORS = {"rate5": 2.4, "rate_pp": 6.5, "rate_sh": 0.8, "rate_ev": 3.5, "share5": 0.80, "share_ev": 0.02,
          "fen5": 0.058, "fen_pp": 0.095, "pp_per_pen": 1.55, "pens": 3.2, "kappa": 1.0, "fen60": 40.0}


@dataclass
class League:
    """Point-in-time league rates, exponentially weighted over recent team-games."""

    num: dict = field(default_factory=lambda: {k: v * 50.0 for k, v in PRIORS.items()})
    den: dict = field(default_factory=lambda: {k: 50.0 for k in PRIORS})

    def __getattr__(self, name):
        if name in RATES:
            d = self.den[name]
            return self.num[name] / d if d > 0 else PRIORS[name]
        raise AttributeError(name)

    def learn(self, row: dict, w: float = 0.004) -> None:
        r = dict(row)
        r.update(h_5v5=row["toi_5v5"] / HOUR, h_PP=row["toi_PP"] / HOUR, h_EV=row["toi_EV"] / HOUR,
                 h_opp_PP=row.get("opp_toi_PP", 0.0) / HOUR, min_PP=row["toi_PP"] / 60.0, one=1.0)
        if r.get("reg_hours") is None:
            r["reg_hours"] = 1.0
        for name, (n, d) in RATES.items():
            num, den = r.get(n), r.get(d)
            if num is None or den is None or not (np.isfinite(num) and np.isfinite(den)):
                continue
            self.num[name] = (1 - w) * self.num[name] + w * num
            self.den[name] = (1 - w) * self.den[name] + w * den


# ---------------------------------------------------------------------------
# The walk
# ---------------------------------------------------------------------------


@dataclass
class Model:
    spec: Spec
    five: Filter
    special: Filter
    goalies: Filter
    finishing: Filter
    league: League
    penalties: dict            # team -> [taken per game, drawn per game], exponentially weighted
    starts: dict               # team -> {goalie: weight}
    last_start: dict           # team -> (date, goalie)
    home5: float = 0.12        # home 5-on-5 expected goals per 60
    b2b: float = -0.15         # goals on the second night of a back-to-back, the team's own
    season: int | None = None
    day: pd.Timestamp | None = None

    @classmethod
    def new(cls, spec: Spec) -> Model:
        return cls(spec, Filter.empty(), Filter.empty(), Filter.empty(), Filter.empty(), League(), {}, {}, {})

    # -- time ------------------------------------------------------------------

    def advance(self, day: pd.Timestamp, season: int) -> None:
        s = self.spec
        if self.season is not None and season != self.season:
            self._summer()
        if self.day is not None and season == self.season:
            days = max((day - self.day).days, 0)
            if days:
                self.five.P[np.diag_indices_from(self.five.P)] += s.q5 * days
                self.special.P[np.diag_indices_from(self.special.P)] += s.q_st * days
                self.goalies.P[np.diag_indices_from(self.goalies.P)] += s.q_g * days
                self.finishing.P[np.diag_indices_from(self.finishing.P)] += s.q_f * days
        self.season, self.day = season, day

    def _summer(self) -> None:
        s = self.spec
        for f, phi, var in ((self.five, s.phi, s.season_var5), (self.special, s.phi, s.season_var_st),
                            (self.goalies, s.phi_g, s.season_var_g), (self.finishing, s.phi_g, s.season_var_f)):
            f.x = phi * f.x
            f.P = phi ** 2 * f.P
            f.P[np.diag_indices_from(f.P)] += var
        self.starts = {t: {g: w * 0.5 for g, w in d.items()} for t, d in self.starts.items()}

    def _team(self, team) -> tuple[int, int, int, int]:
        s = self.spec
        return (self.five.ensure(("off", team), s.p0_5), self.five.ensure(("def", team), s.p0_5),
                self.special.ensure(("pp", team), s.p0_st), self.special.ensure(("pk", team), s.p0_st))

    # -- the expected starter ------------------------------------------------------

    def starter_probs(self, team, day: pd.Timestamp) -> dict:
        weights = dict(self.starts.get(team, {}))
        if not weights:
            return {}
        last = self.last_start.get(team)
        if last is not None and (day - last[0]).days == 1 and last[1] in weights:
            weights[last[1]] *= self.spec.b2b_starter
        total = sum(weights.values())
        return {g: w / total for g, w in weights.items()} if total > 0 else {}

    def goalie_effect(self, team, day: pd.Timestamp, starter=None) -> tuple[float, float]:
        """Goals saved per 60 by the team's goalie: the confirmed starter's, else the expectation."""
        probs = {starter: 1.0} if starter is not None and not pd.isna(starter) else self.starter_probs(team, day)
        mean = var = 0.0
        for g, p in probs.items():
            if g in self.goalies.index:
                k = self.goalies.index[g]
                mean += p * self.goalies.x[k]
                var += p * (self.goalies.P[k, k] + self.goalies.x[k] ** 2)
            else:
                var += p * self.spec.p0_g
        return mean, max(var - mean ** 2, 0.0)

    # -- a game's expected goals ----------------------------------------------------

    def rate(self, team) -> tuple[float, float]:
        pen = self.penalties.get(team)
        return (pen[0], pen[1]) if pen else (self.league.pens, self.league.pens)

    def expect(self, home, away, day, *, home_b2b=False, away_b2b=False, home_starter=None, away_starter=None) -> dict:
        """Expected regulation goals (empty net aside) for each side, and their variances from the state."""
        lg = self.league
        oh, dh, pph, pkh = self._team(home)
        oa, da, ppa, pka = self._team(away)
        t5 = lg.share5
        tev = lg.share_ev
        taken_h, drawn_h = self.rate(home)
        taken_a, drawn_a = self.rate(away)
        pp_h = (drawn_h + taken_a) / 2.0 * lg.pp_per_pen / 60.0        # hours of home power play
        pp_a = (drawn_a + taken_h) / 2.0 * lg.pp_per_pen / 60.0
        g_h, gv_h = self.goalie_effect(home, day, home_starter)
        g_a, gv_a = self.goalie_effect(away, day, away_starter)
        kh, ka = self.finishing.ensure(home, self.spec.p0_f), self.finishing.ensure(away, self.spec.p0_f)
        fh, fa = self.finishing.x[kh], self.finishing.x[ka]
        m5h, v5h = self.five.mean_var([oh, da], [t5, -t5])
        m5a, v5a = self.five.mean_var([oa, dh], [t5, -t5])
        msh, vsh = self.special.mean_var([pph, pka], [pp_h, -pp_h])
        msa, vsa = self.special.mean_var([ppa, pkh], [pp_a, -pp_a])
        lam_h = (lg.rate5 + self.home5) * t5 + m5h + lg.rate_pp * pp_h + msh + lg.rate_sh * pp_a + lg.rate_ev * tev \
            - g_a + fh + (self.b2b if home_b2b else 0.0)
        lam_a = lg.rate5 * t5 + m5a + lg.rate_pp * pp_a + msa + lg.rate_sh * pp_h + lg.rate_ev * tev \
            - g_h + fa + (self.b2b if away_b2b else 0.0)
        return {"lambda_home": max(lam_h, 0.3), "lambda_away": max(lam_a, 0.3), "home_edge": self.home5 * t5,
                "var_home": v5h + vsh + gv_a, "var_away": v5a + vsa + gv_h,
                "off_home": self.five.x[oh], "def_home": self.five.x[dh], "off_away": self.five.x[oa],
                "def_away": self.five.x[da], "pp_home": self.special.x[pph], "pk_home": self.special.x[pkh],
                "pp_away": self.special.x[ppa], "pk_away": self.special.x[pka], "goalie_home": g_h,
                "goalie_away": g_a, "finish_home": fh, "finish_away": fa}

    # -- learning from a game ---------------------------------------------------------

    def learn(self, game: dict, sides: dict, goalies: list[dict]) -> None:
        """Assimilate one completed game. ``sides`` maps home/away to its team-game row."""
        s, lg = self.spec, self.league
        for side, other in (("home", "away"), ("away", "home")):
            me, them = sides[side], sides[other]
            team, opp = me["team"], them["team"]
            o, _, pp, _ = self._team(team)
            _, d_opp, _, pk_opp = self._team(opp)
            t5 = me["toi_5v5"] / HOUR
            if t5 > 0.1:
                seen = s.blend * lg.kappa * me["xg_5v5"] + (1 - s.blend) * lg.fen5 * me["fenwick_5v5"]
                y = seen - (lg.rate5 + (self.home5 if side == "home" else 0.0)) * t5
                self.five.update([o, d_opp], [t5, -t5], y, s.r5 * t5)
            tpp = me["toi_PP"] / HOUR
            if tpp > 0.02:
                seen = s.blend * lg.kappa * me["xg_PP"] + (1 - s.blend) * lg.fen_pp * me["fenwick_PP"]
                y = seen - lg.rate_pp * tpp
                self.special.update([pp, pk_opp], [tpp, -tpp], y, s.r_st * tpp)
            # Finishing: goals over expected goals, every state but the empty net, per hour played.
            hours = max(me["hours"] - (me["toi_EN"] + me["toi_ENA"]) / HOUR, 0.5)
            scored = me["goals_5v5"] + me["goals_PP"] + me["goals_SH"] + me["goals_EV"]
            expected = lg.kappa * (me["xg_5v5"] + me["xg_PP"] + me["xg_SH"] + me["xg_EV"])
            k = self.finishing.ensure(team, s.p0_f)
            self.finishing.update([k], [hours], scored - expected, s.r_f * hours)
        for g in goalies:
            if not (g["hours"] > 0.2 and np.isfinite(g["xga"])):
                continue
            k = self.goalies.ensure(g["player_id"], s.p0_g)
            vol = g["fenwick"] / max(lg.fen60 * g["hours"], 1.0)          # its shot volume against the league's
            y = lg.kappa * g["xga"] - g["ga"]
            self.goalies.update([k], [g["hours"] * vol], y, s.r_g * g["hours"] * vol)
        for side in ("home", "away"):
            me = sides[side]
            pen = self.penalties.get(me["team"], [lg.pens, lg.pens])
            self.penalties[me["team"]] = [0.95 * pen[0] + 0.05 * me["penalties"], 0.95 * pen[1] + 0.05 * me["drawn"]]
            lg.learn(me)
        for g in goalies:
            if g["started"]:
                w = self.starts.setdefault(g["team"], {})
                for key in w:
                    w[key] *= 1 - START_WEIGHT
                w[g["player_id"]] = w.get(g["player_id"], 0.0) + START_WEIGHT
                self.last_start[g["team"]] = (self.day, g["player_id"])


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------

STRENGTHS = ("5v5", "PP", "SH", "EV", "EN", "ENA")


def sides(team_games: pd.DataFrame) -> pd.DataFrame:
    """The team-game table with the columns the walk reads."""
    t = team_games.copy()
    t["xg_all"] = t[[f"xg_{k}" for k in ("5v5", "PP", "SH", "EV", "ENA")]].sum(axis=1)
    t["goals_all"] = t[[f"goals_{k}" for k in ("5v5", "PP", "SH", "EV", "ENA")]].sum(axis=1)
    t["fenwicka_all"] = t[[f"fenwicka_{k}" for k in STRENGTHS if k != "ENA"]].sum(axis=1)
    t["hours"] = t[[f"toi_{k}" for k in STRENGTHS]].sum(axis=1) / HOUR
    t["reg_hours"] = np.minimum(t["hours"], 1.0)
    return t


def walk(games: pd.DataFrame, team_games: pd.DataFrame, goalie_games: pd.DataFrame, spec: Spec, *,
         confirmed: bool = False, model: Model | None = None, until: pd.Timestamp | None = None) -> tuple[pd.DataFrame, Model]:
    """Forecast every game before it is played, then learn from it; one row per game. ``confirmed``
    prices each game with the goalie who did start (known at warm-ups) rather than the expected one."""
    model = model or Model.new(spec)
    g = games.sort_values(["kickoff", "game_id"]).reset_index(drop=True)
    wanted = set(g["game_id"])
    tgf = sides(team_games[team_games["game_id"].isin(wanted)])
    tg = {(r["game_id"], r["team"]): r for r in tgf.to_dict("records")}
    gg = goalie_games[goalie_games["game_id"].isin(wanted)].copy()
    gg["hours"] = pd.to_numeric(gg["toi"], errors="coerce").fillna(0) / HOUR
    gg["fenwick"] = pd.to_numeric(gg["unblocked_faced"], errors="coerce").fillna(0)
    gg["ga"] = pd.to_numeric(gg["ga_pbp"], errors="coerce").fillna(0)
    gg["xga"] = pd.to_numeric(gg["xga"], errors="coerce")
    by_game: dict = {}
    for r in gg[["game_id", "player_id", "team", "started", "hours", "fenwick", "ga", "xga"]].to_dict("records"):
        by_game.setdefault(r["game_id"], []).append(r)
    starters = {}
    for r in gg[gg["started"] == 1][["game_id", "team", "player_id"]].itertuples(index=False):
        starters.setdefault((r.game_id, r.team), r.player_id)
    days = pd.to_datetime(g["kickoff"], utc=True).dt.tz_convert("America/New_York").dt.normalize()
    rows = []
    for day, part in g.groupby(days, sort=True):
        if until is not None and day > until:
            break
        model.advance(day, int(part["season"].iloc[0]))
        for r in part.itertuples(index=False):
            hs = starters.get((r.game_id, r.home_team)) if confirmed else None
            as_ = starters.get((r.game_id, r.away_team)) if confirmed else None
            e = model.expect(r.home_team, r.away_team, day, home_b2b=bool(r.home_b2b), away_b2b=bool(r.away_b2b),
                             home_starter=hs, away_starter=as_)
            rows.append({"game_id": r.game_id, **e})
        for r in part.itertuples(index=False):
            if not r.completed:
                continue
            if (r.game_id, r.home_team) not in tg or (r.game_id, r.away_team) not in tg:
                continue
            sd = {"home": dict(tg[(r.game_id, r.home_team)]), "away": dict(tg[(r.game_id, r.away_team)])}
            sd["home"]["team"], sd["away"]["team"] = r.home_team, r.away_team
            sd["home"]["opp_toi_PP"], sd["away"]["opp_toi_PP"] = sd["away"]["toi_PP"], sd["home"]["toi_PP"]
            model.learn(r._asdict(), sd, by_game.get(r.game_id, []))
    return pd.DataFrame(rows), model


# ---------------------------------------------------------------------------
# Scoring and tuning
# ---------------------------------------------------------------------------


def poisson_loglik(lam: np.ndarray, k: np.ndarray) -> float:
    from scipy.special import gammaln

    lam = np.clip(lam, 1e-6, None)
    return float(np.mean(k * np.log(lam) - lam - gammaln(k + 1)))


def fit_terms(forecasts: pd.DataFrame, games: pd.DataFrame, seasons) -> tuple[float, float]:
    """The home 5-on-5 term and the back-to-back term, least squares on regulation goals (empty net aside)
    over ``seasons``: what the forecasts' residuals say they should be."""
    f = forecasts.merge(games[["game_id", "season", "reg_home", "reg_away", "home_b2b", "away_b2b"]], on="game_id")
    f = f[f["season"].isin(seasons) & f["reg_home"].notna()]
    home_res = (f["reg_home"] - f["lambda_home"]).mean() - (f["reg_away"] - f["lambda_away"]).mean()
    b2b_rows = pd.concat([(f["reg_home"] - f["lambda_home"])[f["home_b2b"].astype(bool)],
                          (f["reg_away"] - f["lambda_away"])[f["away_b2b"].astype(bool)]])
    rest_rows = pd.concat([(f["reg_home"] - f["lambda_home"])[~f["home_b2b"].astype(bool)],
                           (f["reg_away"] - f["lambda_away"])[~f["away_b2b"].astype(bool)]])
    return float(home_res), float(b2b_rows.mean() - rest_rows.mean())


