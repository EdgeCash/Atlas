"""The NCAAF preseason prior: what a team is worth before it has played.

    python -m atlas.models.ncaaf_prior          # -> reports/ncaaf_prior.md

Step 2 of `docs/MODEL_PLAN_NCAAF.md`. For every FBS team-season, a net,
offensive and defensive strength in points, from facts known before the
season starts - last season's SP+ (overall, offence, defence), last season's
FPI, the 247 talent composite, the recruiting rank, and returning production -
fitted to what teams actually turned out to be, walk-forward.

This is Connelly's SP+ projection recipe ("two-thirds last year's rating,
adjusted by returning production, recruiting and recent history") refit on
Atlas's own data with Atlas's own target. The target is the least-squares
season rating from :mod:`atlas.models.ratings`, so the prior lands in the
same units as the state model it will initialise, and its residual standard
deviation is the state model's starting uncertainty.

The prior is scored at game level in exactly the way the references are, and
it is compared against the single-feature priors it is supposed to improve
on. The benchmarks put prior-season FPI at 9.66 CRPS in weeks 1-2
that is
the number to beat.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from atlas import config
from atlas.models import evaluate, ratings
from atlas.models import lattice as lat
from atlas.models import reference as ref
from atlas.research.dataset import load_research_frame, research_sample
from atlas.util import get_logger

LOG = get_logger(__name__)

FIRST_TEST_SEASON = 2021

#: Preseason facts, as the warehouse names them on a team's side of a game.
#: Every one is known before week 1 and is constant within a team-season.
#: Step 4 added the programme context: the programme's long-run SP+ (the
#: regression is toward *that*, not the league mean), whether the team opens
#: under a new head coach, and the interaction of the two - a new coach's team
#: regresses to the programme harder.
PROGRAMME = ["sp_program_mean", "new_coach", "new_coach_x_overach"]
FEATURES = {
    "net": ["sp_plus", "fpi", "talent", "recruiting_rank", "returning_production", *PROGRAMME],
    "off": ["sp_plus_off", "fpi", "talent", "recruiting_rank", "returning_production", *PROGRAMME],
    "def": ["sp_plus_def", "fpi", "talent", "recruiting_rank", "returning_production", *PROGRAMME],
}
ALL_FEATURES = sorted({f for fs in FEATURES.values() for f in fs})
#: Features computed from staged columns rather than read from the frame:
#: ``name -> (flag, last season, programme mean)``, giving ``flag * (last - mean)``.
DERIVED = {"new_coach_x_overach": ("new_coach", "sp_plus", "sp_program_mean")}
FRAME_FEATURES = [f for f in ALL_FEATURES if f not in DERIVED]

#: Ridge on standardised features. Five features against ~130 teams a season
#: times three or more seasons is not a regime that needs much of it.
RIDGE = 1.0


@dataclass(frozen=True)
class PriorFit:
    """The net prior: ``margin = sum(coef * z_home - coef * z_away) + hfa * home``.

    Fitted directly on training games, not on a season rating. A first
    version regressed on the ridge-shrunk least-squares rating and then used
    the compressed prediction at face value as a margin; it lost 0.6 points
    of MAE to a direct fit of the same features. The game is the target.
    """

    features: list[str]
    mean: np.ndarray            # feature means on training team-seasons (imputation + centring)
    scale: np.ndarray           # feature sds on training team-seasons
    coef: np.ndarray            # points of margin per standardised feature
    intercept: float            # always 0: a margin has no constant but home advantage
    hfa: float
    resid_sd: float             # game-level residual sd on training games, in points
    r2: float
    n: int                      # training games

    def standardise(self, table: pd.DataFrame) -> np.ndarray:
        X = table[self.features].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
        X = np.where(np.isnan(X), self.mean, X)
        return (X - self.mean) / self.scale

    def team_net(self, table: pd.DataFrame) -> np.ndarray:
        """A team's net strength in points: what it adds to a margin."""
        return self.standardise(table) @ self.coef

    def table(self) -> pd.DataFrame:
        t = pd.DataFrame({"feature": self.features, "points_per_sd": self.coef})
        return t.reindex(t["points_per_sd"].abs().sort_values(ascending=False).index).reset_index(drop=True)


