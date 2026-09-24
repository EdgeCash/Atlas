"""The NFL total and the joint score grid: step 5 of `docs/MODEL_PLAN_NFL.md`.

    python -m atlas.models.nfl_total            # -> reports/nfl_total.md

The college construction (`atlas/models/ncaaf_total.py`), with three NFL
facts in place of the college ones: the state is the quarterback model
carried across seasons (`atlas/models/nfl_state.py`); the one game-level
term that measured as real on the implied total's residual is the wind
(-0.34 points per mph, t = -5.6; a dome is zero wind, and once wind is in
the dome itself adds nothing, nor do temperature, pace, rest or a division
game); and the grid is 60 points a side, which is every NFL final since
1966. The points lattice is fitted the same way and applied the same way.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

from atlas import config
from atlas.models import elo, evaluate, scoring
from atlas.models import lattice as lat
from atlas.models import ncaaf_total as tm
from atlas.models import nfl_benchmarks as nb
from atlas.models import nfl_state as ns
from atlas.models import reference as ref
from atlas.research.nfl_dataset import load_nfl_frame, research_sample
from atlas.util import get_logger

LOG = get_logger(__name__)

FIRST_TEST_SEASON = ns.FIRST_TEST_SEASON
REPORT_SEASONS = nb.REPORT_SEASONS
MAX_POINTS = 60
ADJUSTMENTS = ("wind_effective",)
SPREAD_BUCKETS = nb.SPREAD_BUCKETS
TAIL_SPREAD = 10


def prepare(frame: pd.DataFrame) -> pd.DataFrame:
    """The frame the state runner wants, plus the total's adjustment column."""
    f = nb.with_qb_change(elo.attach(frame)).sort_values(["kickoff", "game_id"]).reset_index(drop=True)
    wind = pd.to_numeric(f.get("weather_wind"), errors="coerce")
    dome = pd.to_numeric(f.get("venue_dome", 0), errors="coerce").fillna(0)
    f["wind_effective"] = np.where(dome == 1, 0.0, wind)
    for c in ("home_qb_id", "away_qb_id", "home_qb1_id", "away_qb1_id"):
        if c not in f.columns:
            f[c] = pd.NA
    return f


def _with_forecasts(games: pd.DataFrame, fc: pd.DataFrame) -> pd.DataFrame:
    out = games.copy()
    out["m_mean"], out["m_sd"] = fc["mean"].to_numpy(), fc["sd"].to_numpy()
    out["state_home"], out["state_away"] = fc["home_pts"].to_numpy(), fc["away_pts"].to_numpy()
    out["state_total"] = out["state_home"] + out["state_away"]
    return out.dropna(subset=["m_mean"])


