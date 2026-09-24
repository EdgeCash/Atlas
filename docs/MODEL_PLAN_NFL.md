# Atlas — NFL Model Plan

Inherits `MODEL_FOUNDATION.md`. This document covers only what is specific to
the NFL: the data, the empirical profile, the factors and their measured sizes,
the model specification, and the order to build it in.

**Status: nothing exists.** Atlas has no NFL data, no NFL warehouse, no NFL
model. `nfl.html` is a placeholder. Everything below is a plan.

---

## 1. Why the NFL is the harder of the two models

Three structural facts, all measured.

**Parity.** The NFL's team-strength spread is narrow. Glickman & Stern's
posterior strengths run from +8.4 to −9.4 points around the mean; the residual
sd is 13.1. So the *signal* (strength differences) is about the same size as
the *noise* (one game). In college the spread is more than twice as wide.

**Small samples.** 32 teams, 17 games, ~272 regular-season games a season.
Every persistence statistic in the foundation is noisier for the NFL, and
one season cannot distinguish a CRPS improvement smaller than ~0.15.

**The market is already very good, very early.** Last season's net EPA alone
gives weeks 1–2 a margin MAE of 9.27; the closing line gives 9.13; ignoring
everything and taking the home team by two gives 10.15. The market's
information edge over a pure last-season prior is **0.14 points of MAE**. There
is not much room, and what room there is comes from personnel — above all the
quarterback.

---

## 2. Data — all free, none of it in the repo yet

### nflverse, verified fetchable without a key (23 September 2026)

| Release tag | File pattern | Seasons | Use |
|---|---|---|---|
| `pbp` | `play_by_play_{season}.parquet` | **1999–2026** | the warehouse. 372 columns: EPA, WP, CPOE, xpass, series, `fixed_drive_result`, `drive_ended_with_score`, spread/total line, roof, surface, temp, wind |
| `schedules` | `games.parquet` | 1999– | one row per game: result, spread, total, moneylines, `home_qb_name`/`_id` (91% populated 2018+), coaches, referee, `home_rest`/`away_rest`, `div_game`, stadium, roof, surface, temp, wind, overtime |
| `injuries` | `injuries_{season}.parquet` | **2009–** | `report_status` ∈ Out / Doubtful / Questionable, primary/secondary injury, `practice_status` |
| `depth_charts` | `depth_charts_{season}.parquet` | 2001– | `depth_team` 1/2/3 by position — who the QB1 is *this week* |
| `weekly_rosters` | `roster_weekly_{season}.parquet` | 2002– | status, years_exp, position |
| `snap_counts` | `snap_counts_{season}.parquet` | 2012– | offence/defence/ST snap % per player-game |
| `pbp_participation` | `pbp_participation_{season}.parquet` | 2016– (NGS to 2022, FTN from 2023) | `defenders_in_box`, `was_pressure`, `defense_coverage_type`, personnel groupings, players on play |
| `ftn_charting` | `ftn_charting_{season}.parquet` | 2022– | motion, play action, RPO, screen, `n_blitzers`, `n_pass_rushers`, `is_qb_fault_sack` |
| `nextgen_stats` | `ngs_passing.parquet`, `ngs_rushing`, `ngs_receiving` (all seasons in one file) | 2016– | time to throw, aggressiveness, CPOE |
| `espn_data` | `qbr_week_level.parquet`, `qbr_season_level.parquet` | 2006– | ESPN QBR per QB per week |
| `pfr_advstats` | `advstats_season_{pass,rush,rec,def}.parquet` | 2018– | pressures, blitz rate, etc. |
| `stats_team`, `stats_player` | `stats_team_week_{season}.parquet` … | 1999– | pre-aggregated weekly box |
| `contracts`, `draft_picks`, `combine`, `officials`, `trades`, `teams` | — | — | reference |

Total for play-by-play 1999–2026: ~420 MB. Cache exactly as `data/raw/cfbd`
is cached now — one fetch per season, forever.

