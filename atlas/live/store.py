"""Durable, diff-friendly storage for the live tracker.

The store is a directory of CSV files under ``tracking/``, not a database
file, for three reasons: it survives a container being thrown away, it is the
thing a scheduled job can commit, and a reviewer can read a diff of it. Every
write is atomic, every table has a deterministic column order and sort key,
and floats are formatted to a fixed precision so an unchanged row produces no
diff.

Tables
------
``runs``       one append-only row per tracker invocation (Track 2)
``numbers``    Atlas's number for every scheduled game, refreshed weekly
``games``      one row per game Atlas has seen
``snapshots``  append-on-change line observations (Track 2)
``signals``    immutable opinions (Track 1)
``grades``     one row per graded signal (Track 3)
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from atlas import config
from atlas.util import get_logger

LOG = get_logger(__name__)

#: Float precision written to disk. Lines move in quarter-points and CLV is a
#: difference of lines, so three decimals is more than enough and keeps an
#: unchanged row byte-identical between runs.
FLOAT_FORMAT = "%.3f"

SCHEMA: dict[str, list[str]] = {
    "runs": [
        "run_id", "started_at", "finished_at", "command", "provider",
        "code_version", "quotes", "snapshots_added", "signals_added",
        "grades_added", "exceptions", "alerts", "status", "detail",
    ],
    "numbers": [
        "game_id", "season", "week", "market", "prediction", "threshold",
        "model_version", "refreshed_at",
    ],
    "games": [
        "game_id", "season", "week", "kickoff", "home_team", "away_team",
        "home_team_id", "away_team_id", "status", "completed",
        "home_score", "away_score", "first_seen_at", "updated_at",
    ],
    "snapshots": [
        "captured_at", "game_id", "book", "market", "line", "price",
        "open_line", "open_price", "status", "last_seen_at",
    ],
    "signals": [
        "signal_id", "created_at", "run_id", "game_id", "season", "week", "market", "book",
        "open_line", "entry_line", "entry_price", "atlas_number", "disagreement",
        "direction", "selection", "model_version",
    ],
    "grades": [
        "signal_id", "graded_at", "close_line", "clv_points", "result",
        "clv_from_open", "result_from_open", "total_move", "pre_signal_move",
        "execution_flagged",
    ],
}

#: The columns that identify a row. A second write with the same key updates
#: the row rather than duplicating it.
KEYS: dict[str, list[str]] = {
    "runs": ["run_id"],
    # Keyed by model version too, so a refit adds a row rather than
    # overwriting the number a past signal was formed from. Without that
    # history a historical replay silently uses today's model.
    "numbers": ["game_id", "market", "model_version"],
    "games": ["game_id"],
    "snapshots": ["game_id", "book", "market", "line", "price"],
    "signals": ["signal_id"],
    "grades": ["signal_id"],
}

SORT: dict[str, list[str]] = {
    "runs": ["started_at", "run_id"],
    "numbers": ["season", "week", "game_id", "market", "model_version"],
    "games": ["kickoff", "game_id"],
    "snapshots": ["game_id", "market", "book", "captured_at"],
    "signals": ["created_at", "game_id", "market", "book"],
    "grades": ["graded_at", "signal_id"],
}


def tracking_dir() -> Path:
    """Where the committed tracking tables live.

    Honours ``ATLAS_TRACKING_DIR`` so a test never writes into the repo's own
    record.
    """
    override = os.environ.get("ATLAS_TRACKING_DIR")
    if override:
        return Path(override).resolve()
    return config.paths().root / "tracking"


@dataclass(frozen=True)
class Store:
    root: Path

    @classmethod
    def open(cls, root: Path | None = None) -> Store:
        path = Path(root) if root is not None else tracking_dir()
        path.mkdir(parents=True, exist_ok=True)
        return cls(path)

    def path(self, table: str) -> Path:
        if table not in SCHEMA:
            raise KeyError(f"unknown table: {table}")
        return self.root / f"{table}.csv"

    def read(self, table: str) -> pd.DataFrame:
        path = self.path(table)
        if not path.exists():
            return pd.DataFrame(columns=SCHEMA[table])
        frame = pd.read_csv(path)
        for column in SCHEMA[table]:
            if column not in frame.columns:
                frame[column] = pd.NA
        return frame[SCHEMA[table]]

    def write(self, table: str, frame: pd.DataFrame) -> Path:
        """Atomic, deterministic write. Never called with a partial table."""
        columns = SCHEMA[table]
        out = frame.reindex(columns=columns)
        sort = [c for c in SORT[table] if c in out.columns]
        out = out.sort_values(sort, kind="stable").reset_index(drop=True)

        path = self.path(table)
        tmp = path.with_suffix(".csv.tmp")
        out.to_csv(tmp, index=False, float_format=FLOAT_FORMAT, lineterminator="\n")
        os.replace(tmp, path)
        return path

    def upsert(self, table: str, rows: pd.DataFrame) -> int:
        """Insert new rows and update existing ones. Returns the rows added."""
        if rows is None or rows.empty:
            return 0
        keys = KEYS[table]
        existing = self.read(table)
        incoming = rows.reindex(columns=SCHEMA[table])

        # Concatenating onto an empty frame upcasts every float column to
        # object, which defeats float_format and writes 17 digits of noise.
        combined = incoming if existing.empty else pd.concat(
            [existing, incoming], ignore_index=True
        )
        # Last write wins, which is what an updated score or status means.
        combined = combined.drop_duplicates(subset=keys, keep="last")
        added = len(combined) - len(existing)
        self.write(table, combined)
        LOG.info("%s: %d rows in, %d new, %d total", table, len(incoming), added, len(combined))
        return added

    def append_new_only(self, table: str, rows: pd.DataFrame) -> int:
        """Insert rows whose key is not present. Existing rows are untouched.

        Signals use this: an opinion, once stated, is never revised. Rewriting
        one after seeing where the line went is the single easiest way to turn
        this system into a fiction, so the store refuses to do it.
        """
        if rows is None or rows.empty:
            return 0
        keys = KEYS[table]
        existing = self.read(table)
        incoming = rows.reindex(columns=SCHEMA[table])
        if not existing.empty:
            seen = set(map(tuple, existing[keys].astype(str).to_numpy()))
            mask = [tuple(r) not in seen for r in incoming[keys].astype(str).to_numpy()]
            incoming = incoming[mask]
        if incoming.empty:
            return 0
        combined = incoming if existing.empty else pd.concat(
            [existing, incoming], ignore_index=True
        )
        self.write(table, combined)
        LOG.info("%s: %d new rows appended", table, len(incoming))
        return len(incoming)
