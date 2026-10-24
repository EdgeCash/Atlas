"""Standing orders late in games, backtested on Polymarket US's own tape.

    python -m atlas.polymarket.standing          # from the favorites backtest's cache; reads only what is missing

The rule, the primary test and its pass criteria are fixed in
``docs/STANDING_ORDER_PREREGISTRATION.md``, committed before this was written.
In short: late in a game, the first minute a side's ask reaches a threshold
on a tight book, post a buy limit some cents under that ask for a few
minutes; it fills when the ask falls below it, at its own price, and is
graded by the venue's settlement. Late is elapsed time against the league's
median game length - knowable during the game - and not minutes to the
recorded finish, which is not.

The games and the minute-by-minute tapes are the favorites backtest's
(`atlas/polymarket/backtest.py`, cached under ``data/raw/polymarket_us/``).
The orders go to a CSV beside the cache; the summaries and the report to
``reports/standing_order_backtest.md`` and ``reports/tables/``. Nothing here
buys anything.
"""

from __future__ import annotations

import argparse
import math
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from atlas import config
from atlas.polymarket import backtest, pricing, source
from atlas.util import get_logger, offline, session

LOG = get_logger(__name__)

THRESHOLDS = (0.85, 0.90)
DIPS = (0.01, 0.03, 0.05)
WINDOWS = (3, 5, 10)
FILLS = ("through", "touch")
FEES = ("taker", "none")
CEILING = 0.98
TIGHT = 0.04
#: Late: this many minutes before the league's median game length, or later.
LATE_BEFORE = 15.0
#: The primary test (docs/STANDING_ORDER_PREREGISTRATION.md) and its criteria.
PRIMARY = {"threshold": 0.85, "dip": 0.03, "window": 5, "fill": "through", "fee": "taker"}
MIN_FILLS = 200
Z = 1.96

ORDER_COLUMNS = ["league", "event_id", "label", "side", "long", "threshold", "trigger_at", "minutes_in", "trigger_ask",
                 "spread", "fee_rate", "payout", "won", "dip", "window", "fill", "price", "filled", "filled_at"]


def late_starts(games: pd.DataFrame) -> dict[str, float]:
    """Minutes after the start from which a game of each league counts as late: its median length less
    :data:`LATE_BEFORE`. A league constant, the same for every game in it."""
    if games.empty:
        return {}
    length = (pd.to_datetime(games["finished"], utc=True, errors="coerce")
              - pd.to_datetime(games["start"], utc=True, errors="coerce")).dt.total_seconds() / 60.0
    med = length.groupby(games["league"]).median().dropna()
    return {str(k): float(v) - LATE_BEFORE for k, v in med.items()}


def _tape(h: pd.DataFrame) -> pd.DataFrame:
    t = h.assign(long=pd.to_numeric(h["long"], errors="coerce"), short=pd.to_numeric(h["short"], errors="coerce"))
    t = t.dropna(subset=["at"]).sort_values("at", kind="stable").set_index("at")
    return t[~t.index.duplicated(keep="last")]


def orders(g: dict, h: pd.DataFrame, late_from: float, *, thresholds=THRESHOLDS, dips=DIPS, windows=WINDOWS,
           ceiling: float = CEILING, tight: float = TIGHT) -> list[dict]:
    """The rule on one game's tape: for each side and threshold, the trigger (the first late minute the ask
    reached the threshold on a tight book), and for each dip and window the standing order it posts and
    whether each fill model fills it. Rows in :data:`ORDER_COLUMNS`, plus one row per trigger with ``dip``
    of zero and ``fill`` of ``taker``: the ask taken at the trigger, for comparison."""
    result_long = float(g.get("result_long", float("nan")))
    if h.empty or not math.isfinite(result_long) or not math.isfinite(late_from):
        return []
    start = pd.Timestamp(g["start"])
    end = backtest.game_end(h, start, g.get("finished"))
    tape = _tape(h)
    spread = (tape["long"] + tape["short"] - 1.0).clip(lower=0.0)
    late = (tape.index >= start + timedelta(minutes=late_from)) & (tape.index < end)
    rate = float(g.get("fee_rate", 0.0) or 0.0)
    long_side = g.get("long_side")
    out: list[dict] = []
    for column, is_long in (("long", True), ("short", False)):
        series = tape[column]
        payout = result_long if is_long else 1.0 - result_long
        side = (long_side if is_long else {"away": "home", "home": "away"}.get(long_side)) or column
        for t in thresholds:
            ok = late & (series >= t - 1e-9) & (series <= ceiling + 1e-9) & (spread <= tight + 1e-9)
            if not ok.any():
                continue
            when = series.index[np.argmax(ok)]
            ask = float(series.loc[when])
            base = {"league": g["league"], "event_id": g["event_id"], "label": g["label"], "side": side,
                    "long": is_long, "threshold": t, "trigger_at": when,
                    "minutes_in": round((when - start).total_seconds() / 60.0, 1), "trigger_ask": ask,
                    "spread": float(spread.loc[when]), "fee_rate": rate, "payout": payout,
                    "won": 1.0 if payout >= 0.999 else 0.0}
            out.append({**base, "dip": 0.0, "window": 0, "fill": "taker", "price": ask, "filled": True,
                        "filled_at": when})
            for w in windows:
                life = series[(series.index > when) & (series.index <= when + timedelta(minutes=w))
                              & (series.index < end)]
                for d in dips:
                    price = round(ask - d, 2)
                    if price <= 0.0:
                        continue
                    for fill in FILLS:
                        hit = life[(life < price - 1e-9) if fill == "through" else (life <= price + 1e-9)]
                        out.append({**base, "dip": d, "window": w, "fill": fill, "price": price,
                                    "filled": not hit.empty, "filled_at": hit.index[0] if len(hit) else pd.NaT})
    return out