### What is deliberately not on this list

BettingPros and FantasyPros. See `DATA_PROVIDER_REVIEW.md`. Neither adds a
team or player input, and the schedules file already carries the closing
line for the benchmark.

---

## 3. Empirical profile (nflverse, regular season)

### Outcome structure

| | 2002–10 | 2011–19 | **2020–25** |
|---|---|---|---|
| Home margin, mean | +2.48 | +2.22 | **+1.74** |
| Home margin, sd | 14.94 | 14.64 | 14.21 |
| Total, mean / sd | 42.8 / 14.2 | 45.4 / 13.9 | 45.7 / 13.8 |
| Home win % | 57.2 | 56.6 | **53.3** |

**Home advantage has halved this century** and the market prices it near 1.5.
PFF has 2020–24 home teams at .532; the 1990s were .600 and +3.6 points.

Residual against the closing line (2011–25, n=3,951): MAE 10.04, sd 13.01,
bias +0.07; totals MAE 10.43, sd 13.18. Flat across spread size (12.6–13.4)
and total size (12.6–13.9). Skew 0.10, excess kurtosis 0.38.

Home and away points: correlation −0.04 unconditionally, **0.03 given the
market**. sd of a team's points ≈ 10.

### The lattice

|margin| frequency, 2018–25: **3 → 14.4%**, 7 → 8.5%, 6 → 6.5%, 14 → 5.1%,
10 → 4.9%, 2 → 5.0%, 4 → 4.9%, 1 → 4.8%, 0 → 0.4%. Multipliers on a normal
(fit 2002–14): 0 → 0.05, 3 → 2.6–2.9, 7 → 1.9, 10 → 1.6.

The lattice is drifting. Silver (2025): canonical scores were 77% of finals
in 1920–65, 62% since 1994, projected 55%; 14% of touchdowns now yield 6 or 8;
fourth-down attempts have nearly doubled since 2017. **Refit the multipliers on
a rolling window, not once.**

### Drives and scoring events (2018–24)

11.2 drives per team-game. Outcomes: punt 35.5%, TD 22.2%, FG 14.6%, turnover
10.2%, end of half 7.3%, downs 5.0%, missed FG 2.6%, opponent TD 2.3%,
safety 0.2%.

Per game, both teams: 5.19 TD, 3.25 FG, 4.40 XP, 0.50 two-point attempts of
which 0.24 succeed (9.6% of TDs go for two). Touchdown counts are
*under*-dispersed (var/mean 0.80) — a sign of score-dependent behaviour, not
Poisson.

### Score-state dependence (the reason v2 exists)

| Score differential | 2-pt attempt share | Drive TD % | Drive FG % | Drive punt % |
|---|---|---|---|---|
| ≤ −17 | 32% | 23.3 | **6.4** | **27.9** |
| −8..−4 | 8.5% | 23.3 | 13.3 | 35.3 |
| −3..−1 | 15.6% | 20.1 | **18.1** | 33.7 |
| 0 | **1.0%** | 23.0 | 16.9 | **41.6** |
| +1..+2 | 19.0% | — | — | — |
| ≥ +17 | 3.8% | 20.3 | 13.8 | 34.5 |

Drive success is flat; decisions are not.

### Persistence, what a state model can rely on

| | H1 vs H2 same season | year over year |
|---|---|---|
| Offensive EPA/play | 0.44–0.69 (0.69 in 2024) | — |
| Defensive EPA/play allowed | 0.21–0.55, mostly ~0.25 | — |
| Offensive TD/drive | 0.32–0.78 | 0.30–0.58 |
| Defensive TD/drive allowed | 0.05–0.44 | 0.24–0.45 (one season −0.11) |
| FG/drive | ~0 | — |
| Drives/game | 0.15–0.49 | — |

**Offence is roughly twice as persistent as defence.** Shrink the defensive
state harder and let the offensive one move faster.

### How fast in-season data overtakes the prior

