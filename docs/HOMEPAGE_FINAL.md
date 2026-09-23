# Atlas — Homepage, Final

**Rule 1: the board is the product.** The homepage is not navigation; it is
today's board, and a reader who arrives sees games.

`BOARD_EXPERIENCE.md` is the research — why grade-first, league-first and
market-first orderings each fail. This document is what was built.

---

## The page, top to bottom

```
  nav                    wordmark + five links, sticky
  ────────────────────────────────────────────────────────────────
  Week of 24 September   58 cards · 7 graded A or better · 11 marked down
  ┌──────────────────────────────────────────────────────────────┐
  │ search    conference ▾   All  A & up  B & up  Marked down    │  sticky
  └──────────────────────────────────────────────────────────────┘

  FEATURED         ranked matchups, highest-grade cards
                   [three cards]

  RIVALRIES        played in at least eight of the last nine seasons
                   [four rows]

  NEXT KICKOFFS    the next five games on the board
                   [five rows]

  GRADED A         7 cards
  Atlas and the market are closely aligned. Reliable numbers — and the
  cards where Atlas is adding least.
                   [seven rows]

  GRADED B         23 cards
  A moderate disagreement, in the range where the model's claim and its
  realised accuracy stay close.

  GRADED C         17 cards
  A wide disagreement. The model's historical claim starts to run ahead of
  what it delivered.

  MARKED DOWN      11 cards
  A large disagreement, in the range where Atlas has been least reliable
  across seven seasons. Atlas marks these down itself.

  NFL strip · about this week
```

No hero. No marketing. No account controls. The first card is 530px down on a
390px phone, which is inside the first screen.

---

## The sections

### Featured — three cards

Sorted by how many ranked teams are in the game, then by grade. A reader who
came for the big game gets it without scrolling.

**Selected by rank first, not by grade.** Rank is the sport's own consensus
about which games matter; grade is Atlas's opinion about its own numbers. Using
rank as the first key keeps the top of the board from being a list of Atlas's
favourite cards.

### Rivalries — computed, not curated

A pairing counts as a rivalry when the two teams have met in **at least eight of
the nine seasons the warehouse holds**. Keyed on ESPN team ids, because the
warehouse and the scoreboard spell half of college football differently and a
name join silently returns nothing.

179 pairings qualify; four are on this slate.

**Being honest about what this finds.** Texas A&M–LSU and New Mexico–New Mexico
State are rivalries in the cultural sense; Oklahoma State–West Virginia and
Virginia Tech–Boston College are annual conference fixtures. An unbroken annual
series is what a rivalry *is* operationally, and Atlas has no editorial list —
inventing one would be a claim the data cannot support. So the section states
its own definition in the subtitle, where a reader can disagree with it.

### Next kickoffs — five rows

The five soonest games, with days attached. It is the only time-ordered section
left and it does the job the day blocks used to: answering "what's on next".

### The grade sections

Four blocks — A, B, C, and D & F together as "Marked down" — each sorted by
score, each carrying a **caption that says what the letter means**.

The captions are not decoration. A board grouped by letter reads as a ranking of
what to look at first, and the letter does not mean that:

> **Graded A** — Atlas and the market are closely aligned. Reliable numbers —
> and the cards where Atlas is adding least.

That second clause is the finding from `GRADE_STRATEGY_V2.md` §5: cards where
Atlas and the market agree to within a point realise 50.8% against a 51.3%
claim, a coin flip. The heading is the cheapest place in the product to stop the
misreading, so it is where the caveat goes.

**Note on the ordering.** `BOARD_EXPERIENCE.md` recommended time as the board's
structure for exactly this reason, and this sprint's brief asked for grade
sections. Both are now present: the grade blocks are the main list, and "Next
kickoffs" keeps the time view alive at the top. The captions carry the cost of
the change. If the grade blocks should move below the time view instead, that is
a reordering of four lines in `homepage()`.

---

## The row

```
⟦crest⟧⟦crest⟧ Northwestern at Indiana #5      IU −21.0 · 49.5   ⟦B⟧
Fri 8:00 PM ET · FOX                            Atlas −1.4
```

Six things, in the order a reader needs them: crests, teams, rank, kickoff and
TV, the market number, Atlas's difference, the grade.

Two changes this sprint, both from reading the rendered board rather than the
markup:

- **One rank chip, not two.** Two ranks beside a long matchup title pushed the
  title into the numbers column — `#23 #10 Texas A&M at LSU` wrapped to three
  lines. The row now shows the better of the two ranks; the card shows both.
- **The numbers column is capped at 108px on a phone.** Its two values never
  wrap, so without a cap it took whatever width it wanted and the title wrapped
  instead.

Rows in sections that are not time-ordered carry the day (`Fri 8:00 PM ET`);
rows in "Next kickoffs" carry it too. Nothing on the board shows a projected
score, a win probability, a line movement or a side.

---

## Filtering

Search, conference, and four grade filters. Plain DOM over already-rendered
rows: the page is complete before the JavaScript loads and works without it.

**"Marked down" is the most on-brand control in the product.** It finds the
cards Atlas trusts least. Under V1 it returned one card out of 58 and was
effectively decoration; under V2 it returns eleven, which is the first time the
control has been worth using.

The count line stays silent while nothing is filtered — "58 games" under a
heading that already says "58 cards" is a line of chrome above the first card.

---

## Mobile

Designed at 390px. Everything below was decided on a phone.

- Head block is two lines: week, then the summary.
- The filter row wraps to two rows and never scrolls sideways. A scrolling strip
  hides its own right-hand end, and the hidden half was the grade filters.
- Featured cells collapse to one line of numbers — `FLA −3.5 · total 58.5` with
  `Atlas +0.4` right-aligned. All three featured cards plus the next section fit
  in one 844px screen; two used to fill it.
- Crests are 25px on a row, 30px on desktop.
- Nav and filters are both sticky.

---

## What the board still does not do

**No date navigation.** The current slate only. Past weeks are where the
reliability record lives, and `PREMIUM_PLAN.md` puts that behind the paid
boundary.

**No sort control.** The sections are the sort. Offering "sort by grade" as well
would be the same information twice, and offering "sort by difference" would be
a pick list.

**No second sport.** The row and the sections survive an NFL slate unchanged;
the filter row gains a league control on the day NFL cards publish.
