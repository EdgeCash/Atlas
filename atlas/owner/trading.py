"""Sports trading: Kalshi and Polymarket contracts, priced against the sportsbook consensus after fees.

Paper only: nothing here buys anything. The exchanges' prices arrive with
every poll through BettingPros (`atlas/sources/bettingpros.py`), the same
feed and the same sealed record as the board (`atlas/owner/board.py`), so no
exchange API is called and no key is needed.

A binary contract costs its price in dollars and pays one dollar if it wins.
So, for every side an exchange quotes on the upcoming games (totals,
spreads, and the game-winner contract, a moneyline):

* **fair probability**: the sportsbook consensus with its margin removed,
  read at the contract's line (`atlas/live/probability.py`); on totals,
  Atlas's calibrated probability, the measure the board uses;
* **price**: the quote as a contract price (its implied probability), plus
  the venue's taker fee, ``rate x price x (1 - price)`` per contract;
* **expected value after fees**: fair probability / (price + fee) - 1, and
  the Kelly fraction ``(p - cost) / (1 - cost)``.

The day's **positions** are the tradeable venues' contracts at +2% or more
after fees, from games on the Eastern day (or the next day with games), one
per game at the venue and side that pays best, sized at a quarter of Kelly,
at most 2% of the bankroll each and 10% in all. They are logged once into a
sealed record (``tracking/owner_trading/``) at the first run from 10:00 ET
on that day, like the parlays (`atlas/owner/parlays.py`), and graded on the
final score and against the consensus close in win probability.

What is assumed and has to be confirmed before real money: that BettingPros
shows each venue's price to buy; the fee rates (Kalshi's is its published
7% formula, rounded up to the cent per order on the exchange and not here;
Polymarket's 5% is the rate the Velocity repository modelled); and depth,
which the quotes do not carry, so a price may not fill at size.
"""

from __future__ import annotations

import json
import math
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from atlas.live import probability
from atlas.owner import paper, parlays, sealed
from atlas.sources import bettingpros as bp
from atlas.util import get_logger

LOG = get_logger(__name__)


@dataclass(frozen=True)
class Venue:
    name: str
    fee_rate: float                 # taker fee per contract: rate x price x (1 - price)
    tradeable: bool                 # positions are taken here; otherwise shown for reference


#: BettingPros book ids. The global Polymarket is close-only for US accounts: a reference price, never a position.
VENUES = {
    68: Venue("Kalshi", 0.07, True),
    75: Venue("Polymarket US", 0.05, True),
    73: Venue("Polymarket", 0.05, False),
}
#: Raised from +1% on 26 September 2026, after the first day filled all ten positions: a +1% edge read against a
#: stale quote or the best of three venues is within the noise. Positions logged that day were at +1%.
MIN_EV = 0.02
MAX_POSITIONS = 10
KELLY_FRACTION = 0.25
MAX_STAKE = 0.02
DAILY_CAP = 0.10
BOARD_ROWS = 30
MIN_GRADED = 50
NAMESPACE = uuid.UUID("5b8e2c1a-7d3f-4e9a-8c6b-1f2a3d4e5c60")

QUOTE_COLUMNS = ["game_id", "event_id", "sport", "season", "week", "kickoff", "market", "side", "book_id", "line",
                 "cost", "updated", "p_fair", "p_atlas"]
COLUMNS = ["position_id", "formed_at", "day", "season", "week", "game_id", "sport", "kickoff", "home_abbr",
           "visitor_abbr", "label", "book_id", "market", "side", "line", "cost", "ask", "fee", "price", "p", "p_fair",
           "ev", "stake"]


def path() -> Path:
    from atlas.live.store import tracking_dir

    return tracking_dir() / "owner_trading"


def fee(ask: float, rate: float) -> float:
    """The taker fee per one-dollar contract bought at ``ask``."""
    return rate * ask * (1.0 - ask) if 0.0 < ask < 1.0 else float("nan")


# ---------------------------------------------------------------------------
# Quotes
# ---------------------------------------------------------------------------


