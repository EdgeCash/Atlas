# Bootstrap Signal Report (Signal Validation, Task 5)

*Generated 2026-09-22 16:05 UTC. 10,000 resamples, percentile intervals,
seed 20180101.*

## Method

Each bet is one Bernoulli trial and the bootstrap resamples **bets**, not
seasons. That is the more generous choice: resampling seasons would widen the
interval considerably, because the season-to-season swing is larger than
independent bets would produce. The signal fails on the generous version.

Population: the pooled true holdout - Experiment C covering 2018 plus the
walk-forward covering 2019-2025, so every season is scored exactly once and no
game is counted twice.

## Results

| Population | Bets | Observed | Bootstrap mean | 95% CI low | 95% CI high |
|---|---|---|---|---|---|
| Pooled holdout (2018-2025, each season once) | 2,825 | 0.5165 | 0.5166 | 0.4981 | 0.5349 |
| Selectable thresholds only (excludes 2019, 2020) | 1,811 | 0.4953 | 0.4950 | 0.4721 | 0.5185 |

## Probability the true win rate exceeds each bar

| Population | P(> 50%) | P(> 52.38%) | P(> 53%) | P(> 54%) | P(> 55%) |
|---|---|---|---|---|---|
| Pooled holdout (2018-2025, each season once) | 0.9599 | 0.2219 | 0.0705 | 0.0061 | 0.0001 |
| Selectable thresholds only (excludes 2019, 2020) | 0.3340 | 0.0076 | 0.0013 | 0.0001 | 0.0000 |

## Reading it

The pooled holdout observed **51.65%** on 2,825 bets,
with a 95% interval of **[49.81%, 53.49%]**.

- The interval **contains 50%**. A coin flip is inside the range of plausible
  true values.
- The probability the true rate clears the -110 break-even is
  **22.2%** - worse than a coin flip on the
  question "is this profitable at all".
- The probability it clears 53%, roughly the rate a tradable edge would need
  once real juice and limits are priced, is **7.0%**.
- The probability it clears 55%, the rate that would make this a business, is
  **0.0%**.

Restricting to the folds where the threshold could actually be selected
without a fallback - the stricter and more honest population - the observed
rate drops to **49.53%** and the probability of clearing
break-even falls to **0.8%**.

## What would have been needed

To reach 95% confidence that the true rate exceeds 52.38% at the observed
point estimate of 51.65%, the sample would need to be roughly
**676,506,250,000,000,000 bets** -
and that calculation assumes the point estimate is correct, which the holdout
gives no reason to believe. At the observed volumes that is decades of college
football.

This is the quieter finding of the task: even if the signal were real at the
measured size, **it is not measurable within the sport's lifetime of data.**
An edge you cannot distinguish from zero is not an edge you can stake.
