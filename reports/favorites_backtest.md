# The favorites rule on Polymarket US's own tape

*Built 2026-10-24 22:58 UTC by `python -m atlas.polymarket.backtest`.*

The favorites rule (`atlas/polymarket/favorites.py`) replayed on every settled game the venue lists: for each side of each moneyline, in each phase, a paper position at the first minute its ask sat at or over each threshold, at that ask plus the venue's fee, graded by the settled price. The tape is the exchange's own minute-by-minute price history, which carries each side's ask. Edge is the win rate less the break-even rate (the mean cost) in points, with a standard error clustered by game; profit per dollar is what a dollar staked across the positions returned.

## Coverage

| League | Settled games | With a tape and a position | First | Last |
|---|---|---|---|---|
| CBB | 4386 | 4167 | 2025-12-06 | 2026-04-07 |
| CFB | 996 | 921 | 2025-12-06 | 2026-10-23 |
| NBA | 1289 | 1241 | 2025-11-09 | 2026-10-24 |
| NFL | 298 | 297 | 2025-10-31 | 2026-10-23 |
| NHL | 1183 | 1127 | 2025-12-06 | 2026-10-24 |

## Correction: late, as it can be known during the game

The tables further down that bucket by minutes left measure them to the venue's recorded finish, which is not known while the game is on. Games that run long are disproportionately the close ones the favorite loses, and that measure moves their final minutes out of the late buckets, so it flattered the late result. Here late is elapsed time at or beyond the league's median game length less 15 minutes, a league constant, on a tight book. This is the late result to read; the live record (`tracking/favorites.csv`) marks late by the venue's own period.

| League | Late from (minutes after the start) |
|---|---|
| CBB | 113 |
| CFB | 193 |
| NBA | 136 |
| NFL | 173 |
| NHL | 150 |

| Threshold | Taken | Win rate | Break-even | Edge (pts) | Profit per $ |
|---|---|---|---|---|---|
| 80% | 738 | 88.5% | 88.0% | +0.4 ± 1.1 | 0.7% |
| 85% | 966 | 90.3% | 91.1% | -0.8 ± 0.9 | -0.8% |
| 90% | 1276 | 92.8% | 94.0% | -1.2 ± 0.7 | -1.3% |
| 95% | 1597 | 95.7% | 96.7% | -1.1 ± 0.5 | -1.1% |
| 97% | 1617 | 96.8% | 97.7% | -0.9 ± 0.4 | -0.9% |

| League | Threshold | Taken | Win rate | Break-even | Edge (pts) | Profit per $ |
|---|---|---|---|---|---|---|
| CBB | 80% | 361 | 87.5% | 87.5% | +0.0 ± 1.7 | 0.0% |
| CBB | 85% | 480 | 88.8% | 90.9% | -2.2 ± 1.4 | -2.3% |
| CBB | 90% | 646 | 92.1% | 93.9% | -1.8 ± 1.0 | -2.0% |
| CBB | 95% | 833 | 95.7% | 96.7% | -1.1 ± 0.7 | -1.1% |
| CBB | 97% | 865 | 96.5% | 97.7% | -1.2 ± 0.6 | -1.2% |
| CFB | 80% | 61 | 85.2% | 86.9% | -1.7 ± 4.5 | -1.9% |
| CFB | 85% | 72 | 87.5% | 90.0% | -2.5 ± 3.7 | -2.7% |
| CFB | 90% | 90 | 91.1% | 93.8% | -2.7 ± 2.9 | -2.8% |
| CFB | 95% | 124 | 94.4% | 96.5% | -2.2 ± 2.0 | -2.3% |
| CFB | 97% | 117 | 95.7% | 97.6% | -1.9 ± 1.9 | -2.0% |
| NBA | 80% | 145 | 88.3% | 87.4% | +0.8 ± 2.7 | 1.0% |
| NBA | 85% | 193 | 90.7% | 91.3% | -0.6 ± 2.0 | -0.6% |
| NBA | 90% | 248 | 94.0% | 94.2% | -0.2 ± 1.5 | -0.2% |
| NBA | 95% | 304 | 95.1% | 96.7% | -1.7 ± 1.2 | -1.7% |
| NBA | 97% | 319 | 96.9% | 97.7% | -0.9 ± 1.0 | -0.9% |
| NFL | 80% | 43 | 86.0% | 87.4% | -1.3 ± 4.8 | 1.1% |
| NFL | 85% | 47 | 95.7% | 91.3% | +4.4 ± 2.7 | 6.0% |
| NFL | 90% | 51 | 98.0% | 94.5% | +3.6 ± 1.8 | 3.8% |
| NFL | 95% | 61 | 100.0% | 96.9% | +3.1 ± 0.1 | 3.2% |
| NFL | 97% | 65 | 100.0% | 97.7% | +2.3 ± 0.1 | 2.3% |
| NHL | 80% | 128 | 93.8% | 91.1% | +2.7 ± 2.1 | 3.3% |
| NHL | 85% | 174 | 93.7% | 91.9% | +1.8 ± 1.8 | 2.3% |
| NHL | 90% | 241 | 92.9% | 93.9% | -0.9 ± 1.6 | -1.0% |
| NHL | 95% | 275 | 96.0% | 96.8% | -0.8 ± 1.2 | -0.8% |
| NHL | 97% | 251 | 97.6% | 97.7% | -0.1 ± 1.0 | -0.1% |

