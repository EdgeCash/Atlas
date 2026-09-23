# Atlas — Product Roadmap

Where Atlas is, what this sprint changed, and what comes next in what order.

`PRODUCT_EVOLUTION.md` is the argument for the transition from research platform
to consumer product. This is the plan.

---

## Where Atlas is

**Shipped and working**

| Layer | State |
|---|---|
| Data | Point-in-time warehouse, opponent-adjusted, nine seasons |
| Model | Atlas's own: preseason prior + Kalman state + calibrated total + score grid, walk-forward validated (`docs/MODEL_PLAN_NCAAF.md`); the market is never an input |
| Grading | **V2 — continuous, absolute thresholds, every letter reachable** |
| Live tracking | Deterministic signal ids, two-season success horizon, accumulating |
| Operations | Data quality gates, drift detection, anomaly checks, reproducibility harness |
| Product | Static site: board, 58 matchup cards, 116 team pages, research, NFL, premium |
| Social | Two templates generated per card on every build |

**Not built, and named as such in the product**

- Payments. The premium page is a comparison table and a framework.
- NFL cards. Staged behind calibration; the NFL page explains the three stages.
- Player pages. Reserved. Atlas has no player-level model.
- A public reliability record that updates between slates.

---

## What this sprint changed

### Grade V2 (Rule 3, approved and implemented)

The rubric now fits the calibration curve instead of reading a seven-row band
table. The bands were an artifact of the research report's own buckets; the
underlying relationship between disagreement and calibration is smooth and
close to linear, and it holds out of sample in every season tested.

| | V1 | V2 |
|---|---|---|
| Slate distribution | A 39, B 11, C 7, F 1 | A 7, B 23, C 17, D 10, F 1 |
| Distinct scores on 58 cards | 6 | 53 |
| Reachable letters | 4 | 6 |
| Historical A+ share | 0% | 6% |
| Historical F share | 8% | 10% |

Specification: `GRADE_V2_IMPLEMENTATION.md`.

### The grade teaches (Rule 4)

Three plain-English lines on every card, computed from its own numbers: what the
letter says, what Atlas did, and the record behind it. The panel below adds the
arithmetic and the conditions in words.

### Board sections (Rule 8)

Featured → Rivalries → Next kickoffs → Graded A / B / C / Marked down. Rivalries
are computed from the warehouse (met in eight of nine seasons), not curated.
Each grade block carries a caption saying what the letter means.

### Team identity and hierarchy (Rules 5 and 6)

Head-to-head hero with 52px crests either side of "at". One rank chip per board
row instead of two, which was pushing long titles into the numbers column.
Numbers column capped on a phone. Driver rows stack name over value.

### Social (Rule 7)

The wide template's last block is now a sentence rather than a fourth statistic,
and the agreement sentence carries the "adding least" caveat so a screenshot of
an A card cannot establish "A = the one to look at".

---

## The one thing the product now says that it did not before

**The grade prioritises downward.**

Cards where Atlas and the market agree to within a point realise 50.8% against a
51.3% claim — a coin flip, p = 0.69 on 760 games. An A+ card is one where Atlas
has contributed nothing. The most reliable cards are the least informative ones,
and no honest version of the grade can be a list of what to look at first.

This is now on the card, on the board's section captions, and on the social
template. It is the single most important sentence in the product, because
without it every surface that groups by grade is quietly making a claim the
evidence does not support.

---

## Next, in order

### 1. A second market data provider — highest value, smallest change

`books quoting` is **1 on all 58 cards**. Market depth carries no information
anywhere: not in the grade, not in the cautions, not on the card. The historical
sample has almost no variation in it either, which is why that axis failed the
stability test in `GRADE_STRATEGY_V2.md` §C2.

It is a tracker change, not a site change, and it improves the grade, the
cautions and the CLV record at once.

### 2. The public reliability record — the reason to visit on a Tuesday

Today there is none. The board shows the current slate, the cards are complete,
and a reader who has seen them has seen everything.

The live tracker has been accumulating signals since Phase 5 with a two-season
success horizon. The consumer version is a page that says *here is what Atlas
said, here is what happened* — and it changes every week whether or not there
are games.

It is also what makes every other claim on the site checkable, which matters
more now that V2 marks eleven cards down a week.

### 3. Data completeness that varies

15 of the 100 grade points are a constant offset, because completeness is 1.000
on every card. The obvious variable is how many games sit behind each team's
profile — which is also the honest way to encode "it is week 4" without putting
a caution on every card.

### 4. NFL, when it is calibrated

Not before. The page that says so is doing more for the product than an
uncalibrated card would.

### 5. Payments

`PREMIUM_PLAN.md` puts the boundary at a whole surface — history and depth — so
the free card is always complete. Nothing here should ship before the
reliability record, because the record is what the paid surface is made of.

---

## What must not change

- No side, ever, anywhere, in any format, for any reason.
- No figure that implies a return.
- The grade is computed and never entered by hand.
- The calibration curve is refitted from the warehouse on every build, so the
  site cannot drift from the research it cites.
- Absolute thresholds. No slate-relative grading, ever — it would make a
  screenshot mean something different depending on the week it was taken.
- Bright surfaces. Dark mode exists so an OS setting does not produce a glaring
  page at night; it is never the designed default.

---

## How to know whether this worked

Falsifiable, so that in a season it is possible to say.

1. **The F card outperforms the A card socially.** If Atlas's best-performing
   posts are its most confident ones, the audience has misunderstood the
   product.
2. **"Marked down" is used.** Under V1 it returned one card of 58 and was
   decoration. Under V2 it returns eleven. If nobody touches it, the honesty is
   still decoration.
3. **Readers return between slates.** Nothing to return for yet; item 2 on the
   list above is the candidate.
4. **V2's letters stay separated after an eighth season.** The thresholds were
   set from seven. If an eighth moves the distribution much, they were
   overfitted and the fit needs a wider prior.

---

## Document map

| Document | What it holds |
|---|---|
| `PRODUCT_VISION.md` | positioning, scope, the NFL staging gate |
| `BRAND_GUIDE.md` | voice, the language rules and their enforcement |
| `UI_SYSTEM.md` | tokens, type, layout, charts, anti-patterns |
| `ATLAS_CARD_SPEC.md` | the card's sections and empty states |
| `PREMIUM_PLAN.md` | what is free, what is paid, and why |
| `GRADE_REWORK_OPTIONS.md` | why V1 could not be fixed by relabelling |
| `GRADE_STRATEGY_V2.md` | the research behind V2, and the A+ finding |
| `GRADE_V2_IMPLEMENTATION.md` | **the rubric as built, and its tests** |
| `BOARD_EXPERIENCE.md` | why grade-first, league-first and market-first fail |
| `HOMEPAGE_FINAL.md` | **the board as built** |
| `MATCHUP_CARD_FINAL.md` | **the card as built** |
| `SOCIAL_STRATEGY_FINAL.md` | **the templates as built** |
| `SOCIAL_GROWTH_STRATEGY.md` | channels, cadence, what never to post |
| `TEAM_IDENTITY_GUIDE.md` | crests, colour, ranks, the collision rule |
| `PRODUCT_EVOLUTION.md` | research platform → consumer product |
| `SITE_IMPLEMENTATION.md` | architecture and build |
