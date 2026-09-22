"""The research sample and its feature registry.

The sample is FBS-vs-FBS completed games in seasons that have market data.
Features are grouped into the mission's candidate variables; each candidate
contributes a *difference* form (home minus away, the natural margin signal)
and, where it makes sense, a *sum* form (home plus away, the natural total
signal). Modelling a total off difference features is the single most common
way to make a totals model look useless, so Atlas builds both from the start.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from atlas import config
from atlas.util import get_logger

LOG = get_logger(__name__)

ADJUSTED_METRICS = [
    "adj_off_epa",
    "adj_def_epa",
    "adj_success_rate",
    "adj_def_success_rate",
    "adj_explosiveness",
    "adj_def_explosiveness",
    "adj_havoc",
    "adj_havoc_allowed",
    "adj_finishing_drives",
    "adj_def_finishing_drives",
    "adj_pace",
    "adj_def_pace",
]

#: The non-primary adjustment methods, carried so the report can price the
#: choice of method rather than asserting one.
ALTERNATE_METHODS = ("simple", "iterative")

EFFICIENCY_METRICS = [
    "off_epa",
    "def_epa",
    "success_rate",
    "explosiveness",
    "havoc",
    "finishing_drives",
    "pace",
    "def_success_rate",
    "def_explosiveness",
    "plays_per_game",
]


@dataclass(frozen=True)
class Candidate:
    """One of the mission's candidate variables."""

    name: str
    margin_features: list[str]
    total_features: list[str] = field(default_factory=list)
    note: str = ""


def candidates() -> list[Candidate]:
    """The mission's candidate variable list, mapped onto warehouse columns."""
    return [
        Candidate("Market Spread", ["closing_spread"], ["closing_spread_abs"],
                  "closing consensus, home-oriented"),
        Candidate("Market Total", ["closing_total"], ["closing_total"]),
        Candidate("Line Movement", ["spread_movement"], ["total_movement"]),
        Candidate("SP+", ["sp_plus_diff", "sp_plus_off_diff", "sp_plus_def_diff"],
                  ["sp_plus_off_sum", "sp_plus_def_sum"], "CFBD, previous season"),
        Candidate("FPI", ["fpi_diff"], ["fpi_sum"], "ESPN, previous season"),
        Candidate("FPI Game Projection", ["fpi_home_win_prob"], [],
                  "ESPN pre-game matchup projection"),
        Candidate("Elo", ["elo_diff"], ["elo_sum"], "CFBD pre-game Elo"),
        Candidate("EPA", ["off_epa_diff", "def_epa_diff"], ["off_epa_sum", "def_epa_sum"]),
        Candidate("Success Rate", ["success_rate_diff", "def_success_rate_diff"],
                  ["success_rate_sum", "def_success_rate_sum"]),
        Candidate("Explosiveness", ["explosiveness_diff", "def_explosiveness_diff"],
                  ["explosiveness_sum", "def_explosiveness_sum"]),
        Candidate("Havoc", ["havoc_diff"], ["havoc_sum"]),
        Candidate("Finishing Drives", ["finishing_drives_diff"], ["finishing_drives_sum"]),
        Candidate("Pace", ["pace_diff", "plays_per_game_diff"],
                  ["pace_sum", "plays_per_game_sum"]),
        Candidate("Recruiting", ["recruiting_rank_diff", "talent_diff"],
                  ["talent_sum"], "CFBD only"),
        Candidate("Returning Production", ["returning_production_diff"],
                  ["returning_production_sum"], "CFBD only"),
        Candidate("Weather", ["weather_temp", "weather_wind", "weather_precip"],
                  ["weather_temp", "weather_wind", "weather_precip"], "CFBD only"),
        Candidate("Rest", ["rest_diff"], ["rest_abs"]),
        Candidate("Travel", ["travel_distance", "travel_distance_diff"], ["travel_distance"]),
        Candidate("Neutral Site", ["neutral_site_flag"], ["neutral_site_flag"]),
    ]


QUERY = """
SELECT * FROM research_games
WHERE home_division = 'fbs' AND away_division = 'fbs'
"""


