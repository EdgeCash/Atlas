# DFS player projections

Atlas's own player model (`atlas/dfs/model.py`, step 3 of `docs/MODEL_PLAN_DFS.md`): the step 2 baseline, corrected by one gradient-boosted model per position that reads the game Atlas's own game model projected, each player's role from his earlier games, and the week's injury report and depth chart. No outside projection and no market number is an input. Walk-forward: every season predicted from the seasons before it. Scored on players who recorded a stat, beside the step 2 benchmarks on the same rows.

## The gate, 2015-2021, each team's regulars: does not pass

Beat the baseline's CRPS at every position, and rank each position's regulars at least as well as DraftKings' salary does. `rank gap se` is the standard error of the model-minus-salary rank correlation, paired week by week.

| position | crps model | crps baseline | rank model | rank salary | rank gap se | beats baseline | ranks as well as salary |
|---|---|---|---|---|---|---|---|
| DST | 3.280 | 3.322 | 0.241 | 0.243 | 0.013 | yes | no |
| QB | 4.614 | 4.746 | 0.315 | 0.330 | 0.011 | yes | no |
| RB | 4.145 | 4.227 | 0.524 | 0.506 | 0.007 | yes | yes |
| TE | 3.580 | 3.614 | 0.423 | 0.403 | 0.008 | yes | yes |
| WR | 4.164 | 4.242 | 0.492 | 0.484 | 0.004 | yes | yes |

Short of salary's ranking at: DST, QB.

## Where the gap is: the game environment

A diagnostic, not the model. The same model refitted with the closing line's team totals (half the total, plus or minus half the spread) as two more inputs:

| position | crps model | crps baseline | rank model | rank salary | rank gap se | beats baseline | ranks as well as salary |
|---|---|---|---|---|---|---|---|
| DST | 3.251 | 3.322 | 0.270 | 0.243 | 0.011 | yes | yes |
| QB | 4.576 | 4.746 | 0.341 | 0.330 | 0.011 | yes | yes |
| RB | 4.140 | 4.227 | 0.523 | 0.506 | 0.007 | yes | yes |
| TE | 3.578 | 3.614 | 0.420 | 0.403 | 0.008 | yes | yes |
| WR | 4.163 | 4.242 | 0.493 | 0.484 | 0.004 | yes | yes |

And each team's projected points alone, as a ranking of that team's regulars against the week's others:

| position | Atlas team points | closing-line team points |
|---|---|---|
| DST | 0.143 | 0.151 |
| QB | 0.258 | 0.321 |
| RB | 0.071 | 0.095 |
| TE | 0.129 | 0.160 |
| WR | 0.096 | 0.121 |

What salary knows that the model does not is mostly the market's view of the game. Atlas's player model is not the constraint; Atlas's game model is.

## Salary era, 2015-2021, regulars

| model | player-weeks | mae | crps | rank corr |
|---|---|---|---|---|
| model | 28808 | 5.662 | 4.032 | 0.399 |
| baseline | 28808 | 5.769 | 4.107 | 0.367 |
| salary | 28808 | 5.833 | 4.148 | 0.393 |

### By position

| position | model | player-weeks | mae | crps | rank corr |
|---|---|---|---|---|---|
| DST | model | 3616 | 4.632 | 3.280 | 0.241 |
| DST | baseline | 3616 | 4.652 | 3.322 | 0.131 |
| DST | salary | 3616 | 4.702 | 3.311 | 0.243 |
| QB | model | 3607 | 6.512 | 4.614 | 0.315 |
| QB | baseline | 3607 | 6.696 | 4.746 | 0.297 |
| QB | salary | 3607 | 6.766 | 4.858 | 0.330 |
| RB | model | 7187 | 5.774 | 4.145 | 0.524 |
| RB | baseline | 7187 | 5.905 | 4.227 | 0.510 |
| RB | salary | 7187 | 6.055 | 4.288 | 0.506 |
| TE | model | 3600 | 4.992 | 3.580 | 0.423 |
| TE | baseline | 3600 | 5.051 | 3.614 | 0.413 |
| TE | salary | 3600 | 5.093 | 3.686 | 0.403 |
| WR | model | 10798 | 5.872 | 4.164 | 0.492 |
| WR | baseline | 10798 | 5.983 | 4.242 | 0.481 |
| WR | salary | 10798 | 5.998 | 4.252 | 0.484 |

