# College DFS scoring, checked against DraftKings

Atlas scores each college player-game from ESPN's box score with DraftKings' college rules (`atlas/dfs/cfb.py`) and compares each pool player's average with the points per game DraftKings shows for him, 2026 so far. There is no archive of past college DraftKings points, so this is the check. The gate (step 1 of `docs/MODEL_PLAN_DFS_CFB.md`): at least 98% agree within 0.1.

DraftKings divides a player's points by every game he appeared in, a stat or not, while a box score lists only games with a stat; so a player agrees when his total over some count of games - from his games with a stat to his team's games - gives DraftKings' figure to its one decimal. A player at 0.0 with no box line appeared and scored nothing, and agrees.

**1320 of 1337 players agree: 98.7%. The gate passes.**

The strict check - the 433 players with a stat line in every one of their team's games, so the count is known - agrees within 0.1 for 97.9%. What is left is the size of a stat correction (a few yards, a touchdown moved between players), not a rule: two-point conversions, return touchdowns and the 100- and 300-yard bonuses all appear among the players who agree. 2 players with points could not be matched to a box score by name and team.

## By position

| position | players | agree |
|---|---|---|
| K | 43 | 100.0% |
| QB | 155 | 98.1% |
| RB | 318 | 98.7% |
| WR | 821 | 98.8% |

## The largest disagreements

| name | position | team | draftkings | atlas | games | diff |
|---|---|---|---|---|---|---|
| DeShawn Spencer | WR | AUB | 6.70 | 10.70 | 2.000 | 4.00 |
| Linkon Cure | WR | KSU | 2.40 | 5.30 | 1.000 | 2.90 |
| Jared Curtis | QB | VAND | 20.50 | 18.53 | 3.000 | -1.97 |
| Cayden Lee | WR | MIZZ | 17.30 | 18.87 | 3.000 | 1.57 |
| Arlis Boardingham | WR | AUB | 1.60 | 2.80 | 1.000 | 1.20 |
| Kevin Riley | RB | BAMA | 0.90 | 1.75 | 2.000 | 0.85 |
| Donovan Olugbode | WR | MIZZ | 24.30 | 23.63 | 3.000 | -0.67 |
| Brady Hunt | WR | SCAR | 4.40 | 5.03 | 3.000 | 0.63 |
| Donnie Cheers | WR | NEV | 9.20 | 8.60 | 3.000 | -0.60 |
| Hollywood Smothers | RB | TEX | 17.20 | 16.73 | 3.000 | -0.47 |
| Rodney Fields Jr. | RB | KSU | 13.80 | 14.23 | 3.000 | 0.43 |
| Will Loerzel | WR | WAKE | 2.70 | 3.05 | 2.000 | 0.35 |
| Chris Barnes | WR | OKST | 7.90 | 7.60 | 2.000 | -0.30 |
| Mana Carvalho | WR | UTAH | 2.60 | 2.90 | 2.000 | 0.30 |
| Xai'Shaun Edwards | RB | MIZZ | 6.40 | 6.13 | 3.000 | -0.27 |
