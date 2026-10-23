"""Paper positions on Polymarket: taken by rule, logged once, graded on the result and the close.

A position is a contract bought at the ask, after the fee, for a share of a
bankroll of one. The rule, fixed here and never tuned after a result:

* a contract the venue is accepting orders on, quoted inside
  :data:`MAX_SPREAD` with at least :data:`MIN_LIQUIDITY` of depth, whose
  fair probability sits inside :data:`BAND` (the tails of a ladder are
  priced too coarsely to trust a model's sigma there) and whose quote agrees
  with its own ladder within :data:`LADDER_TOLERANCE` (an edge against a
  market that disagrees with itself is not Atlas's);
* expected value after the fee of :data:`MIN_EV` or more;
* one position a game, at the contract that pays best; at most
  :data:`MAX_POSITIONS` a day, the Eastern day of the run or the next day
  with games;
* sized at :data:`KELLY_FRACTION` of Kelly, at most :data:`MAX_STAKE` each
  and :data:`DAILY_CAP` in all, scaled down together when they exceed it.

The day's positions are **logged once**, at the first run at or after
:data:`LOG_HOUR` Eastern on that day, at the prices shown then, into a
sealed record (``tracking/polymarket_positions/``, one file per ISO week),
and never revised. Each is graded on the final score (a push refunded) and
against Polymarket's own close - the contract's last midpoint seen before
the game started - in points of probability: a contract bought below where
it closed was a good buy whether or not it won.
"""

from __future__ import annotations

import json
import math
import uuid
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from atlas.owner import sealed
from atlas.polymarket import source
from atlas.util import get_logger, offline

LOG = get_logger(__name__)

EASTERN = ZoneInfo("America/New_York")
NAMESPACE = uuid.UUID("2c7a1f3e-5b9d-4a6e-8f10-3d2c1b0a9e87")

MIN_EV = 0.02
MAX_POSITIONS = 10
KELLY_FRACTION = 0.25
MAX_STAKE = 0.02
DAILY_CAP = 0.10
MAX_SPREAD = 0.04
MIN_LIQUIDITY = 2_000.0
BAND = (0.15, 0.85)
LADDER_TOLERANCE = 0.05
LOG_HOUR = 10
MIN_GRADED = 50

COLUMNS = ["position_id", "formed_at", "day", "year", "week", "game_id", "sport", "kickoff", "label", "away", "home",
           "market", "side", "line", "token_id", "market_id", "condition_id", "event_slug", "ask", "fee_rate", "fee",
           "cost", "p_market", "p_raw", "p", "ev", "kelly", "stake", "liquidity", "spread"]


def path() -> Path:
    from atlas.live.store import tracking_dir

    return tracking_dir() / "polymarket_positions"


def day_of(ts) -> str:
    """The Eastern calendar day a moment falls on."""
    t = pd.Timestamp(ts)
    t = t.tz_localize("UTC") if t.tzinfo is None else t
    return t.tz_convert(EASTERN).strftime("%Y-%m-%d")


def iso_week(ts) -> tuple[int, int]:
    t = pd.Timestamp(ts)
    t = t.tz_localize("UTC") if t.tzinfo is None else t
    year, week, _ = t.isocalendar()
    return int(year), int(week)


def contract(market: str, side: str, line: float, away: str, home: str) -> str:
    """"Chiefs to win", "Chiefs -1.5", "Over 44.5"."""
    team = home if side == "home" else away
    if market == "moneyline":
        return f"{team} to win"
    if market == "spread":
        return f"{team} {float(line):+g}"
    return f"{side.capitalize()} {float(line):g}"


# ---------------------------------------------------------------------------
# The day's positions
# ---------------------------------------------------------------------------


def eligible(p: pd.DataFrame, now: datetime) -> pd.Series:
    """The contracts a position may be taken on, before the expected-value bar."""
    if p.empty:
        return pd.Series(dtype=bool)
    kick = pd.to_datetime(p["kickoff"], utc=True, errors="coerce")
    ask = pd.to_numeric(p["ask"], errors="coerce")
    ladder = pd.to_numeric(p.get("p_ladder"), errors="coerce") if "p_ladder" in p else pd.Series(np.nan, index=p.index)
    agrees = (pd.to_numeric(p["p_market"], errors="coerce") - ladder).abs() <= LADDER_TOLERANCE
    ok = (p["accepting"].astype(bool)
          & (kick > pd.Timestamp(now))
          & (ask > 0) & (ask < 1)
          & (pd.to_numeric(p["spread"], errors="coerce") <= MAX_SPREAD)
          & (pd.to_numeric(p["liquidity"], errors="coerce") >= MIN_LIQUIDITY)
          & pd.to_numeric(p["p"], errors="coerce").between(*BAND)
          & (agrees | ladder.isna()))
    return ok.fillna(False)


