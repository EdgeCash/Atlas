# NBA player projections, walk-forward

Regular season, 2021-22, 2022-23, 2023-24, 2024-25, 2025-26, player-games with at least 5 games of the season behind them. Atlas is minutes times a rate times the game (`atlas/models/nba_props.py`); the baseline is a Poisson on the player's season mean so far. Brier and log loss of P(over) at each line, and the mean absolute error of each expectation.

Half-lives: minutes 5 games, rates 60 games with a prior of 100 minutes of the position's rate, the teams 20 games.

| stat | line | n | observed | mean_atlas | mean_naive | brier_atlas | brier_naive | logloss_atlas | logloss_naive | mae_atlas | mae_naive |
|---|---|---|---|---|---|---|---|---|---|---|---|
| points | 9.5 | 117033 | 49.1 | 47.1 | 46.4 | 0.1624 | 0.1788 | 0.4924 | 0.6363 | 4.687 | 4.705 |
| points | 14.5 | 117033 | 29.8 | 27.8 | 25.2 | 0.1311 | 0.1412 | 0.4131 | 0.5699 | 4.687 | 4.705 |
| points | 19.5 | 117033 | 16.7 | 15.5 | 12.9 | 0.0898 | 0.0949 | 0.2937 | 0.41 | 4.687 | 4.705 |
| points | 24.5 | 117033 | 8.5 | 8.2 | 5.8 | 0.0547 | 0.0572 | 0.1862 | 0.2578 | 4.687 | 4.705 |
| rebounds | 3.5 | 117033 | 50.0 | 49.4 | 49.1 | 0.1787 | 0.1859 | 0.5321 | 0.5623 | 1.911 | 1.941 |
| rebounds | 5.5 | 117033 | 28.6 | 28.7 | 26.6 | 0.1409 | 0.1458 | 0.4399 | 0.4711 | 1.911 | 1.941 |
| rebounds | 7.5 | 117033 | 15.4 | 15.7 | 13.6 | 0.0893 | 0.0918 | 0.2983 | 0.3231 | 1.911 | 1.941 |
| assists | 1.5 | 117033 | 54.8 | 54.5 | 53.4 | 0.1687 | 0.1734 | 0.5048 | 0.5271 | 1.349 | 1.351 |
| assists | 3.5 | 117033 | 26.6 | 26.1 | 24.4 | 0.1204 | 0.1231 | 0.382 | 0.4006 | 1.349 | 1.351 |
| assists | 5.5 | 117033 | 12.7 | 12.1 | 11.0 | 0.0725 | 0.0738 | 0.238 | 0.2528 | 1.349 | 1.351 |
| threes | 0.5 | 117033 | 57.2 | 57.7 | 57.7 | 0.1679 | 0.171 | 0.5041 | 0.5394 | 0.892 | 0.884 |
| threes | 1.5 | 117033 | 33.4 | 32.8 | 32.3 | 0.1659 | 0.169 | 0.4924 | 0.5088 | 0.892 | 0.884 |
| threes | 2.5 | 117033 | 17.9 | 17.4 | 16.5 | 0.1177 | 0.1196 | 0.3685 | 0.3814 | 0.892 | 0.884 |

Atlas's Brier beats the season-mean Poisson's at 13 of 13 stat-lines.
