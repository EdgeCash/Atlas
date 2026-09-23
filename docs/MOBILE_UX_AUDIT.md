# Atlas — Mobile UX Audit

**Track 2.** One-thumb usage at 390×844, against the built site.

---

## The test

Phone held in one hand. Thumb reaches roughly the **bottom two thirds** of the
screen comfortably and the top third only by shifting grip. So the question for
every control is: *can it be operated without changing how the phone is held?*

---

## The board

### Layout, top to bottom

```
  0px    nav — sticky
  95px   Week of 24 September
  135px  58 cards · 7 graded A or better · 11 marked down
  180px  Every game gets a card — and a letter for how much that card's
         information has historically been worth. How to read one
  280px  [ Search teams ] [ All conferences ▾ ] [ All ]      — sticky
  340px  [ A & up ] [ B & up ] [ Marked down ]
  430px  FEATURED
  480px  first card
  844px  ── fold ──
```

### What works

**Both sticky bars stay reachable.** The nav and the filter row pin to the top,
so search and the grade filters are available through all 53 Saturday games
without scrolling back. They are in the top third — out of easy thumb reach —
but they are *reached deliberately*, not incidentally, which is the right trade
for a control you use once per session.

**The whole row is the tap target**, 60–70px tall, far above the 44px minimum.
There is no small chevron or secondary action to miss.

**Filter chips are 40px tall and 70–120px wide.** Comfortable one-thumb
targets, and they wrap to two rows rather than scrolling sideways — a
horizontally scrolling strip hides its own right-hand end, and in an earlier
review the hidden half was the grade filters.

**Nothing on the board requires precision.** No sliders, no drag, no long
press, no hover-only affordance.

### What was fixed this pass

| Finding | Action |
|---|---|
| Search placeholder truncated to *"Search a team or c"* | shortened to `Search teams` |
| Board summary line (*"7 graded A or better"*) is jargon to a first-time reader | one-line explainer above the filters, linking to the landing page |

### What is still open

**`Atlas +0.4` on a board row is unlabelled.** Plus 0.4 of what? The card says
"on the total"; the row has no width for it at 390px.

Two proposals, neither shipped because Rule 1 says polish only:

1. **Show Atlas's number instead of the difference** — `total 58.5 · Atlas
   58.9`. Two comparable numbers, no sign convention to learn. Costs the
   at-a-glance sense of *how far apart* they are.
2. **Add the unit once, as a column note under the FEATURED heading** — "Atlas
   figures are on the game total". One line for the whole board.

Proposal 2 is the cheaper one and it is the recommendation if you want it
fixed.

**The scroll is long.** 58 cards across four grade sections is roughly 12
screens. There is no jump-to-section control, no back-to-top, and the filters
are the only navigation. For a weekly board that is acceptable; at two sports
it would not be.

---

## The card

### Layout at 390×844

```
  0px    nav — sticky
  95px   hero: crests either side of "at", names, records, kickoff, TV, venue
  460px  MARKET / ATLAS / DIFFERENCE
  700px  the grade — 92px mark, three lines, bar, disclaimer
  1180px WHY — three drivers
  1500px BE CAREFUL ABOUT
  1700px New to Atlas?
  1800px six panels
```

The first 844px carries the game, the three numbers, and the top of the grade
block. Scrolling once reaches the rest of the grade, all three drivers and the
first caution.

### What works

**Panels are `<details>`.** The summary is a full-width 56px target, it works
with the browser's own find-in-page, and it needs no JavaScript. Nothing about
the card depends on a script running.

**One column throughout.** No horizontal scroll anywhere on any page — checked
across all 179.

**Every number is tabular**, so opening a panel does not make the numbers above
it jitter.

**Nothing moves.** No animation, no transition, no auto-update. Audited by
`scripts/audit_site.py`, which fails the build on `@keyframes`, `animation:`,
`setInterval` or a countdown.

### What was fixed this pass

| Finding | Action |
|---|---|
| `Mkt` and `Diff` as narrow-screen labels | full words — `Market`, `Difference` |
| Panel summaries written for someone who already knew | rewritten in plain English |
| The caution used research vocabulary and repeated the grade's figures | rewritten, and a test now fails on jargon in a caution |
| No way to learn what Atlas is without finding the nav | one line at the end of the five-second view |

### What is still open

**The grade block is tall on an F card** — three lines of explanation plus the
bar plus the disclaimer is about 450px. That is the price of Rule 4 (the grade
teaches itself) and it is the right price, but it means the drivers start below
the fold on marked-down cards. Left alone: a reader on an F card should be
reading the F.

**Driver rows stack name over value on a phone**, which is correct, but it
makes the `Why` block four rows tall where desktop is three. No action.

---

## Reachability summary

| Control | Position | One-thumb? |
|---|---|---|
| Board row (open a card) | body | **yes** |
| Panel summary | body | **yes** |
| Grade filters | sticky top | reachable with a shift; deliberate use |
| Search | sticky top | same |
| Conference select | sticky top | same, and it opens the OS picker |
| Nav links | sticky top | same |
| Footer links | bottom of page | yes |

Nothing important lives in a corner, behind a gesture, or in a hover state.

---

## Accessibility, checked

- **Skip link** to `#main` on every page.
- **Every crest has alt text** of the team's short name, so identity is never
  carried by an image alone.
- **`aria-current="page"`** on the active nav item.
- **`aria-pressed`** on the grade filter chips.
- **`aria-live="polite"`** on the filtered count.
- **Colour is never the only carrier.** The grade is a letter first and a
  colour second; driver direction is stated in text beside the crest.
- **Tabular figures and a 16px base**, so nothing is below the platform
  minimum.

Not verified in this pass: screen-reader traversal on a real device, and
`prefers-reduced-motion` (there is no motion to reduce).

---

## Verdict

**The board and the card are one-thumb usable at 390px.** No control is out of
reach in a way that matters, nothing requires precision, and nothing depends on
JavaScript.

The two remaining gaps are both readability rather than reachability —
unlabelled `Atlas +0.4` on a board row, and a long unassisted scroll — and both
have proposals above rather than changes, because the board and the card are
approved.
