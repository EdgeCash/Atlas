# Opening Line Feasibility (Atlas Phase 4, Tracks 1 and 3)

*Generated 2026-09-22 17:03 UTC by `python -m atlas.research.gamma_report`. Counts come
from the per-book odds feed in `data/raw`, rebuilt by
`atlas.research.execution.book_lines` rather than from the staged consensus,
because the consensus is exactly what this report exists to question. Passages
marked **external** are not Atlas measurements; they are named sources with
their limits attached.*

---

## The answer, up front

**A bettor can reach an opening number, but not the one Phase 3 measured
against, and not at the price the closing number is sold at.**

Three facts decide it:

1. **At most four books in the entire feed ever post an opening number**, and
   for most of the sample exactly one book posts the opener for a given game.
2. **Openers disagree with each other.** Where two or more books open the same
   game, only 16.5% of spreads and
   34.7% of totals open on the same number. There
   is no such thing as *the* opening line.
3. **The early number is sold at a worse price.** In the one book-season where
   Atlas can see both, the opening price is worse than the closing price in
   91.3% of
   spreads and
   98.7% of
   totals.

The third fact is the one that matters, and it is developed in
[`clv_economics.md`](clv_economics.md).

---

## Track 1 — Opening line availability

### Coverage, by season

| Market | Season | Games in sample | With an opener | Coverage | Books posting | Books/game | Single-book share | No-move share |
|---|---|---|---|---|---|---|---|---|
| margin | 2018 | 707 | 707 | 1.000 | 1 | 1.000 | 1.000 | 0.129 |
| margin | 2019 | 699 | 695 | 0.994 | 1 | 1.000 | 1.000 | 0.112 |
| margin | 2021 | 732 | 732 | 1.000 | 1 | 1.000 | 1.000 | 0.169 |
| margin | 2022 | 734 | 727 | 0.990 | 1 | 1.000 | 1.000 | 0.165 |
| margin | 2023 | 792 | 792 | 1.000 | 2 | 1.913 | 0.087 | 0.273 |
| margin | 2024 | 798 | 798 | 1.000 | 3 | 2.816 | 0.004 | 0.147 |
| margin | 2025 | 808 | 808 | 1.000 | 3 | 2.760 | 0.051 | 0.190 |
| total | 2018 | 707 | 707 | 1.000 | 1 | 1.000 | 1.000 | 0.076 |
| total | 2019 | 699 | 699 | 1.000 | 1 | 1.000 | 1.000 | 0.080 |
| total | 2021 | 732 | 732 | 1.000 | 1 | 1.000 | 1.000 | 0.138 |
| total | 2022 | 734 | 732 | 0.997 | 1 | 1.000 | 1.000 | 0.092 |
| total | 2023 | 792 | 792 | 1.000 | 2 | 1.569 | 0.431 | 0.223 |
| total | 2024 | 798 | 798 | 1.000 | 3 | 2.119 | 0.014 | 0.179 |
| total | 2025 | 808 | 808 | 1.000 | 3 | 2.006 | 0.074 | 0.173 |

**Coverage itself is not the problem: an opening number exists for
100% of the games Atlas would have an opinion
on, in every season.** The problem is how thin that number is. Through 2022 it
is a *single* book's opener for every game in the sample; only from 2023 does
a second and then a third book appear, and even in 2025 the mean is
2.1 books. There is no depth behind the
number Phase 3 graded against.

The sample is also a different object in each half - one book then three - so
any result has to hold season by season rather than only in the pool. Track 4
tests that directly.

### Who posts the openers

| Market | Book | Games opened | Coverage | Seasons | Median \|move\| | Opening price known |
|---|---|---|---|---|---|---|
| margin | Bovada | 3,850 | 0.666 | 2021, 2022, 2023, 2024, 2025 | 1.000 | 0.000 |
| margin | DraftKings | 2,090 | 0.362 | 2023, 2024, 2025 | 1.000 | 0.000 |
| margin | ESPN Bet | 1,511 | 0.262 | 2024, 2025 | 1.000 | 0.000 |
| margin | 5Dimes & sportbet | 1,402 | 0.243 | 2018, 2019 | 1.500 | 1.000 |
| total | Bovada | 3,856 | 0.667 | 2021, 2022, 2023, 2024, 2025 | 1.500 | 0.000 |
| total | ESPN Bet | 1,488 | 0.258 | 2024, 2025 | 1.000 | 0.000 |
| total | 5Dimes & sportbet | 1,406 | 0.243 | 2018, 2019 | 2.000 | 1.000 |
| total | DraftKings | 675 | 0.117 | 2023, 2024, 2025 | 0.500 | 0.000 |

