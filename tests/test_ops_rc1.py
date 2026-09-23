"""RC1: analytics, backups and the SEO surface.

`tests/test_ops.py` covers the Operations-phase monitors and
`tests/test_ops_schedule.py` the automation layer. This covers the release
candidate's three additions, and the one property that matters most about
each: analytics never identifies a reader, a backup can be read back, and the
SEO tags point where they claim to.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from atlas.live.store import SCHEMA
from atlas.ops import analytics, backup

LOG_LINE = (
    '203.0.113.{n} - - [23/Sep/2026:14:0{n}:00 +0000] '
    '"GET {path} HTTP/1.1" 200 12345 "{referrer}" "{agent}"'
)
BROWSER = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0) AppleWebKit/605.1.15"
CRAWLER = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"


def _log(tmp_path: Path, rows: list[tuple[str, str, str]]) -> Path:
    path = tmp_path / "access.log"
    path.write_text("\n".join(
        LOG_LINE.format(n=i % 10, path=p, referrer=r, agent=a)
        for i, (p, r, a) in enumerate(rows)
    ) + "\n")
    return path


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------


def test_traffic_is_counted_by_page_type(tmp_path):
    path = _log(tmp_path, [
        ("/", "-", BROWSER),
        ("/index.html", "-", BROWSER),
        ("/ncaaf/utah-utes-iowa-state.html", "-", BROWSER),
        ("/team/georgia-bulldogs.html", "-", BROWSER),
        ("/about.html", "-", BROWSER),
    ])
    traffic = analytics.read([path])
    assert traffic.page_views == 5
    assert traffic.by_kind["board"] == 2
    assert traffic.by_kind["card"] == 1
    assert traffic.by_kind["team"] == 1


def test_assets_and_crawlers_are_not_readers(tmp_path):
    """A page view should mean a person looked at a page."""
    path = _log(tmp_path, [
        ("/assets/atlas.css", "-", BROWSER),
        ("/assets/logos/61.png", "-", BROWSER),
        ("/sitemap.xml", "-", BROWSER),
        ("/index.html", "-", CRAWLER),
        ("/index.html", "-", BROWSER),
    ])
    traffic = analytics.read([path])
    assert traffic.page_views == 1
    assert traffic.bots == 1


@pytest.mark.parametrize("referrer,expected", [
    ("https://t.co/abc123", "x"),
    ("https://www.threads.net/@someone", "threads"),
    ("https://l.instagram.com/?u=x", "instagram"),
    ("https://www.google.com/search?q=atlas", "search"),
    ("https://atlas.football/index.html", "internal"),
    ("-", "direct"),
    ("", "direct"),
    ("https://example.com/post", "other"),
])
def test_traffic_source_is_derived_from_the_referrer(referrer, expected):
    assert analytics.source(referrer) == expected


def test_the_headline_metric_needs_no_client_instrumentation(tmp_path):
    """The share of card views that were marked down - `POST_LAUNCH_METRICS`
    calls it the one number that matters. The build knows every grade, so the
    log does not have to carry it."""
    path = _log(tmp_path, [
        ("/ncaaf/a-b.html", "-", BROWSER),
        ("/ncaaf/a-b.html", "-", BROWSER),
        ("/ncaaf/c-d.html", "-", BROWSER),
        ("/ncaaf/e-f.html", "-", BROWSER),
    ])
    grades = {"a-b": "A", "c-d": "F", "e-f": "D"}
    traffic = analytics.read([path], grades=grades)
    assert traffic.by_grade == {"A": 2, "F": 1, "D": 1}
    assert traffic.marked_down_share == pytest.approx(0.5)
    assert traffic.cards.most_common(1) == [("a-b", 2)]


def test_analytics_stores_nothing_that_identifies_a_reader(tmp_path):
    """No IP, no user agent, no session. `POST_LAUNCH_METRICS.md`: nothing
    that identifies an individual reader across sessions."""
    path = _log(tmp_path, [("/index.html", "https://t.co/x", BROWSER)])
    traffic = analytics.read([path])
    serialised = repr(traffic)
    assert "203.0.113" not in serialised
    assert "Mozilla" not in serialised
    assert "iPhone" not in serialised


def test_a_malformed_log_line_is_skipped_not_fatal(tmp_path):
    path = tmp_path / "access.log"
    path.write_text("garbage\n"
                    + LOG_LINE.format(n=1, path="/index.html", referrer="-",
                                      agent=BROWSER) + "\n")
    assert analytics.read([path]).page_views == 1


# ---------------------------------------------------------------------------
# Backups
# ---------------------------------------------------------------------------


@pytest.fixture
def live(tmp_path) -> Path:
    """A small tracking store, with `grades` legitimately absent."""
    source = tmp_path / "tracking"
    source.mkdir()
    for table, columns in SCHEMA.items():
        if table == "grades":
            continue
        frame = pd.DataFrame([{c: f"{c}-{i}" for c in columns} for i in range(3)])
        frame.to_csv(source / f"{table}.csv", index=False)
    return source


def test_a_backup_can_be_read_back(tmp_path, live):
    """The only property that matters. A backup nobody has restored is a
    hypothesis."""
    created = backup.create(tmp_path / "backups", source=live)
    assert backup.verify(created) == []

    restored = tmp_path / "restored"
    rows = backup.restore(created, restored)
    assert rows["signals"] == 3
    assert pd.read_csv(live / "signals.csv").equals(
        pd.read_csv(restored / "signals.csv"))


def test_an_empty_critical_table_is_backed_up_as_its_header(tmp_path, live):
    """`grades` is empty until the first game finishes. A restore should
    still produce a complete store rather than one missing a file."""
    created = backup.create(tmp_path / "backups", source=live)
    assert (created / "grades.csv.gz").exists()
    restored = tmp_path / "restored"
    backup.restore(created, restored)
    frame = pd.read_csv(restored / "grades.csv")
    assert len(frame) == 0
    assert set(frame.columns) == set(SCHEMA["grades"])


def test_verification_notices_a_corrupted_file(tmp_path, live):
    created = backup.create(tmp_path / "backups", source=live)
    (created / "signals.csv.gz").write_bytes(b"not gzip")
    problems = backup.verify(created)
    assert problems and "signals" in problems[0]


def test_verification_notices_a_missing_critical_table(tmp_path, live):
    created = backup.create(tmp_path / "backups", source=live)
    (created / "signals.csv.gz").unlink()
    assert any("signals" in p for p in backup.verify(created))


def test_restore_refuses_to_overwrite_the_live_store(tmp_path, live):
    """Restoring over a running tracker is a decision an operator makes with
    their own hands."""
    from atlas.live.store import tracking_dir

    created = backup.create(tmp_path / "backups", source=live)
    with pytest.raises(ValueError, match="refusing"):
        backup.restore(created, tracking_dir())


def test_pruning_keeps_the_most_recent(tmp_path, live):
    at = tmp_path / "backups"
    made = []
    for _ in range(4):
        made.append(backup.create(at, source=live))
        # Timestamps are per-second; force distinct directory names.
        made[-1].rename(at / f"2026090{len(made)}T000000Z")
    backup.prune(keep=2, at=at)
    assert len(list(at.glob("*T*Z"))) == 2
    assert backup.latest(at).name == "20260904T000000Z"
