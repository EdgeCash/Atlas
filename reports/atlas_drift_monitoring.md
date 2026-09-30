# Atlas Drift Monitoring

*Generated 2026-09-30 14:55 UTC by `python -m atlas.live check`. Every alarm compares
the most recent week of the record against its own history.*

---

## Status

**3 alert(s) firing.** Alarms are advisory: nothing in the monitor edits the record and
nothing in it stops the tracker. A monitor that can silently discard data is a
worse problem than the drift it was watching for.

| Alarm | Severity | Observed | Threshold | Detail |
|---|---|---|---|---|
| signal volume | ok | -0.0345 | 0.5 | week 5: 112 signals against 116 the week before (-3%) |
| silence | ok | 2.8978 | 7 | last signal 2.9 days ago (2026-09-27) |
| single book | alarm | 1.0000 | 1 | 100% of signals from book 'DraftKings' (1 distinct) |
| single market | ok | 0.5000 | 1 | 50% of signals from market 'margin' (2 distinct) |
| model output (margin) | alarm | -4.0179 | 3 | mean Atlas number moved -4.02 points against prior weeks |
| model output (total) | ok | 0.0679 | 3 | mean Atlas number moved +0.07 points against prior weeks |
| disagreement shape (margin) | ok | 0.3006 | 0.01 | KS statistic 0.174, p = 0.3006 |
| disagreement shape (total) | ok | 0.2391 | 0.01 | KS statistic 0.185, p = 0.2391 |
| primary rate | watch | -1.0000 | 0.5 | 0.0% of signals primary against 0.9% before (-100%) |
| college state | ok | 116.0000 | 1 | 116 more team-games assimilated since Saturday noon ET |

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
| 2026-w04 | signals | 116 | 116 | 0 | 0 | yes | exact match |
| 2026-w04 | grades | 116 | 116 | 0 | 0 | yes | exact match |
| 2026-w04 | statistics | 12 | 12 | 0 | 0 | yes | recomputed from the replayed grades |
| 2026-w05 | signals | 112 | 0 | 223 | 0 | no | atlas_number: 107; disagreement: 107; direction: 6; selection: 3 |
| 2026-w05 | grades | 0 | 0 | 0 | 0 | yes | no grades in this period |
| 2026-w05 | statistics | 0 | 0 | 0 | 0 | yes | no graded signals in period |

A **signals** mismatch means the record is not reproducible. A **grades**
mismatch means the grading logic changed under a published number. A
**statistics** mismatch means the scorecard does not follow from the record.
