# College totals: can the total be made more accurate?

`atlas/research/ncaaf_total_accuracy.py`. Five candidates, each one change to the total as it stands (`current`), on the same state forecasts and the same games, regular season 2021-25, walk-forward. The bar, fixed before scoring: better pooled CRPS, MAE no worse, better CRPS in at least three of five seasons. The market row is the closing total through the same scoring, for scale. Lower is better.

## Verdict

- **efficiency: passes** - CRPS 9.124 against 9.133; MAE 12.91 against 12.91; better in 3 of 5 seasons.
- **defence_pace: fails** - CRPS 9.123 against 9.133; MAE 12.91 against 12.91; better in 1 of 5 seasons.
- **recent: fails** - CRPS 9.143 against 9.133; MAE 12.93 against 12.91; better in 1 of 5 seasons.
- **five_seasons: fails** - CRPS 9.128 against 9.133; MAE 12.91 against 12.91; better in 2 of 5 seasons.
- **in_season: fails** - CRPS 9.134 against 9.133; MAE 12.92 against 12.91; better in 1 of 5 seasons.

## Pooled, regular season 2021-25

| model | games | crps | mae |
|---|---|---|---|
| current | 3730 | 9.133 | 12.91 |
| efficiency | 3730 | 9.124 | 12.91 |
| defence_pace | 3730 | 9.123 | 12.91 |
| recent | 3730 | 9.143 | 12.93 |
| five_seasons | 3730 | 9.128 | 12.91 |
| in_season | 3730 | 9.134 | 12.92 |
| market | 3730 | 8.842 | 12.47 |

## CRPS by season

| season | current | efficiency | defence_pace | recent | five_seasons | in_season | market |
|---|---|---|---|---|---|---|---|
| 2021 | 9.520 | 9.586 | 9.426 | 9.573 | 9.520 | 9.523 | 8.907 |
| 2022 | 9.064 | 8.979 | 9.083 | 9.065 | 9.048 | 9.073 | 8.530 |
| 2023 | 9.165 | 9.123 | 9.186 | 9.160 | 9.166 | 9.172 | 9.002 |
| 2024 | 9.087 | 9.110 | 9.089 | 9.093 | 9.076 | 9.091 | 9.085 |
| 2025 | 8.840 | 8.836 | 8.841 | 8.841 | 8.843 | 8.825 | 8.685 |

## After scoring: is any change distinguishable from zero?

Added after the verdicts above, and labelled so: the bar fixed before scoring had no test of noise, and it should have. Each game's CRPS change against `current`, paired, with its standard error. A change within about two standard errors of zero is not evidence of an improvement, whatever the pooled mean.

| model | crps change | standard error | t |
|---|---|---|---|
| efficiency | -0.0085 | 0.0233 | -0.36 |
| defence_pace | -0.0099 | 0.0107 | -0.92 |
| recent | +0.0108 | 0.0045 | +2.39 |
| five_seasons | -0.0044 | 0.0044 | -1.00 |
| in_season | +0.0014 | 0.0055 | +0.25 |

`efficiency` clears the bar as written on a change a third the size of its own standard error, with seasons swinging both ways (2021 worse by 0.07, 2022 better by 0.09): it is not adopted. None of the five is. Recalibrating the same state forecasts has run out; what the total lacks is information the state does not have.
