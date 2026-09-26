# Atlas Data Quality

*Generated 2026-09-26 01:37 UTC by `python -m atlas.live check`. Regenerated on every
tracker run against the live record in `tracking/`.*

---

## Verdict

**Every check passed on every row.**

| | |
|---|---|
| Signals checked | 120 |
| Grades checked | 8 |
| Checks run | 19 |
| Blocking exceptions | 0 |
| Warnings | 0 |

---

## Every check, whether or not it fired

A clean bill needs proof that the checks ran, not just an absence of
complaints. Every check is listed here on every run.

| Check | Severity | Scope | Rows checked | Exceptions | Clean |
|---|---|---|---|---|---|
| game exists | blocking | signals | 120 | 0 | yes |
| market exists | blocking | signals | 120 | 0 | yes |
| opening line exists | warning | signals | 120 | 0 | yes |
| entry line exists | blocking | signals | 120 | 0 | yes |
| line history exists | blocking | signals | 120 | 0 | yes |
| closing line exists | warning | signals | 120 | 0 | yes |
| entry line in range | blocking | signals | 120 | 0 | yes |
| opening line in range | warning | signals | 120 | 0 | yes |
| entry price in range | warning | signals | 120 | 0 | yes |
| disagreement is consistent | blocking | signals | 120 | 0 | yes |
| signal is an opinion | blocking | signals | 120 | 0 | yes |
| signal id is unique | blocking | signals | 120 | 0 | yes |
| model version recorded | warning | signals | 120 | 0 | yes |
| grade references a signal | blocking | grades | 8 | 0 | yes |
| clv is consistent | blocking | grades | 8 | 0 | yes |
| result matches clv | blocking | grades | 8 | 0 | yes |
| one grade per signal | blocking | grades | 8 | 0 | yes |
| probabilities in range | blocking | grades | 8 | 0 | yes |
| clv_prob is consistent | blocking | grades | 8 | 0 | yes |

### What each severity means

**`blocking`** — the row is not evidence. It must not reach the scorecard, and
a blocking exception outranks the kill criteria: the dashboard reports
`SUSPECT` rather than a status derived from a record it cannot trust.

**`warning`** — the row is usable and something is off. An opening line that
never arrived, for instance, costs the comparison with the historical study
but not the CLV grade, which is taken from the entry line.

---

## Exceptions

_No exceptions._

---

## What the checks do not do

**Nothing here repairs anything.** A tracker that silently fixes its own
inputs cannot be trusted to report what it saw, so every exception is
recorded, counted and published, and correcting one is a human decision that
leaves its own trace in `tracking/runs.csv`.

**Nothing here drops a row.** A signal excluded from the scorecard is still in
`tracking/signals.csv` with its exception beside it. Silent exclusion is how a
record becomes flattering.
