# Atlas Sports Intelligence — Implementation Notes

Phase 1 of the product, built to the approved specification, plus the
refinement sprint's five design rules. NCAAF only; NFL staged. Nothing was
redesigned — the sprint changed what is visible first, not what exists.

The sprint's own documents are `UX_REVIEW.md`, `HOMEPAGE_REDESIGN.md`,
`SOCIAL_CARD_REDESIGN.md`, `COMPETITOR_ANALYSIS.md` and
`GRADE_REWORK_OPTIONS.md` (research only — not implemented).

```bash
python -m atlas.warehouse.build --include-scheduled   # features for upcoming games
python -m atlas.live refresh --no-rebuild             # publish Atlas's numbers
python -m atlas.live run                              # capture the current market
make site                                             # build site/
```

```bash
make site-audit                     # the launch gate, over every built page
make launch-check                   # audit + tests + lint
python scripts/shoot_site.py        # design/screens/site/, real viewports
```

Build time: **6.9 seconds** for 58 cards, 116 team pages and 24 social images.

---

## Architecture

A static site generator. No server, no client framework, no hydration — the
card is a document, and a document loads instantly on a phone on a stadium
network. The only JavaScript is 40 lines of filtering on the homepage, and the
page is complete before it loads.

The card's progressive disclosure is native `<details>`, not script: tier 2
opens without JavaScript, survives find-in-page, and prints.

```
atlas/site/
  meta.py      ESPN scoreboard: venue, broadcast, records, ranks, team colours
  grade.py     the V2 rubric, the fitted calibration curve and the bands
  data.py      joins warehouse + tracking + ESPN into one Card per game
  drivers.py   ranks the drivers and writes their sentences
  render.py    the three card tiers, and the other four page types
  social.py    1200×675 and 1080×1080, SVG rasterised to PNG at 2×
  build.py     orchestration and the CLI
  html.py      escaping and number formatting
  assets/      atlas.css (the approved system), atlas.js (filtering)
```

### Where each number comes from

| Card element | Source |
|---|---|
| Teams, venue, TV, records, ranks, colours | ESPN scoreboard, cached 6 hours |
| Opening and current spread/total, prices | `tracking/snapshots.csv` |
| Moneyline | ESPN, where a book posts one |
| Atlas's number | `tracking/numbers.csv`, published by the weekly refresh |
| Drivers, percentiles | the point-in-time warehouse |
| Calibration curve and bands, grade | refitted from the warehouse at build time |

One network call per build, cached. Everything else is local.

### Why the calibration curve is refitted, not transcribed

The grade depends on seven seasons of out-of-sample calibration. Hard-coding it
would let the site drift away from the research it cites the first time a season
was added — and the curve's coefficient moves by about 2.5× across seasons, so
the drift would be real. `grade.calibration_curve()` refits it from the
warehouse on every build, and `calibration_bands()` recomputes the seven-row
table the reliability section reports, so the research page, the grade and the
card cannot disagree with each other.

### Output

```
site/
  index.html          today's board, search, conference and grade filters
  about.html          the thirty-second landing page
  research.html       how Atlas works, what grades mean, calibration
  nfl.html            the three stages, and why grades come last
  premium.html        comparison table, framework only, no payment path
  ncaaf/{slug}.html   58 matchup cards
  team/{slug}.html    116 team pages
  social/             12 templates, SVG + PNG at 2×
  assets/             atlas.css, atlas.js
  sitemap.xml         179 urls
  robots.txt
```

13 MB total, most of it cached logos and rasterised social cards. The largest
HTML page is 31 KB.

Every page carries a canonical URL, a meta description and Open Graph tags;
cards and team pages carry `SportsEvent` and `SportsTeam` structured data. The
structured data deliberately omits the grade and the projection - it describes
the game, and a machine-readable grade is one copy-paste from being a feed of
letters with no card around them.

---

## The grade is computed

`grade.compute()` is `GRADE_V2_IMPLEMENTATION.md` in code: calibration 45,
market agreement 25, card conditions 15, data completeness 15, with absolute
letter thresholds at 96 / 90 / 79 / 66 / 51. Nothing is entered by hand and no
card is adjusted.

Eleven tests pin the properties that matter rather than the numbers that will
move as seasons accumulate — among them that a larger disagreement can never
raise a grade, that a steeper calibration curve can never raise one, that the
thresholds are absolute and never slate-relative, and that every letter is
reachable.

---

## Findings for review

### 1. Grade V2 replaced V1, and the distribution now separates

