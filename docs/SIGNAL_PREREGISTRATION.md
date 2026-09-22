# Atlas Signal Validation - Pre-registration

**Committed before any holdout season was scored.** The git history is the
evidence: this file and `atlas/research/signal_validation.py`'s constants land
in a commit of their own, and the results commit comes after.

The point of a falsification phase is that the person running it cannot move
the goalposts afterwards. Everything below is fixed in advance.

---

## What is being tested

The only candidate surviving Phases 1A-1C: **selective NCAAF totals**. Atlas's
opponent-adjusted totals model disagrees with the closing total by some amount;
the claim is that betting the side of the disagreement, above some threshold,
wins at better than the break-even rate.

Phase 1C measured 52.0% flat rising to 53.9% at an 8-point cut, **after
scanning eight thresholds on the full sample**. That scan is the bias this
phase exists to remove.

## The model (frozen)

The Phase 1B totals model, unchanged. Twelve opponent-adjusted efficiency sums
plus raw pace and plays-per-game:

```
adj_off_epa_sum, adj_def_epa_sum, adj_success_rate_sum,
adj_def_success_rate_sum, adj_explosiveness_sum, adj_def_explosiveness_sum,
adj_havoc_sum, adj_havoc_allowed_sum, adj_finishing_drives_sum,
adj_def_finishing_drives_sum, adj_pace_sum, adj_def_pace_sum,
pace_sum, plays_per_game_sum
```

Estimator: ridge on standardised features, alpha = 1.0. **No new features may
be added during this phase.** No feature selection of any kind.

## Threshold selection rule (frozen)

For each experiment the threshold is chosen **using training seasons only**,
by inner leave-one-season-out cross-validation *within* the training set. The
holdout is never touched during selection.

The rule, fixed in advance:

> Over the grid **{1, 2, 3, 4, 5, 6, 7, 8}** points, choose the threshold that
> maximises **expected units at -110** on the inner-CV training predictions,
> subject to a minimum of **500 training bets**. Ties break to the *lower*
> threshold (more volume, less selection pressure).

Rationale for maximising units rather than win rate: win rate alone is
maximised by the sparsest cut, which is precisely the overfitting this phase
is meant to prevent. The 500-bet floor exists for the same reason.

## Experiments (frozen)

| | Train | Test |
|---|---|---|
| A | 2018-2024 | 2025 |
| B | 2018-2023 | 2024 |
| C | 2019-2025 | 2018 |
| D | rolling walk-forward: fit on all prior seasons, predict the next, 2019 through 2025 |

Each experiment is scored **once**. No re-runs with a different threshold.

## Pre-registered decision criteria

The signal is declared **REAL** only if **all four** hold on the pooled
holdout results (Experiments A, B, C, and D's walk-forward, each scored once):

1. **Pooled holdout win rate > 52.38%** (break-even at -110).
2. **Lower bound of the 95% bootstrap CI on the pooled holdout win rate >
   50.0%.** A signal whose interval includes a coin flip is not a signal.
3. **At least 5 of the 7 walk-forward seasons above 52.38%.** A genuine edge
   should not require the good years.
4. **Positive expected units at -115.** Real college-totals juice is routinely
   worse than -110; an edge that only exists at the best available price is
   not tradable.

Anything less than all four is a **NO**. There is no partial credit, no
"promising", and no "with further work".

## Pre-registered deployment criteria

Even if the signal is declared real, capital is recommended only if
additionally:

5. **Maximum drawdown < 40 units** on flat 1-unit staking across the holdout.
6. **Profit factor > 1.05.**
7. **Probability(true win rate > 53.0%) > 50%** from the bootstrap.

## What counts as failure, and what it means

If criteria 1-4 fail, the recommendation is **termination of Atlas Alpha**.
Not "iterate", not "try different features" - the phase brief is explicit, and
so is the logic: three phases have found every public variable priced, and
this was the last candidate.

## Statistical conventions

- Break-even rates: -105 → 51.22%, -110 → 52.38%, -115 → 53.49%, -120 → 54.55%.
- A win at -110 returns +0.909 units; a loss costs 1.000.
- Bootstrap: 10,000 resamples, percentile intervals, seed 20180101.
- Pushes (actual total exactly equal to the closing total) are excluded from
  win rate and staked as no action.
