"""The watchdog: one issue, opened when stale, refreshed quietly, closed on recovery."""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime

import pytest

from atlas.ops import freshness, health, watchdog

NOW = datetime(2026, 9, 26, 15, 41, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path, monkeypatch):
    monkeypatch.setattr(freshness, "path", lambda: tmp_path / "freshness.json")


def _fresh():
    for event in ("heavy", "poll", "build"):
        freshness.record(event, detail="ok")


class FakeGh:
    """Records every call; answers the reads from what it was given."""

    def __init__(self, *, issue: int | None = None, runs=("success",) * 3, fail_assign=False,
                 runs_error=False):
        self.calls: list[list[str]] = []
        self.issue, self.runs = issue, list(runs)
        self.fail_assign, self.runs_error = fail_assign, runs_error

    def __call__(self, args):
        args = list(args)
        self.calls.append(args)
        if args[:2] == ["run", "list"]:
            if self.runs_error:
                raise subprocess.CalledProcessError(1, "gh")
            return json.dumps([{"conclusion": c} for c in self.runs])
        if args[:2] == ["issue", "list"]:
            return json.dumps([{"number": self.issue}] if self.issue else [])
        if args[:2] == ["issue", "create"] and self.fail_assign and "--assignee" in args:
            raise subprocess.CalledProcessError(1, "gh")
        return ""

    def verbs(self) -> list[tuple[str, str]]:
        return [(c[0], c[1]) for c in self.calls if (c[0], c[1]) not in {("run", "list"), ("issue", "list")}]


def test_healthy_and_no_issue_does_nothing():
    _fresh()
    gh = FakeGh()
    assert watchdog.main(gh, NOW) == 0
    assert gh.verbs() == []


def test_stale_opens_one_assigned_labelled_issue():
    gh = FakeGh()                                  # nothing ever recorded: every stamp missing
    watchdog.main(gh, NOW)
    assert gh.verbs() == [("label", "create"), ("issue", "create")]
    create = gh.calls[-1]
    assert watchdog.TITLE in create and watchdog.LABEL in create
    body = create[create.index("--body") + 1]
    assert "no successful poll recorded" in body and "Atlas health" in body


def test_an_owner_that_cannot_be_assigned_still_gets_the_issue(monkeypatch):
    monkeypatch.setenv("ALERT_ASSIGNEE", "some-org")
    gh = FakeGh(fail_assign=True)
    watchdog.main(gh, NOW)
    creates = [c for c in gh.calls if c[:2] == ["issue", "create"]]
    assert len(creates) == 2 and "--assignee" in creates[0] and "--assignee" not in creates[1]


def test_still_stale_refreshes_the_open_issue_quietly():
    """One notification per outage: no second issue, no hourly comment."""
    gh = FakeGh(issue=41)
    watchdog.main(gh, NOW)
    assert gh.verbs() == [("issue", "edit")]
    assert gh.calls[-1][2] == "41"


def test_recovery_comments_and_closes():
    _fresh()
    gh = FakeGh(issue=41)
    watchdog.main(gh, NOW)
    assert gh.verbs() == [("issue", "comment"), ("issue", "close")]
    assert "Healthy again" in gh.calls[-2][-1]


def test_three_failed_polls_alarm_before_the_stamps_go_stale():
    """25 September: every poll built and then failed the audit. The stamps
    take two hours to show it; three failed runs take about 45 minutes."""
    _fresh()
    checks = health.run()
    v = watchdog.evaluate(checks, ["failure", "failure", "failure"])
    assert v.alarm and "the last 3 site-poll runs all failed" in v.reasons
    assert not watchdog.evaluate(checks, ["failure", "failure", "success"]).alarm
    assert not watchdog.evaluate(checks, ["failure", "failure"]).alarm


def test_an_unreadable_run_list_never_alarms_by_itself():
    _fresh()
    gh = FakeGh(runs_error=True)
    watchdog.main(gh, NOW)
    assert gh.verbs() == []


def test_a_warning_is_not_an_alarm():
    """Social assets only ever warn: the watchdog follows health's own
    blocking flag rather than second-guessing it."""
    _fresh()
    checks = health.run()
    assert all(c.ok or not c.blocking for c in checks)
    assert not watchdog.evaluate(checks, []).alarm
