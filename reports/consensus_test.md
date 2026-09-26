# Consensus test — result

Scored once against `docs/CONSENSUS_PREREGISTRATION.md`, with the constants of `atlas/research/consensus_validation.py`. College, FBS against FBS, regular season, week 5 on, against the closing spread. Owner page only.

## Decision

Q1 passes, Q2 does not. The consensus carries information but does not sharpen Atlas's selections. No rule; the consensus stays a label on the owner page.

## Coverage (read before any outcome)

| Season | Games | Any member | Elo | FPI projection | Enters |
|---|---|---|---|---|---|
| 2016 | 0 | 0.00% | 0.00% | 0.00% | no |
| 2017 | 0 | 0.00% | 0.00% | 0.00% | no |
| 2018 | 515 | 100.00% | 100.00% | 100.00% | yes |
| 2019 | 519 | 100.00% | 100.00% | 100.00% | yes |
| 2020 | 447 | 100.00% | 100.00% | 100.00% | yes |
| 2021 | 527 | 100.00% | 100.00% | 100.00% | yes |
| 2022 | 524 | 100.00% | 100.00% | 100.00% | yes |
| 2023 | 534 | 100.00% | 100.00% | 100.00% | yes |
| 2024 | 558 | 100.00% | 100.00% | 100.00% | yes |
| 2025 | 567 | 100.00% | 100.00% | 100.00% | yes |

Fitting seasons used: 2018, 2019, 2020. Holdout seasons scored: 2021, 2022, 2023, 2024, 2025. Dropped by the coverage rule: 2016, 2017.

## Implied-margin maps (fitting seasons only)

- Elo: margin = 0.0417 × (home Elo − away Elo) + 2.58 × home (1481 games)
- FPI projection: margin = 15.11 × Φ⁻¹(p) (1481 games)

## Q1: does the consensus know something the close does not?

(actual margin − close) = β × (consensus − close), over 2710 holdout games.

β = 0.1670, 95% interval 0.0100 to 0.3292: **pass** (the lower bound must be above 0).

### Q1b: the consensus's strongest 10% each season, its side against the close

| Criterion | Result | |
|---|---|---|
| 1. pooled win rate > 52.38% | 50.94% of 265 | **fail** |
| 2. 95% interval lower bound > 50.0% | 44.91% (95% interval 44.91% to 56.98%) | **fail** |
| 3. at least 4 holdout seasons above 52.38% | 2 of 5 | **fail** |
| 4. positive units at -115 | -12.6 units (at -110: -7.3) | **fail** |

| Season | Win rate | n |
|---|---|---|
| 2021 | 41.18% | 51 |
| 2022 | 50.00% | 52 |
| 2023 | 52.83% | 53 |
| 2024 | 60.38% | 53 |
| 2025 | 50.00% | 56 |

All four required: ****fail****. Q1b does not change the decision; it is the tradable version of Q1, reported as pre-registered.

## Q2: does agreement make Atlas's strongest spread disagreements better?

Atlas's strongest 10% each season, where the consensus is on the same side of the close:

| Criterion | Result | |
|---|---|---|
| 1. pooled win rate > 52.38% | 50.00% of 248 | **fail** |
| 2. 95% interval lower bound > 50.0% | 43.55% (95% interval 43.55% to 56.05%) | **fail** |
| 3. at least 4 holdout seasons above 52.38% | 2 of 5 | **fail** |
| 4. positive units at -115 | -16.2 units (at -110: -11.3) | **fail** |

| Season | Win rate | n |
|---|---|---|
| 2021 | 53.49% | 43 |
| 2022 | 53.06% | 49 |
| 2023 | 41.67% | 48 |
| 2024 | 51.85% | 54 |
| 2025 | 50.00% | 54 |

Where it disagrees: 61.11% of 18. Selected but without a consensus, so in neither group: 0.

Agree minus disagree, 95% interval -33.25% to 12.32% (the lower bound must be above 0).

Both required: ****fail****. Power was stated in advance: this population is small, so a fail here means not shown, not absent.

## Conventions

Bootstrap of 10,000 resamples by game, percentile intervals, seed 20260926. Pushes are no action. A win at -110 returns +0.909 units and a loss costs 1.000.
