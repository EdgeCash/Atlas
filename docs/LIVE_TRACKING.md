# Atlas Live CLV Tracking — Operations

Phase 5 turns the one surviving Atlas result into a system that can be
falsified in public. It records what Atlas thinks about a line, records what
the market then does, and grades the two against each other.

**Atlas generates opinions. Atlas does not generate bets.** Nothing in
`atlas/live/` computes a stake, an expected profit, a return on investment or
a Kelly fraction, and `tests/test_live.py::test_the_tracker_never_computes_a_stake`
tokenises the package on every CI run to keep it that way.

---

## The two jobs

The work splits by cost, not by concern.

| | `refresh` | `poll` |
|---|---|---|
| Frequency | weekly | hourly, in season |
| Needs | the whole warehouse (~1 GB of play-by-play) | `tracking/numbers.csv` |
| Runtime | tens of minutes | seconds |
| Produces | Atlas's number for every scheduled game | quotes, signals, grades, the report |

```bash
make live-refresh   # python -m atlas.ingest && python -m atlas.live refresh
make live-run       # python -m atlas.live run
```

`refresh` rebuilds the warehouse with `--include-scheduled`, which carries
games that have not kicked off yet with null outcomes. Every research entry
point filters those out, so the research answers are unchanged; only the live
tracker looks at them.

`poll` never touches the warehouse. It reads the numbers the refresh
published, fetches the current quote for each upcoming game, forms an opinion
on any game it has not already called, grades anything that has kicked off,
and rewrites `reports/live_clv_tracking.md`.

Both are wired to GitHub Actions in `.github/workflows/live-poll.yml` and
`live-refresh.yml`. Scheduled workflows only run on a repository's default
branch, so they stay dormant until this branch merges.

---

## What gets stored

`tracking/` is CSV, not a database file, for three reasons: it survives a
container being thrown away, a scheduled job can commit it, and a reviewer can
read its diff. Every write is atomic, sorted deterministically and formatted
to three decimals, so an unchanged row produces no diff.

| File | Contents |
|---|---|
| `numbers.csv` | Atlas's number per scheduled game and market, with the model version |
| `games.csv` | every game seen, with kickoff and status |
| `snapshots.csv` | append-on-change line observations, timestamped (Track 2) |
| `signals.csv` | immutable opinions (Track 1) |
| `grades.csv` | one row per graded signal (Track 3) |

---

## Two lines, not one

Every signal stores both numbers, and the distinction matters more than
anything else in the system:

* **`open_line`** — what the book opened on. Keeps the live record comparable
  with the historical study in `reports/clv_economics.md`.
* **`entry_line`** — what the book was quoting when Atlas formed the opinion.
  This is the number that was actually available.

**CLV is graded against `entry_line`.** Grading against the opener would
credit Atlas with movement that happened before it spoke — which is exactly
the failure Gamma's third kill criterion exists to catch. The gap between them
is stored as `pre_signal_move`, and a signal where it reaches 0.5 points is
flagged.

A line that never moved is a **push**, not a loss. Phase 3 learned that the
expensive way: counting no-move games as losses understated every beat rate by
about six points and hid the margin result entirely.

---

## Which signals count

| Population | Rule | Counts toward the criteria? |
|---|---|---|
| `primary` | totals at or above the historical 90th percentile of disagreement | yes |
| `secondary` | the same cut on margins, week 5 onward | no |
| `observed` | everything else | no |

The thresholds come from the pooled historical distribution of
`|model − opening line|`, not from the current slate: "the loudest 10% of this
week's six games" is not a selection rule. They are recomputed on each refresh
and stored on every signal.

Margins before week 5 are excluded because Phase 4 measured them at a 51.2%
beat rate, z = 0.98 — no signal at all.

Everything is recorded, including the signals that do not count. A tracker
that keeps only the signals it likes cannot be audited.

---

## Immutability

An opinion, once stated, is never revised. `signal_id` is a deterministic
UUID5 over `(game_id, market, book)` — a real UUID, so it is unmistakably an
identifier, and derivable, so a replay produces the same ids. It deliberately
excludes the line, the timestamp and the model version — so a second poll does not create a second signal
because the number moved half a point, and a weekly refit does not let Atlas
state a fresh opinion on a game it has already called. The model version is
recorded on the row; it just does not get to mint a new signal.

---

## The kill criteria

Frozen in `reports/atlas_gamma_assessment.md` before any live signal existed,
and transcribed into `atlas/live/scorecard.py` as constants a test pins.

1. CLV beat rate must stay at or above **55%**.
2. Mean CLV must stay at or above **0.49 points** (the −105 break-even).
3. The execution window must stay open: fewer than half of signals may have
   the line already moved 0.5+ points toward Atlas before it spoke.

No criterion is evaluated as decided until **124 graded primary signals** have
accumulated — the sample size Gamma computed to separate the measured beat
rate from a coin flip at 95%. Below that the report says `COLLECTING` and
reports the numbers as a record, not as a result.

**These are checked, never tuned.** A breach is the answer the project
pre-registered, not a prompt to revisit the threshold.

---

## Operations

The operations phase added the checks that keep the record trustworthy. They
run on every `live-run` and are documented in
[`reports/atlas_operations_manual.md`](../reports/atlas_operations_manual.md).

```bash
make live-check      # data quality, drift, anomalies, reproducibility
make live-reproduce  # replay random periods and verify they match
python -m atlas.live trace --signal-id <uuid>   # one signal, end to end
```

| Deliverable | What it holds |
|---|---|
| `reports/atlas_data_quality.md` | every check, fired or not, plus exceptions |
| `reports/atlas_drift_monitoring.md` | every alarm, plus the replay results |
| `reports/atlas_operations_manual.md` | how to run, audit, reproduce and stop it |
| `reports/dashboard.html` | the read-only season dashboard |

**A blocking data-quality exception outranks the kill criteria.** The
dashboard reports `SUSPECT` rather than a status derived from a record it
cannot trust.

---

## Ending it

Two complete seasons, then one of two recommendations and no middle ground:
promote Atlas into a real betting system, or terminate it.

---

## Known limitations

* **One book.** The provider is an interface, but the only implementation is
  ESPN's public scoreboard, which quotes DraftKings. That is one of the four
  books Phase 4 found ever posts an opener, which is why it was chosen; it is
  still one book.
* **One name per book.** In its first week the feed spelled DraftKings two
  ways, alternating between polls, and the tracker keyed each spelling as its
  own book: every signal was recorded twice, and a signal's closing line
  could be the stale last look under its own spelling. Names are now reduced
  to one where a quote enters (`atlas/live/books.py`), and every poll first
  reconciles what is already written: one line history per game, the
  earliest signal per game, market and book kept (the same opinion, recorded
  a day later under the other spelling, removed), grades moved with their
  signal, and any grade of a game whose history was merged cleared so the
  same poll grades it again against the whole of it.
* **Cold start.** A signal formed four days after a line posts has already
  lost part of the move. Early polls will show large `pre_signal_move` values
  and depressed CLV until the tracker has been running long enough to see
  games from the moment they are quoted.
* **No intraday history before the tracker started.** Track 5 of Phase 4 was
  unanswerable for exactly this reason. This system is the fix, and it can
  only fix it going forward.