Corr of this game's net EPA with last season's: 0.27 in weeks 1–4, then
0.14–0.19. With season-to-date: 0.19 → 0.32 by week 14. Implied share of
weight on season-to-date: ~20% after 1 game, ~40% after 2, ~70% after 4,
~90% after 6. **Prior half-life ≈ 3 games.** (n=192 per bucket; noisy.)

---

## 4. Factors, with measured or cited sizes

Ordered by how much they matter. Only the first four are in v1.

| # | Factor | Size | Source | In v1? |
|---|---|---|---|---|
| 1 | **Team strength, off/def, dynamic** | the model | §3 | yes |
| 2 | **Starting QB** | **−3.3 points** when the starter changes week to week (n=430, controlling for season-to-date); the market moves −3.7. Literature: 3–7, elite 6+ | own; oddsmaker surveys | yes — via `home_qb_id` and depth charts |
| 3 | **Home field** | **+1.7** now; use a fitted, slowly-varying value, not 3 | own; PFF; Frontiers | yes |
| 4 | **Between-season regression** | AR ≈ 0.67, innovation sd ≈ 4.3 pts | Glickman & Stern | yes |
| 5 | Preseason roster/QB change | last-season EPA already gets 0.36 corr at week 1 vs market 0.33; the market's entire early edge is 0.14 MAE | own | v1.1: QB identity only |
| 6 | Rest / bye | +0.31 post-2011, not significant; Thursday mini-bye +0.48 ns; the 2011 CBA killed it | Frontiers 2024 | no |
| 7 | Divisional game | none (sd 14.29 vs 14.34) | own | no |
| 8 | Dome / roof | none on margin; possibly on total | own | total model only |
| 9 | Weather (temp, wind) | small, total-only; 81% of outdoor games have it | schedules | total model, v1.1 |
| 10 | Travel / time zone | FiveThirtyEight uses ~4 Elo per 1,000 miles (≈0.16 pts); with HFA halved, likely smaller | 538 | no |
| 11 | Non-QB injuries | via snap counts / injury report; effect diffuse | injuries, snap_counts | v2 |
| 12 | Referee, surface, primetime | unmeasured here; low prior | schedules | no |

**The quarterback deserves its own state.** FiveThirtyEight and nfelo both
model the QB separately and add it back. The plan: an offensive team state
*excluding* the QB (line, receivers, scheme — persistent) plus a QB state
carried by the *player* across teams and seasons, built from `qb_epa` /
CPOE per dropback with heavy shrinkage. When `home_qb_id` changes, the
team's expected margin moves by the difference in QB states, not by a flat
−3.3. The flat number is the fallback when the backup has no history.

---

## 5. Model specification, v1

**State.** For each team *i* and week *t*: `off_it`, `def_it` (points above
average per game, net of QB), and for each quarterback *q*: `qb_qt`.

**Process.**
- Within season: `off_{i,t+1} = off_it + ε`, `ε ~ N(0, σ²_off)`; same for def
  with a smaller σ. Fitted; expect off:def process sd ≈ 2:1 from §3.
- Between seasons: `off_{i,1} = 0.67·off_{i,last} + η`, `η ~ N(0, 4.3²)`.
- QB: slow random walk within season, small shrinkage between.

**Observation.** Game *g* between home *h* and away *a*:
`margin_g ~ N(μ_g, σ²_m)`, `μ_g = (off_h + qb_h − def_a) − (off_a + qb_a − def_h) + HFA_t`,
with `σ_m` fitted (expect 12.7–13.0). Update by Kalman filter; the gain, not a
K, decides how far a result moves the state. Observation noise can be reduced
by feeding `net EPA` for the game rather than the raw margin — EPA is a less
noisy read of the same performance (this is the nfelo/nflfastR insight and
worth testing as a second observation channel).

