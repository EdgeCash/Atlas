# Daily plays: pre-registration of rule `daily-v1`

Frozen 30 September 2026, before the first play was logged. Code:
`atlas/owner/highfive.py`. Record: `tracking/owner_highfive/` (sealed).
Evidence: `reports/highfive_backtest.md`.

## The rule

Every run, from the owner board's priced legs (every takeable book's price on
every side, `atlas/owner/board.py` and `atlas/owner/nhl_board.py`), the plays
for the Eastern day with games are:

1. **NHL** (moneyline, puck line, total): the side whose vig-free consensus
   probability is at least 0.50, when Atlas's probability, shrunk toward the
   consensus by the board's share (0.46), gives positive expected value at
   the best takeable book. Ranked by that expected value.
2. **Football** (NCAAF and NFL totals and spreads): the side of the line
   Atlas's number favours, when the price edge at the best takeable book
   against the consensus is positive. Ranked by that price edge. Atlas's
   probability is not used, and the size of its disagreement is not the rank.
3. One play a game, at most five a day, no minimum. A day where nothing
   passes logs nothing.
4. Logged once, at the first run at or after 10:00 ET on the day, at the book,
   line and price shown; never revised. Graded win, loss or push on the final
   score, in units at the price logged.

Two labels are recorded with each play and are not filters: the model's hit
rate over its last 100 decided walk-forward results in the play's market at
the time (`form`), and the market's probability of the side (`p_fair`).

## Why this rule, and what it predicts

- On the 2013-22 walk-forward at the close, Atlas's NHL picks on the side the
  market favoured hit 61.2% against a market fair of 58.4% (4,760 games,
  positive in 7 of 10 seasons); on the underdog side they hit 41.5% against a
  fair of 41.1% while claiming 45.3%. A top-five rule restricted to favourites
  hit 58.4% (95%: 55-62%) and paid +1.8% a play at a 4.5% hold; the same days'
  chalk paid -0.2%. **Prediction:** NHL plays hit between 55% and 62% and pay
  between 0 and +3% a play at the prices logged.
- In football, hit rate by quintile of Atlas's disagreement with the close is
  flat in every market. So football plays bet the price, not the model. This
  has no history to test against. **Prediction:** none beyond the price edge
  itself, about +1% to +2% a play if the best price is real at the moment of
  logging and 0 or worse if it is not.

## What would end it

Judged at 100 decided plays per split (NHL, football), the size the curated
plays use, and not before:

- **Clears:** the win rate's 95% interval sits above break-even at the prices
  taken and units are positive.
- **Fails:** at or below break-even at the prices taken, or units negative
  over 200 decided plays.

The rule is frozen. A change to any bar, the shrink, the cap or the hour is a
new rule with a new id and a record that starts the day it is frozen.

## What it is not

Not a claim to beat the closing line; the record is what the plays did. Not
five a day: the Daily High Five, which chose the five best by expected value
and five props, was tested on the same walk-forward before its record began
and dropped (47.7% over 6,945 plays under the model's own probabilities; the
props had nothing to test against).
