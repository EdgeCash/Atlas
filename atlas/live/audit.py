"""Track 2: making every row in the record traceable.

Two things are needed before anyone should believe a number in the scorecard:
an identifier for each opinion that cannot drift, and a log of every process
that touched the record.

The identifier is a **deterministic UUID5** over ``(game, market, book)``. It
is a real UUID, so it is globally unique and obviously an identifier rather
than a line of data; and it is deterministic, so rebuilding the record from
its inputs produces the same ids - which is what makes Track 6 possible at
all. A random UUID4 would satisfy the first property and destroy the second.

The log is ``tracking/runs.csv``: one append-only row per tracker invocation,
carrying what ran, when, against which provider, at which commit, and what it
changed. Every signal names the run that created it, so any row in the record
can be traced back to the process that wrote it.
"""

from __future__ import annotations

import os
import subprocess
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

import pandas as pd

from atlas.live.store import Store
from atlas.util import get_logger

LOG = get_logger(__name__)

#: Fixed namespace for Atlas signal ids. Never change it: every id in the
#: record derives from it, and a new namespace silently re-issues all of them.
SIGNAL_NAMESPACE = uuid.UUID("a71a5000-0000-5000-8000-000000000001")


def signal_uuid(game_id: object, market: str, book: str) -> str:
    """The immutable identifier for one opinion.

    Deliberately excludes the line, the timestamp and the model version: a
    second poll must not mint a new id because the number moved half a point,
    and a weekly refit must not let Atlas restate a call it has already made.
    """
    return str(uuid.uuid5(SIGNAL_NAMESPACE, f"{game_id}|{market}|{book}"))


def code_version() -> str:
    """The commit the tracker ran at, so a run can be reproduced exactly."""
    override = os.environ.get("ATLAS_CODE_VERSION")
    if override:
        return override
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=10, check=False,
        )
        return out.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):  # pragma: no cover - defensive
        return "unknown"


@dataclass
class Run:
    """One tracker invocation, from the first fetch to the last write."""

    command: str
    provider: str = ""
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    started_at: str = field(
        default_factory=lambda: datetime.now(UTC).replace(microsecond=0).isoformat()
    )
    quotes: int = 0
    snapshots_added: int = 0
    signals_added: int = 0
    grades_added: int = 0
    exceptions: int = 0
    alerts: int = 0
    status: str = "running"
    detail: str = ""

    def finish(self, store: Store, status: str = "ok", detail: str = "") -> str:
        self.status = status
        self.detail = detail
        row = {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "finished_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
            "command": self.command,
            "provider": self.provider,
            "code_version": code_version(),
            "quotes": self.quotes,
            "snapshots_added": self.snapshots_added,
            "signals_added": self.signals_added,
            "grades_added": self.grades_added,
            "exceptions": self.exceptions,
            "alerts": self.alerts,
            "status": status,
            "detail": detail,
        }
        store.upsert("runs", pd.DataFrame([row]))
        LOG.info("run %s %s: %s", self.run_id[:8], status, detail or "")
        return self.run_id


def trace(store: Store, signal_id: str) -> dict:
    """Everything the record knows about one signal, for an audit.

    A scorecard nobody can drill into is a claim, not evidence.
    """
    signals = store.read("signals")
    row = signals[signals["signal_id"].astype(str) == str(signal_id)]
    if row.empty:
        return {}
    signal = row.iloc[0].to_dict()

    grades = store.read("grades")
    grade = grades[grades["signal_id"].astype(str) == str(signal_id)]

    snapshots = store.read("snapshots")
    history = snapshots[
        (snapshots["game_id"].astype(str) == str(signal["game_id"]))
        & (snapshots["book"].astype(str) == str(signal["book"]))
        & (snapshots["market"].astype(str) == str(signal["market"]))
    ].sort_values("captured_at")

    runs = store.read("runs")
    run = runs[runs["run_id"].astype(str) == str(signal.get("run_id"))]

    return {
        "signal": signal,
        "grade": grade.iloc[0].to_dict() if not grade.empty else None,
        "line_history": history,
        "run": run.iloc[0].to_dict() if not run.empty else None,
    }
