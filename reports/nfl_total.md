# NFL total and joint score grid

Walk-forward, seasons 2020-2026. The total is the quarterback state model's implied home-plus-away points, recalibrated on the training seasons' own state forecasts with the wind (zero in a dome) as the one game-level term. The margin (state mean and sd through the key-number lattice) and the total (discretised normal) meet on a 60x60 grid over (home, away) points, reweighted by the points lattice; every headline number below is a mean of that grid.

## Calibration fitted, per season

| season | intercept | slope on state total | wind_effective | sigma | raw sigma | train games |
|---|---|---|---|---|---|---|
| 2020 | +23.5 | 0.519 | -0.361 | 13.92 | 14.21 | 768 |
| 2021 | +16.6 | 0.700 | -0.379 | 13.56 | 13.77 | 768 |
| 2022 | +23.0 | 0.557 | -0.365 | 13.38 | 13.72 | 784 |
| 2023 | +17.5 | 0.653 | -0.323 | 13.42 | 13.63 | 799 |
| 2024 | +20.6 | 0.567 | -0.344 | 13.32 | 13.60 | 815 |
| 2025 | +18.8 | 0.608 | -0.287 | 13.19 | 13.36 | 815 |
| 2026 | +19.5 | 0.615 | -0.349 | 13.06 | 13.33 | 816 |

## Total, regular season 2023-2025

`over_brier` and `over_ece` score P(over the closing total); a push counts half. A model weaker than the market is over-confident on P(over) by construction, so that ECE measures the gap to the market, not the total's own distribution, which CRPS does.

| model | games | crps | mae | over_brier | over_ece |
|---|---|---|---|---|---|
| naive | 816 | 7.614 | 10.68 | 0.263 | 0.102 |
| state_raw | 816 | 7.471 | 10.54 | 0.256 | 0.074 |
| total | 816 | 7.355 | 10.37 | 0.254 | 0.059 |
| market | 816 | 7.240 | 10.12 | 0.248 | 0.006 |

## Total, every scored season pooled

| model | games | crps | mae | over_brier | over_ece |
|---|---|---|---|---|---|
| naive | 1647 | 7.783 | 10.98 | 0.264 | 0.111 |
| state_raw | 1647 | 7.604 | 10.76 | 0.258 | 0.087 |
| total | 1647 | 7.511 | 10.62 | 0.256 | 0.079 |
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
| state_raw | 2024 | 272 | 7.285 | 10.18 | 0.257 | 0.086 |
| state_raw | 2025 | 272 | 7.556 | 10.63 | 0.252 | 0.071 |
| state_raw | 2026 | 32 | 8.820 | 12.13 | 0.271 | 0.174 |
| total | 2020 | 256 | 7.541 | 10.61 | 0.255 | 0.106 |
| total | 2021 | 272 | 7.598 | 10.93 | 0.254 | 0.104 |
| total | 2022 | 271 | 7.704 | 10.85 | 0.261 | 0.110 |
| total | 2023 | 272 | 7.394 | 10.58 | 0.255 | 0.100 |
| total | 2024 | 272 | 7.224 | 10.06 | 0.257 | 0.077 |
| total | 2025 | 272 | 7.446 | 10.45 | 0.251 | 0.034 |
| total | 2026 | 32 | 8.887 | 12.34 | 0.280 | 0.139 |
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
| state_raw | wk 1-3 | 224 | 7.664 | 11.16 | 0.261 | 0.116 |
| state_raw | wk 3-7 | 365 | 7.135 | 10.02 | 0.248 | 0.059 |
| state_raw | wk 7-13 | 517 | 7.538 | 10.64 | 0.260 | 0.080 |
| state_raw | wk 13+ | 541 | 7.958 | 11.20 | 0.262 | 0.112 |
| total | wk 1-3 | 224 | 7.583 | 10.95 | 0.261 | 0.085 |
| total | wk 3-7 | 365 | 7.189 | 10.21 | 0.251 | 0.058 |
| total | wk 7-13 | 517 | 7.370 | 10.36 | 0.254 | 0.077 |
| total | wk 13+ | 541 | 7.834 | 11.00 | 0.259 | 0.105 |
| market | wk 1-3 | 224 | 7.397 | 10.61 | 0.250 | 0.027 |
| market | wk 3-7 | 365 | 7.030 | 9.94 | 0.247 | 0.041 |
| market | wk 7-13 | 517 | 7.181 | 10.09 | 0.247 | 0.022 |
| market | wk 13+ | 541 | 7.642 | 10.62 | 0.248 | 0.024 |

## Total, playoffs (never fitted, always scored)

