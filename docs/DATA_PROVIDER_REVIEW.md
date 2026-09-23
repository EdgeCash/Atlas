# Atlas — Should BettingPros or FantasyPros Come Over From Velocity?

Reviewed 23 September 2026 against `EdgeCash/Velocity` at its current head.

## The answer

**FantasyPros: no. It has no college football data at all.**

**BettingPros: it has the data, and Atlas cannot use it.** Not a technical
limit, not a cost one — a licensing one.

> **Correction.** An earlier version of this document said neither feed was
> free, on the strength of Velocity's `docs/DATA_PROVIDERS.md` opening *"Three
> paid feeds sit behind the wagering stack."* **That is wrong.** Access is a
> free tier at **5,000 calls a day**, and nothing is billed. That sentence
> reads as "commercial, credentialed feeds" rather than "we pay for these", and
> quoting it as a billing fact was a mistake.
>
> **It changes nothing below.** Cost was never the reason for either answer:
> FantasyPros is ruled out on *coverage* and BettingPros on *redistribution*,
> and a free tier does not grant redistribution rights — free tiers are
> typically more restrictive about republishing, not less.

Capacity is not the constraint either. Velocity's own budget notes put it at
roughly 13 calls a run for game lines and ~240 a day for props — about 5% of
the 5,000/day cap. Atlas polling NCAAF lines would add a trivial amount to
that. **If Atlas could publish this data, there would be plenty of allowance
to fetch it.** It cannot, and that is the whole of the problem.

---

## FantasyPros — ruled out by coverage

From `scripts/collect_fantasypros.py`, verbatim:

> the public v2 API has no NCAAF projections endpoint — see the OpenAPI spec —
> so college projections come from elsewhere

> there is no NCAAF projections path (confirmed against the published OpenAPI
> spec), which is why the college endpoint 404s

And `LEAGUES = ("nfl",)`.

Atlas is college football. FantasyPros publishes NFL, NBA, MLB and NHL fantasy
projections, because that is where fantasy is. There is no overlap to import.
Its value to Velocity is prop inputs for player props, and Atlas has no props.

**Nothing to evaluate.** This one is closed.

---

## BettingPros — it does cover NCAAF

Velocity snapshots `SPORTS = ("NFL", "NCAAF", "MLB")` for game lines, and its
notes record a probe finding NCAAF returns 200 on the props endpoint too. So
college spreads, totals and moneylines are genuinely there, multi-book.

That is a real upgrade over what Atlas reads today. Atlas's market anchor is a
**single book** — ESPN's public scoreboard quotes DraftKings — and the whole
product is built on `w·market + (1−w)·model` with the fitted weight at 1.00 on
spreads. When the anchor is that load-bearing, a multi-book consensus is a
better anchor than one book.

### And Atlas cannot publish it

From the first paragraph of Velocity's `docs/DATA_PROVIDERS.md`:

> they must never write into **git**: provider terms forbid redistributing
> their odds, committing them would leak our edge, and git history is permanent
> and clonable in a way an artifact is not. All paid data lives only in
> **GitHub Actions artifacts**, never in git.

Atlas does all three of the things that rules out:

| Atlas does | BettingPros forbids |
|---|---|
| is a **public** repository | — |
| **commits** market snapshots in `tracking/` on every poll | writing odds into git |
| **publishes the market number on every card** | redistributing odds |

The third is the one that cannot be engineered around, because displaying the
market number *is the product*. A matchup card without it has no anchor, no
disagreement and no grade.

### How firm is this, and who should confirm it

Stated plainly, because the cost claim above was wrong and came from the same
paragraph as this one.

The redistribution restriction is **Velocity's summary of the terms**, not the
terms themselves. I have not read BettingPros' agreement. What raises it above
a single sentence is that Velocity's *architecture* was built around it: paid
payloads go to Actions artifacts and never to git, and there is a dedicated
purge workflow for the one time that discipline slipped. Somebody took this
seriously enough to design for it.

**Before relying on my reading in either direction, check the actual terms of
your BettingPros access.** If they turn out to permit displaying a derived
number with attribution, this answer is worth revisiting — the consensus-line
gain below is real. What should not happen is Atlas publishing the data on the
strength of a summary, in a public repository, with a permanent git history.

