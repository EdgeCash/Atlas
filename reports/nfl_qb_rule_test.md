# NFL quarterback rule: the pre-registered test

`atlas/research/nfl_qb_rule.py`, scored once against `docs/NFL_QB_RULE_PREREGISTRATION.md`. NFL regular season, test seasons 2020-2025, the NFL model's own walk-forward against the closing total. A rule passes only if it clears all four criteria fixed in advance; anything else is not shown.

## Verdict

- **Q1, Change games, Atlas's side of the closing total: not shown** - 145-163-3, 47.1% of 308, lower bound 40.8%, above 50% in 3 of 6 seasons.
- **Q2, Change games, the under: not shown** - 155-153-3, 50.3% of 308, lower bound 44.0%, above 50% in 3 of 6 seasons.
- **Q3, QB1-out games, Atlas's side: not shown** - 69-71-2, 49.3% of 140, lower bound 40.0%, above 50% in 3 of 6 seasons.
- **Q4, QB1-out games, the under: not shown** - 66-74-2, 47.1% of 140, lower bound 38.0%, above 50% in 2 of 6 seasons.

Control (Neither change nor QB1-out, Atlas's side): 623-628-12, 49.8% of 1251.

## The population

| season | games with a closing total | change games | QB1-out games |
|---|---|---|---|
| 2020 | 256 | 33 | 18 |
| 2021 | 272 | 52 | 20 |
| 2022 | 271 | 51 | 28 |
| 2023 | 272 | 51 | 23 |
| 2024 | 272 | 61 | 20 |
| 2025 | 272 | 63 | 33 |
| all | 1615 | 311 | 142 |

## Each rule, by season

### Q1: Change games, Atlas's side of the closing total

| season | won-lost-push | win rate |
|---|---|---|
| 2020 | 14-18-1 | 43.8% |
| 2021 | 26-25-1 | 51.0% |
| 2022 | 28-23-0 | 54.9% |
| 2023 | 18-33-0 | 35.3% |
| 2024 | 27-33-1 | 45.0% |
| 2025 | 32-31-0 | 50.8% |
| all | 145-163-3 | 47.1% |

| criterion | met |
|---|---|
| at least 100 decided | yes |
| win rate above 52.38% | no |
| Wilson lower bound (z = 2.24) above 50% | no |
| above 50% in at least 4 of 6 seasons | no |

### Q2: Change games, the under

| season | won-lost-push | win rate |
|---|---|---|
| 2020 | 15-17-1 | 46.9% |
| 2021 | 29-22-1 | 56.9% |
| 2022 | 26-25-0 | 51.0% |
| 2023 | 30-21-0 | 58.8% |
| 2024 | 26-34-1 | 43.3% |
| 2025 | 29-34-0 | 46.0% |
| all | 155-153-3 | 50.3% |

| criterion | met |
|---|---|
| at least 100 decided | yes |
| win rate above 52.38% | no |
| Wilson lower bound (z = 2.24) above 50% | no |
| above 50% in at least 4 of 6 seasons | no |

### Q3: QB1-out games, Atlas's side

| season | won-lost-push | win rate |
|---|---|---|
| 2020 | 7-11-0 | 38.9% |
| 2021 | 10-9-1 | 52.6% |
| 2022 | 13-15-0 | 46.4% |
| 2023 | 12-10-1 | 54.5% |
| 2024 | 10-10-0 | 50.0% |
| 2025 | 17-16-0 | 51.5% |
| all | 69-71-2 | 49.3% |

| criterion | met |
|---|---|
| at least 100 decided | yes |
| win rate above 52.38% | no |
| Wilson lower bound (z = 2.24) above 50% | no |
| above 50% in at least 4 of 6 seasons | no |

### Q4: QB1-out games, the under

| season | won-lost-push | win rate |
|---|---|---|
| 2020 | 9-9-0 | 50.0% |
| 2021 | 12-7-1 | 63.2% |
| 2022 | 16-12-0 | 57.1% |
| 2023 | 10-12-1 | 45.5% |
| 2024 | 7-13-0 | 35.0% |
| 2025 | 12-21-0 | 36.4% |
| all | 66-74-2 | 47.1% |

| criterion | met |
|---|---|
| at least 100 decided | yes |
| win rate above 52.38% | no |
| Wilson lower bound (z = 2.24) above 50% | no |
| above 50% in at least 4 of 6 seasons | no |

### control: Neither change nor QB1-out, Atlas's side

| season | won-lost-push | win rate |
|---|---|---|
| 2020 | 100-116-4 | 46.3% |
| 2021 | 104-109-2 | 48.8% |
| 2022 | 102-106-3 | 49.0% |
| 2023 | 114-101-1 | 53.0% |
| 2024 | 100-103-2 | 49.3% |
| 2025 | 103-93-0 | 52.6% |
| all | 623-628-12 | 49.8% |

| criterion | met |
|---|---|
| at least 100 decided | yes |
| win rate above 52.38% | no |
| Wilson lower bound (z = 2.24) above 50% | no |
| above 50% in at least 4 of 6 seasons | no |

## What was not tested

Line movement (nflverse publishes the closing total only, so no opener and no CLV), a gap threshold on Atlas's side, Questionable as out, and spreads: each is named in the pre-registration as outside this test, and adding one after seeing these numbers would be tuning.
