# Atlas — NCAAF Model Plan

Inherits `MODEL_FOUNDATION.md`. This document covers only what is specific to
college football: the data (most of it already here), the empirical profile,
the factors and their measured sizes, the model specification, and the order
to build it in.

**Status: the data is here; the model is the wrong shape.** The warehouse has
nine seasons of play-by-play, opponent-adjusted efficiency, SP+, FPI, Elo,
talent, recruiting, returning production, rest, travel and weather. The
current model uses ten features, predicts two scalars, and anchors to the
market. This plan replaces the model and keeps the warehouse.

---

## 1. Why college is the easier of the two — and where it is harder

**Easier.** ~800 FBS-vs-FBS games a season, four times the NFL. Team strength
spans 50+ points, so a model has room to be right. The warehouse, staging,
opponent adjustment and point-in-time machinery already exist and are tested.

**Harder, in three specific ways.**

1. **Strength heterogeneity dominates everything.** Simulating independent
   scoring events at league-average rates gives a margin sd of 16.1; the real
   sd is 24.8. That gap *is* the mismatch between teams. In the NFL the same
   experiment over-disperses. So the college model's first job is getting
   team strength right; the NFL model's first job is getting the noise right.
2. **The schedule is sparse and unbalanced.** Teams play 12 games against a
   handful of opponents, mostly in-conference. Glickman & Stern note that in
   "a larger less-connected league (e.g., NCAA college football)" the standard
   error of strength differences across divisions is much larger. Opponent
   adjustment is not optional here; it is the model.
3. **Early-season priors matter more and are noisier.** A third of the roster
   turns over every year, coaches change, and the portal reshuffles. The
   preseason prior carries the first three games almost entirely.

---

## 2. Data

### Already in the repository

| Source | What | Coverage on the FBS-vs-FBS modelling frame |
|---|---|---|
| cfbfastR pbp, 2018–2026 | 48 columns: EPA, success, down/distance, `drive_id`, `drive_pts`, `drive_start_yards_to_goal`, `TimeSecsRem`, `score_diff`, play type | full |
| sportsdataverse schedules, team_info, odds | game, division, neutral, closing spread/total, pregame Elo | full |
| ESPN FPI, predictor | prior-season FPI | ~100% |
| CFBD (cached, free tier) | SP+ (off/def splits), talent, recruiting, returning production, coaches, rankings | 98–100% |
| Meteostat | temp, wind, precip, humidity, station distance | 81–94% |
| Derived | rest days, travel distance, dome, opponent-adjusted efficiency (`adj_*`), QB of record | 93–100% |

### Free CFBD endpoints not yet ingested (verified against the OpenAPI spec)

`/drives`, `/plays`, `/player/portal` (**transfer portal**), `/coaches`,
`/ratings/elo` (weekly), `/ratings/srs`, `/ppa/games`, `/metrics/wp/pregame`,
`/stats/game/advanced`, `/stats/season/advanced`, `/venues`, `/roster`.

**The only paid endpoint that matters is `/games/weather`**, and Meteostat
already covers it. Opponent-adjusted metrics are also paid — Atlas computes
its own.

Also hosted free: `sportsdataverse-data` → `espn_cfb_drives/drives_{season}.parquet`.

### The FBS filter — verified, and now pinned

**Correction to the first version of this plan.** It said the pipeline was
filtering FBS-vs-FBS "by accident." It is not. `atlas/research/dataset.QUERY`
reads `research_games WHERE home_division = 'fbs' AND away_division = 'fbs'`,
deliberately, and `research_sample()` yields 5,778 such games for 2018–2025.
The unfiltered 28% figure came from an ad-hoc query in the research notes, not
from the pipeline, and so did the 0.90 drive-persistence artifact. Both were
analysis mistakes; the warehouse was right.

What is true and matters: `games` holds **7,588 FBS, 4,976 FCS, 4,890 D-III
and 4,445 D-II games**, and the play-by-play from 2022 on covers ~300 teams.
Any aggregate taken *outside* the research query is wrong without the filter,
and the efficiency staging computes team-game rows for every division. That is
correct — the opponent adjustment needs FCS opponents as actors, each shrunk
toward the league prior by the ridge, which is the "pooled FCS effect" already
in place — but it means **nothing downstream may aggregate from staging
without going through the research frame.** `tests/test_models.py` pins the
frame to FBS-vs-FBS so a future query cannot drift.

