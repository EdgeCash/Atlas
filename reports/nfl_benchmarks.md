# NFL reference benchmarks

Out-of-sample scores for the reference models in `atlas/models/reference.py`, seasons 2020-2026, each forecast by references fitted only on the seasons before it (training starts in 2011). Frame: completed games with a closing line (`atlas/research/nfl_dataset.py`), 1647 regular-season and 78 playoff games. Elo is FiveThirtyEight's, walk-forward (`atlas/models/elo.py`); `atlas_epa` is the opponent-adjusted net EPA difference as it stood before the week.

Lower is better everywhere. CRPS is on the integer margin lattice and reads like an absolute error; Brier is the home-win probability (0.25 is a coin flip); `log_margin` is the negative log probability of the exact margin in nats; ECE is the count-weighted gap between forecast and observed home-win frequency across ten bins. The same key-number lattice, refit on each training window against the market's means, is applied to every model.

## Reporting window, regular season 2023-2025

The plan's targets (`docs/MODEL_PLAN_NFL.md` §6) are set against this window.

| model | games | crps | brier | log_margin | mae | ece |
|---|---|---|---|---|---|---|
| naive | 816 | 8.024 | 0.249 | 3.960 | 11.10 | 0.020 |
| elo | 816 | 7.372 | 0.223 | 3.876 | 10.24 | 0.043 |
| atlas_epa | 816 | 7.391 | 0.224 | 3.879 | 10.31 | 0.044 |
| market | 816 | 7.074 | 0.211 | 3.835 | 9.74 | 0.049 |

## Regular season, every scored season pooled

| model | games | crps | brier | log_margin | mae | ece |
|---|---|---|---|---|---|---|
| naive | 1647 | 7.957 | 0.249 | 3.968 | 11.04 | 0.026 |
| elo | 1647 | 7.343 | 0.223 | 3.889 | 10.23 | 0.042 |
| atlas_epa | 1647 | 7.381 | 0.225 | 3.894 | 10.32 | 0.033 |
| market | 1647 | 7.071 | 0.211 | 3.853 | 9.80 | 0.038 |

## By season (regular season)

| model | season | games | crps | brier | log_margin | mae | ece |
|---|---|---|---|---|---|---|---|
| naive | 2020 | 256 | 7.985 | 0.252 | 3.974 | 11.10 | 0.070 |
| naive | 2021 | 272 | 8.718 | 0.252 | 4.104 | 12.21 | 0.055 |
| naive | 2022 | 271 | 6.900 | 0.244 | 3.850 | 9.51 | 0.013 |
| naive | 2023 | 272 | 8.031 | 0.247 | 3.954 | 11.07 | 0.002 |
| naive | 2024 | 272 | 8.077 | 0.251 | 3.992 | 11.17 | 0.043 |
| naive | 2025 | 272 | 7.964 | 0.248 | 3.933 | 11.06 | 0.020 |
| naive | 2026 | 32 | 8.484 | 0.247 | 4.001 | 12.22 | 0.021 |
| elo | 2020 | 256 | 7.250 | 0.217 | 3.877 | 10.07 | 0.079 |
| elo | 2021 | 272 | 7.978 | 0.230 | 4.015 | 11.28 | 0.089 |
| elo | 2022 | 271 | 6.592 | 0.224 | 3.800 | 9.09 | 0.044 |
| elo | 2023 | 272 | 7.602 | 0.232 | 3.900 | 10.45 | 0.076 |
| elo | 2024 | 272 | 7.272 | 0.213 | 3.888 | 10.06 | 0.063 |
| elo | 2025 | 272 | 7.241 | 0.223 | 3.842 | 10.21 | 0.046 |
| elo | 2026 | 32 | 8.350 | 0.233 | 3.991 | 12.20 | 0.059 |
| atlas_epa | 2020 | 256 | 7.240 | 0.216 | 3.879 | 10.02 | 0.084 |
| atlas_epa | 2021 | 272 | 8.036 | 0.231 | 4.023 | 11.33 | 0.075 |
| atlas_epa | 2022 | 271 | 6.654 | 0.228 | 3.808 | 9.24 | 0.029 |
| atlas_epa | 2023 | 272 | 7.545 | 0.231 | 3.893 | 10.37 | 0.046 |
| atlas_epa | 2024 | 272 | 7.318 | 0.216 | 3.893 | 10.20 | 0.070 |
| atlas_epa | 2025 | 272 | 7.309 | 0.225 | 3.851 | 10.36 | 0.079 |
| atlas_epa | 2026 | 32 | 8.860 | 0.249 | 4.057 | 13.35 | 0.235 |
| market | 2020 | 256 | 7.067 | 0.204 | 3.858 | 9.83 | 0.076 |
| market | 2021 | 272 | 7.665 | 0.217 | 3.977 | 10.78 | 0.102 |
| market | 2022 | 271 | 6.359 | 0.210 | 3.769 | 8.74 | 0.046 |
| market | 2023 | 272 | 7.271 | 0.217 | 3.856 | 9.90 | 0.055 |
| market | 2024 | 272 | 7.040 | 0.203 | 3.855 | 9.61 | 0.094 |
| market | 2025 | 272 | 6.912 | 0.212 | 3.795 | 9.72 | 0.023 |
| market | 2026 | 32 | 8.001 | 0.221 | 3.934 | 11.56 | 0.204 |

