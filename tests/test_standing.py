"""Standing orders late in games (atlas/polymarket/standing.py): the late window, the trigger, the fills,
the fees, and the pre-registered test."""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import pandas as pd

from atlas.polymarket import standing

START = pd.Timestamp("2026-01-10T00:00:00Z")


def _game(result_long=1.0, league="nba", eid="1", finished=START + timedelta(minutes=150)):
    return {"league": league, "event_id": eid, "label": "Chicago @ Milwaukee", "start": START, "finished": finished,
            "fee_rate": 0.0695, "long_side": "away", "result_long": result_long, "market_slug": f"m{eid}"}


def _tape(path: dict[int, float], spread: float = 0.01, minutes: int = 150) -> pd.DataFrame:
    """The long side's ask by minute after the start (held between the minutes given), the short side's one
    less it plus ``spread``; 0.60 before the first given minute."""
    rows, ask = [], 0.60
    for m in range(-10, minutes):
        ask = path.get(m, ask)
        rows.append({"at": START + timedelta(minutes=m), "long": ask, "short": round(1.0 + spread - ask, 3)})
    return pd.DataFrame(rows)


def test_late_is_the_leagues_median_length_less_fifteen_minutes():
    games = pd.DataFrame({"league": ["nba", "nba", "nba", "nhl"], "start": [START] * 4,
                          "finished": [START + timedelta(minutes=m) for m in (140, 150, 170, 160)]})
    assert standing.late_starts(games) == {"nba": 135.0, "nhl": 145.0}
    assert standing.late_starts(pd.DataFrame(columns=["league", "start", "finished"])) == {}


def test_a_standing_order_is_posted_at_the_late_trigger_and_fills_when_the_ask_falls_below_it():
    # Over 85 at minute 50 (not late: ignored), back to 0.70, then 0.86 at 110 (late), 0.84 at 112, 0.82 at 114.
    tape = _tape({50: 0.90, 51: 0.70, 110: 0.86, 112: 0.84, 114: 0.82, 120: 0.95})
    rows = pd.DataFrame(standing.orders(_game(), tape, 100.0, thresholds=(0.85,), dips=(0.01, 0.03, 0.05),
                                        windows=(3, 5)))
    rows = rows[rows["long"]]
    taker = rows[rows["fill"] == "taker"].iloc[0]
    assert taker["trigger_ask"] == 0.86 and taker["minutes_in"] == 110 and taker["price"] == 0.86
    by = rows[rows["fill"] != "taker"].set_index(["dip", "window", "fill"])
    # 1¢ under: 0.85. The ask is 0.84 at minute 112, below it: filled within 3 minutes either way.
    assert by.loc[(0.01, 3, "through"), "filled"] and by.loc[(0.01, 3, "through"), "price"] == 0.85
    assert by.loc[(0.01, 3, "through"), "filled_at"] == START + timedelta(minutes=112)
    # 3¢ under: 0.83. 0.82 arrives at minute 114: four minutes on, inside 5 but not 3.
    assert not by.loc[(0.03, 3, "through"), "filled"] and by.loc[(0.03, 5, "through"), "filled"]
    # 5¢ under: 0.81. The ask never goes below 0.82: no fill. A touch at 0.84 fills 2¢ under (0.84) only.
    assert not by.loc[(0.05, 5, "through"), "filled"] and not by.loc[(0.05, 5, "touch"), "filled"]
    assert set(rows["won"]) == {1.0}
    # The short side never reached 85 late.
    assert rows["long"].all()