## In play, all leagues, by minutes to the recorded finish

Once a side's ask reaches the threshold during the game, does it win more often than it costs? Every crossing, at the trigger minute's ask, however wide the book was. The time left is to the recorded finish, which is not knowable during the game (see the correction above).

| Bucket | Threshold | Taken | Win rate | Break-even | Edge (pts) | Profit per $ |
|---|---|---|---|---|---|---|
| over 60 min left | 80% | 6349 | 80.5% | 85.6% | -5.0 ± 0.5 | -5.7% |
| over 60 min left | 85% | 5332 | 84.5% | 89.0% | -4.5 ± 0.5 | -4.9% |
| over 60 min left | 90% | 4209 | 88.3% | 92.6% | -4.3 ± 0.5 | -4.4% |
| over 60 min left | 95% | 2909 | 93.3% | 96.2% | -2.9 ± 0.5 | -2.8% |
| over 60 min left | 97% | 2167 | 94.8% | 97.6% | -2.8 ± 0.5 | -2.7% |
| 30 to 60 | 80% | 1378 | 79.3% | 84.4% | -5.1 ± 1.1 | -6.0% |
| 30 to 60 | 85% | 1497 | 82.6% | 88.5% | -5.9 ± 1.0 | -6.7% |
| 30 to 60 | 90% | 1562 | 86.6% | 92.5% | -5.9 ± 0.9 | -6.4% |
| 30 to 60 | 95% | 1551 | 92.3% | 96.2% | -3.8 ± 0.7 | -4.0% |
| 30 to 60 | 97% | 1412 | 95.0% | 97.6% | -2.6 ± 0.6 | -2.6% |
| 15 to 30 | 80% | 861 | 85.4% | 85.2% | +0.1 ± 1.2 | 0.2% |
| 15 to 30 | 85% | 1011 | 87.3% | 89.2% | -1.8 ± 1.0 | -2.1% |
| 15 to 30 | 90% | 1115 | 91.3% | 93.0% | -1.7 ± 0.8 | -1.8% |
| 15 to 30 | 95% | 1254 | 93.9% | 96.4% | -2.4 ± 0.7 | -2.5% |
| 15 to 30 | 97% | 1241 | 95.6% | 97.6% | -2.0 ± 0.6 | -2.0% |
| 5 to 15 | 80% | 554 | 90.1% | 88.2% | +1.9 ± 1.3 | 2.3% |
| 5 to 15 | 85% | 733 | 92.6% | 91.0% | +1.7 ± 1.0 | 2.0% |
| 5 to 15 | 90% | 1002 | 95.6% | 93.7% | +1.9 ± 0.6 | 2.1% |
| 5 to 15 | 95% | 1177 | 97.1% | 96.7% | +0.4 ± 0.5 | 0.5% |
| 5 to 15 | 97% | 1144 | 98.2% | 97.7% | +0.5 ± 0.4 | 0.5% |
| under 5 | 80% | 213 | 93.4% | 92.3% | +1.1 ± 1.7 | 1.2% |
| under 5 | 85% | 282 | 94.0% | 93.7% | +0.3 ± 1.4 | 0.3% |
| under 5 | 90% | 391 | 96.4% | 95.2% | +1.2 ± 0.9 | 1.3% |
| under 5 | 95% | 534 | 98.3% | 97.0% | +1.3 ± 0.6 | 1.4% |
| under 5 | 97% | 567 | 98.9% | 97.7% | +1.2 ± 0.4 | 1.2% |

## The same, with a tight book (4¢ or less between the two asks)

