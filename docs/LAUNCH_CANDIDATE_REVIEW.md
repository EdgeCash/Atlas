# Atlas — Launch Candidate 1.0 Review

**No redesigns. Polish only.** The board, the card framework, Grade V2 and the
homepage structure were approved and none of them changed.

---

## Verdict

**Atlas is launch-ready**, with one genuinely blocking item that is not a
product question: the jurisdiction question in `LAUNCH_CHECKLIST.md` §5.

Everything else outstanding is deployment — DNS, hosting, a scheduled rebuild,
social accounts — or is a named gap the product itself is honest about.

```
$ make launch-check

Atlas launch audit — 181 pages

BLOCKING
  [ok] forbidden vocabulary: 0
  [ok] a named side: 0
  [ok] card missing the grade disclaimer: 0
  [ok] motion or urgency: 0

ADVISORY
  [ok] missing canonical: 0        [ok] missing meta description: 0
  [ok] missing structured data: 0  [ok] missing social tags: 0

256 passed · All checks passed!
```

---

## The one sentence

> **Atlas grades its own college football numbers.**

Five words: the sport, the subject, and the thing nothing else in the category
does. Longer forms are in `FINAL_CONTENT_COPY.md`.

---

## The finding that shaped this pass

The brief assumes *"a user arrives from X."* That user **does not land on the
homepage** — every social post links to a specific game, so they land on a
**card**.

The card, not the board and not the landing page, is Atlas's first-visit
surface for most first visits. Auditing the homepage as the entry point would
have audited the wrong screen. Everything below follows from that.

---

## What changed — nine polish items, no redesigns

| # | Change | Why |
|---|---|---|
| 1 | **`/faq.html`** — 27 questions, grouped, uncomfortable ones first | the highest-value missing page for a first-time visitor after the landing page |
| 2 | **`/404.html`** — with `noindex` and no canonical | cards come down when games are played; a 404 that claims a canonical tells a crawler the missing page is the real one |
| 3 | **"New to Atlas?" line at the end of a card's five-second view** | most first visits land on a card and nothing on it said what Atlas *is*; "About" was in the nav and "new here" 6,600 characters down in the footer |
| 4 | **One-line explainer above the board's filters** | *"7 graded A or better · 11 marked down"* is jargon to a new reader, and four grade filters follow for a scale nobody has explained |
| 5 | **Cautions rewritten in plain English** | *"Cards in the 10+ band have claimed 77% and delivered 50%"* — "band" is research vocabulary, and the sentence repeated the figures the grade block had just given |
| 6 | **Panel summaries rewritten** | *"open, current, movement, moneyline"* → *"where the line opened, where it is now, and the prices"* |
| 7 | **`Mkt` and `Diff` → `Market` and `Difference`** | full words fit; abbreviations are for people who already know |
| 8 | **Search placeholder `Search teams`** | it truncated to *"Search a team or c"* at 390px |
| 9 | **Two new tests** — no caution may use research vocabulary; the FAQ must answer the A-card question | Track 3 findings, pinned so they cannot come back |

Total: 256 tests, 181 pages, audit clean.

---

## Track by track

### 1 · First visit — `FIRST_TIME_USER_AUDIT.md`

Three walkthroughs at 390×844: arriving on a card from X, arriving on the
board, arriving on the landing page. Scored against the twenty-second test.

**The card passes.** A reader who has never heard of Atlas learns, in one
screen, that this is about one game, that there are two numbers that differ,
that **Atlas is telling them not to trust this card**, and that the grade is
about information quality rather than about what to do.

**The board passes after the explainer line.** Before it, a new reader met
"graded A or better" and "marked down" with no definition.

**One finding left open:** `MIA −41.5` assumes the reader can read a point
spread. Three options were weighed; the shipped one is to leave it, because the
grade — the thing that matters — is already in plain English and a broadcast
graphic shows the same notation. The other two are live proposals.

### 2 · Board usability — `MOBILE_UX_AUDIT.md`

**One-thumb usable at 390px.** No control is out of reach in a way that
matters, nothing requires precision, and nothing depends on JavaScript. Rows
are 60–70px targets, filter chips are 40px, both bars are sticky, and the
filter row wraps rather than scrolling sideways.

Two gaps remain, both readability rather than reachability: unlabelled
`Atlas +0.4` on a board row (two proposals given), and a long unassisted scroll
across 58 cards.

