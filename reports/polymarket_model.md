# Atlas on Polymarket US

*Rebuilt every run; this one at 2026-10-24 21:22 UTC.*

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
| NCAAF | 100 | 30 | 4020 | 1.0¢ | – | 0.0695 |
| NFL | 14 | 13 | 1846 | 0.5¢ | – | 0.0695 |
| NBA | 60 | 22 | 1756 | 1.0¢ | – | 0.0695 |
| NHL | 59 | 19 | 570 | 1.0¢ | – | 0.0695 |

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
| NFL | moneyline | 1% | 1670 |
| NFL | spread | 1% | 1670 |
| NFL | total | the record's hit rate by gap | 1693 |
| NBA | moneyline | 4% | 12318 |
| NBA | spread | 4% | 12318 |
| NBA | total | the record's hit rate by gap | 12366 |
| NHL | moneyline | 3% | 11120 |
| NHL | spread | 3% | 11120 |
| NHL | total | 3% | 11120 |

On football totals the record is read as a curve: the hit rate of Atlas's
side at disagreements this large or larger, never below one half.

## How far the anchored number sits from the market

| Sport | Market | Games | Atlas, median gap | Atlas, largest gap | Anchored, median gap |
|---|---|---|---|---|---|
| NBA | margin | 21 | 2.4 | 13.1 | 0.09 |
| NBA | total | 12 | 4.9 | 18.7 | 0.40 |
| NCAAF | margin | 30 | 4.0 | 19.3 | 0.00 |
| NCAAF | total | 30 | 4.7 | 26.8 | 1.27 |
| NFL | margin | 13 | 1.0 | 5.1 | 0.01 |
| NFL | total | 13 | 1.6 | 5.0 | 0.25 |

In points of margin or total, per game: Atlas's own projection against
the market's centre, and the anchored number the contracts are priced from.
On a market where the share is zero the anchored gap is zero by
construction.

## Player props

Player props this run: NBA (points, rebounds, assists, threes, steals, blocks, the three combined): 2263 contracts on 8 games, 2263 with an Atlas projection beside them, 0 graded so far; NHL (points, goals, assists): 1444 contracts on 12 games, 1444 with an Atlas projection beside them, 0 graded so far; NFL (yards, receptions, touchdowns, attempts, completions, carries): 2949 contracts on 13 games, 2919 with an Atlas projection beside them, 0 graded so far. Atlas's numbers are `atlas/models/nba_props.py` (`reports/nba_props.md`) and `atlas/models/nhl_props.py` (`reports/nhl_props.md`). Each player-stat's main line is kept in `tracking/polymarket_props.csv` with Atlas's probability as it stood, and graded against the box score and the close into `tracking/prop_record.csv`, the record that decides, a sport at a time, what Atlas's disagreement is worth there.

## The favorites rule

A second paper rule beside Atlas's, with no projection in it
(`atlas/polymarket/favorites.py`): a position on every moneyline the first
time its ask reaches 80, 85, 90 and 95 cents, in play or before the game,
at that ask plus the fee, graded by the venue's settlement and kept in
`tracking/favorites.csv`. The question is whether the venue's favorites
win more often than they cost. Edge is the win rate less the break-even
rate, in points, with one standard error.

| Phase | Threshold | Taken | Graded | Win rate | Break-even | Edge (pts) | Profit per $ |
|---|---|---|---|---|---|---|---|
| in play | 80% | 55 | 36 | 83.3% | 86.3% | -3.0 ± 6.2 | -3.4% |
| in play | 85% | 59 | 36 | 88.9% | 90.6% | -1.7 ± 5.2 | -1.9% |
| in play | 90% | 50 | 31 | 93.5% | 94.0% | -0.4 ± 4.4 | -0.5% |
| in play | 95% | 34 | 22 | 95.5% | 96.6% | -1.1 ± 4.4 | -1.1% |
| pregame | 80% | 43 | 9 | 88.9% | 85.1% | +3.8 ± 10.5 | 4.4% |
| pregame | 85% | 19 | 3 | 100.0% | 90.8% | +9.2 | 10.1% |
| pregame | 90% | 11 | 2 | 100.0% | 92.1% | +7.9 | 8.6% |
| pregame | 95% | 1 | 0 |  |  |  |  |

## The record

Paper positions are taken by a fixed rule, logged once and graded on the
result and against the venue's close. That record is the owner's, sealed
in `tracking/polymarket_positions/`, and is not published here. Nothing on
this page is a recommendation.
