"""Stage 3: assemble the point-in-time warehouse.

Reads the staging tables, derives pre-kickoff features, writes one parquet per
warehouse table and loads them all into ``data/warehouse/atlas.duckdb``.

The build is deterministic: same raw inputs in, byte-identical tables out.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from atlas import config
from atlas.features.point_in_time import add_point_in_time_features, to_matchup
from atlas.sources import cfbd
from atlas.staging import adjusted_efficiency as adjusted_stage
from atlas.staging import context as context_stage
from atlas.staging import efficiency as efficiency_stage
from atlas.staging import games as games_stage
from atlas.staging import market as market_stage
from atlas.staging import ratings as ratings_stage
from atlas.staging import talent as talent_stage
from atlas.staging import teams as teams_stage
from atlas.staging import weather as weather_stage
from atlas.util import get_logger, write_parquet
from atlas.warehouse import schema

LOG = get_logger(__name__)


def build_staging(
    paths: config.Paths, seasons: list[int], *, include_scheduled: bool = False
) -> dict[str, pd.DataFrame]:
    games = games_stage.build_games(
        paths.raw, paths.staging, seasons, include_scheduled=include_scheduled
    )
    teams = teams_stage.build_teams(paths.raw, paths.staging, seasons)
    team_games = games_stage.load_long(paths.staging)
    lines = market_stage.build_market_lines(paths.raw, paths.staging, seasons)
    eff = efficiency_stage.build_efficiency(paths.raw, paths.staging, seasons)
    adjusted = adjusted_stage.build_adjusted(
        paths.raw, paths.staging, include_scheduled=include_scheduled
    )
    ratings = ratings_stage.build_ratings(paths.raw, paths.staging, games, teams)
    talent = talent_stage.build_talent(paths.raw, paths.staging, games, teams)
    weather = weather_stage.build_weather(paths.raw, paths.staging, games, teams)
    ctx = context_stage.build_context(
        paths.raw, paths.staging, games, team_games, teams, weather
    )
    return {
        "games": games,
        "teams": teams,
        "team_games": team_games,
        "market_lines": lines,
        "efficiency": eff,
        "adjusted": adjusted,
        "ratings": ratings,
        "talent": talent,
        "weather": weather,
        "context": ctx,
    }


def build(
    seasons: list[int] | None = None,
    *,
    rebuild_staging: bool = True,
    include_scheduled: bool = False,
) -> dict[str, pd.DataFrame]:
    """Assemble the warehouse.

    ``include_scheduled`` carries games that have not kicked off yet, with null
    outcomes, so the live tracker can compute a feature row for a game it wants
    an opinion on. Research entry points all go through
    :func:`atlas.research.dataset.research_sample`, which drops any row without
    a result, so a warehouse built this way answers every research question
    identically - but it is not byte-identical to one built without the flag,
    and the research build never passes it.
    """
    paths = config.paths().ensure()
    seasons = seasons or config.seasons()

    if rebuild_staging:
        stage = build_staging(paths, seasons, include_scheduled=include_scheduled)
    else:
        stage = {
            "games": games_stage.load(paths.staging),
            "teams": teams_stage.load(paths.staging),
            "team_games": games_stage.load_long(paths.staging),
            "market_lines": market_stage.load(paths.staging),
            "efficiency": efficiency_stage.load(paths.staging),
            "adjusted": adjusted_stage.load(paths.staging),
            "ratings": ratings_stage.load(paths.staging),
            "talent": talent_stage.load(paths.staging),
            "context": context_stage.load(paths.staging),
        }

    games = stage["games"]
    lines = stage["market_lines"]

    tables: dict[str, pd.DataFrame] = {}
    tables["market_lines"] = _market_table(games, lines)
    tables["outcomes"] = _outcomes_table(games, tables["market_lines"])
    tables["games"] = _games_table(games, tables["outcomes"])
    tables["ratings"] = _ratings_table(stage["ratings"])
    tables["efficiency_metrics"] = _efficiency_table(
        games, stage["team_games"], stage["efficiency"]
    )
    tables["adjusted_efficiency_metrics"] = _adjusted_table(games, stage["adjusted"])
    tables["talent"] = _talent_table(stage["talent"])
    tables["context"] = _context_table(stage["context"], games)

    for name, df in tables.items():
        missing = schema.check(name, df.columns)
        if missing:
            raise ValueError(f"warehouse table {name} is missing required columns: {missing}")
        write_parquet(df, paths.warehouse / f"{name}.parquet")

    _load_duckdb(paths, tables)
    _write_manifest(paths, tables, seasons)
    return tables


# ---------------------------------------------------------------------------
# Table builders
# ---------------------------------------------------------------------------


def _market_table(games: pd.DataFrame, lines: pd.DataFrame) -> pd.DataFrame:
    out = games[["game_id"]].merge(lines, on="game_id", how="left")
    for col in schema.REQUIRED["market_lines"]:
        if col not in out.columns:
            out[col] = np.nan
    ordered = schema.REQUIRED["market_lines"]
    extra = [c for c in out.columns if c not in ordered]
    return out[[*ordered, *extra]]


def _outcomes_table(games: pd.DataFrame, market: pd.DataFrame) -> pd.DataFrame:
    df = games[["game_id", "margin", "total_points"]].merge(
        market[["game_id", "closing_spread", "closing_total"]], on="game_id", how="left"
    )
    out = pd.DataFrame({"game_id": df["game_id"]})
    # float64, not a nullable integer: a scheduled game has no result, and NA
    # propagating into the comparisons below raises rather than yielding null.
    out["actual_margin"] = pd.to_numeric(df["margin"], errors="coerce").astype("float64")
    out["actual_total"] = pd.to_numeric(df["total_points"], errors="coerce").astype("float64")

    # closing_spread is home-oriented (negative = home favoured), so the home
    # side covers when margin + closing_spread > 0. Exact zero is a push and
    # is recorded as null rather than a loss.
    ats = out["actual_margin"] + df["closing_spread"]
    out["home_cover"] = np.where(ats > 0, 1.0, np.where(ats < 0, 0.0, np.nan))
    out.loc[df["closing_spread"].isna(), "home_cover"] = np.nan
    out["ats_margin"] = ats

    ou = out["actual_total"] - df["closing_total"]
    out["over_hit"] = np.where(ou > 0, 1.0, np.where(ou < 0, 0.0, np.nan))
    out.loc[df["closing_total"].isna(), "over_hit"] = np.nan
    out["total_error"] = ou

    ordered = schema.REQUIRED["outcomes"]
    extra = [c for c in out.columns if c not in ordered]
    return out[[*ordered, *extra]]


def _games_table(games: pd.DataFrame, outcomes: pd.DataFrame) -> pd.DataFrame:
    out = games.copy()
    out = out.merge(outcomes[["game_id", "home_cover", "over_hit"]], on="game_id", how="left")
    out["over_result"] = out["over_hit"]
    ordered = schema.REQUIRED["games"]
    extra = [c for c in out.columns if c not in ordered]
    return out[[*ordered, *extra]]


def _ratings_table(ratings: pd.DataFrame) -> pd.DataFrame:
    out = ratings.copy()
    for col in schema.REQUIRED["ratings"]:
        if col not in out.columns:
            out[col] = np.nan
    ordered = schema.REQUIRED["ratings"]
    extra = [c for c in out.columns if c not in ordered]
    return out[[*ordered, *extra]]


def _efficiency_table(
    games: pd.DataFrame, team_games: pd.DataFrame, efficiency: pd.DataFrame
) -> pd.DataFrame:
    metrics = [m for m in schema.EFFICIENCY_METRICS if m in efficiency.columns]
    base = team_games[["game_id", "team_id", "season", "week", "kickoff"]].merge(
        efficiency[["game_id", "team_id", *metrics]], on=["game_id", "team_id"], how="left"
    )
    pit = add_point_in_time_features(base, metrics)
    pit_cols = [f"{m}_pit" for m in metrics]
    matchup = to_matchup(pit, games, pit_cols)

    rename = {}
    for m in metrics:
        rename[f"home_{m}_pit"] = f"home_{m}"
        rename[f"away_{m}_pit"] = f"away_{m}"
        rename[f"{m}_pit_diff"] = f"{m}_diff"
    matchup = matchup.rename(columns=rename)

    # Carry how much history each side had; a week-1 feature is all prior
    # season, a week-10 feature is mostly this season.
    prior = pit[["game_id", "team_id", "n_prior_games"]]
    matchup = matchup.merge(
        prior.rename(columns={"team_id": "home_team_id", "n_prior_games": "home_prior_games"}),
        on=["game_id", "home_team_id"],
        how="left",
    ).merge(
        prior.rename(columns={"team_id": "away_team_id", "n_prior_games": "away_prior_games"}),
        on=["game_id", "away_team_id"],
        how="left",
    )
    matchup["min_prior_games"] = matchup[["home_prior_games", "away_prior_games"]].min(axis=1)

    for col in schema.REQUIRED["efficiency_metrics"]:
        if col not in matchup.columns:
            matchup[col] = np.nan
    ordered = schema.REQUIRED["efficiency_metrics"]
    extra = [c for c in matchup.columns if c not in ordered]
    return matchup[[*ordered, *extra]]


def _adjusted_table(games: pd.DataFrame, adjusted: pd.DataFrame) -> pd.DataFrame:
    """Pivot the opponent-adjusted ratings onto one row per game.

    No point-in-time work happens here: the rating attached to a team-game is
    already the one that stood before that week, so this is a plain pivot.
    """
    metrics = [c for c in adjusted.columns if c.startswith("adj_")]
    matchup = to_matchup(adjusted, games, metrics)
    for col in schema.REQUIRED["adjusted_efficiency_metrics"]:
        if col not in matchup.columns:
            matchup[col] = np.nan
    ordered = schema.REQUIRED["adjusted_efficiency_metrics"]
    extra = [c for c in matchup.columns if c not in ordered]
    return matchup[[*ordered, *extra]]


def _talent_table(talent: pd.DataFrame) -> pd.DataFrame:
    out = talent.copy()
    for col in schema.REQUIRED["talent"]:
        if col not in out.columns:
            out[col] = np.nan
    ordered = schema.REQUIRED["talent"]
    extra = [c for c in out.columns if c not in ordered]
    return out[[*ordered, *extra]]


def _context_table(ctx: pd.DataFrame, games: pd.DataFrame) -> pd.DataFrame:
    out = ctx.copy()
    if "neutral_site" not in out.columns:
        out = out.merge(games[["game_id", "neutral_site"]], on="game_id", how="left")
    for col in schema.REQUIRED["context"]:
        if col not in out.columns:
            out[col] = np.nan
    ordered = schema.REQUIRED["context"]
    extra = [c for c in out.columns if c not in ordered]
    return out[[*ordered, *extra]]


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def _load_duckdb(paths: config.Paths, tables: dict[str, pd.DataFrame]) -> Path:
    db_path = paths.duckdb
    db_path.unlink(missing_ok=True)
    con = duckdb.connect(str(db_path))
    try:
        for name, df in tables.items():
            con.register("_df", df)
            con.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM _df")
            con.unregister("_df")
        con.execute(ANALYSIS_VIEW_SQL)
    finally:
        con.close()
    LOG.info("duckdb written -> %s", db_path)
    return db_path


ANALYSIS_VIEW_SQL = """
CREATE OR REPLACE VIEW research_games AS
SELECT
    g.*,
    m.* EXCLUDE (game_id),
    r.* EXCLUDE (game_id, season, home_team_id, away_team_id),
    e.* EXCLUDE (game_id),
    a.* EXCLUDE (game_id, home_team_id, away_team_id),
    t.* EXCLUDE (game_id, season, home_team_id, away_team_id),
    c.* EXCLUDE (game_id, season, home_team_id, away_team_id, neutral_site),
    o.actual_margin, o.actual_total, o.over_hit AS outcome_over_hit, o.ats_margin
