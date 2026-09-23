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

import pandas as pd

from atlas import config
from atlas.models import (
    evaluate,
    scoring,  # noqa: F401 - re-exported for callers
)
from atlas.models import lattice as lat
from atlas.models import reference as ref
from atlas.research.dataset import load_research_frame, research_sample
from atlas.util import get_logger

LOG = get_logger(__name__)

FIRST_TEST_SEASON = 2021
WEEK_BUCKETS = evaluate.WEEK_BUCKETS
SPREAD_BUCKETS = evaluate.SPREAD_BUCKETS


def score_frame(frame: pd.DataFrame, *, first_test_season: int = FIRST_TEST_SEASON) -> pd.DataFrame:
    """One row per (game, model) with every score, plus the fitted parameters."""
    rows = []
    for season, train, test in ref.walk_forward(frame, first_test_season=first_test_season):
        forecasts = ref.all_references(train, test)
        # The lattice is a property of scores, fit on the best available mean.
        grid = lat.fit(train["actual_margin"].to_numpy(), -train["closing_spread"].to_numpy(),
                       forecasts["market"].sigma)
        rows.append(evaluate.score(test, forecasts, grid, season=season))
        LOG.info("season %s: %d games scored against %d references", season, len(test), len(forecasts))
    return pd.concat(rows, ignore_index=True)


summarise = evaluate.summarise
_bucket = evaluate.bucket
_fmt = evaluate.formatted
table = evaluate.markdown


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
