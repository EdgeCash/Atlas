# Atlas — What It Costs to Run

Audited 23 September 2026 against the repository and the GitHub Actions
billing API, not estimated.

## The answer

**Atlas currently costs $0 a month.**

Not "nearly nothing" — nothing. Every external dependency is either a free
public endpoint or a free tier the workload does not come close to exhausting,
and there is no website yet to host.

---

## Every recurring line, checked

| Line | Cost | Evidence |
|---|---|---|
| GitHub repository | **$0** | `EdgeCash/Atlas` is **public** |
| GitHub Actions | **$0** | public repos get unlimited standard runners. The billing API reports `total_ms: 0` on every run |
| Live odds | **$0** | `atlas/live/provider.py` reads ESPN's public scoreboard — no key, no account |
| Historical data | **$0** | sportsdataverse parquet mirrors on GitHub |
| Weather | **$0** | `bulk.meteostat.net`, free bulk download |
| CFBD enrichment | **$0** | free tier is 1,000 calls/month; see below |
| Web hosting | **$0** | there is no site deployed yet |
| Domain | **$0** | `atlas.football` is not registered yet |
| Payments, email, analytics, LLM | **$0** | none are wired. The only credential any code reads is `CFBD_API_KEY` |

### Why CFBD is free and stays free

`atlas/sources/cfbd.py` caches to `data/raw/cfbd/` and `_cached()` returns
early when the file exists, so a season's ratings are fetched **once, ever**.
69 files are already cached. A cold ingest from nothing is roughly 100 calls
against a 1,000/month allowance, and the daily schedule makes **zero** — the
heavy refresh reads local parquet and polls ESPN.

CFBD's paid tiers start at $1/month and buy call volume Atlas does not need.

---

## What the automation actually does today

Worth stating plainly, because it is not what the deployment guide assumes.

| Workflow | Schedule | What it does |
|---|---|---|
| `ci.yml` | every push | lint, tests on 3.11 + 3.12, reproducibility check. **24 runs so far, all free** |
| `live-poll.yml` | hourly, Aug–Jan | polls the market, grades, commits `tracking/` back to the repo |
| `live-refresh.yml` | weekly, Tuesdays in season | ingest, rebuild, publish Atlas's numbers |

**Neither live workflow has ever run.** Both carry the note that scheduled
workflows only fire on the default branch, and both are still waiting on a
merge. The Actions history is 24 CI runs and nothing else.

**And neither builds the website.** They run `atlas.live`, which maintains the
tracking record and the reports. Nothing in CI runs `atlas.site.build`, so the
public site has never been published by automation.

### Two schedules that do not know about each other

| | Cadence |
|---|---|
| `.github/workflows/live-poll.yml` | hourly, months 8–12 and 1 |
| `atlas/ops/schedule.py` | 15 min on game days, hourly otherwise, all year |

The second was written for a VPS crontab and is not wired into Actions. The
freshness, health and status machinery hangs off it, so on the Actions path
today none of it is driving anything. Whichever host is chosen, these two have
to become one schedule.

---

## The cheapest way to get a site up

The repository being public changes the arithmetic, because it removes the
constraint that made a server look necessary.

| | Free stack | Server stack |
|---|---|---|
| Host | GitHub Pages | VPS + nginx |
| Scheduler | GitHub Actions | cron |
| Deploy cap | **none** — the 10-builds-per-hour limit does not apply to custom Actions workflows | none |
| Bandwidth | 100 GB/month soft — about 4 million page views at 23 KB a page | whatever the VPS allows |
| Site size cap | 1 GB against a 13 MB site | — |
| Custom domain + HTTPS | free | free via Let's Encrypt |
| **Monthly** | **$0** | **$11–22** |

**Start on the free stack.** The only recurring cost of launching Atlas is the
domain: roughly $10 the first year and $25–30 to renew, so about **$1–3 a
month amortised.**

### What the free stack costs you instead of money

**Scheduled runs can be late or dropped.** GitHub documents that the `schedule`
event "can be delayed during periods of high loads" and that "some queued jobs
may be dropped." Atlas stamps every page with when its information was last
refreshed, so a missed run publishes a timestamp that overstates freshness.
This is tolerable at an hourly cadence and uncomfortable at fifteen minutes.
Mitigations: schedule off the hour, and let the page state the last *successful*
refresh — which `atlas/ops/freshness.py` already separates as `last_ok`.

**There is no access log.** `atlas.ops.analytics` reads Combined Log Format and
reports traffic by page type and by the grade of the cards readers opened.
GitHub Pages gives no log, so that report goes dark. Cloudflare Web Analytics
is free and privacy-preserving and reports per-path traffic, which the card
grades can still be joined against — but it is a rewrite, not a config change.

**Polling commits to the repository.** `live-poll.yml` commits `tracking/` on
every run. At an hourly in-season cadence that is a few hundred commits a
month in a public repo. It is noisy, and it is also free offsite replication of
the one file in Atlas that cannot be rebuilt.

### When to move to the server

When any of these becomes true, and not before:

- the 15-minute game-day cadence matters more than $12 a month
- the access-log analytics is worth paying for
- a dropped refresh has actually embarrassed you

---

## Correction to the earlier recommendation

`DEPLOYMENT_GUIDE.md` §0 argued against GitHub Actions partly on cost — that
~1,070 publishes a month would consume the 2,000-minute free allowance. **That
reasoning assumed a private repository and does not apply here.** Actions
minutes on a public repo are free and unlimited, and the billing API confirms
every run so far was billed at zero.

The reliability argument stands; the cost argument does not.

---

## The one cost this audit cannot see

Everything above is infrastructure. The real spend on Atlas so far has been
development time and assistant usage, which does not appear in any API this
repository can query.