FROM games g
LEFT JOIN market_lines m USING (game_id)
LEFT JOIN ratings r USING (game_id)
LEFT JOIN efficiency_metrics e USING (game_id)
LEFT JOIN adjusted_efficiency_metrics a USING (game_id)
LEFT JOIN talent t USING (game_id)
LEFT JOIN context c USING (game_id)
LEFT JOIN outcomes o USING (game_id)
"""


def _write_manifest(paths: config.Paths, tables: dict[str, pd.DataFrame], seasons: list[int]) -> None:
    games = tables["games"]
    manifest = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "atlas_version": config.__dict__.get("__version__", "0.1.0"),
        "seasons_requested": seasons,
        "seasons_present": sorted(int(s) for s in games["season"].unique()),
        "cfbd_enrichment": cfbd.available(),
        "tables": {
            name: {"rows": int(len(df)), "columns": int(df.shape[1])}
            for name, df in tables.items()
        },
    }
    (paths.warehouse / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser(description="Atlas stage 3: build the warehouse")
    ap.add_argument("--seasons", type=int, nargs="*", default=None)
    ap.add_argument("--no-restage", action="store_true", help="reuse existing staging tables")
    ap.add_argument(
        "--include-scheduled",
        action="store_true",
        help="also carry games that have not kicked off yet (live tracker only)",
    )
    args = ap.parse_args()
    build(
        args.seasons,
        rebuild_staging=not args.no_restage,
        include_scheduled=args.include_scheduled,
    )


if __name__ == "__main__":
    main()