def moneyline_sides(part: pd.DataFrame, home_abbr: str | None, visitor_abbr: str | None) -> pd.Series:
    """``home``/``away`` for each moneyline row: by the participant's abbreviation where it is the event's,
    else, where a book quotes both sides and one is known, the other is its complement (books spell the same
    team several ways). Unknown otherwise."""
    sides = pd.Series([None] * len(part), index=part.index, dtype=object)
    sides[part["participant"] == home_abbr] = "home"
    sides[part["participant"] == visitor_abbr] = "away"
    for _, grp in part.groupby("book_id"):
        if len(grp) != 2:
            continue
        known = sides.loc[grp.index].dropna()
        if len(known) == 1:
            other = grp.index.difference(known.index)
            sides.loc[other] = "away" if known.iloc[0] == "home" else "home"
    return sides


def moneyline_quotes(lines: pd.DataFrame, events: pd.DataFrame, books) -> pd.DataFrame:
    """Every quote from ``books`` on the game-winner market, with the consensus's vig-free probability."""
    if lines.empty or "market" not in lines:
        return pd.DataFrame(columns=QUOTE_COLUMNS)
    ml = lines[lines["market"] == "moneyline"]
    if ml.empty:
        return pd.DataFrame(columns=QUOTE_COLUMNS)
    info_by = events.assign(game_id=events["game_id"].astype(str)).drop_duplicates("game_id").set_index("game_id") \
        if not events.empty else pd.DataFrame()
    rows = []
    for game_id, part in ml.assign(game_id=ml["game_id"].astype(str)).groupby("game_id"):
        info = info_by.loc[game_id] if game_id in info_by.index else None
        home = str(info["home_abbr"]) if info is not None else None
        visitor = str(info["visitor_abbr"]) if info is not None else None
        # Sides are read among live quotes only: an off or filled row is not a side a book is quoting.
        part = part[_quotable(part, [*books, bp.CONSENSUS])]
        part = part.assign(side=moneyline_sides(part, home, visitor))
        cons = part[part["book_id"] == bp.CONSENSUS]
        h, a = cons[cons["side"] == "home"], cons[cons["side"] == "away"]
        if h.empty or a.empty:
            continue
        p_home = probability.no_vig(float(h["cost"].iloc[0]), float(a["cost"].iloc[0]))
        if not math.isfinite(p_home):
            continue
        take = part[part["book_id"].isin([int(b) for b in books]) & part["side"].notna()]
        for r in take.itertuples():
            rows.append({"game_id": game_id, "event_id": r.event_id, "sport": r.sport,
                         "season": info["season"] if info is not None else None,
                         "week": info["week"] if info is not None else None,
                         "kickoff": info["scheduled"] if info is not None else None, "market": "moneyline",
                         "side": r.side, "book_id": int(r.book_id), "line": 0.0, "cost": float(r.cost),
                         "updated": r.updated, "p_fair": p_home if r.side == "home" else 1.0 - p_home,
                         "p_atlas": float("nan")})
    return pd.DataFrame(rows, columns=QUOTE_COLUMNS)


def _quotable(part: pd.DataFrame, books) -> pd.Series:
    from atlas.owner import board

    return board.quotable(part, books)


def quotes(lines: pd.DataFrame, events: pd.DataFrame, projections: pd.DataFrame, shapes: dict, now: datetime,
           calibration: pd.DataFrame | None = None) -> pd.DataFrame:
    """Every exchange quote on the upcoming games' totals, spreads and moneylines, with its fair probability."""
    from atlas.owner import board

    books = list(VENUES)
    legs = board.legs(lines, events, projections, shapes, now, calibration, books=books)
    parts = [legs.reindex(columns=QUOTE_COLUMNS), moneyline_quotes(lines, events, books)]
    parts = [p for p in parts if not p.empty]
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=QUOTE_COLUMNS)


def priced(q: pd.DataFrame) -> pd.DataFrame:
    """Each quote as a contract: its price, the fee, the cost, the probability used, EV after fees and Kelly."""
    if q.empty:
        return q.assign(**{c: pd.Series(dtype=float) for c in ("ask", "fee", "price", "p", "ev", "kelly")},
                        venue=pd.Series(dtype=str), tradeable=pd.Series(dtype=bool))
    t = q.copy()
    t["venue"] = t["book_id"].map(lambda b: VENUES[int(b)].name)
    t["tradeable"] = t["book_id"].map(lambda b: VENUES[int(b)].tradeable)
    rate = t["book_id"].map(lambda b: VENUES[int(b)].fee_rate)
    t["ask"] = t["cost"].map(lambda c: probability.implied(float(c)))
    t["fee"] = [fee(a, r) for a, r in zip(t["ask"], rate, strict=True)]
    t["price"] = t["ask"] + t["fee"]
    total = t["market"] == "total"
    t["p"] = np.where(total & t["p_atlas"].notna(), t["p_atlas"], t["p_fair"]).astype(float)
    t = t[(t["ask"] > 0) & (t["ask"] < 1) & (t["price"] < 1)].copy()
    t["ev"] = t["p"] / t["price"] - 1.0
    t["kelly"] = ((t["p"] - t["price"]) / (1.0 - t["price"])).clip(lower=0.0)
    return t.reset_index(drop=True)