@dataclass(frozen=True)
class PointsFit:
    """Off/def priors from one stacked regression on points scored.

    ``pts(scorer vs opponent) = intercept + z_scorer @ off_coef + z_opponent @ def_coef + boost * home``.
    A team's ``off`` is its scorer term; its ``def`` is *minus* its opponent
    term, so positive is points prevented and ``off + def`` is comparable to
    ``net``. Two coefficient blocks, one fit, every game twice.
    """

    off_features: list[str]
    def_features: list[str]
    off_mean: np.ndarray
    off_scale: np.ndarray
    def_mean: np.ndarray
    def_scale: np.ndarray
    off_coef: np.ndarray
    def_coef: np.ndarray
    intercept: float
    boost: float
    resid_sd: float
    r2: float
    n: int

    def _z(self, table: pd.DataFrame, features: list[str], mean: np.ndarray, scale: np.ndarray) -> np.ndarray:
        X = table[features].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
        X = np.where(np.isnan(X), mean, X)
        return (X - mean) / scale

    def team_off(self, table: pd.DataFrame) -> np.ndarray:
        return self._z(table, self.off_features, self.off_mean, self.off_scale) @ self.off_coef

    def team_def(self, table: pd.DataFrame) -> np.ndarray:
        return -(self._z(table, self.def_features, self.def_mean, self.def_scale) @ self.def_coef)

    def table(self, block: str) -> pd.DataFrame:
        feats, coef = ((self.off_features, self.off_coef) if block == "off"
                       else (self.def_features, -self.def_coef))
        t = pd.DataFrame({"feature": feats, "points_per_sd": coef})
        return t.reindex(t["points_per_sd"].abs().sort_values(ascending=False).index).reset_index(drop=True)


@dataclass(frozen=True)
class Prior:
    season: int
    net: PriorFit
    points: PointsFit
    teams: pd.DataFrame          # season, team_id, net, off, def for the target season

    @property
    def hfa(self) -> float:
        return self.net.hfa


# ---------------------------------------------------------------------------
# Team-season tables
# ---------------------------------------------------------------------------


def team_seasons(frame: pd.DataFrame) -> pd.DataFrame:
    """One row per (season, team_id) with every preseason feature.

    Built from the game frame's ``home_*`` / ``away_*`` columns, which are
    staged point-in-time and constant within a team-season, so the same
    number the model would have seen in week 1 is the number here.
    """
    parts = []
    for side in ("home", "away"):
        cols = {f"{side}_{f}": f for f in FRAME_FEATURES if f"{side}_{f}" in frame.columns}
        part = frame[["season", f"{side}_team_id", *cols]].rename(
            columns={f"{side}_team_id": "team_id", **cols})
        parts.append(part)
    long = pd.concat(parts, ignore_index=True)
    out = (long.groupby(["season", "team_id"], as_index=False)[[c for c in FRAME_FEATURES if c in long]]
               .first())
    for name, (flag, last, mean) in DERIVED.items():
        if {flag, last, mean} <= set(out.columns):
            num = {c: pd.to_numeric(out[c], errors="coerce") for c in (flag, last, mean)}
            out[name] = num[flag] * (num[last] - num[mean])
    return out


def season_targets(frame: pd.DataFrame) -> pd.DataFrame:
    """Least-squares net/off/def per team-season, fitted on regular-season games only."""
    out, hfas = [], {}
    for season, g in frame.groupby("season"):
        reg = g[g["season_type"] == "regular"] if "season_type" in g else g
        r = ratings.fit(reg)
        t = r.frame()
        t["season"] = int(season)
        out.append(t)
        hfas[int(season)] = r.hfa
    table = pd.concat(out, ignore_index=True)
    table.attrs["hfa"] = hfas
    return table


# ---------------------------------------------------------------------------
# Fitting
# ---------------------------------------------------------------------------


def _moments(feats: pd.DataFrame, cols: list[str]) -> tuple[np.ndarray, np.ndarray]:
    X = feats[cols].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
    mean = np.nanmean(X, axis=0)
    scale = np.nanstd(X, axis=0)
    return mean, np.where(scale > 0, scale, 1.0)


