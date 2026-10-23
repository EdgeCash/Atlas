# NFL player projections, walk-forward

Regular season, 2017 to the last complete season, player-games with at least 3 games of the season behind them and a real chance of the stat (two targets, three carries, ten pass attempts or five touches a game so far that season). Atlas is opportunity times a rate times the game (`atlas/models/nfl_props.py`); the baseline is a Poisson on the player's season mean so far. Brier and log loss of P(over) at each line, and the mean absolute error of each expectation.

Half-lives: shares 2 games with a prior of 0.25 games of the position's share, rates 10 games with a prior of 20 opportunities of the position's rate (20 times that for the touchdown rates), the teams 16 games.

| stat | line | n | observed | mean_atlas | mean_naive | brier_atlas | brier_naive | logloss_atlas | logloss_naive | mae_atlas | mae_naive |
|---|---|---|---|---|---|---|---|---|---|---|---|
| receiving_yards | 24.5 | 21848 | 52.6 | 51.9 | 63.5 | 0.1998 | 0.2739 | 0.5862 | 1.6672 | 21.632 | 22.293 |
| receiving_yards | 49.5 | 21848 | 27.1 | 26.5 | 25.3 | 0.1580 | 0.2082 | 0.4825 | 1.4070 | 21.632 | 22.293 |
| receiving_yards | 74.5 | 21848 | 13.0 | 13.0 | 7.6 | 0.0955 | 0.1205 | 0.3141 | 0.9279 | 21.632 | 22.293 |
| receptions | 2.5 | 21848 | 53.3 | 53.3 | 55.6 | 0.2023 | 0.2092 | 0.5905 | 0.6122 | 1.591 | 1.630 |
| receptions | 4.5 | 21848 | 24.9 | 25.5 | 25.5 | 0.1509 | 0.1559 | 0.4656 | 0.4876 | 1.591 | 1.630 |
| receptions | 6.5 | 21848 | 9.7 | 10.5 | 9.9 | 0.0754 | 0.0771 | 0.2593 | 0.2700 | 1.591 | 1.630 |
| rushing_yards | 24.5 | 9291 | 57.8 | 56.7 | 66.4 | 0.1800 | 0.2430 | 0.5371 | 1.4690 | 22.116 | 22.755 |
| rushing_yards | 49.5 | 9291 | 32.2 | 30.9 | 30.9 | 0.1645 | 0.2175 | 0.4970 | 1.4330 | 22.116 | 22.755 |
| rushing_yards | 74.5 | 9291 | 16.0 | 15.8 | 9.5 | 0.1091 | 0.1417 | 0.3491 | 1.0216 | 22.116 | 22.755 |
| passing_yards | 199.5 | 3632 | 65.3 | 60.0 | 75.9 | 0.2139 | 0.2937 | 0.6198 | 2.1772 | 63.502 | 67.324 |
| passing_yards | 249.5 | 3632 | 40.4 | 37.6 | 39.7 | 0.2245 | 0.3174 | 0.6459 | 1.8534 | 63.502 | 67.324 |
| passing_yards | 299.5 | 3632 | 19.5 | 20.3 | 8.8 | 0.1486 | 0.1894 | 0.4674 | 1.4044 | 63.502 | 67.324 |
| touchdowns | 0.5 | 16198 | 30.7 | 30.7 | 29.5 | 0.2005 | 0.2202 | 0.5878 | 0.9244 | 0.490 | 0.492 |
| touchdowns | 1.5 | 16198 | 6.4 | 6.2 | 7.3 | 0.0571 | 0.0611 | 0.2197 | 0.2760 | 0.490 | 0.492 |
| passing_tds | 0.5 | 3632 | 76.2 | 74.5 | 72.5 | 0.1716 | 0.1861 | 0.5213 | 0.6146 | 0.906 | 0.952 |
| passing_tds | 1.5 | 3632 | 45.3 | 41.8 | 41.7 | 0.2310 | 0.2467 | 0.6536 | 0.7213 | 0.906 | 0.952 |
| passing_tds | 2.5 | 3632 | 18.2 | 18.7 | 19.9 | 0.1400 | 0.1461 | 0.4430 | 0.4703 | 0.906 | 0.952 |
| completions | 17.5 | 3632 | 69.7 | 64.7 | 70.8 | 0.2002 | 0.2164 | 0.5927 | 0.6949 | 5.139 | 5.447 |
| completions | 22.5 | 3632 | 39.0 | 37.7 | 39.1 | 0.2228 | 0.2434 | 0.6477 | 0.7582 | 5.139 | 5.447 |
| completions | 27.5 | 3632 | 14.8 | 17.3 | 14.2 | 0.1213 | 0.1272 | 0.4062 | 0.4602 | 5.139 | 5.447 |
| attempts | 24.5 | 3632 | 80.2 | 75.3 | 83.3 | 0.1534 | 0.1711 | 0.4814 | 0.6231 | 7.431 | 7.817 |
| attempts | 29.5 | 3632 | 62.1 | 56.9 | 63.0 | 0.2302 | 0.2576 | 0.6613 | 0.8404 | 7.431 | 7.817 |
| attempts | 34.5 | 3632 | 39.6 | 38.1 | 37.9 | 0.2326 | 0.2590 | 0.6719 | 0.8534 | 7.431 | 7.817 |
| carries | 9.5 | 9291 | 41.5 | 39.9 | 40.3 | 0.1443 | 0.1615 | 0.4478 | 0.5495 | 3.651 | 3.810 |
| carries | 14.5 | 9291 | 21.1 | 19.9 | 18.1 | 0.1180 | 0.1312 | 0.3666 | 0.4994 | 3.651 | 3.810 |
| carries | 19.5 | 9291 | 8.7 | 8.5 | 5.6 | 0.0652 | 0.0700 | 0.2227 | 0.3245 | 3.651 | 3.810 |
| scrimmage_yards | 49.5 | 16198 | 50.3 | 48.8 | 59.2 | 0.2080 | 0.2857 | 0.6027 | 1.6159 | 28.282 | 29.192 |
| scrimmage_yards | 74.5 | 16198 | 29.1 | 28.3 | 24.8 | 0.1739 | 0.2328 | 0.5222 | 1.4453 | 28.282 | 29.192 |
| scrimmage_yards | 99.5 | 16198 | 15.3 | 15.3 | 7.2 | 0.1131 | 0.1398 | 0.3682 | 1.1366 | 28.282 | 29.192 |

Atlas's Brier beats the season-mean Poisson's at 29 of 29 stat-lines.
