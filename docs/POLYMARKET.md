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
   (`/v1/markets/{slug}/book`, the shares at the best ask alone; `/bbo`'s
   share counts are the whole side summed) only for the contracts that
   clear the rest of the rule, up to forty a run (`positions.deepen`).
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
cents, at that ask plus the fee, and - from 24 October 2026 - only on a
book quoted inside 4¢ bid to ask, the model rule's own bar, since the
venue's tape showed a wider ask to be an empty book rather than a price
and the source of most of the rule's losses (the backtest below);
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

### The loop off the scheduled runs

The scheduled run reads the venue every fifteen minutes and takes three to
five minutes to start, and the rule's live orders go late in games, when a
limit sent that late fills nothing. So from 24 October 2026 the rule can run
as an always-on loop instead
(`atlas/polymarket/worker.py`, `make polymarket-worker`): every 45 seconds
while a game is in play (every three minutes while none is) it reads the
five leagues' listings (the four Atlas models and, from November, college
basketball) - about ten requests, fifty games a page, each game with its moneyline's top
of book and the venue's own period and clock - takes the crossings, grades
the settled ones, writes `tracking/favorites.csv`, hands the new positions
to the live step (late ones only unless `LIVE_PHASE` is `any`), grades the
live ledger, and commits and pushes what changed. The late flag comes from
the venue's clock, read seconds before the order rather than a poll before.

