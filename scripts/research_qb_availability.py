#!/usr/bin/env python3
"""Phase 1B feasibility probe: can historical QB status be obtained, 2018-present?

Research only - this writes nothing into the warehouse. It answers two
separate questions that are easy to conflate:

*retrospective*  Who actually took the snaps in a game that has been played?
*pre-kickoff*    Who was expected to start, known before kickoff?

The first is what a backtest needs to *measure* the effect of a quarterback
change. The second is what a live model would need to *use* one. They have
very different answers, and the report says so.

The probe derives the quarterback of record for every team-game from
play-by-play (most pass attempts), then measures how often the starter changes
and what those changes are worth against the closing line.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from atlas import config  # noqa: E402
from atlas.sources import sportsdataverse as sdv  # noqa: E402
from atlas.util import download, get_logger, write_parquet  # noqa: E402

LOG = get_logger(__name__)

QB_COLUMNS = [
    "game_id", "year", "week", "season_type", "pos_team", "def_pos_team",
    "home", "away", "home_team_id", "away_team_id",
    "passer_player_name", "pass", "pass_attempt", "EPA", "start_date",
]


def extract_qbs(raw: Path, season: int, scratch: Path) -> pd.DataFrame:
    """Quarterback of record per team-game, from the full play-by-play file."""
    dest = scratch / f"qb_{season}.parquet"
    if dest.exists():
        return pd.read_parquet(dest)

    full = scratch / f"_pbp_full_{season}.parquet"
    download(
        f"{sdv.PBP_RELEASE}/play_by_play_{season}.parquet",
        full,
    )
    import pyarrow.parquet as pq

    present = set(pq.ParquetFile(full).schema_arrow.names)
    cols = [c for c in QB_COLUMNS if c in present]
    pbp = pd.read_parquet(full, columns=cols)
    full.unlink(missing_ok=True)

    if "passer_player_name" not in pbp.columns:
        LOG.warning("season %s has no passer column", season)
        return pd.DataFrame()

    passes = pbp.dropna(subset=["passer_player_name", "game_id", "pos_team"]).copy()
    passes["game_id"] = passes["game_id"].astype("int64")
    is_home = passes["pos_team"].astype("string") == passes["home"].astype("string")
    passes["team_id"] = np.where(is_home, passes["home_team_id"], passes["away_team_id"])
    passes = passes.dropna(subset=["team_id"])
    passes["team_id"] = passes["team_id"].astype("int64")

    grouped = (
        passes.groupby(["game_id", "team_id", "passer_player_name"], dropna=False)
        .agg(attempts=("passer_player_name", "size"), epa=("EPA", "mean"))
        .reset_index()
    )
    grouped = grouped.sort_values(["game_id", "team_id", "attempts"], ascending=[True, True, False])
    starters = grouped.groupby(["game_id", "team_id"], as_index=False).first()
    starters = starters.rename(columns={"passer_player_name": "qb", "attempts": "qb_attempts"})

    totals = grouped.groupby(["game_id", "team_id"], as_index=False)["attempts"].sum()
    totals = totals.rename(columns={"attempts": "team_pass_attempts"})
    out = starters.merge(totals, on=["game_id", "team_id"], how="left")
    out["qb_share"] = out["qb_attempts"] / out["team_pass_attempts"]
    out["season"] = season
    write_parquet(out, dest)
    return out


def build(seasons: list[int], scratch: Path) -> pd.DataFrame:
    paths = config.paths()
    frames = []
    for season in seasons:
        try:
            frame = extract_qbs(paths.raw, season, scratch)
            if not frame.empty:
                frames.append(frame)
        except Exception as exc:  # noqa: BLE001 - a missing season is a finding, not a crash
            LOG.warning("season %s failed: %s", season, exc)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def analyse(qbs: pd.DataFrame, scratch: Path) -> dict[str, pd.DataFrame]:
    """Coverage, change rate, and what a change is worth against the line."""
    from atlas.research.dataset import load_research_frame, research_sample
    from atlas.staging import games as games_stage

    paths = config.paths()
    games = games_stage.load(paths.staging)
    # Restrict to the research population. Non-FBS games have no play-by-play,
    # so counting them would understate coverage and inflate the apparent
    # rate at which starters change.
    fbs = games[
        (games["home_division"] == "fbs") & (games["away_division"] == "fbs")
    ]["game_id"]
    long = games_stage.load_long(paths.staging)
    long = long[long["game_id"].isin(fbs)]
    joined = long.merge(qbs[["game_id", "team_id", "qb", "qb_share", "team_pass_attempts"]],
                        on=["game_id", "team_id"], how="left")
    joined = joined.sort_values(["team_id", "season", "kickoff"])

    coverage = (
        joined.groupby("season")
        .agg(
            team_games=("game_id", "size"),
            with_qb=("qb", lambda s: int(s.notna().sum())),
            clear_starter=("qb_share", lambda s: float((s.dropna() >= 0.7).mean())),
            distinct_qbs=("qb", "nunique"),
        )
        .reset_index()
    )
    coverage["coverage"] = coverage["with_qb"] / coverage["team_games"]

    joined["prev_qb"] = joined.groupby(["team_id", "season"])["qb"].shift(1)
    joined["qb_changed"] = (
        joined["qb"].notna() & joined["prev_qb"].notna() & (joined["qb"] != joined["prev_qb"])
    )
    change = (
        joined[joined["prev_qb"].notna()]
        .groupby("season")
        .agg(games=("qb_changed", "size"), changes=("qb_changed", "sum"))
        .reset_index()
    )
    change["change_rate"] = change["changes"] / change["games"]

    df = research_sample(load_research_frame(paths.warehouse))
    changes = joined[["game_id", "team_id", "qb_changed"]]
    home = changes.rename(columns={"team_id": "home_team_id", "qb_changed": "home_qb_changed"})
    away = changes.rename(columns={"team_id": "away_team_id", "qb_changed": "away_qb_changed"})
    df = df.merge(home, on=["game_id", "home_team_id"], how="left")
    df = df.merge(away, on=["game_id", "away_team_id"], how="left")
    df["qb_change_diff"] = df["away_qb_changed"].fillna(False).astype(int) - df[
        "home_qb_changed"
    ].fillna(False).astype(int)

    effect = (
        df.groupby("qb_change_diff")
        .agg(
            games=("game_id", "size"),
            mean_residual=("market_residual_margin", "mean"),
            sd_residual=("market_residual_margin", "std"),
            cover_rate=("home_cover", "mean"),
        )
        .reset_index()
    )
    effect["residual_se"] = effect["sd_residual"] / effect["games"] ** 0.5
    effect["residual_t"] = effect["mean_residual"] / effect["residual_se"]

    # Does the effect hold season by season, or is it one strange year?
    by_season = (
        df[df["qb_change_diff"] != 0]
        .groupby("season")
        .apply(
            lambda d: pd.Series(
                {
                    "games": len(d),
                    "mean_signed_residual": float(
                        (d["market_residual_margin"] * d["qb_change_diff"]).mean()
                    ),
                    "sd": float((d["market_residual_margin"] * d["qb_change_diff"]).std()),
                }
            ),
            include_groups=False,
        )
        .reset_index()
    )
    by_season["se"] = by_season["sd"] / by_season["games"] ** 0.5
    by_season["t"] = by_season["mean_signed_residual"] / by_season["se"]

    return {
        "coverage": coverage,
        "change_rate": change,
        "residual_effect": effect,
        "residual_by_season": by_season,
    }


def main() -> int:
    scratch = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/atlas_qb")
    scratch.mkdir(parents=True, exist_ok=True)
    seasons = config.seasons()
    qbs = build(seasons, scratch)
    if qbs.empty:
        print("no quarterback data could be derived")
        return 1
    print(f"derived quarterback of record for {len(qbs):,} team-games")

    out_dir = config.paths().reports / "tables"
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, table in analyse(qbs, scratch).items():
        table.to_csv(out_dir / f"qb_{name}.csv", index=False)
        print(f"\n== {name} ==")
        print(table.round(4).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
