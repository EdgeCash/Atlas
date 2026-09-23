# Atlas — Model Foundation

What the NFL and NCAAF models share: the goal stated precisely, what "accurate"
can mean for a football score, the ceiling, the architecture the evidence
supports, and the protocol that decides whether a model is good. The two sport
plans (`MODEL_PLAN_NFL.md`, `MODEL_PLAN_NCAAF.md`) inherit everything here and
add only what differs.

Every number below was either measured on data in this repository (nflverse
1999–2025 and cfbfastR 2018–2026, both free) or taken from a cited source.
Where the two disagree, the measurement wins and the disagreement is noted.

---

## 1. The goal, stated so it can be tested

**Produce, for every game, a calibrated joint probability distribution over the
final score (home points, away points).** Everything a reader sees is a
functional of that object:

| Reader sees | Is |
|---|---|
| **"Atlas projects 27.4–25.8, total 53.2"** | **the mean of the distribution — always decimal** |
| "62% Georgia" | mass where home margin > 0 |
| "Total 53.2, likely range 41–65" | the marginal on home + away and its central interval |
| "27–26 exactly: 1.1%" | mass on one integer cell — a secondary output, never the headline |
| "Market says −3, Atlas says −5.5, here's why" | the mean, its drivers, and the market's |

**The headline is the mean, and the mean is a decimal.** 27.4–25.8 is more
honest than 27–26: it says what the distribution is centred on without
pretending a football score is a real number, and it does not invite a reader
to grade it as right or wrong. Integers appear only where the distribution is
asked about an integer — "how likely is 27–26 exactly?" — and that is a
feature a reader opens, not the number on the card.

Two consequences the product must honour.

**Calibration is the target, not error.** A model whose 60% actually happens
60% of the time is doing its job even when it is wrong. A model with a lower
mean error but a lying probability is not. The success criteria in §6 are proper
scoring rules and reliability, with MAE reported alongside as a courtesy.

**The point forecast is a by-product.** The current Atlas model predicts margin
and total as two independent point estimates and derives a score by arithmetic.
That cannot answer "how likely is a two-score game" or "what's the chance of
27–26" — nor can any model built that way. The distribution comes first; the
decimal projection is its mean, read off it.

---

## 2. What "accurate" can mean for a football score

### The ceiling, measured

Take the best publicly available forecast of the mean — the closing market —
wrap it in the residual distribution measured on our own data, and score it.
This is roughly the best a model built from public data can hope to do, and it
is what the models are graded against.

| | NFL (2015–25, n=2,927) | NCAAF FBS-vs-FBS (2021+ out of sample, n=3,864) |
|---|---|---|
| Mean absolute error, margin | **10.04** | **12.25** |
| Residual sd, margin | 12.74 | 15.72 |
| Residual sd, total | 13.21 | 16.60 |
| CRPS, margin | **7.10** | **8.61** |
| Brier, home win | **0.213** | **0.178** |
| Avg probability on the exact margin | 2.12% | 1.79% |
| Avg probability on the exact final score | **0.064%** | **0.042%** |
| Modal exact score is right | **0.34%** | **0.23%** |

Read the last two rows carefully, because they set expectations for the entire
product. **A market-quality model names the exact integer final score about
once in 300 NFL games and once in 400 college games.** The most common NFL
score, 20–17, occurs in 1.9% of games; 619 distinct scores appeared in 2,159
games. That is why the headline is the decimal mean and not an integer guess:
"we projected 27.4–25.8" is a statement about where the distribution sat, and
it is graded by CRPS and calibration, not by whether 27–26 came up.

### Why the ceiling is where it is

Football outcomes are noisy in a way no information fixes. Stern (1991) found
NFL margin-minus-spread ~ N(0, 13.86) on 1981–84 data; Warner (2012) found sd
13.59 on 2002–11; we find 12.74 on 2015–25 and 13.01 on 2011–25. The number has
tightened a point in forty years. For college it is 15.5–15.7 conditional on
the spread (the CFB spread paper uses 15; unconditional it is 21–22).

