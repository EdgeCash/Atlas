# NFL reference benchmarks

Out-of-sample scores for the reference models in `atlas/models/reference.py`, seasons 2020-2026, each forecast by references fitted only on the seasons before it (training starts in 2011). Frame: completed games with a closing line (`atlas/research/nfl_dataset.py`), 1647 regular-season and 78 playoff games. Elo is FiveThirtyEight's, walk-forward (`atlas/models/elo.py`); `atlas_epa` is the opponent-adjusted net EPA difference as it stood before the week.

Lower is better everywhere. CRPS is on the integer margin lattice and reads like an absolute error; Brier is the home-win probability (0.25 is a coin flip); `log_margin` is the negative log probability of the exact margin in nats; ECE is the count-weighted gap between forecast and observed home-win frequency across ten bins. The same key-number lattice, refit on each training window against the market's means, is applied to every model.

## Reporting window, regular season 2023-2025

The plan's targets (`docs/MODEL_PLAN_NFL.md` §6) are set against this window.

| model | games | crps | brier | log_margin | mae | ece |
|---|---|---|---|---|---|---|
| naive | 816 | 8.024 | 0.249 | 3.963 | 11.10 | 0.019 |
| elo | 816 | 7.372 | 0.223 | 3.880 | 10.24 | 0.042 |
| atlas_epa | 816 | 7.391 | 0.224 | 3.883 | 10.31 | 0.041 |
| market | 816 | 7.075 | 0.211 | 3.839 | 9.74 | 0.049 |

## Regular season, every scored season pooled

| model | games | crps | brier | log_margin | mae | ece |
|---|---|---|---|---|---|---|
| naive | 1647 | 7.954 | 0.249 | 3.969 | 11.04 | 0.024 |
| elo | 1647 | 7.340 | 0.223 | 3.890 | 10.23 | 0.041 |
| atlas_epa | 1647 | 7.378 | 0.225 | 3.895 | 10.32 | 0.031 |
| market | 1647 | 7.070 | 0.211 | 3.854 | 9.80 | 0.038 |

## By season (regular season)

| model | season | games | crps | brier | log_margin | mae | ece |
|---|---|---|---|---|---|---|---|
| naive | 2020 | 256 | 7.970 | 0.252 | 3.971 | 11.10 | 0.064 |
| naive | 2021 | 272 | 8.716 | 0.252 | 4.103 | 12.21 | 0.052 |
| naive | 2022 | 271 | 6.899 | 0.244 | 3.848 | 9.51 | 0.015 |
| naive | 2023 | 272 | 8.032 | 0.247 | 3.960 | 11.07 | 0.003 |
| naive | 2024 | 272 | 8.076 | 0.251 | 3.997 | 11.17 | 0.042 |
| naive | 2025 | 272 | 7.964 | 0.248 | 3.933 | 11.06 | 0.019 |
| naive | 2026 | 32 | 8.485 | 0.247 | 4.004 | 12.22 | 0.021 |
| elo | 2020 | 256 | 7.236 | 0.216 | 3.873 | 10.07 | 0.087 |
| elo | 2021 | 272 | 7.975 | 0.230 | 4.013 | 11.28 | 0.087 |
| elo | 2022 | 271 | 6.589 | 0.224 | 3.798 | 9.09 | 0.044 |
| elo | 2023 | 272 | 7.602 | 0.232 | 3.905 | 10.45 | 0.078 |
| elo | 2024 | 272 | 7.271 | 0.213 | 3.893 | 10.06 | 0.062 |
| elo | 2025 | 272 | 7.241 | 0.223 | 3.843 | 10.21 | 0.048 |
| elo | 2026 | 32 | 8.350 | 0.233 | 3.994 | 12.20 | 0.059 |
| atlas_epa | 2020 | 256 | 7.226 | 0.215 | 3.875 | 10.02 | 0.079 |
| atlas_epa | 2021 | 272 | 8.034 | 0.230 | 4.022 | 11.33 | 0.082 |
| atlas_epa | 2022 | 271 | 6.652 | 0.228 | 3.806 | 9.24 | 0.025 |
| atlas_epa | 2023 | 272 | 7.546 | 0.231 | 3.899 | 10.37 | 0.046 |
| atlas_epa | 2024 | 272 | 7.318 | 0.216 | 3.898 | 10.20 | 0.067 |
| atlas_epa | 2025 | 272 | 7.309 | 0.225 | 3.851 | 10.36 | 0.072 |
| atlas_epa | 2026 | 32 | 8.858 | 0.249 | 4.060 | 13.35 | 0.235 |
| market | 2020 | 256 | 7.061 | 0.203 | 3.855 | 9.83 | 0.070 |
| market | 2021 | 272 | 7.663 | 0.217 | 3.976 | 10.78 | 0.117 |
| market | 2022 | 271 | 6.358 | 0.210 | 3.767 | 8.74 | 0.046 |
| market | 2023 | 272 | 7.273 | 0.217 | 3.862 | 9.90 | 0.056 |
| market | 2024 | 272 | 7.041 | 0.203 | 3.860 | 9.61 | 0.094 |
| market | 2025 | 272 | 6.913 | 0.212 | 3.795 | 9.72 | 0.022 |
| market | 2026 | 32 | 8.001 | 0.221 | 3.937 | 11.56 | 0.204 |

