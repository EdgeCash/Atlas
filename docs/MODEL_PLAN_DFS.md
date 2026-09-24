# Atlas — DFS Model Plan (DraftKings NFL Classic)

Status: **steps 0-4 done** (see §7). Scope v1: DraftKings NFL Classic,
the Sunday main slate. College (DraftKings CFB Classic) waits on thinner
player data and comes after the NFL model has a record.

This is a new model, not an extension of the game model. The game model
rates teams and quarterbacks; a DFS lineup needs a projection for every
player on the slate, which Atlas has never made. The optimizer that turns
projections into lineups is the small part. The projections are the work,
and they are held to the same standard as everything else in Atlas:
walk-forward, out of sample, against a baseline and against the market's
own number - here, DraftKings' salaries.

**Atlas's own model only.** Decided with the owner, 24 September 2026: no
outside projections (FantasyPros, BettingPros or any other proprietary
model) are inputs. Atlas builds its player model from public data and its
own game model, and is measured honestly against the baseline and against
salary. If it is not up to par, outside projections are revisited - first
as a benchmark, then, for the owner page only, as a blend - and not before.
The betting line is not a projection in that sense: after step 3 showed
the Atlas-only model's gap was the game environment, the owner added the
line's implied team totals as an input (24 September 2026).

---

## 1. What this is, and the lines it holds

Two surfaces, decided with the owner:

**The public DFS area.** A separate section of the site, walled off from
the game cards, with its own disclaimers.

- **The reader decides; the tool arranges.** Atlas publishes each
  player's projection with its range and the model's track record.
  Lineup building (v1.1) works only under the reader's own settings -
  who is locked in or left out, how often a player may appear. There is
  no "Atlas lineup of the week", no featured plays.
- **The numbers carry their record.** Every projection shows its range;
  the model's out-of-sample accuracy is published before launch and
  updated weekly, the way the grade's record is on Research.
- **No promises of winning.** No "optimal" or "winning" lineups, no
  projected returns or ROI, no bankroll or entry-size advice, and the
  site's banned vocabulary applies (the launch audit is extended to the
  DFS pages). What the builder maximizes is stated plainly: projected
  points.
- **Walled off.** The game cards keep their promise that Atlas does not
  publish selections; About and the FAQ are reworded to say that promise
  covers the cards, and the DFS area says what it is. A note on age and
  state availability, and a link to DraftKings' responsible-gaming
  resources, on every DFS page.

**The owner page.** One-tap optimized lineups for the owner's own use, not
offered to readers. The site is static (GitHub Pages) and the repository
is public, so a login in the usual sense is impossible and anything
published in plain text is public. Instead:

- The heavy run builds the lineups, **encrypts** them (AES-GCM, key
  derived from a passphrase held as a GitHub secret, `ATLAS_OWNER_KEY`),
  and publishes only the ciphertext at `dfs/owner.html`.
- On the iPad the owner types the passphrase; the browser decrypts the
  page locally (WebCrypto). Nothing readable is committed or published.
- Honest limit: the code is public and the public projections are on the
  site, so a determined reader could build a similar optimizer. What
  stays private is Atlas presenting a finished lineup - the line the
  owner drew.

DraftKings allows lineup tools but not automated entry: every lineup
leaves Atlas as a CSV in DraftKings' upload format, entered by a person.
DraftKings is named factually and never in a way that implies a
partnership. None of this is legal advice; paid DFS is not available in
every state.

---

## 2. Data - measured, 24 September 2026

| Source | What | Checked |
|---|---|---|
| nflverse `stats_player` release | weekly player stats, 150 columns: passing, rushing, receiving, target share, air yards, WOPR, EPA, defensive stats | 2025 file fetched: 19,422 player-weeks |
| nflverse (already ingested) | play-by-play, snap counts (2012+), depth charts, injury reports, rosters | in `data/raw/nfl` |
| DraftKings lobby (`/lobby/getcontests?sport=NFL`) | every current slate (draft group), its contest type, games and start time | 38 NFL draft groups today |
| DraftKings draftables (`/draftgroups/v1/draftgroups/{id}/draftables`) | the player pool with salary, position, roster slot and DraftKings ids | Classic group (contest type 21): 1,494 entries, all salaried, QB/RB/WR/TE/DST; other formats (showdown, snake) carry no salary |
| RotoGuru archive (`fyday.pl?game=dk`) | historical DraftKings **salary and points** per player-week | 2014-2021 present (350-440 players a week); 2022-2025 empty |

What follows from the table:

- **Salaries are the market.** They exist for 2014-2021 and from the day
  Atlas starts capturing them; 2022-2025 is a gap. The salary benchmark
  (§5) is scored on 2014-2021; the baseline benchmark on every season.
- **Capture starts at step 0**, daily in the heavy run, into the tracking
  store, so the record from 2026 on is Atlas's own.
- **DraftKings' endpoints are undocumented.** They are public JSON and
  answer without a key today; the capture must fail soft and the plan
  must survive a change (§9).

---

