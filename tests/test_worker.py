"""The favorites rule as an always-on loop (atlas/polymarket/worker.py): the venue's clock read, a tick
offline, the record pushed, and the scheduled run standing down."""

from __future__ import annotations

import math
import subprocess
from datetime import UTC, datetime, timedelta

import pandas as pd

from atlas.live.store import Store
from atlas.polymarket import favorites, worker
from atlas.testing import polymarket_us as us

NOW = datetime(2026, 10, 24, 2, 30, tzinfo=UTC)
START = "2026-10-24T00:00:00Z"
BULLS = us.team(1, "Chicago Bulls", "Chicago", "chi")
CELTICS = us.team(2, "Boston Celtics", "Boston", "bos")


def _stub(eid, slug, away, home, bid, ask, *, period="Q4", elapsed="03:12", live=True, ended=False, start=START):
    """A league listing's stub: the event with its headline market and the venue's own clock."""
    e = us.event(eid, slug, away, home, [us.moneyline(int(eid) * 10, "basketball", away, home, bid, ask, start=start,
                                                      side_ids=(f"26110{eid}0", f"26110{eid}1"))],
                 start=start)
    return {**e, "live": live, "ended": ended, "period": period, "elapsed": elapsed}


def test_the_venues_period_is_read_as_the_scoreboard_counts_them():
    assert worker.venue_period("Q4", "nba") == 4.0 and worker.venue_period("End Q3", "nba") == 3.0
    assert worker.venue_period("P3", "nhl") == 3.0 and worker.venue_period("OT", "nhl") == 4.0
    assert worker.venue_period("2OT", "nba") == 5.0 and worker.venue_period("SO", "nhl") == 4.0
    assert worker.venue_period("HT", "nfl") == 2.0
    # College basketball plays two halves: half-time ends the first, and the second half is its last.
    assert worker.venue_period("HT", "ncaab") == 1.0 and worker.venue_period("H2", "ncaab") == 2.0
    assert worker.venue_period("OT", "ncaab") == 3.0 and favorites.is_late("ncaab", 2.0, "in_play")
    assert not favorites.is_late("ncaab", 1.0, "in_play")
    assert all(math.isnan(worker.venue_period(x, "nba")) for x in ("NS", "FT", "VFT", "", None))
    state = worker.venue_state({"nba": [_stub("1", "nba-a-b", BULLS, CELTICS, 0.85, 0.86),
                                        _stub("2", "nba-c-d", BULLS, CELTICS, 0.85, 0.86, live=False, period="NS"),
                                        _stub("3", "nba-e-f", BULLS, CELTICS, 0.85, 0.86, ended=True, period="FT")]})
    assert state == {"1": (4.0, "03:12")}


def test_the_worker_reads_college_basketball_which_the_scheduled_capture_does_not(monkeypatch):
    from atlas.polymarket import source

    read = []
    monkeypatch.setattr(source, "fetch_listing", lambda league, sess=None: read.append(league.slug) or [])
    out = worker.listings(sess=object())
    assert read == ["nfl", "nhl", "cfb", "nba", "cbb"] and set(out) == {"nfl", "nhl", "ncaaf", "nba", "ncaab"}
    assert "ncaab" not in source.LEAGUES                    # Atlas has no model for it: no full reads each run
    events = {"ncaab": [_stub("4", "cbb-duke-unc-2026-11-10", BULLS, CELTICS, 0.85, 0.86, period="H2")]}
    q = source.capture(NOW, leagues=source.WORKER_LEAGUES.values(), events=events)
    assert len(q) == 2 and set(q["sport"]) == {"ncaab"} and worker.venue_state(events) == {"4": (2.0, "03:12")}


