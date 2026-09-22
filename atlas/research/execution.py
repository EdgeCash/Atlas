"""Phase 4: can the Phase 3 line-movement signal be executed?

Phase 3 established that Atlas predicts the direction of the open-to-close
move (54.4% on margins, 58.3% on totals) while picking winners at chance.
This module asks the only question that follows: is that a tradeable object or
a measurement artefact?

The single most important thing here is :func:`within_book_clv`. Phase 3
compared **one book's opening number** against a **consensus close across
roughly six books**, because that is what the staged warehouse holds. Those are
two different prices at two different shops, and the difference between them is
not something a bettor can collect. A bettor opens an account at one book,
takes their number, and is graded against that same book's close. This module
rebuilds the line table per book so that comparison can be made.

Nothing here stakes, simulates or recommends a wager.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from atlas import config
from atlas.research import market_aware as ma
from atlas.research import signal_validation as sv
from atlas.sources import sportsdataverse as sdv
from atlas.staging import market as staging_market
from atlas.util import get_logger

LOG = get_logger(__name__)

#: Points of closing-line value the brief asks to be priced.
CLV_LADDER = (0.25, 0.50, 0.75, 1.00, 1.50, 2.00)

#: Prices to evaluate each rung against. Break-even rates come from
#: :data:`atlas.research.signal_validation.JUICE`.
PRICE_LADDER = (-105, -110, -115, -120)

#: A line move larger than this is a data error, not a market event: a 300-point
#: spread move is a mis-parsed row, and one of them moves a mean.
MAX_SANE_MOVE = 21.0

#: Signal concentration cuts for Track 7.
CONCENTRATION = (100, 25, 10, 5, 1)


# ---------------------------------------------------------------------------
# Per-book line table
# ---------------------------------------------------------------------------


def book_lines(seasons: tuple[int, ...] | list[int] | None = None) -> pd.DataFrame:
    """Open and close **at the same book**, one row per game/book/market.

    The staged ``market_lines`` table reduces every game to a consensus, which
    is the right choice for measuring what the market thought and the wrong
    one for measuring what a bettor could have done. This rebuilds the
    per-book detail from the same raw feed, reusing the staging layer's
    abbreviation resolver so the home/away orientation is identical.
    """
    paths = config.paths()
    odds = pd.read_parquet(sdv.odds_path(paths.raw))
    if seasons is not None:
        odds = odds[odds["season"].isin(list(seasons))]
    odds = odds.dropna(subset=["game_id"]).copy()
    odds["game_id"] = odds["game_id"].astype("int64")
    odds["home_team_id"] = odds["home_team_id"].astype("Int64")
    odds["away_team_id"] = odds["away_team_id"].astype("Int64")

    mapping = staging_market.resolve_abbreviations(odds)
    mapped = odds["abbr"].map(mapping).astype("Int64")
    odds["side"] = np.where(
        (mapped == odds["home_team_id"]).fillna(False), "home",
        np.where((mapped == odds["away_team_id"]).fillna(False), "away", None),
    )

    frames = []
    for market, rows in (
        ("margin", odds[(odds["market_type"] == "spread") & (odds["side"] == "home")]),
        ("total", odds[(odds["market_type"] == "total") & (odds["abbr"] == "over")]),
    ):
        block = rows.dropna(subset=["opening_lines", "lines", "book"]).copy()
        # Spreads are quoted home-negative; Atlas works in home-margin terms.
        sign = -1.0 if market == "margin" else 1.0
        block["market"] = market
        block["open_line"] = sign * block["opening_lines"].astype(float)
        block["close_line"] = sign * block["lines"].astype(float)
        block["open_price"] = block["opening_odds"]
        block["close_price"] = block["odds"]
        block["move"] = block["close_line"] - block["open_line"]
        block = block[block["move"].abs() <= MAX_SANE_MOVE]
        frames.append(
            block[["game_id", "season", "week", "book", "market", "open_line",
                   "close_line", "move", "open_price", "close_price"]]
        )
    out = pd.concat(frames, ignore_index=True)
    out = out.drop_duplicates(["game_id", "book", "market"])
    LOG.info(
        "per-book lines: %d rows, %d games, %d books",
        len(out), out["game_id"].nunique(), out["book"].nunique(),
    )
    return out


def opener_coverage(lines: pd.DataFrame, games: pd.DataFrame | None = None) -> pd.DataFrame:
    """Track 1: who posts an opening number, and how often.

    ``games`` is the research sample, used only to express coverage as a share
    of the slate Atlas would actually have an opinion on.
    """
    slate = (
        games.groupby("season")["game_id"].nunique().to_dict()
        if games is not None and "season" in games
        else {}
    )
    rows = []
    for (market, season), block in lines.groupby(["market", "season"], observed=True):
        per_game = block.groupby("game_id")
        in_season = slate.get(int(season), np.nan)
        rows.append(
            {
                "market": market,
                "season": int(season),
                "games_in_sample": in_season,
                "games_with_opener": int(block["game_id"].nunique()),
                "coverage": block["game_id"].nunique() / in_season if in_season else np.nan,
                "books_posting_openers": int(block["book"].nunique()),
                "mean_books_per_game": float(per_game["book"].nunique().mean()),
                "single_book_share": float((per_game["book"].nunique() == 1).mean()),
                "median_abs_move": float(block["move"].abs().median()),
                "no_move_share": float((block["move"] == 0).mean()),
                "open_price_known": float(block["open_price"].notna().mean()),
            }
        )
    return pd.DataFrame(rows).sort_values(["market", "season"])


def opener_dispersion(lines: pd.DataFrame) -> pd.DataFrame:
    """Track 1: when several books open a game, do they open on the same number?"""
    rows = []
    for market, block in lines.groupby("market", observed=True):
        per_game = block.groupby("game_id")["open_line"]
        counts = per_game.count()
        multi = counts[counts > 1].index
        spread = (per_game.max() - per_game.min()).loc[multi]
        rows.append(
            {
                "market": market,
                "games_multi_book": int(len(multi)),
                "identical_share": float((spread == 0).mean()),
                "median_spread": float(spread.median()),
                "mean_spread": float(spread.mean()),
                "p90_spread": float(spread.quantile(0.90)),
                "max_spread": float(spread.max()),
            }
        )
    return pd.DataFrame(rows)


def book_roles(lines: pd.DataFrame, consensus: pd.DataFrame) -> pd.DataFrame:
    """Track 3: which books open, which only close, and how many games each covers."""
    rows = []
    for market, block in lines.groupby("market", observed=True):
        total_games = int(consensus["game_id"].nunique())
        for book, sub in block.groupby("book", observed=True):
            rows.append(
                {
                    "market": market,
                    "book": str(book),
                    "games_opened": int(sub["game_id"].nunique()),
                    "coverage": sub["game_id"].nunique() / total_games if total_games else np.nan,
                    "seasons": ", ".join(str(int(s)) for s in sorted(sub["season"].unique())),
                    "median_abs_move": float(sub["move"].abs().median()),
                    "open_price_known": float(sub["open_price"].notna().mean()),
                }
            )
    out = pd.DataFrame(rows)
    return out.sort_values(["market", "games_opened"], ascending=[True, False])


# ---------------------------------------------------------------------------
# The decisive test: CLV measured inside one book
# ---------------------------------------------------------------------------


def attach_predictions(lines: pd.DataFrame, scored: pd.DataFrame,
                       market: ma.Market) -> pd.DataFrame:
    """Join Atlas's out-of-sample prediction onto every game/book row."""
    block = lines[lines["market"] == market.name].copy()
    keep = ["game_id", "prediction", market.line, market.opening, market.target,
            "spread_books", "total_books", "closing_spread_abs", "talent_sum",
            "conference_game"]
    have = [c for c in dict.fromkeys(keep) if c in scored.columns]
    merged = block.merge(scored[have], on="game_id", how="inner")

    merged["side"] = np.sign(merged["prediction"] - merged["open_line"])
    merged["edge_at_open"] = (merged["prediction"] - merged["open_line"]).abs()
    merged["clv_points"] = merged["move"] * merged["side"]
    merged["clv_push"] = merged["clv_points"] == 0
    merged["clv_positive"] = np.where(
        merged["clv_push"], np.nan, merged["clv_points"] > 0
    )
    # The same side, graded the Phase 3 way: against the consensus close.
    consensus_close = pd.to_numeric(merged[market.line], errors="coerce")
    merged["clv_vs_consensus"] = (consensus_close - merged["open_line"]) * merged["side"]
    merged["clv_vs_consensus_positive"] = np.where(
        merged["clv_vs_consensus"] == 0, np.nan, merged["clv_vs_consensus"] > 0
    )
    return merged[merged["side"] != 0]


