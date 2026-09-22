# Atlas — Product Evolution

**Research platform → consumer product, without giving up any of the honesty.**

The research is done. Seven seasons, walk-forward, point-in-time, pre-registered
criteria, placebo tests, a live tracker, a reproducibility harness. The question
is no longer *is this true* but *will anyone open it twice*.

---

## The tension, stated honestly

A research platform and a consumer product want opposite things.

| Research wants | Consumers want |
|---|---|
| Every caveat visible | One answer |
| Uncertainty in the same breath as the claim | Confidence |
| Nothing above the fold but the method | Everything above the fold |
| A reader who came to check the work | A reader who came for the game |

The usual resolution is to hide the caveats, and it is the one thing Atlas
cannot do — the caveats *are* the product. The whole position rests on being the
only thing in the category that tells you when not to trust it.

**So the resolution is the other direction: make the caveat the headline.** The
grade is a caveat rendered as the largest element on the card. "Be careful
about" is a caveat with its own section. "Marked down" is a caveat with a filter
control. None of these is hidden, and none of them is the fine print at the
bottom that nobody reads.

That is the whole strategy. Everything below is the consequence.

---

## Where Atlas has come from

| Phase | What it produced | What it left behind |
|---|---|---|
| Alpha | The point-in-time warehouse, opponent-adjusted features | `POINT_IN_TIME.md`, `DATA_DICTIONARY.md` |
| Beta | Market anchoring, the calibration table | `atlas_beta_framework.md` |
| Gamma | CLV economics, the decision to build a research platform | `atlas_gamma_assessment.md` |
| Live | Signal tracking, deterministic ids, two-season horizon | `LIVE_TRACKING.md` |
| Operations | Data quality, drift, anomaly detection, reproducibility | three ops reports |
| Product build | The design system and the specification | five product documents |
| Product phase 1 | The built site — four page types, a computed grade | `SITE_IMPLEMENTATION.md` |
| Refinement | Three-tier card, board homepage, grade research | `UX_REVIEW.md`, `GRADE_REWORK_OPTIONS.md` |
| **Polish (this one)** | The grade that separates, the board that is the product | this document and four others |

Nothing in that column has been thrown away. The consumer product is a
**presentation layer over research that already existed**, which is why it can
afford to be honest: the honesty is not a marketing decision that a growth team
can later reverse, it is what the numbers underneath actually say.

---

## The four things a consumer product needs that a research platform does not

### 1. A reason to come back on a Tuesday

Today there is none. The board shows the current slate, the cards are complete,
and a reader who has seen them has seen everything.

What exists and is not yet surfaced: **the reliability record updating in
public.** The live tracker has been accumulating signals since Phase 5 with a
two-season success horizon. The consumer version of that is a page that says
*here is what Atlas said, here is what happened* — and it changes every week
whether or not there are games.

This is the single largest gap between Atlas today and a product with a habit
attached. It is not built.

### 2. Something to send someone

Solved, in `SOCIAL_CARD_REDESIGN.md` and `SOCIAL_GROWTH_STRATEGY.md`. Two
templates, generated on every build, each carrying one idea and a sentence that
explains the card without its page.

The test is the screenshot test: an image that arrives with no caption and no
link still has to be right. That constraint is what removed the fourth statistic
from the wide template and replaced it with a sentence.

### 3. A letter that separates

`GRADE_STRATEGY_V2.md`. Under V1, 39 of 58 cards grade A and two letters are
unreachable; the column a reader would use to decide where to look does not
separate anything. Under V2 the same slate is 7 A, 23 B, 17 C, 10 D, 1 F, with
53 distinct scores.

The finding underneath it matters more than the numbers: the seven-band step
function was an artifact of the research's reporting buckets, not a property of
the data. The relationship between disagreement and calibration is smooth,
monotone and close to linear, and it holds out of sample in every season tested.

**Not implemented. Recommended.**

### 4. An answer to "so what should I do"

There isn't one, and there will never be one. The honest version is:

> Atlas tells you how much to trust a number. It does not tell you what to do
> with it.

