"""Declared warehouse schema.

The mission specifies a minimum column set per table. Atlas stores that set
verbatim and adds extra columns after it; ``REQUIRED`` is what the build and
the test suite assert on, so an added column can never silently replace a
required one.
"""

from __future__ import annotations

REQUIRED: dict[str, list[str]] = {
    "games": [
        "game_id",
        "season",
        "week",
        "date",
        "away_team",
        "home_team",
        "away_score",
        "home_score",
        "margin",
        "total_points",
        "home_win",
        "home_cover",
        "over_result",
    ],
    "market_lines": [
        "game_id",
        "closing_spread",
        "closing_total",
        "opening_spread",
        "opening_total",
        "moneyline_home",
        "moneyline_away",
        "spread_movement",
        "total_movement",
    ],
    "ratings": [
        "game_id",
        "home_sp_plus",
        "away_sp_plus",
        "sp_plus_diff",
        "home_fpi",
        "away_fpi",
        "fpi_diff",
    ],
    "efficiency_metrics": [
        "game_id",
        "home_off_epa",
        "away_off_epa",
        "home_def_epa",
        "away_def_epa",
        "off_epa_diff",
        "def_epa_diff",
        "home_success_rate",
        "away_success_rate",
        "success_rate_diff",
        "home_explosiveness",
        "away_explosiveness",
        "explosiveness_diff",
        "home_havoc",
        "away_havoc",
        "havoc_diff",
        "home_finishing_drives",
        "away_finishing_drives",
        "finishing_drives_diff",
        "home_pace",
        "away_pace",
        "pace_diff",
    ],
    "talent": [
        "game_id",
        "home_returning_production",
        "away_returning_production",
        "home_recruiting_rank",
        "away_recruiting_rank",
        "talent_diff",
    ],
    "context": [
        "game_id",
        "rest_diff",
        "travel_distance",
        "weather_temp",
        "weather_wind",
        "weather_precip",
        "neutral_site",
    ],
    "adjusted_efficiency_metrics": [
        "game_id",
        "home_adj_off_epa",
        "away_adj_off_epa",
        "adj_off_epa_diff",
        "home_adj_def_epa",
        "away_adj_def_epa",
        "adj_def_epa_diff",
        "home_adj_success_rate",
        "away_adj_success_rate",
        "adj_success_rate_diff",
        "home_adj_explosiveness",
        "away_adj_explosiveness",
        "adj_explosiveness_diff",
        "home_adj_havoc",
        "away_adj_havoc",
        "adj_havoc_diff",
        "home_adj_finishing_drives",
        "away_adj_finishing_drives",
        "adj_finishing_drives_diff",
        "home_adj_pace",
        "away_adj_pace",
        "adj_pace_diff",
    ],
    "outcomes": [
        "game_id",
        "actual_margin",
        "actual_total",
        "home_cover",
        "over_hit",
    ],
}

TABLES = tuple(REQUIRED)

#: Metrics from the opponent-adjustment solve that get a home/away/diff triple.
#: The unsuffixed names are the primary (network / Massey) method; the other
#: two methods are carried alongside so the report can price the choice.
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


#: Efficiency metrics that get a home/away/diff triple in the warehouse.
EFFICIENCY_METRICS = [
    "off_epa",
    "def_epa",
    "success_rate",
    "explosiveness",
    "havoc",
    "finishing_drives",
    "pace",
    # Atlas additions beyond the mission's minimum set.
    "def_success_rate",
    "def_explosiveness",
    "plays_per_game",
]


def check(table: str, columns) -> list[str]:
    """Return the required columns that are missing from ``columns``."""
    have = set(columns)
    return [c for c in REQUIRED[table] if c not in have]
