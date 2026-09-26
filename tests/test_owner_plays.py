"""The owner's curated plays: a frozen rule, plays logged once before kickoff, graded, sealed."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import numpy as np
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
    sections = plays.build(KEY, store=store, research=research, now=NOW, where=where)
    assert [s["title"] for s in sections] == ["Curated plays, rule v3 (the plays going forward)",
                                              "Curated plays, rule v1", "Curated plays, rule v2"]
    out = sections[1]
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
    assert sections[2]["tables"][0]["rows"][0][0].startswith("West Virginia @ Oklahoma State")   # schools, not mascots
    assert [s["title"] for s in sections] == ["Curated plays, rule v3 (the plays going forward)",
                                              "Curated plays, rule v1", "Curated plays, rule v2"]
    record = plays.load(KEY, where)
    # 4 AM Saturday: v1 and v2 choose; v3 waits for the first poll from 10:00 ET.
    assert sorted(zip(record["rule"], record["game_id"], strict=True)) == [
        ("cfb-total-5-v1", 1), ("cfb-total-top5-v2", 1), ("cfb-total-top5-v2", 2)]
    assert sections[2]["tables"][0]["title"].startswith("This week: 2 plays, chosen Sat 4:00 AM ET")
    assert sections[0]["tables"][0]["rows"] == [["No game qualifies right now.", ""]]
    ten = datetime(2026, 9, 26, 14, 4, tzinfo=UTC)                                       # 10:04 AM Eastern
    sections = plays.build(KEY, store=store, research=research, now=ten, where=where)
    record = plays.load(KEY, where)
    assert sorted(zip(record["rule"], record["game_id"], strict=True)) == [
        ("cfb-total-5-v1", 1), ("cfb-total-top5-sat10-v3", 1), ("cfb-total-top5-sat10-v3", 2),
        ("cfb-total-top5-v2", 1), ("cfb-total-top5-v2", 2)]
    assert sections[0]["tables"][0]["title"] == "This week: 2 plays, chosen Sat 10:04 AM ET"
    # v3's line is the 10 AM one; v2's was the 4 AM one, and neither is revised by the other.
    v3 = record[record["rule"] == "cfb-total-top5-sat10-v3"]
    assert v3["formed_at"].str.startswith("2026-09-26T14:04").all()


def test_each_play_carries_the_line_movement_flag():
    """Logged with how far the line had moved against it from the opener; graded with the move by the close."""
    projections = pd.DataFrame([_projection(1, 60.0), _projection(2, 40.0)])
    snapshots = pd.DataFrame([
        {**_snap(1, 49.0), "open_line": 52.0},        # an over, the total down 3 from the opener: against
        {**_snap(2, 50.0), "open_line": 49.5},        # an under, the total up 0.5: not much
    ])
    games = pd.DataFrame({"game_id": [1, 2], "home_team": ["A B", "C D"], "away_team": ["E F", "G H"]})
    types = {"1": "regular", "2": "regular"}
    got = plays.candidates(plays.RULE_V1, projections, snapshots, games, types, NOW).set_index("game_id")
    assert (got.loc[1, "open_line"], got.loc[1, "moved_against"]) == (52.0, 3.0)
    assert got.loc[2, "moved_against"] == 0.5

    # By the close the over's total fell further, to 48; the under's came back to 49.5. Both have kicked off.
    closing = pd.concat([snapshots, pd.DataFrame([
        {**_snap(1, 48.0, at="2026-09-26T15:00:00+00:00"), "open_line": 52.0},
        {**_snap(2, 49.5, at="2026-09-26T15:00:00+00:00"), "open_line": 49.5}])], ignore_index=True)
    kicked = games.assign(kickoff="2026-09-26T16:00:00Z")
    moved = plays.closing_movement(got.reset_index(), closing, kicked, datetime(2026, 9, 26, 17, tzinfo=UTC))
    assert moved[plays.play_id(plays.RULE_V1, 1)] == 4.0 and moved[plays.play_id(plays.RULE_V1, 2)] == 0.0
    # A play logged without its opener takes the book's from the line history.
    bare = got.reset_index().assign(open_line=np.nan)
    assert plays.closing_movement(bare, closing, kicked, datetime(2026, 9, 26, 17, tzinfo=UTC))[
        plays.play_id(plays.RULE_V1, 1)] == 4.0
    # Before kickoff there is no close yet.
    assert plays.closing_movement(got.reset_index(), closing, kicked, NOW).isna().all()

    finals = pd.DataFrame({"game_id": ["1", "2"], "final_margin": [0.0, 0.0], "final_total": [40.0, 44.0]})
    g = plays.graded(got.reset_index(), finals, moved)
    section = plays.section(plays.RULE_V1, g, datetime(2026, 9, 27, tzinfo=UTC))
    split = next(t for t in section["tables"] if t["title"].startswith("Split by the line movement flag"))
    assert split["rows"] == [["Line moved against Atlas", "0-1-0 (0.0%)"], ["Everything else", "1-0-0 (100.0%)"]]
    graded_rows = next(t for t in section["tables"] if t["title"] == "Latest graded")["rows"]
    assert any("line moved 4 against by the close" in r[0] for r in graded_rows)


def test_rule_v3_is_frozen_and_chooses_at_the_first_poll_from_ten_eastern():
    assert plays.RULE_V3 == plays.Rule(
        id="cfb-total-top5-sat10-v3", frozen="2026-09-26", sport="ncaaf", market="total", threshold=0.0, top_n=5,
        weekday=5, hour=10,
        label="College totals, regular season: each Saturday at the first poll from 10:00 ET, the weekend's five "
              "largest gaps between Atlas's total and the line")
    assert plays.RULE_V3.id not in plays.HISTORY                       # no frozen figures: its history is rebuilt
    four_am = datetime(2026, 9, 26, 8, tzinfo=UTC)
    nine_59 = datetime(2026, 9, 26, 13, 59, tzinfo=UTC)
    ten_04 = datetime(2026, 9, 26, 14, 4, tzinfo=UTC)
    friday_noon = datetime(2026, 9, 25, 16, tzinfo=UTC)
    assert not plays.chooses_now(plays.RULE_V3, four_am) and not plays.chooses_now(plays.RULE_V3, nine_59)
    assert plays.chooses_now(plays.RULE_V3, ten_04) and not plays.chooses_now(plays.RULE_V3, friday_noon)
    assert plays.chooses_now(plays.RULE_V2, four_am) and plays.chooses_now(plays.RULE_V1, friday_noon)
    gaps = [9.0, -8.0, 7.0, 6.5, -6.0, 5.5, 1.0]
    projections = pd.DataFrame([_projection(i, 50.0 + g, kickoff="2026-09-26T16:00:00Z")
                                for i, g in enumerate(gaps, start=10)])
    snapshots = pd.DataFrame([_snap(i, 50.0) for i in range(10, 17)])
    types = {str(i): "regular" for i in range(10, 17)}
    assert plays.candidates(plays.RULE_V3, projections, snapshots, pd.DataFrame(), types, four_am, set()).empty
    got = plays.candidates(plays.RULE_V3, projections, snapshots, pd.DataFrame(), types, ten_04, set())
    assert list(got["game_id"]) == [10, 11, 12, 13, 14] and got["formed_at"].iloc[0] == "2026-09-26T14:04:00+00:00"
    assert plays.candidates(plays.RULE_V3, projections, snapshots, pd.DataFrame(), types, ten_04, {(2026, 4)}).empty


def test_each_play_is_graded_against_its_books_close():
    """CLV: where the book closed against the line taken, on Atlas's side, in points and in probability."""
    projections = pd.DataFrame([_projection(1, 60.0), _projection(2, 40.0)])
    logged = pd.DataFrame([_snap(1, 49.0), _snap(2, 50.0, other=-110.0)])
    games = pd.DataFrame({"game_id": [1, 2], "home_team": ["A B", "C D"], "away_team": ["E F", "G H"],
                          "kickoff": "2026-09-26T16:00:00Z"})
    types = {"1": "regular", "2": "regular"}
    got = plays.candidates(plays.RULE_V1, projections, logged, games, types, NOW)
    # By kickoff the over's total rose to 51 (the market came to Atlas) and the under's rose to 52 (it went away).
    closing = pd.concat([logged, pd.DataFrame([
        _snap(1, 51.0, price=-115.0, other=-105.0, at="2026-09-26T15:30:00+00:00"),
        _snap(2, 52.0, at="2026-09-26T15:30:00+00:00")])], ignore_index=True)
    after = datetime(2026, 9, 26, 17, tzinfo=UTC)
    value = plays.closing_value(got, closing, games, None, after)
    a, b = plays.play_id(plays.RULE_V1, 1), plays.play_id(plays.RULE_V1, 2)
    assert value.loc[a, "close_line"] == 51.0 and value.loc[a, "clv_points"] == 2.0 and value.loc[a, "clv_result"] == "beat"
    assert value.loc[b, "clv_points"] == -2.0 and value.loc[b, "clv_result"] == "lost"
    assert value.loc[a, "clv_prob"] > 0 > value.loc[b, "clv_prob"]
    # Before kickoff there is no close, and nothing is graded against one.
    assert plays.closing_value(got, closing, games, None, NOW).empty
    finals = pd.DataFrame({"game_id": ["1", "2"], "final_margin": [0.0, 0.0], "final_total": [45.0, 44.0]})
    g = plays.graded(got, finals, plays.closing_movement(got, closing, games, after), value)
    assert g.set_index("play_id").loc[a, "outcome"] == "loss" and g.set_index("play_id").loc[a, "clv"] == 2.0
    section = plays.section(plays.RULE_V1, g, datetime(2026, 9, 27, tzinfo=UTC))
    close = next(t for t in section["tables"] if t["title"].startswith("Against the close"))
    rows = dict(close["rows"])
    assert rows["Beat-push-lost the close"] == "1-0-1" and rows["Beat rate"] == "50.0%"
    assert rows["Mean CLV, points"] == "+0.00" and rows["Mean CLV, win probability"] != "–"
    latest = next(t for t in section["tables"] if t["title"] == "Latest graded")["rows"]
    assert any("closed 51, CLV +2" in r[0] for r in latest)
    assert any("CLV" in n and "good play whether or not it won" in n for n in section["notes"])


