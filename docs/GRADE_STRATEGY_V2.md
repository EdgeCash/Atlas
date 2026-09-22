# Atlas Grade — Strategy V2

**Status: research. Nothing here is implemented.** The site still computes the
approved rubric from `ATLAS_CARD_SPEC.md` §5, unchanged.

The brief: *A+ means something rare. F means something rare. Grades help users
prioritize.*

Two of those three are achievable and one is not, for a reason worth stating up
front.

---

## 1. Why V1 clusters — the finding from the previous sprint

`GRADE_REWORK_OPTIONS.md` established that the V1 score is a **step function of
the disagreement band**. Three of its four components are constants: data
completeness is 1.000 on every card, and calibration and stability are both
looked up from a seven-row table. Only market agreement varies, and only within
a band.

So V1 produces seven disjoint score clusters, 2–4 points wide, separated by gaps
of 1.3 to 21 points. The grade is the band wearing a letter. No scheme that
re-maps those seven clusters onto six letters can produce a distribution where
both ends are rare, because 38% of cards land in the top two clusters.

---

## 2. The V2 finding — the seven bands are an artifact of the bucketing

The bands come from `market_aware.EDGE_BUCKETS`, which was a research convention
for reporting, not a claim about the data. Slicing the same seven seasons at
0.5-point intervals instead and plotting the calibration gap against the size of
the disagreement gives a **smooth, monotone, almost-linear relationship**:

| Difference from the market | Calibration gap |
|---|---|
| 0.25 | −0.005 |
| 1.25 | +0.005 |
| 2.25 | −0.012 |
| 3.75 | −0.112 |
| 5.25 | −0.080 |
| 6.75 | −0.146 |
| 8.25 | −0.193 |
| 10.25 | −0.223 |
| 10.75 | −0.256 |

A power fit over 5,006 games:

```
gap(d) = −0.0133 · d^1.139          r = 0.88 against the observed slices
```

The exponent is 1.14 — near linear. **The step function was never in the data;
it was in the report's buckets.**

### Does the curve hold out of sample?

Fitted on prior seasons only, tested on the next:

| Test season | n | fitted a | fitted p | corr(predicted, observed) |
|---|---|---|---|---|
| 2022 | 723 | 0.0096 | 1.214 | 0.81 |
| 2023 | 783 | 0.0198 | 0.964 | 0.44 |
| 2024 | 783 | 0.0266 | 0.845 | 0.70 |
| 2025 | 803 | 0.0102 | 1.257 | 0.67 |

The shape holds every season and the sign never flips. The coefficient moves by
a factor of about 2.5 across seasons, which is real variance and is the reason
the curve should be refitted on every build rather than transcribed — exactly as
`calibration_bands()` is today.

---

## 3. The V2 rubric

Replace the lookup table with the curve, and replace the constant completeness
component with one that varies.

| Component | Weight | What it reads |
|---|---|---|
| **Calibration** | 45 | `1 − |gap(d)| / 0.35`, where `gap` is the fitted curve, adjusted for season stage and market settledness |
| **Market agreement** | 25 | `1 − d / 12`, unchanged |
| **Card conditions** | 15 | how mature the season is, and how settled the market is |
| **Data completeness** | 15 | unchanged |

The two adjustments inside calibration are the axes that survived a
season-by-season stability test in the previous sprint: **season stage** (weeks
1–4 are worse, in 6 of 7 seasons) and **market settledness** (a total that has
moved 1.5 or more since it opened is worse, in 5 of 6 seasons). Each is worth
about 2–3 points of calibration gap.

Signal stability disappears as a separate component. It was measuring "in how
many of seven seasons did this band beat 50%", which is a property of the band —
and there are no bands any more.

### Letter thresholds

Fixed, absolute, published once, and **not recomputed per slate**:

| Letter | Score |
|---|---|
| A+ | ≥ 96 |
| A | ≥ 90 |
| B | ≥ 79 |
| C | ≥ 66 |
| D | ≥ 51 |
| F | < 51 |

They are *chosen* from the historical distribution — the same way a school sets
a grading scale once from years of results — but once set they are constants. A
card's letter depends only on that card. This is the distinction that matters:

> **Calibrating thresholds against history is not grading on a curve.** A curve
> recomputes the boundaries from whoever turned up this week, so the same card
> gets a different letter on a different Saturday. Fixed thresholds do not.

---

## 4. What V2 produces

### Across seven seasons (5,006 games)

| Letter | Share | Count |
|---|---|---|
| A+ | 6% | 281 |
| A | 14% | 690 |
| B | 31% | 1,534 |
| C | 25% | 1,276 |
| D | 15% | 732 |
| F | 10% | 493 |

**A+ is rare. F is rare. Every letter is reachable.** The brief's first two
requirements are met.

### On the 58-card slate of 26 September

| Letter | V1 | V2 |
|---|---|---|
| A+ | 0 | 0 |
| A | 39 | 7 |
| B | 11 | 23 |
| C | 7 | 17 |
| D | 0 | 10 |
| F | 1 | 1 |

Seven cards to look at first instead of thirty-nine; eleven marked down instead
of one. **53 of the 58 cards get a distinct score**, against 6 distinct scores
under V1.

### What each letter means, measured

