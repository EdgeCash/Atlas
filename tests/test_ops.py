"""Operations phase: the checks that keep the live record trustworthy.

Every test here plants a specific corruption and asserts the system notices.
A monitor that has never been shown to fire is decoration.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from atlas.live import dashboard, drift, quality, reproduce
from atlas.live.audit import Run, signal_uuid
from atlas.live.store import Store


@pytest.fixture
def store(tmp_path) -> Store:
    return Store.open(tmp_path / "tracking")


def _clean(store: Store, n: int = 60, *, book: str = "DraftKings",
           market: str = "total", week: int = 6) -> pd.DataFrame:
    """A small, internally consistent record."""
    now = datetime.now(UTC).replace(microsecond=0)
    games, snaps, signals = [], [], []
    for i in range(n):
        game_id = 400000 + i
        entry, number = 52.0, 62.0
        games.append({
            "game_id": game_id, "season": 2026, "week": week,
            "kickoff": (now + timedelta(days=1)).isoformat(),
            "home_team": f"H{i}", "away_team": f"A{i}",
            "home_team_id": i, "away_team_id": 100 + i,
            "status": "STATUS_SCHEDULED", "completed": False,
            "home_score": None, "away_score": None,
            "first_seen_at": now.isoformat(), "updated_at": now.isoformat(),
        })
        snaps.append({
            "captured_at": now.isoformat(), "game_id": game_id, "book": book,
            "market": market, "line": entry, "price": -110.0,
            "open_line": 51.0, "open_price": -110.0,
            "status": "STATUS_SCHEDULED", "last_seen_at": now.isoformat(),
        })
        signals.append({
            "signal_id": signal_uuid(game_id, market, book),
            "created_at": now.isoformat(), "run_id": "test-run",
            "game_id": game_id, "season": 2026, "week": week, "market": market,
            "book": book, "open_line": 51.0, "entry_line": entry,
            "entry_price": -110.0, "atlas_number": number,
            "disagreement": number - entry, "direction": "over",
            "selection": "primary", "model_version": "v1",
        })
    store.write("games", pd.DataFrame(games))
    store.write("snapshots", pd.DataFrame(snaps))
    store.write("signals", pd.DataFrame(signals))
    return store.read("signals")


# ---------------------------------------------------------------------------
# Track 1 - data quality
# ---------------------------------------------------------------------------


def test_a_clean_record_produces_no_exceptions(store):
    _clean(store)
    assert quality.exceptions(store).empty


def test_the_summary_lists_every_check_even_when_nothing_fires(store):
    """A clean bill needs proof the checks ran, not just silence."""
    _clean(store)
    summary = quality.summary(quality.exceptions(store), store)
    assert len(summary) == len(quality._CHECK_REGISTRY)
    assert summary["clean"].all()


@pytest.mark.parametrize(
    ("column", "value", "check"),
    [
        ("game_id", 999999999, "game exists"),
        ("market", "moneyline", "market exists"),
        ("entry_line", None, "entry line exists"),
        ("open_line", None, "opening line exists"),
        ("entry_line", 5000.0, "entry line in range"),
        ("disagreement", 0.0, "signal is an opinion"),
        ("model_version", "", "model version recorded"),
    ],
)
def test_each_existence_check_fires_on_its_own_defect(store, column, value, check):
    signals = _clean(store)
    signals.loc[0, column] = value
    store.write("signals", signals)
    found = quality.exceptions(store)
    assert check in set(found["check"]), f"{check} did not fire for {column}={value}"


def test_a_signal_with_no_line_history_is_blocking(store):
    """It can be neither graded nor reproduced, so it is not evidence."""
    _clean(store)
    store.write("snapshots", store.read("snapshots").iloc[1:])
    found = quality.exceptions(store)
    fired = found[found["check"] == "line history exists"]
    assert len(fired) == 1
    assert fired.iloc[0]["severity"] == "blocking"


def test_an_edited_disagreement_is_caught(store):
    """Hand-editing the record is the corruption this phase exists to catch."""
    signals = _clean(store)
    signals.loc[0, "disagreement"] = 99.0
    store.write("signals", signals)
    assert "disagreement is consistent" in set(quality.exceptions(store)["check"])


def test_a_grade_that_does_not_follow_from_its_signal_is_caught(store):
    signals = _clean(store)
    grades = pd.DataFrame([{
        "signal_id": signals.iloc[0]["signal_id"], "graded_at": "2026-10-01T00:00:00+00:00",
        "close_line": 54.0, "clv_points": 9.0, "result": "beat",
        "clv_from_open": 3.0, "result_from_open": "beat", "total_move": 3.0,
        "pre_signal_move": 1.0, "execution_flagged": False,
    }])
    store.write("grades", grades)
    found = quality.exceptions(store)
    assert "clv is consistent" in set(found["check"])


def test_a_mislabelled_result_is_caught(store):
    signals = _clean(store)
    store.write("grades", pd.DataFrame([{
        "signal_id": signals.iloc[0]["signal_id"], "graded_at": "2026-10-01T00:00:00+00:00",
        "close_line": 50.0, "clv_points": -2.0, "result": "beat",
        "clv_from_open": -1.0, "result_from_open": "lost", "total_move": -1.0,
        "pre_signal_move": 1.0, "execution_flagged": False,
    }]))
    assert "result matches clv" in set(quality.exceptions(store)["check"])


# ---------------------------------------------------------------------------
# Track 2 - auditability
# ---------------------------------------------------------------------------


def test_the_signal_id_is_a_real_uuid_and_is_deterministic():
    first = signal_uuid(401856704, "total", "DraftKings")
    assert uuid.UUID(first).version == 5
    assert first == signal_uuid(401856704, "total", "DraftKings")
    assert first != signal_uuid(401856704, "margin", "DraftKings")
    assert first != signal_uuid(401856704, "total", "Bovada")


def test_the_signal_id_is_pinned():
    """Changing the namespace silently re-issues every id in the record, so
    one known value is pinned here as a tripwire."""
    assert signal_uuid(401856704, "total", "DraftKings") == (
        str(uuid.uuid5(uuid.UUID("a71a5000-0000-5000-8000-000000000001"),
                       "401856704|total|DraftKings"))
    )


def test_a_failed_run_is_logged_not_swallowed(store):
    run = Run(command="poll", provider="espn")
    run.finish(store, "failed", "ConnectionError: boom")
    logged = store.read("runs")
    assert len(logged) == 1
    assert logged.iloc[0]["status"] == "failed"
    assert logged.iloc[0]["code_version"]


def test_every_signal_names_the_run_that_wrote_it(store):
    signals = _clean(store)
    assert signals["run_id"].notna().all()
    assert (signals["run_id"] != "").all()


# ---------------------------------------------------------------------------
# Tracks 3 and 5 - drift and anomalies
# ---------------------------------------------------------------------------


def _alert(alerts: pd.DataFrame, name: str) -> pd.Series:
    match = alerts[alerts["name"] == name]
    assert not match.empty, f"no alert named {name!r}"
    return match.iloc[0]


def test_a_volume_collapse_fires(store):
    first = _clean(store, 60, week=6)
    second = _clean(store, 10, week=7)
    store.write("signals", pd.concat([first, second], ignore_index=True))
    assert _alert(drift.monitor(store), "signal volume")["severity"] == "alarm"


def test_a_volume_spike_fires(store):
    first = _clean(store, 20, week=6)
    second = _clean(store, 80, week=7)
    store.write("signals", pd.concat([first, second], ignore_index=True))
    assert _alert(drift.monitor(store), "signal volume")["severity"] == "alarm"


def test_steady_volume_does_not_fire(store):
    first = _clean(store, 40, week=6)
    second = _clean(store, 44, week=7)
    store.write("signals", pd.concat([first, second], ignore_index=True))
    assert _alert(drift.monitor(store), "signal volume")["severity"] == "ok"


def test_silence_fires_after_a_week(store):
    signals = _clean(store)
    stale = (datetime.now(UTC) - timedelta(days=9)).isoformat()
    signals["created_at"] = stale
    store.write("signals", signals)
    assert _alert(drift.monitor(store), "silence")["severity"] == "alarm"


def test_a_single_book_fires_and_two_books_do_not(store):
    _clean(store)
    assert _alert(drift.monitor(store), "single book")["severity"] == "alarm"

    one = _clean(store, 30, book="DraftKings")
    two = _clean(store, 30, book="Bovada")
    two["signal_id"] = [signal_uuid(g, "total", "Bovada") for g in two["game_id"]]
    store.write("signals", pd.concat([one, two], ignore_index=True))
    assert _alert(drift.monitor(store), "single book")["severity"] == "ok"


def test_a_single_market_fires(store):
    _clean(store, market="total")
    assert _alert(drift.monitor(store), "single market")["severity"] == "alarm"


def test_model_output_drift_fires(store):
    first = _clean(store, 40, week=6)
    second = _clean(store, 40, week=7)
    second["atlas_number"] = second["atlas_number"].astype(float) + 8.0
    store.write("signals", pd.concat([first, second], ignore_index=True))
    assert _alert(drift.monitor(store), "model output (total)")["severity"] == "alarm"


def test_a_changed_disagreement_distribution_fires(store):
    import numpy as np

    rng = np.random.default_rng(3)
    first = _clean(store, 60, week=6)
    first["disagreement"] = rng.normal(2.0, 1.0, len(first))
    second = _clean(store, 60, week=7)
    second["disagreement"] = rng.normal(12.0, 1.0, len(second))
    store.write("signals", pd.concat([first, second], ignore_index=True))
    assert _alert(drift.monitor(store), "disagreement shape (total)")["severity"] == "watch"


def test_the_monitor_reports_every_alarm_even_when_quiet(store):
    _clean(store)
    alerts = drift.monitor(store)
    assert {"signal volume", "silence", "single book", "single market"} <= set(alerts["name"])


# ---------------------------------------------------------------------------
# Track 6 - reproducibility
# ---------------------------------------------------------------------------


def test_a_tampered_signal_fails_the_replay(store):
    signals = _clean(store)
    numbers = pd.DataFrame([{
        "game_id": row["game_id"], "season": 2026, "week": 6, "market": "total",
        "prediction": row["atlas_number"], "threshold": 9.0,
        "model_version": "v1", "refreshed_at": "2026-09-01T00:00:00+00:00",
    } for _, row in signals.iterrows()])
    store.write("numbers", numbers)

    clean = reproduce.replay_signals(store, "2026-w06")
    assert clean.clean, clean.detail

    tampered = store.read("signals")
    tampered.loc[0, "atlas_number"] = 99.0
    tampered.loc[0, "disagreement"] = 99.0 - 52.0
    store.write("signals", tampered)
    assert not reproduce.replay_signals(store, "2026-w06").clean


def test_replay_uses_the_model_version_the_signal_names(store):
    """A refit must not silently rewrite history: replaying a past period has
    to use the number that produced it, not today's."""
    signals = _clean(store)
    old = pd.DataFrame([{
        "game_id": row["game_id"], "season": 2026, "week": 6, "market": "total",
        "prediction": row["atlas_number"], "threshold": 9.0,
        "model_version": "v1", "refreshed_at": "2026-09-01T00:00:00+00:00",
    } for _, row in signals.iterrows()])
    new = old.assign(prediction=old["prediction"] + 20.0, model_version="v2",
                     refreshed_at="2026-09-20T00:00:00+00:00")
    store.write("numbers", pd.concat([old, new], ignore_index=True))
    assert reproduce.replay_signals(store, "2026-w06").clean