## 3. DraftKings NFL Classic, as encoded

Roster: QB, RB, RB, WR, WR, WR, TE, FLEX (RB/WR/TE), DST; salary cap
$50,000; one player once.

Offense: passing yards 0.04 a yard, +3 at 300; passing TD +4;
interception -1; rushing and receiving yards 0.1 a yard, +3 at 100 each;
rushing or receiving TD +6; reception +1; fumble lost -1; two-point
conversion +2; return TD +6.

Defense/special teams: sack +1, interception +2, fumble recovery +2,
return or defensive TD +6, safety +2, blocked kick +2; points allowed
0 → +10, 1-6 → +7, 7-13 → +4, 14-20 → +1, 21-27 → 0, 28-34 → -1,
35+ → -4.

Settled by the record in step 1, not assumed: a fumble lost on a kick or
punt return costs the returner 1; a blocked extra point counts as a
blocked kick, like a punt or field goal; points allowed leave out a
touchdown scored against the team's own offense (a pick-six or fumble
return, removed at 6 points, not 7) and a safety its offense concedes,
while a return touchdown against its kicking or punting unit counts.

**Verified before use**: step 1 computes DraftKings points from nflverse
stats with these rules and must reproduce RotoGuru's recorded DraftKings
points for 2014-2021 on at least 99% of player-weeks to within 0.1. Any
rule the data disagrees with is corrected from DraftKings' published
scoring page, and the check is kept as a test.

---

## 4. Model specification, v1

A player's projection is **opportunity × efficiency, inside Atlas's own
game projection**.

1. **The game environment** comes from the NFL projector already on the
   cards: each team's projected points, and a pass rate and play volume
   from the team's point-in-time tendencies. This is the anchor that
   makes the projections Atlas's rather than a trailing average. Beside
   it, each team's points as the betting line implies them (added after
   step 3; see §7).
2. **Opportunity**: each player's share of his team's snaps, targets,
   carries and red-zone touches, as shrunk exponentially weighted
   estimates over recent games, pulled toward a prior by position and
   depth-chart slot. The injury report and depth chart redistribute a
   missing player's share among the rest.
3. **Efficiency**: yards per target and per carry, touchdown rate per
   opportunity, heavily shrunk to position means - efficiency is mostly
   noise week to week, opportunity is mostly signal.
4. **Quarterbacks** use the game model's quarterback state (EPA per
   dropback, the v1.2 channel) for passing efficiency.
5. **Defenses** from the opponent's projected points, sack rate and
   turnover rate, mapped through DraftKings' points-allowed table.
6. **Output**: each player's mean DraftKings points and a range (10th-90th
   percentile), from component distributions. v1.1 adds the correlations
   between teammates and opponents that stacking needs.

Everything is point-in-time: a projection uses only what was knowable
before that kickoff - the Wednesday-to-Friday injury report, the week's
depth chart, stats from completed games.

---

## 5. Validation

Walk-forward by season (2014 onward as data allows), fit strictly on the
seasons before, scored on regular-season main-slate players.

| Benchmark | What it is | Seasons |
|---|---|---|
| Baseline | the player's trailing average DraftKings points, shrunk to position | all |
| Salary | DraftKings' price mapped to points, fit by position on the training seasons | 2014-2021, then live from 2026 |

Metrics: MAE and CRPS on DraftKings points, by position; coverage of the
80% range; and, for the optimizer, the actual points of the lineups it
would have built.

**Gates.** v1 ships to the public area only if it beats the baseline at
every position and is within reach of salary overall - the same "beat the
floor, approach the ceiling" rule as the game models. The report
(`reports/dfs_projections.md`) states the result either way, and the
public page carries it.

---

## 6. The optimizer

An integer program over the slate's player pool, solved with SciPy's
`milp` (already a dependency): maximize projected points subject to the
cap, the roster slots and one-player-once. Options: no defense facing its
own lineup's offense, stacking rules, a limit on how often a player
appears across a set of lineups, and a minimum number of different
players between lineups. Output: DraftKings' upload CSV (player ids by
slot). Late swap is out of scope for v1.

Tests: every lineup satisfies every constraint on every slate; small
slates are checked against brute force.

---

## 7. Build order

