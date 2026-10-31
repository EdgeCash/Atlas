"""NBA player props: the staging, the model, and their place on Polymarket, on the synthetic hoopR tree."""

from __future__ import annotations

import json
import math
import os
from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pytest

from atlas.models import nba_props as npr
from atlas.polymarket import match, positions, props, source
from atlas.research.nba_dataset import load_table
from atlas.staging.nba import build as nba_build
from atlas.testing import polymarket_us as us
from atlas.testing.synthetic_nba import TEAMS, write_synthetic_nba_raw

SEASONS = [2022, 2023, 2024]
KEY = "correct horse battery staple"


@pytest.fixture(scope="module")
def tree(tmp_path_factory):
    base = tmp_path_factory.mktemp("nba_props")
    write_synthetic_nba_raw(base / "raw", SEASONS)
    old = os.environ.get("ATLAS_DATA_DIR")
    os.environ["ATLAS_DATA_DIR"] = str(base)
    os.environ["ATLAS_OFFLINE"] = "1"
    try:
        nba_build.build(SEASONS)
    finally:
        if old is None:
            os.environ.pop("ATLAS_DATA_DIR", None)
        else:
            os.environ["ATLAS_DATA_DIR"] = old
    return base


@pytest.fixture(scope="module")
def tables(tree):
    return load_table("player_games", tree / "warehouse"), load_table("team_games", tree / "warehouse")


def test_player_games_follow_the_conventions(tables):
    p, _ = tables
    assert set(p["season"]) == set(SEASONS) and set(p["position"]) <= {"G", "F", "C"}
    assert p["player_id"].nunique() == 6 * len(TEAMS)
    assert (p[~p["played"]]["minutes"] == 0).all() and 0.03 < (~p["played"]).mean() < 0.15
    assert {*npr.STATS, "is_home", "opponent_id"} <= set(p.columns)


def test_the_model_walks_forward_and_beats_the_season_mean(tables):
    p, tg = tables
    rows, layers = npr.walk(p, tg, npr.Spec(), [SEASONS[2]])
    assert set(layers) == {SEASONS[2]} and all(layers[SEASONS[2]][s]["dispersion"] >= 1.0 for s in npr.STATS)
    assert (rows[[f"mu_{s}" for s in npr.STATS]] > 0).all().all()
    assert (rows["mu_pra"] == rows["mu_points"] + rows["mu_rebounds"] + rows["mu_assists"]).all()
    assert (rows["pra"] == rows["points"] + rows["rebounds"] + rows["assists"]).all()
    table = npr.score(rows, layers)
    assert len(table) == sum(len(v) for v in npr.LINES.values()) and "pra" in set(table["stat"])
    assert (table["brier_atlas"] < table["brier_naive"]).mean() >= 0.5
    assert npr.loglik(rows, layers) < 0
    text = npr.render(table, npr.Spec(), [SEASONS[2]])
    assert "| points | 9.5 |" in text


def test_the_snapshot_projects_a_player_against_an_opponent_and_seals_nothing(tables, tmp_path):
    p, tg = tables
    now = datetime(2025, 3, 1, tzinfo=UTC)
    snap = npr.snapshot(p, tg, now, npr.Spec())
    assert snap["season"] == 2024 and len(snap["players"]) == 6 * len(TEAMS) and len(snap["teams"]) == len(TEAMS)
    star = snap["players"].set_index("player").loc["BOS Player 0"]
    bench = snap["players"].set_index("player").loc["BOS Player 5"]
    e = npr.expect(snap, star, 2, 13, True)
    assert e["points"] > npr.expect(snap, bench, 2, 13, True)["points"] > 0
    assert set(e) == {*npr.STATS, *npr.COMBINED}
    assert e["pra"] == pytest.approx(e["points"] + e["rebounds"] + e["assists"]) and e["steals"] > 0 and e["blocks"] > 0
    assert npr.dispersion(snap, "pra") >= 1.0 and math.isnan(npr.dispersion(snap, "no such stat"))
    assert all(np.isnan(v) for v in npr.expect(snap, star, 2, 999, True).values())      # a team it does not know
    d = npr.dispersion(snap, "points")
    assert 0.3 < npr.prob(e["points"], 14.5, "over", d) < 0.95
    assert npr.prob(10.0, 9.5, "over", d) + npr.prob(10.0, 9.5, "under", d) == pytest.approx(1.0)
    assert npr.prob(10.0, 10.0, "over", d) + npr.prob(10.0, 10.0, "under", d) < 1.0      # a tie on a whole line
    where = tmp_path / "state.json"
    npr.save_state(snap, where)
    back = npr.load_state(where)
    assert back["season"] == 2024 and len(back["players"]) == len(snap["players"]) and back["layer"] == snap["layer"]
    assert npr.load_state(tmp_path / "missing.json") is None
    assert npr.load_spec(tmp_path) == npr.Spec()


