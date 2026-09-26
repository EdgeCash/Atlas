"""Readers: the site's own counter, its beacon, and the owner page's Readers section."""

from __future__ import annotations

import shutil
import subprocess
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from atlas.live.store import Store
from atlas.ops import readers
from atlas.site import render

ROOT = Path(__file__).resolve().parents[1]
TODAY = date(2026, 10, 3)


def _row(day, event, path="", source="", detail="", n=1):
    return {"day": day, "event": event, "path": path, "source": source, "detail": detail, "n": n}


ROWS = [
    _row("2026-10-03", "view", "ncaaf/a.html", "x", n=6),
    _row("2026-10-03", "view", "ncaaf/b.html", "direct", n=2),
    _row("2026-10-03", "view", "ncaaf.html", "internal", n=5),
    _row("2026-10-02", "view", "index.html", "search", n=3),
    _row("2026-10-03", "visit", detail="new", n=4),
    _row("2026-10-03", "visit", detail="return", n=2),
    _row("2026-10-03", "panel", "ncaaf/a.html", detail="how-this-grade-was-computed", n=2),
    _row("2026-09-20", "view", "ncaaf/old.html", "x", n=100),          # outside the window
]


def test_pages_are_read_by_kind():
    assert readers.kind("index.html") == "home" and readers.kind("") == "home"
    assert readers.kind("nfl.html") == "board"
    assert readers.kind("ncaaf/utah-utes-iowa-state.html") == "card" and readers.kind("nfl/bills-jets.html") == "card"
    assert readers.kind("team/iowa-state.html") == "team" and readers.kind("nfl/team/bills.html") == "team"
    assert readers.kind("record.html") == "record"


def test_the_summary_counts_the_window_and_the_total():
    s = readers.summary(ROWS, {"ncaaf/a.html": "D", "ncaaf/b.html": "B"}, TODAY)
    today = s["by_day"][0]
    assert today == {"day": "2026-10-03", "views": 13, "cards": 8, "visits": 6, "new": 4, "return": 2}
    assert len(s["by_day"]) == readers.WINDOW_DAYS
    assert s["by_kind"] == {"card": 8, "board": 5, "home": 3}
    assert s["total_views"] == 116 and s["first_day"] == "2026-09-20"
    assert s["by_grade"] == {"D": 6, "B": 2}
    assert s["marked_down"] == pytest.approx(0.75)                  # the headline number
    assert s["panels"] == {"how-this-grade-was-computed": 2}


def test_the_section_carries_its_own_words_and_tables():
    sec = readers.section(readers.summary(ROWS, {"ncaaf/a.html": "D"}, TODAY))
    assert sec["title"] == "Readers"
    words = " ".join(sec["notes"])
    assert "nothing that identifies a reader" in words and "Marked down (D or F): 100%" in words
    titles = [t["title"] for t in sec["tables"]]
    assert titles[0] == "Last 7 days" and "Card panels opened" in titles and "Most viewed cards" in titles
    panels = next(t for t in sec["tables"] if t["title"] == "Card panels opened")
    assert panels["rows"] == [["How this grade was computed", "2", "25"]]   # 2 opens per 8 card views


def test_an_empty_counter_still_makes_a_section():
    sec = readers.section(readers.summary([], {}, TODAY))
    assert "Nothing counted yet." in sec["notes"]


def test_no_counter_no_section_and_a_failure_never_raises(monkeypatch):
    monkeypatch.delenv(readers.URL_ENV, raising=False)
    assert readers.build() is None
    monkeypatch.setenv(readers.URL_ENV, "https://counter.example")
    monkeypatch.setenv(readers.TOKEN_ENV, "t")

    def down(since):
        raise ConnectionError("counter down")

    monkeypatch.setattr(readers, "fetch", down)
    assert readers.build() is None


def test_card_views_are_graded_from_the_logged_card(tmp_path, monkeypatch):
    """The grade log keeps each card's page, so a view reads as the letter
    the card showed."""
    monkeypatch.setenv("ATLAS_TRACKING_DIR", str(tmp_path))
    from test_grade_record import _card

    from atlas.site import grade_record as gr

    card = _card(kickoff=datetime.now(UTC) + timedelta(days=1))
    store = Store.open()
    gr.log([card], datetime.now(UTC), store)
    assert readers.grades(store) == {card.path: card.grade.letter}
    monkeypatch.setenv(readers.URL_ENV, "https://counter.example")
    monkeypatch.setenv(readers.TOKEN_ENV, "t")
    monkeypatch.setattr(readers, "fetch", lambda since: [_row(TODAY.isoformat(), "view", card.path, "x", n=3)])
    sec = readers.build(store, today=TODAY)
    grade = next(t for t in sec["tables"] if t["title"] == "Grade of the cards opened")
    assert grade["rows"] == [[card.grade.letter, "3", "100%"]]


def test_the_beacon_is_on_the_page_only_with_a_counter(monkeypatch):
    from test_site import _card, _page

    page = _page(_card())
    assert "atlas-counter" not in page and "readers.js" not in page
    assert 'data-panel="market-detail"' in page                     # the panels are named either way
    monkeypatch.setattr(render, "COUNTER_URL", "https://atlas-readers.example.workers.dev")
    page = _page(_card())
    assert '<meta name="atlas-counter" content="https://atlas-readers.example.workers.dev">' in page
    assert '<script src="../assets/readers.js?v=' in page


def test_the_beacon_respects_a_request_not_to_be_tracked():
    js = (ROOT / "atlas/site/assets/readers.js").read_text()
    assert "globalPrivacyControl" in js and "doNotTrack" in js
    assert "document.cookie" not in js


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_the_worker():
    done = subprocess.run(["node", "--test", "counter/worker.test.mjs"], cwd=ROOT, capture_output=True,
                          text=True, timeout=120)
    assert done.returncode == 0, done.stdout[-2000:] + done.stderr[-2000:]


def test_the_counter_schema_keeps_nothing_that_identifies_a_reader():
    schema = (ROOT / "counter/schema.sql").read_text().lower()
    columns = [line.split()[0] for line in schema.splitlines() if line.startswith("  ") and "primary" not in line]
    assert columns == ["day", "event", "path", "source", "detail", "n"]


def test_the_grade_log_keeps_the_card_path(tmp_path, monkeypatch):
    monkeypatch.setenv("ATLAS_TRACKING_DIR", str(tmp_path))
    t = Store.open().read("card_grades")
    assert "path" in t.columns and isinstance(t, pd.DataFrame)
