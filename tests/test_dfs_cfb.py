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


# ---------------------------------------------------------------------------
# Step 2: the player-game table and the baseline
# ---------------------------------------------------------------------------


def _box_rows(season, week, event, team, rows):
    base = {c: 0.0 for c in espn_cfb.STAT_COLUMNS}
    return [{"season": season, "week": week, "season_type": "regular", "event": event, "team": team,
             "opponent": "X", "home": 1, **base, **r} for r in rows]


def test_positions_come_from_what_a_player_did_and_defenders_are_left_out():
    from atlas.dfs import cfb_players as cp

    rows = []
    for w in range(1, 7):
        rows += _box_rows(2025, w, f"e{w}", "OSU", [
            {"player_id": "qb", "name": "Q", "pass_att": 30, "pass_yds": 250, "rush_car": 6},
            {"player_id": "rb", "name": "R", "rush_car": 18, "rush_yds": 90, "rec": 2},
            {"player_id": "te", "name": "T", "rec": 4, "rec_yds": 40},
            {"player_id": "k", "name": "K", "fg_att": 2, "fg_made": 2, "fg_0_39": 2, "xp_att": 3, "xp_made": 3},
            {"player_id": "lb", "name": "L"},                                  # a tackler: no DraftKings line
        ])
    rows += _box_rows(2025, 1, "e1", "FCS", [{"player_id": "f", "name": "F", "rush_car": 5}])
    g = cp.games(pd.DataFrame(rows))
    pos = g.drop_duplicates("player_id").set_index("player_id")["position"].to_dict()
    assert pos == {"qb": "QB", "rb": "RB", "te": "WR", "k": "K", "f": "RB"}
    assert "lb" not in set(g["player_id"])
    assert bool(g.loc[g["team"] == "OSU", "fbs"].all()) and not bool(g.loc[g["team"] == "FCS", "fbs"].any())
    shares = g[(g["event"] == "e1") & (g["team"] == "OSU")].set_index("player_id")
    assert shares.loc["rb", "rush_share"] == pytest.approx(18 / 24)


def test_college_trends_and_baseline_are_walk_forward():
    from atlas.dfs import cfb_players as cp

    rng = __import__("numpy").random.default_rng(3)
    rows = []
    for s in range(2014, 2018):
        for w in range(1, 11):
            for t in range(8):
                team = f"T{t}"
                rows += _box_rows(s, w, f"{s}{w}{t}", team, [
                    {"player_id": f"{team}qb", "name": "Q", "pass_att": 30, "pass_yds": float(rng.normal(250, 60))},
                    {"player_id": f"{team}wr", "name": "W", "rec": float(rng.integers(1, 9)), "rec_yds": 60.0},
                ])
    table = cp.with_trends(cp.games(pd.DataFrame(rows)))
    first = table.sort_values("order").groupby("player_id").head(1)
    assert first["dk_points_trend"].isna().all()                         # no history before the first game
    f = cp.frame(table)
    scored = cp.walk_forward(f, first_test=2016)
    poisoned = f.copy()
    poisoned.loc[poisoned["season"] == 2017, "target"] += 100
    again = cp.walk_forward(poisoned, first_test=2016)
    assert (scored.loc[scored["season"] == 2016, "baseline"].to_numpy()
            == again.loc[again["season"] == 2016, "baseline"].to_numpy()).all()
    regs = cp.regulars(scored)
    assert (regs.groupby(["event", "team", "position"]).size() == 1).all()   # one QB and one WR here


def test_one_bad_season_does_not_stop_the_rest(tmp_path):
    def fetch(url):
        if "scoreboard" in url and "dates=2024" in url:
            raise RuntimeError("down")
        if "scoreboard" in url:
            week = int(url.split("week=")[1].split("&")[0])
            if "seasontype=2" in url and week == 1:
                return {"events": [{"season": {"year": 2023}},                         # no id: skipped
                                   {"id": "9001", "season": {"year": 2023},
                                    "competitions": [{"status": {"type": {"completed": True}}}]}]}
            return {"events": []}
        return {**SUMMARY, "header": {**SUMMARY["header"], "id": "9001"}}

    got = espn_cfb.refresh(tmp_path, budget=10, seasons=[2024, 2023], current=2026, pause=0, fetch=fetch)
    assert got["fetched"] == 1 and set(espn_cfb.load(tmp_path)["season"]) == {2023}


