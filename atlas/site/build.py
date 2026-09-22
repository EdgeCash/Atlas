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
from atlas.site.data import build_cards, percentile_pool
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

    (out / "index.html").write_text(render.homepage(cards, bands=bands))
    (out / "research.html").write_text(
        render.research_page(bands, overall, card_count=len(cards)))
    (out / "nfl.html").write_text(render.nfl_page())
    (out / "premium.html").write_text(render.premium_page())

    for card in cards:
        (out / card.path).write_text(render.card_page(card, bands=bands, overall_band=overall))

    teams = _teams(cards)
    pool = _pool()
    for slug, team in teams.items():
        (out / "team" / f"{slug}.html").write_text(
            render.team_page(team, cards=cards, pool=pool))

    images = []
    if social_cards:
        graded = [c for c in cards if c.grade]
        # One of each grade band where possible, so the templates are reviewed
        # against the range they have to survive rather than the flattering end.
        picked = _spread_of_grades(graded, SOCIAL_LIMIT)
        for card in picked:
            images.extend(social.write(card, out / "social"))

    _write_robots(out)
    LOG.info("site: %d cards, %d teams, %d images -> %s",
             len(cards), len(teams), len(images), out)
    return {"cards": len(cards), "teams": len(teams), "images": len(images), "out": out}


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
        "User-agent: *\nAllow: /\n"
    )


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
