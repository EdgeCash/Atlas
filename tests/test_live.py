"""Phase 5: the live CLV tracker.

Two kinds of test here. Most check mechanics. One - ``test_the_tracker_never
_computes_a_stake`` - checks the rule the whole phase is built on: Atlas
generates opinions, not bets.
"""

from __future__ import annotations

import re
import tokenize
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from atlas.live import grade as grading
from atlas.live import scorecard as sc
from atlas.live import signals as signalling
from atlas.live.store import SCHEMA, Store


@pytest.fixture
def store(tmp_path) -> Store:
    return Store.open(tmp_path / "tracking")


def _quotes(n: int = 4, *, status: str = "STATUS_SCHEDULED") -> pd.DataFrame:
    now = datetime.now(UTC).replace(microsecond=0)
    return pd.DataFrame(
        {
            "captured_at": [now.isoformat()] * n,
            "game_id": range(100, 100 + n),
            "season": 2026,
            "week": 6,
            "kickoff": [(now + timedelta(days=2)).isoformat()] * n,
            "home_team": [f"Home {i}" for i in range(n)],
            "away_team": [f"Away {i}" for i in range(n)],
            "home_team_id": range(1, n + 1),
            "away_team_id": range(50, 50 + n),
            "home_score": None,
            "away_score": None,
            "status": status,
            "completed": status != "STATUS_SCHEDULED",
            "book": "TestBook",
            "market": "total",
            "line": [50.0, 51.0, 52.0, 53.0],
            "price": -110.0,
            "open_line": [49.0, 51.0, 54.0, 53.0],
            "open_price": -110.0,
        }
    )


def _numbers(n: int = 4) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "game_id": range(100, 100 + n),
            "season": 2026,
            "week": 6,
            "market": "total",
            "prediction": [62.0, 51.5, 41.0, 53.4],
            "threshold": 9.0,
            "model_version": "testmodel01",
        }
    )


# ---------------------------------------------------------------------------
# The rule
# ---------------------------------------------------------------------------


def test_the_tracker_never_computes_a_stake():
    """Phase 5's constraint, enforced rather than promised.

    The brief forbids stakes, expected profit, ROI and Kelly. Those are easy
    to add later "just to see", and the moment one appears the project has
    quietly become the thing it said it was not.
    """
    forbidden = {
        "kelly", "stake", "stakes", "staking", "bankroll", "roi", "wager",
        "wagers", "payout", "profit", "bet_size", "units_won", "expected_value",
        "edge_value", "ev",
    }
    package = Path(__file__).resolve().parent.parent / "atlas" / "live"
    offenders = []
    for path in sorted(package.rglob("*.py")):
        with path.open("rb") as handle:
            # Identifiers only. Prose that names the prohibition is the point;
            # a variable called `stake` is the violation.
            for token in tokenize.tokenize(handle.readline):
                if token.type != tokenize.NAME:
                    continue
                for part in re.split(r"_|(?<=[a-z])(?=[A-Z])", token.string.lower()):
                    if part in forbidden:
                        offenders.append(f"{path.name}:{token.start[0]}: {token.string}")
    assert not offenders, "live tracker must not reason about money:\n" + "\n".join(offenders)


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


def test_a_signal_is_never_restated(store):
    """An opinion, once stated, is immutable.

    Rewriting a signal after seeing where the line went is the single easiest
    way to turn this system into a fiction, so the store refuses.
    """
    formed = signalling.form_signals(_numbers(), _quotes())
    assert store.append_new_only("signals", formed) == len(formed)

    moved = formed.copy()
    moved["entry_line"] = moved["entry_line"] + 3.0
    moved["atlas_number"] = moved["atlas_number"] + 3.0
    assert store.append_new_only("signals", moved) == 0

    stored = store.read("signals")
    assert len(stored) == len(formed)
    assert stored["entry_line"].tolist() == formed["entry_line"].tolist()


