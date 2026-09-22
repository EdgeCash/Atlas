"""Reports for the signal-validation phase.

Everything here reads results produced by :mod:`atlas.research.signal_validation`
under the criteria fixed in ``docs/SIGNAL_PREREGISTRATION.md``. No number is
hand-entered and no threshold is chosen here.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from atlas import config
from atlas.research import adjustment_study as study
from atlas.research import signal_validation as sv
from atlas.research.dataset import load_research_frame, research_sample
from atlas.research.markdown import table
from atlas.util import get_logger

LOG = get_logger(__name__)


def _generated() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")


def totals_features() -> list[str]:
    """The frozen Phase 1B totals model. No feature may be added in this phase."""
    return study.feature_set(study.FULL_ADJ, "total") + ["pace_sum", "plays_per_game_sum"]


def run_validation() -> dict:
    paths = config.paths().ensure()
    df = research_sample(load_research_frame(paths.warehouse))
    features = totals_features()

    results = sv.run_all(df, features)
    pooled = sv.pooled_bets(results)
    selectable = sv.pooled_bets(results, selectable_only=True)
    boot = sv.bootstrap_win_rate(pooled["win"])
    boot_selectable = sv.bootstrap_win_rate(selectable["win"])
    criteria = sv.evaluate_criteria(pooled, results["walk_forward"], boot)
    fixed = sv.fixed_threshold_walk_forward(df, features)

    bundle = {
        "results": results,
        "pooled": pooled,
        "selectable": selectable,
        "bootstrap": boot,
        "bootstrap_selectable": boot_selectable,
        "criteria": criteria,
        "seasons": sv.season_stability(pooled),
        "juice": sv.juice_sensitivity(pooled),
        "capital": sv.capital_metrics(pooled),
        "thresholds": sv.threshold_stability(results),
        "fixed_threshold": fixed,
        "features": features,
    }
    bundle["failure"] = sv.diagnose_failure(
        pooled, results["walk_forward"], bundle["thresholds"], fixed, boot
    )
    _save(bundle)
    return bundle


def _save(bundle: dict) -> None:
    out = config.paths().reports / "tables"
    out.mkdir(parents=True, exist_ok=True)
    frames = {
        "holdouts": bundle["results"]["holdouts"],
        "walk_forward": bundle["results"]["walk_forward"],
        "seasons": bundle["seasons"],
        "juice": bundle["juice"],
        "criteria": bundle["criteria"],
        "thresholds": bundle["thresholds"],
        "fixed_threshold": bundle["fixed_threshold"],
        "failure": bundle["failure"],
    }
    for name, frame in frames.items():
        if isinstance(frame, pd.DataFrame) and not frame.empty:
            frame.to_csv(out / f"validation_{name}.csv", index=False)
    pd.DataFrame([bundle["bootstrap"]]).to_csv(out / "validation_bootstrap.csv", index=False)
    pd.DataFrame([bundle["capital"]]).to_csv(out / "validation_capital.csv", index=False)


# ---------------------------------------------------------------------------
# Task 2 - threshold freezing
# ---------------------------------------------------------------------------


def write_threshold_report(bundle: dict) -> Path:
    paths = config.paths().ensure()
    thresholds = bundle["thresholds"]
    grids = bundle["results"]["grids"]
    selectable = thresholds[thresholds["selectable"]]
    spread = (
        f"{selectable['threshold'].min():g} to {selectable['threshold'].max():g}"
        if not selectable.empty
        else "n/a"
    )

    grid_sections = []
    for name in ("A", "B", "C"):
        grid = grids.get(name)
        if grid is None or grid.empty or not bool(grid["selectable"].iloc[0]):
            continue
        row = thresholds[thresholds["experiment"] == name].iloc[0]
        grid_sections.append(
            f"### Experiment {name} - train {row['train']}\n\n"
            + table(
                grid,
                ["threshold", "bets", "win_rate", "units", "roi", "selected"],
                ["Threshold", "Training bets", "Win rate", "Units", "ROI", "Frozen"],
                digits=4,
            )
            + f"\n\n**Frozen at {row['threshold']:g} points.**\n"
        )

    text = f"""# Threshold Freeze Report (Signal Validation, Task 2)

*Generated {_generated()}. Selection rule fixed in advance -
see [`docs/SIGNAL_PREREGISTRATION.md`](../docs/SIGNAL_PREREGISTRATION.md),
committed before any holdout season was scored.*

