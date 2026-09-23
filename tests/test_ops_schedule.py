"""Live operations automation: the schedule, the freshness contract, the checks.

`tests/test_ops.py` covers the Operations-phase monitors - data quality, drift,
reproducibility. This covers the automation layer on top of them.

The contract these tests defend is one sentence: **a timestamp on a page is
the time of the last successful refresh of that thing, never the time the page
was built.** Everything else here is scaffolding around that.
"""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta

import pytest

from atlas.ops import freshness, health, schedule
from atlas.site.html import stamp

ET = schedule.EASTERN


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path, monkeypatch):
    """Every test gets its own provenance file."""
    monkeypatch.setattr(freshness, "path", lambda: tmp_path / "freshness.json")


# ---------------------------------------------------------------------------
# The timestamp standard
# ---------------------------------------------------------------------------


def test_the_stamp_format_is_the_one_in_the_specification():
    assert stamp(datetime(2026, 9, 22, 23, 5, tzinfo=UTC)) == "Sep 22, 2026 7:05 PM ET"


def test_every_stamp_is_eastern_whatever_the_stored_zone():
    """Storage is UTC, display is ET. A timestamp without a zone is a number a
    reader has to guess about."""
    winter = stamp(datetime(2026, 1, 5, 17, 0, tzinfo=UTC))
    summer = stamp(datetime(2026, 7, 5, 17, 0, tzinfo=UTC))
    assert winter.endswith("12:00 PM ET")   # EST, UTC-5
    assert summer.endswith("1:00 PM ET")    # EDT, UTC-4


# ---------------------------------------------------------------------------
# Freshness: the contract
# ---------------------------------------------------------------------------


def test_a_failed_run_never_advances_a_visible_timestamp():
    """The whole point of separating `last` from `last_ok`. A reader must not
    be told information is current because a refresh was *attempted*."""
    freshness.record("poll", detail="good")
    good = freshness.last("poll")
    freshness.record("poll", ok=False, detail="provider 503")
    assert freshness.last("poll").at == good.at
    assert freshness.last("poll", successful=False).detail == "provider 503"


def test_history_keeps_failures_so_an_operator_can_see_them():
    freshness.record("poll", ok=False, detail="one")
    freshness.record("poll", detail="two")
    names = [(e.ok, e.detail) for e in freshness.history("poll")]
    assert names == [(True, "two"), (False, "one")]


def test_an_unknown_event_is_a_typo_not_a_new_event():
    with pytest.raises(ValueError):
        freshness.record("rebuild")


def test_a_corrupt_provenance_file_does_not_stop_a_build(tmp_path):
    """A site with no timestamps is recoverable; a site that will not build
    is not."""
    freshness.path().write_text("{ this is not json")
    assert freshness.load() == {"last": {}, "history": []}
    assert freshness.last("poll") is None


# ---------------------------------------------------------------------------
# The schedule
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("moment,expected", [
    (datetime(2026, 9, 26, 8, 0, tzinfo=ET), "NCAAF Saturday"),
    (datetime(2026, 9, 26, 23, 59, tzinfo=ET), "NCAAF Saturday"),
    (datetime(2026, 9, 26, 7, 59, tzinfo=ET), None),
    (datetime(2026, 9, 27, 0, 30, tzinfo=ET), None),      # past midnight
    (datetime(2026, 9, 27, 7, 0, tzinfo=ET), "NFL Sunday"),
    (datetime(2026, 9, 27, 19, 59, tzinfo=ET), "NFL Sunday"),
    (datetime(2026, 9, 27, 20, 0, tzinfo=ET), None),
    (datetime(2026, 9, 22, 14, 0, tzinfo=ET), None),      # a Tuesday
])
def test_game_day_windows_match_the_specification(moment, expected):
    window = schedule.game_day(moment)
    assert (window.name if window else None) == expected


def test_game_day_raises_the_cadence_and_nothing_else_does():
    saturday = datetime(2026, 9, 26, 12, 0, tzinfo=ET)
    tuesday = datetime(2026, 9, 22, 12, 0, tzinfo=ET)
    assert schedule.poll_interval_minutes(saturday) == 15
    assert schedule.poll_interval_minutes(tuesday) == 60


def test_the_poller_declines_fourteen_of_fifteen_ticks_off_a_game_day():
    """One crontab line covers both cadences because the task owns the
    schedule. Off a game day that means most invocations cost nothing."""
    tuesday = datetime(2026, 9, 22, 12, 0, tzinfo=ET)
    fires = [schedule.should_poll(tuesday.replace(minute=m))
             for m in (0, 15, 30, 45)]
    assert fires == [True, False, False, False]

    saturday = datetime(2026, 9, 26, 12, 0, tzinfo=ET)
    fires = [schedule.should_poll(saturday.replace(minute=m))
             for m in (0, 15, 30, 45)]
    assert fires == [True, True, True, True]


def test_the_crontab_pins_eastern_explicitly():
    """Without CRON_TZ the schedule moves an hour twice a year, and a 4am
    build becomes a 3am build in the middle of the season."""
    text = schedule.crontab(root="/srv/atlas", logs="/var/log/atlas")
    assert "CRON_TZ=America/New_York" in text
    assert "0 4 * * *" in text        # heavy
    assert "0 5 * * *" in text        # social
    assert "*/15 * * * *" in text     # poller


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


def test_health_fails_when_nothing_has_ever_run():
    checks = health.run()
    assert health.failing(checks)


def test_health_passes_once_every_task_has_succeeded():
    for event in ("poll", "heavy", "build", "social"):
        freshness.record(event, detail="ok")
    checks = health.run()
    assert not health.failing(checks)
    assert all(c.ok for c in checks)


def test_a_stale_poll_is_blocking_and_stale_social_assets_are_not():
    """Thresholds are generous on purpose: an alert that fires on one missed
    poll is an alert an operator learns to ignore."""
    stale = datetime.now(UTC) - timedelta(hours=6)
    state = {"last_ok": {name: {"name": name, "at": stale.isoformat(), "ok": True,
                                "detail": ""} for name in freshness.EVENTS},
             "last": {}, "history": []}
    freshness._write(state)
    by_name = {c.name: c for c in health.run()}
    assert by_name["poll"].ok is False and by_name["poll"].blocking
    assert by_name["board"].ok is False and by_name["board"].blocking
    assert by_name["heavy refresh"].ok is True          # 24h limit
    assert by_name["social assets"].ok is True          # 48h limit


def test_the_alert_thresholds_are_the_ones_in_the_brief():
    assert health.POLL_MAX_HOURS == 2.0
    assert health.HEAVY_MAX_HOURS == 24.0
    assert health.BOARD_MAX_HOURS == 3.0


def test_the_windows_are_stated_in_eastern_not_utc():
    """Expressing a Saturday slate in UTC produces a window that drifts twice
    a year when the clocks change."""
    assert schedule.EASTERN.key == "America/New_York"
    assert all(isinstance(w.start, time) for w in schedule.GAME_DAYS)
