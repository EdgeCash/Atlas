# College DFS player projections

Atlas's college player model (`atlas/dfs/cfb_model.py`, step 3 of `docs/MODEL_PLAN_DFS_CFB.md`): the step 2 baseline corrected by one gradient-boosted model per position that reads the game as the line implies it and each player's role from his earlier games. Walk-forward: every season predicted from the seasons before it. 91% of scored player-games have a line.

## The gate, 2016-2025, each team's regulars: passes

Beat the baseline's CRPS at every position, and 80% ranges that hold 76-84% of outcomes.

| position | crps model | crps baseline | rank model | rank baseline | in range | beats baseline | ranges hold |
|---|---|---|---|---|---|---|---|
| K | 2.073 | 2.164 | 0.341 | 0.208 | 80.2% | yes | yes |
| QB | 5.985 | 6.351 | 0.424 | 0.340 | 80.8% | yes | yes |
| RB | 4.787 | 5.026 | 0.524 | 0.455 | 79.5% | yes | yes |
| WR | 4.374 | 4.493 | 0.451 | 0.390 | 79.6% | yes | yes |

## By season

| season | model | player-weeks | mae | crps | rank corr |
|---|---|---|---|---|---|
| 2016 | model | 11274 | 6.582 | 4.644 | 0.455 |
| 2016 | baseline | 11274 | 6.810 | 4.810 | 0.385 |
| 2017 | model | 11364 | 6.211 | 4.384 | 0.463 |
| 2017 | baseline | 11364 | 6.529 | 4.595 | 0.373 |
| 2018 | model | 11446 | 6.421 | 4.533 | 0.422 |
| 2018 | baseline | 11446 | 6.714 | 4.737 | 0.331 |
| 2019 | model | 11503 | 6.257 | 4.421 | 0.452 |
| 2019 | baseline | 11503 | 6.574 | 4.640 | 0.350 |
| 2020 | model | 7194 | 6.408 | 4.551 | 0.424 |
| 2020 | baseline | 7194 | 6.720 | 4.763 | 0.327 |
| 2021 | model | 11443 | 6.137 | 4.324 | 0.460 |
| 2021 | baseline | 11443 | 6.344 | 4.476 | 0.389 |
| 2022 | model | 11584 | 6.245 | 4.414 | 0.434 |
| 2022 | baseline | 11584 | 6.475 | 4.582 | 0.354 |
| 2023 | model | 11820 | 6.083 | 4.284 | 0.413 |
| 2023 | baseline | 11820 | 6.329 | 4.463 | 0.330 |
| 2024 | model | 11913 | 6.105 | 4.307 | 0.408 |
| 2024 | baseline | 11913 | 6.346 | 4.471 | 0.321 |
| 2025 | model | 12092 | 5.917 | 4.170 | 0.423 |
| 2025 | baseline | 12092 | 6.192 | 4.357 | 0.332 |

## Everyone who recorded a stat

| position | model | player-weeks | mae | crps | rank corr |
|---|---|---|---|---|---|
| K | model | 17765 | 2.955 | 2.084 | 0.367 |
| K | baseline | 17765 | 3.093 | 2.176 | 0.244 |
| QB | model | 23528 | 7.928 | 5.577 | 0.571 |
| QB | baseline | 23528 | 8.199 | 5.819 | 0.519 |
| RB | model | 65479 | 5.156 | 3.668 | 0.682 |
| RB | baseline | 65479 | 5.345 | 3.854 | 0.630 |
| WR | model | 93631 | 5.165 | 3.649 | 0.469 |
| WR | baseline | 93631 | 5.232 | 3.740 | 0.413 |

## Caveats

- College has no targets, snap counts, injury report or depth chart: the model knows a player's role only from what he has done, and nothing of the week's news.
- Scored on the games where a player recorded a stat; whether he plays at all is a separate estimate for live slates.