# ---------------------------------------------------------------------------
# Step 3: the model
# ---------------------------------------------------------------------------


def test_odds_codes_are_learned_from_games_where_one_side_agrees():
    from atlas.dfs import cfb_model as cm

    odds = pd.DataFrame([{"game_id": 1, "abbr": "TCU"}, {"game_id": 1, "abbr": "UTH"},
                         {"game_id": 2, "abbr": "UTH"}, {"game_id": 2, "abbr": "BYU"}])
    box = pd.DataFrame([{"game_id": 1, "team": "TCU"}, {"game_id": 1, "team": "UTAH"},
                        {"game_id": 2, "team": "UTAH"}, {"game_id": 2, "team": "BYU"}])
    assert cm.abbr_map(odds, box) == {"TCU": "TCU", "UTH": "UTAH", "BYU": "BYU"}


def test_a_teams_implied_points_are_half_the_total_less_half_its_spread(tmp_path):
    from atlas.dfs import cfb_model as cm

    (tmp_path / "odds").mkdir()
    pd.DataFrame([
        {"game_id": 7.0, "market_type": "spread", "abbr": "OSU", "lines": -7.0},
        {"game_id": 7.0, "market_type": "spread", "abbr": "GRAM", "lines": 7.0},
        {"game_id": 7.0, "market_type": "total", "abbr": "over", "lines": 51.0},
        {"game_id": 7.0, "market_type": "total", "abbr": "under", "lines": 51.0},
    ]).to_parquet(tmp_path / "odds" / "cfb_line_odds.parquet")
    env = cm.environment(pd.DataFrame({"event": ["7", "7"], "team": ["OSU", "GRAM"]}), raw=tmp_path).set_index("team")
    assert env.loc["OSU", "team_pts"] == pytest.approx(29.0) and env.loc["GRAM", "team_pts"] == pytest.approx(22.0)
    assert env.loc["OSU", "proj_margin"] == pytest.approx(7.0)


def test_college_model_is_walk_forward_and_reads_the_game():
    import numpy as np

    from atlas.dfs import cfb_model as cm
    from atlas.dfs import cfb_players as cp

    rng = np.random.default_rng(8)
    rows, env = [], []
    for s in range(2014, 2019):
        for w in range(1, 11):
            for t in range(10):
                team, ev = f"T{t}", f"{s}{w:02d}{t}"
                pts = float(rng.normal(30, 9))
                env.append({"event": ev, "team": team, "team_pts": pts, "opp_pts": 25.0, "proj_total": pts + 25,
                            "proj_margin": pts - 25})
                for k, pos in enumerate(("QB", "RB", "RB", "WR", "WR", "WR", "K")):
                    stats = {"QB": {"pass_att": 30.0, "pass_yds": 8 * pts + rng.normal(0, 40)},
                             "RB": {"rush_car": 15.0, "rush_yds": 3 * pts + rng.normal(0, 30)},
                             "WR": {"rec": 4.0, "rec_yds": 2 * pts + rng.normal(0, 25)},
                             "K": {"fg_att": 1.0, "xp_att": pts / 7, "xp_made": round(pts / 7), "fg_0_39": 1.0}}[pos]
                    rows += _box_rows(s, w, ev, team, [{"player_id": f"{team}{pos}{k}", "name": f"{pos}{k}", **stats}])
    table = cp.with_trends(cp.games(pd.DataFrame(rows)))
    f = cm.features(table, pd.DataFrame(env))
    out = cm.walk_forward(f, first_test=2017)
    assert out["model"].notna().all() and (out["model_sd"] >= 1).all()
    poisoned = f.copy()
    poisoned.loc[poisoned["season"] == 2018, "target"] += 100
    again = cm.walk_forward(poisoned, first_test=2017)
    a, b = out[out["season"] == 2017], again[again["season"] == 2017]
    assert np.allclose(a["model"].to_numpy(), b["model"].to_numpy())
    qb = out[out["position"] == "QB"]
    assert np.polyfit(qb["team_pts"], qb["model"] - qb["baseline"], 1)[0] > 0.1     # a richer game projects more