def test_through_and_touch_differ_at_the_price_and_a_wide_book_or_an_ended_game_takes_nothing():
    touch = _tape({110: 0.86, 112: 0.83})
    rows = pd.DataFrame(standing.orders(_game(), touch, 100.0, thresholds=(0.85,), dips=(0.03,), windows=(5,)))
    by = rows[rows["long"] & (rows["fill"] != "taker")].set_index("fill")
    assert by.loc["touch", "filled"] and not by.loc["through", "filled"]          # exactly at the price
    wide = _tape({110: 0.86, 112: 0.80}, spread=0.06)
    assert standing.orders(_game(), wide, 100.0, thresholds=(0.85,)) == []
    # The game ends at minute 113: a dip after it is no fill.
    late_dip = _tape({110: 0.86, 115: 0.80})
    rows = pd.DataFrame(standing.orders(_game(finished=START + timedelta(minutes=113)), late_dip, 100.0,
                                        thresholds=(0.85,), dips=(0.03,), windows=(10,)))
    assert not rows[rows["fill"] == "through"]["filled"].any()
    assert standing.orders(_game(result_long=float("nan")), touch, 100.0) == []
    assert standing.orders(_game(), touch, float("nan")) == []


def test_the_fee_models_cost_a_filled_order_and_the_taker_always_pays():
    rows = pd.DataFrame(standing.orders(_game(result_long=0.0), _tape({110: 0.86, 112: 0.80}), 100.0,
                                        thresholds=(0.85,), dips=(0.03,), windows=(5,)))
    taker, none = standing.costed(rows, "taker"), standing.costed(rows, "none")
    t = taker[(taker["fill"] == "through") & taker["long"]].iloc[0]
    n = none[(none["fill"] == "through") & none["long"]].iloc[0]
    assert math.isclose(t["cost"], 0.83 + 0.0695 * 0.83 * 0.17) and n["cost"] == 0.83 and n["profit"] == -0.83
    assert none[none["fill"] == "taker"]["cost"].iloc[0] > 0.86                   # the taker pays its fee regardless


def _orders(n_games: int, won_every: int = 1, start=START) -> pd.DataFrame:
    rows = []
    for i in range(n_games):
        won = 0.0 if won_every > 1 and i % won_every == 0 else 1.0
        rows.append({**standing.PRIMARY, "event_id": str(i), "league": "nba", "filled": True, "won": won,
                     "payout": won, "cost": 0.85, "price": 0.83, "profit": won - 0.85,
                     "trigger_at": start + timedelta(days=i % 60)})
    return pd.DataFrame(rows)


def test_the_pre_registered_test_holds_only_when_all_three_criteria_do():
    passing = standing.primary(_orders(300, won_every=20))                    # 95% wins against 85¢ costs
    assert passing["passed"] and all(passing["checks"].values()) and len(passing["halves"]) == 2
    few = standing.primary(_orders(150, won_every=20))
    assert not few["passed"] and not few["checks"]["at least 200 fills"]
    losing = standing.primary(_orders(300, won_every=5))                      # 80% wins against 85¢
    assert not losing["passed"] and not losing["checks"]["edge less 1.96 errors above zero"]
    # Good in the first half only.
    o = _orders(300, won_every=20)
    o.loc[o["trigger_at"] > START + timedelta(days=30), ["won", "payout"]] = 0.0
    assert not standing.primary(o)["checks"]["edge above zero in both halves"]


def test_the_report_says_what_it_holds(tmp_path):
    rows = pd.DataFrame(standing.orders(_game(), _tape({110: 0.86, 112: 0.80}), 100.0))
    o = pd.concat([standing.costed(rows, f) for f in standing.FEES], ignore_index=True)
    o = o[~((o["fill"] == "taker") & (o["fee"] == "none"))]
    games = pd.DataFrame([_game()])
    text, tables = standing.report(games, o, {"nba": 100.0}, now=datetime(2026, 10, 24, tzinfo=UTC))
    assert "## The pre-registered test" in text and "**Not established.**" in text
    assert "| NBA | 100 |" in text and {"grid", "taker_at_trigger", "primary_by_league"} <= set(tables)
    assert len(tables["grid"]) == 3 * 3 * 2 * 2      # every cell at 85 (the game never reaches 90), both fee models
    out = standing.write(games, o, {"nba": 100.0}, reports=tmp_path, raw=tmp_path / "raw")
    assert out.exists() and (tmp_path / "tables" / "standing_order_grid.csv").exists()
    assert (tmp_path / "raw" / "standing_order_backtest.csv").exists()
    assert "No orders" in standing.report(games, o.iloc[0:0], {"nba": 100.0})[0]