LAL, BOS = us.team(1487, "Lakers", "Los Angeles"), us.team(1500, "Celtics", "Boston")
TIP = "2025-03-02T00:30:00Z"


def _event():
    return us.event("7001", "nba-lal-bos-2025-03-02", LAL, BOS, [
        us.prop(1, "basketball_player_points", "BOS Player 0", 15, 0.49, 0.51, team=BOS, start=TIP),
        us.prop(2, "basketball_player_points", "BOS Player 0", 20, 0.19, 0.21, team=BOS, start=TIP),
        us.prop(3, "basketball_player_rebounds", "LAL Player 1", 6, 0.49, 0.51, team=LAL, start=TIP),
        us.prop(4, "basketball_player_assists", "Nobody Known", 4, 0.49, 0.51, team=LAL, start=TIP),
        us.moneyline(5, "basketball", LAL, BOS, 0.39, 0.41, start=TIP)], start=TIP)


def _pairs():
    return pd.DataFrame([{"event_id": "7001", "game_id": "901", "sport": "nba", "kickoff": "2025-03-02T00:30Z",
                          "season": 2024, "week": 20, "home_team": "Boston Celtics", "away_team": "Los Angeles Lakers",
                          "label": "Los Angeles Lakers @ Boston Celtics", "home_team_id": 2, "away_team_id": 13}])


def test_prop_quotes_are_read_as_yes_over_and_no_under_and_the_main_line_is_kept():
    now = datetime(2025, 3, 1, 15, 0, tzinfo=UTC)
    q = props.prop_quotes([_event()], source.LEAGUES["nba"], now)
    assert len(q) == 8 and set(q["stat"]) == {"points", "rebounds", "assists"}      # the moneyline is not a prop
    over = q.set_index(["player", "stat", "line", "side"])
    assert over.loc[("BOS Player 0", "points", 14.5, "over"), "ask"] == 0.51
    assert over.loc[("BOS Player 0", "points", 14.5, "under"), "ask"] == pytest.approx(0.51)
    assert over.loc[("BOS Player 0", "points", 19.5, "under"), "bid"] == pytest.approx(0.79)
    assert (q["fee_rate"] == 0.0695).all() and q["away"].iloc[0] == "Los Angeles Lakers" \
        and q["home"].iloc[0] == "Boston Celtics"
    assert set(q["team_side"]) == {"home", "away"} and set(q["line"]) == {14.5, 19.5, 5.5, 3.5}  # "at least N" is over N - 1/2
    kept = props.main_lines(q)
    assert set(kept[kept["player"] == "BOS Player 0"]["line"]) == {14.5}             # nearest even, not 19.5
    assert len(kept) == 6
    assert props.key("Luka Dončić") == "luka doncic" and props.key("Jaren Jackson Jr.") == "jaren jackson"


