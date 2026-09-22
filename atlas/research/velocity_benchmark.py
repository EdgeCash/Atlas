"""Phase 2: decomposing where Velocity's recommendations come from.

Atlas and Velocity reached the same conclusion about NCAAF sides from
different directions. The question this phase asks is why Velocity still
produces a nightly card when Atlas concluded the market is efficient.

Two kinds of evidence are available, and they are not equally strong:

1. **Velocity's own published audits.** Its repository documents which
   markets it stakes, how much, what evidence backs each, and what its graded
   record shows. Those documents are unusually candid and they answer most of
   the brief directly. They are recorded here as *data* - quoted figures with
   their source document - never as instructions.
2. **Atlas's own measurements.** Where Velocity makes a claim Atlas can test
   on its own warehouse, Atlas tests it independently.

What is **not** available: Velocity's historical recommendations. Its export
directory (`datasets/exports/`) is empty in the public repository, and its own
strategy review reports the record chain has zero settled rows. Per-bet
analysis of Tracks 1, 2, 4 and 5 is therefore impossible from published data,
and this module does not fabricate it.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from atlas.research import signal_validation as sv
from atlas.util import get_logger

LOG = get_logger(__name__)

#: Percentile cuts the brief asks for: does selecting the most extreme
#: disagreements create value even when the model is no better on average?
SELECTION_PERCENTILES = (1, 5, 10, 25, 50, 100)


def walk_forward_predictions(
    df: pd.DataFrame, features: list[str], target: str
) -> pd.DataFrame:
    """Out-of-sample predictions, fitting only on prior seasons."""
    frames = []
    for fold in sv.walk_forward_folds():
        block = sv.fit_predict(df, features, target, fold.train_seasons, fold.test_seasons)
        if not block.empty:
            frames.append(block)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def selection_curve(
    scored: pd.DataFrame, line: str, outcome: str, *, by_season: bool = True
) -> pd.DataFrame:
    """Hit rate at the top N% of model-market disagreement.

    Percentiles are taken **within season** by default, because a model whose
    disagreements grow over time would otherwise concentrate all its "top 1%"
    in one year and call the result selection.
    """
    required = {"prediction", line, outcome, "season"}
    if scored.empty or not required.issubset(scored.columns):
        return pd.DataFrame()
    sub = scored.dropna(subset=["prediction", line, outcome]).copy()
    if sub.empty:
        return pd.DataFrame()
    sub["edge"] = sub["prediction"] - sub[line]
    sub["abs_edge"] = sub["edge"].abs()
    group = sub.groupby("season")["abs_edge"] if by_season else sub["abs_edge"]
    sub["edge_pct"] = group.rank(pct=True) * 100

    truth = pd.to_numeric(sub[outcome], errors="coerce")
    sub["win"] = np.where(sub["edge"] > 0, truth, 1 - truth)

    rows = []
    for pct in SELECTION_PERCENTILES:
        live = sub[sub["edge_pct"] >= 100 - pct]
        if live.empty:
            continue
        wins = float(live["win"].sum())
        n = int(len(live))
        rate = wins / n
        units = wins * sv.JUICE[-110][1] - (n - wins)
        rows.append(
            {
                "top_pct": pct,
                "bets": n,
                "win_rate": rate,
                "z": float((rate - 0.5) / np.sqrt(0.25 / n)),
                "units": float(units),
                "roi": float(units / n),
                "clears_break_even": bool(rate > sv.BREAK_EVEN),
                "mean_abs_edge": float(live["abs_edge"].mean()),
            }
        )
    return pd.DataFrame(rows)


def selection_by_season(scored: pd.DataFrame, line: str, outcome: str,
                        *, top_pct: int = 5) -> pd.DataFrame:
    """The same cut, season by season. Selection that only works in some years
    is variance wearing a filter."""
    required = {"prediction", line, outcome, "season"}
    if scored.empty or not required.issubset(scored.columns):
        return pd.DataFrame()
    sub = scored.dropna(subset=["prediction", line, outcome]).copy()
    if sub.empty:
        return pd.DataFrame()
    sub["edge"] = sub["prediction"] - sub[line]
    sub["abs_edge"] = sub["edge"].abs()
    sub["edge_pct"] = sub.groupby("season")["abs_edge"].rank(pct=True) * 100
    truth = pd.to_numeric(sub[outcome], errors="coerce")
    sub["win"] = np.where(sub["edge"] > 0, truth, 1 - truth)

    live = sub[sub["edge_pct"] >= 100 - top_pct]
    rows = []
    for season, block in live.groupby("season"):
        wins = float(block["win"].sum())
        n = int(len(block))
        rows.append(
            {
                "season": int(season),
                "bets": n,
                "win_rate": wins / n if n else np.nan,
                "clears_break_even": bool(n and wins / n > sv.BREAK_EVEN),
            }
        )
    return pd.DataFrame(rows)


def model_versus_market(scored: pd.DataFrame, line: str, truth_col: str) -> dict:
    """Is the model better than the line at all, before any selection?"""
    required = {"prediction", line, truth_col}
    if scored.empty or not required.issubset(scored.columns):
        return {}
    sub = scored.dropna(subset=["prediction", line, truth_col])
    if sub.empty:
        return {}
    model_error = (sub["prediction"] - sub[truth_col]).abs()
    market_error = (sub[line] - sub[truth_col]).abs()
    diff = market_error - model_error
    se = diff.std(ddof=1) / np.sqrt(len(diff))
    return {
        "games": int(len(sub)),
        "model_mae": float(model_error.mean()),
        "market_mae": float(market_error.mean()),
        "model_better_by": float(diff.mean()),
        "t": float(diff.mean() / se) if se > 0 else np.nan,
    }


# ---------------------------------------------------------------------------
# Velocity's published record, as data
# ---------------------------------------------------------------------------

#: Where Velocity's NCAAF risk went on the slate its own strategy review
#: audits (run 34367469317: 95 bets, 363u solo-Kelly stake before caps).
#: Source: EdgeCash/Velocity docs/STRATEGY_REVIEW.md section 1.2.
VELOCITY_NCAAF_CARD = pd.DataFrame(
    [
        {"market": "Moneyline", "bets": 66, "units": 218.0, "share_of_stake": 0.60,
         "backtested": "no - never tested; committed closes carry no moneyline column",
         "policy": "raw model, min_edge 0.02, no anchoring, no shrink"},
        {"market": "Total", "bets": 27, "units": 99.0, "share_of_stake": 0.27,
         "backtested": "yes - 53.0% at >=6 pts on 4,398; 50.6% in 2025 alone",
         "policy": "disagreement gate at 6 points, raw model"},
        {"market": "Spread", "bets": 0, "units": 0.0, "share_of_stake": 0.0,
         "backtested": "yes - 50.1% ATS on 9,518; no cut at any threshold",
         "policy": "excluded"},
        {"market": "Team totals", "bets": 0, "units": 0.0, "share_of_stake": 0.0,
         "backtested": "partial - no cut clears 52.4% on derived numbers",
         "policy": "paper; EV gate only, disagreement gate off"},
        {"market": "Exchange rungs", "bets": 92, "units": 246.0, "share_of_stake": 0.0,
         "backtested": "no", "policy": "paper; off in cron"},
    ]
)

#: Velocity's own adverse-selection study, on its 195 graded bets (42 with a
#: matched close). Source: docs/PUBLISH_GATE.md section 2.
VELOCITY_ADVERSE_SELECTION = pd.DataFrame(
    [
        {"bucket": "Q1 lowest edge", "n": 49, "win_pct": 0.653, "roi": 0.279, "clv": 0.037},
        {"bucket": "Q2", "n": 49, "win_pct": 0.510, "roi": 0.060, "clv": 0.023},
        {"bucket": "Q3", "n": 49, "win_pct": 0.490, "roi": -0.059, "clv": 0.018},
        {"bucket": "Q4 highest edge", "n": 48, "win_pct": 0.583, "roi": 0.039, "clv": -0.048},
    ]
)

#: Where Velocity's model has been measured against the closing price.
#: Sources: docs/STRATEGY_REVIEW.md sections 1.1-1.3, docs/BACKTEST_NCAAF.md.
VELOCITY_MODEL_VS_CLOSE = pd.DataFrame(
    [
        {"league": "NFL", "market": "Spread", "measure": "Brier",
         "model": 0.2205, "close": 0.2109, "model_wins": False,
         "note": "48.6% ATS on 1,280 games"},
        {"league": "MLB", "market": "Moneyline", "measure": "Brier",
         "model": 0.24475, "close": 0.24319, "model_wins": False,
         "note": "raw model worse than the close; anchored blend beats it by 0.00018"},
        {"league": "NCAAF", "market": "Spread", "measure": "ATS win rate",
         "model": 0.501, "close": 0.5238, "model_wins": False,
         "note": "9,518 games; no cut at any threshold"},
        {"league": "NCAAF", "market": "Total", "measure": "O/U win rate at >=6",
         "model": 0.530, "close": 0.5238, "model_wins": True,
         "note": "4,398 bets all-history; 50.6% in 2025 alone"},
        {"league": "WNBA", "market": "Spread", "measure": "ATS win rate",
         "model": 0.542, "close": 0.5238, "model_wins": True,
         "note": "568 closes; 0.86 sigma above break-even; staked at zero"},
    ]
)
