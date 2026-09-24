# NFL total and joint score grid

Walk-forward, seasons 2020-2026. The total is the quarterback state model's implied home-plus-away points, recalibrated on the training seasons' own state forecasts with the wind (zero in a dome) as the one game-level term. The margin (state mean and sd through the key-number lattice) and the total (discretised normal) meet on a 60x60 grid over (home, away) points, reweighted by the points lattice; every headline number below is a mean of that grid.

## Calibration fitted, per season

| season | intercept | slope on state total | wind_effective | sigma | raw sigma | train games |
|---|---|---|---|---|---|---|
| 2020 | +23.6 | 0.517 | -0.356 | 13.92 | 14.21 | 768 |
| 2021 | +16.1 | 0.711 | -0.380 | 13.56 | 13.77 | 768 |
| 2022 | +23.1 | 0.554 | -0.366 | 13.39 | 13.72 | 784 |
| 2023 | +18.2 | 0.637 | -0.325 | 13.45 | 13.67 | 799 |
| 2024 | +21.8 | 0.541 | -0.348 | 13.35 | 13.66 | 815 |
| 2025 | +19.2 | 0.595 | -0.291 | 13.21 | 13.39 | 815 |
| 2026 | +18.1 | 0.639 | -0.349 | 13.08 | 13.31 | 816 |

## Total, regular season 2023-2025

`over_brier` and `over_ece` score P(over the closing total); a push counts half. A model weaker than the market is over-confident on P(over) by construction, so that ECE measures the gap to the market, not the total's own distribution, which CRPS does.

| model | games | crps | mae | over_brier | over_ece |
|---|---|---|---|---|---|
| naive | 816 | 7.614 | 10.68 | 0.263 | 0.102 |
| state_raw | 816 | 7.480 | 10.56 | 0.256 | 0.067 |
| total | 816 | 7.365 | 10.39 | 0.255 | 0.053 |
| market | 816 | 7.240 | 10.12 | 0.248 | 0.006 |

## Total, every scored season pooled

| model | games | crps | mae | over_brier | over_ece |
|---|---|---|---|---|---|
| naive | 1647 | 7.783 | 10.98 | 0.264 | 0.111 |
| state_raw | 1647 | 7.619 | 10.79 | 0.259 | 0.090 |
| total | 1647 | 7.525 | 10.64 | 0.256 | 0.075 |
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
| state_raw | 2020 | 256 | 7.555 | 10.69 | 0.254 | 0.080 |
| state_raw | 2021 | 272 | 7.805 | 11.26 | 0.261 | 0.132 |
| state_raw | 2022 | 271 | 7.760 | 10.88 | 0.266 | 0.126 |
| state_raw | 2023 | 272 | 7.622 | 10.89 | 0.262 | 0.094 |
| state_raw | 2024 | 272 | 7.271 | 10.17 | 0.256 | 0.091 |
| state_raw | 2025 | 272 | 7.547 | 10.63 | 0.252 | 0.044 |
| state_raw | 2026 | 32 | 8.920 | 12.29 | 0.277 | 0.151 |
| total | 2020 | 256 | 7.541 | 10.61 | 0.254 | 0.102 |
| total | 2021 | 272 | 7.626 | 10.96 | 0.255 | 0.107 |
| total | 2022 | 271 | 7.729 | 10.88 | 0.262 | 0.112 |
| total | 2023 | 272 | 7.424 | 10.63 | 0.256 | 0.102 |
| total | 2024 | 272 | 7.217 | 10.07 | 0.257 | 0.081 |
| total | 2025 | 272 | 7.453 | 10.47 | 0.251 | 0.022 |
| total | 2026 | 32 | 8.910 | 12.35 | 0.282 | 0.170 |
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
| state_raw | wk 1-3 | 224 | 7.672 | 11.17 | 0.262 | 0.102 |
| state_raw | wk 3-7 | 365 | 7.151 | 10.03 | 0.248 | 0.062 |
| state_raw | wk 7-13 | 517 | 7.557 | 10.65 | 0.260 | 0.087 |
| state_raw | wk 13+ | 541 | 7.973 | 11.26 | 0.264 | 0.117 |
| total | wk 1-3 | 224 | 7.584 | 10.94 | 0.261 | 0.090 |
| total | wk 3-7 | 365 | 7.203 | 10.22 | 0.251 | 0.057 |
| total | wk 7-13 | 517 | 7.388 | 10.39 | 0.254 | 0.067 |
| total | wk 13+ | 541 | 7.849 | 11.03 | 0.260 | 0.106 |
| market | wk 1-3 | 224 | 7.397 | 10.61 | 0.250 | 0.027 |
| market | wk 3-7 | 365 | 7.030 | 9.94 | 0.247 | 0.041 |
| market | wk 7-13 | 517 | 7.181 | 10.09 | 0.247 | 0.022 |
| market | wk 13+ | 541 | 7.642 | 10.62 | 0.248 | 0.024 |

## Total, playoffs (never fitted, always scored)

