"""Two runs that overlapped both commit the store; where git cannot merge them, the store does."""

from __future__ import annotations

import pandas as pd
import pytest

from atlas.live.store import SCHEMA, Store
from atlas.owner import sealed
from scripts import merge_tracking as mt

KEY = "correct horse battery staple"


def _games(*ids, status="scheduled"):
    return pd.DataFrame({"game_id": list(ids), "season": 2026, "week": 5, "kickoff": "2026-09-26T16:00:00Z",
                         "home_team": "H", "away_team": "A", "status": status})


def test_a_table_merges_by_its_keys_and_this_runs_rows_win():
    theirs = _games("a", "b")
    ours = _games("b", "c", status="final")
    out = mt.merge_table("games", ours, theirs)
    assert sorted(out["game_id"]) == ["a", "b", "c"]
    assert out.set_index("game_id")["status"].to_dict() == {"a": "scheduled", "b": "final", "c": "final"}
    assert list(out.columns) == SCHEMA["games"]
    # The branch has no copy: this run's table as it is.
    assert mt.merge_table("games", ours, None)["game_id"].tolist() == ["b", "c"]


def test_the_store_merges_table_by_table_and_only_where_this_run_wrote(tmp_path):
    store = Store.open(tmp_path)
    store.write("games", _games("b", "c", status="final"))
    remote = {"tracking/games.csv": _games("a", "b").to_csv(index=False),
              "tracking/runs.csv": "run_id,started_at\nr1,2026-09-26T00:00:00Z\n"}
    merged = mt.merge_store("origin/main", tracking=tmp_path, remote=remote.get)
    assert merged == ["games"]                      # runs.csv: this run did not write it, nothing to merge
    assert sorted(store.read("games")["game_id"]) == ["a", "b", "c"]
    assert not (tmp_path / "runs.csv").exists()


def test_sealed_rows_merge_by_key_in_the_branchs_order_then_this_runs_new_rows():
    theirs = [{"play_id": "p1", "g": 1}, {"play_id": "p2", "g": None}]
    ours = [{"play_id": "p2", "g": 2}, {"play_id": "p3", "g": None}]
    assert mt.merge_rows(theirs, ours, ["play_id"]) == [
        {"play_id": "p1", "g": 1}, {"play_id": "p2", "g": 2}, {"play_id": "p3", "g": None}]


def test_sealed_weekly_files_both_runs_rewrote_are_merged_and_resealed(tmp_path):
    where = tmp_path / "owner_plays"
    ours = sealed.seal([{"play_id": "p1", "grade": None}, {"play_id": "p3", "grade": None}], KEY,
                       where / "2026-04.enc.json")
    sealed.seal([{"play_id": "p0"}], KEY, where / "2026-03.enc.json")          # only this run has this week
    theirs = sealed.seal([{"play_id": "p1", "grade": "win"}, {"play_id": "p2", "grade": None}], KEY,
                         tmp_path / "theirs.enc.json")
    remote = {"tracking/owner_plays/2026-04.enc.json": theirs.read_text(),
              "tracking/owner_plays/2026-02.enc.json": "only the branch has this week"}
    listing = lambda d: [p for p in remote if p.startswith(d + "/")]  # noqa: E731
    merged = mt.merge_sealed("origin/main", KEY, tracking=tmp_path, remote=remote.get, listing=listing)
    assert merged == ["tracking/owner_plays/2026-04.enc.json"]
    rows = sealed.open_text(ours.read_text(), KEY)
    assert [r["play_id"] for r in rows] == ["p1", "p2", "p3"]
    assert rows[0]["grade"] is None                                            # this run's row for a play both hold
    assert sealed.open_text((where / "2026-03.enc.json").read_text(), KEY) == [{"play_id": "p0"}]
    assert "p1" not in ours.read_text() and "p2" not in ours.read_text()      # still sealed
    # The wrong key opens nothing and writes nothing.
    before = ours.read_text()
    with pytest.raises(sealed.Unreadable):
        mt.merge_sealed("origin/main", "not the key", tracking=tmp_path, remote=remote.get, listing=listing)
    assert ours.read_text() == before


def test_every_sealed_record_the_owner_page_keeps_is_merged_by_its_row_key():
    assert set(mt.SEALED) == {"owner_plays", "owner_board", "owner_market", "owner_parlays"}
    assert mt.SEALED["owner_parlays"] == ["parlay_id"]

