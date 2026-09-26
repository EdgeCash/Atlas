"""The watchdog: tell someone when the site goes stale.

    python -m atlas.ops.watchdog     # needs GH_TOKEN and GITHUB_REPOSITORY; run by watchdog.yml

The health checks (:mod:`atlas.ops.health`) run inside every build, which is
exactly where they cannot see the two failures that matter most: no build at
all (GitHub stopped starting the scheduled runs on 25 September 2026, five
hours without a poll), and builds that fail before they commit the record (a
forbidden word blocked every deploy the same evening). Both leave the
committed freshness stamps getting older, and nobody was told.

This runs on its own schedule, reads the stamps committed on main, and keeps
one GitHub issue in step with the answer:

* stale, and no issue open: open one (GitHub notifies the owner by email and
  in its app);
* still stale: update that issue's body quietly - one notification per
  outage, not one an hour;
* healthy again: comment when and close it.

It alarms on the health check's blocking failures, with its generous limits
(a poll older than two hours, the board three, the heavy refresh a day), and
on one signal the stamps cannot show quickly: the last three site-poll runs
that did any work all failing. A run the gate turned away succeeds, so this
counts only real attempts. On a game day that is about 45 minutes, not two
hours.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from atlas.ops import health
from atlas.util import get_logger

LOG = get_logger(__name__)

LABEL = "site-stale"
TITLE = "Atlas site is stale"
#: Consecutive failed site-poll runs that alarm on their own.
FAILED_RUNS = 3

Gh = Callable[[Sequence[str]], str]


def gh(args: Sequence[str]) -> str:
    """The GitHub CLI, as the runner provides it. Raises on failure."""
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


@dataclass(frozen=True)
class Verdict:
    alarm: bool
    reasons: tuple[str, ...]


def evaluate(checks: list[health.Check], conclusions: Sequence[str] | None) -> Verdict:
    """``conclusions`` are the most recent completed site-poll runs, newest
    first; None when they could not be read, which never alarms by itself."""
    reasons = [f"{c.name}: {c.detail}" for c in checks if not c.ok and c.blocking]
    recent = list(conclusions or [])[:FAILED_RUNS]
    if len(recent) == FAILED_RUNS and all(c == "failure" for c in recent):
        reasons.append(f"the last {FAILED_RUNS} site-poll runs all failed")
    return Verdict(bool(reasons), tuple(reasons))


def recent_poll_conclusions(run: Gh) -> list[str] | None:
    """The newest completed site-poll runs' conclusions. A run the gate turned
    away is a success, so failures here are real attempts."""
    try:
        out = run(["run", "list", "--workflow", "site-poll.yml", "--status", "completed",
                   "--limit", str(FAILED_RUNS), "--json", "conclusion"])
        return [r["conclusion"] for r in json.loads(out)]
    except Exception as exc:  # noqa: BLE001 - an unreadable list never alarms by itself
        LOG.warning("could not read recent site-poll runs: %s", exc)
        return None


def body(checks: list[health.Check], verdict: Verdict, now: datetime) -> str:
    lines = [
        f"The watchdog found the live site stale at {now:%Y-%m-%d %H:%M} UTC.",
        "",
        *[f"- **{r}**" for r in verdict.reasons],
        "",
        "Full health check, from the freshness stamps committed on main:",
        "",
        "```",
        health.report(checks),
        "```",
        "",
        "Where to look: Actions -> site poll and site heavy, the newest failed run. "
        "A run that stops at \"Audit the built site\" is a forbidden word on a page; one that "
        "never started is GitHub not delivering the schedule. This issue closes itself when the "
        "check passes again, and its body is refreshed each hour while it is open.",
    ]
    return "\n".join(lines) + "\n"


def open_issue(run: Gh) -> int | None:
    out = run(["issue", "list", "--label", LABEL, "--state", "open", "--json", "number", "--limit", "1"])
    rows = json.loads(out)
    return int(rows[0]["number"]) if rows else None


def act(verdict: Verdict, text: str, run: Gh, *, now: datetime, assignee: str | None = None) -> str:
    """Bring the issue in step with the verdict. Returns what it did."""
    number = open_issue(run)
    if verdict.alarm and number is None:
        run(["label", "create", LABEL, "--color", "B60205", "--force",
             "--description", "The live site is stale; opened and closed by the watchdog"])
        args = ["issue", "create", "--title", TITLE, "--label", LABEL, "--body", text]
        try:
            run([*args, *(["--assignee", assignee] if assignee else [])])
        except subprocess.CalledProcessError:
            if not assignee:
                raise
            run(args)                       # an owner that cannot be assigned still gets an issue
        return "opened"
    if verdict.alarm:
        run(["issue", "edit", str(number), "--body", text])
        return "updated"
    if number is not None:
        run(["issue", "comment", str(number), "--body",
             f"Healthy again at {now:%Y-%m-%d %H:%M} UTC: every blocking check passes. Closing."])
        run(["issue", "close", str(number)])
        return "closed"
    return "healthy"


def main(run: Gh = gh, now: datetime | None = None) -> int:
    now = now or datetime.now(UTC)
    checks = health.run()
    print(health.report(checks))
    verdict = evaluate(checks, recent_poll_conclusions(run))
    done = act(verdict, body(checks, verdict, now), run, now=now,
               assignee=os.environ.get("ALERT_ASSIGNEE") or None)
    LOG.info("watchdog: %s%s", done, f" ({'; '.join(verdict.reasons)})" if verdict.reasons else "")
    return 0


if __name__ == "__main__":
    sys.exit(main())