| Step | What | Gate / result |
|---|---|---|
| 0 | Sources: nflverse player stats (2011+); DraftKings lobby and Classic draftables captured daily in the heavy run; the RotoGuru 2014-2021 archive, once (`atlas/sources/nflverse.py`, `atlas/sources/draftkings.py`, `atlas/sources/rotoguru.py`; `make dfs-capture`, `make dfs-history`) | **done** — player stats 2011-2026 cached; first capture 24 Sep: 6 Classic slates, 3,016 salaries (main slate 662 players, 26 defenses) in `tracking/dfs_salaries.csv`; the capture never fails the heavy run; RotoGuru archive 2014-2021 cached, 55,386 player-weeks (6,769-7,489 a season, 17 weeks, 18 in 2021) |
| 1 | Staging: player-game table, DraftKings points from stats, opportunity shares, point-in-time features (`atlas/dfs/scoring.py`, `atlas/dfs/players.py`, `atlas/dfs/reconcile.py`; `make dfs-staging`, `make dfs-scoring`) | **done — gate passes: 99.26%** of 55,386 archive player-weeks agree within 0.1 (99.25% without the 137 matched by points); QB 99.10%, RB 99.44%, WR 99.62%, TE 99.77%, DST 95.64% (`reports/dfs_scoring.md`). `dfs_player_games` 90,224 rows and `dfs_dst_games` 8,256, 2011-2026, in the NFL warehouse; snap share covers 99.7%+ from 2013 (none exists for 2011-12); trends checked to use prior games only |
| 2 | Benchmarks: baseline and salary (`atlas/dfs/benchmarks.py`, `make dfs-benchmarks`) | **done** — `reports/dfs_benchmarks.md`. Among each team's regulars (top QB, 2 RB, 3 WR, TE by salary; every defense), 2015-21: the two are nearly tied. Baseline has the lower error everywhere (MAE QB 6.70 / RB 5.91 / WR 5.98 / TE 5.05 / DST 4.65 against salary's 6.77 / 6.06 / 6.00 / 5.09 / 4.70); salary ranks better at QB (0.330 vs 0.297) and DST (0.243 vs 0.131), level elsewhere. DraftKings' prices hold about what a player's recent scoring holds. Scored on everyone who played, the fringe flatters the baseline; the report shows both |
| 3 | Projection model v1, team-anchored (`atlas/dfs/environment.py`, `atlas/dfs/context.py`, `atlas/dfs/model.py`; `make dfs-model`) | **done — gate passes** (`reports/dfs_projections.md`). 2015-21 regulars, CRPS against the baseline: QB 4.58 vs 4.75, RB 4.14 vs 4.23, WR 4.16 vs 4.24, TE 3.58 vs 3.61, DST 3.25 vs 3.32; rank against salary: QB 0.341 vs 0.330, RB 0.523 vs 0.506, WR 0.493 vs 0.484, TE 0.420 vs 0.403, DST 0.270 vs 0.243. 2022-25 holds the same margins over the baseline. Atlas-only, the model fell short of salary's ranking at QB (0.315) and DST (0.241); the gap was the game environment - the line's team totals rank a team's players better than Atlas's projected points - so the owner added them as an input (24 September 2026). The report keeps the Atlas-only result |
| 4 | Defenses and ranges (`atlas/dfs/defense.py`, `atlas/dfs/ranges.py`; in `make dfs-model`) | 80% ranges cover 76-84% — **done, gate passes.** Ranges are each position's 10th and 90th percentile of the model's own out-of-sample misses, as lines in the projection (fitted separately: DraftKings points are lopsided). Regulars 2015-21: DST 80.0%, QB 81.0%, RB 80.0%, TE 81.2%, WR 79.9% (80.2% overall); 2022-25: 80.1-83.1%; every season 2015-25 between 78.6% and 81.8%. Defenses: expected sacks, takeaways and return touchdowns (Poisson rates on form, the opposing offense and both teams' projected points), league rates for the rare events, and the points-allowed bonus averaged over the opponent's score spread; the published projection averages this with the player model. Rank among defenses 2015-21: 0.274 (salary 0.243); 2022-25: 0.296 |
| 5 | Optimizer and DraftKings CSV | constraints always hold; brute-force check |
| 6 | Owner page, encrypted, in the heavy run | decrypts on the iPad with the passphrase; nothing readable published |
| 7 | Public DFS area: projections with ranges and the record; audit rules; About and FAQ reworded | audit passes |

**Before DFS staging runs in the heavy refresh** (step 6): the GitHub
runner's cached play-by-play for past seasons predates the fields step 1
added (who scored, who recovered, blocked punts), and cached seasons are
not re-fetched. One run with those seasons cleared re-fetches them.

v1.1: the in-browser builder under the reader's settings, correlations
and stacks, late swap. v2: DraftKings CFB Classic.

---

## 8. What the owner needs to do

- Add the repository secret `ATLAS_OWNER_KEY` (a long passphrase) before
  step 6.
- Nothing else until launch; the domain move (see `DOMAIN_STRATEGY.md`)
  is independent.

---

## 9. Risks, stated plainly

- **DFS projections are noisy.** A single player-week has a standard
  deviation near its mean; even good projections are wrong most weeks,
  and DraftKings' rake means most lineups lose money over time. The
  published record will show this, and the page will not hide it.
- **The salary gap.** No free salaries for 2022-2025, so the market
  benchmark covers older football until Atlas's own capture builds up.
- **Undocumented endpoints.** DraftKings can change or close them; the
  capture fails soft, and a manual CSV import is the fallback.
- **Positioning.** The DFS area is gambling-adjacent in a way the cards
  are not. The walls in §1 are what keep the cards' promise true.
- **The public repository.** Code and public projections are visible;
  only the owner page's content is protected, and only by the strength
  of the passphrase.
