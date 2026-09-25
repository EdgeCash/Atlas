"""Tracks 3 and 5: drift monitoring and anomaly detection.

The failure this guards against is not a wrong number. It is a *quiet* one:
the provider changes a field name and signal volume halves, or a refit shifts
the model's output by three points, and the scorecard carries on looking
plausible for a month. Every alarm here compares the recent record against its
own history and fires on a change in shape, not on a bad value.

Alarms are advisory. Nothing here edits the record, and nothing here stops the
tracker: a monitor that can silently discard data is a worse problem than the
drift it was watching for.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats

from atlas.live.store import Store
from atlas.util import get_logger

LOG = get_logger(__name__)

#: Track 5: a week-on-week change in signal volume beyond this is an alarm.
VOLUME_CHANGE = 0.50

#: Track 5: no signal at all for this long, in season, means something broke.
SILENT_DAYS = 7

#: Track 3: a shift in mean model output beyond this many points of line is
#: not a model doing its job, it is a model that changed.
OUTPUT_DRIFT_POINTS = 3.0

#: Track 3: the Kolmogorov-Smirnov p-value below which the disagreement
#: distribution is treated as having changed shape.
DISTRIBUTION_P = 0.01

#: Minimum rows before a comparison means anything.
MIN_WINDOW = 30

SEVERITIES = ("alarm", "watch", "ok")


@dataclass(frozen=True)
class Alert:
    name: str
    severity: str
    observed: float
    threshold: float
    detail: str

    @property
    def firing(self) -> bool:
        return self.severity in ("alarm", "watch")


def _as_frame(alerts: list[Alert]) -> pd.DataFrame:
    if not alerts:
        return pd.DataFrame(columns=["name", "severity", "observed", "threshold", "detail"])
    return pd.DataFrame([vars(a) for a in alerts])


def _signals(store: Store) -> pd.DataFrame:
    frame = store.read("signals")
    if frame.empty:
        return frame
    frame = frame.copy()
    frame["created_ts"] = pd.to_datetime(frame["created_at"], utc=True, errors="coerce")
    frame["created_date"] = frame["created_ts"].dt.date.astype("string")
    for column in ("disagreement", "atlas_number", "entry_line", "week", "season"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    # One ordered key per season and week: grouped on the week alone, a new
    # season's week 1 would sort before last season's week 15.
    frame["period"] = frame["season"].fillna(0) * 100 + frame["week"]
    return frame.dropna(subset=["created_ts"])


# ---------------------------------------------------------------------------
# Track 5 - anomaly detection
# ---------------------------------------------------------------------------


def volume_alerts(frame: pd.DataFrame) -> list[Alert]:
    """Signal volume, week on week.

    Weeks, not days: college football is a weekly sport and a Tuesday is
    supposed to be quiet.
    """
    if frame.empty or frame["week"].notna().sum() == 0:
        return [Alert("signal volume", "ok", 0.0, VOLUME_CHANGE,
                      "no signals recorded yet")]
    counts = frame.groupby("period" if "period" in frame else "week").size().sort_index()
    if len(counts) < 2:
        return [Alert("signal volume", "ok", float(counts.iloc[-1]), VOLUME_CHANGE,
                      f"only {len(counts)} week(s) of record; nothing to compare")]

    latest, previous = float(counts.iloc[-1]), float(counts.iloc[-2])
    change = (latest - previous) / previous if previous else np.inf
    severity = "alarm" if abs(change) > VOLUME_CHANGE else "ok"
    return [Alert(
        "signal volume", severity, change, VOLUME_CHANGE,
        f"week {int(counts.index[-1]) % 100}: {latest:.0f} signals against "
        f"{previous:.0f} the week before ({change:+.0%})",
    )]


def silence_alert(frame: pd.DataFrame, *, now: pd.Timestamp | None = None) -> list[Alert]:
    """Nothing recorded for a week means the poller is not running."""
    now = now or pd.Timestamp.now(tz="UTC")
    if frame.empty:
        return [Alert("silence", "alarm", np.inf, SILENT_DAYS,
                      "no signals have ever been recorded")]
    last = frame["created_ts"].max()
    days = (now - last).total_seconds() / 86400.0
    severity = "alarm" if days > SILENT_DAYS else "ok"
    return [Alert("silence", severity, days, float(SILENT_DAYS),
                  f"last signal {days:.1f} days ago ({last.date()})")]


def concentration_alerts(frame: pd.DataFrame) -> list[Alert]:
    """All signals from one book, or one market.

    Both are true of Atlas today and both are still worth alarming on: the
    single-book alarm is the honest statement that this record rests on one
    provider, and it should stay visible rather than becoming furniture.
    """
    out = []
    for column, label in (("book", "book"), ("market", "market")):
        if frame.empty:
            out.append(Alert(f"single {label}", "ok", 0.0, 1.0, "no signals yet"))
            continue
        share = frame[column].value_counts(normalize=True)
        top, value = share.index[0], float(share.iloc[0])
        severity = "alarm" if value >= 1.0 else "ok"
        out.append(Alert(
            f"single {label}", severity, value, 1.0,
            f"{value:.0%} of signals from {label} {top!r} "
            f"({frame[column].nunique()} distinct)",
        ))
    return out


# ---------------------------------------------------------------------------
# Track 3 - drift monitoring
# ---------------------------------------------------------------------------


def _split(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Most recent week against everything before it."""
    key = "period" if "period" in frame else "week"
    weeks = sorted(frame[key].dropna().unique())
    if len(weeks) < 2:
        return pd.DataFrame(), pd.DataFrame()
    return frame[frame[key] == weeks[-1]], frame[frame[key] < weeks[-1]]


