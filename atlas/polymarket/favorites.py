"""The favorites rule: paper positions on heavy favorites, with no projection in them.

    python -m atlas.polymarket.favorites        # the record so far, by threshold and phase

The idea under test is the one that looks obvious on the app: a side at 86%
is going to win, so buy it and collect the few cents. The price says
otherwise - 86% is the market's estimate of how often that side wins, and
the contract costs 86 cents plus the fee - so the question is only whether
the venue's favorites win *more* often than they cost, in play or before,
in any sport, at any threshold. Nothing but the record can answer that.

Every run takes a paper position on each moneyline the first time its ask
is at or above each of :data:`THRESHOLDS`, at that ask plus the taker fee,
and notes the phase (in play or pregame) and the minutes since kickoff. The
moneyline only: a deep spread or total at 90 cents is the ladder's edge,
not a favorite, and there are two thousand of them a day. And only a quoted
one: from 24 October 2026 the book must be inside :data:`MAX_SPREAD`, the
model rule's own bar, because the venue's tape showed that one crossing in
five was an ask with nothing near it on the other side - an empty book,
not a price - and that those carried most of the rule's losses
(`atlas/polymarket/backtest.py`, ``reports/favorites_backtest.md``).
Once the game is a few hours gone the venue's settlement grades it: paid in
full, paid nothing, or the last fair price where the rules settle so. The
record is kept in the clear (``tracking/favorites.csv``): it is a rule on
public prices, not Atlas's own positions. The summary is the win rate
against the break-even rate, which is the mean cost, and the profit per
dollar staked.
"""

from __future__ import annotations

import math
import os
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from atlas.polymarket import positions, pricing, source
from atlas.util import get_logger, offline

LOG = get_logger(__name__)

TABLE = "favorites"
#: The markets the rule is on: the favorite side of a game.
MARKETS = ("moneyline",)
#: A position is taken the first time a contract's ask reaches each of these.
THRESHOLDS = (0.80, 0.85, 0.90, 0.95)
#: Above this the venue's own price limit is near and the fee is nothing; nothing to learn.
CEILING = 0.98
#: The widest book a crossing is taken on, bid to ask: the model rule's bar. A wider ask has nothing behind it.
MAX_SPREAD = positions.MAX_SPREAD
#: Settlement is read once the game is this far gone, and at most this many markets a run.
GRADE_AFTER = timedelta(hours=4)
SETTLEMENT_READS = 40
COLUMNS = ["formed_at", "threshold", "phase", "minutes_in", "sport", "game_id", "event_id", "event_slug", "game_start",
           "label", "market", "side", "long", "line", "market_id", "market_slug", "token_id", "ask", "bid", "spread",
           "fee_rate", "fee", "cost", "payout", "won", "profit", "graded_at", "period", "clock", "late"]
#: The regulation periods a sport plays: in that period or past it (overtime), a position is late.
FINAL_PERIOD = {"nba": 4, "nfl": 4, "ncaaf": 4, "nhl": 3}
#: The variable that widens the live step from late positions (unset, ``late``) to every crossing (``any``).
#: Late is the default since 24 October 2026: on the venue's own tape (``reports/favorites_backtest.md``) a
#: favorite bought with more than fifteen minutes left loses, and one bought in the final minutes does not.
ORDER_PHASE = "LIVE_PHASE"
#: The variable that hands the rule to the always-on worker (``worker``; `atlas/polymarket/worker.py`): the
#: scheduled run then reads the record and takes, grades and orders nothing, so the two never write it at once.
TAKER = "FAVORITES_TAKER"
TAB = "Poly Snipe"
#: The one threshold whose crossings go to the live step (atlas/polymarket/orders.py): the user's "86%".
ORDER_THRESHOLD = 0.85
#: The owner page lists this many of the latest positions, one row per side.
LATEST = 30


def _truthy(value) -> bool:
    return str(value).strip().lower() in ("true", "1", "1.0", "yes")


