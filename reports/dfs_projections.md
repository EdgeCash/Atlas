# DFS player projections

Atlas's player model (`atlas/dfs/model.py`, step 3 of `docs/MODEL_PLAN_DFS.md`): the step 2 baseline, corrected by one gradient-boosted model per position that reads the game as Atlas's own game model projected it and as the line implies it, each player's role from his earlier games, and the week's injury report and depth chart. No outside projection is an input. Walk-forward: every season predicted from the seasons before it. Scored on players who recorded a stat, beside the step 2 benchmarks on the same rows.

## The gate, 2015-2021, each team's regulars: passes

Beat the baseline's CRPS at every position, and rank each position's regulars at least as well as DraftKings' salary does. `rank gap se` is the standard error of the model-minus-salary rank correlation, paired week by week.

| position | crps model | crps baseline | rank model | rank salary | rank gap se | beats baseline | ranks as well as salary |
|---|---|---|---|---|---|---|---|
| DST | 3.229 | 3.354 | 0.284 | 0.243 | 0.012 | yes | yes |
| QB | 4.576 | 4.746 | 0.341 | 0.330 | 0.011 | yes | yes |
| RB | 4.140 | 4.227 | 0.523 | 0.506 | 0.007 | yes | yes |
| TE | 3.578 | 3.614 | 0.420 | 0.403 | 0.008 | yes | yes |
| WR | 4.163 | 4.242 | 0.493 | 0.484 | 0.004 | yes | yes |

## Without the market

The same model with the line's team totals left out - Atlas's game model the only view of the game. It beat the baseline everywhere but fell short of salary's ranking at quarterback and defense:

| position | crps model | crps baseline | rank model | rank salary | rank gap se | beats baseline | ranks as well as salary |
|---|---|---|---|---|---|---|---|
| DST | 3.237 | 3.354 | 0.276 | 0.243 | 0.012 | yes | yes |
| QB | 4.614 | 4.746 | 0.315 | 0.330 | 0.011 | yes | no |
| RB | 4.145 | 4.227 | 0.524 | 0.506 | 0.007 | yes | yes |
| TE | 3.580 | 3.614 | 0.423 | 0.403 | 0.008 | yes | yes |
| WR | 4.164 | 4.242 | 0.492 | 0.484 | 0.004 | yes | yes |

Each team's projected points alone, as a ranking of its regulars against the week's others, show why: the line knows more about how many points a team will score than Atlas's game model does, and salary carries that knowledge.

| position | Atlas team points | line's team points |
|---|---|---|
| DST | 0.143 | 0.151 |
| QB | 0.258 | 0.321 |
| RB | 0.071 | 0.095 |
| TE | 0.129 | 0.160 |
| WR | 0.096 | 0.121 |

## Ranges, 2015-2021, each team's regulars: the gate passes

Each projection carries a range from its 10th to its 90th percentile (`atlas/dfs/ranges.py`): per position, a linear quantile regression of the model's out-of-sample misses on the projection, fitted on the seasons before. DraftKings points are lopsided - a floor near zero, a long tail of touchdown weeks - so the two ends are fitted separately rather than drawn as a normal curve. The gate (plan §7, step 4): the 80% range holds 76%-84% of outcomes at every position. Overall: 80.3%. `below` and `above` should each be near 10%; `width` is the range in points.

| position | player-weeks | coverage | below | above | width |
|---|---|---|---|---|---|
| DST | 3616 | 80.1% | 9.8% | 10.1% | 14.4 |
| QB | 3607 | 81.0% | 7.5% | 11.5% | 21.3 |
| RB | 7187 | 80.0% | 7.6% | 12.5% | 17.8 |
| TE | 3600 | 81.2% | 6.9% | 12.0% | 15.6 |
| WR | 10798 | 79.9% | 8.8% | 11.3% | 18.4 |

### Everyone who played, 2015-2021

