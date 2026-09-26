"""The pre-registered NFL quarterback rule test: flags are pre-kickoff, criteria are the document's."""

from __future__ import annotations

import numpy as np
import pandas as pd

from atlas.research import nfl_qb_rule as qb


def test_the_criteria_are_the_pre_registered_ones():
    """docs/NFL_QB_RULE_PREREGISTRATION.md: changing any of these after scoring is the thing the document forbids."""
    assert qb.TEST_SEASONS == (2020, 2021, 2022, 2023, 2024, 2025)
    assert (qb.MIN_DECIDED, qb.BREAK_EVEN, qb.Z, qb.SEASONS_ABOVE_HALF) == (100, 0.5238, 2.24, 4)
    assert [(r.id, r.games, r.side) for r in qb.RULES] == [
        ("Q1", "change", "atlas"), ("Q2", "change", "under"), ("Q3", "injury", "atlas"), ("Q4", "injury", "under")]
    assert (qb.CONTROL.games, qb.CONTROL.side) == ("control", "atlas")


def _frame():
    """Team 1 plays three games; team 2 and 3 fill the other side. Quarterbacks by id."""
    return pd.DataFrame([
        # game 1: team 1's QB of record is A; the depth chart said A. No previous game: not a change.
        {"game_id": 1, "kickoff": "2025-09-07T17:00:00Z", "home_team_id": 1, "away_team_id": 2,
         "home_qb_id": "A", "home_qb1_id": "A", "home_qb2_id": "B", "home_qb1_out": 0.0,
         "away_qb_id": "X", "away_qb1_id": "X", "away_qb2_id": "Y", "away_qb1_out": 0.0, "actual_total": 44.0},
        # game 2: A is listed Out, B is QB2: the expected starter is B, the previous QB of record A. A change,
        # and a QB1-out game. B actually played.
        {"game_id": 2, "kickoff": "2025-09-14T17:00:00Z", "home_team_id": 3, "away_team_id": 1,
         "home_qb_id": "Z", "home_qb1_id": "Z", "home_qb2_id": None, "home_qb1_out": 0.0,
         "away_qb_id": "B", "away_qb1_id": "A", "away_qb2_id": "B", "away_qb1_out": 1.0, "actual_total": 40.0},
        # game 3: the depth chart moved B to QB1 (a benching or A still hurt without a report). Previous QB of
        # record is B, expected B: not a change. The report lists nobody out.
        {"game_id": 3, "kickoff": "2025-09-21T17:00:00Z", "home_team_id": 1, "away_team_id": 2,
         "home_qb_id": "B", "home_qb1_id": "B", "home_qb2_id": "A", "home_qb1_out": 0.0,
         "away_qb_id": "Y", "away_qb1_id": "Y", "away_qb2_id": "X", "away_qb1_out": 0.0, "actual_total": 50.0},
        # game 4: a scheduled game, not yet played, for team 1: QB1 back to A. Previous QB of record is B (game 3):
        # a change, known before kickoff. A game with no result is never anyone's previous game.
        {"game_id": 4, "kickoff": "2025-09-28T17:00:00Z", "home_team_id": 2, "away_team_id": 1,
         "home_qb_id": None, "home_qb1_id": "Y", "home_qb2_id": "X", "home_qb1_out": 0.0,
         "away_qb_id": None, "away_qb1_id": "A", "away_qb2_id": "B", "away_qb1_out": 0.0, "actual_total": np.nan},
    ])


