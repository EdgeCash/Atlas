# Atlas on Polymarket

From 23 October 2026. Polymarket is the one venue Atlas is priced against:
every sportsbook, the pick'em sites, daily fantasy and the other prediction
exchange were retired that day (the sealed records they left are kept under
`tracking/owner_*` and are not read). Code: `atlas/polymarket/`; the owner
page's box: `atlas/owner/page.py`; the public page about the model:
[`reports/polymarket_model.md`](../reports/polymarket_model.md).

## Why Polymarket

Three things no sportsbook offered, and all three were gaps the research
named:

- **The market is public and keyed to nothing.** Polymarket's Gamma and
  CLOB APIs list every game market and its order book without a key, so the
  market Atlas is measured against can be captured, timestamped and
  committed in the clear. Phase 4 found that "Atlas holds no timestamped
  odds, so the optimal execution window cannot be measured at all";
  `tracking/polymarket_quotes.csv` is that archive.
- **The price is the whole price.** A contract costs its ask plus a taker
  fee the market itself declares (`feeSchedule`), and pays one dollar. There
  is no margin to strip and no "best book" to hunt: the question is only
  whether Atlas's probability clears the ask and the fee.
- **A ladder, not a line.** Each game carries a moneyline, a ladder of
  spreads and a ladder of totals. Atlas's projection is a distribution, and
  a ladder is what a distribution prices.

## What runs

Every run, heavy or poll (`python -m atlas.polymarket refresh`):

1. **Capture** (`source.py`, `match.py`). Every open event of the NFL, NBA,
   NHL and college football series is read from Gamma; the game markets
   (moneyline, spreads, totals) are parsed to one row per contract. Each
   event is matched to the Atlas game it is - same sport, starts within
   three hours, each short name contained in ESPN's full name on the same
   side; a game that would match only with the sides swapped is left
   unmatched, since a swapped match inverts every spread. The matched
   games' main lines (the moneyline, and the spread and the total the market
   prices nearest to even, both sides of each) are folded into
   `tracking/polymarket_quotes.csv` append-on-change, with the time first
   and last seen. The rest of the ladder is read and priced, not kept.
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
4. **Grade.** On the final score (a push refunded) and against Polymarket's
   close: the contract's last midpoint seen before the game started (the
   venue's own price history stands in when the record has none), less the
   ask bought at.
5. **Publish.** The owner page's box (`atlas/owner/page.py`: Positions for
   the day, the board, the record; then the paper tracker and the readers)
   sealed under `ATLAS_OWNER_KEY` into `data/owner/page.enc.json`, which the
   site serves at `owner/`; and `reports/polymarket_model.md`, the public
   page, which carries coverage, the anchoring and the distances and no
   position.

## Player props

The NBA events carry player markets too - "Name: Points O/U 24.5", Yes the
over and No the under, a ladder of lines for each stat - and the same run
prices them (`atlas/polymarket/props.py`), for points, rebounds, assists
and threes.

- **Atlas's number** is minutes times a per-minute rate times the game
  (`atlas/models/nba_props.py`): exponentially weighted minutes and rates
  for the player, a prior of the position's rate for anyone new, and a
  game layer fitted each season on home court, the opponent's allowance
  and the pace, with a negative-binomial spread around the expectation.
  The heavy refresh writes every rostered player's state into
  `data/warehouse/nba_props_state.json`; a poll reads it. Walk-forward,
  Atlas's Brier beats a Poisson on the player's season mean at every stat
  and line (`reports/nba_props.md`).
- **The record.** The main line of each player's stat (the one the market
  prices nearest to even) on a matched game is folded into
  `tracking/polymarket_props.csv` append-on-change, and graded against the
  box score into `tracking/prop_record.csv` once the game is final - a
  player who did not play is a push.
- **The pricing** is the game markets' rule in probability space: fair is
  Polymarket's probability pulled toward Atlas's by the share of Atlas's
  disagreement the prop record has shown to be real, fitted through the
  market the same way and clipped to [0, 1]. The share starts at zero,
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

## Paper only

Nothing here buys anything. Before real money, confirm: that each market's
fee schedule is what the API says; that the depth figure (the market's
resting dollars) is depth at the ask, which `source.book` reads from the
order book for a contract about to be bought; and that an account can trade
the global Polymarket at all from where it is.
