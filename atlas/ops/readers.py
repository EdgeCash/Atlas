"""Readers, from the site's own counter, for the owner page.

    python -m atlas.ops.readers          # the same tables, in a terminal

GitHub Pages keeps no access log, so `atlas/ops/analytics.py` has nothing to
read. The counter (`counter/worker.js`) is the first-party counter
`POST_LAUNCH_METRICS.md` allowed for: daily counts of page views, each
device's first visit of the day (new or returning) and card panels opened,
and nothing that identifies a reader.

The tables go only into the owner page's ciphertext. The repository is
public, and "most viewed cards" is an operator's view that
`ANALYTICS_SPEC_FINAL.md` keeps off the site; so nothing here is committed or
printed by a workflow. The headline number is the one the spec names: the
share of card views that were of cards marked down (D or F), read from the
grade each card showed (`tracking/card_grades.csv`).
"""

from __future__ import annotations

import os
import sys
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from pathlib import PurePosixPath

import pandas as pd

from atlas.util import get_logger, http_get

LOG = get_logger(__name__)

URL_ENV = "ATLAS_COUNTER_URL"
TOKEN_ENV = "ATLAS_COUNTER_TOKEN"
#: How far back the owner page reads, and the window its tables cover.
HISTORY_DAYS = 120
WINDOW_DAYS = 7
TOP = 10
MARKED_DOWN = ("D", "F")


def configured() -> bool:
    return bool(os.environ.get(URL_ENV, "").strip() and os.environ.get(TOKEN_ENV, "").strip())


def fetch(since: date) -> list[dict]:
    """Every count since a day, from the counter."""
    url = os.environ[URL_ENV].strip().rstrip("/") + "/counts"
    response = http_get(url, params={"since": since.isoformat()},
                        headers={"Authorization": f"Bearer {os.environ[TOKEN_ENV].strip()}"}, retries=2, timeout=30)
    return response.json()["rows"]


def kind(path: str) -> str:
    """What a counted page is, from its path from the site root."""
    if path in ("", "index.html"):
        return "home"
    if path in ("ncaaf.html", "nfl.html"):
        return "board"
    if path.startswith(("team/", "nfl/team/")):
        return "team"
    if path.startswith(("ncaaf/", "nfl/")):
        return "card"
    return PurePosixPath(path).stem or "other"


def grades(store) -> dict[str, str]:
    """A card's page to the last letter it showed before kickoff."""
    t = store.read("card_grades")
    t = t[t["path"].notna() & t["letter"].notna()]
    return dict(zip(t["path"].astype(str), t["letter"].astype(str), strict=True))


def summary(rows: list[dict], letters: dict[str, str], today: date) -> dict:
    """The counts, as the owner page shows them: a window of recent days,
    and totals since the counter began."""
    frame = pd.DataFrame(rows, columns=["day", "event", "path", "source", "detail", "n"])
    frame["n"] = pd.to_numeric(frame["n"], errors="coerce").fillna(0).astype(int)
    frame = frame.fillna("")
    start = (today - timedelta(days=WINDOW_DAYS - 1)).isoformat()
    recent = frame[frame["day"] >= start]
    views = recent[recent["event"] == "view"].assign(kind=lambda f: f["path"].map(kind))
    cards = views[views["kind"] == "card"]
    visits = recent[recent["event"] == "visit"]
    panels = recent[recent["event"] == "panel"]

    by_day = []
    for offset in range(WINDOW_DAYS):
        d = (today - timedelta(days=offset)).isoformat()
        v, c, s = views[views["day"] == d], cards[cards["day"] == d], visits[visits["day"] == d]
        new = int(s.loc[s["detail"] == "new", "n"].sum())
        back = int(s.loc[s["detail"] == "return", "n"].sum())
        by_day.append({"day": d, "views": int(v["n"].sum()), "cards": int(c["n"].sum()),
                       "visits": new + back, "new": new, "return": back})

    graded = Counter()
    for path, n in zip(cards["path"], cards["n"], strict=True):
        if path in letters:
            graded[letters[path]] += int(n)
    card_views = int(cards["n"].sum())
    all_views = frame[frame["event"] == "view"]
    all_visits = frame[frame["event"] == "visit"]
    return {
        "first_day": frame["day"].min() if len(frame) else None,
        "total_views": int(all_views["n"].sum()),
        "total_visits": int(all_visits["n"].sum()),
        "by_day": by_day,
        "by_kind": Counter(dict(views.groupby("kind")["n"].sum().astype(int))),
        "by_source": Counter(dict(views.groupby("source")["n"].sum().astype(int))),
        "cards": Counter(dict(cards.groupby("path")["n"].sum().astype(int))),
        "card_views": card_views,
        "by_grade": graded,
        "marked_down": (sum(graded[x] for x in MARKED_DOWN) / sum(graded.values())) if graded else None,
        "panels": Counter(dict(panels.groupby("detail")["n"].sum().astype(int))),
    }


