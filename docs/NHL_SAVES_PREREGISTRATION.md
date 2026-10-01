# NHL goalie saves: pre-registration of the test against PrizePicks' lines

Frozen 1 October 2026, before the first NHL line of 2026-27 was logged.
Code: `atlas/owner/ledger.py`. Record: `tracking/owner_prop_ledger/`
(sealed). Shown on the owner page's Pick'em tab, inside the ciphertext.

## The question

Atlas's player projections (`atlas/models/nhl_props.py`) beat a Poisson on
the goalie's season mean by about ten percent of Brier at every common saves
line, walk-forward 2022-26 (`reports/nhl_props.md`: 0.228 against 0.251 at
24.5). That is a baseline that knows nothing. PrizePicks' line knows the
matchup and the expected starter, and the books' prices around it know more.
There is no history of either, and BettingPros serves only the current line,
so the test can only run forward. This fixes how it will be read.

## What is logged

Every run from 10:00 ET, the pick'em prices every PrizePicks standard NHL
line on the slate (More and Less both offered) on the books' props. The
ledger logs **every one of them**, once a day at the first run from 10:00
ET, pick or not, with:

- the line, and the books' fair probability of the likelier side (the median
  of the books quoting, moved to PrizePicks' line; two books at least);
- Atlas's probability of the same side, where the heavy refresh's sealed
  snapshot has the player on the team BettingPros lists him on;
- the actual from ESPN's box score once the game is final (a goalie who did
  not go in is void; a whole-number tie is a push; both are dropped from the
  scores).

The picks' own record stays as it is; the ledger adds the lines the picks
leave out, which are the lines PrizePicks set well.

## How it is scored

Per stat, on the decided lines, three forecasts of the same side on the same
lines: the books' fair probability, Atlas's, and 0.50 (the line as PrizePicks
set it, Brier 0.25, log loss 0.693). Brier and log loss of each; the paired
Brier difference Atlas minus fair with a normal 95% interval; and the hit
rate of fair's side and of Atlas's side (the logged side where Atlas gives it
50% or more, else the other).

## The saves verdict

Judged at **300 decided goalie lines with an Atlas probability** and not
before (PrizePicks posts saves on most starters, so about a month of the
season). Then:

- **Clears** when all three hold: Atlas's Brier below fair's with the paired
  95% interval entirely below zero; Atlas's Brier below 0.25; and Atlas's
  side hitting 57.7% or better, PrizePicks' two-pick Power break-even.
- **Fails** when Atlas's Brier is not below fair's at 300 (the interval
  reaches zero), or is not below 0.25 at 500.
- **Not proven** otherwise, judged again at 500.

Clearing means Atlas's saves number is worth a pick'em rule, to be written
and frozen as its own pre-registration then. It does not mean a slip is
profitable: PrizePicks pays by slip, and same-game correlation is not
modelled.

## What the walk-forward predicts, and what would surprise

The walk-forward's Brier at the common lines was 0.21 to 0.23. Against the
books' fair probability, which already prices the matchup, the honest
expectation is a Brier within 0.005 of fair's either way, and no verdict
either way is a surprise. A clear win over fair would say the goalie state
carries something the books do not price by 10:00 ET; a clear loss would
say the books' line already holds everything the model knows.

The other stats are scored the same way and shown beside saves, with no
verdict registered: they had small edges over the baseline and no claim is
made for them. A rule on any of them would need its own pre-registration.

## What is not tested

Whether Atlas beats PrizePicks' line at the moment a slip is placed (the
ledger logs at 10:00 ET and PrizePicks moves lines through the day), and
whether the books' fair probability itself beats the coin flip (shown, not
judged). Nothing is entered.
