# Atlas — Improvement Backlog

What to build next, in order, and the evidence for each. Collected on
26 September 2026 from the model reports, the product docs checked against
the code, and two days of running the live schedule. An item leaves this list
when it ships or when a measurement says it is not worth doing; either way the
reason goes in its line.

Effort is S (hours), M (a day or two), L (a week or more).

---

## 1. Reliability

**Alert when the site goes stale.** Shipped 26 September:
`.github/workflows/watchdog.yml` and `atlas/ops/watchdog.py`. Hourly, on its
own schedule, it reads the freshness stamps committed on main and keeps one
`site-stale` issue in step: opened when a blocking health check fails or the
last three site-poll runs all failed, refreshed quietly while it stays stale,
closed on recovery.

**One bad word should not freeze the whole site.** S–M. The audit blocks the
entire deploy on a single forbidden word on a single page (the Kelly/Shorts
Stadium card on 25 September). Venues are now marked as names, but a team,
coach or player name can do it again. Better: hold back the offending page,
deploy the rest, and alert.

## 2. Model accuracy

Walk-forward CRPS (lower is better):

| | Atlas | Market | Elo |
|---|---|---|---|
| College margin, 2021–25 | 8.923 | 8.606 | 9.230 |
| College total | 9.126 | 8.847 | — |
| NFL margin, 2023–25 | 7.290 | 7.074 | 7.372 |
| NFL total | 7.364 | 7.240 | — |

Sources: `reports/ncaaf_state.md`, `reports/ncaaf_total.md`,
`reports/nfl_state.md`, `reports/nfl_total.md`.

**Start capturing NFL starter and injury reports now.** S to start, then it
accumulates. NFL games with a changed quarterback score 7.611 against 7.209
for the rest, while the market's gap on the same split is 0.05
(`reports/nfl_state.md`). The depth chart names the new starter in only
56–59% of those games (`MODEL_PLAN_NFL.md`). College shows the same miss:
−2.46 points in a new starter's first game (`reports/ncaaf_qb.md`). Nothing
can be backtested until a season of history exists, so the value of starting
is the history it builds up. The SEC/ACC availability capture
(`atlas/sources/availability.py`) is the college half, and the model does not
read it yet.

**College weeks 1–4 prior.** M–L, off-season. This is the largest gap: 9.101
against 8.413 in weeks 1–2, 9.281 against 8.663 in weeks 3–4, and about 0.18
by weeks 9–12 (`reports/ncaaf_state.md`). The season is past week 4, so work
here pays from next August.

**Score the NFL total on forecast wind.** S. It is scored on the wind recorded
at game time, which the report calls "a mild look-ahead"
(`reports/nfl_total.md`). Scoring on a pre-kickoff forecast makes the number
honest, and the true gap is probably a little larger than it looks.

**Run the college connectivity test.** S, diagnostic. Specified in
`MODEL_PLAN_NCAAF.md`: score inter-conference games separately from
in-conference ones. It has never been run.

## 3. Site features and UX

**Grade reliability on the record page.** Shipped 26 September, recording from
that day: `atlas/site/grade_record.py`. Every build logs each card's grade
before kickoff to `tracking/card_grades.csv` (the first letter it showed, kept,
and the last, which is graded); the record page shows claimed against realised
on the spread, by letter, with n and a "few" marker under 30 cards. No grade
before 26 September was kept, so the record starts empty and fills as games go
final. The first letter kept for each card is also what grade movement
("opened B, now C") will need.

**An "other models" panel.** Shipped 26 September: `atlas/sources/other_models.py`
and the card's "Other models" panel. The roadmap's premise that the data was
already in the warehouse, fresh, did not hold: ESPN's projection was fetched
once and never refreshed, the schedule file once a season, and SP+ is only the
previous season's (on purpose, for the model). So the heavy refresh fetches
them fresh for upcoming games - FPI's own margin and chance to win (both
sports), current pre-game Elo and current SP+ (college) - and logs them to
`tracking/other_models.csv` before kickoff. Display only; the model never reads
them. The same log is the forward record the owner page's consensus label needs.

**Two template fixes.** Shipped 26 September.
- Board rows, and the featured tiles' phone line, read `Atlas total 58.9`
  beside the market's total instead of an unlabelled `Atlas +0.4` (proposal 1
  in `MOBILE_UX_AUDIT.md`).
- The card header shows each side's rest and trip when known, e.g.
  `Rest UTA 7 days, ISU 13 days · Travel UTA 1,012 mi`. Rest over 21 days (a
  season opener) and trips under 50 miles are left out.

**A way to measure readers.** Built 26 September; counting starts once it is
deployed. GitHub Pages keeps no access log, so the log analyser had nothing to
read. A first-party counter instead (`counter/`, `ANALYTICS_SPEC_FINAL.md`,
"The counter"): a Cloudflare Worker keeping daily counts of page views,
new and returning visits and card panels opened, with no cookie and nothing
that identifies a reader, read only in the owner page's Readers section.

**Later.** Grade movement ("opened B, now C"); a standings page; a context
block (dome, neutral site); deeper team pages.

---

## Research: expert and computer consensus, for the owner page

**The question.** Does the consensus of experts, or of other computer models,
carry information about the result that the line does not? And does it sharpen
the curated plays (`atlas/owner/plays.py`)?

**Where it lives.** Only inside the owner page's ciphertext, like the curated
plays and the DFS lineups: sealed with the owner key, one file a week, never
on the public site, where "Not a picks service" (`PRODUCT_VISION.md`) still
holds.

**Sources.**

| Source | What it has | Access |
|---|---|---|
| SP+, FPI, Elo (college) | three rating systems' implied margins | **already in the warehouse** (`atlas/sources/cfbd.py`, `atlas/staging/ratings.py`), with history |
| The Prediction Tracker | dozens of computer models' predicted margins and totals, NCAAF and NFL, with history | public pages and CSVs behind a Cloudflare bot check that blocked a scripted download on 26 September; by hand works |
| Massey ratings comparison | a composite of about 100 college rating systems | same Cloudflare check |
| Pickwatch | human expert picks aggregated, each expert's record tracked | scraping; terms to check |
| ESPN, CBS, USA Today expert picks | straight-up and against-the-spread picks from named writers | scraping; terms to check |

**Plan, in the order the evidence allows.**

1. *Computer consensus for college, now.* SP+, FPI and Elo are already here
   with history, so the backtest needs no new source. Pre-register it as
   `SIGNAL_PREREGISTRATION.md` did: fix the feature (consensus margin minus the
   line; Atlas and consensus agreeing or not), the holdout seasons and the pass
   bar before scoring anything.
2. *A label on each curated play, meanwhile.* Beside the quarterback flag:
   where the consensus sits and whether it agrees with Atlas's side. A label,
   never a filter, so the frozen rules stay frozen and the record shows
   whether agreement mattered.
3. *Human expert picks: start the record.* Log them before kickoff, sealed,
   never revised, like the plays, from a source whose terms allow it, or from
   a weekly file the owner provides. They cannot be tested until a record
   exists, so the value of starting is the history it builds up.
4. *A new rule only if a test passes.* A rule that uses consensus is frozen
   with a new id and starts its own record the day it is frozen, as v1 and v2
   did. The history it was chosen on is shown beside it, never mixed in.