def test_expectations_find_the_player_on_one_of_the_games_teams(tables):
    p, tg = tables
    snap = npr.snapshot(p, tg, datetime(2025, 3, 1, tzinfo=UTC), npr.Spec())
    from atlas.polymarket import match

    q = match.attach(props.prop_quotes([_event()], source.LEAGUES["nba"], datetime(2025, 3, 1, 15, 0, tzinfo=UTC)),
                     _pairs())
    e = props.expectations(q, {"nba": snap, "nhl": None, "nfl": None})
    by = e.set_index(["player", "stat", "line", "side"])
    assert by.loc[("BOS Player 0", "points", 14.5, "over"), "atlas_mean"] > 10
    assert by.loc[("BOS Player 0", "points", 14.5, "over"), "p_atlas"] \
        + by.loc[("BOS Player 0", "points", 14.5, "under"), "p_atlas"] == pytest.approx(1.0)
    assert by.loc[("LAL Player 1", "rebounds", 5.5, "over"), "atlas_mean"] > 0
    assert np.isnan(by.loc[("Nobody Known", "assists", 3.5, "over"), "p_atlas"])
    priced = props.price(e, None)
    row = priced.set_index(["player", "stat", "line", "side"]).loc[("BOS Player 0", "points", 14.5, "over")]
    assert row["share"] == 0.0 and row["p"] == pytest.approx(row["p_market"]) and row["ev"] < 0   # the market, less the spread
    assert row["market"] == "player:points" and row["prop_key"] == "901|bos player 0|points"
    assert positions.positions(priced, datetime(2025, 3, 1, 15, 0, tzinfo=UTC), unit="prop_key",
                               columns=props.POSITION_COLUMNS).empty


def test_the_record_grades_from_the_box_score_and_gives_the_share(tables, tmp_path):
    p, tg = tables
    now = datetime(2025, 3, 1, 15, 0, tzinfo=UTC)
    snap = npr.snapshot(p, tg, now, npr.Spec())
    from atlas.live.store import Store
    from atlas.polymarket import match

    store = Store.open(tmp_path / "tracking")
    q = props.expectations(match.attach(props.prop_quotes([_event()], source.LEAGUES["nba"], now), _pairs()),
                           {"nba": snap, "nhl": None, "nfl": None})
    kept = props.main_lines(q[q["game_id"].notna()])
    record, added = source.fold(store.read("polymarket_props"), kept.reindex(columns=props.PROP_COLUMNS),
                                cols=props.PROP_COLUMNS)
    assert added == 6
    store.write("polymarket_props", record)
    back = store.read("polymarket_props")
    assert (back["game_id"].astype(str) == "901").all()
    # Before the game, nothing to grade; after it, with a box score, the over side is graded.
    results = pd.DataFrame([{"sport": "nba", "game_id": "901", "player_key": "bos player 0", "played": True,
                             "points": 22.0, "rebounds": 5.0, "assists": 2.0, "threes": 1.0},
                            {"sport": "nba", "game_id": "901", "player_key": "lal player 1", "played": False,
                             "points": 0.0, "rebounds": 0.0, "assists": 0.0, "threes": 0.0}])
    assert props.grade_record(back, store.read("prop_record"), results, now).empty
    after = datetime(2025, 3, 2, 5, 0, tzinfo=UTC)
    new = props.grade_record(back, store.read("prop_record"), results, after)
    g = new.set_index(["player", "stat"])
    assert g.loc[("BOS Player 0", "points"), "value"] == 22.0 and g.loc[("BOS Player 0", "points"), "played"]
    p_atlas = g.loc[("BOS Player 0", "points"), "p_atlas"]
    assert g.loc[("BOS Player 0", "points"), "won"] == (1.0 if p_atlas >= 0.5 else 0.0)
    assert g.loc[("LAL Player 1", "rebounds"), "won"] == 0.5 and not g.loc[("LAL Player 1", "rebounds"), "played"]
    assert "Nobody Known" not in g.index.get_level_values(0)                        # no projection: not in the record
    assert g.loc[("BOS Player 0", "points"), "p_close"] == pytest.approx(0.5)
    store.append_new_only("prop_record", new)
    assert props.grade_record(back, store.read("prop_record"), results, after).empty   # graded once
    cal = props.calibration_rows(store.read("prop_record"))
    assert len(cal) == 1 and cal["market"].iloc[0] == "player" and cal["claimed"].iloc[0] >= 0.5
    from atlas.polymarket import pricing

    assert pricing.share(cal, "nba", "player") == (0.0, 1)                           # thin: the market
    sec = props.record_section(store.read("prop_record"))
    assert sec["title"] == "Prop record: 1 graded" and sec["tab"] == "Props"


