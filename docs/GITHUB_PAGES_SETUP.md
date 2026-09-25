# Atlas — Publishing on GitHub Pages

The free path. `RUNNING_COSTS.md` has the arithmetic; this is how to turn it
on. `DEPLOYMENT_GUIDE.md` covers the VPS path, which is where this goes when
the 15-minute cadence or the access-log analytics becomes worth $12 a month.

**Cost: $0/month plus the domain.**

---

## What was built

Three workflows replace the two that never ran.

| File | When | What |
|---|---|---|
| `publish.yml` | called, never scheduled | the only copy of the build, the Pages deploy and the commit-the-record step |
| `site-heavy.yml` | 04:00 ET daily | ingest, warehouse, model, market, every page, social assets |
| `site-poll.yml` | hourly; 15 min on game days | the market and nothing else |

`live-poll.yml` and `live-refresh.yml` are gone. They polled the market and
maintained the reports but **never built the website**, and their schedule
disagreed with `atlas/ops/schedule.py`. There is now one schedule, and it lives
in the code.

### Cron is UTC; the product is Eastern

Neither can be fixed by writing a cleverer cron, because the offset changes
twice a season. So the crons fire a deliberate superset and
`atlas/ops/schedule.py` decides, in Eastern time, using the committed
freshness stamp. A run that is not due stops at the gate in a few seconds,
before installing anything.

The superset is also what survives GitHub dropping scheduled runs, which it
does under load and most at the top of the hour. Both crons sit off the hour:
the poll fires at :04, :19, :34 and :49 every day, and the heavy run at :12
past 08:00-11:00 UTC, the later hours being backups the gate turns away once
the day's heavy run has succeeded.

### The gate asks "is it due", not "is it the minute"

GitHub documents that a scheduled workflow "can be delayed during periods of
high loads." `should_poll()` tests an exact minute, which is right for cron and
wrong here: a run that fires at 11:07 would answer *no*, and a late poll would
become a **lost** poll. `schedule.due()` compares against the last *successful*
run instead, so a delay stays a delay. Eight tests pin the behaviour, including
the 11:07 case.

---

## Turning it on — four steps, all in GitHub

**1. Set the Pages source.**
Settings → Pages → Build and deployment → Source = **GitHub Actions**.
Nothing deploys until this is done.

**2. Merge to `main`.**
Scheduled workflows only ever run on the default branch. Until the merge these
are dormant, and `Run workflow` in the Actions tab is the only way to fire them.

**3. Seed the warehouse — run `site heavy` once, by hand.**
Actions → **site heavy** → Run workflow.

`data/raw` and `data/warehouse` are gitignored and about 230 MB. The heavy run
builds them and saves them to the Actions cache; a poll only ever restores.
Until one heavy run has completed there is no cache, and the poll workflow
**fails deliberately** with a message saying so rather than publishing a site
built from an empty warehouse.

**4. Optional: add `CFBD_API_KEY`.**
Settings → Secrets and variables → Actions → New repository secret.

Without it the warehouse still builds and drops the enrichment columns — SP+,
FPI, recruiting, returning production. With it, CFBD's free tier is ample:
`_cached()` fetches a season once and never again.

---

## The URL, before and after the domain

Until `atlas.football` is registered the site lives at a Pages **subpath**:
`https://<owner>.github.io/<repo>/`. Every internal link in Atlas is already
relative, so the pages work there unchanged — but canonicals, Open Graph URLs,
the sitemap and robots.txt are absolute, and a canonical claiming a domain
nobody owns is worse than an ugly one.

So `render.py`'s `SITE_URL` now reads `ATLAS_SITE_URL` from the environment,
**defaulting to production**. The workflow sets it to the Pages URL at the
*job* level, not on one step — `make site-audit` depends on `site` and rebuilds
it, which would silently rewrite every canonical back to production if the
variable were scoped to a single step. (That is not hypothetical; it happened
while this was being tested.)

### The cutover, when the domain is live

1. Register `atlas.football` and point it at GitHub Pages.
2. Settings → Pages → Custom domain → `atlas.football`, and tick **Enforce HTTPS**.
3. Settings → Secrets and variables → Actions → **Variables** → set
   `ATLAS_SITE_URL` to `https://atlas.football`, or simply delete the variable —
   the code's default is already production.
4. Run `site heavy` by hand so every canonical is rewritten in one pass.

`scripts/validate_seo.py` now understands a base with a path, so it validates
both spellings.

---

## What gets committed, and why

Each run commits `tracking/` and `data/ops/freshness.json` back to the branch.

`tracking/` is the one thing in Atlas that cannot be rebuilt — a signal is an
opinion published at a moment, and the moment does not come back. Committing it
is also its offsite backup, free.

`data/ops/freshness.json` used to be gitignored on the grounds that it is
machine state derived from the clock. On this path it is not: every timestamp
on the site is read back out of it, and a poll running in a fresh container
that had never heard of the heavy refresh would publish a board with half its
provenance missing. So that one file is tracked; the rest of `data/ops/` is
still ignored.

---

## Known costs of this path

| | |
|---|---|
| A scheduled run can be late, or dropped | the gate turns late into late. A dropped run is a missed poll; `last_ok` means the page never overstates its freshness |
| No access log | `atlas.ops.analytics` reads Combined Log Format and has nothing to read on Pages. Cloudflare Web Analytics is the free substitute, and it is a rewrite rather than a setting |
| ~1,300 gated runs a month in the Actions tab | most stop at the gate in seconds. Filter by workflow to find CI |
| 100 GB/month bandwidth, soft | about 4 million page views at 23 KB a page |

None of these is a reason not to launch on it. All of them are reasons the VPS
path in `DEPLOYMENT_GUIDE.md` exists for later.
