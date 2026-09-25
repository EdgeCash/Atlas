# NCAAF preseason prior

Walk-forward, seasons 2021-2025: each season's prior is fitted on every earlier season's (preseason facts -> eventual least-squares rating), then scored on that season's games beside the reference models, with the same lattice and scoring as `reports/ncaaf_benchmarks.md`. Frame: FBS-vs-FBS regular season.

## What the recipe learned (last training window)

Points of home margin per one standard deviation of each preseason feature, fitted directly on games. `sp_plus_def` is the SP+ defensive *rating* (points allowed), so a lower value is a better defence and its `def` coefficient is expected to be negative.

### net  -  game-level R² 0.318, residual sd 17.22 points, home advantage +2.52, n=4882 games

| feature | points_per_sd |
|---|---|
| sp_plus | +4.31 |
| fpi | +3.29 |
| returning_production | +1.73 |
| talent | +1.62 |
| new_coach_x_overach | -1.36 |
| new_coach | -1.21 |
| portal_in | +1.19 |
| sp_program_mean | +1.01 |
| recruiting_rank | -0.98 |

### off  -  from one stacked points regression, R² 0.223, residual sd 12.17 points per team-game, n=9764 team-games

| feature | points_per_sd |
|---|---|
| talent | +1.88 |
| sp_plus_off | +1.73 |
| fpi | +1.56 |
| sp_program_mean | +1.04 |
| returning_production | +1.01 |
| new_coach | -0.63 |
| new_coach_x_overach | -0.58 |
| portal_in | +0.47 |
| recruiting_rank | +0.26 |

### def  -  from one stacked points regression, R² 0.223, residual sd 12.17 points per team-game, n=9764 team-games

| feature | points_per_sd |
|---|---|
| fpi | +2.49 |
| sp_plus_def | -2.41 |
| recruiting_rank | -1.29 |
| portal_in | +0.81 |
| new_coach_x_overach | -0.71 |
| returning_production | +0.69 |
| new_coach | -0.59 |
| talent | -0.25 |
| sp_program_mean | +0.17 |

A team's prior net has sd 10.18 points across the 136 FBS teams of 2025; the game residual sd of 17.22 is the prior's own uncertainty and the state model's starting variance.

## How well the prior tracked the eventual rating, team level

| season | corr def | corr net | corr off |
|---|---|---|---|
| 2021 | 0.649 | 0.695 | 0.565 |
| 2022 | 0.698 | 0.796 | 0.728 |
| 2023 | 0.723 | 0.801 | 0.660 |
| 2024 | 0.709 | 0.743 | 0.646 |
| 2025 | 0.679 | 0.749 | 0.647 |

## Game-level scores, weeks 1-4 (where a prior is the whole forecast)

| model | games | crps | brier | log_margin | mae | ece |
|---|---|---|---|---|---|---|
| naive | 1020 | 12.628 | 0.234 | 4.397 | 17.63 | 0.044 |
| prior_fpi | 1020 | 9.769 | 0.179 | 4.135 | 13.77 | 0.032 |
| prior_sp | 1020 | 9.880 | 0.180 | 4.145 | 13.99 | 0.040 |
| elo | 1020 | 9.932 | 0.178 | 4.153 | 13.92 | 0.032 |
| market | 1020 | 8.545 | 0.158 | 4.002 | 12.10 | 0.023 |
| prior | 1020 | 9.435 | 0.173 | 4.104 | 13.35 | 0.024 |

## By week bucket, regular season

