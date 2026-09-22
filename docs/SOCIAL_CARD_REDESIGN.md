# Atlas — Social Card Redesign

**One graphic. One game. One idea.**

A social card is seen for about a second and a half, in a scrolling column,
usually at about 500px wide. It is not a card that was exported; it is a
different medium with a different budget.

---

## What the first version got wrong

The 1200×675 template carried three stat cells, three drivers, a three-line
grade note and a footer. Everything on it was true and correctly formatted, and
at timeline size it read as **a screenshot of a dashboard** — which is exactly
the thing `PRODUCT_VISION.md` says Atlas must not look like. A reader scrolling
past learned nothing, because there was nothing large enough to learn in a
second.

The 1080×1080 template had the same problem with more room to have it in.

---

## The rule applied

Each template now carries **one idea**, and everything on it either is that
idea or identifies the game it belongs to.

| Template | The one idea |
|---|---|
| 1200×675 — the default post | *This is the number, and this is how much Atlas trusts it.* |
| 1080×1080 — the drivers post | *This is why the model reads the game the way it does.* |

---

## Template A — 1200 × 675

```
  ▌accent────────────────────────────────────────────────────┐
  Atlas Sports Intelligence              RESEARCH · ANALYTICS · CONTEXT
  ─────────────────────────────────────────────────────────────
  [crest][crest]

  C Michigan at Miami
  Sat 26 Sep · 6:30 PM ET · CW

  MARKET          ATLAS          DIFFERENCE          ┌───┐
  MIA −41.5       52.3           −11.2               │ F │
  total 53.5      projected      on the total        │33 │
                  total                              └───┘
                                                      LOW
  WHAT THE MODEL IS READING
  Pace and possessions · 100 plays · 26th percentile
  ─────────────────────────────────────────────────────────────
  atlas.football/…            Grade = information quality, not a recommendation
```

**Three numbers, one driver, one grade.** Down from three cells, three drivers
and a paragraph.

- **Crests, then the game, at 58px.** A reader recognises two marks before they
  read two names. The title is the largest text on the card.
- **The three numbers are the whole argument** — what the market says, what
  Atlas says, and the distance between them. That is the sentence the card
  exists to make.
- **The grade is a mark, not a sentence.** Letter, score, and one word: VERY
  HIGH / HIGH / SOLID / MIXED / LOW. The explaining happens on the page.
- **One driver.** The first one, as a single line. Three drivers is a list, and
  a list in a timeline is read as a table and skipped.
- **The footer states what a grade is**, on every card, because the card will
  travel without its page.

**The driver is the first thing dropped.** When a title needs two lines, it
takes the room the driver would have used, and the card ships without it. A
cramped card is worse than a quieter one.

---

## Template B — 1080 × 1080

The square is the *why* card, and the one Atlas should post most often when a
card grades badly.

```
  Atlas Sports Intelligence
  ─────────────────────────────────────────────
  [crest][crest]

  C Michigan at Miami
  Sat 26 Sep · 6:30 PM ET · CW

  ┌─ MARKET TOTAL ──┐   ┌─ ATLAS PROJECTS ──┐
  │ 53.5            │   │ 52.3              │
  │ opened 54.5     │   │ unanchored 42.3   │
  └─────────────────┘   └───────────────────┘

  WHAT THE MODEL IS READING
  Pace and possessions        100 plays · 26th percentile
  Offensive efficiency        MIA +0.24 EPA/play
  Success rate                MIA +18.7 pts
  ─────────────────────────────────────────────
  ┌───┐  Low-reliability card
  │ F │  Cards 10+ points from the market claimed 77%
  │33 │  accuracy and delivered 50%. Atlas grades its
  └───┘  own card down.
  ─────────────────────────────────────────────
  atlas.football/…              Research. Analytics. Context.
```

Two numbers instead of three, because the square's idea is the drivers and the
numbers are there to give them a scale. The grade block is the conclusion, so
it **anchors to the footer rule** rather than sitting wherever the drivers
happened to end — otherwise the layout's slack collects underneath it and the
card reads as unfinished.

---

## Defects fixed in this pass

**Both templates overlapped their own text.** On the wide card the kickoff line
was drawn on top of the "MARKET" label whenever the title fitted on one line.
On the square the crests overlapped the title. Both were the same class of
error: two blocks whose positions were computed from separate expressions. Both
templates now walk a single cursor down the canvas, and each block advances it.

**Kickoffs were printed in UTC.** "22:30 UTC" in a timeline is a unit
conversion. Now "6:30 PM ET".

**The square's bottom third was empty.** Fixed by the footer anchoring above.

---

## What neither template can express

By construction, not by convention:

<!-- lang-lint: quoting -->
- **No side.** There is nowhere on either template to put one. This is the
  point.
- **No record of wins and losses**, no units, no countdown, no figure that
  implies a return.
<!-- lang-lint: end -->
- **No dark background.** A dark card arriving in a bright timeline looks like
  every other graphic in this category. Atlas arrives light.
- **No team colour behind text.** Team colour is an 8px accent rule at the top
  edge, split at the centre. It is chrome, never data.

A template that cannot be filled without one of the forbidden words is a broken
template. The rendered SVG is parsed as XML and scanned by
`tests/test_site.py`, the same way every page is.

---

## The card worth posting

`BRAND_GUIDE.md` already says it: *the most on-brand post Atlas can make is a
card it has graded F, with the reason.*

The square template above is that post. Nobody else in this category will
publish a graphic whose conclusion is "our own number is 11 points from the
market and history says do not trust that", and it says more about the product
than any A-grade card could.

Both templates are generated for a spread of grades on every build — one of
each letter where the slate has one — so the F card is always available and
never has to be made specially.

---

## Output

```
site/social/{slug}-wide.svg    1200 × 675
site/social/{slug}-wide.png    2× raster
site/social/{slug}-square.svg  1080 × 1080
site/social/{slug}-square.png  2× raster
```

SVG is the source and the PNG is rasterised from it at 2×, so the text is
crisp on a retina timeline and the SVG can be handed to anyone who wants to
resize it. Crests are embedded as base64 rather than referenced, so a card
renders identically in a tool that will not follow a relative path.
