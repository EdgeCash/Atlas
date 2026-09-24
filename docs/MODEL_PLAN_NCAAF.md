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
| 7 | **Coaching change** | literature: corr −0.56 between overachievement vs the 20-yr programme mean and the next SP+ change. Measured here on the prior's out-of-sample residual: every team under-regresses toward its programme mean (t −3.9) and a new coach's team regresses harder (interaction t −2.6 to −4.2) | **done, step 4** |
| 8 | **Transfer portal** | measured: quality-weighted *incoming* transfers explain the prior's out-of-sample residual (t 2.8); outgoing ones add nothing beside returning production. Staged from CFBD's portal file, 2021 on; +1.19 pts/sd in the prior; weeks 1–4 CRPS 9.47 → 9.44, weeks 1–2 9.25 → 9.16 | **done, v1.2** |
| 9 | QB | measured, retrospectively: a change of quarterback of record moves the state's residual **−3.2 points** (t −6.4) on 20% of team-games, the NFL's −3.3 again. Not modelled: the series is known only at kickoff and is barred from the warehouse; a live signal needs a pre-kickoff starter source Atlas does not have | measured, not in v1 |
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

**v1.1 (step 4) — built.** Three programme features joined the recipe, all
pre-season facts staged by `atlas/staging/talent.py`: the programme's mean
SP+ over the seasons already played, whether the team opens under a head
coach hired since the previous September (a mid-season interim never opens
a season), and their interaction with last season's overachievement. The
recipe learned −1.41 points per sd on the interaction, −1.11 on the
new-coach flag and +0.94 on the programme mean. Weeks 1–4 CRPS 9.51 →
9.47, weeks 3–4 9.73 → 9.67; team-level week-1 correlation up in four
seasons of five (2024: 0.717 → 0.736), down in 2021, whose SP+ history is
four seasons thin. Through the state it is worth 0.02 CRPS pooled and
0.07 in weeks 3–4, winning 2022–2025 and losing 2021 by 0.05. Returning
*passing* production was tested and adds nothing once total returning
production is in. The quarterback and the portal are in §4, rows 8–9.

**v1.2 (portal) — built.** CFBD's portal file starts in 2021; the fetch
was already in place and the raw store now holds 2021–2026 (1,770 to
4,499 transfers a season, the number doubling in five years). Each
transfer is weighted by his composite rating, by the typical rating for
his stars where only stars are known, and by a floor where neither is;
`atlas/staging/talent.py` sums the weight into and out of every
team-season, with seasons before 2021 at zero on both sides so the prior
is fitted across the boundary. Measured on the prior's out-of-sample
residual, incoming quality matters (t 2.8) and outgoing quality does not
once incoming is in (t −0.4): departures are what returning production
already measures. So the prior gained one feature, incoming quality, and
learned +1.19 points per sd on it. Weeks 1–4 CRPS 9.472 → 9.443, weeks
1–2 9.247 → 9.164; better in 2023, 2024 and 2025, worse by 0.04 in 2022,
unchanged in 2021, which had no portal. Small, in the direction the data
said, and it will grow: the portal's scale has doubled since 2021 and
the feature's sd with it.

**State — built, `reports/ncaaf_state.md`.** One joint Kalman filter over
every team's `off` and `def` with a full covariance, which is the opponent
adjustment (`atlas/models/kalman.py`). Each season opens at the prior's
means; every FBS-vs-FBS regular-season game is forecast before kickoff and
then assimilated as two observations, the home and the away points.

**Process.** Within season `off_{i,t+1} = off_it + ε`, `ε ~ N(0, q)` per
week, the same `q` on off and def. Chosen per test season by walk-forward
on the three most recent training seasons, by Gaussian predictive
log-likelihood: `q = 1` point² per week (0 for 2021, whose training window
is a third COVID), prior variance 20 on a team's off and again on its def,
observation sd 10 on one team's points. A game's margin therefore opens at
sd ≈ 15.5 and the prior's half-life comes out near three games, as §3
predicted.

**Observation.** v1 observes the two point totals only. The adjusted-EPA
channel and the pooled FCS opponent are v1.2; they were not needed to pass
the step-3 bar.

