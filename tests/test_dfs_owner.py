"""DFS step 6: the owner page - sealed in Python, opened by WebCrypto, nothing readable published."""

from __future__ import annotations

import json
import shutil
import subprocess

import pandas as pd
import pytest

from atlas.dfs import owner

FAST = 1_000                       # iterations for tests; the real page uses owner.ITERATIONS


def test_sealed_payload_opens_only_with_its_passphrase():
    box = owner.encrypt(b'{"lineups": ["Josh Allen"]}', "horse battery", iterations=FAST)
    assert "Josh Allen" not in json.dumps(box)
    assert owner.decrypt(box, "horse battery") == b'{"lineups": ["Josh Allen"]}'
    assert owner.decrypt(box, "  horse battery\n") == b'{"lineups": ["Josh Allen"]}'   # a pasted newline
    from cryptography.exceptions import InvalidTag

    with pytest.raises(InvalidTag):
        owner.decrypt(box, "horse batterY")
    again = owner.encrypt(b'{"lineups": ["Josh Allen"]}', "horse battery", iterations=FAST)
    assert again["salt"] != box["salt"] and again["iv"] != box["iv"]              # fresh every build
    with pytest.raises(ValueError):
        owner.encrypt(b"x", "   ")


@pytest.mark.skipif(shutil.which("node") is None, reason="no Node to stand in for the browser")
def test_webcrypto_opens_what_python_sealed():
    """The browser's side, run in Node's WebCrypto with owner.js's exact calls."""
    box = owner.encrypt("Amon-Ra St. Brown · $7,900".encode(), "correct horse", iterations=FAST)
    script = """
const box = JSON.parse(process.argv[1]);
const b = s => Uint8Array.from(Buffer.from(s, 'base64'));
(async () => {
  const enc = new TextEncoder();
  const base = await crypto.subtle.importKey('raw', enc.encode(process.argv[2].trim()), 'PBKDF2', false, ['deriveKey']);
  const key = await crypto.subtle.deriveKey({name: 'PBKDF2', salt: b(box.salt), iterations: box.iterations,
    hash: 'SHA-256'}, base, {name: 'AES-GCM', length: 256}, false, ['decrypt']);
  try {
    const plain = await crypto.subtle.decrypt({name: 'AES-GCM', iv: b(box.iv)}, key, b(box.ct));
    console.log(new TextDecoder().decode(plain));
  } catch (e) { console.log('REFUSED'); }
})();
"""
    run = lambda pw: subprocess.run(["node", "-e", script, json.dumps(box), pw], capture_output=True,  # noqa: E731
                                    text=True, timeout=60).stdout.strip()
    assert run("correct horse ") == "Amon-Ra St. Brown · $7,900"
    assert run("wrong horse") == "REFUSED"


def test_no_secret_builds_no_lineups(tmp_path, monkeypatch):
    from atlas.dfs import slate

    monkeypatch.delenv(owner.SECRET, raising=False)
    monkeypatch.setenv("ATLAS_TRACKING_DIR", str(tmp_path))
    monkeypatch.setattr(owner, "enc_path", lambda: tmp_path / "owner.enc.json")
    ran = []
    monkeypatch.setattr(slate, "run_all", lambda: ran.append(1) or tmp_path)
    owner.refresh(rebuild=False)
    assert ran == [1]                                        # the public slate is built regardless
    record = owner.read(tmp_path / "owner.enc.json")
    assert record["box"] is None and "not configured" in record["reason"]


def test_a_failure_records_its_kind_and_nothing_else(tmp_path, monkeypatch):
    from atlas.dfs import slate

    monkeypatch.setenv(owner.SECRET, "horse battery")
    monkeypatch.setenv("ATLAS_TRACKING_DIR", str(tmp_path))
    monkeypatch.setattr(owner, "enc_path", lambda: tmp_path / "owner.enc.json")

    def boom():
        raise KeyError("Josh Allen salary 8000")

    monkeypatch.setattr(slate, "run_all", boom)
    owner.refresh(rebuild=False)
    record = owner.read(tmp_path / "owner.enc.json")
    assert record["box"] is None and "KeyError" in record["reason"]
    assert "Josh" not in json.dumps(record) and "8000" not in json.dumps(record)


