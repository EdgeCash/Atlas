# Atlas — Deployment Guide

Atlas is a static site with a scheduled build. There is no server to run, no
database to provision and no queue. What follows is a morning of work.

---

## What Atlas needs

| | |
|---|---|
| Runtime | Python 3.11+, the repository, the dependencies in `pyproject.toml` |
| Disk | ~2 GB — the warehouse, the tracking store, the built site (13 MB) and a year of backups (<7 MB) |
| Network | outbound HTTPS to the ESPN scoreboard and the sportsdataverse mirrors |
| Web server | anything that serves files — nginx, Caddy, S3 + CloudFront, Netlify, GitHub Pages |
| Scheduler | cron, or anything that runs a command on a clock |

No inbound ports besides the web server's. Nothing in Atlas listens.

---

## 0. Where to host it, and what it costs

Measured on this repository rather than estimated, because the numbers pick the
machine.

> **Corrected 23 September 2026.** This section originally argued against
> GitHub Actions partly on cost, assuming a private repository's 2,000-minute
> allowance. **`EdgeCash/Atlas` is public**, so Actions minutes are free and
> unlimited and the billing API reports every run so far at zero. The cheapest
> way to launch is therefore GitHub Pages + Actions at **$0/month plus the
> domain** — see `RUNNING_COSTS.md`. What follows is the right answer once the
> 15-minute cadence or the access-log analytics is worth paying for; it is not
> the right answer for day one.

| | Measured |
|---|---|
| Built site | **13 MB**, 352 files — 182 HTML, 154 PNG, 12 SVG |
| Heavy rebuild, warehouse step | 67 s, **2.9 GB peak RSS** |
| Heavy rebuild, site render | 43 s, 400 MB |
| Poll — market capture + render | ~45 s, 400 MB |
| Working data on disk | ~250 MB (`data/raw` 184 MB, warehouse 45 MB, staging 13 MB) |
| **Publishes per month** | **1,068** — `should_poll()` counted over September 2026 |

Three of those decide everything.

**The site is 13 MB.** Serving it is free anywhere. Hosting is not the cost and
should not drive the decision.

**The schedule publishes 1,068 times a month.** Every game-day poll rewrites the
board, so each one is a publish. Cloudflare Pages allows 500 deployments a month
on the free plan, so that host is out — but GitHub Pages has no deploy cap when
a custom Actions workflow does the publishing, and on a public repository those
minutes are free. What survives is the *reliability* objection, not the cost
one: GitHub's own documentation says a scheduled workflow "can be delayed during
periods of high loads" and that "some queued jobs may be dropped." Atlas stamps
every page with when its information was last refreshed, so a skipped run
publishes a timestamp that overstates freshness. That is tolerable hourly and
uncomfortable at fifteen minutes.

**The heavy rebuild peaks at 2.9 GB.** That sets the box. 4 GB runs it without
thought; 2 GB runs it with a swapfile, because the spike lasts about ten seconds
and happens at 04:00 when nobody is reading.

### The recommendation

**One small always-on VPS running cron and nginx, with Cloudflare's free plan in
front of it.**

| | |
|---|---|
| Server | 4 GB / 2 vCPU — Vultr $20/mo, DigitalOcean $24/mo |
| CDN, TLS, DNS | **Cloudflare free** — unlimited bandwidth, free certificate |
| Domain | `atlas.football`, roughly $10 the first year and $25–30 to renew |
| **Total** | **~$21–25 a month** |

Cloudflare in front matters more than the choice of VPS: it absorbs a traffic
spike from a post that lands, so the origin only ever serves the CDN, and a
13 MB site behind a cache never troubles a small machine.

A cheaper variant that works: **2 GB with a 4 GB swapfile, about $10–12 a
month.** The only thing that touches 2.9 GB is one daily step. Verify it on day
one by watching `make ops-heavy` complete, and keep the 4 GB option in reserve.

### Why not the free tiers

| Option | Why not |
|---|---|
| Cloudflare Pages / Netlify free | 500 deploys a month against 1,068 publishes — and no access log, see below |
| GitHub Pages + Actions | **nothing, for day one** — free and uncapped on a public repo. The costs are a scheduled run that may be dropped, and no access log. Start here; see `RUNNING_COSTS.md` |
| Oracle Cloud Always Free | genuinely free and big enough (2 OCPU / 12 GB ARM), but ARM capacity is scarce in US regions and Oracle halved this tier in June 2026 without announcing it. Fine to experiment on; not what a launch should depend on. |

**The access log is the second reason to own the web server.** `atlas.ops.analytics`
reads Combined Log Format and reports traffic by page type and by the grade of
the cards readers opened — with no tracker, no consent banner and no third
party. That report exists because nginx writes the log. Host the site on a
managed static platform and the analytics design in `ANALYTICS_SPEC_FINAL.md`
has to be replaced with somebody's JavaScript.

### If the monthly cost needs to come down further

The 2.9 GB peak is not inherent. `_load_duckdb` holds every staged table in
memory at once and hands them to DuckDB together; writing them one at a time and
releasing each would cut the peak substantially and make a 1–2 GB machine
comfortable rather than tight. That is an afternoon of work against roughly $10
a month, so it is worth doing only once the site is actually up.

---

## 1. Install

```bash
git clone <repo> /srv/atlas && cd /srv/atlas
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"      # or: make install
make site-full          # warehouse, numbers, market, site — the cold path
make launch-check       # audit, SEO, 299 tests, lint. Must be green.
```

`site-full` takes minutes because it rebuilds the warehouse. Everything after
that is seconds.

---

## 2. Serve

The built site is `site/`. Every path is relative and there is no server-side
logic, so any static host works.

