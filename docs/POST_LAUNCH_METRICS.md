# Atlas — Post-Launch Metrics

**Track 6.** What to measure, what each number would mean, and what Atlas
refuses to measure.

---

## The one number

**The share of readers who open a marked-down card.**

Every other metric in this document is context for that one. Atlas's entire
position is that it tells you when not to trust it; if nobody reads the cards
where it says so, the position is decoration and the product is a slightly
better-looking version of everything else in the category.

Target at launch: **no target.** There is no prior. The first season sets the
baseline, and the honest thing is to publish it.

---

## What to measure

### Product

| Signal | Why it matters | What "bad" looks like |
|---|---|---|
| **Most viewed cards** | whether readers go to big games or to interesting ones | only ranked matchups — the grade is doing nothing |
| **Grade of the cards opened** | the headline number above | A-heavy — the honesty is decoration |
| **"Marked down" filter use** | whether anyone wants the weak cards | near zero — same conclusion |
| **Tier-2 panel opens, by panel** | which detail readers actually want | nobody opens *how this grade was computed* — the grade is being taken on faith, which is the one thing it must not be |
| **Cards per session** | browsing or arriving | 1.0 — everyone comes from a link and leaves |
| **Return rate between slates** | whether Atlas is a habit | near zero — expected at launch, and the reason the reliability record is next |

### Discovery

| Signal | Why it matters |
|---|---|
| **Most searched teams** (site search) | what a team page should lead with, and which teams deserve depth |
| **Landing page → board conversion** | whether the thirty-second page works |
| **Search queries that reach a card** | whether Atlas is found for "*team* vs *team* prediction" or for something else entirely |
| **Share of arrivals that are first-time** | growth vs. a small loyal group |

### Social

| Signal | Why it matters |
|---|---|
| **Marked-down card vs A card engagement** | the positioning test, in the sharpest form available |
| **Click-through to the card, not just impressions** | whether the post is an excerpt or a substitute |
| **Screenshots reposted without the link** | the test the templates were designed for; if these circulate and still read correctly, the design worked |

### Email

| Signal | Why it matters |
|---|---|
| **Click-through to a marked-down card vs an A card** | same test, different channel |
| **Weekly → site return rate** | whether the email is a reason to visit or a replacement |
| **Unsubscribe rate after a correction** | whether readers punish the thing that makes Atlas worth reading |

That last one is the most uncomfortable number in this document. If corrections
drive unsubscribes, Atlas has the wrong audience — and the answer is not to
stop sending corrections.

---

## What Atlas will not measure

This list is shorter than the one above and it matters more.

- **Nothing that identifies an individual reader across sessions.** No
  fingerprinting, no cross-site identity, no ad-network pixel. Atlas has no
  account system and no reason to build one until premium exists.
- **Nothing about what a reader does after leaving.** No affiliate
  attribution, no outbound click tracking to anywhere that takes money. The
  moment Atlas can see that, someone will eventually optimise for it, and
  `FREE_VS_PREMIUM_FINAL.md` rule 4 exists to make that impossible.
- **No A/B tests on the grade.** Not on its wording, not on its prominence, not
  on whether the caveat appears. The grade is a research output, not a
  conversion surface.
- **No engagement scoring of cards.** A "most popular card" widget is one
  product decision away from being a ranking of what to look at, which is the
  thing `GRADE_STRATEGY_V2.md` §5 established Atlas cannot honestly publish.

---

## How it gets measured

**Server logs and a single first-party counter.** No third-party analytics
script. The site is static and has 40 lines of JavaScript; adding a tracker
would multiply that and hand a reader's browsing to somebody else.

What that supports: page views by URL, referrer, first-time vs returning by
day, and — with a few bytes of first-party event logging — panel opens and
filter use. What it does not support: funnels, cohorts, session replay. That is
the right trade.

**The grade of a viewed card is derivable from the URL**, because the build
knows every card's grade. No client-side instrumentation is needed for the
headline number, which is the point.

---

## The launch baseline

Record these in week one and never re-baseline them quietly:

```
cards published        58
graded A or better      7   (12%)
marked down            11   (19%)
pages                 179
sitemap urls          179
build time            ~7s
largest page          ~31 KB
```

Every one of these is printed by `make site` and `make site-audit`, so the
baseline is a build artifact rather than a spreadsheet somebody maintains.

---

## The four claims, and how each would be falsified

From `PRODUCT_EVOLUTION.md`, restated as things a season of data could
disprove.

1. **The marked-down card outperforms the A card.** Falsified if A cards lead
   on every channel for a full season.
2. **"Marked down" is used.** Falsified if the filter's use is indistinguishable
   from zero once the novelty passes.
3. **Readers return between slates.** Falsified if return rate stays flat after
   the public reliability record ships. That would mean the record is not the
   habit-forming surface, and the roadmap is wrong.
4. **V2's letters stay separated after an eighth season.** Falsified if the
   distribution collapses back toward one letter, which would mean the
   thresholds were fitted to seven seasons rather than to the phenomenon.

Claim 4 is the only one Atlas can test without any readers at all, and it
should be tested the week the eighth season closes whatever the traffic looks
like.
