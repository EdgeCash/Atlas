"""The statistical matchup: counting rules, ranks, and the card panel."""

from __future__ import annotations

import re

import pandas as pd
import pytest

from atlas.site import matchup as mu


def _college_raw(tmp_path):
    """One game, A at home to B: a 10-yard run, a 25-yard pass on third and 5,
    a 7-yard sack, an interception thrown by A; a 4-yard run by B."""
    (tmp_path / "pbp").mkdir()
    (tmp_path / "schedules").mkdir()
    plays = pd.DataFrame([
        # pos, def, rush, pass, sack, int, yards, down, dist, ytg, drive, pts, play_type
        ("A", "B", 1, 0, 0, 0, 10, 1, 10, 30, 1, 7, "Rush"),
        ("A", "B", 0, 1, 0, 0, 25, 3, 5, 20, 1, 7, "Passing Touchdown"),
        ("A", "B", 0, 1, 1, 0, -7, 2, 10, 60, 2, 0, "Sack"),
        ("A", "B", 0, 1, 0, 1, 0, 3, 8, 67, 2, 0, "Interception Return"),
        ("B", "A", 1, 0, 0, 0, 4, 3, 6, 70, 3, 0, "Rush"),
    ], columns=["pos_team", "def_pos_team", "rush", "pass", "sack", "int", "yards_gained", "down", "distance",
                "yards_to_goal", "drive_id", "drive_pts", "play_type"])
    plays = plays.assign(game_id=1, penalty_no_play=False)
    plays.to_parquet(tmp_path / "pbp" / "pbp_2026.parquet")
    pd.DataFrame({"game_id": [1], "home_team": ["A"], "away_team": ["B"], "home_division": ["fbs"],
                  "away_division": ["fbs"], "home_points": [7], "away_points": [3],
                  "start_date": ["2026-09-19T20:00:00Z"]}).to_parquet(tmp_path / "schedules" / "schedules_2026.parquet")
    return tmp_path


def test_college_figures_follow_the_ncaa_conventions(tmp_path):
    t = mu.college_table(2026, raw=_college_raw(tmp_path))
    a, b = t.loc["A"], t.loc["B"]
    assert a["games"] == 1 and a["points_for"] == 7 and a["points_against"] == 3
    assert a["rush_yards"] == 10 - 7                  # the sack is a rushing play, as the NCAA counts it
    assert a["pass_yards"] == 25 and a["explosive"] == 1 and a["sacks_allowed"] == 1 and b["sacks"] == 1
    assert a["third_down"] == pytest.approx(0.5)       # 1 of 2 third downs converted
    assert b["third_down_allowed"] == pytest.approx(0.5) and b["third_down"] == 0
    assert a["red_zone"] == 1.0                        # one drive reached the 20 and scored a touchdown
    assert a["turnover_margin"] == -1 and b["turnover_margin"] == 1
    assert a["plays"] == 4 and a["yards_per_play"] == pytest.approx((10 + 25 - 7 + 0) / 4)


def test_nfl_passing_is_net_of_sacks_and_penalties_are_counted(tmp_path):
    (tmp_path / "nfl").mkdir()
    pbp = pd.DataFrame([
        # posteam, defteam, play_type, sack, yards, down, 3rd conv, yardline, drive, result, int, fumble_lost, penalty, pen_team, pen_yds
        ("BUF", "KC", "pass", 0, 30, 1, 0, 40, 1, "Touchdown", 0, 0, 0, None, 0),
        ("BUF", "KC", "pass", 1, -8, 3, 0, 10, 1, "Touchdown", 0, 0, 0, None, 0),
        ("BUF", "KC", "run", 0, 5, 1, 0, 5, 1, "Touchdown", 0, 0, 1, "KC", 15),
        ("KC", "BUF", "run", 0, 2, 3, 1, 50, 2, "Punt", 0, 1, 1, "KC", 10),
    ], columns=["posteam", "defteam", "play_type", "sack", "yards_gained", "down", "third_down_converted",
                "yardline_100", "fixed_drive", "fixed_drive_result", "interception", "fumble_lost", "penalty",
                "penalty_team", "penalty_yards"]).assign(game_id="2026_01_KC_BUF", aborted_play=0)
    pbp.to_parquet(tmp_path / "nfl" / "pbp_2026.parquet")
    pd.DataFrame({"season": [2026], "game_id": ["2026_01_KC_BUF"], "home_team": ["BUF"], "away_team": ["KC"],
                  "home_score": [7], "away_score": [0], "gameday": ["2026-09-13"]}).to_parquet(
        tmp_path / "nfl" / "schedules.parquet")
    t = mu.nfl_table(2026, raw=tmp_path)
    assert t.loc["BUF", "pass_yards"] == 30 - 8          # net of the sack, as the NFL counts it
    assert t.loc["BUF", "rush_yards"] == 5 and t.loc["BUF", "red_zone"] == 1.0
    assert t.loc["KC", "third_down"] == 1.0 and t.loc["BUF", "turnover_margin"] == 1
    assert t.loc["KC", "penalty_yards"] == 25 and t.loc["BUF", "penalty_yards"] == 0


def test_rank_one_is_the_best_and_pace_ranks_the_most():
    t = pd.DataFrame({"points_for": [30.0, 20.0, 40.0], "points_against": [10.0, 30.0, 20.0],
                      "plays": [60.0, 75.0, 70.0]}, index=["x", "y", "z"])
    r = mu.ranks(t)
    assert list(r["points_for"]) == [2, 3, 1] and list(r["points_against"]) == [1, 3, 2]
    assert list(r["plays"]) == [3, 1, 2]


def test_the_matchup_panel_pairs_each_offense_with_the_defense_it_faces():
    import sys

    sys.path.insert(0, "tests")
    import test_site as ts


    card = ts._card()
    stats = {s.key for pair in mu.PAIRS for s in pair} | {"turnover_margin", "plays"}
    away = mu.TeamLine(values={k: 10.0 for k in stats} | {"third_down": .55, "points_for": 37.7},
                       ranks={k: 5 for k in stats} | {"points_for": 1}, games=3)
    home = mu.TeamLine(values={k: 12.0 for k in stats} | {"third_down_allowed": .40, "points_against": 14.0},
                       ranks={k: 60 for k in stats} | {"points_against": 25}, games=3)
    card.matchup = mu.Matchup(away=away, home=home, teams=138, universe="FBS teams", through="20 September")
    page = ts._page(card)
    panel = re.search(r'<details class="panel"[^>]*>\s*<summary><span class="panel-title">Matchup</span>.*?</details>',
                      page, re.S).group(0)
    assert f"{card.away.short} offense" in panel and f"{card.home.short} defense" in panel
    assert f"{card.home.short} offense" in panel and "Situational" in panel
    assert "37.7" in panel and ">1st<" in panel and "55%" in panel and "14.0" in panel
    assert panel.count('class="mu-row"') == 2 * len(mu.PAIRS) + 2       # no penalty row without penalty figures
    assert "through 20 September" in panel and "138 FBS teams" in panel
    assert "sack yardage as rushing" in panel
    text = re.sub(r"<[^>]+>", " ", panel).lower()
    assert not any(re.search(rf"\b{w}\b", text) for w in ts.FORBIDDEN if w not in ("unit", "units"))
    card.matchup = None
    assert "panel-title\">Matchup<" not in ts._page(card)
