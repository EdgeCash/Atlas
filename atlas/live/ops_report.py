"""The operations phase deliverables.

Three documents, regenerated on every run so none of them can quietly drift
out of date with the system it describes:

``atlas_operations_manual.md``  how to run it, audit it, and stop it
``atlas_data_quality.md``       every check, and every exception (Track 1)
``atlas_drift_monitoring.md``   every alarm, fired or not (Tracks 3 and 5)
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from atlas import config
from atlas.live import drift as drifting
from atlas.live import quality, reproduce
from atlas.live import scorecard as sc
from atlas.live.store import KEYS, SCHEMA, Store
from atlas.research.markdown import table
from atlas.util import get_logger

LOG = get_logger(__name__)

#: How many periods each run replays. Small enough to stay cheap, large enough
#: that a corruption anywhere in the record gets found within a few runs.
REPLAY_SAMPLE = 3


def collect(store: Store | None = None) -> dict:
    store = store or Store.open()
    found = quality.exceptions(store)
    return {
        "store": store,
        "exceptions": found,
        "summary": quality.summary(found, store),
        "alerts": drifting.monitor(store),
        "replays": reproduce.verify(store, sample=REPLAY_SAMPLE),
        "runs": store.read("runs"),
        "signals": store.read("signals"),
        "grades": store.read("grades"),
        "snapshots": store.read("snapshots"),
        "numbers": store.read("numbers"),
    }


def _blocking(found: pd.DataFrame) -> int:
    return int((found["severity"] == "blocking").sum()) if not found.empty else 0


def _firing(alerts: pd.DataFrame) -> pd.DataFrame:
    return alerts[alerts["severity"] != "ok"] if not alerts.empty else alerts


def _stamp() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")


# ---------------------------------------------------------------------------
# Data quality
# ---------------------------------------------------------------------------


def write_data_quality(bundle: dict) -> Path:
    paths = config.paths().ensure()
    found, summary = bundle["exceptions"], bundle["summary"]
    blocking = _blocking(found)
    warnings = len(found) - blocking
    signals = len(bundle["signals"])

    if blocking:
        verdict = (
            f"**{blocking} blocking exception(s). The record is not clean and the "
            "scorecard should not be read until they are resolved.**"
        )
    elif warnings:
        verdict = (
            f"**No blocking exceptions. {warnings} warning(s)** - the record is "
            "usable and something is worth looking at."
        )
    else:
        verdict = "**Every check passed on every row.**"

    detail = (
        table(found.head(200), ["severity", "check", "signal_id", "detail"],
              ["Severity", "Check", "Signal", "Detail"], digits=3)
        if not found.empty else "_No exceptions._"
    )

    text = f"""# Atlas Data Quality

*Generated {_stamp()} by `python -m atlas.live check`. Regenerated on every
tracker run against the live record in `tracking/`.*

---

## Verdict

{verdict}

| | |
|---|---|
| Signals checked | {signals:,} |
| Grades checked | {len(bundle["grades"]):,} |
| Checks run | {len(summary):,} |
| Blocking exceptions | {blocking:,} |
| Warnings | {warnings:,} |

---

## Every check, whether or not it fired

A clean bill needs proof that the checks ran, not just an absence of
complaints. Every check is listed here on every run.

{table(summary, ["check", "severity", "scope", "rows_checked", "exceptions", "clean"], ["Check", "Severity", "Scope", "Rows checked", "Exceptions", "Clean"], digits=0)}

### What each severity means

**`blocking`** — the row is not evidence. It must not reach the scorecard, and
a blocking exception outranks the kill criteria: the dashboard reports
`SUSPECT` rather than a status derived from a record it cannot trust.

**`warning`** — the row is usable and something is off. An opening line that
never arrived, for instance, costs the comparison with the historical study
but not the CLV grade, which is taken from the entry line.

---

## Exceptions

{detail}

---

## What the checks do not do

