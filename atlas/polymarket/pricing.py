"""Each contract priced by Atlas, anchored to Polymarket, after the venue's fee.

For every contract (a side of a game market at a line) three probabilities:

* **market**: Polymarket's own, the two outcomes' midpoints normalised to
  sum to one (and, for football, ``p_ladder``: what the market's own ladder
  of lines implies at this line, which a position requires the quote to
  agree with);
* **raw**: Atlas's model read at the contract's line - the margin or total
  distribution (`atlas/live/probability.py`'s shape, the fitted market
  shape with its key numbers) centred on the projection, for a football
  moneyline, spread or total; the NHL grid's probabilities for its three
  markets;
* **fair**: the probability a position is taken on. Football is priced in
  centre space: the market's centre is read off Polymarket's own ladder of
  lines (`market_centre`), and the anchored centre every line is then priced
  from (`anchored_centre`) is, on totals, where the walk-forward record's
  hit rate of Atlas's side at a gap this large puts it (`edge_curve`: what
  the disagreement has actually been worth, never less than the market's
  even chance); on margins, the market pulled toward Atlas by the **share**
  of Atlas's disagreement that has turned out real (`share`): fitted by
  least squares through the market on ``tracking/calibration.csv``, clipped
  to [0, 1], and zero where the record is thin or says Atlas adds nothing -
  the research's finding on football spreads, and the only honest default.
  Each contract's fair probability is then the market's own quote moved
  by what the anchoring moves the ladder at that line, so with a share of
  zero Atlas's probability is Polymarket's and no contract can clear the
  fee. The NHL, whose grid holds a probability per line, is anchored the
  same way in probability space.

Then the cost of buying: the ask plus the taker fee, ``rate x ask x (1 -
ask)`` per contract, the rate read from the market itself. Expected value is
fair / cost - 1 and the Kelly fraction (fair - cost) / (1 - cost).
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
from scipy import stats

from atlas.live import probability
from atlas.util import get_logger

LOG = get_logger(__name__)

#: The calibration record's market for each Polymarket market, by sport.
CALIBRATION_MARKET = {
    ("ncaaf", "moneyline"): "margin", ("ncaaf", "spread"): "margin", ("ncaaf", "total"): "total",
    ("nfl", "moneyline"): "margin", ("nfl", "spread"): "margin", ("nfl", "total"): "total",
    ("nhl", "moneyline"): "moneyline", ("nhl", "spread"): "moneyline", ("nhl", "total"): "moneyline",
}
#: The share of Atlas's disagreement taken as real when the record cannot say.
DEFAULT_SHARE: dict = {}
MIN_RECORD = 500
MIN_CURVE = 200

PRICED_COLUMNS = ["p_market", "p_raw", "p_ladder", "share", "p", "centre_market", "centre_atlas", "centre", "fee",
                  "cost", "ev", "kelly"]


def fee(ask: float, rate: float) -> float:
    """The taker fee per one-dollar contract bought at ``ask``."""
    return rate * ask * (1.0 - ask) if 0.0 < ask < 1.0 and math.isfinite(rate) else float("nan")


# ---------------------------------------------------------------------------
# What the record says Atlas's disagreement is worth
# ---------------------------------------------------------------------------


def _record(calibration: pd.DataFrame | None, sport: str, market: str) -> pd.DataFrame:
    if calibration is None or calibration.empty:
        return pd.DataFrame()
    c = calibration
    if "sport" in c:
        c = c[c["sport"].fillna("ncaaf").astype(str) == sport]
    c = c[c["market"] == market]
    if "season_type" in c:
        c = c[c["season_type"].fillna("regular") == "regular"]
    c = c.dropna(subset=["abs_edge", "claimed", "won"])
    return c[pd.to_numeric(c["won"], errors="coerce") != 0.5]


def share(calibration: pd.DataFrame | None, sport: str, market: str) -> tuple[float, int]:
    """(the share of Atlas's disagreement with the market that has turned out real, the games it was fitted
    on). Least squares through the market: realised minus market against claimed minus market. On a
    moneyline the market's probability is the claimed one less the stored edge; at a spread or total line
    it is one half, the line being the market's median."""
    cal_market = CALIBRATION_MARKET.get((sport, market), market)
    c = _record(calibration, sport, cal_market)
    default = DEFAULT_SHARE.get((sport, cal_market), 0.0)
    if len(c) < MIN_RECORD:
        return default, len(c)
    claimed = pd.to_numeric(c["claimed"], errors="coerce")
    won = pd.to_numeric(c["won"], errors="coerce")
    if cal_market == "moneyline":
        market_p = claimed - pd.to_numeric(c["abs_edge"], errors="coerce") / 100.0
    else:
        market_p = pd.Series(0.5, index=c.index)
    d = claimed - market_p
    denom = float((d * d).sum())
    if denom <= 0:
        return default, len(c)
    return float(np.clip(((won - market_p) * d).sum() / denom, 0.0, 1.0)), len(c)


