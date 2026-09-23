# Atlas Matchup Card — Specification

One game. One card. One URL: `/{league}/{away-slug}-{home-slug}`.

Reference renders: [`design/matchup.html`](../design/matchup.html) (grade A)
and [`design/matchup-low-grade.html`](../design/matchup-low-grade.html)
(grade F). Both are built from real data for games on 26 September 2026.

---

## Contract

Every card must answer four questions in order, and a card that cannot answer
one of them says so rather than filling the space:

1. What does the market think? *(§2)*
2. What does Atlas think? *(§3)*
3. Why? *(§6)*
4. How much confidence does this deserve? *(§5, §8)*

**Universal rules.**

- Every number is computed **out of sample** from a point-in-time database.
  Nothing attached to a game uses information that did not exist before
  kickoff. See [`POINT_IN_TIME.md`](POINT_IN_TIME.md).
- A missing input renders as `—` with a reason. It is never imputed, never
  hidden, and never causes the section to disappear.
- Every card carries a grade, including the bad ones. Publishing only the
  strong cards would make the reliability record meaningless.
- No field on any card names a side.

---

## §1 Game header

| Field | Source | Empty state |
|---|---|---|
| Away team, home team | schedule | required |
| Date, kickoff (local to venue) | schedule | required |
| Venue, city | schedule | venue name only |
| Weather — temp, wind, precipitation | Meteostat nearest station | omit row; 89% coverage |
| Conference, conference-game flag | schedule | omit |
| TV | schedule feed | omit |
| Rest days, travel distance | derived | omit |

Team accent tints the 3px header rule and the logo chips only. Collision rule
in [`UI_SYSTEM.md`](UI_SYSTEM.md).

Weather appears on the header rather than in the drivers because it is
context, not a model input Atlas can claim credit for: Phase 1B found scoring
falls with wind — and so does the closing total, which already prices it.

---

## §2 Market snapshot

<!-- lang-lint: quoting -->
Two panels: spread, then total. Moneyline gets its own block — two prices in
one table cell is how a premium card starts looking like a betting slip.
<!-- lang-lint: end -->

| Field | Notes |
|---|---|
| Opening spread / current / movement | home-oriented; both sides shown |
| Opening total / current / movement | |
| Price at open and current | in American odds |
| Moneyline, both sides, open and current | with the de-vigged probability |
| Books quoting | honesty about depth — today this is usually 1 |

**Movement colour** follows the *market's* direction, not Atlas's: down is
`--data-neg`, up is `--data-pos`. It describes the market, and the reader is
not being told which direction is good.

Moneyline may be absent — books do not price one on a 41.5-point spread. The
field shows "not posted" rather than a derived number.

---

## §3 Atlas projection

Six values. Three headline, three supporting.

| Field | Definition |
|---|---|
| Projected score | the mean of the 80×80 grid over (home, away) points, **to one decimal**, never a rounded integer |
| Projected spread | the grid's mean margin, home minus away |
| Projected total | the grid's mean total, with its 80% range |
| Win probability | P(home > away) from the grid, key numbers and all |
| Over/under probability | P(total above the current market total), from the model's total and its sd |
| Most likely score | the grid's single most probable cell, with its probability (a fraction of a percent) |

### Where the number comes from

