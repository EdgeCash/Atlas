# NFL total and joint score grid

Walk-forward, seasons 2020-2026. The total is the quarterback state model's implied home-plus-away points, recalibrated on the training seasons' own state forecasts with the wind (zero in a dome) as the one game-level term. The margin (state mean and sd through the key-number lattice) and the total (discretised normal) meet on a 60x60 grid over (home, away) points, reweighted by the points lattice; every headline number below is a mean of that grid.

## Calibration fitted, per season

| season | intercept | slope on state total | wind_effective | sigma | raw sigma | train games |
|---|---|---|---|---|---|---|
| 2020 | +23.5 | 0.519 | -0.361 | 13.92 | 14.21 | 768 |
| 2021 | +16.6 | 0.700 | -0.379 | 13.56 | 13.77 | 768 |
| 2022 | +23.0 | 0.557 | -0.365 | 13.38 | 13.72 | 784 |
| 2023 | +17.5 | 0.653 | -0.323 | 13.42 | 13.63 | 799 |
| 2024 | +19.8 | 0.585 | -0.349 | 13.31 | 13.58 | 815 |
| 2025 | +19.3 | 0.596 | -0.291 | 13.18 | 13.37 | 815 |
| 2026 | +20.9 | 0.580 | -0.349 | 13.07 | 13.39 | 816 |

## Total, regular season 2023-2025

`over_brier` and `over_ece` score P(over the closing total); a push counts half. A model weaker than the market is over-confident on P(over) by construction, so that ECE measures the gap to the market, not the total's own distribution, which CRPS does.

| model | games | crps | mae | over_brier | over_ece |
|---|---|---|---|---|---|
| naive | 816 | 7.614 | 10.68 | 0.263 | 0.102 |
| state_raw | 816 | 7.472 | 10.53 | 0.257 | 0.057 |
| total | 816 | 7.359 | 10.37 | 0.255 | 0.063 |
| market | 816 | 7.240 | 10.12 | 0.248 | 0.006 |

## Total, every scored season pooled

| model | games | crps | mae | over_brier | over_ece |
|---|---|---|---|---|---|
| naive | 1647 | 7.783 | 10.98 | 0.264 | 0.111 |
| state_raw | 1647 | 7.605 | 10.75 | 0.259 | 0.078 |
| total | 1647 | 7.513 | 10.62 | 0.256 | 0.081 |
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
| state_raw | 2020 | 256 | 7.562 | 10.68 | 0.255 | 0.079 |
| state_raw | 2021 | 272 | 7.782 | 11.24 | 0.261 | 0.112 |
| state_raw | 2022 | 271 | 7.720 | 10.83 | 0.264 | 0.109 |
| state_raw | 2023 | 272 | 7.573 | 10.82 | 0.260 | 0.092 |
| state_raw | 2024 | 272 | 7.268 | 10.14 | 0.256 | 0.076 |
| state_raw | 2025 | 272 | 7.577 | 10.64 | 0.254 | 0.044 |
| state_raw | 2026 | 32 | 8.826 | 12.03 | 0.274 | 0.138 |
| total | 2020 | 256 | 7.541 | 10.61 | 0.255 | 0.106 |
| total | 2021 | 272 | 7.598 | 10.93 | 0.254 | 0.104 |
| total | 2022 | 271 | 7.704 | 10.85 | 0.261 | 0.110 |
| total | 2023 | 272 | 7.394 | 10.58 | 0.255 | 0.100 |
| total | 2024 | 272 | 7.219 | 10.06 | 0.257 | 0.077 |
| total | 2025 | 272 | 7.464 | 10.48 | 0.252 | 0.027 |
| total | 2026 | 32 | 8.873 | 12.27 | 0.282 | 0.171 |
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
| state_raw | wk 1-3 | 224 | 7.671 | 11.16 | 0.262 | 0.098 |
| state_raw | wk 3-7 | 365 | 7.121 | 10.00 | 0.248 | 0.067 |
| state_raw | wk 7-13 | 517 | 7.550 | 10.65 | 0.260 | 0.084 |
| state_raw | wk 13+ | 541 | 7.955 | 11.19 | 0.262 | 0.103 |
| total | wk 1-3 | 224 | 7.587 | 10.95 | 0.262 | 0.087 |
| total | wk 3-7 | 365 | 7.181 | 10.20 | 0.250 | 0.051 |
| total | wk 7-13 | 517 | 7.379 | 10.37 | 0.255 | 0.081 |
| total | wk 13+ | 541 | 7.834 | 11.00 | 0.259 | 0.104 |
| market | wk 1-3 | 224 | 7.397 | 10.61 | 0.250 | 0.027 |
| market | wk 3-7 | 365 | 7.030 | 9.94 | 0.247 | 0.041 |
| market | wk 7-13 | 517 | 7.181 | 10.09 | 0.247 | 0.022 |
| market | wk 13+ | 541 | 7.642 | 10.62 | 0.248 | 0.024 |

## Total, playoffs (never fitted, always scored)

| model | games | crps | mae | over_brier | over_ece |
|---|---|---|---|---|---|
| naive | 78 | 7.999 | 10.97 | 0.241 | 0.059 |
| state_raw | 78 | 8.158 | 11.63 | 0.258 | 0.137 |
| total | 78 | 7.776 | 10.88 | 0.240 | 0.088 |
| market | 78 | 7.824 | 10.89 | 0.244 | 0.013 |

## P(home) by closing spread, regular season 2023-2025: the grid against the market

