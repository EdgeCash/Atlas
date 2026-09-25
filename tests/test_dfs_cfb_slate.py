"""College DFS, step 5: who records a stat, and the live college slates."""

from __future__ import annotations

import json

import pandas as pd
import pytest

from atlas.dfs import cfb_participation as part
from atlas.dfs import cfb_slate, owner, slate


def _table():
    """One team's five games: a starter in all of them, a backup in two."""
    rows = []
    for k in range(5):
        event = str(100 + k)
        rows.append({"team": "OSU", "event": event, "season": 2025, "order": 2025000 + k + 1, "player_id": "1",
                     "position": "QB", "dk_points": 20.0 + k, "name": "Julian Sayin"})
        if k in (1, 3):
            rows.append({"team": "OSU", "event": event, "season": 2025, "order": 2025000 + k + 1, "player_id": "2",
                         "position": "QB", "dk_points": 2.0, "name": "Lincoln Kienholz"})
    return pd.DataFrame(rows)


def test_candidates_read_only_earlier_games():
    table = _table()
    upcoming = pd.DataFrame([{"team": "OSU", "event": "200", "season": 2025, "order": 2025010}])
    c = part.candidates(table, upcoming).set_index(["event", "player_id"])
    # Game 3 (k=2): the backup played once in two games before it.
    assert c.loc[("102", "2"), ["played_4", "played_last", "games_since", "career", "played"]].tolist() == [1, 1, 1, 1, 0]
    assert c.loc[("103", "2"), "played"] == 1
    # The coming game: both are candidates, neither has an outcome.
    coming = c.loc["200"]
    assert set(coming.index) == {"1", "2"} and coming["played"].sum() == 0
    assert coming.loc["1", "played_4"] == 4 and coming.loc["2", "games_since"] == 2
    assert coming.loc["1", "points_trend"] == pytest.approx((21 + 22 + 23 + 24) / 4)
    assert set(part.FEATURES) <= set(c.columns)


def test_players_match_by_team_then_position_and_never_twice():
    table = pd.DataFrame([
        {"season": 2025, "order": 2025001, "player_id": "1", "name": "Julian Sayin", "team": "OSU", "position": "QB"},
        {"season": 2025, "order": 2025001, "player_id": "2", "name": "Jeremiah Smith", "team": "OSU", "position": "WR"},
        {"season": 2025, "order": 2025001, "player_id": "3", "name": "Transfer Back", "team": "UGA", "position": "RB"},
        {"season": 2020, "order": 2020001, "player_id": "4", "name": "Long Gone", "team": "OSU", "position": "RB"},
    ])
    pool = pd.DataFrame([
        {"player_id_dk": 11, "name": "Julian Sayin", "espn_team": "OSU", "position": "QB"},
        {"player_id_dk": 12, "name": "Jeremiah Smith", "espn_team": "OSU", "position": "WR"},
        {"player_id_dk": 13, "name": "Transfer Back", "espn_team": "LSU", "position": "RB"},    # moved schools
        {"player_id_dk": 14, "name": "Long Gone", "espn_team": "OSU", "position": "RB"},        # too long ago
        {"player_id_dk": 15, "name": "Jeremiah Smith", "espn_team": "MIA", "position": "WR"},   # a namesake
    ])
    got = cfb_slate.match_players(pool, table).set_index("player_id_dk")
    assert got.loc[11, "player_id"] == "1" and got.loc[11, "matched_by"] == "name and team"
    assert got.loc[13, "player_id"] == "3" and got.loc[13, "matched_by"] == "name and position"
    assert got.loc[14, "player_id"] == "DKC-14"
    assert got.loc[12, "player_id"] == "2" and got.loc[15, "player_id"] == "DKC-15"     # one record, one player
    assert got["player_id"].is_unique


