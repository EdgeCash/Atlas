"""Atlas's NHL player projections (docs/MODEL_PLAN_NHL.md, step 8): walk-forward, nothing from the game itself
or after it.
A synthetic league of four teams."""

from __future__ import annotations

import math
from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pytest

from atlas.models import nhl_props

KEY = "correct horse battery staple"
TEAMS = ("AAA", "BBB", "CCC", "DDD")
#: Each team's skaters: (id, name, position, shots per 60).
FIRST = ("Alpha", "Bravo", "Charlie", "Delta")
ROSTER = {t: [(100 * i + j, f"{FIRST[j]} {t.title()}", "C" if j < 2 else "D", (18.0 if j == 0 else 7.0) if j < 2 else 4.0)
              for j in range(4)] for i, t in enumerate(TEAMS)}


def _league(seasons=range(2018, 2023), games=24, seed=3) -> dict:
    rng = np.random.default_rng(seed)
    sk, tg, gg = [], [], []
    pairs = [(a, b) for a in TEAMS for b in TEAMS if a != b]
    for season in seasons:
        day = pd.Timestamp(f"{season}-10-10")
        for n in range(games):
            for k, (home, away) in enumerate(pairs[n % len(pairs):] + pairs[:n % len(pairs)]):
                if k >= 2:
                    break
                gid = season * 1_000_000 + 20_000 + n * 2 + k + 1
                date = (day + pd.Timedelta(days=2 * n)).strftime("%Y-%m-%d")
                shots = {}
                for team, opp, hr in ((home, away, "H"), (away, home, "R")):
                    total = 0
                    for pid, name, pos, rate in ROSTER[team]:
                        toi = 1100.0 + rng.normal(0, 40)
                        s = int(rng.poisson(rate * toi / 3600.0))
                        g = int(rng.binomial(s, 0.1))
                        a = int(rng.poisson(0.3))
                        sk.append({"game_id": gid, "player_id": pid, "name": name, "position": pos, "team": team,
                                   "opponent": opp, "home_road": hr, "date": date, "goals": g, "assists": a,
                                   "points": g + a, "shots": s, "toi": toi, "hits": int(rng.poisson(1.2)),
                                   "blocks": int(rng.poisson(0.8))})
                        total += s
                    shots[team] = total
                for team, opp, hr in ((home, away, "H"), (away, home, "R")):
                    ga = int(rng.binomial(shots[opp], 0.1))
                    gf = int(rng.binomial(shots[team], 0.1))
                    tg.append({"game_id": gid, "team": team, "opponent": opp, "season": season,
                               "kickoff": f"{date}T23:00:00Z", "sog_5v5": shots[team], "soga_5v5": shots[opp],
                               "corsi_5v5": shots[team] * 2, "goals_5v5": gf, "goalsa_5v5": ga})
                    gg.append({"game_id": gid, "player_id": 900 + TEAMS.index(team), "name": f"Goalie {team}",
                               "team": team, "opponent": opp, "home_road": hr, "date": date, "started": True,
                               "shots_against": shots[opp], "saves": shots[opp] - ga, "season": season})
    return {"skater_games": pd.DataFrame(sk), "team_games": pd.DataFrame(tg), "goalie_games": pd.DataFrame(gg)}


@pytest.fixture(scope="module")
def league():
    return _league()


def test_the_projection_ranks_the_shooters_and_scores_against_the_baseline(league):
    sk, gk, layers = nhl_props.walk(league, nhl_props.Spec(), [2022])
    by = sk[sk["n_season"] >= 5].groupby("name")["mu_shots"].mean()
    assert by["Alpha Aaa"] > 2 * by["Bravo Aaa"] > by["Charlie Aaa"]            # 18, 7 and 4 an hour
    assert gk["mu_saves"].between(4, 20).all()                                        # about ten shots a game
    table = nhl_props.score(sk, gk, layers)
    assert {"brier_atlas", "brier_naive", "logloss_atlas", "mean_atlas", "observed"} <= set(table.columns)
    assert set(table["stat"]) == set(nhl_props.LINES)
    assert "ratio" in layers[2022]["saves"] and layers[2022]["shots"]["dispersion"] >= 1.0


