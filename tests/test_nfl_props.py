"""Atlas's NFL player projections (docs/MODEL_PLAN_NFL.md, step 9): the staged player weeks, the walk-forward,
the snapshot, the injury report, and the exchange's props priced off it. A synthetic nflverse tree."""

from __future__ import annotations

import json
import math
import os
from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pytest

from atlas.models import nfl_props
from atlas.staging.nfl import games as nfl_games
from atlas.staging.nfl import players as nfl_stage
from atlas.testing import polymarket_us as us
from atlas.testing.synthetic_nfl import CODES, ROSTER, WEEKS, player_name, write_synthetic_nfl_raw

SEASONS = [2022, 2023, 2024]
KEY = "correct horse battery staple"
SKILL = [r for r in ROSTER if r[1] != "K"]


@pytest.fixture(scope="module")
def tables(tmp_path_factory):
    base = tmp_path_factory.mktemp("nfl_props")
    write_synthetic_nfl_raw(base / "raw", SEASONS)
    old = os.environ.get("ATLAS_OFFLINE")
    os.environ["ATLAS_OFFLINE"] = "1"
    try:
        return nfl_stage.build(base / "raw", SEASONS)
    finally:
        if old is None:
            os.environ.pop("ATLAS_OFFLINE", None)
        else:
            os.environ["ATLAS_OFFLINE"] = old


@pytest.fixture(scope="module")
def snap(tables):
    players, teams = tables
    return nfl_props.snapshot(players, teams, datetime(2024, 11, 1, tzinfo=UTC), nfl_props.Spec())


def _row(snap, name):
    return snap["players"].set_index("player").loc[name]


# ---------------------------------------------------------------------------
# The staging
# ---------------------------------------------------------------------------


def test_player_weeks_follow_the_conventions(tables):
    players, teams = tables
    assert list(players.columns) == nfl_stage.COLUMNS and list(teams.columns) == nfl_stage.TEAM_COLUMNS
    assert set(players["position"]) == {"QB", "RB", "WR", "TE"}                      # the kicker is dropped
    assert players["player_id"].nunique() == len(CODES) * len(SKILL)
    assert set(players["season"]) == set(SEASONS) and players["espn_id"].notna().all()
    assert set(players["team"]) == set(CODES)                                        # OAK is LV throughout
    assert set(players["season_type"]) == {"regular", "postseason"}
    assert (players["touchdowns"] == players["rushing_tds"] + players["receiving_tds"]).all()
    assert (players["touches"] == players["carries"] + players["targets"]).all()
    assert players["played"].all() and set(players["home"]) == {0.0, 1.0}
    assert players["kickoff"].str.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$").all()
    # Each game's players are two teams, one at home; the last week of the last season is still to play.
    per_game = players.groupby("game_id").agg(teams=("team", "nunique"), home=("home", "mean"))
    assert (per_game["teams"] == 2).all() and (per_game["home"] == 0.5).all()
    assert players[players["season"] == SEASONS[-1]]["week"].max() == WEEKS - 1


def test_team_weeks_carry_attempts_allowances_and_the_implied_total(tables):
    players, teams = tables
    qb = players[players["position"] == "QB"].set_index(["game_id", "team"])
    t = teams.set_index(["game_id", "team"])
    assert (t["pass_attempts"] == qb.loc[t.index, "attempts"]).all()
    assert (t["plays"] == t["pass_attempts"] + t["rush_attempts"]).all()
    # What a team allowed is what its opponent recorded.
    first = teams.iloc[0]
    own = players[(players["game_id"] == first["game_id"]) & (players["team"] == first["opponent"])]
    assert first["allow_receiving_yards"] == own["receiving_yards"].sum()
    assert first["allow_passing_tds"] == own["passing_tds"].sum()
    # (total ± spread) / 2, the spread the home team's.
    both = t.loc[first["game_id"]]
    assert both["implied_total"].sum() == pytest.approx(44.5) and both["implied_total"].notna().all()
    assert teams["implied_total"].notna().all() and (teams["implied_total"] > 0).all()


def test_results_are_keyed_by_the_espn_game_id(tables):
    players, _ = tables
    r = nfl_stage.results(players)
    assert r["game_id"].str.match(r"^\d+$").all() and len(r) == len(players)
    assert {"player", "team", "played", *nfl_stage.PROP_STATS} <= set(r.columns)
    assert nfl_stage.results(players.iloc[0:0]).empty
    assert nfl_stage.normalise(pd.DataFrame(), pd.DataFrame()).empty
    assert nfl_stage.team_weeks(pd.DataFrame(columns=nfl_stage.COLUMNS), pd.DataFrame()).empty


