"""CLV in probability: what the closing market thought of the entry.

``clv_points`` counts half-points. It is blind to two things that decide what
a move is worth: the price (53.5 at -110 to 53.5 at -130 is a real move and
reads as a push), and where the line sits (a spread through 3 or 7 moves far
more probability than one through 10.5).

This module reads both. Each side's price is turned into the market's own
vig-free probability. The closing market's distribution for the game is then
recovered - centred so that it gives the closing line exactly the closing
price's probability - and asked how likely the signal's side was to win *at
the entry line*. The entry market is read the same way at the entry line.
The difference is the signal's closing-line value in probability:

    clv_prob = close_prob - entry_prob

Everything here is a property of lines and prices, never of money. Pushes
are left out of every probability (a push is neither side winning), which is
how a two-way price is quoted.

The distribution's shape - the standard deviation and, for the margin, the
key-number lattice - comes from ``tracking/market_shape.csv``, which the
weekly refresh writes from the fitted models. Without it, a plain
discretised normal at the closing-line error measured in the research stands
in for it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats

#: Integer outcomes the distribution covers, for either market.
SUPPORT = np.arange(-120, 181)

#: The closing line's error as a normal sd, when no fitted shape is stored.
#: College: the README's closing-line MAEs (12.22 margin, 12.71 total) times
#: sqrt(pi / 2). NFL: the same reading of the nflverse closing lines.
DEFAULT_SIGMA = {
    ("ncaaf", "margin"): 15.3, ("ncaaf", "total"): 15.9,
    ("nfl", "margin"): 13.4, ("nfl", "total"): 13.2,
}

#: Where the root-find looks for the closing market's centre, around the line.
SEARCH = 40.0

#: The book's margin on a standard -110 / -110 market: both sides' implied
#: probabilities sum to this. A side quoted without its opposite is read
#: against it, and the probability is marked as assumed.
STANDARD_BOOK = 2 * 110 / 210


@dataclass(frozen=True)
class Shape:
    """One sport and market's outcome distribution, before it is centred."""

    sigma: float
    factor: np.ndarray            # one multiplier per SUPPORT value

    def pmf(self, centre: float) -> np.ndarray:
        hi = stats.norm.cdf((SUPPORT + 0.5 - centre) / self.sigma)
        lo = stats.norm.cdf((SUPPORT - 0.5 - centre) / self.sigma)
        p = (hi - lo) * self.factor
        return p / p.sum()


def implied(price: float) -> float:
    """The probability an American price implies, margin included."""
    if price is None or not math.isfinite(price) or price == 0:
        return float("nan")
    return 100.0 / (price + 100.0) if price > 0 else -price / (-price + 100.0)


def no_vig(price: float, other: float) -> float:
    """The first side's probability with the book's margin taken out."""
    a, b = implied(price), implied(other)
    if not (math.isfinite(a) and math.isfinite(b)) or a + b <= 0:
        return float("nan")
    return a / (a + b)


def quoted_first(price: float, other: float) -> tuple[float, bool]:
    """(first side's vig-free probability, whether any of it was assumed).

    Both prices: the book's own margin comes out. The first side's price
    alone: read against the standard margin. Neither: the standard market,
    0.5 each side.
    """
    both = no_vig(price, other)
    if math.isfinite(both):
        return both, False
    one = implied(price)
    if math.isfinite(one):
        return min(max(one / STANDARD_BOOK, 0.0), 1.0), True
    return 0.5, True


def first_side(pmf: np.ndarray, line: float) -> float:
    """P(outcome above ``line`` | not a push): the home side's or the over's."""
    above = pmf[SUPPORT > line].sum()
    below = pmf[SUPPORT < line].sum()
    return float(above / (above + below)) if above + below > 0 else float("nan")


def centre_for(shape: Shape, line: float, prob: float) -> float:
    """The centre at which ``line``'s first side wins with probability ``prob``."""
    lo, hi = line - SEARCH, line + SEARCH
    for _ in range(60):
        mid = (lo + hi) / 2.0
        if first_side(shape.pmf(mid), line) < prob:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def side_prob(first: float, direction: str) -> float:
    return first if direction in ("home", "over") else 1.0 - first


def at_line(shape: Shape, quoted_line: float, quoted_first: float, line: float) -> float:
    """The first side's probability at ``line``, under the market that quoted
    ``quoted_line`` at a first-side probability of ``quoted_first``."""
    if quoted_line == line:
        return quoted_first
    return first_side(shape.pmf(centre_for(shape, quoted_line, quoted_first)), line)


# ---------------------------------------------------------------------------
# Shapes: fitted, stored by the weekly refresh, read by the hourly poll
# ---------------------------------------------------------------------------


def default_shape(sport: str, market: str) -> Shape:
    sigma = DEFAULT_SIGMA.get((sport, market), DEFAULT_SIGMA[("ncaaf", market)])
    return Shape(sigma, np.ones(len(SUPPORT)))


def shapes_frame(sport: str, lattice, total_sigma: float) -> pd.DataFrame:
    """The rows ``tracking/market_shape.csv`` keeps for one sport.

    ``lattice`` is the fitted :class:`atlas.models.lattice.Lattice` (the
    margin's key numbers and the market sd it was fitted at); the total is a
    plain normal at the total model's calibrated sd.
    """
    margin = pd.DataFrame({"sport": sport, "market": "margin", "sigma": float(lattice.sigma),
                           "point": np.asarray(lattice.support, dtype=int),
                           "factor": np.asarray(lattice.factor, dtype=float)})
    total = pd.DataFrame({"sport": [sport], "market": ["total"], "sigma": [float(total_sigma)],
                          "point": [pd.NA], "factor": [pd.NA]})
    return pd.concat([margin, total], ignore_index=True)


