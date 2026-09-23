# Atlas — Launch Checklist

**Track 7.** Everything that must be true before Atlas is public, and who or
what verifies it.

A box is only ticked when something checks it. Items verified by a human
judgement call are marked **manual** and named as such.

---

## The gate

```bash
make launch-check
```

Runs the audit over every built page, then 256 tests, then lint. **Non-zero
exit on any blocking finding.** Nothing below should be ticked until this is
green.

Current state:

```
Atlas launch audit — 181 pages

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

256 passed · All checks passed!
```

---

## 1. Platform stability

| | Item | Verified by |
|---|---|---|
| ✅ | Build completes from a cold repository | `make site-full` |
| ✅ | Build is ~7 seconds for 181 pages | build log |
| ✅ | Site is static — no server, no database, no runtime dependency | architecture |
| ✅ | Every page works with JavaScript disabled | the only script is board filtering; card panels are native `<details>` |
| ✅ | No third-party asset blocks a page — logos are cached and served locally | `meta.cache_logos` |
| ✅ | No horizontal scroll at 390px on any page | screenshot pass |
| ✅ | Largest page is ~31 KB; whole site 13 MB | build output |
| ✅ | Build is reproducible — same inputs, same output | `scripts/check_reproducible.py` |
| ⬜ | **manual** — hosting configured, HTTPS, `atlas.football` resolving | not done |
| ✅ | A 404 page exists, with `noindex` and no canonical | `site/404.html` |

## 2. Analytics

| | Item | Verified by |
|---|---|---|
| ✅ | No third-party analytics script anywhere | `audit_site.py` finds no external script |
| ✅ | No ad pixel, no cross-site identity, no account | architecture |
| ✅ | The metric set is decided before launch, not after | `POST_LAUNCH_METRICS.md` |
| ✅ | The headline number is chosen: **share of readers who open a marked-down card** | same |
| ✅ | Grade of a viewed card is derivable from the URL — no client instrumentation needed | build knows every card's grade |
| ⬜ | **manual** — server log retention and access configured | depends on hosting |
| ⬜ | First-party counter for panel opens and filter use | **not built**, optional at launch |

## 3. SEO

| | Item | Verified by |
|---|---|---|
| ✅ | Canonical URL on all 180 indexable pages (the 404 has none, on purpose) | `audit_site.py` |
| ✅ | Unique `<title>` and meta description on every page | `audit_site.py` |
| ✅ | `sitemap.xml` — 180 URLs, per-type `changefreq` and `priority` | build log |
| ✅ | `robots.txt` allows crawling and points at the sitemap | built |
| ✅ | `SportsEvent` on cards, `SportsTeam` on team pages, `Organization` on the landing page | `audit_site.py` |
| ✅ | Structured data omits the grade and the projection | `test_a_card_carries_structured_data_for_the_game_and_nothing_more` |
| ✅ | Open Graph and Twitter cards with absolute image URLs | `audit_site.py` |
| ✅ | Discovery strategy written, including what Atlas will **not** chase | `LAUNCH_PLAN.md` |
| ⬜ | **manual** — sitemap submitted to Search Console and Bing | after DNS |
| ⬜ | **manual** — link unfurl checked on X and iMessage | after DNS |

## 4. Social

| | Item | Verified by |
|---|---|---|
| ✅ | Two templates generated on every build, 1200×675 and 1080×1080 | `make site` |
| ✅ | A spread of grades is rendered, so a marked-down card is always available | `_spread_of_grades` |
| ✅ | Templates are parsed as XML and language-scanned | `test_social_templates_*` |
| ✅ | Neither template has anywhere to put a side | design |
| ✅ | Every card explains itself without surrounding text | the "what this means" sentence |
| ✅ | Disclaimer on every card: *Grade = information quality, not a recommendation* | template footer |
| ✅ | Posting schedule, per-channel strategy and card selection written | `SOCIAL_PLAYBOOK.md` |
| ⬜ | **manual** — accounts created, bios set, handle secured on X, IG, Threads | not done |
| ⬜ | **manual** — launch post drafted and approved | copy in `FINAL_CONTENT_COPY.md` |