### nginx

```nginx
server {
    server_name atlas.football;
    root /srv/atlas/site;

    error_page 404 /404.html;

    # HTML is rebuilt on a schedule and must not be cached past it. A reader
    # holding a stale board would see a timestamp that says it is fresh.
    location ~* \.html$ {
        add_header Cache-Control "public, max-age=300, must-revalidate";
    }
    # Crests and social cards are content-stable; the social PNGs change name
    # when the card does.
    location /assets/logos/ { add_header Cache-Control "public, max-age=604800"; }
    location /social/       { add_header Cache-Control "public, max-age=86400"; }

    # Combined format, which atlas.ops.analytics reads.
    access_log /var/log/atlas/access.log combined;
}
```

**The HTML cache header matters.** Atlas stamps every page with when its
information was last refreshed. A CDN holding an hour-old board would serve a
timestamp that says the board is current when it is not, which breaks the one
promise `TIMESTAMP_STANDARD.md` makes. Five minutes is shorter than the
fastest publish cadence (15 minutes on a game day) and long enough to absorb a
traffic spike.

### Behind a CDN

Purge `*.html` after each build, or set the origin cache to five minutes and
let the edge revalidate. Assets can be cached hard — crests never change and
social cards are rebuilt under the same name only once a day.

---

## 3. Schedule

```bash
make ops-crontab | crontab -      # uses the working directory as the root
mkdir -p /var/log/atlas
```

```cron
CRON_TZ=America/New_York
0 3 * * *    make ops-backup    # copy the record, read the copy back
0 4 * * *    make ops-heavy     # warehouse, model, market, every page
0 5 * * *    make ops-social    # the featured card assets
*/15 * * * * make ops-poll      # market only; skips non-poll minutes
30 * * * *   make ops-health    # the check
```

`CRON_TZ` is not optional. Without it a 4 AM build becomes a 3 AM build in
November and the whole schedule moves an hour twice a season.

### Verify it

```bash
make ops-heavy && make ops-health && make ops-status
```

`ops-health` exits non-zero when anything is stale, so it drives an alert
directly:

```cron
30 * * * * cd /srv/atlas && make ops-health || mail -s "Atlas degraded" you@example.com
```

---

## 4. Backups, off this machine

`make ops-backup` writes to `data/backups/` and verifies what it wrote. That
survives a bad deploy. It does not survive a lost disk, and **the tracking
store is the only thing in Atlas that cannot be rebuilt** — the warehouse can
be re-ingested and the site regenerated, but a signal is an opinion published
at a moment and the moment does not come back.

Add one line:

```cron
15 3 * * * rsync -a /srv/atlas/data/backups/ backup-host:/atlas/backups/
```

Then, once, prove it: copy a backup back and run
`python -c "from atlas.ops import backup; print(backup.verify(...))"`. A
backup nobody has restored is a hypothesis.

---

## 5. Analytics

No setup on the site — there is nothing to install, because there is no
tracker. Point the reader at the access logs:

```bash
make ops-analytics LOGS="--access-log /var/log/atlas/access.log"
```

```
Atlas traffic
  requests          12,431
  page views         4,102
  bot requests       3,118  (25%)

By page type
  card                                        2,104   51.3%
  board                                       1,201   29.3%
  …
Grade of the cards opened
  B                                             812   38.6%
  …
  marked down (D or F): 18.4% of graded card views
```

That last line is the headline metric from `POST_LAUNCH_METRICS.md` and it
needs no client instrumentation — the build already knows every card's grade.

Rotate logs with `logrotate`; the reader takes `.gz` files directly.

---

## 6. Deploying a change

```bash
git pull && make launch-check && make site
```

The build is deterministic: two consecutive runs produce 351 of 352
byte-identical files, and only the 60 pages carrying a timestamp change
between rebuilds. So a deploy diff is small and readable, and an rsync moves
very little.

```bash
rsync -a --delete /srv/atlas/site/ /var/www/atlas/
```

`--delete` is safe and wanted: cards for games that have been played should
stop being served, and the 404 page explains that.

---

## Environment

| Variable | Needed? | What it does |
|---|---|---|
| `CFBD_API_KEY` | optional | enrichment — SP+, FPI, recruiting, returning production. The warehouse builds without it from the open mirrors. |
| `ATLAS_DATA` | optional | move `data/` elsewhere |

**No secret is required to run Atlas.** If `CFBD_API_KEY` is set, keep it in
the environment and never in the repository; a test greps the tree for one.

---

## Failure modes

| Symptom | Cause | What to do |
|---|---|---|
| Board timestamp stops moving | poller died | `make ops-health`; check `/var/log/atlas/poll.log` |
| `make ops-health` fails on poll | provider down | nothing — the next run is 15 minutes away and does not retry into a struggling provider |
| Projections stale, market fresh | heavy refresh failed | `make ops-heavy` by hand; check the warehouse step |
| Build fails halfway | bad input | the previous `site/` is still served; nothing is half-written |
| Status page shows *Degraded* | any blocking check | the page names which |
| Disk filling | backups | `prune` keeps 30; check the warehouse and raw cache |

**Nothing retries automatically.** The next scheduled run is the retry, at
most fifteen minutes away. A task that retries inside its own window hammers a
provider that is already struggling.

---

## What is deliberately not here

- **No containers.** A Python process and a crontab; a container would add a
  build step to a project whose whole deployment is `rsync`.
- **No CI/CD pipeline.** `make launch-check` is the gate and it runs anywhere.
- **No blue/green.** The site is static; a rollback is a checkout and a
  rebuild — see `LAUNCH_DAY_PLAN.md`.
- **No secrets management.** There are no required secrets.
