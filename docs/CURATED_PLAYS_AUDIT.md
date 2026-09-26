# Curated plays: audit

26 September 2026. What the owner page's curated plays are built from, what
is measured, and what is missing. Every number below is from the committed
record (`tracking/`), the reports, or the code as of commit `34df7cb`.

**Status, same day.** The findings marked *fixed* below were addressed in the
commits that followed the audit; how the plays work now is in
[`CURATED_PLAYS.md`](CURATED_PLAYS.md). The numbers in this document are
left as they were measured.

| Finding | Status |
|---|---|
| 3.1 The college model is not learning this season's results | fixed: the season in progress is re-fetched on every heavy run; the drift monitor alarms when the state has not moved after a game day |
| 3.2 The rules' history cannot be reproduced | fixed: each rule's history is rebuilt from `tracking/calibration.csv` on every run; the frozen constants are shown as frozen |
| 3.3 The gap is mostly a regression-to-the-mean bet | open: a property of the model's calibration, stated on the page's history rather than changed |
| 3.4 Backtest and live are different bets | partly fixed: the live total now carries a kickoff wind forecast; rule v3 chooses at a fixed Saturday-morning poll; the line and price differences remain and are now measured (v2 beside v3, and CLV) |
| 3.5 One book, captured at the wrong hour | partly fixed: plays are chosen at the first poll at or after 10:00 ET Saturday, from every poll, independent of the rebuild; still one book |
| 3.6 Information the market has and Atlas does not | open: wind is now forecast; quarterbacks, a second price and the line timeline are not |
| 3.7 Grading is thinner than the tracker's | fixed: every play is graded against its book's close, in points and in probability |
| 3.8 Operational state of the record | as it was; the record starts accumulating from here |

The question asked: we do not need a system that beats the market on every
game. We need one that picks a small number of plays each week, logs them
before kickoff, and grades only those. What information are we lacking to
make those picks as good as they can be, and to grade them honestly?

## 1. What exists today

Two frozen rules in `atlas/owner/plays.py`, both college totals, both
using the card model's projected total (`total_mean` in
`tracking/projections.csv`) against the DraftKings total ESPN's scoreboard
quotes:

| Rule | Frozen | Selects | Logged when |
|---|---|---|---|
| `cfb-total-5-v1` | 24 Sep | any regular-season game where the gap is 5+ points | the first daily heavy run at which it qualifies, up to 8 days before kickoff |
| `cfb-total-top5-v2` | 25 Sep | the week's five largest gaps, one set a week | the first heavy run on Saturday (Eastern), about 04:00 ET |

Each play stores the line, the price of the side taken, Atlas's total, the
opener, how far the line had already moved against Atlas, and the expected
quarterbacks' availability status (SEC and ACC only). Plays are sealed with
the owner key into `tracking/owner_plays/` and graded win, loss or push on
the final score at the price taken (or at -110 when no price was captured).
The record is shown only inside the owner page's ciphertext. Two weeks are
sealed so far (2026 weeks 4 and 5).

The mechanics are sound and well tested: 20 tests in
`tests/test_owner_plays.py`, `test_owner_paper.py` and
`test_owner_starters.py` pass. A play is logged once and never revised, the
seal is checked on every write, and the rules are pinned by tests that fail
if their definition or history is edited.

## 2. The verdict in one paragraph

The plumbing is good. The inputs to the picks are not. The college model
that produces the gap has not learned a new result since the season file was
first downloaded, the gap it produces is mostly a bet that the total will
regress to the league average, the backtest the rules were frozen on cannot
be reproduced and was run on a different model, and the live line comes
from one retail book captured at 4 AM. None of that is visible on the owner
page, which reports the rule as a "lead, not a proven edge". It is closer to
untested.

## 3. Findings, most important first

### 3.1 The college model is not learning this season's results

The Kalman filter's only in-season observations are final scores from
`data/raw/schedules/cfb_schedules_2026.parquet`. That file is fetched by
`atlas/util.py:download`, which returns immediately when the file already
exists, and the workflow restores `data/raw` from the Actions cache before
every run (`.github/workflows/publish.yml`, "Restore the warehouse"). Nothing
in the codebase re-fetches the current season's schedule. The NFL side does
(`nflverse.fetch_schedules(refresh=True)`); college does not.