`GRADE_STRATEGY_V2.md` §5 shows why even the grade cannot be turned into a
priority ordering: the most reliable cards are the ones where Atlas agrees with
the market, which is to say the ones where Atlas has said nothing. The grade
prioritises in one direction — it tells a reader what to discount — and the
product should say that rather than implying a ranking it cannot support.

This is the line where a growth team would push, and it is the line that makes
the rest of the product worth anything.

---

## What changed in this sprint

| Rule | Status | Where |
|---|---|---|
| 1 · The board is the product | **Done** | `BOARD_EXPERIENCE.md` |
| 2 · The grade must matter | **Researched, not implemented** | `GRADE_STRATEGY_V2.md` |
| 3 · Team identity | **Done** | `TEAM_IDENTITY_GUIDE.md` |
| 4 · Simplify by half | **Done** | three tiers; featured cells collapse on a phone |
| 5 · Social first | **Done** | `SOCIAL_GROWTH_STRATEGY.md` |
| 6 · Homepage ordering | **Recommended: hybrid** | `BOARD_EXPERIENCE.md` |
| 7 · The Athletic test | **Done, and checkable** | below |
| Grade + Rank | **Recommended against** | `GRADE_STRATEGY_V2.md` §7 |

Concretely, in the built product:

- The card hero is a head-to-head on a phone — two crests either side of "at",
  52px, names underneath — instead of two stacked rows.
- Driver rows stack name over value on a phone instead of wrapping both across
  three columns.
- Featured cells collapse to a single line of numbers on a phone. All three
  featured cards plus the first day block now fit in one 844px screen; two used
  to fill it.
- Board crests are 30px on desktop, 25px on a phone.
- The wide social template spends its last block on a sentence rather than a
  fourth statistic.
- The difference is only coloured above one point, matching the card.

---

## The Athletic test, made checkable

> *Would a sports fan use this? Not: would a bettor use this?*

A taste question becomes a product test if it has answers that can be checked.
Three properties, each verified rather than asserted:

1. **No surface names a side.** Enforced by a test that renders every page type
   and every social template and scans the visible text for the forbidden
   vocabulary, with a context window so football language does not trip it.
2. **The grade is the largest element on the card** — a 92px mark against an
   8px team accent — and it goes *down* as the product gets louder. A sportsbook's
   most prominent element is the thing it wants you to act on.
3. **The board has a "Marked down" filter.** No product whose purpose is
   conversion builds a control for finding its own weakest output.

A fourth, softer one: **nothing on any Atlas surface moves.** No countdown, no
live update, no animation. Motion implies urgency and Atlas is a pre-kickoff
product with nothing to hurry anyone toward.

---

## What would have to be true for this to work

Stated as falsifiable claims, so that in a season it is possible to say whether
it did.

1. **The F card outperforms the A card socially.** If Atlas's best-performing
   posts are its most confident ones, the audience has misunderstood the
   product.
2. **"Marked down" is used.** A filter for the weakest cards that nobody touches
   means the honesty is decoration.
3. **Readers return between slates.** Today there is nothing to return for; the
   reliability record is the candidate and it is unbuilt.
4. **The grade's letters stay separated after V2.** The V2 thresholds are set
   from seven seasons; an eighth should not move the distribution much. If it
   does, the thresholds were overfitted.

---

## The order of the next work

1. **Implement V2** (`GRADE_STRATEGY_V2.md`), with the A+ caveat published
   beside it. Everything else on the board depends on the letters separating.
2. **A second market data provider.** `books quoting` is 1 on all 58 cards, so
   market depth carries no information anywhere in the product — not in the
   grade, not in the cautions. It is a tracker change and it improves the
   reliability record too.
3. **The public reliability record.** The only candidate for a reason to visit
   on a Tuesday, and the surface that makes every other claim checkable.
4. **NFL, when it is calibrated.** Not before, and the page that says so is
   doing more for the product than an uncalibrated card would.

---

## What must not change

- No side, ever, anywhere, in any format, for any reason.
- No figure that implies a return.
- The grade is computed and never entered by hand.
- The calibration table — and, under V2, the calibration curve — is recomputed
  from the warehouse on every build, so the site cannot drift from the research
  it cites.
- Bright surfaces. Dark mode exists so an OS setting does not produce a glaring
  page at night; it is never the designed default and never used in marketing.