def test_a_tick_takes_the_crossings_with_the_venues_clock_and_orders_nothing_offline(tmp_path, monkeypatch):
    monkeypatch.setenv("ATLAS_OFFLINE", "1")
    monkeypatch.delenv("LIVE_PHASE", raising=False)
    store = Store.open(tmp_path / "tracking")
    store.write("games", pd.DataFrame([{"game_id": "901", "kickoff": START, "home_team": "Boston Celtics",
                                        "away_team": "Chicago Bulls", "sport": "nba", "period": 3, "clock": "9:00",
                                        "season": 2026, "week": 1, "status": "STATUS_IN_PROGRESS", "completed": False,
                                        "home_score": 100, "away_score": 90}]))
    events = {"nba": [
        # In the fourth quarter by the venue's clock (the scoreboard, a poll old, still says the third): late.
        _stub("1", "nba-chi-bos-2026-10-23", BULLS, CELTICS, 0.85, 0.86),
        # A wide book: declined, whatever the ask.
        _stub("2", "nba-x-y-2026-10-23", BULLS, CELTICS, 0.70, 0.90),
        # Not started: a pregame crossing, recorded and never late.
        _stub("3", "nba-p-q-2026-10-24", BULLS, CELTICS, 0.88, 0.89, live=False, period="NS",
              start="2026-10-25T00:00:00Z"),
    ]}
    out = worker.tick(store, NOW, None, events=events)
    assert out["events"] == 3 and out["live"] == 2 and out["added"] == 4 and out["graded"] == 0
    r = store.read(favorites.TABLE)
    r = r.assign(event_id=r["event_id"].astype(str)).set_index(["event_id", "threshold"])
    late = r.loc[("1", 0.85)]
    assert late["phase"] == "in_play" and bool(late["late"]) and late["period"] == 4.0 and late["clock"] == "03:12"
    assert int(float(late["game_id"])) == 901 and late["ask"] == 0.86         # matched to Atlas's game
    assert ("2", 0.85) not in r.index and ("2", 0.80) not in r.index
    pre = r.loc[("3", 0.85)]
    assert pre["phase"] == "pregame" and not bool(pre["late"]) and math.isnan(float(pre["period"]))
    # The same tick again adds nothing; the record stands.
    again = worker.tick(store, NOW + timedelta(seconds=45), None, events=events)
    assert again["added"] == 0 and len(store.read(favorites.TABLE)) == 4
    # With no events read (the venue down), nothing happens and nothing fails.
    assert worker.tick(store, NOW, None, events={})["quotes"] == 0


def test_the_live_step_takes_late_crossings_unless_told_any(monkeypatch):
    monkeypatch.delenv("LIVE_PHASE", raising=False)
    assert favorites.phase() == "late"
    monkeypatch.setenv("LIVE_PHASE", "any")
    assert favorites.phase() == "any"
    monkeypatch.setenv("LIVE_PHASE", "late")
    assert favorites.phase() == "late"
    sent = []
    monkeypatch.setenv("POLYMARKET_US_LIVE", "dry")
    from atlas.polymarket import orders

    monkeypatch.setattr(orders, "place", lambda p, *a, **k: sent.append(len(p)))
    rows = pd.DataFrame([
        {**dict.fromkeys(favorites.COLUMNS), "token_id": "a", "threshold": 0.85, "late": True, "formed_at": NOW.isoformat(),
         "game_start": START, "ask": 0.86, "long": True},
        {**dict.fromkeys(favorites.COLUMNS), "token_id": "b", "threshold": 0.85, "late": False, "formed_at": NOW.isoformat(),
         "game_start": START, "ask": 0.86, "long": True},
        {**dict.fromkeys(favorites.COLUMNS), "token_id": "a", "threshold": 0.80, "late": True, "formed_at": NOW.isoformat(),
         "game_start": START, "ask": 0.86, "long": True}])
    favorites.order(rows, "key", NOW)
    assert sent == [1]                                   # the late one at the order threshold only
    monkeypatch.setenv("LIVE_PHASE", "any")
    favorites.order(rows, "key", NOW)
    assert sent == [1, 2]
    monkeypatch.setenv("POLYMARKET_US_LIVE", "")
    favorites.order(rows, "key", NOW)
    assert sent == [1, 2]                                # off: nothing


