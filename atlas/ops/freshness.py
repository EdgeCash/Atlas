"""When each part of Atlas last succeeded.

One JSON file, appended to by every scheduled task and read by the build. It
answers the only question a reader can ask about a static site: *how old is
this?*

The rule this module exists to enforce: **a timestamp on a page is the time of
the last successful refresh of that thing, never the time the page was
built.** A rebuild that ran against a failed poll must not advertise itself as
fresh market data, so the market stamp comes from the poll's record and not
from the build's clock.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from atlas import config
from atlas.util import get_logger

LOG = get_logger(__name__)

#: The events Atlas records. Anything not in here is a typo.
EVENTS = ("heavy", "poll", "social", "build")

#: How many past runs to keep per event. Enough to see a pattern of failures
#: on the status page, small enough that the file stays hand-readable.
HISTORY = 50


def path() -> Path:
    return config.paths().data / "ops" / "freshness.json"


@dataclass(frozen=True)
class Event:
    """One recorded run."""

    name: str
    at: datetime
    ok: bool
    detail: str = ""
    extra: dict | None = None

    @property
    def age(self) -> timedelta:
        return datetime.now(UTC) - self.at

    @property
    def age_hours(self) -> float:
        return self.age.total_seconds() / 3600

    def to_dict(self) -> dict:
        return {"name": self.name, "at": self.at.isoformat(), "ok": self.ok,
                "detail": self.detail, **(self.extra or {})}

    @classmethod
    def from_dict(cls, name: str, row: dict) -> Event:
        extra = {k: v for k, v in row.items()
                 if k not in ("name", "at", "ok", "detail")}
        return cls(name=name, at=datetime.fromisoformat(row["at"]),
                   ok=bool(row.get("ok", True)), detail=row.get("detail", ""),
                   extra=extra or None)


def load() -> dict:
    target = path()
    if not target.exists():
        return {"last": {}, "history": []}
    try:
        return json.loads(target.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        # A corrupt provenance file must not stop a build. A site with no
        # timestamps is recoverable; a site that will not build is not.
        LOG.warning("freshness file unreadable (%s); starting fresh", exc)
        return {"last": {}, "history": []}


def record(name: str, *, ok: bool = True, detail: str = "", **extra) -> Event:
    """Write one run's outcome. Atomic, because a poll can be interrupted."""
    if name not in EVENTS:
        raise ValueError(f"unknown event {name!r}; expected one of {EVENTS}")
    event = Event(name=name, at=datetime.now(UTC), ok=ok, detail=detail,
                  extra=extra or None)
    state = load()
    row = event.to_dict()
    state.setdefault("last", {})[name] = row
    if ok:
        # `last_ok` is what a page stamp reads. A failed run is recorded so an
        # operator can see it, and is deliberately not allowed to age a
        # timestamp forward - a reader must never be told information is
        # current because a refresh was *attempted*.
        state.setdefault("last_ok", {})[name] = row
    state.setdefault("history", []).insert(0, row)
    state["history"] = state["history"][:HISTORY * len(EVENTS)]
    _write(state)
    LOG.info("freshness: %s %s%s", name, "ok" if ok else "FAILED",
             f" ({detail})" if detail else "")
    return event


def last(name: str, *, successful: bool = True) -> Event | None:
    """The most recent run of ``name``, successful ones only by default."""
    state = load()
    row = state.get("last_ok" if successful else "last", {}).get(name)
    return Event.from_dict(name, row) if row else None


def history(name: str | None = None, limit: int = 20) -> list[Event]:
    rows = load().get("history", [])
    events = [Event.from_dict(r["name"], r) for r in rows if "name" in r]
    if name:
        events = [e for e in events if e.name == name]
    return events[:limit]


def _write(state: dict) -> None:
    target = path()
    target.parent.mkdir(parents=True, exist_ok=True)
    # Written through a temporary file in the same directory: a poll killed
    # mid-write would otherwise leave a truncated JSON file that every later
    # build has to recover from.
    handle, tmp = tempfile.mkstemp(dir=target.parent, suffix=".tmp")
    try:
        with os.fdopen(handle, "w") as fh:
            json.dump(state, fh, indent=2, sort_keys=True)
        os.replace(tmp, target)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
