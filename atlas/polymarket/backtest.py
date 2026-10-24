"""The favorites rule, backtested on Polymarket US's own price history.

    python -m atlas.polymarket.backtest                       # every settled game the venue lists, five leagues
    python -m atlas.polymarket.backtest --leagues nba,nhl     # some of them
    python -m atlas.polymarket.backtest --limit 200           # a quick look

The question the favorites rule (`atlas/polymarket/favorites.py`) is asking
one game at a time - does a side whose ask has reached 85 cents win more
often than it costs, in play or before the game - can be asked of every
game the venue has already settled. The gateway lists its closed events
(``/v1/events?closed=true``), each with its two teams, its start, when it
finished and the moneyline's settled price per side; and its price history
(``/v1/price-history`` at a one-minute fidelity) carries, for every minute
a market was open, **each side's ask** - the long side's, and one less the
bid for the short - which is the price the rule buys at.

So the backtest is the rule replayed on the tape: for each side of each
game, in each phase (before the start, and in play), the first minute its
ask sat at or over each of :data:`THRESHOLDS` and under the ceiling is a
position at that ask plus the venue's fee, graded by the settled price. The
summary is the rule's own: the win rate against the break-even rate (the
mean cost), the edge between them in points with its standard error, and
the profit per dollar staked - by league, by threshold, and by how much of
the game was left (the minutes to the final whistle, which the history and
the finish time give).

Execution is modelled too, because it decides whether a thin edge survives.
The ideal fill is the trigger minute's ask. The **stale-limit** fill is what
a poller that sees the crossing ``L`` minutes late and sends a limit at the
price it saw would get: it fills only when the ask ``L`` minutes on is no
higher - the lead has not grown - and misses when it has risen. The report
shows both, at :data:`LATENCIES`, so the adverse selection of a slow loop is
measured rather than argued about.

Raw material is cached under ``data/raw/polymarket_us/`` (the closed listing,
read on from its end next time; each market's history once), so a rerun costs
nothing but the new games.
The positions go to a CSV beside the cache; the summaries and the report
to ``reports/``. Nothing here buys anything.
"""

from __future__ import annotations

import argparse
import json
import math
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd

from atlas import config
from atlas.polymarket import favorites, pricing, source
from atlas.util import get_logger, session

LOG = get_logger(__name__)

#: The leagues read by default: the four Atlas prices, and college basketball, which the venue lists most.
LEAGUES = ("nfl", "nba", "nhl", "cfb", "cbb")
#: The rule's thresholds, and one more for the "pretty much decided" end of the ladder.
THRESHOLDS = (*favorites.THRESHOLDS, 0.97)
CEILING = favorites.CEILING
#: Minutes between the crossing and the order, for the stale-limit fills.
LATENCIES = (1, 5, 15)
#: The history read for a game: this long before the start, to this long after the finish (or after the
#: start, when the finish is not recorded).
BEFORE = timedelta(hours=2)
AFTER = timedelta(minutes=15)
LONGEST = timedelta(hours=6)
PAGE = 500
#: How much of the game was left when the position was taken, in minutes to the finish.
BUCKETS = ((60.0, "over 60 min left"), (30.0, "30 to 60"), (15.0, "15 to 30"), (5.0, "5 to 15"), (0.0, "under 5"))

GAME_COLUMNS = ["league", "event_id", "event_slug", "label", "away", "home", "start", "finished", "market_slug",
                "fee_rate", "long_side", "result_long"]
POSITION_COLUMNS = ["league", "event_id", "event_slug", "label", "side", "long", "phase", "threshold", "at",
                    "minutes_in", "minutes_left", "bucket", "price", "spread", "fee", "cost", "price_at_start",
                    "payout", "won", "profit", *[f"fill_{L}" for L in LATENCIES]]


# ---------------------------------------------------------------------------
# The venue's record
# ---------------------------------------------------------------------------


