"""The owner's board: BettingPros parsed, matched, sealed, priced, picked and graded - and never in the clear."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pytest

from atlas.live.store import Store
from atlas.owner import board, sealed
from atlas.owner import market as market_store
from atlas.sources import bettingpros as bp

KEY = "correct horse battery staple"
NOW = datetime(2026, 9, 26, 14, 4, tzinfo=UTC)


def _offers_body(event_id: int, market: str, home: str = "CSUS", away: str = "UMASS") -> dict:
    """An offers response in the API's shape (26 September 2026), with a book that spells the home side
    another way, a replaced line, a prediction market, and a line that has gone off."""
    def sel(selection, participant, line, books):
        return {"selection": selection, "participant": participant, "label": selection or participant, "active": True,
                "opening_line": {"line": line + 2, "cost": -110, "book_id": 10, "created": "2026-09-22 08:00:00"},
                "books": [{"id": bid, "lines": lines} for bid, lines in books]}

    def ln(line, cost, *, main=True, replaced=False, off=False, updated="2026-09-26 13:00:00"):
        return {"id": f"l{line}{cost}", "main": main, "active": True, "replaced": replaced, "is_off": off,
                "cost": cost, "line": line, "updated": updated, "best": False}
    if market == "total":
        selections = [
            sel("Over", None, 44.5, [(0, [ln(44.5, -110)]), (12, [ln(44.5, -112)]), (19, [ln(44.5, -105)]),
                                      (49, [ln(46.5, -110)]), (60, [ln(49.5, -99900)]),
                                      (73, [ln(49.5, 108, off=True)]),
                                      (24, [ln(45.5, -110, replaced=True, updated="2026-09-26 11:00:00"),
                                            ln(44.5, -115, updated="2026-09-26 12:00:00")])]),
            sel("Under", None, 44.5, [(0, [ln(44.5, -110)]), (12, [ln(44.5, -108)]), (19, [ln(44.5, -115)]),
                                       (49, [ln(46.5, -110)]), (60, [ln(49.5, 150)]), (24, [ln(44.5, -105)])]),
        ]
    else:
        selections = [
            sel("", home, 4.5, [(0, [ln(4.5, -110)]), (12, [ln(4.5, -110)]), (19, [ln(5.5, -115)])]),
            sel("", away, -4.5, [(0, [ln(-4.5, -110)]), (12, [ln(-4.5, -110)]), (19, [ln(-5.5, -105)])]),
            # The home side again, spelt as another book spells it: a consensus row that must not read as the away side.
            sel("", "SAC", 4.5, [(0, [ln(4.5, -102)]), (33, [ln(4.5, -105)])]),
        ]
    return {"_parameters": {"key": "SECRET-MUST-NOT-SURVIVE"}, "markets": [bp.MARKETS["ncaaf"][market]],
            "offers": [{"id": "abc", "market_id": bp.MARKETS["ncaaf"][market], "event_id": event_id, "active": True,
                        "link": "https://example.invalid/affiliate?x=1", "participants": [], "selections": selections}]}


def test_offers_are_parsed_to_one_current_line_per_book_without_the_request_echo():
    lines = bp.parse_offers(_offers_body(32187, "total"), "ncaaf", "total", "2026-09-26T13:05:00+00:00")
    assert set(lines["selection"]) == {"over", "under"} and (lines["event_id"] == 32187).all()
    over = lines[lines["selection"] == "over"].set_index("book_id")
    assert over.loc[24, "line"] == 44.5 and over.loc[24, "cost"] == -115           # the replaced line is not current
    assert bool(over.loc[73, "is_off"]) and over.loc[0, "open_line"] == 46.5 and over.loc[0, "open_book"] == 10
    assert "SECRET" not in lines.to_json() and "link" not in lines.columns
    take = lines[bp.takeable(lines)]
    assert set(take["book_id"]) == {12, 19, 49, 24}                                # no consensus, no prediction markets, no off line


def test_events_match_espn_games_by_kickoff_and_both_mascots():
    games = pd.DataFrame([
        {"game_id": 401866429, "sport": "ncaaf", "home_team": "Sacramento State Hornets", "away_team": "Massachusetts Minutemen",
         "kickoff": "2026-09-27T01:00Z"},
        {"game_id": 401856700, "sport": "ncaaf", "home_team": "Oklahoma State Cowboys", "away_team": "Wyoming Cowboys",
         "kickoff": "2026-09-26T19:30Z"},
        {"game_id": 401856701, "sport": "ncaaf", "home_team": "Dallas Cowboys", "away_team": "Wyoming Cowboys",
         "kickoff": "2026-09-26T19:30Z"},
        {"game_id": 401872948, "sport": "nfl", "home_team": "Kansas City Chiefs", "away_team": "Miami Dolphins",
         "kickoff": "2026-09-27T17:00Z"},
    ])
    events = pd.DataFrame([
        {"event_id": 32187, "sport": "ncaaf", "scheduled": "2026-09-27 01:00:00", "home_abbr": "CSUS", "visitor_abbr": "UMASS",
         "home_school": "Sacramento St.", "visitor_school": "UMass", "home_mascot": "Hornets", "visitor_mascot": "Minutemen"},
        {"event_id": 32200, "sport": "ncaaf", "scheduled": "2026-09-26 19:30:00", "home_abbr": "OKST", "visitor_abbr": "WYO",
         "home_school": "Oklahoma State", "visitor_school": "Wyoming", "home_mascot": "Cowboys", "visitor_mascot": "Cowboys"},
        {"event_id": 22040, "sport": "nfl", "scheduled": "2026-09-27 17:00:00", "home_abbr": "KC", "visitor_abbr": "MIA",
         "home_school": "Kansas City", "visitor_school": "Miami", "home_mascot": "Chiefs", "visitor_mascot": "Dolphins"},
        {"event_id": 99999, "sport": "ncaaf", "scheduled": "2026-09-27 01:00:00", "home_abbr": "X", "visitor_abbr": "Y",
         "home_school": "Nowhere", "visitor_school": "Elsewhere", "home_mascot": "Hornets", "visitor_mascot": "Owls"},
    ])
    pairs = board.match_events(games, events).set_index("event_id")["game_id"].to_dict()
    assert pairs == {32187: 401866429, 32200: 401856700, 22040: 401872948}   # two Cowboys: the schools decide; no match for X-Y


def _lines(event_id=32187, game_id="401866429"):
    parts = [bp.parse_offers(_offers_body(event_id, m), "ncaaf", m, "2026-09-26T13:05:00+00:00") for m in ("total", "spread")]
    return pd.concat(parts, ignore_index=True).assign(game_id=game_id)


def _events(event_id=32187, game_id="401866429"):
    return pd.DataFrame([{"event_id": event_id, "sport": "ncaaf", "scheduled": pd.Timestamp("2026-09-27 01:00:00", tz="UTC"),
                          "season": 2026, "week": 4, "status": "scheduled", "home_abbr": "CSUS", "visitor_abbr": "UMASS",
                          "home_school": "Sacramento St.", "visitor_school": "UMass", "home_mascot": "Hornets",
                          "visitor_mascot": "Minutemen", "home_conference": None, "visitor_conference": None,
                          "stadium_type": "outdoor", "forecast_wind": 18.0, "forecast_temp": 70.0, "game_id": game_id}])


def _projections(total=50.0, game_id=401866429):
    return pd.DataFrame([{"game_id": game_id, "sport": "ncaaf", "season": 2026, "week": 4, "kickoff": "2026-09-27T01:00:00Z",
                          "total_mean": total, "total_sd": 16.0, "total_over_shrink": 0.35, "total_over_sd": 15.8,
                          "margin_mean": -3.0, "margin_sd": 15.0, "model_version": "m1", "refreshed_at": "2026-09-26T08:00:00+00:00"}])


def _calibration(hit_high=0.56, n=600):
    """A walk-forward table whose hit rate rises with the gap: 50% under 4 points, ``hit_high`` from 4 on."""
    rng = np.random.default_rng(0)
    rows = []
    for i in range(n):
        gap = rng.uniform(0, 12)
        p = 0.5 if gap < 4 else hit_high
        rows.append({"game_id": i, "sport": "ncaaf", "season": 2021 + i % 5, "week": 1 + i % 12, "season_type": "regular",
                     "market": "total", "abs_edge": gap, "claimed": 0.55, "won": 1.0 if rng.random() < p else 0.0})
    return pd.DataFrame(rows)


def test_the_board_prices_every_side_at_its_best_book_and_flags_the_market():
    b = board.price(_lines(), _events(), _projections(total=50.0), {}, NOW, _calibration())
    b = b.set_index(["market", "side"])
    over, under = b.loc[("total", "over")], b.loc[("total", "under")]
    # Atlas 50 against a 44.5 consensus: the over is Atlas's side; its best price is BetMGM's -105 at 44.5.
    assert over["cons_line"] == 44.5 and over["best_book"] == 19 and over["best_line"] == 44.5 and over["best_cost"] == -105
    assert over["p_atlas"] > 0.53 > under["p_atlas"] and over["ev_atlas"] > 0 > under["ev_atlas"]
    assert abs(over["p_fair"] - 0.5) < 0.02 and over["ev_price"] < 0                  # -105 on a 50/50 market is not value
    # Hard Rock's under 46.5 is two points off consensus: flagged; steam from the 46.5 opener.
    assert bool(under["off_market"]) and under["best_book"] == 49 and under["best_line"] == 46.5
    assert bool(over["steam"]) and over["move"] == -2.0 and over["moved_against"] == 2.0
    # Spreads: the alias row (SAC +4.5 at -102) is the home side, never the away side; away is UMass -4.5.
    home, away = b.loc[("spread", "home")], b.loc[("spread", "away")]
    assert home["cons_line"] == 4.5 and away["cons_line"] == -4.5 and home["open_line"] == 6.5 and away["open_line"] == -6.5
    assert home["best_line"] == 5.5 and home["best_book"] == 19                      # +5.5 beats +4.5 for the dog
    assert away["best_line"] == -4.5 and away["ev_price"] < 0.05
    assert np.isnan(home["p_atlas"]) and np.isnan(away["ev_atlas"])                    # no model view on spreads
    assert over["forecast_wind"] == 18.0
    # Picks: one side per market, positive EV by the measure that applies; the over qualifies, the under does not.
    chosen = board.picks(b.reset_index())
    assert list(zip(chosen["market"], chosen["side"], strict=True)) == [("total", "over")] or \
        all(m != "total" or s == "over" for m, s in zip(chosen["market"], chosen["side"], strict=True))


def test_the_edge_curve_is_the_walk_forward_hit_rate_at_or_beyond_each_gap():
    curve = board.edge_curve(_calibration(hit_high=0.58), "ncaaf")
    assert 0.48 < curve(0.0) < 0.58 and curve(6.0) > curve(0.0) and 0.5 < curve(8.0) < 0.66
    assert curve(-6.0) == curve(6.0)                                                   # a gap is a size
    assert board.edge_curve(_calibration().head(50), "ncaaf") is None                  # too thin to read
    assert board.edge_curve(None, "ncaaf") is None
    # Without a table the model's own calibration stands in.
    b = board.price(_lines(), _events(), _projections(total=50.0), {}, NOW, None)
    over = b.set_index(["market", "side"]).loc[("total", "over")]
    assert over["p_atlas"] == pytest.approx(board.atlas_over(50.0, 0.35, 15.8, 44.5), abs=1e-6)


def test_the_market_record_appends_on_change_and_seals(tmp_path):
    where = tmp_path / "owner_market"
    first = _lines()
    record, added = market_store.append(market_store.load(KEY, where), first)
    assert len(added) == len(first) and len(record) == len(first)
    market_store.seal(record, KEY, added, where)
    files = sorted(where.glob("*.enc.json"))
    assert len(files) == 1 and files[0].name == "market-2026-W39.enc.json"
    text = files[0].read_text()
    assert "44.5" not in text and "DraftKings" not in text and set(json.loads(text)) >= {"ct", "iv", "salt"}
    # The same lines again: nothing added. One book moves: one row added.
    same = first.assign(captured_at="2026-09-26T13:20:00+00:00")
    record, added = market_store.append(record, same)
    assert added.empty
    moved = same.copy()
    moved.loc[(moved["book_id"] == 12) & (moved["selection"] == "over"), "line"] = 45.5
    record, added = market_store.append(record, moved)
    assert len(added) == 1 and added["book_id"].iloc[0] == 12
    market_store.seal(record, KEY, added, where)
    loaded = market_store.load(KEY, where)
    assert len(loaded) == len(first) + 1
    latest = market_store.latest(loaded).set_index(["market", "selection", "book_id"])
    assert latest.loc[("total", "over", 12), "line"] == 45.5 and latest.loc[("total", "over", 19), "line"] == 44.5
    # The close: the last line before kickoff per book.
    kick = pd.Series({"401866429": pd.Timestamp("2026-09-27T01:00Z")})
    closes = market_store.closing(loaded, kick)
    assert closes[(closes["book_id"] == 12) & (closes["selection"] == "over")]["line"].iloc[0] == 45.5
    with pytest.raises(sealed.Unreadable):
        market_store.load("another key", where)


def test_picks_are_logged_once_and_graded_on_the_score_and_the_consensus_close(tmp_path):
    b = board.price(_lines(), _events(), _projections(total=50.0), {}, NOW, _calibration())
    chosen = board.picks(b)
    chosen = pd.concat([chosen, b[(b["market"] == "spread") & (b["side"] == "home")]], ignore_index=True)
    games = pd.DataFrame([{"game_id": 401866429, "home_team": "Sacramento State Hornets", "away_team": "Massachusetts Minutemen",
                           "kickoff": "2026-09-27T01:00Z", "completed": True, "home_score": 27, "away_score": 24}])
    where = tmp_path / "owner_board"
    record, weeks = board.log_picks(board.load_picks(KEY, where), chosen, games, NOW)
    assert weeks == {(2026, 4)} and len(record) == 2
    board.seal_picks(record, KEY, weeks, where)
    assert "Hornets" not in (where / "2026-04.enc.json").read_text()
    again, weeks = board.log_picks(record, chosen, games, NOW)
    assert weeks == set() and len(again) == 2                                          # never twice
    # Final 27-24 (total 51): the over 44.5 wins; the home +5.5 covers. The consensus closed 45.5 / +5.
    from atlas.owner import paper

    closes = pd.DataFrame([
        {"captured_at": "2026-09-27T00:50:00+00:00", "sport": "ncaaf", "game_id": "401866429", "event_id": 32187, "market": "total",
         "selection": "over", "participant": None, "book_id": 0, "line": 45.5, "cost": -110, "updated": None, "is_off": False,
         "open_line": 46.5, "open_cost": -110, "open_book": 10, "open_created": None},
        {"captured_at": "2026-09-27T00:50:00+00:00", "sport": "ncaaf", "game_id": "401866429", "event_id": 32187, "market": "total",
         "selection": "under", "participant": None, "book_id": 0, "line": 45.5, "cost": -110, "updated": None, "is_off": False,
         "open_line": 46.5, "open_cost": -110, "open_book": 10, "open_created": None},
        {"captured_at": "2026-09-27T00:50:00+00:00", "sport": "ncaaf", "game_id": "401866429", "event_id": 32187, "market": "spread",
         "selection": "CSUS", "participant": "CSUS", "book_id": 0, "line": 5.0, "cost": -110, "updated": None, "is_off": False,
         "open_line": 6.5, "open_cost": -110, "open_book": 10, "open_created": None},
        {"captured_at": "2026-09-27T00:50:00+00:00", "sport": "ncaaf", "game_id": "401866429", "event_id": 32187, "market": "spread",
         "selection": "UMASS", "participant": "UMASS", "book_id": 0, "line": -5.0, "cost": -110, "updated": None, "is_off": False,
         "open_line": -6.5, "open_cost": -110, "open_book": 10, "open_created": None},
    ])
    g = board.grade_picks(board.load_picks(KEY, where), paper.results(None, games), closes, _events(), {}).set_index(["market", "side"])
    over, home = g.loc[("total", "over")], g.loc[("spread", "home")]
    assert over["outcome"] == "win" and over["profit"] == pytest.approx(100 / 105)
    assert over["close_line"] == 45.5 and over["clv"] == 1.0 and over["clv_result"] == "beat" and over["clv_prob"] > 0
    assert home["outcome"] == "win" and home["close_line"] == 5.0 and home["clv"] == -0.5 and home["clv_result"] == "lost"
    section = board.sections(b, chosen, g.reset_index(), {"401866429": "UMass @ Sacramento State"}, NOW, 20)[0]
    titles = [t["title"] for t in section["tables"]]
    assert titles[0].startswith("Picks now: 2") and any(t.startswith("Totals board") for t in titles)
    assert any(t.startswith("Board record") for t in titles) and any(t == "Latest graded picks" for t in titles)
    record_rows = dict(next(t for t in section["tables"] if t["title"].startswith("Board record"))["rows"])
    assert record_rows["Won-lost-push"] == "2-0-0" and record_rows["Beat-push-lost the consensus close"] == "1-0-1"
    assert any("wind 18 mph" in r[-1] for r in next(t for t in section["tables"] if t["title"].startswith("Totals board"))["rows"])


class _FakeClient:
    """Stands in for BettingPros: the events and offers the probe saw, and a count of calls."""

    def __init__(self):
        self.calls = 0

    def get(self, path, **params):
        self.calls += 1
        if path == "/offers":
            market = "total" if int(params["market_id"]) == bp.MARKETS["ncaaf"]["total"] else "spread"
            return _offers_body(32187, market)
        return {"events": [{"id": 32187, "scheduled": "2026-09-27 01:00:00", "season": 2026, "week": 4, "status": "scheduled",
                            "home": "CSUS", "visitor": "UMASS", "venue": {"stadium_type": "outdoor"},
                            "weather": {"forecast_wind_speed": 18, "forecast_temp": 70},
                            "participants": [{"id": "CSUS", "name": "Hornets", "team": {"city": "Sacramento St.", "conference": "Big Sky"}},
                                             {"id": "UMASS", "name": "Minutemen", "team": {"city": "UMass", "conference": "Ind"}}]}],
                "_pagination": {"total_pages": 1}}

    def paged(self, path, key, **params):
        return self.get(path, **params).get(key) or []


def test_the_board_rides_in_the_plays_box_and_only_when_bettingpros_is_configured(tmp_path, monkeypatch):
    from atlas.dfs import owner
    from atlas.owner import plays

    monkeypatch.setenv(owner.SECRET, KEY)
    monkeypatch.setenv("ATLAS_TRACKING_DIR", str(tmp_path / "tracking"))
    monkeypatch.delenv(bp.KEY, raising=False)
    store = Store.open(tmp_path / "tracking")
    store.write("games", pd.DataFrame([{"game_id": 401866429, "home_team": "Sacramento State Hornets", "season": 2026, "week": 4,
                                        "away_team": "Massachusetts Minutemen", "kickoff": "2026-09-27T01:00Z"}]))
    store.write("projections", _projections())
    store.write("snapshots", pd.DataFrame([{"captured_at": "2026-09-26T08:00:00+00:00", "game_id": 401866429, "book": "DraftKings",
                                            "market": "total", "line": 44.5, "price": -110.0, "other_price": -110.0}]))
    research = pd.DataFrame({"game_id": [401866429], "actual_margin": [None], "actual_total": [None], "season_type": ["regular"],
                             "home_team": ["Sacramento State"], "away_team": ["UMass"]})
    monkeypatch.setattr("atlas.research.dataset.load_research_frame", lambda: research)
    where = tmp_path / "plays.enc.json"
    plays.refresh(now=NOW, where=where)
    data = json.loads(owner.decrypt(plays.read_page(where)["box"], KEY))
    assert [s["title"] for s in data["sections"]][0].startswith("Curated plays")      # no BettingPros: no board
    fake = _FakeClient()
    monkeypatch.setattr(bp.Client, "from_env", classmethod(lambda cls: fake))
    plays.refresh(now=NOW, where=where)
    data = json.loads(owner.decrypt(plays.read_page(where)["box"], KEY))
    assert data["sections"][0]["title"] == "The board" and fake.calls >= 3
    picks_table = data["sections"][0]["tables"][0]
    assert picks_table["title"].startswith("Picks now")
    text = where.read_text()
    assert "Hornets" not in text and "BetMGM" not in text and "44.5" not in text
    assert (tmp_path / "tracking" / "owner_market").exists()                          # the lines, sealed
