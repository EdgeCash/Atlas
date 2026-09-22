"""The live tracker's command line.

Two jobs, deliberately separated by cost:

``refresh``  rebuilds the warehouse including scheduled games and refits the
             models. Expensive; run it weekly.
``poll``     captures quotes, forms signals, grades what has kicked off and
             rewrites the report. Cheap; run it often.

``run`` is poll plus report, which is what a scheduled job calls.
"""

from __future__ import annotations

import argparse
from datetime import UTC, date, datetime, timedelta

import pandas as pd

from atlas.live import grade as grading
from atlas.live import report as reporting
from atlas.live import signals as signalling
from atlas.live.provider import get_provider
from atlas.live.store import Store
from atlas.util import get_logger

LOG = get_logger(__name__)

#: How far ahead to look for games. A week covers the slate; beyond that most
#: books have not posted a number and the poll is wasted.
DEFAULT_HORIZON_DAYS = 8


def _days(horizon: int) -> list[date]:
    today = datetime.now(UTC).date()
    return [today + timedelta(days=i) for i in range(horizon)]


def _games_frame(quotes: pd.DataFrame, now: str) -> pd.DataFrame:
    columns = ["game_id", "season", "week", "kickoff", "home_team", "away_team",
               "home_team_id", "away_team_id", "status", "completed",
               "home_score", "away_score"]
    games = quotes[[c for c in columns if c in quotes.columns]].drop_duplicates("game_id")
    games = games.copy()
    games["first_seen_at"] = now
    games["updated_at"] = now
    return games


def _snapshot_frame(quotes: pd.DataFrame, now: str) -> pd.DataFrame:
    block = quotes[[
        "captured_at", "game_id", "book", "market", "line", "price",
        "open_line", "open_price", "status",
    ]].copy()
    block["last_seen_at"] = now
    return block


def load_numbers(store: Store) -> pd.DataFrame:
    """Atlas's numbers, from the weekly refresh rather than a live model fit.

    The poll runs every hour and must stay cheap; fitting the model needs the
    warehouse, which needs the play-by-play, which is a gigabyte. So the
    expensive half writes ``tracking/numbers.csv`` once a week and the cheap
    half reads it. If the table is missing and a warehouse happens to be
    present, the model is fitted in process instead.
    """
    numbers = store.read("numbers")
    if not numbers.empty:
        numbers["prediction"] = pd.to_numeric(numbers["prediction"], errors="coerce")
        numbers["threshold"] = pd.to_numeric(numbers["threshold"], errors="coerce")
        return numbers.dropna(subset=["prediction"])
    LOG.warning("no numbers table - fitting models in process")
    return signalling.atlas_numbers(signalling.build_models())


def poll(horizon: int = DEFAULT_HORIZON_DAYS, *, provider: str = "espn",
         sign: bool = True) -> dict:
    store = Store.open()
    now = datetime.now(UTC).replace(microsecond=0).isoformat()
    quotes = get_provider(provider).fetch(_days(horizon))
    if quotes.empty:
        LOG.warning("no quotes returned")
        return {"quotes": 0, "signals": 0, "graded": 0}

    store.upsert("games", _games_frame(quotes, now))
    # Append-on-change: a quote that has not moved does not earn a new row,
    # which keeps the committed history readable and its diffs meaningful.
    added = store.upsert("snapshots", _snapshot_frame(quotes, now))

    new_signals = 0
    if sign:
        numbers = load_numbers(store)
        formed = signalling.form_signals(numbers, quotes)
        if not formed.empty:
            new_signals = store.append_new_only("signals", formed)

    graded = _grade(store)
    return {"quotes": len(quotes), "snapshots": added,
            "signals": new_signals, "graded": graded}


def _grade(store: Store) -> int:
    signals = store.read("signals")
    if signals.empty:
        return 0
    existing = store.read("grades")
    done = set(existing["signal_id"].astype(str)) if not existing.empty else set()
    rows = grading.grade(
        signals, store.read("snapshots"), store.read("games"), already_graded=done
    )
    return store.upsert("grades", rows) if not rows.empty else 0


def refresh(seasons: list[int] | None = None, *, rebuild: bool = True) -> int:
    """Rebuild the warehouse with scheduled games and publish Atlas's numbers."""
    from atlas.warehouse import build as warehouse

    if rebuild:
        warehouse.build(seasons, include_scheduled=True)
    numbers = signalling.atlas_numbers(signalling.build_models())
    if numbers.empty:
        LOG.warning("refresh produced no numbers")
        return 0
    numbers = numbers.copy()
    numbers["refreshed_at"] = datetime.now(UTC).replace(microsecond=0).isoformat()
    store = Store.open()
    # Replace wholesale: last week's numbers for a game that has since been
    # played are noise, and a stale number is worse than no number.
    store.write("numbers", numbers)
    LOG.info("published %d numbers", len(numbers))
    return len(numbers)


def main() -> None:
    ap = argparse.ArgumentParser(description="Atlas live CLV tracker")
    ap.add_argument("command", choices=["poll", "grade", "report", "run", "refresh"])
    ap.add_argument("--horizon", type=int, default=DEFAULT_HORIZON_DAYS)
    ap.add_argument("--provider", default="espn")
    ap.add_argument("--no-sign", action="store_true",
                    help="capture lines without forming new opinions")
    ap.add_argument("--no-rebuild", action="store_true",
                    help="refresh the numbers without rebuilding the warehouse")
    args = ap.parse_args()

    if args.command == "refresh":
        refresh(rebuild=not args.no_rebuild)
        return
    if args.command == "grade":
        LOG.info("graded %d", _grade(Store.open()))
        return
    if args.command == "report":
        reporting.write()
        return

    result = poll(args.horizon, provider=args.provider, sign=not args.no_sign)
    LOG.info("poll: %s", result)
    if args.command == "run":
        reporting.write()


if __name__ == "__main__":
    main()
