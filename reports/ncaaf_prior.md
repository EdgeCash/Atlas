# NCAAF preseason prior

Walk-forward, seasons 2021-2025: each season's prior is fitted on every earlier season's (preseason facts -> eventual least-squares rating), then scored on that season's games beside the reference models, with the same lattice and scoring as `reports/ncaaf_benchmarks.md`. Frame: FBS-vs-FBS regular season.

## What the recipe learned (last training window)

Points of home margin per one standard deviation of each preseason feature, fitted directly on games. `sp_plus_def` is the SP+ defensive *rating* (points allowed), so a lower value is a better defence and its `def` coefficient is expected to be negative.

### net  -  game-level R² 0.316, residual sd 17.25 points, home advantage +2.52, n=4882 games

| feature | points_per_sd |
|---|---|
| sp_plus | +4.24 |
| fpi | +3.20 |
| talent | +2.09 |
| returning_production | +1.62 |
| new_coach_x_overach | -1.41 |
| new_coach | -1.11 |
| sp_program_mean | +0.94 |
| recruiting_rank | -0.78 |

### off  -  from one stacked points regression, R² 0.221, residual sd 12.18 points per team-game, n=9764 team-games

| feature | points_per_sd |
|---|---|
| talent | +1.93 |
| sp_plus_off | +1.83 |
| fpi | +1.40 |
| sp_program_mean | +1.04 |
| returning_production | +1.01 |
| new_coach_x_overach | -0.61 |
| new_coach | -0.58 |
| recruiting_rank | +0.23 |

### def  -  from one stacked points regression, R² 0.221, residual sd 12.18 points per team-game, n=9764 team-games

| feature | points_per_sd |
|---|---|
| fpi | +2.46 |
| sp_plus_def | -2.31 |
| recruiting_rank | -1.05 |
| new_coach_x_overach | -0.74 |
| returning_production | +0.59 |
| new_coach | -0.53 |
| talent | +0.18 |
| sp_program_mean | +0.10 |

A team's prior net has sd 10.29 points across the 136 FBS teams of 2025; the game residual sd of 17.25 is the prior's own uncertainty and the state model's starting variance.

## How well the prior tracked the eventual rating, team level

| season | corr def | corr net | corr off |
|---|---|---|---|
| 2021 | 0.649 | 0.695 | 0.565 |
| 2022 | 0.718 | 0.799 | 0.720 |
| 2023 | 0.737 | 0.806 | 0.656 |
| 2024 | 0.708 | 0.736 | 0.639 |
| 2025 | 0.694 | 0.754 | 0.645 |

## Game-level scores, weeks 1-4 (where a prior is the whole forecast)

| model | games | crps | brier | log_margin | mae | ece |
|---|---|---|---|---|---|---|
| naive | 1020 | 12.650 | 0.234 | 4.415 | 17.63 | 0.047 |
| prior_fpi | 1020 | 9.782 | 0.179 | 4.152 | 13.77 | 0.032 |
| prior_sp | 1020 | 9.893 | 0.181 | 4.162 | 13.99 | 0.036 |
| elo | 1020 | 9.951 | 0.178 | 4.171 | 13.92 | 0.034 |
| market | 1020 | 8.544 | 0.158 | 4.018 | 12.10 | 0.026 |
| prior | 1020 | 9.472 | 0.174 | 4.123 | 13.42 | 0.022 |

## By week bucket, regular season

