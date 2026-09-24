"""College DFS, step 1: ESPN box scores, DraftKings' college scoring, and its check."""

from __future__ import annotations

import pandas as pd
import pytest

from atlas.dfs import cfb
from atlas.sources import espn_cfb


def _athlete(pid, name, stats):
    return {"athlete": {"id": pid, "displayName": name}, "stats": stats}


SUMMARY = {
    "header": {"id": "401", "competitions": [{"competitors": [
        {"team": {"abbreviation": "OSU"}, "homeAway": "home"},
        {"team": {"abbreviation": "GRAM"}, "homeAway": "away"}]}]},
    "boxscore": {"players": [
        {"team": {"abbreviation": "OSU"}, "statistics": [
            {"name": "passing", "labels": ["C/ATT", "YDS", "AVG", "TD", "INT", "QBR"],
             "athletes": [_athlete("1", "Julian Sayin", ["18/19", "306", "16.1", "4", "1", "--"])]},
            {"name": "rushing", "labels": ["CAR", "YDS", "AVG", "TD", "LONG"],
             "athletes": [_athlete("1", "Julian Sayin", ["3", "-7", "-2.3", "0", "4"]),
                          _athlete("2", "CJ Donaldson", ["14", "102", "7.3", "1", "30"])]},
            {"name": "receiving", "labels": ["REC", "YDS", "AVG", "TD", "LONG"],
             "athletes": [_athlete("3", "Jeremiah Smith", ["5", "119", "23.8", "2", "87"])]},
            {"name": "fumbles", "labels": ["FUM", "LOST", "REC"],
             "athletes": [_athlete("2", "CJ Donaldson", ["1", "1", "0"])]},
            {"name": "kicking", "labels": ["FG", "PCT", "LONG", "XP", "PTS"],
             "athletes": [_athlete("4", "Jayden Fielding", ["2/3", "66.7", "52", "6/6", "14"])]},
        ]},
    ]},
    "scoringPlays": [
        {"text": "Jayden Fielding 52 Yd Field Goal"},
        {"text": "Jayden Fielding 38 Yd Field Goal  "},
        {"text": "Jeremiah Smith 9 Yd pass from Julian Sayin (Julian Sayin Pass to Jeremiah Smith for Two-Point Conversion)"},
        {"text": "CJ Donaldson 2 Yd Run (Two-Point Run Conversion Failed)"},
    ],
}


def test_box_score_parses_every_line_and_the_scoring_plays():
    box = espn_cfb.parse(SUMMARY, 2025, 2, "regular").set_index("name")
    assert box.loc["Julian Sayin", ["pass_cmp", "pass_att", "pass_yds", "pass_td", "pass_int", "rush_yds"]].tolist() \
        == [18, 19, 306, 4, 1, -7]
    assert box.loc["CJ Donaldson", ["rush_car", "rush_yds", "rush_td", "fum_lost", "two_pt"]].tolist() == [14, 102, 1, 1, 0]
    assert box.loc["Jeremiah Smith", ["rec", "rec_yds", "rec_td", "two_pt"]].tolist() == [5, 119, 2, 1]
    assert box.loc["Julian Sayin", "two_pt"] == 1                       # the passer is credited too
    assert box.loc["Jayden Fielding", ["fg_made", "fg_att", "xp_made", "fg_0_39", "fg_40_49", "fg_50"]].tolist() \
        == [2, 3, 6, 1, 0, 1]
    assert set(box["team"]) == {"OSU"} and set(box["opponent"]) == {"GRAM"} and set(box["home"]) == {1}


def test_college_scoring_follows_draftkings():
    box = espn_cfb.parse(SUMMARY, 2025, 2, "regular")
    pts = dict(zip(box["name"], cfb.points(box), strict=True))
    assert pts["Julian Sayin"] == pytest.approx(0.04 * 306 + 16 - 1 + 3 - 0.7 + 2)
    assert pts["CJ Donaldson"] == pytest.approx(10.2 + 6 + 3 - 1)
    assert pts["Jeremiah Smith"] == pytest.approx(5 + 11.9 + 12 + 3 + 2)
    assert pts["Jayden Fielding"] == pytest.approx(3 + 5 + 6)