def costed(o: pd.DataFrame, fee: str) -> pd.DataFrame:
    """The orders with their cost per contract under a fee model, and the profit of the filled ones."""
    price = pd.to_numeric(o["price"], errors="coerce")
    rate = pd.to_numeric(o["fee_rate"], errors="coerce").fillna(0.0)
    # The taker at the trigger always pays the taker fee; a standing order pays it or none.
    pays = (o["fill"] == "taker") | (fee == "taker")
    fees = np.where(pays, [pricing.fee(p, r) for p, r in zip(price, rate, strict=True)], 0.0)
    cost = price + np.nan_to_num(fees)
    return o.assign(fee=fee, cost=cost, profit=pd.to_numeric(o["payout"], errors="coerce") - cost)


def summary(o: pd.DataFrame, by=("threshold", "dip", "window", "fill", "fee")) -> pd.DataFrame:
    """Per cell: orders posted and filled, the fill rate, and over the filled ones the win rate, the
    break-even rate (the mean cost), the edge with a game-clustered standard error, and the profit per
    dollar."""
    cols = [*by, "orders", "filled", "fill_rate", "win_rate", "break_even", "edge", "se", "profit_per_dollar"]
    if o is None or o.empty:
        return pd.DataFrame(columns=cols)
    rows = []
    for key, g in o.groupby(list(by), sort=True):
        key = key if isinstance(key, tuple) else (key,)
        f = g[g["filled"].astype(bool)]
        n = len(f)
        won, cost = pd.to_numeric(f["won"], errors="coerce"), pd.to_numeric(f["cost"], errors="coerce")
        rows.append({**dict(zip(by, key, strict=True)), "orders": int(len(g)), "filled": n,
                     "fill_rate": n / len(g) if len(g) else float("nan"),
                     "win_rate": float(won.mean()) if n else float("nan"),
                     "break_even": float(cost.mean()) if n else float("nan"),
                     "edge": float((won - cost).mean()) if n else float("nan"),
                     "se": backtest.cluster_se(won - cost, f["event_id"]) if n else float("nan"),
                     "profit_per_dollar": float(f["profit"].sum() / cost.sum()) if n and cost.sum() > 0 else float("nan")})
    return pd.DataFrame(rows, columns=cols)


def primary(o: pd.DataFrame) -> dict:
    """The pre-registered test: the primary cell, its halves, and whether each criterion holds."""
    p = PRIMARY
    cell = o[(o["threshold"].round(2) == p["threshold"]) & (o["dip"].round(2) == p["dip"])
             & (o["window"] == p["window"]) & (o["fill"] == p["fill"]) & (o["fee"] == p["fee"])]
    filled = cell[cell["filled"].astype(bool)]
    s = summary(cell, by=("threshold",)).iloc[0].to_dict() if len(cell) else {}
    halves = []
    if len(filled):
        when = pd.to_datetime(filled["trigger_at"], utc=True)
        cut = when.median()
        for name, part in (("first half", filled[when <= cut]), ("second half", filled[when > cut])):
            won, cost = pd.to_numeric(part["won"]), pd.to_numeric(part["cost"])
            halves.append({"half": name, "from": when[part.index].min(), "to": when[part.index].max(),
                           "filled": int(len(part)), "edge": float((won - cost).mean()) if len(part) else float("nan"),
                           "se": backtest.cluster_se(won - cost, part["event_id"]) if len(part) else float("nan")})
    n = int(s.get("filled", 0) or 0)
    edge, se = float(s.get("edge", float("nan"))), float(s.get("se", float("nan")))
    checks = {"at least 200 fills": n >= MIN_FILLS,
              "edge less 1.96 errors above zero": bool(math.isfinite(edge) and math.isfinite(se) and edge - Z * se > 0),
              "edge above zero in both halves": bool(len(halves) == 2 and all(h["edge"] > 0 for h in halves))}
    return {"cell": s, "halves": halves, "checks": checks, "passed": all(checks.values())}


