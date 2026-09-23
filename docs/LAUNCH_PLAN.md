# Atlas — Launch Plan

First public release. Not an MVP, not a prototype.

---

## Launch state

```
$ make launch-check

Atlas launch audit — 179 pages

BLOCKING
  [ok] forbidden vocabulary: 0
  [ok] a named side: 0
  [ok] card missing the grade disclaimer: 0
  [ok] motion or urgency: 0

ADVISORY
  [ok] missing canonical: 0
  [ok] missing meta description: 0
  [ok] missing structured data: 0
  [ok] missing social tags: 0

coverage: {'other': 5, 'card': 58, 'team': 116}
251 passed
All checks passed!
```

| | |
|---|---|
| Pages | 179 — board, landing, research, NFL, premium, 58 cards, 116 team pages |
| Build | ~7 seconds, 13 MB, largest page ~31 KB |
| Grades | V2: 7 A, 23 B, 17 C, 10 D, 1 F |
| Social | 12 templates per build, 1200×675 and 1080×1080 |
| Tests | 251 |
| JavaScript | 40 lines, homepage filtering only; every page works without it |

---

## What ships

### Built this phase

- **`/about.html`** — the thirty-second landing page. What Atlas is, how to read
  a card (built from a real card), what the grades mean, why Atlas exists.
  `ONBOARDING_FLOW.md`.
- **The free/premium line, finalised** and implemented on `/premium.html`.
  `FREE_VS_PREMIUM_FINAL.md`.
- **SEO infrastructure** — canonical URLs on every page, `sitemap.xml` (179
  URLs), `robots.txt` pointing at it, `SportsEvent` and `SportsTeam` structured
  data, Open Graph and Twitter cards with absolute image URLs, and rewritten
  titles and descriptions.
- **`scripts/audit_site.py`** — the launch gate, run over the built site.
- **`make launch-check`** — audit, then tests, then lint.
- **Nav simplified** from six items to five. "NCAAF" pointed at the board,
  which is where "Today" already points.

### Already shipped

The board with its sections, 58 matchup cards in three tiers, Grade V2, team
pages, the research page, the NFL staging page, and the two social templates.

---

## Track 4: how Atlas gets discovered

### The honest answer first

**Not by ranking for "college football picks".** That query belongs to products
that answer it, and Atlas does not. Chasing it would mean writing pages that
promise something the product refuses to deliver, and the bounce rate would
tell the truth within a month.

Atlas has three plausible discovery routes and they are worth different
amounts.

### 1. Game pages — the volume

58 new pages a week, each about a specific matchup, each with a market number,
a projection and a grade. The query shape is *"utah iowa state prediction"*,
*"ole miss florida total"*, *"what is the line on texas tennessee"*.

**What is in place:**

| | |
|---|---|
| Title | `Ole Miss at Florida — market, projection and grade \| Atlas` |
| Description | the market number, the projection and the grade, in one sentence |
| Canonical | `https://atlas.football/ncaaf/{slug}.html` |
| Structured data | `SportsEvent` — teams, venue, kickoff, status |
| Social | Open Graph and Twitter card, absolute image on the six cards that have one |
| Sitemap | `changefreq: daily`, `priority: 0.8` |

**What the structured data deliberately omits:** the grade and the projection.
Structured data is for the game. A machine-readable grade is one copy-paste
from being a feed of letters with no card around them, and the card is what
makes a letter mean anything. There is a test for that.

**The weakness, stated plainly:** these pages have a one-week shelf life and no
inbound links. They will take a season to rank for anything competitive, and
the first months of search traffic will be long-tail team-name queries.

### 2. Team pages — the durable base

116 pages that persist across weeks and accumulate. The query shape is *"utah
offensive efficiency"*, *"iowa state EPA per play"*, *"georgia success rate"* —
low volume, low competition, and exactly the reader Atlas wants: someone who
already thinks in these terms.

`SportsTeam` structured data, conference membership, a description that names
the actual metrics, weekly `changefreq`.

**This is the route worth investing in**, because a team page is the only Atlas
surface that gets better rather than staler as the season runs.

### 3. Research and the landing page — the authority base

`/research.html` and `/about.html` are what somebody links to when they cite
Atlas. They are also the pages that answer *"what is a calibration gap"* and
*"does closing line value predict anything"* — small queries with unusually
high-quality traffic.

`Organization` structured data on the landing page, monthly `changefreq`.

### What Atlas will not do for discovery

- **No programmatic content.** No auto-generated "Team A vs Team B preview"
  prose. The cards are the content.
- **No keyword pages** for terms the product does not serve.
- **No paid search.** Buying traffic for a query Atlas answers differently from
  how the searcher expects is a refund request with extra steps.
- **No link exchanges, no guest posts, no syndication to aggregators** that
  would strip the grade from the card.

### The realistic sequence

Social and word of mouth first, search second. The marked-down card is the
thing people send each other; search is what catches the people they sent it
to, six months later, looking for a different game.

---

## Track 7: the brand audit

Every screen, checked rather than reviewed. `scripts/audit_site.py` runs over
all 179 built pages.