| position | player-weeks | coverage | below | above | width |
|---|---|---|---|---|---|
| DST | 3616 | 80.1% | 9.8% | 10.1% | 14.4 |
| QB | 4256 | 77.4% | 12.6% | 9.9% | 21.2 |
| RB | 11094 | 80.5% | 9.1% | 10.4% | 15.0 |
| TE | 7863 | 81.6% | 8.7% | 9.7% | 12.2 |
| WR | 15649 | 80.7% | 9.1% | 10.1% | 15.9 |

### Regulars, 2022-2025

| position | player-weeks | coverage | below | above | width |
|---|---|---|---|---|---|
| DST | 2174 | 82.3% | 9.3% | 8.4% | 14.2 |
| QB | 2174 | 83.1% | 6.9% | 10.0% | 22.0 |
| RB | 4339 | 80.1% | 9.3% | 10.6% | 17.7 |
| TE | 2168 | 80.9% | 7.8% | 11.3% | 15.5 |
| WR | 6505 | 80.2% | 10.0% | 9.7% | 18.1 |

### Regulars by season

| season | player-weeks | coverage | below | above | width |
|---|---|---|---|---|---|
| 2015 | 4087 | 78.9% | 8.5% | 12.6% | 17.4 |
| 2016 | 4078 | 82.0% | 7.6% | 10.5% | 17.9 |
| 2017 | 4077 | 81.2% | 8.1% | 10.7% | 17.6 |
| 2018 | 4077 | 79.6% | 8.4% | 11.9% | 17.7 |
| 2019 | 4073 | 79.4% | 8.6% | 11.9% | 17.9 |
| 2020 | 4077 | 80.9% | 7.7% | 11.5% | 17.9 |
| 2021 | 4339 | 79.9% | 8.5% | 11.6% | 17.8 |
| 2022 | 4329 | 79.9% | 10.0% | 10.0% | 17.9 |
| 2023 | 4342 | 81.8% | 8.4% | 9.8% | 17.6 |
| 2024 | 4340 | 80.8% | 8.7% | 10.5% | 17.7 |
| 2025 | 4349 | 81.0% | 9.2% | 9.8% | 17.4 |

## Defenses

A defense's projection is the average of the player model's and one built from its parts (`atlas/dfs/defense.py`): expected sacks, takeaways and return touchdowns, each a Poisson rate on the defense's form, the opposing offense's and both teams' projected points; the league's rate for safeties, blocks and returned conversions; and DraftKings' points-allowed bonus averaged over the spread of the opponent's score. Chosen on 2015-2021 from three candidates (the player model alone, the parts alone, the average); 2022-2025 is the unchosen test.

| seasons | projection | mae | rank corr |
|---|---|---|---|
| 2015-2021 | blend (published) | 4.560 | 0.284 |
| 2015-2021 | parts alone | 4.575 | 0.283 |
| 2015-2021 | baseline | 4.753 | 0.132 |
| 2022-2025 | blend (published) | 4.296 | 0.297 |
| 2022-2025 | parts alone | 4.309 | 0.303 |
| 2022-2025 | baseline | 4.476 | 0.111 |

## Salary era, 2015-2021, regulars

| model | player-weeks | mae | crps | rank corr |
|---|---|---|---|---|
| model | 28808 | 5.643 | 4.018 | 0.412 |
| baseline | 28808 | 5.782 | 4.111 | 0.367 |
| salary | 28808 | 5.833 | 4.148 | 0.393 |

### By position

| position | model | player-weeks | mae | crps | rank corr |
|---|---|---|---|---|---|
| DST | model | 3616 | 4.560 | 3.229 | 0.284 |
| DST | baseline | 3616 | 4.753 | 3.354 | 0.132 |
| DST | salary | 3616 | 4.702 | 3.311 | 0.243 |
| QB | model | 3607 | 6.457 | 4.576 | 0.341 |
| QB | baseline | 3607 | 6.696 | 4.746 | 0.297 |
| QB | salary | 3607 | 6.766 | 4.858 | 0.330 |
| RB | model | 7187 | 5.767 | 4.140 | 0.523 |
| RB | baseline | 7187 | 5.905 | 4.227 | 0.510 |
| RB | salary | 7187 | 6.055 | 4.288 | 0.506 |
| TE | model | 3600 | 4.989 | 3.578 | 0.420 |
| TE | baseline | 3600 | 5.051 | 3.614 | 0.413 |
| TE | salary | 3600 | 5.093 | 3.686 | 0.403 |
| WR | model | 10798 | 5.869 | 4.163 | 0.493 |
| WR | baseline | 10798 | 5.983 | 4.242 | 0.481 |
| WR | salary | 10798 | 5.998 | 4.252 | 0.484 |

