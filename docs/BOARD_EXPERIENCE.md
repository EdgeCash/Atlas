# Atlas — Board Experience

The brief's Rule 1: **the board is the product.** Rule 6 asks how it should be
ordered — grade first, league first, market first, or hybrid.

---

## The question behind the question

Ordering is not a layout preference. The first sort a product applies is a claim
about what matters, and a reader adopts it without noticing. So the four options
are four different products.

| Option | The board becomes | What a reader concludes |
|---|---|---|
| **A. Grade first** | Atlas's most-trusted cards, in order | "Start at the top" |
| **B. League first** | NCAAF, then NFL | "Pick your sport" |
| **C. Market first** | Biggest disagreements, in order | "These are the opportunities" |
| **D. Hybrid** | The weekend, with Atlas's read on each game | "Here is Saturday" |

---

## Why each of the first three fails

### A. Grade first

`GRADE_STRATEGY_V2.md` §5 settles this empirically. Cards where Atlas and the
market agree to within a point realise 50.8% against a claim of 51.3% — a coin
flip, p = 0.69. They grade highest because they are the most reliable, and they
are the most reliable because **Atlas has contributed nothing to them.**

A grade-first board puts the least informative cards at the top and tells the
reader to start there. It is the one ordering that is actively misleading.

It also breaks when the distribution is working. Under V2 the slate has 7 A
cards and 23 B cards; under V1 it had 39 A cards. Sorting by a letter that 39
cards share is not a sort.

### B. League first

Atlas publishes one league. `PRODUCT_VISION.md` stages NFL behind calibration,
and `nfl.html` exists to explain why. A league-first board is a tab bar with one
tab and a page saying "not yet" — it advertises the product's largest gap on
first contact.

It becomes the right answer the day NFL cards publish. Not before.

### C. Market first

An ordering by |Atlas − market|, descending, is a list of the games where Atlas
most disagrees with the closing number, ranked best-first.

That is a pick list. The word is absent; the artefact is not. Worse, the
evidence says the ordering is backwards: the cards at the top of a market-first
board are the cards Atlas grades **F**, because disagreement predicts model
failure. A market-first board sorts by the thing that predicts being wrong.

---

## Recommendation: D, Hybrid — and specifically this hybrid

**Time is the structure. Grade is a column and a filter. Market is a number on
the row. Nothing is ranked.**

```
  Week of 24 September          58 cards · 39 graded A or better · 1 marked down
  ┌──────────────────────────────────────────────────────────────────────┐
  │ search        conference ▾    All   A & up   B & up   Marked down    │
  └──────────────────────────────────────────────────────────────────────┘

  FEATURED   ranked matchups, highest-grade cards
  ┌────────────┐ ┌────────────┐ ┌────────────┐
  │ Ole Miss   │ │ Texas at   │ │ Missouri   │
  │ at Florida │ │ Tennessee  │ │ at Miss St │
  └────────────┘ └────────────┘ └────────────┘

  THURSDAY, 24 SEPTEMBER   1 game
  ⟦crest⟧⟦crest⟧ Liberty at Coastal        LIB −2.5 · 50.5   ⟦B⟧
  7:30 PM ET · ESPN                          Atlas +4.8

  FRIDAY, 25 SEPTEMBER   4 games
  …
  SATURDAY, 26 SEPTEMBER   53 games
  …
```

**Why time.** It is how a sports fan holds a weekend in their head. Nobody asks
"what are the most reliable games this week"; they ask "what's on Saturday". It
is also the only ordering that is not a claim — a kickoff time is a fact about
the world, not an opinion about the card.

**Why featured, and why it is small.** Three cards, chosen by ranking and grade.
A reader who came for the big games gets them without scrolling; everyone else
loses about one screen. It answers "what's the game this week" without answering
"which card should I act on".

**Why grade as a filter, not a sort.** A filter is a question the reader asks. A
sort is an answer the product gives. "Marked down" is the filter that matters,
and it is the most on-brand control in the product: no competitor builds a way
to find its own weakest output.

**Why the difference is on the row but small.** A reader deciding whether to open
a card wants to know whether Atlas has anything to say about it. Putting the
difference under the market number, in the secondary ink, at 12.5px, says it
without making it the point of the row.

---

## The row, defended element by element

```
⟦crest⟧⟦crest⟧ Northwestern at Indiana  #5      IU −21.0 · 49.5   ⟦A⟧
8:00 PM ET · FOX                                 Atlas −1.4
```

| Element | Why it earns its place |
|---|---|
| Two crests, 30px | Rule 3: identify the game before reading it. Recognised in about 200ms against about 500 for a name. |
| Teams, away at home | The way the matchup is spoken aloud |
| Rank, where there is one | The single strongest signal of "this one matters" that is not Atlas's own opinion |
| Kickoff and TV | The second question every reader has |
| Market line and total | The reference the whole product is built around |
| Atlas's difference | Whether Atlas has anything to say |
| Grade | Whether it is worth listening to |

Everything else was considered and cut: win probability (a projection presented
with a score's confidence), line movement (needs a direction, and a direction on
a board row is an arrow, and an arrow is a recommendation), projected score
(reads as a prediction of the game), conference (already a filter), records
(three more numbers on 58 rows to save one tap).

---

## Mobile

The board is designed at 390px and widened from there. Every decision below was
made on a phone first.

- **Head block is two lines**, week then summary.
- **Filter row wraps to two rows and never scrolls sideways.** A horizontally
  scrolling strip hides its own right-hand end; in review the hidden half was
  the grade filters.
- **Featured cells collapse to one line of numbers** — `FLA −3.5 · total 58.5`
  with `Atlas +0.4` right-aligned — instead of a three-column grid with labels.
  This is the single largest space saving on the page: all three featured cards
  plus the first day block now fit in one 844px screen, where two featured cards
  used to fill it.
- **Crests drop to 25px** on a row, below which the team names begin to wrap.
- Nav and filters are both sticky, so search stays reachable through 53 Saturday
  games.

---

## What the board is not

- **Not a dashboard.** No totals, no trends, no "cards graded this season".
- **Not a leaderboard.** No rank, no position, no "top cards". See
  `GRADE_STRATEGY_V2.md` §7.
- **Not a feed.** It does not update while you look at it. There is no reason
  for a pre-kickoff product to move, and motion implies urgency.
- **Not paginated.** 58 rendered rows filter instantly. This would need
  revisiting at a few thousand.

---

## Open, and deliberately not built

**Date navigation.** The board shows the current slate only. Past weeks are
where the reliability record lives, which `PREMIUM_PLAN.md` puts behind the
paid boundary.

**Sort by grade.** Defensible once V2 makes the letters separate, and still not
recommended — see Option A above. If it ships it should be a control the reader
turns on, never the default.

**A second sport.** The day grouping and the row survive an NFL slate unchanged;
the filter row gains a league control and Rule 6's Option B becomes live.
