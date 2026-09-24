"""The NFL research frame: one row per game, every column pre-kickoff safe
except the ones named as facts about the finished game.

Mirrors :mod:`atlas.research.dataset` for college. ``research_sample`` is the
college one, reused: completed games with a closing spread and total.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from atlas.research.dataset import research_sample  # noqa: F401 - re-exported for callers
from atlas.staging.nfl.build import warehouse_path


def load_nfl_frame(warehouse: Path | None = None) -> pd.DataFrame:
    con = duckdb.connect(str(warehouse_path(warehouse)), read_only=True)
    try:
        df = con.execute("SELECT * FROM research_games").df()
    finally:
        con.close()
    df["neutral_site_flag"] = df["neutral_site"].astype("float64")
    df["closing_spread_abs"] = df["closing_spread"].abs()
    df["market_margin"] = -df["closing_spread"]
    if "home_days_rest" in df and "away_days_rest" in df:
        df["rest_diff"] = df["home_days_rest"] - df["away_days_rest"]
    # The card's drivers read the same metric names as college; the NFL's
    # season-to-date plays per game is the point-in-time column.
    for side in ("home", "away"):
        if f"{side}_plays_per_game_pit" in df and f"{side}_plays_per_game" not in df:
            df[f"{side}_plays_per_game"] = df[f"{side}_plays_per_game_pit"]
    return df
