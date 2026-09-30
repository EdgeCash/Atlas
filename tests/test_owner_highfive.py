"""The daily plays: rule daily-v1 on the board's legs, however few pass; logged once, graded, labelled, private."""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pytest

from atlas.owner import highfive, sealed
from atlas.owner.board import LEG_COLUMNS

KEY = "correct horse battery staple"
NOW = datetime(2026, 9, 26, 14, 4, tzinfo=UTC)                 # Saturday 10:04 ET
EARLY = datetime(2026, 9, 26, 13, 30, tzinfo=UTC)              # 09:30 ET
SAT = [f"2026-09-26T{h}:00:00Z" for h in ("16", "17", "18", "19", "20", "21", "22", "23")]
NAMES = {str(i): f"Away{i} @ Home{i}" for i in range(1, 12)}
GAMES = pd.DataFrame({"game_id": [str(i) for i in range(1, 12)], "season": 2026, "week": 4, "completed": False})


def _leg(game, market, side, book, cost, kickoff, *, line=44.5, atlas=48.0, p_fair=0.5, p_atlas=float("nan"),
         ev_price=None, ev_atlas=None, sport="ncaaf"):
    dec = 1 + (100 / -cost if cost < 0 else cost / 100)
    ev_price = p_fair * dec - 1 if ev_price is None else ev_price
    ev_atlas = (p_atlas * dec - 1 if not np.isnan(p_atlas) else float("nan")) if ev_atlas is None else ev_atlas
    return {"game_id": str(game), "event_id": game, "sport": sport, "season": 2026, "week": 4, "kickoff": kickoff,
            "market": market, "side": side, "book_id": book, "line": line, "cost": float(cost),
            "updated": "2026-09-26T13:50:00Z", "cons_line": line, "cons_cost": -110.0, "open_line": line, "move": 0.0,
            "p_fair": p_fair, "p_atlas": p_atlas, "ev_price": ev_price, "ev_atlas": ev_atlas, "atlas_number": atlas,
            "forecast_wind": float("nan"), "stadium_type": None}


def _legs():
    rows = [
        # Football totals: Atlas 48 against a 44.5 line says over. The over at a good price is a play, ranked by
        # price edge; the under, even at a great price, is not Atlas's side; a loud disagreement at a bad price is not.
        _leg(1, "total", "over", 10, +105, SAT[0], p_fair=0.51),                      # +4.6% price edge
        _leg(1, "total", "over", 19, -110, SAT[0], p_fair=0.51),                      # same side, worse price
        _leg(1, "total", "under", 10, +120, SAT[0], p_fair=0.49),                     # not Atlas's side
        _leg(2, "total", "over", 10, -115, SAT[1], atlas=60.0, p_fair=0.50),          # Atlas +15.5, negative price edge
        _leg(3, "total", "under", 12, +100, SAT[2], atlas=40.0, p_fair=0.52),         # +4% price edge, Atlas's side
        # Football spread: Atlas margin +5 on a home -3 line says home covers; the away side is not Atlas's.
        _leg(4, "spread", "home", 10, +100, SAT[3], line=-3.0, atlas=5.0, p_fair=0.515),
        _leg(4, "spread", "away", 10, +100, SAT[3], line=3.0, atlas=5.0, p_fair=0.515),
        # NHL: Atlas's favourite with EV is a play; Atlas's underdog with EV is not; a favourite without EV is not.
        _leg(5, "moneyline", "home", 10, -140, SAT[4], line=0.0, atlas=0.62, p_fair=0.58, p_atlas=0.61, sport="nhl"),
        _leg(6, "moneyline", "away", 10, +150, SAT[5], line=0.0, atlas=0.55, p_fair=0.42, p_atlas=0.45, sport="nhl"),
        _leg(7, "moneyline", "home", 10, -200, SAT[6], line=0.0, atlas=0.60, p_fair=0.66, p_atlas=0.64, sport="nhl"),
        # Sunday: not today.
        _leg(8, "total", "over", 10, +110, "2026-09-27T17:00:00Z", p_fair=0.51),
        # Already started.
        _leg(9, "total", "over", 10, +110, "2026-09-26T13:00:00Z", p_fair=0.51),
    ]
    return pd.DataFrame(rows, columns=LEG_COLUMNS)