**Nothing here repairs anything.** A tracker that silently fixes its own
inputs cannot be trusted to report what it saw, so every exception is
recorded, counted and published, and correcting one is a human decision that
leaves its own trace in `tracking/runs.csv`.

**Nothing here drops a row.** A signal excluded from the scorecard is still in
`tracking/signals.csv` with its exception beside it. Silent exclusion is how a
record becomes flattering.
"""
    out = paths.reports / "atlas_data_quality.md"
    out.write_text(text)
    LOG.info("wrote %s", out)
    return out


# ---------------------------------------------------------------------------
# Drift monitoring
# ---------------------------------------------------------------------------


def write_drift(bundle: dict) -> Path:
    paths = config.paths().ensure()
    alerts = bundle["alerts"]
    firing = _firing(alerts)

    verdict = (
        f"**{len(firing)} alert(s) firing.**" if not firing.empty
        else "**Nothing firing.**"
    )

    text = f"""# Atlas Drift Monitoring

*Generated {_stamp()} by `python -m atlas.live check`. Every alarm compares
the most recent week of the record against its own history.*

---

## Status

{verdict} Alarms are advisory: nothing in the monitor edits the record and
nothing in it stops the tracker. A monitor that can silently discard data is a
worse problem than the drift it was watching for.

{table(alerts, ["name", "severity", "observed", "threshold", "detail"], ["Alarm", "Severity", "Observed", "Threshold", "Detail"], digits=4)}

---

## What each alarm watches

### Track 5 — anomaly detection

| Alarm | Fires when | Why it matters |
|---|---|---|
| Signal volume | week-on-week change exceeds {drifting.VOLUME_CHANGE:.0%} | a provider field rename halves the slate and the scorecard carries on looking plausible |
| Silence | no signal for {drifting.SILENT_DAYS} days | the poller has stopped and nobody noticed |
| Single book | 100% of signals from one book | the record rests on one provider; this is **true of Atlas today** and should stay visible rather than become furniture |
| Single market | 100% of signals from one market | one market failing silently would look like a quiet week |

Volume is compared **week on week**, not day on day: college football is a
weekly sport and a Tuesday is supposed to be quiet.

### Track 3 — drift monitoring

| Alarm | Fires when | Why it matters |
|---|---|---|
| Model output | mean Atlas number moves more than {drifting.OUTPUT_DRIFT_POINTS:.0f} points against prior weeks | a refit that shifts the model is a different model |
| Disagreement shape | two-sample KS p < {drifting.DISTRIBUTION_P} | a mean can sit still while the distribution under it changes completely, and the selection rule is a quantile of that distribution |
| Primary rate | share clearing the threshold changes by more than {drifting.VOLUME_CHANGE:.0%} | this is the number that decides whether two seasons produce enough graded evidence to reach a verdict |

No comparison is made below {drifting.MIN_WINDOW} rows on either side. An
alarm that fires on four observations is noise with a siren attached.

---

## Reproducibility (Track 6)

Every run replays {REPLAY_SAMPLE} randomly chosen periods and checks the
record rebuilds from its own inputs. Random rather than "the last few": a bug
that only touches old rows is exactly the bug a tracker that always checks the
newest week never finds.

{table(bundle["replays"], ["period", "scope", "rows", "matched", "mismatched", "missing", "clean", "detail"], ["Period", "Scope", "Rows", "Matched", "Mismatched", "Missing", "Clean", "Detail"], digits=0) if not bundle["replays"].empty else "_Nothing to replay yet._"}