| model | games | crps | mae | over_brier | over_ece |
|---|---|---|---|---|---|
| naive | 78 | 7.999 | 10.97 | 0.241 | 0.059 |
| state_raw | 78 | 8.138 | 11.61 | 0.257 | 0.131 |
| total | 78 | 7.764 | 10.85 | 0.240 | 0.089 |
| market | 78 | 7.824 | 10.89 | 0.244 | 0.013 |

## P(home) by closing spread, regular season 2023-2025: the grid against the market

The plan asks whether the 65-80% bins are honest, because that is where the NFL lives.

| bucket | games | grid P(home) | observed | grid gap | market P(home) | market gap |
|---|---|---|---|---|---|---|
| |spread| 0-3 | 203 | 0.509 | 0.483 | +0.026 | 0.504 | +0.021 |
| |spread| 3-6 | 327 | 0.524 | 0.520 | +0.004 | 0.517 | -0.003 |
| |spread| 6-10 | 207 | 0.576 | 0.563 | +0.013 | 0.562 | -0.001 |
| |spread| 10+ | 79 | 0.676 | 0.734 | -0.058 | 0.700 | -0.035 |

### Reliability, grid

| bin | n | forecast | observed | gap |
|---|---|---|---|---|
| 0.1-0.2 | 12 | 0.168 | 0.250 | +0.082 |
| 0.2-0.3 | 35 | 0.257 | 0.371 | +0.114 |
| 0.3-0.4 | 95 | 0.359 | 0.295 | -0.064 |
| 0.4-0.5 | 189 | 0.454 | 0.415 | -0.039 |
| 0.5-0.6 | 174 | 0.547 | 0.552 | +0.005 |
| 0.6-0.7 | 152 | 0.648 | 0.645 | -0.003 |
| 0.7-0.8 | 113 | 0.742 | 0.770 | +0.028 |
| 0.8-0.9 | 43 | 0.840 | 0.837 | -0.002 |
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

Margin CRPS from the grid's own marginal, points lattice applied: 7.313; from the state's lattice pmf directly: 7.313 (2023-2025).

## The exact score, for what it is

Mean P(top exact score) with the points lattice: 0.0140.

| grid | games | top score was right | actual score in the top 10 cells | actual score in the top 50 cells | mean -log P(actual score) | median rank of the actual score |
|---|---|---|---|---|---|---|
| margin lattice only | 816 | 0.0049 | 0.0404 | 0.1618 | 7.138 | 305 |
| with the points lattice | 816 | 0.0074 | 0.0870 | 0.2157 | 6.880 | 228 |

### Points lattice fitted for 2026

| 0 | 3 | 6 | 7 | 10 | 13 | 14 | 16 | 17 | 20 | 21 | 23 | 24 | 27 | 28 | 30 | 31 | 34 | 35 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1.77 | 2.21 | 2.10 | 1.28 | 2.75 | 1.55 | 1.02 | 1.06 | 1.68 | 2.08 | 0.83 | 0.96 | 1.45 | 1.50 | 0.79 | 1.21 | 1.39 | 1.80 | 0.57 |

## What the card would have said: the last 10 regular-season games of 2026

Decimal means, never rounded integers; the market column is the closing line for comparison, not an input.

| game | projection | P(home) | total 80% range | most likely score | market (spread / total) | actual |
|---|---|---|---|---|---|---|
| NO at BAL | 27.0-17.8, total 44.8 | 76% | 29-61 | 20-17 (1.3%) | -8.5 / 45.5 | 17-24 |
| PHI at TEN | 18.2-24.9, total 43.0 | 30% | 27-60 | 17-20 (1.3%) | +7.0 / 39.5 | 20-24 |
| PIT at NE | 23.4-18.9, total 42.3 | 64% | 26-59 | 20-17 (1.6%) | -4.5 / 41.5 | 20-3 |
| JAX at DEN | 19.6-23.4, total 43.0 | 39% | 27-60 | 17-20 (1.4%) | -2.5 / 45.5 | 20-13 |
| LV at LAC | 24.1-20.7, total 44.7 | 60% | 28-61 | 20-17 (1.4%) | -6.5 / 43.5 | 14-26 |
| MIA at SF | 27.7-17.2, total 45.0 | 79% | 29-61 | 20-17 (1.2%) | -12.5 / 44.5 | 35-13 |
| SEA at ARI | 20.2-25.1, total 45.3 | 36% | 29-62 | 17-20 (1.2%) | +3.5 / 40.5 | 7-31 |
| WAS at DAL | 27.0-24.5, total 51.6 | 57% | 35-69 | 27-24 (1.1%) | -3.5 / 51.5 | 37-20 |
| IND at KC | 26.2-19.9, total 46.1 | 69% | 30-63 | 20-17 (1.3%) | -6.0 / 46.5 | 33-30 |
| NYG at LA | 27.0-22.0, total 49.0 | 65% | 33-66 | 20-17 (1.1%) | -6.5 / 47.5 | 28-6 |