def _calibration():
    rows = []
    for i in range(120):
        rows.append({"sport": "nhl", "market": "moneyline", "won": float(i % 2 == 0 or i >= 100),     # last 100: 60%
                     "kickoff": f"2026-0{1 + i // 28}-{1 + i % 28:02d}T00:00:00Z"})
        rows.append({"sport": "ncaaf", "market": "total", "won": float(i % 5 == 0),                  # 20%
                     "kickoff": f"2026-0{1 + i // 28}-{1 + i % 28:02d}T00:00:00Z"})
    rows.append({"sport": "ncaaf", "market": "margin", "won": 1.0, "kickoff": "2026-09-01T00:00:00Z"})  # too few
    return pd.DataFrame(rows)


def test_the_bar_not_a_count_decides_the_plays():
    w = highfive.pick_wagers(_legs(), NOW, _calibration())
    assert list(w["game_id"]) == ["5", "1", "3", "4"]                                # NHL by Atlas EV, then price edge
    assert list(w["rank"]) == [1, 2, 3, 4] and w["score"].is_monotonic_decreasing
    assert w.set_index("game_id").loc["1", "cost"] == 105.0                          # the better price of the over
    assert "2" not in set(w["game_id"])                                              # loud, but no price edge
    assert "6" not in set(w["game_id"]) and "7" not in set(w["game_id"])             # NHL dog; favourite without EV
    assert "8" not in set(w["game_id"]) and "9" not in set(w["game_id"])
    assert list(w["basis"]) == ["atlas", "price", "price", "price"]
    # Labels: the model's last-100 form in the play's market; nan where the table is thin.
    f = w.set_index("game_id")["form"]
    assert f["5"] == pytest.approx(0.6) and f["1"] == pytest.approx(0.2) and np.isnan(f["4"])
    assert highfive.pick_wagers(_legs().iloc[0:0], NOW).empty
    assert highfive.pick_wagers(_legs()[_legs()["game_id"] == "2"], NOW).empty


def test_the_ceiling_holds_and_a_bare_day_logs_nothing():
    many = pd.concat([_legs().assign(game_id=_legs()["game_id"] + s) for s in ("", "a", "b")], ignore_index=True)
    assert len(highfive.pick_wagers(many, NOW)) == highfive.MAX_PLAYS
    late = datetime(2026, 9, 27, 3, 0, tzinfo=UTC)                                    # Sat 23:00 ET: Sunday's slate
    assert set(highfive.pick_wagers(_legs(), late)["game_id"]) == {"8"}


def test_plays_are_logged_once_at_ten_eastern_sealed_never_revised(tmp_path):
    where = tmp_path / "owner_highfive"
    chosen = highfive.pick_wagers(_legs(), EARLY, _calibration())
    early, weeks = highfive.log(highfive.load(KEY, where), chosen, NAMES, GAMES, EARLY)
    assert early.empty and weeks == set()                                            # 09:30 ET: too early
    record, weeks = highfive.log(highfive.load(KEY, where), highfive.pick_wagers(_legs(), NOW, _calibration()),
                                 NAMES, GAMES, NOW)
    assert weeks == {(2026, 4), (2026, 39)} and len(record) == 4 and set(record["rule"]) == {"daily-v1"}
    assert record.set_index("game_id").loc["5", "season"] == 2026                    # the NHL row by ISO week of puck drop
    assert record.set_index("game_id").loc["5", "week"] == 39
    highfive.seal(record, KEY, weeks, where)
    text = (where / "2026-04.enc.json").read_text() + (where / "2026-39.enc.json").read_text()
    assert "Away1 @ Home1" not in text and "Away5 @ Home5" not in text and "44.5" not in text
    with pytest.raises(sealed.Unreadable):
        highfive.load("not the key", where)
    later = datetime(2026, 9, 26, 15, 4, tzinfo=UTC)
    moved = _legs().assign(cost=lambda d: d["cost"] + 30.0)
    again, weeks2 = highfive.log(highfive.load(KEY, where), highfive.pick_wagers(moved, later), NAMES, GAMES, later)
    assert weeks2 == set() and len(again) == 4
    assert again.set_index("pick_id")["cost"].to_dict() == record.set_index("pick_id")["cost"].to_dict()


