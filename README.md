# Atlas - Phase 1A Research Warehouse

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
make qb-research                          # optional: QB feasibility probe
```

`make qb-research` is deliberately outside `make all`: it re-downloads full
play-by-play and it writes nothing into the warehouse, because a
quarterback-of-record column is only knowable at kickoff and has no business
sitting among point-in-time features.

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
                       adjustment study, reports
  testing/             deterministic synthetic league used by the test suite
scripts/
  check_reproducible.py       builds twice, asserts byte-identical output
  research_qb_availability.py QB feasibility probe (research only)
tests/                 offline suite: 85 tests, no network
```

## Data sources

| Source | Key | Provides |
|---|---|---|
| sportsdataverse `cfbfastR-data` | no | schedules, results, team/venue geography, historical sportsbook lines (open, close, moneyline, per book) |
| sportsdataverse `cfbfastR_cfb_pbp` | no | play-by-play with EPA and success |
| ESPN public endpoints | no | FPI season ratings, pre-game matchup projections |
| Meteostat bulk files | no | hourly station weather - kickoff temperature, wind, precipitation, humidity |
| CollegeFootballData API | free key | SP+ (overall/offence/defence), recruiting, roster talent, returning production |

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

## Scope boundary

Phases 1A and 1B stop here. No predictions, no simulations, no wagers, no
dashboard, no Phase 2.