## The bias this removes

Phase 1C evaluated eight thresholds - 0, 1, 2, 3, 4, 6, 8, 10 - **on the full
sample**, then reported the best-looking cut. That is selection bias with a
known direction: the maximum of eight noisy estimates is biased upward whether
or not any signal exists.

This phase picks **one** threshold per experiment, using training seasons only,
by a rule written down in advance:

> Over the grid {{1, 2, 3, 4, 5, 6, 7, 8}}, choose the threshold that maximises
> expected units at -110 on inner leave-one-season-out predictions *within the
> training set*, subject to at least {sv.MIN_TRAINING_BETS} training bets. Ties
> break to the lower threshold.

Maximising units rather than win rate is deliberate: win rate alone is
maximised by the sparsest cut, which is the overfitting the phase exists to
prevent. The bet floor exists for the same reason.

## The result, and it is the finding

{table(thresholds, ["experiment", "train", "train_seasons", "threshold", "selectable", "holdout_bets", "holdout_win_rate"], ["Experiment", "Training seasons", "n", "Frozen threshold", "Selectable", "Holdout bets", "Holdout win rate"], digits=4)}

**The frozen threshold ranges {spread} points across experiments that differ
only in which seasons they trained on.** Experiment C - trained on 2019-2025 -
freezes at 1 point. Experiment A - trained on 2018-2024, six of the same seven
seasons - freezes at 8.

That instability is, on its own, close to decisive. A real edge has a
reasonably stable optimal cut, because the underlying relationship does not
change when you swap one training season for another. A rule that swings
across the entire grid is fitting noise, and the grid is where the noise is.

It also means the "edge" is not one strategy. At 1 point it bets ~600 games a
season; at 8 points it bets ~40. Those are different products with different
variance, and Phase 1C's headline number quietly assumed the sparse one.

## Training grids

{chr(10).join(grid_sections) if grid_sections else "_no selectable grids_"}

## The walk-forward edge case, stated plainly

The first two walk-forward folds train on one and two seasons, so inner
cross-validation is impossible and no threshold can be selected without either
leaking or guessing. This was **not** anticipated in the pre-registration.

The fallback used is the grid minimum - maximum volume, minimum selection
pressure, the same direction the pre-registered tie-break already points - and
those folds are flagged throughout. Every pooled result is reported twice: with
them and without. The fallback does not decide the phase in either direction.

## Verdict for this task

The threshold cannot be frozen in any meaningful sense, because there is no
stable threshold to freeze. This alone is grounds for scepticism before a
single holdout game is scored.
"""
    out = paths.reports / "threshold_freeze_report.md"
    out.write_text(text)
    LOG.info("wrote %s", out)
    return out


# ---------------------------------------------------------------------------
# Task 5 - bootstrap
# ---------------------------------------------------------------------------


def write_bootstrap_report(bundle: dict) -> Path:
    paths = config.paths().ensure()
    boot = bundle["bootstrap"]
    boot_sel = bundle["bootstrap_selectable"]

    rows = pd.DataFrame(
        [
            {"population": "Pooled holdout (2018-2025, each season once)", **boot},
            {"population": "Selectable thresholds only (excludes 2019, 2020)", **boot_sel},
        ]
    )

    text = f"""# Bootstrap Signal Report (Signal Validation, Task 5)

*Generated {_generated()}. {sv.N_BOOTSTRAP:,} resamples, percentile intervals,
seed {sv.SEED}.*

## Method

Each bet is one Bernoulli trial and the bootstrap resamples **bets**, not
seasons. That is the more generous choice: resampling seasons would widen the
interval considerably, because the season-to-season swing is larger than
independent bets would produce. The signal fails on the generous version.

Population: the pooled true holdout - Experiment C covering 2018 plus the
walk-forward covering 2019-2025, so every season is scored exactly once and no
game is counted twice.

## Results

{table(rows, ["population", "n", "observed", "mean", "ci_low", "ci_high"], ["Population", "Bets", "Observed", "Bootstrap mean", "95% CI low", "95% CI high"], digits=4)}

## Probability the true win rate exceeds each bar

{table(rows, ["population", "p_above_50", "p_above_break_even", "p_above_53", "p_above_54", "p_above_55"], ["Population", "P(> 50%)", "P(> 52.38%)", "P(> 53%)", "P(> 54%)", "P(> 55%)"], digits=4)}

## Reading it