def _slate_output(tmp_path):
    """Two slates as the slate step writes them, and their index."""
    showdown = tmp_path / "153775"
    showdown.mkdir()
    (showdown / "slate.json").write_text(json.dumps({"draft_group_id": 153775, "game_type": "Showdown",
                                                     "label": "ATL @ GB", "starts_at": "2026-09-25T00:15:00+00:00"}))
    pd.DataFrame([{"name": "Bijan Robinson", "position": "RB", "team": "ATL", "salary": 11800, "status": None,
                   "projection": 20.0, "low": 5.0, "high": 35.0, "p_play": 1.0,
                   "game_start": "2026-09-25T00:15:00Z"}]).to_csv(showdown / "projections.csv", index=False)
    pd.DataFrame([{"lineup": 1, "slot": s, "name": f"SD {i}", "team": "ATL", "salary": 8000, "projection": 12.0,
                   "low": 3.0, "high": 22.0} for i, s in enumerate(["CPT", "FLEX", "FLEX", "FLEX", "FLEX", "FLEX"])]
                 ).to_csv(showdown / "lineups.csv", index=False)
    (showdown / "lineups_upload.csv").write_text("CPT,FLEX,FLEX,FLEX,FLEX,FLEX\n1,2,3,4,5,6\n")
    out = tmp_path / "153769"
    out.mkdir()
    (out / "slate.json").write_text(json.dumps({"draft_group_id": 153769, "game_type": "Classic", "label": "Main",
                                                "starts_at": "2026-09-27T17:00:00+00:00"}))
    (tmp_path / "index.json").write_text(json.dumps({"slates": [
        {"draft_group_id": 153775, "game_type": "Showdown", "label": "ATL @ GB"},
        {"draft_group_id": 153769, "game_type": "Classic", "label": "Main"}]}))
    pd.DataFrame([{"name": "Josh Allen", "position": "QB", "team": "BUF", "opponent": "LAC", "salary": 8000,
                   "status": None, "projection": 27.99, "low": 15.7, "high": 40.5, "p_play": 1.0,
                   "game_start": "2026-09-27T17:00:00Z"}]).to_csv(out / "projections.csv", index=False)
    pd.DataFrame([{"lineup": 1, "slot": s, "name": f"Player {i}", "team": "BUF", "salary": 5000, "projection": 15.0,
                   "low": 5.0, "high": 25.0} for i, s in enumerate(
        ["QB", "RB", "RB", "WR", "WR", "WR", "TE", "FLEX", "DST"])]).to_csv(out / "lineups.csv", index=False)
    (out / "lineups_upload.csv").write_text("QB,RB,RB,WR,WR,WR,TE,FLEX,DST\n1,2,3,4,5,6,7,8,9\n")
    return tmp_path / "index.json"


def test_payload_and_page_carry_only_ciphertext(tmp_path, monkeypatch):
    from atlas.site import render

    data = owner.payload(_slate_output(tmp_path))
    assert data["draft_group_id"] == 153769 and [s["game_type"] for s in data["slates"]] == ["Showdown", "Classic"]
    main = data["slates"][1]
    assert main["lineups"][0]["salary"] == 45000 and main["upload_csv"].startswith("QB,RB")
    assert data["slates"][0]["upload_csv"].startswith("CPT,FLEX")
    assert data["players"][0]["name"] == "Josh Allen"                        # the biggest Classic slate's pool
    assert data["first_kickoff"].startswith("2026-09-27T17:00")
    box = owner.encrypt(json.dumps(data).encode(), "horse battery", iterations=FAST)
    page = render.owner_page({"built_at": "2026-09-24T12:00:00+00:00", "box": box, "reason": None})
    assert box["ct"] in page and "Josh Allen" not in page and "Player 1" not in page
    assert 'name="robots" content="noindex, nofollow"' in page and "owner.js" in page
    assert 'autocomplete="current-password"' in page


def test_page_without_lineups_says_why_and_escapes_its_island():
    from atlas.site import render

    page = render.owner_page({"built_at": None, "box": None, "reason": "The owner key is not configured."})
    assert "not configured" in page
    tricky = render.owner_page({"box": {"ct": "</script><b>"}, "reason": None})
    assert "</script><b>" not in tricky


def test_stale_play_by_play_is_fetched_again(tmp_path, monkeypatch):
    from atlas.sources import nflverse

    dest = nflverse.pbp_path(tmp_path, 2012)
    dest.parent.mkdir(parents=True)
    pd.DataFrame({"game_id": ["g"], "epa": [0.1]}).to_parquet(dest)
    assert nflverse._stale_pbp(dest)
    fetched = []

    def fake_download(url, path, **_):
        fetched.append(url)
        pd.DataFrame({c: [1] for c in ("game_id", *nflverse.PBP_REQUIRED)}).to_parquet(path)
        return path

    monkeypatch.setattr(nflverse, "download", fake_download)
    nflverse.fetch_play_by_play(tmp_path, 2012)
    assert len(fetched) == 1 and not nflverse._stale_pbp(dest)
    nflverse.fetch_play_by_play(tmp_path, 2012)
    assert len(fetched) == 1                                                  # fresh now: served from cache


def test_no_upcoming_slate_says_so(tmp_path, monkeypatch):
    from atlas.dfs import slate

    monkeypatch.setenv(owner.SECRET, "horse battery")
    monkeypatch.setenv("ATLAS_TRACKING_DIR", str(tmp_path))
    monkeypatch.setattr(owner, "enc_path", lambda: tmp_path / "owner.enc.json")

    def none():
        raise slate.NoSlate("none")

    monkeypatch.setattr(slate, "run_all", none)
    owner.refresh(rebuild=False)
    assert owner.read(tmp_path / "owner.enc.json")["reason"] == "No upcoming slate is posted yet."


