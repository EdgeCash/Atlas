# Atlas — Consensus Test, Pre-registration

**Committed before any holdout game was scored.** The git history is the
evidence: this file and the frozen constants in
`atlas/research/consensus_validation.py` land in a commit of their own, and
the scoring code and results come in later commits. When this was written the
warehouse was not on the machine, and no consensus-against-result figure had
been computed by anyone.

The format and the criteria follow `SIGNAL_PREREGISTRATION.md`, so both tests
are judged by the same standard.

---

## The question

Does the consensus of other computer models know something about a college
game's margin that the closing line does not? And, for the owner page's
curated-picks trial, does the consensus agreeing with Atlas make Atlas's
strongest spread disagreements more reliable?

## What this test can and cannot say

- **Spreads only.** The only point-in-time consensus Atlas holds is on the
  margin. Both frozen curated rules (`atlas/owner/plays.py`, v1 and v2) pick
  **totals**, so this test says nothing about them. A totals consensus needs a
  source Atlas does not have (The Prediction Tracker, downloaded by hand) and
  gets its own pre-registration.
- **Owner page only.** Whatever the result, nothing here reaches the public
  site, which publishes no selections (`PRODUCT_VISION.md`).
- **The prior is NO.** Phases 1A–1C found every public variable priced, and
  Elo and FPI are public and widely read. A NO is the expected result, and it
  is still useful: it says the consensus label on the owner page is
  information about the market's inputs, not a filter.

## The consensus (frozen)

Only ratings published **before kickoff** are used (`atlas/staging/ratings.py`):

| Member | Column | Why it is safe |
|---|---|---|
| Elo | `home_pregame_elo`, `away_pregame_elo` | pre-game by construction |
| FPI projection | `fpi_home_win_prob` | ESPN's pre-game projection for that game |

**Excluded:** SP+ and the FPI *rating*. Atlas carries only the previous
season's finals of both, deliberately, to avoid leakage. By week 5 they are
stale, and they are not a consensus of anything current.

Each member is turned into an implied home margin by a map fitted **on the
fitting seasons only**, by ordinary least squares against the actual home
margin:

- Elo: `margin = a · (home_elo − away_elo) + b · home`, where `home` is 1 for
  a true home game and 0 at a neutral site.
- FPI: `margin = s · Φ⁻¹(p)`, with `p` clipped to [0.01, 0.99].

The consensus is the mean of the members available for the game. A game with
neither is excluded.

## Data (frozen)

- **Games:** FBS against FBS, regular season, **week 5 on**, with a closing
  spread. Week 5 on matches the owner page's spreads population
  (`atlas/owner/paper.py`, "College spreads, strongest 10%, week 5 on").
- **Fitting seasons:** 2016–2020. Only the two maps above are fitted here;
  nothing is chosen.
- **Holdout seasons:** 2021–2025, the window every model report uses. Each is
  scored **once**.
- **Coverage rule:** a season enters the fitting set or the holdout only if at
  least one member is present for 80% or more of its eligible games. Coverage
  is checked and reported before any outcome is read; a season that fails is
  dropped and named, never replaced.
- **Atlas's number:** the college state model's walk-forward margin (fitted
  only on seasons before the one it forecasts), as in
  `reports/ncaaf_state.md`.
- **The line:** the closing spread. Pushes are no action.

## Q1: does the consensus know something the close does not? (primary)

Over **all** eligible holdout games:

> `actual_margin − close = β · (consensus − close) + ε`

**Pass:** the lower bound of the 95% bootstrap interval on β is above 0.

This uses every game (about 2,700), so it is the test with the power to see a
small effect. The selection test below is the tradable version and has much
less power.

**Q1b, selection.** Each season, take the 10% of eligible games with the
largest |consensus − close| and take the consensus's side against the close
at −110. The fraction is fixed in advance; no threshold is scanned. It passes
only if **all four** of `SIGNAL_PREREGISTRATION.md`'s criteria hold, with the
seasons count scaled to five:

1. pooled holdout win rate above 52.38%;
2. lower bound of the 95% bootstrap interval on it above 50.0%;
3. at least 4 of the 5 holdout seasons above 52.38%;
4. positive expected units at −115.

## Q2: does agreement make Atlas's spread disagreements better?

Each season, take the 10% of eligible games with the largest
|Atlas − close|, Atlas's side against the close: the owner page's spreads
population. Split it by whether the consensus is on **the same side of the
close** as Atlas (agree) or not (disagree).

**Pass**, both required:

1. the *agree* subset passes all four criteria above; and
2. the agree win rate minus the disagree win rate has a 95% bootstrap
   interval whose lower bound is above 0.

**Power, stated in advance.** This population is about 50 games a season,
about 270 over five seasons, and the agree subset is a part of that. With the
standard error of a win rate near 4 points at that size, only a very large
effect can pass. A NO on Q2 therefore means "not shown", not "not there"; the
owner page's live label (below) is what builds the sample.

## Decisions (frozen)

| Result | What follows |
|---|---|
| Q1 and Q2 pass | Freeze a college spreads rule (**v3**) that takes Atlas's strongest 10% only where the consensus agrees. New id, its own sealed record from the day it is frozen, its history shown beside it and never mixed in. |
| Q1 passes, Q2 fails | The consensus carries information but does not sharpen Atlas's selections. No rule; the label stays. A consensus-only rule would need its own pre-registration. |
| Q1 fails | No rule. The consensus is a label on the owner page and nothing more. |

There is no partial credit, no "promising" and no "with further work". Any
change to what is tested is a new pre-registration with a new file.

## The owner-page label (not part of the test)

Independently of the result, each curated play and each strongest-10% spread
on the owner page may carry the consensus and whether it agrees with Atlas: a
label, never a filter, logged with the play before kickoff and sealed with it.
It changes no rule, and from 2026 on it becomes the forward record for Q2.

## Statistical conventions

As `SIGNAL_PREREGISTRATION.md`: break-even at −110 is 52.38% and at −115 is
53.49%; a win at −110 returns +0.909 units and a loss costs 1.000; bootstrap
of 10,000 resamples by game, percentile intervals, seed **20260926**.
