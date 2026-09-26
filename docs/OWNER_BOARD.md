# The owner's board

From 26 September 2026. For the owner's eyes only: every upcoming game
priced across every book BettingPros quotes, ranked by expected value, with
the sides worth taking logged and graded. Code: `atlas/owner/board.py`,
`atlas/sources/bettingpros.py`, `atlas/owner/market.py`. Shown inside the
owner page's ciphertext beside the curated plays, built by every poll and
every rebuild.

## Why it exists

The research behind Atlas found two things a private bettor can use. The
market's price is not one number: across a dozen books the best line and
price on a side is worth one to two percent, more than the model adds. And
Atlas's total disagreeing with the line has been worth something only in
proportion to its size, and less than its in-season calibration claims: on
the current model's walk-forward, Atlas's side hits about 51% on small gaps,
53% at five points, 56% at ten. The board puts both on one page and lets the
prices decide.

## What is on it

For each game inside eight days, for the total and the spread:

- **Consensus**: BettingPros' consensus line and both prices, and the
  opening line (ignored when a prediction market set it).
- **Every takeable book's current main line and price**, with the time it was
  updated. The consensus and prediction markets (Novig, ProphetX, Kalshi,
  Polymarket) are reference, never taken; a line marked off is skipped.
- **Price edge**: the expected value of a book's price under the consensus
  market read at that book's line (`atlas/live/probability.py`: the
  consensus's two prices give a vig-free probability at its line, the fitted
  market shape moves it to the book's line).
- **Atlas EV** (totals only): the expected value under Atlas's probability
  at that book's line, where the probability is the walk-forward hit rate of
  Atlas's side at gaps that large or larger (`tracking/calibration.csv`,
  rebuilt every rebuild). Spreads carry price edge only: the model's market
  weight on spreads is 1.00.
- **The better side at its best book**, by Atlas EV on totals and price edge
  on spreads, with how many books were quoting.
- **Flags**: steam (the consensus moved 1.5+ points on a total, 1+ on a
  spread, from a real book's opener), off-market (the best book a point or
  more off consensus on a total, half a point on a spread), moved against
  Atlas, and BettingPros' kickoff wind forecast from 15 mph outdoors.

## Picks

The sides with positive expected value at the best price, one per game and
market, at most eight, best first. Each is logged once, at the book, line
and price on the board the first time it qualifies, into a sealed record
(`tracking/owner_board/`), and never revised. It is graded on the final
score at the price taken and against the consensus close (the consensus
book's last line before kickoff, from the sealed market record), in points
and in win probability. The record says nothing until fifty are graded.

## What is stored, and where

Every poll appends each book's line to `tracking/owner_market/`, one file
per ISO week, compressed and sealed with the owner key, appended on change
only. Nothing from BettingPros is written in the clear anywhere in the
repository or on any page; the API's request echo (which carries the
credentials) is dropped before a response is read. Credentials are the
repository secrets `BP_API_KEY`, `BP_USER_ID` and `BP_USER_KEY`, passed to
the Refresh step in both workflows.

Budget: about twenty requests per run (events by week, then offers a dozen
games at a time for two markets and two sports), against a limit of 5,000 a
day. Rate and quota errors leave that batch out and keep the rest.

## What it does not do

It does not bet, size, or promise. Atlas EV is what the model's disagreement
has been worth on its own walk-forward, and price edge is arithmetic on the
books' own prices; neither is a forecast of this weekend. Moneylines, alt
lines and team totals are not on it yet; the score grid could price them and
that is the next thing to test. The public site is unchanged.