def test_espn_ids_cover_every_franchise_and_abbreviations_read_back():
    assert set(nfl_games.ESPN_TEAM_ID) == set(nfl_games.TEAMS) and len(set(nfl_games.ESPN_TEAM_ID.values())) == 32
    assert nfl_games.CODE_BY_ESPN_ID[23] == "PIT" and nfl_games.CODE_BY_ESPN_ID[28] == "WAS"
    assert nfl_games.code_of("WSH") == "WAS" and nfl_games.code_of("LAR") == "LA" and nfl_games.code_of("kc") == "KC"
    assert nfl_games.code_of("OAK") == "LV" and nfl_games.code_of(None) == ""


# ---------------------------------------------------------------------------
# The model
# ---------------------------------------------------------------------------


def test_features_are_what_was_known_before_each_game(tables):
    players, teams = tables
    f = nfl_props.features(players, teams, nfl_props.Spec())
    assert len(f) == len(players)
    for opp in nfl_props.OF_TEAM:
        assert f[f"share_{opp}"].between(0.0, 1.0).all()
    # Before his first game a player is his position's prior, with no games behind him.
    wes = f[f["player"] == player_name("Wes", "KC")].sort_values("kickoff")
    assert wes["n"].iloc[0] == 0.0 and wes["n_season"].iloc[0] == 0.0 and math.isnan(wes["naive_receiving_yards"].iloc[0])
    assert wes["n"].iloc[-1] > 10 and wes["n_season"].iloc[-1] == wes[wes["season"] == SEASONS[-1]].shape[0] - 1
    # After a season, the first receiver's share of the targets is above the third's.
    walt = f[f["player"] == player_name("Walt", "KC")].sort_values("kickoff")
    later = wes["season"] == SEASONS[1]
    assert wes[later]["share_targets"].mean() > walt[walt["season"] == SEASONS[1]]["share_targets"].mean()
    assert (f["base_receiving_yards"] >= 0).all() and (f["opp_receiving_yards"].between(0.6, 1.6)).all()
    assert f[f["position"] == "QB"]["base_passing_yards"].mean() > 150
    assert f[f["position"] == "WR"]["base_passing_yards"].max() < 5


def test_the_model_walks_forward_and_scores_against_the_season_mean(tables):
    players, teams = tables
    rows, layers = nfl_props.walk(players, teams, nfl_props.Spec(), SEASONS[1:])
    assert set(layers) == set(SEASONS[1:])
    for season in SEASONS[1:]:
        for stat in nfl_props.STATS:
            assert len(layers[season][stat]["beta"]) == 4 and layers[season][stat]["dispersion"] >= 1.0
    assert set(rows["season_type"]) == {"regular"} and (rows[[f"mu_{s}" for s in nfl_props.STATS]] >= 0).all().all()
    table = nfl_props.score(rows, layers)
    assert set(table["stat"]) == {*nfl_props.STATS, *nfl_props.COMBINED} and table["n"].min() > 50
    assert (rows["mu_scrimmage_yards"] == rows["mu_rushing_yards"] + rows["mu_receiving_yards"]).all()
    assert table["brier_atlas"].between(0, 1).all() and (table["mean_atlas"] - table["observed"]).abs().max() < 0.15
    assert table["brier_atlas"].mean() <= table["brier_naive"].mean() + 0.01
    assert np.isfinite(nfl_props.loglik(rows, layers)) and nfl_props.loglik(rows, layers) < 0
    # A season with nothing before it is fitted on itself, for want of better.
    first = nfl_props.fit_season(nfl_props.features(players, teams, nfl_props.Spec()), SEASONS[0])
    assert set(first) == {*nfl_props.STATS, *nfl_props.COMBINED}


def test_the_spec_is_read_from_the_report_directory(tmp_path):
    assert nfl_props.load_spec(tmp_path) == nfl_props.Spec()
    nfl_props.spec_path(tmp_path).parent.mkdir()
    nfl_props.spec_path(tmp_path).write_text(json.dumps({"h_share": 4, "k_rate": 20, "stray": 1}))
    assert nfl_props.load_spec(tmp_path) == nfl_props.Spec(h_share=4.0, k_rate=20.0)