def test_signal_id_survives_a_model_refit(store):
    """A weekly refit must not let Atlas call the same game twice."""
    numbers = _numbers()
    first = signalling.form_signals(numbers, _quotes())
    refit = numbers.copy()
    refit["model_version"] = "testmodel02"
    refit["prediction"] = refit["prediction"] + 1.0
    second = signalling.form_signals(refit, _quotes())
    assert set(first["signal_id"]) == set(second["signal_id"])


def test_an_unchanged_quote_adds_no_row(store):
    """Append-on-change: polling hourly must not write an identical row every
    hour, or the committed history becomes unreadable."""
    quotes = _quotes()
    snapshot = quotes[[c for c in SCHEMA["snapshots"] if c in quotes.columns]].copy()
    snapshot["last_seen_at"] = quotes["captured_at"]
    assert store.upsert("snapshots", snapshot) == len(snapshot)
    assert store.upsert("snapshots", snapshot) == 0


def _snaps(*quotes):
    """(captured_at, line, price, other_price) sightings of one stream."""
    return pd.DataFrame([
        {"captured_at": at, "game_id": 100, "book": "TestBook", "market": "total", "line": line,
         "price": price, "other_price": other, "status": "STATUS_SCHEDULED", "last_seen_at": at}
        for at, line, price, other in quotes
    ])


def test_a_resighted_quote_keeps_its_first_capture_time(store):
    """The close, seen again after kickoff, must stay stamped before it: a
    re-stamped close drops out of the grader's window and an older line
    grades in its place."""
    store.append_on_change("snapshots", _snaps(("2026-09-26T15:00:00+00:00", 52.5, -110.0, -110.0)))
    assert store.append_on_change(
        "snapshots", _snaps(("2026-09-26T17:00:00+00:00", 52.5, -110.0, -110.0))) == 0
    row = store.read("snapshots").iloc[0]
    assert row["captured_at"] == "2026-09-26T15:00:00+00:00"
    assert row["last_seen_at"] == "2026-09-26T17:00:00+00:00"


def test_a_line_that_returns_is_a_new_row(store):
    for at, line in (("2026-09-26T10:00:00+00:00", 50.0), ("2026-09-26T11:00:00+00:00", 51.0),
                     ("2026-09-26T12:00:00+00:00", 50.0), ("2026-09-26T13:00:00+00:00", 50.0)):
        store.append_on_change("snapshots", _snaps((at, line, -110.0, -110.0)))
    history = store.read("snapshots")
    assert list(history["line"]) == [50.0, 51.0, 50.0]
    assert history["last_seen_at"].iloc[-1] == "2026-09-26T13:00:00+00:00"


def test_a_price_change_alone_is_a_change(store):
    store.append_on_change("snapshots", _snaps(("2026-09-26T10:00:00+00:00", 50.0, -110.0, -110.0)))
    assert store.append_on_change(
        "snapshots", _snaps(("2026-09-26T11:00:00+00:00", 50.0, -120.0, float("nan")))) == 1


def test_the_close_survives_being_seen_after_kickoff(store):
    """End to end: entry 50, close 52.5, 52.5 seen again after kickoff."""
    formed, _, games = _graded_fixture()
    kickoff = pd.Timestamp(games["kickoff"].iloc[0])
    for minutes, line in ((-90, 50.0), (-30, 52.5), (+60, 52.5)):
        at = (kickoff + pd.Timedelta(minutes=minutes)).isoformat()
        store.append_on_change("snapshots", _snaps((at, line, -110.0, -110.0)))
    graded = grading.grade(formed, store.read("snapshots"), games).set_index("signal_id")
    row = graded.loc[formed.set_index("game_id").loc[100, "signal_id"]]
    assert row["close_line"] == 52.5
    assert row["result"] == "beat"


def test_the_close_is_one_whole_snapshot():
    """groupby().last() fills each column from its own last non-null value;
    the close and its price must come from one row."""
    from atlas.owner.plays import current_lines
    snaps = pd.DataFrame({
        "captured_at": ["2026-09-26T10:00:00+00:00", "2026-09-26T11:00:00+00:00"],
        "game_id": 100, "book": "TestBook", "market": "total",
        "line": [53.5, 54.5], "price": [-110.0, -108.0], "other_price": [-105.0, float("nan")],
    })
    row = current_lines(snaps, "total").iloc[0]
    assert row["line"] == 54.5 and row["price"] == -108.0 and pd.isna(row["other_price"])


