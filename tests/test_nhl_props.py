"""Atlas's NHL player projections (docs/MODEL_PLAN_NHL.md, step 8): walk-forward, nothing from the game itself
or after it; the snapshot the heavy refresh seals; Atlas's probability beside the market's in the pick'em.
A synthetic league of four teams."""

from __future__ import annotations

import math
from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pytest

from atlas.models import nhl_props
from atlas.owner import pickem

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


def test_the_snapshot_seals_opens_and_projects_a_player_against_an_opponent(league, tmp_path):
    now = datetime(2023, 10, 1, tzinfo=UTC)
    snap = nhl_props.snapshot(league, now)
    assert snap["season"] == 2023 and len(snap["skaters"]) == 16 and len(snap["goalies"]) == 4
    where = tmp_path / "state.enc.json"
    nhl_props.seal(snap, KEY, where)
    assert "Alpha Aaa" not in where.read_text()
    back = nhl_props.load(KEY, where)
    star = back["skaters"].set_index("name").loc["Alpha Aaa"]
    depth = back["skaters"].set_index("name").loc["Bravo Aaa"]
    home = nhl_props.expect(back, star, "AAA", "BBB", "AAA", "shots")
    assert home > nhl_props.expect(back, depth, "AAA", "BBB", "AAA", "shots") > 0
    assert math.isnan(nhl_props.expect(back, star, "AAA", "ZZZ", "AAA", "shots"))     # a team it does not know
    goalie = back["goalies"].set_index("name").loc["Goalie AAA"]
    assert 4 < nhl_props.expect(back, None, "AAA", "BBB", "AAA", "saves", goalie=goalie) < 20
    assert nhl_props.load(KEY, tmp_path / "missing.enc.json") is None


def test_the_pickem_shows_atlas_beside_the_fair_value_for_the_player_it_finds(league):
    snap = nhl_props.snapshot(league, datetime(2023, 10, 1, tzinfo=UTC))
    priced = pd.DataFrame([
        {"sport": "nhl", "event_id": 7, "market": "shots", "player": "Alpha Aaa", "team": "AAA", "line": 2.5,
         "side": "over", "p": 0.55, "p_atlas": np.nan},
        {"sport": "nhl", "event_id": 7, "market": "saves", "player": "Goalie BBB", "team": "BBB", "line": 9.5,
         "side": "under", "p": 0.55, "p_atlas": np.nan},
        {"sport": "nhl", "event_id": 7, "market": "shots", "player": "Nobody Known", "team": "AAA", "line": 2.5,
         "side": "over", "p": 0.55, "p_atlas": np.nan},
        {"sport": "nfl", "event_id": 8, "market": "receptions", "player": "Alpha Aaa", "team": "AAA", "line": 3.5,
         "side": "over", "p": 0.55, "p_atlas": np.nan}])
    events = pd.DataFrame({"event_id": [7, 8], "home_abbr": ["AAA", "X"], "visitor_abbr": ["BBB", "Y"]})
    out = pickem.atlas_beside(priced, snap, events)
    assert 0.3 < out.loc[0, "p_atlas"] < 0.95 and 0 < out.loc[1, "p_atlas"] < 1
    assert math.isnan(out.loc[2, "p_atlas"]) and math.isnan(out.loc[3, "p_atlas"])
    assert pickem.atlas_beside(priced, None, events) is priced                        # no snapshot: as it was
