"""Market lines: closing and opening spread, total and moneyline.

The source is a per-sportsbook feed in which each team side is identified only
by a sportsbook abbreviation ("BAMA", "OKL", "MSH"). Those abbreviations do not
match any team-id table, so Atlas resolves them by constraint: an abbreviation
appears in every game its team played, and in (almost) no other, therefore the
team id that shows up in ~100% of the games carrying that abbreviation is the
team. The resolution is asserted to cover >95% of rows before use.

Atlas then reduces each game to a consensus line - the median across books -
rather than trusting a single sportsbook, and orients every spread to the home
team (negative = home favoured), matching the convention in the play-by-play
feed used to validate it.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from atlas.sources import sportsdataverse as sdv
from atlas.util import get_logger, write_parquet

LOG = get_logger(__name__)

TEAM_MARKETS = ("spread", "money_line")
MIN_ABBR_CONFIDENCE = 0.90
MIN_RESOLVED_ROW_SHARE = 0.95


def resolve_abbreviations(odds: pd.DataFrame) -> dict[str, int]:
    """Map sportsbook abbreviation -> ESPN team id by constraint propagation."""
    rows = odds[odds["market_type"].isin(TEAM_MARKETS)].copy()
    rows = rows[~rows["abbr"].isin(["over", "under"])]
    rows = rows.dropna(subset=["abbr", "game_id", "home_team_id", "away_team_id"])
    games = rows[["abbr", "game_id", "home_team_id", "away_team_id"]].drop_duplicates()

    resolved: dict[str, int] = {}
    for abbr, grp in games.groupby("abbr"):
        n = len(grp)
        counts = pd.concat([grp["home_team_id"], grp["away_team_id"]]).value_counts()
        best_id = int(counts.index[0])
        if counts.iloc[0] / n >= MIN_ABBR_CONFIDENCE:
            resolved[str(abbr)] = best_id
    LOG.info("resolved %d/%d sportsbook abbreviations", len(resolved), games["abbr"].nunique())
    return resolved


def build_market_lines(raw: Path, staging: Path, seasons: list[int]) -> pd.DataFrame:
    odds = pd.read_parquet(sdv.odds_path(raw))
    odds = odds[odds["season"].isin(seasons)].copy()
    odds = odds.dropna(subset=["game_id"])
    odds["game_id"] = odds["game_id"].astype("int64")
    odds["home_team_id"] = odds["home_team_id"].astype("Int64")
    odds["away_team_id"] = odds["away_team_id"].astype("Int64")
    odds = odds.drop_duplicates(
        ["game_id", "book", "market_type", "abbr", "lines", "odds", "opening_lines", "opening_odds"]
    )

    mapping = resolve_abbreviations(odds)
    odds["mapped_team_id"] = odds["abbr"].map(mapping).astype("Int64")
    is_home = (odds["mapped_team_id"] == odds["home_team_id"]).fillna(False).to_numpy()
    is_away = (odds["mapped_team_id"] == odds["away_team_id"]).fillna(False).to_numpy()
    odds["side"] = np.where(is_home, "home", np.where(is_away, "away", None))

    team_rows = odds[odds["market_type"].isin(TEAM_MARKETS)]
    share = team_rows["side"].notna().mean() if len(team_rows) else 0.0
    if share < MIN_RESOLVED_ROW_SHARE:
        raise ValueError(f"only {share:.1%} of team-side odds rows resolved to a side")
    LOG.info("resolved side for %.2f%% of team-side odds rows", 100 * share)

    spread = _consensus_spread(odds)
    total = _consensus_total(odds)
    moneyline = _consensus_moneyline(odds)

    lines = spread.join(total, how="outer").join(moneyline, how="outer").reset_index()
    lines["spread_movement"] = lines["closing_spread"] - lines["opening_spread"]
    lines["total_movement"] = lines["closing_total"] - lines["opening_total"]
    lines["game_id"] = lines["game_id"].astype("int64")

    write_parquet(lines, staging / "market_lines.parquet")
    return lines


def _consensus_spread(odds: pd.DataFrame) -> pd.DataFrame:
    rows = odds[(odds["market_type"] == "spread") & (odds["side"] == "home")]
    grp = rows.groupby("game_id")
    return pd.DataFrame(
        {
            "closing_spread": grp["lines"].median(),
            "opening_spread": grp["opening_lines"].median(),
            "spread_books": grp["book"].nunique(),
        }
    )


def _consensus_total(odds: pd.DataFrame) -> pd.DataFrame:
    rows = odds[(odds["market_type"] == "total") & (odds["abbr"] == "over")]
    grp = rows.groupby("game_id")
    return pd.DataFrame(
        {
            "closing_total": grp["lines"].median(),
            "opening_total": grp["opening_lines"].median(),
            "total_books": grp["book"].nunique(),
        }
    )


def _consensus_moneyline(odds: pd.DataFrame) -> pd.DataFrame:
    rows = odds[odds["market_type"] == "money_line"]
    home = rows[rows["side"] == "home"].groupby("game_id")["odds"].median()
    away = rows[rows["side"] == "away"].groupby("game_id")["odds"].median()
    return pd.DataFrame({"moneyline_home": home, "moneyline_away": away})


def validate_against_pbp(lines: pd.DataFrame, raw: Path, seasons: list[int]) -> pd.DataFrame:
    """Cross-check our home-oriented spread against the line carried in pbp.

    Returns a per-season agreement report. A sign flip in the orientation logic
    would show up here immediately as a collapse in agreement.
    """
    frames = []
    for season in seasons:
        path = sdv.pbp_path(raw, season)
        if not path.exists():
            continue
        cols = ["game_id", "spread", "over_under"]
        df = pd.read_parquet(path, columns=cols).drop_duplicates("game_id")
        df["season"] = season
        frames.append(df)
    if not frames:
        return pd.DataFrame()
    pbp = pd.concat(frames, ignore_index=True)
    pbp["game_id"] = pbp["game_id"].astype("int64")
    merged = lines.merge(pbp, on="game_id", how="inner")
    merged = merged.dropna(subset=["closing_spread", "spread"])
    merged["spread_abs_diff"] = (merged["closing_spread"] - merged["spread"]).abs()
    merged["total_abs_diff"] = (merged["closing_total"] - merged["over_under"]).abs()
    report = merged.groupby("season").agg(
        games=("game_id", "size"),
        spread_within_3=("spread_abs_diff", lambda s: float((s <= 3).mean())),
        spread_mae=("spread_abs_diff", "mean"),
        total_mae=("total_abs_diff", "mean"),
    )
    return report.reset_index()


def load(staging: Path) -> pd.DataFrame:
    return pd.read_parquet(staging / "market_lines.parquet")