An ask over the threshold with nothing near it on the other side is an empty book, not a price: one crossing in five is at a spread over 4¢, and those are where the worst of the table above comes from. The model rule declines such a quote; this is the favorites rule with the same bar.

| Bucket | Threshold | Taken | Win rate | Break-even | Edge (pts) | Profit per $ |
|---|---|---|---|---|---|---|
| over 60 min left | 80% | 5289 | 82.1% | 85.4% | -3.3 ± 0.5 | -3.8% |
| over 60 min left | 85% | 4398 | 86.1% | 88.8% | -2.8 ± 0.5 | -3.0% |
| over 60 min left | 90% | 3447 | 90.2% | 92.4% | -2.3 ± 0.5 | -2.4% |
| over 60 min left | 95% | 2396 | 95.2% | 96.1% | -0.9 ± 0.4 | -0.9% |
| over 60 min left | 97% | 1839 | 96.6% | 97.5% | -1.0 ± 0.4 | -1.0% |
| 30 to 60 | 80% | 1076 | 81.0% | 83.9% | -2.9 ± 1.2 | -3.5% |
| 30 to 60 | 85% | 1178 | 83.8% | 88.1% | -4.3 ± 1.1 | -4.9% |
| 30 to 60 | 90% | 1250 | 88.2% | 92.3% | -4.0 ± 0.9 | -4.4% |
| 30 to 60 | 95% | 1316 | 93.2% | 96.1% | -2.9 ± 0.7 | -3.0% |
| 30 to 60 | 97% | 1256 | 95.9% | 97.6% | -1.6 ± 0.6 | -1.7% |
| 15 to 30 | 80% | 662 | 87.5% | 84.9% | +2.5 ± 1.3 | 3.0% |
| 15 to 30 | 85% | 784 | 88.3% | 88.9% | -0.7 ± 1.1 | -0.8% |
| 15 to 30 | 90% | 889 | 92.2% | 92.9% | -0.6 ± 0.9 | -0.7% |
| 15 to 30 | 95% | 1054 | 95.4% | 96.3% | -1.0 ± 0.6 | -1.0% |
| 15 to 30 | 97% | 1065 | 97.1% | 97.6% | -0.5 ± 0.5 | -0.5% |
| 5 to 15 | 80% | 371 | 92.7% | 88.0% | +4.7 ± 1.3 | 5.6% |
| 5 to 15 | 85% | 536 | 94.8% | 91.0% | +3.8 ± 1.0 | 4.3% |
| 5 to 15 | 90% | 783 | 96.9% | 93.7% | +3.3 ± 0.6 | 3.5% |
| 5 to 15 | 95% | 964 | 97.7% | 96.7% | +1.1 ± 0.5 | 1.1% |
| 5 to 15 | 97% | 992 | 98.6% | 97.7% | +0.9 ± 0.4 | 0.9% |
| under 5 | 80% | 147 | 96.6% | 93.1% | +3.5 ± 1.5 | 3.7% |
| under 5 | 85% | 202 | 96.5% | 94.4% | +2.1 ± 1.3 | 2.3% |
| under 5 | 90% | 308 | 98.1% | 95.3% | +2.7 ± 0.8 | 2.9% |
| under 5 | 95% | 454 | 99.3% | 97.0% | +2.3 ± 0.4 | 2.4% |
| under 5 | 97% | 498 | 99.6% | 97.8% | +1.8 ± 0.3 | 1.9% |

### Under 15 minutes to the recorded finish, tight book, by league (not knowable live)

