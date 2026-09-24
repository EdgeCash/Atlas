"""DFS step 0: DraftKings capture, the RotoGuru archive, nflverse player stats."""

from __future__ import annotations

from datetime import UTC, datetime

from atlas.sources import draftkings as dk
from atlas.sources import nflverse, rotoguru

NOW = datetime(2026, 9, 24, 12, tzinfo=UTC)

LOBBY = {"DraftGroups": [
    {"DraftGroupId": 1, "ContestTypeId": 21, "ContestStartTimeSuffix": "", "GameCount": 13,
     "StartDate": "2026-09-27T17:00:00.0000000Z"},
    {"DraftGroupId": 2, "ContestTypeId": 21, "ContestStartTimeSuffix": " (Thu-Mon)", "GameCount": 16,
     "StartDate": "2026-09-25T00:15:00.0000000Z"},
    {"DraftGroupId": 3, "ContestTypeId": 96, "ContestStartTimeSuffix": "", "GameCount": 1,       # showdown
     "StartDate": "2026-09-25T00:15:00.0000000Z"},
    {"DraftGroupId": 4, "ContestTypeId": 21, "ContestStartTimeSuffix": None, "GameCount": 11,    # too far out
     "StartDate": "2026-11-01T18:00:00.0000000Z"},
]}


def _draftable(pid, name, pos, salary, slot):
    return {"playerId": pid, "draftableId": 1000 * pid + slot, "displayName": name, "position": pos, "salary": salary,
            "rosterSlotId": slot,
            "teamAbbreviation": "ATL", "status": "Q" if pid == 11 else "None", "isDisabled": False,
            "competition": {"name": "ATL @ GB", "startTime": "2026-09-25T00:15:00.0000000Z"}}


POOL = {"draftables": [
    _draftable(10, "Bijan Robinson", "RB", 8700, 67), _draftable(10, "Bijan Robinson", "RB", 8700, 70),  # RB and FLEX
    _draftable(11, "Drake London", "WR", 7100, 68), {"playerId": 12, "displayName": "No salary"},
]}


def test_only_classic_slates_within_the_horizon_are_kept_and_labeled():
    slates = dk.classic_slates(LOBBY, now=NOW)
    assert list(slates["draft_group_id"]) == [1, 2]
    assert list(slates["label"]) == ["Main", "Thu-Mon"]
    assert list(slates["game_count"]) == [13, 16]


def test_a_player_listed_for_two_roster_slots_is_one_row():
    pool = dk.player_pool(POOL, 1)
    assert list(pool["player_id"]) == [10, 11] and list(pool["salary"]) == [8700, 7100]
    assert pool.loc[pool["player_id"] == 11, "status"].item() == "Q"
    assert pool.loc[pool["player_id"] == 10, "status"].item() == ""            # healthy
    assert pool.loc[pool["player_id"] == 10, "draftable_id"].item() == 10067   # the RB listing, not FLEX


def test_capture_writes_the_record_and_never_fails_the_run(tmp_path, monkeypatch):
    monkeypatch.setenv("ATLAS_TRACKING_DIR", str(tmp_path))
    from atlas.live.store import Store

    store = Store.open()
    calls = []

    def fetch(url):
        calls.append(url)
        return LOBBY if "lobby" in url else POOL

    counts = dk.capture(store, fetch=fetch, now=NOW)
    assert counts == {"slates": 2, "players": 4}
    assert len(store.read("dfs_slates")) == 2 and len(store.read("dfs_salaries")) == 4
    assert sum("draftables" in u for u in calls) == 2
    # Captured again: the same rows, updated in place.
    dk.capture(store, fetch=fetch, now=NOW)
    assert len(store.read("dfs_salaries")) == 4

    def broken(url):
        raise ConnectionError("DraftKings is down")

    assert dk.capture(store, fetch=broken, now=NOW) == {"slates": 0, "players": 0}
    assert len(store.read("dfs_salaries")) == 4                       # the record is untouched


def test_the_rotoguru_page_parses_to_player_weeks():
    page = """<P><pre>Week;Year;GID;Name;Pos;Team;h/a;Oppt;DK points;DK salary
5;2019;1518;Watson, Deshaun;QB;hou;h;atl;44.74;6700
5;2019;7023;Philadelphia;Def;phi;h;nyj;35;3700
</pre>"""
    frame = rotoguru.parse(page)
    assert list(frame.columns) == list(rotoguru.COLUMNS.values())
    assert len(frame) == 2 and frame["dk_salary"].tolist() == [6700, 3700]
    assert frame.loc[0, "name"] == "Watson, Deshaun" and frame.loc[1, "position"] == "Def"
    assert rotoguru.parse("<html>no data</html>").empty


def test_player_stats_are_part_of_the_nfl_ingest(tmp_path):
    assert "stats_player" in nflverse.FETCHERS and nflverse.FIRST_AVAILABLE["stats_player"] == 1999
    assert nflverse.player_stats_path(tmp_path, 2025).name == "stats_player_2025.parquet"


def test_the_heavy_run_captures_draftkings_before_the_site():
    import inspect

    from atlas.ops import __main__ as ops

    source = inspect.getsource(ops.heavy)
    assert source.index('"dfs-capture"') < source.index('("site"')