def test_the_snapshot_projects_a_player_against_an_opponent(snap):
    assert snap["version"] == nfl_props.VERSION and snap["season"] == SEASONS[-1]
    assert len(snap["players"]) == len(CODES) * len(SKILL) and len(snap["teams"]) == len(CODES)
    assert list(snap["players"].columns) == nfl_props.PLAYER_STATE and list(snap["teams"].columns) == nfl_props.TEAM_STATE
    assert "Kip Kc" not in set(snap["players"]["player"]) and snap["level"]["implied_total"] > 15
    wes, walt, qb = _row(snap, "Wes Kc"), _row(snap, "Walt Kc"), _row(snap, "Quinn Kc")
    assert wes["n_season"] == WEEKS - 1 and wes["share_targets"] > walt["share_targets"] > 0
    e = nfl_props.expect(snap, wes, "KC", "BUF", True, 24.0)
    assert set(e) == {*nfl_props.STATS, *nfl_props.COMBINED}
    assert e["receiving_yards"] > nfl_props.expect(snap, walt, "KC", "BUF", True, 24.0)["receiving_yards"] > 0
    assert e["scrimmage_yards"] == pytest.approx(e["rushing_yards"] + e["receiving_yards"])
    assert 20 < e["receiving_yards"] < 120 and 1 < e["receptions"] < 10 and e["passing_yards"] < 5
    passer = nfl_props.expect(snap, qb, "KC", "BUF", True, 24.0)
    assert 150 < passer["passing_yards"] < 400 and 0.5 < passer["passing_tds"] < 4 and passer["receiving_yards"] < 2
    # The opportunities priced as stats: a starter's attempts are his team's, his completions fewer.
    assert 25 < passer["attempts"] < 45 and 0.5 * passer["attempts"] < passer["completions"] < passer["attempts"]
    rex = _row(snap, "Rex Kc")
    assert 8 < nfl_props.expect(snap, rex, "KC", "BUF", True, 24.0)["carries"] < 25 and passer["carries"] < 5
    # A bigger game is more of everything; the league's total when none is known; nan for a team unknown.
    assert nfl_props.expect(snap, wes, "KC", "BUF", True, 30.0)["receiving_yards"] > e["receiving_yards"]
    assert nfl_props.expect(snap, wes, "KC", "BUF", True, None)["receiving_yards"] > 0
    assert all(math.isnan(v) for v in nfl_props.expect(snap, wes, "KC", "ZZZ", True, 24.0).values())
    assert nfl_props.dispersion(snap, "receiving_yards") >= 1.0


def test_probabilities_at_a_line(snap):
    d = nfl_props.dispersion(snap, "receiving_yards")
    over, under = nfl_props.prob(60.0, 49.5, "over", d), nfl_props.prob(60.0, 49.5, "under", d)
    assert over + under == pytest.approx(1.0) and over > 0.5
    whole = nfl_props.prob(60.0, 50.0, "over", d) + nfl_props.prob(60.0, 50.0, "under", d)
    assert whole < 1.0                                                                 # a tie is neither
    assert nfl_props.prob(0.3, 0.5, "over", 1.0) == pytest.approx(1 - math.exp(-0.3))


def test_the_snapshot_is_saved_and_read_back(snap, tmp_path):
    where = tmp_path / "nfl_props_state.json"
    assert nfl_props.save_state(snap, where) == where
    back = nfl_props.load_state(where)
    assert back["season"] == snap["season"] and back["layer"] == snap["layer"] and back["level"] == snap["level"]
    assert len(back["players"]) == len(snap["players"]) and list(back["teams"].columns) == nfl_props.TEAM_STATE
    wes = _row(back, "Wes Kc")
    assert nfl_props.expect(back, wes, "KC", "BUF", True, 24.0) == pytest.approx(
        nfl_props.expect(snap, _row(snap, "Wes Kc"), "KC", "BUF", True, 24.0))
    assert nfl_props.load_state(tmp_path / "missing.json") is None


