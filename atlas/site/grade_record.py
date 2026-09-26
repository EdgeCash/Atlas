"""The grade record: each card's grade as published, against what happened.

The grade (`atlas/site/grade.py`) says how much weight a card's number
deserves. A grade with no record is a promise, and the product docs say what
the record must be (`ATLAS_FEATURE_ROADMAP.md` §1, `RETENTION_DRIVERS.md`):
calibration, claimed against realised, with the sample size beside it, and
never a win-loss record.

It can only be built from grades published *before* kickoff, so it starts the
day this began recording them. Every site build logs each card still to kick
off (`log`): the first letter it showed, kept, and the latest, overwritten, so
the last row standing at kickoff is what a reader saw last. After the final
score each is graded exactly as the grade's own research history is
(`atlas/models/ncaaf_projection.history`): ``claimed`` is Atlas's
probability for its own side of the spread the card showed, and ``won``
whether that side happened, a push counting half.

Conventions: ``line`` is the card's spread as a home margin, positive when the
home side is favoured (`Card.market_margin`), so the home side covers when
the final margin is above it. ``home_side`` is True when Atlas's probability
of that was at least a half.
"""

from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd

from atlas.util import get_logger

LOG = get_logger(__name__)

TABLE = "card_grades"
LETTERS = ("A+", "A", "B", "C", "D", "F")
#: The grade is fitted on the spread (`grade.GRADED_MARKET`).
MARKET = "margin"
#: Fewer cards than this in a letter and its gap is noise, and the page says so.
MIN_CARDS = 30

FIRST = ["first_letter", "first_score", "first_at"]


def rows(cards, now: datetime) -> pd.DataFrame:
    """One row per graded card still to kick off."""
    out = []
    for card in cards:
        g, p, line = card.grade, card.cover_probability, card.market_margin
        if g is None or p is None or line is None or card.kickoff <= now:
            continue
        at = now.isoformat()
        out.append({
            "sport": card.sport, "game_id": card.game_id, "season": card.season, "week": card.week,
            "kickoff": card.kickoff.isoformat(), "market": MARKET,
            "first_letter": g.letter, "first_score": g.score, "first_at": at,
            "letter": g.letter, "score": g.score, "line": float(line), "atlas": float(card.model_margin),
            "claimed": max(p, 1.0 - p), "home_side": bool(p >= 0.5), "published_at": at,
            "path": card.path,
        })
    return pd.DataFrame(out)


def log(cards, now: datetime, store) -> int:
    """Record this build's grades. A card seen before keeps its first letter;
    everything else is this build's. Returns the cards logged."""
    fresh = rows(cards, now)
    if fresh.empty:
        return 0
    existing = store.read(TABLE)
    if len(existing):
        # The store reads game_id back as a number; compare as text either way.
        seen = existing.assign(game_id=existing["game_id"].astype(str)).set_index(["sport", "game_id"])[FIRST]
        key = pd.MultiIndex.from_frame(fresh[["sport", "game_id"]].astype({"game_id": str}))
        known = key.isin(seen.index)
        for column in FIRST:
            fresh.loc[known, column] = seen.loc[key[known], column].to_numpy()
    store.upsert(TABLE, fresh)
    return len(fresh)


def graded(record: pd.DataFrame, finals: pd.DataFrame) -> pd.DataFrame:
    """Every logged card with a final score, with whether its side happened."""
    if record.empty or finals.empty:
        return record.iloc[0:0].assign(final_margin=[], won=[])
    f = finals.assign(game_id=finals["game_id"].astype(str),
                      final_margin=finals["final_home"].astype(float) - finals["final_away"].astype(float))
    g = record.assign(game_id=record["game_id"].astype(str)).merge(f[["game_id", "final_margin"]], on="game_id")
    home_side = g["home_side"].astype(str).str.lower().isin(["true", "1"])
    diff = g["final_margin"] - g["line"].astype(float)
    g["won"] = np.where(diff == 0, 0.5, np.where(home_side, diff > 0, diff < 0).astype(float))
    return g


def by_letter(g: pd.DataFrame) -> list[dict]:
    """Claimed against realised for each letter, in order, and all together."""
    out = []
    for letter in (*LETTERS, None):
        part = g if letter is None else g[g["letter"] == letter]
        n = len(part)
        claimed = float(part["claimed"].astype(float).mean()) if n else None
        realised = float(part["won"].astype(float).mean()) if n else None
        out.append({"letter": letter or "All", "cards": n, "claimed": claimed, "realised": realised,
                    "gap": None if not n else realised - claimed, "few": n < MIN_CARDS})
    return out


def build(store=None) -> dict[str, list[dict]]:
    """The grade record per sport, for the record page. Never raises."""
    try:
        from atlas.site import record

        if store is None:
            from atlas.live.store import Store

            store = Store.open()
        g = graded(store.read(TABLE), record.all_finals(store))
        return {sport: by_letter(g[g["sport"] == sport]) for sport in ("ncaaf", "nfl")}
    except Exception as error:  # noqa: BLE001 - the site builds without it
        LOG.error("grade record not built: %s", type(error).__name__)
        return {}