def test_even_money_is_plus_100_and_pickem_is_zero():
    from atlas.live.provider import _line_block
    assert _line_block({"close": {"line": "PK", "odds": "EVEN"}}, "close") == (0.0, 100.0)
    assert _line_block({"close": {"line": "o52.5", "odds": "-110"}}, "close") == (52.5, -110.0)


def test_the_poll_asks_for_eastern_dates(monkeypatch):
    """At 9pm ET the UTC date is tomorrow; tonight's slate must still be asked for."""
    from atlas.live import __main__ as live
    real = datetime

    class Clock(real):
        @classmethod
        def now(cls, tz=None):
            return real(2026, 9, 27, 1, 0, tzinfo=UTC).astimezone(tz) if tz else real(2026, 9, 27, 1, 0)

    monkeypatch.setattr(live, "datetime", Clock)
    days = [d.isoformat() for d in live._days(2)]
    assert "2026-09-26" in days and "2026-09-28" not in days
    # And the two days before, so a final score is still recorded the morning after.
    assert days[0] == "2026-09-24"


def test_no_signal_forms_after_the_scheduled_kickoff():
    """A delayed game still reads as scheduled; its close is already fixed."""
    past = _quotes().assign(kickoff=(datetime.now(UTC) - timedelta(minutes=5)).isoformat())
    assert signalling.form_signals(_numbers(), past).empty


def test_writes_are_deterministic(store):
    quotes = _quotes()
    store.upsert("games", quotes.assign(first_seen_at="t", updated_at="t"))
    first = store.path("games").read_text()
    store.upsert("games", quotes.assign(first_seen_at="t", updated_at="t"))
    assert store.path("games").read_text() == first


# ---------------------------------------------------------------------------
# Signals
# ---------------------------------------------------------------------------


def test_direction_follows_the_disagreement():
    formed = signalling.form_signals(_numbers(), _quotes()).set_index("game_id")
    assert formed.loc[100, "direction"] == "over"   # 62.0 against a 50.0 line
    assert formed.loc[102, "direction"] == "under"  # 41.0 against a 52.0 line


def test_a_signal_on_the_number_is_not_a_signal():
    """Zero disagreement is not an opinion, and grading it would only ever
    manufacture pushes."""
    numbers = _numbers()
    numbers.loc[:, "prediction"] = [50.0, 51.0, 52.0, 53.0]
    assert signalling.form_signals(numbers, _quotes()).empty


def test_only_loud_enough_signals_reach_the_primary_set():
    formed = signalling.form_signals(_numbers(), _quotes()).set_index("game_id")
    assert formed.loc[100, "selection"] == "primary"   # 12 points, over threshold
    assert formed.loc[101, "selection"] == "observed"  # half a point
    assert formed.loc[103, "selection"] == "observed"


def test_margin_signals_before_week_five_are_not_primary():
    """Phase 4, Track 6: early-season margins beat the close 51.2% of the time
    at z = 0.98. They are recorded and excluded."""
    quotes = _quotes().assign(market="margin", week=2, line=[0.0] * 4)
    numbers = _numbers().assign(market="margin", week=2, prediction=[20.0] * 4)
    formed = signalling.form_signals(numbers, quotes)
    assert set(formed["selection"]) == {"observed"}
    assert set(signalling.form_signals(
        numbers.assign(week=8), quotes.assign(week=8)
    )["selection"]) == {"secondary"}


# ---------------------------------------------------------------------------
# Grading
# ---------------------------------------------------------------------------


