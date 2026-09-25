# NFL total and joint score grid

Walk-forward, seasons 2020-2026. The total is the quarterback state model's implied home-plus-away points, recalibrated on the training seasons' own state forecasts with the wind (zero in a dome) as the one game-level term. The margin (state mean and sd through the key-number lattice) and the total (discretised normal) meet on a 80x80 grid over (home, away) points, reweighted by the points lattice; every headline number below is a mean of that grid. The wind is the recorded game-time wind, not a pre-kickoff forecast - a mild look-ahead in these numbers.

## Calibration fitted, per season

`over shrink` and `over sigma` read P(over a line): `actual - line = shrink * (total - line) + e`, fitted on the training games with a closing total (`fit_over`).

| season | intercept | slope on state total | wind_effective | sigma | raw sigma | train games | over shrink | over sigma | lined train games |
|---|---|---|---|---|---|---|---|---|---|
| 2020 | +22.8 | 0.534 | -0.356 | 13.93 | 14.19 | 768 | 0.161 | 13.69 | 768 |
| 2021 | +15.6 | 0.721 | -0.377 | 13.56 | 13.76 | 768 | 0.042 | 13.26 | 768 |
| 2022 | +23.5 | 0.545 | -0.361 | 13.39 | 13.73 | 784 | 0.239 | 13.18 | 784 |
| 2023 | +16.6 | 0.671 | -0.320 | 13.42 | 13.62 | 799 | 0.081 | 13.13 | 799 |
| 2024 | +19.4 | 0.594 | -0.348 | 13.31 | 13.57 | 815 | 0.385 | 13.18 | 815 |
| 2025 | +18.8 | 0.606 | -0.291 | 13.18 | 13.36 | 815 | 0.117 | 12.98 | 815 |
| 2026 | +20.9 | 0.580 | -0.348 | 13.08 | 13.39 | 816 | 0.328 | 12.94 | 816 |

## Total, regular season 2023-2025

`over_brier` and `over_ece` score P(over the closing total); a push counts half. The total's P(over) is read given the line (`over shrink`, `over sigma`); the other models' off their own distribution. CRPS and MAE score the total's own distribution, which the line does not touch.

| model | games | crps | mae | over_brier | over_ece |
|---|---|---|---|---|---|
| naive | 816 | 7.614 | 10.68 | 0.263 | 0.102 |
| state_raw | 816 | 7.471 | 10.53 | 0.257 | 0.063 |
| total | 816 | 7.364 | 10.38 | 0.249 | 0.014 |
| market | 816 | 7.240 | 10.12 | 0.248 | 0.006 |

## Total, every scored season pooled

| model | games | crps | mae | over_brier | over_ece |
|---|---|---|---|---|---|
| naive | 1647 | 7.783 | 10.98 | 0.264 | 0.111 |
| state_raw | 1647 | 7.597 | 10.74 | 0.258 | 0.085 |
| total | 1647 | 7.515 | 10.62 | 0.248 | 0.023 |
| market | 1647 | 7.328 | 10.30 | 0.248 | 0.012 |

## Total by season, regular

| model | season | games | crps | mae | over_brier | over_ece |
|---|---|---|---|---|---|---|
| naive | 2020 | 256 | 8.029 | 11.29 | 0.269 | 0.154 |
| naive | 2021 | 272 | 7.790 | 11.10 | 0.258 | 0.093 |
| naive | 2022 | 271 | 7.885 | 11.27 | 0.269 | 0.125 |
| naive | 2023 | 272 | 7.756 | 11.01 | 0.268 | 0.135 |
| naive | 2024 | 272 | 7.287 | 10.04 | 0.255 | 0.078 |
| naive | 2025 | 272 | 7.797 | 10.97 | 0.265 | 0.114 |
| naive | 2026 | 32 | 9.198 | 12.89 | 0.296 | 0.270 |
| state_raw | 2020 | 256 | 7.545 | 10.64 | 0.254 | 0.085 |
| state_raw | 2021 | 272 | 7.770 | 11.22 | 0.260 | 0.107 |
| state_raw | 2022 | 271 | 7.707 | 10.82 | 0.264 | 0.122 |
| state_raw | 2023 | 272 | 7.575 | 10.83 | 0.261 | 0.095 |
| state_raw | 2024 | 272 | 7.262 | 10.13 | 0.256 | 0.077 |
| state_raw | 2025 | 272 | 7.577 | 10.64 | 0.254 | 0.057 |
| state_raw | 2026 | 32 | 8.836 | 12.04 | 0.274 | 0.138 |
| total | 2020 | 256 | 7.540 | 10.62 | 0.246 | 0.045 |
| total | 2021 | 272 | 7.602 | 10.93 | 0.247 | 0.040 |
| total | 2022 | 271 | 7.701 | 10.85 | 0.249 | 0.069 |
| total | 2023 | 272 | 7.397 | 10.58 | 0.248 | 0.045 |
| total | 2024 | 272 | 7.223 | 10.06 | 0.250 | 0.043 |
| total | 2025 | 272 | 7.470 | 10.48 | 0.250 | 0.020 |
| total | 2026 | 32 | 8.878 | 12.27 | 0.259 | 0.120 |
| market | 2020 | 256 | 7.231 | 10.15 | 0.245 | 0.006 |
| market | 2021 | 272 | 7.493 | 10.79 | 0.247 | 0.039 |
| market | 2022 | 271 | 7.414 | 10.39 | 0.247 | 0.056 |
| market | 2023 | 272 | 7.304 | 10.24 | 0.248 | 0.041 |
| market | 2024 | 272 | 6.989 | 9.73 | 0.247 | 0.038 |
| market | 2025 | 272 | 7.428 | 10.39 | 0.250 | 0.022 |
| market | 2026 | 32 | 8.224 | 11.19 | 0.250 | 0.031 |

