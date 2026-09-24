# NFL: does early-down EPA make the state model more accurate?

`atlas/research/nfl_early_down.py`. v1.2 is the state model as it stands; each candidate adds one measurement per offence per game - its EPA per play on those downs, garbage time out - read as its offence, quarterback and home advantage against the opposing defence, weighted by its plays. The team and quarterback hyperparameters are v1.2's, held; only the channel's weight is chosen, per season, on the three seasons before it. The bar, fixed before scoring: better CRPS on 2023-25 and on 2020-26 pooled, mean absolute error no worse. Lower is better everywhere.

## Verdict

- **early_down: fails** - window CRPS 7.290 vs 7.290; pooled CRPS 7.332 vs 7.306; pooled MAE 10.23 vs 10.19.
- **all_downs: fails** - window CRPS 7.290 vs 7.290; pooled CRPS 7.306 vs 7.306; pooled MAE 10.19 vs 10.19.

## Weight chosen per season (points per unit of EPA per play; 0 = switched off)

| season | early_down | all_downs |
|---|---|---|
| 2020 | 0.000 | 0.000 |
| 2021 | 60.000 | 0.000 |
| 2022 | 0.000 | 0.000 |
| 2023 | 0.000 | 0.000 |
| 2024 | 0.000 | 0.000 |
| 2025 | 0.000 | 0.000 |
| 2026 | 0.000 | 0.000 |

## Reporting window, regular season 2023-2025

| model | games | crps | brier | log_margin | mae | ece |
|---|---|---|---|---|---|---|
| naive | 816 | 8.024 | 0.249 | 3.963 | 11.10 | 0.019 |
| elo | 816 | 7.372 | 0.223 | 3.880 | 10.24 | 0.042 |
| v1.2 | 816 | 7.290 | 0.220 | 3.868 | 10.13 | 0.032 |
| early_down | 816 | 7.290 | 0.220 | 3.868 | 10.13 | 0.032 |
| all_downs | 816 | 7.290 | 0.220 | 3.868 | 10.13 | 0.032 |
| market | 816 | 7.075 | 0.211 | 3.839 | 9.74 | 0.049 |

## Every scored season pooled, regular season

| model | games | crps | brier | log_margin | mae | ece |
|---|---|---|---|---|---|---|
| naive | 1647 | 7.954 | 0.249 | 3.969 | 11.04 | 0.024 |
| elo | 1647 | 7.340 | 0.223 | 3.890 | 10.23 | 0.041 |
| v1.2 | 1647 | 7.306 | 0.221 | 3.885 | 10.19 | 0.033 |
| early_down | 1647 | 7.332 | 0.222 | 3.890 | 10.23 | 0.028 |
| all_downs | 1647 | 7.306 | 0.221 | 3.885 | 10.19 | 0.033 |
| market | 1647 | 7.070 | 0.211 | 3.854 | 9.80 | 0.038 |

## By season

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
| v1.2 | 2020 | 256 | 7.275 | 0.217 | 3.879 | 10.20 | 0.071 |
| v1.2 | 2021 | 272 | 7.920 | 0.225 | 4.010 | 11.11 | 0.048 |
| v1.2 | 2022 | 271 | 6.646 | 0.226 | 3.803 | 9.20 | 0.037 |
| v1.2 | 2023 | 272 | 7.545 | 0.228 | 3.901 | 10.41 | 0.043 |
| v1.2 | 2024 | 272 | 7.173 | 0.209 | 3.875 | 9.90 | 0.065 |
| v1.2 | 2025 | 272 | 7.153 | 0.221 | 3.828 | 10.09 | 0.065 |
| v1.2 | 2026 | 32 | 8.300 | 0.226 | 3.991 | 12.24 | 0.103 |
| early_down | 2020 | 256 | 7.275 | 0.217 | 3.879 | 10.20 | 0.071 |
| early_down | 2021 | 272 | 8.082 | 0.227 | 4.040 | 11.31 | 0.069 |
| early_down | 2022 | 271 | 6.646 | 0.226 | 3.803 | 9.20 | 0.037 |
| early_down | 2023 | 272 | 7.545 | 0.228 | 3.901 | 10.41 | 0.043 |
| early_down | 2024 | 272 | 7.173 | 0.209 | 3.875 | 9.90 | 0.065 |
| early_down | 2025 | 272 | 7.153 | 0.221 | 3.828 | 10.09 | 0.065 |
| early_down | 2026 | 32 | 8.300 | 0.226 | 3.991 | 12.24 | 0.103 |
| all_downs | 2020 | 256 | 7.275 | 0.217 | 3.879 | 10.20 | 0.071 |
| all_downs | 2021 | 272 | 7.920 | 0.225 | 4.010 | 11.11 | 0.048 |
| all_downs | 2022 | 271 | 6.646 | 0.226 | 3.803 | 9.20 | 0.037 |
| all_downs | 2023 | 272 | 7.545 | 0.228 | 3.901 | 10.41 | 0.043 |
| all_downs | 2024 | 272 | 7.173 | 0.209 | 3.875 | 9.90 | 0.065 |
| all_downs | 2025 | 272 | 7.153 | 0.221 | 3.828 | 10.09 | 0.065 |
| all_downs | 2026 | 32 | 8.300 | 0.226 | 3.991 | 12.24 | 0.103 |
| market | 2020 | 256 | 7.061 | 0.203 | 3.855 | 9.83 | 0.070 |
| market | 2021 | 272 | 7.663 | 0.217 | 3.976 | 10.78 | 0.117 |
| market | 2022 | 271 | 6.358 | 0.210 | 3.767 | 8.74 | 0.046 |
| market | 2023 | 272 | 7.273 | 0.217 | 3.862 | 9.90 | 0.056 |
| market | 2024 | 272 | 7.041 | 0.203 | 3.860 | 9.61 | 0.094 |
| market | 2025 | 272 | 6.913 | 0.212 | 3.795 | 9.72 | 0.022 |
| market | 2026 | 32 | 8.001 | 0.221 | 3.937 | 11.56 | 0.204 |
