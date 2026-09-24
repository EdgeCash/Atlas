"""Can the college total be made more accurate? Five candidates, one bar.

    python -m atlas.research.ncaaf_total_accuracy     # -> reports/ncaaf_total_accuracy.md

The total (`atlas/models/ncaaf_total.py`) is the state model's implied total,
recalibrated on the three training seasons' own state forecasts, plus the
teams' combined adjusted pace and the effective wind. It trails the closing
total by about 0.3 points of CRPS (9.13 against 8.85, 2021-25). The curated
plays (`atlas/owner/plays.py`) are this number's disagreements with the
line, so every point of accuracy here is theirs.

The protocol, fixed before any season was scored. Each candidate changes one
thing; the state, its hyperparameters (``reports/ncaaf_state_choices.json``)
and the test games are the same for all.

* ``efficiency``: the calibration also reads both teams' opponent-adjusted
  EPA, success rate and explosiveness, offence and defence (point-in-time).
* ``defence_pace``: it also reads the pace the two defences allow.
* ``recent``: the calibration's three seasons weighted 1, 2, 4, newest
  heaviest - a rule change (the 2023 clock rules) reaches it sooner.
* ``five_seasons``: calibrated on five training seasons instead of three.
* ``in_season``: the total shifted by this season's running error so far -
  every earlier game's actual total less its forecast, shrunk by
  ``LEVEL_SHRINK`` games - so a league-wide shift is followed within weeks.

A wind-by-pass-rate interaction was on the list; the frame carries no pass
rate, so it was dropped before scoring. **The bar:** better pooled CRPS than
the total as it stands on 2021-25 regular season, mean absolute error no
worse, and better CRPS in at least three of the five seasons. Five were
tried; one passing by luck is possible, and the season count is the guard.
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from atlas import config
from atlas.models import evaluate, scoring
from atlas.models import lattice as lat
from atlas.models import ncaaf_prior as prior_mod
from atlas.models import ncaaf_state as state_mod
from atlas.models import ncaaf_total as total_mod
from atlas.models import reference as ref
from atlas.research.dataset import load_research_frame, research_sample
from atlas.util import get_logger

LOG = get_logger(__name__)

EFFICIENCY = ("adj_off_epa_sum", "adj_def_epa_sum", "adj_success_rate_sum", "adj_def_success_rate_sum",
              "adj_explosiveness_sum", "adj_def_explosiveness_sum")
LEVEL_SHRINK = 300.0
SUPPORT = total_mod.TOTAL_SUPPORT
CANDIDATES = ("current", "efficiency", "defence_pace", "recent", "five_seasons", "in_season")


def _training(frame, feats, season, choice, prior, n_seasons):
    """The state's forecasts on the ``n_seasons`` before ``season``, as the total model builds them."""
    old = state_mod.TUNING_SEASONS
    try:
        state_mod.TUNING_SEASONS = n_seasons
        return total_mod._training_forecasts(frame, feats, season, choice, prior)
    finally:
        state_mod.TUNING_SEASONS = old


def fit_weighted(train: pd.DataFrame, adjustments: tuple[str, ...], weights: np.ndarray) -> total_mod.TotalFit:
    """``fit_total`` by weighted least squares."""
    present = tuple(a for a in adjustments if pd.to_numeric(train[a], errors="coerce").notna().mean() >= 0.5)
    names = ("state_total", *present)
    fill = {a: float(pd.to_numeric(train[a], errors="coerce").mean()) for a in present}
    X = total_mod._design(train, names, fill)
    y = train["actual_total"].to_numpy(dtype=float)
    w = np.sqrt(weights)
    coef, *_ = np.linalg.lstsq(X * w[:, None], y * w, rcond=None)
    resid = y - X @ coef
    sigma = float(np.sqrt(np.sum(weights * resid ** 2) / np.sum(weights) * len(y) / (len(y) - len(coef))))
    return total_mod.TotalFit(names=names, coef=coef, fill=fill, sigma=sigma, raw_sigma=sigma, n=len(y))


