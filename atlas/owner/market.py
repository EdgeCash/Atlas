"""The owner's multi-book market record: every book's line on every game, sealed.

BettingPros' lines are licensed to the owner and must never appear in the
clear in this public repository or on a public page. This keeps them the way
the curated plays are kept (`atlas/owner/sealed.py`): one file per ISO week
of capture in ``tracking/owner_market/``, compressed and sealed with the
owner key, appended on change only, so a book whose line has not moved
earns no new row.

What is kept per row is the minimum the board needs later: when it was
seen, which game, market, selection and book, the line and price, and the
selection's opener. Links, request echoes and anything else the API sends
are not read (`atlas/sources/bettingpros.py`).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from atlas.owner import sealed
from atlas.util import get_logger

LOG = get_logger(__name__)

KEYS = ["sport", "event_id", "market", "selection", "book_id"]
COLUMNS = ["captured_at", "sport", "game_id", "event_id", "market", "selection", "participant", "book_id", "line",
           "cost", "updated", "is_off", "open_line", "open_cost", "open_book", "open_created"]


def path() -> Path:
    from atlas.live.store import tracking_dir

    return tracking_dir() / "owner_market"


def week_file(where: Path, captured_at) -> Path:
    t = pd.Timestamp(captured_at)
    t = t.tz_localize("UTC") if t.tzinfo is None else t
    year, week, _ = t.isocalendar()
    return where / f"market-{int(year)}-W{int(week):02d}.enc.json"


def load(passphrase: str, where: Path | None = None) -> pd.DataFrame:
    rows = sealed.load(where or path(), passphrase)
    out = pd.DataFrame(rows, columns=COLUMNS) if rows else pd.DataFrame(columns=COLUMNS)
    for c in ("line", "cost", "open_line", "open_cost", "open_book", "book_id", "event_id"):
        out[c] = pd.to_numeric(out[c], errors="coerce")
    return out


def latest(rows: pd.DataFrame) -> pd.DataFrame:
    """Each book's last recorded line per game, market and selection."""
    if rows.empty:
        return rows
    r = rows.assign(_t=pd.to_datetime(rows["captured_at"], utc=True, errors="coerce")).sort_values("_t", kind="stable")
    return r.groupby(KEYS, as_index=False).tail(1).drop(columns="_t")


def append(record: pd.DataFrame, fresh: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Rows of ``fresh`` whose line or price differs from each book's last recorded one (or that are new).
    Returns the record with them added, and the rows added."""
    if fresh.empty:
        return record, fresh.iloc[0:0]
    f = fresh.reindex(columns=COLUMNS)
    if record.empty:
        return f.reset_index(drop=True), f
    last = latest(record).set_index(KEYS)
    key = pd.MultiIndex.from_frame(f[KEYS])
    known = key.isin(last.index)
    prev_line = pd.Series(np.nan, index=f.index)
    prev_cost = pd.Series(np.nan, index=f.index)
    prev_off = pd.Series(False, index=f.index)
    if known.any():
        prev = last.loc[key[known]]
        prev_line.loc[known] = prev["line"].to_numpy(dtype=float)
        prev_cost.loc[known] = prev["cost"].to_numpy(dtype=float)
        prev_off.loc[known] = prev["is_off"].astype(bool).to_numpy()
    changed = (~known) | (pd.to_numeric(f["line"], errors="coerce") != prev_line) \
        | (pd.to_numeric(f["cost"], errors="coerce") != prev_cost) | (f["is_off"].astype(bool) != prev_off)
    added = f[changed]
    if added.empty:
        return record, added
    return pd.concat([record.reindex(columns=COLUMNS), added], ignore_index=True), added


def seal(record: pd.DataFrame, passphrase: str, touched: pd.DataFrame, where: Path | None = None) -> list[Path]:
    """Rewrite the weekly files the added rows fall in."""
    where = where or path()
    out = []
    files = {week_file(where, t) for t in touched["captured_at"].unique()}
    stamp = pd.to_datetime(record["captured_at"], utc=True, errors="coerce")
    for f in sorted(files):
        part = record[[week_file(where, t) == f for t in stamp]]
        rows = json.loads(part.reindex(columns=COLUMNS).to_json(orient="records"))
        out.append(sealed.seal(rows, passphrase, f))
    LOG.info("owner market: %d rows added, %d weekly files sealed", len(touched), len(out))
    return out


def closing(rows: pd.DataFrame, kickoffs: pd.Series) -> pd.DataFrame:
    """Each book's last recorded line before kickoff per game, market and selection, for games that
    have kicked off. ``kickoffs`` maps ``game_id`` (as str) to a UTC kickoff."""
    if rows.empty:
        return rows.iloc[0:0]
    r = rows.copy()
    r["_t"] = pd.to_datetime(r["captured_at"], utc=True, errors="coerce")
    r["_k"] = r["game_id"].astype(str).map(kickoffs)
    r = r[r["_t"] <= r["_k"]].sort_values("_t", kind="stable")
    return r.groupby(KEYS, as_index=False).tail(1).drop(columns=["_t", "_k"])