| League | Threshold | Taken | Win rate | Break-even | Edge (pts) | Profit per $ |
|---|---|---|---|---|---|---|
| CBB | 80% | 244 | 93.4% | 89.2% | +4.2 ± 1.6 | 4.7% |
| CBB | 85% | 351 | 94.0% | 91.9% | +2.1 ± 1.2 | 2.3% |
| CBB | 90% | 529 | 96.2% | 94.2% | +2.0 ± 0.8 | 2.2% |
| CBB | 95% | 746 | 98.4% | 96.8% | +1.6 ± 0.5 | 1.7% |
| CBB | 97% | 803 | 99.0% | 97.7% | +1.3 ± 0.3 | 1.3% |
| CFB | 80% | 48 | 91.7% | 88.3% | +3.4 ± 4.0 | 3.9% |
| CFB | 85% | 64 | 93.8% | 90.9% | +2.9 ± 3.0 | 3.1% |
| CFB | 90% | 86 | 97.7% | 93.9% | +3.7 ± 1.6 | 4.0% |
| CFB | 95% | 95 | 96.8% | 96.6% | +0.2 ± 1.8 | 0.2% |
| CFB | 97% | 91 | 98.9% | 97.7% | +1.2 ± 1.1 | 1.2% |
| NBA | 80% | 97 | 91.8% | 88.7% | +3.0 ± 2.8 | 3.4% |
| NBA | 85% | 145 | 94.5% | 92.0% | +2.5 ± 1.9 | 2.7% |
| NBA | 90% | 207 | 98.6% | 94.4% | +4.1 ± 0.8 | 4.4% |
| NBA | 95% | 271 | 97.8% | 96.8% | +1.0 ± 0.9 | 1.1% |
| NBA | 97% | 305 | 98.7% | 97.8% | +0.9 ± 0.7 | 1.0% |
| NFL | 80% | 33 | 87.9% | 87.6% | +0.3 ± 5.3 | 3.8% |
| NFL | 85% | 40 | 97.5% | 91.4% | +6.1 ± 2.5 | 8.1% |
| NFL | 90% | 42 | 97.6% | 94.9% | +2.7 ± 2.2 | 2.8% |
| NFL | 95% | 52 | 100.0% | 96.9% | +3.1 ± 0.1 | 3.2% |
| NFL | 97% | 51 | 100.0% | 97.7% | +2.3 ± 0.1 | 2.4% |
| NHL | 80% | 96 | 100.0% | 92.1% | +7.9 ± 0.6 | 8.5% |
| NHL | 85% | 138 | 99.3% | 92.5% | +6.8 ± 0.9 | 7.3% |
| NHL | 90% | 227 | 98.2% | 93.7% | +4.6 ± 0.9 | 4.9% |
| NHL | 95% | 254 | 98.4% | 96.8% | +1.6 ± 0.8 | 1.6% |
| NHL | 97% | 240 | 98.8% | 97.7% | +1.0 ± 0.7 | 1.0% |

## In play, by league, every crossing

| League | Threshold | Taken | Win rate | Break-even | Edge (pts) | Profit per $ |
|---|---|---|---|---|---|---|
| CBB | 80% | 5068 | 81.5% | 85.7% | -4.3 ± 0.4 | -4.9% |
| CBB | 85% | 4823 | 85.1% | 89.3% | -4.2 ± 0.4 | -4.6% |
| CBB | 90% | 4526 | 89.4% | 93.0% | -3.6 ± 0.4 | -3.8% |
| CBB | 95% | 4115 | 94.0% | 96.4% | -2.4 ± 0.4 | -2.5% |
| CBB | 97% | 3641 | 95.7% | 97.6% | -2.0 ± 0.3 | -2.0% |
| CFB | 80% | 1095 | 82.8% | 86.8% | -3.9 ± 0.9 | -4.4% |
| CFB | 85% | 1042 | 86.0% | 89.8% | -3.9 ± 0.9 | -4.2% |
| CFB | 90% | 970 | 90.1% | 93.0% | -2.9 ± 0.9 | -3.0% |
| CFB | 95% | 859 | 94.2% | 96.2% | -2.0 ± 0.8 | -2.1% |
| CFB | 97% | 744 | 96.1% | 97.5% | -1.4 ± 0.7 | -1.5% |
| NBA | 80% | 1484 | 82.5% | 84.7% | -2.2 ± 0.8 | -2.3% |
| NBA | 85% | 1397 | 86.5% | 88.6% | -2.1 ± 0.8 | -2.1% |
| NBA | 90% | 1317 | 90.1% | 92.6% | -2.5 ± 0.8 | -2.5% |
| NBA | 95% | 1181 | 95.1% | 96.2% | -1.1 ± 0.6 | -1.0% |
| NBA | 97% | 1056 | 97.3% | 97.6% | -0.2 ± 0.5 | -0.2% |
| NFL | 80% | 371 | 79.0% | 84.5% | -5.6 ± 1.7 | -6.3% |
| NFL | 85% | 337 | 84.9% | 88.7% | -3.8 ± 1.7 | -3.9% |
| NFL | 90% | 302 | 91.1% | 92.6% | -1.5 ± 1.6 | -1.5% |
| NFL | 95% | 261 | 95.8% | 96.2% | -0.5 ± 1.2 | -0.5% |
| NFL | 97% | 219 | 98.2% | 97.6% | +0.5 ± 0.9 | 0.5% |
| NHL | 80% | 1337 | 81.2% | 85.8% | -4.6 ± 0.9 | -5.3% |
| NHL | 85% | 1256 | 85.4% | 89.4% | -4.0 ± 0.9 | -4.4% |
| NHL | 90% | 1164 | 89.6% | 93.0% | -3.4 ± 0.8 | -3.6% |
| NHL | 95% | 1009 | 93.5% | 96.4% | -2.9 ± 0.7 | -3.0% |
| NHL | 97% | 871 | 94.6% | 97.6% | -3.0 ± 0.7 | -3.0% |

