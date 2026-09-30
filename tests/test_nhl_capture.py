"""The NHL's market from opening night: ESPN's DraftKings line in the poll, every book's line and the
player props sealed for the owner (docs/MODEL_PLAN_NHL.md, step 0)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import pandas as pd

from atlas.live import provider
from atlas.live.__main__ import _games_frame, _snapshot_frame
from atlas.live.store import Store
from atlas.ops import schedule
from atlas.owner import nhl_capture
from atlas.sources import bettingpros as bp

KEY = "correct horse battery staple"
NOW = datetime(2026, 10, 1, 16, 0, tzinfo=UTC)          # noon ET, the day of eight games


def _line(side_close, side_open=None, line=None):
    block = {"close": {"odds": side_close}, "open": {"odds": side_open or side_close}}
    if line is not None:
        block["close"]["line"] = line
        block["open"]["line"] = line
    return block


def _scoreboard():
    """One game as ESPN's NHL scoreboard carries it on 1 October 2026, trimmed to what is read."""
    return {"events": [{
        "id": "401891781", "date": "2026-10-01T23:00Z", "season": {"year": 2027, "type": 2},
        "competitions": [{
            "status": {"type": {"name": "STATUS_SCHEDULED", "completed": False}},
            "competitors": [
                {"homeAway": "home", "score": "0", "team": {"id": "29", "displayName": "Columbus Blue Jackets"}},
                {"homeAway": "away", "score": "0", "team": {"id": "2", "displayName": "Buffalo Sabres"}}],
            "odds": [{
                "provider": {"name": "DraftKings"},
                "moneyline": {"home": _line("-115", "-120"), "away": _line("-105", "EVEN")},
                "pointSpread": {"home": _line("+205", line="-1.5"), "away": _line("-250", line="+1.5")},
                "total": {"over": _line("-110", line="o6.5"), "under": _line("-110", line="u6.5")},
            }],
        }],
    }]}


def test_the_nhl_scoreboard_gives_the_moneyline_puck_line_and_total():
    board = provider.EspnScoreboard(sport="nhl")
    assert board.name == "espn-nhl" and "hockey/nhl" in board.url
    rows = pd.DataFrame(board._events(_scoreboard(), "2026-10-01T16:00:00+00:00")).set_index("market")
    assert set(rows.index) == {"moneyline", "margin", "total"}
    ml = rows.loc["moneyline"]
    assert pd.isna(ml["line"]) and ml["price"] == -115 and ml["other_price"] == -105 and ml["open_price"] == -120
    assert rows.loc["margin", "line"] == 1.5 and rows.loc["margin", "price"] == 205       # home -1.5 is +1.5
    assert rows.loc["total", "line"] == 6.5
    # ESPN numbers a hockey season by the year it ends; Atlas by the year it starts.
    assert set(rows["season"]) == {2026} and set(rows["sport"]) == {"nhl"}


def test_the_poll_asks_every_sport_and_football_keeps_its_markets():
    assert provider.POLLED == ("espn", "espn-nfl", "espn-nhl")
    payload = _scoreboard()
    football = pd.DataFrame(provider.EspnScoreboard(sport="nfl")._events(payload, "t"))
    assert set(football["market"]) == {"margin", "total"} and set(football["sport"]) == {"nfl"}
    assert set(football["season"]) == {2027}            # football's season year is left as ESPN gives it


def test_the_games_table_records_the_sport_and_the_moneyline_is_kept_on_change(tmp_path):
    store = Store.open(tmp_path)
    quotes = pd.DataFrame(provider.EspnScoreboard(sport="nhl")._events(_scoreboard(), "2026-10-01T16:00:00+00:00"))
    store.upsert("games", _games_frame(quotes, "2026-10-01T16:00:00+00:00"))
    assert store.read("games")["sport"].tolist() == ["nhl"]
    assert store.append_on_change("snapshots", _snapshot_frame(quotes, "2026-10-01T16:00:00+00:00")) == 3
    assert store.append_on_change("snapshots", _snapshot_frame(quotes, "2026-10-01T16:15:00+00:00")) == 0
    moved = quotes.assign(price=quotes["price"].where(quotes["market"] != "moneyline", -125.0),
                          captured_at="2026-10-01T16:30:00+00:00")
    assert store.append_on_change("snapshots", _snapshot_frame(moved, "2026-10-01T16:30:00+00:00")) == 1


