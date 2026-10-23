"""The owner page's Polymarket sections: the day's positions, the board, and the record.

Each section is a dict the page's script renders (`atlas/site/assets/owner.js`): a title, the tab it
belongs in, tables (a head and rows; a cell is a string or a main value with second lines) and the
notes folded beneath. Everything here travels only inside the page's ciphertext.
"""

from __future__ import annotations

import math
from datetime import datetime

import pandas as pd

from atlas.polymarket import positions as pos

HEAD = ["Game", "Contract", "Price", "Edge"]
TOP_ROWS = 10
TAB = "Polymarket"
RECORD_TAB = "Record"


def _eastern(ts) -> str:
    t = pd.Timestamp(ts)
    t = t.tz_localize("UTC") if t.tzinfo is None else t
    return t.tz_convert(pos.EASTERN).strftime("%a %b %-d, %-I:%M %p")


def _cents(x) -> str:
    x = float(x) if x is not None else float("nan")
    return f"{100 * x:.1f}¢" if math.isfinite(x) else "–"


def _pct(x) -> str:
    x = float(x) if x is not None else float("nan")
    return f"{x:.1%}" if math.isfinite(x) else "–"


def _num(x) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return float("nan")
    return v


def _price(x) -> list:
    fee = _num(getattr(x, "fee", None))
    spread = _num(getattr(x, "spread", None))
    second = f"+{100 * fee:.1f}¢ fee" if math.isfinite(fee) else "fee –"
    if math.isfinite(spread):
        second += f" · spread {100 * spread:.0f}¢"
    return [_cents(getattr(x, "ask", None)), second]


def _edge(x) -> list:
    return [f"EV {_num(x.ev):+.1%}" if math.isfinite(_num(x.ev)) else "EV –",
            f"fair {_pct(x.p)} · market {_pct(x.p_market)}"]


def _contract(x) -> str:
    return pos.contract(str(x.market), str(x.side), float(x.line), str(x.away), str(x.home))


def positions_section(chosen: pd.DataFrame, graded: pd.DataFrame, now: datetime) -> dict:
    logged = set(graded["position_id"]) if len(graded) else set()
    day = pd.Timestamp(chosen["day"].iloc[0]).strftime("%a %b %-d") if len(chosen) else \
        pd.Timestamp(pos.day_of(now)).strftime("%a %b %-d")
    rows = [[[x.label, _eastern(x.kickoff)], [_contract(x), str(x.sport).upper()], _price(x), _edge(x),
             [f"{float(x.stake):.1%}", "logged" if x.position_id in logged else ""]]
            for x in chosen.itertuples()]
    tables = [{"title": "", "head": [*HEAD, "Stake"], "stack": True,
               "rows": rows or [[f"Nothing clears {pos.MIN_EV:+.0%} after the fee.", "", "", "", ""]]}]
    previews = preview_table(graded, chosen["day"].iloc[0] if len(chosen) else pos.day_of(now))
    if previews:
        tables.append(previews)
    return {"title": f"Positions for {day} ({len(rows)})", "tab": TAB, "tables": tables,
            "notes": [
                "Paper only: nothing is bought. A contract costs its ask plus Polymarket US's taker fee and pays $1 "
                "if it wins.",
                f"The rule: contracts Polymarket US is accepting orders on, quoted inside {100 * pos.MAX_SPREAD:.0f}¢ "
                f"with at least ${pos.MIN_LIQUIDITY:,.0f} of depth, fair between {pos.BAND[0]:.0%} and "
                f"{pos.BAND[1]:.0%}, and priced in line with their own ladder; {pos.MIN_EV:+.0%} or more after "
                f"the fee; one a game at the contract that pays best, at most {pos.MAX_POSITIONS} a day. Stake "
                f"is a share of the bankroll: a quarter of Kelly, (fair − cost) ÷ (1 − cost), capped at "
                f"{pos.MAX_STAKE:.0%} each and {pos.DAILY_CAP:.0%} a day.",
                f"The day's positions are logged once, at the first run from {pos.LOG_HOUR}:00 ET, at the prices "
                "shown then (marked logged); the table keeps moving through the day.",
                "Fair is Atlas anchored to the market by what the walk-forward record says Atlas's disagreement "
                "has been worth; market is the venue's own probability. Depth is the dollars resting at the best "
                "ask when the book was read, for the contracts that cleared the rest of the rule: confirm the "
                "book before real money.",
                "Order previews, where the venue key is set: each logged position put to Polymarket US's order "
                "preview as a limit at its ask for the stake's worth of contracts at a nominal bankroll, "
                "immediate-or-cancel, and what it says would fill. Nothing is entered."]}


def preview_table(graded: pd.DataFrame, day) -> dict | None:
    """The venue's order previews of the day's logged positions (atlas/polymarket/account.py): what each
    would have filled at against the ask it was logged at. None when none were taken."""
    from atlas.polymarket import account

    s = account.summary(graded, day)
    if s is None:
        return None
    r = graded[(graded["day"].astype(str) == str(day)) & graded["previewed_at"].notna()]
    rows = []
    for x in r.itertuples():
        qty, filled = float(x.preview_qty), float(x.preview_filled) if pd.notna(x.preview_filled) else float("nan")
        px = float(x.preview_px) if pd.notna(x.preview_px) else float("nan")
        state = str(x.preview_state)
        fill = f"{px:.2f}" if math.isfinite(px) else ("none" if state and not state.startswith("error") else "")
        rows.append([[x.label, _contract(x)], f"{float(x.ask):.2f}", fill,
                     f"{filled:g} of {qty:g}" if math.isfinite(filled) else state.replace("error:", "failed: "),
                     f"${float(x.preview_fee):.2f}" if pd.notna(x.preview_fee) else ""])
    gap = f"{100 * s['gap']:+.1f}¢" if math.isfinite(s["gap"]) else "n/a"
    return {"title": f"Order previews: {s['whole']} of {s['n']} would fill in full at the ask; mean fill {gap} "
                     f"from it; fees ${s['fee']:.2f} on ${s['cost']:,.0f}"
                     + (f"; {s['errors']} failed" if s["errors"] else ""),
            "head": ["Contract", "Ask", "Fill", "Filled", "Fee"], "stack": True, "rows": rows}