def test_nothing_from_the_game_or_after_it_reaches_its_projection(league):
    base, _, _ = nhl_props.walk(league, nhl_props.Spec(), [2022])
    changed = {k: v.copy() for k, v in league.items()}
    s = changed["skater_games"]
    last = s["game_id"].max()
    s.loc[s["game_id"] == last, "shots"] = 40                                        # the season's last game
    after, _, _ = nhl_props.walk(changed, nhl_props.Spec(), [2022])
    key = ["game_id", "player_id"]
    a = base.set_index(key)["mu_shots"]
    b = after.set_index(key)["mu_shots"]
    assert np.allclose(a.loc[a.index.get_level_values(0) <= last], b.loc[b.index.get_level_values(0) <= last])


def test_a_count_and_the_empirical_shape_give_probabilities_that_add_up():
    for ratio in (None, list(np.linspace(0.3, 1.6, 101))):
        over = nhl_props.prob(3.0, 3.0, "over", 1.1, ratio)
        under = nhl_props.prob(3.0, 3.0, "under", 1.1, ratio)
        assert 0 < over < 1 and 0 < under < 1 and over + under < 1.0                  # a tie on a whole line
        half = nhl_props.prob(3.0, 2.5, "over", 1.1, ratio) + nhl_props.prob(3.0, 2.5, "under", 1.1, ratio)
        assert half == pytest.approx(1.0)
    assert nhl_props.prob(0.7, 0.5, "over", 1.0) == pytest.approx(1 - math.exp(-0.7))


def test_the_snapshot_projects_a_player_against_an_opponent(league):
    now = datetime(2023, 10, 1, tzinfo=UTC)
    snap = nhl_props.snapshot(league, now)
    assert snap["season"] == 2023 and len(snap["skaters"]) == 16 and len(snap["goalies"]) == 4
    star = snap["skaters"].set_index("name").loc["Alpha Aaa"]
    depth = snap["skaters"].set_index("name").loc["Bravo Aaa"]
    home = nhl_props.expect(snap, star, "AAA", "BBB", "AAA", "shots")
    assert home > nhl_props.expect(snap, depth, "AAA", "BBB", "AAA", "shots") > 0
    assert math.isnan(nhl_props.expect(snap, star, "AAA", "ZZZ", "AAA", "shots"))     # a team it does not know
    goalie = snap["goalies"].set_index("name").loc["Goalie AAA"]
    assert 4 < nhl_props.expect(snap, None, "AAA", "BBB", "AAA", "saves", goalie=goalie) < 20