Scored beside the references, regular season 2021–2025, walk-forward,
same lattice and scoring as the benchmarks:

| regular 2021–25 | CRPS | Brier | MAE | ECE |
|---|---|---|---|---|
| Elo | 9.23 | 0.188 | 13.04 | 0.015 |
| prior alone | 9.79 | 0.204 | 13.83 | 0.016 |
| **state** | **8.96** | **0.183** | **12.66** | 0.017 |
| market | 8.61 | 0.176 | 12.12 | 0.025 |

By week bucket the state's CRPS against Elo's is 9.15 / 10.18 (weeks 1–2),
9.32 / 9.75 (3–4), 8.79 / 8.86 (5–8), 8.84 / 8.99 (9–12) and 9.01 / 9.10
(13+): it wins every bucket on CRPS, Brier, log score and MAE, every
season (2021 is the closest, 9.32 to 9.34), the bowls (9.21 to 9.54) and
every spread bucket, by most at 21+ points (9.28 to 10.27), where Elo's
fixed K under-rates the best teams. Calibration error is within noise of
Elo's, better in three buckets and worse in two. It also beats the prior in
weeks 1–2 (9.15 to 9.26): one game of evidence already helps. The gap to
the market narrows from 0.74 CRPS in weeks 1–2 to 0.12 by week 13, which
is the size of the step-4 job and the step-5 job respectively.

**Total — built, `reports/ncaaf_total.md`.** The state already implies a
total, its home points plus its away points, but the sum of two noisy
strengths spreads more than real totals do (slope 0.69 against actual
totals). So the total is that implied number recalibrated walk-forward on
the training seasons' own state forecasts (slope 0.51–0.67, refit each
season) plus the two game-level terms that measured as real on its
residual: the teams' combined adjusted pace (seconds per play; about −1.5
points per sd) and the effective wind (−0.15 to −0.20 points per mph).
Temperature, precipitation, domes and rest all measured at |t| < 0.5 and
are out. Forecast sd 16.2–17.2 against the market's 15.7.

| total, regular 2021–25 | CRPS | MAE |
|---|---|---|
| naive (training mean) | 9.62 | 13.63 |
| state total, raw | 9.19 | 12.96 |
| **total (calibrated)** | **9.13** | **12.91** |
| market (closing total) | 8.85 | 12.47 |

The gap to the market is 0.53 CRPS in weeks 1–2 and 0.22 by week 13. A
model weaker than the market is over-confident on P(over) by construction
(its ECE against the closing total is 0.07; where it disagrees with the
line the market is usually right), which is one more reason the card never
frames the total as a side.

