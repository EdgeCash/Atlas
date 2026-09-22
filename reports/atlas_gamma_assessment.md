# Atlas Gamma Assessment — Market Movement Monetization (Phase 4)

*Generated 2026-09-22 17:03 UTC by `python -m atlas.research.gamma_report`. All CLV is
measured inside a single sportsbook. Supporting detail is in
[`opening_line_feasibility.md`](opening_line_feasibility.md) (Tracks 1, 3) and
[`clv_economics.md`](clv_economics.md) (Tracks 2, 4). Research only: nothing
here stakes, simulates or recommends a wager.*

---

## The answer, up front

**The signal is real. It is not, on this evidence, monetizable at standard
juice. It is worth instrumenting and not worth betting.**

| Question | Answer |
|---|---|
| Is the CLV signal real? | **Yes** - z = 13.2 on totals within a single book, positive in every season, and Phase 3's placebo tests fail as they should |
| Does it survive execution testing? | **Yes** - the book effect is 0.0005; same-book grading gives 58.8% against the consensus method's 58.9% |
| Is it big enough to bet? | **No** - 0.41 points of CLV on average against the 0.95 points -110 requires |
| Is any subset big enough? | **One** - the loudest 10% of totals signals, at 1.02 points, clears -110 on the point estimate and not on the interval |
| Can the execution window be optimised? | **Unknown** - Atlas holds no timestamped odds and cannot answer Track 5 at all |

**Recommendation: BUILD ATLAS CLV SYSTEM.** Not a betting system. The
reasoning is in the last section, and it carries a kill criterion.

---

## Track 5 — Market timing

**This track cannot be answered and Atlas will not estimate it.**

The brief asks when Atlas beats the close most often: one day before, twelve
hours, six, three, one. Answering requires a timestamped odds archive. Atlas's
feed carries an opening number, a closing number and a kickoff time, and **no
timestamp on either line**. There is no proxy: the number of books quoting a
game is not a clock, and the size of a move says nothing about when it
happened.

What can be said is a bound. Open-to-close is the **whole** window, so every
sub-window sits inside it and the 58.8% measured here is
the total available, not a rate per hour. Whether it accrues in the first hour
after the opener posts - which is what the market structure suggests, since
that is when the number is least informed - or accumulates evenly, is exactly
the thing that is unobservable.

**This is the single highest-value data acquisition Atlas could make**, and it
is the first deliverable of the recommendation below. Candidate sources of
timestamped NCAAF line snapshots, none verified by Atlas:

