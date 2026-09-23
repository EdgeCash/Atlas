# Atlas — RC1 Checklist

Feature freeze, design freeze, research freeze. This is the readiness record.

A box is ticked only when something checks it. Items that need a human are
marked **manual** and named as such.

---

## The gate

```bash
make launch-check     # audit → SEO validation → 299 tests → lint
```

```
Atlas launch audit — 182 pages
BLOCKING   [ok] forbidden vocabulary 0 · a named side 0 ·
                card missing the grade disclaimer 0 · motion or urgency 0
ADVISORY   [ok] canonical 0 · meta description 0 · structured data 0 ·
                social tags 0 · freshness stamp 0 · timestamp without a zone 0

Atlas SEO validation — 182 pages against https://atlas.football
ERROR: 0     warn: 0

299 passed · All checks passed!
```

---

## Track 1 — deployment readiness

| | Item | Verified by |
|---|---|---|
| ✅ | Build completes from a cold repository | `make site-full` |
| ✅ | Build is ~7 s for 182 pages, 357 files, 13 MB | build log |
| ✅ | **Build is deterministic** — two consecutive builds produced 351 of 352 byte-identical files | measured, below |
| ✅ | Static: no server, no database, no runtime dependency | architecture |
| ✅ | Every page works with JavaScript disabled | card panels are native `<details>` |
| ✅ | No third-party asset blocks a page — 142 crests cached and served locally | `meta.cache_logos` |
| ✅ | Image generation: 24 social files per build, SVG source + PNG at 2× | `make site` |
| ✅ | Cron schedule is Eastern-pinned and testable | `make ops-crontab`, `test_the_crontab_pins_eastern_explicitly` |
| ✅ | Cron reliability: every task idempotent, no auto-retry, next run is the retry | `OPERATIONS_SCHEDULE.md` |
| ✅ | A failed task records the failure without advancing a visible timestamp | `test_a_failed_run_never_advances_a_visible_timestamp` |
| ⬜ | **manual** — hosting, HTTPS, `atlas.football` resolving | `DEPLOYMENT_GUIDE.md` |

### The determinism measurement

Two consecutive builds into separate directories, every file hashed:

```
files: 352 vs 352
differing files: 1
    status.html
```

`status.html` changes by design — it carries ages in minutes. Of the 182 HTML
pages, **60 carry a timestamp** and the other 122 are byte-stable between
rebuilds. An incremental deploy therefore moves very little, which matters for
CDN invalidation and for reading a deploy diff.

---

## Track 2 — analytics

| | Item | Verified by |
|---|---|---|
| ✅ | Page views, board views, card views, team views | `atlas/ops/analytics.py` |
| ✅ | Most viewed cards and most viewed teams | same |
| ✅ | Traffic source — X, Threads, Instagram, Reddit, search, email, direct | `test_traffic_source_is_derived_from_the_referrer` |
| ✅ | **The headline metric** — share of card views that were marked down | `test_the_headline_metric_needs_no_client_instrumentation` |
| ✅ | Assets and crawlers excluded from page views | `test_assets_and_crawlers_are_not_readers` |
| ✅ | **Nothing stored identifies a reader** | `test_analytics_stores_nothing_that_identifies_a_reader` |
| ✅ | No third-party script anywhere on the site | `audit_site.py` |
| ⬜ | **manual** — access log retention configured at the host | `DEPLOYMENT_GUIDE.md` |

Implemented as a log reader, not a tracker. `POST_LAUNCH_METRICS.md` decided
this before the site existed, and it holds: the grade of every card is known
to the build, so the one number that matters needs no client instrumentation
at all.

---

## Track 3 — backups

| | Item | Verified by |
|---|---|---|
| ✅ | Tracker, signal and grade backups, gzipped with a manifest | `atlas/ops/backup.py` |
| ✅ | **Every backup is read back and checked on creation** | `backup_and_verify` |
| ✅ | Checksum per file, row count per table, columns validated | `verify()` |
| ✅ | A restore was performed and compared to the source | measured, below |
| ✅ | An empty critical table is stored as its header, not skipped | `test_an_empty_critical_table_is_backed_up_as_its_header` |
| ✅ | Restore refuses to overwrite the live store | `test_restore_refuses_to_overwrite_the_live_store` |
| ✅ | Corruption and missing files are detected | two tests |
| ✅ | 30-day retention with pruning | `prune()` |
| ✅ | Scheduled daily at 03:00 ET, before the heavy refresh | `make ops-crontab` |
| ⬜ | **manual** — an off-machine copy | see gaps |

```
verify: clean
restored: {games: 58, grades: 0, numbers: 1210, runs: 4, signals: 116, snapshots: 131}
signals identical: True
refuses live overwrite: refusing to restore over the live tracking store …
```

One backup is 17.7 KB for 1,519 rows. A year is under 7 MB.

---

## Track 4 — performance

Measured in Chromium over HTTP, three runs, median. Browser Performance API,
not a stopwatch.

