# Atlas Operations Manual

*Generated 2026-09-25 23:25 UTC by `python -m atlas.live check`. Atlas research is
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
| Signals recorded | 120 |
| Grades recorded | 6 |
| Line snapshots | 709 |
| Tracker runs logged | 32 |
| Blocking data-quality exceptions | 0 |
| Monitor alerts firing | 2 |
| Replays clean | 6 of 6 |

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

1. Fetch quotes for the next 8 days.
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
| `signal_id` | `d009be7e-db53-57b6-b1b5-9a4460000b76` | deterministic UUID5 over game, market, book |
| `created_at` | `2026-09-22T17:22:01+00:00` | when the opinion was stated |
| `run_id` | `migrated-2026-09-22` | the run that wrote it |
| `model_version` | `73d507ab32ad` | what produced the number |
| `book` | `DraftKings` | where the number came from |
| `market` | `margin` | which market |


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

| Table | Rows | Columns | Primary key |
|---|---|---|---|
| runs | 32 | 14 | run_id |
| numbers | 2,420 | 8 | game_id, market, model_version |
| projections | 4,218 | 48 | sport, game_id, model_version |
| calibration | 11,180 | 9 | sport, game_id, market |
| dfs_slates | 41 | 7 | draft_group_id |
| dfs_salaries | 7,193 | 15 | draft_group_id, player_id |
| dfs_projections | 671 | 18 | draft_group_id, player_id_dk |
| availability | 137 | 13 | conference, report_id, team, player |
| games | 90 | 14 | game_id |
| snapshots | 709 | 11 | game_id, book, market, captured_at |
| signals | 120 | 17 | signal_id |
| grades | 6 | 14 | signal_id |
| market_shape | 324 | 5 | sport, market, point |

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
6. **The kill criteria are checked, never tuned.** `55%`,
   `0.49` points and an open execution window, transcribed
   from `reports/atlas_gamma_assessment.md` and pinned by a test.
7. **Nothing is decided below 124 graded primary
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
124 graded primary signals: the answer was
pre-registered and the project stops. Do not revisit the threshold.

**On the clock.** 2 complete seasons with all criteria
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