def test_nhl_nights_poll_every_fifteen_minutes_in_season_only():
    et = schedule.EASTERN
    tuesday_october = datetime(2026, 10, 6, 19, 0, tzinfo=et)
    wednesday_october = datetime(2026, 10, 7, 22, 45, tzinfo=et)
    tuesday_september = datetime(2026, 9, 22, 20, 0, tzinfo=et)
    tuesday_july = datetime(2027, 7, 6, 20, 0, tzinfo=et)
    assert schedule.game_day(tuesday_october).name == "NHL Tuesday night"
    assert schedule.game_day(wednesday_october).name == "NHL Wednesday night"
    assert schedule.game_day(tuesday_september) is None and schedule.game_day(tuesday_july) is None
    assert schedule.game_day(datetime(2026, 10, 6, 17, 59, tzinfo=et)) is None
    assert schedule.poll_interval_minutes(tuesday_october) == 15


# ---------------------------------------------------------------------------
# BettingPros: every book's NHL line and the player props, sealed
# ---------------------------------------------------------------------------

CATALOGUE = [{"id": 900, "slug": "moneyline"}, {"id": 901, "slug": "puck-line"}, {"id": 902, "slug": "total"},
             {"id": 903, "slug": "shots-on-goal"}, {"id": 904, "slug": "saves"}, {"id": 905, "slug": "faceoffs-won"}]
GAME_MARKET = {900: "moneyline", 901: "spread", 902: "total"}


def _game_offer(event_id, market):
    if market == "total":
        sels = [("over", None, 6.5, -110), ("under", None, 6.5, -110)]
    elif market == "spread":
        sels = [("home", "CBJ", -1.5, 205), ("away", "BUF", 1.5, -250)]
    else:
        sels = [("home", "CBJ", None, -115), ("away", "BUF", None, -105)]
    return {"offers": [{"event_id": event_id, "selections": [
        {"selection": s, "participant": p, "opening_line": {"line": ln, "cost": c, "book_id": 12},
         "books": [{"id": book, "lines": [{"line": ln, "cost": c + shade, "main": True, "active": True,
                                             "updated": "2026-10-01 15:00:00"}]}
                   for book, shade in ((12, 0), (19, -5), (0, 0))]}
        for s, p, ln, c in sels]}]}


def _prop_offer(event_id, market_id, player, line):
    return {"market_id": market_id, "event_id": event_id, "player_id": player,
            "participants": [{"id": player, "name": player.title(),
                              "player": {"position": "C", "team": "CBJ"}}],
            "selections": [{"selection": side, "books": [
                {"id": book, "lines": [{"line": line, "cost": cost, "main": True, "active": True,
                                        "updated": "2026-10-01 15:00:00"}]}
                for book, cost in ((12, -120), (19, -115), (bp.PRIZEPICKS, None))]}
                for side in ("over", "under")]}


class _FakeClient:
    def __init__(self):
        self.calls = 0
        self.asked = []

    def get(self, path, **params):
        self.calls += 1
        self.asked.append((path, params))
        if path == "/markets":
            return {"markets": CATALOGUE}
        if path == "/events":
            assert params["sport"] == "NHL" and params["date"] == "2026-10-01"
            return {"events": [{"id": 77001, "scheduled": "2026-10-01 23:00:00", "status": "scheduled",
                                "home": "CBJ", "visitor": "BUF",
                                "participants": [{"id": "CBJ", "name": "Blue Jackets", "team": {"city": "Columbus"}},
                                                 {"id": "BUF", "name": "Sabres", "team": {"city": "Buffalo"}}]}],
                    "_pagination": {"total_pages": 1}}
        ids = [int(i) for i in str(params["market_id"]).split(":")]
        if len(ids) == 1 and ids[0] in GAME_MARKET:
            return _game_offer(77001, GAME_MARKET[ids[0]])
        assert set(ids) == {903, 904}                     # the wanted prop markets the catalogue has
        return {"offers": [_prop_offer(77001, 903, "adam fantilli", 2.5), _prop_offer(77001, 904, "elvis merzlikins",
                                                                                         26.5)],
                "_pagination": {"total_pages": 1}}

    def paged(self, path, key, **params):
        return self.get(path, **params).get(key) or []