## By week (regular season)

Weeks 1-2 test the prior; 13+ test what has been learned in season.

| model | week_bucket | games | crps | brier | log_margin | mae | ece |
|---|---|---|---|---|---|---|---|
| naive | wk 1-3 | 224 | 7.403 | 0.251 | 3.929 | 10.22 | 0.050 |
| naive | wk 3-7 | 365 | 8.056 | 0.251 | 3.995 | 11.26 | 0.044 |
| naive | wk 7-13 | 517 | 7.868 | 0.247 | 3.924 | 10.89 | 0.010 |
| naive | wk 13+ | 541 | 8.194 | 0.248 | 4.012 | 11.39 | 0.017 |
| elo | wk 1-3 | 224 | 6.930 | 0.225 | 3.866 | 9.51 | 0.057 |
| elo | wk 3-7 | 365 | 7.626 | 0.236 | 3.945 | 10.72 | 0.053 |
| elo | wk 7-13 | 517 | 7.274 | 0.220 | 3.847 | 10.02 | 0.045 |
| elo | wk 13+ | 541 | 7.380 | 0.218 | 3.904 | 10.41 | 0.047 |
| atlas_epa | wk 1-3 | 224 | 6.946 | 0.221 | 3.868 | 9.63 | 0.068 |
| atlas_epa | wk 3-7 | 365 | 7.698 | 0.239 | 3.956 | 10.90 | 0.048 |
| atlas_epa | wk 7-13 | 517 | 7.308 | 0.222 | 3.850 | 10.11 | 0.024 |
| atlas_epa | wk 13+ | 541 | 7.409 | 0.219 | 3.908 | 10.41 | 0.050 |
| market | wk 1-3 | 224 | 6.747 | 0.218 | 3.839 | 9.21 | 0.056 |
| market | wk 3-7 | 365 | 7.334 | 0.221 | 3.908 | 10.18 | 0.046 |
| market | wk 7-13 | 517 | 7.060 | 0.212 | 3.818 | 9.76 | 0.026 |
| market | wk 13+ | 541 | 7.036 | 0.199 | 3.859 | 9.82 | 0.070 |

## By closing spread (regular season)

The NFL lives between 0 and 7; with parity, few games sit past 10.

| model | spread_bucket | games | crps | brier | log_margin | mae | ece |
|---|---|---|---|---|---|---|---|
| naive | |spread| 0-3 | 384 | 7.031 | 0.257 | 3.848 | 9.84 | 0.099 |
| naive | |spread| 3-6 | 631 | 7.430 | 0.251 | 3.876 | 10.21 | 0.045 |
| naive | |spread| 6-10 | 433 | 8.322 | 0.248 | 4.055 | 11.68 | 0.027 |
| naive | |spread| 10+ | 199 | 10.592 | 0.226 | 4.312 | 14.62 | 0.187 |
| elo | |spread| 0-3 | 384 | 7.043 | 0.257 | 3.843 | 9.84 | 0.068 |
| elo | |spread| 3-6 | 631 | 7.237 | 0.242 | 3.846 | 9.97 | 0.062 |
| elo | |spread| 6-10 | 433 | 7.425 | 0.207 | 3.945 | 10.44 | 0.091 |
| elo | |spread| 10+ | 199 | 8.058 | 0.132 | 3.998 | 11.38 | 0.106 |
| atlas_epa | |spread| 0-3 | 384 | 7.089 | 0.258 | 3.853 | 9.90 | 0.093 |
| atlas_epa | |spread| 3-6 | 631 | 7.260 | 0.245 | 3.850 | 10.08 | 0.043 |
| atlas_epa | |spread| 6-10 | 433 | 7.490 | 0.208 | 3.952 | 10.54 | 0.089 |
| atlas_epa | |spread| 10+ | 199 | 8.068 | 0.133 | 3.998 | 11.38 | 0.111 |
| market | |spread| 0-3 | 384 | 6.864 | 0.246 | 3.819 | 9.48 | 0.037 |
| market | |spread| 3-6 | 631 | 7.097 | 0.236 | 3.830 | 9.68 | 0.017 |
| market | |spread| 6-10 | 433 | 7.020 | 0.187 | 3.891 | 9.87 | 0.053 |
| market | |spread| 10+ | 199 | 7.492 | 0.115 | 3.923 | 10.63 | 0.083 |