def raw_dir() -> Path:
    return config.paths().raw / "polymarket_us"


#: How far back from the end of the cached listing a rerun starts reading, since the listing is oldest first
#: and new events arrive at its end.
OVERLAP = 2_000


def closed_events(sess=None, *, cache: Path | None = None, refresh: bool = False) -> list[dict]:
    """Every closed event the gateway lists - well over a hundred thousand, most of them tennis - read in
    full once and cached; a rerun reads on from near the end of the cache, where the new ones are, and
    ``refresh`` reads the whole listing again. The listing's pages are not all full, so it is read until
    an empty one."""
    cache = cache or raw_dir() / "closed_events.json"
    sess = sess or session()
    out: dict[str, dict] = {}
    offset = 0
    if cache.exists() and not refresh:
        for e in json.loads(cache.read_text()).get("events", []):
            out[str(e.get("id"))] = e
        offset = max(0, len(out) - OVERLAP)
    while True:
        page = source._get("/v1/events", {"closed": "true", "limit": PAGE, "offset": offset}, sess, timeout=120)
        events = page.get("events") if isinstance(page, dict) else None
        if not events:
            break
        for e in events:
            out[str(e.get("id"))] = e
        offset += len(events)
        time.sleep(source.PAUSE)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({"fetched_at": datetime.now(UTC).isoformat(), "events": list(out.values())}))
    LOG.info("backtest: %d closed events read", len(out))
    return list(out.values())


def league_of(event: dict) -> str:
    """The league from the event's slug: "nba-chi-mil-2026-10-23" is the NBA's; a market's slug carries an
    "aec-" in front."""
    parts = str(event.get("slug") or "").split("-")
    if parts and parts[0] == "aec":
        parts = parts[1:]
    return parts[0] if parts else ""


def moneyline_of(event: dict) -> dict | None:
    """The game's moneyline: the legacy ``moneyline`` market type on the older events, the sport's
    ``*_team_full_game_winner`` on the newer."""
    for m in event.get("markets") or []:
        kind = str(m.get("sportsMarketType") or "")
        if kind == "moneyline" or kind.endswith("_team_full_game_winner"):
            return m
    return None


def _side_price(side: dict) -> float:
    try:
        v = float(side.get("price"))
    except (TypeError, ValueError):
        return float("nan")
    return v if math.isfinite(v) else float("nan")


def _teams(event: dict) -> tuple[dict | None, dict | None]:
    """(away, home) by the teams' own ``ordering`` where they carry one, else as listed (away first)."""
    listed = event.get("teams") or []
    if len(listed) != 2:
        return None, None
    by = {str(t.get("ordering") or "").lower(): t for t in listed}
    if "away" in by and "home" in by:
        return by["away"], by["home"]
    return listed[0], listed[1]


def game(event: dict) -> dict | None:
    """One settled game from a closed event: its teams, its start and finish, its moneyline's slug, fee and
    settled price for the long side; None when the event is not a game with two teams and a moneyline."""
    market = moneyline_of(event)
    away, home = _teams(event)
    if market is None or away is None:
        return None
    start = source._utc(event.get("startTime") or market.get("gameStartTime") or event.get("startDate"))
    if pd.isna(start):
        return None
    sides = market.get("marketSides") or []
    long_ = next((s for s in sides if s.get("long", False)), sides[0] if sides else {})
    long_team = str(long_.get("teamId") or "")
    long_side = "away" if long_team == str(away.get("id")) else ("home" if long_team == str(home.get("id")) else None)
    finished = source._utc(event.get("finishedTimestamp") or event.get("closedTime"))
    return {"league": league_of(event), "event_id": str(event.get("id")), "event_slug": event.get("slug"),
            "label": f"{source.team_name(away)} @ {source.team_name(home)}", "away": source.team_name(away),
            "home": source.team_name(home), "start": start, "finished": finished if pd.notna(finished) else pd.NaT,
            "market_slug": market.get("slug"), "fee_rate": source.fee_rate(market), "long_side": long_side,
            "result_long": _side_price(long_)}


