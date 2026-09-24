# College DFS baseline

The number the college player model has to beat (`atlas/dfs/cfb_players.py`, step 2 of `docs/MODEL_PLAN_DFS_CFB.md`): each player's recent DraftKings points, pulled toward his position's average by an amount fitted on the seasons before, walk-forward. There is no college salary archive, so it is the only benchmark. Scored on FBS players' games where the player recorded a stat.

## Each team's regulars, 2016-2025

Its top quarterback, two running backs, three receivers (tight ends included, as DraftKings lists them) and kicker by prior form.

| position | model | player-weeks | mae | crps | rank corr |
|---|---|---|---|---|---|
| K | baseline | 15919 | 3.068 | 2.164 | 0.208 |
| QB | baseline | 15971 | 8.943 | 6.351 | 0.340 |
| RB | baseline | 32150 | 7.143 | 5.019 | 0.454 |
| WR | baseline | 47591 | 6.354 | 4.483 | 0.388 |

## By season

| season | model | player-weeks | mae | crps | rank corr |
|---|---|---|---|---|---|
| 2016 | baseline | 11274 | 6.810 | 4.810 | 0.385 |
| 2017 | baseline | 11364 | 6.527 | 4.593 | 0.373 |
| 2018 | baseline | 11444 | 6.710 | 4.735 | 0.330 |
| 2019 | baseline | 11503 | 6.574 | 4.640 | 0.350 |
| 2020 | baseline | 7194 | 6.708 | 4.756 | 0.326 |
| 2021 | baseline | 11443 | 6.339 | 4.471 | 0.388 |
| 2022 | baseline | 11584 | 6.458 | 4.569 | 0.353 |
| 2023 | baseline | 11820 | 6.311 | 4.450 | 0.329 |
| 2024 | baseline | 11913 | 6.334 | 4.463 | 0.320 |
| 2025 | baseline | 12092 | 6.177 | 4.347 | 0.330 |

## Everyone who recorded a stat

| position | model | player-weeks | mae | crps | rank corr |
|---|---|---|---|---|---|
| K | baseline | 17009 | 3.098 | 2.178 | 0.245 |
| QB | baseline | 22604 | 8.190 | 5.814 | 0.519 |
| RB | baseline | 63205 | 5.331 | 3.844 | 0.628 |
| WR | baseline | 90145 | 5.205 | 3.718 | 0.412 |
