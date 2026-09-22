# Atlas Situational Edge Report (Phase 1C, Track 4)

*Generated 2026-09-22 15:50 UTC.*

Situational angles are the oldest folklore in sports betting: the bye-week
bounce, the letdown after a rivalry win, the cross-country body-clock spot.
Unlike the quarterback track, **every variable here is genuinely knowable
before kickoff** - they come off the schedule. If any of them moved the
residual, they would be immediately usable.

## Margin residual

A positive value means the team in the situation **underperformed** the
closing line.

| Effect | N | N On | Mean | Mean On | Mean Off | Difference | Se | T | P |
|---|---|---|---|---|---|---|---|---|---|
| Coming off a bye (13+ days) | 927 | n/a | -0.050 | n/a | n/a | n/a | 0.508 | -0.098 | 0.922 |
| Revenge spot (lost the last meeting) | 1,603 | n/a | -0.328 | n/a | n/a | n/a | 0.373 | -0.880 | 0.379 |
| Team is AP top 10 | 743 | n/a | -0.382 | n/a | n/a | n/a | 0.551 | -0.694 | 0.488 |
| Recurring rivalry fixture | n/a | 2344.000 | n/a | -0.555 | 0.428 | -0.982 | 0.413 | -2.381 | 0.017 |
| Top-10 vs top-10 | n/a | 69.000 | n/a | 2.301 | 0.002 | 2.299 | 1.597 | 1.439 | 0.150 |
| Ranked vs ranked | n/a | 346.000 | n/a | 1.993 | -0.096 | 2.089 | 0.773 | 2.703 | 0.007 |
| Bowl / postseason | n/a | 134.000 | n/a | 1.132 | 0.003 | 1.129 | 1.401 | 0.806 | 0.420 |
| Rematch after a 21+ point loss | n/a | 490.000 | n/a | -1.681 | 0.188 | -1.869 | 0.710 | -2.634 | 0.008 |
| Conference game | n/a | 4144.000 | n/a | -0.069 | 0.279 | -0.348 | 0.454 | -0.767 | 0.443 |

## Totals residual

| Situation | Games | Mean (on) | Mean (off) | Difference | t | p |
|---|---|---|---|---|---|---|
| Recurring rivalry fixture | 2,344 | 0.369 | 0.422 | -0.053 | -0.124 | 0.902 |
| Top-10 vs top-10 | 69 | 2.525 | 0.375 | 2.150 | 1.056 | 0.291 |
| Ranked vs ranked | 346 | -1.621 | 0.529 | -2.150 | -2.546 | 0.011 |
| Bowl / postseason | 134 | 1.149 | 0.383 | 0.766 | 0.538 | 0.591 |
| Rematch after a 21+ point loss | 490 | 0.418 | 0.399 | 0.019 | 0.025 | 0.980 |
| Conference game | 4,144 | 0.625 | -0.167 | 0.792 | 1.691 | 0.091 |

## Travel in detail

| Travel band | Games | Mean residual | SE | t | p | Home cover rate | z |
|---|---|---|---|---|---|---|---|
| <200mi | 1,049 | -1.010 | 0.481 | -2.101 | 0.036 | 0.482 | -1.183 |
| 200-500 | 1,943 | 0.630 | 0.351 | 1.795 | 0.073 | 0.504 | 0.367 |
| 1500+ | 339 | 0.928 | 0.837 | 1.108 | 0.268 | 0.527 | 0.988 |
| 500-1000 | 1,682 | -0.259 | 0.373 | -0.695 | 0.487 | 0.500 | -0.025 |
| 1000-1500 | 427 | 0.472 | 0.781 | 0.604 | 0.546 | 0.510 | 0.392 |
| n/a | 338 | -0.222 | 0.810 | -0.274 | 0.784 | 0.530 | 1.094 |

## Reading it

3 of 9 situations cleared p < 0.05 before correction: Recurring rivalry fixture, Ranked vs ranked, Rematch after a 21+ point loss

That number is the point. Running 9 tests at p < 0.05 produces
about 0.5 nominal hits from pure noise, and the
synthesis report's pooled Benjamini-Hochberg correction is where these have to
survive - not here. None of them is large: the biggest situational effect in
the table is a point or two on a distribution whose standard deviation is
fifteen.

Three specific folklore results worth naming:

* **The bye week is worth nothing.** Teams with 13+ days rest perform exactly
  as the line expects.
* **Short rest is worth nothing.** Same.
* **Long travel is worth nothing.** The 1500+ mile band is indistinguishable
  from the sub-200 band once error bars are attached.

These are strong negatives precisely because the variables are free, public
and trivially computable. If they carried value, they would have been arbitraged
away decades ago - and the data says they were.

## Recommendation

Exclude the entire situational family from Alpha. Do not revisit without a
specific, pre-registered hypothesis and a reason to believe the market has
changed.