def phase() -> str:
    """Which crossings the live step takes: ``late`` (the default) or ``any``."""
    return "any" if os.environ.get(ORDER_PHASE, "").strip().lower() == "any" else "late"


def worker_owns() -> bool:
    """Whether the always-on worker takes the positions, and the scheduled run only reads them."""
    return os.environ.get(TAKER, "").strip().lower() == "worker"


def candidates(quotes: pd.DataFrame, now: datetime) -> pd.DataFrame:
    """The contracts a position could be taken on this run: accepting orders, with an ask on them below the
    ceiling and a bid within :data:`MAX_SPREAD` of it; each with its phase and the minutes since kickoff."""
    if quotes is None or quotes.empty:
        return pd.DataFrame(columns=[*source.QUOTE_COLUMNS, "phase", "minutes_in"])
    q = quotes.copy()
    ask = pd.to_numeric(q["ask"], errors="coerce")
    spread = pd.to_numeric(q["spread"], errors="coerce")
    start = pd.to_datetime(q["game_start"], utc=True, errors="coerce")
    keep = q["accepting"].map(_truthy) & q["market"].astype(str).isin(MARKETS) & ask.notna() & (ask > 0) \
        & (ask <= CEILING) & (spread <= MAX_SPREAD) & start.notna()
    q = q[keep].copy()
    start = start[keep]
    minutes = (pd.Timestamp(now) - start).dt.total_seconds() / 60.0
    q["minutes_in"] = minutes.round(1)
    q["phase"] = np.where(minutes >= 0, "in_play", "pregame")
    return q


def _state(games: pd.DataFrame | None) -> dict[str, tuple[float, str]]:
    """Each game's (period, clock) as the scoreboard last had it, by game id."""
    if games is None or games.empty or "period" not in games:
        return {}
    out = {}
    for g, p, c in zip(games["game_id"], pd.to_numeric(games["period"], errors="coerce"), games["clock"], strict=True):
        out[str(g)] = (float(p) if pd.notna(p) else float("nan"), str(c) if pd.notna(c) and c is not None else "")
    return out


def is_late(sport, period, phase: str) -> bool:
    """In play, and in the sport's final regulation period or past it."""
    final = FINAL_PERIOD.get(str(sport).lower())
    return bool(phase == "in_play" and final and pd.notna(period) and float(period) >= final)


def take(record: pd.DataFrame, quotes: pd.DataFrame, now: datetime, games: pd.DataFrame | None = None,
         venue: dict[str, tuple[float, str]] | None = None) -> tuple[pd.DataFrame, int]:
    """The record with a position added for each contract at each threshold its ask reaches for the first
    time, at that ask plus the fee, and where the game stood: ``venue`` is (period, clock) by the venue's
    event id as its own feed has it (the worker's, read seconds ago), ``games`` the scoreboard's rows by
    Atlas's game id (the scheduled run's, up to a poll old); the venue's is preferred where both have the
    game. A position is never revised."""
    record = record.reindex(columns=COLUMNS) if len(record) else pd.DataFrame(columns=COLUMNS)
    c = candidates(quotes, now)
    if c.empty:
        return record, 0
    state = _state(games)
    venue = venue or {}
    have = set(zip(record["token_id"].astype(str), pd.to_numeric(record["threshold"], errors="coerce").round(2),
                   strict=True)) if len(record) else set()
    stamp = pd.Timestamp(now).tz_convert("UTC").replace(microsecond=0).isoformat() if pd.Timestamp(now).tzinfo \
        else pd.Timestamp(now).tz_localize("UTC").isoformat()
    rows = []
    for x in c.itertuples(index=False):
        ask = float(x.ask)
        fee_rate = source._num(x.fee_rate)
        fee = pricing.fee(ask, fee_rate)
        period, clock = venue.get(str(x.event_id)) or state.get(str(x.game_id), (float("nan"), ""))
        for t in THRESHOLDS:
            if ask < t or (str(x.token_id), round(t, 2)) in have:
                continue
            rows.append({
                "period": period, "clock": clock, "late": is_late(x.sport, period, x.phase),
                "formed_at": stamp, "threshold": t, "phase": x.phase, "minutes_in": float(x.minutes_in),
                "sport": x.sport, "game_id": x.game_id, "event_id": x.event_id, "event_slug": x.event_slug,
                "game_start": x.game_start, "label": f"{x.away} @ {x.home}", "market": x.market, "side": x.side,
                "long": bool(_truthy(x.long)), "line": x.line, "market_id": x.market_id, "market_slug": x.market_slug,
                "token_id": x.token_id, "ask": ask, "bid": source._num(x.bid), "spread": source._num(x.spread),
                "fee_rate": fee_rate, "fee": fee, "cost": ask + (fee if math.isfinite(fee) else 0.0),
                "payout": float("nan"), "won": float("nan"), "profit": float("nan"), "graded_at": None})
    if not rows:
        return record, 0
    new = pd.DataFrame(rows, columns=COLUMNS)
    out = pd.concat([record, new], ignore_index=True) if len(record) else new
    return out, len(new)