def test_the_history_beside_a_rule_is_the_current_models_walk_forward():
    """Rebuilt from tracking/calibration.csv on every refresh, by the rule's own definition."""
    rows = []
    for season in (2024, 2025):
        for week in (1, 2):
            for i in range(8):
                gid = season * 1000 + week * 10 + i
                # Games alternate Saturday and Friday; the largest gaps are the Friday ones.
                day = "2026-09-26" if i % 2 == 0 else "2026-09-25"
                rows.append({"game_id": gid, "sport": "ncaaf", "season": season, "week": week,
                             "season_type": "regular", "market": "total", "abs_edge": 8.0 - i,
                             "claimed": 0.55, "won": 1.0 if i % 3 else 0.0, "kickoff": f"{day}T16:00:00Z"})
    rows.append({"game_id": 9, "sport": "ncaaf", "season": 2025, "week": 1, "season_type": "postseason",
                 "market": "total", "abs_edge": 9.0, "claimed": 0.6, "won": 0.5, "kickoff": "2026-09-26T16:00:00Z"})
    rows.append({"game_id": 8, "sport": "ncaaf", "season": 2025, "week": 1, "season_type": "regular",
                 "market": "margin", "abs_edge": 9.0, "claimed": 0.6, "won": 1.0, "kickoff": "2026-09-26T16:00:00Z"})
    cal = pd.DataFrame(rows)
    v1, how = plays.rule_history(plays.RULE_V1, cal)
    # |edge| >= 5: i in 0..3 each week, won when i % 3: 2 wins, 2 losses per week, regular season, totals only.
    assert v1 == {2024: (4, 4, 0), 2025: (4, 4, 0)} and "closing total" in how
    v3, how = plays.rule_history(plays.RULE_V3, cal)
    # Saturday games only (i even: edges 8, 6, 4, 2; won for i = 2, 4), the top five is all four of them.
    assert v3 == {2024: (4, 4, 0), 2025: (4, 4, 0)} and "Saturday" in how
    all_days, how = plays.rule_history(plays.RULE_V3, cal.drop(columns=["kickoff"]))
    assert all_days == {2024: (6, 4, 0), 2025: (6, 4, 0)} and "every day" in how
    assert plays.rule_history(plays.RULE_V1, pd.DataFrame()) == ({}, "no walk-forward table yet")
    section = plays.section(plays.RULE_V1, plays.graded(pd.DataFrame(columns=plays.COLUMNS), pd.DataFrame()),
                            NOW, calibration=cal)
    current = next(t for t in section["tables"] if t["title"].startswith("History, current model"))
    assert current["rows"] == [["2024", "50.0% of 8"], ["2025", "50.0% of 8"], ["All", "50.0% of 16"]]
    frozen = next(t for t in section["tables"] if t["title"].startswith("History before the freeze"))
    assert "not reproducible" in frozen["title"] and frozen["rows"][-1][0] == "All"