**Total — built, `reports/nfl_total.md`.** The quarterback state's
implied total (its home points plus its away points), recalibrated
walk-forward on the training seasons' own forecasts - the sum of two
noisy strengths over-disperses, slope 0.52–0.71 - plus the one game-level
term that measured as real on its residual: the wind, −0.29 to −0.38
points per mph, with a dome at zero wind. Once the wind is in, the dome
itself, temperature, pace, rest and a division game all measure at
|t| < 1 and are out. Forecast sd 13.2–13.9 against the market's 13.0.

| total, regular 2023–25 | CRPS | MAE |
|---|---|---|
| naive | 7.61 | 10.68 |
| state total, raw | 7.48 | 10.56 |
| **total (calibrated)** | **7.36** | **10.39** |
| market | 7.24 | 10.12 |

Residual correlation between margin and total measured at 0.01, so the
joint is the product, as in college.

**Distribution — built.** The margin (state mean and sd through the
key-number lattice) and the total (discretised normal) meet on a **60×60
grid** over (home, away) points (`atlas/models/joint.py`), reweighted by
the points lattice fitted on the training seasons' own grids. Passing the
margin through the grid costs nothing (7.351 either way). The points
lattice is worth 0.26 nats on the exact score (7.15 → 6.89), doubles the
top-ten hit rate (4.0% → 8.8%) and moves the actual score's median rank
from 312 to 231. What it fitted for 2026 is Silver's drift in one row:
**3, 6, 10, 13, 17 and 20 are elevated (2.2, 2.1, 2.8, 1.6, 1.7, 2.1×)
while 14, 21 and 28 are not (1.0, 0.8, 0.8×)** - the multiples of seven
are no longer where NFL finals land.

**Output per game — built.** The grid's mean to one decimal - 24.6–21.3,
total 45.9 - never a rounded integer, with P(home), the total's 80% range
and the most probable exact score (1.4% on average). P(home) from the grid
is within 0.03 of the observed rate in every spread bucket to 10 points,
where the NFL lives, and 0.06 low on the 79 games past 10, where the
market is 0.04 low too.

**Card — built, step 6.** `atlas/models/nfl_projection.py` runs steps 3–5
forward to today - the quarterback state through every game already
played, the calibrated total, the grid with its points lattice - one row
per scheduled game, keyed by ESPN's event id (now staged on the NFL games
table) so the odds poll, the game metadata and the card all join on it.
The weekly refresh publishes both sports to `tracking/projections.csv`
and both records to `tracking/calibration.csv`, each row carrying its
sport, and an NFL failure never takes the college publish down. The card
is the college card: the same renderer, the same tiers, the same audited
copy, with no team-page links because the NFL has no team pages yet. The
grade is fitted per sport from that sport's own walk-forward record
(margin market; the NFL curve is `gap(d) = −0.025·d^1.09`, r = 0.72, on
1,725 games). Each poll now captures the NFL scoreboard beside college,
logos are cached per sport because ESPN numbers NFL and college teams
from one, and the heavy job ingests nflverse and builds the NFL warehouse
before the model step. `nfl.html` is the NFL board, grouped by day. The
site audit passes on every page with the NFL cards counted as cards.

---

## 6. Validation — NFL specifics

Foundation §6 applies. NFL additions:

- **Fit 2011–2019, tune 2020–2022, report 2023–2025.** Never report a season
  used for tuning.
- **Three-season rolling CRPS** with bootstrap intervals; one season cannot
  resolve <0.15.
- **The QB test.** Score the model separately on games where `home_qb_id` or
  `away_qb_id` differs from the previous week (10.7% of team-games). If the QB
  state is working, the model's residual there should be no worse than
  elsewhere. Today the market's residual on those games is −0.78 — it slightly
  under-adjusts.
- **Reliability at the extremes.** With parity, few games have P(home) > 80%;
  check the 65–80% bins are honest, because that is where the NFL lives.

### Success criteria

Measured by `make nfl-benchmarks` (`reports/nfl_benchmarks.md`), regular
season 2023–2025, 816 games, every reference fitted only on the seasons
before the one it forecasts (from 2011), the same lattice applied to all:

