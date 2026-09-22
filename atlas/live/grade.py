"""Track 3: grading a signal against the close.

Three outcomes and no fourth: the market came to Atlas (**beat**), it never
moved off the number Atlas took (**push**), or it went the other way
(**lost**). A push is not a loss - Phase 3 learned that the hard way, where
counting no-move games as losses understated every beat rate by about six
points.

Nothing here knows the score of the football game, and nothing here should.
"""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pandas as pd

from atlas.util import get_logger

LOG = get_logger(__name__)

#: A signal whose entry line had already moved this far toward Atlas's side
#: before Atlas spoke is flagged: that part of the move was never capturable.
#: Gamma's third kill criterion.
EXECUTION_FLAG_POINTS = 0.5


def direction_sign(direction: str) -> float:
    return 1.0 if direction in ("over", "home") else -1.0


def closing_lines(snapshots: pd.DataFrame, games: pd.DataFrame) -> pd.DataFrame:
    """The last line observed at or before kickoff, per game/book/market.

    Falling back to the latest observation of all would quietly grade against
    an in-play number, so a game with no pre-kickoff observation is left
    ungraded rather than graded wrongly.
    """
    if snapshots.empty:
        return pd.DataFrame(columns=["game_id", "book", "market", "close_line"])

    kickoff = games.set_index("game_id")["kickoff"]
    block = snapshots.copy()
    block["captured_ts"] = pd.to_datetime(block["captured_at"], utc=True, errors="coerce")
    block["kickoff_ts"] = pd.to_datetime(
        block["game_id"].map(kickoff), utc=True, errors="coerce"
    )
    block = block[block["captured_ts"] <= block["kickoff_ts"]]
    if block.empty:
        return pd.DataFrame(columns=["game_id", "book", "market", "close_line"])

    block = block.sort_values("captured_ts")
    last = block.groupby(["game_id", "book", "market"], as_index=False).last()
    return last.rename(columns={"line": "close_line"})[
        ["game_id", "book", "market", "close_line"]
    ]


def grade(signals: pd.DataFrame, snapshots: pd.DataFrame, games: pd.DataFrame,
          *, already_graded: set[str] | None = None) -> pd.DataFrame:
    """Grade every signal whose game has kicked off and is not already graded."""
    if signals.empty:
        return pd.DataFrame()

    started = games[_has_started(games)]["game_id"]
    pending = signals[signals["game_id"].isin(set(started))]
    if already_graded:
        pending = pending[~pending["signal_id"].isin(already_graded)]
    if pending.empty:
        return pd.DataFrame()

    closes = closing_lines(snapshots, games)
    merged = pending.merge(closes, on=["game_id", "book", "market"], how="inner")
    merged = merged.dropna(subset=["close_line", "entry_line"])
    if merged.empty:
        return pd.DataFrame()

    sign = merged["direction"].map(direction_sign).astype(float)
    close = merged["close_line"].astype(float)
    entry = merged["entry_line"].astype(float)
    opening = pd.to_numeric(merged["open_line"], errors="coerce")

    out = pd.DataFrame({"signal_id": merged["signal_id"]})
    out["graded_at"] = datetime.now(UTC).replace(microsecond=0).isoformat()
    out["close_line"] = close
    out["clv_points"] = (close - entry) * sign
    out["result"] = _result(out["clv_points"])
    out["clv_from_open"] = (close - opening) * sign
    out["result_from_open"] = _result(out["clv_from_open"])
    out["total_move"] = close - opening
    out["pre_signal_move"] = (entry - opening) * sign
    out["execution_flagged"] = out["pre_signal_move"] >= EXECUTION_FLAG_POINTS
    LOG.info("graded %d signals", len(out))
    return out


def _has_started(games: pd.DataFrame) -> pd.Series:
    completed = games["completed"].astype("string").str.lower().isin(["true", "1"])
    kickoff = pd.to_datetime(games["kickoff"], utc=True, errors="coerce")
    return completed | (kickoff < pd.Timestamp.now(tz="UTC"))


def _result(clv: pd.Series) -> pd.Series:
    return pd.Series(
        np.where(clv > 0, "beat", np.where(clv < 0, "lost", "push")), index=clv.index
    )