| model | week_bucket | games | crps | brier | log_margin | mae | ece |
|---|---|---|---|---|---|---|---|
| naive | wk 1-2 | 480 | 12.853 | 0.232 | 4.412 | 18.07 | 0.058 |
| naive | wk 3-4 | 540 | 12.427 | 0.236 | 4.383 | 17.24 | 0.034 |
| naive | wk 5-8 | 1075 | 10.549 | 0.244 | 4.222 | 14.47 | 0.016 |
| naive | wk 9-12 | 1131 | 11.158 | 0.244 | 4.290 | 15.57 | 0.015 |
| naive | wk 13+ | 504 | 11.609 | 0.252 | 4.335 | 16.25 | 0.055 |
| prior_fpi | wk 1-2 | 480 | 9.644 | 0.171 | 4.128 | 13.48 | 0.041 |
| prior_fpi | wk 3-4 | 540 | 9.879 | 0.187 | 4.141 | 14.03 | 0.048 |
| prior_fpi | wk 5-8 | 1075 | 9.486 | 0.216 | 4.106 | 13.31 | 0.026 |
| prior_fpi | wk 9-12 | 1131 | 10.142 | 0.216 | 4.191 | 14.33 | 0.027 |
| prior_fpi | wk 13+ | 504 | 10.740 | 0.227 | 4.268 | 15.08 | 0.054 |
| prior_sp | wk 1-2 | 480 | 9.711 | 0.173 | 4.133 | 13.68 | 0.032 |
| prior_sp | wk 3-4 | 540 | 10.031 | 0.187 | 4.155 | 14.26 | 0.059 |
| prior_sp | wk 5-8 | 1075 | 9.547 | 0.218 | 4.110 | 13.49 | 0.026 |
| prior_sp | wk 9-12 | 1131 | 10.003 | 0.215 | 4.176 | 14.18 | 0.033 |
| prior_sp | wk 13+ | 504 | 10.730 | 0.226 | 4.268 | 15.03 | 0.077 |
| elo | wk 1-2 | 480 | 10.157 | 0.181 | 4.184 | 14.16 | 0.030 |
| elo | wk 3-4 | 540 | 9.732 | 0.176 | 4.126 | 13.71 | 0.039 |
| elo | wk 5-8 | 1075 | 8.874 | 0.200 | 4.038 | 12.59 | 0.040 |
| elo | wk 9-12 | 1131 | 8.992 | 0.186 | 4.075 | 12.76 | 0.028 |
| elo | wk 13+ | 504 | 9.106 | 0.183 | 4.095 | 12.85 | 0.032 |
| market | wk 1-2 | 480 | 8.413 | 0.154 | 3.985 | 11.84 | 0.036 |
| market | wk 3-4 | 540 | 8.663 | 0.161 | 4.016 | 12.33 | 0.024 |
| market | wk 5-8 | 1075 | 8.511 | 0.188 | 3.995 | 11.95 | 0.022 |
| market | wk 9-12 | 1131 | 8.634 | 0.179 | 4.036 | 12.13 | 0.022 |
| market | wk 13+ | 504 | 8.872 | 0.181 | 4.069 | 12.50 | 0.055 |
| prior | wk 1-2 | 480 | 9.154 | 0.163 | 4.078 | 12.90 | 0.036 |
| prior | wk 3-4 | 540 | 9.684 | 0.182 | 4.128 | 13.75 | 0.021 |
| prior | wk 5-8 | 1075 | 9.365 | 0.212 | 4.096 | 13.19 | 0.023 |
| prior | wk 9-12 | 1131 | 9.896 | 0.209 | 4.170 | 13.90 | 0.040 |
| prior | wk 13+ | 504 | 10.811 | 0.232 | 4.281 | 15.18 | 0.078 |

## By season, weeks 1-4

