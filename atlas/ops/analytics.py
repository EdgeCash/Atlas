"""Traffic, from the web server's own access log.

`docs/POST_LAUNCH_METRICS.md` decided this before the site existed: server
logs and nothing else. No third-party script, no ad pixel, no cross-site
identity, no account. The site is static and carries forty lines of
JavaScript; adding a tracker would multiply that and hand a reader's browsing
to somebody else.

What a combined-format access log supports: page views by URL, referrer,
first-time versus returning by day, and - because the build knows every card's
grade - the grade of the cards people actually open. That last one is the
headline number in `POST_LAUNCH_METRICS.md`, and it needs no client
instrumentation at all.

What it does not support: funnels, cohorts, session replay. That is the right
trade.
"""

from __future__ import annotations

import gzip
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from atlas.util import get_logger

LOG = get_logger(__name__)

#: Combined Log Format, which nginx, Apache and Caddy all emit by default.
LINE = re.compile(
    r'^(?P<host>\S+) \S+ \S+ \[(?P<when>[^\]]+)\] '
    r'"(?P<method>[A-Z]+) (?P<path>\S+) [^"]*" '
    r'(?P<status>\d{3}) (?P<bytes>\S+) '
    r'"(?P<referrer>[^"]*)" "(?P<agent>[^"]*)"'
)

#: Requests that are not a reader looking at a page.
ASSET = re.compile(r"\.(css|js|png|jpg|jpeg|svg|webp|ico|xml|txt|json)$", re.I)
BOT = re.compile(
    r"bot|crawl|spider|slurp|bing|duckduck|yandex|baidu|facebookexternalhit|"
    r"headless|curl|wget|python-requests|monitor|uptime|lighthouse",
    re.I,
)

#: Where a visit came from. Matched against the referrer's host.
SOURCES = {
    "x": ("t.co", "twitter.com", "x.com"),
    "threads": ("threads.net", "threads.com"),
    "instagram": ("instagram.com", "l.instagram.com"),
    "reddit": ("reddit.com", "out.reddit.com"),
    "search": ("google.", "bing.com", "duckduckgo.com", "search.yahoo"),
    "email": ("mail.google", "outlook.", "list-manage"),
}


@dataclass
class Traffic:
    """What a log file says, aggregated. Nothing here identifies a reader."""

    requests: int = 0
    page_views: int = 0
    bots: int = 0
    by_page: Counter = field(default_factory=Counter)
    by_kind: Counter = field(default_factory=Counter)
    by_source: Counter = field(default_factory=Counter)
    by_grade: Counter = field(default_factory=Counter)
    by_day: Counter = field(default_factory=Counter)
    cards: Counter = field(default_factory=Counter)
    teams: Counter = field(default_factory=Counter)
    statuses: Counter = field(default_factory=Counter)

    @property
    def marked_down_share(self) -> float:
        """The headline number: the share of card views that were D or F.

        `POST_LAUNCH_METRICS.md` — "Atlas's entire position is that it tells
        you when not to trust it; if nobody reads the cards where it says so,
        the position is decoration."
        """
        graded = sum(self.by_grade.values())
        if not graded:
            return 0.0
        return (self.by_grade["D"] + self.by_grade["F"]) / graded


def kind(path: str) -> str:
    if path in ("/", "/index.html"):
        return "board"
    if path.startswith("/ncaaf/"):
        return "card"
    if path.startswith("/team/"):
        return "team"
    return Path(path).stem or "other"


def source(referrer: str) -> str:
    if not referrer or referrer == "-":
        return "direct"
    host = (urlsplit(referrer).hostname or "").lower()
    if host.endswith("atlas.football") or host == "atlas.football":
        return "internal"
    for label, needles in SOURCES.items():
        if any(needle in host for needle in needles):
            return label
    return "other"


def read(paths: list[Path], *, grades: dict[str, str] | None = None) -> Traffic:
    """Parse access logs into one aggregate.

    ``grades`` maps a card slug to its letter, so the grade of the cards
    people open can be counted without any client-side instrumentation. The
    build knows it; the log does not need to.
    """
    traffic = Traffic()
    grades = grades or {}
    for path in paths:
        opener = gzip.open if path.suffix == ".gz" else open
        with opener(path, "rt", errors="replace") as handle:
            for line in handle:
                _consume(traffic, line, grades)
    LOG.info("analytics: %d requests, %d page views, %d bot requests",
             traffic.requests, traffic.page_views, traffic.bots)
    return traffic


def _consume(traffic: Traffic, line: str, grades: dict[str, str]) -> None:
    match = LINE.match(line.strip())
    if not match:
        return
    traffic.requests += 1
    traffic.statuses[match["status"]] += 1

    if BOT.search(match["agent"]):
        traffic.bots += 1
        return
    if match["method"] != "GET" or match["status"] not in ("200", "304"):
        return

    path = urlsplit(match["path"]).path
    if ASSET.search(path):
        return

    traffic.page_views += 1
    traffic.by_page[path] += 1
    page_kind = kind(path)
    traffic.by_kind[page_kind] += 1
    traffic.by_source[source(match["referrer"])] += 1

    when = _when(match["when"])
    if when:
        traffic.by_day[when.date().isoformat()] += 1

    slug = Path(path).stem
    if page_kind == "card":
        traffic.cards[slug] += 1
        if slug in grades:
            traffic.by_grade[grades[slug]] += 1
    elif page_kind == "team":
        traffic.teams[slug] += 1


def _when(raw: str) -> datetime | None:
    try:
        return datetime.strptime(raw, "%d/%b/%Y:%H:%M:%S %z")
    except ValueError:
        return None


def card_grades(site: Path) -> dict[str, str]:
    """Slug to letter, read from the built cards.

    The build already knows every grade, so the headline metric needs no
    tracking code - only the log and the pages it served.
    """
    pattern = re.compile(r'class="grade-mark">([A-F+]+)')
    grades = {}
    for page in (site / "ncaaf").glob("*.html"):
        found = pattern.search(page.read_text())
        if found:
            grades[page.stem] = found.group(1)
    return grades


def report(traffic: Traffic, *, top: int = 10) -> str:
    def table(title: str, counter: Counter, note: str = "") -> list[str]:
        if not counter:
            return []
        total = sum(counter.values()) or 1
        lines = [f"{title}{f'  ({note})' if note else ''}"]
        for label, count in counter.most_common(top):
            lines.append(f"  {label:44} {count:7,}  {count / total:5.1%}")
        return [*lines, ""]

    out = [
        "Atlas traffic",
        "",
        f"  requests        {traffic.requests:>9,}",
        f"  page views      {traffic.page_views:>9,}",
        f"  bot requests    {traffic.bots:>9,}"
        f"  ({traffic.bots / max(traffic.requests, 1):.0%})",
        "",
    ]
    out += table("By page type", traffic.by_kind)
    out += table("Traffic source", traffic.by_source)
    out += table("Most viewed cards", traffic.cards)
    out += table("Most viewed teams", traffic.teams)
    out += table("Grade of the cards opened", traffic.by_grade)
    if traffic.by_grade:
        out += [f"  marked down (D or F): {traffic.marked_down_share:.1%} "
                "of graded card views", ""]
    out += table("Response codes", traffic.statuses)
    return "\n".join(out)
