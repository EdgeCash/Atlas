# NCAAF total and joint score grid

Walk-forward, seasons 2021-2026. The total is the state model's implied home-plus-away points, recalibrated on the training seasons' own state forecasts with the two adjustments that measured as real (combined adjusted pace, effective wind). The margin (state mean and sd through the key-number lattice) and the total (discretised normal) are combined on an 80x80 grid over (home, away) points, `atlas/models/joint.py`; every headline number below is a mean of that grid.

## Calibration fitted, per season

`raw sigma` is the residual sd of the uncalibrated state total; `sigma` is after calibration and is the total's forecast sd. `over shrink` and `over sigma` read P(over a line): `actual - line = shrink * (total - line) + e`, fitted on the training games with a closing total (`fit_over`).

| season | intercept | slope on state total | adj_pace_sum | weather_wind_effective | sigma | raw sigma | train games | over shrink | over sigma | lined train games |
|---|---|---|---|---|---|---|---|---|---|---|
| 2021 | +82.8 | 0.520 | -1.042 | -0.184 | 17.21 | 17.81 | 1975 | 0.105 | 16.55 | 1936 |
| 2022 | +57.1 | 0.517 | -0.547 | -0.161 | 16.90 | 17.35 | 1974 | 0.163 | 16.30 | 1950 |
| 2023 | +42.4 | 0.688 | -0.449 | -0.145 | 16.61 | 16.79 | 1974 | 0.038 | 16.03 | 1974 |
| 2024 | +33.4 | 0.691 | -0.282 | -0.194 | 16.25 | 16.41 | 2216 | 0.068 | 15.69 | 2216 |
| 2025 | +40.9 | 0.679 | -0.409 | -0.171 | 16.15 | 16.31 | 2236 | 0.216 | 15.79 | 2236 |
| 2026 | +51.7 | 0.591 | -0.529 | -0.143 | 16.00 | 16.23 | 2264 | 0.350 | 15.79 | 2264 |

## Total, regular season, pooled

`over_brier` and `over_ece` score P(over the closing total) against what happened; a push counts half. The total's P(over) is read given the line (`over shrink`, `over sigma`); the other models' off their own distribution. CRPS and MAE score the total's own distribution, which the line does not touch.

| model | games | crps | mae | over_brier | over_ece |
|---|---|---|---|---|---|
| naive | 3730 | 9.616 | 13.63 | 0.264 | 0.106 |
| state_raw | 3730 | 9.183 | 12.96 | 0.257 | 0.083 |
| total | 3730 | 9.126 | 12.90 | 0.247 | 0.005 |
| market | 3730 | 8.847 | 12.47 | 0.247 | 0.005 |

## Total by season, regular

| model | season | games | crps | mae | over_brier | over_ece |
|---|---|---|---|---|---|---|
| naive | 2021 | 732 | 9.560 | 13.39 | 0.260 | 0.109 |
| naive | 2022 | 734 | 9.815 | 14.00 | 0.276 | 0.157 |
| naive | 2023 | 750 | 9.834 | 14.05 | 0.268 | 0.103 |
| naive | 2024 | 752 | 9.493 | 13.37 | 0.250 | 0.083 |
| naive | 2025 | 762 | 9.383 | 13.36 | 0.265 | 0.101 |
| state_raw | 2021 | 732 | 9.435 | 13.23 | 0.264 | 0.091 |
| state_raw | 2022 | 734 | 9.036 | 12.76 | 0.261 | 0.107 |
| state_raw | 2023 | 750 | 9.280 | 13.19 | 0.256 | 0.072 |
| state_raw | 2024 | 752 | 9.200 | 12.90 | 0.248 | 0.066 |
| state_raw | 2025 | 762 | 8.970 | 12.75 | 0.257 | 0.083 |
| total | 2021 | 732 | 9.494 | 13.35 | 0.248 | 0.028 |
| total | 2022 | 734 | 9.058 | 12.80 | 0.247 | 0.046 |
| total | 2023 | 750 | 9.170 | 13.06 | 0.247 | 0.048 |
| total | 2024 | 752 | 9.083 | 12.73 | 0.244 | 0.017 |
| total | 2025 | 762 | 8.839 | 12.59 | 0.248 | 0.020 |
| market | 2021 | 732 | 8.914 | 12.47 | 0.248 | 0.034 |
| market | 2022 | 734 | 8.546 | 11.95 | 0.246 | 0.010 |
| market | 2023 | 750 | 9.001 | 12.80 | 0.247 | 0.009 |
| market | 2024 | 752 | 9.084 | 12.74 | 0.245 | 0.019 |
| market | 2025 | 762 | 8.687 | 12.37 | 0.248 | 0.013 |

## Total by week bucket, regular season