def positions(p: pd.DataFrame, now: datetime, *, unit: str = "game_id", columns: list[str] | None = None,
              limit: int = MAX_POSITIONS) -> pd.DataFrame:
    """The day's positions under the rule, sized: one per ``unit`` (a game; for a prop, a player's stat), at
    most ``limit``, in ``columns``."""
    columns = columns or COLUMNS
    if p.empty:
        return pd.DataFrame(columns=columns)
    t = p[eligible(p, now) & (pd.to_numeric(p["ev"], errors="coerce") >= MIN_EV)].copy()
    if t.empty:
        return pd.DataFrame(columns=columns)
    t["day"] = pd.to_datetime(t["kickoff"], utc=True).map(day_of)
    today = day_of(now)
    day = today if (t["day"] == today).any() else t["day"].min()
    t = t[t["day"] == day].sort_values("ev", ascending=False).drop_duplicates([unit], keep="first")
    t = t.head(limit).copy()
    stake = np.minimum(KELLY_FRACTION * pd.to_numeric(t["kelly"], errors="coerce").fillna(0.0), MAX_STAKE)
    if stake.sum() > DAILY_CAP:
        stake = stake * DAILY_CAP / stake.sum()
    t["stake"] = stake.round(4)
    stamp = pd.Timestamp(now).strftime("%Y-%m-%dT%H:%M:%SZ")
    t["formed_at"] = stamp
    weeks = [iso_week(k) for k in t["kickoff"]]
    t["year"], t["week"] = [y for y, _ in weeks], [w for _, w in weeks]
    t["position_id"] = [str(uuid.uuid5(NAMESPACE, f"{d}|{u}|{m}|{s}|{float(ln):g}"))
                        for d, u, m, s, ln in zip(t["day"], t[unit], t["market"], t["side"], t["line"], strict=True)]
    t["kickoff"] = pd.to_datetime(t["kickoff"], utc=True).dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    for c in ("ask", "fee", "cost", "p_market", "p_raw", "p", "ev", "kelly", "spread"):
        t[c] = pd.to_numeric(t[c], errors="coerce").astype(float).round(4)
    t["game_id"] = t["game_id"].astype(str)
    return t.reindex(columns=columns).reset_index(drop=True)


# ---------------------------------------------------------------------------
# The record
# ---------------------------------------------------------------------------


def load(passphrase: str, where: Path | None = None, columns: list[str] | None = None) -> pd.DataFrame:
    columns = columns or COLUMNS
    rows = sealed.load(where or path(), passphrase)
    return pd.DataFrame(rows, columns=columns) if rows else pd.DataFrame(columns=columns)


def due(record: pd.DataFrame, chosen: pd.DataFrame, now: datetime) -> bool:
    """Is this the run that logs the day's set: at or after :data:`LOG_HOUR` Eastern on the day the
    positions are for, and nothing logged for that day yet."""
    if chosen.empty:
        return False
    local = pd.Timestamp(now).tz_convert(EASTERN)
    day = str(chosen["day"].iloc[0])
    if day != local.strftime("%Y-%m-%d") or local.hour < LOG_HOUR:
        return False
    return not (len(record) and (record["day"].astype(str) == day).any())


def log(record: pd.DataFrame, chosen: pd.DataFrame, columns: list[str] | None = None) -> tuple[pd.DataFrame, set]:
    """Add the positions not yet logged, at the prices shown; a logged position is never revised."""
    columns = columns or COLUMNS
    if chosen.empty:
        return record, set()
    fresh = chosen.reindex(columns=columns)
    new = fresh[~fresh["position_id"].isin(set(record["position_id"]))] if len(record) else fresh
    if new.empty:
        return record, set()
    weeks = {(int(y), int(w)) for y, w in new[["year", "week"]].drop_duplicates().itertuples(index=False)}
    parts = [record.reindex(columns=columns), new] if len(record) else [new]
    return pd.concat(parts, ignore_index=True).reindex(columns=columns), weeks


