"""NFL benchmark report: what the reference models score, walk-forward.

    python -m atlas.models.nfl_benchmarks           # -> reports/nfl_benchmarks.md

Step 2 of `docs/MODEL_PLAN_NFL.md`. The college harness, unchanged: each
season is forecast by references fitted only on the seasons before it, on
the same key-number lattice refit per training window, scored the same
way. What differs is the frame (`atlas/research/nfl_dataset.py`), the Elo
(computed walk-forward here, `atlas/models/elo.py`, because the NFL frame
carries none), the week and spread buckets, and one NFL-specific cut: the
quarterback test, which scores every model separately on games where a
side's quarterback of record differs from its previous game's.

The plan fits on 2011-2019, tunes on 2020-2022 and reports 2023-2025. The
benchmarks are references, not tuned, so every season from 2020 is scored;
the report shows the pooled window and the 2023-2025 reporting window both.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from atlas import config
from atlas.models import elo, evaluate, scoring
from atlas.models import lattice as lat
from atlas.models import reference as ref
from atlas.research.nfl_dataset import load_nfl_frame, research_sample
from atlas.util import get_logger

LOG = get_logger(__name__)

FIRST_TEST_SEASON = 2020
REPORT_SEASONS = (2023, 2024, 2025)
WEEK_BUCKETS = [(1, 3), (3, 7), (7, 13), (13, 99)]
SPREAD_BUCKETS = [(0, 3), (3, 6), (6, 10), (10, 99)]
ORDER = ("naive", "elo", "atlas_epa", "market")


def with_qb_change(frame: pd.DataFrame) -> pd.DataFrame:
    """Flag each side whose quarterback of record is not the one from its previous game.

    Known only after the game (it is the quarterback *of record*), so this is
    a cut for scoring, never a feature. The first game a team plays in the
    frame has no previous quarterback and is not flagged.
    """
    f = frame.copy()
    long = pd.concat([
        f[["game_id", "season", "kickoff", "home_team_id", "home_qb_id"]].rename(columns={"home_team_id": "team_id", "home_qb_id": "qb"}),
        f[["game_id", "season", "kickoff", "away_team_id", "away_qb_id"]].rename(columns={"away_team_id": "team_id", "away_qb_id": "qb"}),
    ]).sort_values(["team_id", "kickoff"])
    prev = long.groupby("team_id")["qb"].shift(1)
    long["changed"] = np.where(prev.isna() | long["qb"].isna(), np.nan, (long["qb"] != prev).astype(float))
    key = long.set_index(["game_id", "team_id"])["changed"]
    for side in ("home", "away"):
        idx = pd.MultiIndex.from_arrays([f["game_id"], f[f"{side}_team_id"]])
        f[f"{side}_qb_change"] = key.reindex(idx).to_numpy()
    f["qb_change"] = ((f["home_qb_change"] == 1) | (f["away_qb_change"] == 1)).astype(float)
    f.loc[f["home_qb_change"].isna() & f["away_qb_change"].isna(), "qb_change"] = np.nan
    return f


def score_frame(frame: pd.DataFrame, *, first_test_season: int = FIRST_TEST_SEASON,
                min_train_seasons: int = 2) -> pd.DataFrame:
    """One row per (game, model) with every score, plus the QB-change cut."""
    frame = with_qb_change(elo.attach(frame))
    rows = []
    for season, train, test in ref.walk_forward(frame, first_test_season=first_test_season,
                                                min_train_seasons=min_train_seasons):
        forecasts = ref.all_references(train, test)
        grid = lat.fit(train["actual_margin"].to_numpy(), -train["closing_spread"].to_numpy(),
                       forecasts["market"].sigma)
        scored = evaluate.score(test, forecasts, grid, season=season)
        scored["qb_change"] = np.tile(test["qb_change"].to_numpy(), len(forecasts))
        rows.append(scored)
        LOG.info("season %s: %d games scored against %d references", season, len(test), len(forecasts))
    return pd.concat(rows, ignore_index=True)


def render(scored: pd.DataFrame) -> str:
    seasons = sorted(scored["season"].unique())
    fmt, table, summarise = evaluate.formatted, evaluate.markdown, evaluate.summarise
    cols = ["crps", "brier", "log_margin", "mae", "ece"]
    regular = scored[scored["season_type"] == "regular"]
    playoffs = scored[scored["season_type"] != "regular"]
    window = regular[regular["season"].isin(REPORT_SEASONS)]
    parts = [
        "# NFL reference benchmarks", "",
        f"Out-of-sample scores for the reference models in `atlas/models/reference.py`, seasons "
        f"{seasons[0]}-{seasons[-1]}, each forecast by references fitted only on the seasons before it "
        f"(training starts in 2011). Frame: completed games with a closing line "
        f"(`atlas/research/nfl_dataset.py`), {len(regular) // regular['model'].nunique()} regular-season and "
        f"{len(playoffs) // max(playoffs['model'].nunique(), 1)} playoff games. Elo is FiveThirtyEight's, "
        "walk-forward (`atlas/models/elo.py`); `atlas_epa` is the opponent-adjusted net EPA difference as it "
        "stood before the week.", "",
        "Lower is better everywhere. CRPS is on the integer margin lattice and reads like an absolute error; "
        "Brier is the home-win probability (0.25 is a coin flip); `log_margin` is the negative log probability "
        "of the exact margin in nats; ECE is the count-weighted gap between forecast and observed home-win "
        "frequency across ten bins. The same key-number lattice, refit on each training window against the "
        "market's means, is applied to every model.", "",
        f"## Reporting window, regular season {REPORT_SEASONS[0]}-{REPORT_SEASONS[-1]}", "",
        "The plan's targets (`docs/MODEL_PLAN_NFL.md` §6) are set against this window.", "",
        table(fmt(summarise(window, order=ORDER), cols)), "",
        "## Regular season, every scored season pooled", "",
        table(fmt(summarise(regular, order=ORDER), cols)), "",
        "## By season (regular season)", "",
        table(fmt(summarise(regular, ["season"], order=ORDER), cols)), "",
        "## By week (regular season)", "",
        "Weeks 1-2 test the prior; 13+ test what has been learned in season.", "",
    ]
    r = regular.copy()
    r["week_bucket"] = evaluate.bucket(r["week"], WEEK_BUCKETS, "wk")
    parts += [table(fmt(summarise(r, ["week_bucket"], order=ORDER), cols)), "",
              "## By closing spread (regular season)", "",
              "The NFL lives between 0 and 7; with parity, few games sit past 10.", ""]
    r["spread_bucket"] = evaluate.bucket(r["abs_spread"], SPREAD_BUCKETS, "|spread|")
    parts += [table(fmt(summarise(r, ["spread_bucket"], order=ORDER), cols)), ""]
    q = regular.dropna(subset=["qb_change"]).copy()
    if not q.empty:
        q["quarterback"] = np.where(q["qb_change"] == 1, "a side changed QB", "same quarterbacks")
        parts += ["## The quarterback test (regular season)", "",
                  "Games where at least one side's quarterback of record differs from its previous game's. "
                  "A model with a working QB state should be no worse here than elsewhere; the market's "
                  "residual on these games says how much it under-adjusts.", "",
                  table(fmt(summarise(q, ["quarterback"], order=ORDER), cols)), ""]
    if not playoffs.empty:
        parts += ["## Playoffs (never fitted, always scored)", "", table(fmt(summarise(playoffs, order=ORDER), cols)), ""]
    parts += ["## Fitted parameters (last training window)", "",
              "Points of home margin per unit of the feature, and the fitted home advantage.", ""]
    last = scored[scored["season"] == seasons[-1]].groupby("model", observed=True).first().reset_index()
    last["model"] = pd.Categorical(last["model"], categories=[m for m in ORDER if m in set(last["model"])], ordered=True)
    params = last.sort_values("model")[["model", "coefficient", "hfa", "sigma"]]
    params = params.assign(coefficient=params["coefficient"].map(lambda v: "" if pd.isna(v) else f"{v:.3f}"),
                           hfa=params["hfa"].map(lambda v: "" if pd.isna(v) else f"{v:.2f}"),
                           sigma=params["sigma"].map(lambda v: f"{v:.2f}"))
    parts += [table(params), "", "## Reliability, home-win probability (regular season)", ""]
    for name in ("elo", "market"):
        d = regular[regular["model"] == name]
        if d.empty:
            continue
        t = scoring.reliability(d["p_home"], d["won"])
        parts += [f"### {name}", "", table(t.assign(forecast=t["forecast"].map("{:.3f}".format),
                                                    observed=t["observed"].map("{:.3f}".format),
                                                    gap=t["gap"].map("{:+.3f}".format))), ""]
    return "\n".join(parts).rstrip() + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description="NFL reference benchmarks, walk-forward")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--first-test-season", type=int, default=FIRST_TEST_SEASON)
    args = ap.parse_args()
    paths = config.paths()
    frame = research_sample(load_nfl_frame(paths.warehouse))
    scored = score_frame(frame, first_test_season=args.first_test_season)
    out = args.out or (paths.root / "reports" / "nfl_benchmarks.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(scored))
    window = scored[(scored["season_type"] == "regular") & scored["season"].isin(REPORT_SEASONS)]
    LOG.info("wrote %s\n%s", out, evaluate.summarise(window, order=ORDER).to_string(index=False))


if __name__ == "__main__":
    main()
