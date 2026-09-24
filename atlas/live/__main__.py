"""The live tracker's command line.

Two jobs, deliberately separated by cost:

``refresh``  rebuilds the warehouse including scheduled games and refits the
             models. Expensive; run it weekly.
``poll``     captures quotes, forms signals, grades what has kicked off and
             rewrites the report. Cheap; run it often.

``run`` is poll, checks and every report, which is what a scheduled job calls.
``check`` runs the operations checks alone and needs no network.
"""

from __future__ import annotations

import argparse
from datetime import UTC, date, datetime, timedelta

import pandas as pd

from atlas import config
from atlas.live import audit, books, ops_report, quality, reproduce
from atlas.live import dashboard as dashboarding
from atlas.live import drift as drifting
from atlas.live import grade as grading
from atlas.live import report as reporting
from atlas.live import signals as signalling
from atlas.live.provider import POLLED, get_provider
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
    block = quotes.reindex(columns=[
        "captured_at", "game_id", "book", "market", "line", "price",
        "open_line", "open_price", "status", "other_price",
    ]).copy()
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
        # The table keeps every model version so replays can find the number a
        # past signal was formed from; a live poll wants only the newest.
        numbers = numbers.sort_values("refreshed_at").drop_duplicates(
            ["game_id", "market"], keep="last"
        )
        return numbers.dropna(subset=["prediction"])
    LOG.warning("no numbers table - fitting models in process")
    return signalling.atlas_numbers(signalling.build_models())


def _fetch_quotes(provider: str, days: list[date]) -> pd.DataFrame:
    """The default provider means every sport Atlas publishes; a named one, itself.

    The NFL feed failing must not cost the college capture, or the reverse,
    so each is fetched on its own and an empty frame stands in for a failure.
    """
    names = list(POLLED) if provider == "espn" else [provider]
    frames = []
    for name in names:
        try:
            frames.append(get_provider(name).fetch(days))
        except Exception as error:  # noqa: BLE001 - one feed's failure is logged, not fatal
            if len(names) == 1:
                raise
            LOG.warning("%s quotes unavailable this poll: %s", name, error)
    frames = [f for f in frames if not f.empty]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def poll(horizon: int = DEFAULT_HORIZON_DAYS, *, provider: str = "espn",
         sign: bool = True) -> dict:
    """One capture pass, logged as a single auditable run.

    Every step either completes or the run is recorded as failed and the
    record is left as it was: a half-written record is worse than a missing
    hour.
    """
    store = Store.open()
    run = audit.Run(command="poll", provider=provider)
    try:
        books.reconcile(store)
        now = datetime.now(UTC).replace(microsecond=0).isoformat()
        quotes = _fetch_quotes(provider, _days(horizon))
        run.quotes = len(quotes)
        if quotes.empty:
            run.finish(store, "empty", "provider returned no quotes")
            LOG.warning("no quotes returned")
            return {"quotes": 0, "signals": 0, "graded": 0, "run_id": run.run_id}

        store.upsert("games", _games_frame(quotes, now))
        # Append-on-change: a quote that has not moved does not earn a new row,
        # which keeps the committed history readable and its diffs meaningful.
        run.snapshots_added = store.upsert("snapshots", _snapshot_frame(quotes, now))

        if sign:
            numbers = load_numbers(store)
            formed = signalling.form_signals(numbers, quotes, run_id=run.run_id)
            if not formed.empty:
                run.signals_added = store.append_new_only("signals", formed)

        run.grades_added = _grade(store)
        run.exceptions = len(quality.exceptions(store))
        alerts = drifting.monitor(store)
        run.alerts = int((alerts["severity"] != "ok").sum()) if not alerts.empty else 0
    except Exception as error:  # noqa: BLE001 - the run log is the point
        run.finish(store, "failed", f"{type(error).__name__}: {error}")
        raise

    run.finish(store, "ok")
    return {"quotes": run.quotes, "snapshots": run.snapshots_added,
            "signals": run.signals_added, "graded": run.grades_added,
            "exceptions": run.exceptions, "alerts": run.alerts,
            "run_id": run.run_id}


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
    # Appended, not replaced: a signal formed last week must stay reproducible
    # from the number that produced it, which a wholesale rewrite would erase.
    store.upsert("numbers", numbers)
    LOG.info("published %d numbers", len(numbers))
    publish_projections(store)
    return len(numbers)


