# Atlas — Homepage Redesign

The refinement brief's second rule: **cards before navigation.** A reader who
lands on Atlas should be looking at games, not at controls for finding games.

---

## What the homepage is for

One job: **get a reader to the right card in one glance and one tap.**

It is not a dashboard, it is not a league table, and it is not a place to read
numbers. Fifty-eight games do not fit in a reader's head; the board's job is to
narrow them to the one or two worth opening.

That framing settles most of the layout questions. Anything on a row that does
not help someone decide *whether to open this card* is decoration, and
decoration on a board of 58 rows costs 58 times.

---

## Structure

```
  nav                          wordmark + five links, sticky
  board head                   Week of 24 September
                               58 cards · 39 graded A or better · 1 marked down
  board bar                    search · conference · All / A & up / B & up / Marked down
  featured                     three cards: ranked matchups, highest grades
  Thursday, 24 September       1 game
  Friday, 25 September         4 games
  Saturday, 26 September       53 games
  NFL strip                    calibration in progress
  about this week              one disclosure, once
```

Three decisions are worth stating.

**The week heading carries the shape of the slate.** "58 cards · 39 graded A or
better · 1 marked down" is the board's summary in one line — how much there is,
how much Atlas trusts it, and how many cards it has marked down. It is also the
honest place to notice that 39 of 58 is too many, which is what
`GRADE_REWORK_OPTIONS.md` is about.

**Featured comes before the day blocks, and it is small.** Three cards, chosen
by rank and grade. A reader who wants the big games gets them immediately; a
reader who wants a specific game uses search, which is directly above.

**Games are grouped by day, not by conference or by grade.** Day is how a
sports fan thinks about a weekend. Conference and grade are filters, not
structure — sorting by grade would put Atlas's own opinion ahead of the
schedule, which is the wrong emphasis for a product that does not tell anyone
what to do.

---

## The row

```
[crest][crest]  Northwestern at Indiana  #5          IU −21.0 · 49.5     ⟦A⟧
8:00 PM ET · FOX                                     Atlas −1.4
```

Six things, in the order a reader needs them:

1. **Crests** — recognised faster than a name, and they make a row scannable at
   a glance rather than readable at a pace.
2. **Teams, away at home** — the way the matchup is spoken.
3. **Rank** — where either side has one.
4. **Kickoff and TV** — the second question every reader has.
5. **The market number and total** — the reference the whole product is built
   around.
6. **Atlas's difference, then the grade.**

The difference sits *under* the market number rather than beside it, because it
is only meaningful relative to that number. The grade sits at the far right, as
the last thing read on the row and the thing that decides whether the row is
worth a tap.

The whole row is the link, and it is 44px tall or more.

---

## What the board does not show

- **No projected score.** A scoreline on a board row reads as a prediction of
  the game. It belongs on the card, where the grade is next to it.
- **No win probability.** Same reason, more so.
- **No side, no arrow, no highlight.** `BRAND_GUIDE.md`: publishing a side is
  the one thing Atlas will not do, and a board is exactly where that discipline
  would erode first.
- **No line movement.** It is on the card. A board row that showed movement
  would need to show direction, and direction on a board is an arrow, and an
  arrow is a recommendation wearing a disguise.

---

## Filtering

Search, conference, and four grade filters — All, A & up, B & up, Marked down.

The filters are plain DOM over already-rendered rows. The page is complete
before the JavaScript loads and works without it; the controls are the only
part that needs it. At 58 rows this is instant, and it would need revisiting at
a few thousand.

**"Marked down" is the most on-brand control in the product.** It is a filter
for the cards Atlas trusts least, and no competitor has one. It is also the
filter that tells a reader the grade is real — a product that grades itself
down and then lets you sort by it is making a claim it cannot take back.

The count line is silent while nothing is filtered. "58 games" directly beneath
a heading that says "58 cards" is a line of chrome above the first card; it
appears the moment a filter changes the number, which is the only moment it
says anything.

---

## Mobile

Designed at 390px, widened from there.

- The board head stacks to two lines: week, then the summary.
- The filter row wraps to two rows — search and conference, then the four grade
  filters. It does **not** scroll sideways. A horizontally scrolling strip
  hides its own right-hand end, and in review the hidden half was the grade
  filters.
- Featured cards become one column.
- The first card begins at 530px, so a card is on screen before any scrolling.

The nav and the filter row are both sticky, so search and the grade filters
stay reachable through 53 Saturday games without a scroll back to the top.

---

## Measurements

| | Before | After |
|---|---|---|
| Pixels before the first game (390px) | 660 | 530 |
| Chrome lines above the first card | 5 | 3 |
| Elements per row | 5 | 6 (crests added) |
| Horizontal overflow on mobile | yes | none |

---

## What is still open

**The grade column is not yet doing its job.** With 39 of 58 rows showing A,
the column a reader would use to decide where to look does not separate
anything. The fix is not on this page — it is in
`GRADE_REWORK_OPTIONS.md` — but the board is where the cost shows.

**Sort order within a day is kickoff time.** Once the grade distribution is
fixed, "sort by grade" becomes a defensible control. It is not offered today,
because sorting 39 identical letters is not a sort.

**No date navigation.** The board shows the current slate only. Past weeks are
where the reliability record lives and that is a premium surface, specified in
`PREMIUM_PLAN.md` and not built.