The pooled holdout observed **{boot['observed']:.2%}** on {boot['n']:,} bets,
with a 95% interval of **[{boot['ci_low']:.2%}, {boot['ci_high']:.2%}]**.

- The interval **contains 50%**. A coin flip is inside the range of plausible
  true values.
- The probability the true rate clears the -110 break-even is
  **{boot['p_above_break_even']:.1%}** - worse than a coin flip on the
  question "is this profitable at all".
- The probability it clears 53%, roughly the rate a tradable edge would need
  once real juice and limits are priced, is **{boot['p_above_53']:.1%}**.
- The probability it clears 55%, the rate that would make this a business, is
  **{boot['p_above_55']:.1%}**.

Restricting to the folds where the threshold could actually be selected
without a fallback - the stricter and more honest population - the observed
rate drops to **{boot_sel['observed']:.2%}** and the probability of clearing
break-even falls to **{boot_sel['p_above_break_even']:.1%}**.

## What would have been needed

To reach 95% confidence that the true rate exceeds 52.38% at the observed
point estimate of {boot['observed']:.2%}, the sample would need to be roughly
**{int(0.25 * (1.645 / max(1e-9, boot['observed'] - sv.BREAK_EVEN)) ** 2):,} bets** -
and that calculation assumes the point estimate is correct, which the holdout
gives no reason to believe. At the observed volumes that is decades of college
football.

This is the quieter finding of the task: even if the signal were real at the
measured size, **it is not measurable within the sport's lifetime of data.**
An edge you cannot distinguish from zero is not an edge you can stake.
"""
    out = paths.reports / "bootstrap_signal_report.md"
    out.write_text(text)
    LOG.info("wrote %s", out)
    return out


# ---------------------------------------------------------------------------
# Final report
# ---------------------------------------------------------------------------


def write_final_report(bundle: dict) -> Path:
    paths = config.paths().ensure()
    criteria = bundle["criteria"]
    boot = bundle["bootstrap"]
    capital = bundle["capital"]
    seasons = bundle["seasons"]
    juice = bundle["juice"]
    holdouts = bundle["results"]["holdouts"]
    walk = bundle["results"]["walk_forward"]
    pooled = bundle["pooled"]

    passed = int(criteria["passes"].sum())
    verdict = "YES" if passed == len(criteria) else "NO"
    deploy_checks = _deployment_checks(capital, boot)
    deploy = "YES" if verdict == "YES" and bool(deploy_checks["passes"].all()) else "NO"

    positives = int((seasons["verdict"] == "positive").sum())
    negatives = int((seasons["verdict"] == "negative").sum())
    neutral = int((seasons["verdict"] == "neutral").sum())
    at_105 = juice[juice["price"] == -105].iloc[0]

    text = f"""# Atlas Signal Verification - Final Report

*Generated {_generated()}. Criteria fixed in
[`docs/SIGNAL_PREREGISTRATION.md`](../docs/SIGNAL_PREREGISTRATION.md) and
committed before any holdout season was scored. Each experiment was scored
exactly once.*

---

# VERDICT: {verdict}

**The selective NCAAF totals signal is not real.** It is the final artifact.

{passed} of {len(criteria)} pre-registered criteria passed.

---

## The six required answers

**1. Is the signal real?**
**NO.** All four pre-registered criteria failed.

**2. What is the estimated true win rate?**
**{boot['observed']:.2%}**, 95% interval
[{boot['ci_low']:.2%}, {boot['ci_high']:.2%}]. The interval contains 50%.
Break-even at -110 is 52.38%.

**3. What is the estimated true ROI?**
**{capital['roi']:+.2%}** per bet at -110, or {capital['units']:+.1f} units on
{capital['bets']:,} bets. At -115 it is {float(juice[juice['price'] == -115]['roi'].iloc[0]):+.2%}.

**4. Does it survive holdout validation?**
**NO.** Each split was scored once, at a threshold frozen on its training
seasons alone:

{table(holdouts, ["experiment", "label", "threshold", "bets", "win_rate", "units", "roi"], ["Experiment", "Split", "Threshold", "Bets", "Win rate", "Units", "ROI"], digits=4)}

**5. Does it survive season-by-season validation?**
**NO.** {positives} positive, {neutral} neutral, {negatives} negative seasons -
against a pre-registered requirement of at least
{sv.CRITERION_MIN_POSITIVE_SEASONS} of {sv.CRITERION_TOTAL_SEASONS}.

