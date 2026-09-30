"""High Five: the day's five wagers and five props, a five-leg parlay when one book has the legs; logged once, graded."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pandas as pd
import pytest

from atlas.owner import highfive, parlays, pickem, sealed
from atlas.owner.board import LEG_COLUMNS

KEY = "correct horse battery staple"
NOW = datetime(2026, 9, 26, 14, 4, tzinfo=UTC)                 # Saturday 10:04 ET
EARLY = datetime(2026, 9, 26, 13, 30, tzinfo=UTC)              # 09:30 ET
SAT = [f"2026-09-26T{h}:00:00Z" for h in ("16", "17", "18", "19", "20", "21", "22")]
NAMES = {str(i): f"Away{i} @ Home{i}" for i in range(1, 9)}


def _leg(game, market, side, book, cost, p, kickoff, line=44.5, sport="ncaaf", updated="2026-09-26T13:50:00Z"):
    ev = parlays.decimal(cost) * p - 1.0
    atlas = market == "total" or sport == "nhl"
    return {"game_id": str(game), "event_id": game, "sport": sport, "season": 2026, "week": 4, "kickoff": kickoff,
            "market": market, "side": side, "book_id": book, "line": line, "cost": float(cost), "updated": updated,
            "cons_line": line, "cons_cost": -110.0, "open_line": line, "move": 0.0,
            "p_fair": p if not atlas else 0.5, "p_atlas": p if atlas else float("nan"),
            "ev_price": ev if not atlas else -0.02, "ev_atlas": ev if atlas else float("nan"),
            "atlas_number": 48.0, "forecast_wind": float("nan"), "stadium_type": None}


def _legs(five_at_one_book=True):
    rows = [
        # BetMGM (19): six games with edge, so its best five compound.
        _leg(1, "total", "over", 19, -105, 0.58, SAT[0]),
        _leg(2, "spread", "home", 19, -108, 0.56, SAT[1], line=3.0),
        _leg(3, "total", "under", 19, +100, 0.54, SAT[2]),
        _leg(4, "total", "over", 19, -110, 0.56, SAT[3]),
        _leg(5, "spread", "away", 19, -110, 0.55, SAT[4], line=-6.5),
        _leg(6, "total", "over", 19, -110, 0.535, SAT[5]),
        # FanDuel (10): a better price on game 1's over, and the same game's spread: one wager a game.
        _leg(1, "total", "over", 10, +100, 0.58, SAT[0]),
        _leg(1, "spread", "home", 10, -110, 0.56, SAT[0], line=-3.5),
        _leg(7, "total", "under", 10, -110, 0.50, SAT[6]),                   # no edge
        # Sunday: not today.
        _leg(8, "total", "over", 19, -105, 0.60, "2026-09-27T17:00:00Z"),
    ]
    if not five_at_one_book:
        rows = [r for r in rows if not (r["book_id"] == 19 and r["game_id"] in ("5", "6"))]
    return pd.DataFrame(rows, columns=LEG_COLUMNS)


def _priced():
    def p(game, key, player, market, side, line, prob, books=3, kick=SAT[0], team="ATL", sport="nfl"):
        return {"sport": sport, "event_id": int(game), "game_id": str(game), "kickoff": kick, "day": "2026-09-26",
                "player_key": key, "player": player, "team": team, "position": "WR", "market": market, "line": line,
                "p_over": prob if side == "over" else 1 - prob, "p_under": prob if side == "under" else 1 - prob,
                "p_push": 0.0, "books": books, "book_line": line, "side": side, "p": prob, "updated": "",
                "p_atlas": float("nan")}

    rows = [
        p(1, "a", "Drake London", "receiving-yards", "over", 62.5, 0.66),
        p(1, "a", "Drake London", "receptions", "over", 4.5, 0.62),            # same player: one prop
        p(1, "b", "Bijan Robinson", "rushing-yards", "over", 80.5, 0.61),
        p(1, "c", "Kyle Pitts", "receiving-yards", "under", 45.5, 0.60),       # third of game 1: over the per-game cap
        p(2, "d", "Jordan Love", "passing-yards", "under", 245.5, 0.59, kick=SAT[1]),
        p(3, "e", "Jahan Dotson", "receptions", "over", 3.5, 0.58, kick=SAT[2]),
        p(4, "f", "Romeo Doubs", "receiving-yards", "over", 45.5, 0.57, kick=SAT[3]),
        p(5, "g", "A Skater", "shots", "over", 2.5, 0.56, kick=SAT[4], sport="nhl"),
        p(6, "h", "Below The Floor", "goals", "under", 0.5, 0.53, kick=SAT[5]),
        p(7, "i", "Already Started", "hits", "over", 1.5, 0.70, kick="2026-09-26T13:00:00Z"),
    ]
    return pd.DataFrame(rows, columns=pickem.PRICED_COLUMNS)


GAMES = pd.DataFrame({"game_id": [str(i) for i in range(1, 9)], "season": 2026, "week": 4, "completed": False})


def test_the_five_wagers_are_the_best_by_ev_one_a_game_at_the_best_price():
    w = highfive.pick_wagers(_legs(), NOW)
    assert list(w["rank"]) == [1, 2, 3, 4, 5] and w["score"].is_monotonic_decreasing
    assert w["game_id"].is_unique and set(w["day"]) == {"2026-09-26"} and "8" not in set(w["game_id"])
    first = w.iloc[0]
    # Game 1's over: FanDuel's +100 beats BetMGM's -105 on the same probability; its spread is not a second wager.
    assert (first["game_id"], first["book_id"], first["cost"]) == ("1", 10, 100.0)
    assert len(w) == 5 and not (w["score"] <= 0).any()
    assert set(w["basis"]) == {"atlas", "market"}          # totals on Atlas's probability, spreads on the price


def test_fewer_than_five_wagers_when_fewer_have_an_edge():
    few = _legs().iloc[[0, 1, 8]]
    assert len(highfive.pick_wagers(few, NOW)) == 2


def test_the_five_props_are_the_likeliest_one_a_player_two_a_game_from_the_floor():
    p = highfive.pick_props(_priced(), NOW)
    assert list(p["player"]) == ["Drake London", "Bijan Robinson", "Jordan Love", "Jahan Dotson", "Romeo Doubs"]
    assert p["p"].is_monotonic_decreasing and list(p["rank"]) == [1, 2, 3, 4, 5]
    assert (p["market"].iloc[0]) == "receiving-yards"                    # his likelier prop, not the receptions
    assert "Kyle Pitts" not in set(p["player"]) and "Already Started" not in set(p["player"])
    assert "Below The Floor" not in set(p["player"])
    assert highfive.pick_props(None, NOW).empty and highfive.pick_props(_priced().iloc[0:0], NOW).empty


def test_the_parlay_is_the_books_five_best_legs_in_five_games_and_only_when_a_book_has_five():
    t = highfive.pick_parlay(_legs(), NAMES, NOW)
    assert len(t) == 1 and t["n_legs"].iloc[0] == 5 and t["book_id"].iloc[0] == 19
    legs = json.loads(t["legs"].iloc[0])
    assert len({lg["game_id"] for lg in legs}) == 5 and "6" not in {lg["game_id"] for lg in legs}  # its sixth-best sits out
    dec = p = 1.0
    for lg in legs:
        dec *= parlays.decimal(lg["cost"])
        p *= lg["p"]
    assert t["ev"].iloc[0] == pytest.approx(dec * p - 1, abs=2e-3) and t["ev"].iloc[0] > 0
    assert highfive.pick_parlay(_legs(five_at_one_book=False), NAMES, NOW).empty


def test_each_kind_is_logged_once_at_ten_eastern_sealed_and_never_revised(tmp_path):
    where = tmp_path / "owner_highfive"
    w, pr = highfive.pick_wagers(_legs(), NOW), highfive.pick_props(_priced(), NOW)
    assert not highfive.due(highfive.load(KEY, where), "wager", "2026-09-26", EARLY)
    assert highfive.due(highfive.load(KEY, where), "wager", "2026-09-26", NOW)
    assert not highfive.due(highfive.load(KEY, where), "wager", "2026-09-27", NOW)           # tomorrow's: not tonight
    record, weeks = highfive.log(highfive.load(KEY, where), w, pr, NAMES, GAMES, NOW)
    assert weeks == {(2026, 4)} and len(record) == 10 and set(record["kind"]) == {"wager", "prop"}
    highfive.seal(record, KEY, weeks, where)
    text = (where / "2026-04.enc.json").read_text()
    assert "Drake London" not in text and "Away1 @ Home1" not in text and "44.5" not in text
    with pytest.raises(sealed.Unreadable):
        highfive.load("not the key", where)
    again = highfive.load(KEY, where)
    assert len(again) == 10
    # A later run with a different top five logs nothing more for the day.
    later = datetime(2026, 9, 26, 15, 4, tzinfo=UTC)
    changed = _legs().assign(cost=lambda d: d["cost"] + 5.0)
    same, weeks2 = highfive.log(again, highfive.pick_wagers(changed, later), highfive.pick_props(_priced(), later),
                                NAMES, GAMES, later)
    assert weeks2 == set() and len(same) == 10
    # The props can log later than the wagers when PrizePicks posts late.
    only_wagers, _ = highfive.log(highfive.load(KEY, tmp_path / "x"), w, highfive.pick_props(None, NOW), NAMES, GAMES, NOW)
    assert set(only_wagers["kind"]) == {"wager"}
    both, weeks3 = highfive.log(only_wagers, w, pr, NAMES, GAMES, later)
    assert len(both) == 10 and weeks3 == {(2026, 4)}


def _box(sport, game_id):
    rows = {"1": [("Drake London", 70.0, 5), ("Bijan Robinson", 60.0, 1)], "2": [("Jordan Love", 260.0, 0)]}
    if game_id not in rows:
        return None
    return pd.DataFrame([{"name": n, "team": "ATL", "rec_yds": y, "rush_yds": y, "pass_yds": y, "rec": c}
                         for n, y, c in rows[game_id]])


def test_plays_are_graded_wagers_at_the_price_and_props_on_the_box_score(tmp_path):
    w, pr = highfive.pick_wagers(_legs(), NOW), highfive.pick_props(_priced(), NOW)
    record, _ = highfive.log(highfive.load(KEY, tmp_path), w, pr, NAMES, GAMES, NOW)
    finals = pd.DataFrame({"game_id": ["1", "2"], "final_total": [50.0, 50.0], "final_margin": [3.0, 2.0]})
    games = GAMES.assign(completed=[True, True] + [False] * 6)
    later = datetime(2026, 9, 27, 4, 0, tzinfo=UTC)
    graded, changed = highfive.grade(record, finals, games, later, _box)
    assert changed == {(2026, 4)}
    wagers = graded[graded["kind"] == "wager"].set_index("game_id")
    g1 = wagers.loc["1"]                                                     # over 44.5 at +100, final 50: a win
    assert g1["outcome"] == "win" and g1["profit"] == pytest.approx(1.0)
    assert wagers.loc["2", "outcome"] == "win"                               # home +3, won by 2: covers
    assert wagers.loc["3", "outcome"] is None or pd.isna(wagers.loc["3", "outcome"])      # not played yet
    props = graded[graded["kind"] == "prop"].set_index("player")
    assert props.loc["Drake London", "outcome"] == "win" and props.loc["Drake London", "actual"] == 70.0    # over 62.5
    assert props.loc["Bijan Robinson", "outcome"] == "loss"                                  # over 80.5, ran for 60
    assert props.loc["Jordan Love", "outcome"] == "loss"                                     # under 245.5, threw 260


def _build(tmp_path, now, legs=None, priced=None, finals=None, games=GAMES):
    finals = pd.DataFrame(columns=["game_id", "final_total", "final_margin"]) if finals is None else finals
    return highfive.build(_legs() if legs is None else legs, _priced() if priced is None else priced, finals, games,
                          NAMES, KEY, now, where=tmp_path / "owner_highfive", parlays_where=tmp_path / "parlays",
                          box=_box)


def test_the_tab_shows_provisional_plays_before_ten_then_the_logged_five_and_the_record(tmp_path):
    early = _build(tmp_path, EARLY)
    assert len(early) == 1 and early[0]["tab"] == "High Five" and early[0]["title"] == "Daily High Five"
    assert "provisional" in early[0]["tables"][0]["title"] and len(early[0]["tables"][0]["rows"]) == 5
    assert early[0]["tables"][0]["rows"][0][-1] == "not logged yet"
    assert not (tmp_path / "owner_highfive").exists()                              # nothing logged before the moment
    shown = _build(tmp_path, NOW)
    wagers, props, parlay = shown[0]["tables"][:3]
    assert wagers["title"] == "Top five game wagers, Sat Sep 26" and props["title"] == "Top five props, Sat Sep 26"
    assert [r[0] for r in wagers["rows"]] == ["1", "2", "3", "4", "5"] and wagers["rows"][0][-1] == "open"
    assert wagers["rows"][0][2][0] == "Over 44.5 (+100)" and any(r[2][0].startswith("Home2 +3") for r in wagers["rows"])
    assert props["rows"][0][1][0] == "Drake London" and props["rows"][0][2] == "Over 62.5 rec yds"
    assert parlay["title"].startswith("Five-leg parlay") and len(parlay["rows"]) == 1
    assert parlay["rows"][0][0][0] == "BetMGM" and parlay["rows"][0][3] == "open"
    record = next(t for t in shown[0]["tables"] if t["title"].startswith("The record"))
    assert record["rows"][2] == ["Won-lost-push", "0-0-0", "0-0-0", "0-0-0"]
    # The day after: results in, the record and the day by day read them.
    finals = pd.DataFrame({"game_id": ["1", "2", "3", "4", "5", "6"], "final_total": [50.0, 50.0, 40.0, 50.0, 40.0, 50.0],
                           "final_margin": [3.0, 2.0, 1.0, 1.0, 7.0, 1.0]})
    games = GAMES.assign(completed=[True] * 4 + [False] * 4)
    after = _build(tmp_path, datetime(2026, 9, 27, 4, 0, tzinfo=UTC), finals=finals, games=games)
    record = next(t for t in after[0]["tables"] if t["title"].startswith("The record"))
    w, _, a = record["rows"][2][1], record["rows"][2][2], record["rows"][2][3]
    assert w.count("-") == 2 and w != "0-0-0" and a != "0-0-0"
    assert any(t["title"] == "Day by day" for t in after[0]["tables"])
    assert any(t["title"] == "Latest graded plays" for t in after[0]["tables"])
    assert len(highfive.load(KEY, tmp_path / "owner_highfive")) == 10                # still the same ten
    parlay_record = parlays.load(KEY, tmp_path / "parlays")
    assert len(parlay_record) == 1


def test_no_legs_and_no_props_shows_why_and_never_raises(tmp_path):
    sec = _build(tmp_path, NOW, legs=pd.DataFrame(columns=LEG_COLUMNS), priced=pd.DataFrame(columns=pickem.PRICED_COLUMNS))
    tables = sec[0]["tables"]
    assert "No wager with positive expected value" in tables[0]["rows"][0][0]
    assert "No prop at 54% or better" in tables[1]["rows"][0][0]
    assert "No book has five" in tables[2]["rows"][0][0]
    broken = highfive.build(None, None, None, None, {}, KEY, NOW, where=tmp_path / "a", parlays_where=tmp_path / "b")
    assert "could not build the High Five" in broken[0]["notes"][0]


def test_the_public_page_and_script_never_name_the_project():
    from pathlib import Path

    from atlas.site import render

    script = (Path(highfive.__file__).parents[1] / "site" / "assets" / "owner.js").read_text()
    page = render.owner_page({"box": None, "reason": "x"}, plays={"box": None, "reason": "y"})
    for text in (script, page):
        assert "High Five" not in text and "highfive" not in text.lower() and "High5" not in text
