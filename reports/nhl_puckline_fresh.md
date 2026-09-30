# NHL puck line: the fresh test on 2023-26

Scored once by the heavy refresh, as `docs/NHL_PUCKLINE_FRESH_PREREGISTRATION.md` fixed it: the first test's puck-line rule at a 5-point threshold, the stored game model walked forward unchanged, the BettingPros consensus close at ±1.5 as the market (sealed, never in the clear), DraftKings' price (else FanDuel's). Aggregates only.

| Criterion | Result | Met |
|---|---|---|
| 1. Positive units | -27.7 on 635 bets (-4.4% a bet) | **no** |
| 2. Won minus the market's probability, 95% lower bound above zero | +0.0% (lower bound -3.8%) | **no** |
| 3. Seasons up | 0 of 3 | **no** |
| 4. Positive units five cents worse | -36.3 | **no** |
| 5. At least 150 bets | 635 | yes |

**The puck line does not clear its bar. There is no curated NHL play.**

| Season | Games tested | Bets | Units | Closes at the off left out | Scored |
|---|---|---|---|---|---|
| 2023-24 | 1249 | 211 | -8.0 | 2 | yes |
| 2024-25 | 1304 | 206 | -7.4 | 0 | yes |
| 2025-26 | 1244 | 218 | -12.4 | 0 | yes |
