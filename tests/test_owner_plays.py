"""The owner's curated plays: a frozen rule, plays logged once before kickoff, graded, sealed."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pandas as pd
import pytest

from atlas.live.store import Store
from atlas.owner import plays, sealed

KEY = "correct horse battery staple"
NOW = datetime(2026, 9, 25, 12, tzinfo=UTC)


def test_rule_v1_is_frozen():
    """A change to the rule is a new rule, never an edit: this fails if v1 or its history is touched."""
    assert plays.RULE_V1 == plays.Rule(
        id="cfb-total-5-v1", frozen="2026-09-24", sport="ncaaf", market="total", threshold=5.0,
        label="College totals, regular season: Atlas's total 5+ points from the line")
    hist = plays.HISTORY["cfb-total-5-v1"]
    assert [sum(v[0][i] for v in hist.values()) for i in range(3)] == [453, 379, 7]
    assert [sum(v[1][i] for v in hist.values()) for i in range(3)] == [526, 460, 12]


def _projection(game, total, kickoff="2026-09-26T16:00:00Z"):
    return {"game_id": game, "sport": "ncaaf", "season": 2026, "week": 4, "kickoff": kickoff, "total_mean": total,
            "model_version": "m1", "refreshed_at": "2026-09-25T08:00:00+00:00"}


def _snap(game, line, price=-110.0, other=-110.0, at="2026-09-25T08:00:00+00:00"):
    return {"captured_at": at, "game_id": game, "book": "DraftKings", "market": "total", "line": line,
            "price": price, "other_price": other}


def _inputs():
    projections = pd.DataFrame([
        _projection(1, 60.0),                                     # 10 over 50: over
        _projection(2, 40.0),                                     # 10 under 50: under
        _projection(3, 53.0),                                     # 3 over: not enough
        _projection(4, 60.0, kickoff="2026-09-25T10:00:00Z"),      # already started
        _projection(5, 60.0),                                     # a bowl
        _projection(6, 60.0),                                     # no line
    ])
    snapshots = pd.DataFrame([
        _snap(1, 49.0, at="2026-09-24T08:00:00+00:00"), _snap(1, 50.0, price=-115.0),   # the latest line counts
        _snap(2, 50.0, price=-115.0, other=-105.0), _snap(3, 50.0), _snap(4, 50.0), _snap(5, 50.0),
    ])
    games = pd.DataFrame({"game_id": [1, 2], "home_team": ["Miami Hurricanes", "Oregon Ducks"],
                          "away_team": ["Central Michigan Chippewas", "USC Trojans"]})
    types = {"1": "regular", "2": "regular", "3": "regular", "4": "regular", "5": "postseason", "6": "regular"}
    return projections, snapshots, games, types


def test_the_rule_selects_and_prices_the_side_taken():
    got = plays.candidates(plays.RULE_V1, *_inputs(), NOW).set_index("game_id")
    assert sorted(got.index) == [1, 2]
    assert (got.loc[1, "side"], got.loc[1, "line"], got.loc[1, "price"], got.loc[1, "gap"]) == ("over", 50.0, -115.0,
                                                                                                10.0)
    assert (got.loc[2, "side"], got.loc[2, "price"]) == ("under", -105.0)           # the under's own price
    assert got.loc[1, "play_id"] == plays.play_id(plays.RULE_V1, 1)
    assert got.loc[2, "home_team"] == "Oregon Ducks"


def test_a_logged_play_is_never_revised():
    projections, snapshots, games, types = _inputs()
    first = plays.candidates(plays.RULE_V1, projections, snapshots, games, types, NOW)
    record, weeks = plays.log(pd.DataFrame(columns=plays.COLUMNS), first)
    assert len(record) == 2 and weeks == {(2026, 4)}
    # The next morning the line has moved and Atlas has too; game 3 now qualifies.
    later = datetime(2026, 9, 26, 8, tzinfo=UTC)
    moved = pd.concat([snapshots, pd.DataFrame([_snap(1, 52.0, at="2026-09-26T07:00:00+00:00")])])
    projections = projections.assign(total_mean=[58.0, 40.0, 58.0, 60.0, 60.0, 60.0])
    record, weeks = plays.log(record, plays.candidates(plays.RULE_V1, projections, moved, games, types, later))
    got = record.set_index("game_id")
    assert len(record) == 3 and got.loc[1, "line"] == 50.0 and got.loc[1, "atlas_total"] == 60.0
    _, weeks = plays.log(record, plays.candidates(plays.RULE_V1, projections, moved, games, types, later))
    assert weeks == set()


def test_plays_are_graded_at_their_price_and_a_missing_one_is_marked():
    record = pd.DataFrame([
        {**dict.fromkeys(plays.COLUMNS), "play_id": "a", "game_id": 1, "side": "over", "line": 50.0, "price": -115.0},
        {**dict.fromkeys(plays.COLUMNS), "play_id": "b", "game_id": 2, "side": "under", "line": 50.0, "price": None},
        {**dict.fromkeys(plays.COLUMNS), "play_id": "c", "game_id": 3, "side": "under", "line": 50.0, "price": -110.0},
        {**dict.fromkeys(plays.COLUMNS), "play_id": "d", "game_id": 4, "side": "over", "line": 50.0, "price": -110.0},
    ])
    finals = pd.DataFrame({"game_id": ["1", "2", "3"], "final_margin": [0.0] * 3, "final_total": [55.0, 44.0, 50.0]})
    g = plays.graded(record, finals).set_index("play_id")
    assert g["outcome"].to_dict() == {"a": "win", "b": "win", "c": "push", "d": "open"}
    assert g.loc["a", "profit"] == pytest.approx(100 / 115) and g.loc["b", "profit"] == pytest.approx(100 / 110)
    assert bool(g.loc["b", "price_assumed"]) and not bool(g.loc["a", "price_assumed"])


def test_the_plays_are_sealed_and_only_the_owner_key_opens_them(tmp_path):
    store = Store.open(tmp_path / "tracking")
    projections, snapshots, games, _ = _inputs()
    store.write("projections", projections)
    store.write("snapshots", snapshots)
    store.write("games", games.assign(kickoff="2026-09-26T16:00:00Z"))
    research = pd.DataFrame({"game_id": [1, 2, 3, 4, 5, 6], "actual_margin": [None] * 6,
                             "actual_total": [None] * 6,
                             "season_type": ["regular"] * 4 + ["postseason", "regular"]})
    where = tmp_path / "owner_plays"
    out = plays.build(KEY, store=store, research=research, now=NOW, where=where)[0]
    upcoming = out["tables"][0]
    assert upcoming["title"] == "This week: 2 plays"
    assert upcoming["rows"][0][1] == "over 50 (-115)" and "Chippewas @ Hurricanes" in upcoming["rows"][0][0]
    assert "Atlas 60.0" in upcoming["rows"][0][0]
    assert any(t["title"].startswith("History before the freeze") for t in out["tables"])
    text = (where / "2026-04.enc.json").read_text()
    assert "Hurricanes" not in text and "Trojans" not in text and set(json.loads(text)) >= {"ct", "iv", "salt"}
    assert len(plays.load(KEY, where)) == 2
    with pytest.raises(sealed.Unreadable):
        plays.load("another key", where)
    refused = plays.build("another key", store=store, research=research, now=NOW, where=where)
    assert "could not be opened" in refused[0]["notes"][0] and (where / "2026-04.enc.json").read_text() == text


def test_rule_v2_is_frozen():
    assert plays.RULE_V2 == plays.Rule(
        id="cfb-total-top5-v2", frozen="2026-09-25", sport="ncaaf", market="total", threshold=0.0, top_n=5,
        weekday=5, label="College totals, regular season: each Saturday morning, the week's five largest gaps "
                         "between Atlas's total and the line")
    hist = plays.HISTORY["cfb-total-top5-v2"]
    assert [sum(v[0][i] for v in hist.values()) for i in range(3)] == [208, 152, 5]
    assert plays.HISTORY_COLUMNS["cfb-total-top5-v2"] == ("Vs close",)


def test_rule_v2_takes_the_weeks_five_largest_gaps_once_on_saturday_morning():
    saturday = datetime(2026, 9, 26, 8, tzinfo=UTC)                    # 4 AM Eastern
    gaps = [9.0, -8.0, 7.0, 6.5, -6.0, 5.5, 1.0]                         # seven Saturday games
    projections = pd.DataFrame([_projection(i, 50.0 + g, kickoff="2026-09-26T16:00:00Z")
                                for i, g in enumerate(gaps, start=10)]
                               + [_projection(99, 70.0, kickoff="2026-09-25T23:00:00Z")])   # Friday: played
    snapshots = pd.DataFrame([_snap(i, 50.0) for i in range(10, 17)] + [_snap(99, 50.0)])
    types = {str(i): "regular" for i in [*range(10, 17), 99]}
    got = plays.candidates(plays.RULE_V2, projections, snapshots, pd.DataFrame(), types, saturday, set())
    assert list(got["game_id"]) == [10, 11, 12, 13, 14]                   # 9, 8, 7, 6.5, 6 - not 5.5, not Friday's
    assert list(got["side"]) == ["over", "under", "over", "over", "under"]
    # Once a week: the second Saturday refresh adds nothing; any other day chooses nothing.
    assert plays.candidates(plays.RULE_V2, projections, snapshots, pd.DataFrame(), types, saturday,
                            {(2026, 4)}).empty
    friday = datetime(2026, 9, 25, 8, tzinfo=UTC)
    assert plays.candidates(plays.RULE_V2, projections, snapshots, pd.DataFrame(), types, friday, set()).empty


def test_each_rule_keeps_its_own_record(tmp_path):
    store = Store.open(tmp_path / "tracking")
    saturday = datetime(2026, 9, 26, 8, tzinfo=UTC)
    store.write("projections", pd.DataFrame([_projection(1, 60.0), _projection(2, 52.0)]))
    store.write("snapshots", pd.DataFrame([_snap(1, 50.0), _snap(2, 50.0)]))
    store.write("games", pd.DataFrame({"game_id": [1, 2], "home_team": ["A B", "C D"], "away_team": ["E F", "G H"],
                                       "kickoff": "2026-09-26T16:00:00Z"}))
    research = pd.DataFrame({"game_id": [1, 2], "actual_margin": [None] * 2, "actual_total": [None] * 2,
                             "season_type": ["regular"] * 2, "home_team": ["Oklahoma State", "Wyoming"],
                             "away_team": ["West Virginia", "Hawai'i"]})
    where = tmp_path / "owner_plays"
    sections = plays.build(KEY, store=store, research=research, now=saturday, where=where)
    assert sections[1]["tables"][0]["rows"][0][0].startswith("West Virginia @ Oklahoma State")   # schools, not mascots
    assert [s["title"] for s in sections] == ["Curated plays, rule v1", "Curated plays, rule v2"]
    record = plays.load(KEY, where)
    assert sorted(zip(record["rule"], record["game_id"], strict=True)) == [
        ("cfb-total-5-v1", 1), ("cfb-total-top5-v2", 1), ("cfb-total-top5-v2", 2)]
    assert sections[1]["tables"][0]["title"] == "This week: 2 plays"
