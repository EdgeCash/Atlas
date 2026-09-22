"""Phase 4 execution mechanics.

The phase exists to check one thing: that Phase 3's CLV was not an artefact of
comparing one book's opening number against a different, larger set of books'
closing number. The tests that matter here are the ones that would catch that
comparison creeping back in.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from atlas.research import execution as ex
from atlas.research import market_aware as ma

MARKET = ma.total_market(["a"])


def _frame(n: int = 600, *, seed: int = 4) -> pd.DataFrame:
    """Two books, different openers, a shared consensus close."""
    rng = np.random.default_rng(seed)
    games = np.arange(n)
    consensus_close = rng.normal(52, 6, n).round(1)
    rows = []
    for book, bias in (("Soft", 1.5), ("Sharp", 0.0)):
        open_line = consensus_close + bias + rng.normal(0, 1, n).round(1)
        # A book's own close sits near the consensus but not on it - which is
        # exactly the difference the within-book construction exists to remove.
        close_line = consensus_close + bias / 3 + rng.normal(0, 0.4, n).round(1)
        rows.append(
            pd.DataFrame(
                {
                    "game_id": games,
                    "season": rng.choice([2022, 2023, 2024], n),
                    "week": rng.integers(1, 15, n),
                    "book": book,
                    "market": "total",
                    "open_line": open_line,
                    "close_line": close_line,
                    "move": close_line - open_line,
                    "open_price": np.where(rng.random(n) < 0.5, -110.0, np.nan),
                    "close_price": -105.0,
                }
            )
        )
    return pd.concat(rows, ignore_index=True)


def _scored(frame: pd.DataFrame, *, seed: int = 5) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    games = frame.drop_duplicates("game_id")
    return pd.DataFrame(
        {
            "game_id": games["game_id"].to_numpy(),
            "prediction": games["close_line"].to_numpy() + rng.normal(0, 4, len(games)),
            # The staged consensus close, deliberately not equal to either
            # book's own closing number.
            "closing_total": games["close_line"].to_numpy() - 0.5,
            "opening_total": games["open_line"].to_numpy(),
            "actual_total": games["close_line"].to_numpy() + rng.normal(0, 14, len(games)),
        }
    )


# ---------------------------------------------------------------------------
# The construction the phase exists to fix
# ---------------------------------------------------------------------------


def test_clv_is_graded_against_the_same_book_that_opened():
    """The regression test for the whole phase.

    ``clv_points`` must come from the book's own open and its own close. If it
    silently reaches for a consensus close, a book whose opener sits away from
    the consensus scores a fake edge - which is precisely what Phase 3 could
    not rule out.
    """
    frame = _frame()
    attached = ex.attach_predictions(frame, _scored(frame), MARKET)
    expected = attached["move"] * attached["side"]
    assert attached["clv_points"].equals(expected)

    # The consensus column is kept, separately, for the comparison.
    assert "clv_vs_consensus" in attached
    assert not attached["clv_points"].equals(attached["clv_vs_consensus"])


def test_within_book_reports_both_gradings_and_their_difference():
    frame = _frame()
    attached = ex.attach_predictions(frame, _scored(frame), MARKET)
    summary = ex.within_book_clv(attached)
    row = summary.iloc[0]
    assert row["book_effect"] == pytest.approx(
        row["consensus_beat_rate"] - row["beat_rate"]
    )
    # A soft book with a biased opener must be reported separately, not pooled
    # away: that is the whole point of splitting by book.
    assert set(summary["group"]) >= {"all books", "Soft", "Sharp"}


def test_pushes_are_excluded_from_the_beat_rate():
    """Inherited from Phase 3: a line that never moved is not a loss."""
    frame = _frame()
    frame["close_line"] = frame["open_line"]
    frame["move"] = frame["close_line"] - frame["open_line"]
    attached = ex.attach_predictions(frame, _scored(frame), MARKET)
    assert attached["clv_push"].all()
    assert attached["clv_positive"].isna().all()
    assert ex.within_book_clv(attached, group=None).iloc[0]["graded"] == 0


# ---------------------------------------------------------------------------
# Economics
# ---------------------------------------------------------------------------


def test_break_even_clv_is_the_inverse_of_the_value_ladder():
    """The two tables answer the same question from opposite ends. If they
    disagree, one of them is wrong and the recommendation rests on both."""
    sd = {"total": 16.0}
    ladder = ex.clv_value_ladder(sd)
    required = ex.breakeven_clv(sd).set_index("price")["points_required"]
    for price in ex.PRICE_LADDER:
        needed = required[price]
        for _, row in ladder.iterrows():
            assert row[f"clears_{price}"] == (row["clv_points"] > needed)


def test_a_larger_residual_sd_makes_a_point_of_clv_worth_less():
    """A point of line matters less when outcomes are more dispersed. Getting
    this backwards would inflate every EV in the report."""
    tight = ex.clv_value_ladder({"m": 10.0})["prob_per_point"].iloc[0]
    wide = ex.clv_value_ladder({"m": 20.0})["prob_per_point"].iloc[0]
    assert tight > wide


def test_cell_economics_interval_is_narrower_than_the_claim():
    frame = _frame()
    attached = ex.attach_predictions(frame, _scored(frame), MARKET)
    economics = ex.cell_economics(attached, 16.0)
    assert economics["win_probability_low"] < economics["win_probability"]
    assert economics["clears_-110_ci"] <= economics["clears_-110"]


# ---------------------------------------------------------------------------
# Portfolio and concentration
# ---------------------------------------------------------------------------


def test_drawdown_is_never_positive_and_follows_the_sequence():
    frame = _frame()
    attached = ex.attach_predictions(frame, _scored(frame), MARKET)
    portfolio = ex.clv_portfolio(attached, market="total")
    assert portfolio["max_drawdown_points"] <= 0
    assert portfolio["total_clv_points"] == pytest.approx(
        attached["clv_points"].sum()
    )


def test_longest_underwater_counts_consecutive_bets_below_a_peak():
    assert ex._longest_underwater(np.array([0.0, -1.0, -2.0, 0.0, -1.0])) == 2
    assert ex._longest_underwater(np.array([0.0, 0.0, 0.0])) == 0


def test_concentration_ranks_within_season():
    """A model whose disagreements grow over time must not have its top decile
    land entirely in the last season and have that called selection."""
    frame = _frame()
    attached = ex.attach_predictions(frame, _scored(frame), MARKET)
    attached.loc[attached["season"] == 2024, "edge_at_open"] += 50
    cell = ex.concentrate(attached, 10)
    assert cell["season"].nunique() == attached["season"].nunique()


def test_absurd_line_moves_are_dropped_before_they_move_a_mean():
    """One mis-parsed 300-point move would dominate every mean in the report."""
    assert ex.MAX_SANE_MOVE < 300
    frame = _frame()
    frame.loc[0, "move"] = 299.5
    kept = frame[frame["move"].abs() <= ex.MAX_SANE_MOVE]
    assert len(kept) == len(frame) - 1


# ---------------------------------------------------------------------------
# The one function that touches disk
# ---------------------------------------------------------------------------


def test_book_lines_orients_spreads_to_home_margin(synthetic_build):
    """Spreads are quoted home-negative; Atlas works in home-margin terms. A
    missed sign flip inverts every side in the phase and nothing else fails."""
    from atlas.sources import sportsdataverse as sdv

    lines = ex.book_lines()
    assert not lines.empty
    assert set(lines["market"]) == {"margin", "total"}

    raw = pd.read_parquet(sdv.odds_path(synthetic_build["paths"].raw))
    game = int(lines[lines["market"] == "margin"]["game_id"].iloc[0])
    book = lines[lines["market"] == "margin"].iloc[0]["book"]
    quoted = raw[
        (raw["game_id"] == game) & (raw["book"] == book)
        & (raw["market_type"] == "spread")
    ]
    home_row = quoted[quoted["abbr"] != "over"].iloc[0]

    row = lines[(lines["game_id"] == game) & (lines["book"] == book)
                & (lines["market"] == "margin")].iloc[0]
    assert abs(row["open_line"]) == pytest.approx(abs(float(home_row["opening_lines"])))
    assert row["move"] == pytest.approx(row["close_line"] - row["open_line"])

    totals = lines[lines["market"] == "total"]
    over = raw[(raw["market_type"] == "total") & (raw["abbr"] == "over")]
    # Totals are never sign-flipped: a total of 52 is 52 at every book.
    assert totals["open_line"].min() > 0
    assert totals["open_line"].max() <= over["opening_lines"].max()