# ---------------------------------------------------------------------------
# Track 4 - the dashboard
# ---------------------------------------------------------------------------


def test_the_dashboard_carries_no_betting_vocabulary(store):
    _clean(store)
    page = dashboard.render(dashboard.collect(store))
    for word in ("$", "Kelly", "bankroll", "units", "ROI", "bet slip"):
        assert word not in page, f"dashboard leaked {word!r}"


def test_the_dashboard_renders_with_an_empty_record(store):
    page = dashboard.render(dashboard.collect(store))
    assert "Atlas Season Dashboard" in page
    assert "No graded weeks yet" in page


def test_a_blocking_exception_outranks_the_kill_criteria(store):
    """A green headline beside 'blocking exceptions' is exactly the accidental
    corruption this phase exists to make impossible."""
    signals = _clean(store)
    signals.loc[0, "entry_line"] = None
    store.write("signals", signals)
    page = dashboard.render(dashboard.collect(store))
    assert "SUSPECT" in page


def _projections(refreshes: list[tuple[str, int]]) -> pd.DataFrame:
    """College projections at each refresh, two teams, each having played ``games``."""
    rows = []
    for stamp, games in refreshes:
        rows.append({"game_id": 1, "sport": "ncaaf", "refreshed_at": stamp, "home_team_id": 61, "away_team_id": 99,
                     "home_games": games, "away_games": games, "model_version": f"m{games}"})
    return pd.DataFrame(rows)