def test_games_match_by_both_teams_within_a_day_and_a_half():
    pool = pd.DataFrame([
        {"team": "Ohio St.", "game": "Texas @ Ohio St.", "game_start": "2026-09-26T16:00:00Z"},
        {"team": "Texas", "game": "Texas @ Ohio St.", "game_start": "2026-09-26T16:00:00Z"},
        {"team": "Navy", "game": "Navy @ UAB", "game_start": "2026-09-26T16:00:00Z"},
    ])
    teams = {"Ohio St.": "OSU", "Texas": "TEX", "Navy": "NAVY", "UAB": "UAB"}
    events = pd.DataFrame([
        {"event": "401", "week": 5, "season_type": "regular", "home": "OSU", "away": "TEX",
         "date": "2026-09-26T16:00Z"},
        {"event": "402", "week": 9, "season_type": "regular", "home": "UAB", "away": "NAVY",
         "date": "2026-10-24T16:00Z"},                                                 # the rematch, weeks away
    ])
    got = cfb_slate.match_games(pool, teams, events)
    assert got["event"].tolist()[:2] == ["401", "401"] and pd.isna(got.loc[2, "event"])
    assert got.loc[0, "espn_home"] == "OSU" and got.loc[1, "espn_team"] == "TEX"


class _Store:
    def __init__(self, snaps):
        self.snaps = snaps

    def read(self, name):
        return self.snaps


def test_live_line_splits_into_each_teams_points():
    snaps = pd.DataFrame([
        {"captured_at": "2026-09-24T10:00Z", "game_id": 401, "book": "A", "market": "margin", "line": 3.0},
        {"captured_at": "2026-09-24T12:00Z", "game_id": 401, "book": "A", "market": "margin", "line": 7.0},
        {"captured_at": "2026-09-24T12:00Z", "game_id": 401, "book": "A", "market": "total", "line": 51.0},
    ])
    events = pd.DataFrame([{"event": "401", "home": "OSU", "away": "TEX"}])
    env = cfb_slate.live_environment(_Store(snaps), events).set_index("team")
    assert env.loc["OSU", "team_pts"] == pytest.approx(29.0) and env.loc["TEX", "team_pts"] == pytest.approx(22.0)
    assert env.loc["TEX", "proj_margin"] == pytest.approx(-7.0) and env.loc["OSU", "proj_total"] == 51.0


def test_college_slates_run_without_an_nfl_one(tmp_path, monkeypatch):
    monkeypatch.setattr(slate, "index_path", lambda: tmp_path / "index.json")
    monkeypatch.setattr("atlas.live.store.Store.open", classmethod(lambda cls: None))
    monkeypatch.setattr(slate, "_nfl", lambda store, now: [])
    monkeypatch.setattr(slate, "_cfb", lambda store, now: [{"draft_group_id": 1, "game_type": "Classic",
                                                            "label": "Main", "sport": "cfb", "lineups": 5}])
    index = json.loads(slate.run_all().read_text())
    assert [s["sport"] for s in index["slates"]] == ["cfb"]
    monkeypatch.setattr(slate, "_cfb", lambda store, now: [])
    with pytest.raises(slate.NoSlate):
        slate.run_all()


def test_a_college_failure_never_costs_the_nfl(tmp_path, monkeypatch):
    from atlas.dfs import cfb_players

    monkeypatch.setattr(cfb_players, "path", lambda: tmp_path / "table.parquet")
    assert slate._cfb(None, None) == []                                      # no table yet
    (tmp_path / "table.parquet").write_text("")

    def boom(store, now=None):
        raise ValueError("a player appears twice in the pool")

    monkeypatch.setattr(cfb_slate, "run", boom)
    assert slate._cfb(None, None) == []


