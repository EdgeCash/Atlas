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

#: name, path, width, height, full page
SHOTS = [
    ("01-home-mobile", "index.html", 390, 844, False),
    ("02-home-desktop", "index.html", 1440, 1000, False),
    ("03-home-ipad", "index.html", 834, 1112, False),
    ("04-card-A-mobile", "ncaaf/oklahoma-sooners-georgia-bulldogs.html", 390, 844, False),
    ("05-card-A-mobile-full", "ncaaf/oklahoma-sooners-georgia-bulldogs.html", 390, 844, True),
    ("06-card-A-desktop", "ncaaf/oklahoma-sooners-georgia-bulldogs.html", 1440, 1000, False),
    ("07-card-F-mobile", "ncaaf/central-michigan-chippewas-miami-hurricanes.html", 390, 844, False),
    ("08-card-F-desktop", "ncaaf/central-michigan-chippewas-miami-hurricanes.html", 1440, 1000, False),
    ("09-card-C-mobile", "ncaaf/texas-a-m-aggies-lsu-tigers.html", 390, 844, False),
    ("10-card-open-mobile", "ncaaf/oklahoma-sooners-georgia-bulldogs.html", 390, 844, True),
    ("11-team-mobile", "team/georgia-bulldogs.html", 390, 844, False),
    ("12-team-desktop", "team/georgia-bulldogs.html", 1440, 1000, False),
    ("13-research", "research.html", 1440, 1000, False),
    ("14-nfl", "nfl.html", 1440, 1000, False),
    ("15-premium", "premium.html", 1440, 1000, False),
]

#: Social templates are images already; they are copied, not screenshotted.
SOCIAL = [
    ("16-social-wide-A", "social/northwestern-wildcats-indiana-hoosiers-wide.png"),
    ("17-social-square-A", "social/northwestern-wildcats-indiana-hoosiers-square.png"),
    ("18-social-wide-F", "social/central-michigan-chippewas-miami-hurricanes-wide.png"),
    ("19-social-square-F", "social/central-michigan-chippewas-miami-hurricanes-square.png"),
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
            if name == "10-card-open-mobile":
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
