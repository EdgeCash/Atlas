# Atlas — Onboarding Flow

**Track 1.** A first-time visitor must understand Atlas in under 30 seconds.

Built and live at `/about.html`, linked from the nav ("About") and from every
page footer ("new here").

---

## The thirty-second budget

Thirty seconds is about **one screen and one scroll**. So the test has a
measurable form: *what is above the fold, and is it enough to be right about
Atlas even if the visitor stops there?*

The first screen carries three things and nothing else:

```
  Atlas grades its own numbers.

  Every college football game gets a card: what the market says, what
  Atlas projects, what is driving the difference — and a letter saying
  how much that card's information has historically been worth.
  Atlas never tells anyone what to do with it.

  [ See this week's board ]   [ How to read a card ]
```

A visitor who reads only that knows: it is college football, it is per-game,
there is a market number and an Atlas number, there is a letter about
reliability, and **nobody is being told what to do**. That last clause is in
bold because it is the sentence that decides whether the rest of the product
is read correctly.

Two buttons, because there are exactly two things a first-time visitor wants:
see it, or learn to read it.

---

## The four sections

### 1. What Atlas is

Two cards side by side — *what it is* and *what it is not* — because the
negative is as load-bearing as the positive in this category.

**A research desk, published.** 58 games a week, point-in-time database, seven
seasons, anchored to the market because the testing said the market is the
better starting point. Then: *"it grades itself, in public, on every card,
using its own historical record."*

**What Atlas is not.** Four lines: not a selections service (no card names a
side, not as a lean, not as an arrow), not a sportsbook, not a record of wins
and losses, not urgent.

### 2. How to read a card

Eight numbered steps, in the order a reader meets them on a real card: the
game, the market, Atlas, the difference, the grade, why, be careful about,
everything else.

**Built from a real card, not a mock.** `about_page()` takes the
highest-graded card that has a rank and a broadcast, so the walkthrough always
ends with a live worked example and cannot drift away from the product it
describes. Out of season, when there is no card, the section disappears rather
than showing a hole — there is a test for that.

The step that matters most is the fourth:

> **The difference** — How far Atlas sits from the market on the total. This is
> the number the grade is mostly about — and a large one is a warning, not an
> opportunity.

That is the single most counter-intuitive thing in the product, and a visitor
who misses it will misread every card.

### 3. What the grades mean

Six letters, what each means in one sentence, and what share of seven seasons
each represents — so a reader can see immediately that A+ is rare (6%) and F is
rare (10%) rather than assuming the scale is flattering.

Then two paragraphs that do the real work:

- **The thresholds are absolute.** Set once from seven seasons, then fixed. The
  same card grades the same on a quiet Tuesday and on championship Saturday, so
  a screenshot means the same thing whenever it was taken.
- **A top grade does not mean "read this one first."** Cards where Atlas and the
  market agree to within a point realised 50.8% against a 51.3% claim across 760
  games — a coin flip. They grade highest because they are the most reliable,
  and they are the most reliable because Atlas added nothing to them.

That second one is in a bordered disclosure block, because it is the caveat a
new reader is least likely to arrive with and most likely to need.

### 4. Why Atlas exists

Three paragraphs, and the argument is the product:

> Every model in this category publishes its numbers with the same confidence
> every week. None of them tells you which of those numbers has historically
> been worth anything.
>
> Atlas measured that, and the answer was uncomfortable: the further its model
> sits from the market, the worse it does. Cards claiming 77% accuracy
> delivered 50%. The loudest cards are the weakest ones.
>
> Most products would bury that. Atlas made it the largest element on the card.
> A grade that can say F is the only kind of grade worth anything, and it is
> the reason the A means something too.

---

## Where the page is reachable from

| Surface | How |
|---|---|
| Nav | **About**, the last item, on every page |
| Footer | "new here", first in the footer link row, on every page |
| Landing page itself | the canonical entry from search, social and email |

The nav dropped **NCAAF** to make room. It pointed at the board, which is where
**Today** already points — two links to one page is a link nobody trusts, and
five items is what a 390px bar holds.

The board deliberately does **not** carry a first-visit banner. Rule 1 is that
the board is the product; a dismissible strip above the first card would cost
every returning visitor for the benefit of one visit.

---

## What onboarding does not do

- **No modal, no tour, no tooltip walkthrough.** Nothing on Atlas moves or
  interrupts. A visitor who wants the board gets the board.
- **No email capture gate.** The newsletter is offered on the page, not
  demanded before it.
- **No account.** There is nothing to sign into, and there will not be until
  premium exists.

---

## Tests

| Test | Property |
|---|---|
| `test_the_landing_page_answers_the_four_questions_it_promises` | all four sections present; the "never tells anyone what to do" clause is above the fold; the grade caveat travels with the grade |
| `test_the_landing_page_works_without_an_example_card` | out of season the walkthrough disappears cleanly |
| `test_no_page_tells_a_reader_what_to_do[about]` | the landing page obeys the vocabulary rules |
| `test_no_card_names_a_side[about]` | and names no side |

The landing page is the surface most likely to drift toward marketing language,
so it is inside the same tripwire as the cards rather than exempt from it.