V1 clustered: 39 of 58 cards at A, two letters unreachable, six distinct scores.
The cause was structural — the score was a step function of the disagreement
band, because three of its four components were constants.

The bands turned out to be an artifact of the research report's own buckets.
V2 fits the curve they were summarising:

```
gap(d) = -0.0133 * d^1.139     r = 0.88, n = 5006
```

On the same 58-card slate:

| Grade | V1 | V2 |
|---|---|---|
| A+ | 0 | 0 |
| A | 39 | 7 |
| B | 11 | 23 |
| C | 7 | 17 |
| D | 0 | 10 |
| F | 1 | 1 |

53 of 58 cards now score distinctly. Across seven seasons: A+ 6%, A 14%, B 31%,
C 25%, D 15%, F 10%.

**The finding underneath it matters more than the numbers.** Cards where Atlas
and the market agree to within a point realise 50.8% against a 51.3% claim — a
coin flip, p = 0.69 on 760 games. An A+ card is one where Atlas has contributed
nothing, so the grade prioritises in one direction only: it says what to
discount. The card, the board's section captions and the research page all say
so, and a test pins that the top of the scale carries the caveat.

### 2. One book quoting, on every card

All 58 cards show `1 book quoting`. The live tracker captures DraftKings via
ESPN's public feed, which was the right choice for the tracker — DraftKings is
one of four books that ever posts an opener — but it means the market snapshot
has no depth and "books quoting" is not yet doing any work.

Adding a second provider is a tracker change, not a site change, and it would
improve both the product and the CLV record.

### 3. Moneyline missing on 3% of cards

Books do not price a moneyline on a forty-point spread. The card shows "not
posted" and says why. This is correct behaviour and is noted only so it is not
mistaken for a bug.

### 4. Two teams, one colour

Iowa State cardinal and Utah crimson are indistinguishable at chip size. The
collision rule from `UI_SYSTEM.md` fires and the away accent falls back to
slate. Implemented as RGB distance with a threshold of 60; a perceptual
distance would be better and is not worth the dependency yet.

---

## The board

`HOMEPAGE_FINAL.md` is the specification. Four section types, in order:
featured national games, rivalries, the next five kickoffs, then every card
grouped by grade.

**Rivalries are computed, not curated.** A pairing counts when the two teams
have met in at least eight of the nine seasons the warehouse holds, keyed on
ESPN team ids — the warehouse and the scoreboard spell half of college football
differently and a name join silently returns nothing. 179 pairings qualify and
four are on this slate.

Each grade block carries a caption saying what the letter means, because a board
grouped by letter reads as a ranking of what to look at first and the letter
does not mean that.

---

## Mobile

Most readers arrive from a link. The card is designed at 390px and expands:

- one column throughout; `.grid-3` becomes two columns below 460px;
- the wordmark's second half is hidden below 420px, where it cost three lines
  of the navigation bar;
- every number is tabular, so columns do not jitter;
- the grade is in tier 1 on every card, so the most important thing on the page
  is visible without scrolling whatever the letter is, and it carries its own
  three-line explanation there;
- the hero is a head-to-head — two 52px crests either side of "at" — so the game
  is identified before a word is read;
- driver rows stack name over value; three columns in 358px meant both wrapped;
- one rank chip per board row, not two, and the numbers column is capped at
  108px, because otherwise a long matchup title wrapped to three lines;
- the board's filter row wraps rather than scrolling sideways — a scrolling
  strip hides its own right-hand end;
- 44px hit targets; the whole game row is the link.

Kickoffs print in Eastern, labelled. Every game on the board is a US college
game and "19:30 UTC" is a unit conversion, not a time.

---

## Language rules

`tests/test_site.py` renders each page type and scans the visible text for the
vocabulary `BRAND_GUIDE.md` forbids, with a context window so football
vocabulary ("per play", "100 plays") does not trip it. A separate test checks
that no page names a side. The social templates are parsed as XML and scanned
the same way.

This is the third layer of the same discipline: the live tracker's source, the
product documents, and now the rendered pages.

---

## What is not built

- **Payments.** The premium page is a comparison table and a framework. There
  is no checkout, no account and no gating logic; every card renders in full.
- **NFL cards.** Stage 1 as specified: the NFL page explains the three stages
  and why grades come last.
- **Player pages.** Reserved. Atlas has no player-level model.
- **Server-side search.** Client-side filtering over 58 rendered rows is
  instant; it would need revisiting at a few thousand cards.
