"""The NCAAF total and the joint score grid: step 5 of `docs/MODEL_PLAN_NCAAF.md`.

    python -m atlas.models.ncaaf_total          # -> reports/ncaaf_total.md

The state model already implies a total - its home points plus its away
points - but the sum of two noisy strengths spreads more than real totals
do (a slope of about 0.7 against actual totals), and it knows nothing about
pace or weather. So the total is that implied number, recalibrated
walk-forward on the training seasons' own state forecasts, plus the two
adjustments that measured as real on the residual: the teams' combined
adjusted pace and the effective wind. Temperature, precipitation, domes and
rest measured as nothing and are left out.

The margin (with its key-number lattice) and the total (a discretised
normal) are then combined on an 80x80 grid over (home, away) points by
:mod:`atlas.models.joint`, and the grid is reweighted by a points lattice
fitted on the training seasons' own grids (step 7's v1.5). Every headline
number is a mean of that grid.

Scored where the plan says to look: the total against naive, the raw state
total and the market; P(home) reliability by spread bucket; and the exact
score, which is reported for what it is.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np
import pandas as pd

from atlas import config
from atlas.models import evaluate, joint, scoring
from atlas.models import lattice as lat
from atlas.models import ncaaf_prior as prior_mod
from atlas.models import ncaaf_state as state_mod
from atlas.models import reference as ref
from atlas.research.dataset import load_research_frame
from atlas.util import get_logger

LOG = get_logger(__name__)

FIRST_TEST_SEASON = 2021

#: Game-level adjustments to the total, each measured on the state total's
#: residual before being admitted (pace t=-1.9, wind t=-2.5; nothing else
#: reached 1). Missing values are filled with the training mean.
ADJUSTMENTS = ("adj_pace_sum", "weather_wind_effective")

TOTAL_SUPPORT = np.arange(0, 2 * joint.DEFAULT_MAX_POINTS - 1)
CHUNK = 400


def total_support(max_points: int = joint.DEFAULT_MAX_POINTS) -> np.ndarray:
    """Every total a ``max_points``-a-side grid can hold."""
    return np.arange(0, 2 * max_points - 1)
LOG_FLOOR = 1e-6
TOTAL_ORDER = ("naive", "state_raw", "total", "market")


@dataclass(frozen=True)
class TotalFit:
    names: tuple[str, ...]           # regressors after the intercept: state_total, then adjustments
    coef: np.ndarray                 # intercept first
    fill: dict[str, float]           # training means, for missing adjustment values
    sigma: float                     # residual sd after calibration
    raw_sigma: float                 # residual sd of the uncalibrated state total
    n: int
    points_factor: np.ndarray | None = None   # the points lattice fitted beside it, one value per points cell

    def mean(self, fc: pd.DataFrame) -> np.ndarray:
        return _design(fc, self.names, self.fill) @ self.coef


def _design(fc: pd.DataFrame, names: tuple[str, ...], fill: dict[str, float]) -> np.ndarray:
    cols = [np.ones(len(fc))]
    for name in names:
        v = pd.to_numeric(fc[name], errors="coerce").to_numpy(dtype=float)
        cols.append(np.where(np.isnan(v), fill.get(name, 0.0), v))
    return np.column_stack(cols)


def fit_total(train: pd.DataFrame, adjustments: tuple[str, ...] = ADJUSTMENTS) -> TotalFit:
    """``actual_total ~ 1 + state_total + adjustments`` on training forecasts."""
    present = tuple(a for a in adjustments if a in train.columns
                    and pd.to_numeric(train[a], errors="coerce").notna().mean() >= 0.5)
    names = ("state_total", *present)
    fill = {a: float(pd.to_numeric(train[a], errors="coerce").mean()) for a in present}
    X = _design(train, names, fill)
    y = train["actual_total"].to_numpy(dtype=float)
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ coef
    raw = y - train["state_total"].to_numpy(dtype=float)
    return TotalFit(names=names, coef=coef, fill=fill, sigma=float(np.std(resid, ddof=len(coef))),
                    raw_sigma=float(np.std(raw - raw.mean(), ddof=1)), n=int(len(y)))


def _with_forecasts(games: pd.DataFrame, prior: prior_mod.Prior, spec) -> pd.DataFrame:
    fc, _ = state_mod._season_forecasts(games, prior, spec)
    out = games.copy()
    out["m_mean"], out["m_sd"] = fc["mean"].to_numpy(), fc["sd"].to_numpy()
    out["state_home"], out["state_away"] = fc["home_pts"].to_numpy(), fc["away_pts"].to_numpy()
    out["state_total"] = out["state_home"] + out["state_away"]
    return out.dropna(subset=["m_mean"])


def _training_forecasts(frame: pd.DataFrame, feats: pd.DataFrame, season: int,
                        choice: state_mod.Choice, like: prior_mod.Prior) -> pd.DataFrame:
    """The state's forecasts on the most recent training seasons, each run from
    its own point-in-time prior (a zero prior where none exists), with the
    test season's hyperparameters - the ones the test season will use."""
    seasons = [int(s) for s in sorted(frame["season"].unique()) if s < season][-state_mod.TUNING_SEASONS:]
    parts = []
    for s in seasons:
        games = frame[(frame["season"] == s) & (frame["season_type"] == "regular")]
        try:
            p, p0 = prior_mod.fit(frame, feats, season=s), choice.p0
        except ValueError:
            p, p0 = state_mod._zero_prior(games, like, s), state_mod.ZERO_PRIOR_P0
        parts.append(_with_forecasts(games, p, state_mod._spec(choice.q, p0, choice.sigma, p, choice.rho)))
    return pd.concat(parts, ignore_index=True)


