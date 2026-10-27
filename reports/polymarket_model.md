# Atlas on Polymarket US

*Rebuilt every run; this one at 2026-10-27 04:37 UTC.*

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
| NCAAF | 58 | 5 | 670 | 1.5¢ | – | 0.0695 |
| NFL | 15 | 1 | 142 | 1.0¢ | – | 0.0695 |
| NBA | 64 | 18 | 676 | 2.0¢ | – | 0.0695 |
| NHL | 62 | 26 | 780 | 2.0¢ | – | 0.0695 |

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
| NFL | moneyline | 1% | 1682 |
| NFL | spread | 1% | 1682 |
| NFL | total | the record's hit rate by gap | 1705 |
| NBA | moneyline | 4% | 12318 |
| NBA | spread | 4% | 12318 |
| NBA | total | the record's hit rate by gap | 12366 |
| NHL | moneyline | 49% | 11137 |
| NHL | spread | 49% | 11137 |
| NHL | total | 49% | 11137 |

On football totals the record is read as a curve: the hit rate of Atlas's
side at disagreements this large or larger, never below one half.

## How far the anchored number sits from the market

| Sport | Market | Games | Atlas, median gap | Atlas, largest gap | Anchored, median gap |
|---|---|---|---|---|---|
| NBA | margin | 18 | 1.4 | 6.3 | 0.05 |
| NBA | total | 5 | 3.1 | 9.3 | 0.39 |
| NCAAF | margin | 5 | 1.0 | 4.7 | 0.00 |
| NCAAF | total | 5 | 2.6 | 5.1 | 0.56 |
| NFL | margin | 1 | 0.4 | 0.4 | 0.00 |
| NFL | total | 1 | 2.7 | 2.7 | 0.45 |

In points of margin or total, per game: Atlas's own projection against
the market's centre, and the anchored number the contracts are priced from.
On a market where the share is zero the anchored gap is zero by
construction.

## Player props

Player props this run: NBA (points, rebounds, assists, threes, steals, blocks, the three combined): 376 contracts on 3 games, 376 with an Atlas projection beside them, 2643 graded so far; NHL (points, goals, assists): 863 contracts on 11 games, 863 with an Atlas projection beside them, 1410 graded so far; NFL (yards, receptions, touchdowns, attempts, completions, carries): 270 contracts on 1 games, 270 with an Atlas projection beside them, 1711 graded so far. Atlas's numbers are `atlas/models/nba_props.py` (`reports/nba_props.md`) and `atlas/models/nhl_props.py` (`reports/nhl_props.md`). Each player-stat's main line is kept in `tracking/polymarket_props.csv` with Atlas's probability as it stood, and graded against the box score and the close into `tracking/prop_record.csv`, the record that decides, a sport at a time, what Atlas's disagreement is worth there.

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
| in play | 80% | 140 | 137 | 83.9% | 85.1% | -1.1 ± 3.1 | -1.3% |
| in play | 85% | 146 | 143 | 88.8% | 89.3% | -0.5 ± 2.6 | -0.6% |
| in play | 90% | 133 | 130 | 91.5% | 92.9% | -1.4 ± 2.4 | -1.5% |
| in play | 95% | 118 | 117 | 94.9% | 96.2% | -1.3 ± 2.0 | -1.4% |
| pregame | 80% | 111 | 44 | 88.6% | 85.7% | +2.9 ± 4.8 | 3.4% |
| pregame | 85% | 67 | 20 | 95.0% | 89.7% | +5.3 ± 4.9 | 5.9% |
| pregame | 90% | 38 | 11 | 100.0% | 92.7% | +7.3 | 7.8% |
| pregame | 95% | 10 | 1 | 100.0% | 97.2% | +2.8 | 2.9% |

## The record

Paper positions are taken by a fixed rule, logged once and graded on the
result and against the venue's close. That record is the owner's, sealed
in `tracking/polymarket_positions/`, and is not published here. Nothing on
this page is a recommendation.