Evidence in the record: every college refresh from 24 September 01:15 UTC
through 25 September 21:12 UTC assimilated exactly the same 157 games (314
team-games across 138 teams, at most 4 per team). No team's game count moved
in two days. In week 4 the state behind every projection is the preseason
prior plus results through about 19 September, and it will stay that way
until the cache is invalidated or the fetch is changed.

This is the single most important gap. A totals model that stops updating
in week 3 is a preseason prior wearing a live label, and every gap it
produces from here on is against a market that has watched three more weeks
of football.

What would fix it: re-fetch the current season's schedule (and play-by-play,
which feeds the pace term) on every heavy run, and add a freshness check
that fails the run when the assimilated count has not moved after a
Saturday. `model_version` already includes the assimilated count, so the
symptom is cheap to alarm on.

### 3.2 The rules' history cannot be reproduced, and was measured on a different model

The five-season records in `plays.HISTORY` (v1: 526-460-12 against the
close; v2: 208-152-5) exist only as constants. No script in the repository
or its git history computes them, and no document records the "ten weekly
variants" v2 was chosen from. The tests pin the numbers; they do not
re-derive them.

The model changed four times in the 24 hours after v1 was frozen
(correlated home/away noise, Joseph-form covariance, pooled p0, and "the
filter learns from every FBS game, not only priced ones"), and the
projection's `model_version` has taken nine values across eight refreshes.
"A rule is fixed before the games it selects, and never tuned after" is true
of the rule's threshold. It is not true of the number the threshold is
applied to.

The current model's own walk-forward, which the heavy run writes to
`tracking/calibration.csv` every day, gives a check. Regular season, totals,
against the close:

| Season | Gap 5+ (v1) | Weekly top 5 (v2 proxy, all days) |
|---|---|---|
| 2021 | 133-141, 48.5% | 37-34, 52.1% |
| 2022 | 115-120, 48.9% | 45-26, 63.4% |
| 2023 | 113-100, 53.1% | 35-35, 50.0% |
| 2024 | 88-49, 64.2% | 54-22, 71.1% |
| 2025 | 63-42, 60.0% | 42-34, 55.3% |
| All | 512-452, 53.1% | 213-151, 58.5% |

Both rules sit at or below break-even (52.4% at -110) in three of five
seasons and are carried by 2024, the one season in which Atlas's total
matched the market's CRPS (9.083 against 9.084, `reports/ncaaf_total.md`).
The hit rate by gap size is flat: 5-6 points 53.4%, 6-7 52.3%, 7-8 51.6%,
8-10 52.9%, 10+ 56.2% on 121 games. A larger gap is not a better play.

What would fix it: a script (`atlas/research/curated_rules.py` or similar)
that rebuilds both rules' history from `calibration.csv` on every heavy run,
so the "History before the freeze" table on the owner page is the current
model's walk-forward rather than a constant, and the ten variants are on the
record.

### 3.3 The gap is mostly a regression-to-the-mean bet

The total is a calibration of the state model's total with a fitted slope of
0.52 to 0.69 on the state (0.591 for 2026) and an intercept of 34 to 83
points. The published totals are therefore compressed toward the league
mean: on the current slate their standard deviation is 3.5 points against
4.8 for the line, and the gap correlates -0.70 with the line's level. When
the line is 47 or lower Atlas is on average 4.1 over it; at 58 or higher,
2.4 under.

So the rules largely select "over on low totals, under on high totals". That
is a coherent hypothesis (the market over-extends extreme totals), but it is
not the hypothesis the rules describe, and it is one the market prices
directly. The model's own line calibration says how much of a gap is real:
`over_shrink` is 0.105, 0.163, 0.038, 0.068 and 0.216 for 2021 to 2025, and
0.350 for 2026 (fitted in-sample on 2023 to 2025). Read through it, a
5-point gap is worth about 50.5% to 54.4% depending on the season, and a
break-even play in four of six.

### 3.4 The backtest and the live plays are different bets

| | History was measured on | Live plays use |
|---|---|---|
| Line | median closing total across sportsbooks, no timestamp | one book (DraftKings), the last capture before about 04:00 ET |
| Price | -110 assumed | the captured price of the side taken (from 24 Sep; -110 assumed before) |
| Wind | observed wind at kickoff from Meteostat, coefficient -0.14 to -0.19 per mph, 89% coverage | none. A scheduled game has no observation; NaN fills to the training mean, so the term is zero. On the current slate 2% to 5% of games carry any wind term, all domes |
| Games | every regular-season game, Thursday to Saturday | v2: Saturday games only |
| Gap | the calibrated regression mean | the joint grid's mean, after the points lattice and the 0-79 bound |
| Model | whatever version ran the backtest | a version that has changed nine times in three days |

Each of these is stated somewhere in the code or docs. Together they mean
the frozen history is not the history of the thing being logged.

### 3.5 One book, one feed, captured at the wrong hour

ESPN's scoreboard returns exactly one provider, DraftKings, for every
college game (verified live today: 65 events, 65 DraftKings, 0 others).
Every snapshot and every play is against that one number. There is no
Pinnacle, Circa or consensus, so there is no way to know whether DraftKings
is off the market or the market is off Atlas. In the historical CLV study
(`reports/clv_economics.md`) DraftKings was the weakest book measured:
beat rate 50.3% on 675 games against 58% to 62% at Bovada and ESPN Bet.

Timing: plays are logged only in the heavy run, which is scheduled for
04:00 ET but landed after 09:00 ET on 24 and 25 September, and was also
forced by hand more than a dozen times on 24 September. v1 logs at
whichever of those runs first sees a 5-point gap, up to 8 days before
kickoff. v2 chooses at about 04:00 ET Saturday, four hours before the
Saturday poll window opens and before most of the week's late money. A
delayed Saturday run past a noon kickoff drops that game from the week's
five.

Two structural risks follow from the sequencing: `ops heavy` stops at the
first failed step, and the plays step is ninth of eleven, so a failure in
the college box-score fetch (which took 23 minutes on 25 September) means
no plays that day; and `live.refresh` returns before publishing projections
if the separate ridge "numbers" model produces no rows.

### 3.6 Information the market has and Atlas does not

The research programme's own conclusion, four phases running, is that every
variable Atlas can reach is priced. The live record already shows what that
looks like on a slate: 17 of the 90 totals captured this week moved 4 or
more points off the opener, and 7 moved 6 or more. The two largest current
gaps under v1 are games where DraftKings has dropped the total 8 and 9
points from the open (Virginia Tech at Boston College, 54.5 to 46.5;
Oklahoma at Georgia, 52.5 to 43.5) and Atlas, which has not moved, reads
both as overs. The rule logs them with a "moved against" label. It does not
ask why the market moved.

What Atlas does not have at the moment it picks:

- **Quarterback and injury status.** The college model has no QB term
  (`reports/ncaaf_qb.md`: a QB state failed to improve the total). A new
  starter's first game misses the forecast by -2.5 points. The availability
  capture reads SEC and ACC conference games only, from a source that will
  not reach the Big Ten or Big 12, and it is a label on the play, not an
  input to the number. Of 137 rows captured, 117 are "Available".
- **Weather forecast.** The backtest used observed kickoff wind. Live there
  is no forecast source, so the term that the backtest credits with -0.14
  points per mph is zero for every outdoor game.
- **The market's own movement.** The opener and the current line are
  captured, but the rule does not use the move, and the record does not
  store enough of a timeline to say when it happened (snapshots are
  append-on-change, about 1.7 per game per day).
- **Pace and efficiency this season.** Play-by-play is cached once per
  season the same way the schedule is, so `adj_pace_sum` is also frozen.
- **Other models' totals.** The "other models" panel fetches FPI, Elo and
  SP+ margins only, none of them a total, and its forward record
  (`tracking/other_models.csv`) does not exist yet.
- **Any second price.** No other book, no exchange, no consensus.

### 3.7 Grading is thinner than the tracker's

The live tracker grades every signal on closing-line value with a
probability conversion (`atlas/live/probability.py`). The plays are graded
on the final score only: `plays.graded` sets `clv` to NaN, and no closing
line at DraftKings is compared to the line taken. So the record can say
whether the plays won and cannot say whether they were good plays, which on
5 plays a week is the only question a season can answer. At 100 decided
plays before the page says anything (`MIN_GRADED`), v2 at five a week
needs about a season and a half; v1 at three qualifying games in this
week's window is similar.

Two smaller grading gaps: the price of the other side was captured only
from 24 September, so earlier plays are graded at an assumed -110; and the
paper tracker on the same page grades the *ridge* model's signals, which is
a different number from the one the plays use, so the two records on the
owner page do not measure the same model.

### 3.8 Operational state of the record

- Live tracking began 22 September. There is no 2026 record before week 4.
- 120 signals, 1 primary, 10 graded; the tracker's own drift monitoring is
  raising two alarms (signal volume -97% week over week; 100% of signals
  from one book).
- `tracking/games.csv` covers weeks 3 to 5 only.
- The other-models step was added on 26 September and has not run.

## 4. What is missing, as a list

Data:

1. A daily re-fetch of the current season's schedule and play-by-play, or
   an in-season score source that is not the cached parquet (ESPN's
   scoreboard, already polled hourly, carries final scores).
2. A second odds source with a sharp book or a consensus, timestamped. The
   roadmap already ranks this first ("highest value, smallest change").
3. A kickoff weather forecast for outdoor games (any NWS or Open-Meteo
   endpoint gives hourly wind for free) so the live total carries the term
   the backtest was scored with.
4. Quarterback availability for the Big Ten, Big 12 and the independents,
   and a decision on whether the QB of record is an input or stays a label.
5. Enough line history to say when a total moved, not only that it did:
   keep every poll's quote, not only changes, for games within 48 hours of
   kickoff.

Model:

6. A reproducible backtest for both rules from `calibration.csv`, rebuilt
   on every heavy run and shown on the owner page in place of the
   constants.
7. A stated rationale for the gap, tested as stated: if the edge is
   "extreme totals regress", test that directly against the line's level
   and stop calling it a model disagreement.
8. A version freeze for the number the rules read: pin `model_version` (or
   the choices file and code) for the season, and treat a model change as a
   new rule the way a threshold change already is.

Process:

9. Log plays at a fixed, stated time relative to kickoff (for example the
   last poll before 11:00 ET Saturday), from the poll rather than the heavy
   run, so a delayed or failed rebuild does not decide the week's plays.
10. Make the plays step independent of the DFS step's success and of the
    ridge model producing rows.
11. Alarm when a heavy run assimilates no new games after a game day.

Grading:

12. Grade every play on CLV at the book it was logged at (the close is
    already computed for the tracker), in points and in probability, and
    show it beside the win-loss record.
13. Record the same play's line at a second book when one exists, so "won
    but got the worst of the number" is visible.
14. Grade the moved-against and QB labels as pre-registered splits with
    sample sizes, not as free text.

## 5. Where to start

In order, each one cheap and each one changing what the record means:

1. **Refresh the season's results daily** (3.1). One-line change in
   `sportsdataverse.fetch_schedules` or a `refresh=True` path like the
   NFL's, plus a cache key that includes the date. Until this is done the
   picks are from a preseason prior.
2. **Rebuild the rules' history from `calibration.csv` on every run**
   (3.2). The data is already written daily; the table on the owner page
   becomes true by construction.
3. **Grade the plays on CLV** (3.7). `closing_lines` and `probability`
   already exist; `plays.graded` needs to call them.
4. **Move logging to a fixed pre-kickoff poll** (3.5). Removes the 4 AM
   line, the delayed-run lottery and the dependency on eight preceding
   steps.
5. **Add a forecast wind term and a second book** (3.4, 3.5). These are
   new sources, so they come last, but the first is nearly free and the
   second is the roadmap's own top item.

None of these changes the frozen rules. They change whether the number
the rules read is current, whether its history is real, and whether the
record can tell a good play from a lucky one.
