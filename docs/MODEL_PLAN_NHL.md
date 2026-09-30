# Atlas — NHL Model Plan (game projections and player props)

Inherits `MODEL_FOUNDATION.md`. This document covers only what is specific to
the NHL: the data, the empirical profile, the factors and their measured
sizes, the game model, the player-prop model, how both are validated, and the
order to build them in. It follows `MODEL_PLAN_NFL.md` section for section.

**Status (30 September 2026): steps 0 to 5 are built; the game model meets v1's bar**
(`reports/nhl_model.md`: better than Elo and the goals-based Poisson model on
every row out of sample). Every poll records
ESPN's DraftKings moneyline, puck line and total and the NHL finals
(`atlas/live/provider.py`), and the owner capture seals every BettingPros
book's NHL lines and player props (`atlas/owner/nhl_capture.py`). The raw
cache (`atlas/sources/nhl.py`, 19,197 games of play-by-play, 2010-11 on) and
the warehouse (`atlas/staging/nhl/`) reproduce §3 (`reports/nhl_profile.md`);
expected goals are fitted a season at a time (`reports/nhl_xg.md`); the
benchmarks are scored (`reports/nhl_benchmarks.md`); the state, the goalie
and the grid are built and scored (`atlas/models/nhl_state.py`,
`nhl_grid.py`, `nhl_model.py`). The rest below is the plan, with what the
build changed marked where it did. Every number in it was
measured on 30 September 2026 from the sources in §2, unless it says it is
cited; step 1's warehouse has to reproduce §3 to the decimal before anything
is built on it, as the NFL's did.