# ---------------------------------------------------------------------------
# Step 7: the public record and page
# ---------------------------------------------------------------------------


def _projected():
    return pd.DataFrame([
        {"player_id_dk": 1, "player_id": "qb1", "name": "Josh Allen", "position": "QB", "team": "BUF",
         "opponent": "LAC", "salary": 8000, "status": "", "projection": 22.0, "low": 12.0, "high": 32.0,
         "p_play": 1.0, "season": 2026, "week": 3},
        {"player_id_dk": 2, "player_id": "wr9", "name": "Deep Receiver", "position": "WR", "team": "BUF",
         "opponent": "LAC", "salary": 3000, "status": "", "projection": 1.0, "low": 0.0, "high": 4.0,
         "p_play": 0.2, "season": 2026, "week": 3},
        {"player_id_dk": 3, "player_id": "DST-BUF", "name": "Bills", "position": "DST", "team": "BUF",
         "opponent": "LAC", "salary": 3000, "status": "", "projection": 8.0, "low": 1.0, "high": 15.0,
         "p_play": 1.0, "season": 2026, "week": 3},
    ])


def test_the_record_freezes_at_the_first_kickoff(tmp_path):
    from datetime import datetime, timezone

    from atlas.dfs import record
    from atlas.live.store import Store

    store = Store.open(tmp_path)
    slate = pd.Series({"draft_group_id": 9, "label": "Main", "starts_at": "2026-09-27T17:00:00+00:00"})
    assert record.save(_projected(), slate, store, now=datetime(2026, 9, 26, tzinfo=timezone.utc)) == 3
    later = _projected().assign(projection=[99.0, 99.0, 99.0])
    record.save(later, slate, store, now=datetime(2026, 9, 27, 8, tzinfo=timezone.utc))   # still before: revised
    assert set(store.read("dfs_projections")["projection"]) == {99.0}
    assert record.save(_projected(), slate, store, now=datetime(2026, 9, 27, 18, tzinfo=timezone.utc)) == 0
    assert set(store.read("dfs_projections")["projection"]) == {99.0}                     # frozen once started


def test_grading_counts_a_player_who_did_not_play_as_zero():
    from atlas.dfs import record

    proj = _projected().assign(draft_group_id=9)
    games = pd.DataFrame([{"season": 2026, "week": 3, "season_type": "REG", "player_id": "qb1", "dk_points": 35.0}])
    dst = pd.DataFrame([{"season": 2026, "week": 3, "season_type": "REG", "team": "BUF", "dk_points": 5.0}])
    g = record.graded(proj, games, dst).set_index("player_id")
    assert g.loc["qb1", "actual"] == 35.0 and g.loc["wr9", "actual"] == 0.0 and g.loc["DST-BUF", "actual"] == 5.0
    s = record.summary(g.reset_index())
    assert s["slates"] == 1 and s["players"] == 3 and s["coverage"] == pytest.approx(2 / 3)   # 35 is above 12-32
    # Not played yet: nothing graded.
    assert record.graded(proj.assign(week=4), games, dst).empty


def test_dfs_page_lists_players_and_keeps_its_promises():
    import re

    from atlas.site import render
    from scripts.audit_site import DFS_PROMISE, FORBIDDEN, visible

    players = _projected().assign(status=["", "", ""], name=["Drew Lock", "Josh Kelly", "Bills"]).to_dict(
        orient="records")                                     # names that contain banned words are still names
    history = {"seasons": "2015-2025", "salary_seasons": "2015-2021", "positions": {
        "QB": {"player_weeks": 10, "mae": 6.4, "baseline_mae": 6.7, "rank": 0.34, "coverage": 0.82,
               "salary_era_rank": 0.341, "salary_rank": 0.33}}}
    page = render.dfs_page({"starts_at": "2026-09-27T17:00:00+00:00", "projected_at": "2026-09-26T08:00:00+00:00"},
                           players, history=history, live={"slates": 0})
    assert "Drew Lock" in page and "Players less likely to play (1)" in page and "0.330" in page
    assert "1-800-GAMBLER" in page and "draftkings.com/responsible-gaming" in page
    text = visible(page)
    assert not DFS_PROMISE.search(text)
    allowed = ("does not publish selections",)
    for word in FORBIDDEN:
        for m in re.finditer(rf"\b{word}\b", text):
            assert any(a in text[max(0, m.start() - 70):m.end() + 70] for a in allowed), word
    empty = render.dfs_page(None, [], history=None, live=None)
    assert "No slate is posted yet" in empty


def test_payload_is_strict_json_for_the_browser():
    data = owner._clean({"lineups": [{"salary": float("nan"), "slots": [{"projection": 1.5, "low": float("nan")}]}]})
    text = json.dumps(data, allow_nan=False)
    assert "NaN" not in text and '"salary": null' in text
