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
