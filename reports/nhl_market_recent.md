# The NHL's market row for the recent seasons

`python -m atlas.owner.nhl_history`, in the heavy refresh. The closing moneyline from BettingPros (sealed in `tracking/owner_nhl_history/`, never in the clear), its margin taken out; the stored game model walked forward unchanged. Brier on P(home wins), overtime and the shootout included. Aggregates only.

| Season | Games | Of which closed at the off | Consensus close | DraftKings close (games) | Atlas | Left out |
|---|---|---|---|---|---|---|
| 2024-25 | 1,224 | 144 | 0.2321 | 0.2322 (1,224) | 0.2347 | – |
| 2025-26 | 1,253 | 1,251 | 0.2438 | 0.2440 (1,253) | 0.2456 | – |
| 2022-26 pooled | 2,477 | 1,395 | 0.2380 | 0.2382 (2,477) | 0.2402 | – |

A close taken at the off is a book's last line on the pregame market as it came off the board, for games whose lines came back stamped after puck drop. Those count only when a season has 30 or more and they score like pregame closes (Brier 0.22 or worse): an in-game price knows the score.

Seasons backfilled: 2025-26 done.