def _graded_fixture():
    quotes = _quotes()
    formed = signalling.form_signals(_numbers(), quotes)
    now = datetime.now(UTC).replace(microsecond=0)
    games = quotes[["game_id"]].drop_duplicates().assign(
        kickoff=(now + timedelta(hours=1)).isoformat(), completed=True
    )
    closes = pd.DataFrame(
        {
            "captured_at": [(now + timedelta(minutes=30)).isoformat()] * 4,
            "game_id": range(100, 104),
            "book": "TestBook",
            "market": "total",
            # over 50 -> 52 (beat); over 51 -> 51 (push); under 52 -> 54 (lost)
            "line": [52.0, 51.0, 54.0, 51.4],
            "price": -110.0,
            "open_line": [49.0, 51.0, 54.0, 53.0],
            "open_price": -110.0,
            "status": "STATUS_FINAL",
            "last_seen_at": now.isoformat(),
        }
    )
    return formed, closes, games


def test_grading_produces_exactly_three_outcomes():
    formed, closes, games = _graded_fixture()
    graded = grading.grade(formed, closes, games).set_index("signal_id")
    by_game = formed.set_index("game_id")["signal_id"]
    assert graded.loc[by_game[100], "result"] == "beat"
    assert graded.loc[by_game[101], "result"] == "push"
    assert graded.loc[by_game[102], "result"] == "lost"
    assert set(graded["result"]) <= {"beat", "push", "lost"}


def test_clv_is_graded_from_the_entry_line_not_the_opener():
    """Grading against the opener would credit Atlas with movement that
    happened before it spoke. That difference is Gamma's third kill criterion,
    so the two must stay separate."""
    formed, closes, games = _graded_fixture()
    graded = grading.grade(formed, closes, games).set_index("signal_id")
    signal = formed.set_index("game_id").loc[100]
    row = graded.loc[signal["signal_id"]]
    assert row["clv_points"] == pytest.approx(52.0 - 50.0)     # from entry
    assert row["clv_from_open"] == pytest.approx(52.0 - 49.0)  # from the open
    assert row["pre_signal_move"] == pytest.approx(50.0 - 49.0)
    assert bool(row["execution_flagged"]) is True


def test_a_game_that_has_not_kicked_off_is_not_graded():
    formed, closes, games = _graded_fixture()
    future = games.assign(
        completed=False,
        kickoff=(datetime.now(UTC) + timedelta(days=3)).isoformat(),
    )
    assert grading.grade(formed, closes, future).empty


def test_an_in_play_line_never_becomes_the_close():
    """A quote captured after kickoff is an in-play number. Grading against it
    would silently score Atlas on a market it never took."""
    formed, closes, games = _graded_fixture()
    late = closes.assign(
        captured_at=(datetime.now(UTC) + timedelta(hours=5)).isoformat()
    )
    assert grading.grade(formed, late, games).empty


# ---------------------------------------------------------------------------
# Scorecard and kill criteria
# ---------------------------------------------------------------------------


def _frame(beats: int, losses: int, pushes: int = 0, *, clv: float = 1.0) -> pd.DataFrame:
    results = ["beat"] * beats + ["lost"] * losses + ["push"] * pushes
    points = [clv] * beats + [-clv] * losses + [0.0] * pushes
    return pd.DataFrame(
        {
            "signal_id": [f"s{i}" for i in range(len(results))],
            "selection": "primary",
            "result": results,
            "clv_points": points,
            "execution_flagged": False,
            "season": 2026,
            "week": 6,
            "book": "TestBook",
        }
    )


def test_a_push_is_not_a_loss():
    """Phase 3 learned this the expensive way: counting no-move games as
    losses understated every beat rate by about six points."""
    without = sc.by_selection(_frame(60, 40)).set_index("selection").loc["primary"]
    with_pushes = sc.by_selection(_frame(60, 40, 20)).set_index("selection").loc["primary"]
    assert without["beat_rate"] == pytest.approx(0.60)
    assert with_pushes["beat_rate"] == pytest.approx(0.60)
    assert with_pushes["pushes"] == 20


def test_kill_criteria_match_the_frozen_gamma_thresholds():
    """These numbers were pre-registered. A test pins them so a later edit is
    a visible change rather than a quiet one."""
    assert sc.KILL_BEAT_RATE == 0.55
    assert sc.KILL_MEAN_CLV == 0.49
    assert sc.SEASONS_REQUIRED == 2