def test_graded_and_stale_markets_retire_once_the_venue_has_let_the_game_go():
    now = datetime(2026, 10, 31, 12, 0, tzinfo=UTC)
    last_night, small_hours, last_week, tomorrow = ("2026-10-30T23:00:00+00:00", "2026-10-31T02:00:00+00:00",
                                                    "2026-10-25T23:00:00+00:00", "2026-11-01T23:00:00+00:00")

    def row(token, market, start, side):
        return {"token_id": token, "market_id": market, "game_start": start, "side": side, "captured_at": start}

    record = pd.DataFrame([
        row("o1", "m1", last_night, "over"), row("u1", "m1", last_night, "under"),      # graded: both sides go
        row("o2", "m2", last_night, "over"), row("u2", "m2", last_night, "under"),      # not graded yet: stays
        row("o3", "m3", small_hours, "over"), row("u3", "m3", small_hours, "under"),    # graded, ten hours ago: too soon
        row("o4", "m4", last_week, "over"),                                              # never graded: stale
        row("o5", "m5", tomorrow, "over"),
    ]).reindex(columns=props.PROP_COLUMNS)
    graded = pd.DataFrame({"token_id": ["o1", "o3"]})
    assert sorted(props.retired(record, graded, now)["token_id"]) == ["o1", "o4", "u1"]
    assert props.retired(record, graded.iloc[0:0], now)["token_id"].tolist() == ["o4"]
    assert props.retired(record.iloc[0:0], graded, now).empty
    assert props.RETIRE_QUIET > match.BEHIND                                             # nothing retired is still matched


def test_refresh_retires_the_graded_markets_to_the_archive_after_the_positions_are_graded(tables, tmp_path, monkeypatch):
    p, tg = tables
    now = datetime(2025, 3, 1, 15, 0, tzinfo=UTC)
    snap = npr.snapshot(p, tg, now, npr.Spec())
    from atlas.live.store import Store

    monkeypatch.setenv("ATLAS_OFFLINE", "1")
    store = Store.open(tmp_path / "tracking")
    monkeypatch.setattr(props, "path", lambda: tmp_path / "prop_positions")
    snaps = {"nba": snap, "nhl": None, "nfl": None}
    results = pd.DataFrame([{"sport": "nba", "game_id": "901", "player_key": "bos player 0", "played": True,
                             "points": 22.0, "rebounds": 5.0, "assists": 2.0, "threes": 1.0},
                            {"sport": "nba", "game_id": "901", "player_key": "lal player 1", "played": False,
                             "points": 0.0, "rebounds": 0.0, "assists": 0.0, "threes": 0.0}])
    props.refresh(store, {"nba": [_event()]}, _pairs(), now, KEY, snaps=snaps, results=results)
    assert len(store.read("polymarket_props")) == 6 and store.parts("polymarket_props") == []   # before the game
    # The afternoon after, with the box score: the two projected players' markets grade and their rows leave the
    # live table for the game date's archive file. The player without a projection never grades and stays.
    later = datetime(2025, 3, 2, 15, 0, tzinfo=UTC)
    props.refresh(store, {"nba": [_event()]}, _pairs(), later, KEY, snaps=snaps, results=results)
    assert len(store.read("prop_record")) == 2
    live = store.read("polymarket_props")
    assert set(live["player"]) == {"Nobody Known"} and len(live) == 2
    assert store.parts("polymarket_props") == ["2025-03-02.csv"]
    archived = store.read("polymarket_props", "2025-03-02.csv")
    assert set(archived["player"]) == {"BOS Player 0", "LAL Player 1"} and len(archived) == 4
    assert len(store.history("polymarket_props")) == 6                                           # nothing lost