### By season

| season | model | player-weeks | mae | crps | rank corr |
|---|---|---|---|---|---|
| 2015 | model | 4087 | 5.816 | 4.148 | 0.362 |
| 2015 | baseline | 4087 | 5.857 | 4.184 | 0.352 |
| 2015 | salary | 4087 | 5.990 | 4.304 | 0.358 |
| 2016 | model | 4078 | 5.514 | 3.922 | 0.403 |
| 2016 | baseline | 4078 | 5.630 | 4.000 | 0.369 |
| 2016 | salary | 4078 | 5.671 | 4.035 | 0.407 |
| 2017 | model | 4077 | 5.464 | 3.881 | 0.363 |
| 2017 | baseline | 4077 | 5.539 | 3.945 | 0.339 |
| 2017 | salary | 4077 | 5.655 | 4.029 | 0.357 |
| 2018 | model | 4077 | 5.736 | 4.091 | 0.422 |
| 2018 | baseline | 4077 | 5.846 | 4.176 | 0.367 |
| 2018 | salary | 4077 | 5.816 | 4.160 | 0.415 |
| 2019 | model | 4073 | 5.796 | 4.146 | 0.410 |
| 2019 | baseline | 4073 | 5.939 | 4.238 | 0.377 |
| 2019 | salary | 4073 | 5.931 | 4.235 | 0.404 |
| 2020 | model | 4077 | 5.681 | 4.046 | 0.417 |
| 2020 | baseline | 4077 | 5.808 | 4.127 | 0.385 |
| 2020 | salary | 4077 | 5.940 | 4.211 | 0.408 |
| 2021 | model | 4339 | 5.629 | 3.989 | 0.416 |
| 2021 | baseline | 4339 | 5.765 | 4.083 | 0.377 |
| 2021 | salary | 4339 | 5.825 | 4.067 | 0.402 |

## 2022-2025, regulars (no salaries; every game-model setting tuned on earlier seasons only)

| position | model | player-weeks | mae | crps | rank corr |
|---|---|---|---|---|---|
| DST | model | 2174 | 4.346 | 3.080 | 0.233 |
| DST | baseline | 2174 | 4.420 | 3.155 | 0.111 |
| QB | model | 2174 | 6.409 | 4.570 | 0.312 |
| QB | baseline | 2174 | 6.636 | 4.726 | 0.292 |
| RB | model | 4339 | 5.463 | 3.868 | 0.589 |
| RB | baseline | 4339 | 5.639 | 3.991 | 0.563 |
| TE | model | 2168 | 4.825 | 3.437 | 0.416 |
| TE | baseline | 2168 | 4.923 | 3.494 | 0.386 |
| WR | model | 6505 | 5.651 | 3.989 | 0.520 |
| WR | baseline | 6505 | 5.838 | 4.108 | 0.495 |

## Caveats

- **The game model's history.** The environment is Atlas's NFL game model run from 2011. From 2020 each season uses settings tuned on earlier seasons only; before 2020 it uses 2020's, tuned on 2017-2019 - a look-ahead of four smoothing constants, not of results, for those three seasons. The 2022-2025 table carries no such caveat.
- **The wind** is the recorded game-time wind; live, it is the forecast, which is close by kickoff and less so earlier in the week.
- **The model's settings** (the boosting's size, the starters-only quarterback rows) were chosen on 2015-2021, the seasons this gate scores, from four candidates. The 2022-2025 table is the unchosen test.