A **signals** mismatch means the record is not reproducible. A **grades**
mismatch means the grading logic changed under a published number. A
**statistics** mismatch means the scorecard does not follow from the record.
"""
    out = paths.reports / "atlas_drift_monitoring.md"
    out.write_text(text)
    LOG.info("wrote %s", out)
    return out


# ---------------------------------------------------------------------------
# Operations manual
# ---------------------------------------------------------------------------


def write_manual(bundle: dict) -> Path:
    paths = config.paths().ensure()
    store = bundle["store"]
    found, alerts, replays = bundle["exceptions"], bundle["alerts"], bundle["replays"]
    runs = bundle["runs"]
    signals = bundle["signals"]

    tables = pd.DataFrame([
        {"table": name, "columns": len(columns), "key": ", ".join(KEYS[name]),
         "rows": len(store.read(name))}
        for name, columns in SCHEMA.items()
    ])

    example = ""
    if not signals.empty:
        row = signals.iloc[0]
        example = (
            f"| `signal_id` | `{row['signal_id']}` | deterministic UUID5 over "
            "game, market, book |\n"
            f"| `created_at` | `{row['created_at']}` | when the opinion was stated |\n"
            f"| `run_id` | `{row['run_id']}` | the run that wrote it |\n"
            f"| `model_version` | `{row['model_version']}` | what produced the number |\n"
            f"| `book` | `{row['book']}` | where the number came from |\n"
            f"| `market` | `{row['market']}` | which market |\n"
        )

    text = f"""# Atlas Operations Manual

*Generated {_stamp()} by `python -m atlas.live check`. Atlas research is
complete; this document is about keeping the live tracker alive and honest for
two seasons.*

> **Atlas generates opinions. Atlas does not generate bets.** No stake, no
> expected profit, no return on investment, no Kelly fraction. Enforced by
> `tests/test_live.py::test_the_tracker_never_computes_a_stake`, which
> tokenises `atlas/live/` on every CI run.

---

## Current state

| | |
|---|---|
| Signals recorded | {len(signals):,} |
| Grades recorded | {len(bundle["grades"]):,} |
| Line snapshots | {len(bundle["snapshots"]):,} |
| Tracker runs logged | {len(runs):,} |
| Blocking data-quality exceptions | {_blocking(found):,} |
| Monitor alerts firing | {len(_firing(alerts)):,} |
| Replays clean | {int(replays["clean"].sum()) if not replays.empty else 0} of {len(replays)} |

---

## Running it

Two jobs, split by cost rather than by concern.

```bash
make live-refresh   # weekly: rebuild the warehouse, publish Atlas's numbers
make live-run       # hourly: poll, sign, grade, check, report
make live-check     # the operations checks alone, no network
```

`refresh` is expensive — it rebuilds the warehouse including games that have
not kicked off, which needs the play-by-play. `poll` is cheap: it reads
`tracking/numbers.csv` and never touches the warehouse.

Both are wired to GitHub Actions. Scheduled workflows only run on a
repository's default branch, so they are dormant until this branch merges.

### What a run does, in order

1. Fetch quotes for the next {8} days.
2. Upsert `games`; append changed quotes to `snapshots`.
3. Form signals on games not already called; append them — never update.
4. Grade every signal whose game has kicked off.
5. Run the data-quality checks, the drift monitor and a reproducibility replay.
6. Rewrite the scorecard, the dashboard and these three documents.
7. Append one row to `runs` recording all of it.

If any step raises, the run is logged with `status = failed` and the record is
left as it was. A half-written record is worse than a missing hour.

---

## Auditing it (Track 2)

Every signal carries five things, and together they make any number on the
scorecard traceable back to the process that produced it:

| Field | Example | What it fixes |
|---|---|---|
{example or "| — | — | no signals recorded yet |"}

### Why the id is a deterministic UUID

`signal_id` is `uuid5(ATLAS_NAMESPACE, "game|market|book")`. It is a real
UUID, so it is unmistakably an identifier; and it is deterministic, so
rebuilding the record from its inputs produces the same ids — which is what
makes Track 6 possible at all. A random UUID4 would satisfy the first property
and destroy the second.

It deliberately excludes the line, the timestamp and the model version. A
second poll must not mint a new id because the number moved half a point, and
a weekly refit must not let Atlas restate a call it has already made.

### The run log