# ---------------------------------------------------------------------------
# The run and the report
# ---------------------------------------------------------------------------


def run(leagues=backtest.LEAGUES, *, raw: Path | None = None, sess=None) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """(the games, every order under every fee model, the late starts by league), from the cached tapes."""
    raw = raw or backtest.raw_dir()
    gs = backtest.games(backtest.closed_events(None if offline() else (sess or session()),
                                               cache=raw / "closed_events.json"), leagues)
    starts = late_starts(gs)
    LOG.info("standing: late from %s minutes", {k: round(v) for k, v in starts.items()})
    rows: list[dict] = []
    for i, g in enumerate(gs.to_dict("records"), 1):
        cached = (raw / "history" / f"{g['market_slug']}.json").exists()
        if not cached and offline():
            continue
        try:
            h = backtest.history(str(g["market_slug"]), g["start"], g["finished"], sess, cache_dir=raw / "history")
        except Exception as error:  # noqa: BLE001 - one market's tape missing is not the backtest's
            LOG.info("standing: no history for %s (%s)", g["market_slug"], type(error).__name__)
            continue
        if not cached:
            time.sleep(source.PAUSE)
        rows.extend(orders(g, h, starts.get(str(g["league"]), float("nan"))))
        if i % 1000 == 0:
            LOG.info("standing: %d of %d games, %d orders", i, len(gs), len(rows))
    o = pd.DataFrame(rows, columns=ORDER_COLUMNS)
    if o.empty:
        return gs, o.assign(fee=pd.Series(dtype=str), cost=pd.Series(dtype=float), profit=pd.Series(dtype=float)), starts
    both = pd.concat([costed(o, fee) for fee in FEES], ignore_index=True)
    both = both[~((both["fill"] == "taker") & (both["fee"] == "none"))].reset_index(drop=True)
    return gs, both, starts


def _pct(v) -> str:
    return f"{v:.1%}" if pd.notna(v) else ""


def _pts(e, se) -> str:
    if pd.isna(e):
        return ""
    return f"{100 * e:+.1f} ± {100 * se:.1f}" if pd.notna(se) else f"{100 * e:+.1f}"


def _day(t) -> str:
    t = pd.Timestamp(t) if t is not None else pd.NaT
    return "" if pd.isna(t) else f"{t:%Y-%m-%d}"