def test_the_plays_box_is_sealed_by_every_run_and_says_why_when_it_cannot_be(tmp_path, monkeypatch):
    from atlas.dfs import owner
    from atlas.site import render

    monkeypatch.delenv(owner.SECRET, raising=False)
    where = tmp_path / "plays.enc.json"
    plays.refresh(where=where)
    record = plays.read_page(where)
    assert record["box"] is None and "not configured" in record["reason"]

    monkeypatch.setenv(owner.SECRET, KEY)
    monkeypatch.setenv("ATLAS_TRACKING_DIR", str(tmp_path / "tracking"))
    store = Store.open(tmp_path / "tracking")
    projections, snapshots, games, _ = _inputs()
    store.write("projections", projections)
    store.write("snapshots", snapshots)
    store.write("games", games.assign(kickoff="2026-09-26T16:00:00Z"))
    research = pd.DataFrame({"game_id": [1, 2, 3, 4, 5, 6], "actual_margin": [None] * 6, "actual_total": [None] * 6,
                             "season_type": ["regular"] * 4 + ["postseason", "regular"],
                             "home_team": ["Miami", "Oregon", "C", "D", "E", "F"],
                             "away_team": ["Central Michigan", "USC", "G", "H", "I", "J"]})
    monkeypatch.setattr("atlas.research.dataset.load_research_frame", lambda: research)
    plays.refresh(now=NOW, where=where)
    record = plays.read_page(where)
    assert record["box"] is not None and record["reason"] is None
    text = where.read_text()
    assert "Miami" not in text and "Oregon" not in text and "over 50" not in text
    data = json.loads(owner.decrypt(record["box"], KEY))
    assert [s["title"] for s in data["sections"]][1] == "Curated plays, rule v1"
    assert data["sections"][1]["tables"][0]["title"] == "This week: 2 plays"
    assert all("record" not in s for s in data["sections"])
    assert (tmp_path / "tracking" / "owner_plays" / "2026-04.enc.json").exists()   # logged and sealed as well
    page = render.owner_page({"built_at": None, "box": None, "reason": "No slate."}, plays=record)
    assert record["box"]["ct"] in page and "Miami" not in page and "The curated plays, encrypted" in page
    bare = render.owner_page(None, plays=None)
    assert "have not been built yet" in bare