def edge_curve(calibration: pd.DataFrame | None, sport: str):
    """Atlas's side of the total against the close as a function of the size of its disagreement: the
    walk-forward hit rate over games at or beyond each gap. Never below one half: a model that has been
    wrong is priced as the market, not against itself. None when the record is thin."""
    c = _record(calibration, sport, "total")
    if len(c) < MIN_CURVE:
        return None
    edges = pd.to_numeric(c["abs_edge"], errors="coerce").to_numpy(dtype=float)
    won = pd.to_numeric(c["won"], errors="coerce").to_numpy(dtype=float) == 1.0
    order = np.argsort(-edges)
    edges, won = edges[order], won[order]
    cum = np.cumsum(won) / np.arange(1, len(won) + 1)
    steps = np.arange(0.0, 12.5, 0.5)
    rate = np.array([cum[edges >= g][-1] if (edges >= g).sum() >= 60 else np.nan for g in steps])
    rate = pd.Series(rate).ffill().bfill().to_numpy()
    rate = np.clip(rate, 0.5, 1.0)

    def p(gap: float) -> float:
        i = min(int(abs(float(gap)) / 0.5), len(steps) - 1)
        return float(rate[i])
    return p


# ---------------------------------------------------------------------------
# Atlas's reading of a contract
# ---------------------------------------------------------------------------


def atlas_over(atlas_total, shrink, over_sd, line) -> float:
    """Atlas's calibrated P(over ``line``) from the projection's own shrink and sd."""
    try:
        a, s, sd, ln = float(atlas_total), float(shrink), float(over_sd), float(line)
    except (TypeError, ValueError):
        return float("nan")
    if not all(math.isfinite(v) for v in (a, s, sd, ln)) or sd <= 0:
        return float("nan")
    return float(stats.norm.cdf(s * (a - ln) / sd))


#: Market lines whose probability sits inside this band say where the market's centre is; the tails of a
#: ladder are priced too coarsely to.
CENTRE_BAND = (0.15, 0.85)


def market_centre(part: pd.DataFrame, shape, first_side: str) -> float:
    """Where Polymarket's ladder puts the centre of a margin or total: for each line whose first side (the
    home side, the over) is priced inside :data:`CENTRE_BAND`, the centre at which the market's shape gives
    that line that probability; the median of them. nan with no such line."""
    found = []
    for r in part[part["side"] == first_side].itertuples():
        q = float(r.p_market) if pd.notna(r.p_market) else float("nan")
        if not (CENTRE_BAND[0] <= q <= CENTRE_BAND[1]):
            continue
        line = float(r.line)
        market_line = line if first_side == "over" else -line      # a home handicap h: the margin line is -h
        found.append(probability.centre_for(shape, market_line, q))
    return float(np.median(found)) if found else float("nan")


def anchored_centre(market: str, c_market: float, c_atlas: float, shape, k: float, curve) -> float:
    """The centre a position is priced from. A total with a curve: the centre at which the market's own
    shape gives the market's line the curve's hit rate for Atlas's side at this gap. Otherwise the market
    pulled toward Atlas by the share ``k``."""
    if not (math.isfinite(c_market) and math.isfinite(c_atlas)):
        return float("nan")
    if market == "total" and curve is not None:
        gap = c_atlas - c_market
        if abs(gap) < 1e-9:
            return c_market
        hit = curve(gap)
        over = hit if gap > 0 else 1.0 - hit
        return probability.centre_for(shape, c_market, over)
    return c_market + k * (c_atlas - c_market)