def _table(s: pd.DataFrame, keys: list[str]) -> str:
    names = {"threshold": "Threshold", "dip": "Under the ask", "window": "Minutes", "fill": "Fill", "fee": "Fee",
             "league": "League"}
    head = [names.get(k, k) for k in keys] + ["Filled / posted", "Win rate", "Break-even", "Edge (pts)", "Profit per $"]
    lines = ["| " + " | ".join(head) + " |", "|" + "|".join("---" for _ in head) + "|"]
    for x in s.itertuples(index=False):
        cells = []
        for k in keys:
            v = getattr(x, k)
            cells.append(f"{float(v):.0%}" if k == "threshold" else f"{100 * float(v):.0f}¢" if k == "dip"
                         else str(v).upper() if k == "league" else str(v))
        cells += [f"{x.filled} / {x.orders}", _pct(x.win_rate), _pct(x.break_even), _pts(x.edge, x.se),
                  _pct(x.profit_per_dollar)]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def report(gs: pd.DataFrame, o: pd.DataFrame, starts: dict, now: datetime | None = None) -> tuple[str, dict]:
    now = now or datetime.now(UTC)
    tables: dict[str, pd.DataFrame] = {}
    lines = ["# Standing orders late in games, on Polymarket US's own tape", "",
             f"*Built {now:%Y-%m-%d %H:%M} UTC by `python -m atlas.polymarket.standing`. The rule and the test were "
             "fixed first, in [`docs/STANDING_ORDER_PREREGISTRATION.md`](../docs/STANDING_ORDER_PREREGISTRATION.md).*",
             "", "Late in a game, the first minute a side's ask reaches the threshold on a book inside 4¢, a buy "
             "limit is posted some cents under that ask for a few minutes. It fills at its own price when the ask "
             "falls below it, and is graded by the venue's settlement. Late is elapsed time against the league's "
             "median game length, which is knowable during the game:", ""]
    lines += ["| League | Late from (minutes after the start) |", "|---|---|"]
    lines += [f"| {k.upper()} | {v:.0f} |" for k, v in sorted(starts.items())] + [""]
    if o.empty:
        return "\n".join(lines + ["No orders: no late trigger on any tape.", ""]), tables
    test = primary(o)
    c = test["cell"]
    verdict = "**Passed.**" if test["passed"] else "**Not established.**"
    lines += ["## The pre-registered test", "",
              f"85¢, 3¢ under the ask, resting 5 minutes, filled only when the ask goes below it, paying the taker "
              f"fee. {verdict}", "",
              "| | |", "|---|---|",
              f"| Orders posted | {int(c.get('orders', 0))} |", f"| Filled | {int(c.get('filled', 0))} "
              f"({_pct(c.get('fill_rate'))}) |", f"| Win rate | {_pct(c.get('win_rate'))} |",
              f"| Break-even (mean cost) | {_pct(c.get('break_even'))} |",
              f"| Edge | {_pts(c.get('edge'), c.get('se'))} points |",
              f"| Profit per $ | {_pct(c.get('profit_per_dollar'))} |", ""]
    lines += ["| Criterion | Held |", "|---|---|"] + [f"| {k} | {'yes' if v else 'no'} |"
                                                       for k, v in test["checks"].items()] + [""]
    if test["halves"]:
        lines += ["| Half | Triggers from | to | Filled | Edge (pts) |", "|---|---|---|---|---|"]
        lines += [f"| {h['half']} | {_day(h['from'])} | {_day(h['to'])} | {h['filled']} | {_pts(h['edge'], h['se'])} |"
                  for h in test["halves"]] + [""]
    tables["primary_halves"] = pd.DataFrame(test["halves"])
    # Comparison: the taker at the trigger.
    taker = summary(o[o["fill"] == "taker"], by=("threshold",))
    tables["taker_at_trigger"] = taker
    lines += ["## For comparison: taking the ask at the trigger", "",
              "The same late triggers, bought at the trigger minute's ask with the taker fee. This is the live "
              "favorites rule's late trade, with late defined the same knowable way.", "",
              _table(taker, ["threshold"]), ""]
    # The primary by league.
    p = PRIMARY
    pcell = o[(o["dip"].round(2) == p["dip"]) & (o["window"] == p["window"]) & (o["fill"] == p["fill"])
              & (o["fee"] == p["fee"])]
    s = summary(pcell, by=("league", "threshold"))
    tables["primary_by_league"] = s
    lines += ["## The primary rule by league (exploration)", "", _table(s, ["league", "threshold"]), ""]
    # The whole grid.
    grid = summary(o[o["fill"] != "taker"])
    tables["grid"] = grid
    lines += ["## Every cell (exploration)", "",
              "Each row is a separate rule. With 72 of them, a few will look good by chance; none but the "
              "pre-registered one above counts as evidence.", "",
              _table(grid, ["threshold", "dip", "window", "fill", "fee"]), ""]
    lines += ["## Reading it", "",
              "- A filled order pays its own limit price; the break-even rate is that price plus the fee.",
              "- The fills are a selected set: an order fills only when the market has fallen, which is when the "
              "favorite's position has got worse. The win rate is measured on that set.",
              "- One sample a minute of the top of the book: a dip between samples is missed, and a fill assumes "
              "no one was ahead of the order at its price. Touch fills are the more generous of the two.",
              "- Elapsed time is not the game clock. The live worker marks late by the venue's period, which this "
              "tape does not carry; its paper record is the test of that.", ""]
    return "\n".join(lines), tables


def write(gs: pd.DataFrame, o: pd.DataFrame, starts: dict, *, reports: Path | None = None,
          raw: Path | None = None) -> Path:
    reports = reports or config.paths().reports
    raw = raw or backtest.raw_dir()
    text, tables = report(gs, o, starts)
    out = reports / "standing_order_backtest.md"
    out.write_text(text)
    (reports / "tables").mkdir(parents=True, exist_ok=True)
    for name, t in tables.items():
        t.to_csv(reports / "tables" / f"standing_order_{name}.csv", index=False, float_format="%.4f")
    raw.mkdir(parents=True, exist_ok=True)
    o.to_csv(raw / "standing_order_backtest.csv", index=False, float_format="%.4f")
    return out


def main() -> None:
    argparse.ArgumentParser(description="Standing orders late in games, on Polymarket US's own tape").parse_args()
    gs, o, starts = run()
    out = write(gs, o, starts)
    test = primary(o) if len(o) else {"passed": False, "checks": {}}
    print(f"{len(gs)} games, {int((o['fill'] != 'taker').sum()) if len(o) else 0} standing orders -> {out}")
    print("pre-registered test:", "PASSED" if test["passed"] else "not established", test["checks"])


if __name__ == "__main__":
    main()