def test_the_scheduled_run_stands_down_when_the_worker_owns_the_rule(tmp_path, monkeypatch):
    monkeypatch.setenv("ATLAS_OFFLINE", "1")
    store = Store.open(tmp_path / "tracking")
    store.write(favorites.TABLE, pd.DataFrame([{**dict.fromkeys(favorites.COLUMNS), "token_id": "t", "threshold": 0.85,
                                                "phase": "in_play", "formed_at": NOW.isoformat(), "game_start": START,
                                                "sport": "nba", "ask": 0.86, "cost": 0.87, "label": "a @ b", "side": "home"}]))
    quotes = pd.DataFrame([{**dict.fromkeys(["captured_at", *favorites.COLUMNS]), "sport": "nba", "event_id": "e",
                            "game_start": START, "away": "A", "home": "B", "market": "moneyline", "side": "home",
                            "long": True, "token_id": "u", "ask": 0.90, "bid": 0.89, "spread": 0.01, "fee_rate": 0.0695,
                            "accepting": True, "market_id": "m", "market_slug": "m", "event_slug": "nba-e", "line": 0.0}])
    monkeypatch.setenv(favorites.TAKER, "worker")
    record, section = favorites.refresh(store, quotes, NOW, None)
    assert len(record) == 1 and "worker" in section["notes"][0] and len(store.read(favorites.TABLE)) == 1
    monkeypatch.delenv(favorites.TAKER)
    record, _ = favorites.refresh(store, quotes, NOW, None)
    assert len(record) == 4                                # the run takes the crossing itself again


def _position(token, threshold=0.85, *, at="2026-10-24T01:00:00+00:00", won=None, **kw):
    return {**dict.fromkeys(favorites.COLUMNS), "token_id": token, "threshold": threshold, "formed_at": at,
            "phase": "in_play", "sport": "nba", "game_start": START, "label": "Chicago Bulls @ Boston Celtics",
            "market": "moneyline", "side": "home", "long": True, "ask": threshold + 0.01, "cost": threshold + 0.02,
            "market_slug": f"m{token}", "event_id": "1", "won": won, "payout": won, "profit": None, **kw}


def _repo(tmp_path):
    """A bare remote, the worker's clone of it, and a second clone standing in for the scheduled runs."""
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)
    clones = []
    for name in ("worker", "runs"):
        root = tmp_path / name
        subprocess.run(["git", "clone", "-q", str(remote), str(root)], check=True, capture_output=True)
        subprocess.run(["git", "checkout", "-q", "-B", "main"], cwd=root, check=True)
        clones.append(root)
    return clones


def _commit(root, message):
    env = ["-c", "user.name=t", "-c", "user.email=t@example.com"]
    subprocess.run(["git", *env, "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", *env, "commit", "-q", "-m", message], cwd=root, check=True)
    subprocess.run(["git", "pull", "-q", "--rebase", "origin", "main"], cwd=root, check=False, capture_output=True)
    subprocess.run(["git", "push", "-q", "origin", "HEAD:main"], cwd=root, check=True, capture_output=True)


def _record(root) -> pd.DataFrame:
    return Store.open(root / "tracking").read(favorites.TABLE)


def test_the_record_is_cleaned_of_what_a_merge_leaves_and_held_once_per_position():
    rows = pd.DataFrame([_position("2611050"), _position("2611050", at="2026-10-24T01:05:00+00:00", won=1.0),
                         _position("2611050", 0.90), _position("777", at="2026-10-24T00:59:00+00:00")])
    marks = pd.DataFrame([{**dict.fromkeys(favorites.COLUMNS), "formed_at": m}
                          for m in ("<<<<<<< Updated upstream", "=======", ">>>>>>> Stashed changes")])
    dirty = pd.concat([rows, marks], ignore_index=True)
    dirty["token_id"] = pd.to_numeric(dirty["token_id"])            # what a blank line does to the column: decimals
    clean = favorites.clean(dirty)
    assert len(clean) == 3 and set(clean["token_id"]) == {"2611050", "777"}
    held = clean.set_index(["token_id", "threshold"]).loc[("2611050", 0.85)]
    assert held["formed_at"] == "2026-10-24T01:00:00+00:00" and held["won"] == 1.0   # the first taken, graded
    assert favorites.ident(2611050.0) == "2611050" and favorites.ident("2611050.0") == "2611050"
    assert favorites.ident(None) is None and favorites.ident(float("nan")) is None and favorites.ident("abc") == "abc"
    assert len(favorites.merge(clean, rows)) == 3 and favorites.clean(None).empty


