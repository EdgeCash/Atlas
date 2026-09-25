"""Track 6: the forward validation report, rewritten on every run."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from atlas import config
from atlas.live import grade as grading
from atlas.live import scorecard as sc
from atlas.live.store import Store
from atlas.research.markdown import table
from atlas.util import get_logger

LOG = get_logger(__name__)


def _verdict(criteria: list[sc.Criterion]) -> str:
    if not any(c.decided for c in criteria):
        return "COLLECTING"
    return "PASSING" if all(c.passing for c in criteria) else "FAILING"


def build(store: Store | None = None) -> dict:
    store = store or Store.open()
    signals = store.read("signals")
    grades = store.read("grades")
    snapshots = store.read("snapshots")
    games = store.read("games")
    frame = sc.graded_frame(signals, grades)
    return {
        "signals": signals,
        "grades": grades,
        "snapshots": snapshots,
        "games": games,
        "frame": frame,
        "criteria": sc.kill_criteria(frame),
        "daily": sc.scorecard(frame, by="graded_date"),
        "weekly": sc.scorecard(frame, by="week"),
        "season": sc.scorecard(frame, by="season"),
        "books": sc.by_book(frame),
        "selections": sc.by_selection(frame),
    }


def write(bundle: dict | None = None, store: Store | None = None) -> Path:
    store = store or Store.open()
    bundle = bundle or build(store)
    paths = config.paths().ensure()
    generated = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

    signals, frame = bundle["signals"], bundle["frame"]
    criteria = bundle["criteria"]
    verdict = _verdict(criteria)
    graded = int(criteria[0].graded)
    seasons = sc.seasons_complete(signals)

    open_signals = len(signals) - len(frame)
    primary = signals[signals["selection"] == "primary"] if not signals.empty else signals

    criteria_rows = pd.DataFrame([
        {
            "criterion": c.name,
            "observed": c.observed,
            "threshold": c.threshold,
            "graded": c.graded,
            "status": ("holding" if c.passing else "BREACHED") if c.decided
            else "collecting",
            "note": c.note,
        }
        for c in criteria
    ])

    text = f"""# Atlas Live CLV Tracking

*Generated {generated} by `python -m atlas.live report`. Updated on every run
of the tracker. Source tables are the CSVs in `tracking/`, which are committed
alongside this file so the record can be audited row by row.*

> **Atlas generates opinions. Atlas does not generate bets.** Nothing in this
> system computes a stake, an expected profit, a return on investment or a
> Kelly fraction. The only question asked is whether the market moved toward
> Atlas's number after Atlas stated it.

---

## Status: {verdict}

| | |
|---|---|
| Signals recorded | {len(signals):,} |
| Primary signals | {len(primary):,} |
| Graded (decided) | {graded:,} |
| Awaiting kickoff | {open_signals:,} |
| Seasons of tracking | {seasons} of {sc.SEASONS_REQUIRED} required |
| Verdict possible at | {sc.MIN_GRADED_FOR_VERDICT:,} graded primary signals |

{_status_sentence(verdict, graded, seasons)}

---

## Kill criteria

Frozen in [`{sc.KILL_SOURCE}`](atlas_gamma_assessment.md) before any live
signal existed. They are checked, never tuned.

{table(criteria_rows, ["criterion", "observed", "threshold", "graded", "status", "note"], ["Criterion", "Observed", "Threshold", "Graded", "Status", "Requirement"], digits=4) if not criteria_rows.empty else "_No criteria evaluated yet._"}

---

## Scorecard

### By season

{_or_empty(bundle["season"], ["season", "signals", "graded", "pushes", "beat_rate", "beat_low", "beat_high", "p_value", "mean_clv", "median_clv", "flagged"], ["Season", "Signals", "Graded", "Pushes", "Beat rate", "95% low", "95% high", "p vs 50%", "Mean CLV", "Median CLV", "Flagged"])}

### By week

{_or_empty(bundle["weekly"], ["season", "week", "signals", "graded", "pushes", "beat_rate", "mean_clv", "median_clv", "flagged"], ["Season", "Week", "Signals", "Graded", "Pushes", "Beat rate", "Mean CLV", "Median CLV", "Flagged"])}

### By day

{_or_empty(bundle["daily"], ["graded_date", "signals", "graded", "pushes", "beat_rate", "mean_clv", "median_clv", "flagged"], ["Date", "Signals", "Graded", "Pushes", "Beat rate", "Mean CLV", "Median CLV", "Flagged"])}

### By book

{_or_empty(bundle["books"], ["book", "signals", "graded", "pushes", "beat_rate", "mean_clv", "median_clv", "flagged"], ["Book", "Signals", "Graded", "Pushes", "Beat rate", "Mean CLV", "Median CLV", "Flagged"])}

### Every population, including the ones the criteria ignore

{_or_empty(bundle["selections"], ["selection", "signals", "graded", "pushes", "beat_rate", "beat_low", "beat_high", "p_value", "mean_clv", "median_clv", "flagged"], ["Population", "Signals", "Graded", "Pushes", "Beat rate", "95% low", "95% high", "p vs 50%", "Mean CLV", "Median CLV", "Flagged"])}

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
exceeds {grading.EXECUTION_FLAG_POINTS:.1f} points is flagged - that is Gamma's
third kill criterion, made operational.

A line that never moved is a **push**, not a loss. It is excluded from the
beat rate and reported separately.

---

## Data captured

| Table | Rows | What it holds |
|---|---|---|
| `tracking/games.csv` | {len(bundle["games"]):,} | every game seen, with kickoff and status |
| `tracking/snapshots.csv` | {len(bundle["snapshots"]):,} | append-on-change line observations, timestamped |
| `tracking/signals.csv` | {len(signals):,} | immutable opinions |
| `tracking/grades.csv` | {len(bundle["grades"]):,} | one row per graded signal |

---

## What happens at the end

Two complete seasons, then one of two recommendations and no middle ground:
promote Atlas into a real betting system, or terminate it. The criteria above
decide which. They will not be revised in between.
"""
    out = paths.reports / "live_clv_tracking.md"
    out.write_text(text)
    LOG.info("wrote %s", out)
    return out


def _or_empty(frame: pd.DataFrame, columns: list[str], headers: list[str]) -> str:
    if frame is None or frame.empty:
        return "_No graded signals yet._"
    present = [c for c in columns if c in frame.columns]
    labels = [h for c, h in zip(columns, headers, strict=False) if c in frame.columns]
    return table(frame, present, labels, digits=4)


def _status_sentence(verdict: str, graded: int, seasons: int) -> str:
    if verdict == "COLLECTING":
        return (
            f"**The record is too short to decide anything.** {graded:,} graded "
            f"signals against the {sc.MIN_GRADED_FOR_VERDICT:,} needed to "
            "separate the beat rate from a coin flip. Numbers below are "
            "reported because they are the record, not because they mean "
            "anything yet."
        )
    if verdict == "PASSING":
        return (
            f"**All criteria are holding** on {graded:,} graded signals across "
            f"{seasons} season(s). The criteria stay frozen until "
            f"{sc.SEASONS_REQUIRED} complete seasons are in."
        )
    return (
        f"**At least one criterion has been breached** on {graded:,} graded "
        "signals. See the table above. A breach is the answer the project "
        "pre-registered, not a prompt to revisit the threshold."
    )


def main() -> None:
    write()


if __name__ == "__main__":
    main()
