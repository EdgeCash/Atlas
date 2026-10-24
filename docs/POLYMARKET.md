# Atlas on Polymarket US

From 23 October 2026. Polymarket US is the one venue Atlas is priced
against: every sportsbook, the pick'em sites, daily fantasy and the other
prediction exchange were retired on 22 October (the sealed records they left
are kept under `tracking/owner_*` and are not read), and the global
Polymarket, read for one day, gave way to the US exchange on the 23rd (its
day's record is kept as `tracking/polymarket_global_*.csv` and is not read).
Code: `atlas/polymarket/`; the owner page's box: `atlas/owner/page.py`; the
public page about the model:
[`reports/polymarket_model.md`](../reports/polymarket_model.md).

## Why Polymarket US

Polymarket US (`polymarket.us`) is the CFTC-regulated exchange: dollar
contracts on a central order book, one instrument per market, bought at the
ask as Yes or sold as No at one less the bid, and the one an account in the
United States trades. Three things no sportsbook offered, and all three were
gaps the research named:

- **The market is public and keyed to nothing.** The exchange's public
  gateway (`gateway.polymarket.us`) lists every game, every market on it
  and the top of each book without a key, so the market Atlas is measured
  against can be captured, timestamped and committed in the clear. Phase 4
  found that "Atlas holds no timestamped odds, so the optimal execution
  window cannot be measured at all"; `tracking/polymarket_quotes.csv` is
  that archive.
- **The price is the whole price.** A contract costs its ask plus a taker
  fee the market itself declares (`feeCoefficient`, 0.0695 on every market
  on 23 October: `0.0695 × price × (1 − price)` a contract), and pays one
  dollar. There is no margin to strip and no "best book" to hunt: the
  question is only whether Atlas's probability clears the ask and the fee.
- **A ladder, not a line.** Each game carries a moneyline, a ladder of
  spreads and a ladder of totals. Atlas's projection is a distribution, and
  a ladder is what a distribution prices.

## What runs

Every run, heavy or poll (`python -m atlas.polymarket refresh`):

1. **Capture** (`source.py`, `match.py`). Every NFL, NBA, NHL and college
   football game from six hours ago to three days ahead is read in full
   from the gateway (the league's listing, then each game by its slug); the
   full-game markets (moneyline, spreads, totals) are parsed to one row per
   contract, the long side and the short, with the market's slug as its
   handle on the API. Each
   event is matched to the Atlas game it is - same sport, starts within
   three hours, each short name contained in ESPN's full name on the same
   side; a game that would match only with the sides swapped is left
   unmatched, since a swapped match inverts every spread. The matched
   games' main lines (the moneyline, and the spread and the total the market
   prices nearest to even, both sides of each) are folded into
   `tracking/polymarket_quotes.csv` append-on-change, with the time first
   and last seen. The rest of the ladder is read and priced, not kept. The
   gateway's game feed carries the top of each book but not what rests
   there, so the depth of a contract is read from its book
   (`/v1/markets/{slug}/bbo`) only for the contracts that clear the rest of
   the rule, up to forty a run (`positions.deepen`).
2. **Price** (`pricing.py`). For every contract, three probabilities:
   Polymarket's own (the two outcomes' midpoints normalised to one);
   Atlas's raw reading of the line (the fitted market shape centred on the
   projection; the NHL grid's probability); and the fair probability a
   position is taken on. Football is anchored in centre space: Polymarket's
   centre for the margin and the total is read off its own ladder, and the
   anchored centre every line is priced from is where the walk-forward
   record puts it - on totals, the hit rate of Atlas's side at
   disagreements this large or larger, never below one half; on margins,
   the market pulled toward Atlas by the share of its disagreement the
   record says has been real, fitted by least squares through the market on
   `tracking/calibration.csv` and clipped to [0, 1]. The fair probability is
   the quote moved by what the anchoring moves the ladder at that line: with
   a share of zero, Atlas's probability is Polymarket's, and nothing clears
   the fee. Expected value is fair ÷ (ask + fee) − 1.