## Total by week bucket, regular season

| model | week_bucket | games | crps | mae | over_brier | over_ece |
|---|---|---|---|---|---|---|
| naive | wk 1-3 | 224 | 7.822 | 11.22 | 0.270 | 0.138 |
| naive | wk 3-7 | 365 | 7.459 | 10.60 | 0.257 | 0.071 |
| naive | wk 7-13 | 517 | 7.602 | 10.69 | 0.263 | 0.123 |
| naive | wk 13+ | 541 | 8.158 | 11.42 | 0.269 | 0.114 |
| state_raw | wk 1-3 | 224 | 7.675 | 11.15 | 0.263 | 0.107 |
| state_raw | wk 3-7 | 365 | 7.132 | 10.02 | 0.248 | 0.057 |
| state_raw | wk 7-13 | 517 | 7.528 | 10.61 | 0.260 | 0.089 |
| state_raw | wk 13+ | 541 | 7.946 | 11.18 | 0.262 | 0.099 |
| total | wk 1-3 | 224 | 7.594 | 10.95 | 0.252 | 0.032 |
| total | wk 3-7 | 365 | 7.192 | 10.22 | 0.246 | 0.042 |
| total | wk 7-13 | 517 | 7.374 | 10.36 | 0.248 | 0.023 |
| total | wk 13+ | 541 | 7.836 | 11.00 | 0.249 | 0.042 |
| market | wk 1-3 | 224 | 7.397 | 10.61 | 0.250 | 0.027 |
| market | wk 3-7 | 365 | 7.030 | 9.94 | 0.247 | 0.041 |
| market | wk 7-13 | 517 | 7.181 | 10.09 | 0.247 | 0.022 |
| market | wk 13+ | 541 | 7.642 | 10.62 | 0.248 | 0.024 |

## P(over): the total alone against the total given the line, regular season 2023-2025

The same games and the same total; only how a line is read differs. `mean P(side)` is the confidence the model states in its own side.

| P(over) from | games | brier | ece | mean P(side) |
|---|---|---|---|---|
| the total alone | 816 | 0.2550 | 0.063 | 0.561 |
| the total given the line | 816 | 0.2493 | 0.014 | 0.512 |

## P(over): the total alone against the total given the line, regular season, every scored season

The same games and the same total; only how a line is read differs. `mean P(side)` is the confidence the model states in its own side.

| P(over) from | games | brier | ece | mean P(side) |
|---|---|---|---|---|
| the total alone | 1647 | 0.2563 | 0.081 | 0.570 |
| the total given the line | 1647 | 0.2485 | 0.023 | 0.512 |

## Total, playoffs (never fitted, always scored)

| model | games | crps | mae | over_brier | over_ece |
|---|---|---|---|---|---|
| naive | 78 | 7.999 | 10.97 | 0.241 | 0.059 |
| state_raw | 78 | 8.136 | 11.59 | 0.257 | 0.163 |
| total | 78 | 7.770 | 10.87 | 0.241 | 0.053 |
| market | 78 | 7.824 | 10.89 | 0.244 | 0.013 |

## P(home) by closing spread, regular season 2023-2025: the grid against the market

The plan asks whether the 65-80% bins are honest, because that is where the NFL lives.

| bucket | games | grid P(home) | observed | grid gap | market P(home) | market gap |
|---|---|---|---|---|---|---|
| |spread| 0-3 | 203 | 0.507 | 0.483 | +0.025 | 0.505 | +0.022 |
| |spread| 3-6 | 327 | 0.525 | 0.520 | +0.005 | 0.518 | -0.002 |
| |spread| 6-10 | 207 | 0.577 | 0.563 | +0.014 | 0.563 | -0.000 |
| |spread| 10+ | 79 | 0.679 | 0.734 | -0.055 | 0.701 | -0.034 |