def test_flags_are_knowable_before_kickoff():
    f = qb.flags(_frame()).set_index("game_id")
    assert not f.loc[1, "change"] and not f.loc[1, "injury"]                     # no previous game
    assert f.loc[2, "change"] and f.loc[2, "injury"] and f.loc[2, "away_expected"] == "B" and f.loc[2, "away_prev"] == "A"
    assert not f.loc[2, "home_change"]                                          # Z's first game
    # Game 3: away team 2's previous QB of record was X (game 1); the depth chart now says Y: a change on that
    # side, none on team 1's (B started game 2 and is QB1 now).
    assert not f.loc[3, "home_change"] and f.loc[3, "away_change"] and f.loc[3, "change"] and not f.loc[3, "injury"]
    assert f.loc[4, "away_change"] and f.loc[4, "away_prev"] == "B"             # from the last completed game
    # The actual starter of the game itself is never read: blank every QB of record for the game and the
    # flags for that game do not move.
    blind = _frame()
    blind.loc[blind["game_id"] == 2, ["home_qb_id", "away_qb_id"]] = None
    assert qb.flags(blind).set_index("game_id").loc[2, "change"]


def _scored(n_change=120, change_rate=0.6, n_plain=200, plain_rate=0.5, seed=1):
    """Scored rows over the six seasons: change games won at ``change_rate`` on Atlas's side."""
    rng = np.random.default_rng(seed)
    rows, gid = [], 1
    for season in qb.TEST_SEASONS:
        for kind, n, rate in (("change", n_change // 6, change_rate), ("plain", n_plain // 6, plain_rate)):
            for _ in range(n):
                side = rng.choice(["over", "under"])
                won = rng.random() < rate
                over = 1.0 if (side == "over") == won else 0.0
                rows.append({"game_id": gid, "season": season, "week": 1, "mean": 45.0 + (1 if side == "over" else -1),
                             "line": 45.0, "over": over, "side": side, "kind": kind})
                gid += 1
    scored = pd.DataFrame(rows)
    flags = pd.DataFrame({"game_id": scored["game_id"], "change": scored["kind"] == "change",
                          "injury": False, "home_change": False, "away_change": False,
                          "home_qb1_out": False, "away_qb1_out": False})
    return scored.drop(columns="kind"), flags


def test_a_rule_passes_only_on_all_four_criteria():
    scored, flags = _scored(n_change=600, change_rate=0.62)
    results = qb.evaluate(scored, flags)
    q1 = results["Q1"]
    assert q1["verdict"] == "PASSES" and q1["decided"] == 600 and all(q1["checks"].values())
    assert results["control"]["decided"] == 198 and abs(results["control"]["rate"] - 0.5) < 0.1
    # The same games, the under only: half the picks are on the wrong side of a 62% Atlas rule.
    assert results["Q2"]["decided"] == 600 and results["Q2"]["verdict"] != "PASSES"
    # Too few QB1-out games: not shown, whatever the rate.
    assert results["Q3"]["decided"] == 0 and results["Q3"]["verdict"] == "not shown"
    # A 55% lead on 120 games clears break-even but not the lower bound: a lead, not a result.
    lead = qb.record(qb.grade(qb.select(scored.merge(_scored(n_change=120, change_rate=0.56, seed=3)[1],
                                                     on="game_id", how="left").assign(
        change=lambda d: d["change"].fillna(False).astype(bool), injury=False), qb.RULES[0])))
    assert lead["verdict"] in ("a lead, not a result", "not shown")
    pushes = qb.grade(pd.DataFrame({"over": [0.5, 1.0, 0.0], "taken": ["over", "over", "over"]}))
    assert list(pushes["won"]) == [0.5, 1.0, 0.0]


def test_wilson_lower_bound_is_the_pre_registered_z():
    assert qb.wilson_low(60, 100, z=2.24) < qb.wilson_low(60, 100, z=1.96) < 0.6
    assert np.isnan(qb.wilson_low(0, 0))


def test_the_report_names_every_rule_and_criterion():
    scored, flags = _scored()
    results = qb.evaluate(scored, flags)
    text = qb.report(results, flags, scored)
    assert text.startswith("# NFL quarterback rule")
    for rid in ("Q1", "Q2", "Q3", "Q4"):
        assert f"**{rid}," in text
    assert "Control" in text and "| criterion | met |" in text and "What was not tested" in text
    assert "| 2020 |" in text and "| all |" in text