def line_prob(shape, centre: float, market: str, side: str, line: float) -> float:
    """The side's probability at its line under the shape centred at ``centre``, pushes left out."""
    if not math.isfinite(centre):
        return float("nan")
    pmf = shape.pmf(centre)
    if market == "total":
        p_over = probability.first_side(pmf, float(line))
        return p_over if side == "over" else 1.0 - p_over
    home_handicap = float(line) if side == "home" else -float(line)
    p_home = probability.first_side(pmf, -home_handicap)
    return p_home if side == "home" else 1.0 - p_home


def nhl_prob(pr, market: str, side: str, line: float) -> float:
    """The grid's probability for an NHL contract; nan at a line it holds no reading at (a puck line other
    than 1.5, a total outside 4.5 to 7.5 or on a whole goal)."""
    try:
        if market == "moneyline":
            p = float(pr["p_home"])
            return p if side == "home" else 1.0 - p
        if market == "spread":
            if abs(abs(float(line)) - 1.5) > 1e-9:
                return float("nan")
            home_by_two, away_by_two = float(pr["p_home_minus_1_5"]), float(pr["p_away_minus_1_5"])
            if side == "home":
                return home_by_two if line < 0 else 1.0 - away_by_two
            return away_by_two if line < 0 else 1.0 - home_by_two
        if market == "total":
            key = f"p_over_{float(line):.1f}"
            if key in pr.index and pd.notna(pr[key]):
                p = float(pr[key])
                return p if side == "over" else 1.0 - p
    except (TypeError, ValueError, KeyError):
        return float("nan")
    return float("nan")


# ---------------------------------------------------------------------------
# The whole board
# ---------------------------------------------------------------------------


def _latest(frame: pd.DataFrame | None) -> pd.DataFrame | None:
    if frame is None or frame.empty:
        return None
    f = frame.sort_values("refreshed_at").drop_duplicates("game_id", keep="last")
    return f.assign(game_id=f["game_id"].astype(str)).set_index("game_id")


def market_probs(q: pd.DataFrame) -> pd.Series:
    """Each contract's market probability: its midpoint over the two outcomes' midpoints; the bid-ask
    midpoint where a side has no stored midpoint."""
    mid = pd.to_numeric(q["mid"], errors="coerce")
    bid, ask = pd.to_numeric(q["bid"], errors="coerce"), pd.to_numeric(q["ask"], errors="coerce")
    mid = mid.where(mid.notna(), (bid + ask) / 2.0)
    total = mid.groupby(q["market_id"]).transform("sum")
    count = mid.groupby(q["market_id"]).transform("count")
    return (mid / total).where((count == 2) & (total > 0))


