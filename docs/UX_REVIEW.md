# Atlas — UX Review

The refinement sprint's test: **a sports fan with no betting experience opens a
card on a phone and understands the game in under five seconds.** This is a
review of what the built product did against that test, what changed, and what
is still wrong.

Screenshots referenced throughout are in `design/screens/site/`, taken from the
built site at real viewports — nothing here is a mockup.

---

## 1. The five-second test, applied honestly

Five seconds on a 390×844 phone is roughly *one screen, no scrolling*. So the
test has a measurable form: **what is above 844px, and can it be read in one
pass?**

### Before

The first screen of a card showed the top three of eight always-open sections:
the header, the market table, and the beginning of the projection table. A
reader saw fourteen numbers, no hierarchy among them, and had to scroll twice
to reach the grade — the one element that tells them how much to trust
everything above it.

The homepage was worse. Navigation, a heading, a sub-line, a filter bar, a
count line and a section label consumed 440px before the first game.

### After

| Surface | What is on the first screen now |
|---|---|
| Card | Both teams with crests, records, ranks; kickoff, TV, venue; market, Atlas, difference; **the grade at 92px with its confidence bar**; the first two of three drivers |
| Board | Week, card count, one search row, filters; then cards |

Five things on a card instead of fourteen. The grade is the largest element on
the page.

---

## 2. What changed, by design rule

### Rule 1 — reduce visible information by 50%

The card's eight sections became **three tiers**:

- **Tier 1, always visible:** teams, the answer (market / Atlas / difference),
  the grade, why (three drivers), and what to be careful about.
- **Tier 2, one tap:** market detail, projection, the grade's arithmetic,
  driver detail, market movement, the reliability record.
- **Tier 3:** methodology, linked to the research page.

Nothing was deleted. Every number that was on the card is still on the card,
behind a native `<details>` panel — no JavaScript, works with the page's own
find-in-page, and a printed card still contains everything.

Measured: the card's always-visible text dropped from about 2,400 characters
to about 900.

### Rule 2 — cards before navigation

The homepage was rebuilt as a board. The heading block is two lines, the filter
row is one row on desktop and two on a phone, and the first card now begins at
530px instead of 660px.

The redundant "58 games" count line was removed while nothing is filtered — it
sat directly beneath a heading that already read "58 cards". It reappears the
moment a filter changes the number, which is the only moment it says anything.

### Rule 3 — increase team identity

142 team logos are cached at build time and served from the site rather than
hot-linked, so the board does not wait on a third-party CDN. Crests appear on
every board row, in the card hero, in the driver rows (the crest of the team a
driver favours, rather than a coloured dot), and on both social templates.

Ranks (`#2`), records (`3-0`) and conference sit under each team name. Team
colour tints the hero rule and nothing else — it is chrome, never data, per
`BRAND_GUIDE.md`.

### Rule 4 — the Atlas Grade is the centrepiece

The grade has its own full-width card, a 92px mark with a 44px letter, a
plain-language headline ("High confidence"), the score out of 100, and a
confidence bar. On a D or F card the block carries the tone colour as a border
so the marked-down cards read as marked down at a glance.

The grade is still computed and never entered by hand.

### Rule 5 — every card answers five questions

| Question | Where it is answered |
|---|---|
| Who is playing? | Hero: crests, names, ranks, records, conference |
| When and where? | Hero: date, kickoff, TV, venue |
| What does the market say? | Answer row, cell 1 |
| What does Atlas say, and how much does it differ? | Answer row, cells 2 and 3 |
| What should make users cautious? | **"Be careful about" — computed per card** |

The fifth was the missing one and it is the one worth the most. `data.cautions`
computes up to three specific warnings from the card itself: a wide
disagreement with that band's claimed-versus-realised record, a market with one
book behind it, a lopsided spread, missing metrics, or Atlas and the market
having moved opposite ways.

It deliberately does **not** say "it is week 4". That is true of every card on
the board, and a caution that appears on every card is read as decoration
within a week. It belongs once, on the board, and that is where it is.

---

## 3. Defects found in review, and fixed

These were bugs against the approved design, not design changes.

**Kickoff times were printed in UTC.** "Sat 19:30 UTC" is a unit conversion,
not a time. Every kickoff on the board is a US college game; the product now
prints Eastern, labelled — "Sat 26 Sep · 3:30 PM ET". A card that asks a sports
fan to do arithmetic has already lost the five seconds it had.

**Two different components were both called `.bar`.** The driver meter track
and the homepage filter row shared a class name, so the meter's centre tick was
being drawn through the middle of the filter row and the filter row inherited a
99px border radius. The board's is now `.board-bar`.

**The filter row scrolled sideways on a phone and hid its own right-hand end.**
The grade filters — the most product-specific control on the page — were the
half that stayed hidden. It now wraps to two rows and clips nothing.

**Both social templates overlapped their own text.** On the 1200×675 card the
kickoff line landed on top of the "MARKET" label whenever the title fitted on
one line; on the 1080×1080 card the crests overlapped the title. Both now use a
single cursor down the canvas, and the square template anchors the grade block
to the footer rule so the layout's slack collects in the middle rather than
under the conclusion.

**A 0.3-point difference was printed in alarm red.** The difference cell
coloured by sign alone, so a card where Atlas and the market agree to within a
third of a point shouted at the reader. Colour now starts at 1.0 point — the
0–1 band is where the two are indistinguishable out of sample, so below it
there is nothing to point at.

**The projected score was an unlabelled pair of numbers.** "15–29" now carries
"OU–UGA" underneath it, so the order is stated rather than assumed.

---

## 4. What is still wrong

### Needs a decision, not a fix

**Grade distribution.** 67% of cards grade A and two letters are unreachable.
This is the largest remaining problem with the product and it has its own
document: `GRADE_REWORK_OPTIONS.md`. It is not implemented because changing
what a grade means is not an implementation decision.

**One book quoting, on every card.** All 58 cards show `1 book quoting`,
because the live tracker captures a single provider. The "market depth" idea
appears in the caution text and in the grade's inputs and currently carries no
information. Adding a second provider is a tracker change; it would improve
both the product and the reliability record.

### Known and deliberate

**Drivers wrap to two lines on a phone.** "Pace and possessions" takes two
lines in the 390px driver row. Shortening driver names is a content change that
touches `drivers.py`'s sentences as well as its labels, and abbreviating them
("Pace") loses the thing that makes the row readable to someone who does not
already know what the model does.

**Moneyline missing on 3% of cards.** Books do not price a moneyline on a
forty-point spread. The card says "not posted" and why. Correct behaviour,
noted so it is not mistaken for a bug.

**Two teams, one colour.** Iowa State cardinal and Utah crimson are
indistinguishable at chip size; the collision rule fires and the away accent
falls back to slate. Implemented as RGB distance with a threshold of 60. A
perceptual distance would be better and is not worth the dependency yet — and
with crests now on every row, the accent carries less of the identity load than
it did.

---

## 5. Does it pass?

**The card: yes.** Teams, kickoff, market, Atlas, difference and a grade with a
plain-language headline are all visible without scrolling, and the grade is the
largest thing on the screen. A reader who stops after five seconds leaves with
the right impression, including when the right impression is "Atlas does not
trust this one".

**The board: yes, with a caveat.** A row gives teams, crests, kickoff, the
market number, the difference and the grade. The caveat is the grade itself —
when 39 of 58 rows show A, the column that is supposed to help a reader choose
where to look is not helping. That is the distribution problem, on the surface
where it costs the most.
