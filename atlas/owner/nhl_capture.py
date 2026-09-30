"""The NHL's market, captured from opening night and sealed (docs/MODEL_PLAN_NHL.md, step 0).

Closing lines not captured are gone: no free source keeps the NHL's past lines
after 2021-22, and the season opened on 30 September 2026, before any model.
So this records the market now and prices nothing:

* **game lines**: every book's moneyline, puck line and total on the NHL games
  within the next day and a half, from BettingPros, into the owner's sealed
  market record beside football's (`atlas/owner/market.py`);
* **player props**: every book's line on the NHL player markets, PrizePicks
  among them, into their own sealed record (``tracking/owner_props/``, one file
  per ISO week, appended on change), at most once an hour.

The log carries counts only: games matched, markets found, lines and books,
players per prop market and how many PrizePicks lists. Never a line or a
price. ESPN's DraftKings line and the finals come through the poll
(`atlas/live/provider.py`); this is the whole market behind them.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from atlas.owner import sealed
from atlas.sources import bettingpros as bp
from atlas.util import get_logger

LOG = get_logger(__name__)

EASTERN = ZoneInfo("America/New_York")
SPORT = "nhl"
#: Games whose puck drop is this close are captured: tonight's, and tomorrow's openers.
AHEAD = timedelta(hours=36)
#: The game markets, as the owner board names them.
GAME_MARKETS = ("moneyline", "spread", "total")
#: The player markets wanted, by the slugs BettingPros is expected to give them. The first
#: capture's log says which exist; a slug not in the catalogue is simply not asked for.
PROP_SLUGS = ("shots-on-goal", "points", "goals", "assists", "saves", "blocked-shots", "power-play-points",
              "hits", "goals-against", "anytime-goal", "first-goal")
#: Words that mark a catalogue slug as a player market worth naming in the log when it is not wanted.
PROP_WORDS = ("shot", "point", "goal", "assist", "save", "block", "hit", "faceoff", "penalt", "time-on-ice")
#: Props are fetched at most this often, and at most this many pages at a time.
PROP_EVERY = timedelta(minutes=50)
PROP_PAGES = 40
PROP_KEYS = ["sport", "event_id", "market", "player_key", "selection", "book_id"]
PROP_COLUMNS = ["captured_at", "sport", "event_id", "game_id", "market", "player_key", "player", "position", "team",
                "selection", "book_id", "line", "cost", "updated", "main"]


def props_path() -> Path:
    from atlas.live.store import tracking_dir

    return tracking_dir() / "owner_props"


# ---------------------------------------------------------------------------
# Games and game lines
# ---------------------------------------------------------------------------


def ahead(games: pd.DataFrame, now: datetime) -> pd.DataFrame:
    """ESPN's NHL games not yet started, puck drop within :data:`AHEAD`."""
    if games.empty or "sport" not in games:
        return games.iloc[0:0]
    g = games[games["sport"].astype(str) == SPORT].copy()
    kick = pd.to_datetime(g["kickoff"], utc=True, errors="coerce")
    g = g[(kick > pd.Timestamp(now)) & (kick <= pd.Timestamp(now) + AHEAD)]
    return g.assign(sport=SPORT).reset_index(drop=True)


def days_of(games: pd.DataFrame) -> list[str]:
    """The Eastern dates the games fall on, as BettingPros lists events."""
    kick = pd.to_datetime(games["kickoff"], utc=True, errors="coerce").dropna()
    return sorted({k.tz_convert(EASTERN).strftime("%Y-%m-%d") for k in kick})


def catalogue(client: bp.Client) -> list[dict]:
    try:
        return bp.markets(client, SPORT)
    except Exception as error:  # noqa: BLE001 - the type only
        LOG.warning("nhl capture: no market catalogue (%s)", type(error).__name__)
        return []


def game_ids(listed: list[dict]) -> dict[str, int]:
    """{moneyline/spread/total: market id} from the catalogue, by :data:`bp.GAME_SLUGS`."""
    by_slug = {str(m.get("slug") or ""): int(m["id"]) for m in listed if m.get("id") is not None}
    out = {}
    for market, slugs in bp.GAME_SLUGS.items():
        hit = next((by_slug[s] for s in slugs if s in by_slug), None)
        if hit is not None:
            out[market] = hit
    return out


