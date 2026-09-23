"""Build the site.

    python -m atlas.site.build [--out site] [--no-social] [--refresh-meta]

Emits static HTML into ``site/``. No server, no client framework: the card is
a document, and a document loads instantly on a phone on a stadium network.
"""

from __future__ import annotations

import argparse
import shutil
from dataclasses import replace
from pathlib import Path

from atlas import config
from atlas.site import grade as grading
from atlas.site import meta as espn_meta
from atlas.site import render, social
from atlas.site.data import build_cards, percentile_pool, rivalry_pairs
from atlas.util import get_logger

LOG = get_logger(__name__)

#: Cards to render social templates for. Every card gets a page; rasterising a
#: PNG pair for all of them is minutes of work for images nobody asked for.
SOCIAL_LIMIT = 6


def default_out() -> Path:
    return config.paths().root / "site"


def build(out: Path | None = None, *, social_cards: bool = True,
          refresh_meta: bool = False, horizon: int = 8) -> dict:
    out = out or default_out()
    cards = build_cards(horizon=horizon, refresh_meta=refresh_meta)
    if not cards:
        raise SystemExit(
            "no cards to publish - rebuild the warehouse with "
            "`python -m atlas.warehouse.build --include-scheduled`"
        )

    bands = grading.calibration_bands("total")
    overall = grading.overall(bands)

    if out.exists():
        shutil.rmtree(out)
    (out / "ncaaf").mkdir(parents=True)
    (out / "team").mkdir(parents=True)

    assets_src = Path(__file__).resolve().parent / "assets"
    shutil.copytree(assets_src, out / "assets")

    # Logos are served from the site, not hot-linked: a card that waits on a
    # third-party CDN is not a fast card.
    logos = espn_meta.cache_logos(
        espn_meta.fetch(espn_meta.days_ahead(horizon)),
        config.paths().data / "site" / "logos",
    )
    if logos:
        shutil.copytree(config.paths().data / "site" / "logos", out / "assets" / "logos")
    for card in cards:
        for side in (card.home, card.away):
            side.logo = logos.get(side.team_id)

    (out / "index.html").write_text(
        render.homepage(cards, bands=bands, rivalries=rivalry_pairs()))
    (out / "research.html").write_text(
        render.research_page(bands, overall, card_count=len(cards)))
    (out / "about.html").write_text(
        render.about_page(_example_card(cards), card_count=len(cards)))
    (out / "nfl.html").write_text(render.nfl_page())
    (out / "premium.html").write_text(render.premium_page())

    social_slugs = {c.slug for c in _spread_of_grades(
        [c for c in cards if c.grade], SOCIAL_LIMIT)} if social_cards else set()
    for card in cards:
        (out / card.path).write_text(render.card_page(
            card, bands=bands, overall_band=overall,
            social_image=card.slug in social_slugs))

    teams = _teams(cards)
    pool = _pool()
    for slug, team in teams.items():
        (out / "team" / f"{slug}.html").write_text(
            render.team_page(team, cards=cards, pool=pool))

    images = []
    if social_cards:
        # One of each grade where possible, so the templates are reviewed
        # against the range they have to survive rather than the flattering end.
        for card in (c for c in cards if c.slug in social_slugs):
            images.extend(social.write(card, out / "social"))

    _write_robots(out)
    _write_sitemap(out, cards, teams)
    LOG.info("site: %d cards, %d teams, %d images -> %s",
             len(cards), len(teams), len(images), out)
    return {"cards": len(cards), "teams": len(teams), "images": len(images), "out": out}


def _example_card(cards) -> object | None:
    """The card the "how to read a card" walkthrough points at.

    The highest-graded card with both a rank and a broadcast: a first-time
    reader should meet the product on a game they have heard of, and on a card
    that has something in every section."""
    ranked = [c for c in cards
              if c.grade and c.tv and (c.home.rank or c.away.rank)]
    pool = ranked or [c for c in cards if c.grade] or list(cards)
    return max(pool, key=lambda c: c.grade.score if c.grade else 0) if pool else None


def _teams(cards) -> dict:
    """One profile per team, taken from that team's earliest upcoming card."""
    from atlas.site.data import _slug

    teams: dict[str, object] = {}
    for card in cards:
        for side in (card.home, card.away):
            slug = _slug(side.name)
            if slug not in teams:
                teams[slug] = replace(side)
    return teams


def _pool() -> dict:
    from atlas.research.dataset import load_research_frame

    frame = load_research_frame()
    season = int(frame["season"].max())
    return percentile_pool(frame, season)


def _spread_of_grades(cards, limit: int) -> list:
    by_letter: dict[str, list] = {}
    for card in cards:
        by_letter.setdefault(card.grade.letter, []).append(card)
    picked, order = [], ["F", "A+", "A", "D", "B", "C"]
    for letter in order:
        for card in by_letter.get(letter, [])[:1]:
            picked.append(card)
    for card in cards:
        if len(picked) >= limit:
            break
        if card not in picked:
            picked.append(card)
    return picked[:limit]


def _write_robots(out: Path) -> None:
    (out / "robots.txt").write_text(
        "User-agent: *\n"
        "Allow: /\n"
        f"Sitemap: {render.SITE_URL}/sitemap.xml\n"
    )


#: Crawl priority. A game card is the page somebody searches for; the board is
#: the page they land on from the outside. Everything else is context.
SITEMAP_PRIORITY = {"": "1.0", "about.html": "0.9", "research.html": "0.8",
                    "ncaaf": "0.8", "team": "0.6"}


def _write_sitemap(out: Path, cards, teams: dict) -> None:
    """Every public page, once, with the day it was built.

    A card's content changes whenever the market does, so `changefreq` is
    daily on cards and weekly on the pages that only move when the research
    does. Nothing here is a claim the site does not keep.
    """
    from datetime import UTC, datetime

    today = datetime.now(UTC).date().isoformat()
    urls: list[tuple[str, str, str]] = [
        ("", "daily", SITEMAP_PRIORITY[""]),
        ("about.html", "monthly", SITEMAP_PRIORITY["about.html"]),
        ("research.html", "weekly", SITEMAP_PRIORITY["research.html"]),
        ("nfl.html", "monthly", "0.4"),
        ("premium.html", "monthly", "0.5"),
    ]
    urls += [(card.path, "daily", SITEMAP_PRIORITY["ncaaf"]) for card in cards]
    urls += [(f"team/{slug}.html", "weekly", SITEMAP_PRIORITY["team"])
             for slug in sorted(teams)]

    entries = "".join(
        f"<url><loc>{render.SITE_URL}/{path}</loc>"
        f"<lastmod>{today}</lastmod>"
        f"<changefreq>{freq}</changefreq>"
        f"<priority>{priority}</priority></url>"
        for path, freq, priority in urls
    )
    (out / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"{entries}</urlset>\n"
    )
    LOG.info("sitemap: %d urls", len(urls))


def main() -> None:
    ap = argparse.ArgumentParser(description="Build the Atlas site")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--no-social", action="store_true")
    ap.add_argument("--refresh-meta", action="store_true")
    ap.add_argument("--horizon", type=int, default=8)
    args = ap.parse_args()
    result = build(args.out, social_cards=not args.no_social,
                   refresh_meta=args.refresh_meta, horizon=args.horizon)
    LOG.info("done: %s", result)


if __name__ == "__main__":
    main()
