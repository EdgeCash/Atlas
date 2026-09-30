"""The puck line's fresh test (docs/NHL_PUCKLINE_FRESH_PREREGISTRATION.md): sides and prices at +/-1.5, the
closes at the off and the thin seasons left out, the five criteria, scored once. Synthetic."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from atlas.live.probability import no_vig
from atlas.owner import nhl_history as hist
from atlas.research import nhl_puckline_fresh as fresh


def _american(p: float) -> float:
    return -100 * p / (1 - p) if p >= 0.5 else 100 * (1 - p) / p


def _league(n=400, edge=0.0, seed=4, at_off=(), dk=True, games_per=None):
    """Closes for 2023-25: the consensus at home -1.5 (market P(home covers) 0.35), DraftKings (or FanDuel) at the
    same price; Atlas off the market by up to ten points either way; the side covers with the market's
    probability plus ``edge`` times the disagreement."""
    rng = np.random.default_rng(seed)
    rows, walked = [], []
    gid = 0
    for season in fresh.SEASONS:
        for _ in range(games_per.get(season, n) if games_per else n):
            gid += 1
            pm = 0.35
            pa = float(np.clip(pm + rng.uniform(-0.10, 0.10), 0.05, 0.95))
            home_side = pa >= pm
            d = abs(pa - pm)
            p_side = (pm if home_side else 1 - pm) + edge * d
            covered = rng.random() < p_side
            home_covers = covered if home_side else not covered
            margin = 2.0 if home_covers else -1.0
            source = "at-off" if season in at_off else "pregame"
            for book in (0, 12 if dk else 10):
                rows += [{"kind": "close", "season": season, "game_id": gid, "market": "spread", "side": "home",
                          "book_id": book, "line": -1.5, "cost": _american(pm), "source": source},
                         {"kind": "close", "season": season, "game_id": gid, "market": "spread", "side": "away",
                          "book_id": book, "line": 1.5, "cost": _american(1 - pm), "source": source}]
            # The moneyline, for the at-the-off check: an in-game price that knows the winner where closed at the off.
            p_ml = (0.95 if margin > 0 else 0.05) if season in at_off else 0.55
            rows += [{"kind": "close", "season": season, "game_id": gid, "market": "moneyline", "side": "home",
                      "book_id": 0, "line": 0.0, "cost": _american(p_ml), "source": source},
                     {"kind": "close", "season": season, "game_id": gid, "market": "moneyline", "side": "away",
                      "book_id": 0, "line": 0.0, "cost": _american(1 - p_ml), "source": source}]
            walked.append({"game_id": gid, "p_home": 0.55, "home_win": float(margin > 0), "p_home_minus_1_5": pa,
                           "p_away_minus_1_5": 0.2, "margin": margin})
        rows.append({"kind": "season", "season": season, "status": "done", "rule": hist.RULE})
    return pd.DataFrame(rows).reindex(columns=hist.COLUMNS), pd.DataFrame(walked)


def test_the_registration_is_what_the_code_runs():
    assert fresh.SEASONS == (2023, 2024, 2025) and fresh.THRESHOLD == 5.0 and fresh.PRICE_BOOKS == (12, 10)
    assert fresh.MIN_GAMES == 300 and fresh.MIN_BETS == 150 and fresh.ALPHA == 0.05
    assert fresh.RESAMPLES == 10_000 and fresh.SEED == 2026 and fresh.SHADE == 5.0


def test_a_side_is_priced_at_its_own_handicap_by_draftkings_else_fanduel():
    record, walked = _league(n=5)
    c = fresh.candidates(record, walked).set_index("game_id")
    g = c.iloc[0]
    pm_home = no_vig(_american(0.35), _american(0.65))
    pa_home = float(walked.set_index("game_id").loc[c.index[0], "p_home_minus_1_5"])
    assert g["side"] == ("home" if pa_home >= pm_home else "away") and g["book_id"] == 12
    assert g["disagreement"] == pytest.approx(100 * abs(pa_home - pm_home))
    fd, fd_walked = _league(n=5, dk=False)
    assert set(fresh.candidates(fd, fd_walked)["book_id"]) == {10}
    none = record[record["book_id"] == 0]
    assert fresh.candidates(none, walked).empty                                     # no price, no bet


def test_home_plus_one_and_a_half_reads_the_away_side_by_two():
    record = pd.DataFrame([
        {"kind": "close", "season": 2024, "game_id": 1, "market": "spread", "side": side, "book_id": b,
         "line": line, "cost": cost, "source": "pregame"}
        for b in (0, 12) for side, line, cost in (("home", 1.5, -250.0), ("away", -1.5, 200.0))]).reindex(
        columns=hist.COLUMNS)
    walked = pd.DataFrame([{"game_id": 1, "p_home": 0.4, "home_win": 0.0, "p_home_minus_1_5": 0.1,
                            "p_away_minus_1_5": 0.40, "margin": -2.0}])
    c = fresh.candidates(record, walked).iloc[0]
    assert c["side"] == "away" and c["covered"]                                    # away by two covered its -1.5
    assert c["p_atlas"] == pytest.approx(0.40) and c["price"] == 200.0


def test_closes_at_the_off_that_look_in_game_and_thin_seasons_are_left_out():
    record, walked = _league(n=320, at_off=(2025,), games_per={2023: 200})
    games, notes = fresh.testable(fresh.candidates(record, walked), record, walked)
    assert notes[2025]["at_off_left_out"] == 320 and notes[2025]["excluded"]      # in-game moneylines: out
    assert notes[2023]["excluded"] and notes[2023]["games"] == 200                 # under 300 games
    assert set(games["season"]) == {2024}


def test_a_real_edge_clears_the_bar_and_none_does_not(tmp_path):
    record, walked = _league(n=700, edge=3.0)
    result = fresh.score(*fresh.testable(fresh.candidates(record, walked), record, walked))
    assert result["real"] and result["bets"] >= fresh.MIN_BETS and result["seasons_up"] >= 2
    record, walked = _league(n=700, edge=0.0, seed=9)
    result = fresh.score(*fresh.testable(fresh.candidates(record, walked), record, walked))
    assert not result["real"]


def test_it_is_scored_once_and_only_when_all_three_seasons_are_in(tmp_path):
    (tmp_path / "reports").mkdir()
    record, walked = _league(n=320)
    partial = record[~((record["kind"] == "season") & (record["season"] == 2023))]
    assert not fresh.due(partial, tmp_path) and fresh.run(partial, walked, tmp_path) is None
    out = fresh.run(record, walked, tmp_path)
    assert out is not None and fresh.json_path(tmp_path).exists()
    text = out.read_text()
    assert "fresh test on 2023-26" in text and "-186" not in text                  # aggregates, never a price
    assert fresh.run(record, walked, tmp_path) is None                             # never scored again
    old_rule = record.copy()
    old_rule.loc[old_rule["kind"] == "season", "rule"] = 1
    assert not fresh.ready(old_rule)
