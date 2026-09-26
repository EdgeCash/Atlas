# Curated plays: how they work

From 26 September 2026. The owner page's curated plays are the small set of
college totals Atlas commits to each week, logged before kickoff and graded
two ways. This is the operating description; the audit that led to it is
[`CURATED_PLAYS_AUDIT.md`](CURATED_PLAYS_AUDIT.md). Code:
`atlas/owner/plays.py`.

## The week, in order

1. **Every day at 04:00 ET** the heavy run re-fetches the season in
   progress (schedule with results, play-by-play, team file, the lines
   file), rebuilds the warehouse, carries the college state through every
   game played so far, and publishes a projection for every scheduled game.
   Each projection carries the kickoff wind it assumed, from Open-Meteo's
   forecast for games inside eight days, zero indoors, and the training mean
   where there is no forecast yet.
2. **Every poll** (hourly; every fifteen minutes on game days) captures the
   DraftKings line and both prices for every game, then runs the plays step:
   log anything a rule chooses now, grade every play whose game has started
   or finished, and seal the owner page's plays box.
3. **Saturday, the first poll at or after 10:00 ET**, rule v3 chooses the
   weekend's five plays: among college regular-season games still to kick
   off, the five with the largest gap between Atlas's total and the
   DraftKings total, Atlas's side, one flat unit each, at the line and price
   quoted at that moment. They are sealed into `tracking/owner_plays/` and
   never changed.
4. **Sunday through the week**, the polls grade them: win, loss or push on
   the final score at the price taken, and closing-line value against where
   DraftKings closed. The heavy run rebuilds the rule's history from the
   current model's walk-forward, so the history beside the record is always
   the history of the model that chose the plays.

## The rules

Three rules run side by side. Each is frozen: a change is a new rule with
a new id and a record that starts the day it is frozen.

| Rule | Chooses | When | Record starts |
|---|---|---|---|
| `cfb-total-top5-sat10-v3` | the weekend's five largest gaps | the first poll at or after 10:00 ET Saturday | 26 Sep 2026 |
| `cfb-total-top5-v2` | the week's five largest gaps | the first run on Saturday (the 04:00 ET rebuild) | 25 Sep 2026 |
| `cfb-total-5-v1` | every game with a gap of 5+ points | the first run at which it qualifies, up to 8 days out | 24 Sep 2026 |

v3 is the rule the plays are chosen by going forward. v2 keeps running:
the same five games chosen six hours earlier, at Friday night's line,
measure directly what the earlier line costs. v1 keeps running as the
threshold rule it was.

Thursday and Friday games are not in v2 or v3. A play with no captured
price is graded at -110 and marked.

## What is logged with each play

The line and price of the side taken, Atlas's total and the gap, the
opener and how far the line had already moved against Atlas's side, the
model version, the moment it was chosen, and each side's expected
quarterback with his status in the latest SEC or ACC availability report.
The starter and line-movement flags are labels, recorded so they can be
tested against the record; neither is a filter.

## How the plays are graded

**On the score.** Win, loss or push at the price taken. The live record
shows graded, won-lost-push, win rate with its 95% range, break-even at the
prices taken, units and per-play return. Nothing is called until 100
decided plays; proving a rule that truly wins 54% takes about 2,400.

**On the close.** Every play is graded against its book's close: the last
DraftKings total captured before kickoff. CLV is the points the close sat
past the line taken, on Atlas's side; positive means the market moved
toward the play after it was logged. The same is read in win probability
through the prices at both ends (`atlas/live/probability.py`). The page
shows beat-push-lost the close, the beat rate, and mean CLV in points and
in probability. A play that beats the close was a good play whether or not
it won, and on five plays a week that is the record a season can read.

**The splits.** Graded plays are split by the line-movement flag (moved two
or more points against Atlas by the close) and by the starter flag.

## The history beside each rule

Two tables, labelled for what they are.

*History, current model* is the rule applied to `tracking/calibration.csv`,
the current model's walk-forward against the closing total over the
regular seasons since 2021, rebuilt on every heavy run. For a weekly rule
it takes each week's largest gaps among Saturday games. It changes when the
model changes, which is the point.

*History before the freeze* is the record v1 and v2 were frozen on. It was
measured on an earlier version of the model by a script that is not in the
repository, is shown as frozen, and is not relied on. v3 has none: its
history is only ever the current model's.

## What the owner page shows

One passphrase opens two boxes: the curated plays (built by every run) and
the DFS lineups (built by the heavy run). The plays come first, one section
per rule with v3 at the top: this week's plays with the time they were
chosen, the live record, the record against the close, the two splits, the
latest graded plays with their close and CLV, and the two histories. Every
word is inside the ciphertext; the page's script holds none of it.

## What changed on 26 September 2026

- The college season's results were fetched once and never again
  (`atlas/util.download` serves any existing file; the workflow restores
  the cache). Every projection from 24 to 25 September came from a state
  that had assimilated the same 157 games. The season in progress is now
  re-fetched on every heavy run (`atlas/ingest.py`), and the drift monitor
  alarms when the state has not moved after a game day.
- Plays were logged only inside the heavy run's DFS step, ninth of eleven,
  at whatever hour the run landed. They now have their own step, in every
  run, and their own sealed box.
- The rules' history was a set of constants. It is now rebuilt from the
  model's own walk-forward on every run, and the constants are shown as
  frozen.
- Plays were graded on the score alone. They are now graded against the
  close as well, in points and in probability.
- The live total carried no wind term for outdoor games; the backtest had
  the observed kickoff wind. Scheduled games now carry a forecast.
- The card projections were not written when the tracker's separate
  number-maker produced no rows. They are written first now.

## What is still missing

- A second book. Every line is DraftKings, through ESPN's scoreboard, which
  returns no other provider. A timestamped second source (a sharp book or
  a consensus) is the roadmap's top item and needs a key or an account.
- Quarterback availability beyond the SEC and ACC, and a decision on
  whether the expected starter becomes an input rather than a label.
- A full line timeline. Snapshots are append-on-change, so the record says
  a total moved and roughly when, not the minute.
- A season's worth of graded plays before any of the records says anything.
