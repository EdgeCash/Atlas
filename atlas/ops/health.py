"""Is Atlas actually running?

A static site fails quietly. The board keeps serving, the cards keep
rendering, and the only symptom of a poller that died on Thursday is a market
number that stopped moving. These checks turn that into an exit code.

Thresholds are deliberately generous. An alert that fires on a single missed
poll is an alert an operator learns to ignore, and an ignored alert is worse
than none.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from atlas.ops import freshness, schedule
from atlas.util import get_logger

LOG = get_logger(__name__)

#: No successful poll in this many hours is a failure. Two hours is two missed
#: hourly polls, or eight missed game-day polls.
POLL_MAX_HOURS = 2.0

#: No successful heavy refresh in a day means the projections are stale.
HEAVY_MAX_HOURS = 24.0

#: The board's own stamp. Three hours, because a reader looking at a board
#: stamped four hours ago on a Saturday is looking at the wrong market.
BOARD_MAX_HOURS = 3.0

#: Social assets are a publishing convenience, not information, so they get a
#: longer rope and only ever warn.
SOCIAL_MAX_HOURS = 48.0


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    blocking: bool
    detail: str

    @property
    def status(self) -> str:
        if self.ok:
            return "ok"
        return "FAIL" if self.blocking else "warn"


def _age_check(name: str, event_name: str, limit: float, *,
               blocking: bool) -> Check:
    event = freshness.last(event_name)
    if event is None:
        return Check(name, False, blocking, f"no successful {event_name} recorded")
    age = event.age_hours
    ok = age <= limit
    return Check(name, ok, blocking,
                 f"{age:.1f}h ago, limit {limit:.0f}h"
                 + (f" — {event.detail}" if event.detail else ""))


def _failure_streak(event_name: str, limit: int = 3) -> Check:
    """Recent runs that failed. A run that fails and then succeeds is noise;
    three in a row is a provider that has stopped answering."""
    recent = freshness.history(event_name, limit=limit)
    failing = [e for e in recent if not e.ok]
    ok = len(failing) < limit or not recent
    return Check(f"{event_name} provider", ok, blocking=False,
                 detail=f"{len(failing)} of the last {len(recent)} runs failed")


def run(moment: datetime | None = None) -> list[Check]:
    checks = [
        _age_check("poll", "poll", POLL_MAX_HOURS, blocking=True),
        _age_check("heavy refresh", "heavy", HEAVY_MAX_HOURS, blocking=True),
        _age_check("board", "build", BOARD_MAX_HOURS, blocking=True),
        _age_check("social assets", "social", SOCIAL_MAX_HOURS, blocking=False),
        _failure_streak("poll"),
        _failure_streak("heavy"),
    ]
    window = schedule.game_day(moment)
    checks.append(Check(
        "mode", True, False,
        f"{window.name}, polling every {schedule.GAME_DAY_MINUTES} minutes"
        if window else
        f"ordinary schedule, polling every {schedule.POLL_MINUTES} minutes",
    ))
    return checks


def report(checks: list[Check]) -> str:
    lines = ["Atlas health"]
    for check in checks:
        lines.append(f"  [{check.status:>4}] {check.name}: {check.detail}")
    failing = [c for c in checks if not c.ok and c.blocking]
    warning = [c for c in checks if not c.ok and not c.blocking]
    lines.append("")
    lines.append(f"{len(failing)} failing, {len(warning)} warning, "
                 f"{sum(1 for c in checks if c.ok)} ok")
    return "\n".join(lines)


def failing(checks: list[Check]) -> bool:
    return any(not c.ok and c.blocking for c in checks)