def load_shapes(frame: pd.DataFrame | None) -> dict[tuple[str, str], Shape]:
    """Every stored shape, keyed by (sport, market)."""
    out: dict[tuple[str, str], Shape] = {}
    if frame is None or frame.empty:
        return out
    for (sport, market), rows in frame.groupby(["sport", "market"]):
        sigma = float(pd.to_numeric(rows["sigma"], errors="coerce").dropna().iloc[0])
        factor = np.ones(len(SUPPORT))
        known = rows.dropna(subset=["point", "factor"])
        if len(known):
            where = dict(zip(pd.to_numeric(known["point"]).astype(int), pd.to_numeric(known["factor"]),
                             strict=True))
            factor = np.array([where.get(int(k), 1.0) for k in SUPPORT], dtype=float)
        if math.isfinite(sigma) and sigma > 0:
            out[(str(sport), str(market))] = Shape(sigma, factor)
    return out


# ---------------------------------------------------------------------------
# The grades' three columns
# ---------------------------------------------------------------------------


def _latest_before(snapshots: pd.DataFrame, cutoff: pd.Series, lines: pd.Series | None = None) -> pd.DataFrame:
    """Per signal, the last whole snapshot captured at or before its cutoff.

    With ``lines``, a signal with no snapshot before its cutoff falls back to
    the first snapshot quoting its own line: the poll that forms a signal
    records the quote it was formed against, and a history rebuilt from
    hourly commits can date that quote a few minutes after the signal.
    """
    s = snapshots.copy()
    s["captured_ts"] = pd.to_datetime(s["captured_at"], utc=True, errors="coerce")
    s = s.dropna(subset=["captured_ts", "line"]).sort_values("captured_ts", kind="stable")
    rows = []
    for i, (game, book, market, when) in cutoff.items():
        stream = s[(s["game_id"].astype(str) == str(game)) & (s["book"] == book) & (s["market"] == market)]
        block = stream[stream["captured_ts"] <= when]
        if len(block):
            rows.append(block.iloc[-1].rename(i))
        elif lines is not None:
            same = stream[pd.to_numeric(stream["line"], errors="coerce") == float(lines[i])]
            if len(same):
                rows.append(same.iloc[0].rename(i))
    return pd.DataFrame(rows)


def _num(value) -> float:
    v = pd.to_numeric(value, errors="coerce")
    return float(v) if pd.notna(v) else float("nan")


def clv_prob(signals: pd.DataFrame, snapshots: pd.DataFrame, games: pd.DataFrame,
             shapes: dict[tuple[str, str], Shape] | None = None,
             sports: dict[str, str] | None = None) -> pd.DataFrame:
    """``entry_prob``, ``close_prob`` and ``clv_prob`` per signal.

    The entry market is the last snapshot captured at or before the signal
    was formed, which is the quote the signal was formed against; the close
    is the last one at or before kickoff. A missing price at either end is
    read against the standard -110 / -110 market (:func:`quoted_first`) and
    ``prob_assumed`` says so. A signal with no close has no probability.
    """
    columns = ["signal_id", "entry_prob", "close_prob", "clv_prob", "prob_assumed"]
    if signals.empty or snapshots.empty:
        return pd.DataFrame(columns=columns)
    shapes = shapes or {}
    sports = sports or {}
    kickoff = pd.to_datetime(games.set_index(games["game_id"].astype(str))["kickoff"], utc=True, errors="coerce")
    sig = signals.reset_index(drop=True)
    created = pd.to_datetime(sig["created_at"], utc=True, errors="coerce")
    kicks = sig["game_id"].astype(str).map(kickoff)
    entry = _latest_before(snapshots, pd.Series(list(zip(sig["game_id"], sig["book"], sig["market"], created,
                                                         strict=True)), index=sig.index),
                           lines=pd.to_numeric(sig["entry_line"], errors="coerce"))
    close = _latest_before(snapshots, pd.Series(list(zip(sig["game_id"], sig["book"], sig["market"], kicks,
                                                         strict=True)), index=sig.index))
    rows = []
    for i, s in sig.iterrows():
        sport = sports.get(str(s["game_id"]), "ncaaf")
        shape = shapes.get((sport, s["market"])) or default_shape(sport, s["market"])
        line_in = float(s["entry_line"])
        if i not in close.index:
            rows.append({"signal_id": s["signal_id"], "entry_prob": np.nan, "close_prob": np.nan,
                         "clv_prob": np.nan, "prob_assumed": pd.NA})
            continue
        entry_first, assumed = 0.5, True
        if i in entry.index:
            e = entry.loc[i]
            quoted, assumed = quoted_first(_num(e.get("price")), _num(e.get("other_price")))
            entry_first = at_line(shape, float(e["line"]), quoted, line_in)
        c = close.loc[i]
        quoted, close_assumed = quoted_first(_num(c.get("price")), _num(c.get("other_price")))
        close_first = at_line(shape, float(c["line"]), quoted, line_in)
        e_side = side_prob(entry_first, s["direction"])
        c_side = side_prob(close_first, s["direction"])
        rows.append({"signal_id": s["signal_id"], "entry_prob": e_side, "close_prob": c_side,
                     "clv_prob": c_side - e_side, "prob_assumed": bool(assumed or close_assumed)})
    return pd.DataFrame(rows, columns=columns)