def _rate(series: pd.Series) -> dict:
    graded = series.dropna()
    n = len(graded)
    if n == 0:
        return {"graded": 0, "beat_rate": np.nan, "z": np.nan}
    rate = float(graded.mean())
    return {
        "graded": n,
        "beat_rate": rate,
        "z": float((rate - 0.5) / np.sqrt(0.25 / n)),
    }


def within_book_clv(frame: pd.DataFrame, *, group: str | None = "book") -> pd.DataFrame:
    """Beat rate and mean CLV **inside one book**, against the consensus read.

    ``beat_rate`` is the executable number: open and close at the same shop.
    ``consensus_beat_rate`` reproduces Phase 3's construction on the same rows,
    so the gap between the two columns *is* the book effect.
    """
    def _block(block: pd.DataFrame, label: str) -> dict:
        n = len(block)
        mean = float(block["clv_points"].mean())
        se = float(block["clv_points"].std(ddof=1) / np.sqrt(n)) if n > 1 else np.nan
        own = _rate(block["clv_positive"])
        cons = _rate(block["clv_vs_consensus_positive"])
        return {
            "group": label,
            "games": n,
            "pushes": int(block["clv_push"].sum()),
            "graded": own["graded"],
            "mean_clv": mean,
            "clv_se": se,
            "clv_t": mean / se if se and se > 0 else np.nan,
            "median_clv": float(block["clv_points"].median()),
            "beat_rate": own["beat_rate"],
            "beat_z": own["z"],
            "consensus_beat_rate": cons["beat_rate"],
            "consensus_z": cons["z"],
            "book_effect": (
                cons["beat_rate"] - own["beat_rate"]
                if np.isfinite(cons["beat_rate"]) and np.isfinite(own["beat_rate"])
                else np.nan
            ),
        }

    if group is None:
        return pd.DataFrame([_block(frame, "all books")])
    rows = [_block(frame, "all books")]
    for name, block in frame.groupby(group, observed=True):
        if len(block) >= 200:
            rows.append(_block(block, str(name)))
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Track 2 - what a point of CLV is worth
# ---------------------------------------------------------------------------


