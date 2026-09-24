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
from atlas.ops import freshness as ops_freshness
from atlas.ops import status as ops_status
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
    nfl_cards = _nfl_cards(horizon=horizon, refresh_meta=refresh_meta)

    bands = grading.calibration_bands()
    overall = grading.overall(bands)
    nfl_bands = grading.calibration_bands(sport="nfl") if nfl_cards else {}
    nfl_overall = grading.overall(nfl_bands) if nfl_bands else overall
    stamps = _freshness(social_cards=social_cards)

    if out.exists():
        shutil.rmtree(out)
    (out / "ncaaf").mkdir(parents=True)
    (out / "nfl" / "team").mkdir(parents=True)
    (out / "team").mkdir(parents=True)

    assets_src = Path(__file__).resolve().parent / "assets"
    shutil.copytree(assets_src, out / "assets")

    # Logos are served from the site, not hot-linked: a card that waits on a
    # third-party CDN is not a fast card.
    logos = espn_meta.cache_logos(
        espn_meta.fetch(espn_meta.days_ahead(horizon)),
        config.paths().data / "site" / "logos",
    )
    nfl_logos = espn_meta.cache_logos(
        espn_meta.fetch(espn_meta.days_ahead(horizon), sport="nfl"),
        config.paths().data / "site" / "logos", prefix="nfl-",
    ) if nfl_cards else {}
    if logos or nfl_logos:
        shutil.copytree(config.paths().data / "site" / "logos", out / "assets" / "logos")
    for card in cards:
        for side in (card.home, card.away):
            side.logo = logos.get(side.team_id)
    for card in nfl_cards:
        for side in (card.home, card.away):
            side.logo = nfl_logos.get(side.team_id)

    (out / "index.html").write_text(render.homepage(
        cards, bands=bands, rivalries=rivalry_pairs(), freshness=stamps))
    (out / "research.html").write_text(
        render.research_page(bands, overall, card_count=len(cards)))
    (out / "about.html").write_text(
        render.about_page(_example_card(cards), card_count=len(cards)))
    (out / "faq.html").write_text(render.faq_page())
    (out / "404.html").write_text(render.not_found_page())
    nfl_teams = _teams(nfl_cards)
    (out / "nfl.html").write_text(render.nfl_page(nfl_cards, bands=nfl_bands, freshness=stamps, teams=nfl_teams))
    for card in nfl_cards:
        (out / card.path).write_text(render.card_page(
            card, bands=nfl_bands, overall_band=nfl_overall, freshness=stamps))
    if nfl_teams:
        nfl_pool, nfl_results, nfl_records = _nfl_context(nfl_cards)
        for team in nfl_teams.values():
            team.record = team.record or nfl_records.get(team.team_id)
            (out / render.team_path(team, "nfl")).write_text(render.nfl_team_page(
                team, cards=nfl_cards, pool=nfl_pool, results=nfl_results.get(team.team_id, []),
                freshness=stamps))
    (out / "premium.html").write_text(render.premium_page())

    social_slugs = {c.slug for c in _spread_of_grades(
        [c for c in cards if c.grade], SOCIAL_LIMIT)} if social_cards else set()
    for card in cards:
        (out / card.path).write_text(render.card_page(
            card, bands=bands, overall_band=overall,
            social_image=card.slug in social_slugs, freshness=stamps))

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
            images.extend(social.write(card, out / "social",
                                       generated=stamps["social"]))

    # The build's own stamp is what the board shows as "Updated". Recorded
    # after the pages are written, so a build that fails halfway never
    # advertises itself as complete.
    if social_cards:
        ops_freshness.record("social", detail=f"{len(images)} files")
    ops_freshness.record("build", detail=f"{len(cards)} cards, {len(nfl_cards)} NFL cards, {len(teams)} teams, "
                                         f"{len(nfl_teams)} NFL teams")
    # Written last, so it reports the run that just happened rather than the
    # one before it.
    (out / "status.html").write_text(render.status_page(ops_status.summary()))
    _write_robots(out)
    _write_sitemap(out, [*cards, *nfl_cards], teams, nfl_teams)
    LOG.info("site: %d cards, %d NFL cards, %d teams, %d NFL teams, %d images -> %s",
             len(cards), len(nfl_cards), len(teams), len(nfl_teams), len(images), out)
    return {"cards": len(cards), "nfl_cards": len(nfl_cards), "teams": len(teams), "nfl_teams": len(nfl_teams),
            "images": len(images), "out": out}


def _nfl_cards(*, horizon: int, refresh_meta: bool) -> list:
    """The NFL slate, or nothing: an NFL failure never takes the college board down."""
    try:
        return build_cards(horizon=horizon, refresh_meta=refresh_meta, sport="nfl")
    except Exception as error:  # noqa: BLE001 - logged; the page says so
        LOG.warning("no NFL cards this build: %s", error)
        return []


def _freshness(*, social_cards: bool = True) -> dict:
    """The four stamps every page can show.

    Each is the last *successful* run of the thing it describes, not this
    build's clock. A rebuild triggered by an hourly poll shows the market's
    poll time; a rebuild that ran while the poller was down shows the older
    market time, which is the honest answer.
    """
    from atlas.site.data import generated_at
    from atlas.site.html import stamp

    def at(event: str, fallback: str = "") -> str:
        recorded = ops_freshness.last(event)
        return stamp(recorded.at) if recorded else fallback

    now = generated_at()
    return {
        # Projections come from the heavy refresh, so they age at its pace.
        "projection": at("heavy", now),
        "market": at("poll", now),
        "board": at("build", now),
        # Same reasoning as the board: if this build is making the social
        # assets, their stamp is this build's clock.
        "social": now if social_cards else at("social", now),
    }


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


def _nfl_context(nfl_cards) -> tuple[dict, dict, dict]:
    """The NFL percentile pool, each team's results and its record this season; empty on any failure."""
    from atlas.live.store import Store
    from atlas.research.nfl_dataset import load_nfl_frame
    from atlas.site.data import team_results, team_win_loss

    try:
        frame = load_nfl_frame()
        season = max(c.season for c in nfl_cards)
        projections = Store.open().read("projections")
        projections = projections[projections["sport"].fillna("ncaaf").astype(str) == "nfl"]
        return (percentile_pool(frame, season), team_results(nfl_cards, frame, projections),
                team_win_loss(nfl_cards, frame))
    except Exception as error:  # noqa: BLE001 - a team page without a profile is still a page
        LOG.warning("NFL team pages without a profile or results: %s", error)
        return {}, {}, {}


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


def _write_sitemap(out: Path, cards, teams: dict, nfl_teams: dict | None = None) -> None:
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
        ("faq.html", "monthly", "0.7"),
        ("status.html", "daily", "0.4"),
        ("research.html", "weekly", SITEMAP_PRIORITY["research.html"]),
        ("nfl.html", "monthly", "0.4"),
        ("premium.html", "monthly", "0.5"),
    ]
    urls += [(card.path, "daily", SITEMAP_PRIORITY.get(card.sport, SITEMAP_PRIORITY["ncaaf"])) for card in cards]
    urls += [(f"team/{slug}.html", "weekly", SITEMAP_PRIORITY["team"])
             for slug in sorted(teams)]
    urls += [(render.team_path(side, "nfl"), "weekly", SITEMAP_PRIORITY["team"])
             for _, side in sorted((nfl_teams or {}).items())]

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
