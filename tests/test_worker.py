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
    e = us.event(eid, slug, away, home, [us.moneyline(int(eid) * 10, "basketball", away, home, bid, ask, start=start)],
                 start=start)
    return {**e, "live": live, "ended": ended, "period": period, "elapsed": elapsed}


def test_the_venues_period_is_read_as_the_scoreboard_counts_them():
    assert worker.venue_period("Q4", "nba") == 4.0 and worker.venue_period("End Q3", "nba") == 3.0
    assert worker.venue_period("P3", "nhl") == 3.0 and worker.venue_period("OT", "nhl") == 4.0
    assert worker.venue_period("2OT", "nba") == 5.0 and worker.venue_period("SO", "nhl") == 4.0
    assert worker.venue_period("HT", "nfl") == 2.0
    assert all(math.isnan(worker.venue_period(x, "nba")) for x in ("NS", "FT", "VFT", "", None))
    state = worker.venue_state({"nba": [_stub("1", "nba-a-b", BULLS, CELTICS, 0.85, 0.86),
                                        _stub("2", "nba-c-d", BULLS, CELTICS, 0.85, 0.86, live=False, period="NS"),
                                        _stub("3", "nba-e-f", BULLS, CELTICS, 0.85, 0.86, ended=True, period="FT")]})
    assert state == {"1": (4.0, "03:12")}


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


def test_the_record_is_committed_and_pushed_to_the_branch(tmp_path):
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
    root = tmp_path / "clone"
    subprocess.run(["git", "clone", "-q", str(remote), str(root)], check=True)
    env = ["-c", "user.name=t", "-c", "user.email=t@example.com"]
    (root / "tracking").mkdir()
    (root / "tracking" / "favorites.csv").write_text("a\n1\n")
    subprocess.run(["git", *env, "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", *env, "commit", "-q", "-m", "first"], cwd=root, check=True)
    subprocess.run(["git", "push", "-q", "-u", "origin", "HEAD"], cwd=root, check=True)
    assert worker.publish(root, NOW) is False                           # nothing changed
    (root / "tracking" / "favorites.csv").write_text("a\n1\n2\n")
    (root / "README.md").write_text("not the worker's to commit")
    assert worker.publish(root, NOW) is True
    log = subprocess.run(["git", "log", "--oneline", "origin/" + worker.branch(root)], cwd=root,
                         capture_output=True, text=True, check=True).stdout
    assert log.startswith(("worker: 2026-10-23 22:30 ET",)) or "worker: 2026-10-23 22:30 ET" in log
    status = subprocess.run(["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True, check=True).stdout
    assert "README.md" in status                                        # left alone
