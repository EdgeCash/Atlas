"""The live step's audit trail: every call it makes to the venue, and every order it declined, as it happened.

The venue's Rulebook (5.2(h)) asks a participant's automated system for an
electronic audit trail "capturing order entry, modification, cancellation,
and execution timestamps sufficient to reconstruct all trading activity".
The ledger (`atlas/polymarket/orders.py`) is a row per order, as the owner
reads it; this is the record underneath it, one event per line of what
happened:

* ``balance`` - the account read before a run places anything, and what it
  said (or the error);
* ``submit`` - an order (or, in a dry run, a preview) about to go: the exact
  request body, the path, the time it was sent;
* ``response`` - the venue's answer to it: the time it came back, the
  latency, the venue's own response in full (order id, executions, fill
  price and quantity, commission, state, the venue's timestamps), or the
  error, its HTTP status and the body the venue sent with it;
* ``refused`` - a position the step declined before the venue, and why: the
  kill switch, the throttle, a cap, the stop, the floor, no key, not armed.

A submit and its response share a ``request_id``. Orders are limits,
immediate-or-cancel, so nothing rests to be modified or cancelled later:
the venue cancels what does not fill at once, and the response records it.

Each live order's submit is written to disk before the order is sent, and
an order whose submit cannot be written is not sent: no order leaves
without its trace. The rest of a run's events are written as they
accumulate and at its end. The trail is sealed with the owner key, a file
per ISO week of the events (``tracking/polymarket_audit/``), and only ever
grows: a week's file is rewritten with the rows it held and the new ones.
The worker and the scheduled run merge their copies by ``event_id``
(`atlas/polymarket/worker.py`, `scripts/merge_tracking.py`).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from atlas import config
from atlas.owner import sealed

#: What identifies an event across copies of the trail.
KEY = ["event_id"]
#: The longest error body kept, in characters.
BODY = 4000


def path() -> Path:
    return config.paths().root / "tracking" / "polymarket_audit"


def stamp(t: datetime) -> str:
    """UTC, to the millisecond."""
    t = pd.Timestamp(t)
    t = t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")
    return t.isoformat(timespec="milliseconds")


def week_of(at: str) -> tuple[int, int]:
    iso = pd.Timestamp(at).isocalendar()
    return int(iso[0]), int(iso[1])


def load(passphrase: str, where: Path | None = None) -> pd.DataFrame:
    """Every event of the trail, oldest first."""
    rows = sealed.load(where or path(), passphrase)
    frame = pd.DataFrame(rows)
    return frame.sort_values("at", kind="stable").reset_index(drop=True) if len(frame) else frame


def plain(value):
    """A value as JSON holds it: no NaN (the sealed file refuses them; None instead), no numpy scalars, times as
    text; dicts and lists all the way down."""
    if isinstance(value, dict):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [plain(v) for v in value]
    if hasattr(value, "item") and not isinstance(value, str | bytes):
        value = value.item()
    if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
        return None
    if isinstance(value, datetime | pd.Timestamp):
        return stamp(value)
    return value


def failure(error: Exception) -> dict:
    """What an exception says that the trail keeps: its type, and for an HTTP error the status and the body."""
    response = getattr(error, "response", None)
    status = getattr(response, "status_code", None)
    try:
        body = response.text[:BODY] if response is not None else None
    except Exception:  # noqa: BLE001 - a body that cannot be read is left out
        body = None
    return {"ok": False, "error": type(error).__name__, "http_status": status, "error_body": body}


class Trail:
    """A run's events: added as they happen, sealed into their week's file on :meth:`flush`."""

    def __init__(self, passphrase: str, where: Path | None = None, *, mode: str = "", rule: str = "",
                 clock: Callable[[], datetime] | None = None):
        self.passphrase, self.where = passphrase, where or path()
        self.base = {"mode": mode, "rule": rule}
        self.clock = clock or (lambda: datetime.now(UTC))
        self.pending: list[dict] = []
        self._held: dict[Path, list[dict]] = {}

    def now(self) -> str:
        return stamp(self.clock())

    def add(self, kind: str, **fields) -> dict:
        """One event, stamped now (a response, when its answer came back) and held until the next :meth:`flush`."""
        at = fields.get("received_at") or self.now()
        event = plain({"event_id": uuid.uuid4().hex, "at": at, "kind": kind, **self.base, **fields})
        self.pending.append(event)
        return event

    def flush(self) -> int:
        """The held events sealed into their weeks' files, after the rows each file already holds. Raises when a
        file cannot be written; the events stay held for the next try. Returns how many were written."""
        if not self.pending:
            return 0
        by_file: dict[Path, list[dict]] = {}
        for event in self.pending:
            by_file.setdefault(sealed.week_file(self.where, *week_of(event["at"])), []).append(event)
        for f, events in by_file.items():
            if f not in self._held:
                self._held[f] = sealed.open_text(f.read_text(), self.passphrase) if f.exists() else []
            rows = [*self._held[f], *events]
            sealed.seal(rows, self.passphrase, f)
            self._held[f] = rows
        n = len(self.pending)
        self.pending = []
        return n


def request_id() -> str:
    return uuid.uuid4().hex


def answered(submit: dict, at: str) -> dict:
    """A response's link to its submit: the shared request id and path, the time sent (the submit's), the time
    the answer came back, and the milliseconds between."""
    latency = (pd.Timestamp(at) - pd.Timestamp(submit["at"])).total_seconds() * 1000.0
    return {"request_id": submit.get("request_id"), "path": submit.get("path"), "sent_at": submit["at"],
            "received_at": at, "latency_ms": round(latency, 1)}