def capture_lines(client: bp.Client, games: pd.DataFrame, listed: list[dict],
                  now: datetime) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Every book's current line on the games ahead: (lines with ``game_id``, matched events)."""
    from atlas.owner.board import match_events

    empty = (pd.DataFrame(columns=[*bp.LINE_COLUMNS, "game_id"]), pd.DataFrame(columns=[*bp.EVENT_COLUMNS, "game_id"]))
    if games.empty:
        return empty
    listed_events = []
    for day in days_of(games):
        try:
            listed_events.append(bp.events_on(client, SPORT, day))
        except Exception as error:  # noqa: BLE001 - the type only
            LOG.warning("nhl capture: %s events not fetched (%s)", day, type(error).__name__)
    ev = pd.concat(listed_events, ignore_index=True) if listed_events else pd.DataFrame(columns=bp.EVENT_COLUMNS)
    pairs = match_events(games, ev.assign(sport=SPORT))
    ids = game_ids(listed)
    LOG.info("nhl capture: %d games ahead, %d listed, %d matched; game markets found: %s", len(games), len(ev),
             len(pairs), ", ".join(sorted(ids)) or "none")
    if pairs.empty or not ids:
        return empty
    stamp = now.replace(microsecond=0).isoformat()
    found = bp.offers(client, SPORT, pairs["event_id"].tolist(), markets=GAME_MARKETS, captured_at=stamp,
                      market_ids=ids)
    found = found.merge(pairs, on="event_id", how="inner")
    books = found.loc[bp.takeable(found), "book_id"].nunique() if len(found) else 0
    LOG.info("nhl capture: %d lines, %d books", len(found), books)
    return found, ev.merge(pairs, on="event_id", how="inner")


# ---------------------------------------------------------------------------
# Player props
# ---------------------------------------------------------------------------


def prop_ids(listed: list[dict]) -> dict[int, str]:
    """{market id: slug} for the wanted player markets the catalogue has."""
    return {int(m["id"]): str(m["slug"]) for m in listed
            if str(m.get("slug") or "") in PROP_SLUGS and m.get("id") is not None}


def unwanted(listed: list[dict]) -> list[str]:
    """Catalogue slugs that look like player markets and are not asked for: named in the log so the
    wanted list can be put right after the first capture."""
    slugs = {str(m.get("slug") or "") for m in listed}
    return sorted(s for s in slugs if s not in PROP_SLUGS and any(w in s for w in PROP_WORDS))


def describe(props: pd.DataFrame, events: int) -> str:
    """Counts only: per market the players, the books quoting them, and the players PrizePicks lists."""
    if props.empty:
        return f"nhl props: nothing on {events} events"
    parts = []
    for market, part in props.groupby("market"):
        pp = part[part["book_id"] == bp.PRIZEPICKS]["player_key"].nunique()
        parts.append(f"{market} {part['player_key'].nunique()} players, {part['book_id'].nunique()} books, "
                     f"PrizePicks {pp}")
    return f"nhl props on {props['event_id'].nunique()} of {events} events: " + "; ".join(parts)


def load_props(passphrase: str, where: Path | None = None) -> pd.DataFrame:
    rows = sealed.load(where or props_path(), passphrase)
    out = pd.DataFrame(rows, columns=PROP_COLUMNS) if rows else pd.DataFrame(columns=PROP_COLUMNS)
    for c in ("line", "cost", "book_id", "event_id"):
        out[c] = pd.to_numeric(out[c], errors="coerce")
    return out


def due(record: pd.DataFrame, now: datetime) -> bool:
    """Whether an hour has passed since the last props capture."""
    if record.empty:
        return True
    last = pd.to_datetime(record["captured_at"], utc=True, errors="coerce").max()
    return pd.isna(last) or pd.Timestamp(now) - last >= PROP_EVERY