| model | week_bucket | games | crps | mae | over_brier | over_ece |
|---|---|---|---|---|---|---|
| naive | wk 1-2 | 480 | 9.558 | 13.53 | 0.258 | 0.136 |
| naive | wk 3-4 | 540 | 9.389 | 13.35 | 0.254 | 0.096 |
| naive | wk 5-8 | 1075 | 9.705 | 13.74 | 0.271 | 0.123 |
| naive | wk 9-12 | 1131 | 9.725 | 13.81 | 0.266 | 0.111 |
| naive | wk 13+ | 504 | 9.478 | 13.43 | 0.260 | 0.101 |
| state_raw | wk 1-2 | 480 | 9.376 | 13.26 | 0.256 | 0.136 |
| state_raw | wk 3-4 | 540 | 9.192 | 12.92 | 0.251 | 0.070 |
| state_raw | wk 5-8 | 1075 | 9.085 | 12.82 | 0.257 | 0.070 |
| state_raw | wk 9-12 | 1131 | 9.222 | 13.08 | 0.262 | 0.090 |
| state_raw | wk 13+ | 504 | 9.113 | 12.78 | 0.255 | 0.082 |
| total | wk 1-2 | 480 | 9.462 | 13.43 | 0.247 | 0.066 |
| total | wk 3-4 | 540 | 9.180 | 12.96 | 0.245 | 0.020 |
| total | wk 5-8 | 1075 | 9.054 | 12.77 | 0.247 | 0.017 |
| total | wk 9-12 | 1131 | 9.077 | 12.88 | 0.248 | 0.006 |
| total | wk 13+ | 504 | 9.014 | 12.67 | 0.246 | 0.041 |
| market | wk 1-2 | 480 | 8.957 | 12.63 | 0.247 | 0.067 |
| market | wk 3-4 | 540 | 8.958 | 12.57 | 0.246 | 0.017 |
| market | wk 5-8 | 1075 | 8.746 | 12.38 | 0.247 | 0.016 |
| market | wk 9-12 | 1131 | 8.862 | 12.51 | 0.247 | 0.006 |
| market | wk 13+ | 504 | 8.806 | 12.28 | 0.245 | 0.044 |

## Total, bowls and playoffs (never fitted, always scored)

| model | games | crps | mae | over_brier | over_ece |
|---|---|---|---|---|---|
| naive | 134 | 9.738 | 14.08 | 0.269 | 0.150 |
| state_raw | 134 | 9.694 | 13.95 | 0.261 | 0.114 |
| total | 134 | 9.408 | 13.58 | 0.250 | 0.009 |
| market | 134 | 9.253 | 13.51 | 0.250 | 0.009 |

## P(over): the total alone against the total given the line, regular season

The same games and the same total; only how a line is read differs. `mean P(side)` is the confidence the model states in its own side.

| P(over) from | games | brier | ece | mean P(side) |
|---|---|---|---|---|
| the total alone | 3730 | 0.2547 | 0.080 | 0.583 |
| the total given the line | 3730 | 0.2468 | 0.005 | 0.511 |

## Reliability, P(over the closing total), regular season

### total

| bin | n | forecast | observed | gap |
|---|---|---|---|---|
| 0.4-0.5 | 1586 | 0.489 | 0.482 | -0.007 |
| 0.5-0.6 | 2144 | 0.511 | 0.507 | -0.004 |

### market

| bin | n | forecast | observed | gap |
|---|---|---|---|---|
| 0.4-0.5 | 161 | 0.494 | 0.478 | -0.016 |
| 0.5-0.6 | 3569 | 0.501 | 0.497 | -0.004 |

## P(home) by closing spread, regular season: the grid against the market

The 28+ row is the plan's check on the tails; it overlaps the 21+ row.

| bucket | games | grid P(home) | observed | grid gap | market P(home) | market gap |
|---|---|---|---|---|---|---|
| |spread| 0-3 | 538 | 0.529 | 0.487 | +0.042 | 0.529 | +0.042 |
| |spread| 3-7 | 1023 | 0.536 | 0.543 | -0.006 | 0.538 | -0.004 |
| |spread| 7-14 | 1022 | 0.552 | 0.538 | +0.014 | 0.552 | +0.014 |
| |spread| 14-21 | 598 | 0.642 | 0.644 | -0.001 | 0.651 | +0.007 |
| |spread| 21+ | 549 | 0.757 | 0.780 | -0.022 | 0.774 | -0.006 |
| |spread| 28+ | 224 | 0.832 | 0.848 | -0.016 | 0.847 | -0.001 |

## The margin through the grid

Margin CRPS from the grid's own margin marginal, points lattice applied: 8.934; from the state's lattice pmf directly: 8.923. The grid's 0-79 bounds and the points lattice together cost +0.012.

## The exact score, for what it is

The headline is the mean, to one decimal. With a team's points uncertain by eleven or so, the most probable exact score is a fraction-of-a-percent event (mean 0.0093 with the points lattice), and the card shows it as such. The points lattice is step 7's answer to the plan's gate: a fitted multiplier on each side's own key numbers, no simulation.

| grid | games | top score was right | actual score in the top 10 cells | actual score in the top 50 cells | mean -log P(actual score) | median rank of the actual score |
|---|---|---|---|---|---|---|
| margin lattice only (v1) | 3730 | 0.0035 | 0.0308 | 0.1166 | 7.515 | 467 |
| with the points lattice (v1.5) | 3730 | 0.0064 | 0.0566 | 0.2019 | 7.076 | 232 |

### Points lattice fitted for 2025

Observed over expected frequency of a team scoring exactly this many points, shrunk toward one where the expectation is thin and capped at 5.

| 0 | 3 | 6 | 7 | 10 | 13 | 14 | 17 | 20 | 21 | 24 | 27 | 28 | 31 | 35 | 38 | 42 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 3.47 | 2.63 | 1.32 | 2.96 | 2.67 | 1.77 | 2.46 | 1.98 | 1.63 | 1.50 | 1.97 | 1.48 | 1.27 | 1.68 | 1.14 | 1.75 | 1.55 |

## What the card would have said: the last 0 regular-season games of 2026

Decimal means, never rounded integers; the market column is the closing line for comparison, not an input.

| game | projection | P(home) | total 80% range | most likely score | market (spread / total) | actual |
|---|---|---|---|---|---|---|
