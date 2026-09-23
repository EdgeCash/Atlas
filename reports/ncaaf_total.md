# NCAAF total and joint score grid

Walk-forward, seasons 2021-2025. The total is the state model's implied home-plus-away points, recalibrated on the training seasons' own state forecasts with the two adjustments that measured as real (combined adjusted pace, effective wind). The margin (state mean and sd through the key-number lattice) and the total (discretised normal) are combined on an 80x80 grid over (home, away) points, `atlas/models/joint.py`; every headline number below is a mean of that grid.

## Calibration fitted, per season

`raw sigma` is the residual sd of the uncalibrated state total; `sigma` is after calibration and is the total's forecast sd.

| season | intercept | slope on state total | adj_pace_sum | weather_wind_effective | sigma | raw sigma | train games |
|---|---|---|---|---|---|---|---|
| 2021 | +83.6 | 0.534 | -1.073 | -0.182 | 17.17 | 17.73 | 1914 |
| 2022 | +57.7 | 0.508 | -0.549 | -0.148 | 16.85 | 17.32 | 1939 |
| 2023 | +44.2 | 0.661 | -0.455 | -0.146 | 16.62 | 16.83 | 1974 |
| 2024 | +34.5 | 0.673 | -0.287 | -0.196 | 16.25 | 16.43 | 2216 |
| 2025 | +41.9 | 0.659 | -0.413 | -0.173 | 16.15 | 16.33 | 2236 |

## Total, regular season, pooled

`over_brier` and `over_ece` score P(over the closing total) against what happened; a push counts half. A model weaker than the market is over-confident on P(over) by construction - where it disagrees with the closing total the market is usually right - so that ECE measures the gap to the market, not the soundness of the total's own distribution, which CRPS does.

| model | games | crps | mae | over_brier | over_ece |
|---|---|---|---|---|---|
| naive | 3730 | 9.616 | 13.63 | 0.264 | 0.106 |
| state_raw | 3730 | 9.187 | 12.96 | 0.257 | 0.082 |
| total | 3730 | 9.132 | 12.91 | 0.255 | 0.075 |
| market | 3730 | 8.847 | 12.47 | 0.247 | 0.005 |

## Total by season, regular

| model | season | games | crps | mae | over_brier | over_ece |
|---|---|---|---|---|---|---|
| naive | 2021 | 732 | 9.560 | 13.39 | 0.260 | 0.109 |
| naive | 2022 | 734 | 9.815 | 14.00 | 0.276 | 0.157 |
| naive | 2023 | 750 | 9.834 | 14.05 | 0.268 | 0.103 |
| naive | 2024 | 752 | 9.493 | 13.37 | 0.250 | 0.083 |
| naive | 2025 | 762 | 9.383 | 13.36 | 0.265 | 0.101 |
| state_raw | 2021 | 732 | 9.362 | 13.06 | 0.261 | 0.075 |
| state_raw | 2022 | 734 | 9.059 | 12.79 | 0.262 | 0.110 |
| state_raw | 2023 | 750 | 9.290 | 13.19 | 0.257 | 0.077 |
| state_raw | 2024 | 752 | 9.232 | 12.94 | 0.249 | 0.071 |
| state_raw | 2025 | 762 | 8.996 | 12.80 | 0.258 | 0.077 |
| total | 2021 | 732 | 9.520 | 13.38 | 0.264 | 0.106 |
| total | 2022 | 734 | 9.066 | 12.81 | 0.263 | 0.117 |
| total | 2023 | 750 | 9.162 | 13.06 | 0.252 | 0.064 |
| total | 2024 | 752 | 9.089 | 12.73 | 0.244 | 0.058 |
| total | 2025 | 762 | 8.837 | 12.60 | 0.252 | 0.070 |
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
| state_raw | wk 1-2 | 480 | 9.437 | 13.37 | 0.259 | 0.137 |
| state_raw | wk 3-4 | 540 | 9.192 | 12.88 | 0.251 | 0.067 |
| state_raw | wk 5-8 | 1075 | 9.074 | 12.79 | 0.257 | 0.074 |
| state_raw | wk 9-12 | 1131 | 9.210 | 13.04 | 0.261 | 0.088 |
| state_raw | wk 13+ | 504 | 9.134 | 12.81 | 0.256 | 0.093 |
| total | wk 1-2 | 480 | 9.500 | 13.49 | 0.260 | 0.113 |
| total | wk 3-4 | 540 | 9.180 | 12.96 | 0.251 | 0.074 |
| total | wk 5-8 | 1075 | 9.051 | 12.76 | 0.255 | 0.071 |
| total | wk 9-12 | 1131 | 9.079 | 12.89 | 0.255 | 0.071 |
| total | wk 13+ | 504 | 9.026 | 12.69 | 0.254 | 0.072 |
| market | wk 1-2 | 480 | 8.957 | 12.63 | 0.247 | 0.067 |
| market | wk 3-4 | 540 | 8.958 | 12.57 | 0.246 | 0.017 |
| market | wk 5-8 | 1075 | 8.746 | 12.38 | 0.247 | 0.016 |
| market | wk 9-12 | 1131 | 8.862 | 12.51 | 0.247 | 0.006 |
| market | wk 13+ | 504 | 8.806 | 12.28 | 0.245 | 0.044 |

