"""Track 6: rebuilding the record from its inputs and checking it matches.

The claim this phase has to support is not "the tracker works". It is "anyone
can rebuild what the tracker published, from the inputs it stored, and get the
same answer". That is a stronger claim and it is the only one that makes the
scorecard evidence rather than testimony.

Three things are replayed, in increasing order of what a mismatch would mean:

``signals``     re-derived from the stored numbers and the first snapshot
``grades``      recomputed from the stored signals, snapshots and games
``statistics``  recomputed from the replayed signals and grades

A signal mismatch means the record is not reproducible. A grade mismatch means
the grading logic changed under a published number. A statistics mismatch
means the scorecard does not follow from the record.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from atlas.live import grade as grading
from atlas.live import scorecard as sc
from atlas.live import signals as signalling
from atlas.live.store import Store
from atlas.util import get_logger

LOG = get_logger(__name__)

#: Periods replayed per run by default.
REPLAY_SAMPLE = 3

#: Lines move in quarter-points; anything under this is float noise.
TOLERANCE = 0.001

#: Columns a replayed signal must match exactly. ``created_at`` is excluded on
#: purpose - a replay happens later than the thing it replays, and demanding
#: the timestamp match would only ever prove the clock works.
SIGNAL_COLUMNS = (
    "signal_id", "game_id", "market", "book", "entry_line", "atlas_number",
    "disagreement", "direction", "selection", "model_version",
)

GRADE_COLUMNS = ("signal_id", "close_line", "clv_points", "result")


@dataclass(frozen=True)
class Replay:
    """The outcome of rebuilding one period."""

    period: str
    scope: str
    rows: int
    matched: int
    mismatched: int
    missing: int
    detail: str

    @property
    def clean(self) -> bool:
        return self.mismatched == 0 and self.missing == 0


def periods(store: Store | None = None) -> list[str]:
    """Every period that can be replayed, as ``season-week`` labels."""
    store = store or Store.open()
    signals = store.read("signals")
    if signals.empty:
        return []
    frame = signals.dropna(subset=["season", "week"])
    labels = (
        frame["season"].astype(float).astype(int).astype(str)
        + "-w"
        + frame["week"].astype(float).astype(int).astype(str).str.zfill(2)
    )
    return sorted(labels.unique())


def _label(frame: pd.DataFrame) -> pd.Series:
    return (
        pd.to_numeric(frame["season"], errors="coerce").astype("Int64").astype(str)
        + "-w"
        + pd.to_numeric(frame["week"], errors="coerce").astype("Int64")
        .astype(str).str.zfill(2)
    )


def first_quotes(store: Store, signals: pd.DataFrame) -> pd.DataFrame:
    """The earliest snapshot for each signal's game, book and market.

    That snapshot is what the signal was formed against: the poll that first
    saw a game writes both in the same pass, so the first observation is the
    entry line by construction.
    """
    snapshots = store.read("snapshots")
    if snapshots.empty:
        return pd.DataFrame()
    block = snapshots.copy()
    block["captured_ts"] = pd.to_datetime(block["captured_at"], utc=True, errors="coerce")
    block = block.sort_values("captured_ts")
    first = block.drop_duplicates(["game_id", "book", "market"], keep="first")
    for column in ("line", "price", "open_line", "open_price"):
        first[column] = pd.to_numeric(first[column], errors="coerce")
    first["status"] = "STATUS_SCHEDULED"
    keys = signals[["game_id", "market", "book"]].astype(str).agg("|".join, axis=1)
    mask = first[["game_id", "market", "book"]].astype(str).agg("|".join, axis=1)
    return first[mask.isin(set(keys))]


def replay_signals(store: Store, period: str) -> Replay:
    """Re-derive the period's signals from the stored numbers and quotes."""
    stored = store.read("signals")
    if stored.empty:
        return Replay(period, "signals", 0, 0, 0, 0, "no signals recorded")
    stored = stored[_label(stored) == period]
    if stored.empty:
        return Replay(period, "signals", 0, 0, 0, 0, "no signals in this period")

    quotes = first_quotes(store, stored)
    if quotes.empty:
        return Replay(period, "signals", len(stored), 0, 0, len(stored),
                      "no snapshots to replay against")

    numbers = store.read("numbers")
    numbers["prediction"] = pd.to_numeric(numbers["prediction"], errors="coerce")
    numbers["threshold"] = pd.to_numeric(numbers["threshold"], errors="coerce")
    # Replay with the model version the signal names, not today's.
    versions = set(stored["model_version"].astype(str))
    numbers = numbers[numbers["model_version"].astype(str).isin(versions)]

    quotes = quotes.merge(
        stored[["game_id", "market", "season", "week"]].drop_duplicates(),
        on=["game_id", "market"], how="left", suffixes=("", "_signal"),
    )
    replayed = signalling.form_signals(numbers, quotes)
    return _compare(period, "signals", stored, replayed, SIGNAL_COLUMNS)


