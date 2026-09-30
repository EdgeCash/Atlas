# NHL curated plays — pre-registration (docs/MODEL_PLAN_NHL.md, step 9)

**Committed before any rule below was scored.** The git history is the
evidence: this file lands in a commit of its own, and the code that scores it
(`atlas/research/nhl_plays.py`) and its results (`reports/nhl_plays.md`) come
after. The plan's step 9 says curated NHL plays exist *only if a rule
clears its bar*; this fixes the rules and the bar before anyone looks.

---

## Known before registration

Honesty about what was already seen, so nothing here pretends to be blind:

- The game model's Brier on the moneyline against the closing line
  (`reports/nhl_model.md`): 0.2388 against the market's 0.2385 pooled over
  2010–22; 0.2276 against 0.2256 in 2021–22. Atlas is close to the close and
  not better than it.
- The share of Atlas's moneyline disagreement that has turned out real,
  fitted on the whole record 2013–14 to date (`atlas/owner/nhl_board.py`):
  0.46. About half.
- No rule below has been computed on any season, and no threshold has been
  looked at.

## The model (frozen)

The stored NHL game model, unchanged: `reports/nhl_model.json` (spec, home
and back-to-back terms, and every season's grid layer, each fitted on the
three seasons before it). Walked forward with those choices
(`atlas.models.nhl_model.run` with the stored terms and layers), every
game's numbers made before it. No refit, no new feature, no new term during
this test.

## The market (frozen)

The archive's closing lines (`atlas/sources/nhl.py`, sportsbookreviewsonline),
2013–14 to 2022–23 (the archive ends partway through 2022–23): the closing
moneyline, the closing total and its two prices, the closing puck line (±1.5)
and its two prices. The market's probability is the two closing prices with
the margin taken out proportionally. A game missing a price is not a
candidate for that market.

## The rules (frozen)

Three, one per market, the same shape each:

| Rule | Atlas's probability of a side | The side |
|---|---|---|
| **M**, moneyline | P(home wins), overtime and shootout included | the side Atlas rates above the market |
| **T**, total | P(over the closing total) ÷ (1 − P(push)), from the grid's total distribution | the side Atlas rates above the market |
| **P**, puck line | P(home by 2 or more) for home −1.5, else 1 − P(away by 2 or more) | the side Atlas rates above the market |

**Disagreement** is Atlas's probability of its side minus the market's, in
points. A game is a bet when its disagreement is at least the threshold. One
unit a bet at the closing price of that side; a total that lands on a
whole-number line is a push and returns the unit.

## Threshold selection (frozen)

For each test season, chosen **on the seasons before it only** (from
2013–14), over the grid **{2, 3, 4, 5, 6, 8, 10}** points: the threshold
that maximises units at the closing price, subject to at least **300**
training bets; ties to the lower threshold. The first test season,
2014–15, is chosen on 2013–14 alone.

## Seasons (frozen)

- **Deciding: 2020–21, 2021–22 and 2022–23** (the archive's part of it).
  Outside the game model's fit seasons (2010–17) and its tuning seasons
  (2017–20). Each scored once.
- **Descriptive: 2014–15 to 2019–20**, walked forward the same way. The
  model's spec was tuned on some of these, so they cannot decide; they can
  only contradict.

## Decision criteria (frozen)

A rule is **REAL** only if **all five** hold, on the deciding seasons
pooled unless said otherwise:

1. **Positive units** at the closing price.
2. **The side beats the market's own fair probability:** the lower bound of
   the bootstrap confidence interval of the mean of (won − the market's
   probability of the side), pushes left out, is above zero. Three rules are
   tested, so the interval is two-sided at 1 − 0.05/3 (98.3%), 10,000
   resamples of bets, seed 2026.
3. **At least two of the three deciding seasons** with positive units.
4. **Positive units at a price five cents worse** on every bet (−150 taken
   as −155, +130 as +125).
5. **At least 150 bets.**

And the descriptive seasons must not contradict: **pooled units over
2014–20 not negative**. A rule failing that is not real whatever the
deciding seasons say.

## What follows

- A rule that is REAL becomes the NHL's curated play on the owner page, its
  threshold chosen by the same selection rule on every season through
  2022–23, logged and graded the way the football plays are
  (`atlas/owner/plays.py`), and published nowhere else.
- A rule that is not real is not a play. The owner board's NHL picks (step 6:
  positive expected value by Atlas pulled halfway to the market) are a
  different thing and stay as they are; they are graded on their own record
  and decide nothing here.
- Nothing is re-run with another grid, another floor or another season
  split. A future test of a changed model is a new registration.
