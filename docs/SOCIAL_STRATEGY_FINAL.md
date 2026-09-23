# Atlas — Social Strategy, Final

**Rule 7: every card generates a website version, a share version and a social
version without redesign.**

`SOCIAL_GROWTH_STRATEGY.md` is the channel strategy — what to post, what never
to post, and the growth thesis. This document is the artefact specification and
what changed to make it work.

---

## One card, three surfaces, one build

```
python -m atlas.site.build
```

produces, for the same `Card` object and from the same numbers:

| Surface | Output | Job |
|---|---|---|
| **Website** | `site/ncaaf/{slug}.html` | the full card, three tiers |
| **Share** | Open Graph and Twitter meta in that page's `<head>` | what a pasted link unfurls into |
| **Social** | `site/social/{slug}-wide.png`, `-square.png` | what gets posted and screenshotted |

Nothing is made by hand and nothing is redesigned between them, so a social card
cannot drift from the page it links to. The social templates read the same
`Card`, the same grade and the same calibration band the page does.

---

## Template A — 1200 × 675

The default post. *This is the number, and this is how much Atlas trusts it.*

```
  ▌accent (away | home)
  Atlas Sports Intelligence          RESEARCH · ANALYTICS · CONTEXT
  ─────────────────────────────────────────────────────────────────
  [crest][crest]

  Colorado St at UTSA
  Sat 26 Sep · 12:00 PM ET · ESPNU

  MARKET          ATLAS          DIFFERENCE        ┌───┐
  UTSA −13.5      58.6           +0.9              │ A │
  total 58.5      projected      on the total      │91 │
                  total                            └───┘
                                                    HIGH
  WHAT THIS MEANS
  Atlas and the market land on the same number — which is where this
  model has been most reliable, and where it adds least.
  ─────────────────────────────────────────────────────────────────
  atlas.football/…       Grade = information quality, not a recommendation
```

**Three numbers, one grade, one sentence.**

---

## Template B — 1080 × 1080

The drivers post. *This is why the model reads the game the way it does.*

Two numbers instead of three, three driver rows, and the grade block anchored to
the footer rule so the layout's slack collects in the middle rather than under
the conclusion.

Use it when the story is *why*, and use it above all when a card grades badly.

---

## Rule 7's hard part: explaining itself

> Social cards must explain themselves without surrounding text.

A screenshot arrives with no caption, no thread, no profile and no link. It has
to survive being wrong about its own context. Three things make a card pass:

1. **The numbers with their labels.** MARKET, ATLAS, DIFFERENCE — a reader who
   knows nothing can tell which is which.
2. **The grade with a word beside it.** `A 91` alone is a symbol; `A 91 · HIGH`
   is a claim.
3. **A sentence saying what it means**, computed from the numbers already on the
   card.

That third one is what changed. The wide template used to spend its last block
on a driver statistic — a fourth number, more information and less meaning.
It now spends it on the sentence:

| Card | Sentence |
|---|---|
| Agreement | *Atlas and the market land on the same number — which is where this model has been most reliable, and where it adds least.* |
| Disagreement | *Atlas projects 4.6 points below the market. Cards in that range claimed 61% accuracy and delivered 52%.* |
| Marked down | *Atlas projects 11.2 points below the market. Cards this far out claimed 77% accuracy over seven seasons and delivered 50%.* |

Note the agreement sentence. It carries the same caveat the card's grade carries
— **the most reliable cards are the ones where Atlas added least** — because a
screenshot of an A card with no caveat is exactly how "A = the one to look at"
would get established.

The footer carries the disclaimer on every card, because the card travels
without its page: *Grade = information quality, not a recommendation.*

---

## What changed this sprint

- **Both templates overlapped their own text.** The wide card drew the kickoff
  line on top of the MARKET label whenever the title fitted on one line; the
  square drew the crests through the title. Both now walk a single cursor down
  the canvas, and each block advances it.
- **Kickoffs were in UTC.** "22:30 UTC" in a timeline is a unit conversion, not
  a time. Now Eastern, labelled.
- **The driver line became the sentence**, as above.
- **The difference now uses the same one-point colour floor as the card**, so a
  card where Atlas and the market agree does not shout.
- **The square template anchors its grade block to the footer**, which removed
  the empty bottom third.
- **Grades are V2**, so the templates now render the full range. Under V1 a
  spread-of-grades selection returned four A cards and one F; it now returns one
  of each letter the slate actually contains.

---

## Production

```
site/social/{slug}-wide.svg     1200 × 675
site/social/{slug}-wide.png     2× raster
site/social/{slug}-square.svg   1080 × 1080
site/social/{slug}-square.png   2× raster
```

SVG is the source and the PNG is rasterised from it at 2×, so text is crisp on a
retina timeline and the SVG can be handed to anyone who wants to resize it.
Crests are embedded as base64 rather than referenced, so a card renders
identically in a tool that will not follow a relative path.

Six cards get templates on each build, chosen as a spread across the grade
range — so the F card is always available and never has to be made specially.

---

## What neither template can express

By construction, not by convention:

<!-- lang-lint: quoting -->
- **No side.** There is nowhere on either template to put one.
- **No record of wins and losses**, no units, no countdown, no figure that
  implies a return.
<!-- lang-lint: end -->
- **No dark background.** Atlas arrives light in a timeline full of dark
  graphics.
- **No team colour behind text.** Team colour is an 8px accent rule at the top
  edge, split at the centre.

The rendered SVG is parsed as XML and scanned for the forbidden vocabulary by
`tests/test_site.py`, the same way every page is. A template that could be
filled with a recommendation would fail the build.

---

## The post worth making

`BRAND_GUIDE.md` already says it: *the most on-brand post Atlas can make is a
card it has graded F, with the reason.*

Under V1 that post existed once a week at best — the rubric produced one F on a
58-card slate. Under V2 the slate carries eleven marked-down cards, so the
honest post is available whenever it is true rather than whenever the arithmetic
happens to allow it.

The measurable version of the whole strategy: **the F card should outperform the
A card.** If Atlas's best-performing posts are its most confident ones, the
audience has misunderstood the product.
