# The NHL's market row for the recent seasons

`python -m atlas.owner.nhl_history`, in the heavy refresh. The closing moneyline from BettingPros (sealed in `tracking/owner_nhl_history/`, never in the clear), its margin taken out; the stored game model walked forward unchanged. Brier on P(home wins), overtime and the shootout included. Aggregates only.

| Season | Games | Consensus close | DraftKings close (games) | Atlas |
|---|---|---|---|---|
| 2024-25 | 612 | 0.2348 | 0.2348 (612) | 0.2371 |
| 2025-26 | 2 | 0.2081 | 0.2137 (2) | 0.2373 |
| 2022-26 pooled | 614 | 0.2347 | 0.2347 (614) | 0.2371 |

Seasons backfilled: 2025-26 done.
