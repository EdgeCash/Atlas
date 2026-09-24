"""Screenshot the built site into design/screens/site/.

    python scripts/shoot_site.py [--out design/screens/site]

Requires a built `site/` and Playwright's bundled Chromium. Every shot is a
real page at a real viewport — nothing here is a mockup.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from playwright.sync_api import sync_playwright

#: This container ships Chromium at a fixed path; the pinned Playwright build
#: looks for a different revision, so point it at the one that is here.
CHROMIUM = Path("/opt/pw-browsers/chromium")

ROOT = Path(__file__).resolve().parents[1]

#: name, path, width, height, full page. The card set covers the grades the
#: product has to survive, not the flattering end of the scale.
A_CARD = "ncaaf/ole-miss-rebels-florida-gators.html"
C_CARD = "ncaaf/app-state-mountaineers-nc-state-wolfpack.html"
F_CARD = "ncaaf/central-michigan-chippewas-miami-hurricanes.html"

SHOTS = [
    ("00-about-mobile", "about.html", 390, 844, False),
    ("00-about-desktop", "about.html", 1440, 1000, False),
    ("00-about-read", "about.html", 1440, 2200, False),
    ("00-faq", "faq.html", 1440, 1400, False),
    ("00-status", "status.html", 1440, 1400, False),
    ("00-status-mobile", "status.html", 390, 844, False),
    ("00-404", "404.html", 1440, 700, False),
    ("01-homepage-desktop", "index.html", 1440, 1000, False),
    ("02-homepage-mobile", "index.html", 390, 844, False),
    ("03-board-desktop", "ncaaf.html", 1440, 2400, False),
    ("04-board-mobile", "ncaaf.html", 390, 2000, False),
    ("05-board-ipad", "ncaaf.html", 834, 1112, False),
    ("06-card-A-mobile", A_CARD, 390, 844, False),
    ("07-card-A-desktop", A_CARD, 1440, 1000, False),
    ("08-card-C-mobile", C_CARD, 390, 844, False),
    ("09-card-C-desktop", C_CARD, 1440, 1000, False),
    ("10-card-F-mobile", F_CARD, 390, 844, False),
    ("11-card-F-desktop", F_CARD, 1440, 1000, False),
    ("12-card-mobile-full", F_CARD, 390, 844, True),
    ("13-card-open-mobile", F_CARD, 390, 844, True),
    ("14-team-mobile", "team/georgia-bulldogs.html", 390, 844, False),
    ("15-team-desktop", "team/georgia-bulldogs.html", 1440, 1000, False),
    ("16-research", "research.html", 1440, 1000, False),
    ("17-nfl", "nfl.html", 1440, 1000, False),
    ("18-premium", "premium.html", 1440, 1000, False),
]

#: Social templates are images already; they are copied, not screenshotted.
SOCIAL = [
    ("19-social-1200x675-A", "social/colorado-state-rams-utsa-roadrunners-wide.png"),
    ("20-social-1080x1080-A", "social/colorado-state-rams-utsa-roadrunners-square.png"),
    ("21-social-1200x675-F", "social/central-michigan-chippewas-miami-hurricanes-wide.png"),
    ("22-social-1080x1080-F", "social/central-michigan-chippewas-miami-hurricanes-square.png"),
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", type=Path, default=ROOT / "site")
    ap.add_argument("--out", type=Path, default=ROOT / "design" / "screens" / "site")
    args = ap.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    for old in args.out.glob("*.png"):
        old.unlink()

    with sync_playwright() as pw:
        launch = {"executable_path": str(CHROMIUM)} if CHROMIUM.exists() else {}
        browser = pw.chromium.launch(**launch)
        for name, rel, width, height, full in SHOTS:
            target = args.site / rel
            if not target.exists():
                print(f"  skip {name}: {rel} missing")
                continue
            page = browser.new_page(viewport={"width": width, "height": height},
                                    device_scale_factor=2)
            page.goto(target.resolve().as_uri())
            page.wait_for_timeout(350)
            if name == "13-card-open-mobile":
                page.eval_on_selector_all("details", "els => els.forEach(e => e.open = true)")
                page.wait_for_timeout(200)
            page.screenshot(path=args.out / f"{name}.png", full_page=full)
            page.close()
            print(f"  {name}.png  {width}x{height}{' full' if full else ''}")
        browser.close()

    for name, rel in SOCIAL:
        src = args.site / rel
        if src.exists():
            shutil.copyfile(src, args.out / f"{name}.png")
            print(f"  {name}.png  copied")


if __name__ == "__main__":
    main()
