"""Atlas live operations.

    python -m atlas.ops heavy     # 04:00 ET - warehouse, model, every page
    python -m atlas.ops poll      # hourly (15 min on game days) - market only
    python -m atlas.ops social    # 05:00 ET - the featured card assets
    python -m atlas.ops backup    # copy the live record, then read it back
    python -m atlas.ops analytics # traffic, from the web server's access log
    python -m atlas.ops health    # the check; non-zero exit when failing
    python -m atlas.ops status    # what the status page will say
    python -m atlas.ops crontab   # print the schedule

Every task records its outcome through :mod:`atlas.ops.freshness`, and every
task is safe to run twice. A failed task records the failure and exits
non-zero without advancing any timestamp a reader can see - that is the whole
point of the separation between ``last`` and ``last_ok``.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from atlas.ops import freshness, health, schedule
from atlas.util import get_logger

LOG = get_logger(__name__)


def _run(label: str, args: list[str]) -> tuple[bool, str]:
    """One subprocess step. Returns (ok, detail) rather than raising, because
    a heavy refresh that fails at step three should still record steps one and
    two and still leave the site standing."""
    LOG.info("%s: %s", label, " ".join(args))
    started = time.monotonic()
    result = subprocess.run([sys.executable, "-m", *args], check=False)
    took = time.monotonic() - started
    if result.returncode != 0:
        return False, f"{label} exited {result.returncode} after {took:.0f}s"
    return True, f"{label} in {took:.0f}s"


def heavy(*, skip_warehouse: bool = False) -> int:
    """Track 1. Rebuild everything.

    Order matters: the warehouse feeds the model, the model feeds the cards,
    and the market snapshot has to be captured before the pages are written or
    the board advertises a market number older than the one in the tracker.
    """
    steps = []
    if not skip_warehouse:
        steps.append(("warehouse", ["atlas.warehouse.build", "--include-scheduled"]))
    steps += [
        ("model", ["atlas.live", "refresh", "--no-rebuild"]),
        ("market", ["atlas.live", "run"]),
        ("site", ["atlas.site.build"]),
    ]
    details = []
    for label, args in steps:
        ok, detail = _run(label, args)
        details.append(detail)
        if not ok:
            freshness.record("heavy", ok=False, detail=detail)
            LOG.error("heavy refresh failed: %s", detail)
            return 1
    freshness.record("heavy", detail="; ".join(details))
    # The market moved as part of this, so the poll stamp advances too - a
    # reader should not be told the market is an hour old when the heavy
    # refresh just captured it.
    freshness.record("poll", detail="captured during the heavy refresh")
    return 0


def poll(*, force: bool = False) -> int:
    """Track 2 and 3. Market only, no rebuild.

    The cron entry fires every fifteen minutes and this decides whether the
    minute is a poll minute, so one schedule covers both cadences. Off a game
    day, fourteen of every fifteen invocations do nothing and cost no provider
    request.
    """
    now = datetime.now(schedule.EASTERN)
    if not force and not schedule.should_poll(now):
        LOG.info("not a poll minute (%s, every %dm); nothing to do",
                 now.strftime("%H:%M ET"), schedule.poll_interval_minutes(now))
        return 0

    window = schedule.game_day(now)
    ok, detail = _run("market", ["atlas.live", "run"])
    if not ok:
        freshness.record("poll", ok=False, detail=detail)
        return 1

    # A poll refreshes the market on the pages without touching the warehouse
    # or the model. The projections on a card are from the heavy refresh; only
    # the market numbers and the board's stamp move.
    built, build_detail = _run("site", ["atlas.site.build", "--no-social"])
    if not built:
        freshness.record("poll", ok=False, detail=build_detail)
        return 1

    freshness.record("poll", detail=detail,
                     mode=window.name if window else "ordinary")
    return 0


def backup_and_verify(*, keep: int = 30) -> int:
    """Track 3. Copy the live record, read the copy back, prune the old ones.

    The verify step is not optional and does not run separately: a backup
    nobody has restored is a hypothesis, and the cheapest moment to find out
    it is wrong is immediately.
    """
    from atlas.ops import backup as backups

    created = backups.create()
    problems = backups.verify(created)
    if problems:
        for problem in problems:
            LOG.error("backup verification: %s", problem)
        return 1
    backups.prune(keep=keep)
    print(backups.summary())
    return 0


def traffic(logs: list | None, *, top: int = 10) -> int:
    """Track 2. Traffic from the access log. No client-side anything."""
    from atlas import config
    from atlas.ops import analytics

    paths = [p for p in (logs or []) if p.exists()]
    if not paths:
        print("no access logs given — pass --access-log /var/log/atlas/access.log")
        return 1
    site = config.paths().root / "site"
    grades = analytics.card_grades(site) if site.exists() else {}
    print(analytics.report(analytics.read(paths, grades=grades), top=top))
    return 0


def social() -> int:
    """Track 4. The featured card assets, from the cards already published.

    The build records the ``social`` stamp itself, because only the build
    knows how many files it actually produced. This records a failure if the
    build never got that far.
    """
    ok, detail = _run("social", ["atlas.site.build"])
    if not ok:
        freshness.record("social", ok=False, detail=detail)
        return 1
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(description="Atlas live operations")
    ap.add_argument("command", choices=["heavy", "poll", "social", "health",
                                        "status", "crontab", "backup",
                                        "analytics"])
    ap.add_argument("--force", action="store_true",
                    help="poll even when this minute is not a poll minute")
    ap.add_argument("--skip-warehouse", action="store_true",
                    help="heavy refresh without rebuilding the warehouse")
    ap.add_argument("--root", default="/srv/atlas", help="crontab: repo path")
    ap.add_argument("--logs", default="/var/log/atlas", help="crontab: log path")
    ap.add_argument("--keep", type=int, default=30,
                    help="backup: how many to retain")
    ap.add_argument("--access-log", type=Path, action="append", default=None,
                    help="analytics: an access log; repeat for several")
    ap.add_argument("--top", type=int, default=10,
                    help="analytics: rows per table")
    args = ap.parse_args()

    if args.command == "heavy":
        raise SystemExit(heavy(skip_warehouse=args.skip_warehouse))
    if args.command == "poll":
        raise SystemExit(poll(force=args.force))
    if args.command == "social":
        raise SystemExit(social())
    if args.command == "backup":
        raise SystemExit(backup_and_verify(keep=args.keep))
    if args.command == "analytics":
        raise SystemExit(traffic(args.access_log, top=args.top))
    if args.command == "crontab":
        print(schedule.crontab(root=args.root, logs=args.logs))
        return
    if args.command == "status":
        from atlas.ops import status

        print(status.summary().as_text())
        return

    checks = health.run()
    print(health.report(checks))
    raise SystemExit(1 if health.failing(checks) else 0)


if __name__ == "__main__":
    main()
