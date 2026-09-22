# Atlas Sports Intelligence — Implementation Notes

Phase 1 of the product, built to the approved specification. NCAAF only; NFL
staged. Nothing was redesigned.

```bash
python -m atlas.warehouse.build --include-scheduled   # features for upcoming games
python -m atlas.live refresh --no-rebuild             # publish Atlas's numbers
python -m atlas.live run                              # capture the current market
make site                                             # build site/
```

Build time: **6.6 seconds** for 58 cards, 116 team pages and 24 social images.

---

## Architecture

A static site generator. No server, no client framework, no hydration — the
card is a document, and a document loads instantly on a phone on a stadium
network. The only JavaScript is 40 lines of filtering on the homepage, and the
page is complete before it loads.

```
atlas/site/
  meta.py      ESPN scoreboard: venue, broadcast, records, ranks, team colours
  grade.py     the rubric from ATLAS_CARD_SPEC §5, and the calibration bands
  data.py      joins warehouse + tracking + ESPN into one Card per game
  drivers.py   ranks the drivers and writes their sentences
  render.py    the eight sections, and the other four page types
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
| Calibration bands, grade | recomputed from the warehouse at build time |

One network call per build, cached. Everything else is local.

### Why the calibration bands are recomputed, not transcribed

The grade depends on seven seasons of out-of-sample calibration. Hard-coding
that table would let the site drift away from the research it cites the first
time a season was added. `grade.calibration_bands()` recomputes it from the
warehouse on every build — about two seconds — so the research page, the grade
and the reliability section cannot disagree with each other.

### Output

```
site/
  index.html          today's board, search, conference and grade filters
  research.html       how Atlas works, what grades mean, calibration
  nfl.html            the three stages, and why grades come last
  premium.html        comparison table, framework only, no payment path
  ncaaf/{slug}.html   58 matchup cards
  team/{slug}.html    116 team pages
  social/             12 templates, SVG + PNG at 2×
  assets/             atlas.css, atlas.js
```

3.6 MB total. The largest HTML page is 31 KB.

---

## The grade is computed

`grade.compute()` is `ATLAS_CARD_SPEC.md` §5 in code: calibration 40, market
agreement 25, signal stability 20, data completeness 15. Nothing is entered by
hand and no card is adjusted.

Three tests pin the properties that matter, rather than the numbers that will
move as seasons accumulate:

- a larger disagreement can never raise a grade;
- a worse-calibrated band can never raise a grade;
- the letter boundaries match the specification exactly.

---

## Findings for review

### 1. Grades cluster at A — the one thing that needs a decision

The approved rubric, applied to a real 58-game slate:

| Grade | Cards | Share |
|---|---|---|
| A+ | 0 | 0% |
| A | 39 | 67% |
| B | 11 | 19% |
| C | 7 | 12% |
| D | 0 | 0% |
| F | 1 | 2% |

Scores run 33.0 to 87.6, median 82.0.

`PRODUCT_VISION.md` names this exact failure: *"Grades cluster: if 80% of
cards grade B, the grade is decoration."* It is 67% at A, and two letters are
unreachable.

**The cause is structural, not a bug.** Mean component scores across the slate:

| Component | Mean | Why |
|---|---|---|
| Data completeness | 1.000 | every input is present on every card |
| Calibration | 0.839 | 67% of cards sit within 4 points of the market, where gaps are small |
| Market agreement | 0.737 | same reason |
| Signal stability | 0.640 | the best real band is 5 of 7 seasons |

A+ is arithmetically unreachable: with stability capped near 0.71 and a
realistic calibration score, the ceiling is about 88. D is nearly unreachable
because the 8–10 band still scores around 60.

**I implemented the rubric exactly as approved and did not adjust it.** Three
options for the review, in order of how much I would recommend them:

1. **Grade on the curve of the season's own distribution** — A+ = top 5%, A =
   next 15%, and so on. Keeps the rubric, makes every letter mean something,
   and preserves the property that matters (loudest cards grade lowest).
2. **Rescale the components** so a realistic best card scores near 100:
   divide by the observed maximum rather than a theoretical one.
3. **Accept it** and say so on the research page: most cards *are* reliable,
   because most cards sit near the market, and the letter is a filter for the
   minority that do not.

Option 1 is what I would do. It needs approval because it changes what a grade
means, and that is not an implementation decision.

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

## Mobile

Most readers arrive from a link. The card is designed at 390px and expands:

- one column throughout; `.grid-3` becomes two columns below 460px;
- the wordmark's second half is hidden below 420px, where it cost three lines
  of the navigation bar;
- every number is tabular, so columns do not jitter;
- a D or F card puts its grade banner above the projection, so the most
  important thing on the page is visible without scrolling;
- 44px hit targets; the whole game row is the link.

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