def test_the_injury_report_sets_the_chance_of_playing(snap):
    from atlas.sources.nba_availability import COLUMNS

    report = pd.DataFrame([
        {"player": "Wes Kc", "team_abbr": "KC", "status": "Out"},
        {"player": "Will Kc", "team_abbr": "KC", "status": "Questionable"},
        {"player": "Walt Kc", "team_abbr": "KC", "status": "Active"},                  # listed, but playing
        {"player": "Wes Buf", "team_abbr": "BUF", "status": "Injured Reserve"},
        {"player": "Wes Sea", "team_abbr": "WSH", "status": "Out"},                     # not his team
    ], columns=COLUMNS)
    adj = nfl_props.adjust(snap, report)
    p = adj["players"].set_index("player")
    assert p.loc["Wes Kc", "p_play"] == 0.02 and p.loc["Wes Kc", "status"] == "out"
    assert p.loc["Will Kc", "p_play"] == 0.75 and p.loc["Will Kc", "status"] == "questionable"
    assert p.loc["Walt Kc", "p_play"] == 1.0 and p.loc["Walt Kc", "status"] == ""
    assert p.loc["Wes Buf", "p_play"] == 0.0 and p.loc["Wes Sea", "p_play"] == 1.0
    assert "p_play" not in snap["players"]                                             # the snapshot stands
    assert (nfl_props.adjust(snap, None)["players"]["p_play"] == 1.0).all()
    assert (nfl_props.adjust(snap, pd.DataFrame(columns=COLUMNS))["players"]["p_play"] == 1.0).all()


# ---------------------------------------------------------------------------
# The props on Polymarket US
# ---------------------------------------------------------------------------

KC, BUF = us.team(12, "Kansas City Chiefs", "Chiefs", "kc"), us.team(2, "Buffalo Bills", "Bills", "buf")
START = "2024-11-03T18:00:00Z"


def _nfl_prop(mid, stat, player, n, bid, ask, team):
    """The NFL's form of the question, "N+", as the gateway writes it."""
    words = stat.replace("_", " ")
    return us.market(mid, f"football_player_{stat}", f"Will {player} record {n}+ {words}?", "Yes", "No", bid, ask,
                     line=n, long_team=team["id"], short_team=team["id"], start=START)


def _event():
    return us.event("8001", "nfl-kc-buf-2024-11-03", KC, BUF, [
        _nfl_prop(1, "receiving_yards", "Wes Kc", 50, 0.49, 0.51, KC),
        _nfl_prop(2, "receiving_yards", "Wes Kc", 75, 0.24, 0.26, KC),
        _nfl_prop(3, "receptions", "Wes Kc", 5, 0.44, 0.46, KC),
        _nfl_prop(4, "passing_yards", "Quinn Buf", 250, 0.49, 0.51, BUF),
        _nfl_prop(5, "passing_touchdowns", "Quinn Buf", 2, 0.49, 0.51, BUF),
        _nfl_prop(6, "touchdowns", "Rex Buf", 1, 0.54, 0.56, BUF),
        _nfl_prop(7, "rushing_yards", "Nobody Known", 50, 0.49, 0.51, BUF),
        us.moneyline(8, "football", KC, BUF, 0.44, 0.46, start=START)], start=START)


def _pairs():
    return pd.DataFrame([{"event_id": "8001", "game_id": "401024091", "sport": "nfl", "kickoff": START,
                          "season": 2024, "week": 9, "home_team": "Buffalo Bills", "away_team": "Kansas City Chiefs",
                          "label": "Kansas City Chiefs @ Buffalo Bills", "home_team_id": 2, "away_team_id": 12}])


def test_the_nfl_question_is_read_as_the_over_at_a_half_line():
    from atlas.polymarket import props, source

    now = datetime(2024, 11, 1, tzinfo=UTC)
    q = props.prop_quotes([_event()], source.LEAGUES["nfl"], now)
    assert len(q) == 14 and set(q["sport"]) == {"nfl"}
    by = q.set_index(["player", "stat", "line", "side"])
    assert by.loc[("Wes Kc", "receiving_yards", 49.5, "over"), "ask"] == 0.51
    assert by.loc[("Wes Kc", "receiving_yards", 49.5, "under"), "ask"] == pytest.approx(0.51)
    assert by.loc[("Quinn Buf", "passing_tds", 1.5, "over"), "team_side"] == "home"
    assert by.loc[("Wes Kc", "receptions", 4.5, "over"), "team_side"] == "away"
    assert set(q["stat"]) == {"receiving_yards", "receptions", "passing_yards", "passing_tds", "touchdowns", "rushing_yards"}
    main = props.main_lines(q)
    assert len(main[(main["player"] == "Wes Kc") & (main["stat"] == "receiving_yards")]) == 2       # 49.5, not 74.5