def clv_value_ladder(residual_sd: dict[str, float]) -> pd.DataFrame:
    """Price each rung of the CLV ladder, for each market and each juice level.

    Converting points to probability uses the local density of the outcome
    distribution at the line: one point is worth ``phi(0) / sd``. This assumes
    the close is a fair 50/50, which is exactly what Phases 1-3 established, so
    it is the right prior to price against rather than an approximation of
    convenience.

    ``ev_per_unit`` is the expected return on one unit risked, at that price,
    if the whole CLV converted into win probability.
    """
    rows = []
    for market, sd in residual_sd.items():
        per_point = float(stats.norm.pdf(0.0) / sd)
        for clv in CLV_LADDER:
            win = 0.5 + per_point * clv
            row = {
                "market": market,
                "clv_points": clv,
                "residual_sd": sd,
                "prob_per_point": per_point,
                "win_probability": win,
            }
            for price in PRICE_LADDER:
                breakeven, payout = sv.JUICE[price]
                row[f"ev_{price}"] = win * payout - (1 - win)
                row[f"clears_{price}"] = bool(win > breakeven)
            rows.append(row)
    return pd.DataFrame(rows)


def breakeven_clv(residual_sd: dict[str, float]) -> pd.DataFrame:
    """How many points of CLV each price demands before a bet is even money."""
    rows = []
    for market, sd in residual_sd.items():
        per_point = float(stats.norm.pdf(0.0) / sd)
        for price in PRICE_LADDER:
            breakeven, _ = sv.JUICE[price]
            rows.append(
                {
                    "market": market,
                    "price": price,
                    "break_even_rate": breakeven,
                    "points_required": (breakeven - 0.5) / per_point,
                }
            )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Track 4 - the CLV portfolio
# ---------------------------------------------------------------------------