def grade(record: pd.DataFrame, now: datetime, fetch=None, limit: int = SETTLEMENT_READS) -> pd.DataFrame:
    """The record with the venue's settlement applied to positions whose game is :data:`GRADE_AFTER` gone:
    the payout per contract, whether it won, and the profit against the cost. One read per market, at most
    ``limit`` a run; a market not yet settled stays pending."""
    if record.empty or offline():
        return record
    out = record.copy()
    payout = pd.to_numeric(out["payout"], errors="coerce")
    start = pd.to_datetime(out["game_start"], utc=True, errors="coerce")
    pending = out[payout.isna() & (start <= pd.Timestamp(now) - GRADE_AFTER)]
    if pending.empty:
        return out
    fetch = fetch or source.settlement
    stamp = pd.Timestamp(now).tz_convert("UTC").replace(microsecond=0).isoformat()
    cache: dict[str, float] = {}
    for slug in pending["market_slug"].astype(str).drop_duplicates():
        if len(cache) >= limit:
            break
        try:
            cache[slug] = float(fetch(slug))
        except Exception as error:  # noqa: BLE001 - the type only
            LOG.info("favorites: no settlement for a market (%s)", type(error).__name__)
            cache[slug] = float("nan")
    graded = 0
    for i, x in pending.iterrows():
        px = cache.get(str(x["market_slug"]), float("nan"))
        if not math.isfinite(px):
            continue
        paid = px if _truthy(x["long"]) else 1.0 - px
        out.loc[i, "payout"] = paid
        out.loc[i, "won"] = 1.0 if paid >= 0.999 else 0.0
        out.loc[i, "profit"] = paid - float(x["cost"])
        out.loc[i, "graded_at"] = stamp
        graded += 1
    if graded:
        LOG.info("favorites: %d positions graded (%d markets read)", graded, len(cache))
    return out


def stage(record: pd.DataFrame) -> pd.Series:
    """pregame, in play early, or in play late, per position."""
    late = record["late"].map(_truthy) if "late" in record else pd.Series(False, index=record.index)
    phase = record["phase"].astype(str)
    return pd.Series(np.where(phase == "pregame", "pregame", np.where(late, "in play late", "in play early")),
                     index=record.index)