def _games():
    return pd.DataFrame([
        {"game_id": 401891781, "sport": "nhl", "kickoff": "2026-10-01T23:00Z", "home_team": "Columbus Blue Jackets",
         "away_team": "Buffalo Sabres"},
        {"game_id": 401891799, "sport": "nhl", "kickoff": "2026-10-04T23:00Z", "home_team": "Boston Bruins",
         "away_team": "Chicago Blackhawks"},                                   # beyond the day and a half
        {"game_id": 401866429, "sport": None, "kickoff": "2026-10-01T23:30Z", "home_team": "Sacramento State Hornets",
         "away_team": "Massachusetts Minutemen"},                              # football: not this module's
    ])


def test_only_the_nhl_games_in_the_next_day_and_a_half_are_captured():
    near = nhl_capture.ahead(_games(), NOW)
    assert near["game_id"].tolist() == [401891781]
    assert nhl_capture.days_of(near) == ["2026-10-01"]
    assert nhl_capture.ahead(_games(), NOW + timedelta(hours=8)).empty       # started


def test_the_capture_seals_every_books_line_and_the_props_and_logs_counts_only(tmp_path, caplog):
    client = _FakeClient()
    where = tmp_path / "owner_props"
    with caplog.at_level("INFO"):
        lines, events = nhl_capture.capture(client, _games(), KEY, NOW, props_where=where)
    assert set(lines["market"]) == {"moneyline", "spread", "total"} and set(lines["game_id"]) == {401891781}
    assert set(lines["book_id"]) == {0, 12, 19} and events["event_id"].tolist() == [77001]
    assert lines.loc[lines["market"] == "moneyline", "line"].eq(0.0).all()
    props = nhl_capture.load_props(KEY, where)
    assert set(props["market"]) == {"shots-on-goal", "saves"} and set(props["game_id"]) == {401891781}
    assert len(props) == 2 * 2 * 3
    files = list(where.glob("props-2026-W40.enc.json"))
    assert len(files) == 1 and "fantilli" not in files[0].read_text().lower()
    log = caplog.text
    assert "1 games ahead, 1 listed, 1 matched; game markets found: moneyline, spread, total" in log
    assert "not asked for: faceoffs-won" in log
    assert "shots-on-goal 1 players, 3 books, PrizePicks 1" in log
    assert "26.5" not in log and "-115" not in log and "Fantilli" not in log


def test_props_are_fetched_at_most_hourly_and_kept_on_change_only(tmp_path):
    client = _FakeClient()
    where = tmp_path / "owner_props"
    nhl_capture.capture(client, _games(), KEY, NOW, props_where=where)
    prop_calls = lambda: sum(1 for p, q in client.asked if p == "/offers" and ":" in str(q["market_id"]))  # noqa: E731
    assert prop_calls() == 1
    nhl_capture.capture(client, _games(), KEY, NOW + timedelta(minutes=15), props_where=where)
    assert prop_calls() == 1                                               # not due
    nhl_capture.capture(client, _games(), KEY, NOW + timedelta(hours=1), props_where=where)
    assert prop_calls() == 2 and len(nhl_capture.load_props(KEY, where)) == 12   # nothing moved: nothing added


def test_a_failing_api_costs_the_nhl_capture_and_nothing_else(caplog):
    class Broken(_FakeClient):
        def get(self, path, **params):
            raise RuntimeError("price -115 for someone")

    with caplog.at_level(logging.WARNING):
        lines, events = nhl_capture.capture(Broken(), _games(), KEY, NOW)
    assert lines.empty and events.empty
    assert "-115" not in caplog.text


def test_the_board_seals_nhl_lines_beside_footballs_and_prices_none_of_them(tmp_path, monkeypatch):
    from atlas.owner import board
    from atlas.owner import market as market_store

    monkeypatch.setenv("ATLAS_TRACKING_DIR", str(tmp_path / "tracking"))
    store = Store.open(tmp_path / "tracking")
    store.write("games", _games())
    client = _FakeClient()
    sections = board.build(KEY, store=store, now=NOW, client=client, market_where=tmp_path / "market",
                           picks_where=tmp_path / "picks", parlays_where=tmp_path / "parlays",
                           trading_where=tmp_path / "trading", pickem_where=tmp_path / "pickem",
                           slips_where=tmp_path / "slips", props_where=tmp_path / "props")
    record = market_store.load(KEY, tmp_path / "market")
    assert set(record["sport"]) == {"nhl"} and set(record["game_id"].astype(int)) == {401891781}
    assert client.calls > 0
    shown = str(sections)
    assert "Blue Jackets" not in shown and "Sabres" not in shown          # captured, never priced or shown
