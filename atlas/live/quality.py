"""Track 1: data quality checks over the live record.

Every check answers one question about one row and returns an exception if the
answer is wrong. Nothing here repairs anything: a tracker that silently fixes
its own inputs cannot be trusted to report what it saw. Exceptions are
recorded, counted and published; correcting them is a human decision.

Severity is binary and means what it says:

``blocking``  the row is not evidence and must not reach the scorecard
``warning``   the row is usable but something is off and should be looked at
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from atlas.live.store import Store
from atlas.util import get_logger

LOG = get_logger(__name__)

#: Markets Atlas is allowed to have an opinion on. Anything else in the record
#: is a provider change that nobody noticed.
VALID_MARKETS = ("margin", "total")

#: A line outside these bounds is a parsing error, not a market.
BOUNDS = {"margin": (-80.0, 80.0), "total": (20.0, 110.0)}

#: A price outside this band is not a standard two-way market.
PRICE_BOUNDS = (-400.0, 400.0)


@dataclass(frozen=True)
class Exception_:
    """One failed check on one row."""

    check: str
    severity: str
    signal_id: str
    detail: str


def _rows(frame: pd.DataFrame, mask, check: str, severity: str,
          detail: str) -> list[Exception_]:
    # A numpy comparison arrives here as an ndarray; align it before use so a
    # check can never silently select the wrong rows.
    mask = pd.Series(np.asarray(mask), index=frame.index)
    return [
        Exception_(check, severity, str(row.signal_id), detail)
        for row in frame[mask.fillna(True)].itertuples(index=False)
    ]


def check_signals(store: Store | None = None) -> pd.DataFrame:
    """Run every check over every signal. Returns one row per exception."""
    store = store or Store.open()
    signals = store.read("signals")
    if signals.empty:
        return pd.DataFrame(columns=["check", "severity", "signal_id", "detail"])

    game_rows = store.read("games")
    games = set(game_rows["game_id"].astype(str))
    snapshots = store.read("snapshots")
    quoted = set(
        snapshots[["game_id", "book", "market"]].astype(str).agg("|".join, axis=1)
    ) if not snapshots.empty else set()

    frame = signals.copy()
    for column in ("open_line", "entry_line", "entry_price", "atlas_number",
                   "disagreement", "game_id"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")

    found: list[Exception_] = []

    # The four existence checks the brief names.
    found += _rows(frame, ~frame["game_id"].astype("Int64").astype(str).isin(games),
                   "game exists", "blocking",
                   "signal references a game not in tracking/games.csv")
    found += _rows(frame, ~frame["market"].isin(VALID_MARKETS),
                   "market exists", "blocking",
                   f"market is not one of {VALID_MARKETS}")
    found += _rows(frame, frame["open_line"].isna(),
                   "opening line exists", "warning",
                   "no opening line recorded; the comparison with Phase 4 is lost")
    found += _rows(frame, frame["entry_line"].isna(),
                   "entry line exists", "blocking",
                   "no entry line; CLV cannot be graded")

    # A signal whose line was never snapshotted cannot be reproduced or graded.
    key = frame[["game_id", "book", "market"]].astype(str).agg("|".join, axis=1)
    found += _rows(frame, ~key.isin(quoted), "line history exists", "blocking",
                   "no snapshot for this game/book/market")

    # A game that has kicked off with no line captured before it can never be
    # graded: without this it would sit under "awaiting kickoff" for ever.
    if not game_rows.empty:
        from atlas.live.grade import closing_lines

        kickoff = pd.to_datetime(game_rows.set_index(game_rows["game_id"].astype(str))["kickoff"],
                                 utc=True, errors="coerce")
        started = frame["game_id"].astype("Int64").astype(str).map(kickoff) <= pd.Timestamp.now(tz="UTC")
        closes = closing_lines(snapshots, game_rows) if not snapshots.empty else pd.DataFrame(
            columns=["game_id", "book", "market"])
        closed = set(closes[["game_id", "book", "market"]].astype(str).agg("|".join, axis=1)) \
            if len(closes) else set()
        key_int = frame["game_id"].astype("Int64").astype(str) + "|" + frame["book"].astype(str) + "|" \
            + frame["market"].astype(str)
        found += _rows(frame, started.fillna(False) & ~key_int.isin(closed), "closing line exists", "warning",
                       "the game has kicked off with no line captured before it; the signal cannot be graded")

    # Plausibility.
    for market, (low, high) in BOUNDS.items():
        block = frame[frame["market"] == market]
        if block.empty:
            continue
        outside = ~block["entry_line"].between(low, high)
        found += _rows(block, outside, "entry line in range", "blocking",
                       f"{market} entry line outside [{low:g}, {high:g}]")
        outside_open = ~block["open_line"].between(low, high) & block["open_line"].notna()
        found += _rows(block, outside_open, "opening line in range", "warning",
                       f"{market} opening line outside [{low:g}, {high:g}]")

    found += _rows(frame, ~frame["entry_price"].between(*PRICE_BOUNDS)
                   & frame["entry_price"].notna(),
                   "entry price in range", "warning",
                   f"price outside [{PRICE_BOUNDS[0]:g}, {PRICE_BOUNDS[1]:g}]")

    # Internal consistency: the stored disagreement must equal the arithmetic.
    implied = frame["atlas_number"] - frame["entry_line"]
    found += _rows(frame, (implied - frame["disagreement"]).abs() > 0.01,
                   "disagreement is consistent", "blocking",
                   "disagreement does not equal atlas_number - entry_line")

    found += _rows(frame, frame["disagreement"] == 0,
                   "signal is an opinion", "blocking",
                   "zero disagreement is not an opinion")

    # Identity.
    found += _rows(frame, frame["signal_id"].duplicated(keep=False),
                   "signal id is unique", "blocking",
                   "duplicate signal id")
    found += _rows(frame, frame["model_version"].isna() | (frame["model_version"] == ""),
                   "model version recorded", "warning",
                   "no model version; the signal cannot be attributed")

    out = pd.DataFrame([vars(e) for e in found])
    if not out.empty:
        LOG.warning("%d data-quality exceptions", len(out))
    return out


def check_grades(store: Store | None = None) -> pd.DataFrame:
    """Grades must reference a real signal and agree with their own inputs."""
    store = store or Store.open()
    grades = store.read("grades")
    if grades.empty:
        return pd.DataFrame(columns=["check", "severity", "signal_id", "detail"])

    signals = store.read("signals").set_index("signal_id")
    frame = grades.copy()
    frame["clv_points"] = pd.to_numeric(frame["clv_points"], errors="coerce")
    frame["close_line"] = pd.to_numeric(frame["close_line"], errors="coerce")

    found: list[Exception_] = []
    orphan = ~frame["signal_id"].astype(str).isin(signals.index.astype(str))
    found += _rows(frame, orphan, "grade references a signal", "blocking",
                   "graded signal is not in tracking/signals.csv")

    joined = frame.join(signals[["entry_line", "direction"]], on="signal_id")
    entry = pd.to_numeric(joined["entry_line"], errors="coerce")
    sign = joined["direction"].map({"over": 1.0, "home": 1.0, "under": -1.0, "away": -1.0})
    implied = (joined["close_line"] - entry) * sign
    found += _rows(frame, (implied - frame["clv_points"]).abs() > 0.01,
                   "clv is consistent", "blocking",
                   "clv_points does not equal (close - entry) * direction")

    expected = np.where(frame["clv_points"] > 0, "beat",
                        np.where(frame["clv_points"] < 0, "lost", "push"))
    found += _rows(frame, frame["result"].to_numpy() != expected,
                   "result matches clv", "blocking",
                   "result label disagrees with clv_points")

    found += _rows(frame, frame["signal_id"].duplicated(keep=False),
                   "one grade per signal", "blocking", "duplicate grade")

    out = pd.DataFrame([vars(e) for e in found])
    if not out.empty:
        LOG.warning("%d grade exceptions", len(out))
    return out


def exceptions(store: Store | None = None) -> pd.DataFrame:
    store = store or Store.open()
    parts = [check_signals(store), check_grades(store)]
    parts = [p for p in parts if not p.empty]
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(
        columns=["check", "severity", "signal_id", "detail"]
    )


def summary(found: pd.DataFrame, store: Store | None = None) -> pd.DataFrame:
    """One row per check, whether or not it fired - a clean bill needs proof."""
    store = store or Store.open()
    signals = len(store.read("signals"))
    grades = len(store.read("grades"))
    counts = found.groupby(["check", "severity"]).size() if not found.empty else {}

    rows = []
    for check, severity, scope in _CHECK_REGISTRY:
        n = int(counts.get((check, severity), 0)) if len(counts) else 0
        total = signals if scope == "signals" else grades
        rows.append({
            "check": check,
            "severity": severity,
            "scope": scope,
            "rows_checked": total,
            "exceptions": n,
            "clean": n == 0,
        })
    return pd.DataFrame(rows)


#: Every check the module runs, so the report can show the ones that passed.
_CHECK_REGISTRY: tuple[tuple[str, str, str], ...] = (
    ("game exists", "blocking", "signals"),
    ("market exists", "blocking", "signals"),
    ("opening line exists", "warning", "signals"),
    ("entry line exists", "blocking", "signals"),
    ("line history exists", "blocking", "signals"),
    ("closing line exists", "warning", "signals"),
    ("entry line in range", "blocking", "signals"),
    ("opening line in range", "warning", "signals"),
    ("entry price in range", "warning", "signals"),
    ("disagreement is consistent", "blocking", "signals"),
    ("signal is an opinion", "blocking", "signals"),
    ("signal id is unique", "blocking", "signals"),
    ("model version recorded", "warning", "signals"),
    ("grade references a signal", "blocking", "grades"),
    ("clv is consistent", "blocking", "grades"),
    ("result matches clv", "blocking", "grades"),
    ("one grade per signal", "blocking", "grades"),
)
