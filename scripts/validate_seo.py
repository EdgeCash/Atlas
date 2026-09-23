"""Validate the built site's SEO surface.

    python scripts/validate_seo.py [--site site] [--url https://atlas.football]

`scripts/audit_site.py` checks that the tags are *present*. This checks that
they are *correct* - a canonical that points at another page, a sitemap entry
for a file that does not exist, a social image that will 404 when X tries to
fetch it. Those are the failures that only show up after launch, in somebody
else's cache.

Non-zero exit on any error, so it can gate a deploy.
"""

from __future__ import annotations

import argparse
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
SITEMAP_NS = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}

#: Search engines truncate a title around here and a description around there.
#: Over is a warning, not an error - a long title is worse than a short one
#: and better than a missing one.
TITLE_MAX = 65
DESCRIPTION_MIN, DESCRIPTION_MAX = 70, 165


def _tag(html: str, pattern: str) -> str | None:
    found = re.search(pattern, html, re.I)
    return found.group(1).strip() if found else None


def _meta(html: str, kind: str, name: str) -> str | None:
    return _tag(html, rf'<meta\s+{kind}="{re.escape(name)}"\s+content="([^"]*)"')


def _site_relative(base: str, url: str) -> str:
    """The part of ``url`` below ``base``, as a path relative to the site root.

    The base may carry a path of its own: GitHub Pages serves a project site at
    ``/<repo>/``, so a correct canonical there is ``/Atlas/ncaaf/x.html`` while
    the file on disk is ``ncaaf/x.html``. Against a bare domain this strips
    nothing and behaves exactly as it always did.
    """
    prefix = urlsplit(base).path.strip("/")
    path = urlsplit(url).path.lstrip("/")
    if not prefix:
        return path
    if path == prefix:
        return ""
    if path.startswith(f"{prefix}/"):
        return path[len(prefix) + 1:]
    return path


def validate(site: Path, base: str) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    pages = sorted(site.rglob("*.html"))
    canonicals: Counter = Counter()
    titles: Counter = Counter()

    for page in pages:
        rel = page.relative_to(site).as_posix()
        html = page.read_text()

        title = _tag(html, r"<title>(.*?)</title>")
        if not title:
            errors.append(f"{rel}: no <title>")
        else:
            titles[title] += 1
            if len(title) > TITLE_MAX:
                warnings.append(f"{rel}: title is {len(title)} chars (>{TITLE_MAX})")

        description = _meta(html, "name", "description")
        if not description:
            errors.append(f"{rel}: no meta description")
        elif not (DESCRIPTION_MIN <= len(description) <= DESCRIPTION_MAX):
            warnings.append(
                f"{rel}: description is {len(description)} chars "
                f"(want {DESCRIPTION_MIN}-{DESCRIPTION_MAX})")

        canonical = _tag(html, r'<link rel="canonical" href="([^"]*)"')
        if rel == "404.html":
            if canonical:
                errors.append("404.html: has a canonical — it must not claim one")
            if 'name="robots" content="noindex"' not in html:
                errors.append("404.html: not marked noindex")
        elif not canonical:
            errors.append(f"{rel}: no canonical")
        else:
            canonicals[canonical] += 1
            if not canonical.startswith(base):
                errors.append(f"{rel}: canonical is not on {base} — {canonical}")
            expected = "" if rel == "index.html" else rel
            if _site_relative(base, canonical) != expected:
                errors.append(f"{rel}: canonical points elsewhere — {canonical}")

        # Open Graph and Twitter, where the page claims them.
        if _meta(html, "property", "og:title"):
            for required in ("og:description", "og:type", "og:site_name"):
                if not _meta(html, "property", required):
                    errors.append(f"{rel}: og:title without {required}")
            if not _meta(html, "name", "twitter:card"):
                errors.append(f"{rel}: Open Graph without a twitter:card")
            image = _meta(html, "property", "og:image")
            if image:
                if not image.startswith("http"):
                    errors.append(f"{rel}: og:image is relative — {image}")
                else:
                    local = site / _site_relative(base, image)
                    if not local.exists():
                        errors.append(f"{rel}: og:image does not exist — {image}")
                    elif local.stat().st_size < 1024:
                        errors.append(f"{rel}: og:image is suspiciously small")

    for canonical, count in canonicals.items():
        if count > 1:
            errors.append(f"{count} pages share the canonical {canonical}")
    for title, count in titles.items():
        if count > 1:
            warnings.append(f'{count} pages share the title "{title}"')

    errors += _sitemap(site, base, pages)
    errors += _robots(site, base)
    return errors, warnings


def _sitemap(site: Path, base: str, pages: list[Path]) -> list[str]:
    path = site / "sitemap.xml"
    if not path.exists():
        return ["no sitemap.xml"]
    errors: list[str] = []
    try:
        root = ET.fromstring(path.read_text())
    except ET.ParseError as exc:
        return [f"sitemap.xml will not parse — {exc}"]

    listed = set()
    for url in root.findall("s:url", SITEMAP_NS):
        loc = (url.findtext("s:loc", "", SITEMAP_NS) or "").strip()
        if not loc.startswith(base):
            errors.append(f"sitemap: {loc} is not on {base}")
            continue
        rel = _site_relative(base, loc) or "index.html"
        listed.add(rel)
        if not (site / rel).exists():
            errors.append(f"sitemap: {loc} does not exist on disk")
        for field, values in (("s:changefreq", {"always", "hourly", "daily",
                                                "weekly", "monthly", "yearly",
                                                "never"}),):
            value = url.findtext(field, "", SITEMAP_NS)
            if value and value not in values:
                errors.append(f"sitemap: {loc} has {field} {value!r}")
        priority = url.findtext("s:priority", "", SITEMAP_NS)
        if priority and not 0.0 <= float(priority) <= 1.0:
            errors.append(f"sitemap: {loc} has priority {priority}")

    # Every indexable page should be listed. The 404 must not be.
    for page in pages:
        rel = page.relative_to(site).as_posix()
        if rel == "404.html":
            if rel in listed:
                errors.append("sitemap: lists 404.html")
            continue
        if rel not in listed:
            errors.append(f"sitemap: {rel} is missing")
    return errors


def _robots(site: Path, base: str) -> list[str]:
    path = site / "robots.txt"
    if not path.exists():
        return ["no robots.txt"]
    text = path.read_text()
    errors = []
    if "User-agent: *" not in text:
        errors.append("robots.txt: no User-agent rule")
    if f"Sitemap: {base}/sitemap.xml" not in text:
        errors.append("robots.txt: does not point at the sitemap")
    if re.search(r"^Disallow: /\s*$", text, re.M):
        errors.append("robots.txt: disallows everything")
    return errors


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", type=Path, default=ROOT / "site")
    ap.add_argument("--url", default="https://atlas.football")
    args = ap.parse_args()
    if not args.site.exists():
        sys.exit(f"no built site at {args.site} — run `make site` first")

    pages = len(list(args.site.rglob("*.html")))
    errors, warnings = validate(args.site, args.url.rstrip("/"))
    print(f"Atlas SEO validation — {pages} pages against {args.url}\n")
    for label, rows in (("ERROR", errors), ("warn", warnings)):
        print(f"{label}: {len(rows)}")
        for row in rows[:12]:
            print(f"    {row}")
        if len(rows) > 12:
            print(f"    ... and {len(rows) - 12} more")
        print()
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
