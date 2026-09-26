# NFL quarterback rule - pre-registration

**Committed before any game was scored.** This file and
`atlas/research/nfl_qb_rule.py` land in a commit of their own; the results
(`reports/nfl_qb_rule_test.md`) come in the commit after. The person running
the test cannot move the goalposts afterwards, and the git history shows it.

## The question

The curated plays are college totals only. The NFL total is a market the
Atlas model does not beat by disagreement: on the current model's
walk-forward, 2020-2025, a gap of three or more points hits 49.7% of 515
against the close, and the weekly top five 48.6% (measured 26 September
2026, before this test was written). The market is sharper and the slate
is a third the size.

What the NFL side has that college does not is the quarterback. The audit
of the curated plays named quarterback availability as the one measured
unpriced factor, and the NFL warehouse carries it before kickoff: the
depth chart's QB1 and QB2 for the week, from the latest snapshot before
kickoff, and whether the QB1 is listed Out or Doubtful on the week's
injury report (`atlas/staging/nfl/build.py`). The NFL projection already
forecasts every game with that expected starter (`atlas/models/nfl_state.py`,
`expected_starter`).

The hypothesis: **in games where a team's expected starter is not the
quarterback who started its previous game, the closing total has not fully
priced the change, and a side can be taken at better than break-even.**

## What is fixed

### The population

NFL regular-season games with a closing total, test seasons **2020 to
2025**, six seasons. 2026 is in progress and is excluded. The walk-forward
is the NFL model's own (`atlas/models/nfl_total.run`, first test season
2020, three tuning seasons, saved hyperparameters): each season is
forecast by a model that has seen only the seasons before it.

### The flags, all pre-kickoff

For each side of a game:

- **expected starter**: the depth chart's QB1 for the week, unless the
  injury report lists him Out or Doubtful and a QB2 is listed, when it is
  the QB2 (`expected_starter`, unchanged).
- **previous quarterback of record**: the passer with the most dropbacks in
  that team's previous game, in the same or the previous season. Known once
  that game is over, so pre-kickoff for this one.
- **change**: the expected starter is known, the previous quarterback of
  record is known, and they differ.
- **QB1 out**: the injury report lists the depth chart's QB1 Out or Doubtful.

A game is a **change game** when either side changes, and a **QB1-out
game** when either side's QB1 is out. A game whose expected starter or
previous quarterback is unknown on both sides is neither.

### The four rules

All at the closing total, one flat unit, regular season only.

| Rule | Games | Side |
|---|---|---|
| Q1 | change games | Atlas's side of the closing total (its mean above the line: over; below: under) |
| Q2 | change games | the under |
| Q3 | QB1-out games | Atlas's side |
| Q4 | QB1-out games | the under |

A game where Atlas's mean equals the line has no side for Q1 and Q3 and is
left out. A game whose final total equals the line is a push: graded,
counted, and excluded from the win rate.

**Control**: games that are neither change nor QB1-out games, Atlas's
side. Reported beside the rules so a rule's number can be read against the
model's ordinary hit rate rather than against 50%.

### The criteria

A rule **passes** only if all four hold on the pooled six seasons:

1. At least **100 decided games** (wins plus losses).
2. Pooled win rate above **52.38%**, break-even at -110.
3. The lower bound of the Wilson interval at **z = 2.24** is above 50.0%.
   That is a 97.5% two-sided interval divided by the four rules tested
   (0.025 / 4 one-sided), a Bonferroni correction for reading four results
   and keeping the best.
4. Win rate above 50% in at least **four of the six** seasons.

Anything else is **not shown**. A rule that clears 1, 2 and 4 but not 3 is
reported as "a lead, not a result", the phrase the curated plays use, and
does not become a rule.

### What happens on each outcome

- **A rule passes**: it is added to `atlas/owner/plays.py` as a new rule
  with its own id, frozen the day the result is committed, choosing at a
  fixed pre-kickoff poll (the flags are the week's, so the choice can be
  made Saturday for Sunday's games; Thursday and Monday games are excluded
  as the college rules exclude Thursday and Friday). Its live record starts
  empty. Nothing about the passing rule is tuned after this test.
- **No rule passes**: the result is recorded in `reports/nfl_qb_rule_test.md`
  and the NFL stays out of the curated plays. The negative result is
  reusable: "quarterback changes are priced in the NFL closing total" is a
  finding.

### What is not being tested

- Line movement. nflverse publishes the closing total only, so no opener,
  no CLV, and no moved-against split. The test is against the close.
- Questionable. Only Out and Doubtful count as out; a Questionable QB1 is
  expected to start. Changing that after seeing the result is tuning.
- Spreads. The curated plays are totals; this test is totals.
- Any threshold on Atlas's gap. Q1 and Q3 take Atlas's side at any gap. A
  gap threshold on top would be a second parameter chosen after the fact.

## Power, stated in advance

Quarterback changes are common: in a 32-team league with injuries,
benchings and rookies, roughly a fifth to a quarter of regular-season games
have a change on at least one side, about 50 to 65 a season, 300 to 400
over six. At that size a true 55% rule has about a 50% chance of clearing
criterion 3; a true 54% rule about a third. So a **not shown** on Q1 or Q2
means "not shown at this power", not "shown to be zero". QB1-out games are
rarer, perhaps 15 to 25 a season; Q3 and Q4 will likely fail criterion 1,
and are included because the injury case is the cleanest version of the
hypothesis and the record should show what it did rather than that it was
not looked at.

## Provenance

- Frame: `data/warehouse/nfl.duckdb`, `research_games`, built by
  `atlas.staging.nfl.build` from the nflverse files fetched 26 September
  2026 (schedules with closing lines, play-by-play, depth charts, injuries,
  rosters, player stats).
- Model: `atlas/models/nfl_total.run` with `reports/nfl_state_choices.json`,
  the same call `atlas/models/nfl_projection.history` makes for the card's
  grade.
- Scorer: `atlas/research/nfl_qb_rule.py`, run once:
  `python -m atlas.research.nfl_qb_rule`.