def games(events: list[dict], leagues=LEAGUES) -> pd.DataFrame:
    """The settled games of ``leagues`` among the closed events, oldest first."""
    rows = [g for g in (game(e) for e in events) if g and g["league"] in set(leagues)]
    out = pd.DataFrame(rows, columns=GAME_COLUMNS)
    return out.sort_values("start", kind="stable").reset_index(drop=True)


# ---------------------------------------------------------------------------
# The tape
# ---------------------------------------------------------------------------


def window(start, finished) -> tuple[pd.Timestamp, pd.Timestamp]:
    start = pd.Timestamp(start)
    end = pd.Timestamp(finished) if pd.notna(finished) else start + LONGEST
    return start - BEFORE, max(end, start) + AFTER


def history(market_slug: str, start, finished, sess=None, *, cache_dir: Path | None = None,
            refresh: bool = False) -> pd.DataFrame:
    """The market's minute-by-minute asks (``at``, ``long``, ``short``) through the game, read once and
    cached as JSON beside the listing."""
    cache_dir = cache_dir or raw_dir() / "history"
    path = cache_dir / f"{market_slug}.json"
    if path.exists() and not refresh:
        rows = json.loads(path.read_text())
        h = pd.DataFrame(rows, columns=["at", "long", "short"])
        h["at"] = pd.to_datetime(h["at"], utc=True)
        return h
    lo, hi = window(start, finished)
    h = source.history(market_slug, sess, start=lo, end=hi)
    cache_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([[t.isoformat(), lg, sh] for t, lg, sh in
                                zip(h["at"], h["long"], h["short"], strict=True)]))
    return h


def terminal(price: pd.Series) -> pd.Series:
    """A price the market has stopped pricing: settled, or as good as."""
    return (price <= 0.01) | (price >= 0.99)


def game_end(h: pd.DataFrame, start, finished) -> pd.Timestamp:
    """When the game ended: the venue's finish time, else the minute after the tape last priced the long
    side between one and ninety-nine cents; the start when neither is known."""
    if pd.notna(finished):
        return pd.Timestamp(finished)
    start = pd.Timestamp(start)
    if h.empty:
        return start
    live = h[(h["at"] >= start) & ~terminal(pd.to_numeric(h["long"], errors="coerce"))]
    return live["at"].max() + timedelta(minutes=1) if len(live) else start


def bucket(phase: str, minutes_left: float) -> str:
    if phase == "pregame":
        return "pregame"
    if not math.isfinite(minutes_left):
        return "in play, time unknown"
    for floor, name in BUCKETS:
        if minutes_left >= floor:
            return name
    return BUCKETS[-1][1]


def stale_fill(series: pd.Series, when: pd.Timestamp, price: float, latency: int, end: pd.Timestamp) -> float:
    """What a limit at ``price`` sent ``latency`` minutes after ``when`` fills at: the ask then, when it is
    no higher than the price seen and the market is still pricing the game; nan when it misses."""
    later = series[series.index >= when + timedelta(minutes=latency)]
    if later.empty:
        return float("nan")
    at, ask = later.index[0], float(later.iloc[0])
    if at > end or not math.isfinite(ask) or ask <= 0.01 or ask >= 0.99 or ask > price + 1e-9:
        return float("nan")
    return ask


