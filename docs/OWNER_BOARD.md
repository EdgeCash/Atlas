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

On the owner page the Board tab is four cards: **Picks now**, then **Totals**
and **Spreads** (each game's better side, best expected value first, the top
ten shown and the rest folded under "The other N games"), then the **Board
record** once picks are logged (latest graded picks folded). Each row reads
game and kickoff, the bet at its book (a spread names the team, not "home"),
the consensus and where it opened, the edge (EV, and the probability behind
it), and the flags. On a phone each row becomes a small card. Each card's
explanations fold under "How this works".

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

**The NHL, recorded** (`atlas/owner/nhl_capture.py`,
`docs/MODEL_PLAN_NHL.md` step 0). From opening night, every poll also takes
every book's moneyline, puck line and total on the NHL games within the next
day and a half into the same sealed market record, and at most once an hour
every book's line on the NHL player markets, PrizePicks among them, into
`tracking/owner_props/` (one sealed file per ISO week, appended on change).
The log says, in counts, how many games matched, which game and player
markets the catalogue has, and per market how many players, books and
PrizePicks lines there were.

**The NHL, priced** (`atlas/owner/nhl_board.py`, step 6). The same lines,
cards of their own on the Board tab after football's:

* **fair** is the consensus book's two prices with the margin out, at the
  consensus line; a book at another line is left out (the grid could move
  it, but a price edge read off Atlas's own shape is Atlas's opinion wearing
  the market's clothes);
* **Atlas** is the grid's probability for the side at that line
  (`tracking/nhl_projections.csv`: the moneyline, the puck line at ±1.5,
  totals 4.5 to 7.5), pulled toward fair by the share of its disagreement
  that has turned out real: least squares through the market on the NHL's
  moneyline record against the close in `tracking/calibration.csv`, 0.46
  over 11,764 games (0.46 too while the record is under 500);
* **picks** are the sides with positive expected value by Atlas at the best
  price: per game one on the result (the moneyline or the puck line, one
  team either way being one opinion) and one on the total, at most six;
  logged once, the first board they qualify on, into
  `tracking/owner_nhl/` (one sealed file per ISO week of puck drop), with
  the teams' BettingPros codes so the close can be read after puck drop;
  graded on the final score as the books settle it, a shootout goal
  included, and against the consensus close in win probability.

The same NHL legs go to the day's parlays and, where Kalshi or Polymarket
quote an NHL game, to the exchange board, valued by Atlas as above (on
football, Atlas's probability prices totals only). With no NHL game ahead
and no record, the NHL adds nothing to the page; with lines and no
projection, one line says so.

Budget: about eighteen requests per run for the board (events by week, then
offers a dozen games at a time for three markets and two sports), and for the
pick'em one market lookup per sport on the slate and at most sixteen pages of
player props; for the NHL one catalogue lookup, one events call per day and
about three offers calls per run, and at most forty pages of props an hour;
against a limit of 5,000 a day. Rate and quota errors leave that batch out
and keep the rest.

## What it does not do

It does not bet, size, or promise. Atlas EV is what the model's disagreement
has been worth on its own walk-forward, and price edge is arithmetic on the
books' own prices; neither is a forecast of this weekend. Moneylines, alt
lines and team totals are not on it yet; football's score grid could price
them and that is the next thing to test. The NHL's moneyline, puck line and
total are on it, from the NHL's own grid. The public site is unchanged.

## Daily parlays

Below the board, the owner page shows the day's parlays (`atlas/owner/parlays.py`), built from the
same priced legs: every takeable book's price on every side, with the probability the board uses for
it (Atlas's calibrated probability on totals, the consensus fair probability at that book's line on
spreads).

- **Legs** are the board's positive-EV sides from games kicking off today Eastern, or the next day with
  games: one per game at a book, the best six per book.
- **Parlays** are two or three of a book's legs from different games. Never a same-game parlay: the
  books price those on correlations this does not model. The same legs at several books are shown
  once, at the book that pays best for them; the best six by expected value are shown.
- **The arithmetic** is stated, not dressed up: with independent legs the parlay's expected value is
  the product of the legs' decimal odds times the product of their probabilities, minus one. A parlay
  compounds the legs' edges and their variance; it adds no information a single bet lacks.
- Each row shows the odds, the probability it hits, its expected value, a quarter-Kelly stake on a
  bankroll of one, and the age of its oldest quote, marked stale past 90 minutes, because a book may
  re-price a stale leg in its parlay builder.
- **The record** (`tracking/owner_parlays/`, sealed): the day's set is logged once, at the first run
  at or after 10:00 ET on that day, the moment rule v3 of the curated plays chooses, at the odds shown
  then. Graded when every leg's game is final; a pushed leg drops out and the odds reduce, as the books
  settle it. The live table keeps moving through the day and marks the logged set.

## Sports trading: Kalshi and Polymarket

The Trading tab (`atlas/owner/trading.py`) is a paper-trading model for the prediction exchanges, built from
the same BettingPros capture as the board: Kalshi (book 68), Polymarket US (75) and the global Polymarket (73).
The capture includes the game-winner market (moneyline) as well as totals and spreads; the board itself prices
only totals and spreads.

- **Fair value** is the sportsbook consensus with its margin removed, read at the contract's line; on totals,
  Atlas's calibrated probability, as on the board.
- **Cost** is the quote as a contract price (its implied probability) plus the taker fee,
  `rate × price × (1 − price)` per contract: 7% for Kalshi (its published formula; the exchange rounds each
  order up to the cent, not modelled) and 5% for Polymarket, the rate the Velocity repository modelled.
- **EV after fees** is fair ÷ cost − 1; the Kelly fraction is (fair − cost) ÷ (1 − cost).
- **Positions**: Kalshi and Polymarket US only (the global Polymarket is close-only for US accounts and is
  shown as a reference price), +2% or more after fees (raised from +1% on 26 September 2026; that day's positions
  were logged at +1%), one per game at the side and venue that pays best, at
  most ten a day; a quarter of Kelly, capped at 2% of the bankroll each and 10% a day.
- **Record** (`tracking/owner_trading/`, sealed): the day's positions are logged once at the first run from
  10:00 ET, like the parlays, and graded on the final score (a push refunded) and against the consensus close
  in win probability.
- The tab is three cards: **Positions for the day** (game over kickoff, contract over venue, price over fee, EV
  over the fair probability, stake over whether it is logged); the **Exchange board** (each game and market at
  its best exchange price, the best ten shown and the rest folded, with the quotes each venue gave this run
  folded beneath); and the **Trading record** once positions are logged. On a phone each row becomes a small
  card. The run's log carries the per-venue counts too, never a price.

To confirm before real money: that BettingPros shows each venue's price to buy, both fee rates against the
venues' current schedules, and depth (the quotes carry none, so a price may not fill at size). Nothing places
an order; execution would need a Kalshi API key and a Polymarket US account, and a paper record that earns it.

## Pick'em: PrizePicks

The Pick'em tab (`atlas/owner/pickem.py`) prices PrizePicks' lines against the sportsbooks' player props and
builds the slips worth entering. PrizePicks sells a line, not a price: More or Less on two to six players, paid
by a fixed table. The books sell the same props at prices, and a price says how likely a side is.

- **The capture**: every run, for the slate's games (not started, on today's Eastern date, or the next day with
  games), passing yards, rushing yards, receiving yards and receptions, every book's current line on both sides
  (`bettingpros.props`, markets found by slug). PrizePicks is book 37. The 26 September probe found PrizePicks on
  most NFL props and some college ones, with DraftKings, FanDuel, Caesars, Hard Rock and ProphetX quoting.
- **Fair value**: each sportsbook or exchange quoting both sides (FanDuel, DraftKings, Caesars, BetMGM, Fanatics,
  BetRivers, bet365, Hard Rock, theScore, ProphetX, Novig and a few more; never the consensus, a pick'em app or an
  unnamed book) gives a vig-free probability at its line, which a shape for the stat moves to PrizePicks' line; the
  median across books, two at least. Yardage shapes are a player's yards over the player's season mean without that game,
  NFL regular seasons 2016-2025 (`python -m atlas.owner.pickem fit`); receptions a negative binomial, variance 1.1
  times the mean. A book more than a quarter of its line (plus two yards), or a catch and a half, from PrizePicks
  is left out. College uses the NFL shapes.
- **Picks**: the likelier side of each standard line (PrizePicks quotes More and Less at it), from 54%. A line
  offered More only is a demon or a goblin: its payout depends on the mix and is not published, so it is left out
  and counted. A whole-number line can tie; a tie drops the pick from the entry, as PrizePicks settles it.
- **Slips**: for each entry (Power, every pick must hit; Flex, partial pays) and size, the combination of the best
  twelve picks (two a game at most), never two in one slip from the same game, that grows a bankroll fastest at
  full Kelly, when its expected value is positive. Each shows its expected value, the chance it pays more than the
  entry, and a quarter-Kelly stake for that slip alone (the slips share picks: one, not all).
- **Payouts**: PrizePicks' standard table, Power 3×, 5×, 10×, 20×, 37.5× for two to six picks; Flex 2.25× and
  1.25× for three, 5× and 1.5× for four, 10×, 2× and 0.4× for five, 25×, 2× and 0.4× for six. The break-even hit
  rate per pick runs from 54.2% (six-pick Flex) to 59.1% (three-pick Flex). Some states pay differently: confirm
  in the app and change `PAYOUTS`. Each logged slip keeps the table it was priced on.
- **Record** (sealed, `tracking/owner_pickem/` for picks and `tracking/owner_slips/` for slips): the day's picks
  from 54% and its slips, logged once at the first run from 10:00 ET, like the parlays. Each pick's fair
  probability at its logged line is followed until kickoff (did the books move toward it?), and graded from ESPN's
  box score once the game is final, both sports keyed by ESPN's event id. A player missing from the box score is
  void, as PrizePicks voids a player who does not play. A slip settles on its picks: ties and voids drop out and
  the entry pays as the next size down (a Flex left with two pays as a two-pick Power; one left is refunded).
- The tab is three cards: **Slips for the day**, the **Pick board** (the best ten picks, the rest folded) and the
  **Pick'em record** once picks are logged. The run's log carries counts only, never a line or a price: the props
  and the slate games they came back on, then the PrizePicks lines, More-only and unpriced lines, picks, and slips
  by entry. It says so when the sixteen-page cap cut the latest games.

It does not enter anything. Same-game correlations, where pick'em is most often beaten, are not modelled, so a
slip never holds two picks from one game.

