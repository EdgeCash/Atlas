# Atlas — Status Page Specification

**Track 7.** `/status.html`, built on every run. `atlas/ops/status.py` is the
model; `render.status_page` is the page.

---

## Why it is public

Atlas asks readers to trust a grade. A product that asks for trust and hides
its own operational state is asking for the thing it refuses to give.

It is also the same discipline as the reliability record: **a claim nobody can
audit is a claim.** The status page is the version of that for "how current is
this", and it costs nothing — the data already exists because the health check
needs it.

One model feeds three consumers — the page, `make ops-status`, and the health
check — so they cannot drift.

---

## What it shows

### Header

A badge and the current mode:

> **All systems reporting** — ordinary schedule, polling every 60 minutes.

On a game day: *"NCAAF Saturday, polling every 15 minutes."* When a blocking
check fails the badge reads **Degraded** in the warning tone.

### Freshness

The last **successful** run of each task, with its age.

| Row | Limit |
|---|---|
| Last heavy refresh | 24 hours |
| Last market poll | 2 hours |
| Board published | 3 hours |
| Social assets | 48 hours |

A row past its limit renders in the critical tone with its value in red.

### Providers

Where the information comes from, and what it last did.

| Row | Value |
|---|---|
| Market provider | `espn` — last run status and quote count, from the tracker's own run log |
| **Books quoting** | **1** — flagged, with the reason |
| Team metadata | ESPN scoreboard — venue, broadcast, records, ranks, crests, cached 6 hours |
| Warehouse | point-in-time, nine seasons |

**Books quoting is deliberately red.** It is a real limitation: market depth
carries no information anywhere in the product until a second provider is
added, and it is named on the card, in the roadmap, and here. Putting a
product's weakest number on its own status page is the point of having one.

### Tracker

| Row | Meaning |
|---|---|
| Signals recorded | opinions published before kickoff |
| Signals graded | games played and scored against the entry line |
| Awaiting a result | graded once the game is complete |
| Line observations | appended only when a number changes |
| Atlas numbers live | one per scheduled game and market |

Read straight from the tracking store. If it is unreadable the section says
so rather than showing zeros — a zero and a failure look identical otherwise.

### Health checks

The same seven checks the operator's alert runs on, with the same pass/fail.
Publishing them means a reader and an operator are looking at one truth.

### Footer note

> **What the timestamps mean.** Every stamp on this site is the time of the
> last **successful** refresh of that thing, in Eastern — never the time a
> page was built and never your browser's clock. A rebuild that ran against a
> failed market poll shows the market's older time, because that is when the
> numbers a reader is looking at were last true.

---

## Design

Uses the existing system: `.section`, `.card`, `.badge`, the status palette.
No new tokens, no charts, no colour carrying meaning alone — a failing row is
red **and** its value reads `FAIL` or `never`.

Rows stack on a phone (label, value, note) and become three columns above
720px. Nothing on the page moves or auto-refreshes; it is a static page like
every other, rebuilt on the same schedule as everything else.

---

## Where it is linked

- Every footer, beside *questions* and *how Atlas works*.
- Every freshness stamp on the board and on every card.
- In the sitemap at `changefreq: daily`, `priority: 0.4` — it should be
  crawlable and it is not a landing page.

---

## What it does not show

- **No uptime percentage.** Atlas is a static site; "uptime" is the host's
  and claiming it would be claiming something not measured.
- **No incident history or postmortems.** The failure streak in the health
  checks is the honest version at this scale.
- **No per-request metrics.** Nothing is counted per reader; see
  `POST_LAUNCH_METRICS.md`.
- **No subscribe-to-updates.** It is a page, not a service.

---

## Operator view

```bash
make ops-status
```

The same model as plain text:

```
Atlas status — ordinary schedule, polling every 60 minutes

Freshness
   Last heavy refresh     Sep 22, 2026 10:42 PM ET   (0 minutes ago)
   Last market poll       Sep 22, 2026 10:42 PM ET   (0 minutes ago)
   Board published        Sep 22, 2026 10:43 PM ET   (0 minutes ago)
   Social assets          Sep 22, 2026 10:43 PM ET   (0 minutes ago)

Providers
   Market provider        espn   (last run ok, 116 quotes)
 ! Books quoting          1   (a known limitation …)
 …

Atlas health
  [  ok] poll: 0.0h ago, limit 2h
  …
0 failing, 0 warning, 7 ok
```
