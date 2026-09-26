"""The day's parlays: same-book legs from different games, compounded, logged once, graded with pushes dropped."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pandas as pd
import pytest

from atlas.owner import parlays, sealed
from atlas.owner.board import LEG_COLUMNS

KEY = "correct horse battery staple"
NOW = datetime(2026, 9, 26, 14, 4, tzinfo=UTC)                 # Saturday 10:04 ET
NAMES = {"1": "A @ B", "2": "C @ D", "3": "E @ F", "4": "G @ H"}


def _leg(game, market, side, book, cost, p, kickoff, line=44.5, ev=None, updated="2026-09-26T13:50:00Z"):
    ev = (1.0 + parlays.decimal(cost) - 1.0) * p - 1.0 if ev is None else ev      # decimal * p - 1
    return {"game_id": str(game), "event_id": game, "sport": "ncaaf", "season": 2026, "week": 4, "kickoff": kickoff,
            "market": market, "side": side, "book_id": book, "line": line, "cost": float(cost), "updated": updated,
            "cons_line": line, "cons_cost": -110.0, "open_line": line, "move": 0.0,
            "p_fair": p if market != "total" else 0.5, "p_atlas": p if market == "total" else float("nan"),
            "ev_price": ev if market != "total" else -0.02, "ev_atlas": ev if market == "total" else float("nan"),
            "atlas_number": 48.0, "forecast_wind": float("nan"), "stadium_type": None}


def _legs():
    sat = ["2026-09-26T16:00:00Z", "2026-09-26T19:30:00Z", "2026-09-26T23:30:00Z"]
    rows = [
        _leg(1, "total", "over", 19, -105, 0.56, sat[0]),                      # BetMGM: three games
        _leg(2, "spread", "home", 19, -108, 0.55, sat[1], line=3.0),
        _leg(3, "total", "under", 19, +100, 0.53, sat[2]),
        _leg(3, "spread", "away", 19, -110, 0.54, sat[2], line=-6.5),          # same game as the under: one leg per game
        _leg(1, "total", "over", 10, -110, 0.56, sat[0]),                      # FanDuel: two games
        _leg(2, "spread", "home", 10, -110, 0.55, sat[1], line=3.0),
        _leg(2, "spread", "away", 10, -110, 0.45, sat[1], line=-3.0),          # negative EV: not a candidate
        _leg(4, "total", "over", 19, -105, 0.57, "2026-09-27T17:00:00Z"),      # Sunday: not today
        _leg(1, "total", "under", 49, -110, 0.44, sat[0]),                     # Hard Rock, negative EV
    ]
    return pd.DataFrame(rows, columns=LEG_COLUMNS)


def test_candidates_are_todays_positive_ev_legs_one_per_game_at_each_book():
    c = parlays.candidates(_legs(), NOW)
    assert set(c["day"]) == {"2026-09-26"} and "4" not in set(c["game_id"])            # Sunday waits its turn
    assert (c["score"] > 0).all()
    # Game 3 at BetMGM: the under at +100 (2.00 x 0.53 - 1 = +6.0%) beats the away side at -110 (+3.1%).
    assert len(c[(c["book_id"] == 19) & (c["game_id"] == "3")]) == 1
    assert c[(c["book_id"] == 19) & (c["game_id"] == "3")]["side"].iloc[0] == "under"
    assert not ((c["book_id"] == 10) & (c["side"] == "away")).any()
    # After the last kickoff of the day, the next day with games is the day.
    late = parlays.candidates(_legs(), datetime(2026, 9, 27, 3, 0, tzinfo=UTC))
    assert set(late["day"]) == {"2026-09-27"} and set(late["game_id"]) == {"4"}


def test_parlays_compound_same_book_legs_from_different_games_and_rank_by_ev():
    chosen = parlays.combine(parlays.candidates(_legs(), NOW), NAMES, NOW)
    assert not chosen.empty and chosen["ev"].is_monotonic_decreasing
    for r in chosen.itertuples():
        legs = json.loads(r.legs)
        assert 2 <= len(legs) <= parlays.MAX_LEGS and len({lg["game_id"] for lg in legs}) == len(legs)
        dec = 1.0
        p = 1.0
        for lg in legs:
            dec *= parlays.decimal(lg["cost"])
            p *= lg["p"]
        assert r.dec_odds == pytest.approx(dec, abs=1e-3) and r.p_hit == pytest.approx(p, abs=1e-3)
        assert r.ev == pytest.approx(dec * p - 1, abs=2e-3) and r.ev > 0
        assert r.kelly == pytest.approx((dec * p - 1) / (dec - 1), abs=2e-3)
        assert r.american == pytest.approx(parlays.american(dec), abs=1.0)
        assert r.oldest_quote == pytest.approx(14.0, abs=0.1)                          # quoted 13:50, now 14:04
    # BetMGM's three-leg parlay exists; FanDuel has only two legs, so only its two-leg parlay.
    assert (chosen[chosen["book_id"] == 19]["n_legs"] == 3).any()
    assert set(chosen[chosen["book_id"] == 10]["n_legs"]) <= {2}
    # An id names the legs and the book, not the price: the same ticket is the same parlay.
    first = json.loads(chosen["legs"].iloc[0])
    assert parlays.parlay_id(chosen["book_id"].iloc[0], list(reversed(first))) == chosen["parlay_id"].iloc[0]


def test_parlays_are_logged_once_sealed_and_graded_with_pushed_legs_dropped(tmp_path):
    where = tmp_path / "owner_parlays"
    chosen = parlays.combine(parlays.candidates(_legs(), NOW), NAMES, NOW)
    record, weeks = parlays.log(parlays.load(KEY, where), chosen)
    assert weeks == {(2026, 4)} and len(record) == len(chosen)
    parlays.seal(record, KEY, weeks, where)
    again, weeks2 = parlays.log(parlays.load(KEY, where), chosen)
    assert weeks2 == set() and len(again) == len(chosen)                                # once
    text = (where / "2026-04.enc.json").read_text()
    assert "A @ B" not in text and "BetMGM" not in text and "44.5" not in text        # sealed
    with pytest.raises(sealed.Unreadable):
        parlays.load("not the key", where)
    # Grading: game 1's over 44.5 wins (48 points); game 2's home +3 pushes (lost by 3); game 3 is still to play.
    finals = pd.DataFrame({"game_id": ["1", "2"], "final_total": [48.0, 50.0], "final_margin": [3.0, -3.0]})
    g = parlays.grade(again, finals)
    # Game 1 over with game 2 home: shown once, at BetMGM, which pays more for that pair than FanDuel.
    pair = g[[parlays._leg_set(json.loads(x)) == "1:total:over|2:spread:home" for x in g["legs"]]].iloc[0]
    assert pair["book_id"] == 19 and pair["outcome"] == "win" and pair["legs_result"] in ("w-p", "p-w")
    won = next(lg for lg in json.loads(pair["legs"]) if lg["game_id"] == "1")
    assert pair["profit"] == pytest.approx(parlays.decimal(won["cost"]) - 1.0, abs=1e-6)  # the push dropped: one leg pays
    three = g[(g["n_legs"] == 3) & (g["book_id"] == 19)].iloc[0]
    assert three["outcome"] == "open"                                                   # game 3 still to play
    lost = parlays.grade(again, pd.DataFrame({"game_id": ["1"], "final_total": [40.0], "final_margin": [0.0]}))
    assert (lost[lost["legs"].str.contains('"game_id": "1"')]["outcome"] == "loss").all()


def test_the_section_states_the_arithmetic_and_shows_the_record():
    chosen = parlays.combine(parlays.candidates(_legs(), NOW), NAMES, NOW)
    finals = pd.DataFrame({"game_id": ["1", "2", "3"], "final_total": [48.0, 50.0, 40.0], "final_margin": [3.0, 2.0, 1.0]})
    sec = parlays.section(chosen, parlays.grade(chosen, finals), NOW)
    assert sec[0]["title"] == "Daily parlays" and "compounded" in sec[0]["notes"][0]
    table = sec[0]["tables"][0]
    assert table["title"].startswith("Parlays for Sat Sep 26") and len(table["rows"]) == len(chosen)
    assert table["rows"][0][0] in ("BetMGM", "FanDuel") and "P(hit)" in table["rows"][0][3] and "¼-Kelly" in table["rows"][0][3]
    titles = [t["title"] for t in sec[0]["tables"]]
    assert any(t.startswith("Parlay record") for t in titles) and any(t.startswith("Latest graded") for t in titles)
    empty = parlays.section(chosen.iloc[0:0], chosen.iloc[0:0].assign(outcome=[], profit=[], legs_result=[]), NOW)
    assert "No two positive-EV legs" in empty[0]["tables"][0]["rows"][0][0]


def test_the_days_set_is_logged_once_at_the_first_run_from_ten_eastern(tmp_path):
    where = tmp_path / "owner_parlays"
    early = datetime(2026, 9, 26, 13, 30, tzinfo=UTC)                                    # 09:30 ET: too early
    chosen = parlays.combine(parlays.candidates(_legs(), early), NAMES, early)
    assert not parlays.due(parlays.load(KEY, where), chosen, early)
    assert parlays.due(parlays.load(KEY, where), chosen, NOW)                            # 10:04 ET: the moment
    parlays.build(_legs(), pd.DataFrame(columns=["game_id", "final_total", "final_margin"]), NAMES, KEY, NOW, where=where)
    logged = parlays.load(KEY, where)
    assert len(logged) and set(logged["day"]) == {"2026-09-26"}
    # A later poll the same day, whatever now ranks first, logs nothing more; the live table marks the logged set.
    later = datetime(2026, 9, 26, 15, 4, tzinfo=UTC)
    sec = parlays.build(_legs(), pd.DataFrame(columns=["game_id", "final_total", "final_margin"]), NAMES, KEY, later,
                        where=where)
    assert len(parlays.load(KEY, where)) == len(logged)
    assert any(row[3].endswith("· logged") for row in sec[0]["tables"][0]["rows"])
    # Parlays for tomorrow, shown tonight, are not logged tonight.
    night = datetime(2026, 9, 27, 3, 0, tzinfo=UTC)                                     # Sat 23:00 ET, Sunday's games
    assert not parlays.due(logged, parlays.combine(parlays.candidates(_legs(), night), NAMES, night), night)


def test_the_same_legs_at_several_books_are_one_ticket_at_the_best_book():
    two_books = pd.concat([_legs(), pd.DataFrame([_leg(1, "total", "over", 49, +100, 0.56, "2026-09-26T16:00:00Z"),
                                                  _leg(2, "spread", "home", 49, -105, 0.55, "2026-09-26T19:30:00Z",
                                                       line=3.0)], columns=LEG_COLUMNS)], ignore_index=True)
    chosen = parlays.combine(parlays.candidates(two_books, NOW), NAMES, NOW)
    sets = [parlays._leg_set(json.loads(x)) for x in chosen["legs"]]
    assert len(sets) == len(set(sets))
    pair = chosen[[s == "1:total:over|2:spread:home" for s in sets]]
    assert len(pair) == 1 and pair["book_id"].iloc[0] == 49                           # Hard Rock pays best for the pair

