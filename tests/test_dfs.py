"""DFS step 1: DraftKings scoring, the player-game table's trends, archive matching."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from atlas.dfs import players, scoring


def test_offense_scoring_follows_draftkings_classic():
    rows = pd.DataFrame([
        # a quarterback: 310 yards and a bonus, 2 TDs, an interception, 20 rushing yards, a lost sack fumble
        {"passing_yards": 310, "passing_tds": 2, "passing_interceptions": 1, "rushing_yards": 20, "fumbles_lost_total": 1},
        # a receiver: 8 catches, 104 yards and a bonus, a TD, a two-point catch
        {"receptions": 8, "receiving_yards": 104, "receiving_tds": 1, "receiving_2pt_conversions": 1},
        # a returner: a punt-return TD and a fumble lost on a kickoff return
        {"special_teams_tds": 1, "fumbles_lost_total": 1},
    ])
    assert list(scoring.offense_points(rows)) == pytest.approx([
        0.04 * 310 + 3 + 8 - 1 + 2.0 - 1,
        8 + 10.4 + 3 + 6 + 2,
        6 - 1,
    ])


def test_points_allowed_bands_have_draftkings_edges():
    pa = pd.Series([0, 1, 6, 7, 13, 14, 20, 21, 27, 28, 34, 35])
    assert list(scoring.points_allowed_score(pa)) == [10, 7, 7, 4, 4, 1, 1, 0, 0, -1, -1, -4]


def _play(**kw):
    base = {"game_id": "g", "season": 2020, "week": 1, "season_type": "REG", "home_team": "BUF", "away_team": "MIA",
            "total_home_score": 0, "total_away_score": 0, "posteam": "MIA", "defteam": "BUF", "play_type": "pass",
            "sack": 0, "interception": 0, "fumble_lost": 0, "touchdown": 0, "return_touchdown": 0, "safety": 0,
            "punt_blocked": 0, "field_goal_result": None, "extra_point_result": None, "defensive_two_point_conv": 0,
            "defensive_extra_point_conv": 0, "td_team": None, "fumble_recovery_1_team": None}
    return {**base, **kw}


def test_defense_events_and_the_points_it_allowed():
    pbp = pd.DataFrame([
        _play(sack=1),                                                              # BUF sack
        _play(interception=1, touchdown=1, return_touchdown=1, td_team="BUF"),      # BUF pick-six on MIA's pass
        _play(fumble_lost=1, fumble_recovery_1_team="BUF"),                          # BUF recovery
        _play(posteam="BUF", defteam="MIA", play_type="kickoff", touchdown=1, return_touchdown=1, td_team="BUF"),
        _play(posteam="MIA", defteam="BUF", play_type="extra_point", extra_point_result="blocked"),
        # MIA scores against BUF's offense twice: a pick-six (not BUF's defense's to allow) and a safety
        _play(posteam="BUF", defteam="MIA", interception=1, touchdown=1, return_touchdown=1, td_team="MIA"),
        _play(posteam="BUF", defteam="MIA", play_type="run", safety=1),
        _play(total_home_score=21, total_away_score=15),
    ])
    ev = scoring.dst_events(pbp).set_index("team")
    buf = ev.loc["BUF"]
    assert (buf.sacks, buf.interceptions, buf.fumble_recoveries, buf.tds, buf.blocked_kicks) == (1, 1, 1, 2, 1)
    assert buf.opp_score == 15 and buf.offense_conceded_tds == 1 and buf.offense_conceded_safeties == 1
    assert scoring.points_allowed(ev).loc["BUF"] == 15 - 6 - 2
    # sack, interception, recovery, two touchdowns, a block; 7 allowed is the 7-13 band, worth 4
    assert scoring.dst_points(ev).loc["BUF"] == 1 + 2 + 2 + 12 + 2 + 4


def test_defense_points_band_for_the_example():
    ev = pd.DataFrame([{"sacks": 1, "interceptions": 1, "fumble_recoveries": 1, "tds": 2, "safeties": 0,
                        "blocked_kicks": 1, "conversion_returns": 0, "opp_score": 15, "offense_conceded_tds": 1,
                        "offense_conceded_safeties": 1}])
    # 1 + 2 + 2 + 12 + 2, and 7 allowed is worth 4
    assert scoring.dst_points(ev).iloc[0] == 1 + 2 + 2 + 12 + 2 + 4


def test_trends_use_only_earlier_games():
    g = pd.DataFrame({"player_id": ["a"] * 3 + ["b"], "season": [2020, 2020, 2021, 2020], "week": [1, 2, 1, 1],
                      "team": "BUF", "dk_points": [10.0, 20.0, 30.0, 5.0]})
    t = players.with_trends(g).set_index(["player_id", "season", "week"]).sort_index()
    assert np.isnan(t.loc[("a", 2020, 1), "dk_points_trend"]) and np.isnan(t.loc[("b", 2020, 1), "dk_points_trend"])
    assert t.loc[("a", 2020, 2), "dk_points_trend"] == 10.0                        # its own 20 is not in it
    assert 10.0 < t.loc[("a", 2021, 1), "dk_points_trend"] < 20.0                  # carried across the season
    assert list(t.loc["a", "games_before"]) == [0, 1, 2]


def test_archive_matching_by_name_position_and_points():
    games = pd.DataFrame([
        {"season": 2021, "week": 4, "season_type": "REG", "team": "NYJ", "player_id": "rb", "name": "Michael Carter",
         "position": "RB", "dk_points": 10.4},
        {"season": 2021, "week": 4, "season_type": "REG", "team": "NYJ", "player_id": "wr", "name": "Robbie Chosen",
         "position": "WR", "dk_points": 12.3},
    ])
    arch = pd.DataFrame([
        {"season": 2021, "week": 4, "name": "Carter, Michael", "position": "RB", "team": "nyj", "dk_points": 10.4},
        {"season": 2021, "week": 4, "name": "Anderson, Robby", "position": "WR", "team": "nyj", "dk_points": 12.3},
        {"season": 2021, "week": 4, "name": "Nobody, Practice", "position": "WR", "team": "nyj", "dk_points": 0.0},
    ])
    arch["team_n"] = arch["team"].str.upper()
    arch["key"] = arch["name"].map(lambda n: players.norm_name(" ".join(reversed(n.split(", ")))))
    arch["last"] = arch["name"].map(lambda n: players.norm_name(n.split(",")[0]))
    m = players.match_archive(arch, games).set_index("name")
    assert m.loc["Carter, Michael", "player_id"] == "rb" and m.loc["Carter, Michael", "stage"] == "name"
    assert m.loc["Anderson, Robby", "player_id"] == "wr" and m.loc["Anderson, Robby", "stage"] == "points"
    assert m.loc["Nobody, Practice", "stage"] == "none"


def test_names_normalize_across_sources():
    assert players.norm_name("C.J. Uzomah") == players.norm_name("CJ Uzomah") == "cj uzomah"
    assert players.norm_name("Michael Carter II") == "michael carter"
    assert players.norm_name("Ja'Marr Chase") == "jamarr chase" and players.norm_name(None) == ""


def test_crps_of_a_normal_behaves():
    from atlas.dfs import benchmarks as bm

    y = np.array([10.0, 20.0])
    assert bm.crps_normal(np.array([10.0, 10.0]), np.array([1e-9, 1e-9]), y) == pytest.approx([0.0, 10.0], abs=1e-5)
    wide, narrow = bm.crps_normal(np.array([10.0]), np.array([8.0]), np.array([10.0])), \
        bm.crps_normal(np.array([10.0]), np.array([2.0]), np.array([10.0]))
    assert narrow < wide                                         # a sharp forecast that is right scores better


def _league(seasons=(2014, 2015, 2016), weeks=8, seed=3):
    """Players whose points are exactly 2 + 0.003 x salary plus noise, and
    whose form persists: both benchmarks have something to find."""
    rng = np.random.default_rng(seed)
    rows = []
    for s in seasons:
        for team in ("A", "B", "C"):
            for pos, n in (("QB", 2), ("RB", 3), ("WR", 4), ("TE", 2), ("DST", 1)):
                for i in range(n):
                    talent = rng.normal(0, 4)
                    for w in range(1, weeks + 1):
                        salary = 4000 + 1000 * (n - i) + 200 * talent
                        rows.append({"season": s, "week": w, "team": team, "player_id": f"{team}{pos}{i}{s}",
                                     "position": pos, "dk_salary": salary,
                                     "target": 2 + 0.003 * salary + talent + rng.normal(0, 3)})
    f = pd.DataFrame(rows).sort_values(["player_id", "season", "week"])
    by = f.groupby("player_id")
    f["games_before"] = by.cumcount()
    f["dk_points_trend"] = by["target"].transform(lambda s: s.shift(1).ewm(halflife=4).mean())
    return f.reset_index(drop=True)


def test_benchmarks_are_walk_forward_and_find_what_is_there():
    from atlas.dfs import benchmarks as bm

    f = _league()
    scored = bm.walk_forward(f, first_test=2015)
    assert set(scored["season"]) == {2015, 2016}
    # A season's fit never sees that season: poison 2016's targets and 2015's predictions do not move.
    poisoned = f.copy()
    poisoned.loc[poisoned["season"] == 2016, "target"] += 1000
    again = bm.walk_forward(poisoned, first_test=2015)
    assert np.allclose(scored.loc[scored["season"] == 2015, "salary"], again.loc[again["season"] == 2015, "salary"])
    fit = bm.fit(f[f["season"] < 2016])
    assert all(slope > 0 for _, slope in fit.salary.values())          # pricier players score more
    table = bm.summarise(scored, ("baseline", "salary"), ["position"])
    assert (table["rank corr"].dropna() > 0).all() and (table["crps"] > 0).all()   # 3 defenses a week: no rank


def test_regulars_are_each_teams_top_players_by_salary():
    from atlas.dfs import benchmarks as bm

    f = bm.predict(_league(seasons=(2014, 2015)), bm.fit(_league(seasons=(2014,))))
    r = bm.regulars(f[f["season"] == 2015])
    per_team = r.groupby(["week", "team", "position"]).size().unstack()
    assert (per_team["QB"] == 1).all() and (per_team["RB"] == 2).all() and (per_team["WR"] == 3).all()
    assert (per_team["TE"] == 1).all() and (per_team["DST"] == 1).all()
    top = f[(f["season"] == 2015) & (f["position"] == "QB")].groupby(["week", "team"])["dk_salary"].max()
    chosen = r[r["position"] == "QB"].set_index(["week", "team"])["dk_salary"]
    assert (chosen.sort_index() == top.sort_index()).all()