## By week (regular season)

Weeks 1-2 test the prior; 13+ test what has been learned in season.

| model | week_bucket | games | crps | brier | log_margin | mae | ece |
|---|---|---|---|---|---|---|---|
| naive | wk 1-3 | 224 | 7.407 | 0.251 | 3.933 | 10.22 | 0.052 |
| naive | wk 3-7 | 365 | 8.062 | 0.251 | 3.998 | 11.26 | 0.047 |
| naive | wk 7-13 | 517 | 7.872 | 0.248 | 3.920 | 10.89 | 0.013 |
| naive | wk 13+ | 541 | 8.194 | 0.248 | 4.009 | 11.39 | 0.019 |
| elo | wk 1-3 | 224 | 6.935 | 0.225 | 3.870 | 9.51 | 0.061 |
| elo | wk 3-7 | 365 | 7.632 | 0.236 | 3.948 | 10.72 | 0.054 |
| elo | wk 7-13 | 517 | 7.277 | 0.220 | 3.843 | 10.02 | 0.045 |
| elo | wk 13+ | 541 | 7.382 | 0.218 | 3.902 | 10.41 | 0.043 |
| atlas_epa | wk 1-3 | 224 | 6.952 | 0.221 | 3.873 | 9.63 | 0.068 |
| atlas_epa | wk 3-7 | 365 | 7.703 | 0.239 | 3.960 | 10.90 | 0.050 |
| atlas_epa | wk 7-13 | 517 | 7.310 | 0.222 | 3.847 | 10.11 | 0.025 |
| atlas_epa | wk 13+ | 541 | 7.410 | 0.220 | 3.905 | 10.41 | 0.052 |
| market | wk 1-3 | 224 | 6.749 | 0.218 | 3.843 | 9.21 | 0.054 |
| market | wk 3-7 | 365 | 7.338 | 0.221 | 3.911 | 10.18 | 0.048 |
| market | wk 7-13 | 517 | 7.061 | 0.212 | 3.814 | 9.76 | 0.024 |
| market | wk 13+ | 541 | 7.034 | 0.199 | 3.856 | 9.82 | 0.070 |

## By closing spread (regular season)

The NFL lives between 0 and 7; with parity, few games sit past 10.

| model | spread_bucket | games | crps | brier | log_margin | mae | ece |
|---|---|---|---|---|---|---|---|
| naive | |spread| 0-3 | 384 | 7.042 | 0.258 | 3.849 | 9.84 | 0.101 |
| naive | |spread| 3-6 | 631 | 7.437 | 0.252 | 3.874 | 10.21 | 0.047 |
| naive | |spread| 6-10 | 433 | 8.325 | 0.248 | 4.058 | 11.68 | 0.029 |
| naive | |spread| 10+ | 199 | 10.568 | 0.225 | 4.305 | 14.62 | 0.184 |
| elo | |spread| 0-3 | 384 | 7.050 | 0.258 | 3.843 | 9.84 | 0.075 |
| elo | |spread| 3-6 | 631 | 7.242 | 0.242 | 3.844 | 9.97 | 0.066 |
| elo | |spread| 6-10 | 433 | 7.429 | 0.207 | 3.948 | 10.44 | 0.083 |
| elo | |spread| 10+ | 199 | 8.046 | 0.131 | 3.993 | 11.38 | 0.105 |
| atlas_epa | |spread| 0-3 | 384 | 7.096 | 0.258 | 3.853 | 9.90 | 0.096 |
| atlas_epa | |spread| 3-6 | 631 | 7.265 | 0.245 | 3.847 | 10.08 | 0.045 |
| atlas_epa | |spread| 6-10 | 433 | 7.494 | 0.208 | 3.955 | 10.54 | 0.090 |
| atlas_epa | |spread| 10+ | 199 | 8.056 | 0.133 | 3.993 | 11.38 | 0.111 |
| market | |spread| 0-3 | 384 | 6.869 | 0.247 | 3.818 | 9.48 | 0.039 |
| market | |spread| 3-6 | 631 | 7.099 | 0.236 | 3.827 | 9.68 | 0.017 |
| market | |spread| 6-10 | 433 | 7.021 | 0.187 | 3.893 | 9.87 | 0.055 |
| market | |spread| 10+ | 199 | 7.483 | 0.115 | 3.918 | 10.63 | 0.081 |

