# Atlas — Matchup Card, Final

**Rule 2: the matchup card is the product.** Five questions, answered in under
five seconds, on a phone.

---

## The five questions, and where each is answered

| # | Question | Where | Visible without scrolling? |
|---|---|---|---|
| 1 | What does the market think? | Answer row, cell 1 — `MIA −41.5`, `total 53.5` | yes |
| 2 | What does Atlas think? | Answer row, cell 2 — `5–47`, `CMU–MIA · total 52.3` | yes |
| 3 | Why? | **Why** — three drivers with the favoured team's crest | yes |
| 4 | How trustworthy is the information? | **The grade**, 92px, with its three-line lesson | yes |
| 5 | What should make me cautious? | **Be careful about** — computed per card | first item visible, rest one scroll |

All five are above 844px on a 390px phone. Question 5's section header and first
caution sit at the fold; on a D or F card the caution is the thing the reader
scrolls into, which is the right order for that card.

---

## The three tiers

### Tier 1 — always visible

```
  ▌accent rule (away | home)
  ┌──────────────────────────────────────────────┐
  │   [crest]          at          [crest]       │
  │  C Michigan               #6 Miami           │
  │  Mid-American · 2-1       ACC · 3-0          │
  │  ──────────────────────────────────────────  │
  │  Sat 26 Sep · 6:30 PM ET · CW · Hard Rock    │
  └──────────────────────────────────────────────┘
  ┌───────────┬────────────┬───────────┐
  │ MKT       │ ATLAS      │ DIFF      │
  │ MIA −41.5 │ 5–47       │ −11.2     │
  │ total 53.5│ CMU–MIA ·  │ on the    │
  │           │ total 52.3 │ total     │
  └───────────┴────────────┴───────────┘
  ┌──────────────────────────────────────────────┐
  │ ┌────┐  Historically unreliable.             │
  │ │ F  │  A very large disagreement of 11.2    │
  │ │ 44 │  points.                              │
  │ └────┘  Across seven seasons, cards this far │
  │         from the market claimed 77% accuracy │
  │         and delivered 50%. Atlas marks its   │
  │         own card down.                       │
  │         ▬▬▬▬▬▬▬░░░░░░░░░░░░░░░░░░░░░░░░░░░░  │
  │         How much weight this card's          │
  │         information deserves — not a         │
  │         recommendation.                      │
  └──────────────────────────────────────────────┘
  WHY  what the model is reading
  ⟦U⟧ Offensive efficiency      MIA +0.24 EPA/play
  ...
  BE CAREFUL ABOUT
  • Atlas sits 11.2 points from the market...
```

### Tier 2 — one tap, native `<details>`

Market detail · Projection detail · How this grade was computed · All drivers ·
Market movement · Reliability record.

No JavaScript. The panels work with find-in-page, they print, and the page is
complete before anything loads. **No information was deleted** — every number
that was on the eight-section card is still on the card.

### Tier 3

Methodology, linked to the research page.

---

## The hero (Rule 5: team identity first)

A head-to-head, not a list of two teams:

- **52px crests either side of "at"**, names underneath, centred. On desktop the
  crests sit outboard with the names inboard and the layout reads left to right.
- Rank, record and conference under each name.
- An 8px accent rule at the top, split at the centre, away colour on the left.
  That is the only place team colour appears; it is chrome, never data.

A reader identifies the game from the two marks before reading either name,
which is the point — a familiar crest is recognised in about 200ms against about
500 for a name.

The stacked version this replaced read as a table of two teams. A matchup has a
shape, and the layout should have it too.

---

## The grade (Rules 3 and 4)

The grade is the largest element on the card: a 92px mark with a 44px letter,
its own full-width block, a confidence bar, and on a D or F card a tinted border
so a marked-down card reads as marked down at a glance.

**It teaches itself.** Three lines, computed from the card's own numbers:

1. **What the letter says** — "Historically reliable." / "Historically
   unreliable."
2. **What Atlas did** — "Atlas and the market are closely aligned, 0.4 points
   apart."
3. **The record behind it** — "Across seven seasons, cards this close to the
   market claimed 51% accuracy and delivered 51%."

Then the smallest line in the block, on every card: *How much weight this card's
information deserves — not a recommendation.*

At the top of the scale the second line carries the caveat that stops the grade
being read as a ranking:

> Agreement is where this model is most reliable, and where it is adding least —
> a top grade means trust the number, not that this is the card to read first.

Opening **How this grade was computed** shows the four component meters, the
arithmetic —

> Atlas sits **11.2 points** from the market. The calibration curve, fitted to
> seven seasons out of sample, expects cards at that distance to fall **24.6%**
> short of what they claim.

— and the conditions in plain words: *"It is week 4. Team profiles are still
shrunk toward last season, and early-season cards have calibrated worse in six
of seven seasons."*

Specification and tests: `GRADE_V2_IMPLEMENTATION.md`.

---

## "Be careful about" (question 5)

Up to three warnings, computed from the card. Never boilerplate:

- a wide disagreement, with that band's claimed-versus-realised record;
- a market with one book behind it;
- a lopsided spread;
- missing team metrics;
- Atlas and the market having moved opposite ways since the total opened.

It deliberately never says *"it is week 4"*. That is true of every card on the
board, and a caution that appears on every card is read as decoration within a
week. It belongs once, on the board, and that is where it is. (The week *does*
reach the grade, as a condition — it just is not a per-card caution.)

A card with nothing to flag says nothing rather than inventing a worry.

---

## Numbers and their colour

**The difference is only coloured above one point.** The 0–1 band is where Atlas
and the market are statistically indistinguishable out of sample, so a
0.3-point difference in alarm red was shouting about nothing. Below the floor it
takes the ordinary ink.

**The projected score names both teams.** `5–47` is a pair of numbers; `CMU–MIA`
underneath makes it a scoreline.

Every number is tabular, so nothing jitters as digits change.

---

## Mobile

- One column throughout, designed at 390px.
- The hero is the head-to-head described above.
- Driver rows stack name over value. Three columns in 358px meant the name and
  the value each took two lines and the row read as four lines of nothing.
- `MIA −41.5` is the longest value the answer row ever holds; at 17px it fits
  without wrapping, and a wrapped number reads as two numbers.
- 44px hit targets; the whole panel summary is the target.

---

## Rule 9: would a sports fan use this?

Checked element by element, and three things are on the card only because the
answer was yes:

- **Records, ranks and conference in the hero.** A bettor does not need them; a
  sports fan orients with them.
- **Venue and broadcast.** The second question every fan has, and no use to
  anyone acting on a number.
- **The drivers in plain language** — "Offensive efficiency · MIA +0.24
  EPA/play" — rather than a coefficient table.

And three things were rejected because the answer was sports-fan no:

- A closing-line-value figure.
- Anything comparing Atlas's number to a price.
- A "sharp money" or market-consensus indicator.

---

## What is not on the card

No side. No lean. No arrow. No highlighted row. No figure that implies a return.
No countdown. Nothing on the card moves.

`tests/test_site.py` renders every page type and scans the visible text for the
vocabulary `BRAND_GUIDE.md` forbids, with a context window so football language
does not trip it, and a separate test checks that no page names a side.
