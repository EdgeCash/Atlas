# Atlas on Polymarket

*Rebuilt every run; this one at 2026-10-23 09:53 UTC.*

Polymarket is the one venue Atlas is priced against. It lists a moneyline,
a ladder of spreads and a ladder of totals on every NFL, NBA, NHL and college
football game as binary contracts, and its prices are public: every run
reads them from Polymarket's own API, matches each game to the one Atlas
projects, and keeps every quote, timestamped, in
`tracking/polymarket_quotes.csv`. That table is the point-in-time archive of
the market Atlas is measured against.

## Coverage this run

| Sport | Games ahead | On Polymarket | Contracts | Median spread (main lines) | Median depth (main lines) | Fee rate |
|---|---|---|---|---|---|---|
| NCAAF | 49 | 49 | 5358 | 3.0¢ | $10,244 | 3% |
| NFL | 14 | 14 | 1568 | 2.0¢ | $42,153 | 3% |
| NBA | 13 | 12 | 682 | 2.0¢ | $45,090 | 0% |
| NHL | 2 | 2 | 24 | 1.0¢ | $41,442 | 5% |

Spread is the gap between the best bid and the best ask on the contracts
priced near even; depth is the dollars resting in the market. The fee is
Polymarket's taker fee, `rate × price × (1 − price)` per contract, read from
each market's own schedule.

## How Atlas is anchored to Polymarket

Atlas's number for a game is never used raw. Polymarket's centre for the
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
| NFL | moneyline | 1% | 1669 |
| NFL | spread | 1% | 1669 |
| NFL | total | the record's hit rate by gap | 1692 |
| NBA | moneyline | 0% | 0 |
| NBA | spread | 0% | 0 |
| NBA | total | 0% | 0 |
| NHL | moneyline | 0% | 11111 |
| NHL | spread | 0% | 11111 |
| NHL | total | 0% | 11111 |

On football totals the record is read as a curve: the hit rate of Atlas's
side at disagreements this large or larger, never below one half.

## How far the anchored number sits from the market

| Sport | Market | Games | Atlas, median gap | Atlas, largest gap | Anchored, median gap |
|---|---|---|---|---|---|
| NCAAF | margin | 49 | 2.2 | 7.7 | 0.00 |
| NCAAF | total | 49 | 2.1 | 6.1 | 0.76 |
| NFL | margin | 14 | 1.4 | 3.2 | 0.01 |
| NFL | total | 14 | 1.2 | 4.9 | 0.27 |

In points of margin or total, per game: Atlas's own projection against
Polymarket's centre, and the anchored number the contracts are priced from.
On a market where the share is zero the anchored gap is zero by
construction.

## Player props

NBA player props (points, rebounds, assists, threes) this run: 0 contracts on 0 games, 0 with an Atlas projection beside them (`atlas/models/nba_props.py`, `reports/nba_props.md`). Each player-stat's main line is kept in `tracking/polymarket_props.csv` with Atlas's probability as it stood, and graded against the box score and the close into `tracking/prop_record.csv`: 0 graded so far. Most prop books on Polymarket are thin; the record, not the depth, decides what Atlas's disagreement is worth there.

## The record

Paper positions are taken by a fixed rule, logged once and graded on the
result and against Polymarket's close. That record is the owner's, sealed
in `tracking/polymarket_positions/`, and is not published here. Nothing on
this page is a recommendation.