## Total, bowls and playoffs (never fitted, always scored)

| model | games | crps | mae | over_brier | over_ece |
|---|---|---|---|---|---|
| naive | 134 | 9.738 | 14.08 | 0.269 | 0.150 |
| state_raw | 134 | 9.704 | 13.97 | 0.261 | 0.109 |
| total | 134 | 9.413 | 13.57 | 0.254 | 0.052 |
| market | 134 | 9.253 | 13.51 | 0.250 | 0.009 |

## Reliability, P(over the closing total), regular season

### total

| bin | n | forecast | observed | gap |
|---|---|---|---|---|
| 0.0-0.1 | 1 | 0.069 | 0.000 | -0.069 |
| 0.1-0.2 | 15 | 0.165 | 0.333 | +0.168 |
| 0.2-0.3 | 114 | 0.263 | 0.474 | +0.210 |
| 0.3-0.4 | 396 | 0.357 | 0.484 | +0.127 |
| 0.4-0.5 | 1047 | 0.456 | 0.489 | +0.033 |
| 0.5-0.6 | 1419 | 0.548 | 0.500 | -0.049 |
| 0.6-0.7 | 651 | 0.639 | 0.505 | -0.135 |
| 0.7-0.8 | 86 | 0.727 | 0.587 | -0.140 |
| 0.8-0.9 | 1 | 0.838 | 0.000 | -0.838 |

### market

| bin | n | forecast | observed | gap |
|---|---|---|---|---|
| 0.4-0.5 | 161 | 0.494 | 0.478 | -0.016 |
| 0.5-0.6 | 3569 | 0.501 | 0.497 | -0.004 |

## P(home) by closing spread, regular season: the grid against the market

The 28+ row is the plan's check on the tails; it overlaps the 21+ row.

| bucket | games | grid P(home) | observed | grid gap | market P(home) | market gap |
|---|---|---|---|---|---|---|
| |spread| 0-3 | 538 | 0.529 | 0.487 | +0.042 | 0.527 | +0.040 |
| |spread| 3-7 | 1023 | 0.535 | 0.543 | -0.007 | 0.535 | -0.008 |
| |spread| 7-14 | 1022 | 0.551 | 0.538 | +0.013 | 0.549 | +0.011 |
| |spread| 14-21 | 598 | 0.640 | 0.644 | -0.004 | 0.648 | +0.004 |
| |spread| 21+ | 549 | 0.755 | 0.780 | -0.024 | 0.772 | -0.008 |
| |spread| 28+ | 224 | 0.831 | 0.848 | -0.017 | 0.846 | -0.002 |

