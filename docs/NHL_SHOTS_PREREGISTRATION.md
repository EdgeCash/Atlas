# NHL shots on goal: pre-registration of the test against PrizePicks' lines

Frozen 1 October 2026, before the first NHL line of 2026-27 was logged. The
same ledger, scoring and bars as the saves test
([`NHL_SAVES_PREREGISTRATION.md`](NHL_SAVES_PREREGISTRATION.md)); this
registers the shots verdict, at its own size, and says why the size differs.
Code: `atlas/owner/ledger.py`. Record: `tracking/owner_prop_ledger/`.

## Why a separate size

On the walk-forward, Atlas's shots projection beat a Poisson on the player's
season mean by about two percent of Brier (`reports/nhl_props.md`: 0.2112
against 0.2163 at 1.5, 0.1547 against 0.1580 at 2.5), where saves beat it by
about ten. Against the books' fair probability, which already prices the
matchup and the line, the edge to expect is smaller still: a paired Brier
difference of a few thousandths at most. A paired difference of 0.006 with
the usual line-by-line spread of about 0.10 needs roughly a thousand lines
for its 95% interval to clear zero; 300 would detect only an edge the
walk-forward gives no reason to expect.

Shots lines are plentiful: PrizePicks posts them on most regulars, ten to
fifteen a game, so a thousand decided lines is two to three weeks of the
season.

## The verdict

Scored exactly as saves: per line, the books' fair probability, Atlas's, and
0.50, on the logged side; Brier, log loss, the paired difference with its
normal 95% interval, and each side's hit rate. Judged at **1,000 decided
shots lines with an Atlas probability** and not before:

- **Clears** when all three hold: Atlas's Brier below fair's with the paired
  95% interval entirely below zero; below 0.25; and Atlas's side hitting
  57.7% or better, PrizePicks' two-pick Power break-even.
- **Fails** when Atlas's Brier is not below fair's at 1,000, or not below
  0.25 at 2,000.
- **Not proven** otherwise, judged again at 2,000.

## What the walk-forward predicts

Atlas's Brier within 0.003 of fair's either way, and the bet-shaped bar
(57.7% on Atlas's side) is the one most likely to be missed: a shots line is
set close to the median, so neither side is often far from a coin flip, and
the hit rate the bar asks for is a high one for this stat. A clear says the skater state carries something the books do not
price by 10:00 ET; a fail says it does not, and both are useful, since
shots lines are where a pick'em slip is most often built.

## What is not tested

As for saves: the line at the moment a slip is placed rather than at 10:00
ET, and whether fair itself beats the coin flip (shown, not judged). Points,
goals, assists, blocked shots and hits are scored and shown beside these two
with no verdict registered; a rule on any of them would need its own.
