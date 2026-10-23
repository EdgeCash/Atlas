"""Atlas on Polymarket US, as a run.

    python -m atlas.polymarket refresh [--heavy]   # every run: capture, record, price, log, grade, seal, report
    python -m atlas.polymarket capture             # the quotes into the record and nothing else
    python -m atlas.polymarket show                # the board and the record, to the terminal (needs the key)

``refresh`` never fails the run it is part of: a venue outage or a missing
key leaves the record as it was and says so in the owner page.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime

import pandas as pd

from atlas.live import probability
from atlas.live.store import Store
from atlas.owner import crypto
from atlas.polymarket import (
    favorites,
    match,
    orders,
    page,
    positions,
    pricing,
    props,
    report,
    source,
)
from atlas.util import get_logger, offline

LOG = get_logger(__name__)
TABLE = "polymarket_quotes"


def _research() -> pd.DataFrame | None:
    try:
        from atlas.research.dataset import load_research_frame

        return load_research_frame()
    except Exception as error:  # noqa: BLE001
        LOG.info("polymarket: no warehouse (%s)", type(error).__name__)
        return None


def capture(store: Store, now: datetime) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict, pd.DataFrame]:
    """Read the venue, match the games, fold the quotes into the record. Returns (the matched quotes of
    this run, the games ahead, the whole record, the events read by sport, the matched pairs). Offline,
    this run's quotes are empty and the record is read as it stands."""
    games, proj, nhl = store.read("games"), store.read("projections"), store.read("nhl_projections")
    up = match.upcoming(games, now, proj, nhl)
    events = source.capture_events() if not offline() else {}
    fresh = source.capture(now, events=events) if events else pd.DataFrame(columns=source.QUOTE_COLUMNS)
    pairs = match.match(fresh, up)
    attached = match.attach(fresh, pairs)
    record = store.read(TABLE)
    if len(attached):
        # Kept: the matched games' main lines. Read every run and priced, not kept: the rest of the ladder.
        kept = source.main_lines(attached[attached["game_id"].notna()])
        record, added = source.fold(record, kept.reindex(columns=source.QUOTE_COLUMNS))
        store.write(TABLE, record)
        LOG.info("polymarket: %d of %d games ahead matched; %d quotes read, %d kept, %d new rows in the record",
                 len(pairs), len(up), len(attached), len(kept), added)
    return attached, up, record, events, pairs


def price(store: Store, quotes: pd.DataFrame) -> pd.DataFrame:
    shapes = probability.load_shapes(store.read("market_shape"))
    return pricing.price(quotes, store.read("projections"), store.read("nhl_projections"), shapes,
                         store.read("calibration"))


def refresh(*, now: datetime | None = None, heavy: bool = False, store: Store | None = None) -> list[dict]:
    """The Polymarket step of every run. Returns the owner page's sections, having written the record, the
    public report and the owner page. Never raises."""
    now = now or datetime.now(UTC)
    from atlas.owner import page as owner_page

    sections: list[dict] = []
    reason = None
    try:
        store = store or Store.open()
        quotes, up, record, events, pairs = capture(store, now)
        priced = price(store, quotes)
        passphrase = os.environ.get(crypto.SECRET, "").strip()
        # The player props, read from the same events: kept, graded, priced, and positioned when the key
        # is set (atlas/polymarket/props.py). Never fails the run.
        prop_sections, prop_summary = props.refresh(store, events, pairs, now, passphrase or None)
        # The favorites rule, on this run's quotes: no projection in it (atlas/polymarket/favorites.py).
        fav_record, fav_section = favorites.refresh(store, quotes, now)
        report.write(priced, up, store.read("calibration"), now, props=prop_summary,
                     favorites_text=favorites.text(fav_record))
        if passphrase:
            from atlas.owner import paper

            research = _research()
            finals = paper.results(research, store.read("games"))
            chosen, graded = positions.run(priced, finals, record, passphrase, now)
            ledger = orders.grade(orders.load(passphrase), passphrase, now) if orders.mode() != "off" else orders.load(passphrase)
            sections = [*page.sections(priced, chosen, graded, now), *prop_sections, fav_section,
                        orders.section(ledger, now)]
        else:
            reason = "The owner key is not configured."
    except Exception as error:  # noqa: BLE001 - the type only: a message could quote a price
        LOG.error("polymarket not refreshed: %s", type(error).__name__)
        reason = f"This run could not price Polymarket ({type(error).__name__})."
        sections = []
    owner_page.refresh(now=now, heavy=heavy, polymarket=sections, reason=reason)
    return sections


def main() -> None:
    ap = argparse.ArgumentParser(description="Atlas on Polymarket US")
    ap.add_argument("command", nargs="?", choices=["refresh", "capture", "show"], default="show")
    ap.add_argument("--heavy", action="store_true", help="this is the daily rebuild")
    args = ap.parse_args()
    now = datetime.now(UTC)
    if args.command == "refresh":
        refresh(now=now, heavy=args.heavy)
        return
    store = Store.open()
    if args.command == "capture":
        capture(store, now)
        return
    passphrase = os.environ.get(crypto.SECRET, "").strip()
    if not passphrase:
        raise SystemExit(f"{crypto.SECRET} is not set")
    quotes, up, record, _, _ = capture(store, now)
    priced = price(store, quotes)
    from atlas.owner import paper

    chosen, graded = positions.run(priced, paper.results(_research(), store.read("games")), record, passphrase, now)
    for s in page.sections(priced, chosen, graded, now):
        print(s["title"])
        for t in s["tables"]:
            print(" ", t.get("title", ""))
            for row in t["rows"]:
                print("   ", " | ".join(json.dumps(c) if isinstance(c, list) else str(c) for c in row))


if __name__ == "__main__":
    main()
