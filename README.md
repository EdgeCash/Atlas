# Atlas - NCAAF Research Warehouse

A point-in-time-correct historical database for NCAAF (2018-present) and the
research needed to answer one question: **which variables actually predict
college football games?**

Phase 1A deliberately produces no projections, no simulations, no wagers and
no dashboard. It produces a warehouse, a measurement, and a recommendation.

## What is here

| Deliverable | Where |
|---|---|
| Point-in-time warehouse (8 tables, parquet + DuckDB) | `data/warehouse/` |
| Phase 1A research report | [`reports/atlas_research_report_v1.md`](reports/atlas_research_report_v1.md) |
| Phase 1B opponent-adjustment report | [`reports/opponent_adjustment_report.md`](reports/opponent_adjustment_report.md) |
| Phase 1B weather report | [`reports/weather_data_report.md`](reports/weather_data_report.md) |
| Phase 1B QB availability report | [`reports/qb_availability_report.md`](reports/qb_availability_report.md) |
| **Phase 1C information edge report** | [`reports/atlas_information_edge_v1.md`](reports/atlas_information_edge_v1.md) |
| Phase 1C QB value model | [`reports/qb_value_model_report.md`](reports/qb_value_model_report.md) |
| Phase 1C market efficiency | [`reports/market_efficiency_report.md`](reports/market_efficiency_report.md) |
| Phase 1C roster continuity | [`reports/roster_continuity_report.md`](reports/roster_continuity_report.md) |
| Phase 1C situational edge | [`reports/situational_edge_report.md`](reports/situational_edge_report.md) |
| Phase 1C market failure | [`reports/market_failure_report.md`](reports/market_failure_report.md) |
| Phase 1C Velocity comparison | [`reports/velocity_comparison_report.md`](reports/velocity_comparison_report.md) |
| **Signal verification (final verdict)** | [`reports/atlas_signal_verification_final.md`](reports/atlas_signal_verification_final.md) |
| Threshold freeze report | [`reports/threshold_freeze_report.md`](reports/threshold_freeze_report.md) |
| Bootstrap signal report | [`reports/bootstrap_signal_report.md`](reports/bootstrap_signal_report.md) |
| Pre-registered criteria | [`docs/SIGNAL_PREREGISTRATION.md`](docs/SIGNAL_PREREGISTRATION.md) |
| **Phase 2: Velocity edge decomposition** | [`reports/velocity_edge_decomposition.md`](reports/velocity_edge_decomposition.md) |
| **Phase 3: market-aware beta framework** | [`reports/atlas_beta_framework.md`](reports/atlas_beta_framework.md) |
| **Phase 4: gamma assessment (monetization)** | [`reports/atlas_gamma_assessment.md`](reports/atlas_gamma_assessment.md) |
| **Phase 5: live CLV tracking (updated continuously)** | [`reports/live_clv_tracking.md`](reports/live_clv_tracking.md) |
| Phase 5 operations manual | [`docs/LIVE_TRACKING.md`](docs/LIVE_TRACKING.md) |
| Phase 5 raw record (CSV, committed) | `tracking/` |
| Phase 4 opening-line feasibility | [`reports/opening_line_feasibility.md`](reports/opening_line_feasibility.md) |
| Phase 4 CLV economics | [`reports/clv_economics.md`](reports/clv_economics.md) |
| Supporting tables (CSV/JSON) | `reports/tables/` |
| Alpha model recommendation | [`docs/ATLAS_ALPHA_SPEC.md`](docs/ATLAS_ALPHA_SPEC.md) |
| Point-in-time methodology | [`docs/POINT_IN_TIME.md`](docs/POINT_IN_TIME.md) |
| Column reference | [`docs/DATA_DICTIONARY.md`](docs/DATA_DICTIONARY.md) |

## Headline result

Measured on **5,778 FBS-vs-FBS games, 2018-2025**, leave-one-season-out:

| | Margin MAE | Total MAE |
|---|---|---|
| Closing line (raw) | **12.22** | **12.71** |
| ESPN pre-game FPI projection | 12.92 | - |
| CFBD pre-game Elo | 13.11 | 13.85 |
| **Atlas opponent-adjusted efficiency** | **13.39** | 13.21 |
| Atlas raw efficiency | 13.96 | **13.17** |
| ESPN FPI, previous-season rating | 14.10 | 13.85 |
| SP+, previous-season rating | 14.18 | 13.57 |

No candidate variable improved on the closing line by more than its own noise,
and no benchmark cleared the 52.38% break-even hit rate against it. Marginal
value over the market is reported as a paired per-game comparison with a
t-statistic, so a 0.01 MAE point estimate cannot be mistaken for an edge.

### The final answer: no edge

The one candidate surviving Phases 1A-1C - selective NCAAF totals - was
pre-registered and held out. **It failed all four criteria.**

