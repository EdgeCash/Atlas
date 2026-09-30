"""Step 9's scoring (docs/NHL_PLAYS_PREREGISTRATION.md): the sides, the prices, the pushes, the thresholds chosen
on earlier seasons only, and the five criteria. Synthetic."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from atlas.live.probability import no_vig
from atlas.research import nhl_plays as plays


def _game(**kw):
    tcdf = np.cumsum(np.full(13, 1 / 13))                            # totals 0..12 equally likely
    base = {"game_id": 1, "season": 2020, "home_score": 4, "away_score": 2, "p_home": 0.60, "p_home_minus_1_5": 0.35,
            "p_away_minus_1_5": 0.15, "_tcdf": tcdf, "home_ml_close": -120.0, "away_ml_close": 100.0,
            "total_close": 6.0, "over_close": -105.0, "under_close": -115.0, "home_pl": -1.5, "home_pl_price": 180.0,
            "away_pl_price": -220.0}
    return {**base, **kw}


def test_the_prices_pay_and_shade_as_a_book_ladders_them():
    assert plays.payout(150) == 1.5 and plays.payout(-125) == pytest.approx(0.8)
    assert plays.shade(-150) == -155 and plays.shade(130) == 125 and plays.shade(102) == -103
    assert plays.units(-110, "push") == 0.0 and plays.units(-110, "loss") == -1.0


def test_each_game_gives_atlas_side_in_each_market_and_settles_it():
    c = plays.candidates(pd.DataFrame([_game()])).set_index("rule")
    pm = no_vig(-120, 100)
    assert c.loc["M", "side"] == "home" and c.loc["M", "outcome"] == "win"
    assert c.loc["M", "disagreement"] == pytest.approx(100 * (0.60 - pm))
    # Total 6: over is 6/13, a push 1/13; over given no push 6/12 = 0.5 against the market's 0.489: the over, pushed.
    assert c.loc["T", "side"] == "over" and c.loc["T", "outcome"] == "push" and c.loc["T", "units"] == 0.0
    # Puck line: home -1.5 at 0.35 against the market's no-vig; home won by two, so it covered.
    assert c.loc["P", "side"] == ("home" if 0.35 >= no_vig(180, -220) else "away")
    assert c.loc["P", "outcome"] == ("win" if c.loc["P", "side"] == "home" else "loss")


def test_a_home_plus_one_and_a_half_reads_the_away_side_by_two():
    c = plays.candidates(pd.DataFrame([_game(home_pl=1.5, home_pl_price=-250.0, away_pl_price=200.0,
                                             home_score=1, away_score=3)])).set_index("rule")
    p_home_covers = 1 - 0.15
    assert c.loc["P", "side"] == ("home" if p_home_covers >= no_vig(-250, 200) else "away")
    assert c.loc["P", "outcome"] == ("loss" if c.loc["P", "side"] == "home" else "win")   # lost by two


def _cands(n_per_season=400, edge=0.0, seed=1):
    rng = np.random.default_rng(seed)
    rows = []
    for season in range(2013, 2023):
        d = rng.uniform(0, 12, n_per_season)
        pm = np.full(n_per_season, 0.5)
        won = rng.random(n_per_season) < pm + edge * d / 100
        rows.append(pd.DataFrame({"game_id": range(n_per_season), "season": season, "rule": "M", "side": "home",
                                  "p_atlas": pm + d / 100, "p_market": pm, "disagreement": d, "price": 100.0,
                                  "outcome": np.where(won, "win", "loss")}))
    c = pd.concat(rows, ignore_index=True)
    c["units"] = [plays.units(p, o) for p, o in zip(c["price"], c["outcome"], strict=True)]
    c["units_shaded"] = [plays.units(plays.shade(p), o) for p, o in zip(c["price"], c["outcome"], strict=True)]
    return c


def test_the_threshold_is_chosen_on_earlier_seasons_with_enough_bets_ties_low():
    c = _cands()
    train = c[c["season"] == 2013].assign(units=1.0)                   # every bet a win: more bets, more units
    assert plays.choose(train) == 2.0
    assert plays.choose(train.head(100)) is None                       # under 300 at every threshold
    bets, chosen = plays.walk(c)
    assert set(bets["season"]) == set(plays.DESCRIPTIVE) | set(plays.DECIDING)
    first = chosen[(chosen["rule"] == "M") & (chosen["season"] == 2014)]["threshold"].iloc[0]
    assert first == plays.choose(c[c["season"] == 2013])               # 2014-15 chosen on 2013-14 alone


def test_a_real_edge_clears_every_criterion_and_none_does_not():
    real = plays.verdict(plays.walk(_cands(edge=1.5))[0]).set_index("rule").loc["M"]
    assert real["real"] and real["c2_beats_market"] and real["bets"] >= plays.MIN_BETS
    none = plays.verdict(plays.walk(_cands(edge=0.0, seed=7))[0]).set_index("rule").loc["M"]
    assert not none["real"]


def test_the_registration_is_what_the_code_runs():
    assert plays.GRID == (2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0) and plays.MIN_TRAIN == 300
    assert plays.DECIDING == (2020, 2021, 2022) and plays.DESCRIPTIVE == tuple(range(2014, 2020))
    assert plays.ALPHA == pytest.approx(0.05 / 3) and plays.RESAMPLES == 10_000 and plays.SEED == 2026
    assert plays.MIN_BETS == 150 and plays.SHADE == 5.0 and plays.FIRST == 2013
