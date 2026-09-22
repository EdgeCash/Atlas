# Atlas — Competitor Analysis

Five products a reader might open instead of Atlas. For each: what it is good
at, what Atlas should take, and what Atlas must not take.

This is a design analysis of interface patterns, not a feature comparison and
not a claim about anybody's accuracy.

---

## 1. BettorSheets

**What it is.** A dense, sortable sheet of games with model numbers beside
market numbers.

### Emulate

- **The sheet is the product.** No onboarding, no hero section, no marketing
  above the data. A reader arrives and is immediately looking at games. Atlas's
  board takes this directly.
- **Model and market on the same row.** The comparison is the information, and
  putting the two numbers side by side makes it without a sentence.
- **It is not embarrassed by numbers.** There is no attempt to hide the
  quantitative nature of the thing behind illustration.

### Avoid

- **Everything is the same size.** A sheet has no hierarchy by definition, so
  the reader does the ranking. This is fine for a professional and fails the
  five-second test completely.
- **No uncertainty anywhere.** Every row is presented with identical
  confidence. Atlas's entire differentiation is that its rows are *not*
  equally trustworthy and it says which.
- **A difference column reads as a ranking of opportunities.** Sorting by it
  turns a research tool into a recommendation engine without anyone deciding
  to. Atlas shows the difference on a row but never sorts by it.

---

## 2. The Athletic

**What it is.** Subscription sports journalism, with charts used as
illustration inside long-form writing.

### Emulate

- **Editorial restraint.** Generous white space, one idea per screen, a serious
  typographic voice. It looks like something worth paying for because it looks
  like it was made by people who care.
- **Charts that carry a sentence.** Every graphic in a piece makes one point
  and is labelled with that point rather than with its axes.
- **It never shouts.** No urgency, no countdown, no scarcity. Atlas's voice
  rules are the same rules.
- **Bylines and accountability.** A named author is a claim of
  responsibility. Atlas's version is the reliability record and the grade —
  the same move, made by a model instead of a person.

### Avoid

- **Long form is the wrong shape for a game card.** A reader opening a card
  three hours before kickoff wants a number and a caveat, not 900 words.
- **The hard paywall interrupts mid-sentence.** `PREMIUM_PLAN.md` puts the
  boundary at a whole surface — history and depth — so the free card is always
  complete.
- **The charts illustrate an argument someone already wrote.** Atlas's numbers
  come first and the sentences describe them, which is the opposite order.

---

## 3. Apple Sports

**What it is.** A free scores app. The clearest interface in the category by a
distance.

### Emulate

- **One screen, one game, no chrome.** The information density is low on
  purpose and nothing on the screen is not the game.
- **Team identity does the navigation.** Crests and team colour tell you which
  game you are looking at before you read a word. This is the single strongest
  argument for the sprint's third rule, and why Atlas now caches 142 logos and
  puts crests on every board row.
- **Instant.** No spinner, no skeleton screen, no layout shift. Atlas's static
  pages are the same bet made a different way.
- **Type does the hierarchy, colour barely participates.** Size and weight
  separate the elements; colour is reserved for team identity and almost
  nothing else.

### Avoid

- **It carries no uncertainty because it has none to carry.** A score is a
  fact. A projection is not, and an interface that presents a projection with a
  score's confidence is lying with layout. This is the one place Atlas must be
  *less* clean than Apple Sports: the grade and the caution have to be on the
  card, and they cost space.
- **No explanation anywhere.** Atlas has to show its working, which is why the
  card has tier 2 at all.

---

## 4. ESPN Gamecast

**What it is.** A live game hub — win probability, drive charts, box score,
play log.

### Emulate

- **Progressive disclosure done at scale.** The summary is on top and the
  detail is in tabs. Atlas's three tiers are the same idea with native
  `<details>` instead of tabs, because a document that works without JavaScript
  is a document that prints, searches and loads on a stadium network.
