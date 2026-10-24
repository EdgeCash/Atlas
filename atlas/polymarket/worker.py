"""The favorites rule as an always-on loop, off the scheduled runs.

    python -m atlas.polymarket.worker                 # every 45 seconds while a game is on, pushing the record
    python -m atlas.polymarket.worker --once          # one tick, to the terminal
    python -m atlas.polymarket.worker --no-push       # keep the record locally

The scheduled run reads the venue every fifteen minutes and takes three to
five minutes to start, and the rule's live orders go late in games, when a
limit sent that late fills nothing (``reports/favorites_backtest.md``). On
the venue's own tape a late favorite has lost about a point against its
cost, and an earlier one more; the live record is the test of the late rule. So the
rule runs here, on a machine that stays up: each tick reads the four
leagues' listings - about ten requests, fifty games a page, each game with
its moneyline's top of book and the venue's own
period and clock - takes the crossings (`favorites.take`), grades the
settled ones, writes ``tracking/favorites.csv``, hands the new positions to
the live step (`favorites.order`: nothing is sent unless its secrets say
so, and late ones only by default), grades the live ledger, and commits
and pushes what changed. It never lets git merge the record line by line:
it reads what it holds, resets to the branch, and lays its rows back over
the branch's (`sync`), so a run that wrote the same file meanwhile costs
nothing and leaves no conflict in it. The scheduled run keeps rendering the owner page
from the record it finds; set the repository variable ``FAVORITES_TAKER``
to ``worker`` so it stops taking positions itself, and the two never write
the record at once.

Everything the worker needs is in the environment the scheduled run has
(docs/POLYMARKET.md): the owner key, the venue's key, the live step's
secrets and caps, and a git remote it may push to. A tick that fails is
logged and the next one runs; the loop never stops on its own.
"""

from __future__ import annotations

import argparse
import math
import os
import re
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from atlas import config
from atlas.live.store import Store
from atlas.owner import crypto
from atlas.polymarket import favorites, match, source
from atlas.util import get_logger, offline, session

LOG = get_logger(__name__)

#: Seconds between ticks while a game is in play, and while none is.
EVERY = 45
IDLE = 180
#: Settlements (the rule's and the ledger's) are read every this many ticks, not every tick.
GRADE_EVERY = 8
#: The branch the record is pushed to; the checkout's own when unset.
BRANCH = "ATLAS_WORKER_BRANCH"
#: What the worker commits: the rule's record and the live ledger, and nothing else.
LEDGER = "tracking/polymarket_live"
FILES = ("tracking/favorites.csv", LEDGER)
#: The venue's period strings: a quarter or period by its number, overtime past the last, the half between.
_NUMBER = re.compile(r"(\d+)")


def venue_period(text, sport) -> float:
    """The period a venue's event stub says the game is in, as the scoreboard counts them: "Q4" and "End Q3"
    by their number, "OT" and "SO" one past the sport's last, "HT" the second of four; nan before the
    start, after the end, or unread."""
    s = str(text or "").strip().upper()
    final = favorites.FINAL_PERIOD.get(str(sport).lower())
    if not s or s in ("NS", "FT", "VFT", "FINAL", "ENDED", "CANCELLED", "POSTPONED"):
        return float("nan")
    if "OT" in s or s.startswith("SO") or "SHOOTOUT" in s.replace(" ", ""):
        return float(final + 1) if final else float("nan")
    if s in ("HT", "HALF", "HALFTIME"):
        return 2.0
    m = _NUMBER.search(s)
    return float(m.group(1)) if m else float("nan")


def venue_state(events: dict[str, list[dict]]) -> dict[str, tuple[float, str]]:
    """(period, clock) by the venue's event id, from its own feed, for the events it says are in play."""
    out: dict[str, tuple[float, str]] = {}
    for sport, stubs in (events or {}).items():
        for e in stubs or []:
            if not e.get("live") or e.get("ended"):
                continue
            period = venue_period(e.get("period"), sport)
            if math.isfinite(period):
                out[str(e.get("id"))] = (period, str(e.get("elapsed") or ""))
    return out


