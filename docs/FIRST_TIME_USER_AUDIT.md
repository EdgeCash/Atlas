# Atlas — First-Time User Audit

**Track 1.** A complete walkthrough. No account, no context, twenty seconds.

Done against the built site at 390×844, not against the design.

---

## The assumption that changes everything

The brief says *"a user arrives from X."* That user does **not** land on the
homepage. They land on **a card**, because every social post links to a
specific game.

So the card — not the board and not the landing page — is Atlas's first-visit
surface for most first visits. Auditing the homepage as the entry point would
have audited the wrong screen.

Three entry points, in the order they will actually happen:

| Entry | Lands on | Share, expected |
|---|---|---|
| A link from X, Threads or a group chat | a **card** | most |
| A search for a matchup | a **card** | growing, slowly |
| Someone typing the domain, or a launch post | the **board** | few |

---

## Walkthrough 1 — arriving on a card from X

*Central Michigan at Miami, graded F. 390×844. No prior knowledge.*

### What the user sees, in order

| Seconds | What is on screen |
|---|---|
| 0–2 | Two crests either side of "at". **C Michigan** / **#6 Miami**, records and conferences. Kickoff, TV, venue. |
| 2–5 | MARKET `MIA −41.5`, ATLAS `5–47`, DIFFERENCE `−11.2`. |
| 5–12 | A red **F 44/100** block: *"Historically unreliable. A very large disagreement of 11.2 points. Across seven seasons, cards this far from the market claimed 77% accuracy and delivered 50%. Atlas marks its own card down."* Then, smaller: *"How much weight this card's information deserves — not a recommendation."* |
| 12–20 | **Why** — three drivers with crests. Then **Be careful about**. |

### What the user learns

- This is about one specific game, and it knows the game (crests, rank,
  record, venue, broadcast).
- There are two numbers — a market one and an Atlas one — and they differ.
- **Atlas is telling them not to trust this card.** In red. With a reason and
  a seven-season figure.
- The grade is about information quality, not about what to do.

That last pair is the whole product, delivered in the first screen, to somebody
who has never heard of Atlas. **This surface passes.**

### What was confusing — and what was done

| Finding | Severity | Action |
|---|---|---|
| **Nothing on the card says what Atlas *is*.** "About" was in the nav and "new here" in the footer, 6,600 characters down. A reader who wants the explanation had to go looking. | **high** | Added one quiet line at the end of the five-second view: *"New to Atlas? What a card is, and what a grade means"* — placed exactly where a confused reader has got to. |
| **"Cards in the 10+ band have claimed 77% and delivered 50%."** "Band" is research vocabulary, and the sentence repeated figures the grade block had just given — a caution spent on something already read. | **high** | Rewritten: *"Atlas is 11.2 points away from the market here. That is the range where its projection has been least worth leaning on — read the drivers and the market context instead."* A test now fails if any caution uses research vocabulary. |
| **`Mkt` and `Diff`** as the narrow-screen labels. Abbreviations for a first-time reader. | medium | Full words, `Market` and `Difference`. They fit. |
| **Panel summaries were written for someone who already knew** — *"open, current, movement, moneyline"*, *"score, win probability, the unanchored model"*, *"seven seasons, out of sample"*. | medium | Rewritten in plain English: *"where the line opened, where it is now, and the prices"*; *"the projected score, the chance of winning, and the model before it is anchored to the market"*; *"what Atlas claimed and what it delivered, across seven seasons it never saw while being built."* |
| **`MIA −41.5` requires betting literacy.** | medium | **Not changed.** See below. |
| **`5–47` is an unlabelled scoreline** until the eye reaches `CMU–MIA` underneath. | low | Left. The note is directly below it and the order matches the title. |

### The one finding left open

**`MIA −41.5` assumes the reader can read a point spread.** The success
criteria say Atlas must not require users to understand betting.

Three options were considered and none is free:

1. **Translate it** — "Miami by 41.5" as the cell's note. The note already
   carries `total 53.5`, and at 110px both wrap to five lines.
2. **A sentence under the answer row** — *"The market makes Miami a
   41.5-point favourite and expects 53.5 total points."* Costs about 60px,
   which pushes the grade block off the first screen and breaks the rule that
   the grade is always in the five-second view.
3. **Leave it**, and teach it on the landing page and in the grade's own
   sentence, which already says *"a very large disagreement of 11.2 points"*
   in plain words.

**Option 3 shipped**, because the grade — the thing that matters — is already
in plain English, and a broadcast graphic shows the same notation. Options 1
and 2 are live proposals if you would rather pay the space.

---

## Walkthrough 2 — arriving on the board

### What the user saw, before

```
  Week of 24 September
  58 cards · 7 graded A or better · 11 marked down
  [ search ] [ conference ▾ ] [ All ][ A & up ][ B & up ][ Marked down ]
  FEATURED …
```

A first-time visitor reads *"7 graded A or better · 11 marked down"* and has
no idea what either phrase means. Then four grade filters for a scale nobody
has explained. The board is excellent for a returning reader and opaque for a
new one.

### What was done

One line, above the filters:

> *Every game gets a card — and a letter for how much that card's information
> has historically been worth.* **How to read one**

It costs about 90px and it converts the summary line from jargon into a
legend. It is a line of text, not a banner: no dismiss control, no state, and
a returning reader's eye skips it.

Also: the search placeholder was `Search a team or conference`, which
truncated to *"Search a team or c"* at 390px. Now `Search teams`.

### What the user learns now

Within one screen: Atlas is about games, each game has a card, each card has a
letter, the letter is about how much the information is worth, and there is a
page explaining it. Then three featured games with grades A, B and C — which
teaches the scale by example before the reader has read a definition.

---

## Walkthrough 3 — arriving on the landing page

`/about.html`, built last phase. Audited again here.

**Passes.** The first screen carries the whole claim including the *"Atlas
never tells anyone what to do with it"* clause, and the two buttons match the
two things a first-time visitor wants — see it, or learn to read it.

One thing noted and not changed: the page is reached from the nav and the
footer but is **not** the default entry for a launch link. `LAUNCH_PLAN.md`
already says the landing page is the link that goes out on day one, not the
board. That remains the recommendation.

---

## The twenty-second test, scored

| Question | Card | Board | Landing |
|---|---|---|---|
| Do I know what this site is? | **yes**, after the fix | **yes**, after the fix | yes |
| Do I know what this page is about? | yes | yes | yes |
| Do I know what the numbers mean? | mostly — the spread is assumed | mostly | yes |
| Do I know what the letter means? | **yes** — it explains itself | by example, then the link | yes |
| Do I know what Atlas wants me to do? | **yes: nothing** | yes | yes |

The last row is the one that matters and it is the only one that was already
passing everywhere before this audit.

---

## What is still confusing, and deliberately left

- **`Atlas +0.4` on a board row.** Plus 0.4 of what? The card says "on the
  total"; the row has no room. A reader learns it on their first card.
  Flagged in `MOBILE_UX_AUDIT.md` with two proposals.
- **`26th percentile`** in a driver row. Common enough in sports coverage to
  stand, and the alternative ("bottom quarter of the country") is longer and
  vaguer.
- **`EPA/play`.** The single most jargon-heavy string in tier 1. It is also
  the standard term in modern football coverage, and replacing it with
  "efficiency" would lose the unit. Left, and defined on the research page.
- **Team pages** were not audited as a first-visit surface, because nothing
  links to them from outside. They are a second-click surface.