`tracking/runs.csv` carries one append-only row per invocation: what ran, when,
against which provider, **at which commit**, and what it changed. Every signal
names the run that created it.

```python
from atlas.live.audit import trace
from atlas.live.store import Store
trace(Store.open(), "<signal_id>")   # signal, grade, full line history, run
```

### The tables

{table(tables, ["table", "rows", "columns", "key"], ["Table", "Rows", "Columns", "Primary key"], digits=0)}

Storage is CSV, not a database file: it survives the container, a scheduled
job can commit it, and a reviewer can read its diff. Writes are atomic, sorted
deterministically and fixed to three decimals, so an unchanged row produces no
diff.

---

## The invariants

These are the properties that make the record trustworthy. Each is enforced by
code and pinned by a test, not by discipline.

1. **A signal is never restated.** `Store.append_new_only` refuses a key that
   already exists. Rewriting an opinion after seeing where the line went is the
   single easiest way to turn this system into a fiction.
2. **CLV is graded from the entry line, never the opener.** Grading against the
   opener would credit Atlas with movement that happened before it spoke.
3. **A line that never moved is a push, not a loss.** Phase 3 learned this the
   expensive way: counting no-move games as losses understated every beat rate
   by about six points.
4. **An in-play quote never becomes the close.** A game with no pre-kickoff
   observation is left ungraded rather than graded wrongly.
5. **Nothing is repaired silently.** Exceptions are published; fixes are human
   decisions that leave a trace.
6. **The kill criteria are checked, never tuned.** `{sc.KILL_BEAT_RATE:.0%}`,
   `{sc.KILL_MEAN_CLV:.2f}` points and an open execution window, transcribed
   from `reports/atlas_gamma_assessment.md` and pinned by a test.
7. **Nothing is decided below {sc.MIN_GRADED_FOR_VERDICT:,} graded primary
   signals.** A 40% beat rate on ten signals is noise, and reporting it as a
   breach would terminate the project on nothing.

---

## Reproducing it (Track 6)

```bash
python -m atlas.live reproduce --sample 5
```

Replays randomly chosen periods and checks that the signals, the grades and
the statistics all rebuild from the stored inputs. Signals replay against the
**first snapshot** for each game, book and market — the poll that first sees a
game writes both in the same pass, so the first observation is the entry line
by construction — and against the **model version the signal names**, which is
why `tracking/numbers.csv` keeps every version rather than being overwritten.

---

## Terminating it

The project ends one of two ways and there is no third.

**On the criteria.** Any one of the three breaches, on at least
{sc.MIN_GRADED_FOR_VERDICT:,} graded primary signals: the answer was
pre-registered and the project stops. Do not revisit the threshold.

**On the clock.** {sc.SEASONS_REQUIRED} complete seasons with all criteria
holding: promote Atlas into a real betting system, or terminate it. That
decision is outside this system's scope and this system does not argue for
either.

### What to do when something breaks instead

| Symptom | Where to look | What it usually is |
|---|---|---|
| Silence alarm | `tracking/runs.csv` | the scheduled job stopped |
| Volume alarm | provider response shape | a renamed field in the feed |
| Blocking exceptions | `reports/atlas_data_quality.md` | a provider change, or a game that vanished |
| Replay mismatch | `reports/atlas_drift_monitoring.md` | the record was edited by hand |
| `SUSPECT` on the dashboard | blocking exceptions | see above; the criteria are not the problem |

A replay mismatch is the serious one. The record is meant to be derivable from
its inputs; if it is not, the scorecard is testimony rather than evidence and
should say so until the cause is found.
"""
    out = paths.reports / "atlas_operations_manual.md"
    out.write_text(text)
    LOG.info("wrote %s", out)
    return out


def write_all(store: Store | None = None) -> dict:
    bundle = collect(store)
    return {
        "quality": write_data_quality(bundle),
        "drift": write_drift(bundle),
        "manual": write_manual(bundle),
        "bundle": bundle,
    }