## 5. Legal and disclaimers

| | Item | Verified by |
|---|---|---|
| ✅ | Every card carries *"not a recommendation"* | `audit_site.py`, 58 of 58 |
| ✅ | Every card carries the "what this card is" disclosure | `test_every_card_repeats_the_difference_disclaimer` |
| ✅ | No page names a side | two tests plus the audit |
| ✅ | No figure that implies a return anywhere in the product | language tests |
| ✅ | Footer on every page: *"Atlas publishes information. Readers make their own decisions."* | layout |
| ✅ | No affiliate links, no book partnerships, stated publicly | `premium.html` |
| ✅ | No payment path, no checkout, no subscription — Rule 3 | nothing built |
| ⬜ | **manual** — privacy note published (what is logged, what is not) | **not written** — see gaps |
| ⬜ | **manual** — terms of use, or an explicit decision not to have one | not decided |
| ⬜ | **manual** — a "must be 21+" style notice, or the decision that Atlas does not need one because it does not facilitate anything | **decision needed** |

That last row is the one to think about. Atlas publishes no selections and
takes no money, so it is not a gambling service — but it describes betting
markets, and jurisdictions differ on what that requires. It is a legal question,
not a product one, and it should be answered before launch rather than after.

## 6. Live tracker status

| | Item | Verified by |
|---|---|---|
| ✅ | Tracker runs and writes deterministic signal ids | `atlas.live` |
| ✅ | Numbers and snapshots feed the cards | `data.build_cards` |
| ✅ | Signals accumulating against a two-season horizon | Phase 5 |
| ✅ | Data-quality gates, drift detection, anomaly checks in place | Operations phase |
| ✅ | Tracker never computes a stake — checked in source | `test_the_tracker_never_computes_a_stake` |
| ⚠️ | **One provider quoting.** Every card shows `1 book quoting`, so market depth carries no information anywhere | named on the card and in the launch plan |
| ⬜ | **manual** — a schedule that refreshes numbers and rebuilds before each slate | **not configured** |
| ⬜ | **manual** — alerting if the tracker stops writing | not built |

The scheduled refresh is the one operational gap that would be visible to a
reader: without it, the board goes stale mid-week and the market numbers stop
matching reality.

## 7. Content

| | Item | Verified by |
|---|---|---|
| ✅ | Landing page explains Atlas in the first screen | `ONBOARDING_FLOW.md`, `test_the_landing_page_answers_the_four_questions_it_promises` |
| ✅ | FAQ written, including the uncomfortable questions | `FAQ.md` |
| ✅ | Every positioning string collected in one place | `FINAL_CONTENT_COPY.md` |
| ✅ | Research page explains the grade, the thresholds and the A+ caveat | `research.html` |
| ✅ | NFL page explains why there are no NFL cards | `nfl.html` |
| ✅ | Premium page says plainly there is no way to subscribe | `premium.html` |
| ✅ | FAQ published as a page on the site | `site/faq.html`, linked from the footer and the landing page |
| ⬜ | Waitlist form | **not built**, `WAITLIST_STRATEGY.md` |

---

## Gaps at launch, as decisions

Each of these is a choice, not an oversight.

**No privacy note.** Atlas logs less than almost any site on the internet, which
is a thing worth saying rather than leaving implied.

**No scheduled rebuild.** The site is built by hand today. Before launch it
needs a schedule: refresh the market, rebuild, publish.

**One book quoting.** The highest-value item on the roadmap and not a blocker —
the card says so honestly.

**Nothing to return for between slates.** The known structural gap. The public
reliability record is the fix and it is next.

---

## Recommended order

1. `make launch-check` green. **Done.**
2. FAQ page and 404. **Done this pass.**
3. Write the privacy note.
4. Answer the jurisdiction question.
5. DNS, HTTPS, hosting.
6. Configure the scheduled refresh and rebuild.
7. Submit the sitemap; check unfurls.
8. Create the social accounts.
9. Launch with the landing page as the link and one marked-down card as the
   first post.

Steps 3 and 4 are the only ones that should hold a launch date, and only step 4
is genuinely blocking. Everything from 5 onward is deployment rather than
product.