def test_criteria_stay_undecided_until_the_sample_is_large_enough():
    """A 40% beat rate on ten signals is noise, and reporting it as a breach
    would terminate the project on nothing."""
    thin = sc.kill_criteria(_frame(4, 6))
    assert all(not c.decided for c in thin)

    plenty = sc.kill_criteria(_frame(40, 120, clv=0.1))
    assert all(c.decided for c in plenty)
    assert not plenty[0].passing


def test_criteria_ignore_the_observed_population():
    """The primary set is what Gamma's recommendation names. Letting the
    recorded-but-not-selected signals into the verdict would measure a
    different thing from the one that was pre-registered."""
    frame = pd.concat([_frame(40, 120, clv=0.1).assign(selection="observed"),
                       _frame(100, 30, clv=1.0)], ignore_index=True)
    criteria = sc.kill_criteria(frame)
    assert criteria[0].passing
    assert criteria[0].graded == 130


def test_a_signal_records_the_price_of_its_own_side():
    """The over's price for an over, the under's for an under, and which it is."""
    quotes = _quotes().assign(price=-115.0, other_price=-105.0)
    formed = signalling.form_signals(_numbers(), quotes).set_index("game_id")
    over, under = formed.loc[100], formed.loc[102]                    # 62 over 50; 41 under 52
    assert (over["direction"], over["entry_price"], over["entry_price_side"]) == ("over", -115.0, "over")
    assert (under["direction"], under["entry_price"], under["entry_price_side"]) == ("under", -105.0, "under")
    # A feed without the other side's price records none, rather than the wrong one.
    bare = signalling.form_signals(_numbers(), _quotes()).set_index("game_id")
    assert pd.isna(bare.loc[102, "entry_price"]) and pd.isna(bare.loc[102, "entry_price_side"])


def test_a_new_seasons_week_one_is_the_latest_week():
    from atlas.live import drift

    frame = pd.DataFrame({"season": [2025] * 3 + [2026], "week": [15, 15, 15, 1], "selection": "primary",
                          "created_ts": pd.Timestamp("2026-09-01", tz="UTC")})
    frame["period"] = frame["season"] * 100 + frame["week"]
    recent, history = drift._split(frame)
    assert list(recent["season"]) == [2026] and len(history) == 3
    alert = drift.volume_alerts(frame)[0]
    assert alert.detail.startswith("week 1:")


def test_the_weekly_scorecard_keeps_seasons_apart():
    frame = pd.concat([_frame(3, 1).assign(season=2025, week=3), _frame(1, 3).assign(season=2026, week=3)])
    weekly = sc.scorecard(frame, by="week")
    assert list(zip(weekly["season"], weekly["week"], strict=True)) == [(2025, 3), (2026, 3)]


def test_a_started_game_with_no_close_is_an_exception(store):
    from atlas.live import quality

    formed = signalling.form_signals(_numbers(), _quotes())
    store.append_new_only("signals", formed)
    kicked = datetime.now(UTC) - timedelta(hours=1)
    store.upsert("games", pd.DataFrame({"game_id": range(100, 104), "kickoff": kicked.isoformat()}))
    # Only captured after kickoff: an in-play number, never a close.
    late = _snaps(((kicked + timedelta(minutes=30)).isoformat(), 50.0, -110.0, -110.0))
    store.append_on_change("snapshots", late)
    found = quality.check_signals(store)
    assert (found["check"] == "closing line exists").sum() == len(formed)


def test_the_beat_rate_carries_its_interval():
    low, high, p = sc.beat_interval(60, 100)
    assert low < 0.60 < high and 0.49 < low < 0.51
    assert p == pytest.approx(0.0284, abs=1e-3)
    row = sc.by_selection(_frame(60, 40)).set_index("selection").loc["primary"]
    assert row["beat_low"] == pytest.approx(low) and row["p_value"] == pytest.approx(p)