### Reliability, grid

| bin | n | forecast | observed | gap |
|---|---|---|---|---|
| 0.1-0.2 | 15 | 0.173 | 0.267 | +0.094 |
| 0.2-0.3 | 32 | 0.257 | 0.344 | +0.087 |
| 0.3-0.4 | 89 | 0.354 | 0.298 | -0.056 |
| 0.4-0.5 | 203 | 0.454 | 0.419 | -0.035 |
| 0.5-0.6 | 169 | 0.550 | 0.527 | -0.023 |
| 0.6-0.7 | 142 | 0.649 | 0.669 | +0.020 |
| 0.7-0.8 | 117 | 0.742 | 0.769 | +0.027 |
| 0.8-0.9 | 46 | 0.843 | 0.848 | +0.005 |
| 0.9-1.0 | 3 | 0.912 | 1.000 | +0.088 |

### Reliability, market

| bin | n | forecast | observed | gap |
|---|---|---|---|---|
| 0.1-0.2 | 9 | 0.166 | 0.111 | -0.055 |
| 0.2-0.3 | 35 | 0.265 | 0.229 | -0.036 |
| 0.3-0.4 | 108 | 0.350 | 0.310 | -0.040 |
| 0.4-0.5 | 179 | 0.431 | 0.369 | -0.062 |
| 0.5-0.6 | 165 | 0.572 | 0.594 | +0.022 |
| 0.6-0.7 | 197 | 0.647 | 0.706 | +0.059 |
| 0.7-0.8 | 76 | 0.740 | 0.697 | -0.042 |
| 0.8-0.9 | 45 | 0.845 | 0.933 | +0.089 |
| 0.9-1.0 | 2 | 0.917 | 1.000 | +0.083 |

## The margin through the grid

Margin CRPS from the grid's own marginal, points lattice applied: 7.289; from the state's lattice pmf directly: 7.290 (2023-2025).

## The exact score, for what it is

Mean P(top exact score) with the points lattice: 0.0141.

| grid | games | top score was right | actual score in the top 10 cells | actual score in the top 50 cells | mean -log P(actual score) | median rank of the actual score |
|---|---|---|---|---|---|---|
| margin lattice only | 816 | 0.0074 | 0.0417 | 0.1642 | 7.133 | 306 |
| with the points lattice | 816 | 0.0086 | 0.0882 | 0.2108 | 6.874 | 228 |

### Points lattice fitted for 2026

| 0 | 3 | 6 | 7 | 10 | 13 | 14 | 16 | 17 | 20 | 21 | 23 | 24 | 27 | 28 | 30 | 31 | 34 | 35 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1.77 | 2.20 | 2.09 | 1.28 | 2.74 | 1.55 | 1.02 | 1.06 | 1.68 | 2.08 | 0.83 | 0.96 | 1.46 | 1.51 | 0.79 | 1.21 | 1.39 | 1.79 | 0.57 |

## What the card would have said: the last 10 regular-season games of 2026

Decimal means, never rounded integers; the market column is the closing line for comparison, not an input.

| game | projection | P(home) | total 80% range | most likely score | market (spread / total) | actual |
|---|---|---|---|---|---|---|
| NO at BAL | 27.3-17.9, total 45.2 | 76% | 29-62 | 20-17 (1.3%) | -8.5 / 45.5 | 17-24 |
| PHI at TEN | 18.1-25.0, total 43.1 | 30% | 27-60 | 17-20 (1.3%) | +7.0 / 39.5 | 20-24 |
| PIT at NE | 24.3-18.5, total 42.8 | 67% | 27-59 | 20-17 (1.5%) | -4.5 / 41.5 | 20-3 |
| JAX at DEN | 19.8-23.7, total 43.4 | 38% | 27-60 | 17-20 (1.4%) | -2.5 / 45.5 | 20-13 |
| LV at LAC | 23.9-21.0, total 44.9 | 59% | 29-62 | 20-17 (1.4%) | -6.5 / 43.5 | 14-26 |
| MIA at SF | 28.3-17.4, total 45.7 | 80% | 30-62 | 20-17 (1.2%) | -12.5 / 44.5 | 35-13 |
| SEA at ARI | 20.3-24.2, total 44.5 | 38% | 28-61 | 17-20 (1.3%) | +3.5 / 40.5 | 7-31 |
| WAS at DAL | 27.0-24.5, total 51.5 | 57% | 35-69 | 27-24 (1.1%) | -3.5 / 51.5 | 37-20 |
| IND at KC | 25.7-19.9, total 45.6 | 67% | 29-62 | 20-17 (1.3%) | -6.0 / 46.5 | 33-30 |
| NYG at LA | 27.4-21.7, total 49.1 | 67% | 33-66 | 20-17 (1.1%) | -6.5 / 47.5 | 28-6 |
