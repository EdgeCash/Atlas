# Atlas — Analytics, Final

**Track 2.** Implemented in `atlas/ops/analytics.py`. No client-side code, no
third-party script, no account.

---

## The decision, made before the site existed

`POST_LAUNCH_METRICS.md` settled this: *"Server logs and a single first-party
counter. No third-party analytics script. The site is static and has 40 lines
of JavaScript; adding a tracker would multiply that and hand a reader's
browsing to somebody else."*

RC1 implements exactly that and nothing more. **Atlas ships zero analytics
JavaScript.** The web server already writes a line per request; the analyser
reads it.

```bash
make ops-analytics LOGS="--access-log /var/log/atlas/access.log"
```

---

## What it measures

### Page views, by type

Board, card, team, and every named page. A request counts as a page view only
when it is a `GET`, returns 200 or 304, is not an asset, and does not come
from a crawler. Bots are roughly a quarter of raw requests and are counted
separately rather than silently folded in.

### Most viewed cards and teams

Counted by slug, straight from the path.

### Traffic source

Derived from the referrer's host:

| Source | Matches |
|---|---|
| `x` | t.co, twitter.com, x.com |
| `threads` | threads.net, threads.com |
| `instagram` | instagram.com, l.instagram.com |
| `reddit` | reddit.com, out.reddit.com |
| `search` | google, bing, duckduckgo, yahoo |
| `email` | mail.google, outlook, list-manage |
| `internal` | atlas.football |
| `direct` | no referrer |
| `other` | anything else |

### The headline metric

**The share of card views that were marked down.**

`POST_LAUNCH_METRICS.md`: *"Atlas's entire position is that it tells you when
not to trust it; if nobody reads the cards where it says so, the position is
decoration."*

This needs **no instrumentation at all**. The build knows every card's grade —
`analytics.card_grades()` reads it back out of the rendered pages — so the
log's path is enough to attribute a view to a letter. That is the whole
argument for log-based analytics in one example: the thing worth knowing was
already knowable.

---

## What it stores

| Kept | Not kept |
|---|---|
| counts by path, kind, source, grade, day | IP addresses |
| response code totals | user agents |
| bot request total | sessions, cookies, fingerprints |
| | anything joining one request to another |

A test asserts the aggregate contains no IP and no user-agent string:
`test_analytics_stores_nothing_that_identifies_a_reader`.

The raw access log does contain IPs — that is the web server's doing, not
Atlas's — and the deployment guide points at `logrotate`. Nothing Atlas writes
retains them.

---

## What it cannot do, and why that is the trade

| Not supported | Why it is acceptable |
|---|---|
| Funnels | Atlas has one page type that matters and one action: open a card |
| Cohorts / retention curves | needs identity across sessions, which is the line |
| Session replay | needs a script on every page |
| Scroll depth, panel opens | would need the first-party counter, which is optional and unbuilt |
| Real-time dashboards | the log is read on demand; nothing is live |

The one genuine loss is **panel opens** — which of the card's six tier-2
panels readers actually expand. `POST_LAUNCH_METRICS.md` wanted it ("nobody
opens *how this grade was computed*" would mean the grade is being taken on
faith). That needs a few bytes of first-party event logging and it is
deliberately not in RC1: it is the only item that would add JavaScript to a
frozen product.

---

## The report

```
Atlas traffic

  requests          12,431
  page views         4,102
  bot requests       3,118  (25%)

By page type
  card                                        2,104   51.3%
  board                                       1,201   29.3%
  team                                          512   12.5%

Traffic source
  x                                           1,890   46.1%
  direct                                        901   22.0%
  search                                        612   14.9%

Most viewed cards
  central-michigan-chippewas-miami-hurricanes    340   16.2%

Grade of the cards opened
  B                                             812   38.6%
  C                                             604   28.7%
  D                                             288   13.7%
  A                                             213   10.1%
  F                                             100    4.8%

  marked down (D or F): 18.4% of graded card views
```

*(Shape only — no traffic exists yet.)*

---

## Reading it

| Signal | Good | Bad |
|---|---|---|
| Marked-down share of card views | rising, or near the board's own 19% | near zero — the honesty is decoration |
| Card views ÷ board views | above 1 | at 1 — everyone arrives from a link and leaves |
| `x` as a source | high early | zero after posting — the cards are not travelling |
| `search` | rising across a season | flat — team pages are not accumulating |
| Bot share | 20–40% | above 70% — something is crawling badly |

No targets are set at launch. There is no prior, the first season sets the
baseline, and `POST_LAUNCH_METRICS.md` commits to publishing it rather than
quietly re-baselining.

---

## What Atlas will not measure

Unchanged from `POST_LAUNCH_METRICS.md`, restated because RC1 is where the
temptation starts:

- **Nothing identifying a reader across sessions.**
- **Nothing about what a reader does after leaving.** No affiliate
  attribution, no outbound click tracking. If Atlas could see it, someone
  would eventually optimise for it.
- **No A/B tests on the grade** — not its wording, not its prominence, not
  whether the caveat appears. The grade is a research output, not a conversion
  surface.
- **No engagement scoring of cards.** A "most popular card" widget is one
  product decision from being a ranking of what to look at, which
  `GRADE_STRATEGY_V2.md` §5 establishes Atlas cannot honestly publish.

The "most viewed cards" table above is an **operator** view in a terminal. It
does not go on the site, for exactly that reason.