def test_the_props_are_priced_off_the_snapshot_with_the_report_and_the_projection(snap, tables):
    from atlas.polymarket import match, props, source

    players, _ = tables
    now = datetime(2024, 11, 1, tzinfo=UTC)
    q = match.attach(props.prop_quotes([_event()], source.LEAGUES["nfl"], now), _pairs())
    snaps = {"nba": None, "nhl": None, "nfl": snap}
    totals = {"401024091": (21.0, 27.5)}
    e = props.expectations(q, snaps, totals=totals)
    by = e.set_index(["player", "stat", "line", "side"])
    wes = by.loc[("Wes Kc", "receiving_yards", 49.5, "over")]
    assert 20 < wes["atlas_mean"] < 120 and 0 < wes["p_atlas"] < 1 and wes["status"] == ""
    assert wes["p_atlas"] + by.loc[("Wes Kc", "receiving_yards", 49.5, "under"), "p_atlas"] == pytest.approx(1.0)
    assert by.loc[("Wes Kc", "receiving_yards", 74.5, "over"), "p_atlas"] < wes["p_atlas"]
    assert 150 < by.loc[("Quinn Buf", "passing_yards", 249.5, "over"), "atlas_mean"] < 400
    assert 0 < by.loc[("Rex Buf", "touchdowns", 0.5, "over"), "atlas_mean"] < 2
    assert math.isnan(by.loc[("Nobody Known", "rushing_yards", 49.5, "over"), "p_atlas"])
    # The home team's implied total lifts its passer; without a projection the league's total stands.
    bigger = props.expectations(q, snaps, totals={"401024091": (21.0, 34.0)}).set_index(["player", "stat", "line", "side"])
    assert bigger.loc[("Quinn Buf", "passing_yards", 249.5, "over"), "atlas_mean"] \
        > by.loc[("Quinn Buf", "passing_yards", 249.5, "over"), "atlas_mean"]
    plain = props.expectations(q, snaps).set_index(["player", "stat", "line", "side"])
    assert plain.loc[("Wes Kc", "receiving_yards", 49.5, "over"), "atlas_mean"] > 0
    # A player listed Out keeps his number, and his chance of not playing goes to the market's price.
    from atlas.sources.nba_availability import COLUMNS

    report = pd.DataFrame([{"player": "Wes Kc", "team_abbr": "KC", "status": "Out"}], columns=COLUMNS)
    out = props.expectations(q, snaps, totals=totals, nfl_availability=report).set_index(["player", "stat", "line", "side"])
    listed = out.loc[("Wes Kc", "receiving_yards", 49.5, "over")]
    assert listed["status"] == "out" and listed["atlas_mean"] == pytest.approx(wes["atlas_mean"])
    assert listed["p_atlas"] == pytest.approx(0.02 * wes["p_atlas"] + 0.98 * 0.50)
    # Graded from the player weeks, keyed by the ESPN game id.
    results = props.results_frame("nfl", players)
    assert set(results["sport"]) == {"nfl"} and results["game_id"].str.match(r"^\d+$").all()
    game = players[players["player"] == "Wes Kc"].iloc[-1]
    value, played = props._value(results, "nfl", str(int(game["espn_id"])), "Wes Kc", "receiving_yards")
    assert played and value == game["receiving_yards"]
    assert props._value(results, "nfl", str(int(game["espn_id"])), "Nobody Known", "receiving_yards")[1] is False


def test_refresh_prices_the_nfl_and_counts_it_in_the_summary(snap, tables, tmp_path, monkeypatch):
    from atlas.live.store import Store
    from atlas.polymarket import props

    players, _ = tables
    now = datetime(2024, 11, 1, 15, 0, tzinfo=UTC)
    monkeypatch.setenv("ATLAS_OFFLINE", "1")
    monkeypatch.setenv("ATLAS_DATA_DIR", str(tmp_path / "data"))
    store = Store.open(tmp_path / "tracking")
    monkeypatch.setattr(props, "path", lambda: tmp_path / "prop_positions")
    sections, summary = props.refresh(store, {"nfl": [_event()]}, _pairs(), now, KEY,
                                      snaps={"nba": None, "nhl": None, "nfl": snap},
                                      results=props.results_frame("nfl", players))
    nfl = summary["sports"]["nfl"]
    assert nfl["contracts"] == 7 and nfl["games"] == 1 and nfl["projected"] == 6 and nfl["listed"] == 0
    assert summary["contracts"] == 7 and summary["sports"]["nba"]["contracts"] == 0
    assert [s["title"] for s in sections][:2] == ["Prop positions for Fri Nov 1 (0)", "Props board"]
    kept = store.read("polymarket_props")
    assert set(kept["sport"]) == {"nfl"} and len(kept) == 12                            # the main lines, both sides
    assert json.dumps(sections)


