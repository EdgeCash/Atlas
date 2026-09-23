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

**Total.** Separate, additive: `total_g = (off_h + off_a) − (def_h + def_a) + base_t + roof/weather`.

**Distribution.** Bivariate normal on (margin, total) with fitted sds and
residual correlation ≈ 0.03, discretised to integer (home, away), margin
reweighted by rolling key-number multipliers. Overtime is absorbed by the
lattice fit (ties are 0.4%).

**Output per game.** A 60×60 probability grid over (home, away) points, plus
its functionals.

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

| Score | Naive | Elo (538 params) | **Target v1** | Market |
|---|---|---|---|---|
| CRPS, margin | ~7.9 | ~7.4 (est.) | **≤ 7.35** | 7.10 |
| Brier, home win | 0.249 | ~0.225 (est.) | **≤ 0.220** | 0.213 |
| MAE, margin | 10.9 | ~10.6 | **≤ 10.5** | 10.04 |
| ECE, home win | — | — | **< 0.02** | ~0.01 |

Elo's numbers are estimates from the literature (Prediction Tracker: best
systems ≈ 10.5 MAE); the first thing phase 3 does is measure them on our data.
**v1 is done when it beats Elo on every row out of sample.** Matching the
market is v2's ambition, not v1's requirement.

---

## 7. Build order

| Step | Work | Output |
|---|---|---|
| 0 | `atlas/sources/nflverse.py`: fetch + cache pbp, schedules, injuries, depth charts, snap counts. Mirror `cfbd.py`'s `_cached()` | `data/raw/nfl/` |
| 1 | `atlas/staging/nfl/`: team-game table (EPA off/def, drives, drive results, QB id, rest, roof, weather, market), point-in-time | `data/warehouse/nfl.duckdb` |
| 2 | Benchmarks: naive, Elo, market-in-lattice. Reproduce §3 and foundation §2 exactly | `reports/nfl_benchmarks.md` |
| 3 | Kalman state model, off/def, no QB. Walk-forward 2011–25 | beats naive and Elo? |
| 4 | Add QB state and HFA fit | the QB test |
| 5 | Total model + bivariate lattice distribution | full 60×60 grid; reliability |
| 6 | Wire into the card and the grade | `nfl.html` becomes a board |
| 7 | v2: state-dependent drive simulation, only if step 5's exact-score log-score is measurably short of the benchmark | |

Steps 0–2 are mechanical and should take days, not weeks. Step 3 is where
the work is.

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