def _side(games: pd.DataFrame, side: str, feats: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """The preseason feature rows for one side of every game, aligned to the games."""
    key = games[["season", f"{side}_team_id"]].rename(columns={f"{side}_team_id": "team_id"})
    return key.merge(feats[["season", "team_id", *cols]], on=["season", "team_id"], how="left")[cols]


def _ridge_solve(X: np.ndarray, y: np.ndarray, penalise: np.ndarray, ridge: float) -> np.ndarray:
    lhs = X.T @ X + np.diag(penalise * ridge)
    return np.linalg.solve(lhs, X.T @ y)


def _covered(feats: pd.DataFrame, cols: list[str]) -> list[str]:
    return [c for c in cols if c in feats.columns and feats[c].notna().mean() >= 0.5]


def fit(games: pd.DataFrame, feats: pd.DataFrame, *, season: int, ridge: float = RIDGE) -> Prior:
    """Fit the prior for ``season`` on every earlier regular-season game.

    ``games`` is the research frame (any seasons); ``feats`` is
    :func:`team_seasons` over the same. Only rows with ``season < season``
    are used, and only regular-season ones, so bowls never teach the prior.
    """
    train = games[(games["season"] < season)]
    if "season_type" in train:
        train = train[train["season_type"] == "regular"]
    if train["season"].nunique() < 2:
        raise ValueError(f"need at least two training seasons before {season}")
    tf = feats[feats["season"] < season]
    is_home = 1.0 - pd.to_numeric(train.get("neutral_site", 0), errors="coerce").fillna(0).to_numpy(dtype=float)
    margin = train["actual_margin"].to_numpy(dtype=float)
    total = train["actual_total"].to_numpy(dtype=float)

    # --- net: margin on standardised feature differences -------------------
    cols = _covered(tf, FEATURES["net"])
    mean, scale = _moments(tf, cols)
    zh = (np.where(np.isnan(v := _side(train, "home", tf, cols).to_numpy(dtype=float)), mean, v) - mean) / scale
    za = (np.where(np.isnan(v := _side(train, "away", tf, cols).to_numpy(dtype=float)), mean, v) - mean) / scale
    # No free intercept: a margin is antisymmetric in the two teams, so the
    # only constant it can carry is the home advantage, and ``is_home`` is
    # that column. (A separate intercept is exactly collinear with it on any
    # frame without neutral-site games, which the synthetic league is.)
    X = np.column_stack([zh - za, is_home])
    pen = np.r_[np.ones(len(cols)), 0.0]
    beta = _ridge_solve(X, margin, pen, ridge)
    resid = margin - X @ beta
    net = PriorFit(features=cols, mean=mean, scale=scale, coef=beta[:-1], intercept=0.0,
                   hfa=float(beta[-1]), resid_sd=float(np.std(resid, ddof=len(beta))),
                   r2=float(1 - resid.var() / margin.var()), n=int(len(train)))

    # --- off/def: points scored, stacked, scorer block + opponent block -----
    ocols, dcols = _covered(tf, FEATURES["off"]), _covered(tf, FEATURES["def"])
    omean, oscale = _moments(tf, ocols)
    dmean, dscale = _moments(tf, dcols)

    def z(side, cols_, m, sc):
        v = _side(train, side, tf, cols_).to_numpy(dtype=float)
        return (np.where(np.isnan(v), m, v) - m) / sc

    zho, zao = z("home", ocols, omean, oscale), z("away", ocols, omean, oscale)
    zhd, zad = z("home", dcols, dmean, dscale), z("away", dcols, dmean, dscale)
    home_pts, away_pts = (total + margin) / 2.0, (total - margin) / 2.0
    n = len(train)
    Xs = np.vstack([
        np.column_stack([np.ones(n), zho, zad, is_home]),        # home scoring vs away defence
        np.column_stack([np.ones(n), zao, zhd, np.zeros(n)]),    # away scoring vs home defence
    ])
    ys = np.r_[home_pts, away_pts]
    pen = np.r_[0.0, np.ones(len(ocols) + len(dcols)), 0.0]
    b = _ridge_solve(Xs, ys, pen, ridge)
    resid = ys - Xs @ b
    points = PointsFit(off_features=ocols, def_features=dcols, off_mean=omean, off_scale=oscale,
                       def_mean=dmean, def_scale=dscale, off_coef=b[1:1 + len(ocols)],
                       def_coef=b[1 + len(ocols):-1], intercept=float(b[0]), boost=float(b[-1]),
                       resid_sd=float(np.std(resid, ddof=len(b))), r2=float(1 - resid.var() / ys.var()),
                       n=int(len(ys)))

    return Prior(season=season, net=net, points=points, teams=team_table(net, points, feats, season))


def team_table(net: PriorFit, points: PointsFit, feats: pd.DataFrame, season: int) -> pd.DataFrame:
    rows = feats[feats["season"] == season]
    out = rows[["season", "team_id"]].copy()
    out["net"] = net.team_net(rows)
    out["off"] = points.team_off(rows)
    out["def"] = points.team_def(rows)
    return out.reset_index(drop=True)


def game_forecast(prior: Prior, test: pd.DataFrame, sigma: float | None = None,
                  name: str = "prior") -> ref.Forecast:
    """Home margin = net_home - net_away + hfa (0 at a neutral site)."""
    home = _lookup(prior.teams, test, "home")
    away = _lookup(prior.teams, test, "away")
    is_home = 1.0 - pd.to_numeric(test.get("neutral_site", 0), errors="coerce").fillna(0).to_numpy(dtype=float)
    mean = home - away + prior.net.hfa * is_home
    return ref.Forecast(name, mean, prior.net.resid_sd if sigma is None else sigma, hfa=prior.net.hfa)


def _lookup(teams: pd.DataFrame, test: pd.DataFrame, side: str) -> np.ndarray:
    """A side's prior net for every game; a team the prior never saw is league average."""
    net = teams.set_index(["season", "team_id"])["net"]
    keys = pd.Series(list(zip(test["season"], test[f"{side}_team_id"], strict=True)))
    return keys.map(net).fillna(0.0).to_numpy(dtype=float)


# ---------------------------------------------------------------------------
# Walk-forward evaluation
# ---------------------------------------------------------------------------


def run(frame: pd.DataFrame, *, first_test_season: int = FIRST_TEST_SEASON,
        ridge: float = RIDGE) -> tuple[pd.DataFrame, dict[int, Prior], pd.DataFrame]:
    """Score the prior beside the references, season by season.

    Returns the scored rows, the fitted prior per season, and a team-level
    table of how well each season's prior tracked the eventual least-squares
    rating - a diagnostic, since the rating is never the target.
    """
    feats = team_seasons(frame)
    targs = season_targets(frame)
    scored, priors, tracking = [], {}, []
    for season, train, test in ref.walk_forward(frame, first_test_season=first_test_season):
        prior = fit(frame, feats, season=season, ridge=ridge)
        priors[season] = prior
        refs = ref.all_references(train, test)
        grid = lat.fit(train["actual_margin"].to_numpy(), -train["closing_spread"].to_numpy(),
                       refs["market"].sigma)
        # sigma is the direct fit's in-sample training residual - the same
        # convention every reference uses, so the comparison is fair.
        fc = game_forecast(prior, test)
        keep = {k: refs[k] for k in ("naive", "prior_fpi", "prior_sp", "elo", "market") if k in refs}
        scored.append(evaluate.score(test, {**keep, "prior": fc}, grid, season=season))
        actual = targs[targs["season"] == season]
        merged = prior.teams.merge(actual, on=["season", "team_id"], suffixes=("_prior", "_actual"))
        for t in ("net", "off", "def"):
            tracking.append({"season": season, "target": t, "teams": len(merged),
                             "corr": float(merged[f"{t}_prior"].corr(merged[f"{t}_actual"])),
                             "rmse": float(np.sqrt(((merged[f"{t}_prior"] - merged[f"{t}_actual"]) ** 2).mean()))})
        LOG.info("season %s: prior fitted on %d games, sigma %.2f, hfa %.2f", season,
                 prior.net.n, prior.net.resid_sd, prior.net.hfa)
    return pd.concat(scored, ignore_index=True), priors, pd.DataFrame(tracking)


def render(scored: pd.DataFrame, priors: dict[int, Prior], tracking: pd.DataFrame,
           frame: pd.DataFrame) -> str:
    seasons = sorted(priors)
    last = priors[seasons[-1]]
    reg = scored[scored["season_type"] == "regular"]
    early = reg[reg["week"] <= 4]
    md = evaluate.markdown
    fmt = evaluate.formatted
    parts = [
        "# NCAAF preseason prior",
        "",
        f"Walk-forward, seasons {seasons[0]}-{seasons[-1]}: each season's prior is fitted on every "
        f"earlier season's (preseason facts -> eventual least-squares rating), then scored on that "
        f"season's games beside the reference models, with the same lattice and scoring as "
        f"`reports/ncaaf_benchmarks.md`. Frame: FBS-vs-FBS regular season.",
        "",
        "## What the recipe learned (last training window)",
        "",
        "Points of home margin per one standard deviation of each preseason feature, fitted "
        "directly on games. `sp_plus_def` is the SP+ defensive *rating* (points allowed), so a "
        "lower value is a better defence and its `def` coefficient is expected to be negative.",
        "",
    ]
    n = last.net
    parts += [f"### net  -  game-level R² {n.r2:.3f}, residual sd {n.resid_sd:.2f} points, "
              f"home advantage {n.hfa:+.2f}, n={n.n} games", "",
              md(n.table().assign(points_per_sd=lambda d: d["points_per_sd"].map("{:+.2f}".format))), ""]
    pt = last.points
    for block in ("off", "def"):
        parts += [f"### {block}  -  from one stacked points regression, R² {pt.r2:.3f}, "
                  f"residual sd {pt.resid_sd:.2f} points per team-game, n={pt.n} team-games", "",
                  md(pt.table(block).assign(points_per_sd=lambda d: d["points_per_sd"].map("{:+.2f}".format))), ""]
    parts += [
        f"A team's prior net has sd {last.teams['net'].std():.2f} points across the "
        f"{len(last.teams)} FBS teams of {seasons[-1]}; the game residual sd of {n.resid_sd:.2f} is the "
        "prior's own uncertainty and the state model's starting variance.",
        "",
        "## How well the prior tracked the eventual rating, team level",
        "",
        md(tracking.pivot(index="season", columns="target", values="corr").round(3)
           .reset_index().rename(columns={"net": "corr net", "off": "corr off", "def": "corr def"})),
        "",
        "## Game-level scores, weeks 1-4 (where a prior is the whole forecast)",
        "",
        md(fmt(evaluate.summarise(early))),
        "",
        "## By week bucket, regular season",
        "",
    ]
    r = reg.copy()
    r["week_bucket"] = evaluate.bucket(r["week"], evaluate.WEEK_BUCKETS, "wk")
    parts += [md(fmt(evaluate.summarise(r, ["week_bucket"]))), "",
              "## By season, weeks 1-4", "",
              md(fmt(evaluate.summarise(early, ["season"]))), "",
              f"## The {seasons[-1]} prior, top and bottom ten by net", ""]
    names = pd.concat([frame[["home_team_id", "home_team"]].rename(columns={"home_team_id": "team_id", "home_team": "team"}),
                       frame[["away_team_id", "away_team"]].rename(columns={"away_team_id": "team_id", "away_team": "team"})]
                      ).drop_duplicates("team_id").set_index("team_id")["team"]
    t = last.teams.copy()
    t["team"] = t["team_id"].map(names)
    t = t.sort_values("net", ascending=False)[["team", "net", "off", "def"]]
    show = pd.concat([t.head(10), t.tail(10)]).assign(
        net=lambda d: d["net"].map("{:+.1f}".format), off=lambda d: d["off"].map("{:+.1f}".format),
        **{"def": lambda d: d["def"].map("{:+.1f}".format)})
    parts += [md(show), ""]
    return "\n".join(parts).rstrip() + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description="NCAAF preseason prior, walk-forward")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--first-test-season", type=int, default=FIRST_TEST_SEASON)
    args = ap.parse_args()
    paths = config.paths()
    frame = research_sample(load_research_frame(paths.warehouse))
    scored, priors, tracking = run(frame, first_test_season=args.first_test_season)
    out = args.out or (paths.root / "reports" / "ncaaf_prior.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(scored, priors, tracking, frame))
    early = scored[(scored["season_type"] == "regular") & (scored["week"] <= 4)]
    LOG.info("wrote %s\n%s", out, evaluate.summarise(early).to_string(index=False))


if __name__ == "__main__":
    main()
