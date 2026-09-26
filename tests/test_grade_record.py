"""The grade record: each card's grade as published before kickoff, against what happened."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from atlas.live.store import Store
from atlas.site import grade_record as gr
from atlas.site import render

NOW = datetime(2026, 9, 26, 14, 0, tzinfo=UTC)


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("ATLAS_TRACKING_DIR", str(tmp_path))
    return Store.open()


def _card(game_id=1, *, kickoff=None, letter=None):
    from test_site import _card as site_card

    card = site_card()
    card.game_id = game_id
    card.kickoff = kickoff or NOW + timedelta(days=1)
    if letter:
        card.grade = replace(card.grade, letter=letter)
    return card


def test_a_card_is_logged_with_its_claim_on_the_spread_it_showed(store):
    card = _card()
    assert gr.log([card], NOW, store) == 1
    row = store.read(gr.TABLE).iloc[0]
    p = card.cover_probability
    assert row["letter"] == row["first_letter"] == card.grade.letter
    assert row["line"] == pytest.approx(card.market_margin)
    assert row["claimed"] == pytest.approx(max(p, 1 - p), abs=1e-3)
    assert bool(row["home_side"]) == (p >= 0.5)
    assert row["market"] == "margin"


def test_a_card_keeps_its_first_letter_and_takes_its_latest(store):
    """The first letter a reader could have seen is kept for grade movement;
    the last before kickoff is the one the record grades."""
    gr.log([_card(letter="B")], NOW, store)
    gr.log([_card(letter="D")], NOW + timedelta(hours=3), store)
    t = store.read(gr.TABLE)
    assert len(t) == 1
    assert t.iloc[0]["first_letter"] == "B" and t.iloc[0]["letter"] == "D"
    assert t.iloc[0]["first_at"] == NOW.isoformat()
    assert t.iloc[0]["published_at"] == (NOW + timedelta(hours=3)).isoformat()


def test_a_card_whose_game_has_started_is_never_logged(store):
    """A grade logged after kickoff is not a claim made in advance."""
    assert gr.log([_card(kickoff=NOW - timedelta(minutes=1))], NOW, store) == 0
    assert store.read(gr.TABLE).empty


def _logged(line, home_side, claimed=0.6, letter="B", game_id="1", sport="ncaaf"):
    return {"sport": sport, "game_id": game_id, "letter": letter, "line": line,
            "home_side": home_side, "claimed": claimed}


def test_the_side_that_happened_is_graded_on_the_line_the_card_showed():
    """line is a home margin, positive when home is favoured: a home side
    favoured by 7 that wins by 10 covers; by 7 is a push, which counts half."""
    record = pd.DataFrame([_logged(7.0, True, game_id="1"), _logged(7.0, False, game_id="2"),
                           _logged(7.0, True, game_id="3"), _logged(-3.5, True, game_id="4")])
    finals = pd.DataFrame({"game_id": ["1", "2", "3", "4"], "final_home": [31, 31, 24, 20],
                           "final_away": [21, 21, 17, 22]})
    won = gr.graded(record, finals).set_index("game_id")["won"]
    assert won["1"] == 1.0          # home by 10 against home -7: home covered
    assert won["2"] == 0.0          # the away side was Atlas's
    assert won["3"] == 0.5          # home by exactly 7: a push
    assert won["4"] == 1.0          # home lost by 2 as a 3.5-point underdog: covered


def test_a_card_with_no_final_is_not_graded_yet():
    record = pd.DataFrame([_logged(3.0, True, game_id="9")])
    assert gr.graded(record, pd.DataFrame({"game_id": ["1"], "final_home": [1], "final_away": [0]})).empty


def test_claimed_against_realised_by_letter():
    g = pd.DataFrame([
        {**_logged(1, True, claimed=0.60, letter="A"), "won": 1.0},
        {**_logged(1, True, claimed=0.50, letter="A"), "won": 0.0},
        {**_logged(1, True, claimed=0.70, letter="D"), "won": 0.5},
    ])
    rows = {r["letter"]: r for r in gr.by_letter(g)}
    assert [r["letter"] for r in gr.by_letter(g)] == [*gr.LETTERS, "All"]
    assert rows["A"]["cards"] == 2 and rows["A"]["claimed"] == pytest.approx(0.55)
    assert rows["A"]["realised"] == pytest.approx(0.5) and rows["A"]["gap"] == pytest.approx(-0.05)
    assert rows["B"]["cards"] == 0 and rows["B"]["gap"] is None
    assert rows["All"]["cards"] == 3 and rows["A"]["few"]


def test_the_page_shows_the_record_by_grade_and_passes_the_audit(tmp_path):
    from scripts.audit_site import audit

    g = pd.DataFrame([{**_logged(1, True, claimed=0.55, letter="B"), "won": 1.0}] * 40)
    page = render.record_page({}, since="today", grades={"ncaaf": gr.by_letter(g), "nfl": gr.by_letter(g.iloc[0:0])},
                              grades_since="26 September 2026")
    assert "By grade" in page and "Claimed" in page and "Realised" in page
    assert "<td>+45.0</td>" in page and "Gap, pts" in page      # 100% realised against 55% claimed
    assert "No graded card yet" in page                          # the NFL, with nothing graded
    assert "It began on 26 September 2026" in page
    (tmp_path / "record.html").write_text(page)
    blocking, _ = audit(tmp_path)
    assert blocking["forbidden vocabulary"] == [] and blocking["a named side"] == []


def test_without_a_grade_record_the_page_is_as_it_was():
    assert "By grade" not in render.record_page({}, since="today")


def test_end_to_end_through_the_store(store):
    """Logged before kickoff, final in the tracking store's games, graded."""
    card = _card(game_id=401)
    gr.log([card], NOW, store)
    store.upsert("games", pd.DataFrame([{"game_id": 401, "completed": True, "home_score": 30, "away_score": 20,
                                         "kickoff": card.kickoff.isoformat()}]))
    result = gr.build(store)
    assert result["ncaaf"][-1]["cards"] == 1
    assert result["nfl"][-1]["cards"] == 0