def summary(record: pd.DataFrame, by=("phase", "threshold")) -> pd.DataFrame:
    """Per group: positions taken and graded, the win rate, the break-even rate (the mean cost), and the
    profit per dollar staked; the rate observed less the one needed, with its standard error."""
    cols = [*by, "taken", "graded", "win_rate", "break_even", "edge", "se", "profit_per_dollar"]
    if record is None or record.empty:
        return pd.DataFrame(columns=cols)
    r = record.copy()
    if "stage" in by:
        r["stage"] = stage(r)
    r["won"] = pd.to_numeric(r["won"], errors="coerce")
    r["cost"] = pd.to_numeric(r["cost"], errors="coerce")
    r["profit"] = pd.to_numeric(r["profit"], errors="coerce")
    rows = []
    for key, g in r.groupby(list(by), sort=True):
        key = key if isinstance(key, tuple) else (key,)
        done = g[g["won"].notna()]
        n = len(done)
        win = float(done["won"].mean()) if n else float("nan")
        cost = float(done["cost"].mean()) if n else float("nan")
        rows.append({**dict(zip(by, key, strict=True)), "taken": int(len(g)), "graded": n, "win_rate": win,
                     "break_even": cost, "edge": win - cost if n else float("nan"),
                     "se": math.sqrt(win * (1 - win) / n) if n and 0 < win < 1 else float("nan"),
                     "profit_per_dollar": float(done["profit"].sum() / done["cost"].sum()) if n else float("nan")})
    return pd.DataFrame(rows, columns=cols)


def _table(s: pd.DataFrame, head: list[str]) -> dict:
    rows = []
    for x in s.itertuples(index=False):
        keys = [str(getattr(x, c)).replace("_", " ") if c != "threshold" else f"{float(getattr(x, c)):.0%}"
                for c in head]
        rows.append([*keys, f"{x.taken} / {x.graded}",
                     f"{x.win_rate:.1%}" if x.graded else "", f"{x.break_even:.1%}" if x.graded else "",
                     (f"{100 * x.edge:+.1f} ± {100 * x.se:.1f}" if math.isfinite(x.se) else f"{100 * x.edge:+.1f}")
                     if x.graded else "", f"{x.profit_per_dollar:+.1%}" if x.graded else ""])
    return {"title": "", "head": [*[h.title() for h in head], "Taken / graded", "Win rate", "Break-even",
                                  "Edge (pts)", "Profit per $"], "stack": True, "rows": rows}


def latest(record: pd.DataFrame, n: int = LATEST) -> dict | None:
    """The newest positions, one row per side at the lowest threshold it reached: what the rule took and
    how each stands (pending, won, lost, or settled at a price)."""
    if record is None or record.empty:
        return None
    r = record.sort_values(["formed_at", "threshold"], kind="stable")
    r = r.drop_duplicates("token_id", keep="first").tail(n).iloc[::-1]
    rows = []
    for x in r.itertuples():
        won = pd.to_numeric(pd.Series([x.won]), errors="coerce").iloc[0]
        payout = pd.to_numeric(pd.Series([x.payout]), errors="coerce").iloc[0]
        if pd.isna(won):
            state = "pending"
        elif won >= 1.0:
            state = "won"
        elif pd.notna(payout) and payout > 0.0:
            state = f"settled {payout:.2f}"
        else:
            state = "lost"
        when = pd.to_datetime(x.formed_at, utc=True, errors="coerce")
        minutes = float(x.minutes_in) if pd.notna(x.minutes_in) else float("nan")
        period = pd.to_numeric(pd.Series([x.period]), errors="coerce").iloc[0] if hasattr(x, "period") else float("nan")
        where = f"P{int(period)} {x.clock}".strip() if pd.notna(period) and period > 0 else ""
        phase = ((f"in play, {where}" if where else f"in play, {minutes:.0f}'") if minutes >= 0
                 else f"pregame, {-minutes / 60:.1f}h out") if math.isfinite(minutes) else str(x.phase).replace("_", " ")
        rows.append([[str(x.label), str(x.sport).upper()], str(x.side), f"{float(x.ask):.2f}", phase,
                     when.tz_convert("America/New_York").strftime("%a %H:%M") if pd.notna(when) else "", state])
    return {"title": f"Latest positions ({len(rows)} sides)", "head": ["Game", "Side", "Ask", "Phase", "Taken", "Result"],
            "stack": True, "rows": rows}


