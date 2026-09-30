"""The NHL's closing lines for 2022-26 from BettingPros (docs/MODEL_PLAN_NHL.md §2, §9): events matched to the
warehouse's games, each kept book's last pregame line, sealed, resumed within a budget, the key's depth found,
and the market row. A fake BettingPros; synthetic."""

from __future__ import annotations

import logging

import pandas as pd
import pytest

from atlas.owner import nhl_history as hist
from atlas.owner import sealed
from atlas.sources import bettingpros as bp

KEY = "correct horse battery staple"
CATALOGUE = [{"id": 900, "slug": "moneyline"}, {"id": 901, "slug": "puck-line"}, {"id": 902, "slug": "total"}]
MARKET = {900: "moneyline", 901: "spread", 902: "total"}


@pytest.fixture(autouse=True)
def _no_pause(monkeypatch):
    monkeypatch.setattr(hist, "PAUSE", 0.0)


def _games() -> pd.DataFrame:
    rows = []
    for season, n in ((2025, 30), (2024, 10)):
        for i in range(n):
            day = pd.Timestamp(f"{season}-11-01T23:00:00Z") + pd.Timedelta(days=i)
            home, away = ("CBJ", "UTA") if i % 2 == 0 else ("NJD", "BUF")
            rows.append({"game_id": season * 1_000_000 + 20_000 + i + 1, "season": season, "kickoff": day,
                         "home_team": home, "away_team": away, "completed": True,
                         "home_score": 3 if i % 3 else 1, "away_score": 2})
    return pd.DataFrame(rows)


def _line(line, cost, updated, *, main=True, live=False):
    return {"line": line, "cost": cost, "updated": updated, "main": main, "from_live": live, "active": True,
            "is_off": True}


