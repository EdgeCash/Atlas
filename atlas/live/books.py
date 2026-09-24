"""One name per sportsbook.

ESPN's scoreboard names the book it quotes, and it has spelled the same book
two ways - "DraftKings" and "Draft Kings" - alternating from one poll to the
next. The tracker keys everything by book, so each spelling kept its own line
history and minted its own signal: every opinion was recorded twice, and a
signal's closing line could be the stale last look under its own spelling
while the later line sat under the other.

``canonical`` is applied where a quote enters (`atlas/live/provider.py`), and
``reconcile`` brings the record already written into line, once, at the start
of every poll - a no-op when there is nothing to fix:

* snapshots take the canonical name, so a game's line history is one series;
* of the signals for one game, market and book, the earliest stands - it is
  the opinion Atlas stated first - under the id the canonical name mints, so
  a later poll cannot state it again; the rest were the same opinion recorded
  twice by the feed's spelling, and are removed;
* a grade follows its signal to the new id; a removed signal's grade goes too.
"""

from __future__ import annotations

import re

from atlas.live.audit import signal_uuid
from atlas.util import get_logger

LOG = get_logger(__name__)

#: Spellings reduced to lower-case letters and digits, and the name kept.
ALIASES = {"draftkings": "DraftKings"}


def canonical(name):
    if not isinstance(name, str):
        return name
    return ALIASES.get(re.sub(r"[^a-z0-9]", "", name.lower()), name)


def reconcile(store) -> dict:
    """Bring the stored snapshots, signals and grades onto one name per book."""
    out = {"snapshots_renamed": 0, "signals_removed": 0, "signals_reissued": 0, "grades_moved": 0,
           "grades_cleared": 0}
    merged: set[str] = set()

    snaps = store.read("snapshots")
    if len(snaps):
        names = snaps["book"].map(canonical)
        changed = names != snaps["book"]
        if changed.any():
            from atlas.live.store import KEYS

            merged = set(snaps.loc[changed, "game_id"].astype(str))
            snaps = snaps.assign(book=names).sort_values("captured_at", kind="stable")
            # As an upsert would have kept it: the latest look at each line and price.
            store.write("snapshots", snaps.drop_duplicates(KEYS["snapshots"], keep="last"))
            out["snapshots_renamed"] = int(changed.sum())

    signals = store.read("signals")
    grades = store.read("grades")
    move: dict[str, str] = {}
    if len(signals):
        names = signals["book"].map(canonical)
        ids = [signal_uuid(g, m, b) for g, m, b in zip(signals["game_id"], signals["market"], names, strict=True)]
        if not (names == signals["book"]).all() or list(signals["signal_id"].astype(str)) != ids:
            s = signals.assign(book=names, new_id=ids).sort_values(["created_at", "signal_id"], kind="stable")
            first = ~s.duplicated(["game_id", "market", "book"], keep="first")
            kept = s[first]
            out["signals_removed"] = int((~first).sum())
            out["signals_reissued"] = int((kept["new_id"] != kept["signal_id"].astype(str)).sum())
            move = dict(zip(kept["signal_id"].astype(str), kept["new_id"], strict=True))
            store.write("signals", kept.assign(signal_id=kept["new_id"]).drop(columns=["new_id"]))
            signals = store.read("signals")

    if len(grades) and (move or merged):
        g = grades.assign(signal_id=grades["signal_id"].astype(str))
        if move:
            g = g[g["signal_id"].isin(move)]
            out["grades_moved"] = int((g["signal_id"].map(move) != g["signal_id"]).sum())
            g = g.assign(signal_id=g["signal_id"].map(move))
        if merged:
            # Graded against one spelling's history: graded again, by the same poll, against the whole of it.
            game = signals.assign(signal_id=signals["signal_id"].astype(str)).set_index("signal_id")["game_id"]
            stale = g["signal_id"].map(game).astype(str).isin(merged)
            out["grades_cleared"] = int(stale.sum())
            g = g[~stale]
        store.write("grades", g)
    if any(out.values()):
        LOG.info("book names reconciled: %s", out)
    return out