def test_the_snapshot_is_saved_read_back_and_prices_a_prop_on_polymarket_us(league, tmp_path):
    from atlas.polymarket import match, props, source
    from atlas.testing import polymarket_us as us

    now = datetime(2023, 10, 1, tzinfo=UTC)
    snap = nhl_props.snapshot(league, now)
    where = tmp_path / "nhl_props_state.json"
    nhl_props.save_state(snap, where)
    back = nhl_props.load_state(where)
    assert back["season"] == 2023 and len(back["skaters"]) == 16 and back["layer"] == snap["layer"]
    assert back["level"] == snap["level"] and len(back["teams"]) == len(snap["teams"])
    assert nhl_props.load_state(tmp_path / "missing.json") is None
    assert nhl_props.load_spec(tmp_path) == nhl_props.Spec()

    aaa, bbb = us.team(1, "Aaa Alphas", "Aaa"), us.team(2, "Bbb Bravos", "Bbb")
    start = "2023-10-02T23:00:00Z"
    ev = us.event("5001", "nhl-bbb-aaa-2023-10-02", bbb, aaa, [
        us.prop(1, "hockey_player_points", "Alpha Aaa", 1, 0.55, 0.57, team=aaa, start=start),
        us.prop(2, "hockey_player_goals", "Alpha Aaa", 1, 0.25, 0.27, team=aaa, start=start),
        us.prop(3, "hockey_player_assists", "Nobody", 1, 0.40, 0.42, team=bbb, start=start)], start=start)
    q = props.prop_quotes([ev], source.LEAGUES["nhl"], now)
    assert len(q) == 6 and set(q["line"]) == {0.5} and set(q["stat"]) == {"points", "goals", "assists"}
    assert q.set_index(["player", "stat", "side"]).loc[("Alpha Aaa", "points", "under"), "ask"] == pytest.approx(0.45)
    pairs = pd.DataFrame([{"event_id": "5001", "game_id": "901", "sport": "nhl", "kickoff": start, "season": 2023,
                           "week": 1, "home_team": "Aaa Alphas", "away_team": "Bbb Bravos",
                           "label": "Bbb Bravos @ Aaa Alphas", "home_team_id": None, "away_team_id": None}])
    e = props.expectations(match.attach(q, pairs), {"nba": None, "nhl": back}, codes={"901": ("BBB", "AAA")})
    by = e.set_index(["player", "stat", "side"])
    assert by.loc[("Alpha Aaa", "points", "over"), "atlas_mean"] > by.loc[("Alpha Aaa", "goals", "over"), "atlas_mean"] > 0
    assert by.loc[("Alpha Aaa", "points", "over"), "p_atlas"] + by.loc[("Alpha Aaa", "points", "under"), "p_atlas"] \
        == pytest.approx(1.0)
    assert math.isnan(by.loc[("Nobody", "assists", "over"), "p_atlas"])
    priced = props.price(e, None)
    assert (priced["share"] == 0.0).all() and (priced["market"].str.startswith("player:")).all()
    # Graded from the skater games, whose game ids are the league's, through the projection that maps them.
    sk = league["skater_games"]
    gid = int(sk["game_id"].iloc[0])
    proj = pd.DataFrame([{"game_id": "901", "nhl_game_id": gid, "away_team": "BBB", "home_team": "AAA"}])
    results = props.results_frame("nhl", sk, proj)
    assert set(results["sport"]) == {"nhl"} and (results["game_id"] == "901").all() and "alpha aaa" in set(results["player_key"])
    value, played = props._value(results, "nhl", "901", "Alpha Aaa", "points")
    assert played and value >= 0
    assert props._value(results, "nhl", "901", "Nobody", "points") == (pytest.approx(float("nan"), nan_ok=True), False)


def test_the_injury_report_sets_the_chance_of_dressing(league):
    from atlas.sources.nba_availability import COLUMNS

    snap = nhl_props.snapshot(league, datetime(2023, 10, 1, tzinfo=UTC))
    report = pd.DataFrame([
        {"player": "Alpha Aaa", "team_abbr": "AAA", "status": "Out"},
        {"player": "Bravo Aaa", "team_abbr": "AAA", "status": "Day-To-Day"},
        {"player": "Charlie Aaa", "team_abbr": "AAA", "status": "Injured Reserve"},
        {"player": "Alpha Bbb", "team_abbr": "CCC", "status": "Out"},                   # not his team
        {"player": "Delta Bbb", "team_abbr": "BBB", "status": "Probable"},              # a status not known
    ], columns=COLUMNS)
    adj = nhl_props.adjust(snap, report)
    p = adj["skaters"].set_index("name")
    assert p.loc["Alpha Aaa", "p_play"] == 0.03 and p.loc["Alpha Aaa", "status"] == "out"
    assert p.loc["Bravo Aaa", "p_play"] == 0.5 and p.loc["Bravo Aaa", "status"] == "day-to-day"
    assert p.loc["Charlie Aaa", "p_play"] == 0.0 and p.loc["Charlie Aaa", "status"] == "injured reserve"
    assert p.loc["Alpha Bbb", "p_play"] == 1.0 and p.loc["Delta Bbb", "p_play"] == 1.0
    assert "p_play" not in snap["skaters"] and adj["goalies"] is snap["goalies"]
    assert (nhl_props.adjust(snap, None)["skaters"]["p_play"] == 1.0).all()
    assert (nhl_props.adjust(snap, pd.DataFrame(columns=COLUMNS))["skaters"]["p_play"] == 1.0).all()