### By season

| season | model | player-weeks | mae | crps | rank corr |
|---|---|---|---|---|---|
| 2015 | model | 4087 | 5.788 | 4.133 | 0.374 |
| 2015 | baseline | 4087 | 5.871 | 4.187 | 0.352 |
| 2015 | salary | 4087 | 5.990 | 4.304 | 0.358 |
| 2016 | model | 4078 | 5.499 | 3.912 | 0.420 |
| 2016 | baseline | 4078 | 5.647 | 4.008 | 0.369 |
| 2016 | salary | 4078 | 5.671 | 4.035 | 0.407 |
| 2017 | model | 4077 | 5.435 | 3.861 | 0.391 |
| 2017 | baseline | 4077 | 5.549 | 3.946 | 0.339 |
| 2017 | salary | 4077 | 5.655 | 4.029 | 0.357 |
| 2018 | model | 4077 | 5.715 | 4.076 | 0.431 |
| 2018 | baseline | 4077 | 5.859 | 4.179 | 0.367 |
| 2018 | salary | 4077 | 5.816 | 4.160 | 0.415 |
| 2019 | model | 4073 | 5.776 | 4.131 | 0.429 |
| 2019 | baseline | 4073 | 5.949 | 4.241 | 0.377 |
| 2019 | salary | 4073 | 5.931 | 4.235 | 0.404 |
| 2020 | model | 4077 | 5.658 | 4.030 | 0.425 |
| 2020 | baseline | 4077 | 5.826 | 4.134 | 0.385 |
| 2020 | salary | 4077 | 5.940 | 4.211 | 0.408 |
| 2021 | model | 4339 | 5.632 | 3.988 | 0.416 |
| 2021 | baseline | 4339 | 5.773 | 4.086 | 0.377 |
| 2021 | salary | 4339 | 5.825 | 4.067 | 0.402 |

## 2022-2025, regulars (no salaries; every game-model setting tuned on earlier seasons only)

| position | model | player-weeks | mae | crps | rank corr |
|---|---|---|---|---|---|
| DST | model | 2174 | 4.296 | 3.037 | 0.297 |
| DST | baseline | 2174 | 4.476 | 3.176 | 0.111 |
| QB | model | 2174 | 6.337 | 4.523 | 0.340 |
| QB | baseline | 2174 | 6.636 | 4.726 | 0.292 |
| RB | model | 4339 | 5.454 | 3.863 | 0.590 |
| RB | baseline | 4339 | 5.639 | 3.991 | 0.563 |
| TE | model | 2168 | 4.816 | 3.433 | 0.414 |
| TE | baseline | 2168 | 4.923 | 3.494 | 0.386 |
| WR | model | 6505 | 5.648 | 3.987 | 0.521 |
| WR | baseline | 6505 | 5.838 | 4.108 | 0.495 |

## Caveats

- **The game model's history.** The environment is Atlas's NFL game model run from 2011. From 2020 each season uses settings tuned on earlier seasons only; before 2020 it uses 2020's, tuned on 2017-2019 - a look-ahead of four smoothing constants, not of results, for those three seasons. The 2022-2025 table carries no such caveat.
- **The line** is the closing line for past games; live, it is the line as it stands at the refresh, which moves toward the close through the week.
- **The wind** is the recorded game-time wind; live, it is the forecast, which is close by kickoff and less so earlier in the week.
- **The model's settings** (the boosting's size, the starters-only quarterback rows) were chosen on 2015-2021, the seasons this gate scores, from four candidates. The 2022-2025 table is the unchosen test.
