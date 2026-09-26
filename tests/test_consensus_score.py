"""The consensus test's scoring, on synthetic games only.

No real holdout game is read here: the test is scored once, by the workflow,
and these check only that the machinery does what the pre-registration says.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from scipy.stats import norm

from atlas.research import consensus_score as score
from atlas.research import consensus_validation as cv

SEASONS = range(2018, 2026)          # the warehouse starts in 2018


def _frame(*, informative: bool, per_season: int = 500, seed: int = 7) -> pd.DataFrame:
    """Games where the line knows a team-strength gap ``m``. When
    ``informative``, the consensus also knows ``h``, which the result
    contains and the line does not."""
    rng = np.random.default_rng(seed)
    rows = []
    gid = 0
    for season in SEASONS:
        for i in range(per_season):
            gid += 1
            m = rng.normal(0, 12)
            h = rng.normal(0, 4)
            known = m + (h if informative else 0.0)
            actual = round(m + h + rng.normal(0, 12))
            line = round(m * 2) / 2
            rows.append({
                "game_id": gid, "season": season, "week": 5 + i % 9, "season_type": "regular",
                "closing_spread": -line, "actual_margin": float(actual),
                "home_pregame_elo": 1500 + 25 * known + rng.normal(0, 10), "away_pregame_elo": 1500.0,
                "neutral_site": False,
                "fpi_home_win_prob": float(norm.cdf(known / 15 + rng.normal(0, 0.05))),
            })
    return pd.DataFrame(rows)


def test_the_sign_conventions_match_the_data_dictionary():
    """closing_spread is home-oriented, negative when home is favoured: a
    home side laying 7 that wins by 10 covers by 3."""
    g = pd.DataFrame([{"game_id": 1, "season": 2021, "week": 6, "season_type": "regular",
                       "closing_spread": -7.0, "actual_margin": 10.0}])
    e = score.eligible(g)
    assert e["line"].iloc[0] == 7.0 and e["ats"].iloc[0] == 3.0
    # The consensus thinks home is better than the line says, and home covered: a win.
    won = score.results(e.assign(gap=2.5))["won"].iloc[0]
    assert won == 1
    assert score.results(e.assign(gap=-2.5))["won"].iloc[0] == 0


def test_a_push_is_no_action():
    g = pd.DataFrame([{"game_id": 1, "season": 2021, "week": 6, "season_type": "regular",
                       "closing_spread": -7.0, "actual_margin": 7.0}])
    assert score.results(score.eligible(g).assign(gap=3.0)).empty


def test_early_weeks_and_bowls_are_not_eligible():
    g = pd.DataFrame([
        {"game_id": 1, "season": 2021, "week": 4, "season_type": "regular", "closing_spread": -3.0, "actual_margin": 1.0},
        {"game_id": 2, "season": 2021, "week": 5, "season_type": "regular", "closing_spread": -3.0, "actual_margin": 1.0},
        {"game_id": 3, "season": 2021, "week": 16, "season_type": "postseason", "closing_spread": -3.0, "actual_margin": 1.0},
        {"game_id": 4, "season": 2021, "week": 6, "season_type": "regular", "closing_spread": None, "actual_margin": 1.0},
    ])
    assert list(score.eligible(g)["game_id"]) == [2]


def test_missing_seasons_are_dropped_by_the_coverage_rule_and_named():
    """The pre-registration names 2016-2020 as fitting seasons; the warehouse
    starts in 2018, so 2016 and 2017 fail coverage, are dropped and are
    listed - the frozen rule, not an edit."""
    o = score.score(_frame(informative=False, per_season=200), None)
    assert o.fit_seasons == [2018, 2019, 2020]
    assert o.holdout_seasons == list(cv.HOLDOUT_SEASONS)
    dropped = set(o.coverage.loc[~o.coverage["enters"], "season"])
    assert dropped == {2016, 2017}
    assert "Dropped by the coverage rule: 2016, 2017" in score.render(o)


def test_an_informative_consensus_passes_q1_and_a_useless_one_does_not():
    good = score.score(_frame(informative=True), None)
    assert good.beta > 0 and good.q1_pass, good.beta_ci
    useless = score.score(_frame(informative=False), None)
    assert not useless.q1_pass, useless.beta_ci
    assert useless.decision.startswith("Q1 fails")


def test_the_selection_is_the_fixed_fraction_each_season():
    games = score.eligible(_frame(informative=False, per_season=333))
    gap = pd.Series(np.random.default_rng(1).normal(0, 3, len(games)), index=games.index)
    picked = score.select(games, gap)
    assert picked.groupby("season").size().eq(int(333 * cv.SELECT_FRACTION + 0.5)).all()
    # Deterministic: the same input picks the same games.
    assert picked["game_id"].tolist() == score.select(games, gap)["game_id"].tolist()


def test_q2_splits_atlas_selections_by_agreement():
    frame = _frame(informative=True)
    games = score.eligible(frame)
    rng = np.random.default_rng(3)
    atlas = pd.Series((games["line"] + rng.normal(0, 3, len(games))).to_numpy(), index=games["game_id"].to_numpy())
    o = score.score(frame, atlas)
    assert o.q2_agree is not None
    k = int(500 * cv.SELECT_FRACTION + 0.5) * len(cv.HOLDOUT_SEASONS)
    assert o.q2_agree["n"] + o.q2_disagree_n + o.q2_unsplit <= k
    text = score.render(o)
    assert "Where it disagrees" in text and "Both required" in text


def test_the_report_bolds_each_verdict_once():
    """The first scored report printed ****fail****: the verdict was bolded
    by the helper and again by the sentence around it."""
    frame = _frame(informative=False)
    games = score.eligible(frame)
    atlas = pd.Series(games["line"].to_numpy(), index=games["game_id"].to_numpy())
    text = score.render(score.score(frame, atlas))
    assert "***" not in text
    assert "All four required: **fail**" in text and "Both required: **fail**" in text
    assert "| **fail** |" in text


def test_the_holdout_is_scored_once(tmp_path):
    out = tmp_path / "consensus_test.md"
    out.write_text("already scored\n")
    assert score.main(["--out", str(out)]) == 2
    assert out.read_text() == "already scored\n"


@pytest.mark.parametrize("name", ["FIT_SEASONS", "HOLDOUT_SEASONS", "FIRST_WEEK", "MIN_COVERAGE",
                                  "SELECT_FRACTION", "SEED"])
def test_the_scorer_reads_the_frozen_constants_and_defines_none(name):
    assert not hasattr(score, name), f"{name} must come from consensus_validation, not be redefined"
