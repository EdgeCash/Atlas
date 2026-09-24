# DFS kickers

Atlas's kicker model for DraftKings Showdown (`atlas/dfs/kicker.py`): the kicker's recent scoring, shrunk to the league's, corrected for his game - both teams' projected points from Atlas's game model and the line, the wind - and his recent attempts. Walk-forward: each season fitted on the seasons before it.

## The gate: passes

- **Scoring matches DraftKings'**: 28 of 28 kickers in DraftKings' 2026 Showdown pools have exactly the points per game Atlas computes (field goal 0-39 yards 3, 40-49 yards 4, 50+ yards 5, extra point 1, no penalty for a miss).
- **Beats the baseline's CRPS**, 2015-2025: 2.480 against 2.508 - yes.
- **80% ranges cover 76-84%**: 80.0% - yes.

## Model against the baseline

| projection | kicker-games | mae | crps | rank corr |
|---|---|---|---|---|
| model | 5817 | 3.524 | 2.480 | 0.178 |
| baseline | 5817 | 3.561 | 2.508 | 0.107 |

## Ranges by season

| season | player-weeks | coverage | below | above | width |
|---|---|---|---|---|---|
| 2015 | 526 | 81.2% | 8.7% | 10.1% | 11.5 |
| 2016 | 515 | 82.3% | 8.7% | 8.9% | 11.4 |
| 2017 | 513 | 75.6% | 12.1% | 12.3% | 11.2 |
| 2018 | 511 | 82.4% | 9.6% | 8.0% | 11.4 |
| 2019 | 514 | 83.1% | 7.2% | 9.7% | 11.2 |
| 2020 | 513 | 82.1% | 8.0% | 9.9% | 11.3 |
| 2021 | 544 | 79.6% | 10.7% | 9.7% | 11.2 |
| 2022 | 547 | 79.7% | 10.1% | 10.2% | 11.2 |
| 2023 | 545 | 77.6% | 10.3% | 12.1% | 11.2 |
| 2024 | 545 | 78.5% | 8.8% | 12.7% | 11.3 |
| 2025 | 544 | 78.5% | 8.3% | 13.2% | 11.3 |

## Scoring against DraftKings, 2026 so far

| kicker | draftkings | atlas | games | agrees |
|---|---|---|---|---|
| Trey Smack | 10.5 | 10.50 | 2 | yes |
| Nick Folk | 7.0 | 7.00 | 2 | yes |
| Cam Little | 10.0 | 10.00 | 2 | yes |
| Andy Borregales | 7.5 | 7.50 | 2 | yes |
| Cameron Dicker | 2.0 | 2.00 | 2 | yes |
| Tyler Bass | 9.0 | 9.00 | 2 | yes |
| Evan McPherson | 15.5 | 15.50 | 2 | yes |
| Chris Boswell | 7.0 | 7.00 | 2 | yes |
| Ka'imi Fairbairn | 8.0 | 8.00 | 2 | yes |
| Spencer Shrader | 10.5 | 10.50 | 2 | yes |
| Harrison Butker | 12.0 | 12.00 | 2 | yes |
| Riley Patterson | 7.5 | 7.50 | 2 | yes |
| Jason Myers | 7.0 | 7.00 | 2 | yes |
| Drew Stevens | 7.5 | 7.50 | 2 | yes |
| Dominic Zvada | 6.0 | 6.00 | 2 | yes |
| Joey Slye | 6.5 | 6.50 | 2 | yes |
| Jake Bates | 7.0 | 7.00 | 2 | yes |
| Jason Sanders | 10.0 | 10.00 | 2 | yes |
| Ryan Fitzgerald | 9.0 | 9.00 | 2 | yes |
| Andre Szmyt | 8.5 | 8.50 | 2 | yes |
| Eddy Pineiro | 8.0 | 8.00 | 2 | yes |
| Chad Ryland | 8.5 | 8.50 | 2 | yes |
| Will Reichard | 8.5 | 8.50 | 2 | yes |
| Chase McLaughlin | 13.5 | 13.50 | 2 | yes |
| Daniel Carlson | 9.5 | 9.50 | 2 | yes |
| Matt Gay | 9.0 | 9.00 | 2 | yes |
| Brandon Aubrey | 9.0 | 9.00 | 2 | yes |
| Tyler Loop | 10.0 | 10.00 | 2 | yes |

A kicker's week is mostly his team's, so the ranking among kickers is modest; the range, which is wide, is the honest part of the number.
