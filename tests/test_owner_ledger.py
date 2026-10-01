"""The prop ledger: every NHL line logged once a day, graded from the box, scored fair against Atlas against 0.5."""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pytest

from atlas.owner import ledger, pickem, sealed

KEY = "correct horse battery staple"
NOW = datetime(2026, 10, 8, 14, 4, tzinfo=UTC)                  # Thursday 10:04 ET
EARLY = datetime(2026, 10, 8, 13, 30, tzinfo=UTC)
KICK = "2026-10-08T23:00:00Z"
NAMES = {"g1": "Bruins @ Rangers", "g2": "Leafs @ Habs", "f1": "Jets @ Chiefs"}
GAMES = pd.DataFrame({"game_id": ["g1", "g2", "f1"], "season": 2026, "week": 41, "completed": False})


def _line(event, game, key, player, market, side, line, p, p_atlas=np.nan, *, sport="nhl", position="G", team="NYR"):
    return {"sport": sport, "event_id": event, "game_id": game, "kickoff": KICK, "day": "2026-10-08", "player_key": key,
            "player": player, "team": team, "position": position, "market": market, "line": line,
            "p_over": p if side == "over" else 1 - p, "p_under": p if side == "under" else 1 - p, "p_push": 0.0,
            "books": 3, "book_line": line, "side": side, "p": p, "updated": "", "p_atlas": p_atlas}


def _priced():
    rows = [
        _line(1, "g1", "shesterkin", "Igor Shesterkin", "saves", "over", 27.5, 0.56, 0.62),
        _line(1, "g1", "swayman", "Jeremy Swayman", "saves", "under", 28.5, 0.52, 0.45),     # not a pick: logged anyway
        _line(1, "g1", "panarin", "Artemi Panarin", "shots", "over", 2.5, 0.58, 0.55, position="LW"),
        _line(2, "g2", "matthews", "Auston Matthews", "shots", "over", 3.5, 0.51, np.nan, position="C", team="TOR"),
        _line(3, "f1", "mahomes", "Patrick Mahomes", "passing-yards", "over", 265.5, 0.60, sport="nfl", position="QB",
              team="KC"),                                                                        # football: not in the ledger
    ]
    return pd.DataFrame(rows, columns=pickem.PRICED_COLUMNS)


def _box(sport, game_id):
    rows = {"g1": [("Igor Shesterkin", "NYR", 31, 0), ("Jeremy Swayman", "BOS", 30, 0), ("Artemi Panarin", "NYR", 0, 2)]}
    if game_id not in rows:
        return None
    return pd.DataFrame([{"name": n, "team": t, "sv": sv, "sog": sog} for n, t, sv, sog in rows[game_id]])


def test_every_nhl_line_is_logged_once_at_ten_eastern_and_sealed(tmp_path):
    where = tmp_path / "owner_prop_ledger"
    assert not ledger.due(ledger.load(KEY, where), "2026-10-08", EARLY)
    led, weeks = ledger.log(ledger.load(KEY, where), _priced(), NAMES, NOW)
    assert weeks == {(2026, 41)} and len(led) == 4 and set(led["sport"]) == {"nhl"}
    assert "Patrick Mahomes" not in set(led["player"]) and "Jeremy Swayman" in set(led["player"])  # not a pick, still logged
    assert pd.isna(led.set_index("player_key").loc["matthews", "p_atlas"])                          # no Atlas: logged, unscored
    ledger.seal(led, KEY, weeks, where)
    text = (where / "2026-41.enc.json").read_text()
    assert "Shesterkin" not in text and "Bruins @ Rangers" not in text and "27.5" not in text
    with pytest.raises(sealed.Unreadable):
        ledger.load("not the key", where)
    again, weeks2 = ledger.log(ledger.load(KEY, where), _priced().assign(line=lambda d: d["line"] + 1), NAMES, NOW)
    assert weeks2 == set() and len(again) == 4 and again.set_index("player_key").loc["shesterkin", "line"] == 27.5
    assert not ledger.due(again, "2026-10-08", NOW)                                                   # once a day