def section(record: pd.DataFrame, now: datetime) -> dict:
    """The owner page's section: the rule's record by phase and threshold, by sport at the lowest, and the
    latest positions taken."""
    s = summary(record)
    tables = [_table(s, ["phase", "threshold"])] if len(s) else []
    if len(tables):
        tables[0]["title"] = "By phase and threshold"
    if len(record):
        by_stage = summary(record, by=("stage", "threshold"))
        if len(by_stage):
            t = _table(by_stage, ["stage", "threshold"])
            t["title"] = "By stage of the game: before it, in play before the final period, in play in it or past it"
            tables.append(t)
        low = record[pd.to_numeric(record["threshold"], errors="coerce").round(2) == round(THRESHOLDS[0], 2)]
        by_sport = summary(low, by=("sport", "phase"))
        if len(by_sport):
            t = _table(by_sport, ["sport", "phase"])
            t["title"] = f"By sport, at the {THRESHOLDS[0]:.0%} threshold"
            tables.append(t)
    new = latest(record)
    if new:
        tables.append(new)
    n = int(len(record)) if record is not None else 0
    graded = int(pd.to_numeric(record["won"], errors="coerce").notna().sum()) if n else 0
    return {"title": f"Poly Snipe: the favorites rule ({graded} of {n} positions graded)", "tab": TAB,
            "tables": tables, "notes": [
        "A paper position on every moneyline the first time its ask reaches each threshold, at that ask plus "
        "the fee, in play or before the game; graded by the venue's settlement. No projection is in it: the "
        "question is whether the venue's favorites win more often than they cost.",
        f"From 24 October 2026 a crossing is taken only on a book quoted inside {MAX_SPREAD * 100:.0f}¢, bid to "
        "ask: on the venue's own tape (reports/favorites_backtest.md) one crossing in five was an ask with "
        "nothing near it, and those carried most of the losses. Earlier positions carry their spread, so the "
        "record can be read either way.",
        "Edge is the win rate less the break-even rate in points, with one standard error; profit per dollar "
        "is what a dollar staked across the positions returned. Positive and several errors wide, over "
        "hundreds of positions, before it means anything.",
        "Late is the sport's final regulation period or past it, as the game stood when the position was taken "
        "(the venue's own clock from the worker, the scoreboard's up to a quarter hour old from a scheduled "
        f"run). The live step takes {'late positions only' if phase() == 'late' else 'every crossing'}"
        f"{'' if phase() == 'late' else ' (LIVE_PHASE=any)'}."]}


def text(record: pd.DataFrame) -> str:
    """The public report's paragraph and table."""
    s = summary(record)
    if s.empty:
        return "No favorites positions yet."
    t = s.copy()
    t["threshold"] = t["threshold"].map(lambda v: f"{float(v):.0%}")
    t["phase"] = t["phase"].str.replace("_", " ")
    for c in ("win_rate", "break_even", "profit_per_dollar"):
        t[c] = t[c].map(lambda v: f"{v:.1%}" if pd.notna(v) else "")
    t["edge"] = [f"{100 * e:+.1f} ± {100 * se:.1f}" if pd.notna(se) else (f"{100 * e:+.1f}" if pd.notna(e) else "")
                 for e, se in zip(t["edge"], t["se"], strict=True)]
    t = t[["phase", "threshold", "taken", "graded", "win_rate", "break_even", "edge", "profit_per_dollar"]]
    t.columns = ["Phase", "Threshold", "Taken", "Graded", "Win rate", "Break-even", "Edge (pts)", "Profit per $"]
    head = "| " + " | ".join(t.columns) + " |\n|" + "|".join("---" for _ in t.columns) + "|"
    body = "\n".join("| " + " | ".join(str(v) for v in r) + " |" for r in t.itertuples(index=False))
    return head + "\n" + body


