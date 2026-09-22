# Atlas / Velocity Comparison (Phase 1C, Track 6)

*Generated 2026-09-22 15:50 UTC. Velocity's figures are quoted from its own
repository (`EdgeCash/Velocity`, `docs/BACKTEST_NCAAF.md`) and are not
recomputed here.*

## Why this track changed the phase

Velocity is an independent model over the same sport. Comparing it to Atlas
surfaced a **methodological gap in Atlas**, not just a benchmark.

Phase 1A and 1B asked: *does this feature set lower MAE on average?* Velocity
asks a different question: *is the model right about the games it disagrees
with the market on most?* Those are not the same. A model can be worse than
the market on average and still be right on its biggest disagreements - which
is precisely the shape a real edge takes, and precisely the test Atlas had
never run.

So this track runs Velocity's test on Atlas's own out-of-sample predictions.

## The two models

| | Atlas | Velocity |
|---|---|---|
| Sample | 2018-2025, 5,778 FBS-vs-FBS games | 2015-2024, ~9,500 games |
| Rating | Opponent-adjusted EPA / success rate (Phase 1B) | Opponent-adjusted points ("scores"), EPA path built |
| Evaluation | Leave-one-season-out | Walk-forward |
| Codebase | Independent | Independent |

Different samples, different features, different code. Agreement between them
is therefore informative in a way that a second run of the same model is not.

## Sides

| Disagreement ≥ | Bets | Win rate | z |
|---|---|---|---|
| 0 | 5,671 | 0.4974 | -0.3851 |
| 1 | 4,893 | 0.4966 | -0.4718 |
| 2 | 4,200 | 0.4986 | -0.1852 |
| 3 | 3,567 | 0.4948 | -0.6195 |
| 4 | 2,924 | 0.4962 | -0.4068 |
| 6 | 1,931 | 0.4925 | -0.6599 |
| 8 | 1,210 | 0.4876 | -0.8624 |
| 10 | 767 | 0.4602 | -2.2026 |

Velocity reports **50.1%** flat on 9,518 games, with no edge at any
disagreement threshold. Atlas reads **49.7%** flat and stays
flat-to-declining as the threshold rises.

**Two independent models, two independent samples, the same answer: college
football sides are efficient.** This is the strongest confirmation in the
programme of Phase 1A's central finding, and it is worth more than either
result alone.

## Totals

| Disagreement ≥ | Bets | Win rate | z | Clears -110? |
|---|---|---|---|---|
| 0 | 5,708 | 0.5200 | 3.0178 | no |
| 1 | 4,800 | 0.5210 | 2.9156 | no |
| 2 | 3,885 | 0.5176 | 2.1980 | no |
| 3 | 3,091 | 0.5205 | 2.2843 | no |
| 4 | 2,380 | 0.5244 | 2.3778 | yes |
| 6 | 1,285 | 0.5261 | 1.8691 | no |
| 8 | 649 | 0.5393 | 2.0019 | yes |
| 10 | 282 | 0.5461 | 1.5483 | no |

Velocity's published curve, for comparison:

| Disagreement ≥ | Win rate | Bets |
|---|---|---|
| 0 | 0.5160 | 9,567 |
| 3 | 0.5230 | 6,605 |
| 4 | 0.5260 | 5,630 |
| 6 | 0.5340 | 3,894 |
| 8 | 0.5300 | 2,461 |

**The shape reproduces.** Atlas goes from 52.0% flat to
53.9% at the 8-point cut; Velocity goes from 51.6% to 53.0-53.4%.
Two models built from different data, evaluated differently, produce the same
monotone rise. That is much harder to dismiss as one model's overfitting than
either curve alone.

## And the caveats, which are severe

**1. Season robustness is weak.** At the 4-point cut Atlas is above the -110
break-even in **5 of 8 seasons**. Velocity's own
re-verification came out at 6 of 10, revised down from an originally reported
7 of 10.

| Season | Bets | Win rate | z | Above break-even |
|---|---|---|---|---|
| 2,018 | 316 | 0.4905 | -0.3375 | no |
| 2,019 | 291 | 0.5430 | 1.4655 | yes |
| 2,020 | 234 | 0.6026 | 3.1379 | yes |
| 2,021 | 351 | 0.4872 | -0.4804 | no |
| 2,022 | 334 | 0.4731 | -0.9849 | no |
| 2,023 | 342 | 0.5409 | 1.5141 | yes |
| 2,024 | 275 | 0.5636 | 2.1106 | yes |
| 2,025 | 237 | 0.5274 | 0.8444 | yes |

**2. The margin over break-even is nearly zero.** 52.44% at the
4-point cut against a 52.38% break-even is not an edge, it is a tie. Only the
sparsest cuts clear it, on the smallest samples.

**3. Multiple testing.** Eight thresholds were scanned. The best-looking cut
in an eight-way scan is biased upward by construction.

**4. Break-even assumes -110 and unlimited liquidity.** Neither holds. Real
juice on college totals is often worse, and the limits on the games where a
model most disagrees with the market are the lowest on the board.

## Did Velocity succeed where the market failed?

Not on sides - it reports the same wall Atlas hit. On totals it reports a thin
selective edge, and **Atlas independently reproduces the shape of it**.

## Did Velocity succeed where Atlas signals existed?

The two agree on where the signal is not: sides, team quality, and the market
residual as measured by mean error. They agree on where the only candidate
lives: **selective totals**.

## Recommendation

This is the one direction in the programme that two independent models both
point at. It should be the thing Atlas tests next - and tested properly, which
means:

1. **Hold out a season entirely** and measure the cut once, on data no model
   fitting touched.
2. **Pre-register the threshold** rather than picking the best of eight.
3. **Price real friction** - actual juice, actual limits, actual availability
   at the number.

Until those three are done, the honest description is "a signal at the edge of
noise that two models see", not "an edge".