### Blocking checks — all clean

| Check | Result |
|---|---|
| Forbidden vocabulary outside an allowed context | **0** |
| A named side (`take the`, `we like`, `leans over`…) | **0** |
| A card missing *"not a recommendation"* | **0 of 58** |
| Motion, animation or a countdown | **0** |

### Screen by screen

| Screen | Verdict |
|---|---|
| **Landing** | Explains what Atlas is and what it is not, side by side. The grade caveat is on the page, not just the card. Inside the same language tests as the cards. |
| **Board** | Grouped by grade with captions saying what each letter means. No sort by difference. No arrows, no highlights. "Marked down" is a first-class filter. |
| **Card** | The grade is the largest element and goes *down* as the product gets louder. No side. "Be careful about" is computed per card. |
| **Team page** | Season profile and upcoming cards with grades. No record against the spread — that is a betting statistic. |
| **Research** | The rubric, the thresholds, the seven-season record, and the A+ caveat in full. |
| **NFL** | Explains why there are no cards yet. The most on-brand page on the site: it advertises a gap rather than filling it. |
| **Premium** | Says plainly there is no way to subscribe. Nothing blurred, nothing teased. |
| **Social** | Neither template has anywhere to put a side. Both carry the disclaimer. |

### The three properties that keep Atlas from becoming a picks service

Each is checkable, not a matter of taste:

1. **No surface names a side.** Two tests at render time, one audit over the
   built site.
2. **The grade is the largest element on the card, and it falls as the
   disagreement grows.** A sportsbook's most prominent element is the thing it
   wants you to act on.
3. **The board has a "Marked down" filter.** No product whose purpose is
   conversion builds a control for finding its own weakest output.

A fourth, softer: **nothing on any Atlas page moves.** Audited.

---

## Launch sequence

### Before publishing

1. `make launch-check` — audit, 251 tests, lint. Must be green.
2. Point `atlas.football` at the built site; `SITE_URL` in `render.py` is the
   single place that spelling lives.
3. Submit `sitemap.xml` to Search Console and Bing Webmaster.
4. Verify one card, one team page and the landing page render correctly when
   their links are unfurled on X and in iMessage.

### Day one

- The landing page is the link that goes out, not the board. A first-time
  visitor needs the thirty seconds before the 58 cards.
- One social post: the marked-down card, with the reason. Not an announcement
  post — the product explains itself better than a launch thread would.

### Week one

- Weekly board email, if the sender exists. If not, it waits; a launch is not a
  reason to ship an unaudited surface.
- Record the launch baseline from `POST_LAUNCH_METRICS.md`.

### What is explicitly not in the launch

- **Payments.** `FREE_VS_PREMIUM_FINAL.md`: the paid surface is mostly the
  archive and the reliability record as browsable history, and neither exists
  yet. Selling a subscription whose main asset is still being collected is
  selling a promise.
- **The daily email.** A premium feature; premium does not ship.
- **NFL cards.** Staged behind calibration, and the page that says so is doing
  more for the product than an uncalibrated card would.
- **Accounts.** Nothing to sign into.

---

## Known gaps at launch

Stated here so they are decisions rather than oversights.

**One book quoting, on every card.** `books quoting` is 1 on all 58 cards
because the tracker captures a single provider. Market depth carries no
information anywhere in the product. It is a tracker change, it is the highest
value / lowest cost item on the roadmap, and it improves the grade, the
cautions and the reliability record at once.

**No reason to visit between slates.** The board shows the current week; a
reader who has seen it has seen everything. The public reliability record is
the fix and it is next.

**Data completeness is a constant.** 15 of the 100 grade points are 1.000 on
every card.

**Search will be slow.** Game pages have a one-week shelf life and no inbound
links. The first months of organic traffic will be long-tail team queries, and
that is the expected shape rather than a failure.

---

## The success criterion

A visitor understands, in thirty seconds: **what Atlas is, what Atlas is not,
how to use it, and why it is valuable.**

The first screen of `/about.html` carries all four:

> **Atlas grades its own numbers.**
>
> Every college football game gets a card: what the market says, what Atlas
> projects, what is driving the difference — and a letter saying how much that
> card's information has historically been worth. **Atlas never tells anyone
> what to do with it.**

*What it is* — a card per game with a market number, a projection and a
grade. *What it is not* — the bold clause. *How to use it* — the two buttons.
*Why it is valuable* — "how much that card's information has historically been
worth" is a claim nothing else in the category makes.

---

## Document map

| Document | Track |
|---|---|
| `ONBOARDING_FLOW.md` | 1 — landing page, as built |
| `FREE_VS_PREMIUM_FINAL.md` | 2 — the line, and what changed |
| `EMAIL_STRATEGY.md` | 3 — two emails, specified not built |
| `LAUNCH_PLAN.md` (this) | 4 and 7 — SEO, and the brand audit |
| `SOCIAL_PLAYBOOK.md` | 5 — the operating manual |
| `POST_LAUNCH_METRICS.md` | 6 — what to measure, and what not to |