def append_props(record: pd.DataFrame, fresh: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Rows of ``fresh`` whose line or price differs from that book's last recorded one, or that are new."""
    if fresh.empty:
        return record, fresh.iloc[0:0]
    f = fresh.reindex(columns=PROP_COLUMNS).reset_index(drop=True)
    if record.empty:
        return f, f
    r = record.assign(_t=pd.to_datetime(record["captured_at"], utc=True, errors="coerce")).sort_values(
        "_t", kind="stable")
    last = r.groupby(PROP_KEYS, as_index=False).tail(1).drop(columns="_t")
    key = lambda d: d[PROP_KEYS].astype(str).agg("|".join, axis=1)  # noqa: E731
    held = dict(zip(key(last), zip(last["line"], last["cost"], strict=True), strict=True))
    changed = []
    for k, line, cost in zip(key(f), f["line"], f["cost"], strict=True):
        prev = held.get(k)
        changed.append(prev is None or not (_same(prev[0], line) and _same(prev[1], cost)))
    added = f[np.array(changed, dtype=bool)]
    if added.empty:
        return record, added
    return pd.concat([record.reindex(columns=PROP_COLUMNS), added], ignore_index=True), added


def _same(a, b) -> bool:
    a, b = pd.to_numeric(a, errors="coerce"), pd.to_numeric(b, errors="coerce")
    return bool(pd.isna(a) and pd.isna(b)) or bool(a == b)


def week_file(where: Path, captured_at) -> Path:
    t = pd.Timestamp(captured_at)
    t = t.tz_localize("UTC") if t.tzinfo is None else t
    year, week, _ = t.isocalendar()
    return where / f"props-{int(year)}-W{int(week):02d}.enc.json"


def seal_props(record: pd.DataFrame, passphrase: str, touched: pd.DataFrame, where: Path | None = None) -> list[Path]:
    """Rewrite the weekly files the added rows fall in."""
    where = where or props_path()
    files = {week_file(where, t) for t in touched["captured_at"].unique()}
    stamp = record["captured_at"]
    out = []
    for f in sorted(files):
        part = record[[week_file(where, t) == f for t in stamp]]
        rows = json.loads(part.reindex(columns=PROP_COLUMNS).to_json(orient="records"))
        out.append(sealed.seal(rows, passphrase, f))
    return out


def capture_props(client: bp.Client, events: pd.DataFrame, listed: list[dict], passphrase: str, now: datetime,
                  where: Path | None = None) -> pd.DataFrame:
    """Every book's line on the NHL player markets for the matched events, sealed; at most hourly.
    Returns what this call fetched (empty when it was not due)."""
    where = where or props_path()
    if events.empty:
        return pd.DataFrame(columns=PROP_COLUMNS)
    record = load_props(passphrase, where)
    if not due(record, now):
        return pd.DataFrame(columns=PROP_COLUMNS)
    slug_of = prop_ids(listed)
    extra = unwanted(listed)
    LOG.info("nhl props: markets found: %s%s", ", ".join(sorted(slug_of.values())) or "none",
             f"; not asked for: {', '.join(extra)}" if extra else "")
    stamp = now.replace(microsecond=0).isoformat()
    got = bp.props(client, SPORT, events["event_id"].astype(int).tolist(), slug_of, max_pages=PROP_PAGES,
                   captured_at=stamp)
    LOG.info(describe(got, len(events)))
    got = got.merge(events[["event_id", "game_id"]], on="event_id", how="inner")
    record, added = append_props(record, got)
    if not added.empty:
        files = seal_props(record, passphrase, added, where)
        LOG.info("nhl props: %d rows added, %d weekly files sealed", len(added), len(files))
    return got


def capture(client: bp.Client, games: pd.DataFrame, passphrase: str, now: datetime, *,
            props_where: Path | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """The NHL's lines and props for the next day and a half. Returns (lines with ``game_id``, matched
    events) for the owner's sealed market record. Never raises."""
    empty = (pd.DataFrame(columns=[*bp.LINE_COLUMNS, "game_id"]), pd.DataFrame(columns=[*bp.EVENT_COLUMNS, "game_id"]))
    try:
        near = ahead(games, now)
        if near.empty:
            return empty
        listed = catalogue(client)
        lines, events = capture_lines(client, near, listed, now)
        capture_props(client, events, listed, passphrase, now, props_where)
        return lines, events
    except Exception as error:  # noqa: BLE001 - the type and the place only: a message could quote a line
        from atlas.util import where

        LOG.warning("nhl capture failed: %s at %s", type(error).__name__, where(error))
        return empty