class FakeBP:
    """Lists each season's games as events (Arizona as ARI, New Jersey as NJ), and prices them: pregame lines by
    default; ``stamped_after`` seasons with every line stamped after puck drop (as 2025-26's came back); ``empty``
    seasons with no line at all (the key's depth ends there)."""

    def __init__(self, honour_windows=True, stamped_after=(), empty=(2024,)):
        self.calls = 0
        self.asked = []
        self.honour = honour_windows
        self.stamped_after, self.empty = set(stamped_after), set(empty)
        g = _games()
        self.events = [{"id": int(r.game_id) % 100_000 + 70_000 * (r.season - 2023), "season": int(r.season),
                        "scheduled": r.kickoff.strftime("%Y-%m-%d %H:%M:%S"), "status": "complete",
                        "home": "CBJ" if r.home_team == "CBJ" else "NJ",
                        "visitor": "ARI" if r.away_team == "UTA" else "BUF", "participants": []}
                       for r in g.itertuples()]

    def get(self, path, **params):
        self.calls += 1
        self.asked.append((path, params))
        if path == "/markets":
            return {"markets": CATALOGUE}
        if path == "/events":
            if "start" in params:
                if not self.honour:
                    return {"events": self.events[:3], "_pagination": {"total_pages": 1}}
                lo, hi = pd.Timestamp(params["start"]), pd.Timestamp(params["end"]) + pd.Timedelta(days=1)
                listed = [e for e in self.events if lo <= pd.Timestamp(e["scheduled"]) < hi]
            else:
                listed = [e for e in self.events if e["scheduled"].startswith(params["date"])]
            return {"events": listed, "_pagination": {"total_pages": 1}}
        assert path == "/offers"
        market = MARKET[int(params["market_id"])]
        offers = []
        for eid in (int(x) for x in str(params["event_id"]).split(":")):
            ev = next(e for e in self.events if e["id"] == eid)
            start = pd.Timestamp(ev["scheduled"])
            pre = (start - pd.Timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
            early = (start - pd.Timedelta(hours=9)).strftime("%Y-%m-%d %H:%M:%S")
            after = (start + pd.Timedelta(minutes=20)).strftime("%Y-%m-%d %H:%M:%S")
            if ev["season"] in self.empty:                               # no line at all: the depth ends here
                offers.append({"event_id": eid, "selections": []})
                continue
            if ev["season"] in self.stamped_after:                       # the close, stamped as it came off
                stamp_close, stamp_open = after, after
            else:
                stamp_close, stamp_open = pre, early
            if market == "total":
                sels = [("over", None, 6.5, -115), ("under", None, 6.5, -105)]
            elif market == "spread":
                sels = [("home", ev["home"], -1.5, 190), ("away", ev["visitor"], 1.5, -230)]
            else:
                sels = [("home", ev["home"], None, -140), ("away", ev["visitor"], None, 120)]
            selections = []
            for name, part, ln, cost in sels:
                books = []
                for book in (0, 12, 10, 19):
                    books.append({"id": book, "lines": [
                        _line(ln, cost + 10, stamp_open, main=True),                  # opened, then moved
                        _line(ln, cost, stamp_close, main=True),                      # the close
                        _line(ln, cost - 200, after, main=True, live=True)]})         # the live feed: never
                selections.append({"selection": name, "participant": part, "books": books,
                                   "opening_line": {"line": ln, "cost": cost + 10}})
            offers.append({"event_id": eid, "selections": selections})
        return {"offers": offers}

    def paged(self, path, key, **params):
        return self.get(path, **params).get(key) or []


def test_a_season_is_a_month_at_a_time_october_to_june():
    w = hist.windows(2025)
    assert w[0] == ("2025-10-01", "2025-10-31") and w[2] == ("2025-12-01", "2025-12-31")
    assert w[-1] == ("2026-06-01", "2026-06-30") and len(w) == 9


def test_events_match_by_puck_drop_and_both_teams_arizona_under_utah():
    events = bp._events([{"id": 1, "scheduled": "2025-11-01 23:00:00", "home": "CBJ", "visitor": "ARI"},
                         {"id": 2, "scheduled": "2025-11-02 23:00:00", "home": "NJ", "visitor": "BUF"},
                         {"id": 3, "scheduled": "2025-11-09 23:00:00", "home": "NJ", "visitor": "BUF"}], "nhl")
    m = hist.match(_games(), events).set_index("event_id")
    assert m.loc[1, "game_id"] == 2025020001 and m.loc[2, "game_id"] == 2025020002
    assert 3 not in m.index or m.loc[3, "game_id"] == 2025020010                        # its own night only


def test_the_close_is_the_last_main_pregame_line_never_the_live_feed():
    start = pd.Timestamp("2025-11-01T23:00:00Z")
    lines = [_line(6.5, -110, "2025-11-01 14:00:00"), _line(6.5, -120, "2025-11-01 22:30:00"),
             _line(6.5, -125, "2025-11-01 22:40:00", main=False), _line(5.5, -300, "2025-11-01 23:30:00"),
             _line(6.5, -500, "2025-11-01 22:50:00", live=True)]
    close, source = hist.closing(lines, start)
    assert (close["cost"], source) == (-120, "pregame")
    # Nothing stamped before puck drop: the last line nothing replaced, as it came off the board.
    off = [_line(6.5, -110, "2025-11-02 01:00:00"), {**_line(6.5, -150, "2025-11-02 01:30:00"), "replaced": True},
           _line(6.5, -900, "2025-11-02 00:10:00", live=True)]
    close, source = hist.closing(off, start)
    assert (close["cost"], source) == (-110, "at-off")
    assert hist.closing([_line(6.5, -900, "2025-11-02 00:10:00", live=True)], start) == (None, None)


def test_the_backfill_keeps_three_books_seals_and_resumes_within_its_budget(tmp_path):
    client = FakeBP()
    where = tmp_path / "owner_nhl_history"
    # The catalogue and nine months' listings are ten calls; one batch of a dozen events is three more.
    record, changed = hist.backfill(client, _games(), KEY, where=where, budget=15)
    assert changed and client.calls <= 15
    closes = record[record["kind"] == "close"]
    assert set(closes["book_id"]) == set(hist.KEPT) and set(closes["market"]) == set(hist.MARKETS)
    assert "done" not in hist.status(record).values()                                 # stopped for the budget
    ml = closes[(closes["market"] == "moneyline") & (closes["book_id"] == 0) & (closes["side"] == "home")]
    assert set(ml["cost"]) == {-140.0}                                                 # the close, not the open
    text = (where / "closes-2025.enc.json").read_text()
    assert "moneyline" not in text and "CBJ" not in text
    with pytest.raises(sealed.Unreadable):
        hist.load("not the key", where)
    before = int((record["kind"] == "tried").sum())
    record, _ = hist.backfill(client, _games(), KEY, where=where, budget=client.calls + 400)
    tried = record[record["kind"] == "tried"]
    assert len(tried) > before and tried["event_id"].is_unique                       # resumed, nothing asked twice
    assert hist.status(record) == {2025: "done", 2024: "empty"}                       # the depth found
    assert set(record.loc[record["kind"] == "close", "source"]) == {"pregame"}


def test_the_depth_found_stops_the_asking(tmp_path, caplog):
    client = FakeBP()
    where = tmp_path / "h"
    hist.backfill(client, _games(), KEY, where=where, budget=1000)
    calls = client.calls
    with caplog.at_level(logging.INFO):
        _, changed = hist.backfill(client, _games(), KEY, where=where, budget=1000)
    assert not changed and client.calls == calls                                      # 2023 and 2022 never asked
    assert "depth ends at 2024" in caplog.text and "-140" not in caplog.text


def test_lines_stamped_after_puck_drop_are_kept_at_the_off_and_timed_in_the_log(tmp_path, caplog):
    client = FakeBP(stamped_after=(2025,))
    with caplog.at_level(logging.INFO):
        record, _ = hist.backfill(client, _games(), KEY, where=tmp_path / "h", budget=1000)
    closes = record[record["kind"] == "close"]
    assert set(closes["source"]) == {"at-off"} and set(closes["book_id"]) == set(hist.KEPT)
    assert hist.status(record)[2025] == "done"
    assert "at the off (stamped 20/20/20 minutes after puck drop" in caplog.text and "-140" not in caplog.text


def test_a_season_closed_under_the_old_rule_with_few_consensus_closes_is_asked_again(tmp_path):
    old = pd.DataFrame(
        [{"kind": "tried", "season": 2025, "event_id": e, "game_id": e} for e in range(10)]
        + [{"kind": "close", "season": 2025, "event_id": 0, "game_id": 0, "market": "moneyline", "side": "home",
            "book_id": 0, "cost": -120.0},
           {"kind": "season", "season": 2025, "status": "done", "events": 10},
           {"kind": "tried", "season": 2024, "event_id": 99, "game_id": 99}]).reindex(columns=hist.COLUMNS)
    record, reopened = hist.reopen(old)
    assert reopened == [2025] and set(record["season"]) == {2024}
    ruled = old.copy()
    ruled.loc[ruled["kind"] == "season", "rule"] = hist.RULE
    assert hist.reopen(ruled)[1] == []                                               # the current rule stands
    hist.seal(old, KEY, [2025, 2024], tmp_path)
    client = FakeBP(stamped_after=(2025,))
    record, changed = hist.backfill(client, _games(), KEY, where=tmp_path, budget=1000)
    assert changed and (record.loc[(record["kind"] == "close") & (record["season"] == 2025), "source"] == "at-off").all()
    assert int(((record["kind"] == "season") & (record["season"] == 2025)).sum()) == 1


def test_a_window_the_api_ignores_is_listed_a_day_at_a_time():
    client = FakeBP(honour_windows=False)
    days = sorted({t.strftime("%Y-%m-%d") for t in _games().query("season == 2025")["kickoff"]})
    events, how = hist.list_events(client, 2025, days, budget=500)
    assert how == "day" and len(events) == 30


def test_the_market_row_scores_the_consensus_draftkings_and_atlas_on_the_same_games():
    record = pd.DataFrame([
        {"kind": "close", "season": 2025, "game_id": g, "market": "moneyline", "side": side, "book_id": book,
         "cost": cost}
        for g in (1, 2) for book in (0, 12) for side, cost in (("home", -150.0), ("away", 130.0))])
    atlas = pd.DataFrame({"game_id": [1, 2], "p_home": [0.6, 0.5], "home_win": [1.0, 0.0]})
    row = hist.market_row(record, atlas).set_index("season")
    from atlas.live.probability import no_vig

    p = no_vig(-150, 130)
    assert row.loc[2025, "games"] == 2 and row.loc[2025, "market"] == pytest.approx(((p - 1) ** 2 + p ** 2) / 2)
    assert row.loc[2025, "atlas"] == pytest.approx((0.16 + 0.25) / 2) and row.loc[2025, "dk_games"] == 2
    assert row.loc["all", "games"] == 2


def test_closes_at_the_off_count_only_when_they_score_like_pregame_closes():
    import numpy as np

    rng = np.random.default_rng(1)
    n = 200
    won = (rng.random(n) < 0.55).astype(float)
    games = np.arange(n)

    def record(p_home):
        rows = []
        for g, p in zip(games, p_home, strict=True):
            home = -100 * p / (1 - p) if p >= 0.5 else 100 * (1 - p) / p
            away = -100 * (1 - p) / p if p < 0.5 else 100 * p / (1 - p)
            rows += [{"kind": "close", "season": 2025, "game_id": g, "market": "moneyline", "side": "home",
                      "book_id": 0, "cost": home, "source": "at-off"},
                     {"kind": "close", "season": 2025, "game_id": g, "market": "moneyline", "side": "away",
                      "book_id": 0, "cost": away, "source": "at-off"}]
        return pd.DataFrame(rows)

    atlas = pd.DataFrame({"game_id": games, "p_home": 0.55, "home_win": won})
    pregame = hist.market_row(record(np.full(n, 0.55)), atlas).set_index("season")
    assert pregame.loc[2025, "games"] == n and pregame.loc[2025, "left_out"] == 0
    in_game = hist.market_row(record(np.where(won == 1, 0.9, 0.1)), atlas).set_index("season")
    assert in_game.loc[2025, "left_out"] == n and in_game.loc[2025, "games"] == 0      # an in-game price: out
    assert in_game.loc[2025, "off_brier"] < hist.SANE_BRIER