## The quarterback test (regular season)

Games where at least one side's quarterback of record differs from its previous game's. A model with a working QB state should be no worse here than elsewhere; the market's residual on these games says how much it under-adjusts.

| model | quarterback | games | crps | brier | log_margin | mae | ece |
|---|---|---|---|---|---|---|---|
| naive | a side changed QB | 385 | 8.066 | 0.249 | 4.039 | 11.19 | 0.021 |
| naive | same quarterbacks | 1262 | 7.923 | 0.249 | 3.947 | 11.00 | 0.028 |
| elo | a side changed QB | 385 | 7.637 | 0.228 | 3.995 | 10.52 | 0.067 |
| elo | same quarterbacks | 1262 | 7.254 | 0.222 | 3.857 | 10.15 | 0.036 |
| atlas_epa | a side changed QB | 385 | 7.674 | 0.227 | 3.998 | 10.66 | 0.079 |
| atlas_epa | same quarterbacks | 1262 | 7.292 | 0.224 | 3.863 | 10.21 | 0.034 |
| market | a side changed QB | 385 | 7.112 | 0.201 | 3.920 | 9.90 | 0.059 |
| market | same quarterbacks | 1262 | 7.059 | 0.214 | 3.833 | 9.77 | 0.034 |

## Playoffs (never fitted, always scored)

| model | games | crps | brier | log_margin | mae | ece |
|---|---|---|---|---|---|---|
| naive | 78 | 7.686 | 0.239 | 3.768 | 10.63 | 0.092 |
| elo | 78 | 7.197 | 0.212 | 3.703 | 9.85 | 0.087 |
| atlas_epa | 78 | 7.226 | 0.214 | 3.710 | 9.94 | 0.093 |
| market | 78 | 7.181 | 0.208 | 3.705 | 9.81 | 0.145 |

## Fitted parameters (last training window)

Points of home margin per unit of the feature, and the fitted home advantage.

| model | coefficient | hfa | sigma |
|---|---|---|---|
| naive |  | 3.05 | 14.46 |
| elo | 1.023 | 1.18 | 13.39 |
| atlas_epa | 35.151 | 1.81 | 13.47 |
| market |  |  | 13.00 |

## Reliability, home-win probability (regular season)

### elo

| bin | n | forecast | observed | gap |
|---|---|---|---|---|
| 0.1-0.2 | 13 | 0.171 | 0.385 | +0.214 |
| 0.2-0.3 | 61 | 0.266 | 0.344 | +0.078 |
| 0.3-0.4 | 168 | 0.357 | 0.312 | -0.044 |
| 0.4-0.5 | 344 | 0.455 | 0.381 | -0.074 |
| 0.5-0.6 | 403 | 0.553 | 0.499 | -0.054 |
| 0.6-0.7 | 356 | 0.648 | 0.656 | +0.007 |
| 0.7-0.8 | 228 | 0.743 | 0.759 | +0.016 |
| 0.8-0.9 | 72 | 0.842 | 0.840 | -0.002 |
| 0.9-1.0 | 2 | 0.910 | 1.000 | +0.090 |

### market

| bin | n | forecast | observed | gap |
|---|---|---|---|---|
| 0.1-0.2 | 27 | 0.158 | 0.259 | +0.101 |
| 0.2-0.3 | 75 | 0.260 | 0.200 | -0.060 |
| 0.3-0.4 | 215 | 0.346 | 0.293 | -0.053 |
| 0.4-0.5 | 343 | 0.433 | 0.392 | -0.041 |
| 0.5-0.6 | 334 | 0.572 | 0.542 | -0.030 |
| 0.6-0.7 | 359 | 0.647 | 0.667 | +0.020 |
| 0.7-0.8 | 207 | 0.742 | 0.761 | +0.018 |
| 0.8-0.9 | 80 | 0.846 | 0.950 | +0.104 |
| 0.9-1.0 | 7 | 0.920 | 0.857 | -0.063 |