- **Win probability as a single number with a shape behind it.** Readers
  understand it. Atlas states its probabilities the same way and always beside
  the number they are derived from.

### Avoid

- **Ads inside the data.** The single fastest way to look like free inventory
  rather than a product.
- **Modules stacked without hierarchy.** Gamecast is a collection of panels
  with no view about which matters, so every reader does their own triage.
- **Win probability presented without its error.** A 68.7% that swings 20
  points on one play, shown with no sense of how wide it is, teaches readers
  that a probability is a prediction. Atlas caps displayed probability at 99%
  and prints the residual standard deviation it came from.
- **Live-updating everything.** Motion implies urgency. Atlas is a pre-kickoff
  product and has no reason to move.

---

## 5. Action Network

**What it is.** The category-defining product for this audience, and the one
Atlas is most likely to be mistaken for.

### Emulate

- **The information architecture is right.** Board → game → why. Atlas uses the
  same three steps.
- **Line movement is presented as history, not as an alert** in its better
  screens — open, current, and the path between.
- **It takes mobile seriously.** Almost all of this audience arrives on a phone
  from a link.

### Avoid — this is the important half

<!-- lang-lint: quoting -->
- **Everything is a call to action.** Every number is adjacent to a button that
  places a bet. The interface's purpose is conversion, and every design
  decision serves it.
- **Confidence is sold, not measured.** Star ratings, "best bets", expert
  records. A star rating is a confidence claim with no record behind it; Atlas's
  grade is a confidence claim with seven seasons behind it, and the difference
  is invisible unless the interface makes it visible.
- **Records are published selectively.** Win-loss records with no denominator
  and no calibration.
- **Dark, saturated, urgent.** Dark surfaces, neon accents, red badges,
  countdowns. Atlas is bright, off-white, and has no countdown anywhere.
<!-- lang-lint: end -->

---

## Where Atlas sits

|  | BettorSheets | The Athletic | Apple Sports | Gamecast | Action Network | **Atlas** |
|---|---|---|---|---|---|---|
| Model number beside market | ✓ | — | — | — | ✓ | ✓ |
| Says how much to trust *this* item | — | — | — | — | — | **✓** |
| Publishes its own failures | — | — | — | — | — | **✓** |
| Names a side | ✓ | — | — | — | ✓ | **never** |
| Readable in 5 seconds on a phone | — | — | ✓ | — | — | ✓ |
| Bright by default | ✓ | ✓ | — | — | — | ✓ |
| Loads instantly | — | — | ✓ | — | — | ✓ |
| Shows its working | ✓ | ✓ | — | ✓ | — | ✓ |

**The two rows nobody else has are the product.** Everything else on this table
is available somewhere; per-item reliability and published failures are not
available anywhere. The design consequence is that the grade has to be the
largest element on the card and the cautions have to be above the fold —
because they are the only things on the page a reader cannot get elsewhere.

---

## What each one teaches, in one line

- **BettorSheets:** put the data first, and do not apologise for it.
- **The Athletic:** looking like it was made carefully *is* the value
  proposition of a paid product.
- **Apple Sports:** crests and type do the work that chrome and colour usually
  do badly.
- **ESPN Gamecast:** summary on top, detail behind a tap, always.
- **Action Network:** this is what Atlas looks like if a single decision goes
  wrong.

---

## The test the brief set

> *Fight the urge to make it look like a sportsbook.*

Three properties make the difference, and each is checkable rather than a
matter of taste:

1. **Nothing on any surface names a side.** Enforced by a test that renders
   every page type and scans the visible text, and by two templates with
   nowhere to put one.
2. **The grade is the largest element on the card**, and it goes down as the
   product gets louder. A sportsbook's most prominent element is the thing it
   wants you to act on; Atlas's is the thing that tells you how much to trust
   it.
3. **The board has a "Marked down" filter.** No product whose purpose is
   conversion would build a control for finding its own weakest output.