def test_refresh_reads_grades_prices_and_seals_offline(tables, tmp_path, monkeypatch):
    p, tg = tables
    now = datetime(2025, 3, 1, 15, 0, tzinfo=UTC)
    snap = npr.snapshot(p, tg, now, npr.Spec())
    from atlas.live.store import Store

    monkeypatch.setenv("ATLAS_OFFLINE", "1")
    store = Store.open(tmp_path / "tracking")
    monkeypatch.setattr(props, "path", lambda: tmp_path / "prop_positions")
    sections, summary = props.refresh(store, {"nba": [_event()]}, _pairs(), now, KEY,
                                      snaps={"nba": snap, "nhl": None, "nfl": None}, results=props.results_frame("nba", p))
    assert summary["contracts"] == 4 and summary["games"] == 1 and summary["projected"] == 3
    assert [s["title"] for s in sections][:2] == ["Prop positions for Sat Mar 1 (0)", "Props board"]
    board = sections[1]["tables"][0]
    assert board["rows"] and "Atlas" in board["rows"][0][1][1]
    assert json.dumps(sections)
    assert len(store.read("polymarket_props")) == 6 and store.read("prop_record").empty
    # Without a snapshot the step says so and keeps nothing.
    empty, _ = props.refresh(store, {"nba": [_event()]}, _pairs(), now, KEY, snaps={"nba": None, "nhl": None, "nfl": None})
    assert "No player snapshot yet" in empty[0]["notes"][0]


def test_grading_positions_pushes_a_player_who_did_not_play_as_the_venue_settles_him():
    base = {**dict.fromkeys(props.POSITION_COLUMNS), "sport": "nba", "game_id": "901", "kickoff": "2025-03-02T00:30:00Z",
            "player": "LAL Player 1", "stat": "rebounds", "line": 5.5, "ask": 0.5, "cost": 0.5, "stake": 0.01}
    record = pd.DataFrame([{**base, "position_id": "x", "side": "over", "token_id": "p5"},
                           {**base, "position_id": "y", "side": "under", "token_id": "p6"}])
    results = pd.DataFrame([{"sport": "nba", "game_id": "901", "player_key": "lal player 1", "played": False,
                             "points": 0.0, "rebounds": 0.0, "assists": 0.0, "threes": 0.0}])
    g = props.grade_positions(record, results, pd.DataFrame(columns=props.PROP_COLUMNS),
                              datetime(2025, 3, 2, 5, 0, tzinfo=UTC))
    assert list(g["outcome"]) == ["push", "push"] and (g["pnl"] == 0.0).all()
    played = results.assign(played=True, rebounds=7.0)
    assert list(props.grade_positions(record, played, pd.DataFrame(columns=props.PROP_COLUMNS),
                                      datetime(2025, 3, 2, 5, 0, tzinfo=UTC))["outcome"]) == ["win", "loss"]
    assert props.grade_positions(record, pd.DataFrame(columns=props.RESULT_COLUMNS), pd.DataFrame(columns=props.PROP_COLUMNS),
                                 datetime(2025, 3, 2, 5, 0, tzinfo=UTC))["outcome"].tolist() == ["open", "open"]