def test_a_record_read_back_as_decimals_does_not_take_its_positions_again(tmp_path, monkeypatch):
    monkeypatch.setenv("ATLAS_OFFLINE", "1")
    store = Store.open(tmp_path / "tracking")
    events = {"nba": [_stub("1", "nba-chi-bos-2026-10-23", BULLS, CELTICS, 0.85, 0.86)]}
    first = worker.tick(store, NOW, None, events=events)
    assert first["added"] == 2
    record = store.read(favorites.TABLE)
    record.loc[len(record)] = {**dict.fromkeys(favorites.COLUMNS), "formed_at": "======="}   # the incident's line
    record["token_id"] = pd.to_numeric(record["token_id"], errors="coerce")
    record.to_csv(store.path(favorites.TABLE), index=False)
    again = worker.tick(store, NOW + timedelta(minutes=1), None, events=events)
    assert again["added"] == 0 and again["positions"] == 2
    assert len(store.read(favorites.TABLE)) == 2                      # and the line is gone from the file


def test_a_position_already_in_the_ledger_is_not_ordered_again(tmp_path, monkeypatch):
    from atlas.polymarket import orders, positions

    monkeypatch.delenv("ATLAS_OFFLINE", raising=False)
    monkeypatch.setenv(orders.MODE, "dry")
    monkeypatch.setenv(orders.BANKROLL, "")                           # no bankroll: refused, but written, and offline-safe
    pos = favorites.as_positions(pd.DataFrame([_position("2611050", late=True)]))
    assert list(pos["position_id"]) == ["fav:2611050:0.85"] and list(pos.columns) == positions.COLUMNS
    where = tmp_path / "live"
    first = orders.place(pos, "key", NOW, where=where, rule="favorites", signer=None)
    assert len(first) == 1
    # The same position from a record whose ids read back as decimals: the same order, not a second one.
    pos2 = favorites.as_positions(pd.DataFrame([_position(2611050.0, late=True)]))
    second = orders.place(pos2, "key", NOW + timedelta(seconds=45), where=where, rule="favorites", signer=None)
    assert len(second) == 1 and len(orders.load("key", where)) == 1


