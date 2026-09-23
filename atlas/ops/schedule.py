"""When Atlas runs, in Eastern time.

Every schedule in this module is expressed in ET because every schedule is
about American football: a Saturday slate starts in the morning Eastern and
ends after midnight Eastern, and expressing that in UTC produces a window that
drifts twice a year when the clocks change.

Cron is given UTC by most hosts, so :data:`CRONTAB` writes the schedule with
an explicit ``CRON_TZ`` and the windows below are checked again at run time -
a poller that fires at the wrong hour should notice and do nothing rather than
burn a provider request.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from zoneinfo import ZoneInfo

EASTERN = ZoneInfo("America/New_York")

#: The heavy rebuild. Late enough that every West Coast game has finished and
#: the day's scores have settled; early enough that the board is current before
#: anybody is awake to read it.
HEAVY_HOUR = 4

#: The social assets, an hour after the heavy build so they are made from the
#: cards the heavy build just published rather than yesterday's.
SOCIAL_HOUR = 5

#: The ordinary poll: hourly, on the hour.
POLL_MINUTES = 60

#: Game-day poll cadence.
GAME_DAY_MINUTES = 15


@dataclass(frozen=True)
class Window:
    """A recurring weekday window in Eastern time.

    ``end`` before ``start`` means the window crosses midnight. The NCAAF
    window ends at midnight exactly, so nothing spills into Sunday; the branch
    exists so that moving the end to 01:00 for a late West Coast slate is a
    one-character change rather than a rewrite.
    """

    name: str
    weekday: int          # Monday is 0, as `datetime.weekday()` has it
    start: time
    end: time

    def contains(self, moment: datetime) -> bool:
        local = moment.astimezone(EASTERN)
        if self.start <= self.end:
            return local.weekday() == self.weekday and self.start <= local.time() < self.end
        # Crosses midnight: the tail belongs to the previous day's window.
        if local.weekday() == self.weekday and local.time() >= self.start:
            return True
        return local.weekday() == (self.weekday + 1) % 7 and local.time() < self.end


#: NCAAF Saturday 08:00 ET through midnight; NFL Sunday 07:00 to 20:00 ET.
GAME_DAYS = (
    Window("NCAAF Saturday", weekday=5, start=time(8, 0), end=time(0, 0)),
    Window("NFL Sunday", weekday=6, start=time(7, 0), end=time(20, 0)),
)


def game_day(moment: datetime | None = None) -> Window | None:
    """The game-day window containing ``moment``, or None."""
    moment = moment or datetime.now(EASTERN)
    for window in GAME_DAYS:
        if window.contains(moment):
            return window
    return None


def poll_interval_minutes(moment: datetime | None = None) -> int:
    return GAME_DAY_MINUTES if game_day(moment) else POLL_MINUTES


def should_poll(moment: datetime | None = None) -> bool:
    """Whether this minute is a scheduled poll minute.

    Off a game day the poller fires on the hour and returns immediately on the
    other fifty-nine cron ticks. That keeps one crontab line covering both
    cadences, and means the *code* owns the schedule rather than the host.
    """
    local = (moment or datetime.now(EASTERN)).astimezone(EASTERN)
    return local.minute % poll_interval_minutes(local) == 0


#: How late a hosted scheduler may fire and still count as this tick rather
#: than a missed one. Five minutes is longer than any delay cron imposes and
#: shorter than the tightest cadence Atlas runs.
SLACK_MINUTES = 5


def due(event: str, last: datetime | None, moment: datetime | None = None,
        *, slack: int = SLACK_MINUTES) -> tuple[bool, str]:
    """Whether ``event`` is due now, given when it last succeeded.

    :func:`should_poll` answers *"is this a scheduled minute"*, which is the
    right question for a crontab: cron fires on the minute, so an exact match
    is exact. A hosted scheduler is not cron. GitHub documents that a
    scheduled workflow "can be delayed during periods of high loads", and a
    run that fires at 11:07 asked *"is this the minute"* answers **no** - so a
    late poll becomes a lost poll, which is strictly worse than a late one.

    Asking *"is it due"* turns a delay back into a delay. It is also
    self-correcting in the other direction: two runs that overlap cannot both
    be due, because the first one's success moves ``last``.

    Returns the decision and a sentence for the log, because a scheduler that
    silently declines to run is the thing that is hard to debug at 4 AM.
    """
    now = (moment or datetime.now(EASTERN)).astimezone(EASTERN)
    if last is None:
        return True, f"{event} has never run"
    last = last.astimezone(EASTERN)
    waited = (now - last).total_seconds() / 60

    if event == "heavy":
        if last.date() >= now.date():
            return False, f"heavy already ran today at {last:%H:%M ET}"
        if now.hour < HEAVY_HOUR:
            return False, f"{now:%H:%M ET} is before the {HEAVY_HOUR:02d}:00 rebuild"
        return True, f"last heavy was {last:%a %H:%M ET}, {waited / 60:.0f}h ago"

    interval = poll_interval_minutes(now)
    if waited + slack < interval:
        return False, (f"polled {waited:.0f}m ago; the cadence here is "
                       f"every {interval}m")
    window = game_day(now)
    where = f" ({window.name})" if window else ""
    return True, f"last poll {waited:.0f}m ago, cadence {interval}m{where}"


#: The crontab Atlas ships. Written in Eastern with an explicit CRON_TZ so the
#: schedule does not move when the clocks do.
CRONTAB = """\
# Atlas live operations. Times are Eastern; CRON_TZ keeps them Eastern
# through both daylight-saving transitions.
CRON_TZ=America/New_York

# Back up the live record and read the copy back. Daily 03:00 ET, an hour
# before the heavy refresh so the backup is of a quiet store.
0 3 * * *   cd {root} && make ops-backup >> {logs}/backup.log 2>&1

# Heavy refresh - warehouse, model, every page. Daily 04:00 ET.
0 4 * * *   cd {root} && make ops-heavy  >> {logs}/heavy.log 2>&1

# Social assets, from the cards the heavy build just published. Daily 05:00 ET.
0 5 * * *   cd {root} && make ops-social >> {logs}/social.log 2>&1

# Light poller. Fires every 15 minutes; the task itself decides whether this
# minute is a poll minute, so one line covers the hourly cadence and the
# game-day cadence without two competing schedules.
*/15 * * * * cd {root} && make ops-poll   >> {logs}/poll.log 2>&1

# Health check. Hourly, and the only task that is allowed to be noisy.
30 * * * *  cd {root} && make ops-health >> {logs}/health.log 2>&1
"""


def crontab(root: str = "/srv/atlas", logs: str = "/var/log/atlas") -> str:
    return CRONTAB.format(root=root, logs=logs)