def as_positions(rows: pd.DataFrame) -> pd.DataFrame:
    """The rule's positions in the shape the live step takes (the positions record's columns): one order's
    worth each, the stake the whole bankroll so the per-order cap decides the size."""
    from atlas.polymarket import positions

    if rows is None or rows.empty:
        return pd.DataFrame(columns=positions.COLUMNS)
    out = pd.DataFrame({
        "position_id": [f"fav:{t}:{float(th):.2f}" for t, th in zip(rows["token_id"], rows["threshold"], strict=True)],
        "formed_at": rows["formed_at"], "day": [positions.day_of(t) for t in rows["formed_at"]],
        "year": [positions.iso_week(t)[0] for t in rows["formed_at"]],
        "week": [positions.iso_week(t)[1] for t in rows["formed_at"]],
        "game_id": rows["game_id"], "sport": rows["sport"], "kickoff": rows["game_start"], "label": rows["label"],
        "market": rows["market"], "side": rows["side"], "long": rows["long"], "line": rows["line"],
        "token_id": rows["token_id"], "market_id": rows["market_id"], "market_slug": rows["market_slug"],
        "event_slug": rows["event_slug"], "ask": rows["ask"], "fee_rate": rows["fee_rate"], "fee": rows["fee"],
        "cost": rows["cost"], "stake": 1.0, "spread": rows["spread"]})
    return out.reindex(columns=positions.COLUMNS)


def order(new: pd.DataFrame, passphrase: str, now: datetime) -> None:
    """The positions just taken to the live step (`atlas/polymarket/orders.py`), which does nothing unless
    its secrets say so: those at :data:`ORDER_THRESHOLD`, and late ones only unless :func:`phase` is any."""
    from atlas.polymarket import orders

    if new is None or new.empty or orders.mode() == "off":
        return
    new = new[pd.to_numeric(new["threshold"], errors="coerce").round(2) == round(ORDER_THRESHOLD, 2)]
    if phase() == "late":
        new = new[new["late"].map(_truthy)]
    if new.empty:
        return
    try:
        orders.place(as_positions(new), passphrase, now, rule="favorites")
    except Exception as error:  # noqa: BLE001 - the type only
        LOG.error("favorites: live orders not placed: %s", type(error).__name__)


def refresh(store, quotes: pd.DataFrame, now: datetime, passphrase: str | None = None) -> tuple[pd.DataFrame, dict]:
    """The rule's step of every scheduled run: take, grade, write; and, with the owner key, the new positions
    to the live step. When the worker owns the rule (:func:`worker_owns`) the run reads the record and
    writes nothing. Returns (the record, the owner page's section). Never raises."""
    try:
        record = store.read(TABLE)
        if worker_owns():
            out = section(record, now)
            out["notes"].insert(0, "The always-on worker takes, grades and orders the positions "
                                   "(atlas/polymarket/worker.py); this run reads the record it pushed.")
            return record, out
        before = len(record)
        record, added = take(record, quotes, now, store.read("games"))
        record = grade(record, now)
        if added or len(record):
            store.write(TABLE, record)
        if added:
            LOG.info("favorites: %d positions taken (%d in all)", added, len(record))
            if passphrase:
                order(record.iloc[before:], passphrase, now)
        return record, section(record, now)
    except Exception as error:  # noqa: BLE001 - the type only
        LOG.error("favorites not refreshed: %s", type(error).__name__)
        return pd.DataFrame(columns=COLUMNS), {"title": "Poly Snipe: the favorites rule", "tab": TAB, "tables": [],
                                               "notes": [f"This run could not keep the rule ({type(error).__name__})."]}


def main() -> None:
    from atlas.live.store import Store

    record = Store.open().read(TABLE)
    print(text(record))
    by_sport = summary(record, by=("sport", "phase", "threshold"))
    if len(by_sport):
        print()
        print(by_sport.to_string(index=False))


if __name__ == "__main__":
    main()