3. **Positions** (`positions.py`). A fixed rule: contracts Polymarket is
   accepting orders on, quoted inside 4¢ with at least $2,000 of depth, fair
   between 15% and 85%, priced in line with their own ladder; +2% or more
   after the fee; one a game at the contract that pays best, at most ten a
   day; a quarter of Kelly, capped at 2% of the bankroll each and 10% a day.
   The day's set is logged once, at the first run from 10:00 ET, at the
   prices shown then, into `tracking/polymarket_positions/` (sealed, one
   file per ISO week), and never revised.
4. **Grade.** On the exchange's own settlement where it has one
   (`/v1/markets/{slug}/settlement`: one or zero, or the last fair price
   where the market's rules settle so - a player who did not play, a game
   moved more than two days - which pays that price), else on the final
   score (a push refunded); and against the venue's close: the contract's
   last midpoint seen before the game started (the exchange's price
   history, `/v1/price-history`, stands in when the record has none), less
   the ask bought at. The record the share is fitted on stays on the box
   score, since it measures the model.
5. **Publish.** The owner page's box (`atlas/owner/page.py`: Positions for
   the day, the board, the record; then the paper tracker and the readers)
   sealed under `ATLAS_OWNER_KEY` into `data/owner/page.enc.json`, which the
   site serves at `owner/`; and `reports/polymarket_model.md`, the public
   page, which carries coverage, the anchoring and the distances and no
   position.

## Player props

The NBA, NHL and NFL games carry player markets too - "Will Name record at
least N points" (the NFL's "Will Name record 50+ receiving yards"), Yes and
No, a ladder of N for each stat - and the same run prices them
(`atlas/polymarket/props.py`): points, rebounds, assists, threes, steals,
blocks and the first three combined in the NBA; points, goals and assists
in the NHL; receiving yards, receptions,
rushing yards, passing yards, touchdowns, passing touchdowns, pass attempts,
completions, carries and scrimmage yards in the NFL.
"At least N" and "N+" are kept as the over at N − ½, so a record row reads
as a sportsbook's would.

- **Atlas's number** is minutes times a per-minute rate times the game
  (`atlas/models/nba_props.py`): exponentially weighted minutes and rates
  for the player, a prior of the position's rate for anyone new, and a
  game layer fitted each season on home court, the opponent's allowance
  and the pace, with a negative-binomial spread around the expectation.
  The heavy refresh writes every rostered player's state into
  `data/warehouse/nba_props_state.json`; a poll reads it. Walk-forward,
  Atlas's Brier beats a Poisson on the player's season mean at every stat
  and line (`reports/nba_props.md`). The NHL's number is ice time times a
  rate times the game (`atlas/models/nhl_props.py`, `docs/MODEL_PLAN_NHL.md`
  step 8), its snapshot written the same way into
  `data/warehouse/nhl_props_state.json`; the player is found on the team
  the venue lists him on, by the team's code from the game projection. The
  NFL's is his share of his team's pass or rush attempts times the team's
  attempts, times his rate per target, carry or attempt, times the game
  (`atlas/models/nfl_props.py`, `docs/MODEL_PLAN_NFL.md` step 9) - where
  the game's size is the total Atlas's own projection implies for his
  team, so a shootout the model expects is in his number; its snapshot is
  `data/warehouse/nfl_props_state.json`, and the team is read from the
  venue's ESPN id.
- **The injury report.** ESPN's NBA, NFL and NHL injuries feeds are read
  every run (`atlas/sources/nba_availability.py`), kept in
  `tracking/nba_availability.csv`, `tracking/nfl_availability.csv` and
  `tracking/nhl_availability.csv`, and applied before anything is priced: an
  NBA player listed Out is given a 3% chance of taking the court, a game-time
  decision 55% and nine tenths of his minutes, and the minutes a team is
  without go to its rotation; an NFL player listed Out 2%, Doubtful 10%,
  Questionable 75%, and on injured reserve or suspended none; an NHL skater
  listed Out 3%, Day-To-Day an even chance, and on injured reserve none. The
  chance of not playing goes to the market's
  own price, because the exchange's rules settle a player who does not take
  the field at the last fair market price (a venue that resolved him as No
  would send it to the under in full). Those numbers are stated, not fitted
  - there is no archive of reports to walk forward on, which is what the
  capture is building - and the board shows the status beside Atlas's
  number.