def _espn_report(star_id: int) -> dict:
    """ESPN's injuries feed, shrunk: the Celtics' star out (found by id), a Laker day-to-day (by name)."""
    return {"timestamp": "2025-03-01T12:00Z", "status": "success", "injuries": [
        {"id": "2", "displayName": "Boston Celtics", "injuries": [
            {"id": "-1", "status": "Out", "date": "2025-02-27T19:38Z", "shortComment": "Sprained his ankle.",
             "athlete": {"displayName": "BOS Player 0", "position": {"abbreviation": "G"},
                         "links": [{"href": f"https://www.espn.com/nba/player/_/id/{star_id}/bos-player-0"}]},
             "type": {"description": "out"},
             "details": {"fantasyStatus": {"abbreviation": "OUT"}, "type": "Ankle", "location": "Leg",
                         "detail": "Sprain", "side": "Left", "returnDate": "2025-03-10"}}]},
        {"id": "13", "displayName": "Los Angeles Lakers", "injuries": [
            {"id": "-2", "status": "Day-To-Day", "date": "2025-03-01T03:39Z", "shortComment": "Questionable.",
             "athlete": {"displayName": "LAL Player 1", "position": {"abbreviation": "F"}, "links": []},
             "type": {"description": "day-to-day"},
             "details": {"fantasyStatus": {"abbreviation": "GTD"}, "type": "Shoulder", "side": "Not Specified",
                         "returnDate": "2025-03-02"}},
            {"id": "-3", "status": "Out", "date": "2025-03-01T03:40Z", "athlete": {"displayName": "Nobody Here"},
             "details": {}}]},
    ]}


def test_the_injury_report_is_parsed_and_applied_to_the_snapshot(tables):
    from atlas.sources import nba_availability as avail

    p, tg = tables
    snap = npr.snapshot(p, tg, datetime(2025, 3, 1, tzinfo=UTC), npr.Spec())
    star_id = int(snap["players"].set_index("player").loc["BOS Player 0", "player_id"])
    report = avail.parse(_espn_report(star_id), datetime(2025, 3, 1, 15, 0, tzinfo=UTC))
    assert list(report.columns) == avail.COLUMNS and len(report) == 3
    r = report.set_index("player")
    assert r.loc["BOS Player 0", "player_id"] == star_id and r.loc["BOS Player 0", "injury"] == "Left Ankle Sprain"
    assert r.loc["BOS Player 0", "return_date"] == "2025-03-10" and r.loc["BOS Player 0", "fantasy"] == "OUT"
    assert pd.isna(r.loc["LAL Player 1", "player_id"]) and r.loc["LAL Player 1", "injury"] == "Shoulder"
    assert r["captured_at"].iloc[0] == "2025-03-01T15:00:00+00:00"

    before = snap["players"].set_index("player")
    after = npr.adjust(snap, report)["players"].set_index("player")
    assert snap["players"].columns.tolist() == npr.PLAYER_STATE                           # the given one is untouched
    assert after.loc["BOS Player 0", "p_play"] == 0.03 and after.loc["BOS Player 0", "status"] == "out"
    assert after.loc["BOS Player 0", "min_hat"] == before.loc["BOS Player 0", "min_hat"]  # when he plays, he plays
    assert after.loc["LAL Player 1", "p_play"] == 0.55 and after.loc["LAL Player 1", "status"] == "day-to-day"
    assert after.loc["LAL Player 1", "min_hat"] == pytest.approx(0.9 * before.loc["LAL Player 1", "min_hat"])
    bos = after[after["team_id"] == before.loc["BOS Player 0", "team_id"]]
    others = bos.index.drop("BOS Player 0")
    assert (bos.loc[others, "min_hat"] >= before.loc[others, "min_hat"]).all()           # his minutes go to them
    assert (bos.loc[others, "min_hat"] <= npr.MAX_MINUTES).all() and (bos.loc[others, "p_play"] == 1.0).all()
    assert (bos.loc[others, "min_hat"] - before.loc[others, "min_hat"]).sum() == \
        pytest.approx(0.97 * before.loc["BOS Player 0", "min_hat"], rel=1e-6) or \
        (bos.loc[others, "min_hat"] == npr.MAX_MINUTES).any()
    # Unlisted, the snapshot is itself.
    same = npr.adjust(snap, None)["players"]
    assert (same["p_play"] == 1.0).all() and (same["status"] == "").all() and \
        same["min_hat"].tolist() == snap["players"]["min_hat"].tolist()
    # The venue resolves a player who does not play as No: the chance goes to the under.
    d = npr.dispersion(snap, "points")
    assert npr.prob_available(20.0, 14.5, "over", d, 0.03) == pytest.approx(0.03 * npr.prob(20.0, 14.5, "over", d))
    assert npr.prob_available(20.0, 14.5, "under", d, 0.03) + npr.prob_available(20.0, 14.5, "over", d, 0.03) \
        == pytest.approx(1.0)
    assert npr.prob_available(20.0, 14.5, "over", d, 1.0) == npr.prob(20.0, 14.5, "over", d)
    # Settled at the last fair price instead: the chance of not playing goes to the market's own number.
    assert npr.prob_available(20.0, 14.5, "over", d, 0.03, settle=0.6) == \
        pytest.approx(0.03 * npr.prob(20.0, 14.5, "over", d) + 0.97 * 0.6)
    assert npr.prob_available(20.0, 14.5, "over", d, 0.03, settle=0.6) \
        + npr.prob_available(20.0, 14.5, "under", d, 0.03, settle=0.6) == pytest.approx(1.0)


