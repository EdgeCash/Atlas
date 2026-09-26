"""The day's parlays: same-book combinations of the board's positive-EV legs, compounded honestly.

A parlay adds no information a single bet lacks. Its expected value is the
product of its legs' decimal odds times the product of their probabilities,
minus one, when the legs come from different games priced independently; the
edges compound and so does the variance. What a parlay does offer is a way to
put several of the board's edges on one ticket at one book, at a payout the
books price multiplicatively across games, which is the one place a small
edge per leg becomes a large edge per ticket.

So, from the board's legs (`atlas/owner/board.py`: every takeable book's price
on every side, with the probability the board uses for it):

* the day's **candidates**: sides with positive expected value by the board's
  measure (Atlas EV on totals, price edge on spreads), from games kicking off
  today Eastern, or on the next day with games; one leg per game at a book;
* **parlays** of two or three legs at one book, different games only (never
  a same-game parlay, which the books price on correlations this does not
  model), the best few by expected value;
* each with its decimal and American odds, the probability it hits, its
  expected value, a quarter-Kelly stake, and the age of its oldest quote,
  because a book may re-price a stale leg in its parlay builder;
* a sealed **record** (``tracking/owner_parlays/``): the day's set logged
  once, at the first run at or after 10:00 Eastern on that day (the curated
  plays' rule v3 chooses at the same moment), at the odds shown then; graded
  when every leg's game is final, a pushed leg dropped and the odds reduced,
  as the books settle it. A fixed moment, so the record is one decision a
  day and not whatever happened to rank first at each poll.

Only inside the owner page's ciphertext, like the board.
"""

from __future__ import annotations

import itertools
import json
import math
import uuid
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from atlas.owner import paper, sealed
from atlas.sources import bettingpros as bp
from atlas.util import get_logger

LOG = get_logger(__name__)

NAMESPACE = uuid.UUID("3d9c6b2e-5a1f-4c8e-9b7d-2e4f6a8c0d13")
COLUMNS = ["parlay_id", "formed_at", "day", "book_id", "n_legs", "legs", "season", "week", "first_kickoff",
           "last_kickoff", "dec_odds", "american", "p_hit", "ev", "kelly"]
LEG_KEYS = ["game_id", "market", "side", "line", "cost", "p", "kickoff", "label"]

#: Legs per parlay, legs a book contributes (best first), parlays shown, and the floor.
MAX_LEGS = 3
PER_BOOK = 6
MAX_PARLAYS = 6
MIN_EV = 0.0
#: The stake shown: this fraction of Kelly, on a bankroll of one.
KELLY_FRACTION = 0.25
#: A quote older than this is flagged: the book may have moved by now.
STALE_MINUTES = 90
#: The day's set is logged at the first run at or after this hour, Eastern, on that day.
LOG_HOUR = 10
MIN_GRADED = 30


def path() -> Path:
    from atlas.live.store import tracking_dir

    return tracking_dir() / "owner_parlays"


def decimal(cost: float) -> float:
    return 1.0 + paper.payout(float(cost))


def american(dec: float) -> float:
    return (dec - 1.0) * 100.0 if dec >= 2.0 else -100.0 / (dec - 1.0)


def day_of(ts) -> str:
    """The Eastern calendar day a moment falls on."""
    from atlas.owner.board import EASTERN

    t = pd.Timestamp(ts)
    t = t.tz_localize("UTC") if t.tzinfo is None else t
    return t.tz_convert(EASTERN).strftime("%Y-%m-%d")


def candidates(legs: pd.DataFrame, now: datetime) -> pd.DataFrame:
    """The day's legs: upcoming, positive expected value by the board's measure, at most one per game
    at each book (its best side and market), on the Eastern day of ``now`` when it has any, else the
    next day with games."""
    if legs.empty:
        return legs.assign(score=pd.Series(dtype=float), p=pd.Series(dtype=float), day=pd.Series(dtype=str))
    t = legs.copy()
    t["kickoff"] = pd.to_datetime(t["kickoff"], utc=True, errors="coerce")
    t = t[t["kickoff"] > pd.Timestamp(now)]
    total = t["market"] == "total"
    t["score"] = np.where(total & t["ev_atlas"].notna(), t["ev_atlas"], t["ev_price"])
    t["p"] = np.where(total & t["p_atlas"].notna(), t["p_atlas"], t["p_fair"])
    t = t[(t["score"] > MIN_EV) & t["p"].between(0.05, 0.95)]
    if t.empty:
        return t.assign(day=pd.Series(dtype=str))
    t["day"] = t["kickoff"].map(day_of)
    today = day_of(now)
    day = today if (t["day"] == today).any() else t["day"].min()
    t = t[t["day"] == day].sort_values("score", ascending=False)
    return t.drop_duplicates(["book_id", "game_id"], keep="first").reset_index(drop=True)


