# Atlas Market Efficiency Report (Phase 1C, Track 2)

*Generated 2026-09-22 15:50 UTC.*

## What could and could not be measured

The brief asks for line snapshots at open, 24h, 12h, 6h, 1h and close. **The
intraday snapshots do not exist in any free source**, and this was checked
rather than assumed:

| Source | Line history available |
|---|---|
| CollegeFootballData `/lines` | opening and closing only, per provider |
| The historical sportsbook feed Atlas already uses | opening and closing only |
| Velocity's own NCAAF archive | closing only - its docs name the same gap |

A timestamped archive is a commercial product. What Atlas *can* measure is the
total information that arrives between open and close, which bounds
everything inside that window, plus two proxies for where in the window it
arrives.

## Opening versus closing accuracy

| Line | Games | MAE | RMSE |
|---|---|---|---|
| opening spread | 5,262 | 12.376 | 16.148 |
| closing spread | 5,262 | 12.159 | 15.396 |
| opening total | 5,268 | 12.800 | 16.131 |
| closing total | 5,268 | 12.603 | 15.920 |

The close beats the open by **0.217 points of MAE on spreads**
and **0.197 on totals**. That is the entire value of every piece
of news, every injury report and every dollar of sharp money between the two -
about a fifth of a point.

For scale: the closing spread's own MAE is around 12.2 points. The open-to-close
move is worth roughly **1.8% of the market's residual error**. Whatever
information enters the market during the week, there is very little of it, and
the opening line is already nearly as good as the closing one.

## Does the direction of the move carry information?

If the move were carrying news the close had not fully absorbed, following it
would beat the close.

| Market | Move | Games | Mean residual | SE | t | p |
|---|---|---|---|---|---|---|
| spread | 1..3 | 1,008 | 0.791 | 0.489 | 1.617 | 0.106 |
| spread | <= -3 | 340 | -0.932 | 0.809 | -1.153 | 0.250 |
| spread | no move | 675 | 0.390 | 0.573 | 0.680 | 0.497 |
| spread | >= 3 | 302 | -0.563 | 0.887 | -0.635 | 0.526 |
| spread | -1..0 | 707 | 0.116 | 0.583 | 0.200 | 0.842 |
| spread | 0..1 | 1,150 | 0.005 | 0.460 | 0.010 | 0.992 |
| spread | -3..-1 | 1,078 | 0.004 | 0.470 | 0.009 | 0.993 |
| total | >= 3 | 318 | 1.521 | 0.892 | 1.704 | 0.089 |
| total | 0..1 | 866 | 0.613 | 0.551 | 1.113 | 0.266 |
| total | 1..3 | 879 | 0.315 | 0.565 | 0.558 | 0.577 |
| total | -1..0 | 610 | 0.340 | 0.624 | 0.545 | 0.586 |
| total | -3..-1 | 1,454 | 0.121 | 0.417 | 0.290 | 0.772 |
| total | no move | 442 | 0.211 | 0.734 | 0.288 | 0.774 |
| total | <= -3 | 699 | 0.102 | 0.577 | 0.177 | 0.859 |

No band is significant. The move is absorbed by the time the line closes,
which is what an efficient close means.

## Does the market's own disagreement flag its errors?

Books disagree at the close by about half a point on average. If that
disagreement marked genuinely uncertain games, the market's error would be
larger where books disagree most.

| Market | Book disagreement | Games | Mean absolute residual | Mean residual |
|---|---|---|---|---|
| spread | tightest | 1,445 | 12.050 | -0.570 |
| spread | tight | 1,656 | 12.171 | 0.213 |
| spread | loose | 1,225 | 12.376 | 0.632 |
| spread | loosest | 1,442 | 12.328 | -0.126 |
| total | tightest | 1,574 | 12.397 | 0.366 |
| total | tight | 1,308 | 12.521 | 0.861 |
| total | loose | 1,500 | 12.992 | 0.131 |
| total | loosest | 1,381 | 12.906 | 0.263 |

Slightly - the loosest quartile misses by a little more than the tightest -
but the spread across quartiles is a fraction of a point on a 12-point error.
Book disagreement is not a useful uncertainty signal at this resolution.

## Answers

**How much information enters the market over time?**
About 0.22 points of spread accuracy between open and close,
against a 12-point error. Very little.

**Where does the biggest jump occur?**
Not measurable without a timestamped archive. But the ceiling on *any* jump
inside the window is the 0.22-point total, so no intraday
moment can be worth much more than that.

**Can Atlas obtain information before that point?**
The question is close to moot. Even perfect foreknowledge of the entire
open-to-close move is worth a fifth of a point. Beating the *opening* line is
a more interesting target than beating the close, and it is a different
business - it requires speed and market access rather than better models.

## Recommendation

Do not buy a line-history archive to chase closing-line value on sides. The
prize is measurably small. If a timestamped archive is ever acquired, the
first thing to measure with it is **totals**, where the open-to-close gain is
0.20 points and where Track 6 finds the only live signal.
