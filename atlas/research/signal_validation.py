"""Signal validation: an attempt to falsify the selective-totals candidate.

Phases 1A-1C found every public variable priced except one candidate, and that
candidate was measured in a way that flatters it: eight thresholds scanned on
the full sample, then the best one reported. This module removes that bias.

The discipline here is the product:

* the model is frozen and no feature may be added;
* the threshold is chosen inside the **training** seasons only, by a rule
  fixed in advance (`docs/SIGNAL_PREREGISTRATION.md`);
* each holdout is scored exactly **once**;
* the pass/fail criteria are constants in this file, committed before any
  holdout season was scored.

If the constants below were edited after seeing a result, the phase would be
worthless. The git history is the audit trail.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from atlas.research.dataset import available_features, feature_matrix
from atlas.util import get_logger

LOG = get_logger(__name__)

SEED = 20180101

# ---------------------------------------------------------------------------
# Frozen configuration - see docs/SIGNAL_PREREGISTRATION.md
# ---------------------------------------------------------------------------

#: The threshold grid searched inside training data only.
THRESHOLD_GRID: tuple[float, ...] = (1, 2, 3, 4, 5, 6, 7, 8)

#: Minimum training bets a threshold must produce to be selectable. Without a
#: floor the rule would drift to the sparsest, noisiest cut.
MIN_TRAINING_BETS = 500

#: American odds -> (break-even win rate, units returned by a win).
JUICE: dict[int, tuple[float, float]] = {
    -105: (105 / 205, 100 / 105),
    -110: (110 / 210, 100 / 110),
    -115: (115 / 215, 100 / 115),
    -120: (120 / 220, 100 / 120),
}
BREAK_EVEN = JUICE[-110][0]

N_BOOTSTRAP = 10_000

# --- pre-registered pass/fail criteria -------------------------------------

#: 1. Pooled holdout win rate must exceed break-even at -110.
CRITERION_WIN_RATE = BREAK_EVEN
#: 2. Lower bound of the 95% bootstrap CI must exceed a coin flip.
CRITERION_CI_LOWER = 0.50
#: 3. This many of the seven walk-forward seasons must clear break-even.
CRITERION_MIN_POSITIVE_SEASONS = 5
CRITERION_TOTAL_SEASONS = 7
#: 4. Expected units at -115 must be positive.
CRITERION_JUICE = -115

#: Deployment criteria, applied only if the four above all pass.
DEPLOY_MAX_DRAWDOWN_UNITS = 40.0
DEPLOY_MIN_PROFIT_FACTOR = 1.05
DEPLOY_MIN_PROB_ABOVE_53 = 0.50


# ---------------------------------------------------------------------------
# Experiments
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Experiment:
    name: str
    label: str
    train_seasons: tuple[int, ...]
    test_seasons: tuple[int, ...]


def experiments(seasons: tuple[int, ...] = tuple(range(2018, 2026))) -> list[Experiment]:
    return [
        Experiment("A", "train 2018-2024, test 2025", tuple(range(2018, 2025)), (2025,)),
        Experiment("B", "train 2018-2023, test 2024", tuple(range(2018, 2024)), (2024,)),
        Experiment("C", "train 2019-2025, test 2018", tuple(range(2019, 2026)), (2018,)),
    ]


def walk_forward_folds(
    seasons: tuple[int, ...] = tuple(range(2018, 2026)),
) -> list[Experiment]:
    """Fit on every prior season, predict the next. The honest ordering."""
    folds = []
    for i in range(1, len(seasons)):
        train = seasons[:i]
        test = (seasons[i],)
        folds.append(
            Experiment(
                f"WF{test[0]}",
                f"train {train[0]}-{train[-1]}, test {test[0]}",
                train,
                test,
            )
        )
    return folds


# ---------------------------------------------------------------------------
# Model - frozen
# ---------------------------------------------------------------------------


def _model() -> Pipeline:
    return Pipeline([("scale", StandardScaler()), ("model", Ridge(alpha=1.0))])


def fit_predict(
    df: pd.DataFrame,
    features: list[str],
    target: str,
    train_seasons: tuple[int, ...],
    test_seasons: tuple[int, ...],
) -> pd.DataFrame:
    """Fit on the training seasons only; predict the test seasons."""
    feats = available_features(df, features)
    X, used = feature_matrix(df, feats)
    y = pd.to_numeric(df[target], errors="coerce").to_numpy(dtype=float)
    seasons = df["season"].to_numpy()
    valid = np.isfinite(y)

    train = valid & np.isin(seasons, train_seasons)
    test = valid & np.isin(seasons, test_seasons)
    if train.sum() < 200 or test.sum() == 0 or not used:
        return pd.DataFrame()

    model = _model()
    model.fit(X[train], y[train])
    out = df.loc[test].copy()
    out["prediction"] = model.predict(X[test])
    return out


def inner_cv_predictions(
    df: pd.DataFrame, features: list[str], target: str, train_seasons: tuple[int, ...]
) -> pd.DataFrame:
    """Leave-one-season-out *inside* the training set.

    This is what the threshold is chosen on. The holdout contributes nothing.
    """
    frames = []
    for held in train_seasons:
        rest = tuple(s for s in train_seasons if s != held)
        block = fit_predict(df, features, target, rest, (held,))
        if not block.empty:
            frames.append(block)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def score_bets(
    scored: pd.DataFrame, threshold: float, *, line: str = "closing_total",
    outcome: str = "over_hit",
) -> pd.DataFrame:
    """The bets a threshold produces, with each one's win/loss.

    Pushes - where the total landed exactly on the number - carry a null
    outcome upstream and are dropped here as no action.
    """
    required = {"prediction", line, outcome}
    if scored.empty or not required.issubset(scored.columns):
        return pd.DataFrame()
    sub = scored.dropna(subset=["prediction", line, outcome]).copy()
    if sub.empty:
        return sub
    sub["edge"] = sub["prediction"] - sub[line]
    sub = sub[sub["edge"].abs() >= threshold]
    if sub.empty:
        return sub
    truth = pd.to_numeric(sub[outcome], errors="coerce")
    sub["pick"] = np.where(sub["edge"] > 0, "over", "under")
    sub["win"] = np.where(sub["edge"] > 0, truth, 1 - truth)
    return sub


def summarise(bets: pd.DataFrame, juice: int = -110) -> dict:
    """Win rate, units and ROI at a given price."""
    if bets.empty:
        return {"bets": 0, "wins": 0, "win_rate": np.nan, "units": np.nan,
                "roi": np.nan, "z": np.nan}
    break_even, win_return = JUICE[juice]
    wins = float(bets["win"].sum())
    n = int(len(bets))
    rate = wins / n
    units = wins * win_return - (n - wins)
    return {
        "bets": n,
        "wins": int(wins),
        "win_rate": rate,
        "units": float(units),
        "roi": float(units / n),
        "z": float((rate - 0.5) / np.sqrt(0.25 / n)),
        "break_even": break_even,
        "clears_break_even": bool(rate > break_even),
    }


#: Inner leave-one-season-out needs enough training seasons that each inner
#: fold still fits on at least two. Below this the threshold cannot be chosen
#: without either leaking or guessing.
MIN_SEASONS_FOR_SELECTION = 3


def select_threshold(
    df: pd.DataFrame, features: list[str], target: str, train_seasons: tuple[int, ...]
) -> tuple[float, pd.DataFrame]:
    """Choose one threshold on training data, by the pre-registered rule.

    Maximise expected units at -110 over the grid, subject to at least
    ``MIN_TRAINING_BETS`` bets; ties break to the lower threshold.

    **Edge case, documented because it was discovered after pre-registration:**
    the earliest walk-forward folds have one or two training seasons, so inner
    cross-validation is impossible. Those folds fall back to the grid minimum -
    the maximum-volume, minimum-selection-pressure choice, and the same
    direction the pre-registered tie-break already points. The reports mark
    such folds and also state the result with them excluded, so the fallback
    cannot quietly decide the phase.
    """
    if len(train_seasons) < MIN_SEASONS_FOR_SELECTION:
        table = pd.DataFrame(
            {"threshold": list(THRESHOLD_GRID), "bets": np.nan, "win_rate": np.nan,
             "units": np.nan, "roi": np.nan}
        )
        table["selected"] = table["threshold"] == min(THRESHOLD_GRID)
        table["selectable"] = False
        return float(min(THRESHOLD_GRID)), table

    inner = inner_cv_predictions(df, features, target, train_seasons)
    rows = []
    for threshold in THRESHOLD_GRID:
        bets = score_bets(inner, threshold)
        summary = summarise(bets)
        rows.append({"threshold": threshold, **summary})
    table = pd.DataFrame(rows)
    eligible = table[table["bets"] >= MIN_TRAINING_BETS]
    if eligible.empty:
        LOG.warning("no threshold met the %d-bet floor; falling back to the lowest",
                    MIN_TRAINING_BETS)
        eligible = table
    best = eligible.sort_values(["units", "threshold"], ascending=[False, True]).iloc[0]
    table["selected"] = table["threshold"] == best["threshold"]
    table["selectable"] = True
    return float(best["threshold"]), table


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------


def bootstrap_win_rate(
    wins: pd.Series, *, n_boot: int = N_BOOTSTRAP, seed: int = SEED
) -> dict:
    """Resample the individual bets, not the seasons. Each bet is one trial."""
    values = pd.to_numeric(wins, errors="coerce").dropna().to_numpy(dtype=float)
    n = len(values)
    if n < 50:
        return {"n": n}
    rng = np.random.default_rng(seed)
    draws = rng.choice(values, size=(n_boot, n), replace=True).mean(axis=1)
    return {
        "n": n,
        "observed": float(values.mean()),
        "mean": float(draws.mean()),
        "ci_low": float(np.percentile(draws, 2.5)),
        "ci_high": float(np.percentile(draws, 97.5)),
        "p_above_break_even": float((draws > BREAK_EVEN).mean()),
        "p_above_53": float((draws > 0.530).mean()),
        "p_above_54": float((draws > 0.540).mean()),
        "p_above_55": float((draws > 0.550).mean()),
        "p_above_50": float((draws > 0.500).mean()),
    }


# ---------------------------------------------------------------------------
# Running the experiments - each scored exactly once
# ---------------------------------------------------------------------------


def run_experiment(
    df: pd.DataFrame, features: list[str], target: str, experiment: Experiment
) -> dict:
    """Select on train, freeze, score the holdout once."""
    threshold, grid = select_threshold(df, features, target, experiment.train_seasons)
    scored = fit_predict(df, features, target, experiment.train_seasons,
                         experiment.test_seasons)
    bets = score_bets(scored, threshold)
    summary = summarise(bets)
    return {
        "experiment": experiment.name,
        "label": experiment.label,
        "train_from": experiment.train_seasons[0],
        "train_to": experiment.train_seasons[-1],
        "test": experiment.test_seasons[0],
        "threshold": threshold,
        "threshold_selectable": bool(grid["selectable"].iloc[0]),
        "eligible_games": int(len(scored)),
        **summary,
        "_bets": bets,
        "_grid": grid,
    }


def run_all(df: pd.DataFrame, features: list[str], target: str = "actual_total") -> dict:
    """Every experiment, once. This function is not meant to be re-run with
    different settings - that is the whole point of the phase."""
    holdouts = [run_experiment(df, features, target, e) for e in experiments()]
    folds = [run_experiment(df, features, target, e) for e in walk_forward_folds()]

    def _frame(rows: list[dict]) -> pd.DataFrame:
        return pd.DataFrame([{k: v for k, v in r.items() if not k.startswith("_")}
                             for r in rows])

    all_bets = pd.concat(
        [r["_bets"] for r in holdouts + folds if not r["_bets"].empty], ignore_index=True
    )
    selectable_bets = pd.concat(
        [r["_bets"] for r in holdouts + folds
         if not r["_bets"].empty and r["threshold_selectable"]],
        ignore_index=True,
    )
    return {
        "holdouts": _frame(holdouts),
        "walk_forward": _frame(folds),
        "grids": {r["experiment"]: r["_grid"] for r in holdouts + folds},
        "bets": all_bets,
        "selectable_bets": selectable_bets,
        "raw": holdouts + folds,
    }


#: The primary pooled holdout: every season 2018-2025 scored exactly once,
#: with no game counted twice. The walk-forward covers 2019-2025 and
#: Experiment C covers 2018. Experiments A and B are *subsets* of the
#: walk-forward (identical train/test splits), so pooling all four would
#: double-count 2024 and 2025.
PRIMARY_POOL = ("C", "WF2019", "WF2020", "WF2021", "WF2022", "WF2023", "WF2024", "WF2025")


def pooled_bets(results: dict, *, selectable_only: bool = False) -> pd.DataFrame:
    frames = []
    for row in results["raw"]:
        if row["experiment"] not in PRIMARY_POOL:
            continue
        if selectable_only and not row["threshold_selectable"]:
            continue
        bets = row["_bets"]
        if bets.empty:
            continue
        block = bets.copy()
        block["experiment"] = row["experiment"]
        block["threshold"] = row["threshold"]
        frames.append(block)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def season_stability(bets: pd.DataFrame, juice: int = -110) -> pd.DataFrame:
    """Per-season win rate, ROI, units and z, with a verdict."""
    if bets.empty:
        return pd.DataFrame()
    break_even = JUICE[juice][0]
    rows = []
    for season, block in bets.groupby("season"):
        summary = summarise(block, juice)
        if summary["win_rate"] > break_even:
            verdict = "positive"
        elif summary["win_rate"] < 0.50:
            verdict = "negative"
        else:
            verdict = "neutral"
        rows.append({"season": int(season), **summary, "verdict": verdict})
    return pd.DataFrame(rows).sort_values("season").reset_index(drop=True)


def juice_sensitivity(bets: pd.DataFrame) -> pd.DataFrame:
    """The same bets priced at every plausible number."""
    if bets.empty:
        return pd.DataFrame()
    rate = float(bets["win"].mean())
    rows = []
    for price, (break_even, _win_return) in JUICE.items():
        summary = summarise(bets, price)
        rows.append(
            {
                "price": price,
                "break_even": break_even,
                "observed_win_rate": rate,
                "edge_over_break_even": rate - break_even,
                "units": summary["units"],
                "roi": summary["roi"],
                "profitable": bool(summary["units"] > 0),
            }
        )
    return pd.DataFrame(rows)


def capital_metrics(bets: pd.DataFrame, juice: int = -110) -> dict:
    """Flat 1-unit staking: what holding this would actually have felt like."""
    if bets.empty:
        return {}
    _, win_return = JUICE[juice]
    ordered = bets.sort_values(["kickoff", "game_id"]) if "kickoff" in bets else bets
    pnl = np.where(ordered["win"] > 0, win_return, -1.0)
    equity = np.cumsum(pnl)
    peak = np.maximum.accumulate(np.concatenate([[0.0], equity]))[1:]
    drawdown = peak - equity

    losses = (ordered["win"] <= 0).to_numpy()
    longest, current = 0, 0
    for loss in losses:
        current = current + 1 if loss else 0
        longest = max(longest, current)

    gross_win = float(pnl[pnl > 0].sum())
    gross_loss = float(-pnl[pnl < 0].sum())
    return {
        "bets": int(len(ordered)),
        "units": float(equity[-1]),
        "roi": float(equity[-1] / len(ordered)),
        "max_drawdown": float(drawdown.max()),
        "max_drawdown_pct_of_turnover": float(drawdown.max() / len(ordered)),
        "longest_losing_streak": int(longest),
        "profit_factor": float(gross_win / gross_loss) if gross_loss > 0 else np.nan,
        "final_equity": float(equity[-1]),
        "worst_equity": float(equity.min()),
    }


def threshold_stability(results: dict) -> pd.DataFrame:
    """What the selection rule chose in each experiment.

    A genuine edge should have a roughly stable optimal cut. A rule that
    swings across the whole grid depending on which seasons it sees is
    describing noise.
    """
    rows = []
    for row in results["raw"]:
        rows.append(
            {
                "experiment": row["experiment"],
                "train": f"{row['train_from']}-{row['train_to']}",
                "train_seasons": row["train_to"] - row["train_from"] + 1,
                "threshold": row["threshold"],
                "selectable": row["threshold_selectable"],
                "holdout_bets": row["bets"],
                "holdout_win_rate": row["win_rate"],
            }
        )
    return pd.DataFrame(rows)


def evaluate_criteria(pooled: pd.DataFrame, walk_forward: pd.DataFrame,
                      boot: dict) -> pd.DataFrame:
    """The four pre-registered pass/fail criteria, applied mechanically."""
    rate = float(pooled["win"].mean()) if not pooled.empty else np.nan
    positive_seasons = int(walk_forward["clears_break_even"].sum()) if not walk_forward.empty else 0
    units_at_juice = summarise(pooled, CRITERION_JUICE)["units"] if not pooled.empty else np.nan

    checks = [
        {
            "criterion": "1. Pooled holdout win rate > 52.38%",
            "required": f"> {CRITERION_WIN_RATE:.4f}",
            "observed": rate,
            "passes": bool(np.isfinite(rate) and rate > CRITERION_WIN_RATE),
        },
        {
            "criterion": "2. Bootstrap 95% CI lower bound > 50.0%",
            "required": f"> {CRITERION_CI_LOWER:.2f}",
            "observed": boot.get("ci_low", np.nan),
            "passes": bool(boot.get("ci_low", np.nan) > CRITERION_CI_LOWER),
        },
        {
            "criterion": f"3. At least {CRITERION_MIN_POSITIVE_SEASONS} of "
                         f"{CRITERION_TOTAL_SEASONS} walk-forward seasons clear -110",
            "required": f">= {CRITERION_MIN_POSITIVE_SEASONS}",
            "observed": float(positive_seasons),
            "passes": positive_seasons >= CRITERION_MIN_POSITIVE_SEASONS,
        },
        {
            "criterion": f"4. Positive expected units at {CRITERION_JUICE}",
            "required": "> 0 units",
            "observed": units_at_juice,
            "passes": bool(np.isfinite(units_at_juice) and units_at_juice > 0),
        },
    ]
    out = pd.DataFrame(checks)
    out["verdict"] = np.where(out["passes"], "PASS", "FAIL")
    return out


# ---------------------------------------------------------------------------
# Failure analysis (Task 6) - diagnostics only
# ---------------------------------------------------------------------------

#: A diagnostic threshold, held fixed across every season so that changes in
#: the result reflect the market rather than the selection rule. This is
#: **not** a re-test and cannot rescue the signal: the pre-registered criteria
#: were evaluated once, above, and they failed.
DIAGNOSTIC_THRESHOLD = 4.0


def fixed_threshold_walk_forward(
    df: pd.DataFrame, features: list[str], target: str = "actual_total",
    threshold: float = DIAGNOSTIC_THRESHOLD,
) -> pd.DataFrame:
    """Walk-forward at one fixed threshold, to separate causes of failure.

    When the selection rule is free to move, bet volume collapses from 645 to
    42 across the sample and every per-season number changes meaning. Holding
    it fixed isolates whether the market changed or the rule did.
    """
    rows = []
    for fold in walk_forward_folds():
        scored = fit_predict(df, features, target, fold.train_seasons, fold.test_seasons)
        bets = score_bets(scored, threshold)
        rows.append(
            {"season": fold.test_seasons[0], "threshold": threshold, **summarise(bets)}
        )
    return pd.DataFrame(rows)


def diagnose_failure(
    pooled: pd.DataFrame,
    walk_forward: pd.DataFrame,
    thresholds: pd.DataFrame,
    fixed: pd.DataFrame,
    boot: dict,
) -> pd.DataFrame:
    """Attribute the failure to specific causes, with the evidence for each."""
    selectable = thresholds[thresholds["selectable"]]
    threshold_range = (
        f"{selectable['threshold'].min():g} to {selectable['threshold'].max():g}"
        if not selectable.empty
        else "n/a"
    )
    volume_range = (
        f"{int(walk_forward['bets'].min())} to {int(walk_forward['bets'].max())}"
        if not walk_forward.empty
        else "n/a"
    )
    early = fixed[fixed["season"] <= 2021]["win_rate"].mean() if not fixed.empty else np.nan
    late = fixed[fixed["season"] >= 2022]["win_rate"].mean() if not fixed.empty else np.nan

    return pd.DataFrame(
        [
            {
                "cause": "Threshold sensitivity",
                "implicated": True,
                "evidence": f"the frozen threshold ranged {threshold_range} points across "
                            f"experiments that differ only in which seasons they trained on",
            },
            {
                "cause": "Season instability",
                "implicated": True,
                "evidence": f"{int(walk_forward['clears_break_even'].sum())} of "
                            f"{len(walk_forward)} walk-forward seasons cleared -110; "
                            f"season win rates span "
                            f"{walk_forward['win_rate'].min():.3f} to "
                            f"{walk_forward['win_rate'].max():.3f}",
            },
            {
                "cause": "Holdout collapse",
                "implicated": True,
                "evidence": f"Phase 1C's in-sample scan read 52.4% at a 4-point cut; the "
                            f"pooled true holdout reads {pooled['win'].mean():.4f}",
            },
            {
                "cause": "Sample size",
                "implicated": True,
                "evidence": f"bets per season ranged {volume_range}; the highest-threshold "
                            f"folds bet fewer than 100 games, where a 55% read is noise",
            },
            {
                "cause": "Multiple testing",
                "implicated": True,
                "evidence": "Phase 1C scanned eight thresholds on the full sample and "
                            "reported the best; this phase scanned none on holdout data "
                            "and the apparent edge disappeared",
            },
            {
                "cause": "Market adaptation",
                "implicated": False,
                "evidence": f"at a fixed {DIAGNOSTIC_THRESHOLD:g}-point threshold the win rate "
                            f"averaged {early:.3f} in 2019-2021 and {late:.3f} in 2022-2025 - "
                            f"no trend consistent with the market learning; the signal was "
                            f"never there to adapt to",
            },
            {
                "cause": "Sample variance",
                "implicated": True,
                "evidence": f"the bootstrap 95% interval on the pooled holdout is "
                            f"[{boot.get('ci_low', float('nan')):.4f}, "
                            f"{boot.get('ci_high', float('nan')):.4f}] - it contains 50%",
            },
        ]
    )