| model | week_bucket | games | crps | brier | log_margin | mae | ece |
|---|---|---|---|---|---|---|---|
| naive | wk 1-2 | 480 | 12.882 | 0.232 | 4.431 | 18.07 | 0.062 |
| naive | wk 3-4 | 540 | 12.443 | 0.236 | 4.400 | 17.24 | 0.038 |
| naive | wk 5-8 | 1075 | 10.531 | 0.244 | 4.237 | 14.47 | 0.012 |
| naive | wk 9-12 | 1131 | 11.155 | 0.244 | 4.302 | 15.57 | 0.011 |
| naive | wk 13+ | 504 | 11.601 | 0.251 | 4.354 | 16.25 | 0.052 |
| prior_fpi | wk 1-2 | 480 | 9.662 | 0.171 | 4.146 | 13.48 | 0.046 |
| prior_fpi | wk 3-4 | 540 | 9.889 | 0.187 | 4.157 | 14.03 | 0.050 |
| prior_fpi | wk 5-8 | 1075 | 9.473 | 0.216 | 4.122 | 13.31 | 0.030 |
| prior_fpi | wk 9-12 | 1131 | 10.139 | 0.216 | 4.204 | 14.33 | 0.028 |
| prior_fpi | wk 13+ | 504 | 10.734 | 0.226 | 4.288 | 15.08 | 0.054 |
| prior_sp | wk 1-2 | 480 | 9.730 | 0.173 | 4.151 | 13.68 | 0.036 |
| prior_sp | wk 3-4 | 540 | 10.039 | 0.188 | 4.171 | 14.26 | 0.052 |
| prior_sp | wk 5-8 | 1075 | 9.530 | 0.218 | 4.125 | 13.49 | 0.027 |
| prior_sp | wk 9-12 | 1131 | 9.996 | 0.215 | 4.189 | 14.18 | 0.028 |
| prior_sp | wk 13+ | 504 | 10.722 | 0.225 | 4.288 | 15.03 | 0.079 |
| elo | wk 1-2 | 480 | 10.183 | 0.181 | 4.203 | 14.16 | 0.036 |
| elo | wk 3-4 | 540 | 9.745 | 0.176 | 4.143 | 13.71 | 0.035 |
| elo | wk 5-8 | 1075 | 8.862 | 0.200 | 4.054 | 12.59 | 0.031 |
| elo | wk 9-12 | 1131 | 8.986 | 0.186 | 4.087 | 12.76 | 0.025 |
| elo | wk 13+ | 504 | 9.104 | 0.183 | 4.114 | 12.85 | 0.030 |
| market | wk 1-2 | 480 | 8.412 | 0.154 | 4.002 | 11.84 | 0.033 |
| market | wk 3-4 | 540 | 8.662 | 0.161 | 4.032 | 12.33 | 0.030 |
| market | wk 5-8 | 1075 | 8.507 | 0.188 | 4.012 | 11.95 | 0.032 |
| market | wk 9-12 | 1131 | 8.639 | 0.179 | 4.049 | 12.13 | 0.021 |
| market | wk 13+ | 504 | 8.886 | 0.181 | 4.089 | 12.50 | 0.062 |
| prior | wk 1-2 | 480 | 9.247 | 0.165 | 4.101 | 13.05 | 0.038 |
| prior | wk 3-4 | 540 | 9.671 | 0.182 | 4.142 | 13.75 | 0.019 |
| prior | wk 5-8 | 1075 | 9.368 | 0.212 | 4.113 | 13.23 | 0.031 |
| prior | wk 9-12 | 1131 | 9.879 | 0.209 | 4.181 | 13.92 | 0.035 |
| prior | wk 13+ | 504 | 10.765 | 0.228 | 4.298 | 15.10 | 0.070 |

## By season, weeks 1-4

