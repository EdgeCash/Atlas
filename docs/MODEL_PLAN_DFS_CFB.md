# Atlas — DFS Model Plan: college (DraftKings CFB)

Status: **steps 0-4 done** (see §5). The NFL DFS model (`docs/MODEL_PLAN_DFS.md`)
is the template: the same lines, the same walk-forward standard, the same
optimizer and owner page. This plan is what college changes.

---

## 1. What this is

DraftKings' two college salary formats, for the **owner page** first:

- **Classic** (contest type 94): QB, RB, RB, WR, WR, WR, FLEX (RB/WR),
  SUPERFLEX (QB/RB/WR), $50,000 cap, players from at least two games. There
  is no tight end slot (tight ends are listed as WR) and no defense.
- **Showdown Captain Mode** (95): one game, a Captain at 1.5 times salary and
  points and five UTIL, kickers included, both teams required.

The lines are the NFL's: Atlas's own model, no outside projections, the
betting market's team totals as an input (as the NFL model uses them),
lineups only on the encrypted owner page. Public college projections come
only after the model has a live record, and are a separate decision.

---

## 2. What the data is, measured 24 September 2026

- **DraftKings' pools.** The 12-game Classic slate prices 857 players (121
  QB, 180 RB, 556 WR); a Showdown about 70, kickers included. DraftKings
  keeps no history, and there is **no free archive of past college
  salaries** - so, unlike the NFL, there is no salary benchmark for the past.
  Atlas's own capture (step 0) builds one from 2026 on.
- **Player stats.** Atlas's college play-by-play (cfbfastR) is trimmed to
  team-level fields: no player names. Two sources carry per-player games:
  - ESPN's box score, one public call per game (chosen: testable without a
    key, and it carries the field-goal distances DraftKings scores): passing (C/ATT, yards, TD,
    INT), rushing, receiving, fumbles lost, return touchdowns, kicking; ESPN
    athlete ids; field-goal distances from the scoring plays' text. No key;
    about 870 games a season, so a 2014-2025 backfill is about 10,000 calls,
    once.
  - CFBD's `/games/players`, one call per week for every team (the key is
    already a repository secret): about 200 calls for the same backfill,
    inside the free tier if the endpoint is on it - untested, since the key
    is only in GitHub.
- **What college does not have**: targets, snap counts, an official injury
  report or weekly depth charts. The NFL model leans on all four. College
  opportunity has to be read from receptions, carries and yards shares, and
  whether a player plays from whether he has been playing.
- **The game.** Atlas's NCAAF game model projects every FBS game; the
  market's lines are in Atlas's odds history. Both anchor a team's expected
  points, as in the NFL.

---

## 3. Scoring

DraftKings' college scoring is expected to be the NFL's without the
defense (passing yards 0.04 and a 300-yard bonus, touchdowns 4 passing and 6
otherwise, a point a reception, 0.1 a rushing or receiving yard and 100-yard
bonuses, -1 an interception or fumble lost, 2 a two-point conversion, 6 a
return touchdown; kickers as in the NFL Showdown). It is settled the way the
NFL kickers were: Atlas's computed points per game against DraftKings' own
FPPG for every player in the live pools who has played this season.

---

## 4. Model

The NFL model's shape, with college's inputs:

1. **The game**: each team's points as the line implies them (Atlas's NCAAF
   model is walk-forward only from 2021, so the line is the environment).
2. **The role**: shrunk, exponentially weighted shares of the team's
   receptions, receiving yards, carries and passing, and the player's recent
   scoring - from earlier games only.
3. **Whether he plays**: from how recently and how often he has played; a
   transfer's history travels with him.
4. **Kickers**: the NFL kicker model's form on college data.

---

## 5. Build order

