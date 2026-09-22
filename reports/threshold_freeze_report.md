# Threshold Freeze Report (Signal Validation, Task 2)

*Generated 2026-09-22 16:05 UTC. Selection rule fixed in advance -
see [`docs/SIGNAL_PREREGISTRATION.md`](../docs/SIGNAL_PREREGISTRATION.md),
committed before any holdout season was scored.*

## The bias this removes

Phase 1C evaluated eight thresholds - 0, 1, 2, 3, 4, 6, 8, 10 - **on the full
sample**, then reported the best-looking cut. That is selection bias with a
known direction: the maximum of eight noisy estimates is biased upward whether
or not any signal exists.

This phase picks **one** threshold per experiment, using training seasons only,
by a rule written down in advance:

> Over the grid {1, 2, 3, 4, 5, 6, 7, 8}, choose the threshold that maximises
> expected units at -110 on inner leave-one-season-out predictions *within the
> training set*, subject to at least 500 training bets. Ties
> break to the lower threshold.

Maximising units rather than win rate is deliberate: win rate alone is
maximised by the sparsest cut, which is the overfitting the phase exists to
prevent. The bet floor exists for the same reason.

## The result, and it is the finding

| Experiment | Training seasons | n | Frozen threshold | Selectable | Holdout bets | Holdout win rate |
|---|---|---|---|---|---|---|
| A | 2018-2024 | 7 | 8 | yes | 42 | 0.5000 |
| B | 2018-2023 | 6 | 7 | yes | 88 | 0.5568 |
| C | 2019-2025 | 7 | 1 | yes | 597 | 0.4891 |
| WF2019 | 2018-2018 | 1 | 1 | no | 587 | 0.5332 |
| WF2020 | 2018-2019 | 2 | 1 | no | 427 | 0.5831 |
| WF2021 | 2018-2020 | 3 | 1 | yes | 645 | 0.4946 |
| WF2022 | 2018-2021 | 4 | 6 | yes | 317 | 0.4700 |
| WF2023 | 2018-2022 | 5 | 7 | yes | 122 | 0.5492 |
| WF2024 | 2018-2023 | 6 | 7 | yes | 88 | 0.5568 |
| WF2025 | 2018-2024 | 7 | 8 | yes | 42 | 0.5000 |

**The frozen threshold ranges 1 to 8 points across experiments that differ
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

### Experiment A - train 2018-2024

| Threshold | Training bets | Win rate | Units | ROI | Frozen |
|---|---|---|---|---|---|
| 1 | 4,148 | 0.5205 | -26.2727 | -0.0063 | no |
| 2 | 3,426 | 0.5196 | -27.8182 | -0.0081 | no |
| 3 | 2,746 | 0.5193 | -23.6364 | -0.0086 | no |
| 4 | 2,144 | 0.5266 | 11.3636 | 0.0053 | no |
| 5 | 1,632 | 0.5221 | -5.4545 | -0.0033 | no |
| 6 | 1,192 | 0.5252 | 3.0909 | 0.0026 | no |
| 7 | 879 | 0.5301 | 10.6364 | 0.0121 | no |
| 8 | 616 | 0.5422 | 21.6364 | 0.0351 | yes |

**Frozen at 8 points.**

### Experiment B - train 2018-2023

| Threshold | Training bets | Win rate | Units | ROI | Frozen |
|---|---|---|---|---|---|
| 1 | 3,506 | 0.5177 | -41.0000 | -0.0117 | no |
| 2 | 2,875 | 0.5113 | -68.6364 | -0.0239 | no |
| 3 | 2,325 | 0.5114 | -55.0909 | -0.0237 | no |
| 4 | 1,826 | 0.5181 | -20.0000 | -0.0110 | no |
| 5 | 1,374 | 0.5153 | -22.3636 | -0.0163 | no |
| 6 | 1,015 | 0.5261 | 4.4545 | 0.0044 | no |
| 7 | 766 | 0.5313 | 11.0000 | 0.0144 | yes |
| 8 | 543 | 0.5193 | -4.6364 | -0.0085 | no |

**Frozen at 7 points.**

### Experiment C - train 2019-2025

| Threshold | Training bets | Win rate | Units | ROI | Frozen |
|---|---|---|---|---|---|
| 1 | 4,205 | 0.5284 | 37.0000 | 0.0088 | yes |
| 2 | 3,405 | 0.5222 | -10.6364 | -0.0031 | no |
| 3 | 2,707 | 0.5275 | 19.1818 | 0.0071 | no |
| 4 | 2,092 | 0.5320 | 32.8182 | 0.0157 | no |
| 5 | 1,568 | 0.5274 | 10.8182 | 0.0069 | no |
| 6 | 1,168 | 0.5214 | -5.3636 | -0.0046 | no |
| 7 | 835 | 0.5210 | -4.5455 | -0.0054 | no |
| 8 | 566 | 0.5389 | 16.2727 | 0.0288 | no |

**Frozen at 1 points.**


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