def _p_over(pmf: np.ndarray, support: np.ndarray, line: np.ndarray) -> np.ndarray:
    """P(total > line) with half credit on a push."""
    cdf = np.cumsum(pmf, axis=1)
    floor = np.floor(line).astype(int)
    idx = np.clip(np.searchsorted(support, floor), 0, len(support) - 1)
    at_or_below = cdf[np.arange(len(line)), idx]
    exact = pmf[np.arange(len(line)), idx] * (support[idx] == floor)
    push = (line == floor)
    return 1.0 - at_or_below + np.where(push, 0.5 * exact, 0.0)


def _score_total(test: pd.DataFrame, models: dict[str, tuple[np.ndarray, float]], season: int,
                 support: np.ndarray = TOTAL_SUPPORT) -> pd.DataFrame:
    y = test["actual_total"].to_numpy(dtype=int)
    line = pd.to_numeric(test["closing_total"], errors="coerce").to_numpy(dtype=float) \
        if "closing_total" in test else np.full(len(test), np.nan)
    has_line = ~np.isnan(line)
    over = np.where(has_line, (y > line).astype(float) + 0.5 * (y == line), np.nan)
    rows = []
    for name, (mean, sigma) in models.items():
        pmf = lat.discretise(mean, sigma, support)
        p_over = np.full(len(test), np.nan)
        if has_line.any():
            p_over[has_line] = _p_over(pmf[has_line], support, line[has_line])
        rows.append(pd.DataFrame({
            "game_id": test["game_id"].to_numpy() if "game_id" in test else np.arange(len(test)),
            "season": season, "week": test["week"].to_numpy(),
            "season_type": test["season_type"].to_numpy() if "season_type" in test else "regular",
            "abs_spread": test["closing_spread"].abs().to_numpy() if "closing_spread" in test else np.nan,
            "model": name, "mean": mean, "sigma": sigma, "line": line,
            "crps": scoring.crps(pmf, support, y), "mae": scoring.mae(mean, y),
            "p_over": p_over, "over": over,
        }))
    return pd.concat(rows, ignore_index=True)