def test_the_worker_and_a_run_writing_the_record_at_once_leave_it_whole(tmp_path, monkeypatch):
    monkeypatch.delenv("ATLAS_OFFLINE", raising=False)
    mine, runs = _repo(tmp_path)
    base = pd.DataFrame([_position("100")])
    Store.open(runs / "tracking").write(favorites.TABLE, base)
    (runs / "README.md").write_text("atlas\n")
    _commit(runs, "first")
    subprocess.run(["git", "pull", "-q", "origin", "main"], cwd=mine, check=True, capture_output=True)
    # The scheduled run grades the position and takes another; the worker, meanwhile, takes one more and
    # holds it uncommitted - the state the setup script's test tick left on the server.
    Store.open(runs / "tracking").write(favorites.TABLE, pd.DataFrame([_position("100", won=1.0), _position("200")]))
    _commit(runs, "poll")
    Store.open(mine / "tracking").write(favorites.TABLE, pd.DataFrame([_position("100"), _position("300")]))
    (mine / "local.txt").write_text("untracked, not the worker's")
    assert worker.publish(mine, NOW) is True
    subprocess.run(["git", "pull", "-q", "origin", "main"], cwd=runs, check=True, capture_output=True)
    text = (runs / "tracking" / "favorites.csv").read_text()
    assert "<<<<<<<" not in text and "=======" not in text and ">>>>>>>" not in text
    merged = _record(runs).assign(token_id=lambda d: d["token_id"].astype(str)).set_index("token_id")
    assert set(merged.index) == {"100", "200", "300"} and merged.loc["100", "won"] == 1.0
    log = subprocess.run(["git", "log", "--format=%s", "-1", "origin/main"], cwd=mine, capture_output=True,
                         text=True, check=True).stdout
    assert log.startswith("worker: 2026-10-23 22:30 ET") and (mine / "local.txt").exists()
    # Level with the branch, there is nothing to push.
    assert worker.publish(mine, NOW + timedelta(minutes=1)) is False
    # A worker whose own copy carries the incident's lines repairs the branch's on its next push.
    Store.open(runs / "tracking").write(favorites.TABLE, pd.concat(
        [_record(runs), pd.DataFrame([{**dict.fromkeys(favorites.COLUMNS), "formed_at": "<<<<<<< Updated upstream"}])]))
    _commit(runs, "the bad commit")
    Store.open(mine / "tracking").write(favorites.TABLE, pd.concat([_record(mine), pd.DataFrame([_position("400")])]))
    assert worker.publish(mine, NOW + timedelta(minutes=2)) is True
    subprocess.run(["git", "pull", "-q", "origin", "main"], cwd=runs, check=True, capture_output=True)
    assert "<<<<<<<" not in (runs / "tracking" / "favorites.csv").read_text()
    assert set(_record(runs)["token_id"].astype(str)) == {"100", "200", "300", "400"}


def test_the_worker_reads_the_branchs_kill_file_every_tick(tmp_path, monkeypatch):
    from atlas.polymarket import orders

    monkeypatch.delenv(worker.BRANCH, raising=False)
    mine, theirs = _repo(tmp_path)
    (theirs / "README").write_text("x")
    _commit(theirs, "start")
    subprocess.run(["git", "pull", "-q", "origin", "main"], cwd=mine, check=True, capture_output=True)
    assert worker.branch_kill(mine) is None
    flag = theirs / worker.LEDGER / orders.KILL_FILE
    flag.parent.mkdir(parents=True)
    flag.write_text("stop: odd fills\n")
    _commit(theirs, "kill")
    assert worker.branch_kill(mine) == "stop: odd fills"           # without the worker's checkout moving
    assert not (mine / worker.LEDGER / orders.KILL_FILE).exists()
    flag.unlink()
    _commit(theirs, "lift")
    assert worker.branch_kill(mine) is None
    # GitHub out of reach: the last reading holds, so an outage never lifts a kill.
    subprocess.run(["git", "remote", "set-url", "origin", str(tmp_path / "gone.git")], cwd=mine, check=True)
    monkeypatch.setattr(orders, "branch_kill", "held")
    assert worker.branch_kill(mine) == "held"


def test_the_worker_merges_the_audit_trail_with_the_branchs_by_event(tmp_path, monkeypatch):
    from atlas.polymarket import audit

    monkeypatch.delenv("ATLAS_OFFLINE", raising=False)
    monkeypatch.delenv(worker.BRANCH, raising=False)
    key = "correct horse battery staple"
    mine, runs = _repo(tmp_path)
    (runs / "README.md").write_text("atlas\n")
    _commit(runs, "first")
    subprocess.run(["git", "pull", "-q", "origin", "main"], cwd=mine, check=True, capture_output=True)
    for root, note in ((runs, "the scheduled run's"), (mine, "the worker's")):
        trail = audit.Trail(key, root / worker.AUDIT, clock=lambda: NOW)
        trail.add("refused", note=note)
        trail.flush()
    _commit(runs, "a run's trail")
    assert worker.publish(mine, NOW, key) is True
    subprocess.run(["git", "pull", "-q", "origin", "main"], cwd=runs, check=True, capture_output=True)
    merged = audit.load(key, runs / worker.AUDIT)
    assert sorted(merged["note"]) == ["the scheduled run's", "the worker's"] and merged["event_id"].is_unique
