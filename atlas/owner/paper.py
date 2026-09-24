"""The owner's paper tracker: Atlas's live signals as flat paper wagers, graded.

    python -m atlas.owner.paper             # the record, to the terminal

The live tracker (`atlas/live/signals.py`, `atlas/live/grade.py`) asks one
question - does the market move toward Atlas's number - and never asks what
that would have paid. This asks the second question, for the owner only: if
every signal had been taken at the number and price the book was quoting
when Atlas formed it, one unit each and nothing else, what would the record
be?

It adds no opinion and changes no signal. One paper wager per game and
market, the earliest signal (the tracker records one per book, and the feed
has named the same book two ways); graded on the final score from the
warehouse, or the tracking store's when the warehouse has not caught up. A
push returns the stake.

Judged the way `docs/SIGNAL_PREREGISTRATION.md` judged the historical signal,
against numbers fixed before the first live signal: the population that
counts is the tracker's own ``primary`` one (totals at or above the
historical 90th percentile of disagreement), and nothing is decided before
``MIN_GRADED`` of them are graded - the size `reports/live_clv_tracking.md`
names. The record is built from the committed signals and scores on every
heavy refresh, so nothing is stored; it is published only inside the owner
page's ciphertext, with every word of it, so the page's public script carries
none of this.
"""

from __future__ import annotations

import argparse
import json
import math

import numpy as np
import pandas as pd

from atlas.util import get_logger

LOG = get_logger(__name__)

#: Graded primary wagers before the record can say anything (reports/live_clv_tracking.md).
MIN_GRADED = 124
#: The price assumed when the feed gave none: the standard one.
DEFAULT_PRICE = -110.0
POPULATIONS = (
    ("primary", "College totals, strongest 10% (the one judged)"),
    ("secondary", "College spreads, strongest 10%, week 5 on"),
    ("observed", "Everything else Atlas recorded"),
)
#: Column heads that fit a phone, in POPULATIONS' order.
SHORT = (("primary", "Totals"), ("secondary", "Spreads"), ("observed", "Rest"))
#: The historical walk-forward test of the same idea, for comparison
#: (reports/atlas_signal_verification_final.md).
HISTORY = ("2018-2025, tested once each season on rules fixed in advance: 51.65% of 2,825 at -110, "
           "-1.4% per wager. Break-even at -110 is 52.38%.")


def payout(price: float) -> float:
    """Profit on one unit at American odds."""
    price = DEFAULT_PRICE if price is None or not math.isfinite(price) or price == 0 else price
    return 100.0 / abs(price) if price < 0 else price / 100.0


def break_even(price: float) -> float:
    p = payout(price)
    return 1.0 / (1.0 + p)


def results(research: pd.DataFrame | None, games: pd.DataFrame) -> pd.DataFrame:
    """Final margin (home minus away) and total per game: the warehouse's, else the tracking store's."""
    parts = []
    if research is not None and len(research):
        r = research[["game_id", "actual_margin", "actual_total"]].dropna()
        parts.append(r.rename(columns={"actual_margin": "final_margin", "actual_total": "final_total"}))
    if len(games):
        g = games[games["completed"].astype("string").str.lower().isin(["true", "1"])]
        g = g.dropna(subset=["home_score", "away_score"])
        parts.append(pd.DataFrame({"game_id": g["game_id"],
                                   "final_margin": g["home_score"].astype(float) - g["away_score"].astype(float),
                                   "final_total": g["home_score"].astype(float) + g["away_score"].astype(float)}))
    if not parts:
        return pd.DataFrame(columns=["game_id", "final_margin", "final_total"])
    out = pd.concat(parts, ignore_index=True)
    out["game_id"] = out["game_id"].astype(str)
    return out.drop_duplicates("game_id", keep="first")


def wagers(signals: pd.DataFrame, finals: pd.DataFrame, grades: pd.DataFrame | None = None) -> pd.DataFrame:
    """One paper wager per game and market, graded where the game is final."""
    if signals.empty:
        return pd.DataFrame(columns=["game_id", "market", "selection", "outcome", "profit"])
    s = signals.assign(game_id=signals["game_id"].astype(str)).sort_values(["created_at", "signal_id"])
    w = s.drop_duplicates(["game_id", "market"], keep="first").copy()
    w["price"] = pd.to_numeric(w["entry_price"], errors="coerce").fillna(DEFAULT_PRICE)
    w = w.merge(finals, on="game_id", how="left")
    final = np.where(w["market"] == "total", w["final_total"], w["final_margin"])
    sign = np.where(w["direction"].isin(["over", "home"]), 1.0, -1.0)
    edge = (final - w["entry_line"].astype(float)) * sign
    w["outcome"] = np.select([np.isnan(edge), edge > 0, edge < 0], ["open", "win", "loss"], "push")
    win = w["price"].map(payout)
    w["profit"] = np.select([w["outcome"] == "win", w["outcome"] == "loss"], [win, -1.0], 0.0)
    if grades is not None and len(grades):
        clv = grades.drop_duplicates("signal_id").set_index("signal_id")["clv_points"]
        w["clv"] = w["signal_id"].map(clv)
    else:
        w["clv"] = np.nan
    return w.reset_index(drop=True)