def _share(n: int, total: int) -> str:
    return f"{n / total:.0%}" if total else "–"


def _count(n: int, noun: str) -> str:
    return f"{n:,} {noun}" + ("" if n == 1 else "s")


def _day(d: str) -> str:
    return datetime.strptime(d, "%Y-%m-%d").strftime("%a %-d %b")


def _card_name(path: str) -> str:
    return PurePosixPath(path).stem.replace("-", " ")


def section(s: dict) -> dict:
    """The owner page's Readers card: its words and tables travel in the payload."""
    views = sum(s["by_kind"].values())
    notes = [
        "Counted by the site's own counter: page views, each device's first visit of the day (new or "
        "returning) and card panels opened. No cookie and nothing that identifies a reader. Browsers that "
        "ask not to be tracked, and crawlers, are not counted, so these run low; and anyone can send the "
        "counter a hit, so read the trend, not the exact number.",
        f"Since {_day(s['first_day'])}: {_count(s['total_views'], 'page view')}, "
        f"{_count(s['total_visits'], 'visit')}."
        if s["first_day"] else "Nothing counted yet.",
    ]
    if s["marked_down"] is not None:
        notes.append(f"Marked down (D or F): {s['marked_down']:.0%} of the graded card views in the last "
                     f"{WINDOW_DAYS} days. If this is near zero, nobody reads the cards where Atlas says not "
                     "to trust it.")
    # A visit is a device's first page of the day, so visits are new plus returning.
    tables = [{"title": f"Last {WINDOW_DAYS} days", "head": ["Day", "Views", "Cards", "New", "Returning"],
               "rows": [[_day(r["day"]), f"{r['views']:,}", f"{r['cards']:,}", f"{r['new']:,}",
                         f"{r['return']:,}"] for r in s["by_day"]]}]

    def counted(title: str, head: str, counter: Counter, total: int, name=str) -> None:
        if counter:
            tables.append({"title": title, "head": [head, "Views", "Share"],
                           "rows": [[name(k), f"{n:,}", _share(n, total)] for k, n in counter.most_common(TOP)]})

    counted("By page", "Page", s["by_kind"], views)
    counted("Where views came from", "Source", s["by_source"], views)
    counted("Grade of the cards opened", "Grade", s["by_grade"], sum(s["by_grade"].values()))
    if s["panels"]:
        tables.append({"title": "Card panels opened", "head": ["Panel", "Opens", "Per 100 card views"],
                       "rows": [[k.replace("-", " ").capitalize(), f"{n:,}",
                                 f"{100 * n / s['card_views']:.0f}" if s["card_views"] else "–"]
                                for k, n in s["panels"].most_common()]})
    counted("Most viewed cards", "Card", s["cards"], s["card_views"], name=_card_name)
    return {"title": "Readers", "notes": notes, "tables": tables}


def build(store=None, today: date | None = None) -> dict | None:
    """The owner page's Readers section, or None when there is no counter
    or it cannot be read. Never raises: the owner page builds without it."""
    if not configured():
        return None
    try:
        from atlas.live.store import Store
        from atlas.site.html import eastern

        today = today or eastern(datetime.now(UTC)).date()
        rows = fetch(today - timedelta(days=HISTORY_DAYS))
        return section(summary(rows, grades(store or Store.open()), today))
    except Exception as error:  # noqa: BLE001 - the type only
        LOG.error("readers not read: %s", type(error).__name__)
        return None


def text(sec: dict) -> str:
    """The section as plain text, for a terminal."""
    out = [sec["title"], "", *sec["notes"], ""]
    for t in sec["tables"]:
        out.append(t["title"])
        for row in [t["head"], *t["rows"]]:
            out.append("  " + row[0].ljust(40) + "".join(str(c).rjust(20) for c in row[1:]))
        out.append("")
    return "\n".join(out)


def main() -> int:
    if not configured():
        print(f"Set {URL_ENV} and {TOKEN_ENV} to read the counter.", file=sys.stderr)
        return 1
    sec = build()
    if sec is None:
        return 1
    print(text(sec))
    return 0


if __name__ == "__main__":
    sys.exit(main())