Every number in this plan is FBS-vs-FBS.

---

## 3. Empirical profile (FBS-vs-FBS unless noted)

### Outcome structure

| | 2018–19 | 2020–22 | **2023–25** |
|---|---|---|---|
| Home margin, mean (all div.) | +7.07 | +4.49 | **+4.60** |
| Home win % | 62.3 | 56.9 | **57.2** |
| Total, mean / sd | 56.2 / 18.5 | 54.0 / 17.9 | 53.1 / 17.6 |

**Home advantage dropped by a third in 2020 and never came back.** Wharton
finds ~2.8 controlled; a 2023 FBS-vs-FBS figure is +4.1 / 63.6%. Fit it,
don't assume it.

Residual against the closing line: MAE 12.25, sd 15.52, bias +0.23 (all games
with a line); FBS-vs-FBS through 2020: sd margin 15.72, total 16.60, residual
correlation 0.029. Flat across spread size (14.8–16.0, even for 28+ point
favourites) and across weeks (15.2–15.9; only slightly higher in weeks 1–4 and
bowls). Skew 0.00, excess kurtosis 0.17 — closer to normal than the NFL.

Home and away points correlate at −0.17 unconditionally (mismatches), **0.05
given the market**. A team's points have sd ≈ 13.8.

### The lattice

|margin| 2018–25: **3 → 8.1%**, 7 → 7.3%, 14 → 4.1%, 10 → 3.8%, 1 → 3.2%,
4 → 3.2%, 6 → 2.9%, 0 → 0.2%. Multipliers on a normal (fit ≤2020):
0 → 0, **3 → 2.7**, **7 → 2.4**, 14 → 1.7, 10 → 1.3. The CFB spread paper
finds 3 → 2.7 and 7 → 2.1 on its own data — a close match. Less peaked than
the NFL at 3, more at 14: college has more two-score games.

### Drives and scoring (all divisions; FBS-only figures in the persistence table)

12.7 drives per team-game. Drive points: 0 → 61.6%, 7 → 24.5%, 3 → 9.4%,
6 → 1.6%, 8 → 0.7%, defensive TD (−7) → 1.4%. Per team-game: 2.49 TD,
0.88 FG. FBS-only TD counts are near-Poisson (var/mean 1.13).

### Score-state dependence

| Score differential at drive start | Drive TD % | Drive FG % |
|---|---|---|
| ≤ −17 | 24.5 | **5.9** |
| 0 | 26.8 | **11.9** |
| ≥ +17 | 27.7 | 6.8 |

Fourth quarter, fourth down inside the 35: **go for it 82%** when trailing by
9+, kick 69–70% when up 0–7, kick 60% when up 8+. Same shape as the NFL; same
implication for a v2 simulation.

**Garbage time is 11.1% of scrimmage plays** at Connelly's thresholds (43 /
37 / 27 / 21 by quarter). The staging layer already excludes it from every
efficiency input, at Atlas's own, slightly stricter thresholds
(`config.GARBAGE_TIME_MARGIN` = 38 / 28 / 22 / 16; overtime never). Pinned by
test.

### Persistence (FBS-vs-FBS)

| | wk ≤6 vs later, same season | year over year |
|---|---|---|
| Offensive EPA/play (non-garbage) | 0.38–0.58 | — |
| Offensive TD/drive | 0.44–0.59 | 0.27–0.54 |
| Defensive TD/drive allowed | 0.33–0.55 | 0.40–0.52 |
| FG/drive | 0.05–0.32 | — |

Defence persists *more* in college than in the NFL — recruiting depth and
scheme continuity — so the off:def process-noise ratio is closer to 1:1 here.

### Preseason priors — what actually predicts week 1

Correlation of each pre-game quantity with the actual margin, FBS-vs-FBS:

| | weeks 1–2 | weeks 3–4 | weeks 5–8 | weeks 9–12 | weeks 13–16 |
|---|---|---|---|---|---|
| **Closing spread** | **0.708** | 0.708 | 0.620 | 0.648 | 0.658 |
| Prior-season FPI | **0.625** | 0.635 | 0.478 | 0.448 | 0.424 |
| Prior-season SP+ | 0.604 | 0.617 | 0.474 | 0.455 | 0.425 |
| Point-in-time Elo | 0.590 | 0.647 | 0.571 | 0.609 | **0.634** |
| Recruiting rank | 0.558 | 0.507 | 0.302 | 0.301 | 0.250 |
| Talent composite | 0.532 | 0.508 | 0.287 | 0.293 | 0.280 |
| Atlas adj. net EPA (point-in-time) | 0.539 | 0.577 | 0.526 | 0.594 | 0.603 |
| **Returning production, alone** | **0.106** | 0.100 | 0.125 | 0.109 | 0.134 |

Five things to take from that table.

1. **The gap to the market at week 1 is 0.71 vs 0.63.** Real but not vast.
2. **Prior-season ratings decay fast** — SP+ and FPI lose a third of their
   correlation by mid-season. They are a prior, not a feature.
3. **Elo, a plain dynamic rating, is the best single predictor from week 9
   on.** It is the floor the state model must beat, and by a margin.
4. **Atlas's own adjusted EPA is already a respectable in-season signal** (0.60
   late) — the current model's problem was never its efficiency inputs.
5. **Returning production is useless alone and essential as a modifier.**
   Connelly's SP+ projection is "two-thirds last year's rating adjusted by
   returning production"; the top-10 returning teams improve by +1.0 wins /
   +6.4 SP+ spots on average, the bottom-15 (<36%) regress 10 times in 15. The
   right use is `prior = f(last SP+, returning production, recruiting, transfers)`,
   not a column in a regression.

### How fast in-season data overtakes the prior