def board_section(priced: pd.DataFrame, now: datetime) -> dict:
    tables = []
    upcoming = priced[pd.to_datetime(priced["kickoff"], utc=True, errors="coerce") > pd.Timestamp(now)] \
        if len(priced) else priced
    if len(upcoming):
        ok = pos.eligible(upcoming, now)
        best = upcoming.assign(takeable=ok).sort_values(["takeable", "ev"], ascending=[False, False]) \
            .drop_duplicates(["game_id", "market"], keep="first")
        best = best.sort_values("ev", ascending=False)
        rows = [[[x.label, _eastern(x.kickoff)],
                 [_contract(x), str(x.sport).upper() + ("" if x.takeable else " · not takeable")],
                 _price(x), _edge(x)] for x in best.itertuples()]
        tables.append({"title": f"Best {min(TOP_ROWS, len(rows))} of {len(rows)} by expected value after the fee",
                       "head": HEAD, "stack": True, "rows": rows[:TOP_ROWS]})
        if len(rows) > TOP_ROWS:
            tables.append({"title": f"The other {len(rows) - TOP_ROWS}", "fold": True, "stack": True, "head": HEAD,
                           "rows": rows[TOP_ROWS:]})
    counts = []
    if len(priced):
        for sport, part in priced.groupby(priced["sport"].astype(str)):
            n = {m: int((part["market"] == m).sum()) for m in ("moneyline", "spread", "total")}
            counts.append([sport.upper(), str(part["game_id"].nunique()), str(n["moneyline"]), str(n["spread"]),
                           str(n["total"])])
    tables.append({"title": "Contracts this run, by sport", "fold": True,
                   "head": ["Sport", "Games", "Moneylines", "Spreads", "Totals"], "rows": counts})
    return {"title": "Polymarket US board", "tab": TAB, "tables": tables, "notes": [
        "Each game and market at the contract that pays best, whether or not it clears the bar; a contract the "
        "rule would not take says so. Expected value after the fee is fair ÷ (ask + fee) − 1.",
        "The fee is Polymarket US's taker fee, coefficient × price × (1 − price) per contract, the coefficient read "
        "from each market (0.0695 on every market on 23 October 2026). Makers pay none below $10 million a month.",
        "Quotes are read from Polymarket US's public API every run and kept in tracking/polymarket_quotes.csv."]}


def record_section(graded: pd.DataFrame) -> dict | None:
    if not len(graded):
        return None
    done = graded[graded["outcome"].isin(["win", "loss", "push", "settled"])]
    decided = done[done["outcome"].isin(["win", "loss"])]
    staked = float(pd.to_numeric(done["stake"], errors="coerce").sum()) if len(done) else 0.0
    pnl = float(done["pnl"].sum()) if len(done) else 0.0
    clv = pd.to_numeric(graded["clv"], errors="coerce")
    rows = [["Positions logged", str(len(graded))], ["Graded", str(len(done))],
            ["Won-lost-push", f"{int((decided['outcome'] == 'win').sum())}-{int((decided['outcome'] == 'loss').sum())}-"
                              f"{int((done['outcome'] == 'push').sum())}"],
            ["Return on the bankroll", f"{pnl:+.2%}" if len(done) else "–"],
            ["Return per dollar staked", f"{pnl / staked:+.1%}" if staked else "–"],
            ["Bought below the close", f"{int((clv > 0).sum())} of {int(clv.notna().sum())}" if clv.notna().any() else "–"],
            ["Mean value against the close", f"{100 * clv.mean():+.1f}¢" if clv.notna().any() else "–"]]
    tables = [{"title": "", "head": ["", ""], "rows": rows}]
    latest = graded[graded["outcome"] != "open"].sort_values("kickoff", ascending=False).head(10)
    if len(latest):
        tables.append({"title": "Latest graded", "fold": True, "stack": True, "head": ["Game", "Contract", "Result"],
                       "rows": [[x.label, [_contract(x), f"{_cents(x.ask)} · {_eastern(x.kickoff)}"],
                                 [f"{x.outcome} {x.pnl:+.2%}" if pd.notna(x.pnl) else x.outcome,
                                  f"closed {_cents(x.close)}" if pd.notna(x.close) else ""]]
                                for x in latest.itertuples()]})
    return {"title": "Polymarket US record (paper)", "tab": RECORD_TAB, "tables": tables, "notes": [
        "Each position is graded on the exchange's own settlement where it has one (a settle at the last fair "
        "price pays that price), else on the final score (a push refunded), and against the venue's close: the "
        "contract's last midpoint seen before the game started, less the ask it was bought at. Returns are shares "
        f"of the bankroll at the stakes shown. Nothing is read from fewer than {pos.MIN_GRADED} graded."]}


def sections(priced: pd.DataFrame, chosen: pd.DataFrame, graded: pd.DataFrame, now: datetime) -> list[dict]:
    out = [positions_section(chosen, graded, now), board_section(priced, now)]
    record = record_section(graded)
    return [*out, record] if record else out