**The 2026–27 regular season opened on 29 September 2026** (five games, then
three on 30 September and eight on 1 October; this plan first said the 30th,
from ESPN's scoreboard for that day alone). The build runs in season. The
market capture starts first, because closing lines not captured are gone:
it began on 30 September, so the five opening-night closes were missed.

---

## 1. Why hockey is its own problem

Four structural facts, all measured.

**One game is mostly luck, and the prior lasts.** A team's goal share over
the rest of a season correlates 0.55 with last season's before a game is
played, and still 0.50 twenty games in; this season's own goal share only
overtakes it after about twenty games (§3). The NFL's prior half-life is
about three games; hockey's is closer to twenty-five. So the state moves
slowly, and it is fed by shots and expected goals, which stabilise far
faster than goals (split-half 0.72 against 0.50).

**The market is good, and the room is small.** Closing moneylines, 2010–11 to
2021–22 (14,865 games, playoffs included): Brier 0.2385 against 0.2482 for
"the home side, always". The whole gap between knowing nothing and the closing line is 0.010
of Brier. Calibration is within about two points in every bucket from 30%
to 70%.

**The goaltender is the quarterback.** The spread of save percentage across
goalie-seasons is 1.07 points, about 0.3 goals a game on thirty shots, the
largest single-game factor after the teams themselves. It is also the
noisiest thing to measure (odd/even-game reliability 0.31, year over year
0.44), and who starts is not known until the morning skate: the team's #1
starts 67% of games on rest and 42% on the second night of a back-to-back.

**The score lattice is shaped by overtime and the empty net.** Overtime adds
exactly one goal, so odd totals are inflated (5 goals 20.0% of games, 6
goals 13.7%, 7 goals 17.9%). Pulled goalies turn one-goal games into
two-goal ones: 64% of two-goal wins include an empty-net goal, and 98% of
those were one-goal games before it. The puck line is mostly an empty-net
model.

---

## 2. Data — verified 30 September 2026

### The NHL's own API — free, no key

| Source | Endpoint | Seasons | Use |
|---|---|---|---|
| Game list | `api.nhle.com/stats/rest/en/game?cayenneExp=season=YYYYYYYY and gameType=2&limit=-1` | 2010–11 → | one call a season: id, date, teams, final score, `period` (3 regulation, 4 overtime, 5 shootout) |
| Team game logs | `stats/rest/en/team/summary?isGame=true` | → | goals, shots for/against, PP%, PK% per team-game; 2,624 rows a season, one call |
| Goalie game logs | `stats/rest/en/goalie/summary?isGame=true` | → | `gamesStarted`, saves, shots against, TOI per goalie-game; one call a season |
| Skater game logs | `stats/rest/en/skater/{summary,realtime,timeonice}?isGame=true` | → | goals, assists, points, shots, hits, blocks, missed shots, empty-net goals, TOI by strength (EV/PP/SH); ~47,000 rows a season, **capped at 10,000 a query**, so fetched a month at a time |
| Play-by-play | `api-web.nhle.com/v1/gamecenter/{id}/play-by-play` | coordinates from 2010–11 | every shot with x/y, shot type, shooter, `goalieInNetId`, `situationCode` (skaters and goalies on ice, so empty net and strength state): the expected-goals model's input. ~320 events a game |
| Shift charts | `api.nhle.com/stats/rest/en/shiftcharts?cayenneExp=gameId=…` | recent seasons | every shift: TOI by strength, line combinations |
| Schedule | `api-web.nhle.com/v1/schedule/{date}` | 2026–27 published | the week's games, start times, venue |

One game-list call and three game-log calls a season cover the game model's
history back to 2010–11 (19,152 regular-season games, measured). The play-
by-play is one call a game, ~1,300 a season: cache it trimmed to shot events,
once, as the college play-by-play is cached.

### ESPN — the public anchor, as for football

The NHL scoreboard (`site.api.espn.com/apis/site/v2/sports/hockey/nhl/scoreboard`)
carries **DraftKings' moneyline, puck line and total on upcoming games**, the
same book and the same code path the football cards anchor to, and its event
id is the key Atlas already uses for every game. ESPN keeps **no odds on past
NHL games** (`pickcenter` empty for 2012, 2015, 2018 and 2025 games checked),
so it is a live source only. The game summary has a `goalies` block and an
`injuries` block; whether it names the probable starter before puck drop is
to be checked on the first game days.

### Historical closing lines

| Source | Coverage | Status |
|---|---|---|
| SportsBookReviewsOnline archive (`/scoresoddsarchives/nhl-odds-YYYY-YY`) | 2010–11 → 2021–22 verified complete (e.g. 1,401 games in 2021–22 with playoffs; pages go back to 2007–08); 2022–23 stops on 27 November | **fetched and parsed**: opening and closing moneyline, puck line with price, opening and closing total with price. Needs a browser user agent. Personal-use archive: cache it, never republish it |
| The Odds API, historical | from late 2020 | paid; fills 2022–23 → 2025–26 |
| BettingPros partner API, `/offers` by season | unknown | the key Atlas already has; its depth for past NHL seasons is to be measured with a counts-only call |
| sports-statistics.com | ESPN-derived skater (1.01M rows) and goalie box scores, keyed by ESPN event id | a cross-check only: the NHL API is the primary, and the download was not reachable from here |

The market benchmark therefore exists for 2010–11 to 2021–22 now, and for
the seasons since only if one of the last two is bought or verified. From
opening night Atlas captures its own closing lines (ESPN's DraftKings and
BettingPros' books), as it does for football.

### BettingPros — the owner's side

The partner API lists the NHL in every sport enum and filters props by
C/LW/RW/D/G. Markets are found by slug at run time, as the football props are
(`bettingpros.prop_markets`). Expected: moneyline, puck line, total, and
props for shots on goal, points, goals, assists, saves, blocked shots and
power-play points. The slugs, the books quoting them and PrizePicks' coverage
are the first counts-only log line of the NHL capture.

### What is deliberately not on this list

MoneyPuck and Natural Stat Trick. Both publish expected goals and on-ice
rates, and both have terms that do not fit a product that republishes
derived numbers. Atlas fits its own expected-goals model on the NHL's
play-by-play (step 2), which also keeps every input point-in-time.

---

## 3. Empirical profile (NHL API, regular seasons 2010–11 to 2025–26)

Recomputed from the warehouse by `python -m atlas.research.nhl_profile`
(`reports/nhl_profile.md`), step 1's test. Every figure below is the
warehouse's. Where the first measurement differed it has been corrected here:
the back-to-back counts (1,055 and 3,330, against 1,048 and 3,296; the home
side's rate 46.5% against 46.8%), the goalie's year-over-year 0.45 and spread
1.08 (0.44, 1.07), the prop dispersions (shots 1.08, points 0.97, hits 1.18,
blocks 1.08, saves 1.98 with sd 7.6; first 1.10, 0.95, 1.20, 1.12, 2.11,
7.4), the high-volume shooters' over rates, now on the season mean without
the game (58.5% and 64.5%; first 58.2% and 65.0%), and the market's count
(14,865, playoffs included). The split-half figures are the first half of a
team's season against the second; year over year is pooled over consecutive
seasons.

### Outcome structure

A shootout adds one goal to the winner's final score; it is taken off here.

| | 2010–14 | 2014–20 | **2020–26** |
|---|---|---|---|
| Games | 4,410 | 7,314 | 7,428 |
| Home win % (incl. OT/SO) | 54.3 | 54.4 | **53.7** |
| Home win % of regulation decisions | 55.7 | 55.5 | 54.2 |
| Overtime % (incl. shootouts) | 24.2 | 23.1 | 22.3 |
| Shootout % | 13.7 | 8.9 | **7.3** |
| Goals per game | 5.37 | 5.65 | **6.13** |
| Total, sd | 2.22 | 2.28 | 2.32 |
| Home / away goals per game | 2.82 / 2.54 | 2.96 / 2.69 | 3.18 / 2.95 |
| Home–away goals correlation | −0.05 | −0.05 | −0.11 |
| Team goals var/mean | 0.97 | 0.98 | 1.00 |
| One-goal regulation games % | 23.2 | 21.4 | **18.0** |
| Two-goal games % | 21.6 | 20.9 | 19.4 |
| Three+ goal games % | 31.1 | 34.6 | **40.3** |

Home ice is worth **+0.23 goals** and 53.7% of games, steady for fifteen
years (season to season 51.9–56.8%). Scoring is up 0.8 goals a game since
2010–14. The shootout has halved since three-on-three overtime (2015–16).

Team goals are Poisson *unconditionally* (var/mean 0.99), which means they
are **under**-dispersed given the teams: score effects, overtime's single
goal and the empty net all pull outcomes toward the middle.

### The lattice: totals and margins

Totals, 2020–26: 3 → 9.3%, 4 → 10.1%, **5 → 20.0%**, 6 → 13.7%, **7 →
17.9%**, 8 → 8.6%, 9 → 9.0%, 10 → 3.1%. Odd totals carry the overtime goal.

Final margin, home side, 2020–26: −3 → 10.5%, −2 → 9.3%, −1 → 15.6%, 0 (a
shootout, its goal removed) → 7.3%, +1 → 17.3%, +2 → 10.1%, **+3 → 13.0%**.
Three-goal margins now outnumber two-goal ones.

**The empty net** (skater game logs, 2022–23 to 2024–25): 0.36 empty-net
goals a game; a third of games have one. Wins by two include one 64% of the
time, wins by three 63%, wins by four 35%, wins by one 2%. Of two-goal wins
with an empty-netter, 497 of 506 were one-goal games before it.

The market has seen it. A closing favourite of 65–70% won by two or more
39.3% of the time in 2010–19 and 44.1% in 2019–22.

### Overtime and the shootout

Home teams win 51.0% of overtimes (n = 2,013) and 51.6% of shootouts
(n = 1,022), 2015–26: close to coin flips, against 54% in regulation.

### Rest

Second night of a back-to-back against a rested opponent, 2010–26:

| | Both rested | On the second night |
|---|---|---|
| At home | 53.5% win, +0.22 goals | **46.5%, −0.09** (n = 1,055) |
| Away | 46.5%, −0.22 | **40.8%, −0.50** (n = 3,330) |

About −6 points of win probability and −0.3 goals, much of it the goalie: the
#1 starts 42% of second nights and 67% otherwise.

### Persistence, what a state model can rely on

| Team metric | Split-half (median season) | Year over year |
|---|---|---|
| Shot share | **0.72** (0.45–0.86) | 0.65 |
| Goal share | 0.50 (0.15–0.80) | 0.55 |
| Shooting % | 0.30 | 0.53 |
| Save % | 0.27 | 0.48 |
| PDO | 0.30 | — |

**Shots are twice as persistent as goals within a season.** The state reads
shot and expected-goal share and shrinks finishing and goaltending hard.

### How fast in-season data overtakes the prior

Correlation with a team's goal share over the rest of the season:

| Games played | Last season's goal share | To-date shot share | To-date goal share |
|---|---|---|---|
| 0 | 0.55 | — | — |
| 5 | 0.54 | 0.38 | 0.26 |
| 10 | 0.53 | 0.44 | 0.37 |
| 20 | 0.50 | 0.47 | 0.49 |
| 40 | 0.42 | 0.45 | 0.51 |

The prior carries more than this season's evidence for the first twenty games
or so. Early, shots say more than goals.

### Goaltenders

The #1's share of a team's starts, median: 69.5% (2010–14), 64.6% (2014–20),
**59.8%** (2020–26). Tandems are the norm now. Save percentage, goalies with
40+ starts: odd/even-game reliability 0.31 (391 goalie-seasons), year over
year 0.45 (224), sd across goalie-seasons 1.08 points.

### Player props (skater game logs 2022–23 to 2024–25, 141,653 player-games)

| Stat | Odd/even-game reliability (40+ games) | Var/mean around the player's own mean |
|---|---|---|
| Shots on goal per game | **0.91** | 1.08 |
| Shots per 60 | 0.87 | — |
| Time on ice per game | **0.99** | — |
| Points per game | 0.85 | 0.97 |
| Shooting % | **0.46** | — |
| Hits per game | 0.94 | 1.18 |
| Blocked shots per game | 0.92 | 1.08 |
| Goalie saves (starters, 2021–26) | — | **1.98** (sd 7.6 on a mean of 26) |

Volume is stable and finishing is not: shots, ice time, hits and blocks are
among the most projectable numbers in sport; goals are not. A plain Poisson
on the season mean overstates the over for high-volume shooters: players at
3.0–3.5 shots a game (the season's mean without the game itself) went over
2.5 58.5% of the time against Poisson's 61.9%, 3.5–4.0 at 64.5% against
71.7% (part of that is the mean regressing, part is the tail). Saves are over-dispersed because shots against swing
with the opponent and the score: they need each game's projected shots
against, not a season average.

**The scorekeeper matters.** Total shots in a team's home games over its road
games: 0.95 (NJD) to 1.07 (FLA), sd 0.026. Total hits: 0.81 (SJS) to **1.30
(TOR)**, sd 0.12. Hits props without an arena term are mispriced by design.

---

## 4. Factors, with measured or cited sizes

| # | Factor | Size | Source | In v1? |
|---|---|---|---|---|
| 1 | **Team strength, 5-on-5 expected goals for and against, dynamic** | the model | §3 | yes |
| 2 | **Starting goalie** | ±0.3 goals a game across goalie-seasons; #1 starts 67% rested, 42% on a back-to-back | §3 | yes — a goalie state carried by the player, and the expected starter |
| 3 | **Home ice** | +0.23 goals, 53.7%; fitted, slowly varying | §3 | yes |
| 4 | **Special teams** | PP and PK as their own states, times expected penalty minutes | — | yes |
| 5 | **Between-season regression** | shot share YoY 0.65, goal share 0.55 | §3 | yes |
| 6 | **Rest / back-to-back** | −0.3 goals, −6 points, part of it the goalie | §3 | yes |
| 7 | Empty net and overtime | the outcome layer, not a strength term | §3 | yes, in the grid |
| 8 | Skater injuries and line changes | through TOI and shift charts; diffuse | shifts | v2 |
| 9 | Travel and time zones | unmeasured here; small in the literature | — | measure in step 2 |
| 10 | Arena scorer bias | shots ±5%, hits up to 30% | §3 | props only |
| 11 | Referee, schedule density beyond back-to-backs, trade deadline | low prior | — | no |

**The goalie deserves its own state,** as the quarterback did: a team's
defence net of the goalie (the shots and expected goals it allows) plus a
goalie state carried across teams and seasons, measured in goals saved above
expected per shot and shrunk hard (reliability 0.31). On game day the model
prices the expected starter; when the starter is confirmed, the price
updates.

---

## 5. Game model, v1

**State.** For each team *i* and game *t*: `xgf_it`, `xga_it` (5-on-5
expected goals for and against per 60, above average), `pp_it`, `pk_it`
(expected goals per 60 on the power play and short-handed), and for each
goalie *k*: `gsax_kt` (goals saved above expected per shot).

**Process.** As the NFL's: a slow random walk within a season, with process
noise tuned small (the prior half-life is ~25 games), and between seasons
`x_{i,1} = φ·x_{i,last} + η`, φ fitted (expect ~0.65 on shot share). The goalie
state regresses harder.

**Observation.** Each game's expected goals, from Atlas's own model on the
play-by-play (distance, angle, shot type, rebound, rush, strength state,
empty net; logistic), by strength state and time on ice. The plan was to fit
it once on 2010–19 and check it on 2020–26; the check found the NHL's
tracking changed under it (from 2021–22 twice the recorded rebounds and
attempts inside ten feet, each converting less often), and a fixed fit
drifted to 0.88 goals per expected goal by 2025–26. So each season's model
is fitted on the three seasons before it: point-in-time, within 0.95–1.05 of
the goals in every season (`reports/nhl_xg.md`). Goals are a second, noisier
channel; expected goals are the primary one, the way EPA was tested for the
NFL.

**Expected goals for the game.** For the home side,
`λ_h = base + xgf_h − xga_a + PP/PK terms × expected penalties − gsax(starter_a) × shots + HFA − rest`,
and the away side's alike, in regulation.

**Distribution — the grid.** A 12×12 grid of final scores built in three
layers, each fitted on the training seasons' own games:

1. Regulation goals, a bivariate Poisson with the measured small negative
   correlation, reweighted for score effects.
2. The empty net: the probability of a pulled goalie when a side trails by
   one or two late, and the empty-net and six-on-five goal rates behind it,
   moving mass from one-goal to two- and three-goal margins (and adding to
   the total).
3. Overtime: tied regulation games go to three-on-three for five minutes
   (a sudden-death goal, split near 51/49) and then the shootout (51.6/48.4),
   each adding exactly one goal to the winner.

**Output per game.** Expected goals to two decimals for each side, P(home)
including overtime, the regulation three-way, P(overtime), the puck line
both ways, the total at 5.5 and 6.5 and the most probable exact scores. The
card is the football card: the same renderer, tiers and audited copy, the
DraftKings line from ESPN beside Atlas's number, and a grade fitted from the
NHL's own walk-forward record.

**What v1 does not do.** No line combinations, no in-game skater injuries,
no travel term until it is measured.

---

## 6. Player props

Two layers, built in this order, because the first is days of work and the
second is weeks.

### v1 — the market's fair value (the football pick'em, pointed at hockey)

The Pick'em engine (`atlas/owner/pickem.py`) already does this for football:
every sportsbook's two-sided price on a player prop, margin out, moved to
PrizePicks' line along the stat's shape, the median across books; slips
optimised under the payout table; a sealed record graded from the box score.
For the NHL it needs:

- the NHL prop slugs (shots on goal, points, goals, assists, saves, blocked
  shots, power-play points) and the owner board's NHL game markets;
- count shapes as measured in §3: shots a negative binomial with
  variance/mean 1.1, blocks 1.1, hits 1.2, points and goals Poisson, saves a
  negative binomial at ~2 around the *game's* projected shots against;
- grading from the NHL API's box score, keyed by the NHL game id, mapped to
  ESPN's.

### v2 — Atlas's own projection

For each skater, before each game:
`E[shots] = projected TOI by strength × shots per 60 (shrunk to position and role) × opponent shots-against factor × arena factor × game script`,
with TOI from the last games and the power-play unit (reliability 0.99),
the rate shrunk toward the player's role (0.87), the opponent and the script
from the game model. Goals are shots × a heavily shrunk shooting percentage
(0.46). Points are the team's projected goals × the player's share of the
goals scored while the player is on the ice. Saves are the start probability × the
opponent's projected shots on goal × (1 − save rate). Hits and blocks carry
the arena term.

Shown beside the market's fair value, never instead of it, until the
walk-forward says it is better.

---

## 7. Validation — NHL specifics

Foundation §6 applies. NHL additions:

- **Fit 2010–11 to 2016–17, tune 2017–18 to 2019–20, report 2020–21 onward.**
  Never report a season used for tuning. The market benchmark covers the
  reporting window through 2021–22 now, and through 2025–26 if §2's gap is
  filled.
- **Scores:** log loss and Brier on P(home) including overtime; ranked
  probability on the regulation three-way; CRPS on the goal margin and the
  total; calibration of the puck line and of the total at 5.5 and 6.5.
- **The goalie test.** Score the model separately on games the team's #1 did
  not start. If the goalie state works, the model's loss there is no worse
  than elsewhere.
- **The prior test.** Games 1–20 against the rest, as the NFL's weeks 1–3.
- **Props:** calibration of P(over) at the common lines (shots 1.5/2.5/3.5,
  saves 24.5–27.5, points 0.5) against a Poisson-on-the-season-mean baseline,
  walk-forward on 2022–25 player-games; against the market only on the prop
  lines Atlas captures from opening night.

### Success criteria

| Score, moneyline incl. OT | Naive | Elo | Goals-Poisson | **Target v1** | Market |
|---|---|---|---|---|---|
| Brier, 2010–22 pooled | 0.2482 | 0.2408 | 0.2411 | **< Elo: 0.2388** | 0.2385 |
| Brier, 2021–22 | 0.2483 | 0.2309 | 0.2312 | **< Elo: 0.2276** | 0.2256 |
| Brier, 2020–26, every game | 0.2487 | 0.2367 | 0.2373 | **< Elo: 0.2343** | — |

Elo is walk-forward from 2010–11 (K 6, 30 Elo points of home ice, 30% back
to the mean each summer, tuned on 2010–17); the goals-Poisson model is each
team's exponentially weighted goals for and against in a Poisson grid
(`reports/nhl_benchmarks.md`). Elo closes three quarters of the way from
"home, always" to the market.

**v1 is done when it beats Elo and a goals-based Poisson team model on
every row out of sample.** It does, in every season from 2020–21 to
2025–26 (the narrowest 2023–24: 0.2339 against Elo's 0.2341), and it comes
within 0.0003 of the closing line pooled over 2010–22 and 0.0005 in 2020–21. Matching the market is v2's ambition, as it was
for the NFL. The market's lead over "home, always" is one hundredth of
Brier; a model that closes a fifth of it is doing well.

---

## 8. Build order

| Step | Work | Output |
|---|---|---|
| 0 | **Capture first.** ESPN's NHL scoreboard in the poll (DraftKings line, results) and BettingPros' NHL game lines and props in the owner capture, sealed like football's, with a counts-only log of the slugs, books and PrizePicks coverage. `atlas/sources/nhl.py`: the game list, team, goalie and skater game logs, trimmed play-by-play and shift charts, 2010–11 on, cached once (`make nhl-ingest`); the odds archive, 2010–22; the ESPN event id for every NHL game | **done** — capture live from 30 September 2026 (the five opening-night closes of the 29th missed); raw cache 2010–11 to 2026–27: 22,052 games, 19,197 of play-by-play, 736,638 skater-games, the archive's 15,206 games (15,205 matched), ESPN ids for every played game; 52 MB; the heavy run adds the season in progress and fills history newest first, twelve minutes at most (`make nhl-ingest`) |
| 1 | `atlas/staging/nhl/`: games, team-game shots and goals by strength, goalie-games with the starter, skater-games, point-in-time features, through the college modules (`make nhl-warehouse`) | **done** — `data/warehouse/nhl.duckdb` (28 MB; every shot attempt staged to `data/staging/nhl/`); reproduces §3, the handful of first measurements that differed corrected in §3 (`reports/nhl_profile.md`) |
| 2 | Expected-goals model; benchmarks: naive, Elo, goals-Poisson team model, market (`make nhl-benchmarks`) | **done** — xG fitted a season at a time on the three before it, AUC 0.76, 0.95–1.05 goals per xG every season; Elo 0.2408 pooled 2010–22, 0.2309 in 2021–22; goals-Poisson 0.2411, 0.2312 (`reports/nhl_xg.md`, `reports/nhl_benchmarks.md`) |
| 3 | Kalman state, 5-on-5 expected goals for and against plus special teams, carried across seasons | **done** — 5-on-5 and special-teams states, and a finishing state (goals over expected goals, shrunk hard) the plan did not have: without it the model trailed Elo, with it it leads; the observation is expected goals six parts to unblocked attempts four, tuned |
| 4 | Goalie state and the expected starter (rest, back-to-back, the confirmation when it comes) | **done** — the goalie state and the expected starter; the goalie test passes (no worse when a usual starter sits); pricing the confirmed starter instead changes Brier by 0.0002, so the goalie state is small, as its reliability (0.31) said it would be |
| 5 | The grid: regulation, empty net, overtime; puck line and totals calibrated | **done** — every layer fitted on the three seasons before the one it prices (the empty net moved: 0.30 goals a game in 2010–11, 0.55 by 2024–25), plus a fitted stretch of the teams' gap; the §7 table met (`reports/nhl_model.md`) |
| 6 | Wire into the card and grade (`nhl.html` board, the live and site layers take a third sport), the owner board, parlays and the exchanges (Kalshi and Polymarket list NHL games) | NHL cards; the audit passes |
| 7 | Props v1: the Pick'em engine on NHL slugs, with §3's shapes, graded from the NHL box score | a Pick'em slate on NHL nights |
| 8 | Props v2: Atlas's player projections, walk-forward | shown beside the market when it earns it |
| 9 | Curated NHL plays: rules pre-registered on the walk-forward before any is logged, as the football rules were | only if a rule clears its bar |

Steps 0 and 7 reuse code that exists and can run within days of a go-ahead;
steps 1–5 are the NFL's steps 0–5 again, weeks rather than days. Nothing
reaches the public site until step 5's table is filled in and passes.

---

## 9. What the owner needs to decide

- **Historical closing lines for 2022–23 to 2025–26:** buy The Odds API's
  history, or let the BettingPros partner key's depth be measured first. The
  model can be built and benchmarked against Elo without it; the market row
  for recent seasons cannot.
- **PrizePicks' NHL payouts:** the same table as football's is assumed; a
  state that pays differently changes `PAYOUTS`.
- No new credentials: the NHL API and ESPN are keyless, and BettingPros is
  already configured.

---

## 10. Risks, stated plainly

- **There may be little room.** The closing line's lead over "home, always"
  is 0.010 of Brier. A model between Elo and the market is an honest product;
  "we beat Vegas" is not a claim this plan expects to make.
- **The goalie is announced late.** Starters are often confirmed at the
  morning skate or warm-ups; a number published the night before prices an
  expected starter and must say so, and move when the starter is known.
- **The NHL's API is undocumented** and was reshaped in 2023; endpoints can
  change without notice. Cache everything once and fail soft.
- **Scorekeepers drift.** Arena factors are refitted each season; a new scorer
  can move a building's hit count overnight.
- **The season is under way.** Building in season means the first weeks of
  cards, if any, run on a model with no in-season record; the prior's slow
  handover (§3) makes that less costly than in football, not free.
- **The odds archive is personal-use.** It is cached, used for the benchmark
  and never republished.
