"""NCAAF benchmark report: what the reference models score, walk-forward.

    python -m atlas.models.ncaaf_benchmarks          # -> reports/ncaaf_benchmarks.md

This is step 1 of `docs/MODEL_PLAN_NCAAF.md`: before any model exists, fix
the numbers it has to beat, on the exact frame it will be trained on, scored
the exact way it will be scored. Everything is out of sample - each season is
forecast by references fitted only on the seasons before it - and the lattice
is refit per training window.

The frame is `research_sample(load_research_frame())`: FBS-vs-FBS completed
games with a closing line, garbage time already excluded from every
efficiency input upstream. Both facts are pinned by tests.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from atlas import config
from atlas.models import lattice as lat
from atlas.models import reference as ref
from atlas.models import scoring
from atlas.research.dataset import load_research_frame, research_sample
from atlas.util import get_logger

LOG = get_logger(__name__)

FIRST_TEST_SEASON = 2021
WEEK_BUCKETS = [(1, 2), (3, 4), (5, 8), (9, 12), (13, 99)]
SPREAD_BUCKETS = [(0, 3), (3, 7), (7, 14), (14, 21), (21, 99)]


def score_frame(frame: pd.DataFrame, *, first_test_season: int = FIRST_TEST_SEASON) -> pd.DataFrame:
    """One row per (game, model) with every score, plus the fitted parameters."""
    rows = []
    for season, train, test in ref.walk_forward(frame, first_test_season=first_test_season):
        forecasts = ref.all_references(train, test)
        # The lattice is a property of scores, fit on the best available mean.
        grid = lat.fit(train["actual_margin"].to_numpy(), -train["closing_spread"].to_numpy(),
                       forecasts["market"].sigma)
        y = test["actual_margin"].to_numpy(dtype=int)
        for name, fc in forecasts.items():
            pmf = grid.pmf(fc.mean, fc.sigma)
            p_home = scoring.home_win_probability(pmf, grid.support)
            rows.append(pd.DataFrame({
                "season": season,
                "week": test["week"].to_numpy(),
                "season_type": test["season_type"].to_numpy() if "season_type" in test else "regular",
                "abs_spread": test["closing_spread"].abs().to_numpy(),
                "model": name,
                "mean": fc.mean,
                "sigma": fc.sigma,
                "coefficient": fc.coefficient,
                "hfa": fc.hfa,
                "p_home": p_home,
                "won": (y > 0).astype(float) + 0.5 * (y == 0),
                "crps": scoring.crps(pmf, grid.support, y),
                "brier": scoring.brier(pmf, grid.support, y),
                "log_margin": scoring.log_score(pmf, grid.support, y),
                "mae": scoring.mae(fc.mean, y),
            }))
        LOG.info("season %s: %d games scored against %d references", season, len(test), len(forecasts))
    return pd.concat(rows, ignore_index=True)


def summarise(scored: pd.DataFrame, by: list[str] | None = None) -> pd.DataFrame:
    keys = ["model", *(by or [])]
    out = scored.groupby(keys, observed=True).agg(
        games=("crps", "size"),
        crps=("crps", "mean"),
        brier=("brier", "mean"),
        log_margin=("log_margin", "mean"),
        mae=("mae", "mean"),
    ).reset_index()
    ece = scored.groupby(keys, observed=True).apply(
        lambda d: scoring.expected_calibration_error(d["p_home"], d["won"]), include_groups=False
    ).rename("ece").reset_index()
    out = out.merge(ece, on=keys)
    out["model"] = pd.Categorical(out["model"], categories=ref.ORDER, ordered=True)
    return out.sort_values(keys).reset_index(drop=True)


def _bucket(values: pd.Series, buckets: list[tuple[int, int]], label: str) -> pd.Series:
    edges = [b[0] for b in buckets] + [buckets[-1][1]]
    labels = [f"{label} {lo}-{hi}" if hi < 99 else f"{label} {lo}+" for lo, hi in buckets]
    return pd.cut(values, bins=edges, labels=labels, right=False, include_lowest=True)


def _fmt(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    out = df.copy()
    for c in cols:
        if c in out:
            digits = 2 if c == "mae" else 3
            out[c] = [("" if pd.isna(v) else f"{v:.{digits}f}") for v in out[c]]
    return out


def table(df: pd.DataFrame) -> str:
    """A GitHub-flavoured markdown table from a frame whose cells are already
    formatted. Integers stay integers; anything else is rendered with str()."""
    cols = list(df.columns)
    lines = ["| " + " | ".join(str(c) for c in cols) + " |", "|" + "|".join(["---"] * len(cols)) + "|"]
    for _, row in df.iterrows():
        cells = []
        for c in cols:
            v = row[c]
            if isinstance(v, (int, np.integer)):
                cells.append(str(int(v)))
            elif isinstance(v, (float, np.floating)):
                cells.append("" if pd.isna(v) else f"{v:.3f}")
            else:
                cells.append(str(v))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def render(scored: pd.DataFrame) -> str:
    seasons = sorted(scored["season"].unique())
    regular = scored[scored["season_type"] == "regular"]
    bowls = scored[scored["season_type"] != "regular"]
    parts = [
        "# NCAAF reference benchmarks",
        "",
        f"Out-of-sample scores for the reference models in `atlas/models/reference.py`, "
        f"seasons {seasons[0]}-{seasons[-1]}, each forecast by references fitted only on "
        f"the seasons before it. Frame: FBS-vs-FBS completed games with a closing line "
        f"(`research_sample`), {scored['season'].nunique()} scored seasons, "
        f"{len(regular) // regular['model'].nunique()} regular-season games and "
        f"{len(bowls) // max(bowls['model'].nunique(), 1)} bowl/playoff games.",
        "",
        "Lower is better everywhere. CRPS is on the integer margin lattice and reads like an "
        "absolute error; Brier is the home-win probability (0.25 is a coin flip); "
        "`log_margin` is the negative log probability of the exact margin in nats; ECE is the "
        "count-weighted gap between forecast and observed home-win frequency across ten bins.",
        "",
        "The same key-number lattice - refit on each training window against the market's "
        "means - is applied to every model, so the rows differ only in mean and standard "
        "deviation. `docs/MODEL_FOUNDATION.md` §6 is the protocol; `docs/MODEL_PLAN_NCAAF.md` "
        "§6 sets the targets a candidate must beat.",
        "",
        "## Regular season, all scored seasons pooled",
        "",
        table(_fmt(summarise(regular), ["crps", "brier", "log_margin", "mae", "ece"])),
        "",
        "## By season (regular season)",
        "",
        table(_fmt(summarise(regular, ["season"]), ["crps", "brier", "log_margin", "mae", "ece"])),
        "",
        "## By week (regular season)",
        "",
        "Weeks 1-2 test the prior; 9+ test whatever has been learned in season.",
        "",
    ]
    r = regular.copy()
    r["week_bucket"] = _bucket(r["week"], WEEK_BUCKETS, "wk")
    parts.append(table(_fmt(summarise(r, ["week_bucket"]), ["crps", "brier", "log_margin", "mae", "ece"])))
    parts += ["", "## By closing spread (regular season)", "",
              "Where the market has a large favourite, the tails and the lattice matter most.", ""]
    r["spread_bucket"] = _bucket(r["abs_spread"], SPREAD_BUCKETS, "|spread|")
    parts.append(table(_fmt(summarise(r, ["spread_bucket"]), ["crps", "brier", "log_margin", "mae", "ece"])))
    if not bowls.empty:
        parts += ["", "## Bowls and playoffs (never fitted, always scored)", "",
                  table(_fmt(summarise(bowls), ["crps", "brier", "log_margin", "mae", "ece"]))]
    parts += ["", "## Fitted parameters (last training window)", "",
              "Points of home margin per unit of the feature, and the fitted home advantage.", ""]
    last = scored[scored["season"] == seasons[-1]].groupby("model", observed=True).first().reset_index()
    last["model"] = pd.Categorical(last["model"], categories=ref.ORDER, ordered=True)
    params = last.sort_values("model")[["model", "coefficient", "hfa", "sigma"]]
    params = params.assign(coefficient=params["coefficient"].map(lambda v: "" if pd.isna(v) else f"{v:.3f}"),
                           hfa=params["hfa"].map(lambda v: "" if pd.isna(v) else f"{v:.2f}"),
                           sigma=params["sigma"].map(lambda v: f"{v:.2f}"))
    parts.append(table(params))
    parts += ["", "## Reliability, home-win probability (regular season)", ""]
    for name in ("elo", "market"):
        d = regular[regular["model"] == name]
        if d.empty:
            continue
        parts += [f"### {name}", "",
                  table(scoring.reliability(d["p_home"], d["won"]).assign(
                      forecast=lambda t: t["forecast"].map("{:.3f}".format),
                      observed=lambda t: t["observed"].map("{:.3f}".format),
                      gap=lambda t: t["gap"].map("{:+.3f}".format))), ""]
    return "\n".join(parts).rstrip() + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description="NCAAF reference benchmarks, walk-forward")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--first-test-season", type=int, default=FIRST_TEST_SEASON)
    args = ap.parse_args()
    paths = config.paths()
    frame = research_sample(load_research_frame(paths.warehouse))
    scored = score_frame(frame, first_test_season=args.first_test_season)
    out = args.out or (paths.root / "reports" / "ncaaf_benchmarks.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(scored))
    pooled = summarise(scored[scored["season_type"] == "regular"])
    LOG.info("wrote %s\n%s", out, pooled.to_string(index=False))


if __name__ == "__main__":
    main()