| model | season | games | crps | brier | log_margin | mae | ece |
|---|---|---|---|---|---|---|---|
| naive | 2021 | 205 | 12.184 | 0.236 | 4.398 | 16.88 | 0.042 |
| naive | 2022 | 210 | 12.853 | 0.232 | 4.395 | 17.80 | 0.067 |
| naive | 2023 | 216 | 11.928 | 0.235 | 4.307 | 16.79 | 0.044 |
| naive | 2024 | 194 | 13.485 | 0.240 | 4.531 | 18.82 | 0.018 |
| naive | 2025 | 195 | 12.890 | 0.229 | 4.456 | 17.99 | 0.074 |
| prior_fpi | 2021 | 205 | 9.683 | 0.182 | 4.165 | 13.64 | 0.032 |
| prior_fpi | 2022 | 210 | 9.725 | 0.185 | 4.105 | 14.08 | 0.044 |
| prior_fpi | 2023 | 216 | 8.975 | 0.171 | 4.030 | 12.60 | 0.076 |
| prior_fpi | 2024 | 194 | 10.654 | 0.183 | 4.276 | 15.16 | 0.081 |
| prior_fpi | 2025 | 195 | 9.975 | 0.177 | 4.200 | 13.52 | 0.068 |
| prior_sp | 2021 | 205 | 9.524 | 0.176 | 4.148 | 13.39 | 0.082 |
| prior_sp | 2022 | 210 | 9.925 | 0.189 | 4.126 | 14.44 | 0.057 |
| prior_sp | 2023 | 216 | 8.956 | 0.169 | 4.028 | 12.58 | 0.063 |
| prior_sp | 2024 | 194 | 11.066 | 0.189 | 4.313 | 15.89 | 0.068 |
| prior_sp | 2025 | 195 | 10.118 | 0.181 | 4.212 | 13.78 | 0.105 |
| elo | 2021 | 205 | 9.820 | 0.173 | 4.173 | 13.81 | 0.049 |
| elo | 2022 | 210 | 9.912 | 0.190 | 4.125 | 14.25 | 0.041 |
| elo | 2023 | 216 | 9.051 | 0.166 | 4.032 | 12.51 | 0.077 |
| elo | 2024 | 194 | 10.867 | 0.185 | 4.319 | 15.03 | 0.080 |
| elo | 2025 | 195 | 10.218 | 0.179 | 4.227 | 14.13 | 0.074 |
| market | 2021 | 205 | 8.823 | 0.160 | 4.067 | 12.63 | 0.077 |
| market | 2022 | 210 | 8.386 | 0.165 | 3.961 | 11.94 | 0.061 |
| market | 2023 | 216 | 7.593 | 0.141 | 3.863 | 10.90 | 0.046 |
| market | 2024 | 194 | 9.303 | 0.163 | 4.154 | 13.03 | 0.103 |
| market | 2025 | 195 | 8.721 | 0.160 | 4.063 | 12.13 | 0.052 |
| prior | 2021 | 205 | 9.860 | 0.176 | 4.193 | 14.00 | 0.046 |
| prior | 2022 | 210 | 9.147 | 0.173 | 4.050 | 13.13 | 0.043 |
| prior | 2023 | 216 | 8.407 | 0.164 | 3.968 | 12.05 | 0.066 |
| prior | 2024 | 194 | 10.289 | 0.177 | 4.243 | 14.60 | 0.100 |
| prior | 2025 | 195 | 9.778 | 0.180 | 4.179 | 13.48 | 0.058 |

## The 2025 prior, top and bottom ten by net

| team | net | off | def |
|---|---|---|---|
| Ohio State | +23.8 | +11.1 | +12.9 |
| Alabama | +21.3 | +10.8 | +10.5 |
| Georgia | +20.4 | +10.3 | +10.1 |
| Penn State | +19.9 | +9.6 | +10.5 |
| Texas | +19.5 | +8.8 | +11.8 |
| Notre Dame | +19.4 | +9.3 | +10.7 |
| Oregon | +18.1 | +8.7 | +8.9 |
| Ole Miss | +16.9 | +6.5 | +9.9 |
| Clemson | +15.7 | +9.4 | +7.1 |
| LSU | +15.5 | +8.6 | +6.8 |
| Middle Tennessee | -15.9 | -7.2 | -8.0 |
| New Mexico State | -16.7 | -7.9 | -9.4 |
| Bowling Green | -17.0 | -9.1 | -7.7 |
| Charlotte | -17.2 | -7.4 | -10.2 |
| Ball State | -17.3 | -7.5 | -10.1 |
| Rice | -17.3 | -9.1 | -7.6 |
| Kent State | -20.1 | -9.6 | -10.3 |
| New Mexico | -20.7 | -7.9 | -12.7 |
| Massachusetts | -22.3 | -9.5 | -12.3 |
| Kennesaw State | -24.1 | -12.8 | -11.1 |