It runs on any machine that stays up, from a clone it may push to. On a
fresh Ubuntu server (a five-dollar virtual machine in a US region does),
`deploy/setup-worker.sh` does the whole setup: it installs git and Python,
makes an `atlas` user and a deploy key and waits while the key is added on
GitHub with write access, clones `main` into `/srv/atlas`, installs the
package, and puts the systemd unit (`deploy/favorites-worker.service`) and
the environment file (`deploy/favorites-worker.env.example`, which is the
scheduled run's secrets less the ingest keys) in place; `start` runs one
tick from that file and starts the service, and `update` pulls new code and
restarts it:

```bash
curl -fsSL https://raw.githubusercontent.com/EdgeCash/Atlas/main/deploy/setup-worker.sh | sudo bash
sudo nano /etc/atlas/favorites-worker.env
sudo bash /srv/atlas/deploy/setup-worker.sh start
```
 Set the repository variable
`FAVORITES_TAKER` to `worker` once it is up: the scheduled run then reads
the record the worker pushed and takes, grades and orders nothing for this
rule itself, so the two never write it at once. The worker's
`ATLAS_OWNER_KEY` must be the repository secret's own: a ledger week file
sealed with another key cannot be opened by the scheduled run, which then
leaves the file as it is, grades nothing of the ledger, and says so on the
Live tab instead of failing the page. The scheduled run still
logs the model's positions and places their orders; the worker's
`LIVE_RULES` is `favorites`. Run exactly one worker: two would take every
position twice.

### The rule on the venue's own tape

The same question can be asked of every game the venue has already settled
(`atlas/polymarket/backtest.py`, `make polymarket-backtest`). The gateway
lists its closed events back to November 2025 - the NBA, the NHL, the NFL,
college football and college basketball among them - each with its teams,
its start, when it finished and the moneyline's settled price per side; and
its price history at a one-minute fidelity carries each side's ask for
every minute the market was open, which is the price the rule buys at. The
backtest replays the rule on that tape: for each side of each game, before
the start and in play, a position at the first minute its ask reached each
threshold, at that ask plus the fee, graded by the settled price, and
summed the way the live record is - by league, by threshold, and by how
many minutes of the game were left. It also fills each position as a slow
poller would, a limit at the ask it saw sent one, five or fifteen minutes
late, which fills only when the ask has not risen since: the adverse
selection of a scheduled loop, measured. The report is
[`reports/favorites_backtest.md`](../reports/favorites_backtest.md), its
tables `reports/tables/favorites_backtest_*.csv`; the tape is cached under
`data/raw/polymarket_us/` so a rerun costs only the new games. The live
record is the out-of-sample continuation of it.

**A correction, 24 October 2026.** The first version of that report put
"late" at fewer than fifteen minutes to the game's recorded finish, which
is not known while the game is on. Games that run long are
disproportionately the close ones the favorite loses, and that measure
moved their final minutes out of the late buckets: it showed a late edge
of one to four points that, with late defined as it can be known during
the game (elapsed time against the league's median length), is not there.
A late favorite on a tight book has lost about a point against its cost,
or broken even; an earlier one has lost more. No threshold shows an edge. The report now leads with the knowable
definition.

### Standing orders late in games

The exchange lets a bid rest in the book instead of taking the ask, so the
other way to buy a late favorite is a bid a few cents under the market,
filled only if the price dips. That was tested on the same tape
(`atlas/polymarket/standing.py`, `make polymarket-standing`), with the rule
and its pass criteria fixed first in
[`STANDING_ORDER_PREREGISTRATION.md`](STANDING_ORDER_PREREGISTRATION.md).
It failed: every one of the 72 variants lost money, by four to ten points,
in both halves of the season. A late favorite's price dips when its
chance has fallen, and by more than the dip; a resting bid fills on
exactly those minutes. The report is
[`reports/standing_order_backtest.md`](../reports/standing_order_backtest.md).

## The finish-line rule

The one trade the edge survey (`reports/Polymarket US worker edge
survey.md`) measured as positive on this venue: when a game is over, its
winner's contract will pay a dollar, but the venue settles some minutes
later, and until then some holders sell it for 98 or 99 cents. The tape
showed such an ask after the recorded finish in 43% of 8,016 settled games,
and the loser priced as the winner after the finish in 4 of 9,273. At those
prices the taker fee is a tenth of a cent, so the cent or two left is a
real, small edge, and one loss erases fifty to a hundred wins.

The worker runs it every tick (`atlas/polymarket/finish.py`). A game is
over when the venue says so: the event's `ended` flag or a full-time
period (`FT`); end of regulation (`End P3`, `End Q4`) is not, since a tied
game goes on. The rule takes a paper position on the side whose ask sits
between 90 and 99 cents, once per contract, at that ask plus the fee, with
the shares resting at the ask read from the book and the minutes since the
venue's recorded finish. Every tick reads the settlement of the open
positions, so the record (`tracking/finish.csv`, in the clear) carries the
payout, the profit and the minutes from position to settlement - the
capital lock the research could not measure. The worker keeps its
45-second pace while any game is over but unsettled. The owner page's
Finish line tab sums the record by sport and by price band.

Only a position the market calls decided - the ask at or under 99 cents
and the bid at or over 98 - goes to the live step, as rule `finish`, and
only when `LIVE_RULES` names it (`favorites,finish`); it is never on by
default. With the live mode at `dry` that writes a previewed order to the
ledger and sends nothing.

## The gold and silver 15-minute rule, in practice

From 26 October 2026, the worker also runs a practice rule on Polymarket
US's gold and silver Up/Down markets (`atlas/polymarket/metals.py`). A new
window opens every fifteen minutes; Up settles to a dollar when the
Chainlink spot price at its end is at or above the price at its start (one
value each), read about a minute after the end. The category survey
(`reports/Polymarket US category survey.md`) found these books priced to a
simple model in the middle of a window, and one place they lag: in the last
few minutes, the side the spot price has all but decided is sometimes still
offered at 91-97 cents. On one trading day of the venue's history that paid
+0.8 to +2.9 cents a contract after the fee; one live sample lost.

The rule is the test of that, on paper only: nothing is ordered, and the
live step does not know it. Between its own ticks the worker wakes for each
window's last five minutes and reads every ten seconds: the commodities
listing (`/v2/tags/commodities/events`, not edge-cached) for the window's
price to beat and top of book, and the venue's own Chainlink feed
(`/v1/asset-prices/history`, not edge-cached) for the spot price and an
hour of five-second candles. A driftless lognormal on those gives the
chance the window ends Up. Where it puts a side at or above 0.95, 0.97 or
0.99, the side is offered at or under 0.97, and the chance beats the ask
and the fee by more than a cent, it takes a paper position at that ask,
once per side and threshold per window, with the shares the market's full
book holds there. That one book read carries a unique query: the edge
cache otherwise serves a 30-second-old book, or the "not found" it cached
before the window's market existed. A minute after the window, the venue's
settlement grades it. The listing's top of book is sometimes a price the
book no longer holds (in the first practice window, three of six positions
had no shares behind the quoted ask), so a position whose fresh book holds
nothing at or under its ask is marked unfillable: kept in the record and
left out of its totals, which count only trades that could have happened.

The record is `tracking/metals.csv`, in the clear; the owner page's
Metals 15m tab shows it by threshold and by metal, with what $1 orders
would have made (a dollar at 93 cents or more pays no fee, since the venue
rounds a fee under half a cent to nothing). Set `METALS_RULE=off` in the
worker's environment to stop it. A loss at 0.95 costs about twenty wins, so
the record needs a few hundred settled windows before its edge means
anything; trading it for real would also need the authenticated WebSocket,
since a REST read of the book is up to 30 seconds old.

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
(`favorites`, `model`, or both, the default), and the favorites' orders go
only on games in their final regulation period or past it - as the venue's
clock stood when the worker took the position, or the scoreboard's at the
poll - unless `LIVE_PHASE` is set to `any`. The caps, the stop and the floor are
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
arming secret to the phrase, and the bankroll.

Two more controls answer the venue's Rulebook (5.2(i) asks an automated
system for "order throttles, price collars, and kill switches"). The
**throttle** refuses an order once the run's mode has sent five in the last
minute or fifty in the last day (`MAX_ORDERS_PER_MINUTE`,
`MAX_ORDERS_PER_DAY`). The **kill switch** stops everything at once: every
position is refused and nothing at all is sent to the venue, not even the
balance read. Three ways to throw it:

- **From anywhere, no restart:** commit a file named `KILL` to
  `tracking/polymarket_live/` on the branch (GitHub's "Add file" on a phone
  will do; its first line is the reason, shown on the owner page). The
  worker reads the branch's copy every tick, so it holds within one tick
  (45 seconds in play); the scheduled run holds at its next checkout.
  Delete the file on the branch to lift it.
- **On the worker's machine:** `touch /srv/atlas/tracking/polymarket_live/KILL`.
  It holds at once, and the worker pushes it to the branch with the ledger,
  so lifting it is the same: delete it on the branch.
- **By variable:** set `POLYMARKET_US_KILL` to anything (the repository
  variable for the scheduled run; the worker's environment file, then a
  restart, for the worker).

The price collar is the order itself: a limit at the ask the position was
taken at, never a market order.

Underneath the ledger is the **audit trail** the Rulebook's 5.2(h) asks
for - "order entry, modification, cancellation, and execution timestamps
sufficient to reconstruct all trading activity"
(`atlas/polymarket/audit.py`, sealed with the owner key in
`tracking/polymarket_audit/`, a file per ISO week). Every call the step
makes to the venue is an event stamped to the millisecond in UTC: the
balance read and what it said; each order's (or, dry, each preview's)
exact request as it was sent; and the venue's answer in full - the order
id, the executions with their prices, quantities and the venue's own
timestamps, the commission and the state, or the error with its HTTP
status and the body the venue sent - with the time it came back and the
latency. A submit and its answer share a request id. Every position
declined before the venue is an event too, with why (the kill switch, the
throttle, a cap, the stop, the floor, not armed) and the order it would
have been. A live order's submit is written to disk before the order is
sent, and an order whose submit cannot be written is not sent. Orders are
immediate-or-cancel, so nothing rests to be modified or cancelled: the
venue cancels what does not fill at once, and its answer says so. The
trail only grows; the worker and the scheduled run merge their copies by
event.

