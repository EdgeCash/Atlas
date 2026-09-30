# NHL puck line, a fresh test on 2023–26 — pre-registration

**Committed before any puck-line number for 2023–24, 2024–25 or 2025–26 was
computed.** The git history is the evidence: this file lands in a commit of
its own; the code that scores it and its one result come after. The first
registration (`docs/NHL_PLAYS_PREREGISTRATION.md`) said a new test is a new
registration. This is that registration, asked for by the owner on 30
September 2026 after the BettingPros backfill made seasons the first test
never saw available.

---

## Known before registration

- The first test (`reports/nhl_plays.md`): no rule cleared its bar. The
  puck line came closest over 2020–23: +34.5 units on 997 bets, all three
  seasons up, still up five cents worse, but won 2.3 points above the
  market's probability with a 98.3% lower bound of −1.4. It is being tested
  again *because* it came closest; that choice is the reason the seasons
  below must be ones it has never been scored on.
- The threshold below, computed from the archive alone (2014–15 to 2022–23)
  by the first test's own selection rule: 5 points, 1,839 bets there. Those
  are training seasons, not a result.
- The backfill's first run (`reports/nhl_market_recent.md`): on 612 games of
  2024–25, the consensus moneyline close's Brier 0.2348 against Atlas's
  0.2371; 2025–26's lines came back stamped after puck drop. Nothing about
  the puck line in any of the three seasons.

## The model (frozen)

The stored NHL game model, unchanged: `reports/nhl_model.json`, walked
forward with its stored terms and every season's grid layer (each fitted on
the three seasons before it). No refit, no new term.

## The market (frozen)

The BettingPros closes the heavy refresh backfills and seals
(`atlas/owner/nhl_history.py`, rule 2):

- **The market's probability** of a side: the consensus close at ±1.5, its
  two prices with the margin taken out proportionally.
- **The price taken**: DraftKings' close for that side at the same handicap;
  FanDuel's where DraftKings has none there; no bet where neither has.
- **A close taken at the off** (a season whose lines came back stamped after
  puck drop) counts only in a season whose consensus moneyline closes taken
  at the off pass the market row's check: 30 or more, and a Brier of 0.22 or
  worse (a pregame price's, not an in-game one's). Otherwise that season's
  games closed at the off are left out.
- A season with fewer than 300 games left to test is left out entirely.

## The rule (frozen)

The first registration's rule P, unchanged: Atlas's probability of the home
side covering is P(home by 2 or more) for home −1.5, else 1 − P(away by 2 or
more); the side is the one Atlas rates above the market; the disagreement is
Atlas's probability of its side minus the market's, in points. A game is a
bet when the disagreement is **at least 5 points**. One unit a bet at the
price taken. Settled on the final score as the books settle it (a shootout's
deciding goal counts).

The threshold is fixed at 5, the first test's selection rule applied to
every archive season (at least 300 bets; the most units; ties to the lower).
It is not chosen again on any fresh season.

## Seasons (frozen)

**2023–24, 2024–25 and 2025–26**, regular season and playoffs, every game
with a usable close. None of them has been scored on the puck line.
Scored **once**, by the heavy refresh, the first time all three are
backfilled under rule 2; never again.

## Decision criteria (frozen)

The rule is **REAL** only if **all five** hold, on the seasons pooled unless
said otherwise:

1. **Positive units** at the price taken.
2. **The side beats the market's own probability:** the lower bound of the
   two-sided 95% bootstrap interval of the mean of (won − the market's
   probability of the side) is above zero; 10,000 resamples of bets, seed
   2026. One rule is tested, so no correction.
3. **At least two of the three seasons** with positive units (if a season is
   left out, every season scored).
4. **Positive units at a price five cents worse** on every bet (−150 taken
   as −155, +130 as +125).
5. **At least 150 bets.**

## What follows

- REAL: the puck line becomes the NHL's curated play on the owner page, at
  the 5-point threshold, logged and graded as the football plays are, and
  published nowhere else.
- Not real: no NHL curated play. The owner board's NHL picks (step 6) carry
  on, on their own record.
- Nothing is re-run with another threshold, another price source or another
  season set. A further test is a further registration.