def run(frame: pd.DataFrame, *, first_test_season: int = FIRST_TEST_SEASON,
        choices: tuple[dict, dict] | None = None, passers: pd.DataFrame | None = None,
        players: pd.DataFrame | None = None):
    """Walk-forward: state, calibrated total, joint grid, scored beside the references."""
    frame = prepare(frame)
    record = ns.PasserRecord(passers, players) if passers is not None else None
    all_seasons = [int(s) for s in sorted(frame["season"].unique())]
    levels = {s: ns._levels(frame[frame["season"] < max(s, all_seasons[0] + 1)], s) for s in all_seasons}
    team_choices, qb_choices = choices if choices else ({}, {})
    scored, tables, fits = [], [], {}
    for season, train, test in ref.walk_forward(frame, first_test_season=first_test_season):
        choice = team_choices.get(season) or ns.tune(frame, season, levels)
        qb = qb_choices.get(season) or ns.tune_qb(frame, season, choice, levels, record=record)
        history = [s for s in all_seasons if s < season]
        fcs, state, starters = ns.run_qb(frame[frame["season"] < season], history, choice=choice, p0=qb.p0,
                                         new_mean=qb.new_mean, levels=levels, k_epa=qb.k_epa, record=record, k_obs=qb.k_obs,
                                         k_draft=qb.k_draft)
        train_fc = pd.concat([_with_forecasts(frame[frame["season"] == s], fcs[s])
                              for s in history[-ns.TUNING_SEASONS:]], ignore_index=True)
        train_fc = train_fc[train_fc["season_type"] == "regular"]
        tfit = tm.fit_total(train_fc, ADJUSTMENTS)
        tfcs, _, _ = ns.run_qb(frame, [season], choice=choice, p0=qb.p0, new_mean=qb.new_mean, levels=levels,
                               state=state, starters=starters, k_epa=qb.k_epa, record=record, k_obs=qb.k_obs,
                               k_draft=qb.k_draft)
        fc = _with_forecasts(test, tfcs[season])
        treg = train[train["season_type"] == "regular"]
        naive_mean, naive_sd = float(treg["actual_total"].mean()), float(treg["actual_total"].std(ddof=1))
        total_mean = tfit.mean(fc)
        models = {"naive": (np.full(len(fc), naive_mean), naive_sd),
                  "state_raw": (fc["state_total"].to_numpy(dtype=float), tfit.raw_sigma),
                  "total": (total_mean, tfit.sigma)}
        mres = (treg["actual_total"] - treg["closing_total"]).dropna()
        line = pd.to_numeric(fc["closing_total"], errors="coerce").to_numpy(dtype=float)
        models["market"] = (np.where(np.isnan(line), naive_mean, line), float(mres.std(ddof=1)))
        refs = ref.market(train, fc)
        grid_ = lat.fit(train["actual_margin"].to_numpy(), -train["closing_spread"].to_numpy(), refs.sigma)
        market_pmf = grid_.pmf(refs.mean, refs.sigma)
        scored.append(tm._score_total(fc, models, season, support=tm.total_support(MAX_POINTS)))
        points_factor = tm.fit_points_lattice(train_fc, grid_, tfit, MAX_POINTS)
        fits[season] = replace(tfit, points_factor=points_factor)
        margin_pmf = grid_.pmf(fc["m_mean"].to_numpy(dtype=float), fc["m_sd"].to_numpy(dtype=float))
        tables.append(tm._joint_table(fc, margin_pmf, grid_.support, total_mean, tfit.sigma, market_pmf, season,
                                      points_factor=points_factor, max_points=MAX_POINTS))
        LOG.info("season %s: total = %.2f + %.3f state%s; sigma %.2f (raw %.2f); %d games", season, tfit.coef[0],
                 tfit.coef[1], "".join(f" {c:+.3f} {n}" for n, c in zip(tfit.names[1:], tfit.coef[2:], strict=True)),
                 tfit.sigma, tfit.raw_sigma, len(fc))
    return pd.concat(scored, ignore_index=True), pd.concat(tables, ignore_index=True), fits