| model | season | games | crps | brier | log_margin | mae | ece |
|---|---|---|---|---|---|---|---|
| naive | 2021 | 205 | 12.153 | 0.236 | 4.382 | 16.88 | 0.032 |
| naive | 2022 | 210 | 12.832 | 0.231 | 4.376 | 17.80 | 0.064 |
| naive | 2023 | 216 | 11.914 | 0.235 | 4.289 | 16.79 | 0.043 |
| naive | 2024 | 194 | 13.464 | 0.240 | 4.513 | 18.82 | 0.017 |
| naive | 2025 | 195 | 12.866 | 0.229 | 4.438 | 17.99 | 0.072 |
| prior_fpi | 2021 | 205 | 9.675 | 0.182 | 4.151 | 13.64 | 0.034 |
| prior_fpi | 2022 | 210 | 9.718 | 0.185 | 4.087 | 14.08 | 0.047 |
| prior_fpi | 2023 | 216 | 8.954 | 0.170 | 4.012 | 12.60 | 0.065 |
| prior_fpi | 2024 | 194 | 10.642 | 0.183 | 4.258 | 15.16 | 0.086 |
| prior_fpi | 2025 | 195 | 9.953 | 0.177 | 4.182 | 13.52 | 0.077 |
| prior_sp | 2021 | 205 | 9.505 | 0.176 | 4.133 | 13.39 | 0.066 |
| prior_sp | 2022 | 210 | 9.922 | 0.189 | 4.109 | 14.44 | 0.067 |
| prior_sp | 2023 | 216 | 8.946 | 0.169 | 4.011 | 12.58 | 0.058 |
| prior_sp | 2024 | 194 | 11.053 | 0.189 | 4.296 | 15.89 | 0.062 |
| prior_sp | 2025 | 195 | 10.097 | 0.181 | 4.194 | 13.78 | 0.090 |
| elo | 2021 | 205 | 9.805 | 0.173 | 4.157 | 13.81 | 0.037 |
| elo | 2022 | 210 | 9.905 | 0.190 | 4.107 | 14.25 | 0.046 |
| elo | 2023 | 216 | 9.025 | 0.166 | 4.013 | 12.51 | 0.072 |
| elo | 2024 | 194 | 10.845 | 0.185 | 4.300 | 15.03 | 0.070 |
| elo | 2025 | 195 | 10.191 | 0.179 | 4.208 | 14.13 | 0.072 |
| market | 2021 | 205 | 8.835 | 0.160 | 4.054 | 12.63 | 0.072 |
| market | 2022 | 210 | 8.394 | 0.165 | 3.945 | 11.94 | 0.059 |
| market | 2023 | 216 | 7.585 | 0.141 | 3.846 | 10.90 | 0.044 |
| market | 2024 | 194 | 9.299 | 0.163 | 4.137 | 13.03 | 0.096 |
| market | 2025 | 195 | 8.719 | 0.160 | 4.046 | 12.13 | 0.052 |
| prior | 2021 | 205 | 9.849 | 0.176 | 4.179 | 14.00 | 0.059 |
| prior | 2022 | 210 | 9.181 | 0.173 | 4.037 | 13.08 | 0.040 |
| prior | 2023 | 216 | 8.266 | 0.161 | 3.937 | 11.87 | 0.049 |
| prior | 2024 | 194 | 10.265 | 0.176 | 4.225 | 14.54 | 0.102 |
| prior | 2025 | 195 | 9.740 | 0.179 | 4.163 | 13.42 | 0.062 |

## The 2025 prior, top and bottom ten by net

| team | net | off | def |
|---|---|---|---|
| Ohio State | +24.5 | +11.5 | +13.4 |
| Alabama | +22.0 | +11.2 | +10.9 |
| Georgia | +20.9 | +10.6 | +10.3 |
| Ole Miss | +20.6 | +8.1 | +12.4 |
| Penn State | +20.2 | +9.8 | +10.8 |
| Texas | +20.1 | +9.2 | +12.2 |
| Notre Dame | +19.6 | +9.6 | +10.8 |
| Oregon | +18.7 | +9.1 | +9.3 |
| LSU | +17.5 | +9.4 | +8.1 |
| Texas A&M | +16.0 | +7.8 | +8.1 |
| New Mexico State | -14.6 | -7.1 | -8.1 |
| Bowling Green | -15.0 | -8.2 | -6.4 |
| Middle Tennessee | -15.3 | -6.8 | -7.7 |
| Central Michigan | -15.4 | -7.8 | -7.7 |
| Ball State | -15.5 | -6.6 | -9.0 |
| New Mexico | -17.1 | -6.2 | -10.6 |
| Rice | -17.2 | -8.8 | -7.6 |
| Massachusetts | -18.9 | -7.9 | -10.2 |
| Kent State | -20.3 | -9.7 | -10.5 |
| Kennesaw State | -21.5 | -11.5 | -9.4 |
