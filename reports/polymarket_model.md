# Atlas on Polymarket US

*Rebuilt every run; this one at 2026-10-29 04:23 UTC.*

Polymarket US, the CFTC-regulated exchange, is the one venue Atlas is priced
against. It lists a moneyline, a ladder of spreads and a ladder of totals on
every NFL, NBA, NHL and college football game as dollar contracts on a
central order book, and its prices are public: every run reads them from the
exchange's own API, matches each game to the one Atlas projects, and keeps
every quote, timestamped, in `tracking/polymarket_quotes.csv`. That table is
the point-in-time archive of the market Atlas is measured against.

## Coverage this run

| Sport | Games ahead | On Polymarket US | Contracts | Median spread (main lines) | Median depth (where read) | Fee coefficient |
|---|---|---|---|---|---|---|
| NCAAF | 61 | 49 | 6556 | 2.0¢ | – | 0.0695 |
| NFL | 15 | 1 | 142 | 0.5¢ | – | 0.0695 |
| NBA | 67 | 19 | 444 | 1.0¢ | – | 0.0695 |
| NHL | 63 | 25 | 750 | 2.0¢ | – | 0.0695 |

Spread is the gap between the best bid and the best ask on the contracts
priced near even; depth is the dollars resting at the best ask, read from
the book for the contracts that cleared the rest of the rule. The fee is the
exchange's taker fee, `coefficient × price × (1 − price)` per contract, the
coefficient read from each market.

## How Atlas is anchored to the market

Atlas's number for a game is never used raw. The market's centre for the
margin and the total is read off its own ladder of lines; Atlas's projection
is pulled toward it by the share of Atlas's disagreement that has turned out
real on the walk-forward record (`tracking/calibration.csv`), and every line
on the ladder is then priced from that one anchored centre. A share of 0%
means the record says Atlas adds nothing to the market there, and Atlas is
priced as the market.

| Sport | Market | Share of Atlas's disagreement taken | Games on the record |
|---|---|---|---|
| NCAAF | moneyline | 0% | 3661 |
| NCAAF | spread | 0% | 3661 |
| NCAAF | total | the record's hit rate by gap | 3683 |
| NFL | moneyline | 0% | 1683 |
| NFL | spread | 0% | 1683 |
| NFL | total | the record's hit rate by gap | 1706 |
| NBA | moneyline | 4% | 12318 |
| NBA | spread | 4% | 12318 |
| NBA | total | the record's hit rate by gap | 12366 |
| NHL | moneyline | 49% | 11151 |
| NHL | spread | 49% | 11151 |
| NHL | total | 49% | 11151 |

On football totals the record is read as a curve: the hit rate of Atlas's
side at disagreements this large or larger, never below one half.

## How far the anchored number sits from the market

| Sport | Market | Games | Atlas, median gap | Atlas, largest gap | Anchored, median gap |
|---|---|---|---|---|---|
| NBA | margin | 19 | 1.0 | 6.6 | 0.04 |
| NBA | total | 3 | 3.1 | 3.5 | 0.37 |
| NCAAF | margin | 49 | 1.9 | 8.8 | 0.00 |
| NCAAF | total | 49 | 2.1 | 10.8 | 0.83 |
| NFL | margin | 1 | 0.0 | 0.0 | 0.00 |
| NFL | total | 1 | 2.3 | 2.3 | 0.01 |

In points of margin or total, per game: Atlas's own projection against
the market's centre, and the anchored number the contracts are priced from.
On a market where the share is zero the anchored gap is zero by
construction.

## Player props

Player props this run: NHL (points, goals, assists): 567 contracts on 12 games, 567 with an Atlas projection beside them, 2516 graded so far; NFL (yards, receptions, touchdowns, attempts, completions, carries): 287 contracts on 1 games, 287 with an Atlas projection beside them, 1870 graded so far. Atlas's numbers are `atlas/models/nba_props.py` (`reports/nba_props.md`) and `atlas/models/nhl_props.py` (`reports/nhl_props.md`). Each player-stat's main line is kept in `tracking/polymarket_props.csv` with Atlas's probability as it stood, and graded against the box score and the close into `tracking/prop_record.csv`, the record that decides, a sport at a time, what Atlas's disagreement is worth there.

## The favorites rule

A second paper rule beside Atlas's, with no projection in it
(`atlas/polymarket/favorites.py`): a position on every moneyline the first
time its ask reaches 80, 85, 90 and 95 cents, in play or before the game,
at that ask plus the fee - and, from 24 October 2026, only on a book quoted
inside 4¢ bid to ask, since the venue's own tape showed a wider ask to be
an empty book rather than a price ([`favorites_backtest.md`](favorites_backtest.md)) -
graded by the venue's settlement and kept in `tracking/favorites.csv`. The
question is whether the venue's favorites win more often than they cost.
Edge is the win rate less the break-even rate, in points, with one standard
error.

| Phase | Threshold | Taken | Graded | Win rate | Break-even | Edge (pts) | Profit per $ |
|---|---|---|---|---|---|---|---|
| in play | 80% | 173 | 168 | 83.9% | 84.6% | -0.7 ± 2.8 | -0.8% |
| in play | 85% | 179 | 174 | 89.1% | 89.1% | -0.0 ± 2.4 | -0.0% |
| in play | 90% | 167 | 161 | 91.9% | 92.8% | -0.8 ± 2.1 | -0.9% |
| in play | 95% | 149 | 145 | 95.2% | 96.2% | -1.0 ± 1.8 | -1.0% |
| pregame | 80% | 128 | 49 | 87.8% | 85.3% | +2.4 ± 4.7 | 2.8% |
| pregame | 85% | 73 | 22 | 95.5% | 89.4% | +6.1 ± 4.4 | 6.8% |
| pregame | 90% | 43 | 12 | 100.0% | 92.6% | +7.4 | 8.0% |
| pregame | 95% | 12 | 1 | 100.0% | 97.2% | +2.8 | 2.9% |

## The record

Paper positions are taken by a fixed rule, logged once and graded on the
result and against the venue's close. That record is the owner's, sealed
in `tracking/polymarket_positions/`, and is not published here. Nothing on
this page is a recommendation.