def test_espn_abbreviations_are_read_to_the_nhl_codes(league):
    from atlas.sources.nba_availability import COLUMNS
    from atlas.sources.nhl import ESPN_CODES
    from atlas.staging.nhl.games import TEAMS

    assert all(code in TEAMS or code == "PHX" for code in ESPN_CODES.values())
    snap = nhl_props.snapshot(league, datetime(2023, 10, 1, tzinfo=UTC))
    snap["skaters"].loc[snap["skaters"]["name"] == "Alpha Aaa", "team"] = "TBL"
    report = pd.DataFrame([{"player": "Alpha Aaa", "team_abbr": "TB", "status": "Out"}], columns=COLUMNS)
    assert nhl_props.adjust(snap, report)["skaters"].set_index("name").loc["Alpha Aaa", "p_play"] == 0.03


def test_a_listed_skater_is_priced_with_his_chance_of_dressing(league):
    from atlas.polymarket import match, props, source
    from atlas.sources.nba_availability import COLUMNS, parse
    from atlas.testing import polymarket_us as us

    now = datetime(2023, 10, 1, tzinfo=UTC)
    snap = nhl_props.snapshot(league, now)
    aaa, bbb = us.team(1, "Aaa Alphas", "Aaa"), us.team(2, "Bbb Bravos", "Bbb")
    start = "2023-10-02T23:00:00Z"
    ev = us.event("5001", "nhl-bbb-aaa-2023-10-02", bbb, aaa, [
        us.prop(1, "hockey_player_points", "Alpha Aaa", 1, 0.55, 0.57, team=aaa, start=start)], start=start)
    pairs = pd.DataFrame([{"event_id": "5001", "game_id": "901", "sport": "nhl", "kickoff": start, "season": 2023,
                           "week": 1, "home_team": "Aaa Alphas", "away_team": "Bbb Bravos",
                           "label": "Bbb Bravos @ Aaa Alphas", "home_team_id": None, "away_team_id": None}])
    q = match.attach(props.prop_quotes([ev], source.LEAGUES["nhl"], now), pairs)
    snaps = {"nba": None, "nhl": snap, "nfl": None}
    plain = props.expectations(q, snaps, codes={"901": ("BBB", "AAA")}).set_index("side")
    # The feed's shape: a team with one listed skater, parsed as the capture would.
    payload = {"injuries": [{"id": "1", "displayName": "Aaa Alphas", "injuries": [
        {"status": "Day-To-Day", "date": "2023-10-01T12:00Z", "shortComment": "lower body",
         "details": {"fantasyStatus": {"abbreviation": "DTD"}, "type": "Lower Body", "returnDate": "2023-10-02"},
         "athlete": {"id": "100", "displayName": "Alpha Aaa", "position": {"abbreviation": "C"},
                     "team": {"abbreviation": "AAA"}}}]}]}
    report = parse(payload, now)
    assert list(report.columns) == COLUMNS and report.loc[0, "team_abbr"] == "AAA" and report.loc[0, "status"] == "Day-To-Day"
    listed = props.expectations(q, snaps, codes={"901": ("BBB", "AAA")}, nhl_availability=report).set_index("side")
    assert listed.loc["over", "status"] == "day-to-day" and listed.loc["over", "atlas_mean"] == plain.loc["over", "atlas_mean"]
    assert listed.loc["over", "p_atlas"] == pytest.approx(0.5 * plain.loc["over", "p_atlas"] + 0.5 * 0.56)
    assert listed.loc["under", "p_atlas"] == pytest.approx(0.5 * plain.loc["under", "p_atlas"] + 0.5 * 0.44)