| Source | Claimed NCAAF history | Note |
|---|---|---|
| [The Odds API](https://the-odds-api.com/historical-odds-data/) | mid-2020 onward | timestamped snapshots with previous/next references |
| [TheRundown](https://therundown.io/) | 2020 onward | line movement archived open to close |
| [ParlayAPI](https://parlay-api.com/historical-coverage) | 2014 onward | odds snapshots and closing lines |

Coverage, granularity, which books are included and cost all need verifying
before any of them is relied on. The requirement is specific: **snapshots at
least hourly, including at least one book that posts openers**, over three or
more seasons.

---

## Track 6 — Market regimes

Where the signal lives, measured on the executable within-book construction:

### Margins

| Regime | Bets | Graded | Beat rate | z | Mean CLV |
|---|---|---|---|---|---|
| All games | 8,146 | 6,656 | 0.5544 | 8.8743 | 0.2820 |
| Season phase: Early (weeks 1-4) | 2,171 | 1,749 | 0.5117 | 0.9804 | 0.0755 |
| Season phase: Mid (weeks 5-10) | 3,465 | 2,918 | 0.5613 | 6.6274 | 0.3446 |
| Season phase: Late (weeks 11+) | 2,414 | 1,908 | 0.5849 | 7.4175 | 0.3950 |
| Profile: most-quoted quarter | 2,261 | 1,908 | 0.5487 | 4.2582 | 0.1796 |
| Profile: least-quoted quarter | 5,885 | 4,748 | 0.5567 | 7.8078 | 0.3214 |
| Spread: small (\|line\| <= 7) | 3,818 | 3,057 | 0.5685 | 7.5782 | 0.3612 |
| Spread: large (\|line\| > 14) | 2,234 | 1,849 | 0.5133 | 1.1395 | 0.0803 |
| Talent: top quarter | 2,022 | 1,715 | 0.5778 | 6.4473 | 0.6565 |
| Talent: bottom quarter | 2,023 | 1,651 | 0.5687 | 5.5867 | 0.1802 |

### Totals

| Regime | Bets | Graded | Beat rate | z | Mean CLV |
|---|---|---|---|---|---|
| All games | 6,718 | 5,634 | 0.5880 | 13.2161 | 0.4099 |
| Season phase: Early (weeks 1-4) | 2,063 | 1,703 | 0.5590 | 4.8707 | 0.3017 |
| Season phase: Mid (weeks 5-10) | 2,694 | 2,343 | 0.6009 | 9.7718 | 0.4586 |
| Season phase: Late (weeks 11+) | 1,864 | 1,495 | 0.5973 | 7.5261 | 0.4324 |
| Profile: most-quoted quarter | 2,276 | 2,023 | 0.6016 | 9.1378 | 0.4422 |
| Profile: least-quoted quarter | 4,442 | 3,611 | 0.5804 | 9.6686 | 0.3933 |
| Spread: small (\|line\| <= 7) | 3,093 | 2,603 | 0.5859 | 8.7613 | 0.4111 |
| Spread: large (\|line\| > 14) | 1,914 | 1,577 | 0.6056 | 8.3855 | 0.4177 |
| Talent: top quarter | 1,669 | 1,413 | 0.5888 | 6.6773 | 0.4224 |
| Talent: bottom quarter | 1,669 | 1,416 | 0.6052 | 7.9193 | 0.4700 |

Three findings, one of them useful:

**Early-season margins are dead.** Weeks 1-4 give
51.2% at z = 0.98 - no signal at
all - against 58.5% from week 11. That is the sharpest
regime effect in the study and it has an obvious reading: in September the
model is running on last season's ratings, which is precisely when the market's
own opener is least informed by current-season data too. Both are guessing, so
neither moves toward the other. **Totals do not share the weakness**
(55.9% early), which is itself informative: pace and
scoring environment carry across a season better than team strength does.

**Spread size matters for margins and not for totals.** Close games give
56.9% against 51.3% on
blowout-prone lines (z = 1.14). A lopsided line has little
room to move and little reason to.

**Profile does not matter.** The most-quoted quarter of games and the
least-quoted quarter give beat rates within two points of each other in both
markets. This is worth stating because it contradicts the obvious hypothesis:
one would expect a small, ignored game to have a lazier opener and therefore
more predictable movement. It does not. The quoting count is a proxy for
attention rather than a measure of it, and the proxy shows nothing.

---

## Track 7 — Signal concentration

Keeping only the loudest signals each season, ranked within season so a
drifting model cannot pile its "top 1%" into one year:

### Margins

| Keep top | Bets | Min edge | Mean edge | Beat rate | z | Mean CLV | Median CLV |
|---|---|---|---|---|---|---|---|
| 100 | 8,146 | 0.0003 | 4.9892 | 0.5544 | 8.8743 | 0.2820 | 0 |
| 25 | 2,040 | 6.7436 | 10.7069 | 0.5754 | 6.2126 | 0.5914 | 0 |
| 10 | 818 | 9.7235 | 13.9262 | 0.5815 | 4.2535 | 0.7689 | 0 |
| 5 | 410 | 12.0435 | 16.2730 | 0.5620 | 2.3084 | 0.7390 | 0 |

### Totals

| Keep top | Bets | Min edge | Mean edge | Beat rate | z | Mean CLV | Median CLV |
|---|---|---|---|---|---|---|---|
| 100 | 6,718 | 0.0004 | 4.0911 | 0.5880 | 13.2161 | 0.4099 | 0 |
| 25 | 1,683 | 4.4325 | 8.4741 | 0.6664 | 12.6139 | 0.8304 | 0.5 |
| 10 | 676 | 6.5490 | 10.7514 | 0.6924 | 9.1810 | 1.0207 | 1 |
| 5 | 339 | 8.3319 | 12.2513 | 0.6976 | 6.7414 | 1.1180 | 1 |

**Yes, concentration improves the signal, and it improves it in the right
currency.** Mean CLV on totals rises from 0.41
points across everything to 1.02 at the top
10%, while the beat rate climbs from 58.8% to
69.2%.

Note this does **not** contradict Phase 3, which recommended discarding the
quarter of games where the model disagrees most. Those are two different
measurements: Phase 3's ceiling is distance from the **closing** line, which
predicts the model's own failure, while concentration here is distance from the
**opening** line, which predicts movement. A model far from the close is wrong;
a model far from the open is early. Both are true and they select different
games.

Concentration also runs out. On margins the top 5% is *worse* than the top 10%
(56.2%
against
58.1%),
and the 1% cut has too few bets to grade. Ten percent is where the evidence
stops.

### The one cell that clears the bar

| Market | Bets | Per season | Mean CLV | SE | Implied win rate | 95% lower | -105? | -105 (CI)? | -110? | -110 (CI)? |
|---|---|---|---|---|---|---|---|---|---|---|
| margin | 818 | 136 | 0.7689 | 0.1157 | 0.5199 | 0.5140 | yes | yes | no | no |
| total | 676 | 113 | 1.0207 | 0.1054 | 0.5255 | 0.5204 | yes | yes | yes | no |

Season by season, at the totals cut:

| Season | Bets | Beat rate | Mean CLV | Implied win rate | Clears -110? |
|---|---|---|---|---|---|
| 2019 | 70 | 0.7419 | 1.6571 | 0.5414 | yes |
| 2021 | 74 | 0.6769 | 1.2230 | 0.5306 | yes |
| 2022 | 74 | 0.6377 | 0.9122 | 0.5228 | no |
| 2023 | 125 | 0.6170 | 0.1600 | 0.5040 | no |
| 2024 | 170 | 0.7222 | 0.9412 | 0.5235 | no |
| 2025 | 163 | 0.7259 | 1.4479 | 0.5362 | yes |

It clears -110 in **3 of 6 seasons**. And it is
available where a bettor could reach it:

| Book | Bets | Share | Beat rate | Mean CLV | Seasons |
|---|---|---|---|---|---|
| Bovada | 373 | 0.5518 | 0.6596 | 0.8070 | 2021, 2022, 2023, 2024, 2025 |
| ESPN Bet | 151 | 0.2234 | 0.7656 | 1.5430 | 2024, 2025 |
| DraftKings | 82 | 0.1213 | 0.6596 | 0.4878 | 2023, 2024, 2025 |
| 5Dimes & sportbet | 70 | 0.1036 | 0.7419 | 1.6571 | 2019 |

---

## The seven questions

### 1. Is the CLV signal real?

**Yes.** Measured inside a single sportsbook - the only construction a bettor
could execute - Atlas beats that book's own close on 58.8%
of 5,634 graded totals (z = 13.2) and
55.4% of 6,656 margins (z =
8.9). It is positive in every season of both markets, the
book effect against Phase 3's consensus construction is
0.0005, and Phase 3's three placebo predictors all
score at or below chance.

This is the most robust finding in five phases of Atlas research, and it is
the only one that has survived every falsification aimed at it.

### 2. Can it be executed in practice?

**Partly, and not by everyone.**

What works: an opening number exists for essentially every game in the sample,
in every season, and the signal survives being graded at the book that posted
it.

What does not: there are **4 books in the
entire feed that ever post an opener**, all retail. Two or more openers exist
for fewer than half of games, so there is little to shop between. The opening
number appears to be sold about five cents worse than the closing number - the
only direct evidence is one book over two seasons, but it points the same way
the market structure does. And the structural reason early numbers are
available is that limits on them are small, which is a feature of the market
rather than an accident.

**Execution is possible for a small bettor and structurally closed to a large
one.**

### 3. How much is it worth?

One point of CLV is worth about 2.5 percentage points of win probability.
Against that scale:

| Selection | Mean CLV | Implied win rate | -110 needs 52.38% |
|---|---|---|---|
| All margin signals | 0.282 | 50.73% | no |
| All totals signals | 0.410 | 51.02% | no |
| Loudest 10% of margins | 0.769 | 51.99% | no |
| Loudest 10% of totals | 1.021 | 52.55% | **yes, by 0.17%** |

The honest summary: **worth roughly one percentage point of win probability
across the board, and about two and a half on its best tenth.** The best cell
clears -110 by
0.17% with a 95% lower bound of
52.04%, which does not clear. At -105 both markets
clear comfortably at the 10% cut, including on the interval.

**It is worth something. It is not yet worth enough to bet at the prices the
books that post openers actually charge.**

### 4. What is the best execution window?

**Unknown, and unknowable from Atlas's current data.** See Track 5. The
open-to-close window bounds the answer from above; nothing in Atlas's feed
divides it.

### 5. Who could realistically use it?

A **small bettor with accounts at two or three retail books, betting college
football totals only, at reduced juice, on roughly
113 games a season.** That is the entire
addressable population implied by the measurements.

A medium bettor runs into account restrictions at exactly the retail books
that post the openers. A large bettor has no venue in this dataset that both
posts an opener and would accept a serious wager on a college football total.

### 6. What should Atlas become?

**C - a CLV tracking system**, whose substance is B.

Not **A (a betting system)**: the best available cell clears -110 on a point
estimate whose confidence interval contains break-even, in
3 of 6 seasons, before any account restriction or
price penalty. Staking money on that is not supported by this evidence.

Not **D (research only)**: five phases have now produced one robust,
independently falsified signal. Shelving it because it is not yet profitable
discards the only positive result the programme has.

**C is what the measurement problem demands.** Grading on CLV needs about
124 bets to separate the beat rate from chance. Grading on
profit needs tens of thousands. A tracking system learns within one season
what a betting system could not establish in a decade - and it risks nothing
while doing it.

### 7. Is Atlas worth continuing?

**YES.**

Not because it has found a way to make money - it has not, and this report
should not be read as saying so. Because it has found a **measurable,
falsifiable, executable-in-principle signal** that is one data acquisition away
from being answerable, and the acquisition is cheap.

---

## Recommendation: BUILD ATLAS CLV SYSTEM

Scope, in order:

1. **Acquire a timestamped odds archive.** Three seasons minimum, hourly or
   better, including at least one book that posts openers. This answers Track 5
   and nothing else can.
2. **Instrument the signal forward.** Record Atlas's direction and the
   available number at the time of the call, grade against that book's close,
   in public, with no money involved.
3. **Restrict to what the evidence supports**: totals, the loudest 10% of
   signals at the open, outside weeks 1-4 on margins if margins are carried at
   all.
4. **Grade on CLV, report in points of line**, never on simulated profit.

This is explicitly **not** authorisation to wager, and the system should not be
built in a way that makes wagering the obvious next step.

### Kill criterion, pre-registered

Atlas Gamma should be terminated if, after **two forward seasons** of live
tracking:

* the within-book CLV beat rate on the totals 10% cut falls below **55%**
  (against 69.2%
  measured here), **or**
* mean CLV on that cut falls below **0.49 points** -
  the -105 break-even - **or**
* the timestamped archive shows the movement Atlas predicts has already
  happened before a retail bettor could have acted on it.

Any one of those, and the programme has its answer and should stop. These
numbers are frozen here, in the same spirit as
[`docs/SIGNAL_PREREGISTRATION.md`](../docs/SIGNAL_PREREGISTRATION.md), so that
a future phase cannot move them after seeing the result.

---

## What this phase did not establish

- **That the signal is profitable.** It is not, at -110, on this evidence.
- **What limits apply.** No limit data exists in any auditable form; Track 3 is
  a framework with named assumptions, not a measurement.
- **When the movement happens.** Track 5 is unanswered.
- **That the price penalty generalises.** One book, two seasons, and the only
  direct evidence Atlas has.