Implied share of weight on season-to-date adjusted net EPA: 8% after 1 game,
18% after 2, **50% after 3**, 67% after 5, ~100% after 8. Half-life ≈ 3
games, slightly slower than the NFL because the prior (0.25 corr with this
game's EPA) is weaker than a good preseason projection would be.

---

## 4. Factors, with measured or cited sizes

| # | Factor | Size / evidence | In v1? |
|---|---|---|---|
| 1 | **Opponent-adjusted team strength, off/def, dynamic** | the model; `adj_*` exists | yes |
| 2 | **Preseason prior from last SP+/FPI × returning production × recruiting/talent** | 0.60–0.63 corr at week 1; SP+ recipe | yes |
| 3 | **Home field** | +4.6 now, +7.1 in 2018–19; fit per season | yes |
| 4 | **Strength-of-schedule / connectivity** | via opponent adjustment; FCS games as one effect | yes |
| 5 | Garbage-time exclusion | 11.1% of plays; already in staging | yes (in place) |
| 6 | Between-season regression | AR ≈ 0.67 by analogy; **fit it** — college turnover is higher | yes |
| 7 | **Coaching change** | corr −0.56 between prior overachievement vs 20-yr program mean and subsequent SP+ change; i.e. regress a new-coach team toward its *program* mean, not the league mean | v1.1 |
| 8 | **Transfer portal** | unquantified in the literature beyond "large"; CFBD `/player/portal` is free; use as a returning-production adjustment | v1.1 |
| 9 | QB | `qb_of_record` exists; effect unmeasured here; college backups are further from starters than NFL ones | v1.1 |
| 10 | Bowl opt-outs / motivation | lines move 3–9 points on opt-outs; **exclude bowls from fitting**, flag on the card | v1: exclude |
| 11 | Rest, travel | rest_diff, travel_distance in warehouse; expect small | total model / v2 |
| 12 | Weather | Meteostat; total-only | total model |
| 13 | Pace | `adj_pace`, plays/game; total-only | total model |
| 14 | Week-1 / early-season variance | residual sd only ~0.5 higher; handled by the prior's uncertainty, not a separate term | via Kalman |

---

## 5. Model specification, v1

**Frame.** FBS-vs-FBS regular season, 2018–2025 fitted walk-forward; bowls
scored but never fitted. Garbage time removed from every efficiency input.

**State.** For each FBS team *i* and week *t*: `off_it`, `def_it` in points
per game above FBS average, opponent-adjusted.

**Preseason prior (week 1) — built, `reports/ncaaf_prior.md`.**
`net_i` is a linear combination of last season's SP+, last season's FPI, the
talent composite, recruiting rank and returning production, standardised and
fitted **directly on training games** (margin on the home-minus-away feature
difference plus home advantage), walk-forward. Off and def come from one
stacked regression on points scored with a scorer block and an opponent
block. A first version regressed on the ridge-shrunk least-squares season
rating and used the compressed prediction as a margin; it needed a slope of
1.21 to match real margins and lost 0.6 MAE to the direct fit. The game is
the target.

What the recipe learned (2025 window, points of margin per sd): SP+ +4.19,
FPI +3.41, talent +2.26, returning production +1.68, recruiting −1.38;
home advantage +2.52; game residual sd 17.40, which is the state model's
starting uncertainty. Coaching change and the portal are v1.1 (factors 7–8).

Scored where a prior is the whole forecast, regular season 2021–2025,
walk-forward, same lattice and scoring as the benchmarks:

| weeks 1–4 | CRPS | Brier | MAE | ECE | corr, wk 1 |
|---|---|---|---|---|---|
| naive | 12.65 | 0.234 | 17.63 | 0.047 | — |
| prior FPI | 9.78 | 0.179 | 13.77 | 0.032 | 0.623 |
| prior SP+ | 9.89 | 0.181 | 13.99 | 0.036 | — |
| Elo | 9.95 | 0.178 | 13.92 | 0.034 | — |
| **prior (this)** | **9.51** | **0.175** | **13.47** | **0.017** | **0.671** |
| market | 8.54 | 0.158 | 12.10 | 0.026 | 0.738 |

Weeks 1–2 alone: 9.25 against FPI's 9.66. It wins four seasons of five and
loses 2021 by 0.03 CRPS — the one season whose training window is a third
COVID, when every preseason feature's correlation with the eventual rating
collapsed (SP+ 0.56, talent 0.31, recruiting −0.28 against ~0.73, ~0.62,
~−0.62 in every other year). It is the best-calibrated of the six.

**Process.** Within season `off_{i,t+1} = off_it + ε`, `ε ~ N(0, σ²_off)`,
`σ_off ≈ σ_def` (college defence persists). Fitted so the prior's half-life
comes out near three games.

**Observation.** `margin_g ~ N(μ_g, σ²_m)`,
`μ_g = (off_h − def_a) − (off_a − def_h) + HFA_t·(1 − neutral)`, `σ_m` fitted
(expect 15.5–15.7). Kalman update; also observe game-level adjusted net EPA as
a second, lower-noise channel. FBS-vs-FCS games update the FBS team against a
single pooled FCS strength.

**Total.** `(off_h + off_a) − (def_h + def_a) + base_t + pace + weather`.

**Distribution.** Bivariate normal (margin, total), fitted sds, correlation
≈ 0.05, discretised, margin reweighted by the key-number multipliers above,
refit on a rolling window.

**Output.** An 80×80 grid over (home, away) points. The headline projection is
its mean to one decimal — 31.7–24.2, total 55.9 — never a rounded integer.

---

## 6. Validation — college specifics

Foundation §6 applies. Additions:

- **Fit 2018–2021, tune 2022–2023, report 2024–2025.** Bowls are always
  out-of-fit.
- **Report by week bucket.** Weeks 1–3 test the prior; 9+ test the state.
  A model that beats Elo late but loses to prior-season FPI early has a prior
  problem, not a model problem, and the table above says which.
- **Report by spread bucket.** With 28+ point favourites, check the reliability
  of P(home) > 95% — the lattice and tails matter most there.
- **The connectivity test.** Score inter-conference and non-conference games
  separately. If those are worse than in-conference games, opponent
  adjustment is under-regularised.

### Success criteria

Measured by `make ncaaf-benchmarks` (`reports/ncaaf_benchmarks.md`):
regular season 2021–2025, 3,730 games, every reference fitted only on the
seasons before the one it forecasts, the same lattice applied to all.

| Score | Naive | Prior FPI | Prior SP+ | Elo | Atlas adj. EPA (today) | **Target v1** | Market |
|---|---|---|---|---|---|---|---|
| CRPS, margin | 11.44 | 9.93 | 9.93 | **9.23** | 9.37 | **≤ 9.00** | 8.61 |
| Brier, home win | 0.242 | 0.207 | 0.208 | **0.188** | 0.192 | **≤ 0.184** | 0.176 |
| MAE, margin | 15.91 | 13.98 | 14.04 | **13.04** | 13.25 | **≤ 12.8** | 12.12 |
| ECE, home win | 0.001 | 0.018 | 0.023 | 0.015 | 0.017 | **< 0.02** | 0.025 |

Two things the measured table says that the estimated one could not.

**Elo and the priors trade places across the season.** In weeks 1–2 Elo scores
10.18 CRPS and prior-season FPI 9.66 — the prior wins; from week 5 on Elo is
8.86–9.10 and FPI 9.47–10.73 — the state wins. A candidate has to beat *both*
in *their* weeks, which is the whole reason the plan has a prior layer and a
state layer rather than one or the other.

**Atlas's current point-in-time adjusted EPA is already within 0.14 CRPS of
Elo** and clear of both prior-season ratings. The inputs were never the
problem; the model shape was.

Naive's ECE of 0.001 is not a virtue — a constant forecast is trivially
calibrated. It is there to show ECE must be read beside Brier.

**v1 is done when it beats Elo on every row, out of sample, in every week
bucket**, and the ECE row holds.

---

## 7. Build order

| Step | Work | Output |
|---|---|---|
| 0 | Pin the frame: tests that the research frame is FBS-vs-FBS and that staging excludes garbage time. Both were already true; the tests stop them drifting | `tests/test_models.py` |
| 1 | Benchmarks on that frame: naive, prior-FPI, prior-SP+, Elo, Atlas's own adjusted EPA, market-in-lattice, walk-forward 2021–25 | `reports/ncaaf_benchmarks.md` via `make ncaaf-benchmarks` |
| 2 | Preseason prior: the SP+ recipe refit on our data, directly on games (`atlas/models/ncaaf_prior.py`, `make ncaaf-prior`) | **done — week-1 corr 0.671** (bar 0.62; FPI alone 0.623) |
| 3 | Kalman state model, off/def, opponent-adjusted, no extras. Walk-forward 2018–25 | beats Elo? by week bucket |
| 4 | Coaching-change and portal adjustments to the prior; QB of record | week 1–3 improvement |
| 5 | Total model + bivariate lattice distribution | 80×80 grid; reliability by spread bucket |
| 6 | Wire into the card (model number second slot, market open/move/now first, drivers third) and the grade | language audit passes |
| 7 | v2 drive simulation, if warranted | |

Steps 0–2 are done. Step 3 — the Kalman state, initialised from this prior
with variance 17.4² on the game and ~10² on a team — is the substance.

---

## 8. Risks

- **The prior may be the whole game early.** If weeks 1–3 cannot beat
  prior-season FPI, the honest product for September is "our prior says X;
  the market says Y; we have two games of evidence" — and the card should say
  exactly that.
- **Coverage drift.** SP+ / talent / returning production are 98–100% on
  FBS-vs-FBS but lower on the raw frame; the manifest's `cfbd_enrichment`
  block now reports coverage per dataset, so a drop is visible.
- **The portal is not in the historical priors.** Returning-production
  numbers before ~2022 predate the portal's current scale; the prior recipe
  fitted on 2018–21 may under-weight roster churn. Refit yearly.
- **Bowls and opt-outs.** Excluded from fitting; the card must carry a flag,
  because a reader looking at a bowl card is looking at a different game.
- **Two-thirds of the warehouse is not FBS.** Anything that aggregates
  from staging without going through the research frame is wrong; it bit the
  research for this plan once. The frame is pinned; the habit still has to be
  kept.