| Score | Naive | Elo (538 params) | Adjusted EPA | **Target v1** | Market |
|---|---|---|---|---|---|
| CRPS, margin | 8.02 | 7.37 | 7.39 | **< 7.37** | 7.08 |
| Brier, home win | 0.249 | 0.223 | 0.224 | **< 0.223** | 0.211 |
| MAE, margin | 11.10 | 10.24 | 10.31 | **< 10.24** | 9.74 |
| ECE, home win | 0.019 | 0.042 | 0.041 | **< 0.03** | 0.049 |

The estimates in the first draft of this table (naive ~7.9, Elo ~7.4,
market 7.10) were within 0.1 of the measurement. Two things the
measurement added:

- **The quarterback test has a number now.** On regular-season games where
  a side's quarterback of record differs from its previous game's (385 of
  1,647 from 2020), Elo's CRPS is 7.63 against 7.25 elsewhere, a gap of
  **0.38**; adjusted EPA's is 0.38 too; the market's is **0.05** (7.11
  against 7.06). That 0.33 is what the QB state (step 4) is for.
- **Elo is strongest early.** Weeks 1–3: Elo 6.93 to the market's 6.75;
  weeks 13+: 7.38 to 7.04. The gap to the market opens as the season goes,
  the opposite of college, because the NFL's prior (last season, reverted)
  is good and its in-season read is noisy at 17 games.

**v1 is done when it beats Elo on every row out of sample.** Matching the
market is v2's ambition, not v1's requirement.

---

## 7. Build order

| Step | Work | Output |
|---|---|---|
| 0 | `atlas/sources/nflverse.py`: fetch + cache pbp, schedules, injuries, depth charts, snap counts, rosters (`make nfl-ingest`) | **done** — 80 files, 114 MB, 2011–2026; pbp trimmed to 145 columns |
| 1 | `atlas/staging/nfl/`: games, team-game efficiency and drives, QB of record and QB1, injuries, opponent-adjusted and point-in-time features through the college modules unchanged (`make nfl-warehouse`) | **done** — `data/warehouse/nfl.duckdb`, 4,368 games (4,128 completed), 122 columns; reproduces §3 exactly |
| 2 | Benchmarks: naive, Elo, adjusted EPA, market-in-lattice, plus the quarterback test (`atlas/models/nfl_benchmarks.py`, `make nfl-benchmarks`) | **done** — `reports/nfl_benchmarks.md`; 2023–25 regular season: naive 8.02, Elo 7.37, market 7.08 CRPS |
| 3 | Kalman state model, off/def, no QB, carried across seasons (`atlas/models/nfl_state.py`, `make nfl-state`) | **done** — ties Elo (2023–25: CRPS 7.375 to 7.372) |
| 4 | Add QB state and HFA fit | **done — beats Elo on every row** (CRPS 7.351, Brier 0.222, MAE 10.20, ECE 0.027); the QB test gap did not close, and the report says why |
| 5 | Total model + joint grid (`atlas/models/nfl_total.py`, `make nfl-total`) | **done** — total CRPS 7.36 (naive 7.61, market 7.24); 60×60 grid with the points lattice; P(home) within 0.03 of observed where the NFL lives |
| 6 | Wire into the card and the grade (`atlas/models/nfl_projection.py`; the live and site layers take a sport) | **done** — `nfl.html` is a board; 17 NFL cards this week; audit passes |
| 7 | v2: state-dependent drive simulation, only if step 5's exact-score log-score is measurably short of the benchmark | |

Steps 0–1 are done, in a session. What the build established:

- **The frame reproduces §3 to the decimal.** Home margin +2.22 / sd 14.64
  (2011–19) and +1.74 / 14.21 (2020–25); residual against the closing line
  MAE 10.04, sd 13.01, bias +0.07 on 3,951 games. The same
  `atlas/models` code that scores college scores this.