## The margin through the grid

Margin CRPS from the grid's own margin marginal, points lattice applied: 8.950; from the state's lattice pmf directly: 8.940. The grid's 0-79 bounds and the points lattice together cost +0.010.

## The exact score, for what it is

The headline is the mean, to one decimal. With a team's points uncertain by eleven or so, the most probable exact score is a fraction-of-a-percent event (mean 0.0090 with the points lattice), and the card shows it as such. The points lattice is step 7's answer to the plan's gate: a fitted multiplier on each side's own key numbers, no simulation.

| grid | games | top score was right | actual score in the top 10 cells | actual score in the top 50 cells | mean -log P(actual score) | median rank of the actual score |
|---|---|---|---|---|---|---|
| margin lattice only (v1) | 3730 | 0.0035 | 0.0308 | 0.1161 | 7.535 | 478 |
| with the points lattice (v1.5) | 3730 | 0.0067 | 0.0566 | 0.1995 | 7.099 | 239 |

### Points lattice fitted for 2025

Observed over expected frequency of a team scoring exactly this many points, shrunk toward one where the expectation is thin and capped at 5.

| 0 | 3 | 6 | 7 | 10 | 13 | 14 | 17 | 20 | 21 | 24 | 27 | 28 | 31 | 35 | 38 | 42 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 3.51 | 2.66 | 1.33 | 2.99 | 2.69 | 1.78 | 2.47 | 1.98 | 1.62 | 1.49 | 1.95 | 1.46 | 1.26 | 1.67 | 1.14 | 1.76 | 1.56 |

## What the card would have said: the last 12 regular-season games of 2025

Decimal means, never rounded integers; the market column is the closing line for comparison, not an input.

| game | projection | P(home) | total 80% range | most likely score | market (spread / total) | actual |
|---|---|---|---|---|---|---|
| Fresno State at San José State | 22.2-28.0, total 50.2 | 36% | 30-72 | 24-31 (0.8%) | +3.5 / 45.5 | 14-41 |
| Wyoming at Hawai'i | 26.6-19.1, total 45.7 | 70% | 26-66 | 24-17 (1.0%) | -8.5 / 44.5 | 27-7 |
| Kennesaw State at Jacksonville State | 30.5-28.6, total 59.0 | 56% | 37-81 | 31-24 (0.9%) | +3.0 / 62.5 | 15-19 |
| Troy at James Madison | 36.8-15.2, total 52.0 | 92% | 33-72 | 38-10 (1.0%) | -24.5 / 47.5 | 31-14 |
| North Texas at Tulane | 30.1-33.7, total 63.9 | 42% | 42-86 | 31-38 (0.8%) | +1.5 / 66.5 | 34-21 |
| UNLV at Boise State | 31.5-25.8, total 57.3 | 65% | 35-79 | 31-24 (0.9%) | -6.0 / 59.5 | 38-21 |
| Miami (OH) vs Western Michigan | 21.3-21.2, total 42.5 | 51% | 23-63 | 17-14 (1.1%) | -2.5 / 44.2 | 23-13 |
| BYU vs Texas Tech | 30.0-20.5, total 50.5 | 74% | 30-72 | 31-24 (0.9%) | -12.5 / 50.5 | 34-7 |
| Georgia vs Alabama | 24.2-22.8, total 47.0 | 55% | 27-69 | 24-17 (0.9%) | +1.5 / 48.5 | 7-28 |
| Indiana vs Ohio State | 22.6-22.2, total 44.8 | 52% | 24-66 | 17-14 (0.9%) | -3.5 / 45.8 | 10-13 |
| Duke vs Virginia | 29.1-26.3, total 55.5 | 58% | 34-77 | 31-24 (0.9%) | -3.5 / 58.5 | 20-27 |
| Army vs Navy | 22.7-18.1, total 40.8 | 63% | 21-61 | 17-14 (1.2%) | -6.0 / 37.8 | 17-16 |