def crossings(g: dict, h: pd.DataFrame, *, thresholds=THRESHOLDS, ceiling: float = CEILING,
              latencies=LATENCIES) -> list[dict]:
    """The rule replayed on one game's tape: for each side, in each phase, a position at the first minute
    its ask sat at or over each threshold and at or under the ceiling, at that ask plus the fee, graded by
    the settled price; with what a stale limit at each latency would have filled at."""
    if h.empty or not math.isfinite(float(g.get("result_long", float("nan")))):
        return []
    start = pd.Timestamp(g["start"])
    end = game_end(h, start, g.get("finished"))
    tape = h.assign(long=pd.to_numeric(h["long"], errors="coerce"), short=pd.to_numeric(h["short"], errors="coerce"))
    tape = tape.dropna(subset=["at"]).sort_values("at", kind="stable").set_index("at")
    tape = tape[~tape.index.duplicated(keep="last")]
    spread = (tape["long"] + tape["short"] - 1.0).clip(lower=0.0)
    before = tape[tape.index < start]
    at_start = {c: float(before[c].iloc[-1]) if len(before) and pd.notna(before[c].iloc[-1]) else float("nan")
                for c in ("long", "short")}
    result_long = float(g["result_long"])
    rate = float(g.get("fee_rate", 0.0) or 0.0)
    long_side = g.get("long_side")
    out = []
    for column, is_long in (("long", True), ("short", False)):
        series = tape[column]
        payout = result_long if is_long else 1.0 - result_long
        side = (long_side if is_long else {"away": "home", "home": "away"}.get(long_side)) or column
        for phase, part in (("pregame", series[series.index < start]),
                            ("in_play", series[(series.index >= start) & (series.index < end)])):
            for t in thresholds:
                hit = part[(part >= t - 1e-9) & (part <= ceiling + 1e-9)]
                if hit.empty:
                    continue
                when, price = hit.index[0], float(hit.iloc[0])
                fee = pricing.fee(price, rate)
                fee = fee if math.isfinite(fee) else 0.0
                cost = price + fee
                minutes_left = (end - when).total_seconds() / 60.0 if pd.notna(end) else float("nan")
                row = {"league": g["league"], "event_id": g["event_id"], "event_slug": g["event_slug"],
                       "label": g["label"], "side": side, "long": is_long, "phase": phase, "threshold": t,
                       "at": when, "minutes_in": round((when - start).total_seconds() / 60.0, 1),
                       "minutes_left": round(minutes_left, 1) if math.isfinite(minutes_left) else float("nan"),
                       "bucket": bucket(phase, minutes_left), "price": price,
                       "spread": float(spread.loc[when]) if when in spread.index else float("nan"),
                       "fee": fee, "cost": cost, "price_at_start": at_start[column], "payout": payout,
                       "won": 1.0 if payout >= 0.999 else 0.0, "profit": payout - cost}
                for L in latencies:
                    row[f"fill_{L}"] = stale_fill(series, when, price, L, end)
                out.append(row)
    return out


# ---------------------------------------------------------------------------
# The summary
# ---------------------------------------------------------------------------


def cluster_se(x: pd.Series, groups: pd.Series) -> float:
    """The standard error of the mean of ``x`` with the observations clustered by ``groups`` (a game's
    positions are not independent of each other)."""
    x = pd.to_numeric(x, errors="coerce")
    n = int(x.notna().sum())
    if n < 2:
        return float("nan")
    d = (x - x.mean()).groupby(groups).sum()
    return float(math.sqrt(float((d * d).sum())) / n)