| Step | What | Gate |
|---|---|---|
| 0 | Capture DraftKings' college Classic and Showdown slates daily, beside the NFL's (`atlas/sources/draftkings.py`) | **done** — the heavy run's capture now takes both sports; college slates are kept apart from the NFL model's |
| 1 | Source and scoring: the player-game table 2014-2026 from ESPN's box scores (`atlas/sources/espn_cfb.py`), scored with DraftKings' college rules (`atlas/dfs/cfb.py`; `make cfb-players`, `make cfb-scoring`) | Atlas's points per game match DraftKings' FPPG for at least 98% of pool players who have played — **done, gate passes: 1,320 of 1,337 (98.7%)** (`reports/dfs_cfb_scoring.md`); QB 98.1%, RB 98.7%, WR 98.8%, K 100%. DraftKings divides by every game a player appeared in, a stat or not, and a box score lists only games with a stat, so agreement is a total that gives DraftKings' figure over some count of games between the two; the strict subset with a stat line every game agrees 97.9% within 0.1, the rest the size of stat corrections. The rules match the NFL's without a defense, kickers included. No separate backfill workflow: each heavy run fetches up to 2,000 games it lacks, the season in progress first and then the newest seasons back, and the raw cache keeps them - about five runs for 2014-2025 |
| 2 | Baseline: recent form shrunk to position, walk-forward (`atlas/dfs/cfb_players.py`; `make cfb-baseline`) | reported, by position — **done** (`reports/dfs_cfb_benchmarks.md`). The player-game table from 11,700 box scores, 2014-2026: 234,000 player-games, 22,100 players, with each player's position read from his season (DraftKings lists tight ends as receivers; kickers kick), his shares of his team's carries, catches, receiving yards and passes, and trends from earlier games only, carried across transfers. FCS opponents (a team-season under six games in the record) count toward histories but are not scored. Each team's regulars by prior form, 2016-2025 - the bar the model has to clear: CRPS QB 6.35, RB 5.02, WR 4.48, K 2.16; ranking QB 0.340, RB 0.454, WR 0.388, K 0.208 |
| 3 | Model and ranges (`atlas/dfs/cfb_model.py`; `make cfb-model`) | beats the baseline's CRPS at QB, RB and WR (and K), ranges cover 76-84% — **done, gate passes** (`reports/dfs_cfb_projections.md`), each team's regulars 2016-2025. CRPS against the baseline: QB 5.99 vs 6.35, RB 4.79 vs 5.03, WR 4.37 vs 4.49, K 2.07 vs 2.16; ranking QB 0.424 vs 0.340, RB 0.524 vs 0.455, WR 0.451 vs 0.390, K 0.341 vs 0.208; ranges hold 79.5-80.8%; better than the baseline in every season. The environment is the line's implied team points, every season from 2014, from Atlas's odds history (its team codes translated to ESPN's by learning from games where one side's agree; 89-95% of scored games have a line, correlating 0.64 with the points scored). Atlas's own college game model is walk-forward only from 2021 and is not an input |
| 4 | Optimizer: Classic with the SUPERFLEX, Showdown with UTIL (`atlas/dfs/optimizer.py`) | matches brute force — **done.** Classic is now a roster definition (size, position bounds, upload slots, which positions each flexible slot takes), so the NFL's and college's share one program: college is QB, 2 RB, 3 WR, FLEX (RB/WR), S-FLEX (QB/RB/WR), 1-2 QB, 2-4 RB, 3-5 WR, two games at least; the fixed slots take each position's earliest kickoffs and the flexible ones the latest. It matches every eight-player set on four random slates, and the S-FLEX takes a second quarterback when that is best. Showdown takes DraftKings' college slot name (UTIL). The NFL's results are unchanged |
| 5 | College slates on the owner page | decrypts; every college slate listed |
| 6 | Public college projections | a decision after the live record, not a step |

---

## 6. Risks, stated plainly

- **Thinner signal.** Without targets, snaps, injury reports or depth charts
  the college model will be weaker than the NFL's, and the plays-at-all
  estimate weakest of all. The gates are against its own baseline; there is
  no salary to be measured against until Atlas's capture has a season.
- **Many players, little history.** 857 players on one slate, over a hundred
  teams, transfers every year.
- **Undocumented endpoints.** ESPN and DraftKings can change them; each
  capture fails soft.

---

## 7. What the owner needs to do

- Nothing for step 1: the history arrives with the daily heavy runs (about
  five). Running site heavy by hand a few times speeds it up.