def listings(sess=None, leagues=None) -> dict[str, list[dict]]:
    """Each league's games as the gateway lists them: a stub per event with its headline market, which is
    the moneyline with its top of book. A league that fails is skipped."""
    sess = sess or session()
    out: dict[str, list[dict]] = {}
    for league in (leagues or source.LEAGUES.values()):
        try:
            out[league.sport] = source.fetch_listing(league, sess)
        except Exception as error:  # noqa: BLE001 - one league's outage is not the tick's
            LOG.warning("worker: %s not read (%s)", league.sport, type(error).__name__)
    return out


def tick(store: Store, now: datetime, passphrase: str | None, *, events: dict[str, list[dict]] | None = None,
         sess=None, grade: bool = True) -> dict:
    """One pass: the listings read (or ``events`` given), the crossings taken, the settled positions graded
    when ``grade``, the record written, the new positions to the live step, and the ledger graded. Returns
    what happened, for the log."""
    events = events if events is not None else (listings(sess) if not offline() else {})
    live = sum(1 for stubs in events.values() for e in stubs if e.get("live") and not e.get("ended"))
    quotes = source.capture(now, events=events) if events else pd.DataFrame(columns=source.QUOTE_COLUMNS)
    games = store.read("games")
    if len(quotes):
        up = match.upcoming(games, now, store.read("projections"), store.read("nhl_projections"))
        quotes = match.attach(quotes, match.match(quotes, up))
    held = store.read(favorites.TABLE)
    record, added = favorites.take(held, quotes, now, games, venue=venue_state(events))
    repaired = len(record) - added != len(held)          # lines that were not positions, or a position held twice
    new = record.tail(added) if added else record.iloc[0:0]
    graded = 0
    if grade and len(record):
        pending = pd.to_numeric(record["won"], errors="coerce").isna().sum()
        record = favorites.grade(record, now)
        graded = int(pending - pd.to_numeric(record["won"], errors="coerce").isna().sum())
    if added or graded or repaired:
        store.write(favorites.TABLE, record)
    if added and passphrase:
        favorites.order(new, passphrase, now)
    if grade and passphrase:
        from atlas.polymarket import orders

        if orders.mode() != "off" and not offline():
            try:
                orders.grade(orders.load(passphrase), passphrase, now)
            except Exception as error:  # noqa: BLE001 - the type only
                LOG.error("worker: ledger not graded: %s", type(error).__name__)
    return {"events": sum(len(v) for v in events.values()), "live": live, "quotes": int(len(quotes)),
            "added": int(added), "graded": graded or int(repaired), "positions": int(len(record))}


# ---------------------------------------------------------------------------
# The record to the branch
# ---------------------------------------------------------------------------


def _git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=check)