def replay_grades(store: Store, period: str) -> Replay:
    """Recompute the period's grades from the record."""
    stored_signals = store.read("signals")
    stored_grades = store.read("grades")
    if stored_signals.empty or stored_grades.empty:
        return Replay(period, "grades", 0, 0, 0, 0, "no grades recorded")

    in_period = stored_signals[_label(stored_signals) == period]
    stored = stored_grades[stored_grades["signal_id"].isin(set(in_period["signal_id"]))]
    if stored.empty:
        return Replay(period, "grades", 0, 0, 0, 0, "no grades in this period")

    replayed = grading.grade(in_period, store.read("snapshots"), store.read("games"))
    return _compare(period, "grades", stored, replayed, GRADE_COLUMNS)


def replay_statistics(store: Store, period: str) -> Replay:
    """Check the published scorecard follows from the record."""
    signals = store.read("signals")
    grades = store.read("grades")
    if signals.empty or grades.empty:
        return Replay(period, "statistics", 0, 0, 0, 0, "nothing graded yet")

    in_period = signals[_label(signals) == period]
    frame = sc.graded_frame(in_period, grades)
    if frame.empty:
        return Replay(period, "statistics", 0, 0, 0, 0, "no graded signals in period")

    published = sc.by_selection(frame)
    replayed_grades = grading.grade(in_period, store.read("snapshots"), store.read("games"))
    replayed = sc.by_selection(sc.graded_frame(in_period, replayed_grades))

    if replayed.empty:
        return Replay(period, "statistics", len(published), 0, 0, len(published),
                      "statistics could not be recomputed")

    merged = published.merge(replayed, on="selection", suffixes=("_pub", "_new"))
    metrics = ["beat_rate", "mean_clv", "median_clv", "graded"]
    bad = []
    for metric in metrics:
        left = pd.to_numeric(merged[f"{metric}_pub"], errors="coerce")
        right = pd.to_numeric(merged[f"{metric}_new"], errors="coerce")
        differs = (left - right).abs() > TOLERANCE
        differs = differs & ~(left.isna() & right.isna())
        bad.extend(merged.loc[differs, "selection"].tolist())
    rows = len(merged) * len(metrics)
    return Replay(period, "statistics", rows, rows - len(bad), len(bad), 0,
                  "recomputed from the replayed grades")


def _compare(period: str, scope: str, stored: pd.DataFrame, replayed: pd.DataFrame,
             columns: tuple[str, ...]) -> Replay:
    if replayed is None or replayed.empty:
        return Replay(period, scope, len(stored), 0, 0, len(stored),
                      "replay produced nothing")

    left = stored.set_index("signal_id")
    right = replayed.set_index("signal_id")
    missing = [i for i in left.index if i not in right.index]
    shared = [i for i in left.index if i in right.index]

    mismatched = 0
    notes: list[str] = []
    for column in columns:
        if column == "signal_id" or column not in left or column not in right:
            continue
        a, b = left.loc[shared, column], right.loc[shared, column]
        numeric_a = pd.to_numeric(a, errors="coerce")
        numeric_b = pd.to_numeric(b, errors="coerce")
        if numeric_a.notna().all() and numeric_b.notna().all():
            differs = (numeric_a - numeric_b).abs() > TOLERANCE
        else:
            differs = a.astype(str) != b.astype(str)
        count = int(differs.sum())
        if count:
            mismatched += count
            notes.append(f"{column}: {count}")

    return Replay(
        period, scope, len(stored), len(shared) - min(mismatched, len(shared)),
        mismatched, len(missing),
        "; ".join(notes) if notes else "exact match",
    )


def verify(store: Store | None = None, *, sample: int = 3, seed: int | None = None
           ) -> pd.DataFrame:
    """Replay a random sample of periods.

    Random rather than "the last few": a bug that only touches old rows is
    exactly the bug a tracker that always checks the newest week never finds.
    """
    store = store or Store.open()
    available = periods(store)
    if not available:
        return pd.DataFrame(columns=["period", "scope", "rows", "matched",
                                     "mismatched", "missing", "clean", "detail"])
    rng = np.random.default_rng(seed)
    chosen = sorted(
        rng.choice(available, size=min(sample, len(available)), replace=False).tolist()
    )
    rows = []
    for period in chosen:
        for replay in (replay_signals(store, period), replay_grades(store, period),
                       replay_statistics(store, period)):
            rows.append({**vars(replay), "clean": replay.clean})
    out = pd.DataFrame(rows)
    dirty = out[~out["clean"]]
    if not dirty.empty:
        LOG.error("%d replays did not reproduce", len(dirty))
    return out
