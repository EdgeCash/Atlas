# Atlas Sports Intelligence — Product Vision

**Research. Analytics. Context.**

---

## What Atlas is

A sports intelligence product for NFL and college football. One game, one
card, one URL. Every card answers four questions and nothing else:

1. What does the market think?
2. What does Atlas think?
3. Why?
4. How much confidence does this information deserve?

Users decide what to do with the answers. Atlas does not decide for them, and
the product is built so that it *cannot* quietly start to.

## What Atlas is not

<!-- lang-lint: quoting -->
Not a sportsbook. Not a picks service. Not a tout account. Atlas publishes no
selections, no stake sizing, no unit counts and no projected returns — not as
a compliance posture but because five phases of research established that
Atlas does not have an edge worth acting on, and a product that implied
otherwise would be lying.
<!-- lang-lint: end -->

---

## The idea the whole product rests on

Every competitor in this category sells confidence. Atlas sells **calibrated**
confidence, which is a different and rarer thing.

Atlas has measured its own model against 5,778 college football games and
knows, band by band, where it is reliable and where it is not. Two findings
shape every screen:

**The market is the strongest forecast available.** Atlas weights it at
**1.00 on spreads** and **0.89 on totals** — fitted from the data, not chosen.
Against 5,778 games the model's own contribution to a spread was
statistically indistinguishable from zero.

**A large disagreement is a warning, not an opportunity.** Where Atlas sits
10+ points from the market total, it has historically claimed 77% accuracy and
delivered 49.5%. The gap widens monotonically with the size of the
disagreement.

So Atlas ships the **anchored** projection — the accurate one — and shows the
unanchored model beside it so the correction is visible rather than hidden.
And the loudest cards get the **lowest** grades.

### Why this is the product, not a caveat

Everyone else in this market shouts loudest exactly where their model is
weakest, because a big disagreement makes a compelling post. Atlas does the
opposite, publicly, on every card, with the seven-season record beside it.

That is the whole differentiator. It cannot be copied by anyone who has not
done the measurement, and it is the only defensible position for a product
that has honestly established it has no edge to sell.

---

## Positioning

|  | Atlas | Category norm |
|---|---|---|
| Sells | information quality | confidence |
| Loudest when | the model is reliable | the model disagrees most |
| Aesthetic | bright, editorial, calm | dark, neon, urgent |
| What gets published | a card | a selection |
| Record published | calibration and line movement | wins and losses |
| Reader leaves with | a view and its error bars | an instruction |

Reference points: **The Athletic** for editorial seriousness, **Apple** for
restraint and density discipline, **Bloomberg** for the assumption that the
reader is a professional who wants the number and its provenance.

---

## Phase 1 scope

**NFL and NCAAF only.** No MLB, NBA, WNBA, DFS or props. No expansion until
this product works.

### An honest scoping note on NFL

Atlas's model is built and validated on college football. **There is no NFL
model.** Shipping NFL projections today would mean shipping an untested model
behind a grade framework whose entire credibility comes from having been
tested.

The recommendation is therefore a staged NFL launch:

| Stage | What ships | What it needs |
|---|---|---|
| 1 (now) | NFL schedules, scores, team pages, market snapshot | odds + schedule feed |
| 2 | NFL projections and drivers | nflverse play-by-play 2018–, warehouse rebuilt on NFL, model refitted |
| 3 | NFL grades | the same seven-season calibration study NCAAF has |

Stage 3 is the gate. A grade means "here is how this model has performed on
cards like this one"; until that sentence is true for NFL it is a decoration.
The homepage shows the NFL section in this state rather than hiding it, with
one sentence explaining why.

Estimated work: the warehouse, feature and model layers are sport-agnostic —
the NCAAF pipeline is roughly 80% reusable. The binding constraint is the
calibration study, which needs completed seasons and cannot be rushed.

---

## The card

Eight sections, specified field by field in
[`ATLAS_CARD_SPEC.md`](ATLAS_CARD_SPEC.md):

1. Game header
2. Market snapshot
3. Atlas projection
4. Atlas difference
5. Atlas grade
6. Why Atlas sees it this way
7. Market intelligence
8. Reliability

Section 5 is the product's centre of gravity. The grade is not a
recommendation — it is a statement about how much weight the information on
the rest of the card deserves, computed from historical calibration, market
agreement, signal stability and data completeness.

---

## Site structure

| Route | Contents | Tier |
|---|---|---|
| `/` | today's games, search, filters | free |
| `/{league}/{away}-{home}` | the full matchup card | mixed |
| `/team/{slug}` | season profile, recent form, schedule | free (history premium) |
| `/player/{slug}` | **reserved, not implemented** | — |
| `/research` | methodology, the reliability record | free |

Player pages are reserved and deliberately empty. Atlas has no player-level
model, and a page that looked like one would imply research that does not
exist.

---

## What "done" looks like for Phase 1

- Every FBS game with a market has a card, every week, with a grade.
- The reliability record is public, current and free.
- A reader can get from the homepage to the number they came for in under ten
  seconds on a phone.
<!-- lang-lint: quoting -->
- No screen, export, post or email contains a selection, a stake, a unit or a
  projected return.
<!-- lang-lint: end -->
- NFL is at stage 1 or better, with its stage stated on the page.

## What would mean it failed

- Grades cluster: if 80% of cards grade B, the grade is decoration.
- The reliability record stops being published, or moves behind the paywall.
- The first "just this once" selection.

---

## Relationship to the research

This product is the front end of work that is already finished and already
falsifiable. Nothing on a card is invented for the product:

| Card element | Source |
|---|---|
| Market anchoring weights | `reports/atlas_beta_framework.md` |
| Calibration by disagreement band | `reports/atlas_beta_framework.md` |
| Grade rubric inputs | same, plus `reports/atlas_gamma_assessment.md` |
| Line movement and CLV record | `reports/live_clv_tracking.md` |
| Point-in-time guarantee | `docs/POINT_IN_TIME.md` |

The live CLV tracker keeps running underneath the product on its own
pre-registered kill criteria. If those criteria fail, the honest consequence
is that Section 7's market-direction claims come off the card — not that the
product quietly keeps making them.
