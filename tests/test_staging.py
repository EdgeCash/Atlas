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


def test_name_resolver_falls_back_across_seasons():
    """Ratings from the season before the warehouse starts must still resolve."""
    ref = pd.DataFrame(
        {
            "season": [2021, 2022],
            "team_id": [7, 7],
            "school": ["Team 00", "Team 00"],
        }
    )
    resolve = teams.name_resolver(ref)
    exact = resolve(2021, pd.Series(["Team 00"]))
    earlier = resolve(2017, pd.Series(["Team 00"]))  # season absent from the table
    unknown = resolve(2021, pd.Series(["Nowhere State"]))
    assert exact.iloc[0] == 7
    assert earlier.iloc[0] == 7
    assert pd.isna(unknown.iloc[0])


def test_new_coach_and_program_mean_are_preseason_facts(tmp_path):
    """A head coach hired in the off-season is new; a mid-season interim never
    opens a season; the programme mean uses only seasons already played."""
    from atlas.staging import talent

    raw = tmp_path / "raw"
    (raw / "cfbd").mkdir(parents=True)
    teams = pd.DataFrame({"season": [2021, 2021, 2022, 2022], "school": ["A", "B", "A", "B"],
                          "team_id": [1, 2, 1, 2]})

    def coaches(season, rows):
        pd.DataFrame([{"id": i, "firstName": "x", "lastName": n, "hireDate": h,
                       "seasons": [{"school": s, "year": season, "games": g}]}
                      for i, n, h, s, g in rows]).to_parquet(raw / "cfbd" / f"coaches_{season}.parquet", index=False)

    coaches(2021, [(1, "Old", "2015-01-10T00:00:00.000Z", "A", 8),
                   (3, "Interim", "2021-10-01T00:00:00.000Z", "A", 4),
                   (2, "Steady", "2010-01-10T00:00:00.000Z", "B", 12)])
    coaches(2022, [(4, "New", "2021-12-05T00:00:00.000Z", "A", 12),
                   (2, "Steady", "2010-01-10T00:00:00.000Z", "B", 12)])
    for year, a, b in ((2019, 10.0, -5.0), (2020, 20.0, -5.0), (2021, 30.0, -5.0), (2022, 99.0, 99.0)):
        pd.DataFrame({"year": year, "team": ["A", "B"], "rating": [a, b]}).to_parquet(
            raw / "cfbd" / f"sp_plus_{year}.parquet", index=False)
    games = pd.DataFrame({"game_id": [1, 2], "season": [2021, 2022], "home_team_id": [1, 1], "away_team_id": [2, 2]})

    out = talent.build_talent(raw, tmp_path, games, teams).set_index("game_id")
    assert out.loc[1, "home_new_coach"] == 0.0          # hired 2015; the October interim never opened 2021
    assert out.loc[2, "home_new_coach"] == 1.0          # hired December 2021
    assert out.loc[2, "away_new_coach"] == 0.0
    assert out.loc[2, "new_coach_diff"] == 1.0
    assert out.loc[1, "home_sp_program_mean"] == 15.0   # 2019-2020: 2021 has not been played
    assert out.loc[2, "home_sp_program_mean"] == 20.0   # 2019-2021; 2022's 99 is the future
    assert out.loc[2, "away_sp_program_mean"] == -5.0


def test_transfer_portal_quality_is_summed_in_and_out_and_zero_before_the_portal(tmp_path):
    from atlas.staging import talent

    raw = tmp_path / "raw"
    (raw / "cfbd").mkdir(parents=True)
    teams = pd.DataFrame({"season": [2020, 2020, 2022, 2022], "school": ["A", "B", "A", "B"], "team_id": [1, 2, 1, 2]})
    pd.DataFrame({"season": 2022, "firstName": ["x"] * 3, "lastName": ["y"] * 3, "position": ["QB", "WR", "DL"],
                  "origin": ["B", "Elsewhere", "A"], "destination": ["A", "A", "Elsewhere"],
                  "transferDate": ["2022-01-05"] * 3, "rating": [0.90, None, None], "stars": [4, 3, None],
                  "eligibility": ["Immediate"] * 3}).to_parquet(raw / "cfbd" / "portal_2022.parquet", index=False)
    games = pd.DataFrame({"game_id": [1, 2], "season": [2020, 2022], "home_team_id": [1, 1], "away_team_id": [2, 2]})
    out = talent.build_talent(raw, tmp_path, games, teams).set_index("game_id")
    assert out.loc[2, "home_portal_in"] == pytest.approx(0.90 + 0.84)      # rating, then the three-star typical
    assert out.loc[2, "home_portal_out"] == pytest.approx(0.75)            # unrated: the floor
    assert out.loc[2, "away_portal_out"] == pytest.approx(0.90) and out.loc[2, "away_portal_in"] == 0.0
    assert out.loc[1, "home_portal_in"] == 0.0 and out.loc[1, "away_portal_out"] == 0.0   # 2020: no portal