def test_plays_are_graded_on_the_score_at_the_price_logged(tmp_path):
    record, _ = highfive.log(highfive.load(KEY, tmp_path), highfive.pick_wagers(_legs(), NOW), NAMES, GAMES, NOW)
    finals = pd.DataFrame({"game_id": ["1", "3", "4", "5"], "final_total": [50.0, 40.0, 50.0, 5.0],
                           "final_margin": [3.0, 2.0, 3.0, 1.0]})
    graded, changed = highfive.grade(record, finals, datetime(2026, 9, 27, 4, 0, tzinfo=UTC))
    g = graded.set_index("game_id")
    assert changed == {(2026, 4), (2026, 39)}
    assert g.loc["1", "outcome"] == "win" and g.loc["1", "profit"] == pytest.approx(1.05)    # over 44.5 at +105
    assert g.loc["3", "outcome"] == "win" and g.loc["3", "profit"] == pytest.approx(1.0)     # under 44.5 at +100
    assert g.loc["4", "outcome"] == "push" and g.loc["4", "profit"] == 0.0                   # home -3, won by 3
    assert g.loc["5", "outcome"] == "win" and g.loc["5", "profit"] == pytest.approx(100 / 140)  # ML at -140


def _build(tmp_path, now, legs=None, finals=None):
    finals = pd.DataFrame(columns=["game_id", "final_total", "final_margin"]) if finals is None else finals
    return highfive.build(_legs() if legs is None else legs, finals, GAMES, NAMES, KEY, now,
                          calibration=_calibration(), where=tmp_path / "owner_highfive")


def test_the_tab_shows_provisional_plays_then_the_logged_ones_and_the_labelled_record(tmp_path):
    early = _build(tmp_path, EARLY)
    assert early[0]["tab"] == "Daily" and early[0]["title"] == "Daily plays"
    first = early[0]["tables"][0]
    assert "provisional" in first["title"] and len(first["rows"]) == 4 and first["rows"][0][4][0] == "not logged yet"
    assert not (tmp_path / "owner_highfive").exists()
    shown = _build(tmp_path, NOW)
    plays = shown[0]["tables"][0]
    assert plays["title"] == "Plays for Sat Sep 26" and [r[0] for r in plays["rows"]] == ["1", "2", "3", "4"]
    assert plays["rows"][0][2][0] == "Home5 ML (-140)" and plays["rows"][0][4] == ["open", "form 60% · market 58%"]
    assert plays["rows"][1][2][0] == "Over 44.5 (+105)" and "price vs consensus" in plays["rows"][1][3][1]
    rec = next(t for t in shown[0]["tables"] if t["title"].startswith("The record"))
    assert [r[0] for r in rec["rows"]] == ["All plays", "NHL, Atlas's favourite", "Football, price edge",
                                           "Form at or above 50% when logged", "Form below 50%"]
    finals = pd.DataFrame({"game_id": ["1", "3", "4", "5"], "final_total": [50.0, 40.0, 50.0, 5.0],
                           "final_margin": [3.0, 2.0, 3.0, 1.0]})
    after = _build(tmp_path, datetime(2026, 9, 27, 4, 0, tzinfo=UTC), finals=finals)
    rec = next(t for t in after[0]["tables"] if t["title"].startswith("The record"))
    assert rec["rows"][0][1] == "3-0-1" and rec["rows"][0][2].startswith("100.0%")
    assert any(t["title"] == "Day by day" for t in after[0]["tables"])
    assert any(t["title"] == "Latest graded plays" for t in after[0]["tables"])
    assert len(highfive.load(KEY, tmp_path / "owner_highfive")) == 4


def test_nothing_passing_says_so_and_a_failure_never_raises(tmp_path):
    sec = _build(tmp_path, NOW, legs=pd.DataFrame(columns=LEG_COLUMNS))
    assert "No play passes the bar" in sec[0]["tables"][0]["rows"][0][0]
    broken = highfive.build(None, None, None, {}, KEY, NOW, where=tmp_path / "a")
    assert "could not build the daily plays" in broken[0]["notes"][0]


def test_the_public_page_and_script_never_name_the_tab():
    from pathlib import Path

    from atlas.site import render

    script = (Path(highfive.__file__).parents[1] / "site" / "assets" / "owner.js").read_text()
    page = render.owner_page({"box": None, "reason": "x"}, plays={"box": None, "reason": "y"})
    for text in (script, page):
        assert "Daily plays" not in text and "High Five" not in text and "highfive" not in text.lower()
        assert '"Daily"' not in text