- **The record.** The main line of each player's stat (the one the market
  prices nearest to even) on a matched game is folded into
  `tracking/polymarket_props.csv` append-on-change, and graded against the
  box score into `tracking/prop_record.csv` once the game is final - a
  player who did not play is a push, in the record (which measures the rate
  model) and on a paper position (which the venue settles at the last
  price). The NHL's box score is the warehouse's skater games, whose game
  ids are the league's, mapped to Atlas's through the game projection.
- **The pricing** is the game markets' rule in probability space: fair is
  the market's probability pulled toward Atlas's by the share of Atlas's
  disagreement the sport's prop record has shown to be real, fitted through
  the market the same way and clipped to [0, 1]. The share starts at zero,
  because the record starts empty - so at first every prop is a projection
  beside the market and nothing clears the fee. That is deliberate: the
  props take positions only once their own graded record says the model's
  disagreement is worth something.
- **Positions**, when they come, follow the same rule as the games (the
  same spread, depth and probability gates, +2% after the fee, quarter
  Kelly, the same caps) with one position per player's stat and at most
  ten a day, logged once into `tracking/polymarket_prop_positions/`.

The owner page carries a Props tab - the day's prop positions, the board of
every priced contract on an upcoming game, and the record by Atlas's
confidence; the public report carries the coverage only.

## What the record said on day one

Fitted on the walk-forward record as it stood on 23 October 2026:

| Sport | Market | Share of Atlas's disagreement taken | Games |
|---|---|---|---|
| NCAAF | moneyline, spread | 0% | 3,661 |
| NCAAF | total | the record's hit rate by gap (about 51% at a small gap, 56% at ten points) | 3,683 |
| NFL | moneyline, spread | 1% | 1,669 |
| NFL | total | the curve, which the record holds at one half: the NFL total has not beaten the close | 1,692 |
| NBA | all three | what `reports/nba_state.md`'s record says, from the first heavy run after 23 October 2026 (`docs/MODEL_PLAN_NBA.md`) | 2012-13 to 2022-23 |
| NHL | all three | 0% | 11,111 |

So, as the research concluded, the only contracts the rule can take are
college totals, and only where the record says the size of Atlas's
disagreement has been worth something. Every other market is priced as the
market and declines by the fee. That is the model, not a bug: a share that
rises on the record will widen what the rule takes without a line of code
changing.

## The favorites rule

A second paper rule beside Atlas's, with no projection in it
(`atlas/polymarket/favorites.py`). The idea under test is the one that
looks obvious on the app: a side at 86% is going to win, so buy it and
collect the few cents. The price says otherwise - 86% is the market's
estimate of how often that side wins, and the contract costs 86 cents plus
the fee - so the question is only whether the venue's favorites win more
often than they cost, in play or before the game, in any sport, at any
threshold. Every run takes a paper position on each moneyline (the
favorite side of a game; a deep spread or total at 90 cents is the ladder's
edge, not a favorite) the first time its ask reaches 80, 85, 90 and 95
cents, at that ask plus the fee,
noting the phase and the minutes since kickoff; once the game is four hours
gone the venue's settlement grades it (at most forty reads a run). The
record is `tracking/favorites.csv`, in the clear, since it is a rule on
public prices rather than Atlas's own positions, each position carrying
the period and the clock the scoreboard had for the game at that poll and
whether that was the final period; the public report and the
owner page sum it by phase and threshold, and by sport: the win rate
against the break-even rate (the mean cost), with a standard error, and the
profit per dollar staked. Positive and several errors wide, over hundreds
of positions, before it means anything.

## Going live, armed off

The step that would place real orders exists and ships off
(`atlas/polymarket/orders.py`). It is the one module that can place an order,
and it will not until three things hold at once: the repository secret
`POLYMARKET_US_LIVE` says `live`, the secret `POLYMARKET_US_ARMED` carries
the exact phrase the module states, and the ledger's loss stop is not in
force. Without the mode secret the step does nothing; with it set to `dry`
it walks the whole path - the sizing, the caps, the stop, the venue's own
preview of the order - and writes what it would have sent to the ledger
without sending it.