def price(quotes: pd.DataFrame, projections: pd.DataFrame | None, nhl_projections: pd.DataFrame | None,
          shapes: dict | None, calibration: pd.DataFrame | None) -> pd.DataFrame:
    """Every matched contract with its three probabilities, the fee, the cost, expected value and Kelly.

    Football is priced in centre space: the market's centre for the margin and the total is read off
    Polymarket's own ladder (`market_centre`), Atlas's is the projection, and the anchored centre
    (`anchored_centre`) prices every line of the ladder at once, so a contract on the tail of the ladder
    is valued by the same distribution as the main line. The NHL grid holds a probability per line, so
    the NHL is anchored in probability space, line by line.
    """
    if quotes.empty or "game_id" not in quotes:
        return quotes.assign(**{c: pd.Series(dtype=float) for c in PRICED_COLUMNS})
    q = quotes[quotes["game_id"].notna()].copy()
    if q.empty:
        return q.assign(**{c: pd.Series(dtype=float) for c in PRICED_COLUMNS})
    shapes = shapes or {}
    proj, nhl = _latest(projections), _latest(nhl_projections)
    sports = set(q["sport"].astype(str))
    curves = {s: edge_curve(calibration, s) for s in sports if s != "nhl"}
    shares = {(s, m): share(calibration, s, m)[0] for s in sports for m in ("moneyline", "spread", "total")}
    q["p_market"] = market_probs(q)
    q["p_raw"] = np.nan
    q["p_ladder"] = np.nan
    q["share"] = np.nan
    q["p"] = np.nan
    q["centre_market"] = np.nan
    q["centre_atlas"] = np.nan
    q["centre"] = np.nan
    for (sport, game), part in q.groupby([q["sport"].astype(str), q["game_id"].astype(str)]):
        if sport == "nhl":
            if nhl is None or game not in nhl.index:
                continue
            pr = nhl.loc[game]
            for i, r in part.iterrows():
                raw = nhl_prob(pr, str(r["market"]), str(r["side"]), float(r["line"]))
                k = shares[(sport, str(r["market"]))]
                q.at[i, "p_raw"], q.at[i, "share"] = raw, k
                if pd.notna(r["p_market"]):
                    q.at[i, "p"] = r["p_market"] + k * (raw - r["p_market"]) if math.isfinite(raw) else r["p_market"]
            continue
        if proj is None or game not in proj.index:
            continue
        pr = proj.loc[game]
        for family, markets in (("margin", ("moneyline", "spread")), ("total", ("total",))):
            rows = part[part["market"].isin(markets)]
            if rows.empty:
                continue
            shape = shapes.get((sport, family)) or probability.default_shape(sport, family)
            c_atlas = float(pr["margin_mean"] if family == "margin" else pr["total_mean"])
            c_market = market_centre(rows, shape, "home" if family == "margin" else "over")
            k = shares[(sport, "spread" if family == "margin" else "total")]
            curve = curves.get(sport) if family == "total" else None
            c = anchored_centre(family, c_market, c_atlas, shape, k, curve)
            for i, r in rows.iterrows():
                market, side, line = str(r["market"]), str(r["side"]), float(r["line"])
                q.at[i, "p_raw"] = line_prob(shape, c_atlas, market, side, line)
                # The market's own ladder read at this line: a quote far from it is the ladder disagreeing
                # with itself, not Atlas with the market.
                ladder = line_prob(shape, c_market, market, side, line)
                q.at[i, "p_ladder"] = ladder
                q.at[i, "share"] = 1.0 if curve is not None else k
                q.at[i, "centre_market"], q.at[i, "centre_atlas"], q.at[i, "centre"] = c_market, c_atlas, c
                # The quote itself, moved by what the anchoring moves the ladder at this line: with nothing
                # to add, Atlas's probability is the market's own.
                anchored = line_prob(shape, c, market, side, line)
                shift = anchored - ladder if math.isfinite(anchored) and math.isfinite(ladder) else 0.0
                q.at[i, "p"] = min(max(float(r["p_market"]) + shift, 0.0), 1.0) if pd.notna(r["p_market"]) else np.nan
    ask = pd.to_numeric(q["ask"], errors="coerce")
    rate = pd.to_numeric(q["fee_rate"], errors="coerce").fillna(0.0)
    q["fee"] = [fee(a, f) for a, f in zip(ask, rate, strict=True)]
    q["cost"] = ask + q["fee"]
    ok = (ask > 0) & (ask < 1) & (q["cost"] < 1) & q["p"].notna()
    q["ev"] = np.where(ok, q["p"] / q["cost"] - 1.0, np.nan)
    q["kelly"] = np.where(ok, ((q["p"] - q["cost"]) / (1.0 - q["cost"])).clip(lower=0.0), np.nan)
    return q.reset_index(drop=True)


def shares_table(calibration: pd.DataFrame | None, sports=("ncaaf", "nfl", "nhl")) -> pd.DataFrame:
    """The shares and the record sizes behind them, for the reports."""
    rows = []
    for s in sports:
        for m in ("moneyline", "spread", "total"):
            k, n = share(calibration, s, m)
            curve = s != "nhl" and m == "total" and edge_curve(calibration, s) is not None
            rows.append({"sport": s, "market": m, "share": k, "games": n, "curve": bool(curve)})
    return pd.DataFrame(rows)