### 3 · Card readability

Tier 1 is **1,194 visible characters**. Research vocabulary is almost entirely
in tier 2, behind panels:

| Term | Tier 1 | Tier 2 |
|---|---|---|
| calibration | 0 | 5 |
| out of sample | 0 | 4 |
| point-in-time | 0 | 2 |
| unanchored | 0 | 3 |
| opponent-adjusted | 0 | 1 |
| percentile | 1 | 7 |
| EPA | 1 | 2 |

The two leaks in tier 1 are `26th percentile` and `EPA/play`, both standard in
modern football coverage. The one real leak — "the 10+ band" in a caution — is
fixed and now has a test.

### 4 · Explanation system

Can an ordinary reader understand Market, Atlas, Difference, Grade and
Reliability without the research pages?

| | Verdict |
|---|---|
| **Market** | partly — the number is labelled, the notation is assumed |
| **Atlas** | yes — a projected score with both abbreviations under it |
| **Difference** | yes — signed, with "on the total" beneath, coloured only above one point |
| **Grade** | **yes** — three plain sentences on every card, computed from its own numbers |
| **Reliability** | yes — the grade's third line gives claimed vs delivered for this card's range |

The grade is the strongest part of the explanation system and it was already
built. The FAQ and the landing page now carry the rest.

### 5 · Social — `SOCIAL_PLAYBOOK.md`

Five posts a week, per-channel strategy, an example week, and the card
selection rule. The Saturday marked-down post is the one that matters; under V2
the slate carries eleven of them, so it is available whenever it is true.

### 6 · Launch content — `FINAL_CONTENT_COPY.md`, `FAQ.md`

Every positioning string in one place, marked live or draft. The FAQ is now a
published page as well as a document.

### 7 · Checklist — `LAUNCH_CHECKLIST.md`

Seven sections, each item verified by something named. Analytics, SEO, social,
legal, disclaimers, platform stability, live tracker.

### 8 · Waitlist — `WAITLIST_STRATEGY.md`

One field, one button, double opt-in, unsubscribe in the header. No modal, no
exit intent, no cap, no scarcity. Founding readers get a guarantee about the
present rather than a discount on a future, and get **asked** what to charge
for before anything is decided. No payment system built — Rule 3.

---

## What is not launch-ready, honestly

**Blocking**

- **The jurisdiction question.** Atlas publishes no selections and takes no
  money, so it is not a gambling service — but it describes betting markets,
  and jurisdictions differ on what that requires. A legal question, not a
  product one, and it should be answered before launch rather than after.

**Deployment, not product**

- DNS, HTTPS, hosting. `SITE_URL` in `render.py` is the single place the
  domain is spelled.
- A scheduled refresh and rebuild. Without it the board goes stale mid-week and
  the market numbers stop matching reality. This is the one operational gap a
  reader would notice.
- Social accounts and handles.
- Sitemap submission and an unfurl check.

**Named gaps the product is honest about**

- **One book quoting**, on every card. Highest-value roadmap item; the card
  says so rather than hiding it.
- **Nothing to return for between slates.** The public reliability record is
  the fix and it is next.
- **No privacy note.** Atlas logs less than almost any site on the internet,
  which is worth saying rather than leaving implied.
- **No waitlist form.** Specified, not built.

---

## Recommendation

**Ship it**, in this order:

1. Answer the jurisdiction question.
2. Write the privacy note — half a page.
3. DNS, hosting, scheduled rebuild.
4. Submit the sitemap; check the unfurls.
5. Launch with **the landing page as the link** and **one marked-down card as
   the first post**. Not an announcement thread; the product explains itself
   better than a launch thread would.

Then, before anything else on the roadmap: **a second market data provider**,
and **the public reliability record**. The first makes the grade better; the
second gives anyone a reason to come back.

---

## Success criteria, scored

| Criterion | Verdict |
|---|---|
| Atlas can be shown publicly | **yes** |
| Atlas can be explained in one sentence | **yes** — *"Atlas grades its own college football numbers."* |
| Atlas can be understood in 20 seconds | **yes** on all three entry surfaces, after this pass |
| Does not require understanding betting | **mostly** — one spread notation is assumed, and is the one open finding |
| Does not require understanding modelling | **yes** — the grade explains itself in three plain sentences |
| Helps users understand games better | **yes** — and it is the only product in the category that says when its own numbers are not worth leaning on |