def parlay_id(book_id, legs: list[dict]) -> str:
    key = "|".join(sorted(f"{lg['game_id']}:{lg['market']}:{lg['side']}" for lg in legs))
    return str(uuid.uuid5(NAMESPACE, f"{int(book_id)}|{key}"))


def _age_minutes(updated, now: datetime) -> float:
    t = pd.to_datetime(updated, utc=True, errors="coerce")
    return float("nan") if pd.isna(t) else (pd.Timestamp(now) - t).total_seconds() / 60.0


def combine(cands: pd.DataFrame, names: dict, now: datetime, *, max_legs: int = MAX_LEGS,
            per_book: int = PER_BOOK, top: int = MAX_PARLAYS) -> pd.DataFrame:
    """Every two- and three-leg parlay of a book's best legs (different games), the best ``top`` by
    expected value across books. One row per parlay; ``legs`` is its legs as records."""
    out = []
    if cands.empty:
        return pd.DataFrame(columns=[*COLUMNS, "oldest_quote"])
    for book_id, part in cands.groupby("book_id"):
        pool = part.sort_values("score", ascending=False).head(per_book)
        rows = list(pool.itertuples())
        for n in range(2, min(max_legs, len(rows)) + 1):
            for combo in itertools.combinations(rows, n):
                dec = float(np.prod([decimal(r.cost) for r in combo]))
                p_hit = float(np.prod([float(r.p) for r in combo]))
                e = dec * p_hit - 1.0
                if not (math.isfinite(e) and e > MIN_EV):
                    continue
                legs = [{"game_id": str(r.game_id), "market": r.market, "side": r.side, "line": float(r.line),
                         "cost": float(r.cost), "p": round(float(r.p), 4),
                         "kickoff": pd.Timestamp(r.kickoff).strftime("%Y-%m-%dT%H:%M:%SZ"),
                         "label": names.get(str(r.game_id), str(r.game_id))} for r in combo]
                kicks = [pd.Timestamp(r.kickoff) for r in combo]
                ages = [_age_minutes(r.updated, now) for r in combo]
                out.append({
                    "parlay_id": parlay_id(book_id, legs), "formed_at": pd.Timestamp(now).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "day": str(combo[0].day), "book_id": int(book_id), "n_legs": n, "legs": json.dumps(legs),
                    "season": combo[0].season, "week": combo[0].week,
                    "first_kickoff": min(kicks).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "last_kickoff": max(kicks).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "dec_odds": round(dec, 4), "american": round(american(dec)), "p_hit": round(p_hit, 4),
                    "ev": round(e, 4), "kelly": round(max(0.0, (dec * p_hit - 1.0) / (dec - 1.0)), 4),
                    "oldest_quote": max(a for a in ages if math.isfinite(a)) if any(math.isfinite(a) for a in ages) else float("nan"),
                })
    if not out:
        return pd.DataFrame(columns=[*COLUMNS, "oldest_quote"])
    table = pd.DataFrame(out).sort_values(["ev", "n_legs"], ascending=[False, True])
    # The same legs at several books are one ticket: shown once, at the book that pays best for them.
    table["_set"] = [_leg_set(json.loads(x)) for x in table["legs"]]
    table = table.drop_duplicates("_set", keep="first").drop(columns="_set")
    return table.head(top).reset_index(drop=True)


def _leg_set(legs: list[dict]) -> str:
    return "|".join(sorted(f"{lg['game_id']}:{lg['market']}:{lg['side']}" for lg in legs))


# ---------------------------------------------------------------------------
# The record
# ---------------------------------------------------------------------------


def load(passphrase: str, where: Path | None = None) -> pd.DataFrame:
    rows = sealed.load(where or path(), passphrase)
    return pd.DataFrame(rows, columns=COLUMNS) if rows else pd.DataFrame(columns=COLUMNS)