Once a day, from 6 AM Eastern, the trail is **reconciled** against the
venue's own account history (`atlas/polymarket/reconcile.py`,
`GET /v1/portfolio/activities`): every trade on the account in the previous
Eastern day is matched by its trade id to an execution the trail recorded,
and their quantity and price compared. What does not reconcile is named: a
trade whose figures differ, a trade on the account the trail never recorded
(one made by hand in the app, or a lost answer), a fill the trail recorded
that the venue does not show, and a trade the venue busted or rejected
after the fact. The same read checks the ledger's grades: each settlement
the venue made of the account's positions that day is set beside the
ledger's filled orders on that market - the contracts held going in, and
the payout per contract (the realized profit the settlement added plus the
position's cost, over its contracts) against the payout the ledger graded -
and it names a settlement that differs, a market the venue settled that the
ledger has not graded, a market the ledger graded that the account shows no
settlement of (read three days back, since the ledger grades after the
venue settles), and a settlement of a position the ledger does not hold (one
bought by hand). The result is an event in the trail, and the owner page's
Live tab states the latest ("everything agrees", or MISMATCH and what). A
read that fails is recorded and tried again an hour later. The worker runs
it, and the scheduled run as a backstop; `python -m atlas.polymarket.reconcile`
runs it by hand (`--day YYYY-MM-DD` for any day, printed only).

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
price, from `/v1/markets/{slug}/book`) fills at that price for the size
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