def test_reconcile_maps_team_codes_and_compares_averages():
    box = pd.concat([espn_cfb.parse(SUMMARY, 2026, w, "regular") for w in (1, 2)], ignore_index=True)
    pools = [{"draftables": [
        {"playerId": 1, "displayName": "Julian Sayin", "position": "QB", "teamAbbreviation": "OHST",
         "draftStatAttributes": [{"id": 90, "value": f"{float(cfb.points(box).iloc[0]):.1f}"}]},
        {"playerId": 3, "displayName": "Jeremiah Smith", "position": "WR", "teamAbbreviation": "OHST",
         "draftStatAttributes": [{"id": 90, "value": "10.0"}]},             # DraftKings disagrees
        {"playerId": 9, "displayName": "No Games Yet", "position": "WR", "teamAbbreviation": "OHST",
         "draftStatAttributes": [{"id": 90, "value": "-"}]},
    ]}]
    pools[0]["draftables"].append({"playerId": 7, "displayName": "Bench Player", "position": "WR",
                                   "teamAbbreviation": "OHST", "draftStatAttributes": [{"id": 90, "value": "0.0"}]})
    rec = cfb.reconcile(pools, box, 2026).set_index("name")
    assert bool(rec.loc["Bench Player", "agrees"])                      # appeared, scored nothing
    assert rec.loc["Julian Sayin", "espn_team"] == "OSU"                   # DraftKings' OHST is ESPN's OSU
    assert bool(rec.loc["Julian Sayin", "agrees"]) and not bool(rec.loc["Jeremiah Smith", "agrees"])
    assert "No Games Yet" not in rec.index


def test_refresh_is_budgeted_and_never_fetches_a_game_twice(tmp_path):
    calls = []

    def fetch(url):
        calls.append(url)
        if "scoreboard" in url:
            week = int(url.split("week=")[1].split("&")[0])
            kind = int(url.split("seasontype=")[1].split("&")[0])
            if kind == 2 and week in (1, 2):
                return {"events": [{"id": f"{week}0{i}", "season": {"year": 2025},
                                    "competitions": [{"status": {"type": {"completed": True}}}]} for i in range(3)]}
            return {"events": []}
        return {**SUMMARY, "header": {**SUMMARY["header"], "id": url.split("event=")[1]}}

    got = espn_cfb.refresh(tmp_path, budget=4, seasons=[2025], current=2026, pause=0, fetch=fetch)
    assert got["fetched"] == 4
    assert espn_cfb.load(tmp_path)["event"].nunique() == 4
    summaries = [u for u in calls if "summary" in u]
    espn_cfb.refresh(tmp_path, budget=10, seasons=[2025], current=2026, pause=0, fetch=fetch)
    again = [u for u in calls if "summary" in u][len(summaries):]
    assert len(again) == 2                                              # only the two it did not have
    assert espn_cfb.load(tmp_path)["event"].nunique() == 6


def test_a_game_without_a_stat_still_counts_in_draftkings_average():
    one = espn_cfb.parse(SUMMARY, 2026, 1, "regular")
    other = one[one["name"] != "Jeremiah Smith"].assign(week=2, event="402")   # his team played; he had no line
    box = pd.concat([one, other], ignore_index=True)
    smith = float(cfb.points(one.set_index("name").loc[["Jeremiah Smith"]].reset_index()).iloc[0])
    pools = [{"draftStats": [{"id": 174, "abbr": "FPPG"}], "draftables": [
        {"playerId": 3, "displayName": "Jeremiah Smith", "position": "WR", "teamAbbreviation": "OSU",
         "draftStatAttributes": [{"id": 174, "value": f"{smith / 2:.1f}"}]}]}]      # college's id for FPPG
    rec = cfb.reconcile(pools, box, 2026).set_index("name")
    assert rec.loc["Jeremiah Smith", "games"] == 1 and rec.loc["Jeremiah Smith", "team_games"] == 2
    assert bool(rec.loc["Jeremiah Smith", "agrees"]) and not bool(rec.loc["Jeremiah Smith", "strict"])