def wilson(wins: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return float("nan"), float("nan")
    p = wins / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return centre - half, centre + half


def record(w: pd.DataFrame) -> dict:
    """One population's numbers."""
    done = w[w["outcome"].isin(["win", "loss", "push"])]
    decided = done[done["outcome"] != "push"]
    wins = int((decided["outcome"] == "win").sum())
    lo, hi = wilson(wins, len(decided))
    be = float(decided["price"].map(break_even).mean()) if len(decided) else float("nan")
    return {"wagers": len(w), "graded": len(done), "open": int((w["outcome"] == "open").sum()),
            "wins": wins, "losses": int((decided["outcome"] == "loss").sum()),
            "pushes": int((done["outcome"] == "push").sum()),
            "win_rate": wins / len(decided) if len(decided) else float("nan"), "low": lo, "high": hi,
            "break_even": be, "units": float(done["profit"].sum()),
            "roi": float(done["profit"].sum() / len(done)) if len(done) else float("nan"),
            "clv": float(done["clv"].mean()) if done["clv"].notna().any() else float("nan")}


def verdict(r: dict) -> str:
    if r["graded"] < MIN_GRADED:
        return (f"Collecting: {r['graded']} of {MIN_GRADED} graded. Nothing can be read from fewer; "
                "treat every number below as noise until then.")
    if r["low"] > r["break_even"] and r["units"] > 0:
        return ("Clears: the win rate's 95% interval sits above break-even at the prices taken. "
                "It still has to hold into a second season before real money.")
    if r["win_rate"] > r["break_even"]:
        return "Not proven: above break-even, but the 95% interval reaches below it."
    return "Fails: at or below break-even at the prices taken."


def _pct(x: float) -> str:
    return "–" if x is None or not math.isfinite(x) else f"{x:.1%}"


def _num(x: float, fmt: str = "{:+.1f}") -> str:
    return "–" if x is None or not math.isfinite(x) else fmt.format(x)


def _matchups(games: pd.DataFrame | None) -> dict:
    if games is None or games.empty:
        return {}
    last = lambda name: str(name).split(" ")[-1] if isinstance(name, str) else "?"  # noqa: E731
    return {str(g.game_id): f"{last(g.away_team)} @ {last(g.home_team)}" for g in games.itertuples()}


def section(w: pd.DataFrame, games: pd.DataFrame | None = None) -> dict:
    """The owner page's view: every word in the ciphertext, none in the page's script."""
    recs = {key: record(w[w["selection"] == key]) for key, _ in POPULATIONS}
    measures = (
        ("Graded", lambda r: str(r["graded"])),
        ("Won-lost-push", lambda r: f"{r['wins']}-{r['losses']}-{r['pushes']}"),
        ("Win rate", lambda r: _pct(r["win_rate"])),
        ("95% range", lambda r: f"{_pct(r['low'])}–{_pct(r['high'])}" if r["wins"] + r["losses"] else "–"),
        ("Break-even", lambda r: _pct(r["break_even"])),
        ("Units", lambda r: _num(r["units"])),
        ("Per wager", lambda r: _num(r["roi"], "{:+.1%}")),
        ("CLV", lambda r: _num(r["clv"], "{:+.2f}")),
    )
    head = ["", *[short for _, short in SHORT]]
    rows = [[label, *[f(recs[key]) for key, _ in SHORT]] for label, f in measures]
    recent = w[(w["selection"] == "primary")].sort_values("created_at", ascending=False).head(15)
    names = _matchups(games)
    recent_rows = [[names.get(str(x.game_id), str(x.game_id)), f"{x.direction} {x.entry_line:g} ({x.price:+.0f})",
                    x.outcome if x.outcome == "open" else f"{x.outcome} {x.profit:+.2f}"]
                   for x in recent.itertuples()]
    notes = [
        "Paper only: every signal Atlas's live tracker records, taken as one flat unit at the number and price "
        "the book was quoting when Atlas formed it. No money, and no sizing.",
        verdict(recs["primary"]),
        "Columns: " + "; ".join(f"{short} is {label[0].lower() + label[1:]}" for (_, label), (_, short) in zip(POPULATIONS, SHORT,
                                                                                            strict=True)) + ".",
        "The historical test of the same idea: " + HISTORY,
        "Units are profit in stakes of one; per wager is units over graded wagers; CLV is the average points "
        "the closing line moved toward the side taken.",
    ]
    tables = [{"head": head, "rows": rows}]
    if recent_rows:
        tables.append({"title": "Latest college totals, strongest 10%",
                       "head": ["Game", "Side (price)", "Result (units)"], "rows": recent_rows})
    return {"title": "Paper tracker", "notes": notes, "tables": tables, "record": recs}


def build(store=None, research: pd.DataFrame | None = None) -> dict | None:
    """The section from the tracking store and the warehouse. Never raises."""
    try:
        if store is None:
            from atlas.live.store import Store

            store = Store.open()
        if research is None:
            try:
                from atlas.research.dataset import load_research_frame

                research = load_research_frame()
            except Exception as error:  # noqa: BLE001 - the tracking store's scores still grade
                LOG.info("paper tracker: no warehouse (%s)", type(error).__name__)
        signals = store.read("signals")
        if signals.empty:
            return None
        games = store.read("games")
        w = wagers(signals, results(research, games), store.read("grades"))
        return section(w, games)
    except Exception as error:  # noqa: BLE001
        LOG.error("paper tracker not built: %s", type(error).__name__)
        return None


def main() -> None:
    argparse.ArgumentParser(description="The owner's paper tracker").parse_args()
    s = build()
    print(json.dumps(s["record"] if s else {}, indent=1, default=str))


if __name__ == "__main__":
    main()
