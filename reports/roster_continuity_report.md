# Atlas Roster Continuity Report (Phase 1C, Track 3)

*Generated 2026-09-22 15:50 UTC.*

The question is deliberately **not** "does roster continuity predict
football?". Phase 1A and 1B established that everything predicting football is
already in the closing line. The only question is whether any of it moves the
**residual**.

## What was measured, and from where

| Variable | Source | Pre-kickoff? |
|---|---|---|
| Returning production | CFBD `/player/returning` | yes - fixed before the season |
| Recruiting rank, roster talent | CFBD `/recruiting/teams`, `/talent` | yes |
| Roster churn | Roster membership year over year | yes |
| Head-coach change | CFBD `/coaches` | yes |
| Transfer quarterback | Roster membership across teams | yes |
| QB continuity | Play-by-play | see below |

**Offensive and defensive coordinator changes could not be measured.** CFBD
carries head coaches only; no free source has a historical coordinator table
for 2018-present. Building one means scraping media guides and news archives,
which is a project rather than a data step. Given every other continuity
variable below measures zero, it is not a project worth funding on this
evidence.

## Results

| Variable | Games | Effect (pts) | r | t | p |
|---|---|---|---|---|---|
| New head coach | 1,674 | 0.6486 | n/a | 1.6862 | 0.0919 |
| QB change (reference) | 1,509 | 2.1022 | n/a | 5.2290 | 0.0000 |
| Returning production edge | 5,680 | 1.0760 | 0.0243 | 1.8349 | 0.0666 |
| Recruiting edge | 5,767 | 0.0018 | 0.0044 | 0.3354 | 0.7373 |
| Roster talent edge | 5,756 | -0.0006 | -0.0068 | -0.5195 | 0.6034 |
| Transfer QB | 5,778 | -0.0472 | -0.0019 | -0.1467 | 0.8834 |
| QB continuity edge (today's starter - post-hoc) | 5,109 | 1.8744 | 0.0560 | 4.0089 | 0.0001 |
| QB continuity edge (last game's - pre-kickoff) | 4,586 | -0.4527 | -0.0140 | -0.9494 | 0.3425 |
| Roster churn edge | 5,778 | 1.4419 | 0.0102 | 0.7736 | 0.4392 |

Effect sizes for continuous variables are the slope in residual points per
unit of the variable; for flags they are the signed residual in points.

## Reading it

**Nothing survives except the quarterback variables, and those are artefacts.**

`QB continuity edge (today's starter)` looks significant at t = 4.0. It is the
same contamination Track 1 dismantles: "the share of prior games started by
whoever starts today" requires knowing who starts today, and teams whose
starter is displaced are disproportionately teams whose games went badly. The
**pre-kickoff** version - continuity as it stood after the previous game -
measures within noise of zero, and it is in the table directly beneath.

Everything else is flat. A new head coach is worth
0.65
points against the line and does not clear its own error bar. Returning
production, recruiting, roster talent and roster churn are all priced.

This is consistent with everything before it: these are *widely published*
pre-season variables. The market has had all summer to price them, and it has.

## Recommendation

Drop the whole family from Alpha's feature search. It is not that these
variables are uninformative about football - returning production and
recruiting clearly are - it is that being informative and being *unpriced* are
different properties, and Phase 1C only cares about the second.

Do not build a coordinator-change dataset.
