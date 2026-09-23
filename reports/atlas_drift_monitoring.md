# Atlas Drift Monitoring

*Generated 2026-09-23 22:10 UTC by `python -m atlas.live check`. Every alarm compares
the most recent week of the record against its own history.*

---

## Status

**Nothing firing.** Alarms are advisory: nothing in the monitor edits the record and
nothing in it stops the tracker. A monitor that can silently discard data is a
worse problem than the drift it was watching for.

| Alarm | Severity | Observed | Threshold | Detail |
|---|---|---|---|---|
| signal volume | ok | 232.0000 | 0.5 | only 1 week(s) of record; nothing to compare |
| silence | ok | 0.0947 | 7 | last signal 0.1 days ago (2026-09-23) |
| single book | ok | 0.5000 | 1 | 50% of signals from book 'DraftKings' (2 distinct) |
| single market | ok | 0.5000 | 1 | 50% of signals from market 'margin' (2 distinct) |
| model output (margin) | ok | n/a | 3 | 0 recent / 0 prior rows; too few to compare |
| model output (total) | ok | n/a | 3 | 0 recent / 0 prior rows; too few to compare |
| disagreement shape (margin) | ok | n/a | 0.01 | 0 recent / 0 prior rows; too few to compare |
| disagreement shape (total) | ok | n/a | 0.01 | 0 recent / 0 prior rows; too few to compare |
| primary rate | ok | n/a | 0.5 | 0 recent / 0 prior rows; too few to compare |

---

## What each alarm watches

### Track 5 — anomaly detection

| Alarm | Fires when | Why it matters |
|---|---|---|
| Signal volume | week-on-week change exceeds 50% | a provider field rename halves the slate and the scorecard carries on looking plausible |
| Silence | no signal for 7 days | the poller has stopped and nobody noticed |
| Single book | 100% of signals from one book | the record rests on one provider; this is **true of Atlas today** and should stay visible rather than become furniture |
| Single market | 100% of signals from one market | one market failing silently would look like a quiet week |

Volume is compared **week on week**, not day on day: college football is a
weekly sport and a Tuesday is supposed to be quiet.

### Track 3 — drift monitoring

| Alarm | Fires when | Why it matters |
|---|---|---|
| Model output | mean Atlas number moves more than 3 points against prior weeks | a refit that shifts the model is a different model |
| Disagreement shape | two-sample KS p < 0.01 | a mean can sit still while the distribution under it changes completely, and the selection rule is a quantile of that distribution |
| Primary rate | share clearing the threshold changes by more than 50% | this is the number that decides whether two seasons produce enough graded evidence to reach a verdict |

No comparison is made below 30 rows on either side. An
alarm that fires on four observations is noise with a siren attached.

---

## Reproducibility (Track 6)

Every run replays 3 randomly chosen periods and checks the
record rebuilds from its own inputs. Random rather than "the last few": a bug
that only touches old rows is exactly the bug a tracker that always checks the
newest week never finds.

| Period | Scope | Rows | Matched | Mismatched | Missing | Clean | Detail |
|---|---|---|---|---|---|---|---|
| 2026-w04 | signals | 232 | 232 | 0 | 0 | yes | exact match |
| 2026-w04 | grades | 0 | 0 | 0 | 0 | yes | no grades recorded |
| 2026-w04 | statistics | 0 | 0 | 0 | 0 | yes | nothing graded yet |

A **signals** mismatch means the record is not reproducible. A **grades**
mismatch means the grading logic changed under a published number. A
**statistics** mismatch means the scorecard does not follow from the record.