| model | games | crps | mae | over_brier | over_ece |
|---|---|---|---|---|---|
| naive | 78 | 7.999 | 10.97 | 0.241 | 0.059 |
| state_raw | 78 | 8.134 | 11.57 | 0.256 | 0.118 |
| total | 78 | 7.775 | 10.86 | 0.240 | 0.097 |
| market | 78 | 7.824 | 10.89 | 0.244 | 0.013 |

## P(home) by closing spread, regular season 2023-2025: the grid against the market

The plan asks whether the 65-80% bins are honest, because that is where the NFL lives.

| bucket | games | grid P(home) | observed | grid gap | market P(home) | market gap |
|---|---|---|---|---|---|---|
| |spread| 0-3 | 203 | 0.511 | 0.483 | +0.028 | 0.504 | +0.021 |
| |spread| 3-6 | 327 | 0.523 | 0.520 | +0.004 | 0.517 | -0.003 |
| |spread| 6-10 | 207 | 0.576 | 0.563 | +0.013 | 0.562 | -0.001 |
| |spread| 10+ | 79 | 0.673 | 0.734 | -0.061 | 0.700 | -0.035 |

### Reliability, grid

| bin | n | forecast | observed | gap |
|---|---|---|---|---|
| 0.1-0.2 | 9 | 0.163 | 0.222 | +0.059 |
| 0.2-0.3 | 36 | 0.254 | 0.361 | +0.107 |
| 0.3-0.4 | 98 | 0.359 | 0.316 | -0.042 |
| 0.4-0.5 | 186 | 0.454 | 0.417 | -0.038 |
| 0.5-0.6 | 172 | 0.547 | 0.558 | +0.011 |
| 0.6-0.7 | 160 | 0.646 | 0.625 | -0.021 |
| 0.7-0.8 | 111 | 0.741 | 0.766 | +0.024 |
| 0.8-0.9 | 42 | 0.841 | 0.857 | +0.016 |
| 0.9-1.0 | 2 | 0.911 | 1.000 | +0.089 |

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

Margin CRPS from the grid's own marginal, points lattice applied: 7.351; from the state's lattice pmf directly: 7.351 (2023-2025).

## The exact score, for what it is

Mean P(top exact score) with the points lattice: 0.0140.

| grid | games | top score was right | actual score in the top 10 cells | actual score in the top 50 cells | mean -log P(actual score) | median rank of the actual score |
|---|---|---|---|---|---|---|
| margin lattice only | 816 | 0.0061 | 0.0404 | 0.1630 | 7.148 | 312 |
| with the points lattice | 816 | 0.0086 | 0.0882 | 0.2120 | 6.889 | 231 |

### Points lattice fitted for 2026

| 0 | 3 | 6 | 7 | 10 | 13 | 14 | 16 | 17 | 20 | 21 | 23 | 24 | 27 | 28 | 30 | 31 | 34 | 35 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1.79 | 2.22 | 2.14 | 1.30 | 2.76 | 1.55 | 1.01 | 1.05 | 1.67 | 2.06 | 0.83 | 0.95 | 1.44 | 1.50 | 0.79 | 1.21 | 1.38 | 1.80 | 0.58 |

## What the card would have said: the last 10 regular-season games of 2026

Decimal means, never rounded integers; the market column is the closing line for comparison, not an input.

| game | projection | P(home) | total 80% range | most likely score | market (spread / total) | actual |
|---|---|---|---|---|---|---|
| NO at BAL | 26.7-18.6, total 45.3 | 73% | 29-62 | 20-17 (1.3%) | -8.5 / 45.5 | 17-24 |
| PHI at TEN | 18.4-24.7, total 43.1 | 32% | 27-60 | 17-20 (1.3%) | +7.0 / 39.5 | 20-24 |
| PIT at NE | 23.4-18.8, total 42.2 | 64% | 26-59 | 20-17 (1.5%) | -4.5 / 41.5 | 20-3 |
| JAX at DEN | 19.5-23.4, total 42.9 | 38% | 27-60 | 17-20 (1.4%) | -2.5 / 45.5 | 20-13 |
| LV at LAC | 23.8-20.7, total 44.4 | 60% | 28-61 | 20-17 (1.4%) | -6.5 / 43.5 | 14-26 |
| MIA at SF | 27.4-17.6, total 45.0 | 77% | 29-61 | 20-17 (1.2%) | -12.5 / 44.5 | 35-13 |
| SEA at ARI | 19.6-27.0, total 46.6 | 29% | 30-64 | 17-20 (1.1%) | +3.5 / 40.5 | 7-31 |
| WAS at DAL | 27.0-24.6, total 51.6 | 57% | 35-69 | 27-24 (1.1%) | -3.5 / 51.5 | 37-20 |
| IND at KC | 25.9-20.0, total 46.0 | 67% | 30-63 | 20-17 (1.3%) | -6.0 / 46.5 | 33-30 |
| NYG at LA | 26.9-22.0, total 48.9 | 65% | 32-66 | 20-17 (1.1%) | -6.5 / 47.5 | 28-6 |