def test_expectations_carry_the_report_into_the_probabilities_and_the_board(tables, tmp_path, monkeypatch):
    from atlas.live.store import Store
    from atlas.sources import nba_availability as avail

    p, tg = tables
    snap = npr.snapshot(p, tg, datetime(2025, 3, 1, tzinfo=UTC), npr.Spec())
    star_id = int(snap["players"].set_index("player").loc["BOS Player 0", "player_id"])
    now = datetime(2025, 3, 1, 15, 0, tzinfo=UTC)
    report = avail.parse(_espn_report(star_id), now)
    q = match.attach(props.prop_quotes([_event()], source.LEAGUES["nba"], now), _pairs())
    plain = props.expectations(q, {"nba": snap}).set_index(["player", "stat", "line", "side"])
    e = props.expectations(q, {"nba": snap}, report).set_index(["player", "stat", "line", "side"])
    star = ("BOS Player 0", "points", 14.5)
    # Out: the venue settles a non-player at the last fair price, so Atlas's probability is the market's,
    # less the 3% chance he plays after all.
    assert abs(e.loc[(*star, "over"), "p_atlas"] - 0.5) < 0.03 < abs(plain.loc[(*star, "over"), "p_atlas"] - 0.5)
    assert e.loc[(*star, "over"), "p_atlas"] + e.loc[(*star, "under"), "p_atlas"] == pytest.approx(1.0)
    assert e.loc[(*star, "over"), "atlas_mean"] == plain.loc[(*star, "over"), "atlas_mean"]   # when he plays
    assert e.loc[(*star, "over"), "status"] == "out" and plain.loc[(*star, "over"), "status"] == ""
    laker = ("LAL Player 1", "rebounds", 5.5)
    assert abs(e.loc[(*laker, "over"), "p_atlas"] - 0.5) < abs(plain.loc[(*laker, "over"), "p_atlas"] - 0.5)
    assert e.loc[(*laker, "over"), "status"] == "day-to-day"
    row = next(x for x in props.price(e.reset_index(), None).itertuples() if x.player == "BOS Player 0" and x.side == "over")
    assert props._atlas(row).endswith(" · out")

    # The run captures the report itself unless one is given or it is offline; here it is given.
    monkeypatch.setenv("ATLAS_OFFLINE", "1")
    monkeypatch.setenv("ATLAS_TRACKING_DIR", str(tmp_path / "tracking"))
    monkeypatch.setattr(props, "path", lambda: tmp_path / "positions")
    store = Store.open(tmp_path / "tracking")
    secs, summary = props.refresh(store, {"nba": [_event()]}, _pairs(), now, "pass", snaps={"nba": snap, "nhl": None, "nfl": None},
                                  results=props.results_frame("nba", p), availability=report)
    assert summary["listed"] == 2 and summary["contracts"] == 4
    kept = store.read("polymarket_props")
    assert set(kept[kept["player"] == "BOS Player 0"]["status"]) == {"out"}
    assert store.append_new_only("nba_availability", report) == 3 and len(store.read("nba_availability")) == 3
    assert store.append_new_only("nba_availability", report) == 0                           # a re-read adds nothing