def output_drift(frame: pd.DataFrame) -> list[Alert]:
    """Has the model's own output moved, market by market?"""
    out = []
    for market, block in (frame.groupby("market") if not frame.empty else []):
        recent, history = _split(block)
        if len(recent) < MIN_WINDOW or len(history) < MIN_WINDOW:
            out.append(Alert(f"model output ({market})", "ok", np.nan,
                             OUTPUT_DRIFT_POINTS,
                             f"{len(recent)} recent / {len(history)} prior rows; "
                             "too few to compare"))
            continue
        shift = float(recent["atlas_number"].mean() - history["atlas_number"].mean())
        severity = "alarm" if abs(shift) > OUTPUT_DRIFT_POINTS else "ok"
        out.append(Alert(
            f"model output ({market})", severity, shift, OUTPUT_DRIFT_POINTS,
            f"mean Atlas number moved {shift:+.2f} points against prior weeks",
        ))
    return out or [Alert("model output", "ok", np.nan, OUTPUT_DRIFT_POINTS,
                         "no signals yet")]


def distribution_drift(frame: pd.DataFrame) -> list[Alert]:
    """Has the *shape* of the disagreement distribution changed?

    A mean can sit still while the distribution underneath it changes
    completely, and the selection rule is a quantile of that distribution -
    so its shape is the thing that decides what gets tracked.
    """
    out = []
    for market, block in (frame.groupby("market") if not frame.empty else []):
        recent, history = _split(block)
        if len(recent) < MIN_WINDOW or len(history) < MIN_WINDOW:
            out.append(Alert(f"disagreement shape ({market})", "ok", np.nan,
                             DISTRIBUTION_P,
                             f"{len(recent)} recent / {len(history)} prior rows; "
                             "too few to compare"))
            continue
        result = stats.ks_2samp(
            recent["disagreement"].dropna(), history["disagreement"].dropna()
        )
        severity = "watch" if result.pvalue < DISTRIBUTION_P else "ok"
        out.append(Alert(
            f"disagreement shape ({market})", severity, float(result.pvalue),
            DISTRIBUTION_P,
            f"KS statistic {result.statistic:.3f}, p = {result.pvalue:.4f}",
        ))
    return out or [Alert("disagreement shape", "ok", np.nan, DISTRIBUTION_P,
                         "no signals yet")]


def selection_rate_drift(frame: pd.DataFrame) -> list[Alert]:
    """What share of signals clears the primary threshold, week on week.

    This is the number that decides whether two seasons will produce enough
    graded evidence to reach a verdict, so a change in it is operationally
    more important than a change in the model's mean.
    """
    if frame.empty:
        return [Alert("primary rate", "ok", np.nan, VOLUME_CHANGE, "no signals yet")]
    recent, history = _split(frame)
    if len(recent) < MIN_WINDOW or len(history) < MIN_WINDOW:
        return [Alert("primary rate", "ok", np.nan, VOLUME_CHANGE,
                      f"{len(recent)} recent / {len(history)} prior rows; "
                      "too few to compare")]
    now = float((recent["selection"] == "primary").mean())
    before = float((history["selection"] == "primary").mean())
    change = (now - before) / before if before else np.inf
    severity = "watch" if abs(change) > VOLUME_CHANGE else "ok"
    return [Alert("primary rate", severity, change, VOLUME_CHANGE,
                  f"{now:.1%} of signals primary against {before:.1%} before "
                  f"({change:+.0%})")]


def monitor(store: Store | None = None) -> pd.DataFrame:
    """Every alarm, fired or not. A quiet monitor has to prove it looked."""
    store = store or Store.open()
    frame = _signals(store)
    alerts = [
        *volume_alerts(frame),
        *silence_alert(frame),
        *concentration_alerts(frame),
        *output_drift(frame),
        *distribution_drift(frame),
        *selection_rate_drift(frame),
    ]
    out = _as_frame(alerts)
    firing = out[out["severity"] != "ok"]
    if not firing.empty:
        LOG.warning("%d alerts firing: %s", len(firing), ", ".join(firing["name"]))
    return out
