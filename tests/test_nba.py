"""The NBA: the staging's conventions, the state model walk-forward, the projector, and its place in the
live tracker and on Polymarket, on a synthetic hoopR tree."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pytest

from atlas.models import nba_projection as pj
from atlas.models import nba_state as ns
from atlas.research.nba_dataset import load_nba_frame, research_sample
from atlas.sources import nba
from atlas.staging.nba import build as nba_build
from atlas.staging.nba import games as nba_games
from atlas.testing.synthetic_nba import TEAMS, WEEKS, write_synthetic_nba_raw

SEASONS = [2022, 2023, 2024]
SMALL_GRID = {"q": (0.0, 1.0), "phi": (0.7,), "p_season": (30.0,), "sigma": (10.0,)}


@pytest.fixture(scope="module")
def nba_tree(tmp_path_factory):
    base = tmp_path_factory.mktemp("nba_data")
    write_synthetic_nba_raw(base / "raw", SEASONS)
    return base


@pytest.fixture(scope="module")
def nba_frame(nba_tree):
    old = os.environ.get("ATLAS_DATA_DIR")
    os.environ["ATLAS_DATA_DIR"] = str(nba_tree)
    os.environ["ATLAS_OFFLINE"] = "1"
    try:
        nba_build.build(SEASONS)
        frame = load_nba_frame(nba_tree / "warehouse")
    finally:
        if old is None:
            os.environ.pop("ATLAS_DATA_DIR", None)
        else:
            os.environ["ATLAS_DATA_DIR"] = old
    return frame


def test_games_follow_atlas_conventions(nba_frame):
    g = nba_frame
    assert set(g["season"]) == set(SEASONS)                                    # the start year, not hoopR's
    assert "EAST" not in set(g["home_abbr"]) and (g["home_team_id"] != 999).all()  # the All-Star game is dropped
    assert set(g["season_type"]) == {"regular", "postseason"}
    assert g["week"].min() == 1 and g["week"].max() == WEEKS
    assert g["kickoff"].dt.tz is not None
    done = g[g["completed"]]
    assert (done["actual_margin"] == done["home_score"] - done["away_score"]).all()
    assert g[~g["completed"]]["actual_margin"].isna().all() and (~g["completed"]).sum() == 8
    # The archive's close is joined by date and both sides, as the home handicap: negative when home is favoured.
    with_close = g[g["closing_spread"].notna()]
    assert set(with_close["season"]) == set(SEASONS[:-1]) and with_close["closing_total"].iloc[0] == 225.5
    assert (g["market_margin"] == -g["closing_spread"]).where(g["closing_spread"].notna(), True).all()
    # Seattle in the first season is Oklahoma City's franchise.
    first = g[g["season"] == SEASONS[0]]
    assert "SEA" in set(first["home_abbr"]) | set(first["away_abbr"]) and 25 in set(first["home_team_id"])
    assert g["home_b2b"].dtype == bool and g["home_days_rest"].dropna().min() >= 1


def test_the_odds_archive_parses_the_spread_and_the_total_from_one_column():
    html = """<table><tr><th>Date</th></tr>
    <tr><td>1018</td><td>501</td><td>V</td><td>Philadelphia</td><td>29</td><td>34</td><td>25</td><td>29</td><td>117</td><td>229</td><td>216</td><td>135</td><td>107</td></tr>
    <tr><td>1018</td><td>502</td><td>H</td><td>Boston</td><td>24</td><td>39</td><td>35</td><td>28</td><td>126</td><td>7</td><td>3</td><td>-155</td><td>2</td></tr>
    <tr><td>116</td><td>517</td><td>V</td><td>Houston</td><td>35</td><td>26</td><td>37</td><td>34</td><td>132</td><td>234.5</td><td>236.5</td><td>240</td><td>116</td></tr>
    <tr><td>116</td><td>518</td><td>H</td><td>LALakers</td><td>37</td><td>36</td><td>29</td><td>38</td><td>140</td><td>0.5</td><td>pk</td><td>-280</td><td>pk</td></tr>
    </table>"""
    o = nba.parse_odds(html, 2022)
    assert len(o) == 2 and o["date"].tolist() == ["2022-10-18", "2023-01-16"]
    assert o.loc[0, "home"] == "BOS" and o.loc[0, "away"] == "PHI"
    assert o.loc[0, "closing_spread"] == -3.0 and o.loc[0, "closing_total"] == 216.0 and o.loc[0, "opening_spread"] == -7.0
    assert o.loc[0, "home_ml_close"] == -155.0 and o.loc[0, "away_ml_close"] == 135.0
    assert o.loc[1, "closing_spread"] == 0.0 and o.loc[1, "closing_total"] == 236.5
    assert nba.current_season(datetime(2026, 10, 23).date()) == 2026 and nba.current_season(datetime(2026, 7, 1).date()) == 2025
    assert nba.file_season(2025) == 2026 and nba.odds_slug(2022) == "2022-23"


def test_the_warehouse_holds_team_games_with_possessions(nba_tree, nba_frame):
    t = nba_games.team_games(nba_tree / "raw", SEASONS)
    assert len(t) == 2 * int(nba_frame["completed"].sum())
    assert np.allclose(t["possessions"], 88 - 10 + 14 + 0.44 * 22)
    assert t["points_per_100"].between(60, 200).all()


def test_the_state_runs_walk_forward_and_beats_naive(nba_frame):
    scored, choices, finals, table = ns.walk_forward(nba_frame, first_test_season=SEASONS[1], grid=SMALL_GRID,
                                                     min_train_seasons=1)
    assert set(choices) == {SEASONS[1]}                                         # the one scored season with a close
    pooled = ns.evaluate.summarise(scored[scored["season_type"] == "regular"], order=ns.ORDER).set_index("model")
    assert {"naive", "elo", "market", "state"} <= set(pooled.index)
    assert pooled.loc["state", "crps"] < pooled.loc["naive", "crps"]
    assert len(finals[SEASONS[1]].frame()) == len(TEAMS)
    assert table["p_cover"].between(0, 1).all() and table["p_over"].between(0, 1).all()
    assert (table["total_mean"] > 150).all()
    cal = ns.calibration(table)
    assert set(cal["market"]) == {"margin", "total"} and (cal["sport"] == "nba").all()
    assert cal["claimed"].between(0.5, 1).all() and cal["won"].isin([0.0, 0.5, 1.0]).all()
    text = ns.render(scored, choices, table)
    assert "## The record at the close" in text and "### Total" in text and "## Hyperparameters" in text


def test_choices_round_trip(tmp_path):
    choices = {2023: ns.Choice(1.0, 0.7, 30.0, 10.0, -12.5, (2020, 2021, 2022), 0.1)}
    ns.save_choices(choices, tmp_path / "c.json")
    back = ns.load_choices(tmp_path / "c.json")
    assert back == choices and json.loads((tmp_path / "c.json").read_text())["2023"]["rho"] == 0.1
    assert ns.load_choices(tmp_path / "missing.json") is None


def test_the_projector_projects_the_games_ahead_keyed_by_espns_id(nba_frame):
    choices = {SEASONS[2]: ns.Choice(1.0, 0.7, 30.0, 10.0, 0.0, (SEASONS[0], SEASONS[1]))}
    projector = pj.fit(nba_frame, choices=choices)
    assert projector.season == SEASONS[2] and projector.assimilated > 0
    kick = pd.to_datetime(nba_frame["kickoff"], utc=True)
    now = nba_frame[nba_frame["actual_margin"].notna()]["kickoff"].max()
    scheduled = pj.ahead(nba_frame, now, projector.season)
    assert len(scheduled) == 8 and (kick[scheduled.index] > now).all()
    out = pj.project(projector, scheduled)
    assert len(out) == 8 and (out["sport"] == "nba").all()
    assert set(out["game_id"]) == set(scheduled["espn_id"].astype(int))
    assert (out["home_mean"] + out["away_mean"] - out["total_mean"]).abs().max() < 1e-6
    assert ((out["p_home"] > 0) & (out["p_home"] < 1)).all() and out["total_mean"].between(180, 260).all()
    assert out["home_rank"].between(1, len(TEAMS)).all() and out["teams"].iloc[0] == len(TEAMS)
    assert out["margin_sd"].between(8, 25).all() and (out["total_lo"] < out["total_mean"]).all()
    # The projections table's columns are all there for the store.
    from atlas.live.store import SCHEMA

    missing = set(SCHEMA["projections"]) - set(out.columns) - {"refreshed_at"}
    assert missing <= {"home_qb", "home_qb_pts", "home_qb_sd", "away_qb", "away_qb_pts", "away_qb_sd"}
    # Nothing ahead: nothing projected.
    assert pj.project(projector, scheduled.iloc[0:0]).empty


def test_the_calibration_rows_price_the_football_way_on_polymarket(nba_frame, tmp_path):
    """An NBA contract is priced in centre space like football's, from the record's share."""
    from atlas.polymarket import match, pricing, source

    _, _, _, table = ns.walk_forward(nba_frame, first_test_season=SEASONS[1], grid=SMALL_GRID, min_train_seasons=1)
    cal = ns.calibration(table)
    k, n = pricing.share(cal, "nba", "spread")
    margin = cal[(cal["market"] == "margin") & (cal["season_type"] == "regular") & (cal["won"] != 0.5)]
    assert n == len(margin) and 0.0 <= k <= 1.0
    assert pricing.edge_curve(cal, "nba") is None                                    # thin: no curve on a toy league
    league = source.LEAGUES["nba"]
    ev = {"id": "9001", "slug": "nba-lal-bos-2026-10-24", "title": "Lakers vs. Celtics", "markets": [
        {"id": "1", "question": "Lakers vs. Celtics", "sportsMarketType": "moneyline", "outcomes": '["Lakers", "Celtics"]',
         "outcomePrices": '["0.4", "0.6"]', "clobTokenIds": '["a", "b"]', "conditionId": "0x1", "bestBid": 0.39,
         "bestAsk": 0.41, "spread": 0.02, "gameStartTime": "2026-10-24 23:30:00+00", "feesEnabled": True,
         "feeSchedule": {"rate": 0}, "liquidityNum": 50000.0, "acceptingOrders": True, "active": True, "closed": False},
        {"id": "2", "question": "Spread: Celtics (-4.5)", "sportsMarketType": "spreads", "line": -4.5,
         "outcomes": '["Celtics", "Lakers"]', "outcomePrices": '["0.5", "0.5"]', "clobTokenIds": '["c", "d"]',
         "conditionId": "0x2", "bestBid": 0.49, "bestAsk": 0.51, "spread": 0.02, "gameStartTime": "2026-10-24 23:30:00+00",
         "feesEnabled": True, "feeSchedule": {"rate": 0}, "liquidityNum": 50000.0, "acceptingOrders": True,
         "active": True, "closed": False},
        {"id": "3", "question": "Lakers vs. Celtics: O/U 225.5", "sportsMarketType": "totals", "line": 225.5,
         "outcomes": '["Over", "Under"]', "outcomePrices": '["0.5", "0.5"]', "clobTokenIds": '["e", "f"]',
         "conditionId": "0x3", "bestBid": 0.49, "bestAsk": 0.51, "spread": 0.02, "gameStartTime": "2026-10-24 23:30:00+00",
         "feesEnabled": True, "feeSchedule": {"rate": 0}, "liquidityNum": 50000.0, "acceptingOrders": True,
         "active": True, "closed": False}]}
    now = datetime(2026, 10, 24, 14, 0, tzinfo=UTC)
    q = source.quotes([ev], league, now)
    assert set(q["side"]) == {"away", "home", "over", "under"} and (q["fee_rate"] == 0.0).all()
    assert q.set_index(["market", "side"]).loc[("spread", "home"), "line"] == -4.5        # the named team's handicap
    games = pd.DataFrame([{"game_id": "401", "sport": "nba", "kickoff": "2026-10-24T23:30Z", "home_team": "Boston Celtics",
                           "away_team": "Los Angeles Lakers", "season": 2026, "week": 1}])
    pairs = match.match(q, games)
    assert pairs["game_id"].tolist() == ["401"]
    proj = pd.DataFrame([{"game_id": 401, "sport": "nba", "season": 2026, "week": 1, "kickoff": "2026-10-24T23:30Z",
                          "margin_mean": 6.0, "margin_sd": 13.0, "total_mean": 232.0, "total_sd": 18.0,
                          "total_over_shrink": np.nan, "total_over_sd": np.nan, "p_home": 0.67, "model_version": "n1",
                          "refreshed_at": "2026-10-24T08:00:00+00:00"}])
    priced = pricing.price(match.attach(q, pairs), proj, None, {}, cal).set_index(["market", "side"])
    assert priced.loc[("total", "over"), "centre_market"] == pytest.approx(225.5, abs=0.5)
    assert priced.loc[("total", "over"), "centre_atlas"] == 232.0
    assert priced.loc[("total", "over"), "p_raw"] > 0.5 and priced.loc[("spread", "home"), "p_raw"] > 0.5
    assert priced["p"].between(0, 1).all() and (priced["fee"] == 0.0).all()


def test_the_live_tracker_knows_the_nba():
    from atlas.live import probability, provider
    from atlas.ops import schedule

    assert "espn-nba" in provider.POLLED and provider.get_provider("espn-nba").sport == "nba"
    assert provider._season({"season": {"year": 2027}}, "nba") == 2026 and provider._season({"season": {"year": 2026}}, "nfl") == 2026
    assert probability.SUPPORT.max() >= 300 and probability.default_shape("nba", "total").sigma == 18.0
    from zoneinfo import ZoneInfo

    et = ZoneInfo("America/New_York")
    assert schedule.game_day(datetime(2026, 11, 8, 21, 0, tzinfo=et)).name == "NBA Sunday night"
    assert schedule.game_day(datetime(2026, 9, 27, 21, 0, tzinfo=et)) is None       # not in September


def test_the_research_sample_keeps_the_games_the_archive_prices(nba_frame):
    s = research_sample(nba_frame)
    assert s["closing_spread"].notna().all() and set(s["season"]) == set(SEASONS[:-1])
    assert len(research_sample(nba_frame, require_market=False)) == int(nba_frame["completed"].sum())
