"""The NBA research frame: ``research_games`` from ``data/warehouse/nba.duckdb``."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from atlas.staging.nba.build import warehouse_path


def load_nba_frame(warehouse: Path | None = None) -> pd.DataFrame:
    con = duckdb.connect(str(warehouse_path(warehouse)), read_only=True)
    try:
        df = con.execute("SELECT * FROM research_games").df()
    finally:
        con.close()
    df["neutral_site_flag"] = df["neutral_site"].astype("float64")
    df["market_margin"] = -df["closing_spread"]
    df["rest_diff"] = df["home_days_rest"] - df["away_days_rest"]
    return df


def load_table(name: str, warehouse: Path | None = None) -> pd.DataFrame:
    """Any table of the NBA warehouse (``team_games``, ``player_games``)."""
    con = duckdb.connect(str(warehouse_path(warehouse)), read_only=True)
    try:
        return con.execute(f"SELECT * FROM {name}").df()  # noqa: S608 - a table name from the code, not input
    finally:
        con.close()


def research_sample(df: pd.DataFrame, *, require_market: bool = True) -> pd.DataFrame:
    """Completed games, and with the market's close where the model is scored against it."""
    out = df[df["actual_margin"].notna()]
    if require_market:
        out = out[out["closing_spread"].notna() & out["closing_total"].notna()]
    return out.reset_index(drop=True)