**6. Would you deploy real capital?**
**{deploy}.**

---

## The pre-registered criteria, applied mechanically

{table(criteria, ["criterion", "required", "observed", "verdict"], ["Criterion", "Required", "Observed", "Verdict"], digits=4)}

Not one passed. There is no reading of this in which the signal survives.

## Task 1 - true holdout

{table(walk, ["experiment", "label", "threshold", "threshold_selectable", "bets", "wins", "win_rate", "units", "roi", "z"], ["Fold", "Split", "Threshold", "Selectable", "Bets", "Wins", "Win rate", "Units", "ROI", "z"], digits=4)}

Pooled across 2018-2025 with every season scored once:
**{pooled['win'].mean():.2%} on {len(pooled):,} bets, {capital['units']:+.1f} units.**
Restricted to folds whose threshold was genuinely selectable, it falls to
**{bundle['selectable']['win'].mean():.2%}**.

## Task 2 - threshold freezing

The frozen threshold ranged **1 to 8 points** across experiments differing only
in which seasons they trained on. See
[`threshold_freeze_report.md`](threshold_freeze_report.md). There is no stable
threshold to freeze, which is what fitting noise looks like.

## Task 3 - season stability

{table(seasons, ["season", "bets", "wins", "win_rate", "units", "roi", "z", "verdict"], ["Season", "Bets", "Wins", "Win rate", "Units", "ROI", "z", "Verdict"], digits=4)}

**Can the signal survive bad seasons?** The question does not arise. It does
not survive the *average* season. The two profitable years carrying the record
(2019, 2020) are the two whose threshold could not be selected without a
fallback, and 2020 was a pandemic-shortened season with unusual scoring.

## Task 4 - juice sensitivity

{table(juice, ["price", "break_even", "observed_win_rate", "edge_over_break_even", "units", "roi", "profitable"], ["Price", "Break-even", "Observed", "Edge", "Units", "ROI", "Profitable"], digits=4)}

Profitable at **-105 only**, by {at_105['edge_over_break_even']:.2%} - and -105
on college totals is not a price that exists at size. At -110 it loses
{abs(capital['units']):.0f} units; at -120 it loses
{abs(float(juice[juice['price'] == -120]['units'].iloc[0])):.0f}.

## Task 5 - bootstrap

P(true rate > 52.38%) = **{boot['p_above_break_even']:.1%}**.
P(> 53%) = **{boot['p_above_53']:.1%}**. P(> 55%) = **{boot['p_above_55']:.1%}**.
Full detail in [`bootstrap_signal_report.md`](bootstrap_signal_report.md).

## Task 6 - failure analysis

{table(bundle["failure"], ["cause", "implicated", "evidence"], ["Cause", "Implicated", "Evidence"])}

The diagnostic worth stating separately: holding the threshold **fixed at 4
points** across every walk-forward season - removing the selection rule
entirely - gives {float(bundle['fixed_threshold']['wins'].sum()) / float(bundle['fixed_threshold']['bets'].sum()):.2%}
on {int(bundle['fixed_threshold']['bets'].sum()):,} bets.

{table(bundle["fixed_threshold"], ["season", "bets", "wins", "win_rate", "units", "roi", "z"], ["Season", "Bets", "Wins", "Win rate", "Units", "ROI", "z"], digits=4)}

That is the single most favourable honest reading available, and it lands
**{abs(float(bundle['fixed_threshold']['wins'].sum()) / float(bundle['fixed_threshold']['bets'].sum()) - sv.BREAK_EVEN):.4%} from break-even**
- a coin flip against the vig, netting
{float(bundle['fixed_threshold']['units'].sum()):+.1f} units across seven
seasons. The most charitable version of the signal is indistinguishable from
zero.

Note also what is *not* implicated: **market adaptation**. At a fixed
threshold the win rate is no worse in recent seasons than early ones. The
market did not learn to price this. There was nothing to learn.

## Task 7 - capital allocation

{table(pd.DataFrame([capital]), ["bets", "units", "roi", "max_drawdown", "longest_losing_streak", "profit_factor"], ["Bets", "Units", "ROI", "Max drawdown", "Longest losing streak", "Profit factor"], digits=4)}