Glickman & Stern's dynamic model, which uses everything the scores can tell it,
lands at residual sd 13.1 for the NFL. That is the noise floor with perfect
knowledge of team strength. **The gap between a perfect model and the market is
smaller than the gap between the market and nothing.**

---

## 3. Why the current model is the wrong shape

Three facts about `atlas/live/signals.py` as it stands:

1. **It predicts two scalars** — `model_margin`, `model_total` — and derives the
   score. No distribution exists to be calibrated.
2. **It uses 10 features** chosen to make a research comparison fair
   (`MATCHED_ADJ`: "so the headline comparison is like-for-like rather than a
   bigger feature set beating a smaller one"). SP+, FPI, Elo, talent,
   recruiting, returning production, rest, travel and weather are in the
   warehouse at 81–100% coverage and the model has never seen them.
3. **It was fitted to beat the closing line**, and on margins it could not
   (β = 0.023 ± 0.032), so it anchors to the market at weight 1.00 and publishes
   the market's number. That was the right answer to the wrong question.

None of that is salvageable by tuning. The replacement is a different object.

---

## 4. Architecture the evidence supports

Three layers. The first two produce a mean; the third turns it into a
distribution. Each choice below is tied to a measurement.

### Layer A — team strength as a dynamic state

Every team carries a latent strength vector that evolves week to week and
regresses between seasons. Glickman & Stern (1998; 2015 update) and Lopez et
al. (2018) fit exactly this as a normal state-space model; Elvidge (2025)
implements it as a Kalman filter whose gain replaces Elo's fixed K. We follow
that lineage, with **separate offensive and defensive states**, because the
data says they behave differently:

| Within-season persistence (H1 vs H2 corr) | NFL | NCAAF (FBS only) |
|---|---|---|
| Offensive EPA/play | 0.44–0.69 | 0.38–0.58 |
| Defensive EPA/play allowed | 0.21–0.55 (mostly ~0.25) | 0.33–0.55 |
| Offensive TD per drive | 0.32–0.78 | 0.44–0.59 |
| **Field-goal rate per drive** | **−0.25 to 0.59, median ~0.05** | **0.05–0.32** |
| Defensive TD/drive allowed | 0.05–0.44 | 0.33–0.55 |
| Drives per game (pace) | 0.15–0.49 | — |

Offence is a skill that persists. Defence persists less in the NFL and is
shrunk harder toward the mean. **Field-goal rate is not a team skill in either
sport** — it is a function of where drives end and what the score is — and
must never be a state variable. (The nflfastR community weights offensive EPA
1.6× defensive for the same reason.)

**Priors matter for exactly as long as the data says.** Regressing this game's
net EPA on last season's and on season-to-date:

| Games already played | NFL: share of weight on season-to-date | NCAAF: share |
|---|---|---|
| 1 | ~20% | 8% |
| 2 | ~40% | 18% |
| 3–4 | ~50–70% | 50% |
| 5–6 | ~90% | 65% |
| 8+ | ~100% | ~100% |

So the prior has a half-life of roughly three games in both sports. That is
the Kalman process noise, and it is a fitted quantity, not a setting.

**Between seasons, strength regresses about a third of the way to the mean.**
Glickman & Stern's autoregressive parameter is 0.67 with innovation sd 4.28
points; FiveThirtyEight's Elo reverts one-third toward 1505. Our own measurement
agrees in kind: NFL year-over-year correlation of offensive TD/drive is
0.30–0.58, defensive 0.24–0.45.

### Layer B — game expectation

`E[margin] = (off_home − def_away) − (off_away − def_home) + HFA + adjustments`,
and the same for the total with sums instead of differences. Adjustments are
few, and each one is in the plans with its measured size. The headline ones:

| Adjustment | NFL | NCAAF |
|---|---|---|
| Home field, current | **+1.7** (was +2.5 pre-2011; 53.3% home win) | **+4.6** (was +7.1 in 2018–19; 57% home win) |
| Starting QB change | **−3.3** (market moves −3.7) | see plan; larger and noisier |
| Bye-week rest | +0.3, not significant | — |
| Divisional game | none (margin sd 14.29 vs 14.34) | — |
| Dome | none (home margin +1.76 dome, +1.75 outdoors) | — |

### Layer C — from a mean to a distribution

The evidence is unusually clean here, and it rules out the obvious approach.

**A normal on the margin is an excellent marginal model.** Residuals against
the market are homoskedastic (NFL sd 12.6–13.4 across every spread bucket;
NCAAF 14.8–16.0), symmetric (skew 0.10 / 0.00) and only mildly heavy-tailed
(excess kurtosis 0.38 / 0.17). Glickman & Stern, Stern, and the CFB spread
paper all reach the same conclusion.

**But the normal misses the lattice.** Football scores land on 3s and 7s.
Empirically |margin| = 3 in **14.4%** of NFL games and 8.1% of college games;
a normal with the right sd puts 3.6% there. The fix is the one the CFB spread
paper uses and we re-derived on our own data: **multiply each integer's normal
probability by an empirical factor, then renormalise.**

| |margin| | NFL multiplier (fit 2002–14) | NCAAF multiplier (fit ≤2020) |
|---|---|---|
| 0 | 0.05 | 0.00 |
| 3 | **2.6–2.9** | **2.7** |
| 7 | **1.9** | **2.4** |
| 10 | 1.6 | 1.3 |
| 14 | — | 1.7 |

CRPS barely notices (7.095 vs 7.111) because CRPS is a distance score; the
log-score of the exact margin and every exact-score probability depend on it
entirely.

**Independent Poisson scoring events do not work, and the reason is
instructive.** Simulating each team's TDs and FGs as independent Poissons at
league-average rates gives |margin| = 3 in 5.5% of games (real: 14.6%), ties
in 3.05% (real: 0.36%), and margin sd 16.8 (real: 14.3). Moyer et al. (WSC
2024) find the same failure and diagnose it: teams change behaviour with the
score. Our play-by-play confirms it — the 2-point attempt share is **32% when
trailing by 9+, 1% when tied, 19% when up 1–2**; in the fourth quarter on
fourth down inside the 35, NFL and college offences go for it ~80% when
trailing by 9+ and kick ~70% when up 0–3. Drive *success* barely varies with
score (TD rate 20–24% NFL, 24–28% NCAAF across all states); drive *decisions*
vary enormously. A simulation that ignores that produces the wrong lattice.

**And team points are conditionally independent.** Unconditionally, home and
away points correlate at −0.04 (NFL) and −0.17 (NCAAF, because mismatches are
bigger). Conditional on the market's mean, the residual correlation is 0.03 and
0.05. So once strength is accounted for, the two teams' scoring noise is
independent — which is what makes a bivariate normal on (margin, total) with
near-zero residual correlation a sound joint model.

**Therefore, in order of build:**

1. **v1 — Normal + lattice.** Bivariate normal on (margin, total) with fitted
   residual sds, near-zero correlation, discretised to integer scores, margin
   reweighted by the key-number multipliers. This is the market-quality
   benchmark's own construction, it is cheap, and it is immediately calibratable.
2. **v2 — State-dependent drive simulation.** The Moyer et al. non-stationary,
   state-dependent process, driven by our own drive-outcome rates and
   decision tables (which we have already measured). Only if v1's exact-score
   log-score leaves visible room — the lattice multiplier is a good enough
   proxy that it may not.

---

## 5. Data: what both sports have, free

| | NFL (nflverse) | NCAAF (cfbfastR + CFBD free tier) |
|---|---|---|
| Play-by-play | **1999–present, 372 columns**, EPA/WP/CPOE, fixed drives with result | 2018–present in repo, 48 columns, EPA, drive_pts; `espn_cfb_drives` hosted |
| Game-level | schedules: result, spread, total, moneylines, roof, surface, temp, wind, **starting QB (91%)**, coach, referee, rest days, div flag | games: division, neutral, pregame Elo, market |
| Personnel | weekly rosters 2002+, depth charts 2001+ (depth 1/2/3), **injuries 2009+** (Out/Doubtful/Questionable + practice status), snap counts 2012+ | rosters, returning production, recruiting, talent, **transfer portal**, coaches — all free CFBD |
| Tracking / charting | participation 2016+ (box count, pressure, coverage, personnel), FTN 2022+ (motion, play action, RPO, blitzers), NGS 2016+ | — |
| Ratings | ESPN QBR, PFR advanced | SP+, FPI, Elo, SRS — free CFBD |
| Weather | temp/wind in schedules, 81% of outdoor games | Meteostat (already ingested); CFBD weather is the one paid endpoint |
| Cost | **$0**, no key | **$0**; CFBD free tier is 1,000 calls/month and ingest caches per season |

The NFL side is not in the repo yet. It is ~420 MB and an afternoon.

---

## 6. Validation protocol — the same for both sports

**Walk-forward only.** Fit through week *w−1*, predict week *w*, roll. Seasons
are the outer fold. Nothing in a game's prediction may post-date its kickoff;
`atlas/features/point_in_time.py` already enforces this for the warehouse and
the models inherit it.

**Scores, in this priority:**

| Score | What it measures | Benchmark to beat |
|---|---|---|
| **Reliability diagram + ECE**, home-win probability | is 60% really 60% | ECE < 0.02 |
| **CRPS**, margin and total | whole distribution, distance-aware | NFL 7.10 / NCAAF 8.61 |
| **Brier**, home win | discrimination + calibration | NFL 0.213 / NCAAF 0.178 |
| **Log-score**, exact margin | the lattice | avg prob NFL 2.1% / NCAAF 1.8% |
| **Log-score**, exact final score | the product claim | avg prob NFL 0.064% / NCAAF 0.042% |
| MAE, margin | courtesy | NFL 10.0 / NCAAF 12.3 |

**Three reference models are always scored beside ours,** and a plan is not
finished until it beats the first two and is within reach of the third:

1. *Naive* — home team by the historical home advantage, league-average sd.
2. *Elo* — a plain rating with FiveThirtyEight's parameters. In college this is
   the strongest single external predictor late in the season (corr with
   margin 0.63 in weeks 13–16, ahead of prior-season SP+ at 0.43).
3. *Market* — the closing line inside the residual distribution from §2.

**Minimum detectable improvement.** With ~270 NFL games a season, a CRPS
difference below ~0.15 is not distinguishable from noise in one season; report
three-season rolling windows and bootstrap intervals. College has ~800
FBS-vs-FBS games a season and can resolve about half that.

**The grade machinery is the validation.** `atlas/site/grade.py` already fits
realised-versus-claimed accuracy walk-forward and out of sample. Its
`calibration_curve()` is a reliability diagram. The new models plug into it.

---

## 7. What transfers from Atlas unchanged

- Point-in-time feature construction and the walk-forward harness
  (`atlas/features/point_in_time.py`, `atlas/research/market_aware.py`).
- Opponent adjustment (`atlas/features/opponent_adjustment.py`) — the
  college model's most important preprocessing, near-irrelevant in the NFL.
- The calibration and grading code, which becomes the model's own report card.
- The warehouse, staging and freshness/ops plumbing.
- The card. Its three tiers already have slots for market open, market now,
  Atlas's number and the drivers. What changes is what goes in the second slot.

---

## 8. Build order

| Phase | Deliverable | Done when |
|---|---|---|
| 0 | NFL ingest (nflverse → warehouse); pin the NCAAF frame (FBS-vs-FBS, garbage time excluded — both already true) with tests | both frames pass the point-in-time tests |
| 1 | Reference models + lattice + scoring harness, walk-forward, both sports (`atlas/models/`) | `reports/{sport}_benchmarks.md` reproduces the §2 table |
| 2 | Layer A+B, **NCAAF first** (the data is here) | beats Elo on CRPS and Brier out of sample |
| 3 | Layer A+B, NFL | same |
| 4 | Card: model number in the second slot, market open/move/now in the first, drivers third | language audit passes; grade uses the new distribution — **done for NCAAF** (`docs/MODEL_PLAN_NCAAF.md` step 6) |
| 5 | v2 drive simulation, if phase 1's exact-score log-score leaves room | measurable gain on exact-score log-score |

College goes first because its warehouse exists, its games are four times as
numerous, and its team-strength spread is wide enough that a model has room to
be visibly right or wrong. The NFL model is the harder problem — see its plan —
and benefits from a working college pipeline to copy.

---

## 9. Why not the market feed, one last time

A better market number sharpens the thing the model is compared *against*. It
does nothing for the model. Everything in §4 is built from team and play data
the repo already has or can fetch for free. `DATA_PROVIDER_REVIEW.md` stands.

---

## Sources

- Stern, H. (1991). *On the probability of winning a football game.* The American Statistician 45(3). — N(0, 13.86).
- Warner, J. (2012). [*The performance of betting lines for predicting the outcome of NFL games*](https://arxiv.org/abs/1211.4000). — sd 13.59, 2002–11.
- Glickman, M. & Stern, H. (1998). *A state-space model for NFL scores.* JASA 93. And [*Estimating team strength in the NFL*](https://www.glicko.net/research/nfl-chapter.pdf) (2015 update). — HFA 2.4, residual 13.1, innovation 4.28, AR 0.67.
- Lopez, M., Matthews, G. & Baumer, B. (2018). [*How often does the best team win?*](https://arxiv.org/abs/1701.05976) — cross-sport state-space.
- Moyer, Railey, Daw & Gutekunst (2024). [*Simulating NFL scores with a non-stationary, state-dependent Poisson process.*](https://informs-sim.org/wsc24papers/con253.pdf) — why naive Poisson fails.
- Baker, R. & McHale, I. (2013). *Forecasting exact scores in NFL games.* Int. J. Forecasting 29.
- [*Converting college football point spread differentials to probability*](https://arxiv.org/abs/2212.08116) (2022). — sd 15, key-number multipliers.
- Elvidge, S. (2025). [*Tracking football team strengths with a Bayesian Kalman model.*](https://seanelvidge.com/articles/2025/Football_team_rankings/)
- Silver, N. (2025). [*The NFL has entered the Scorigami era.*](https://www.natesilver.net/p/the-nfl-has-entered-the-scorigami) — score-lattice drift.
- [FiveThirtyEight NFL Elo](https://github.com/fivethirtyeight/nfl-elo-game); [nfelo](https://www.nfeloapp.com/about/).
- [Bye-bye, bye advantage](https://www.frontiersin.org/journals/behavioral-economics/articles/10.3389/frbhe.2024.1479832/full) (Frontiers 2024). — rest effects 2002–23.
- [PFF: NFL home teams are winning less](https://www.pff.com/news/nfl-home-field-advantage-pff-data); [The Prediction Tracker](https://www.thepredictiontracker.com/nflresults.php).
- Gneiting, T. & Raftery, A. (2007). *Strictly proper scoring rules, prediction, and estimation.* JASA 102.
- [nflverse data](https://github.com/nflverse/nflverse-data/releases); [nflreadr reference](https://nflreadr.nflverse.com/reference/index.html); [cfbfastR reference](https://cfbfastr.sportsdataverse.org/reference/index.html); [CFBD API tiers](https://collegefootballdata.com/api-tiers).
