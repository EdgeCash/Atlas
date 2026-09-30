# The NHL's market row for the recent seasons

`python -m atlas.owner.nhl_history`, in the heavy refresh. The closing moneyline from BettingPros (sealed in `tracking/owner_nhl_history/`, never in the clear), its margin taken out; the stored game model walked forward unchanged. Brier on P(home wins), overtime and the shootout included. Aggregates only.

| Season | Games | Of which closed at the off | Consensus close | DraftKings close (games) | Atlas | Left out |
|---|---|---|---|---|---|---|
| 2022-23 | 1,232 | 0 | 0.2343 | 0.2344 (1,231) | 0.2354 | – |
| 2023-24 | 1,251 | 0 | 0.2333 | 0.2338 (1,218) | 0.2363 | 2 closed at the off (too few to judge) |
| 2024-25 | 1,306 | 226 | 0.2318 | 0.2319 (1,306) | 0.2352 | – |
| 2025-26 | 1,253 | 1,251 | 0.2438 | 0.2440 (1,253) | 0.2456 | – |
| 2022-26 pooled | 5,042 | 1,477 | 0.2358 | 0.2360 (5,008) | 0.2381 | 2 closed at the off |

A close taken at the off is a book's last line on the pregame market as it came off the board, for games whose lines came back stamped after puck drop. Those count only when a season has 30 or more and they score like pregame closes (Brier 0.22 or worse): an in-game price knows the score.

Seasons backfilled: 2022-23 done, 2023-24 done, 2024-25 done, 2025-26 done.
