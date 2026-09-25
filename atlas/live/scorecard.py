"""Tracks 4 and 5: the public scorecard and the kill criteria.

Every number here is a property of lines, not of football games and not of
money. The vocabulary is deliberately narrow: beat rate, CLV in points, signal
count, book.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats

from atlas.util import get_logger

LOG = get_logger(__name__)

# ---------------------------------------------------------------------------
# Kill criteria, transcribed from reports/atlas_gamma_assessment.md
# ---------------------------------------------------------------------------

#: Gamma froze these before any live signal existed. They are thresholds to be
#: checked against, not parameters to be tuned: moving one after seeing the
#: data is the whole thing this project has spent five phases avoiding.
KILL_BEAT_RATE = 0.55
KILL_MEAN_CLV = 0.49
KILL_SOURCE = "reports/atlas_gamma_assessment.md"

#: Graded signals needed before a criterion can fail on evidence rather than
#: on noise. 124 is the sample size Gamma computed to separate the measured
#: beat rate from a coin flip at 95%.
MIN_GRADED_FOR_VERDICT = 124

#: The success criterion: two complete seasons.
SEASONS_REQUIRED = 2


@dataclass(frozen=True)
class Criterion:
    name: str
    observed: float
    threshold: float
    graded: int
    passing: bool
    decided: bool
    note: str


def graded_frame(signals: pd.DataFrame, grades: pd.DataFrame) -> pd.DataFrame:
    """Signals joined to their grades, with a usable date column."""
    if signals.empty or grades.empty:
        return pd.DataFrame()
    frame = signals.merge(grades, on="signal_id", how="inner")
    frame["clv_points"] = pd.to_numeric(frame["clv_points"], errors="coerce")
    if "clv_prob" in frame:
        frame["clv_prob"] = pd.to_numeric(frame["clv_prob"], errors="coerce")
    frame["date"] = pd.to_datetime(
        frame["created_at"], utc=True, errors="coerce"
    ).dt.date.astype("string")
    frame["graded_date"] = pd.to_datetime(
        frame["graded_at"], utc=True, errors="coerce"
    ).dt.date.astype("string")
    return frame.dropna(subset=["clv_points"])


def beat_interval(beats: int, n: int, z: float = 1.96) -> tuple[float, float, float]:
    """(low, high, p) for a beat rate: the Wilson 95% interval, and the
    one-sided binomial p-value against a coin flip. With a few dozen graded
    signals a 60% beat rate is well inside noise; the interval says so."""
    if n == 0:
        return np.nan, np.nan, np.nan
    p = beats / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return float(centre - half), float(centre + half), float(stats.binom.sf(beats - 1, n, 0.5))


def _block(frame: pd.DataFrame) -> dict:
    clv = frame["clv_points"]
    decided = frame[frame["result"] != "push"]
    beats = (decided["result"] == "beat").sum()
    n = len(decided)
    low, high, p_value = beat_interval(int(beats), n)
    return {
        "signals": int(len(frame)),
        "graded": n,
        "pushes": int((frame["result"] == "push").sum()),
        "beat_rate": float(beats / n) if n else np.nan,
        "beat_low": low,
        "beat_high": high,
        "p_value": p_value,
        "mean_clv": float(clv.mean()),
        "median_clv": float(clv.median()),
        # CLV in probability: price and key numbers counted, the vig taken out.
        # Reported beside the points; the frozen criteria stay in points.
        "mean_clv_prob": float(frame["clv_prob"].mean()) if "clv_prob" in frame else np.nan,
        "priced": int(frame["clv_prob"].notna().sum()) if "clv_prob" in frame else 0,
        "flagged": int(frame["execution_flagged"].astype("string").str.lower()
                       .isin(["true", "1"]).sum()),
    }


def scorecard(frame: pd.DataFrame, *, by: str, selection: str | None = "primary"
              ) -> pd.DataFrame:
    """Aggregate the graded record. ``by`` is a column such as date or week.

    A week is a week of one season: grouped by ``week`` alone, week 3 of this
    season and week 3 of last would be one row. So ``by="week"`` groups by
    season and week, and the frame keeps both columns.
    """
    if frame.empty:
        return pd.DataFrame()
    block = frame if selection is None else frame[frame["selection"] == selection]
    if block.empty or by not in block.columns:
        return pd.DataFrame()
    keys = ["season", "week"] if by == "week" and "season" in block.columns else [by]
    rows = []
    for key, sub in block.groupby(keys, observed=True, dropna=False):
        key = key if isinstance(key, tuple) else (key,)
        rows.append({**dict(zip(keys, key, strict=True)), **_block(sub)})
    return pd.DataFrame(rows).sort_values(keys).reset_index(drop=True)


def by_book(frame: pd.DataFrame, *, selection: str | None = "primary") -> pd.DataFrame:
    return scorecard(frame, by="book", selection=selection)


def by_selection(frame: pd.DataFrame) -> pd.DataFrame:
    """Every population, including the one the criteria ignore."""
    if frame.empty:
        return pd.DataFrame()
    rows = []
    for name, sub in frame.groupby("selection", observed=True):
        rows.append({"selection": name, **_block(sub)})
    rows.append({"selection": "all", **_block(frame)})
    return pd.DataFrame(rows)


def kill_criteria(frame: pd.DataFrame) -> list[Criterion]:
    """Evaluate Gamma's three criteria on the primary population."""
    primary = frame[frame["selection"] == "primary"] if not frame.empty else frame
    stats = _block(primary) if not primary.empty else {
        "graded": 0, "beat_rate": np.nan, "mean_clv": np.nan, "signals": 0, "flagged": 0
    }
    graded = int(stats["graded"])
    decided = graded >= MIN_GRADED_FOR_VERDICT

    flagged_share = (
        stats["flagged"] / stats["signals"] if stats["signals"] else np.nan
    )
    return [
        Criterion(
            name="CLV beat rate",
            observed=stats["beat_rate"],
            threshold=KILL_BEAT_RATE,
            graded=graded,
            passing=bool(stats["beat_rate"] >= KILL_BEAT_RATE)
            if np.isfinite(stats["beat_rate"]) else True,
            decided=decided,
            note=f"must stay at or above {KILL_BEAT_RATE:.0%}",
        ),
        Criterion(
            name="Mean CLV",
            observed=stats["mean_clv"],
            threshold=KILL_MEAN_CLV,
            graded=graded,
            passing=bool(stats["mean_clv"] >= KILL_MEAN_CLV)
            if np.isfinite(stats["mean_clv"]) else True,
            decided=decided,
            note=f"must stay at or above {KILL_MEAN_CLV:.2f} points",
        ),
        Criterion(
            name="Execution window",
            observed=flagged_share,
            threshold=0.5,
            graded=graded,
            passing=bool(flagged_share < 0.5) if np.isfinite(flagged_share) else True,
            decided=decided,
            note="share of signals where the line had already moved "
                 f"{0.5:.1f}+ points toward Atlas before it spoke",
        ),
    ]


def seasons_complete(frame: pd.DataFrame) -> int:
    """Completed seasons of tracking, for the two-season success criterion."""
    if frame.empty or "season" not in frame:
        return 0
    seasons = pd.to_numeric(frame["season"], errors="coerce").dropna()
    return int(seasons.nunique())