- **Conventions match college**, so nothing in the model layer forks:
  `closing_spread` is the book's home line (negative when the home side is
  favoured; nflverse's `spread_line` is the opposite sign and is negated),
  `season_type` is `regular`/`postseason`, kickoffs are UTC, team ids are
  integers that follow a franchise through a relocation (STL→LA, SD→LAC,
  OAK→LV).
- **Two quarterback columns, deliberately.** `home_qb_id` is the
  quarterback of record from the schedules file - who did start, knowable
  at kickoff at the earliest - and `home_qb1_id` is the depth chart's QB1
  for the week, which was knowable before it. They agree on 88% of
  team-games from 2018; the other 12% are the QB test's material and the
  QB state's job. nflverse changed the depth-chart feed in 2025 to daily
  snapshots with no week; those are mapped to a game by the latest
  snapshot before its kickoff.
- **Elo is code, not a column.** `atlas/models/elo.py` is a walk-forward
  Elo with FiveThirtyEight's parameters (K 20, home field 48, a third of
  the way back to 1505 each season, margin-of-victory multiplier) that
  attaches `elo_diff` in points to any game frame; step 2 uses it.
- Coverage: adjusted and point-in-time metrics 99.6%, QB1 99.4%, injury
  counts 94%, wind 64% (outdoor games only, as expected).

Steps 3 and 4 are done (`reports/nfl_state.md`). What they established:

- **The state alone ties Elo.** Regular season 2023–25: CRPS 7.375 against
  Elo's 7.372, Brier 0.2229 to 0.2227, MAE 10.24 to 10.24. The tuned
  hyperparameters sit at the strong-regression end of the grid: `phi` 0.5
  to 0.67 between seasons, innovation 5, process noise 0.25 to 0.5 a week,
  observation sd 8.5 on a team's points. An NFL team is mostly last year's
  team, shrunk hard, plus a season's worth of noisy evidence.
- **The quarterback state and the fitted home advantage clear the bar.**
  `state_qb` beats Elo on every row of the reporting window: CRPS 7.351,
  Brier 0.2216, MAE 10.20, ECE 0.027 (Elo 0.042). Its gains are in weeks
  1–3 (6.86 to Elo's 6.93) and in calibration. The fitted home advantage
  drifted from 0.6 in 2020 to 2.1 in 2025, against the training means'
  2.2: the filter agrees with §3 that home field fell and has come part of
  the way back.
- **The quarterback test did not close, and the reason is the data.** On
  the 385 games where a side changed quarterback, `state_qb` scores 7.61
  against 7.25 elsewhere, the same 0.37 gap as Elo. The forecast uses the
  depth chart's QB1 for the week, and on those games the depth chart named
  the new starter only **37% of the time** (home) and 42% (away), against
  96% agreement with the starter in games with no change: most changes are
  in-week injuries and benchings the weekly chart never carried. The model
  can only price a change it is told about. v1.1 is to stage the QB2 from
  the depth chart and switch to it when the injury report lists the QB1 as
  Out or Doubtful (`home_qb1_out` is already in the frame), and to give a
  new quarterback a prior from his own `qb_epa`/CPOE per dropback rather
  than a flat number; the tuned flat prior came out at 0 to −2, tight.

---

## 8. Risks, stated plainly

- **The NFL may not have room.** The market's edge over last-season EPA is
  0.14 MAE early and the residual sd is at the noise floor. It is possible v1
  lands between Elo and the market and stays there. That is a publishable
  result and an honest product — "here is an independent number and here is
  exactly how good it is" — but it is not "we beat Vegas," and the product
  copy must never imply it.
- **Small samples make every fitted parameter uncertain.** Three seasons of
  reporting is the minimum before any claim about the model's quality.
- **The lattice is moving.** Rule changes (kickoff, two-point, fourth-down
  culture) are reshaping score frequencies year by year. A multiplier table
  fit on 2002–14 is already stale; the rolling refit is mandatory.
- **QB data is 91% complete.** The 9% of games with no listed starter need a
  fallback (previous week's starter), and preseason weeks have none.