def seal(record: pd.DataFrame, passphrase: str, weeks: set, where: Path | None = None,
         columns: list[str] | None = None) -> list[Path]:
    columns = columns or COLUMNS
    where = where or path()
    out = []
    for year, week in sorted(weeks):
        part = record[(pd.to_numeric(record["year"]) == year) & (pd.to_numeric(record["week"]) == week)]
        rows = json.loads(part.reindex(columns=columns).to_json(orient="records"))
        out.append(sealed.seal(rows, passphrase, sealed.week_file(where, year, week),
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


def closing(quotes: pd.DataFrame, token_id, start) -> float:
    """The contract's close: the record's last midpoint before the start, else (a line the record does not
    keep, a poll missed) the venue's own price history, read when the network allows."""
    mid = source.close(quotes, token_id, start)
    if math.isfinite(mid) or offline():
        return mid
    try:
        h = source.history(str(token_id))
    except Exception as error:  # noqa: BLE001 - a close the venue will not give is a close not read
        LOG.info("polymarket: no price history for a contract (%s)", type(error).__name__)
        return float("nan")
    if h.empty:
        return float("nan")
    cutoff = pd.Timestamp(start)
    cutoff = cutoff.tz_localize("UTC") if cutoff.tzinfo is None else cutoff.tz_convert("UTC")
    before = h[h["at"] <= cutoff]
    return float(before["price"].iloc[-1]) if len(before) else float("nan")


def grade(record: pd.DataFrame, finals: pd.DataFrame, quotes: pd.DataFrame, now: datetime) -> pd.DataFrame:
    """Each position with its outcome, its return per dollar staked (a winning contract pays one dollar on
    its cost; a push is refunded), its return on the bankroll, Polymarket's close for the contract and the
    position's value against it (close less the ask bought at, in probability)."""
    if record.empty:
        return record.assign(outcome=pd.Series(dtype=str), profit=pd.Series(dtype=float),
                             pnl=pd.Series(dtype=float), close=pd.Series(dtype=float), clv=pd.Series(dtype=float))
    r = record.assign(game_id=record["game_id"].astype(str)).merge(
        finals.assign(game_id=finals["game_id"].astype(str)), on="game_id", how="left")
    r["outcome"] = [outcome(m, s, float(ln), float(mg) if pd.notna(mg) else float("nan"),
                            float(tt) if pd.notna(tt) else float("nan"))
                    for m, s, ln, mg, tt in zip(r["market"], r["side"], r["line"], r["final_margin"],
                                                r["final_total"], strict=True)]
    cost = pd.to_numeric(r["cost"], errors="coerce")
    r["profit"] = np.select([r["outcome"] == "win", r["outcome"] == "loss"], [(1.0 - cost) / cost, -1.0], 0.0)
    r.loc[r["outcome"] == "open", "profit"] = np.nan
    r["pnl"] = pd.to_numeric(r["stake"], errors="coerce") * r["profit"]
    kick = pd.to_datetime(r["kickoff"], utc=True, errors="coerce")
    started = kick <= pd.Timestamp(now)
    r["close"] = [closing(quotes, tok, k) if s else float("nan")
                  for tok, k, s in zip(r["token_id"], kick, started, strict=True)]
    r["clv"] = r["close"] - pd.to_numeric(r["ask"], errors="coerce")
    return r.drop(columns=[c for c in ("final_margin", "final_total") if c in r])


# ---------------------------------------------------------------------------
# One run
# ---------------------------------------------------------------------------


def run(priced: pd.DataFrame, finals: pd.DataFrame, quotes: pd.DataFrame, passphrase: str, now: datetime,
        where: Path | None = None, *, unit: str = "game_id", columns: list[str] | None = None,
        grader=None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """The day's positions chosen, logged if due, and the record graded: (chosen, graded). ``grader`` grades
    the record (:func:`grade` on the final score by default; a prop's grader reads the box score)."""
    columns = columns or COLUMNS
    chosen = positions(priced, now, unit=unit, columns=columns)
    record = load(passphrase, where, columns)
    if due(record, chosen, now):
        record, weeks = log(record, chosen, columns)
        if weeks:
            seal(record, passphrase, weeks, where, columns)
            LOG.info("polymarket: %d positions logged for %s", len(chosen), chosen["day"].iloc[0])
    return chosen, (grader or grade)(record, finals, quotes, now)
