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


def test_no_secret_builds_nothing(tmp_path, monkeypatch):
    monkeypatch.delenv(owner.SECRET, raising=False)
    monkeypatch.setattr(owner, "enc_path", lambda: tmp_path / "owner.enc.json")
    owner.refresh(rebuild=False)
    record = owner.read(tmp_path / "owner.enc.json")
    assert record["box"] is None and "not configured" in record["reason"]


def test_a_failure_records_its_kind_and_nothing_else(tmp_path, monkeypatch):
    from atlas.dfs import slate

    monkeypatch.setenv(owner.SECRET, "horse battery")
    monkeypatch.setattr(owner, "enc_path", lambda: tmp_path / "owner.enc.json")

    def boom(label):
        raise KeyError("Josh Allen salary 8000")

    monkeypatch.setattr(slate, "run", boom)
    owner.refresh(rebuild=False)
    record = owner.read(tmp_path / "owner.enc.json")
    assert record["box"] is None and "KeyError" in record["reason"]
    assert "Josh" not in json.dumps(record) and "8000" not in json.dumps(record)


def _slate_output(tmp_path):
    out = tmp_path / "153769"
    out.mkdir()
    pd.DataFrame([{"name": "Josh Allen", "position": "QB", "team": "BUF", "opponent": "LAC", "salary": 8000,
                   "status": None, "projection": 27.99, "low": 15.7, "high": 40.5, "p_play": 1.0,
                   "game_start": "2026-09-27T17:00:00Z"}]).to_csv(out / "projections.csv", index=False)
    pd.DataFrame([{"lineup": 1, "slot": s, "name": f"Player {i}", "team": "BUF", "salary": 5000, "projection": 15.0,
                   "low": 5.0, "high": 25.0} for i, s in enumerate(
        ["QB", "RB", "RB", "WR", "WR", "WR", "TE", "FLEX", "DST"])]).to_csv(out / "lineups.csv", index=False)
    (out / "lineups_upload.csv").write_text("QB,RB,RB,WR,WR,WR,TE,FLEX,DST\n1,2,3,4,5,6,7,8,9\n")
    return out


def test_payload_and_page_carry_only_ciphertext(tmp_path, monkeypatch):
    from atlas.site import render

    data = owner.payload(_slate_output(tmp_path))
    assert data["draft_group_id"] == 153769 and len(data["lineups"]) == 1
    assert data["lineups"][0]["salary"] == 45000 and data["upload_csv"].startswith("QB,RB")
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