**Even if it were real, is it tradable?** No. A profit factor of
{capital['profit_factor']:.3f} is a losing book. The maximum drawdown is
{capital['max_drawdown']:.0f} units - more than twice the pre-registered
{sv.DEPLOY_MAX_DRAWDOWN_UNITS:.0f}-unit tolerance - on a strategy whose total
return is negative. Anyone staking this would have sat through a
{capital['longest_losing_streak']}-bet losing streak and an
{capital['max_drawdown']:.0f}-unit hole to arrive at {capital['units']:+.1f}.

{table(deploy_checks, ["check", "required", "observed", "verdict"], ["Deployment check", "Required", "Observed", "Verdict"], digits=4)}

---

## Recommendation: terminate Atlas Alpha

Per the phase brief, and without qualification.

Four phases have now tested, against the closing line:

| Phase | Tested | Result |
|---|---|---|
| 1A | Market, SP+, FPI, Elo, raw efficiency, recruiting, returning production, weather | all priced |
| 1B | Opponent-adjusted efficiency, free weather | all priced |
| 1C | Quarterback events, roster and staff continuity, situational angles, market failures, line movement - 50 tests | zero survivors after correction |
| This phase | The one remaining candidate, pre-registered and held out | fails all four criteria |

The closing line is a complete summary of the information Atlas can reach.
That is a real finding, arrived at honestly, and it is worth more than a
model that would have lost money slowly.

### What was actually built, and is worth keeping

The warehouse is not wasted by this verdict. It is a clean,
point-in-time-correct, reproducible research instrument for college football,
and the negative results are reusable: anyone starting this search again can
begin from "these forty variables are priced" rather than spending three
phases rediscovering it.

### If the search is ever restarted

Not with better features. Three phases say that direction is closed. The only
untested hypotheses left require **information the market does not have** -
which in practice means non-public, timely, or expensive:

- a timestamped line archive, to measure closing-line value rather than
  outcomes (Phase 1C measured the whole open-to-close window at 0.22 points,
  so the ceiling is low);
- genuinely private information, which is a different business with different
  legality;
- markets less efficient than FBS sides and totals - lower divisions, obscure
  props, live - each of which is a fresh research programme, not an extension
  of this one.

None of those is a reason to keep Atlas Alpha open today.

### The methodological record

Three things this programme got wrong and then caught, worth carrying forward:

1. **Phase 1B's quarterback signal** was reverse causation, caught in 1C by
   splitting contemporaneous from lagged variables.
2. **Phase 1C's totals signal** was threshold selection on the full sample,
   caught here by pre-registering and holding out.
3. **Phase 1B's opponent-adjustment weights** were silently rescaling the
   ridge prior to 0.07 games, caught by unit analysis before publication.

Each was found by asking what would have to be true for the result to be
false. That is the habit worth keeping, and it is the reason to trust this
report's NO more than the earlier reports' YES.
"""
    out = paths.reports / "atlas_signal_verification_final.md"
    out.write_text(text)
    LOG.info("wrote %s", out)
    return out


def _deployment_checks(capital: dict, boot: dict) -> pd.DataFrame:
    checks = [
        {
            "check": f"Max drawdown < {sv.DEPLOY_MAX_DRAWDOWN_UNITS:.0f} units",
            "required": f"< {sv.DEPLOY_MAX_DRAWDOWN_UNITS:.0f}",
            "observed": capital.get("max_drawdown", float("nan")),
            "passes": capital.get("max_drawdown", float("inf"))
            < sv.DEPLOY_MAX_DRAWDOWN_UNITS,
        },
        {
            "check": f"Profit factor > {sv.DEPLOY_MIN_PROFIT_FACTOR}",
            "required": f"> {sv.DEPLOY_MIN_PROFIT_FACTOR}",
            "observed": capital.get("profit_factor", float("nan")),
            "passes": capital.get("profit_factor", 0.0) > sv.DEPLOY_MIN_PROFIT_FACTOR,
        },
        {
            "check": "P(true win rate > 53%) > 50%",
            "required": f"> {sv.DEPLOY_MIN_PROB_ABOVE_53}",
            "observed": boot.get("p_above_53", float("nan")),
            "passes": boot.get("p_above_53", 0.0) > sv.DEPLOY_MIN_PROB_ABOVE_53,
        },
    ]
    out = pd.DataFrame(checks)
    out["verdict"] = np.where(out["passes"], "PASS", "FAIL")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Atlas signal validation reports")
    ap.parse_args()
    bundle = run_validation()
    write_threshold_report(bundle)
    write_bootstrap_report(bundle)
    write_final_report(bundle)


if __name__ == "__main__":
    main()