### The credential problem, on top

Velocity has a `purge-leaked-bp-artifacts.yml` workflow. Its header records
that BettingPros echoes the request URL — partner key included — inside its
`/props` response, that the collector banked it verbatim into 89 artifacts, and
that **the partner key cannot be reissued.**

Putting that same key into a second repository — a public one — multiplies the
exposure of a credential that has already leaked once and cannot be rotated.

---

## The reason that outranks licensing

Asked again on 23 September, and tracing what the market number actually drives
turned up a stronger answer than the licensing one. Three facts from the code:

**1. The grade is computed from the total alone.** `atlas/site/data.py` grades
a card with `difference = card.total_difference`. The spread never enters a
grade. So the headline benefit of a multi-book feed - a sharper consensus
*spread* - is worth nothing to the thing Atlas sells.

**2. Atlas's published spread already *is* the market spread.**
`MARKET_WEIGHT = {"margin": 1.00, "total": 0.89}`. At a weight of 1.00 the
model contributes nothing to the spread, so a better spread would change a
displayed number and no computed one. The only market figure that drives
anything is the total, at 89% market and 11% model.

**3. The calibration could never be refitted against BettingPros.**
`grade.calibration_curve()` fits `gap(d) = -a * d ** p` over seven seasons of
historical closing lines, refitting on every build because the coefficient
moves about 2.5x across seasons. **BettingPros has no archive** - that is the
stated reason Velocity's collector snapshots the live board at all. So adopting
it would mean grading BettingPros-measured disagreements with a curve fitted on
a different market series, with no way to ever validate or correct the
mismatch. The grade is the product, and an uncalibrated grade is worse than no
grade.

In fairness, a seam already exists: the live feed is ESPN's scoreboard, not
literally the historical closing-line series the curve is fitted on. Adding
BettingPros would widen that seam rather than create it. But the current feed
is the same *kind* of series - one book's closing-ish line - and a multi-book
consensus is not, and the current one can at least be checked against history.

**And there is no failure to fix.** Every recorded live run so far reports
`status: ok`, 142 quotes, zero exceptions. That is one day of history and thin
evidence, so it argues weakly - but it argues against, not for.

---

## What Atlas actually gives up by not taking it

Worth stating honestly rather than pretending the answer is free.

| | |
|---|---|
| **Consensus vs one book** | the real loss. One book's number can be off-market; a consensus is a better anchor and would likely tighten calibration |
| Opening lines | **no loss** — ESPN already publishes open *and* current, which `provider.py` notes is why it was chosen |
| Props | no loss; Atlas has no prop product and `ATLAS_FEATURE_ROADMAP.md` does not want one |
| Line history | no loss; Atlas builds its own by snapshotting, which is what BettingPros requires anyway since it has no archive |

So the gap is one thing, not four: **Atlas anchors to one book.**

### If that gap is worth closing

Two routes that do not involve redistributing anybody's licensed odds:

1. **A second free source for cross-checking only.** Not published, not
   committed — used to flag "our anchor is 1.5 off the market" in the health
   check. That is internal quality control, not redistribution, and it is the
   cheapest real improvement available.
2. **A licence that permits display.** If a multi-book anchor is worth paying
   for, the thing to buy is a feed whose terms allow publishing the number,
   and to ask that question before building against it. Velocity's own
   comparison table is the place to start.

**Recommended: neither, for now.** The market weight is fitted at 1.00 on
spreads against the book Atlas already reads, the calibration curve is fitted
against that same history, and changing the anchor mid-season would invalidate
both. This is a post-season question.

---

## Summary

| | Covers NCAAF? | Usable by Atlas? | Why |
|---|---|---|---|
| **FantasyPros** | **no** | no | no college endpoint exists |
| **BettingPros** | yes | **no** | terms forbid redistributing odds; Atlas is public, commits them, and displays them |

Atlas's current feed carries no licence restriction, publishes both the opening
and current number, and is the feed the model was fitted against. Bringing a
non-redistributable feed into a public repository would add licensing risk and
credential risk — for free, but not for nothing — to fix one thing that is
better fixed after the season ends.
