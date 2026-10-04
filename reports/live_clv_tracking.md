# Atlas Live CLV Tracking

*Generated 2026-10-04 21:22 UTC by `python -m atlas.live report`. Updated on every run
of the tracker. Source tables are the CSVs in `tracking/`, which are committed
alongside this file so the record can be audited row by row.*

> **Atlas generates opinions. Atlas does not generate bets.** Nothing in this
> system computes a stake, an expected profit, a return on investment or a
> Kelly fraction. The only question asked is whether the market moved toward
> Atlas's number after Atlas stated it.

---

## Status: COLLECTING

| | |
|---|---|
| Signals recorded | 344 |
| Primary signals | 5 |
| Graded (decided) | 1 |
| Awaiting kickoff | 116 |
| Seasons of tracking | 1 of 2 required |
| Verdict possible at | 124 graded primary signals |

**The record is too short to decide anything.** 1 graded signals against the 124 needed to separate the beat rate from a coin flip. Numbers below are reported because they are the record, not because they mean anything yet.

---

## Kill criteria

Frozen in [`reports/atlas_gamma_assessment.md`](atlas_gamma_assessment.md) before any live
signal existed. They are checked, never tuned.

| Criterion | Observed | Threshold | Graded | Status | Requirement |
|---|---|---|---|---|---|
| CLV beat rate | 1.0000 | 0.55 | 1 | collecting | must stay at or above 55% |
| Mean CLV | 1.0000 | 0.49 | 1 | collecting | must stay at or above 0.49 points |
| Execution window | 1.0000 | 0.5 | 1 | collecting | share of signals where the line had already moved 0.5+ points toward Atlas before it spoke |

---

## Scorecard

### By season

| Season | Signals | Graded | Pushes | Beat rate | 95% low | 95% high | p vs 50% | Mean CLV | Median CLV | Mean CLV (prob) | Flagged |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 2026 | 1 | 1 | 0 | 1.0000 | 0.2065 | 1.0000 | 0.5000 | 1.0000 | 1 | 0.0460 | 1 |

### By week

| Season | Week | Signals | Graded | Pushes | Beat rate | Mean CLV | Median CLV | Mean CLV (prob) | Flagged |
|---|---|---|---|---|---|---|---|---|---|
| 2026 | 4.0000 | 1 | 1 | 0 | 1.0000 | 1.0000 | 1 | 0.0460 | 1 |

### By day

| Date | Signals | Graded | Pushes | Beat rate | Mean CLV | Median CLV | Mean CLV (prob) | Flagged |
|---|---|---|---|---|---|---|---|---|
| 2026-09-26 | 1 | 1 | 0 | 1.0000 | 1.0000 | 1 | 0.0460 | 1 |

### By book

| Book | Signals | Graded | Pushes | Beat rate | Mean CLV | Median CLV | Mean CLV (prob) | Flagged |
|---|---|---|---|---|---|---|---|---|
| DraftKings | 1 | 1 | 0 | 1.0000 | 1.0000 | 1 | 0.0460 | 1 |

### Every population, including the ones the criteria ignore

| Population | Signals | Graded | Pushes | Beat rate | 95% low | 95% high | p vs 50% | Mean CLV | Median CLV | Mean CLV (prob) | Flagged |
|---|---|---|---|---|---|---|---|---|---|---|---|
| observed | 222 | 170 | 52 | 0.5118 | 0.4372 | 0.5858 | 0.4091 | 0.1306 | 0 | 0.0028 | 50 |
| primary | 1 | 1 | 0 | 1.0000 | 0.2065 | 1.0000 | 0.5000 | 1.0000 | 1 | 0.0460 | 1 |
| secondary | 5 | 4 | 1 | 0.7500 | 0.3006 | 0.9544 | 0.3125 | 1.0000 | 1 | 0.0216 | 2 |
| all | 228 | 175 | 53 | 0.5200 | 0.4463 | 0.5928 | 0.3251 | 0.1535 | 0 | 0.0034 | 53 |

`primary` is the population the criteria are evaluated on: totals at or above
the historical 90th percentile of disagreement. `secondary` is the same cut on
margins from week 5 onward. `observed` is everything else - recorded because a
tracker that keeps only the signals it likes cannot be audited.

---

## How a signal is graded

Each signal stores two numbers. `open_line` is what the book opened on, which
makes the live record comparable with the historical study. `entry_line` is
what the book was quoting when Atlas formed the opinion, which is the number
that was actually available.

**CLV is graded against `entry_line`.** Grading against the opener would
credit Atlas with movement that happened before it spoke. The difference
between the two is recorded as `pre_signal_move`, and a signal where that
exceeds 0.5 points is flagged - that is Gamma's
third kill criterion, made operational.

A line that never moved is a **push**, not a loss. It is excluded from the
beat rate and reported separately.

---

## Data captured

| Table | Rows | What it holds |
|---|---|---|
| `tracking/games.csv` | 277 | every game seen, with kickoff and status |
| `tracking/snapshots.csv` | 3,891 | append-on-change line observations, timestamped |
| `tracking/signals.csv` | 344 | immutable opinions |
| `tracking/grades.csv` | 228 | one row per graded signal |

---

## What happens at the end

Two complete seasons, then one of two recommendations and no middle ground:
promote Atlas into a real betting system, or terminate it. The criteria above
decide which. They will not be revised in between.
