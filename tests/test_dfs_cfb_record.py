"""College DFS: the private live record."""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pytest

from atlas.dfs import cfb_record as rec

KEY = "correct horse battery staple"


def _row(event, dk, pid, name, position="WR", projection=10.0, start="2026-09-26T16:00:00Z", **kw):
    return {"event": event, "season": 2026, "week": 5, "game_start": start, "player_id_dk": dk, "player_id": pid,
            "matched_by": "name and team", "name": name, "position": position, "team": "OSU", "espn_team": "OSU",
            "salary": 5000, "projection": projection, "low": 2.0, "high": 20.0, "p_play": 0.9,
            "if_plays": projection / 0.9, **kw}


def test_a_projection_freezes_at_its_kickoff():
    before = datetime(2026, 9, 26, 12, tzinfo=timezone.utc)
    early = [_row("1", 11, "a", "Early Game", start="2026-09-26T14:00:00Z"),
             _row("2", 12, "b", "Late Game", start="2026-09-26T20:00:00Z")]
    record, weeks = rec.merge(pd.DataFrame(columns=rec.COLUMNS), pd.DataFrame(early), before)
    assert weeks == {(2026, 5)} and len(record) == 2
    # Later that day the first game has kicked off: only the second is revised.
    later = datetime(2026, 9, 26, 15, tzinfo=timezone.utc)
    revised = [{**r, "projection": 99.0} for r in early]
    record, weeks = rec.merge(record, pd.DataFrame(revised), later)
    got = record.set_index("name")["projection"]
    assert weeks and len(record) == 2 and got["Early Game"] == 10.0 and got["Late Game"] == 99.0
    # After every kickoff nothing is written at all.
    _, weeks = rec.merge(record, pd.DataFrame(revised), datetime(2026, 9, 27, tzinfo=timezone.utc))
    assert weeks == set()


def test_the_record_is_sealed_by_week_and_a_wrong_key_changes_nothing(tmp_path, monkeypatch):
    where = tmp_path / "dfs_cfb_record"
    record = pd.DataFrame([_row("1", 11, "a", "Jeremiah Smith"), _row("9", 19, "q", "Next Week", week=6)])
    files = rec.seal(record, KEY, {(2026, 5), (2026, 6)}, where)
    assert [f.name for f in files] == ["2026-05.enc.json", "2026-06.enc.json"]
    text, week6 = files[0].read_text(), files[1].read_text()
    assert "Jeremiah" not in text and "OSU" not in text
    back = rec.load(KEY, where).set_index("name")
    assert back.loc["Jeremiah Smith", "projection"] == 10.0 and back.loc["Next Week", "week"] == 6
    with pytest.raises(rec.Unreadable):
        rec.load("another key", where)

    fresh = tmp_path / "cfb_projections.csv"
    pd.DataFrame([_row("2", 12, "b", "New Player", start="2099-01-01T00:00:00Z")]).to_csv(fresh, index=False)
    monkeypatch.setattr(rec, "projections_path", lambda: fresh)
    out = rec.update("another key", where=where, table=pd.DataFrame(columns=["event"]))
    assert out["games"] == 0 and "could not be opened" in out["note"] and files[0].read_text() == text
    rec.update(KEY, where=where, table=pd.DataFrame(columns=["event", "player_id", "team", "name", "dk_points"]))
    assert set(rec.load(KEY, where)["name"]) == {"Jeremiah Smith", "Next Week", "New Player"}
    assert files[1].read_text() == week6 and files[0].read_text() != text        # only week 5 rewritten


def test_grading_by_id_then_name_and_zero_for_nothing():
    record = pd.DataFrame([
        _row("1", 11, "a", "Julian Sayin", "QB", 20.0),
        _row("1", 12, "DKC-12", "Freshman Back", "RB", 1.5, matched_by="none (no history)"),
        _row("1", 13, "c", "Bench Receiver", "WR", 3.0),
        _row("2", 14, "d", "Not Yet", "WR", 9.0),                      # his game is not in the box scores
    ])
    table = pd.DataFrame([
        {"event": "1", "player_id": "a", "team": "OSU", "name": "Julian Sayin", "dk_points": 25.0},
        {"event": "1", "player_id": "z", "team": "OSU", "name": "Freshman Back Jr.", "dk_points": 8.0},
    ])
    g = rec.graded(record, table).set_index("name")["actual"]
    assert g.to_dict() == {"Julian Sayin": 25.0, "Freshman Back": 8.0, "Bench Receiver": 0.0}
    s = rec.summary(rec.graded(record, table))
    assert s["games"] == 1 and s["all"]["players"] == 3
    assert s["all"]["mae"] == pytest.approx((5.0 + 6.5 + 3.0) / 3)
    assert s["regulars"]["players"] == 3                              # top QB, top RB, top WR