**Distribution — built, `atlas/models/joint.py`.** The margin (state mean
and sd through the key-number lattice) and the total (discretised normal)
are combined as a product on the pairs they both allow, which is the whole
grid, since a margin and a total from one game always share parity. Their
residual correlation measured at 0.07, so independence is the v1 joint.
Passing the margin through the grid costs +0.03 CRPS (8.97 against the
lattice's 8.94), the price of the 0–79 bounds.

**Output — built.** An 80×80 grid over (home, away) points; the headline is
its mean to one decimal — 31.7–24.2, total 55.9 — never a rounded integer.
P(home) from the grid is within 0.04 of the observed rate in every spread
bucket, 28+ point favourites included (0.83 forecast, 0.85 observed), the
same shape as the market's. The most probable exact score is a 0.3% event
and was right 0.35% of the time; the actual score sat in the grid's top
ten cells 3% of the time and its median rank was 478. The card shows the
top cell for what it is.

**Card — built, step 6.** `atlas/models/ncaaf_projection.py` runs steps 2–5
forward to today: the season's prior, the state carried through every game
already played, the calibrated total and the grid, one row per scheduled
game, published by the weekly refresh to `tracking/projections.csv` with
the state's view of each team (offence, defence, rank, games of evidence)
for the drivers. The card reads it; nothing on the card blends the model
with the market any more. Tier one is the market (spread, total, where the
spread opened and how far it moved) first, Atlas's projection second, to
one decimal, and the difference on the spread; the drivers open with the
model's own terms in points; the cautions say when a team's number is
still mostly its preseason expectation and when a game is a bowl. The
grade is computed on the spread and fitted to this model's walk-forward
record against the closing line (`tracking/calibration.csv`, written by
the same refresh; five seasons, 3,864 games; the curve's fit r = 0.72), so
it describes this model and not the one before it. The site audit passes
on every page. Not changed: the closing-line signal tracker still forms
its signals from the earlier ridge model's numbers; replacing that is a
product decision, not a modelling one.

**Step 7 — the gate, measured; v1.5 instead of v2.** The foundation said
to build the state-dependent drive simulation only if v1's exact-score
log score left visible room. It did, but not where a simulation would
look for it. Walk-forward, regular seasons 2021–2025, mean −log P(actual
score) on the 80×80 grid:

| grid | −log P | top-10 hit | median rank | margin CRPS | total CRPS |
|---|---|---|---|---|---|
| two discretised normals, no lattice | 7.647 | 1.2% | 562 | 8.975 | 9.141 |
| margin lattice only (v1) | 7.535 | 3.1% | 481 | 8.973 | 9.140 |
| market's grid (closing spread and total through the same margin lattice) | 7.465 | 3.4% | 444 | 8.645 | 8.846 |
| **v1 + points lattice (v1.5)** | **7.099** | **5.7%** | **242** | **8.950** | **9.122** |

A team's points cluster on their own key numbers — 0, 3, 7, 10, 14, 17,
21, 24, 28 — and a lattice on the margin sees none of that. The points
lattice is one fitted multiplier per points value, observed over expected
frequency on the training seasons' own grids, shrunk toward one where the
expectation is thin and capped at 5, applied to both sides and
renormalised (`atlas/models/joint.py`, `fit_points` and `reweight`). It
is worth four times what the margin lattice was, it beats the market's
own grid on the exact score by 0.37 nats, and it leaves the margin and
total CRPS very slightly better rather than worse. The 2025 fit puts a
shutout at 3.5× the normal's frequency, 7 points at 3.0×, 3 at 2.7×, 10
at 2.7× and 14 at 2.5×. It is fitted walk-forward in `ncaaf_total` and in
the projector, so the card's most likely score is now a key-number pair
at roughly 1% rather than an off-key cell at 0.3%.

So the drive simulation is not warranted on this evidence. Its case would
have to be made against 7.10, and the remaining structure a product of
two points lattices and a margin lattice cannot express — score-dependent
decisions late in games, the 2-point conversion — is what it would have
to capture. That is the v2 bar, and it stays open.

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
| 3 | Kalman state model, off/def, opponent-adjusted, no extras (`atlas/models/kalman.py`, `atlas/models/ncaaf_state.py`, `make ncaaf-state`) | **done — beats Elo in every week bucket; CRPS 8.96 vs Elo 9.23, market 8.61** |
| 4 | Coaching-change and programme-mean features in the prior; portal fetch; QB measured | **done — weeks 1–4 CRPS 9.51 → 9.47, weeks 3–4 9.73 → 9.67; state pooled 8.96 → 8.94** |
| 5 | Total model + joint grid (`atlas/models/ncaaf_total.py`, `atlas/models/joint.py`, `make ncaaf-total`) | **done — total CRPS 9.13 (naive 9.62, market 8.85); grid P(home) within 0.04 in every spread bucket** |
| 6 | Wire into the card (model number second slot, market open/move/now first, drivers third) and the grade (`atlas/models/ncaaf_projection.py`, `tracking/projections.csv`, `tracking/calibration.csv`) | **done — audit passes on 182 pages; grade fitted to this model's record** |
| 7 | v2 drive simulation, if warranted | **gate measured; not warranted yet.** A points lattice (v1.5, `joint.fit_points`) took the exact-score log score 7.54 → 7.10 with no simulation; a simulation has to beat 7.10 |

Steps 0–7 are done, step 7 by measuring its own gate, and the portal (factor
8, v1.2) is in the prior. What remains is a v2 simulation only if it can beat
the v1.5 grid on the exact score. The NFL plan (`docs/MODEL_PLAN_NFL.md`) is
built through its own step 7.

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