**Every opener in this dataset comes from a retail book.** Bovada opens
roughly 67% of games;
DraftKings, ESPN Bet and (in 2018-19) 5Dimes cover the rest. The books whose
numbers the market actually respects - Pinnacle and BetCRIS/BOOKMAKER both
appear in this feed - are present **only at the close**. They never open a
game here.

That is a structural statement about the dataset, not about the world: those
books certainly post early numbers of their own. What it means for Atlas is
narrower and sharper: **the openers Atlas has measured against are retail
openers**, and any conclusion about them is a conclusion about retail books.

### Stability of the opening number

| Market | Games with 2+ openers | Identical | Median gap | Mean gap | P90 gap | Max gap |
|---|---|---|---|---|---|---|
| margin | 2,285 | 0.165 | 1.000 | 1.443 | 3.000 | 21.000 |
| total | 1,986 | 0.347 | 0.500 | 0.799 | 2.000 | 14.000 |

On spreads, two books opening the same game agree on the number
16.5% of the time, and the median gap between
them is 1.0 points - the same size as the median
move from open to close. **The disagreement between two openers is as large as
the thing Atlas is trying to forecast.**

Totals are tighter (34.7% identical, median gap
0.5), which is one reason the totals signal
survives execution testing better than the margin signal does.

### Time between open and close

**Atlas cannot measure this.** The odds feed carries an opening number, a
closing number and a kickoff time. It carries **no timestamp on either line**,
so the elapsed time between them, and the path taken, are both unobservable.
Track 5 of this phase is unanswerable with the data Atlas holds, and the
assessment says so rather than estimating it.

---

## Track 3 — Book availability, by bettor size

This track asks what limits a bettor would face. **Atlas holds no limit data**,
and limits are not published in a form that can be audited: they vary by
account, by state, by game and by time of day. What follows is therefore a
framework with its assumptions named, not a measurement, and it is separated
from the measured sections deliberately.

What Atlas *can* state from its own data is the part that constrains every
bettor equally:

| Constraint | Measured value |
|---|---|
| Books at which the signal is available at all | 4 |
| Games with more than one opener to shop between | 2,285 of 5,259 |
| Median gap between two books' openers (spread) | 1.0 points |
| Opening **price** observable | 17% of book-games |

**External context.** The structural reason the early number is hard to reach
is not a secret: books post early lines at deliberately small limits and raise
them as the market forms. Pinnacle's own model is described publicly as posting
"overnight" lines at low limits precisely so sharp money can shape the number
before the book is exposed, with limits rising into the tens of thousands only
once the line has settled
([Pinnacle betting limits overview](https://surebetmonitor.com/knowledge-base/pinnacle-sports-betting-limits/)).
Atlas has not verified those figures and they are not from the book's own
documentation; they are consistent with the structure and should be treated as
orientation, not evidence.

### The three bettors

| | Small | Medium | Large |
|---|---|---|---|
| Stake per bet | $50-200 | $500-2,000 | $5,000+ |
| Can reach a retail opener | Yes | Probably | No |
| Limited or closed after a winning run | Eventually | Quickly | Immediately |
| Can shop between openers | Only on the 43% of games with two openers | Same | Same |
| Bets per season at the Track 7 cut | ~113 (totals) | Same | Same |
| Binding constraint | Price | Limits, then account survival | No market |

The asymmetry is the finding. A **small** bettor can reach these numbers and is
constrained by price - the edge measured in the next report does not clear
standard juice. A **medium** bettor is constrained by account survival at the
same retail books that post the openers. A **large** bettor has no market here
at all: there is no venue in this dataset that both posts an opener and would
take a five-figure wager on a college football total.

**A signal that only works at a stake size too small to matter, at books that
close winning accounts, is not a business.** That is Track 3's answer, and it
does not depend on the limit figures Atlas could not obtain.