def test_the_combined_and_defensive_props_are_read_and_priced(tables):
    from atlas.polymarket import match

    p, tg = tables
    now = datetime(2025, 3, 1, 15, 0, tzinfo=UTC)
    snap = npr.snapshot(p, tg, datetime(2025, 3, 1, tzinfo=UTC), npr.Spec())
    ev = us.event("7001", "nba-lal-bos-2025-03-02", LAL, BOS, [
        us.market(1, "basketball_player_points_rebounds_assists",
                  "Will BOS Player 0 record at least 25 combined points, rebounds and assists in LAL vs. BOS?",
                  "Yes", "No", 0.49, 0.51, line=25, long_team=BOS["id"], short_team=BOS["id"], start=TIP),
        us.prop(2, "basketball_player_steals", "BOS Player 0", 1, 0.59, 0.61, team=BOS, start=TIP),
        us.prop(3, "basketball_player_blocks", "LAL Player 1", 1, 0.39, 0.41, team=LAL, start=TIP),
        us.prop(4, "basketball_player_points", "BOS Player 0", 15, 0.49, 0.51, team=BOS, start=TIP)], start=TIP)
    q = props.prop_quotes([ev], source.LEAGUES["nba"], now)
    assert set(q["stat"]) == {"pra", "steals", "blocks", "points"} and len(q) == 8
    by = q.set_index(["player", "stat", "line", "side"])
    assert by.loc[("BOS Player 0", "pra", 24.5, "over"), "ask"] == 0.51
    e = props.expectations(match.attach(q, _pairs()), {"nba": snap, "nhl": None, "nfl": None})
    by = e.set_index(["player", "stat", "line", "side"])
    star = npr.expect(snap, snap["players"].set_index("player").loc["BOS Player 0"], 2, 13, True)
    assert by.loc[("BOS Player 0", "pra", 24.5, "over"), "atlas_mean"] == pytest.approx(star["pra"])
    assert by.loc[("BOS Player 0", "pra", 24.5, "over"), "atlas_mean"] \
        == pytest.approx(by.loc[("BOS Player 0", "points", 14.5, "over"), "atlas_mean"] + star["rebounds"] + star["assists"])
    for key in (("BOS Player 0", "pra", 24.5), ("BOS Player 0", "steals", 0.5), ("LAL Player 1", "blocks", 0.5)):
        assert 0 < by.loc[(*key, "over"), "p_atlas"] < 1
        assert by.loc[(*key, "over"), "p_atlas"] + by.loc[(*key, "under"), "p_atlas"] == pytest.approx(1.0)
    # Graded from the box score: the combined stat is the sum of the three.
    results = props.results_frame("nba", p)
    assert {"steals", "blocks", "pra"} <= set(results.columns)
    game = p[(p["player"] == "BOS Player 0") & p["played"]].iloc[-1]
    value, played = props._value(results, "nba", str(game["game_id"]), "BOS Player 0", "pra")
    assert played and value == game["points"] + game["rebounds"] + game["assists"]
    assert props._value(results, "nba", str(game["game_id"]), "BOS Player 0", "steals") == (game["steals"], True)
    # A snapshot written before the stats were added prices what it has, and nan for the rest.
    old = {**snap, "layer": {s: snap["layer"][s] for s in ("points", "rebounds", "assists", "threes")},
           "players": snap["players"].drop(columns=["steals_rate", "blocks_rate"]),
           "teams": snap["teams"].drop(columns=["f_allow_steals", "f_allow_blocks"])}
    e_old = props.expectations(match.attach(q, _pairs()), {"nba": old, "nhl": None, "nfl": None}).set_index(["player", "stat", "line", "side"])
    assert e_old.loc[("BOS Player 0", "points", 14.5, "over"), "atlas_mean"] == pytest.approx(star["points"])
    assert np.isnan(e_old.loc[("BOS Player 0", "steals", 0.5, "over"), "p_atlas"])
    assert np.isnan(e_old.loc[("BOS Player 0", "pra", 24.5, "over"), "p_atlas"])
