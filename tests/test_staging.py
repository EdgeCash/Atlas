"""Staging transforms: market orientation, efficiency maths, geography."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from atlas.staging import context, efficiency, games, market, teams

# --- market ---------------------------------------------------------------


def _odds_rows(home_id: int, away_id: int, home_abbr: str, away_abbr: str, close: float):
    common = {"game_id": 1.0, "season": 2021.0, "book": "Book A", "season_type": "regular",
              "week": 1.0, "home_team_id": float(home_id), "away_team_id": float(away_id),
              "game_desc": "A@B", "date_time": "x", "id": 1.0,
              "opening_lines": np.nan, "opening_odds": np.nan}
    return [
        {**common, "market_type": "spread", "abbr": home_abbr, "lines": close, "odds": -110.0},
        {**common, "market_type": "spread", "abbr": away_abbr, "lines": -close, "odds": -110.0},
    ]


def test_abbreviations_resolve_to_the_team_present_in_every_game():
    rows = []
    for i, opponent in enumerate([20, 30, 40], start=1):
        for r in _odds_rows(10, opponent, "HOM", f"OPP{i}", -7.0):
            r["game_id"] = float(i)
            rows.append(r)
    mapping = market.resolve_abbreviations(pd.DataFrame(rows))
    assert mapping["HOM"] == 10


def test_consensus_spread_is_home_oriented(tmp_path, synthetic_build):
    lines = market.load(synthetic_build["paths"].staging)
    g = games.load(synthetic_build["paths"].staging)
    merged = g.merge(lines, on="game_id").dropna(subset=["closing_spread"])
    # A home favourite must carry a negative spread, and the synthetic league
    # was generated with the home side favoured by its strength edge.
    strong_home = merged[merged["home_pregame_elo"] - merged["away_pregame_elo"] > 200]
    assert (strong_home["closing_spread"] < 0).mean() > 0.9


def test_line_movement_is_close_minus_open(synthetic_build):
    lines = market.load(synthetic_build["paths"].staging).dropna(
        subset=["closing_spread", "opening_spread"]
    )
    np.testing.assert_allclose(
        lines["spread_movement"], lines["closing_spread"] - lines["opening_spread"]
    )


def test_market_build_rejects_unresolvable_abbreviations(tmp_path, monkeypatch):
    rows = []
    for i in range(3):
        for r in _odds_rows(10, 20 + i, "???", "!!!", -3.0):
            r["game_id"] = float(i)
            rows.append(r)
    odds = pd.DataFrame(rows)
    (tmp_path / "odds").mkdir(parents=True)
    odds.to_parquet(tmp_path / "odds" / "cfb_line_odds.parquet", index=False)
    monkeypatch.setattr(market, "resolve_abbreviations", lambda _df: {})
    with pytest.raises(ValueError, match="resolved to a side"):
        market.build_market_lines(tmp_path, tmp_path, [2021])


# --- games ----------------------------------------------------------------


def test_margin_and_total_definitions(synthetic_build):
    g = games.load(synthetic_build["paths"].staging)
    assert (g["margin"] == g["home_score"] - g["away_score"]).all()
    assert (g["total_points"] == g["home_score"] + g["away_score"]).all()
    assert set(g["home_win"].unique()) <= {0, 1}


def test_long_view_has_two_rows_per_game(synthetic_build):
    g = games.load(synthetic_build["paths"].staging)
    long = games.load_long(synthetic_build["paths"].staging)
    assert len(long) == 2 * len(g)
    assert long.groupby("game_id").size().eq(2).all()


def test_days_rest_is_the_gap_since_a_team_last_played(synthetic_build):
    long = games.load_long(synthetic_build["paths"].staging)
    sample = long[long["days_rest"].notna()]
    assert (sample["days_rest"] > 0).all()
    assert sample["days_rest"].median() == pytest.approx(7.0, abs=1.0)


# --- efficiency -----------------------------------------------------------


def test_efficiency_is_mirrored_between_the_two_sides(synthetic_build):
    eff = efficiency.load(synthetic_build["paths"].staging)
    pair = eff.groupby("game_id").filter(lambda d: len(d) == 2)
    first = pair.groupby("game_id").nth(0).reset_index(drop=True)
    second = pair.groupby("game_id").nth(1).reset_index(drop=True)
    np.testing.assert_allclose(first["off_epa"], second["def_epa"], rtol=1e-9)


def test_havoc_is_a_rate(synthetic_build):
    eff = efficiency.load(synthetic_build["paths"].staging)
    havoc = eff["havoc"].dropna()
    assert havoc.between(0, 1).all()


def test_garbage_time_plays_are_excluded():
    plays = pd.DataFrame(
        {
            "score_diff": [0.0, 50.0, 0.0, 30.0],
            "period": [1, 1, 4, 4],
        }
    )
    mask = efficiency._is_garbage_time(plays)
    assert mask.tolist() == [False, True, False, True]


# --- context --------------------------------------------------------------


def test_haversine_matches_a_known_distance():
    # New York to Los Angeles is about 2,450 miles.
    miles = context.haversine_miles([40.7128], [-74.0060], [34.0522], [-118.2437])[0]
    assert 2400 < miles < 2500


def test_home_team_travels_nothing_at_its_own_stadium(synthetic_build):
    ctx = context.load(synthetic_build["paths"].staging)
    home_travel = ctx["home_travel_distance"].dropna()
    assert (home_travel < 1e-6).all()


def test_venue_lookup_is_unique_per_venue(synthetic_build):
    t = teams.load(synthetic_build["paths"].staging)
    v = teams.venues(t)
    assert v["venue_id"].is_unique