def _write_slate(root, group, meta, players):
    out = root / str(group)
    out.mkdir()
    (out / "slate.json").write_text(json.dumps(meta))
    pd.DataFrame(players).to_csv(out / "projections.csv", index=False)
    pd.DataFrame([{"lineup": 1, "slot": "QB", "name": players[0]["name"], "team": players[0]["team"],
                   "salary": 8000, "projection": 20.0, "low": 5.0, "high": 30.0}]).to_csv(out / "lineups.csv",
                                                                                         index=False)
    (out / "lineups_upload.csv").write_text("QB\n1\n")


def test_owner_payload_carries_both_sports(tmp_path):
    player = {"position": "QB", "opponent": "X", "salary": 8000, "status": None, "projection": 20.0, "low": 5.0,
              "high": 30.0, "p_play": 0.9, "game_start": "2026-09-26T16:00:00Z"}
    college = {"draft_group_id": 2, "game_type": "Classic", "label": "Main", "sport": "cfb",
               "starts_at": "2026-09-26T16:00:00+00:00"}
    nfl = {"draft_group_id": 1, "game_type": "Classic", "label": "Main", "sport": "nfl",
           "starts_at": "2026-09-27T17:00:00+00:00"}
    # The college pool is the bigger one; the NFL's still leads.
    _write_slate(tmp_path, 2, college, [{**player, "name": f"College {i}", "team": "OSU"} for i in range(3)])
    _write_slate(tmp_path, 1, nfl, [{**player, "name": "Josh Allen", "team": "BUF"}])
    (tmp_path / "index.json").write_text(json.dumps({"slates": [college, nfl]}))
    data = owner.payload(tmp_path / "index.json")
    assert data["draft_group_id"] == 1 and data["players"][0]["name"] == "Josh Allen"
    assert [p["name"] for p in data["college_players"]] == ["College 0", "College 1", "College 2"]
    assert [s["sport"] for s in data["slates"]] == ["cfb", "nfl"]

    (tmp_path / "index.json").write_text(json.dumps({"slates": [college]}))
    alone = owner.payload(tmp_path / "index.json")
    assert alone["players"][0]["name"] == "College 0" and "college_players" not in alone


def test_the_college_quarterback_of_record_and_his_state():
    """The passer with the most attempts is the quarterback of record; a new starter enters at the prior."""
    import numpy as np

    from atlas.models import kalman
    from atlas.models import ncaaf_qb as nq

    box = pd.DataFrame([
        {"event": "1", "home": 1, "player_id": "a", "pass_att": 30, "pass_yds": 250},
        {"event": "1", "home": 1, "player_id": "b", "pass_att": 3, "pass_yds": 20},
        {"event": "1", "home": 0, "player_id": "c", "pass_att": 25, "pass_yds": 200},
    ])
    assert nq.quarterbacks(box).iloc[0][["home_qb_id", "away_qb_id"]].tolist() == ["a", "c"]

    kick = pd.Timestamp("2025-09-06", tz="UTC")
    games = pd.DataFrame([{"game_id": f"g{w}", "week": w, "kickoff": kick + pd.Timedelta(days=7 * w),
                           "home_team_id": 1, "away_team_id": 2, "home_qb_id": qb, "away_qb_id": "c",
                           "actual_margin": 0.0, "actual_total": 50.0, "neutral_site": 1}
                          for w, qb in ((1, "a"), (2, "a"), (3, "new"), (4, "new"))])
    spec = kalman.Spec(q_off=0.0, q_def=0.0, p0_off=4.0, p0_def=4.0, sigma=10.0, base=25.0, boost=2.0)
    state = kalman.initialise(np.array([1, 2]), np.zeros(2), np.zeros(2), spec)
    fc = nq.run_season_qb(games, state, spec, p0=4.0, new_mean=-4.0)
    assert state.value(("qb", "a")) == pytest.approx(0.0, abs=1.0)          # the first starter: the prior's
    assert state.value(("qb", "new")) < -2.0                                # a change enters at the backup's price
    assert fc.loc[3, "mean"] < fc.loc[2, "mean"] - 1.0                      # and is forecast with him next