| Criterion | Required | Observed | |
|---|---|---|---|
| Pooled holdout win rate | > 52.38% | **51.65%** | FAIL |
| Bootstrap 95% CI lower bound | > 50.0% | **49.81%** | FAIL |
| Walk-forward seasons clearing -110 | ≥ 5 of 7 | **4 of 7** | FAIL |
| Expected units at -115 | > 0 | **-97.3** | FAIL |

The frozen threshold ranged from **1 to 8 points** across experiments that
differed only in which seasons they trained on - there is no stable threshold
to freeze. Holding it fixed at 4 points across every season, the most
favourable honest reading available, lands 0.02% from break-even and nets
-0.9 units over seven seasons.

**Recommendation: terminate Atlas Alpha.** Four phases have found every
variable Atlas can reach already priced into the closing line. That is a real
finding, and it is worth more than a model that would have lost money slowly.

### Phase 2: benchmarking against Velocity

[Velocity](https://github.com/EdgeCash/Velocity) runs a nightly card across
four sports. Phase 2 asked why, given Atlas concluded the market is efficient.

**The two projects agree wherever they have measured the same thing.**
Velocity's own edge research opens with "the closing line of a liquid market is
nearly unbeatable with public data"; its intelligence-layer backtest measures a
null on matchup/form/rest "because the closing line already prices them"; and
it excludes NCAAF spreads on 50.1% ATS over 9,518 games. Atlas read 49.7%.

The difference is not information. Velocity prices a far larger surface — five
game markets, props, DFS, two prediction exchanges — so *something* clears an
EV gate every night. Its own strategy review reports 60% of the NCAAF card's
stake sits in moneylines that "have never been backtested in this repo", and
that the record chain has **zero settled rows**.

Atlas's one independent contribution: **selecting the biggest model-market
disagreements makes things worse.** The top 1% of Atlas's totals disagreements
hit 40.7%; the curve is non-monotone. That replicates Velocity's own
adverse-selection finding (`corr(stake, CLV) = −0.35`) on completely different
data.

Worth borrowing, in order: the publish gate's **edge ceiling**, **market
anchoring**, **CLV as the grading metric**, **constitutional staking caps**,
and **per-market evidence gating**. None of them is a football insight.

### Phase 5: the live tracker

History is finished. Atlas is now a live validation project with one job:
**record an opinion about a line, record what the market then does, and grade
the two against each other.**

> Atlas generates opinions. Atlas does not generate bets. Nothing in
> `atlas/live/` computes a stake, expected profit, ROI or a Kelly fraction, and
> a test tokenises the package on every CI run to keep it that way.

The system splits by cost: a **weekly refresh** rebuilds the warehouse with
scheduled games and publishes Atlas's number for each one; an **hourly poll**
captures the current quote, forms an opinion on games it has not already
called, grades anything that has kicked off, and rewrites the scorecard. The
poll never touches the warehouse, so it runs in seconds.

Every signal stores two numbers: what the book *opened* on, and what it was
quoting when Atlas spoke. **CLV is graded against the second one** — crediting
Atlas with movement that happened before it had an opinion is exactly the
failure Gamma's third kill criterion exists to catch.

The three kill criteria are transcribed from Phase 4 and pinned by a test:
beat rate ≥ **55%**, mean CLV ≥ **0.49 points**, and fewer than half of signals
flagged for a closed execution window. Nothing is called decided until **124
graded primary signals** have accumulated. They are checked, never tuned.

Two complete seasons, then one of two recommendations and no middle ground.
Operations manual: [`docs/LIVE_TRACKING.md`](docs/LIVE_TRACKING.md).

### Phase 4: can the movement signal be executed?

Phase 3 measured CLV against one book's opener and a consensus close across
roughly six books. That is not a bet anyone can place, so Phase 4 rebuilt the
line table **per sportsbook** and graded each side at the book that posted it.

**The signal survives.** Same-book grading gives **55.4%** on margins
(z = 8.9) and **58.8%** on totals (z = 13.2), against the consensus method's
55.2% and 58.9% - a book effect of 0.0005. It was not an artefact.

**It is still not a bet.** One point of CLV is worth ~2.5% of win probability
and -110 costs 2.38%, so -110 demands roughly **one full point**. Atlas
averages 0.28 (margins) and 0.41 (totals). Concentrating on the loudest 10% of
signals at the open lifts totals to **1.02 points (52.55% implied)** - clearing
-110 by 0.17% on the point estimate, with a 95% lower bound of 52.04% that does
not clear, in 3 of 6 seasons.

Three structural findings decide the rest:

* **Only four books in the entire feed ever post an opener**, all retail
  (Bovada opens 67% of games). Pinnacle and BOOKMAKER appear only at the close.
* **The early number is sold worse.** In the one book-season where both prices
  are visible, the opener is -110 where the close is -105 - and that 5-cent
  penalty is ~45% of the entire edge on the best cell in the study.
* **Track 5 is unanswerable.** Atlas holds no timestamped odds, so the optimal
  execution window cannot be measured at all.

**Recommendation: BUILD ATLAS CLV SYSTEM** - instrument and grade the signal on
CLV, acquire a timestamped archive, and do not wager. A pre-registered kill
criterion is frozen in the report.

### Phase 3: the market as the prior

Phases 1 and 2 asked whether Atlas could beat the closing line. Phase 3 changed
the question, treating the market as the prior rather than the benchmark, and
found that Atlas is good at something nobody had measured: **predicting which
way the line will move.**

| Market | Beats the close (open → close) | z | Picks winners |
|---|---|---|---|
| Margin | **54.4%** of 3,963 graded games | +5.5 | 49.8% |
| Total | **58.3%** of 4,175 graded games | +10.7 | 52.2% |

Positive in six seasons out of six in both markets, and it survives the
falsification that matters: a constant lean, a within-season shuffle of the
predictions and a coin-flip side all score **at or below 50%**. Games where the
line never moved are CLV pushes, not CLV losses - grading them as losses
understated every beat rate by roughly six points and hid this result
entirely.

It is still not obviously a bet. One point of line is worth ~2.4% of win
probability, so the movement Atlas anticipates is worth **1.0% on totals and
0.7% on margins** - under the vig. Discarding the quarter of the slate where
the model disagrees most with the close (the single most valuable rule found in
five phases) roughly doubles it to 1.9% and 1.6%, which clears **-105 and
nothing worse**.

The fitted market weight is **0.98 on margins and 0.89 on totals**, and the
unanchored model's Brier score is *worse than declaring every game a coin
flip*. Full framework, including when not to bet:
[`reports/atlas_beta_framework.md`](reports/atlas_beta_framework.md).

### Phase 1C: the search for unpriced information

Phase 1C stopped measuring team quality and went looking for information the
market does not have. It ran **50 pre-kickoff hypothesis tests** across
quarterback events, roster and staff continuity, situational angles,
market-failure characteristics and line movement.

**Zero survived a pooled Benjamini-Hochberg correction.**

It also **withdrew Phase 1B's headline finding.** The 2.1-point "quarterback
change" signal was reverse causation - teams pull their quarterback *because*
the game is going badly:

| | Games | Residual | t |
|---|---|---|---|
| QB changed *during* the game | 1,600 | **+4.81** | 11.7 |
| New QB who took ~every snap (knowable pre-kickoff) | 870 | **-0.97** | -1.9 |

The one live candidate is a **method, not a variable**: scoring a totals model
by its hit rate on its biggest disagreements with the market rather than by
mean error. Atlas reads 52.0% flat rising to 53.9% at an 8-point cut;
[Velocity](https://github.com/EdgeCash/Velocity) independently reports 51.6%
rising to 53.4%. Break-even is 52.38%, so this is a tie that might be an edge -
and it is the only direction two independent models both point at.

### Earlier findings

Findings worth pulling out:

* **Opponent adjustment works, and does not help against the market.** It
  removes 0.53 points of margin MAE against raw efficiency (t = 7.3) and puts
  Atlas ahead of SP+ and FPI. Against the closing line it is worth exactly as
  much as raw efficiency was: nothing.
* **In-season beats stale.** A system's current view of a matchup (ESPN's
  pre-game FPI projection, 12.92) is far better than the same family's
  previous-season rating (14.10).
* **Totals are a different problem.** Adjustment helps margin and *hurts*
  totals - an opponent adjustment redistributes credit between two teams and a
  total is their sum, so it largely cancels. Pace gets actively worse.
* **Weather is free now, and priced.** Meteostat bulk station data gives
  kickoff conditions for 89% of the sample with no API key. Scoring falls with
  wind - and so does the closing total.
* **Quarterback availability is the one thing that is not zero.** A team
  starting a different quarterback than the week before underperforms the
  closing line by ~2.3 points, significant in 6 of 8 seasons. That is an upper
  bound on perfect pre-kickoff knowledge, and it is not yet obtainable for
  free with history.

## Quick start

```bash
make install     # pip install -e ".[dev]"
make all         # ingest -> warehouse -> research -> phase 1B reports
```

Or step by step:

```bash
python -m atlas.ingest                    # stage 1: sources -> data/raw
python -m atlas.warehouse.build           # stages 2-3: staging -> warehouse + DuckDB
python -m atlas.research.report           # stage 4: Phase 1A report
python -m atlas.research.phase1b_report   # stage 5: Phase 1B reports
make qb-data                              # research-only QB extraction
python -m atlas.research.phase1c_report   # stage 6: Phase 1C reports
python -m atlas.research.validation_report # stage 7: signal validation
python -m atlas.research.velocity_report   # stage 8: Velocity benchmark
python -m atlas.research.beta_report       # stage 9: Phase 3 market-aware framework
python -m atlas.research.gamma_report      # stage 10: Phase 4 execution research

python -m atlas.live refresh               # Phase 5: publish Atlas's numbers (weekly)
python -m atlas.live run                   # Phase 5: poll, grade, report (hourly)
```

The quarterback-of-record extraction writes nothing into the warehouse, and
`atlas.warehouse.build` never imports it. A column only knowable at kickoff
has no business sitting among point-in-time features - Phase 1C is the
demonstration of why, and a test enforces the boundary.

A full rebuild downloads roughly 1 GB of play-by-play, which is trimmed to
~35 MB on disk, and takes a few minutes.

Query the result:

```bash
python -c "
import duckdb
con = duckdb.connect('data/warehouse/atlas.duckdb', read_only=True)
print(con.execute('SELECT season, count(*) FROM research_games GROUP BY 1 ORDER BY 1').df())
"
```

## Enabling CFBD (optional)

Atlas builds end-to-end with no API key. A free
[CollegeFootballData](https://collegefootballdata.com/key) key adds the fields
that exist nowhere else - **SP+ ratings (overall, offence and defence),
recruiting rankings, roster talent and returning production**. Kickoff weather
needs a *paid* CFBD tier and is reported as unavailable on a free key:

```bash
export CFBD_API_KEY=...
make all
```

Nothing else changes: the same tables gain non-null columns and the report
fills in Section 3 and the corresponding rows of the variable ranking. The
report states the exact blocker for anything still missing rather than
assuming a key is absent.

## Layout

```
atlas/
  config.py            scope, paths, constants - one place to change a run
  ingest.py            stage 1 driver
  sources/             collectors: sportsdataverse, espn, cfbd (key-gated)
  staging/             teams, games, market, efficiency, adjusted efficiency,
                       ratings, talent, weather, context
  features/            the point-in-time engine + opponent adjustment
  warehouse/           schema + build into parquet and DuckDB
  research/            dataset, models, benchmarks, importance, validation,
                       adjustment study, residual tools, QB features,
                       Phase 1C tracks, reports
  testing/             deterministic synthetic league used by the test suite
scripts/
  check_reproducible.py       builds twice, asserts byte-identical output
  research_qb_availability.py QB feasibility probe (research only)
tests/                 offline suite: 124 tests, no network
```

## Data sources

| Source | Key | Provides |
|---|---|---|
| sportsdataverse `cfbfastR-data` | no | schedules, results, team/venue geography, historical sportsbook lines (open, close, moneyline, per book) |
| sportsdataverse `cfbfastR_cfb_pbp` | no | play-by-play with EPA and success |
| ESPN public endpoints | no | FPI season ratings, pre-game matchup projections |
| Meteostat bulk files | no | hourly station weather - kickoff temperature, wind, precipitation, humidity |
| sportsdataverse rosters | no | season rosters - transfer and first-year identification |
| CollegeFootballData API | free key | SP+ (overall/offence/defence), recruiting, roster talent, returning production, coaching staffs, weekly polls |

## Testing and CI

```bash
make test    # pytest, offline
make lint    # ruff
python scripts/check_reproducible.py
```

The suite builds a complete warehouse from a seeded synthetic league and runs
the entire research pipeline over it, so the code under test is the code that
runs in production. CI additionally builds the warehouse twice from identical
sources and asserts every table is byte-identical.

## Testing and reproducibility

The suite sets `ATLAS_OFFLINE=1`, so any accidental network call fails loudly
rather than quietly downloading a gigabyte of real data. Weather is exercised
end to end against synthetic station files in the collector's own layout.

## Two methodological rules, both learned the hard way

1. **Point-in-time is necessary but not sufficient.** A variable can be
   computed correctly from only prior information and still be worthless if
   the thing it describes is *caused by* the outcome. Every such variable is
   reported in both a contemporaneous and a lagged form, and only the lagged
   form supports a conclusion.
2. **Pool p-values and correct once.** Phase 1C ran 50 tests; at p < 0.05 that
   is ~2.5 apparent findings from noise alone. Post-hoc tests are carried but
   excluded from the pool and labelled.
3. **Pre-register before you look.** The validation phase fixed its model,
   threshold rule and pass/fail criteria in a commit of their own, *before*
   any holdout season was scored. The git history is the audit trail.

Phase 1B lacked the first two and it cost the programme a headline finding.
Phase 1C lacked the third and it cost the programme the next one.

## Scope boundary

The programme stops here. No predictions, no simulations, no wagers, no
dashboard, no Phase 2. The warehouse remains a clean, point-in-time-correct,
reproducible research instrument for college football, and the negative
results are reusable: anyone restarting this search can begin from "these
forty variables are priced".