def clv_portfolio(frame: pd.DataFrame, *, market: str) -> dict:
    """Distribution, drawdown and volatility of CLV, outcomes ignored entirely.

    The path is walked in chronological order (season, then week) because a
    drawdown is a statement about sequence. Every quantity is in **points of
    line**, not units: turning points into units needs a stake rule, and a
    stake rule is a wagering simulation.
    """
    block = frame.dropna(subset=["clv_points"]).sort_values(["season", "week"])
    if block.empty:
        return {}
    points = block["clv_points"].to_numpy(dtype=float)
    path = np.cumsum(points)
    peak = np.maximum.accumulate(path)
    drawdown = path - peak
    graded = block["clv_positive"].dropna()

    return {
        "market": market,
        "bets": int(len(block)),
        "mean_clv": float(points.mean()),
        "median_clv": float(np.median(points)),
        "sd_clv": float(points.std(ddof=1)),
        "sharpe_per_bet": float(points.mean() / points.std(ddof=1)),
        "p05": float(np.quantile(points, 0.05)),
        "p25": float(np.quantile(points, 0.25)),
        "p75": float(np.quantile(points, 0.75)),
        "p95": float(np.quantile(points, 0.95)),
        "beat_rate": float(graded.mean()) if len(graded) else np.nan,
        "total_clv_points": float(path[-1]),
        "max_drawdown_points": float(drawdown.min()),
        "max_drawdown_bets": int(np.argmin(drawdown) - np.argmax(peak[: np.argmin(drawdown) + 1])
                                 if len(drawdown) else 0),
        "longest_flat_or_down": int(_longest_underwater(drawdown)),
    }


def _longest_underwater(drawdown: np.ndarray) -> int:
    """Longest run of consecutive bets spent below a previous peak."""
    longest = run = 0
    for value in drawdown:
        run = run + 1 if value < 0 else 0
        longest = max(longest, run)
    return longest


def clv_distribution(frame: pd.DataFrame, *, bins: tuple[float, ...] = (
    -1000, -3, -2, -1, -0.5, 0, 0.5, 1, 2, 3, 1000)) -> pd.DataFrame:
    """The shape of the CLV distribution, which a mean hides."""
    block = frame.dropna(subset=["clv_points"])
    cut = pd.cut(block["clv_points"], bins=list(bins), right=False)
    out = cut.value_counts().sort_index().rename("games").to_frame()
    out["share"] = out["games"] / len(block)
    out["bucket"] = [f"[{i.left:g}, {i.right:g})" for i in out.index]
    return out.reset_index(drop=True)[["bucket", "games", "share"]]