def summary(positions: pd.DataFrame, by=("phase", "threshold"), *, latency: int | None = None) -> pd.DataFrame:
    """Per group: positions taken (and filled, at a latency), the win rate, the break-even rate (the mean
    cost), the edge between them with a game-clustered standard error, and the profit per dollar staked.
    At a latency, the positions are the stale limits that filled, at the price they filled at."""
    cols = [*by, "taken", "filled", "win_rate", "break_even", "edge", "se", "profit_per_dollar"]
    if positions is None or positions.empty:
        return pd.DataFrame(columns=cols)
    p = positions.copy()
    if latency is not None:
        px = pd.to_numeric(p[f"fill_{latency}"], errors="coerce")
        rate = pd.to_numeric(p["fee"], errors="coerce") / (pd.to_numeric(p["price"], errors="coerce")
                                                           * (1.0 - pd.to_numeric(p["price"], errors="coerce")))
        fee = (rate.fillna(0.0) * px * (1.0 - px)).where(px.notna(), float("nan"))
        p["cost"] = px + fee
        p["profit"] = pd.to_numeric(p["payout"], errors="coerce") - p["cost"]
        p["filled"] = px.notna()
    else:
        p["filled"] = True
    rows = []
    for key, g in p.groupby(list(by), sort=True):
        key = key if isinstance(key, tuple) else (key,)
        f = g[g["filled"]]
        n = len(f)
        won = pd.to_numeric(f["won"], errors="coerce")
        cost = pd.to_numeric(f["cost"], errors="coerce")
        win = float(won.mean()) if n else float("nan")
        need = float(cost.mean()) if n else float("nan")
        rows.append({**dict(zip(by, key, strict=True)), "taken": int(len(g)), "filled": n, "win_rate": win,
                     "break_even": need, "edge": win - need if n else float("nan"),
                     "se": cluster_se(won - cost, f["event_id"]) if n else float("nan"),
                     "profit_per_dollar": float(f["profit"].sum() / cost.sum()) if n and cost.sum() > 0 else float("nan")})
    return pd.DataFrame(rows, columns=cols)


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------