def test_the_opportunity_props_are_read_priced_and_graded(snap, tables):
    from atlas.polymarket import match, props, source

    players, _ = tables
    now = datetime(2024, 11, 1, tzinfo=UTC)
    ev = us.event("8001", "nfl-kc-buf-2024-11-03", KC, BUF, [
        _nfl_prop(1, "passing_attempts", "Quinn Buf", 30, 0.49, 0.51, BUF),
        _nfl_prop(2, "passing_completions", "Quinn Buf", 20, 0.49, 0.51, BUF),
        _nfl_prop(3, "rushing_attempts", "Rex Kc", 12, 0.49, 0.51, KC),
        _nfl_prop(4, "scrimmage_yards", "Rex Kc", 75, 0.39, 0.41, KC)], start=START)
    q = props.prop_quotes([ev], source.LEAGUES["nfl"], now)
    assert set(q["stat"]) == {"attempts", "completions", "carries", "scrimmage_yards"} and len(q) == 8
    e = props.expectations(match.attach(q, _pairs()), {"nba": None, "nhl": None, "nfl": snap}).set_index(["player", "stat", "line", "side"])
    qb = nfl_props.expect(snap, _row(snap, "Quinn Buf"), "BUF", "KC", True, None)
    assert e.loc[("Quinn Buf", "attempts", 29.5, "over"), "atlas_mean"] == pytest.approx(qb["attempts"])
    assert e.loc[("Quinn Buf", "completions", 19.5, "over"), "atlas_mean"] == pytest.approx(qb["completions"])
    rex = nfl_props.expect(snap, _row(snap, "Rex Kc"), "KC", "BUF", False, None)
    assert e.loc[("Rex Kc", "scrimmage_yards", 74.5, "over"), "atlas_mean"] == pytest.approx(rex["rushing_yards"] + rex["receiving_yards"])
    for key in (("Quinn Buf", "attempts", 29.5), ("Quinn Buf", "completions", 19.5), ("Rex Kc", "carries", 11.5),
                ("Rex Kc", "scrimmage_yards", 74.5)):
        assert 0 < e.loc[(*key, "over"), "p_atlas"] < 1
        assert e.loc[(*key, "over"), "p_atlas"] + e.loc[(*key, "under"), "p_atlas"] == pytest.approx(1.0)
    # Graded from the player weeks: scrimmage yards the sum of the two.
    results = props.results_frame("nfl", players)
    game = players[players["player"] == "Rex Kc"].iloc[-1]
    value, played = props._value(results, "nfl", str(int(game["espn_id"])), "Rex Kc", "scrimmage_yards")
    assert played and value == game["rushing_yards"] + game["receiving_yards"]
    assert props._value(results, "nfl", str(int(game["espn_id"])), "Rex Kc", "carries") == (game["carries"], True)
    # A snapshot written before the stats were added prices what it has, and nan for the rest.
    old = {**snap, "layer": {s: snap["layer"][s] for s in snap["layer"] if s not in ("attempts", "completions", "carries", "scrimmage_yards")},
           "players": snap["players"].drop(columns=["attempts_rate", "completions_rate", "carries_rate"]),
           "teams": snap["teams"].drop(columns=["f_allow_attempts", "f_allow_completions", "f_allow_carries"])}
    e_old = props.expectations(match.attach(q, _pairs()), {"nba": None, "nhl": None, "nfl": old}).set_index(["player", "stat", "line", "side"])
    assert math.isnan(e_old.loc[("Quinn Buf", "attempts", 29.5, "over"), "p_atlas"])
    assert e_old.loc[("Rex Kc", "scrimmage_yards", 74.5, "over"), "atlas_mean"] == pytest.approx(rex["rushing_yards"] + rex["receiving_yards"])