def render(scored: pd.DataFrame, table: pd.DataFrame, fits: dict[int, tm.TotalFit]) -> str:
    md = evaluate.markdown
    seasons = sorted(fits)
    reg = scored[scored["season_type"] == "regular"]
    treg = table[table["season_type"] == "regular"]
    window = reg[reg["season"].isin(REPORT_SEASONS)]
    twindow = treg[treg["season"].isin(REPORT_SEASONS)]

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
        "# NFL total and joint score grid", "",
        f"Walk-forward, seasons {seasons[0]}-{seasons[-1]}. The total is the quarterback state model's implied "
        "home-plus-away points, recalibrated on the training seasons' own state forecasts with the wind "
        "(zero in a dome) as the one game-level term. The margin (state mean and sd through the key-number "
        f"lattice) and the total (discretised normal) meet on a {MAX_POINTS}x{MAX_POINTS} grid over (home, away) "
        "points, reweighted by the points lattice; every headline number below is a mean of that grid.", "",
        "## Calibration fitted, per season", "",
        md(pd.DataFrame(coef_rows)), "",
        f"## Total, regular season {REPORT_SEASONS[0]}-{REPORT_SEASONS[-1]}", "",
        "`over_brier` and `over_ece` score P(over the closing total); a push counts half. A model weaker than "
        "the market is over-confident on P(over) by construction, so that ECE measures the gap to the market, "
        "not the total's own distribution, which CRPS does.", "",
        md(fmt(tm.summarise_total(window))), "",
        "## Total, every scored season pooled", "",
        md(fmt(tm.summarise_total(reg))), "",
        "## Total by season, regular", "",
        md(fmt(tm.summarise_total(reg, ["season"]))), "",
    ]
    r = reg.copy()
    r["week_bucket"] = evaluate.bucket(r["week"], nb.WEEK_BUCKETS, "wk")
    parts += ["## Total by week bucket, regular season", "", md(fmt(tm.summarise_total(r, ["week_bucket"]))), ""]
    playoffs = scored[scored["season_type"] != "regular"]
    if not playoffs.empty:
        parts += ["## Total, playoffs (never fitted, always scored)", "", md(fmt(tm.summarise_total(playoffs))), ""]
    rel = tm._reliability_by_spread(twindow, SPREAD_BUCKETS, TAIL_SPREAD)
    for c in rel.columns:
        if c not in ("bucket", "games"):
            signed = "gap" in c
            rel[c] = ["" if pd.isna(v) else (f"{v:+.3f}" if signed else f"{v:.3f}") for v in rel[c]]
    parts += [f"## P(home) by closing spread, regular season {REPORT_SEASONS[0]}-{REPORT_SEASONS[-1]}: the grid against the market", "",
              "The plan asks whether the 65-80% bins are honest, because that is where the NFL lives.", "", md(rel), ""]
    for name, col in (("grid", "p_home"), ("market", "p_home_market")):
        d = twindow.dropna(subset=[col])
        if d.empty:
            continue
        t = scoring.reliability(d[col], d["won"])
        parts += [f"### Reliability, {name}", "", md(t.assign(forecast=t["forecast"].map("{:.3f}".format),
                                                               observed=t["observed"].map("{:.3f}".format),
                                                               gap=t["gap"].map("{:+.3f}".format))), ""]
    mc = twindow[["margin_crps_joint", "margin_crps_state"]].mean()
    parts += ["## The margin through the grid", "",
              f"Margin CRPS from the grid's own marginal, points lattice applied: {mc['margin_crps_joint']:.3f}; from "
              f"the state's lattice pmf directly: {mc['margin_crps_state']:.3f} ({REPORT_SEASONS[0]}-{REPORT_SEASONS[-1]}).", ""]

    def exact(rank: str, log: str) -> dict:
        return {"games": len(twindow),
                "top score was right": f"{(twindow[rank] == 1).mean():.4f}",
                "actual score in the top 10 cells": f"{(twindow[rank] <= 10).mean():.4f}",
                "actual score in the top 50 cells": f"{(twindow[rank] <= 50).mean():.4f}",
                "mean -log P(actual score)": f"{twindow[log].mean():.3f}",
                "median rank of the actual score": f"{twindow[rank].median():.0f}"}
    parts += ["## The exact score, for what it is", "",
              f"Mean P(top exact score) with the points lattice: {twindow['top_p'].mean():.4f}.", "",
              md(pd.DataFrame([{"grid": "margin lattice only", **exact("rank_plain", "cell_log_plain")},
                               {"grid": "with the points lattice", **exact("rank", "cell_log")}])), ""]
    last_l = fits[max(fits)].points_factor
    if last_l is not None:
        keys = (0, 3, 6, 7, 10, 13, 14, 16, 17, 20, 21, 23, 24, 27, 28, 30, 31, 34, 35)
        parts += [f"### Points lattice fitted for {max(fits)}", "",
                  md(pd.DataFrame([{str(k): f"{last_l[k]:.2f}" for k in keys}])), ""]
    last = treg[treg["season"] == seasons[-1]]
    if "kickoff" in last:
        last = last.sort_values("kickoff").tail(10)
    cards = pd.DataFrame({
        "game": [f"{a} {'vs' if n else 'at'} {h}" for h, a, n in zip(last["home_team"], last["away_team"],
                 pd.to_numeric(last.get("neutral_site", 0), errors="coerce").fillna(0), strict=True)],
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
    ap = argparse.ArgumentParser(description="NFL total and joint score grid, walk-forward")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--first-test-season", type=int, default=FIRST_TEST_SEASON)
    args = ap.parse_args()
    paths = config.paths()
    frame = research_sample(load_nfl_frame(paths.warehouse))
    choices = ns.load_choices(ns.choices_path(paths.root))
    if choices is None:
        LOG.warning("no saved NFL state hyperparameters (%s); tuning here, which is slow", ns.choices_path(paths.root))
    from atlas.models.nfl_projection import _passers, _players
    scored, table, fits = run(frame, first_test_season=args.first_test_season, choices=choices, passers=_passers(paths),
                              players=_players(paths))
    out = args.out or (paths.root / "reports" / "nfl_total.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(scored, table, fits))
    window = scored[(scored["season_type"] == "regular") & scored["season"].isin(REPORT_SEASONS)]
    LOG.info("wrote %s\n%s", out, tm.summarise_total(window).to_string(index=False))


if __name__ == "__main__":
    main()