def load_research_frame(warehouse: Path | None = None) -> pd.DataFrame:
    warehouse = warehouse or config.paths().warehouse
    con = duckdb.connect(str(warehouse / "atlas.duckdb"), read_only=True)
    try:
        df = con.execute(QUERY).df()
    finally:
        con.close()
    return add_derived_features(df)


def add_derived_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["neutral_site_flag"] = out["neutral_site"].astype("float64")
    out["closing_spread_abs"] = out["closing_spread"].abs()
    out["rest_abs"] = out["rest_diff"].abs()

    adjusted_variants = [
        *ADJUSTED_METRICS,
        *(f"{m}_{method}" for method in ALTERNATE_METHODS for m in ADJUSTED_METRICS),
    ]
    for metric in [*EFFICIENCY_METRICS, *adjusted_variants]:
        home, away = f"home_{metric}", f"away_{metric}"
        if home in out.columns and away in out.columns:
            out[f"{metric}_sum"] = out[home] + out[away]

    for name in ("sp_plus", "sp_plus_off", "sp_plus_def", "fpi", "talent",
                 "returning_production"):
        home, away = f"home_{name}", f"away_{name}"
        if home in out.columns and away in out.columns:
            out[f"{name}_sum"] = pd.to_numeric(out[home], errors="coerce") + pd.to_numeric(
                out[away], errors="coerce"
            )
    if {"home_pregame_elo", "away_pregame_elo"}.issubset(out.columns):
        out["elo_sum"] = out["home_pregame_elo"] + out["away_pregame_elo"]

    # Market-implied margin: the closing spread is home-oriented, so the
    # market's point estimate of the home margin is its negation.
    out["market_margin"] = -out["closing_spread"]

    # Phase 1B's central targets. A model that predicts margin well has mostly
    # rediscovered the closing line; a model that predicts the *residual* has
    # found something the line does not know.
    out["market_residual_margin"] = out["actual_margin"] - out["market_margin"]
    out["market_residual_total"] = out["actual_total"] - out["closing_total"]

    # Net team strength in one number, raw and adjusted, for like-for-like
    # comparison (defensive metrics are "allowed", so they subtract).
    if {"off_epa_diff", "def_epa_diff"}.issubset(out.columns):
        out["net_epa_diff"] = out["off_epa_diff"] - out["def_epa_diff"]
    if {"adj_off_epa_diff", "adj_def_epa_diff"}.issubset(out.columns):
        out["adj_net_epa_diff"] = out["adj_off_epa_diff"] - out["adj_def_epa_diff"]

    # Weather: a dome has no wind whatever the station says, and wind is the
    # channel with a documented effect on scoring.
    if "weather_wind_effective" in out.columns:
        out["weather_wind_sq"] = out["weather_wind_effective"] ** 2
    return out


def research_sample(
    df: pd.DataFrame,
    *,
    require_market: bool = True,
    min_prior_games: int | None = None,
) -> pd.DataFrame:
    """Apply the standard research filters and report what each one costs."""
    out = df.copy()
    n0 = len(out)
    out = out[out["actual_margin"].notna()]
    if require_market:
        out = out[out["closing_spread"].notna() & out["closing_total"].notna()]
    if min_prior_games is not None:
        out = out[out["min_prior_games"].fillna(0) >= min_prior_games]
    LOG.info("research sample: %d -> %d games", n0, len(out))
    return out.reset_index(drop=True)


def available_features(df: pd.DataFrame, features: list[str], *, min_coverage: float = 0.5) -> list[str]:
    """Keep only features that exist and are populated often enough to model."""
    keep = []
    for f in features:
        if f not in df.columns:
            continue
        series = pd.to_numeric(df[f], errors="coerce")
        if series.notna().mean() >= min_coverage and series.std(skipna=True) > 0:
            keep.append(f)
    return keep


def feature_matrix(df: pd.DataFrame, features: list[str]) -> tuple[np.ndarray, list[str]]:
    """Numeric matrix with median imputation, plus the surviving column names."""
    cols = available_features(df, features)
    if not cols:
        return np.zeros((len(df), 0)), []
    block = df[cols].apply(pd.to_numeric, errors="coerce")
    filled = block.fillna(block.median(numeric_only=True))
    return filled.to_numpy(dtype=float), cols