| Viewport | Page | LCP | Load | Transfer | Requests |
|---|---|---|---|---|---|
| mobile 390 | board | **100 ms** | 77 ms | 68.4 KB | 30 |
| mobile 390 | card | **64 ms** | 22 ms | 23.2 KB | 3 |
| mobile 390 | team | 44 ms | 15 ms | 5.4 KB | 2 |
| mobile 390 | landing | 56 ms | 18 ms | 11.2 KB | 1 |
| tablet 834 | board | 104 ms | 58 ms | 68.4 KB | 42 |
| tablet 834 | card | 68 ms | 17 ms | 23.2 KB | 3 |
| desktop 1440 | board | 120 ms | 65 ms | 68.4 KB | 40 |
| desktop 1440 | card | 76 ms | 20 ms | 23.2 KB | 3 |

**Every page is 40–120 ms LCP.** Google's "good" threshold is 2,500 ms; Atlas
is about twenty times inside it on localhost, and the numbers are dominated by
paint rather than by transfer, so a real network moves them by the round trip
and not much else.

**Card render performance:** 3 requests, 23 KB, 64–76 ms. The card is the
page most readers land on and it is the second-lightest on the site.

**The board's 30–42 requests are the crests.** One per team on the board,
served locally and cached by the browser after the first visit. It is the only
page on the site that makes more than three requests, and at 68 KB it is still
under a single stock photograph.

Reproduce with `make perf`.

---

## Track 5 — SEO validation

`scripts/validate_seo.py` — 182 pages, **0 errors, 0 warnings**.

| | Check |
|---|---|
| ✅ | Canonical present, absolute, on the right origin, and **self-referential** |
| ✅ | No two pages share a canonical |
| ✅ | `<title>` unique and within 65 characters |
| ✅ | Meta description present and 70–165 characters |
| ✅ | Open Graph complete where claimed — title, description, type, site name |
| ✅ | A Twitter card wherever Open Graph appears |
| ✅ | **`og:image` is absolute and the file exists on disk** |
| ✅ | Sitemap parses; every URL resolves to a real file; valid `changefreq` and `priority` |
| ✅ | Every indexable page is in the sitemap; the 404 is not |
| ✅ | `robots.txt` allows crawling and points at the sitemap |
| ✅ | The 404 has **no** canonical and **is** `noindex` |

It found and I fixed: five card titles over 65 characters, and 153 descriptions
outside the 70–165 band — team pages at 167–177, the board at 243, the landing
page at 202. Copy only; no design or product change.

---

## Track 6 — beta instrumentation

| | Item |
|---|---|
| ✅ | Feedback route — one footer link, `mailto:beta@atlas.football` |
| ✅ | Bug report and feature request flows | `BETA_FEEDBACK_LOOP.md` |
| ⬜ | **manual** — the mailbox exists and somebody reads it |

**This is the only visible change RC1 makes.** One footer link beside *data
status*. No button, no modal, nothing on the board or the card, nothing that
touches a frozen surface. A form would need a server, and the one thing this
product does not have is a server.

---

## Track 7 — release

| | Item |
|---|---|
| ✅ | RC1 checklist — this document |
| ✅ | Launch day plan | `LAUNCH_DAY_PLAN.md` |
| ✅ | Rollback plan | `LAUNCH_DAY_PLAN.md` |
| ✅ | Deployment guide | `DEPLOYMENT_GUIDE.md` |

---

## What changed in RC1

Stabilization only. No design change, no feature addition, no product change.

**New, all operational:** `atlas/ops/analytics.py`, `atlas/ops/backup.py`,
`scripts/validate_seo.py`, `scripts/measure_performance.py`, the 03:00 backup
in the crontab, and `make perf` / `seo` / `ops-backup` / `ops-analytics`.

**Changed:** meta descriptions and five card titles trimmed to fit search
results. One footer link.

**Tests:** 280 → **299**.

---

## Gaps, as decisions

**Blocking, and not a product question**

- **The jurisdiction question.** Atlas publishes no selections and takes no
  money, so it is not a gambling service — but it describes betting markets,
  and jurisdictions differ. Legal, and outstanding since the launch phase.

**Manual, before DNS**

- Hosting, HTTPS, the domain.
- The scheduled tasks installed, with a writable log directory.
- An **off-machine copy** of the backups. On-machine backups survive a bad
  deploy and not a lost disk, and the tracking store is the one thing in Atlas
  that cannot be rebuilt.
- A mailbox for `beta@atlas.football`.
- Access log retention.

**Named limitations the product is honest about**

- **One book quoting.** On every card, on the status page in red, and top of
  the roadmap.
- **No privacy note.** Atlas logs less than almost any site on the internet,
  which is worth saying rather than leaving implied.
- **Nothing to return for between slates.** The public reliability record is
  the fix and it is the first thing after launch.

---

## Readiness

**RC1 is ready to deploy.** Every automated gate is green, the build is
deterministic, the backup has been restored and compared, and performance is
twenty times inside the threshold at every viewport.

What stands between RC1 and public: one legal answer and a morning of
infrastructure.
