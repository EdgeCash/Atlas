# DFS lineups, 2015-2021

Every Sunday main slate with DraftKings' own salaries: the lineup with the most projected points under the $50,000 cap, built by Atlas's optimizer (`atlas/dfs/optimizer.py`) from each projection, and scored by what its nine players actually recorded (`atlas/dfs/backtest.py`). One lineup per projection per slate, no defense facing its own lineup's offense, no other rule. `best possible` is the lineup built from the outcomes themselves - the ceiling, for scale.

## Actual points of each projection's lineup

| seasons | slates | model | salary | baseline | best possible |
|---|---|---|---|---|---|
| 2015-2021 | 119 | 137.2 | 123.4 | 127.7 | 279.1 |

`salary` is DraftKings' price read as a projection: one straight line per position, so its optimizer simply spends the cap where a dollar buys the most. It is the market's view taken literally, not a way anyone would build a lineup - the fair comparison for the model's ranking is step 3's.

## Head to head

| model against | slates | model higher | mean difference | standard error |
|---|---|---|---|---|
| salary | 119 | 72% | +13.8 | 2.9 |
| baseline | 119 | 71% | +9.5 | 2.0 |

## Projected against scored

What each lineup was projected to score and what it did. A lineup chosen as the highest projection is chosen partly for its projection's errors, so every projection's best lineup scores below its own number; the smaller the gap, the less the projection fooled its optimizer.

| projection | projected | scored |
|---|---|---|
| model | 150.4 | 137.2 |
| salary | 120.4 | 123.4 |
| baseline | 160.9 | 127.7 |

## By season

| season | slates | model | salary | baseline | best possible |
|---|---|---|---|---|---|
| 2015 | 17 | 140.9 | 127.9 | 132.9 | 287.6 |
| 2016 | 16 | 126.0 | 105.2 | 111.3 | 271.3 |
| 2017 | 17 | 134.5 | 127.5 | 121.3 | 264.3 |
| 2018 | 17 | 146.5 | 136.7 | 138.4 | 284.5 |
| 2019 | 17 | 137.9 | 124.3 | 130.4 | 296.8 |
| 2020 | 17 | 140.2 | 130.4 | 134.1 | 279.8 |
| 2021 | 18 | 133.9 | 111.7 | 124.6 | 269.8 |

## Who plays at all

The backtest's pool is the players who recorded a stat; a live slate's pool is everyone DraftKings prices. For the live slate, each player's projection is multiplied by the chance he records a stat (`atlas/dfs/participation.py`): fitted on every quarterback, running back, receiver and tight end on a depth chart, from his position, depth-chart rank, injury status, games played, snap share and weeks since his last game. Walk-forward, 2015-2026, 86,413 listings:

- Brier score 0.121, against 0.173 for the share of earlier listings at the same position and depth who played (lower is better).

Predicted against observed, by tenths of the prediction:

| listings | predicted | observed |
|---|---|---|
| 6026 | 2.3% | 1.8% |
| 4140 | 15.3% | 17.9% |
| 3238 | 25.8% | 23.2% |
| 3760 | 35.4% | 31.7% |
| 4374 | 44.9% | 40.9% |
| 4643 | 55.3% | 52.5% |
| 6258 | 65.2% | 63.8% |
| 10030 | 75.3% | 76.0% |
| 12730 | 85.2% | 83.5% |
| 31214 | 96.4% | 96.2% |

## Caveats

- **The pool** is the players who recorded a stat that week: a player ruled out beforehand is not in it (the injury report and the inactive list say so before lock), and neither is an active player who recorded nothing, which flatters every projection alike.
- **The main slate** is reconstructed from kickoff times (Sunday, noon to 5pm Eastern); DraftKings' own slate for a given week may have differed by a game.
- **Nothing here is a return.** A lineup's points say how well a projection ranks players under a cap. They say nothing about winning a contest, which depends on the field, the entry fee and DraftKings' rake.