The plan asks whether the 65-80% bins are honest, because that is where the NFL lives.

| bucket | games | grid P(home) | observed | grid gap | market P(home) | market gap |
|---|---|---|---|---|---|---|
| |spread| 0-3 | 203 | 0.507 | 0.483 | +0.024 | 0.504 | +0.021 |
| |spread| 3-6 | 327 | 0.524 | 0.520 | +0.004 | 0.517 | -0.003 |
| |spread| 6-10 | 207 | 0.576 | 0.563 | +0.013 | 0.562 | -0.001 |
| |spread| 10+ | 79 | 0.677 | 0.734 | -0.058 | 0.700 | -0.035 |

### Reliability, grid

| bin | n | forecast | observed | gap |
|---|---|---|---|---|
| 0.1-0.2 | 14 | 0.171 | 0.286 | +0.115 |
| 0.2-0.3 | 33 | 0.257 | 0.333 | +0.076 |
| 0.3-0.4 | 90 | 0.354 | 0.294 | -0.060 |
| 0.4-0.5 | 207 | 0.455 | 0.420 | -0.034 |
| 0.5-0.6 | 162 | 0.550 | 0.531 | -0.019 |
| 0.6-0.7 | 152 | 0.649 | 0.678 | +0.028 |
| 0.7-0.8 | 113 | 0.743 | 0.761 | +0.018 |
| 0.8-0.9 | 42 | 0.845 | 0.857 | +0.012 |
| 0.9-1.0 | 3 | 0.911 | 1.000 | +0.089 |

### Reliability, market

| bin | n | forecast | observed | gap |
|---|---|---|---|---|
| 0.1-0.2 | 9 | 0.166 | 0.111 | -0.055 |
| 0.2-0.3 | 35 | 0.265 | 0.229 | -0.037 |
| 0.3-0.4 | 108 | 0.350 | 0.310 | -0.039 |
| 0.4-0.5 | 179 | 0.431 | 0.369 | -0.062 |
| 0.5-0.6 | 165 | 0.571 | 0.594 | +0.023 |
| 0.6-0.7 | 197 | 0.646 | 0.706 | +0.060 |
| 0.7-0.8 | 76 | 0.738 | 0.697 | -0.041 |
| 0.8-0.9 | 45 | 0.844 | 0.933 | +0.090 |
| 0.9-1.0 | 2 | 0.917 | 1.000 | +0.083 |

## The margin through the grid

Margin CRPS from the grid's own marginal, points lattice applied: 7.290; from the state's lattice pmf directly: 7.290 (2023-2025).

## The exact score, for what it is

Mean P(top exact score) with the points lattice: 0.0140.

| grid | games | top score was right | actual score in the top 10 cells | actual score in the top 50 cells | mean -log P(actual score) | median rank of the actual score |
|---|---|---|---|---|---|---|
| margin lattice only | 816 | 0.0061 | 0.0417 | 0.1642 | 7.137 | 307 |
| with the points lattice | 816 | 0.0086 | 0.0870 | 0.2108 | 6.878 | 230 |

### Points lattice fitted for 2026

| 0 | 3 | 6 | 7 | 10 | 13 | 14 | 16 | 17 | 20 | 21 | 23 | 24 | 27 | 28 | 30 | 31 | 34 | 35 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1.77 | 2.20 | 2.09 | 1.28 | 2.74 | 1.55 | 1.02 | 1.06 | 1.68 | 2.08 | 0.83 | 0.96 | 1.46 | 1.51 | 0.79 | 1.21 | 1.39 | 1.80 | 0.57 |

## What the card would have said: the last 10 regular-season games of 2026

Decimal means, never rounded integers; the market column is the closing line for comparison, not an input.

| game | projection | P(home) | total 80% range | most likely score | market (spread / total) | actual |
|---|---|---|---|---|---|---|
| NO at BAL | 26.9-18.1, total 45.0 | 75% | 29-61 | 20-17 (1.3%) | -8.5 / 45.5 | 17-24 |
| PHI at TEN | 17.8-25.2, total 43.0 | 28% | 27-59 | 17-20 (1.3%) | +7.0 / 39.5 | 20-24 |
| PIT at NE | 23.9-18.6, total 42.5 | 66% | 26-59 | 20-17 (1.5%) | -4.5 / 41.5 | 20-3 |
| JAX at DEN | 19.7-23.7, total 43.4 | 38% | 27-60 | 17-20 (1.4%) | -2.5 / 45.5 | 20-13 |
| LV at LAC | 24.0-21.0, total 44.9 | 59% | 29-62 | 20-17 (1.4%) | -6.5 / 43.5 | 14-26 |
| MIA at SF | 28.2-17.4, total 45.6 | 80% | 30-62 | 20-17 (1.2%) | -12.5 / 44.5 | 35-13 |
| SEA at ARI | 20.3-24.2, total 44.5 | 38% | 28-61 | 17-20 (1.3%) | +3.5 / 40.5 | 7-31 |
| WAS at DAL | 27.0-24.6, total 51.5 | 57% | 35-69 | 27-24 (1.1%) | -3.5 / 51.5 | 37-20 |
| IND at KC | 25.7-20.0, total 45.7 | 67% | 29-62 | 20-17 (1.3%) | -6.0 / 46.5 | 33-30 |
| NYG at LA | 27.4-21.7, total 49.1 | 67% | 33-66 | 20-17 (1.1%) | -6.5 / 47.5 | 28-6 |
