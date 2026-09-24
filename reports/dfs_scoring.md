# DraftKings scoring, reconciled

Atlas computes DraftKings NFL Classic points from nflverse's public stats and play-by-play (`atlas/dfs/scoring.py`) and checks them against the points DraftKings recorded, from RotoGuru's archive, 2014-2021 regular season. The gate of step 1 of `docs/MODEL_PLAN_DFS.md` is agreement to within 0.1 on at least 99% of player-weeks.

**54,974 of 55,386 player-weeks agree: 99.26%. The gate passes.**

The last matching stage finds a player by identical points, so its 137 rows agree by construction. Leaving them out entirely, agreement is 99.25%.

## By position

| position | player-weeks | agree |
|---|---|---|
| DST | 4128 | 95.64% |
| QB | 5124 | 99.10% |
| RB | 14729 | 99.44% |
| TE | 11571 | 99.77% |
| WR | 19834 | 99.62% |

Defenses are scored from play-by-play: sacks, takeaways, touchdowns, safeties, blocked kicks and points allowed. Three of DraftKings' rules were settled by the record rather than assumed: a blocked extra point counts as a blocked kick; points allowed leave out a touchdown scored against the team's own offense (a pick-six, at 6 points, not 7) and a safety its offense concedes. What still differs is mostly single sacks and recoveries, where DraftKings' stat corrections and the public play-by-play disagree.

## How archive players were matched

By the same name on the same team that week (position separating two teammates of one name); then by last name at the same position; then by identical points at the same position, which finds a player who changed his name. Unmatched players are the archive's rostered players who recorded no stat (0.00 on both sides) - all but 106 of them.

| matched by | player-weeks | share |
|---|---|---|
| name | 43892 | 85.63% |
| none | 6933 | 13.53% |
| last name | 296 | 0.58% |
| points | 137 | 0.27% |

## Where computed and recorded points differ

| computed minus recorded | player-weeks |
|---|---|
| -1.0 | 68 |
| -2.0 | 53 |
| +1.0 | 30 |
| +2.0 | 30 |
| +6.0 | 20 |
| -0.2 | 19 |
| -3.0 | 18 |
| +0.2 | 12 |
| -0.3 | 8 |
| +0.3 | 7 |
