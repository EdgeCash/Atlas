"""Stage 1: pull every source into data/raw.

Re-running is cheap: each artefact is cached on disk and skipped if present.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from atlas import config
from atlas.sources import cfbd, espn, qb_of_record, rosters
from atlas.sources import sportsdataverse as sdv
from atlas.util import get_logger

LOG = get_logger(__name__)


def ingest(
    seasons: list[int] | None = None,
    *,
    with_pbp: bool = True,
    with_predictors: bool = True,
    with_cfbd: bool = True,
    with_qb: bool = False,
) -> dict:
    paths = config.paths().ensure()
    seasons = seasons or config.seasons()
    manifest: dict = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "seasons": seasons,
        "sources": {},
    }

    LOG.info("ingesting betting market odds")
    sdv.fetch_odds(paths.raw)
    manifest["sources"]["odds"] = "sportsdataverse/cfbfastR-data betting/parquet"

    got_schedule: list[int] = []
    for season in seasons:
        try:
            sdv.fetch_schedules(paths.raw, season)
            sdv.fetch_team_info(paths.raw, season)
            got_schedule.append(season)
        except Exception as exc:  # noqa: BLE001 - a season may not exist yet
            LOG.warning("schedule/team_info unavailable for %s: %s", season, exc)
    manifest["sources"]["schedules"] = got_schedule

    # FPI needs the season before the first one we model, because Atlas only
    # ever uses the previous season's final rating.
    fpi_seasons = [min(seasons) - 1, *seasons]
    got_fpi: list[int] = []
    for season in fpi_seasons:
        try:
            espn.fetch_season_fpi(paths.raw, season)
            got_fpi.append(season)
        except Exception as exc:  # noqa: BLE001
            LOG.warning("ESPN FPI unavailable for %s: %s", season, exc)
    manifest["sources"]["espn_season_fpi"] = got_fpi

    if with_pbp:
        got_pbp: list[int] = []
        for season in got_schedule:
            try:
                sdv.fetch_play_by_play(paths.raw, season)
                got_pbp.append(season)
            except Exception as exc:  # noqa: BLE001
                LOG.warning("play-by-play unavailable for %s: %s", season, exc)
        manifest["sources"]["play_by_play"] = got_pbp

    if with_predictors:
        got_pred: list[int] = []
        for season in got_schedule:
            try:
                ids = _fbs_game_ids(paths.raw, season)
                espn.fetch_game_predictors(paths.raw, season, ids)
                got_pred.append(season)
            except Exception as exc:  # noqa: BLE001
                LOG.warning("ESPN predictors failed for %s: %s", season, exc)
        manifest["sources"]["espn_predictor"] = got_pred

    # Rosters carry class membership across seasons, which is how Phase 1C
    # identifies transfers and first-year players.
    got_rosters: list[int] = []
    roster_seasons = list(range(min(seasons) - 4, max(seasons) + 1))
    for season in roster_seasons:
        try:
            rosters.fetch(paths.raw, season)
            got_rosters.append(season)
        except Exception as exc:  # noqa: BLE001
            LOG.warning("rosters unavailable for %s: %s", season, exc)
    manifest["sources"]["rosters"] = got_rosters

    if with_qb:
        # Research-only: the quarterback of record is known at kickoff at the
        # earliest, so it is fetched into its own directory and never read by
        # the warehouse build.
        qb = qb_of_record.build(paths.raw, got_schedule)
        manifest["sources"]["qb_of_record"] = {
            "team_games": int(len(qb)),
            "warehouse_use": "none - post-kickoff data, research only",
        }

    if with_cfbd:
        # Season-level ratings are joined from the *previous* season, so the
        # season before the first modelled one has to be fetched too.
        manifest["sources"]["cfbd"] = {
            "enabled": cfbd.available(),
            "datasets": sorted(cfbd.fetch_all(paths.raw, [min(seasons) - 1, *seasons])),
        }

    out = paths.raw / "MANIFEST.json"
    out.write_text(json.dumps(manifest, indent=2) + "\n")
    LOG.info("raw ingest complete -> %s", out)
    return manifest


def _fbs_game_ids(raw: Path, season: int) -> list[int]:
    df = pd.read_parquet(sdv.schedules_path(raw, season))
    mask = (
        df["home_division"].isin(config.FBS_DIVISIONS)
        & df["away_division"].isin(config.FBS_DIVISIONS)
        & df["season_type"].isin(config.SEASON_TYPES)
        & df["completed"].fillna(False).astype(bool)
    )
    return sorted(df.loc[mask, "game_id"].dropna().astype("int64").unique().tolist())


def main() -> None:
    ap = argparse.ArgumentParser(description="Atlas stage 1: raw ingest")
    ap.add_argument("--seasons", type=int, nargs="*", default=None)
    ap.add_argument("--no-pbp", action="store_true")
    ap.add_argument("--no-predictors", action="store_true")
    ap.add_argument("--no-cfbd", action="store_true")
    ap.add_argument(
        "--with-qb",
        action="store_true",
        help="also extract the quarterback of record (research only, ~1 GB transient)",
    )
    args = ap.parse_args()
    ingest(
        args.seasons,
        with_pbp=not args.no_pbp,
        with_predictors=not args.no_predictors,
        with_cfbd=not args.no_cfbd,
        with_qb=args.with_qb,
    )


if __name__ == "__main__":
    main()