def running_level(fc: pd.DataFrame, mean: np.ndarray, shrink: float = LEVEL_SHRINK) -> np.ndarray:
    """Each game's shift: the season's error on games kicked off on an earlier day, shrunk toward zero."""
    day = pd.to_datetime(fc["kickoff"], utc=True, errors="coerce").dt.floor("D").to_numpy()
    resid = fc["actual_total"].to_numpy(dtype=float) - mean
    out = np.zeros(len(fc))
    for i, d in enumerate(day):
        before = day < d
        n = int(before.sum())
        out[i] = resid[before].sum() / (n + shrink) if n else 0.0
    return out


def run(frame: pd.DataFrame, *, first_test_season: int = total_mod.FIRST_TEST_SEASON) -> pd.DataFrame:
    feats = prior_mod.team_seasons(frame)
    choices = state_mod.load_choices(state_mod.choices_path(config.paths().root)) or {}
    rows = []
    for season, _train, test in ref.walk_forward(frame, first_test_season=first_test_season):
        prior = prior_mod.fit(frame, feats, season=season)
        choice = choices.get(season) or state_mod.tune(frame, feats, season, like=prior)
        fc = total_mod._with_forecasts(test, prior, state_mod._spec(choice.q, choice.p0, choice.sigma, prior))
        fc = fc[fc["season_type"] == "regular"] if "season_type" in fc else fc
        tr3 = _training(frame, feats, season, choice, prior, 3)
        tr5 = _training(frame, feats, season, choice, prior, 5)
        base = total_mod.ADJUSTMENTS
        fits = {
            "current": total_mod.fit_total(tr3, base),
            "efficiency": total_mod.fit_total(tr3, (*base, *EFFICIENCY)),
            "defence_pace": total_mod.fit_total(tr3, (*base, "adj_def_pace_sum")),
            "recent": fit_weighted(tr3, base, tr3["season"].map(
                {s: 2.0 ** i for i, s in enumerate(sorted(tr3["season"].unique()))}).to_numpy(dtype=float)),
            "five_seasons": total_mod.fit_total(tr5, base),
        }
        means = {name: f.mean(fc) for name, f in fits.items()}
        sigmas = {name: f.sigma for name, f in fits.items()}
        means["in_season"] = means["current"] + running_level(fc, means["current"])
        sigmas["in_season"] = sigmas["current"]
        y = fc["actual_total"].to_numpy(dtype=int)
        for name in CANDIDATES:
            pmf = lat.discretise(means[name], sigmas[name], SUPPORT)
            rows.append(pd.DataFrame({"season": season, "game_id": fc["game_id"].to_numpy(), "model": name,
                                      "mean": means[name], "line": fc["closing_total"].to_numpy(dtype=float),
                                      "actual": y, "crps": scoring.crps(pmf, SUPPORT, y),
                                      "mae": scoring.mae(means[name], y)}))
        line = fc["closing_total"].to_numpy(dtype=float)
        ok = ~np.isnan(line)
        mpmf = lat.discretise(np.where(ok, line, means["current"]), float(np.std((y - line)[ok], ddof=1)), SUPPORT)
        rows.append(pd.DataFrame({"season": season, "game_id": fc["game_id"].to_numpy(), "model": "market",
                                  "mean": line, "line": line, "actual": y, "crps": scoring.crps(mpmf, SUPPORT, y),
                                  "mae": np.abs(line - y)}).loc[ok])
        LOG.info("season %s: %d games", season, len(fc))
    return pd.concat(rows, ignore_index=True)