| Letter | n | Mean difference | Claimed | Realised | Gap |
|---|---|---|---|---|---|
| A+ | 281 | 0.6 pts | 51.4% | 45.9% | −5.5% |
| A | 690 | 1.2 pts | 52.8% | 53.9% | +1.1% |
| B | 1,534 | 2.4 pts | 55.7% | 52.5% | −3.2% |
| C | 1,276 | 4.6 pts | 60.9% | 51.8% | −9.1% |
| D | 732 | 7.3 pts | 66.9% | 52.9% | −14.0% |
| F | 493 | 12.0 pts | 75.9% | 50.7% | −25.1% |

Monotone from B down to F, which is the property the grade exists to have.

---

## 5. The thing the brief cannot have, and why

**Grades cannot help users prioritise — not this grade, and not any honest
version of it.**

Look at the A+ row. Those cards realised 45.9% against a 51.4% claim. That is
not a defect in the fit; it is what an A+ card *is*. Across the whole 0–1 band:

```
n = 760   claimed 51.3%   realised 50.8%   gap −0.5%
binomial test against a coin flip: p = 0.69
```

Perfectly calibrated, and statistically indistinguishable from a coin flip. An
A+ card is one where **Atlas and the market landed on the same number, so Atlas
has contributed nothing.** It is the most trustworthy card on the board and the
least interesting one.

This is not a fixable property. The grade measures how much weight the card's
information deserves; the cards whose information is most reliable are exactly
the cards with the least information in them. Any grade that rose with
*interestingness* would be ranking cards by how far Atlas has strayed from the
market, which is a list of opportunities, which is the one thing Atlas will not
publish.

**So the grade prioritises in one direction only: it tells a reader what to
discount.** "Marked down" is the actionable end of the scale. That is worth
saying plainly on the research page rather than implying otherwise.

---

## 6. Recommendation

**Adopt V2.** Specifically:

1. **Replace the band lookup with the fitted curve.** This is the change that
   matters; everything else follows from it. Refit on every build from the
   warehouse, as `calibration_bands()` already does, so the site can never drift
   from the research.
2. **Replace signal stability with card conditions.** Stability was a band
   property and the bands are gone; conditions is the only component besides
   agreement that varies card to card.
3. **Set the six thresholds at 96 / 90 / 79 / 66 / 51.** Publish them on the
   research page alongside the historical distribution they were chosen from,
   and treat a change to them as a research change, not a design change.
4. **Publish the A+ caveat.** An A+ card should say, in its headline, that Atlas
   and the market agree and Atlas is adding little — not "high confidence" full
   stop.

### Risks

- **The curve's coefficient varies by ~2.5× across seasons.** Refitting each
  build handles it; a hard-coded coefficient would not.
- **A card's letter now changes as the market moves.** Under V1 a card had to
  cross a band boundary; under V2 every tick moves the score. Letters will
  change between a Tuesday and a Saturday, and the card should say when it was
  computed. This is honest but it is new behaviour and it needs a line on the
  card.
- **D becomes a common letter (15%).** Under V1 it never appeared. Readers will
  see cards marked down who have not seen it before, and the research page has
  to be ready to explain it.

---

## 7. The special request: Grade, or Grade + Rank?

> *Should Atlas show `A+ #1`, `A+ #2`, `A #3`, … as a way to make grades more
> actionable without becoming betting advice?*

**Recommendation: no rank. Grade only.**

Three reasons, in order of weight.

**1. A rank is a ranking of *something*, and every candidate is either useless
or a pick list.**

- Rank by grade → an ordering of how little Atlas disagrees with the market.
  `#1` is the card where Atlas has said nothing at all. Useless, and section 5
  proves it rather than asserting it.
- Rank by difference → an ordering of how far Atlas has strayed from the
  market, best first. That is a pick list with the word "pick" removed. It is
  the exact artefact `BRAND_GUIDE.md` forbids and the exact thing a screenshot
  would be read as.
- Rank by grade *then* difference → the second one, with a filter on it.

**2. A rank is ordinal where the underlying quantity is not.** Cards #3 and #4
in section 4's slate differ by 0.1 of a point of score. Printing `#3` and `#4`
tells a reader there is an ordering there that the evidence does not support.
The score already carries the magnitude, and it carries the fact that the two
are indistinguishable.

**3. A rank is slate-relative, and the previous sprint rejected slate-relative
letters for the same reason.** `#1` on a quiet Tuesday and `#1` on championship
Saturday are not the same thing, and a screenshot cannot tell you which it was.
Everything V2 does to make the letter week-independent, a rank undoes.

### What to do instead

Two things, both of which give a reader the ordering they actually want without
publishing one:

- **Sort and filter, don't rank.** The board already offers "A & up", "B & up"
  and "Marked down". A reader who wants the most reliable cards filters to them
  and sees them in kickoff order. No number implies an ordering that is not
  there.
- **Show the score, not a position.** `A 87` already distinguishes two A cards.
  It is a measurement, so two cards with the same score read as the same, which
  is correct. `#3` and `#4` cannot do that.

If a positional cue is wanted later, the defensible one is a **descriptive
percentile against history, not against the slate** — "more reliable than 94% of
cards Atlas has graded". It is week-independent, it is a measurement rather than
a contest, and it still is not a list of what to look at first.