## The quarterback test (regular season)

Games where at least one side's quarterback of record differs from its previous game's. A model with a working QB state should be no worse here than elsewhere; the market's residual on these games says how much it under-adjusts.

| model | quarterback | games | crps | brier | log_margin | mae | ece |
|---|---|---|---|---|---|---|---|
| naive | a side changed QB | 385 | 8.060 | 0.248 | 4.036 | 11.19 | 0.019 |
| naive | same quarterbacks | 1262 | 7.921 | 0.249 | 3.949 | 11.00 | 0.025 |
| elo | a side changed QB | 385 | 7.631 | 0.227 | 3.992 | 10.52 | 0.066 |
| elo | same quarterbacks | 1262 | 7.252 | 0.222 | 3.859 | 10.15 | 0.036 |
| atlas_epa | a side changed QB | 385 | 7.669 | 0.227 | 3.995 | 10.66 | 0.074 |
| atlas_epa | same quarterbacks | 1262 | 7.290 | 0.224 | 3.865 | 10.21 | 0.035 |
| market | a side changed QB | 385 | 7.109 | 0.201 | 3.918 | 9.90 | 0.053 |
| market | same quarterbacks | 1262 | 7.058 | 0.214 | 3.835 | 9.77 | 0.034 |

## Playoffs (never fitted, always scored)

| model | games | crps | brier | log_margin | mae | ece |
|---|---|---|---|---|---|---|
| naive | 78 | 7.695 | 0.239 | 3.777 | 10.63 | 0.095 |
| elo | 78 | 7.199 | 0.212 | 3.712 | 9.85 | 0.087 |
| atlas_epa | 78 | 7.231 | 0.214 | 3.718 | 9.94 | 0.095 |
| market | 78 | 7.184 | 0.208 | 3.714 | 9.81 | 0.146 |

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
| 0.2-0.3 | 63 | 0.267 | 0.349 | +0.083 |
| 0.3-0.4 | 170 | 0.357 | 0.315 | -0.043 |
| 0.4-0.5 | 346 | 0.454 | 0.379 | -0.076 |
| 0.5-0.6 | 401 | 0.552 | 0.504 | -0.048 |
| 0.6-0.7 | 359 | 0.647 | 0.656 | +0.009 |
| 0.7-0.8 | 224 | 0.743 | 0.759 | +0.016 |
| 0.8-0.9 | 69 | 0.842 | 0.848 | +0.006 |
| 0.9-1.0 | 2 | 0.908 | 1.000 | +0.092 |

### market

| bin | n | forecast | observed | gap |
|---|---|---|---|---|
| 0.1-0.2 | 27 | 0.158 | 0.259 | +0.102 |
| 0.2-0.3 | 84 | 0.263 | 0.202 | -0.061 |
| 0.3-0.4 | 206 | 0.347 | 0.296 | -0.051 |
| 0.4-0.5 | 343 | 0.431 | 0.392 | -0.039 |
| 0.5-0.6 | 334 | 0.570 | 0.542 | -0.028 |
| 0.6-0.7 | 380 | 0.648 | 0.664 | +0.017 |
| 0.7-0.8 | 186 | 0.744 | 0.777 | +0.033 |
| 0.8-0.9 | 80 | 0.844 | 0.950 | +0.106 |
| 0.9-1.0 | 7 | 0.919 | 0.857 | -0.061 |
