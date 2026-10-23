"""NBA player props: the staging, the model, and their place on Polymarket, on the synthetic hoopR tree."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pytest

from atlas.models import nba_props as npr
from atlas.polymarket import positions, props, source
from atlas.research.nba_dataset import load_table
from atlas.staging.nba import build as nba_build
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
    assert {"points", "rebounds", "assists", "threes", "is_home", "opponent_id"} <= set(p.columns)


def test_the_model_walks_forward_and_beats_the_season_mean(tables):
    p, tg = tables
    rows, layers = npr.walk(p, tg, npr.Spec(), [SEASONS[2]])
    assert set(layers) == {SEASONS[2]} and all(layers[SEASONS[2]][s]["dispersion"] >= 1.0 for s in npr.STATS)
    assert (rows[["mu_points", "mu_rebounds", "mu_assists", "mu_threes"]] > 0).all().all()
    table = npr.score(rows, layers)
    assert len(table) == sum(len(v) for v in npr.LINES.values())
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
    assert set(e) == set(npr.STATS)
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


def _event(line=14.5, mid=0.5, liq=5000.0, question="BOS Player 0: Points O/U 14.5", kind="points"):
    return {"id": "7001", "slug": "nba-lal-bos-2025-03-02", "title": "Lakers vs. Celtics", "markets": [
        {"id": "1", "question": question, "sportsMarketType": kind, "line": line, "outcomes": '["Yes", "No"]',
         "outcomePrices": f'["{mid}", "{1 - mid}"]', "clobTokenIds": '["p1", "p2"]', "conditionId": "0xp1",
         "bestBid": round(mid - 0.01, 3), "bestAsk": round(mid + 0.01, 3), "spread": 0.02,
         "gameStartTime": "2025-03-02 00:30:00+00", "feesEnabled": True, "feeSchedule": {"rate": 0},
         "liquidityNum": liq, "acceptingOrders": True, "active": True, "closed": False},
        {"id": "2", "question": "BOS Player 0: Points O/U 19.5", "sportsMarketType": "points", "line": 19.5,
         "outcomes": '["Yes", "No"]', "outcomePrices": '["0.2", "0.8"]', "clobTokenIds": '["p3", "p4"]',
         "conditionId": "0xp2", "bestBid": 0.19, "bestAsk": 0.21, "spread": 0.02,
         "gameStartTime": "2025-03-02 00:30:00+00", "feesEnabled": True, "feeSchedule": {"rate": 0},
         "liquidityNum": 3000.0, "acceptingOrders": True, "active": True, "closed": False},
        {"id": "3", "question": "LAL Player 1: Rebounds O/U 5.5", "sportsMarketType": "rebounds", "line": 5.5,
         "outcomes": '["Yes", "No"]', "outcomePrices": '["0.5", "0.5"]', "clobTokenIds": '["p5", "p6"]',
         "conditionId": "0xp3", "bestBid": 0.49, "bestAsk": 0.51, "spread": 0.02,
         "gameStartTime": "2025-03-02 00:30:00+00", "feesEnabled": True, "feeSchedule": {"rate": 0},
         "liquidityNum": 8000.0, "acceptingOrders": True, "active": True, "closed": False},
        {"id": "4", "question": "Nobody Known: Assists O/U 3.5", "sportsMarketType": "assists", "line": 3.5,
         "outcomes": '["Yes", "No"]', "outcomePrices": '["0.5", "0.5"]', "clobTokenIds": '["p7", "p8"]',
         "conditionId": "0xp4", "bestBid": 0.49, "bestAsk": 0.51, "spread": 0.02,
         "gameStartTime": "2025-03-02 00:30:00+00", "feesEnabled": True, "feeSchedule": {"rate": 0},
         "liquidityNum": 8000.0, "acceptingOrders": True, "active": True, "closed": False},
        {"id": "5", "question": "Lakers vs. Celtics", "sportsMarketType": "moneyline", "outcomes": '["Lakers", "Celtics"]',
         "outcomePrices": '["0.4", "0.6"]', "clobTokenIds": '["g1", "g2"]', "conditionId": "0xg", "bestBid": 0.39,
         "bestAsk": 0.41, "spread": 0.02, "gameStartTime": "2025-03-02 00:30:00+00", "feesEnabled": True,
         "feeSchedule": {"rate": 0}, "liquidityNum": 50000.0, "acceptingOrders": True, "active": True, "closed": False},
    ]}


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
    assert (q["fee_rate"] == 0.0).all() and q["away"].iloc[0] == "Lakers" and q["home"].iloc[0] == "Celtics"
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
    e = props.expectations(q, snap)
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
    q = props.expectations(match.attach(props.prop_quotes([_event()], source.LEAGUES["nba"], now), _pairs()), snap)
    kept = props.main_lines(q[q["game_id"].notna()])
    record, added = source.fold(store.read("polymarket_props"), kept.reindex(columns=props.PROP_COLUMNS),
                                cols=props.PROP_COLUMNS)
    assert added == 6
    store.write("polymarket_props", record)
    back = store.read("polymarket_props")
    assert (back["game_id"].astype(str) == "901").all()
    # Before the game, nothing to grade; after it, with a box score, the over side is graded.
    results = pd.DataFrame([{"game_id": "901", "player_key": "bos player 0", "played": True, "points": 22.0,
                             "rebounds": 5.0, "assists": 2.0, "threes": 1.0},
                            {"game_id": "901", "player_key": "lal player 1", "played": False, "points": 0.0,
                             "rebounds": 0.0, "assists": 0.0, "threes": 0.0}])
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


def test_refresh_reads_grades_prices_and_seals_offline(tables, tmp_path, monkeypatch):
    p, tg = tables
    now = datetime(2025, 3, 1, 15, 0, tzinfo=UTC)
    snap = npr.snapshot(p, tg, now, npr.Spec())
    from atlas.live.store import Store

    monkeypatch.setenv("ATLAS_OFFLINE", "1")
    store = Store.open(tmp_path / "tracking")
    monkeypatch.setattr(props, "path", lambda: tmp_path / "prop_positions")
    sections, summary = props.refresh(store, [_event()], _pairs(), now, KEY, snap=snap, player_games=p)
    assert summary["contracts"] == 4 and summary["games"] == 1 and summary["projected"] == 3
    assert [s["title"] for s in sections][:2] == ["Prop positions for Sat Mar 1 (0)", "Props board"]
    board = sections[1]["tables"][0]
    assert board["rows"] and "Atlas" in board["rows"][0][1][1]
    assert json.dumps(sections)
    assert len(store.read("polymarket_props")) == 6 and store.read("prop_record").empty
    # Without a snapshot the step says so and keeps nothing.
    monkeypatch.setattr(npr, "load_state", lambda *a, **k: None)
    empty, _ = props.refresh(store, [_event()], _pairs(), now, KEY)
    assert "No NBA player snapshot yet" in empty[0]["notes"][0]


def test_grading_positions_pushes_a_player_who_did_not_play():
    record = pd.DataFrame([{**dict.fromkeys(props.POSITION_COLUMNS), "position_id": "x", "game_id": "901",
                            "kickoff": "2025-03-02T00:30:00Z", "player": "LAL Player 1", "stat": "rebounds",
                            "side": "over", "line": 5.5, "token_id": "p5", "ask": 0.5, "cost": 0.5, "stake": 0.01}])
    results = pd.DataFrame([{"game_id": "901", "player_key": "lal player 1", "played": False, "points": 0.0,
                             "rebounds": 0.0, "assists": 0.0, "threes": 0.0}])
    g = props.grade_positions(record, results, pd.DataFrame(columns=props.PROP_COLUMNS),
                              datetime(2025, 3, 2, 5, 0, tzinfo=UTC))
    assert g["outcome"].iloc[0] == "push" and g["pnl"].iloc[0] == 0.0
    played = results.assign(played=True, rebounds=7.0)
    assert props.grade_positions(record, played, pd.DataFrame(columns=props.PROP_COLUMNS),
                                 datetime(2025, 3, 2, 5, 0, tzinfo=UTC))["outcome"].iloc[0] == "win"