## What a slow loop would actually get

The same positions, filled as a poller would fill them: it sees the crossing some minutes late and sends a limit at the ask it saw. The order fills only when the ask has not risen since (the lead has not grown) and misses when it has, so the fills are a selected set and their break-even is lower than the trigger price. A fifteen-minute latency is what a quarter-hourly scheduled job delivers; on a late position it cannot fill at all, because the game is over.

Every in-play crossing:

| Latency | Threshold | Filled / taken | Win rate | Break-even | Edge (pts) | Profit per $ |
|---|---|---|---|---|---|---|
| 1 min | 80% | 5712 / 9355 | 79.3% | 82.3% | -3.0 ± 0.5 | -3.4% |
| 1 min | 85% | 5345 / 8855 | 83.6% | 85.8% | -2.2 ± 0.5 | -2.3% |
| 1 min | 90% | 4964 / 8279 | 87.4% | 89.7% | -2.3 ± 0.4 | -2.4% |
| 1 min | 95% | 4683 / 7425 | 92.5% | 93.9% | -1.3 ± 0.4 | -1.3% |
| 1 min | 97% | 4369 / 6531 | 95.0% | 95.7% | -0.7 ± 0.3 | -0.7% |
| 5 min | 80% | 4756 / 9355 | 76.3% | 78.6% | -2.3 ± 0.5 | -2.7% |
| 5 min | 85% | 4309 / 8855 | 80.1% | 82.1% | -2.0 ± 0.5 | -2.3% |
| 5 min | 90% | 3832 / 8279 | 83.7% | 86.3% | -2.5 ± 0.5 | -2.7% |
| 5 min | 95% | 3536 / 7425 | 90.3% | 91.1% | -0.8 ± 0.4 | -0.7% |
| 5 min | 97% | 3278 / 6531 | 93.1% | 93.6% | -0.4 ± 0.4 | -0.4% |
| 15 min | 80% | 4051 / 9355 | 70.7% | 74.0% | -3.3 ± 0.6 | -4.2% |
| 15 min | 85% | 3597 / 8855 | 74.9% | 77.5% | -2.7 ± 0.6 | -3.2% |
| 15 min | 90% | 3028 / 8279 | 79.2% | 81.7% | -2.5 ± 0.6 | -2.8% |
| 15 min | 95% | 2590 / 7425 | 87.5% | 87.7% | -0.2 ± 0.5 | -0.0% |
| 15 min | 97% | 2390 / 6531 | 91.3% | 91.1% | +0.1 ± 0.5 | 0.3% |

Under 15 minutes to the recorded finish with a tight book (not knowable live; `reports/standing_order_backtest.md` repeats the test with a knowable late):

| Latency | Threshold | Filled / taken | Win rate | Break-even | Edge (pts) | Profit per $ |
|---|---|---|---|---|---|---|
| 1 min | 80% | 207 / 518 | 91.3% | 85.1% | +6.2 ± 1.7 | 7.6% |
| 1 min | 85% | 320 / 738 | 92.8% | 88.4% | +4.4 ± 1.3 | 5.2% |
| 1 min | 90% | 482 / 1091 | 96.3% | 91.2% | +5.0 ± 0.8 | 5.5% |
| 1 min | 95% | 691 / 1418 | 97.1% | 94.5% | +2.6 ± 0.6 | 2.7% |
| 1 min | 97% | 815 / 1490 | 98.5% | 96.2% | +2.3 ± 0.4 | 2.4% |
| 5 min | 80% | 97 / 518 | 78.4% | 65.2% | +13.2 ± 3.1 | 21.0% |
| 5 min | 85% | 129 / 738 | 82.9% | 74.1% | +8.8 ± 2.3 | 12.4% |
| 5 min | 90% | 187 / 1091 | 89.8% | 82.4% | +7.4 ± 1.8 | 9.0% |
| 5 min | 95% | 306 / 1418 | 93.5% | 89.3% | +4.1 ± 1.2 | 4.6% |
| 5 min | 97% | 414 / 1490 | 96.6% | 93.0% | +3.6 ± 0.8 | 3.9% |
| 15 min | 80% | 0 / 518 |  |  |  |  |
| 15 min | 85% | 0 / 738 |  |  |  |  |
| 15 min | 90% | 0 / 1091 |  |  |  |  |
| 15 min | 95% | 0 / 1418 |  |  |  |  |
| 15 min | 97% | 0 / 1490 |  |  |  |  |

