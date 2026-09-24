"""Launch audit: scan every rendered page for the things Atlas must never do.

    python scripts/audit_site.py [--site site] [--strict]

`tests/test_site.py` checks the page *types* at render time with fixtures. This
checks the built site — all 179 pages, with the real data in them — and adds
the launch-readiness checks a test cannot see: canonical URLs, meta
descriptions, structured data, motion.

Exit code is non-zero when a blocking check fails, so it can gate a deploy.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: `docs/BRAND_GUIDE.md`. The same list the render-time test uses.
FORBIDDEN = (
    "bet", "bets", "wager", "wagers", "lock", "locks", "hammer", "smash",
    "unit", "units", "pick", "picks", "selection", "selections", "roi",
    "bankroll", "kelly", "stake", "stakes", "parlay", "sweat", "fade", "tail",
)

#: Football and market vocabulary that legitimately contains a forbidden word.
#: A phrase gets added here only with the sentence that justifies it.
ALLOWED_CONTEXT = (
    "betting market", "the spread market", "books quoting", "moneyline",
    "per play", "plays per game", "plays ·", "epa/play", "play-by-play",
    "no card names a side", "not a selections service", "does not publish "
    "selections", "does not publish a side", "no countdowns",
)

#: Anything that would make a page read as a recommendation.
SIDE = re.compile(
    r"\b(take the|lay the|back the|we like|our pick|recommended side|"
    r"leans? (over|under)|best bet)\b", re.IGNORECASE)

#: Motion implies urgency, and Atlas is a pre-kickoff product.
MOTION = re.compile(r"@keyframes|animation\s*:|setInterval|requestAnimationFrame")


def visible(html: str) -> str:
    html = re.sub(r"<script.*?</script>", " ", html, flags=re.S)
    html = re.sub(r"<style.*?</style>", " ", html, flags=re.S)
    return re.sub(r"<[^>]+>", " ", html).lower()


def audit(site: Path) -> tuple[dict, dict]:
    pages = sorted(site.rglob("*.html"))
    blocking: dict[str, list[str]] = {
        "forbidden vocabulary": [], "a named side": [],
        "card missing the grade disclaimer": [], "motion or urgency": [],
    }
    advisory: dict[str, list[str]] = {
        "missing canonical": [], "missing meta description": [],
        "missing structured data": [], "missing social tags": [],
        "missing freshness stamp": [], "timestamp without a zone": [],
    }

    for path in pages:
        rel = path.relative_to(site).as_posix()
        html = path.read_text()
        text = visible(html)

        for word in FORBIDDEN:
            for match in re.finditer(rf"\b{word}\b", text):
                window = text[max(0, match.start() - 70):match.end() + 70]
                if any(phrase in window for phrase in ALLOWED_CONTEXT):
                    continue
                blocking["forbidden vocabulary"].append(
                    f"{rel}: {word!r} in ...{' '.join(window.split())}...")
        if SIDE.search(html):
            blocking["a named side"].append(rel)
        if rel.startswith(("ncaaf/", "nfl/")) and "not a recommendation" not in text:
            blocking["card missing the grade disclaimer"].append(rel)
        if MOTION.search(html):
            blocking["motion or urgency"].append(rel)

        # A 404 has no canonical on purpose: claiming one tells a crawler the
        # missing page is the real one.
        if 'rel="canonical"' not in html and rel != "404.html":
            advisory["missing canonical"].append(rel)
        if 'name="description"' not in html:
            advisory["missing meta description"].append(rel)
        if rel.startswith(("ncaaf/", "nfl/", "team/")) and "application/ld+json" not in html:
            advisory["missing structured data"].append(rel)
        if rel.startswith(("ncaaf/", "nfl/")) and 'property="og:title"' not in html:
            advisory["missing social tags"].append(rel)
        # Track 6: a reader must never have to guess how old a number is.
        if (rel == "index.html" or rel.startswith(("ncaaf/", "nfl/"))) \
                and 'class="freshness"' not in html:
            advisory["missing freshness stamp"].append(rel)
        # A clock time with no zone is a number a reader has to guess about.
        for match in re.finditer(r"\d{1,2}:\d{2}\s*[AP]M(?!\s*ET)", text):
            advisory["timestamp without a zone"].append(
                f"{rel}: ...{text[max(0, match.start() - 30):match.end() + 6]}...")

    return blocking, advisory


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", type=Path, default=ROOT / "site")
    ap.add_argument("--strict", action="store_true",
                    help="fail on advisory findings too")
    args = ap.parse_args()

    if not args.site.exists():
        sys.exit(f"no built site at {args.site} - run `make site` first")

    blocking, advisory = audit(args.site)
    pages = len(list(args.site.rglob("*.html")))
    print(f"Atlas launch audit — {pages} pages\n")

    failed = False
    for label, findings in (("BLOCKING", blocking), ("ADVISORY", advisory)):
        print(label)
        for check, rows in findings.items():
            mark = "ok  " if not rows else "FAIL" if label == "BLOCKING" else "warn"
            print(f"  [{mark}] {check}: {len(rows)}")
            for row in rows[:5]:
                print(f"          {row}")
            if len(rows) > 5:
                print(f"          ... and {len(rows) - 5} more")
            if rows and (label == "BLOCKING" or args.strict):
                failed = True
        print()

    def kind(rel: str) -> str:
        if rel.startswith("nfl/team/"):
            return "nfl team"
        if rel.startswith("nfl/"):
            return "nfl card"
        if rel.startswith("ncaaf/"):
            return "card"
        return "team" if rel.startswith("team/") else "other"

    kinds = Counter(kind(q.relative_to(args.site).as_posix()) for q in args.site.rglob("*.html"))
    print(f"coverage: {dict(kinds)}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
