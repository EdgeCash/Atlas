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

Atlas's Brier beats the season-mean Poisson's at 17 of 17 stat-lines.