## Before the game

The first minute before the start at which the ask reached the threshold, which can be days out.

| League | Threshold | Taken | Win rate | Break-even | Edge (pts) | Profit per $ |
|---|---|---|---|---|---|---|
| CBB | 80% | 1306 | 87.9% | 89.1% | -1.2 ± 0.9 | -1.2% |
| CBB | 85% | 942 | 91.2% | 91.7% | -0.6 ± 0.9 | -0.4% |
| CBB | 90% | 600 | 94.7% | 94.3% | +0.4 ± 0.9 | 0.5% |
| CBB | 95% | 287 | 98.3% | 96.7% | +1.6 ± 0.8 | 1.6% |
| CBB | 97% | 156 | 96.8% | 97.7% | -0.9 ± 1.4 | -0.9% |
| CFB | 80% | 407 | 86.2% | 90.4% | -4.1 ± 1.7 | -4.3% |
| CFB | 85% | 311 | 89.4% | 92.7% | -3.3 ± 1.7 | -3.3% |
| CFB | 90% | 228 | 90.8% | 94.7% | -3.9 ± 1.9 | -3.7% |
| CFB | 95% | 110 | 92.7% | 96.8% | -4.1 ± 2.4 | -4.2% |
| CFB | 97% | 53 | 98.1% | 97.8% | +0.3 ± 1.9 | 0.3% |
| NBA | 80% | 350 | 83.7% | 87.3% | -3.6 ± 2.0 | -3.3% |
| NBA | 85% | 223 | 88.3% | 90.1% | -1.8 ± 2.3 | -0.8% |
| NBA | 90% | 114 | 90.4% | 92.9% | -2.5 ± 3.2 | -0.3% |
| NBA | 95% | 26 | 80.8% | 96.0% | -15.2 ± 9.9 | -7.8% |
| NBA | 97% | 6 | 100.0% | 97.4% | +2.6 ± 0.1 | 2.7% |
| NFL | 80% | 43 | 81.4% | 86.5% | -5.2 ± 5.9 | -6.0% |
| NFL | 85% | 26 | 88.5% | 89.3% | -0.9 ± 6.3 | -1.0% |
| NFL | 90% | 10 | 90.0% | 91.6% | -1.6 ± 9.6 | -1.7% |
| NHL | 80% | 6 | 50.0% | 88.5% | -38.5 ± 16.2 | -43.5% |
| NHL | 85% | 5 | 60.0% | 93.2% | -33.2 ± 18.9 | -35.6% |
| NHL | 90% | 4 | 50.0% | 95.3% | -45.3 ± 18.8 | -47.5% |
| NHL | 95% | 3 | 33.3% | 96.7% | -63.3 ± 16.1 | -65.5% |
| NHL | 97% | 3 | 33.3% | 97.3% | -64.0 ± 15.8 | -65.7% |

## Reading it

- A position is one side of one game at one threshold in one phase; a side that climbs through several thresholds appears at each, so the standard errors are clustered by game.
- The tape is sampled once a minute and carries the top of the book only: the two asks, whose sum over one is the spread, and nothing of what rests behind them. A fill at the ask is assumed for the size meant; the live rule reads the depth it does not have here.
- The live favorites rule took a crossing at any spread until 24 October 2026; on this tape, a bar of 4¢ removes the empty books and most of the loss, and the rule carries it since.
- With late defined as it can be known during the game, a late favorite on a tight book has lost about a point against its cost, or broken even; no threshold shows an edge. Earlier in the game it has lost more.
- The fee is the market's own coefficient times price times one less the price; the break-even rate is the mean cost, fee included.
- The time left is to the venue's recorded finish (or the last minute the tape priced the game), not the game clock: an NFL game's last five minutes of play are more than five minutes of tape.
- Positive and several errors wide, over hundreds of positions, before it means anything. The live record (`tracking/favorites.csv`) is the out-of-sample continuation of this table.