def due(record: pd.DataFrame, chosen: pd.DataFrame, now: datetime) -> bool:
    """Is this the run that logs the day's set: at or after :data:`LOG_HOUR` Eastern on the day the
    parlays are for, and nothing logged for that day yet."""
    from atlas.owner.board import EASTERN

    if chosen.empty:
        return False
    local = pd.Timestamp(now).tz_convert(EASTERN)
    day = str(chosen["day"].iloc[0])
    if day != local.strftime("%Y-%m-%d") or local.hour < LOG_HOUR:
        return False
    return not (len(record) and (record["day"].astype(str) == day).any())


def log(record: pd.DataFrame, chosen: pd.DataFrame) -> tuple[pd.DataFrame, set]:
    """Add the parlays not yet logged, at the odds shown; a logged parlay is never revised."""
    if chosen.empty:
        return record, set()
    fresh = chosen.reindex(columns=COLUMNS)
    new = fresh[~fresh["parlay_id"].isin(set(record["parlay_id"]))] if len(record) else fresh
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
        names = [lg.get("label") for r in rows for lg in json.loads(r.get("legs") or "[]")]
        out.append(sealed.seal(rows, passphrase, sealed.week_file(where, season, week), names=names))
    return out


def leg_outcome(leg: dict, finals: pd.DataFrame) -> str:
    """win, loss, push, or open, from the final score."""
    f = finals[finals["game_id"].astype(str) == str(leg["game_id"])]
    if f.empty:
        return "open"
    total, margin = float(f["final_total"].iloc[0]), float(f["final_margin"].iloc[0])
    line = float(leg["line"])
    if leg["market"] == "total":
        edge = (total - line) * (1.0 if leg["side"] == "over" else -1.0)
    else:
        own = margin if leg["side"] == "home" else -margin
        edge = own + line
    return "win" if edge > 0 else ("loss" if edge < 0 else "push")


def grade(record: pd.DataFrame, finals: pd.DataFrame) -> pd.DataFrame:
    """Each parlay with its outcome and profit on one unit: a loss on any leg loses; every leg won pays
    the product of the winning legs' decimal odds, a pushed leg dropped; all pushed is a push; a leg
    still to play leaves it open."""
    outcomes, profits, settled = [], [], []
    for r in record.itertuples():
        legs = json.loads(r.legs or "[]")
        results = [leg_outcome(lg, finals) for lg in legs]
        if "loss" in results:
            outcome, profit = "loss", -1.0
        elif "open" in results:
            outcome, profit = "open", float("nan")
        elif all(x == "push" for x in results):
            outcome, profit = "push", 0.0
        else:
            paid = float(np.prod([decimal(lg["cost"]) for lg, x in zip(legs, results, strict=True) if x == "win"]))
            outcome, profit = "win", paid - 1.0
        outcomes.append(outcome)
        profits.append(profit)
        settled.append("-".join(x[0] for x in results))
    return record.assign(outcome=outcomes, profit=profits, legs_result=settled)


# ---------------------------------------------------------------------------
# The owner page's view
# ---------------------------------------------------------------------------


def _leg_text(lg: dict) -> str:
    line = f"{lg['line']:g}" if lg["market"] == "total" else f"{lg['line']:+g}"
    return f"{lg['label']}: {lg['side']} {line} ({lg['cost']:+.0f}) · P {lg['p']:.0%}"


def _day_label(day: str) -> str:
    return pd.Timestamp(day).strftime("%a %b %-d")


