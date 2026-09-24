"""One name per sportsbook: the feed's two spellings of DraftKings."""

from __future__ import annotations

import pandas as pd

from atlas.live import books
from atlas.live import grade as grading
from atlas.live.audit import signal_uuid
from atlas.live.store import Store


def test_every_spelling_is_one_book():
    assert books.canonical("Draft Kings") == books.canonical("DraftKings") == books.canonical("draftkings ")
    assert books.canonical("Draft Kings") == "DraftKings"
    assert books.canonical("Caesars") == "Caesars" and books.canonical(None) is None


def _signal(book, created, entry):
    return {"signal_id": signal_uuid(1, "total", book), "created_at": created, "run_id": "r", "game_id": 1,
            "season": 2026, "week": 4, "market": "total", "book": book, "open_line": 50.0, "entry_line": entry,
            "entry_price": -110.0, "atlas_number": 40.0, "disagreement": -10.0, "direction": "under",
            "selection": "primary", "model_version": "m"}


def test_the_record_is_reconciled_once_and_grades_against_one_line(tmp_path):
    store = Store.open(tmp_path)
    store.write("snapshots", pd.DataFrame([
        {"captured_at": "2026-09-23T10:00:00+00:00", "game_id": 1, "book": "DraftKings", "market": "total",
         "line": 50.0, "price": -110.0},
        {"captured_at": "2026-09-23T20:00:00+00:00", "game_id": 1, "book": "Draft Kings", "market": "total",
         "line": 48.0, "price": -110.0},                              # the later look, under the other name
    ]))
    # The feed's second spelling minted a second signal a day later; only it was graded.
    later = _signal("Draft Kings", "2026-09-23T20:00:00+00:00", 48.0)
    store.write("signals", pd.DataFrame([_signal("DraftKings", "2026-09-22T12:00:00+00:00", 50.0), later]))
    store.write("grades", pd.DataFrame([{"signal_id": later["signal_id"], "graded_at": "x", "close_line": 48.0}]))

    got = books.reconcile(store)
    assert got["snapshots_renamed"] == 1 and got["signals_removed"] == 1
    signals = store.read("signals")
    assert len(signals) == 1 and signals.loc[0, "book"] == "DraftKings" and signals.loc[0, "entry_line"] == 50.0
    assert signals.loc[0, "signal_id"] == signal_uuid(1, "total", "DraftKings")      # a later poll cannot restate it
    assert store.read("grades").empty                                                 # the removed signal's grade
    assert set(store.read("snapshots")["book"]) == {"DraftKings"}
    assert not any(books.reconcile(store).values())

    games = pd.DataFrame([{"game_id": 1, "kickoff": "2026-09-24T00:00:00+00:00", "completed": "True"}])
    graded = grading.grade(signals, store.read("snapshots"), games)
    assert graded.loc[0, "close_line"] == 48.0 and graded.loc[0, "clv_points"] == 2.0   # the latest look, either name


def test_a_signal_only_under_the_other_spelling_is_reissued(tmp_path):
    store = Store.open(tmp_path)
    only = _signal("Draft Kings", "2026-09-23T20:00:00+00:00", 48.0)
    store.write("signals", pd.DataFrame([only]))
    store.write("grades", pd.DataFrame([{"signal_id": only["signal_id"], "graded_at": "x", "close_line": 47.0}]))
    got = books.reconcile(store)
    assert got["signals_reissued"] == 1 and got["grades_moved"] == 1 and got["grades_cleared"] == 0
    new_id = signal_uuid(1, "total", "DraftKings")
    assert store.read("signals").loc[0, "signal_id"] == new_id
    assert store.read("grades").loc[0, "signal_id"] == new_id


def test_a_grade_made_against_one_spelling_is_made_again(tmp_path):
    store = Store.open(tmp_path)
    kept = _signal("DraftKings", "2026-09-22T12:00:00+00:00", 50.0)
    store.write("signals", pd.DataFrame([kept]))
    store.write("snapshots", pd.DataFrame([
        {"captured_at": "2026-09-23T10:00:00+00:00", "game_id": 1, "book": "DraftKings", "market": "total",
         "line": 50.0, "price": -110.0},
        {"captured_at": "2026-09-23T20:00:00+00:00", "game_id": 1, "book": "Draft Kings", "market": "total",
         "line": 48.0, "price": -110.0},
    ]))
    # Graded against the DraftKings spelling alone: a close of 50, no move - wrong.
    store.write("grades", pd.DataFrame([{"signal_id": kept["signal_id"], "graded_at": "x", "close_line": 50.0}]))
    got = books.reconcile(store)
    assert got["grades_cleared"] == 1 and store.read("grades").empty