def summarise_total(scored: pd.DataFrame, by: list[str] | None = None) -> pd.DataFrame:
    keys = ["model", *(by or [])]
    out = scored.groupby(keys, observed=True).agg(games=("crps", "size"), crps=("crps", "mean"),
                                                   mae=("mae", "mean")).reset_index()
    over = scored.dropna(subset=["p_over", "over"])
    if not over.empty:
        cal = over.groupby(keys, observed=True).apply(
            lambda d: pd.Series({"over_brier": float(np.mean((d["p_over"] - d["over"]) ** 2)),
                                 "over_ece": scoring.expected_calibration_error(d["p_over"], d["over"])}),
            include_groups=False).reset_index()
        out = out.merge(cal, on=keys, how="left")
    seen = [m for m in TOTAL_ORDER if m in set(out["model"])]
    out["model"] = pd.Categorical(out["model"], categories=[*seen, *sorted(set(out["model"]) - set(seen))], ordered=True)
    return out.sort_values(keys).reset_index(drop=True)


def _points(fc: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    home = ((fc["actual_total"] + fc["actual_margin"]) / 2).to_numpy(dtype=int)
    away = ((fc["actual_total"] - fc["actual_margin"]) / 2).to_numpy(dtype=int)
    return home, away


def _plain_grids(fc: pd.DataFrame, grid_: lat.Lattice, tfit: TotalFit,
                 max_points: int = joint.DEFAULT_MAX_POINTS) -> list[joint.Joint]:
    """The v1 grids of a frame of state forecasts, in chunks."""
    support = total_support(max_points)
    margin_pmf = grid_.pmf(fc["m_mean"].to_numpy(dtype=float), fc["m_sd"].to_numpy(dtype=float))
    total_pmf = lat.discretise(tfit.mean(fc), tfit.sigma, support)
    return [joint.build(margin_pmf[s:s + CHUNK], grid_.support, total_pmf[s:s + CHUNK], support, max_points=max_points)
            for s in range(0, len(fc), CHUNK)]


def fit_points_lattice(train_fc: pd.DataFrame, grid_: lat.Lattice, tfit: TotalFit,
                       max_points: int = joint.DEFAULT_MAX_POINTS) -> np.ndarray:
    """The points lattice, fitted on the training seasons' own grids."""
    home, away = _points(train_fc)
    return joint.fit_points(_plain_grids(train_fc, grid_, tfit, max_points), home, away)


def _joint_table(fc: pd.DataFrame, margin_pmf: np.ndarray, margin_support: np.ndarray,
                 total_mean: np.ndarray, total_sigma: float, market_pmf: np.ndarray | None,
                 season: int, points_factor: np.ndarray | None = None,
                 max_points: int = joint.DEFAULT_MAX_POINTS) -> pd.DataFrame:
    """Build the grid in chunks and keep one row of headline numbers per game.

    ``cell_p_plain`` and ``rank_plain`` are the v1 grid's, before the points
    lattice, so the report can show what the lattice is worth.
    """
    support = total_support(max_points)
    total_pmf = lat.discretise(total_mean, total_sigma, support)
    y = fc["actual_margin"].to_numpy(dtype=int)
    home, away = _points(fc)
    parts = []
    for start in range(0, len(fc), CHUNK):
        sl = slice(start, start + CHUNK)
        J = joint.build(margin_pmf[sl], margin_support, total_pmf[sl], support, max_points=max_points)
        plain_p, plain_rank = J.cell_probability(home[sl], away[sl]), J.rank_of(home[sl], away[sl])
        if points_factor is not None:
            J = J.reweight(points_factor)
        s = J.summary()
        ms, mp = J.margin_pmf()
        s["margin_crps_joint"] = scoring.crps(mp, ms, y[sl])
        s["margin_crps_state"] = scoring.crps(margin_pmf[sl], margin_support, y[sl])
        s["cell_p"] = J.cell_probability(home[sl], away[sl])
        s["rank"] = J.rank_of(home[sl], away[sl])
        s["cell_p_plain"], s["rank_plain"] = plain_p, plain_rank
        s["margin_sd"] = fc["m_sd"].to_numpy(dtype=float)[sl]
        if "closing_spread" in fc:
            line = -pd.to_numeric(fc["closing_spread"], errors="coerce").to_numpy(dtype=float)[sl]
            s["p_cover"] = _p_over(mp, ms, np.where(np.isnan(line), 0.0, line))
            s.loc[np.isnan(line), "p_cover"] = np.nan
        parts.append(s)
    out = pd.concat(parts, ignore_index=True)
    out.insert(0, "season", season)
    for c in ("game_id", "week", "season_type", "kickoff", "home_team", "away_team", "neutral_site", "closing_spread",
              "closing_total", "actual_margin", "actual_total"):
        if c in fc:
            out[c] = fc[c].to_numpy()
    out["abs_spread"] = out["closing_spread"].abs() if "closing_spread" in out else np.nan
    out["home_score"], out["away_score"] = home, away
    out["won"] = (y > 0).astype(float) + 0.5 * (y == 0)
    out["p_home_market"] = scoring.home_win_probability(market_pmf, margin_support) if market_pmf is not None else np.nan
    out["cell_log"] = -np.log(np.maximum(out["cell_p"], LOG_FLOOR))
    out["cell_log_plain"] = -np.log(np.maximum(out["cell_p_plain"], LOG_FLOOR))
    return out


def run(frame: pd.DataFrame, *, first_test_season: int = FIRST_TEST_SEASON,
        choices: dict[int, state_mod.Choice] | None = None, grid: dict = state_mod.GRID):
    """Walk-forward: state, calibrated total, joint grid, scored beside the references.

    ``frame`` is every completed game (:func:`atlas.models.ncaaf_state.every_game`):
    the state, its tuning and the total's calibration learn from all of it;
    scores, the market and the lattice are on the games with a closing line.
    """
    feats = prior_mod.team_seasons(frame)
    scored, tables, fits = [], [], {}
    for season, train, test in ref.walk_forward(frame, first_test_season=first_test_season):
        prior = prior_mod.fit(frame, feats, season=season)
        choice = (choices or {}).get(season) or state_mod.tune(frame, feats, season, grid=grid, like=prior)
        train_fc = _training_forecasts(frame, feats, season, choice, prior)
        tfit = fit_total(train_fc)
        fits[season] = tfit
        fc = _with_forecasts(test, prior, state_mod._spec(choice.q, choice.p0, choice.sigma, prior, choice.rho))
        fc = fc[state_mod.has_market(fc)]
        train = train[state_mod.has_market(train)]
        if fc.empty:
            # A season played before the odds file carries its lines (the
            # current one, usually): its games taught the state and the total
            # through the training forecasts, and there is nothing to score.
            LOG.info("season %s: total = %.2f + %.3f state; no game with a closing line yet, nothing scored",
                     season, tfit.coef[0], tfit.coef[1])
            continue
        treg = train[train["season_type"] == "regular"] if "season_type" in train else train
        naive_mean, naive_sd = float(treg["actual_total"].mean()), float(treg["actual_total"].std(ddof=1))
        total_mean = tfit.mean(fc)
        models = {"naive": (np.full(len(fc), naive_mean), naive_sd),
                  "state_raw": (fc["state_total"].to_numpy(dtype=float), tfit.raw_sigma),
                  "total": (total_mean, tfit.sigma)}
        market_pmf = None
        if "closing_total" in fc and treg["closing_total"].notna().any():
            mres = (treg["actual_total"] - treg["closing_total"]).dropna()
            line = pd.to_numeric(fc["closing_total"], errors="coerce").to_numpy(dtype=float)
            models["market"] = (np.where(np.isnan(line), naive_mean, line), float(mres.std(ddof=1)))
            refs = ref.market(train, fc)
            grid_ = lat.fit(train["actual_margin"].to_numpy(), -train["closing_spread"].to_numpy(), refs.sigma)
            market_pmf = grid_.pmf(refs.mean, refs.sigma)
        else:
            grid_ = lat.Lattice(support=lat.DEFAULT_SUPPORT, factor=np.ones(len(lat.DEFAULT_SUPPORT)),
                                sigma=float(fc["m_sd"].mean()), games=0)
        scored.append(_score_total(fc, models, season))
        points_factor = fit_points_lattice(train_fc, grid_, tfit)
        fits[season] = tfit = replace(tfit, points_factor=points_factor)
        margin_pmf = grid_.pmf(fc["m_mean"].to_numpy(dtype=float), fc["m_sd"].to_numpy(dtype=float))
        tables.append(_joint_table(fc, margin_pmf, grid_.support, total_mean, tfit.sigma, market_pmf, season,
                                   points_factor=points_factor))
        LOG.info("season %s: total = %.2f + %.3f state%s; sigma %.2f (raw %.2f); %d games", season, tfit.coef[0],
                 tfit.coef[1], "".join(f" {c:+.3f} {n}" for n, c in zip(tfit.names[1:], tfit.coef[2:], strict=True)),
                 tfit.sigma, tfit.raw_sigma, len(fc))
    if not scored:
        raise ValueError("no test season has a game with a closing line to score")
    return pd.concat(scored, ignore_index=True), pd.concat(tables, ignore_index=True), fits


def _reliability_by_spread(table: pd.DataFrame, buckets: list[tuple[int, int]] = evaluate.SPREAD_BUCKETS,
                           tail: int = 28) -> pd.DataFrame:
    t = table.dropna(subset=["abs_spread"]).copy()
    t["bucket"] = evaluate.bucket(t["abs_spread"], buckets, "|spread|").astype(str)
    tail_label = f"|spread| {tail}+"
    if tail_label not in set(t["bucket"]):                 # the tail row overlaps the last bucket unless it is it
        t = pd.concat([t, t[t["abs_spread"] >= tail].assign(bucket=tail_label)])
    rows = []
    for b, d in t.groupby("bucket", sort=False):
        row = {"bucket": b, "games": len(d), "grid P(home)": d["p_home"].mean(), "observed": d["won"].mean()}
        row["grid gap"] = row["grid P(home)"] - row["observed"]
        if d["p_home_market"].notna().any():
            row["market P(home)"] = d["p_home_market"].mean()
            row["market gap"] = row["market P(home)"] - row["observed"]
        rows.append(row)
    order = list(dict.fromkeys([f"|spread| {lo}-{hi}" if hi < 99 else f"|spread| {lo}+" for lo, hi in buckets] + [tail_label]))
    out = pd.DataFrame(rows)
    out["bucket"] = pd.Categorical(out["bucket"], categories=[o for o in order if o in set(out["bucket"])], ordered=True)
    return out.sort_values("bucket").reset_index(drop=True)


def render(scored: pd.DataFrame, table: pd.DataFrame, fits: dict[int, TotalFit]) -> str:
    md = evaluate.markdown
    seasons = sorted(fits)
    reg = scored[scored["season_type"] == "regular"]
    treg = table[table["season_type"] == "regular"]

    def fmt(df, cols=("crps", "mae", "over_brier", "over_ece")):
        out = df.copy()
        for c in cols:
            if c in out:
                out[c] = [("" if pd.isna(v) else f"{v:.2f}" if c == "mae" else f"{v:.3f}") for v in out[c]]
        return out

    coef_rows = []
    for s, f in fits.items():
        row = {"season": s, "intercept": f"{f.coef[0]:+.1f}", "slope on state total": f"{f.coef[1]:.3f}"}
        for n, c in zip(f.names[1:], f.coef[2:], strict=True):
            row[n] = f"{c:+.3f}"
        row.update({"sigma": f"{f.sigma:.2f}", "raw sigma": f"{f.raw_sigma:.2f}", "train games": f.n})
        coef_rows.append(row)
    parts = [
        "# NCAAF total and joint score grid", "",
        f"Walk-forward, seasons {seasons[0]}-{seasons[-1]}. The total is the state model's implied home-plus-away "
        "points, recalibrated on the training seasons' own state forecasts with the two adjustments that "
        "measured as real (combined adjusted pace, effective wind). The margin (state mean and sd through the "
        "key-number lattice) and the total (discretised normal) are combined on an 80x80 grid over "
        "(home, away) points, `atlas/models/joint.py`; every headline number below is a mean of that grid.", "",
        "## Calibration fitted, per season", "",
        "`raw sigma` is the residual sd of the uncalibrated state total; `sigma` is after calibration and is the total's forecast sd.", "",
        md(pd.DataFrame(coef_rows)), "",
        "## Total, regular season, pooled", "",
        "`over_brier` and `over_ece` score P(over the closing total) against what happened; a push counts half. "
        "A model weaker than the market is over-confident on P(over) by construction - where it disagrees with "
        "the closing total the market is usually right - so that ECE measures the gap to the market, not the "
        "soundness of the total's own distribution, which CRPS does.", "",
        md(fmt(summarise_total(reg))), "",
        "## Total by season, regular", "",
        md(fmt(summarise_total(reg, ["season"]))), "",
    ]
    r = reg.copy()
    r["week_bucket"] = evaluate.bucket(r["week"], evaluate.WEEK_BUCKETS, "wk")
    parts += ["## Total by week bucket, regular season", "", md(fmt(summarise_total(r, ["week_bucket"]))), ""]
    bowls = scored[scored["season_type"] != "regular"]
    if not bowls.empty:
        parts += ["## Total, bowls and playoffs (never fitted, always scored)", "", md(fmt(summarise_total(bowls))), ""]
    parts += ["## Reliability, P(over the closing total), regular season", ""]
    for name in ("total", "market"):
        d = reg[(reg["model"] == name)].dropna(subset=["p_over", "over"])
        if d.empty:
            continue
        t = scoring.reliability(d["p_over"], d["over"])
        parts += [f"### {name}", "", md(t.assign(forecast=t["forecast"].map("{:.3f}".format), observed=t["observed"].map("{:.3f}".format),
                                                  gap=t["gap"].map("{:+.3f}".format))), ""]
    rel = _reliability_by_spread(treg)
    for c in rel.columns:
        if c not in ("bucket", "games"):
            signed = "gap" in c
            rel[c] = ["" if pd.isna(v) else (f"{v:+.3f}" if signed else f"{v:.3f}") for v in rel[c]]
    parts += ["## P(home) by closing spread, regular season: the grid against the market", "",
              "The 28+ row is the plan's check on the tails; it overlaps the 21+ row.", "", md(rel), ""]
    mc = treg[["margin_crps_joint", "margin_crps_state"]].mean()
    parts += ["## The margin through the grid", "",
              f"Margin CRPS from the grid's own margin marginal, points lattice applied: {mc['margin_crps_joint']:.3f}; "
              f"from the state's lattice pmf directly: {mc['margin_crps_state']:.3f}. The grid's 0-79 bounds and the "
              f"points lattice together cost {mc['margin_crps_joint'] - mc['margin_crps_state']:+.3f}.", ""]
    def exact(rank: str, log: str) -> dict:
        return {"games": len(treg),
                "top score was right": f"{(treg[rank] == 1).mean():.4f}",
                "actual score in the top 10 cells": f"{(treg[rank] <= 10).mean():.4f}",
                "actual score in the top 50 cells": f"{(treg[rank] <= 50).mean():.4f}",
                "mean -log P(actual score)": f"{treg[log].mean():.3f}",
                "median rank of the actual score": f"{treg[rank].median():.0f}"}
    exact_rows = pd.DataFrame([{"grid": "margin lattice only (v1)", **exact("rank_plain", "cell_log_plain")},
                               {"grid": "with the points lattice (v1.5)", **exact("rank", "cell_log")}])
    lattices = {s: f.points_factor for s, f in fits.items() if f.points_factor is not None}
    parts += ["## The exact score, for what it is", "",
              "The headline is the mean, to one decimal. With a team's points uncertain by eleven or so, the most "
              f"probable exact score is a fraction-of-a-percent event (mean {treg['top_p'].mean():.4f} with the points "
              "lattice), and the card shows it as such. The points lattice is step 7's answer to the plan's gate: "
              "a fitted multiplier on each side's own key numbers, no simulation.", "",
              md(exact_rows), ""]
    if lattices:
        last_l = lattices[max(lattices)]
        keys = (0, 3, 6, 7, 10, 13, 14, 17, 20, 21, 24, 27, 28, 31, 35, 38, 42)
        parts += [f"### Points lattice fitted for {max(lattices)}", "",
                  "Observed over expected frequency of a team scoring exactly this many points, shrunk toward one "
                  "where the expectation is thin and capped at 5.", "",
                  md(pd.DataFrame([{str(k): f"{last_l[k]:.2f}" for k in keys}])), ""]
    last = treg[treg["season"] == seasons[-1]]
    if "kickoff" in last:
        last = last.sort_values("kickoff").tail(12)
    cards = pd.DataFrame({
        "game": [f"{a} {'vs' if n else 'at'} {h}" for h, a, n in zip(last["home_team"], last["away_team"],
                 pd.to_numeric(last.get("neutral_site", pd.Series(0, index=last.index)), errors="coerce").fillna(0), strict=True)]
                if "home_team" in last else last.index,
        "projection": [f"{h:.1f}-{a:.1f}, total {t:.1f}" for h, a, t in zip(last["home_mean"], last["away_mean"], last["total_mean"], strict=True)],
        "P(home)": last["p_home"].map("{:.0%}".format),
        "total 80% range": [f"{lo:.0f}-{hi:.0f}" for lo, hi in zip(last["total_lo"], last["total_hi"], strict=True)],
        "most likely score": [f"{h}-{a} ({p:.1%})" for h, a, p in zip(last["top_home"], last["top_away"], last["top_p"], strict=True)],
        "market (spread / total)": [f"{s:+.1f} / {t:.1f}" if pd.notna(s) else "" for s, t in zip(last["closing_spread"], last["closing_total"], strict=True)],
        "actual": [f"{h}-{a}" for h, a in zip(last["home_score"], last["away_score"], strict=True)],
    })
    parts += [f"## What the card would have said: the last {len(cards)} regular-season games of {seasons[-1]}", "",
              "Decimal means, never rounded integers; the market column is the closing line for comparison, not an input.", "",
              md(cards), ""]
    return "\n".join(parts).rstrip() + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description="NCAAF total and joint score grid, walk-forward")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--first-test-season", type=int, default=FIRST_TEST_SEASON)
    ap.add_argument("--retune", action="store_true", help="ignore the state's saved hyperparameters and re-tune")
    args = ap.parse_args()
    paths = config.paths()
    frame = state_mod.every_game(load_research_frame(paths.warehouse))
    choices = None if args.retune else state_mod.load_choices(state_mod.choices_path(paths.root))
    if choices is None:
        LOG.warning("no saved state hyperparameters (%s); tuning here, which is slow", state_mod.choices_path(paths.root))
    scored, table, fits = run(frame, first_test_season=args.first_test_season, choices=choices)
    out = args.out or (paths.root / "reports" / "ncaaf_total.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(scored, table, fits))
    reg = scored[scored["season_type"] == "regular"]
    LOG.info("wrote %s\n%s", out, summarise_total(reg).to_string(index=False))


if __name__ == "__main__":
    main()