`docs/MODEL_PLAN_NCAAF.md`, steps 2–5, run forward to today by
`atlas/models/ncaaf_projection.py` and published by the weekly refresh to
`tracking/projections.csv`: every FBS team opens the season at a preseason
prior (last season's SP+ and FPI, talent, recruiting, returning production,
the programme's long-run mean and the coaching situation); a joint Kalman
filter over every team's offence and defence updates it after each game,
opponent-adjusted; the total is the state's implied total recalibrated with
pace and wind; the margin and total meet on the grid.

**The market is never an input.** It is on the card because it is the
reference the grade is measured against and the number a reader has already
seen. Where the two differ, the difference and the drivers are the product.

### Win probability is not cover probability

`Win probability` answers *who wins the game*. `Over probability` answers
*where the score lands relative to the market number*. They are different
questions and appear in different cells, never merged into one "confidence"
figure.

---

## §4 Atlas difference

Model minus market, on the spread (home margin) and on the total. The grade
is computed on the spread difference; the total's is shown beneath it.

| Row | Shown as |
|---|---|
| Spread | model, market, signed difference |
| Total | model, market, signed difference |
| Win probability | model %, market de-vigged %, difference in points |

**Every card repeats the same sentence here:** a difference is not an edge.
The disclosure names the band this game falls in and what that band has
historically delivered.

---

## §5 Atlas grade

**The grade is not a recommendation.** It measures how much weight the
information on the rest of the card deserves.

### Rubric

Four components, 100 points.

| Component | Points | Formula | Source |
|---|---|---|---|
| Calibration | 40 | `40 · max(0, 1 − \|gap\| / 0.35)` | realised minus claimed accuracy in this game's disagreement band |
| Market agreement | 25 | `25 · max(0, 1 − \|difference\| / 12)` | model minus market, on the spread |
| Signal stability | 20 | `20 · (seasons above 50% / seasons measured)` | same band, season by season |
| Data completeness | 15 | share of required inputs present | features, books quoting, weeks of season data |

| Score | Grade |
|---|---|
| 90–100 | A+ |
| 80–89 | A |
| 70–79 | B |
| 60–69 | C |
| 50–59 | D |
| < 50 | F |

### The calibration input

Measured on 5,071 out-of-sample games, totals market:

| Disagreement | Games | Claimed | Realised | Gap | Seasons above 50% |
|---|---|---|---|---|---|
| 0–1 | 760 | 51.3% | 50.8% | −0.5 pts | 3 / 7 |
| 1–2 | 772 | 53.6% | 52.1% | −1.5 pts | 4 / 7 |
| 2–4 | 1,262 | 57.0% | 51.9% | −5.1 pts | 5 / 7 |
| 4–6 | 896 | 61.7% | 52.7% | −9.0 pts | 5 / 7 |
| 6–8 | 594 | 66.0% | 52.7% | −13.3 pts | 6 / 7 |
| 8–10 | 320 | 70.2% | 55.3% | −14.9 pts | 5 / 7 |
| **10+** | **402** | **77.3%** | **49.5%** | **−27.8 pts** | **2 / 5** |

The gap widens monotonically. This is why market agreement is a *positive*
component: the louder the card, the less it has historically been worth.

### Worked examples

**Utah at Iowa State** — difference 2.2, band 2–4:
`40(0.853) + 25(0.818) + 20(0.714) + 15(1.00)` = **84 → A**

**Central Michigan at Miami** — difference 11.2, band 10+:
`40(0.206) + 25(0.069) + 20(0.400) + 15(1.00)` = **33 → F**

### Rules

- Recomputed on every market move; the grade is a property of the current
  number, not of the opener.
- Shown at the top of a D or F card as a banner, before the projection. A
  reader who reads nothing else must see it.
- Never rounded up across a boundary, never adjusted by hand, never suppressed.
- Data completeness at 15/15 on an F card is the point: the inputs are all
  there and the model still does not handle the game well.

---

## §6 Why Atlas sees it this way

**Three to five drivers. Never more.**

Each driver is: a name, a signed magnitude, one sentence in plain English, and
a centred diverging bar with the two team names as its scale.

Driver pool — opponent-adjusted, point-in-time:

| Driver | Metric |
|---|---|
| Offensive efficiency | adjusted EPA per play |
| Success rate | adjusted success rate |
| Defensive success allowed | adjusted defensive success rate |
| Explosiveness | adjusted explosiveness |
| Pace and possessions | adjusted seconds per play, plays per game |
| Finishing | adjusted finishing drives |

**Selection:** rank by absolute contribution to the projection; keep the top
four; always include a pace/possession driver on a total card because it is
frequently the largest single contributor and is the least intuitive.

**Presentation:** every value carries its FBS percentile. "95th percentile" is
readable; "+0.283 adjusted EPA" alone is not.

On a low-grade card the drivers section ends with a disclosure explaining that
the drivers can each be correct while the projection is still weak — which is
the actual situation, and the one a reader most needs help with.

---

## §7 Market intelligence

Two panels.

**Line movement.** Open, current, direction, and Atlas's direction, with a
step chart. Where the model is far outside the plotted range the chart says so
in words rather than rescaling until the movement becomes invisible.

**Historically similar situations.** A cohort defined by stated filters, with
`n`, the observed rate, **and the baseline rate beside it**. Where a difference
is not statistically distinguishable, the card says that in a sentence.

Cohorts require `n ≥ 50` to appear at all, and any cohort under 150 carries an
explicit small-sample note.

### A note the card must keep straight

Atlas has two separate findings about disagreement, and they are not in
conflict:

- Distance from the **closing** line predicts the model's own failure → §5
  grades it down.
- Distance from the **opening** line predicts which way the line will move →
  §7 reports it.

A model far from the close is wrong; a model far from the open is early. The
card must never let the second finding leak into the grade, and the CLV record
lives in §7 with its own caveats.

---

## §8 Reliability

The section that makes the product defensible.

| Field | Definition |
|---|---|
| Calibration curve | claimed vs realised by band, this card's band marked |
| Realised accuracy, this band | out-of-sample, seven seasons |
| Claimed accuracy, this band | the raw model's own confidence |
| Calibration gap | realised minus claimed |
| Seasons above 50% | stability |
| Season-to-season SD | stability |
| Games measured | sample size |

Every row shows the all-cards figure beside the this-band figure so the reader
can see whether this card is better or worse than typical.

**The disclosure is mandatory and identical on every card:** Atlas's raw
confidence numbers run high against the closing number, the grade already
corrects for it, and the claim is shown so the correction is visible.

---

## Free / premium by field

Full rationale in [`PREMIUM_PLAN.md`](PREMIUM_PLAN.md).

| Section | Free | Premium |
|---|---|---|
| §1 Header | all | — |
| §2 Market | current spread, total | opening numbers, movement, moneyline, book depth |
| §3 Projection | projected spread, total | score, win probability, total range, most likely score |
| §4 Difference | — | all |
| §5 Grade | **letter grade** | component breakdown |
| §6 Drivers | top 1 | all 3–5, percentiles, bars |
| §7 Market intelligence | — | all |
| §8 Reliability | **all — never paywalled** | — |

Two deliberate choices: **the grade letter and the entire reliability section
are free.** The grade is the product's honesty in one character, and the
reliability record is the evidence behind it. Paywalling either would mean
selling confidence and charging extra for the caveat.

---

## Empty and degraded states

| Condition | Behaviour |
|---|---|
| No market posted | §2 shows "not posted"; §3 shows the model's number as always; no difference, so no grade |
| No moneyline | field reads "not posted"; never derived |
| Fewer than 3 games played by a team | drivers shown with a shrinkage note; completeness component reduced |
| Weather unavailable | row omitted |
| Fewer than 50 similar historical games | §7 cohort panel omitted entirely |
| Model unavailable (NFL stage 1) | §3–§6 replaced by one sentence explaining the stage |

A degraded card still publishes. It says what is missing.
