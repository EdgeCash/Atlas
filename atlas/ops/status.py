"""What Atlas knows about its own state.

One model, read by three things: the operator's ``python -m atlas.ops
status``, the public ``/status.html`` page, and the health check. They agree
because they share this, rather than each computing freshness their own way
and drifting.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from atlas.ops import freshness, health, schedule
from atlas.util import get_logger

LOG = get_logger(__name__)


@dataclass(frozen=True)
class Row:
    """One line on the status page."""

    label: str
    value: str
    note: str = ""
    ok: bool = True


@dataclass
class Summary:
    generated_at: datetime
    mode: str
    freshness_rows: list[Row] = field(default_factory=list)
    tracker_rows: list[Row] = field(default_factory=list)
    provider_rows: list[Row] = field(default_factory=list)
    checks: list = field(default_factory=list)

    @property
    def healthy(self) -> bool:
        return not health.failing(self.checks)

    def as_text(self) -> str:
        lines = [f"Atlas status — {self.mode}", ""]
        for title, rows in (("Freshness", self.freshness_rows),
                            ("Providers", self.provider_rows),
                            ("Tracker", self.tracker_rows)):
            lines.append(title)
            for row in rows:
                mark = " " if row.ok else "!"
                lines.append(f" {mark} {row.label:22} {row.value}"
                             + (f"   ({row.note})" if row.note else ""))
            lines.append("")
        lines.append(health.report(self.checks))
        return "\n".join(lines)


def _stamp(event_name: str) -> tuple[str, str, bool]:
    """A timestamp, its age and whether it is acceptable."""
    from atlas.site.html import stamp

    event = freshness.last(event_name)
    if event is None:
        return "never", "no successful run recorded", False
    age = event.age_hours
    note = f"{age:.1f} hours ago" if age >= 1 else f"{age * 60:.0f} minutes ago"
    limits = {"poll": health.POLL_MAX_HOURS, "heavy": health.HEAVY_MAX_HOURS,
              "build": health.BOARD_MAX_HOURS, "social": health.SOCIAL_MAX_HOURS}
    return stamp(event.at), note, age <= limits.get(event_name, 24.0)


def summary() -> Summary:
    window = schedule.game_day()
    mode = (f"{window.name}, polling every {schedule.GAME_DAY_MINUTES} minutes"
            if window else
            f"ordinary schedule, polling every {schedule.POLL_MINUTES} minutes")

    rows = []
    for label, event in (("Last heavy refresh", "heavy"),
                         ("Last market poll", "poll"),
                         ("Board published", "build"),
                         ("Social assets", "social")):
        value, note, ok = _stamp(event)
        rows.append(Row(label, value, note, ok))

    return Summary(generated_at=datetime.now(UTC), mode=mode,
                   freshness_rows=rows, tracker_rows=_tracker_rows(),
                   provider_rows=_provider_rows(), checks=health.run())


def _tracker_rows() -> list[Row]:
    """Signals, grades and quotes, read straight from the tracking store."""
    from atlas.live.store import Store

    try:
        store = Store.open()
        signals = store.read("signals")
        grades = store.read("grades")
        snapshots = store.read("snapshots")
        numbers = store.read("numbers")
    except (FileNotFoundError, OSError) as exc:
        LOG.warning("tracker unreadable: %s", exc)
        return [Row("Tracker", "unavailable", str(exc), ok=False)]

    pending = max(len(signals) - len(grades), 0)
    return [
        Row("Signals recorded", f"{len(signals):,}",
            "opinions published before kickoff"),
        Row("Signals graded", f"{len(grades):,}",
            "games played and scored against the entry line"),
        Row("Awaiting a result", f"{pending:,}",
            "graded once the game is complete"),
        Row("Line observations", f"{len(snapshots):,}",
            "appended only when a number changes"),
        Row("Atlas numbers live", f"{len(numbers):,}",
            "one per scheduled game and market"),
    ]


def _provider_rows() -> list[Row]:
    """One row per source, with what it last did.

    Deliberately honest about depth: a single provider is a real limitation
    and the status page is exactly where it should be visible rather than
    only in a caution on a card.
    """
    from atlas.live.store import Store

    rows = []
    try:
        runs = Store.open().read("runs")
    except (FileNotFoundError, OSError):
        runs = None

    if runs is not None and len(runs):
        latest = runs.iloc[-1]
        ok = str(latest.get("status", "")).lower() in ("ok", "success", "passing")
        rows.append(Row("Market provider", str(latest.get("provider", "espn")),
                        f"last run {latest.get('status', 'unknown')}, "
                        f"{latest.get('quotes', 0)} quotes", ok=ok))
    else:
        rows.append(Row("Market provider", "espn", "no runs recorded", ok=False))

    rows.append(Row("Books quoting", "1",
                    "a known limitation — market depth carries no information "
                    "until a second provider is added", ok=False))
    rows.append(Row("Team metadata", "ESPN scoreboard",
                    "venue, broadcast, records, ranks and crests, cached 6 hours"))
    rows.append(Row("Warehouse", "point-in-time, nine seasons",
                    "opponent-adjusted efficiency, ratings, talent and context"))
    return rows