def test_lines_are_graded_from_the_box_and_scored_fair_against_atlas_against_the_coin_flip():
    led, _ = ledger.log(pd.DataFrame(columns=ledger.COLUMNS), _priced(), NAMES, NOW)
    games = GAMES.assign(completed=[True, False, False])
    graded, changed = ledger.grade(led, games, datetime(2026, 10, 9, 5, 0, tzinfo=UTC), _box)
    g = graded.set_index("player_key")
    assert changed == {(2026, 41)}
    assert g.loc["shesterkin", "outcome"] == "win" and g.loc["shesterkin", "actual"] == 31     # over 27.5
    assert g.loc["swayman", "outcome"] == "loss"                                                # under 28.5, made 30
    assert g.loc["panarin", "outcome"] == "loss" and pd.isna(g.loc["matthews", "outcome"])       # over 2.5, had 2; not played
    s = ledger.score(graded).set_index("stat")
    assert list(s.index) == ["sv", "sog"]                                                        # saves first
    saves = s.loc["sv"]
    assert saves["lines"] == 2 and saves["with_atlas"] == 2
    assert saves["brier_fair"] == pytest.approx(((0.56 - 1) ** 2 + (0.52 - 0) ** 2) / 2)
    assert saves["brier_atlas"] == pytest.approx(((0.62 - 1) ** 2 + (0.45 - 0) ** 2) / 2)
    assert saves["brier_half"] == 0.25 and saves["diff"] == pytest.approx(saves["brier_atlas"] - saves["brier_fair"])
    # Fair's side went 1-1; Atlas's side (Shesterkin over, Swayman OVER since it gave the under 45%) went 2-0.
    assert saves["hit_fair"] == 0.5 and saves["hit_atlas"] == 1.0


def _synthetic(n, edge, atlas_better=True):
    """n decided saves lines where the books' fair is 0.55 and Atlas says 0.55 plus ``edge``; the outcomes are
    exactly calibrated to Atlas when it is better and to fair when it is not (no sampling noise)."""
    p_fair = np.full(n, 0.55)
    p_atlas = np.full(n, 0.55 + edge)
    truth = p_atlas if atlas_better else p_fair
    won = (np.arange(n) + 0.5) / n < truth
    return pd.DataFrame({"ledger_id": [str(i) for i in range(n)]}).reindex(columns=ledger.COLUMNS) \
        .assign(market="saves", p=p_fair, p_atlas=p_atlas, outcome=np.where(won, "win", "loss"))


def test_the_saves_verdict_is_pre_registered_collecting_then_clears_or_fails():
    assert ledger.verdict(ledger.score(pd.DataFrame(columns=ledger.COLUMNS))).startswith("Saves: collecting, 0 of 300")
    assert "collecting, 120 of 300" in ledger.verdict(ledger.score(_synthetic(120, 0.15)))
    # A real 15-point edge clears at 400; the same numbers with no edge behind them fail.
    assert ledger.verdict(ledger.score(_synthetic(400, 0.15, atlas_better=True))).startswith("Saves: clears at 400")
    assert ledger.verdict(ledger.score(_synthetic(400, 0.15, atlas_better=False))).startswith("Saves: fails at 400")
    assert ledger.BET_BAR == pytest.approx(1 / 3 ** 0.5)


def test_the_section_and_the_step_never_raise(tmp_path):
    out = ledger.build(_priced(), GAMES, NAMES, KEY, NOW, where=tmp_path / "l", box=_box, day="2026-10-08")
    assert out[0]["tab"] == "Pick'em" and out[0]["title"].startswith("Prop ledger")
    assert out[0]["tables"][0]["title"].startswith("Saves: collecting")
    assert len(ledger.load(KEY, tmp_path / "l")) == 4
    empty = ledger.build(_priced().iloc[0:0], GAMES, NAMES, KEY, NOW, where=tmp_path / "e", box=_box, day=None)
    assert "No NHL line graded yet" in empty[0]["tables"][0]["rows"][0][0]
    broken = ledger.build(None, None, {}, KEY, NOW, where=tmp_path / "b", day="2026-10-08")
    assert "could not build the prop ledger" in broken[0]["notes"][0]