What it orders is what the paper rule chose: as the day's positions are
logged, each becomes a limit order at the ask it was logged at,
immediate-or-cancel, for the stake's worth of contracts at the live
bankroll (`ATLAS_LIVE_BANKROLL`, dollars), sized down to the dollars-per-order
cap; never a market order, never a resting one. Each is checked against
the caps before it goes - $100 a day, $250 open across unsettled positions
- against the stop (when the orders settled over the trailing three days
have lost more than $50, nothing is placed until that window clears), and
against the floor: before a run places anything (a dry run too) it reads
the account's balance from the venue, cash plus the value of what it
holds, and places nothing while that is below half the bankroll or of the
highest balance it has read, whichever is more - the floor moves up with
the account, never down - or when the balance cannot be read at all. Two
rules feed the step, each order's row naming its rule: the model's
positions as they are logged once a day, and the favorites rule's
positions as they are taken every poll, at the 85-cent crossing only; the
repository variable `LIVE_RULES` names which of the two the step takes
(`favorites`, `model`, or both, the default), and `LIVE_PHASE` set to
`late` confines the favorites' orders to games in their final regulation
period or past it, as the scoreboard stood at the poll. The caps, the stop and the floor are
constants in the module, set for the owner as repository variables
(`MAX_ORDER_DOLLARS`, `MAX_DAY_DOLLARS`, `MAX_OPEN_DOLLARS`,
`LOSS_STOP_DOLLARS`, `BALANCE_FLOOR`), never widened by anything the venue
or the market says. A soft launch is the variables at `MAX_ORDER_DOLLARS=1`
with the bankroll set to the account's balance: every position becomes a
one-dollar order, and the floor stops the step at half. Every order, sent or
not, is a row in a ledger sealed with the owner key beside the positions
record (`tracking/polymarket_live/`), with the order id, the state, the
fill and fee, and later the settlement and the profit; the owner page's
Live tab sums it. To arm it for real: set the mode secret to `live`, the
arming secret to the phrase, and the bankroll; to stop at once, change the
mode secret.

The key is checked before anything else, and a bad one is written down
rather than crashing the step. `python -m atlas.polymarket.account` with
the two secrets in the environment says whether the key id is set, whether
the secret decodes to an Ed25519 key, and whether the venue accepts one
signed read of the account's balances - and prints nothing from the key
itself. The secret is read as the portal shows it, standard base64 of the
seed (the venue's own sample decodes it with `base64.b64decode` and takes
the first 32 bytes); pasted without its padding, in the URL-safe alphabet,
as hex, or as a PEM block it is read too. When it is none of those, every
order of the run is refused with the note `bad key: the secret key does
not decode to an Ed25519 key`, with the lengths it saw, on the Live tab
and in the log, and no preview is taken.

## Paper only

Nothing here buys anything. Before real money, confirm: that each market's
fee coefficient is what the API says and the taker tier the account sits
in; that the depth figure (the shares resting at the best ask times the
price, from `/v1/markets/{slug}/bbo`) fills at that price for the size
meant; and that the settlement rules the pricing assumes (a player who does
not play settled at the last fair price; a game moved more than two days
settled the same way) are the ones on each market's page.

The second of those is measured, where the venue key is set. As the day's
positions are logged, each is put to Polymarket US's order preview
(`atlas/polymarket/account.py`): a limit at the ask it was logged at for
the stake's worth of contracts at a nominal bankroll (`ATLAS_PREVIEW_BANKROLL`,
$1,000 by default), immediate-or-cancel, so the venue says what the book
would fill at that price right then - the average price, the contracts
filled and left, the commission - without entering anything. The answer
goes into the sealed record beside the paper price, and the owner page
sums the day: how many would fill in full at the ask, the mean fill
against it, the fees. That module can reach the preview path only, and a
test holds it to that. The key is two repository secrets, the key id and
the secret key from polymarket.us/developer (`POLYMARKET_US_KEY_ID`,
`POLYMARKET_US_SECRET`); without them the step does nothing.