def run(leagues=LEAGUES, *, limit: int | None = None, refresh: bool = False, sess=None, raw: Path | None = None,
        thresholds=THRESHOLDS, latencies=LATENCIES) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(the games, the positions): every settled game of ``leagues`` the venue lists (the newest ``limit``
    of them), each replayed. The tape is cached, so only new games cost a request."""
    sess = sess or session()
    raw = raw or raw_dir()
    evs = closed_events(sess, cache=raw / "closed_events.json", refresh=refresh)
    gs = games(evs, leagues)
    if limit:
        gs = gs.tail(limit).reset_index(drop=True)
    LOG.info("backtest: %d settled games in %s", len(gs), ",".join(leagues))
    rows: list[dict] = []
    read = {"with_tape": 0, "empty": 0, "failed": 0}
    for i, g in enumerate(gs.to_dict("records"), 1):
        try:
            h = history(str(g["market_slug"]), g["start"], g["finished"], sess, cache_dir=raw / "history")
        except Exception as error:  # noqa: BLE001 - one market's tape missing is not the backtest's
            LOG.info("backtest: no history for %s (%s)", g["market_slug"], type(error).__name__)
            read["failed"] += 1
            continue
        read["with_tape" if len(h) else "empty"] += 1
        rows.extend(crossings(g, h, thresholds=thresholds, latencies=latencies))
        if i % 250 == 0:
            LOG.info("backtest: %d of %d games replayed, %d positions", i, len(gs), len(rows))
        time.sleep(source.PAUSE)
    LOG.info("backtest: %d games with a tape, %d empty, %d failed; %d positions", read["with_tape"], read["empty"],
             read["failed"], len(rows))
    positions = pd.DataFrame(rows, columns=POSITION_COLUMNS)
    if len(positions):
        positions["at"] = pd.to_datetime(positions["at"], utc=True).dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    return gs, positions


# ---------------------------------------------------------------------------
# The report
# ---------------------------------------------------------------------------


def _pct(v) -> str:
    return f"{v:.1%}" if pd.notna(v) else ""


def _edge(e, se) -> str:
    if pd.isna(e):
        return ""
    return f"{100 * e:+.1f} ± {100 * se:.1f}" if pd.notna(se) else f"{100 * e:+.1f}"


def _table(s: pd.DataFrame, keys: list[str], *, filled: bool = False) -> str:
    head = [k.replace("_", " ").title() for k in keys] + (["Filled / taken"] if filled else ["Taken"]) + \
        ["Win rate", "Break-even", "Edge (pts)", "Profit per $"]
    lines = ["| " + " | ".join(head) + " |", "|" + "|".join("---" for _ in head) + "|"]
    for x in s.itertuples(index=False):
        cells = []
        for k in keys:
            v = getattr(x, k)
            cells.append(f"{float(v):.0%}" if k == "threshold" else (str(v).replace("_", " ") if k != "latency"
                                                                      else f"{int(v)} min"))
        cells.append(f"{x.filled} / {x.taken}" if filled else str(x.taken))
        cells += [_pct(x.win_rate), _pct(x.break_even), _edge(x.edge, x.se), _pct(x.profit_per_dollar)]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _ordered(s: pd.DataFrame) -> pd.DataFrame:
    order = {name: i for i, (_, name) in enumerate(BUCKETS)}
    order = {"pregame": -1, **order, "in play, time unknown": len(order)}
    if "bucket" in s:
        s = s.assign(_o=s["bucket"].map(order).fillna(99)).sort_values(["_o", "threshold"], kind="stable") \
            .drop(columns="_o")
    return s


def report(gs: pd.DataFrame, positions: pd.DataFrame, now: datetime | None = None,
           latencies=LATENCIES) -> tuple[str, dict[str, pd.DataFrame]]:
    """The markdown report and the summary tables behind it, keyed by name."""
    now = now or datetime.now(UTC)
    tables: dict[str, pd.DataFrame] = {}
    lines = ["# The favorites rule on Polymarket US's own tape", "",
             f"*Built {now:%Y-%m-%d %H:%M} UTC by `python -m atlas.polymarket.backtest`.*", "",
             "The favorites rule (`atlas/polymarket/favorites.py`) replayed on every settled game the venue "
             "lists: for each side of each moneyline, in each phase, a paper position at the first minute its "
             "ask sat at or over each threshold, at that ask plus the venue's fee, graded by the settled price. "
             "The tape is the exchange's own minute-by-minute price history, which carries each side's ask. "
             "Edge is the win rate less the break-even rate (the mean cost) in points, with a standard error "
             "clustered by game; profit per dollar is what a dollar staked across the positions returned.", ""]
    # Coverage
    lines += ["## Coverage", ""]
    if len(gs):
        taped = set(positions["event_id"].astype(str)) if len(positions) else set()
        cov = gs.assign(taped=gs["event_id"].astype(str).isin(taped)).groupby("league").agg(
            games=("event_id", "size"), with_tape=("taped", "sum"), first=("start", "min"), last=("start", "max"))
        lines += ["| League | Settled games | With a tape and a position | First | Last |", "|---|---|---|---|---|"]
        for lg, r in cov.iterrows():
            lines.append(f"| {str(lg).upper()} | {int(r['games'])} | {int(r['with_tape'])} | "
                         f"{pd.Timestamp(r['first']):%Y-%m-%d} | {pd.Timestamp(r['last']):%Y-%m-%d} |")
        lines.append("")
    if positions.empty:
        lines += ["No positions: no game's tape crossed a threshold.", ""]
        return "\n".join(lines), tables
    inplay = positions[positions["phase"] == "in_play"]
    # Headline
    lines += ["## In play, all leagues, by how much of the game was left", "",
              "The question asked of the tape: once a side's ask reaches the threshold during the game, does it "
              "win more often than it costs, and does that depend on how late it is. The ideal fill, at the "
              "trigger minute's ask.", ""]
    s = _ordered(summary(inplay, by=("bucket", "threshold")))
    tables["in_play_by_time_left"] = s
    lines += [_table(s, ["bucket", "threshold"]), ""]
    # By league
    lines += ["## In play, by league", ""]
    s = summary(inplay, by=("league", "threshold")).assign(league=lambda d: d["league"].str.upper())
    tables["in_play_by_league"] = s
    lines += [_table(s, ["league", "threshold"]), ""]
    late = inplay[inplay["bucket"].isin([name for floor, name in BUCKETS if floor < 15.0])]
    if len(late):
        lines += ["### In play with under 15 minutes left, by league", ""]
        s = summary(late, by=("league", "threshold")).assign(league=lambda d: d["league"].str.upper())
        tables["late_by_league"] = s
        lines += [_table(s, ["league", "threshold"]), ""]
    # Execution
    lines += ["## What a slow loop would actually get", "",
              "The same in-play positions, filled as a poller would fill them: it sees the crossing some minutes "
              "late and sends a limit at the ask it saw. The order fills only when the ask has not risen since "
              "(the lead has not grown) and misses when it has. A fifteen-minute latency is what a quarter-hourly "
              "scheduled job delivers.", ""]
    parts = []
    for L in latencies:
        parts.append(summary(inplay, by=("threshold",), latency=L).assign(latency=L))
    s = pd.concat(parts, ignore_index=True)[["latency", "threshold", "taken", "filled", "win_rate", "break_even",
                                             "edge", "se", "profit_per_dollar"]]
    tables["in_play_by_latency"] = s
    lines += [_table(s, ["latency", "threshold"], filled=True), ""]
    # Pregame
    pre = positions[positions["phase"] == "pregame"]
    if len(pre):
        lines += ["## Before the game", "", "The first minute before the start at which the ask reached the "
                  "threshold, which can be days out.", ""]
        s = summary(pre, by=("league", "threshold")).assign(league=lambda d: d["league"].str.upper())
        tables["pregame_by_league"] = s
        lines += [_table(s, ["league", "threshold"]), ""]
    # Reading it
    lines += ["## Reading it", "",
              "- A position is one side of one game at one threshold in one phase; a side that climbs through "
              "several thresholds appears at each, so the standard errors are clustered by game.",
              "- The tape is sampled once a minute and carries the top of the book only. A fill at the ask is "
              "assumed for the size meant; the live rule reads the depth it does not have here.",
              "- The fee is the market's own coefficient times price times one less the price; the break-even "
              "rate is the mean cost, fee included.",
              "- The time left is to the venue's recorded finish (or the last minute the tape priced the game), "
              "not the game clock: an NFL game's last five minutes of play are more than five minutes of tape.",
              "- Positive and several errors wide, over hundreds of positions, before it means anything. The "
              "live record (`tracking/favorites.csv`) is the out-of-sample continuation of this table.", ""]
    return "\n".join(lines), tables


def write(gs: pd.DataFrame, positions: pd.DataFrame, *, reports: Path | None = None,
          raw: Path | None = None) -> Path:
    reports = reports or config.paths().reports
    raw = raw or raw_dir()
    text, tables = report(gs, positions)
    out = reports / "favorites_backtest.md"
    out.write_text(text)
    (reports / "tables").mkdir(parents=True, exist_ok=True)
    for name, t in tables.items():
        t.to_csv(reports / "tables" / f"favorites_backtest_{name}.csv", index=False, float_format="%.4f")
    raw.mkdir(parents=True, exist_ok=True)
    positions.to_csv(raw / "favorites_backtest_positions.csv", index=False, float_format="%.4f")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="The favorites rule on Polymarket US's own price history")
    ap.add_argument("--leagues", default=",".join(LEAGUES), help="comma-separated league slugs")
    ap.add_argument("--limit", type=int, default=None, help="only the newest N games")
    ap.add_argument("--refresh", action="store_true", help="read the whole closed-events listing again, not just its end")
    args = ap.parse_args()
    leagues = tuple(x.strip().lower() for x in args.leagues.split(",") if x.strip())
    gs, positions = run(leagues, limit=args.limit, refresh=args.refresh)
    out = write(gs, positions)
    print(f"{len(gs)} games, {len(positions)} positions -> {out}")
    if len(positions):
        print(_table(_ordered(summary(positions[positions["phase"] == "in_play"], by=("bucket", "threshold"))),
                     ["bucket", "threshold"]))


if __name__ == "__main__":
    main()
