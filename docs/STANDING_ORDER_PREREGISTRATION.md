# Standing orders late in games: pre-registration

Written and committed on 24 October 2026, before the backtest it describes was
run. The rule, the primary test and the pass criteria below are fixed; the
backtest (`atlas/polymarket/standing.py`) reports them as written, and every
other cell it prints is exploration, not evidence.

## The idea

The favorites rule takes the ask: it pays the spread and the fee to buy a
favorite the moment its price crosses a threshold. On an exchange the other
way to buy is to post a bid and wait for a seller. The hypothesis is that late
in a game, when the trailing side makes a run, other bettors sell the favorite
for less than its chance of holding on is worth, and a bid resting a few cents
under the market collects those prices.

## What changed before this was written

The favorites backtest (`reports/favorites_backtest.md`) measured "late" as
minutes to the venue's recorded finish. That time is not known during the
game, and games that run long are disproportionately the close ones the
favorite loses, so that definition dropped them from the late bucket. With a
definition knowable during the game, the late taker edge it reported is gone
(about −1 point at 85 to 95 cents, against +1.5 to +3.5). This test uses only
information available at the time of each order.

## The rule

- **Games.** Every settled moneyline the venue lists for the NFL, NBA, NHL,
  college football and college basketball, as cached under
  `data/raw/polymarket_us/`, each side on its own.
- **Late.** Minutes since the start at or beyond the league's median game
  length (start to finish, over the same games) less fifteen, and before the
  game ends. The median is a league constant, not a fact about the game.
- **Trigger.** The first late minute at which the side's ask is at or above
  the threshold T and at or below 98 cents, with the two sides' asks summing
  to no more than 1.04 (a book inside 4 cents). One trigger per side per
  threshold.
- **Order.** A buy limit at P = the trigger minute's ask less d cents,
  resting for the W minutes after the trigger minute, cancelled when the game
  ends.
- **Fill.** "Through": the first minute in the order's life at which the
  side's ask is below P fills it at P. "Touch" (exploration): an ask at or
  below P.
- **Cost.** P plus the fee: the market's own taker coefficient × P × (1 − P)
  (conservative, since a resting order may pay less), or none (exploration).
- **Grade.** The venue's settled price for the side.

## The primary test

T = 85 cents, d = 3 cents, W = 5 minutes, through fills, the taker fee.

It passes only if all three hold:

1. at least 200 orders fill;
2. the edge (win rate less the mean cost) less 1.96 standard errors,
   clustered by game, is above zero;
3. the edge is above zero in each chronological half of the filled orders,
   split at the median trigger date.

Otherwise the result is "not established", whatever any other cell shows.

## Exploration, reported in full

T in {85, 90} cents; d in {1, 3, 5} cents; W in {3, 5, 10} minutes; through
and touch fills; the taker fee and none; and, for each T, the taker at the
trigger minute on the same triggers, for comparison.

## Limits stated in advance

- The tape is one sample a minute of the top of the book: a dip between
  samples is missed, and a fill assumes nobody was ahead of the order at P.
- "Late" here is elapsed time, not the game clock. The live worker uses the
  venue's period, which this tape does not carry; its own paper record is
  the test of that.
- One season of games, most of them college basketball.
