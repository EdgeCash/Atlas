# DFS benchmarks

The two numbers the player model has to beat (`atlas/dfs/benchmarks.py`, step 2 of `docs/MODEL_PLAN_DFS.md`), walk-forward: every season predicted from the seasons before it only. `baseline` is each player's recent DraftKings points, pulled toward his position's average by a fitted amount; `salary` is DraftKings' price mapped to points by a line per position. The target is DraftKings' recorded points. Scored on player-weeks where the player recorded a stat (inactive players are the injury report's question, step 3). Lower MAE and CRPS are better; higher rank correlation (within each position's week) is better, and it is the figure the optimizer lives on.

## Salary era, 2015-2021: each team's regulars

Each team's top quarterback, two running backs, three receivers and tight end by salary, and every defense: the pool a lineup is built from.

| model | player-weeks | mae | crps | rank corr |
|---|---|---|---|---|
| baseline | 28808 | 5.769 | 4.107 | 0.367 |
| salary | 28808 | 5.833 | 4.148 | 0.393 |

### By position

| position | model | player-weeks | mae | crps | rank corr |
|---|---|---|---|---|---|
| DST | baseline | 3616 | 4.652 | 3.322 | 0.131 |
| DST | salary | 3616 | 4.702 | 3.311 | 0.243 |
| QB | baseline | 3607 | 6.696 | 4.746 | 0.297 |
| QB | salary | 3607 | 6.766 | 4.858 | 0.330 |
| RB | baseline | 7187 | 5.905 | 4.227 | 0.510 |
| RB | salary | 7187 | 6.055 | 4.288 | 0.506 |
| TE | baseline | 3600 | 5.051 | 3.614 | 0.413 |
| TE | salary | 3600 | 5.093 | 3.686 | 0.403 |
| WR | baseline | 10798 | 5.983 | 4.242 | 0.481 |
| WR | salary | 10798 | 5.998 | 4.252 | 0.484 |

### By season

| season | model | player-weeks | mae | crps | rank corr |
|---|---|---|---|---|---|
| 2015 | baseline | 4087 | 5.857 | 4.184 | 0.352 |
| 2015 | salary | 4087 | 5.990 | 4.304 | 0.358 |
| 2016 | baseline | 4078 | 5.630 | 4.000 | 0.369 |
| 2016 | salary | 4078 | 5.671 | 4.035 | 0.407 |
| 2017 | baseline | 4077 | 5.539 | 3.945 | 0.339 |
| 2017 | salary | 4077 | 5.655 | 4.029 | 0.357 |
| 2018 | baseline | 4077 | 5.846 | 4.176 | 0.367 |
| 2018 | salary | 4077 | 5.816 | 4.160 | 0.415 |
| 2019 | baseline | 4073 | 5.939 | 4.238 | 0.377 |
| 2019 | salary | 4073 | 5.931 | 4.235 | 0.404 |
| 2020 | baseline | 4077 | 5.808 | 4.127 | 0.385 |
| 2020 | salary | 4077 | 5.940 | 4.211 | 0.408 |
| 2021 | baseline | 4339 | 5.765 | 4.083 | 0.377 |
| 2021 | salary | 4339 | 5.825 | 4.067 | 0.402 |

### Everyone who played, by position

The fringe - a minimum-salary backup with one catch - is most of these rows; the baseline reads a player's own tiny history and a straight salary line cannot, so this view flatters the baseline.

| position | model | player-weeks | mae | crps | rank corr |
|---|---|---|---|---|---|
| DST | baseline | 3616 | 4.652 | 3.322 | 0.131 |
| DST | salary | 3616 | 4.702 | 3.311 | 0.243 |
| QB | baseline | 4256 | 6.724 | 4.734 | 0.483 |
| QB | salary | 4256 | 7.121 | 5.003 | 0.518 |
| RB | baseline | 11094 | 4.886 | 3.509 | 0.644 |
| RB | salary | 11094 | 5.510 | 3.831 | 0.630 |
| TE | baseline | 7863 | 3.919 | 2.792 | 0.531 |
| TE | salary | 7863 | 4.114 | 2.935 | 0.514 |
| WR | baseline | 15649 | 5.127 | 3.653 | 0.608 |
| WR | salary | 15649 | 5.473 | 3.827 | 0.596 |

## Baseline only, 2022-2025 (no salaries exist)

The floor on the seasons the model will also be judged on; regulars chosen by prior form.

| position | model | player-weeks | mae | crps | rank corr |
|---|---|---|---|---|---|
| DST | baseline | 2174 | 4.420 | 3.155 | 0.111 |
| QB | baseline | 2174 | 6.636 | 4.726 | 0.292 |
| RB | baseline | 4339 | 5.639 | 3.991 | 0.563 |
| TE | baseline | 2168 | 4.923 | 3.494 | 0.386 |
| WR | baseline | 6505 | 5.838 | 4.108 | 0.495 |