def section(chosen: pd.DataFrame, graded: pd.DataFrame, now: datetime) -> list[dict]:
    from atlas.owner.board import _eastern

    logged = set(graded["parlay_id"]) if len(graded) else set()
    rows = []
    for r in chosen.itertuples():
        legs = json.loads(r.legs)
        age = "" if not math.isfinite(r.oldest_quote) else (
            f" · oldest quote {r.oldest_quote:.0f} min" + (" (stale)" if r.oldest_quote > STALE_MINUTES else ""))
        rows.append([bp.book_name(r.book_id), " / ".join(_leg_text(lg) for lg in legs),
                     f"{r.american:+.0f} ({r.dec_odds:.2f}×)",
                     f"P(hit) {r.p_hit:.1%} · EV {r.ev:+.1%} · ¼-Kelly {KELLY_FRACTION * r.kelly:.1%}{age}"
                     + (" · logged" if r.parlay_id in logged else "")])
    day = _day_label(chosen["day"].iloc[0]) if not chosen.empty else _day_label(day_of(now))
    tables = [{"title": f"Parlays for {day}: {len(rows)} with positive expected value at one book",
               "head": ["Book", "Legs", "Odds", "P(hit) · EV · stake"],
               "rows": rows or [["No two positive-EV legs share a book today.", "", "", ""]]}]
    done = graded[graded["outcome"].isin(["win", "loss", "push"])] if len(graded) else graded
    if len(graded):
        wins = int((done["outcome"] == "win").sum()) if len(done) else 0
        losses = int((done["outcome"] == "loss").sum()) if len(done) else 0
        pushes = int((done["outcome"] == "push").sum()) if len(done) else 0
        units = float(pd.to_numeric(done["profit"], errors="coerce").sum()) if len(done) else 0.0
        decided = wins + losses
        expected = float(pd.to_numeric(done.loc[done["outcome"] != "push", "p_hit"], errors="coerce").mean()) if decided else float("nan")
        rows = [["Parlays logged", str(len(graded))], ["Graded", str(len(done))],
                ["Won-lost-push", f"{wins}-{losses}-{pushes}"],
                ["Hit rate (expected)", f"{wins / decided:.1%} ({expected:.1%})" if decided else "–"],
                ["Units", paper._num(units)], ["Per parlay", paper._num(units / len(done), "{:+.1%}") if len(done) else "–"]]
        tables.append({"title": "Parlay record (one unit each, at the odds shown when logged)", "head": ["", ""], "rows": rows})
        latest = graded[graded["outcome"] != "open"].sort_values("last_kickoff", ascending=False).head(8)
        if len(latest):
            tables.append({"title": "Latest graded parlays", "head": ["Book", "Legs", "Odds", "Result"],
                           "rows": [[bp.book_name(x.book_id), " / ".join(_leg_text(lg) for lg in json.loads(x.legs)),
                                     f"{x.american:+.0f}", f"{x.outcome} {x.profit:+.2f} ({x.legs_result})"]
                                    for x in latest.itertuples()]})
    notes = [
        "A parlay's edge is its legs' edges compounded. With legs from different games priced independently, its "
        "expected value is the product of the legs' decimal odds times the product of their probabilities, minus one: "
        "it adds nothing a single bet lacks, and trades a lower hit rate for a higher payout at more variance. Its "
        "one real use is putting several of the board's edges on one ticket at one book, where the payout compounds.",
        f"Legs are the board's positive-EV sides (Atlas EV on totals, price edge on spreads) from games kicking off "
        f"today Eastern, or the next day with games: one per game at a book, the best {PER_BOOK} per book, "
        f"{MAX_LEGS} legs at most. Never a same-game parlay: the books price those on correlations this does not model.",
        f"The stake is a quarter of Kelly on a bankroll of one. The age of the oldest quote is shown because a book "
        f"may re-price a stale leg in its parlay builder; past {STALE_MINUTES} minutes it is marked stale.",
        f"The day's set is logged once, at the first run from {LOG_HOUR}:00 ET on that day, at the odds shown then "
        f"(marked logged); the table above is live and keeps moving. Each is graded when every leg's game is final: a "
        f"pushed leg drops out and the odds reduce, as the books settle it. Nothing is read from fewer than "
        f"{MIN_GRADED} graded. Built {_eastern(now)} ET.",
    ]
    return [{"title": "Daily parlays", "notes": notes, "tables": tables}]


def build(legs: pd.DataFrame, finals: pd.DataFrame, names: dict, passphrase: str, now: datetime,
          where: Path | None = None) -> list[dict]:
    """The day's parlays from the board's legs: chosen, logged once, graded, and shown. Never raises."""
    try:
        chosen = combine(candidates(legs, now), names, now)
        record = load(passphrase, where)
        record, weeks = log(record, chosen) if due(record, chosen, now) else (record, set())
        if weeks:
            seal(record, passphrase, weeks, where)
            LOG.info("parlays: %d logged", len(chosen))
        graded = grade(record, finals) if len(record) else record.assign(outcome=pd.Series(dtype=str),
                                                                        profit=pd.Series(dtype=float),
                                                                        legs_result=pd.Series(dtype=str))
        return section(chosen, graded, now)
    except Exception as error:  # noqa: BLE001 - the type only: a message could quote a line
        LOG.error("parlays not built: %s", type(error).__name__)
        return [{"title": "Daily parlays", "notes": [f"This run could not build the parlays ({type(error).__name__})."],
                 "tables": []}]