def publish_projections(store: Store) -> int:
    """The model's own number for every scheduled game, and its record.

    The card reads ``projections``; the grade reads ``calibration``. Both are
    written here, by the heavy refresh, because both need the warehouse and
    the hourly poll must not.
    """
    from atlas.models import ncaaf_projection as projecting
    from atlas.models import ncaaf_state as state_mod
    from atlas.research.dataset import load_research_frame

    paths = config.paths()
    now = datetime.now(UTC).replace(microsecond=0).isoformat()
    frame = load_research_frame(paths.warehouse)
    choices = state_mod.load_choices(state_mod.choices_path(paths.root))
    projector = projecting.fit(frame, choices=choices)
    scheduled = frame[frame["actual_margin"].isna() & (frame["season"] == projector.season)]
    rows = projecting.project(projector, scheduled)
    published = 0
    if rows.empty:
        LOG.warning("refresh produced no college projections")
    else:
        rows = rows.assign(sport="ncaaf", refreshed_at=now)
        store.upsert("projections", rows)
        published += len(rows)
        LOG.info("published %d college projections, model %s", len(rows), projector.version)
    calibration = [projecting.history(frame, choices=choices).assign(sport="ncaaf")]
    # The NFL, when its warehouse is there. Its absence or failure is logged
    # and never takes the college publish down with it.
    try:
        from atlas.models import nfl_projection, nfl_state
        from atlas.research.nfl_dataset import load_nfl_frame

        nfl_frame = load_nfl_frame(paths.warehouse)
        nfl = nfl_projection.fit(nfl_frame, choices=nfl_state.load_choices(nfl_state.choices_path(paths.root)),
                                 passers=nfl_projection._passers(paths), players=nfl_projection._players(paths))
        nfl_rows = nfl_projection.project(nfl, nfl_frame[nfl_frame["actual_margin"].isna()
                                                         & (nfl_frame["season"] == nfl.season)])
        if not nfl_rows.empty:
            store.upsert("projections", nfl_rows.assign(refreshed_at=now))
            published += len(nfl_rows)
            LOG.info("published %d NFL projections, model %s", len(nfl_rows), nfl.version)
        calibration.append(nfl_projection.history(paths))
    except Exception as error:  # noqa: BLE001 - logged; the college publish stands
        LOG.warning("no NFL projections this refresh: %s", error)
    store.write("calibration", pd.concat(calibration, ignore_index=True))
    return published


def check(store: Store | None = None) -> dict:
    """Every operations check, plus the three documents. No network."""
    store = store or Store.open()
    written = ops_report.write_all(store)
    bundle = written["bundle"]
    blocking = int((bundle["exceptions"]["severity"] == "blocking").sum()) \
        if not bundle["exceptions"].empty else 0
    firing = int((bundle["alerts"]["severity"] != "ok").sum()) \
        if not bundle["alerts"].empty else 0
    replays = bundle["replays"]
    dirty = int((~replays["clean"]).sum()) if not replays.empty else 0
    return {"blocking": blocking, "alerts": firing, "replays_failed": dirty}


def main() -> None:
    ap = argparse.ArgumentParser(description="Atlas live CLV tracker")
    ap.add_argument(
        "command",
        choices=["poll", "grade", "report", "run", "refresh", "check",
                 "reproduce", "dashboard", "trace"],
    )
    ap.add_argument("--horizon", type=int, default=DEFAULT_HORIZON_DAYS)
    ap.add_argument("--provider", default="espn")
    ap.add_argument("--no-sign", action="store_true",
                    help="capture lines without forming new opinions")
    ap.add_argument("--no-rebuild", action="store_true",
                    help="refresh the numbers without rebuilding the warehouse")
    ap.add_argument("--sample", type=int, default=reproduce.REPLAY_SAMPLE
                    if hasattr(reproduce, "REPLAY_SAMPLE") else 3,
                    help="periods to replay for `reproduce`")
    ap.add_argument("--signal-id", default="", help="signal to trace")
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
    if args.command == "dashboard":
        dashboarding.write()
        return
    if args.command == "trace":
        if not args.signal_id:
            raise SystemExit("trace needs --signal-id")
        found = audit.trace(Store.open(), args.signal_id)
        if not found:
            raise SystemExit(f"no signal {args.signal_id}")
        print(pd.Series(found["signal"]).to_string())
        print()
        print(found["line_history"].to_string(index=False))
        return
    if args.command == "reproduce":
        replays = reproduce.verify(Store.open(), sample=args.sample)
        print(replays.to_string(index=False) if not replays.empty
              else "nothing to replay")
        raise SystemExit(0 if replays.empty or bool(replays["clean"].all()) else 1)
    if args.command == "check":
        LOG.info("check: %s", check())
        return

    result = poll(args.horizon, provider=args.provider, sign=not args.no_sign)
    LOG.info("poll: %s", result)
    if args.command == "run":
        reporting.write()
        LOG.info("check: %s", check())
        dashboarding.write()


if __name__ == "__main__":
    main()