def branch(root: Path) -> str:
    name = os.environ.get(BRANCH, "").strip()
    if name:
        return name
    return _git(root, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()


def _ledger(root: Path, passphrase: str | None) -> dict[str, list[dict]]:
    """The live ledger's weekly files as this checkout holds them, opened; nothing without the key."""
    from atlas.owner import sealed

    where = root / LEDGER
    if not passphrase or not where.exists():
        return {}
    out = {}
    for f in sorted(where.glob("*.enc.json")):
        try:
            out[f.name] = sealed.open_text(f.read_text(), passphrase)
        except Exception as error:  # noqa: BLE001 - a file this key cannot open is the branch's to keep
            LOG.warning("worker: %s not opened (%s); the branch's copy stands", f.name, type(error).__name__)
    return out


def sync(root: Path, passphrase: str | None = None) -> bool:
    """This checkout brought level with the branch without losing anything it holds: the record and the
    ledger read as they stand here (pushed or not), the checkout reset to the branch, and both laid back
    over the branch's copies by their rows - the record by position (`favorites.merge`), the ledger by
    order (`scripts/merge_tracking.py`'s key). Git never merges these files line by line, so no merge can
    leave its marks in them. True when what this checkout holds is not all on the branch yet."""
    from atlas.owner import sealed

    target = branch(root)
    store = Store.open(root / "tracking")
    ours = favorites.clean(store.read(favorites.TABLE))
    ledger = _ledger(root, passphrase)
    for args in (("rebase", "--abort"), ("merge", "--abort")):
        _git(root, *args, check=False)
    if _git(root, "fetch", "-q", "origin", target, check=False).returncode != 0:
        LOG.warning("worker: could not fetch %s this tick", target)
        return False
    _git(root, "reset", "-q", "--hard", f"origin/{target}")
    store.write(favorites.TABLE, favorites.merge(store.read(favorites.TABLE), ours))
    if ledger:
        keys = ["position_id", "placed_at", "rule"]
        ident = lambda row: tuple(row.get(k) for k in keys)  # noqa: E731
        for name, rows in ledger.items():
            f = root / LEDGER / name
            theirs = sealed.open_text(f.read_text(), passphrase) if f.exists() else []
            have = {ident(r) for r in theirs}
            missing = [r for r in rows if ident(r) not in have]
            if missing:
                sealed.seal([*theirs, *missing], passphrase, f)
    return bool(_git(root, "status", "--porcelain", "--", *FILES).stdout.strip())


def publish(root: Path, now: datetime, passphrase: str | None = None, *, attempts: int = 3) -> bool:
    """What this checkout holds and the branch does not, committed and pushed: brought level first
    (:func:`sync`), and again if the branch moved before the push landed. False when there is nothing to
    push or it could not be pushed this time (it is kept for the next tick)."""
    stamp = pd.Timestamp(now).tz_convert("America/New_York").strftime("%Y-%m-%d %H:%M ET")
    target = branch(root)
    for _ in range(attempts):
        if not sync(root, passphrase):
            return False
        _git(root, "add", "-A", "--", *[f for f in FILES if (root / f).exists()])
        _git(root, "-c", "user.name=atlas-worker", "-c", "user.email=noreply@anthropic.com", "commit", "-q", "-m",
             f"worker: {stamp}")
        if _git(root, "push", "-q", "origin", f"HEAD:{target}", check=False).returncode == 0:
            LOG.info("worker: record pushed to %s", target)
            return True
        LOG.warning("worker: %s moved before the push landed; bringing it level again", target)
    LOG.error("worker: could not push to %s; what is held here waits for the next tick", target)
    return False


# ---------------------------------------------------------------------------
# The loop
# ---------------------------------------------------------------------------


def run(*, every: int = EVERY, idle: int = IDLE, once: bool = False, push: bool = True,
        store: Store | None = None, root: Path | None = None) -> None:
    root = root or config.paths().root
    store = store or Store.open()
    passphrase = os.environ.get(crypto.SECRET, "").strip() or None
    if not passphrase:
        LOG.warning("worker: %s is not set; positions are taken and nothing is ordered", crypto.SECRET)
    sess = session()
    n = 0
    failures = 0
    while True:
        n += 1
        now = datetime.now(UTC)
        try:
            level = n % GRADE_EVERY == 1
            if push and level and not offline():
                sync(root, passphrase)          # the branch's scoreboard and projections, and anything unpushed
            summary = tick(store, now, passphrase, sess=sess, grade=level)
            failures = 0
            LOG.info("worker: %(events)d events, %(live)d in play, %(quotes)d quotes, %(added)d taken, "
                     "%(graded)d graded, %(positions)d in all", summary)
            if push and (summary["added"] or summary["graded"] or level) and not offline():
                publish(root, now, passphrase)
        except Exception as error:  # noqa: BLE001 - the loop outlives any one tick
            failures += 1
            summary = {"live": 0}
            LOG.error("worker: tick failed (%s), %d in a row", type(error).__name__, failures)
        if once:
            return
        wait = every if summary.get("live") else idle
        time.sleep(min(wait * (2 ** min(failures, 4)), 1800))


def main() -> None:
    ap = argparse.ArgumentParser(description="The favorites rule, as an always-on loop")
    ap.add_argument("--every", type=int, default=EVERY, help="seconds between ticks while a game is on")
    ap.add_argument("--idle", type=int, default=IDLE, help="seconds between ticks while none is")
    ap.add_argument("--once", action="store_true", help="one tick and exit")
    ap.add_argument("--no-push", action="store_true", help="keep the record locally; do not commit or push")
    args = ap.parse_args()
    run(every=args.every, idle=args.idle, once=args.once, push=not args.no_push)


if __name__ == "__main__":
    main()