def test_a_college_state_that_learns_nothing_after_a_game_day_fires(store):
    stale = _projections([("2026-09-25T13:00:00+00:00", 3), ("2026-09-27T08:00:00+00:00", 3),
                          ("2026-09-28T08:00:00+00:00", 3)])
    # Monday 13:00 ET: past the 36-hour deadline (Monday noon ET), not yet the alarm (Wednesday noon ET).
    watch = drift.state_alerts(stale, now=pd.Timestamp("2026-09-28T17:00:00Z"))[0]
    assert watch.severity == "watch" and "no game" in watch.detail
    alarm = drift.state_alerts(stale, now=pd.Timestamp("2026-09-30T18:00:00Z"))[0]        # Wednesday 14:00 ET
    assert alarm.severity == "alarm"
    moved = _projections([("2026-09-25T13:00:00+00:00", 3), ("2026-09-28T08:00:00+00:00", 4)])
    assert drift.state_alerts(moved, now=pd.Timestamp("2026-09-30T18:00:00Z"))[0].severity == "ok"
    # Before the deadline nothing is expected of it; with no projections nothing is said.
    assert drift.state_alerts(stale, now=pd.Timestamp("2026-09-28T09:00:00Z"))[0].severity == "ok"
    assert drift.state_alerts(pd.DataFrame(), now=pd.Timestamp("2026-09-30T18:00:00Z"))[0].severity == "ok"
    store.write("projections", stale)
    assert "college state" in set(drift.monitor(store)["name"])
