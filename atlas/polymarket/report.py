"""The public page about the model: ``reports/polymarket_model.md``.

What Polymarket quotes on the games Atlas projects, how far Atlas sits from
it, and what the record says that distance is worth. No position, no
expected value and no contract is on it: the paper record is the owner's,
sealed, and the page says so.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from atlas import config
from atlas.polymarket import pricing


def path() -> Path:
    return config.paths().reports / "polymarket_model.md"


def _md(frame: pd.DataFrame) -> str:
    cols = list(frame.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for row in frame.itertuples(index=False):
        lines.append("| " + " | ".join("" if (isinstance(v, float) and np.isnan(v)) else str(v) for v in row) + " |")
    return "\n".join(lines)


def coverage(priced: pd.DataFrame, upcoming: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for sport in ("ncaaf", "nfl", "nba", "nhl"):
        ahead = upcoming[upcoming["sport"].astype(str) == sport] if len(upcoming) else upcoming
        mine = priced[priced["sport"].astype(str) == sport] if len(priced) else priced
        main = mine[pd.to_numeric(mine["p_market"], errors="coerce").between(0.3, 0.7)] if len(mine) else mine
        rows.append({"Sport": sport.upper(), "Games ahead": len(ahead),
                     "On Polymarket": int(mine["game_id"].nunique()) if len(mine) else 0,
                     "Contracts": len(mine),
                     "Median spread (main lines)": f"{100 * main['spread'].median():.1f}¢" if len(main) else "–",
                     "Median depth (main lines)": f"${main['liquidity'].median():,.0f}" if len(main) else "–",
                     "Fee rate": f"{100 * mine['fee_rate'].median():.0f}%" if len(mine) else "–"})
    return pd.DataFrame(rows)


def distance(priced: pd.DataFrame) -> pd.DataFrame:
    """How far Atlas sits from Polymarket's centre, per sport and family, in points: the projection's own
    distance, and the anchored number's."""
    cols = ["Sport", "Market", "Games", "Atlas, median gap", "Atlas, largest gap", "Anchored, median gap"]
    if not len(priced) or "centre_market" not in priced:
        return pd.DataFrame(columns=cols)
    f = priced[priced["centre_market"].notna()]
    if f.empty:
        return pd.DataFrame(columns=cols)
    f = f.assign(family=np.where(f["market"] == "total", "total", "margin"))
    rows = []
    for (sport, family), part in f.groupby(["sport", "family"]):
        one = part.drop_duplicates("game_id")
        market = pd.to_numeric(one["centre_market"], errors="coerce")
        raw = (pd.to_numeric(one["centre_atlas"], errors="coerce") - market).abs()
        anchored = (pd.to_numeric(one["centre"], errors="coerce") - market).abs()
        rows.append({"Sport": str(sport).upper(), "Market": family, "Games": len(one),
                     "Atlas, median gap": f"{raw.median():.1f}", "Atlas, largest gap": f"{raw.max():.1f}",
                     "Anchored, median gap": f"{anchored.median():.2f}"})
    return pd.DataFrame(rows, columns=cols)


def write(priced: pd.DataFrame, upcoming: pd.DataFrame, calibration: pd.DataFrame | None, now: datetime,
          where: Path | None = None) -> Path:
    shares = pricing.shares_table(calibration)
    shares_rows = shares.assign(**{
        "Sport": shares["sport"].str.upper(), "Market": shares["market"],
        "Share of Atlas's disagreement taken": [("the record's hit rate by gap" if c else f"{k:.0%}")
                                                for k, c in zip(shares["share"], shares["curve"], strict=True)],
        "Games on the record": shares["games"]})[["Sport", "Market", "Share of Atlas's disagreement taken",
                                                  "Games on the record"]]
    stamp = pd.Timestamp(now).tz_convert("UTC").strftime("%Y-%m-%d %H:%M UTC")
    text = f"""# Atlas on Polymarket

*Rebuilt every run; this one at {stamp}.*

Polymarket is the one venue Atlas is priced against. It lists a moneyline,
a ladder of spreads and a ladder of totals on every NFL, NBA, NHL and college
football game as binary contracts, and its prices are public: every run
reads them from Polymarket's own API, matches each game to the one Atlas
projects, and keeps every quote, timestamped, in
`tracking/polymarket_quotes.csv`. That table is the point-in-time archive of
the market Atlas is measured against.

## Coverage this run

{_md(coverage(priced, upcoming))}

Spread is the gap between the best bid and the best ask on the contracts
priced near even; depth is the dollars resting in the market. The fee is
Polymarket's taker fee, `rate × price × (1 − price)` per contract, read from
each market's own schedule.

## How Atlas is anchored to Polymarket

Atlas's number for a game is never used raw. Polymarket's centre for the
margin and the total is read off its own ladder of lines; Atlas's projection
is pulled toward it by the share of Atlas's disagreement that has turned out
real on the walk-forward record (`tracking/calibration.csv`), and every line
on the ladder is then priced from that one anchored centre. A share of 0%
means the record says Atlas adds nothing to the market there, and Atlas is
priced as the market.

{_md(shares_rows)}

On football totals the record is read as a curve: the hit rate of Atlas's
side at disagreements this large or larger, never below one half.

## How far the anchored number sits from the market

{_md(distance(priced))}

In points of margin or total, per game: Atlas's own projection against
Polymarket's centre, and the anchored number the contracts are priced from.
On a market where the share is zero the anchored gap is zero by
construction.

## The record

Paper positions are taken by a fixed rule, logged once and graded on the
result and against Polymarket's close. That record is the owner's, sealed
in `tracking/polymarket_positions/`, and is not published here. Nothing on
this page is a recommendation.
"""
    where = where or path()
    where.parent.mkdir(parents=True, exist_ok=True)
    where.write_text(text)
    return where