def clv_by_season(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for season, block in frame.groupby("season", observed=True):
        stats_row = clv_portfolio(block, market=str(int(season)))
        if stats_row:
            stats_row["season"] = int(season)
            rows.append(stats_row)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Track 6 - regimes
# ---------------------------------------------------------------------------


def _phase(week: pd.Series) -> pd.Series:
    return pd.cut(
        pd.to_numeric(week, errors="coerce"),
        bins=[0, 4, 10, 99],
        labels=["Early (weeks 1-4)", "Mid (weeks 5-10)", "Late (weeks 11+)"],
    )


def regime_table(frame: pd.DataFrame, market: ma.Market) -> pd.DataFrame:
    """Does the CLV signal concentrate in a regime?

    "Profile" is proxied by how many books quote the game - a market-attention
    measure Atlas actually holds. It is not viewership, and a game can be
    heavily quoted and little watched; the proxy is named rather than dressed
    up.
    """
    block = frame.copy()
    books = "spread_books" if market.name == "margin" else "total_books"
    cuts: dict[str, pd.Series] = {}

    phase = _phase(block["week"])
    for label in phase.cat.categories:
        cuts[f"Season phase: {label}"] = phase == label

    if books in block:
        quoting = pd.to_numeric(block[books], errors="coerce")
        high = quoting >= quoting.quantile(0.75)
        low = quoting <= quoting.quantile(0.25)
        cuts["Profile: most-quoted quarter"] = high
        cuts["Profile: least-quoted quarter"] = low

    if "closing_spread_abs" in block:
        margin = pd.to_numeric(block["closing_spread_abs"], errors="coerce")
        cuts["Spread: small (|line| <= 7)"] = margin <= 7
        cuts["Spread: large (|line| > 14)"] = margin > 14

    if "talent_sum" in block:
        talent = pd.to_numeric(block["talent_sum"], errors="coerce")
        cuts["Talent: top quarter"] = talent >= talent.quantile(0.75)
        cuts["Talent: bottom quarter"] = talent <= talent.quantile(0.25)

    rows = [{"regime": "All games", **_regime_row(block)}]
    for label, mask in cuts.items():
        sub = block[mask.fillna(False)]
        if len(sub) >= 200:
            rows.append({"regime": label, **_regime_row(sub)})
    return pd.DataFrame(rows)


def _regime_row(block: pd.DataFrame) -> dict:
    rate = _rate(block["clv_positive"])
    return {
        "games": int(len(block)),
        "graded": rate["graded"],
        "beat_rate": rate["beat_rate"],
        "z": rate["z"],
        "mean_clv": float(block["clv_points"].mean()),
    }


# ---------------------------------------------------------------------------
# Track 7 - signal concentration
# ---------------------------------------------------------------------------


def concentration_curve(frame: pd.DataFrame) -> pd.DataFrame:
    """Keep only the loudest N% of signals each season, and re-measure.

    Ranking is **within season** so a model whose disagreements drift over time
    cannot have its "top 1%" land entirely in one year and call that selection.
    """
    block = frame.dropna(subset=["edge_at_open"]).copy()
    block["pct"] = block.groupby("season")["edge_at_open"].rank(pct=True) * 100
    rows = []
    for top in CONCENTRATION:
        sub = block[block["pct"] >= 100 - top]
        if len(sub) < 100:
            continue
        rate = _rate(sub["clv_positive"])
        rows.append(
            {
                "top_pct": top,
                "bets": int(len(sub)),
                "min_edge": float(sub["edge_at_open"].min()),
                "mean_edge": float(sub["edge_at_open"].mean()),
                "beat_rate": rate["beat_rate"],
                "z": rate["z"],
                "mean_clv": float(sub["clv_points"].mean()),
                "median_clv": float(sub["clv_points"].median()),
            }
        )
    return pd.DataFrame(rows)


def concentrate(frame: pd.DataFrame, top_pct: float) -> pd.DataFrame:
    """The loudest ``top_pct``% of signals, ranked within season."""
    block = frame.dropna(subset=["edge_at_open"]).copy()
    block["pct"] = block.groupby("season")["edge_at_open"].rank(pct=True) * 100
    return block[block["pct"] >= 100 - top_pct]


def cell_economics(frame: pd.DataFrame, residual_sd: float) -> dict:
    """Price one selection of bets against every rung of the juice ladder."""
    block = frame.dropna(subset=["clv_points"])
    if block.empty:
        return {}
    per_point = float(stats.norm.pdf(0.0) / residual_sd)
    mean_clv = float(block["clv_points"].mean())
    se = float(block["clv_points"].std(ddof=1) / np.sqrt(len(block)))
    win = 0.5 + per_point * mean_clv
    row = {
        "bets": int(len(block)),
        "bets_per_season": len(block) / block["season"].nunique(),
        "mean_clv": mean_clv,
        "clv_se": se,
        "clv_ci_low": mean_clv - 1.96 * se,
        "win_probability": win,
        "win_probability_low": 0.5 + per_point * (mean_clv - 1.96 * se),
    }
    for price in PRICE_LADDER:
        breakeven, payout = sv.JUICE[price]
        row[f"ev_{price}"] = win * payout - (1 - win)
        row[f"clears_{price}"] = bool(win > breakeven)
        row[f"clears_{price}_ci"] = bool(row["win_probability_low"] > breakeven)
    return row


def cell_by_season(frame: pd.DataFrame, residual_sd: float) -> pd.DataFrame:
    """Season-by-season stability of one selection, priced at -110."""
    rows = []
    for season, block in frame.groupby("season", observed=True):
        economics = cell_economics(block, residual_sd)
        if not economics:
            continue
        rate = _rate(block["clv_positive"])
        rows.append(
            {
                "season": int(season),
                "bets": economics["bets"],
                "beat_rate": rate["beat_rate"],
                "mean_clv": economics["mean_clv"],
                "win_probability": economics["win_probability"],
                "clears_-110": economics["clears_-110"],
            }
        )
    return pd.DataFrame(rows)


def cell_books(frame: pd.DataFrame) -> pd.DataFrame:
    """Which books the selected signals are actually available at."""
    block = frame.dropna(subset=["clv_points"])
    rows = []
    for book, sub in block.groupby("book", observed=True):
        rate = _rate(sub["clv_positive"])
        rows.append(
            {
                "book": str(book),
                "bets": int(len(sub)),
                "share": len(sub) / len(block),
                "beat_rate": rate["beat_rate"],
                "mean_clv": float(sub["clv_points"].mean()),
                "seasons": ", ".join(str(int(s)) for s in sorted(sub["season"].unique())),
            }
        )
    return pd.DataFrame(rows).sort_values("bets", ascending=False)
