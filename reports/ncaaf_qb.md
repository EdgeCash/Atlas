# College: the quarterback state

`atlas/models/ncaaf_qb.py`. The college state as it stands (`state`) and with a quarterback state inside the season (`state_qb`): forecast with the team's previous quarterback of record, learned from who played, a new starter entering at a prior tuned on the training seasons. Regular season 2021-25, walk-forward. The bar, fixed before scoring: margin CRPS better on a paired test with t at or below -2, MAE no worse, better in three seasons of five; the total judged by the same paired test.

## Verdict

- **Margin: fails** - paired CRPS change +0.0055 (standard error 0.0045, t +1.24); MAE change +0.007; better in 2 of 5 seasons.
- **Total: fails** - paired CRPS change +0.0035 (standard error 0.0023, t +1.49); MAE change +0.007; better in 3 of 5 seasons.

## Why: where the state misses

The state's miss on a team's points (actual less forecast), regular season 2021-25. The quarterback's effect is in the game a new one starts - which the record shows only afterwards - and by his next start the team's own state has already absorbed it from that game's points. A quarterback state learned from the record has nothing left to add; what would help is knowing the starter before kickoff, which no source Atlas has provides for college.

| team-games | count | mean miss (points) | standard error |
|---|---|---|---|
| the game a new quarterback starts - unforeseeable from the record | 893 | -2.46 | 0.38 |
| his next start - foreseeable from the record | 607 | -0.09 | 0.48 |
| a settled starter | 4626 | +0.40 | 0.16 |

## Quarterback prior chosen per season

| season | prior variance | new starter (points) |
|---|---|---|
| 2021 | 2.000 | -2.000 |
| 2022 | 2.000 | 0.000 |
| 2023 | 2.000 | 0.000 |
| 2024 | 2.000 | 0.000 |
| 2025 | 2.000 | 0.000 |

## Margin, regular season 2021-25

| model | games | crps | brier | log_margin | mae | ece |
|---|---|---|---|---|---|---|
| elo | 3730 | 9.230 | 0.188 | 4.104 | 13.04 | 0.015 |
| state | 3730 | 8.936 | 0.182 | 4.074 | 12.60 | 0.021 |
| state_qb | 3730 | 8.941 | 0.182 | 4.074 | 12.61 | 0.016 |
| market | 3730 | 8.608 | 0.176 | 4.035 | 12.12 | 0.025 |

## Margin by season

| model | season | games | crps | brier | log_margin | mae | ece |
|---|---|---|---|---|---|---|---|
| elo | 2021 | 732 | 9.341 | 0.185 | 4.126 | 13.33 | 0.022 |
| elo | 2022 | 734 | 9.223 | 0.200 | 4.099 | 13.05 | 0.037 |
| elo | 2023 | 750 | 9.065 | 0.180 | 4.059 | 12.67 | 0.047 |
| elo | 2024 | 752 | 9.431 | 0.192 | 4.140 | 13.36 | 0.045 |
| elo | 2025 | 762 | 9.095 | 0.182 | 4.097 | 12.80 | 0.029 |
| state | 2021 | 732 | 9.370 | 0.183 | 4.135 | 13.35 | 0.025 |
| state | 2022 | 734 | 8.827 | 0.189 | 4.055 | 12.50 | 0.028 |
| state | 2023 | 750 | 8.679 | 0.174 | 4.017 | 12.27 | 0.035 |
| state | 2024 | 752 | 9.023 | 0.185 | 4.096 | 12.66 | 0.044 |
| state | 2025 | 762 | 8.790 | 0.179 | 4.067 | 12.26 | 0.032 |
| state_qb | 2021 | 732 | 9.398 | 0.184 | 4.137 | 13.39 | 0.029 |
| state_qb | 2022 | 734 | 8.833 | 0.189 | 4.056 | 12.51 | 0.027 |
| state_qb | 2023 | 750 | 8.676 | 0.174 | 4.017 | 12.27 | 0.037 |
| state_qb | 2024 | 752 | 9.023 | 0.185 | 4.095 | 12.66 | 0.044 |
| state_qb | 2025 | 762 | 8.787 | 0.179 | 4.067 | 12.26 | 0.029 |
| market | 2021 | 732 | 8.832 | 0.174 | 4.072 | 12.56 | 0.040 |
| market | 2022 | 734 | 8.536 | 0.184 | 4.021 | 12.03 | 0.041 |
| market | 2023 | 750 | 8.472 | 0.168 | 3.990 | 11.97 | 0.038 |
| market | 2024 | 752 | 8.740 | 0.181 | 4.067 | 12.22 | 0.063 |
| market | 2025 | 762 | 8.468 | 0.173 | 4.026 | 11.85 | 0.030 |

## Total, regular season 2021-25

| model | crps | mae |
|---|---|---|
| state | 9.133 | 12.914 |
| state_qb | 9.136 | 12.922 |

## Total CRPS by season

| season | state | state_qb |
|---|---|---|
| 2021 | 9.520 | 9.545 |
| 2022 | 9.064 | 9.061 |
| 2023 | 9.165 | 9.163 |
| 2024 | 9.087 | 9.087 |
| 2025 | 8.840 | 8.838 |