# ---------------------------------------------------------------------------
# The day's positions
# ---------------------------------------------------------------------------


def label_of(names: dict, game_id) -> str:
    return names.get(str(game_id), str(game_id))


def contract(market: str, side: str, line: float, label: str) -> str:
    """"Georgia to win", "Georgia -3.5", "Over 44.5"."""
    away, home = label.split(" @ ", 1) if " @ " in label else ("Away", "Home")
    team = home if side == "home" else away
    if market == "moneyline":
        return f"{team} to win"
    if market == "spread":
        return f"{team} {float(line):+g}"
    return f"{side.capitalize()} {float(line):g}"


def positions(p: pd.DataFrame, events: pd.DataFrame, names: dict, now: datetime) -> pd.DataFrame:
    """The day's positions: tradeable venues, +2% or more after fees, one per game at the side and venue that
    pays best, at most :data:`MAX_POSITIONS`, sized at a quarter of Kelly under the caps."""
    if p.empty:
        return pd.DataFrame(columns=[*COLUMNS, "venue", "oldest"])
    t = p[p["tradeable"].astype(bool)].copy()
    t["kickoff"] = pd.to_datetime(t["kickoff"], utc=True, errors="coerce")
    t = t[(t["kickoff"] > pd.Timestamp(now)) & (t["ev"] >= MIN_EV) & t["p"].between(0.03, 0.97)]
    if t.empty:
        return pd.DataFrame(columns=[*COLUMNS, "venue", "oldest"])
    t["day"] = t["kickoff"].map(parlays.day_of)
    today = parlays.day_of(now)
    day = today if (t["day"] == today).any() else t["day"].min()
    # One position a game: a moneyline and a spread on the same team are nearly one bet.
    t = t[t["day"] == day].sort_values("ev", ascending=False).drop_duplicates(["game_id"], keep="first")
    t = t.head(MAX_POSITIONS).copy()
    stake = np.minimum(KELLY_FRACTION * t["kelly"], MAX_STAKE)
    if stake.sum() > DAILY_CAP:
        stake = stake * DAILY_CAP / stake.sum()
    t["stake"] = stake.round(4)
    abbr = events.assign(game_id=events["game_id"].astype(str)).drop_duplicates("game_id").set_index("game_id") \
        if not events.empty else pd.DataFrame(columns=["home_abbr", "visitor_abbr"])
    t["home_abbr"] = t["game_id"].astype(str).map(abbr["home_abbr"]) if len(abbr) else None
    t["visitor_abbr"] = t["game_id"].astype(str).map(abbr["visitor_abbr"]) if len(abbr) else None
    t["label"] = [label_of(names, g) for g in t["game_id"]]
    stamp = pd.Timestamp(now).strftime("%Y-%m-%dT%H:%M:%SZ")
    t["formed_at"] = stamp
    t["position_id"] = [str(uuid.uuid5(NAMESPACE, f"{d}|{int(b)}|{g}|{m}|{s}"))
                        for d, b, g, m, s in zip(t["day"], t["book_id"], t["game_id"], t["market"], t["side"],
                                                 strict=True)]
    t["kickoff"] = t["kickoff"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    for c in ("ask", "fee", "price", "p", "p_fair", "ev"):
        t[c] = t[c].astype(float).round(4)
    t["oldest"] = [_age(u, now) for u in t["updated"]]
    return t.reset_index(drop=True)


def _age(updated, now: datetime) -> float:
    if updated is None:
        return float("nan")
    ts = pd.to_datetime(updated, utc=True, errors="coerce")
    return float("nan") if pd.isna(ts) else (pd.Timestamp(now) - ts).total_seconds() / 60.0


# ---------------------------------------------------------------------------
# The record
# ---------------------------------------------------------------------------


def load(passphrase: str, where: Path | None = None) -> pd.DataFrame:
    rows = sealed.load(where or path(), passphrase)
    return pd.DataFrame(rows, columns=COLUMNS) if rows else pd.DataFrame(columns=COLUMNS)


def log(record: pd.DataFrame, chosen: pd.DataFrame) -> tuple[pd.DataFrame, set]:
    """Add the positions not yet logged, at the prices shown; a logged position is never revised."""
    if chosen.empty:
        return record, set()
    fresh = chosen.reindex(columns=COLUMNS)
    new = fresh[~fresh["position_id"].isin(set(record["position_id"]))] if len(record) else fresh
    if new.empty:
        return record, set()
    weeks = {(int(a), int(b)) for a, b in new[["season", "week"]].dropna().drop_duplicates().itertuples(index=False)}
    parts = [record.reindex(columns=COLUMNS), new] if len(record) else [new]
    return pd.concat(parts, ignore_index=True).reindex(columns=COLUMNS), weeks


def seal(record: pd.DataFrame, passphrase: str, weeks: set, where: Path | None = None) -> list[Path]:
    where = where or path()
    out = []
    for season, week in sorted(weeks):
        part = record[(pd.to_numeric(record["season"]) == season) & (pd.to_numeric(record["week"]) == week)]
        rows = json.loads(part.reindex(columns=COLUMNS).to_json(orient="records"))
        out.append(sealed.seal(rows, passphrase, sealed.week_file(where, season, week),
                               names=[r.get("label") for r in rows]))
    return out


def outcome(market: str, side: str, line: float, margin: float, total: float) -> str:
    """win, loss, push, or open, from the final score (``margin`` is home minus away)."""
    if not (math.isfinite(margin) and math.isfinite(total)):
        return "open"
    if market == "total":
        edge = (total - line) * (1.0 if side == "over" else -1.0)
    else:
        own = margin if side == "home" else -margin
        edge = own + (line if market == "spread" else 0.0)
    return "win" if edge > 0 else ("loss" if edge < 0 else "push")


def close_prob(pos, closes: pd.DataFrame, shapes: dict) -> float:
    """The consensus close's vig-free probability for the position's side at its line."""
    from atlas.owner import board

    c = closes[(closes["book_id"] == bp.CONSENSUS) & (closes["game_id"].astype(str) == str(pos.game_id))
               & (closes["market"] == pos.market)]
    if c.empty:
        return float("nan")
    if pos.market == "moneyline":
        sides = moneyline_sides(c, pos.home_abbr, pos.visitor_abbr)
        h, a = c[sides == "home"], c[sides == "away"]
        if h.empty or a.empty:
            return float("nan")
        p_home = probability.no_vig(float(h["cost"].iloc[0]), float(a["cost"].iloc[0]))
        return p_home if pos.side == "home" else 1.0 - p_home
    cons = board._consensus(c, pos.market, pos.home_abbr, pos.visitor_abbr)
    if cons is None:
        return float("nan")
    shape = shapes.get((pos.sport, "total" if pos.market == "total" else "margin")) \
        or probability.default_shape(pos.sport, "total" if pos.market == "total" else "margin")
    first = pos.side in ("over", "home")
    close_first, _ = probability.quoted_first(cons["first_cost"], cons["second_cost"])
    cons_market_line = cons["line"] if pos.market == "total" else -cons["line"]
    line = float(pos.line)
    taken = line if pos.market == "total" else (-line if first else line)
    return probability.side_prob(probability.at_line(shape, cons_market_line, close_first, taken),
                                 "over" if first else "under")


def grade(record: pd.DataFrame, finals: pd.DataFrame, closes: pd.DataFrame, shapes: dict) -> pd.DataFrame:
    """Each position with its outcome, its return per dollar staked (a winning contract pays one dollar on
    its cost; a push is refunded), its return on the bankroll, and its CLV against the consensus close."""
    if record.empty:
        return record.assign(outcome=pd.Series(dtype=str), profit=pd.Series(dtype=float),
                             pnl=pd.Series(dtype=float), clv_prob=pd.Series(dtype=float))
    r = record.assign(game_id=record["game_id"].astype(str)).merge(
        finals.assign(game_id=finals["game_id"].astype(str)), on="game_id", how="left")
    r["outcome"] = [outcome(m, s, float(ln), float(mg), float(tt)) for m, s, ln, mg, tt in
                    zip(r["market"], r["side"], r["line"], r["final_margin"], r["final_total"], strict=True)]
    price = pd.to_numeric(r["price"], errors="coerce")
    r["profit"] = np.select([r["outcome"] == "win", r["outcome"] == "loss"], [(1.0 - price) / price, -1.0], 0.0)
    r.loc[r["outcome"] == "open", "profit"] = np.nan
    r["pnl"] = pd.to_numeric(r["stake"], errors="coerce") * r["profit"]
    r["clv_prob"] = np.nan
    if not closes.empty:
        r["clv_prob"] = [close_prob(x, closes, shapes) - float(x.p_fair) for x in r.itertuples()]
    return r


# ---------------------------------------------------------------------------
# The owner page's view
# ---------------------------------------------------------------------------


def _cents(x: float) -> str:
    return f"{100 * x:.0f}¢" if math.isfinite(x) else "–"


def _buy(x, now: datetime) -> str:
    """"52¢ + 1.7¢ fee", marked when the quote is older than the parlays' stale mark."""
    age = _age(getattr(x, "updated", None), now)
    stale = f" (quote {age:.0f} min old)" if math.isfinite(age) and age > parlays.STALE_MINUTES else ""
    return f"{_cents(x.ask)} + {100 * x.fee:.1f}¢ fee{stale}"


def section(p: pd.DataFrame, chosen: pd.DataFrame, graded: pd.DataFrame, names: dict, now: datetime) -> list[dict]:
    from atlas.owner.board import _eastern

    logged = set(graded["position_id"]) if len(graded) else set()
    rows = [[f"{x.label} · {_eastern(x.kickoff)}", contract(x.market, x.side, x.line, x.label), x.venue, _buy(x, now),
             paper._pct(x.p), f"{x.ev:+.1%}", f"{x.stake:.1%} of bankroll" + (" · logged" if x.position_id in logged else "")]
            for x in chosen.itertuples()]
    day = pd.Timestamp(chosen["day"].iloc[0]).strftime("%a %b %-d") if len(chosen) else \
        pd.Timestamp(parlays.day_of(now)).strftime("%a %b %-d")
    tables = [{"title": f"Positions for {day}: {len(rows)}",
               "head": ["Game", "Contract", "Venue", "Buy at", "Fair", "EV after fees", "Stake"],
               "rows": rows or [[f"Nothing clears {MIN_EV:+.0%} after fees at Kalshi or Polymarket US.", "", "", "", "",
                                 "", ""]]}]
    upcoming = p[pd.to_datetime(p["kickoff"], utc=True, errors="coerce") > pd.Timestamp(now)] if len(p) else p
    if len(upcoming):
        best = upcoming.sort_values("ev", ascending=False).drop_duplicates(["game_id", "market"], keep="first")
        best = best.head(BOARD_ROWS)
        tables.append({"title": "Exchange board: each game and market at its best exchange price, against the consensus",
                       "head": ["Game", "Contract", "Venue", "Buy at", "Fair", "EV after fees"],
                       "rows": [[f"{label_of(names, x.game_id)} · {_eastern(x.kickoff)}",
                                 contract(x.market, x.side, x.line, label_of(names, x.game_id)),
                                 x.venue + ("" if x.tradeable else " (reference)"), _buy(x, now), paper._pct(x.p),
                                 f"{x.ev:+.1%}"] for x in best.itertuples()]})
    counts = []
    for book, venue in VENUES.items():
        mine = p[p["book_id"] == book] if len(p) else p
        n = {m: int((mine["market"] == m).sum()) if len(mine) else 0 for m in ("total", "spread", "moneyline")}
        counts.append([venue.name + ("" if venue.tradeable else " (reference)"), str(n["total"]), str(n["spread"]),
                       str(n["moneyline"])])
    tables.append({"title": "Quotes this run (sides priced)", "head": ["Venue", "Totals", "Spreads", "Moneylines"],
                   "rows": counts})
    if len(graded):
        done = graded[graded["outcome"].isin(["win", "loss", "push"])]
        decided = done[done["outcome"] != "push"]
        staked = float(pd.to_numeric(done["stake"], errors="coerce").sum()) if len(done) else 0.0
        pnl = float(done["pnl"].sum()) if len(done) else 0.0
        clv = pd.to_numeric(graded["clv_prob"], errors="coerce")
        rows = [["Positions logged", str(len(graded))], ["Graded", str(len(done))],
                ["Won-lost-push", f"{int((decided['outcome'] == 'win').sum())}-{int((decided['outcome'] == 'loss').sum())}-"
                                  f"{int((done['outcome'] == 'push').sum())}"],
                ["Return on the bankroll", f"{pnl:+.2%}" if len(done) else "–"],
                ["Return per dollar staked", f"{pnl / staked:+.1%}" if staked else "–"],
                ["Beat the consensus close", f"{int((clv > 0).sum())} of {int(clv.notna().sum())}" if clv.notna().any() else "–"],
                ["Mean CLV, win probability", f"{clv.mean():+.1%}" if clv.notna().any() else "–"]]
        tables.append({"title": "Record (paper)", "head": ["", ""], "rows": rows})
        latest = graded[graded["outcome"] != "open"].sort_values("kickoff", ascending=False).head(10)
        if len(latest):
            tables.append({"title": "Latest graded", "head": ["Game", "Contract", "Venue", "Result"],
                           "rows": [[x.label, contract(x.market, x.side, x.line, x.label),
                                     VENUES[int(x.book_id)].name if int(x.book_id) in VENUES else str(x.book_id),
                                     f"{x.outcome} {x.pnl:+.2%} of bankroll"
                                     + (f" · CLV {x.clv_prob:+.1%}" if pd.notna(x.clv_prob) else "")]
                                    for x in latest.itertuples()]})
    notes = [
        "Paper trading only: nothing is bought. Kalshi and Polymarket quotes arrive with every poll through "
        "BettingPros, the board's feed, and stay sealed like the board's lines. A contract costs its price and pays "
        "$1 if it wins.",
        "Fair is the sportsbook consensus with its margin removed, read at the contract's line; on totals, Atlas's "
        "calibrated probability, as on the board. EV after fees is fair ÷ (price + fee) − 1. Fees: Kalshi's taker "
        "fee, 7% × price × (1 − price) per contract (the exchange rounds each order up to the cent; not modelled), "
        "and 5% for Polymarket, the rate the Velocity repository modelled. Confirm both against each venue's current "
        "schedule before real money.",
        f"Positions: Kalshi and Polymarket US only (the global Polymarket is close-only for US accounts, shown for "
        f"reference), {MIN_EV:+.0%} or more after fees, one per game at the side and venue that pays best, at most "
        f"{MAX_POSITIONS} a day. Stake: a quarter of Kelly, (fair − cost) ÷ (1 − cost), capped at {MAX_STAKE:.0%} of "
        f"the bankroll each and {DAILY_CAP:.0%} a day.",
        "The day's positions are logged once, at the first run from 10:00 ET, at the prices shown then (marked "
        "logged); the tables keep moving. Each is graded on the final score, a push refunded, and against the "
        f"consensus close in win probability. Nothing is read from fewer than {MIN_GRADED} graded.",
        "Assumed, to confirm before trading: that each quote is the venue's price to buy, and that it fills at the "
        "size staked; the quotes carry no depth.",
    ]
    return [{"title": "Sports trading: Kalshi and Polymarket", "tab": "Trading", "notes": notes, "tables": tables}]


def build(lines: pd.DataFrame, events: pd.DataFrame, projections: pd.DataFrame, shapes: dict,
          calibration: pd.DataFrame | None, finals: pd.DataFrame, closes: pd.DataFrame, names: dict,
          passphrase: str, now: datetime, where: Path | None = None) -> list[dict]:
    """The exchanges priced, the day's positions logged once and graded, and the section. Never raises."""
    try:
        p = priced(quotes(lines, events, projections, shapes, now, calibration))
        chosen = positions(p, events, names, now)
        record = load(passphrase, where)
        if parlays.due(record, chosen, now):
            record, weeks = log(record, chosen)
            if weeks:
                seal(record, passphrase, weeks, where)
                LOG.info("trading: %d positions logged", len(chosen))
        counts = ", ".join(f"{v.name} {int((p['book_id'] == b).sum()) if len(p) else 0}" for b, v in VENUES.items())
        LOG.info("trading: %d exchange quotes priced (%s), %d positions today", len(p), counts, len(chosen))
        graded = grade(record, finals, closes, shapes)
        return section(p, chosen, graded, names, now)
    except Exception as error:  # noqa: BLE001 - the type only: a message could quote a price
        LOG.error("trading not built: %s", type(error).__name__)
        return [{"title": "Sports trading: Kalshi and Polymarket", "tab": "Trading",
                 "notes": [f"This run could not build the trading section ({type(error).__name__})."], "tables": []}]
