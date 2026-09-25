"""CLV in probability: prices and key numbers, not just half-points."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from atlas.live import grade as grading
from atlas.live import probability as pr
from atlas.live.store import Store


def test_prices_read_as_probabilities_without_the_margin():
    assert pr.implied(-110) == pytest.approx(110 / 210)
    assert pr.implied(150) == pytest.approx(0.4)
    assert pr.no_vig(-110, -110) == pytest.approx(0.5)
    assert pr.no_vig(-130, 110) == pytest.approx((130 / 230) / (130 / 230 + 100 / 210))
    assert np.isnan(pr.no_vig(-110, float("nan")))


def test_the_centre_reproduces_the_quoted_probability():
    shape = pr.default_shape("ncaaf", "total")
    for line, prob in ((52.5, 0.5), (52.5, 0.56), (-7.0, 0.45)):
        centre = pr.centre_for(shape, line, prob)
        assert pr.first_side(shape.pmf(centre), line) == pytest.approx(prob, abs=1e-6)


def test_a_move_through_a_key_number_is_worth_more():
    """Half a point through 3 moves more probability than half a point at 10."""
    factor = np.ones(len(pr.SUPPORT))
    factor[np.isin(pr.SUPPORT, [-3, 3])] = 2.7
    shape = pr.Shape(15.3, factor)
    through_three = pr.at_line(shape, 3.5, 0.5, 2.5) - 0.5
    at_ten = pr.at_line(shape, 10.5, 0.5, 9.5) - 0.5
    assert through_three > 1.5 * at_ten > 0


def _fixture(close_line, close_price, close_other, direction="over"):
    now = datetime.now(UTC).replace(microsecond=0)
    kickoff = now - timedelta(hours=1)
    entry_at = kickoff - timedelta(days=2)
    signals = pd.DataFrame({
        "signal_id": ["s1"], "created_at": [entry_at.isoformat()], "game_id": [100], "book": ["B"],
        "market": ["total"], "entry_line": [50.5], "open_line": [50.5], "direction": [direction]})
    snapshots = pd.DataFrame({
        "captured_at": [entry_at.isoformat(), (kickoff - timedelta(hours=2)).isoformat()],
        "game_id": [100, 100], "book": ["B", "B"], "market": ["total", "total"],
        "line": [50.5, close_line], "price": [-110.0, close_price], "other_price": [-110.0, close_other]})
    games = pd.DataFrame({"game_id": [100], "kickoff": [kickoff.isoformat()], "completed": [False]})
    return signals, snapshots, games


def test_a_price_move_at_the_same_line_is_not_a_push():
    signals, snapshots, games = _fixture(50.5, -130.0, 110.0)
    row = grading.grade(signals, snapshots, games).iloc[0]
    assert row["clv_points"] == 0 and row["result"] == "push"
    assert row["entry_prob"] == pytest.approx(0.5) and not row["prob_assumed"]
    assert row["clv_prob"] == pytest.approx(pr.no_vig(-130, 110) - 0.5)


def test_the_side_decides_the_sign():
    signals, snapshots, games = _fixture(52.5, -110.0, -110.0)
    over = grading.grade(signals, snapshots, games).iloc[0]
    under = grading.grade(signals.assign(direction="under"), snapshots, games).iloc[0]
    assert over["clv_prob"] > 0.03 and under["clv_prob"] == pytest.approx(-over["clv_prob"])
    assert over["close_prob"] + under["close_prob"] == pytest.approx(1.0)


def test_a_one_sided_price_is_read_against_the_standard_market_and_flagged():
    signals, snapshots, games = _fixture(50.5, -130.0, float("nan"))
    row = grading.grade(signals, snapshots, games).iloc[0]
    assert row["prob_assumed"]
    assert row["close_prob"] == pytest.approx(pr.implied(-130) / pr.STANDARD_BOOK)
    assert pr.quoted_first(float("nan"), float("nan")) == (0.5, True)


def test_a_signal_formed_before_its_first_snapshot_reads_the_quote_at_its_line():
    signals, snapshots, games = _fixture(52.5, -110.0, -110.0)
    late = snapshots.copy()
    late.loc[0, "price"], late.loc[0, "other_price"] = -125.0, 105.0
    late.loc[0, "captured_at"] = (pd.Timestamp(signals["created_at"].iloc[0]) + pd.Timedelta(minutes=20)).isoformat()
    row = grading.grade(signals, late, games).iloc[0]
    assert row["entry_prob"] == pytest.approx(pr.no_vig(-125, 105)) and not row["prob_assumed"]


def test_shapes_round_trip_through_the_store(tmp_path):
    from atlas.models.lattice import Lattice

    lattice = Lattice(support=np.arange(-5, 6), factor=np.r_[np.ones(8), 2.5, np.ones(2)], sigma=14.0, games=10)
    store = Store.open(tmp_path)
    store.write("market_shape", pr.shapes_frame("ncaaf", lattice, 16.0))
    shapes = pr.load_shapes(store.read("market_shape"))
    margin, total = shapes[("ncaaf", "margin")], shapes[("ncaaf", "total")]
    assert margin.sigma == 14.0 and margin.factor[list(pr.SUPPORT).index(3)] == 2.5
    assert total.sigma == 16.0 and (total.factor == 1.0).all()


def test_old_grades_get_their_probability_once(tmp_path, monkeypatch):
    from atlas.live import __main__ as live

    signals, snapshots, games = _fixture(52.5, -110.0, -110.0)
    store = Store.open(tmp_path)
    store.write("signals", signals)
    store.write("snapshots", snapshots)
    store.write("games", games)
    old = grading.grade(signals, snapshots, games).drop(columns=["entry_prob", "close_prob", "clv_prob",
                                                                 "prob_assumed"])
    store.write("grades", old)
    assert live._grade(store) == 0
    graded = store.read("grades").iloc[0]
    assert graded["clv_points"] == 2.0 and graded["clv_prob"] > 0.03
