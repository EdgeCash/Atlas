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
from atlas.live.store import SCHEMA, Store
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


#: What names a model's number for a game; with ``refreshed_at``, one refresh of it.
NUMBER_KEY = ["game_id", "market", "model_version"]


def _key(frame: pd.DataFrame, columns: list[str]) -> pd.Series:
    return frame[columns].astype(str).agg("|".join, axis=1) if len(frame) else pd.Series(dtype=str)


def in_effect(numbers: pd.DataFrame, signals: pd.DataFrame) -> pd.DataFrame:
    """For each signal, the number it was formed from: the latest refresh of its game, market and model
    version at or before the signal was created. When the record of a number begins after the signal
    (a table written before refreshes were kept), its earliest refresh. One row per signal, the numbers'
    columns and ``signal_id``; a signal with no number for its version has no row."""
    columns = ["signal_id", *SCHEMA["numbers"]]
    if numbers.empty or signals.empty:
        return pd.DataFrame(columns=columns)
    n = numbers.assign(_k=_key(numbers, NUMBER_KEY).to_numpy(),
                       _t=pd.to_datetime(numbers["refreshed_at"], utc=True, errors="coerce").to_numpy())
    s = pd.DataFrame({"signal_id": signals["signal_id"].to_numpy(), "_k": _key(signals, NUMBER_KEY).to_numpy(),
                      "_c": pd.to_datetime(signals["created_at"], utc=True, errors="coerce").to_numpy()})
    m = s.merge(n, on="_k", how="inner").sort_values("_t", kind="stable")
    before = m[m["_t"] <= m["_c"]].drop_duplicates("signal_id", keep="last")
    after = m[~m["signal_id"].isin(set(before["signal_id"]))].drop_duplicates("signal_id", keep="first")
    return pd.concat([before, after], ignore_index=True)[columns]


def keep_history(existing: pd.DataFrame, fresh: pd.DataFrame, signals: pd.DataFrame) -> pd.DataFrame:
    """The numbers table after a refresh: every fresh row; every earlier row the refresh does not
    supersede (another model version, a game no longer scheduled); and of the rows it does supersede,
    those a signal was formed from. A number no signal used is replaced, so the table grows by about
    one row per signal, not by a table per refresh."""
    if existing.empty:
        return fresh.reindex(columns=SCHEMA["numbers"])
    full = [*NUMBER_KEY, "refreshed_at"]
    superseded = _key(existing, NUMBER_KEY).isin(set(_key(fresh, NUMBER_KEY)))
    used = set(_key(in_effect(existing, signals), full))
    keep = (~superseded) | _key(existing, full).isin(used)
    out = pd.concat([existing[keep.to_numpy()], fresh], ignore_index=True).reindex(columns=SCHEMA["numbers"])
    return out[~_key(out, full).duplicated(keep="last").to_numpy()].reset_index(drop=True)


def restore(current: pd.DataFrame, history: list[pd.DataFrame], signals: pd.DataFrame) -> pd.DataFrame:
    """Put back the numbers signals were formed from that a refresh overwrote: for each signal, the row in
    effect at its creation among every version of the table in ``history``, added when ``current`` lacks
    it. Nothing in ``current`` changes."""
    full = [*NUMBER_KEY, "refreshed_at"]
    pool = pd.concat([current, *history], ignore_index=True).reindex(columns=SCHEMA["numbers"])
    pool = pool[~_key(pool, full).duplicated(keep="first").to_numpy()]
    needed = in_effect(pool, signals).drop(columns="signal_id")
    missing = needed[~_key(needed, full).isin(set(_key(current, full))).to_numpy()]
    missing = missing[~_key(missing, full).duplicated().to_numpy()]
    return pd.concat([current, missing], ignore_index=True).reindex(columns=SCHEMA["numbers"])


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
    # Replay each signal with the number *it* was formed from: the version it names, not today's and not
    # every version any signal in the period names (a week with signals from two refits replayed every
    # game twice and took every poll down on 26 September 2026), and the refresh of that version in
    # effect when it was formed, not the latest (new results change every number under one version: on
    # 27 September a refresh left 31 of week 5's signals unreproducible).
    used = in_effect(numbers, stored)
    if used.empty:
        return Replay(period, "signals", len(stored), 0, 0, len(stored), "no numbers to replay against")

    quotes = quotes.merge(
        stored[["game_id", "market", "season", "week"]].drop_duplicates(),
        on=["game_id", "market"], how="left", suffixes=("", "_signal"),
    )
    books = stored.set_index("signal_id")[["game_id", "market", "book"]]
    quote_key = _key(quotes, ["game_id", "market", "book"])
    parts = []
    # One refresh of one version names each game and market once: replay each such group against the
    # quotes its own signals were formed from, so no signal is replayed with another's number.
    for _, rows in used.groupby(["refreshed_at", "model_version"], sort=True, dropna=False):
        wanted = set(_key(books.loc[rows["signal_id"]], ["game_id", "market", "book"]))
        part = signalling.form_signals(rows.drop(columns="signal_id").drop_duplicates(["game_id", "market"]),
                                       quotes[quote_key.isin(wanted).to_numpy()])
        if part is not None and not part.empty:
            parts.append(part)
    replayed = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
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

    # One row per id on each side. A replay that produced the same id twice is
    # itself a mismatch to report, never a reason to stop the run: the poll
    # that calls this has already captured the market, and a crash here
    # discards that capture with the commit that never follows.
    left = stored.drop_duplicates("signal_id").set_index("signal_id")
    right_all = replayed.drop_duplicates("signal_id").set_index("signal_id")
    duplicated = int(len(replayed) - len(right_all))
    missing = [i for i in left.index if i not in right_all.index]
    shared = [i for i in left.index if i in right_all.index]
    right = right_all.reindex(shared)

    mismatched = duplicated
    notes: list[str] = [f"replayed {duplicated} ids twice"] if duplicated else []
    for column in columns:
        if column == "signal_id" or column not in left or column not in right:
            continue
        a, b = left.loc[shared, column], right.loc[shared, column]
        numeric_a = pd.to_numeric(a, errors="coerce")
        numeric_b = pd.to_numeric(b, errors="coerce")
        if numeric_a.notna().all() and numeric_b.notna().all():
            differs = (numeric_a.to_numpy() - numeric_b.to_numpy()).__abs__() > TOLERANCE
        else:
            differs = a.astype(str).to_numpy() != b.astype(str).to_numpy()
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