def verdicts(scored: pd.DataFrame) -> dict[str, tuple[bool, str]]:
    pooled = scored.groupby("model")[["crps", "mae"]].mean()
    by = scored.groupby(["season", "model"])["crps"].mean().unstack()
    out = {}
    for name in CANDIDATES[1:]:
        wins = int((by[name] < by["current"]).sum())
        ok = (pooled.loc[name, "crps"] < pooled.loc["current", "crps"]
              and pooled.loc[name, "mae"] <= pooled.loc["current", "mae"] and wins >= 3)
        out[name] = (ok, f"CRPS {pooled.loc[name, 'crps']:.3f} against {pooled.loc['current', 'crps']:.3f}; MAE "
                         f"{pooled.loc[name, 'mae']:.2f} against {pooled.loc['current', 'mae']:.2f}; better in "
                         f"{wins} of {len(by)} seasons")
    return out


def paired(scored: pd.DataFrame) -> pd.DataFrame:
    """Each candidate's CRPS change against ``current`` game by game, with its standard error."""
    w = scored.pivot_table(index=["season", "game_id"], columns="model", values="crps")
    rows = []
    for name in CANDIDATES[1:]:
        d = (w[name] - w["current"]).dropna()
        se = float(d.std(ddof=1) / np.sqrt(len(d)))
        rows.append({"model": name, "crps change": f"{d.mean():+.4f}", "standard error": f"{se:.4f}",
                     "t": f"{d.mean() / se:+.2f}"})
    return pd.DataFrame(rows)


def render(scored: pd.DataFrame) -> str:
    md = evaluate.markdown
    order = [*CANDIDATES, "market"]
    pooled = scored.groupby("model")[["crps", "mae"]].mean().reindex(order).reset_index()
    pooled["games"] = scored.groupby("model").size().reindex(order).to_numpy()
    by = scored.groupby(["season", "model"])["crps"].mean().unstack()[order].reset_index()
    for c in order:
        by[c] = by[c].map("{:.3f}".format)
    pooled["crps"], pooled["mae"] = pooled["crps"].map("{:.3f}".format), pooled["mae"].map("{:.2f}".format)
    v = verdicts(scored)
    lines = [f"- **{n}: {'passes' if ok else 'fails'}** - {text}." for n, (ok, text) in v.items()]
    parts = [
        "# College totals: can the total be made more accurate?", "",
        "`atlas/research/ncaaf_total_accuracy.py`. Five candidates, each one change to the total as it stands "
        "(`current`), on the same state forecasts and the same games, regular season 2021-25, walk-forward. The "
        "bar, fixed before scoring: better pooled CRPS, MAE no worse, better CRPS in at least three of five "
        "seasons. The market row is the closing total through the same scoring, for scale. Lower is better.", "",
        "## Verdict", "", *lines, "",
        "## Pooled, regular season 2021-25", "", md(pooled[["model", "games", "crps", "mae"]]), "",
        "## CRPS by season", "", md(by), "",
        "## After scoring: is any change distinguishable from zero?", "",
        "Added after the verdicts above, and labelled so: the bar fixed before scoring had no test of noise, "
        "and it should have. Each game's CRPS change against `current`, paired, with its standard error. A change "
        "within about two standard errors of zero is not evidence of an improvement, whatever the pooled mean.",
        "", md(paired(scored)), "",
        "`efficiency` clears the bar as written on a change a third the size of its own standard error, with "
        "seasons swinging both ways (2021 worse by 0.07, 2022 better by 0.09): it is not adopted. None of the "
        "five is. Recalibrating the same state forecasts has run out; what the total lacks is information the "
        "state does not have.", "",
    ]
    return "\n".join(parts).rstrip() + "\n"


def main() -> None:
    argparse.ArgumentParser(description="College total accuracy candidates, walk-forward").parse_args()
    frame = research_sample(load_research_frame())
    scored = run(frame)
    out = config.paths().root / "reports" / "ncaaf_total_accuracy.md"
    out.write_text(render(scored))
    LOG.info("wrote %s\n%s", out, "\n".join(f"{n}: {t}" for n, (_, t) in verdicts(scored).items()))


if __name__ == "__main__":
    main()
