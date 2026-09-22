# CLV Economics (Atlas Phase 4, Tracks 2 and 4)

*Generated 2026-09-22 17:03 UTC by `python -m atlas.research.gamma_report`. Every CLV
figure is measured **inside a single sportsbook** - the side is taken at that
book's opening number and graded against that same book's close - because a
bettor holds one ticket at one shop. Phase 3's consensus construction is
carried alongside for comparison. No stake rule is applied anywhere: turning
points into units requires a wagering simulation, which is out of scope.*

---

## The answer, up front

**One point of closing-line value is worth about 2.5 percentage points of win
probability. Standard -110 juice costs 2.38. So the whole question is whether
Atlas can find a point of CLV, and the answer is: not on average, and only
just on its best tenth.**

| | Mean CLV (points) | Worth | -110 needs | Verdict |
|---|---|---|---|---|
| Margins, all signals | +0.282 | +0.73% | +2.38% | short |
| Totals, all signals | +0.410 | +1.02% | +2.38% | short |
| Margins, loudest 10% | +0.769 | +1.99% | +2.38% | short |
| **Totals, loudest 10%** | **+1.021** | **+2.55%** | +2.38% | **clears, barely** |

The one cell that clears does so by
0.17% of win
probability, and its 95% interval does **not** clear
(lower bound 52.04%).

---

## First: the signal survives being measured honestly

Phase 3 compared one book's opener against a consensus close across roughly
six books. That is not a bet anyone can place. Rebuilt inside each book:

| Market | Book | Games | Pushes | Graded | Mean CLV | Beat rate (same book) | z | Beat rate (Phase 3 method) | Book effect |
|---|---|---|---|---|---|---|---|---|---|
| margin | all books | 8,146 | 1,490 | 6,656 | 0.2820 | 0.5544 | 8.8743 | 0.5518 | -0.0026 |
| margin | 5Dimes & sportbet | 695 | 78 | 617 | 0.2245 | 0.5397 | 1.9727 | 0.5455 | 0.0057 |
| margin | Bovada | 3,850 | 552 | 3,298 | 0.1825 | 0.5449 | 5.1543 | 0.5427 | -0.0022 |
| margin | DraftKings | 2,090 | 576 | 1,514 | 0.5074 | 0.5898 | 6.9905 | 0.5818 | -0.0080 |
| margin | ESPN Bet | 1,511 | 284 | 1,227 | 0.2505 | 0.5436 | 3.0547 | 0.5364 | -0.0072 |
| total | all books | 6,718 | 1,084 | 5,634 | 0.4099 | 0.5880 | 13.2161 | 0.5886 | 0.0005 |
| total | 5Dimes & sportbet | 699 | 56 | 643 | 0.4671 | 0.6065 | 5.4028 | 0.5953 | -0.0112 |
| total | Bovada | 3,856 | 449 | 3,407 | 0.3881 | 0.5832 | 9.7140 | 0.5875 | 0.0043 |
| total | DraftKings | 675 | 307 | 368 | 0.0556 | 0.5027 | 0.1043 | 0.5309 | 0.0281 |
| total | ESPN Bet | 1,488 | 272 | 1,216 | 0.6001 | 0.6176 | 8.2016 | 0.6140 | -0.0036 |

**The book effect is essentially zero.** Same-book grading gives
55.4% on margins and 58.8% on
totals, against Phase 3's 55.2% and
58.9%. The Phase 3 result was not an artefact
of comparing two different shops' prices - it replicates on the construction a
bettor could actually execute, and on margins it is slightly *stronger*.

That is the good news, and it is the last of it.

---

## Track 2 — What CLV is worth

One point of line is worth `φ(0) / sd` of win probability, where `sd` is the
out-of-sample residual standard deviation around the closing number
(15.41 points on margins,
15.96 on totals). This assumes the close is a
fair 50/50 - which is what Phases 1 to 3 established, so it is the correct
prior to price against rather than a convenience.

| Market | CLV (points) | Win probability | EV at -105 | EV at -110 | EV at -115 | EV at -120 | -105? | -110? | -115? | -120? |
|---|---|---|---|---|---|---|---|---|---|---|
| margin | 0.25 | 0.5065 | -0.0112 | -0.0331 | -0.0531 | -0.0715 | no | no | no | no |
| margin | 0.5 | 0.5129 | 0.0015 | -0.0207 | -0.0410 | -0.0596 | yes | no | no | no |
| margin | 0.75 | 0.5194 | 0.0141 | -0.0084 | -0.0289 | -0.0477 | yes | no | no | no |
| margin | 1 | 0.5259 | 0.0267 | 0.0040 | -0.0168 | -0.0359 | yes | yes | no | no |
| margin | 1.5 | 0.5388 | 0.0520 | 0.0287 | 0.0074 | -0.0122 | yes | yes | yes | no |
| margin | 2 | 0.5518 | 0.0773 | 0.0534 | 0.0316 | 0.0116 | yes | yes | yes | yes |
| total | 0.25 | 0.5063 | -0.0116 | -0.0335 | -0.0535 | -0.0719 | no | no | no | no |
| total | 0.5 | 0.5125 | 0.0006 | -0.0216 | -0.0418 | -0.0604 | yes | no | no | no |
| total | 0.75 | 0.5188 | 0.0128 | -0.0097 | -0.0302 | -0.0490 | yes | no | no | no |
| total | 1 | 0.5250 | 0.0250 | 0.0023 | -0.0185 | -0.0375 | yes | yes | no | no |
| total | 1.5 | 0.5375 | 0.0494 | 0.0261 | 0.0049 | -0.0146 | yes | yes | yes | no |
| total | 2 | 0.5500 | 0.0738 | 0.0500 | 0.0283 | 0.0083 | yes | yes | yes | yes |

Read down the ladder rather than across it. **A quarter-point of CLV is worth
nothing at any price.** Half a point clears -105 and nothing else. A full point
clears -110. It takes a point and a half to clear -115, and two full points to
clear -120.

Inverted, so the requirement is explicit:

| Market | Price | Break-even win rate | Points of CLV required |
|---|---|---|---|
| margin | -105 | 0.5122 | 0.4711 |
| margin | -110 | 0.5238 | 0.9199 |
| margin | -115 | 0.5349 | 1.3477 |
| margin | -120 | 0.5455 | 1.7561 |
| total | -105 | 0.5122 | 0.4877 |
| total | -110 | 0.5238 | 0.9523 |
| total | -115 | 0.5349 | 1.3952 |
| total | -120 | 0.5455 | 1.8180 |

**This is the bar.** Everything else in this phase is a question of whether
Atlas clears 0.95 points of CLV on totals and
0.92 on margins.

### The price of being early

There is a second cost, and Atlas can only see it through a keyhole. Of the
four books that post openers, exactly one - 5Dimes, in 2018-19 - also publishes
an opening **price**:

| Market | Book | Seasons | Games | Median opening price | Median closing price | Open is worse | Median cents worse |
|---|---|---|---|---|---|---|---|
| margin | 5Dimes & sportbet | 2018, 2019 | 1,402 | -110.000 | -105.000 | 0.913 | 5.000 |
| total | 5Dimes & sportbet | 2018, 2019 | 1,406 | -110.000 | -105.000 | 0.987 | 5.000 |

The opening number is sold at **-110 where the closing number is sold at
-105**, and the opener is the worse price in
91.3% of spreads and
98.7% of totals.

The size of that penalty is the whole phase in one number. Moving from -105 to
-110 raises the break-even from 51.22% to
52.38% - a cost of
1.16% of win probability, which is
**46% of the entire edge on the best cell in this study.**

Two seasons at one book is thin evidence and it is labelled as such. But it
points the same way as the market structure does: a book posting a number
early, with little information and small limits, prices that number wider. If
that is true generally, it removes the edge.

---

## Track 4 — The CLV portfolio

Outcomes are ignored entirely here. The only inputs are the opening line, the
closing line and Atlas's direction. Everything is in **points of line**, and
the path is walked in chronological order because a drawdown is a statement
about sequence.

| Market | Bets | Mean | Median | SD | Mean/SD | P05 | P25 | P75 | P95 | Beat rate | Total points | Max drawdown | Longest underwater (bets) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| margin | 8,146 | 0.282 | 0 | 2.295 | 0.123 | -3.000 | -1.000 | 1.500 | 4.000 | 0.554 | 2297.500 | -121.500 | 699 |
| total | 6,718 | 0.410 | 0 | 2.240 | 0.183 | -3.000 | -1.000 | 2.000 | 4.000 | 0.588 | 2753.500 | -52.000 | 307 |

Three things in that table deserve to be read slowly.

**The median CLV is zero in both markets.** The mean is positive because the
right tail is fatter than the left, not because the typical bet gains anything.
Roughly a fifth of all bets land exactly on the opening number and gain nothing
at all.

**The noise is eight times the signal.** A standard deviation of
2.24 points against a mean of 0.41 means
the per-bet information ratio is 0.183. That is a real
edge and an almost invisible one.

**The underwater stretches are long.** The worst margin drawdown is
122 points, and margins spend
699 consecutive bets below a previous peak -
more than a full season. A signal significant at z =
8.9 still looks broken for a year at a time.

### Distribution

| Market | CLV (points) | Bets | Share |
|---|---|---|---|
| margin | [-1000, -3) | 362 | 0.0444 |
| margin | [-3, -2) | 407 | 0.0500 |
| margin | [-2, -1) | 747 | 0.0917 |
| margin | [-1, -0.5) | 680 | 0.0835 |
| margin | [-0.5, 0) | 770 | 0.0945 |
| margin | [0, 0.5) | 1,490 | 0.1829 |
| margin | [0.5, 1) | 844 | 0.1036 |
| margin | [1, 2) | 1,279 | 0.1570 |
| margin | [2, 3) | 722 | 0.0886 |
| margin | [3, 1000) | 845 | 0.1037 |
| total | [-1000, -3) | 314 | 0.0467 |
| total | [-3, -2) | 340 | 0.0506 |
| total | [-2, -1) | 623 | 0.0927 |
| total | [-1, -0.5) | 609 | 0.0907 |
| total | [-0.5, 0) | 435 | 0.0648 |
| total | [0, 0.5) | 1,084 | 0.1614 |
| total | [0.5, 1) | 510 | 0.0759 |
| total | [1, 2) | 1,113 | 0.1657 |
| total | [2, 3) | 762 | 0.1134 |
| total | [3, 1000) | 928 | 0.1381 |

### Season by season

| Market | Season | Bets | Mean CLV | Median | Beat rate | Total points | Max drawdown |
|---|---|---|---|---|---|---|---|
| margin | 2019 | 695 | 0.224 | 0 | 0.540 | 156.000 | -63.500 |
| margin | 2021 | 732 | 0.193 | 0 | 0.566 | 141.000 | -33.500 |
| margin | 2022 | 727 | 0.153 | 0 | 0.544 | 111.500 | -45.000 |
| margin | 2023 | 1,515 | 0.335 | 0 | 0.566 | 507.500 | -43.000 |
| margin | 2024 | 2,247 | 0.309 | 0 | 0.567 | 693.500 | -121.500 |
| margin | 2025 | 2,230 | 0.309 | 0 | 0.539 | 688.000 | -54.500 |
| total | 2019 | 699 | 0.467 | 0.5 | 0.607 | 326.500 | -25.500 |
| total | 2021 | 732 | 0.415 | 0.5 | 0.585 | 303.500 | -15.000 |
| total | 2022 | 732 | 0.545 | 0.5 | 0.623 | 399.000 | -29.000 |
| total | 2023 | 1,243 | 0.181 | 0 | 0.543 | 225.000 | -52.000 |
| total | 2024 | 1,691 | 0.359 | 0 | 0.582 | 607.000 | -45.000 |
| total | 2025 | 1,621 | 0.551 | 0 | 0.602 | 892.500 | -42.000 |

Positive in every season in both markets - 53.9%
to 56.7% on margins,
54.3% to
62.3% on totals. The signal is stable. It is
simply small.

---

## What this report establishes

1. The Phase 3 CLV signal **is not a book artefact**. It replicates inside a
   single book, which is the only version anyone could trade.
2. One point of CLV is worth ~2.5% of win probability, so **-110 demands
   roughly one full point** and -115 demands a point and a half.
3. Atlas averages 0.28 points on margins and
   0.41 on totals. **Neither clears -110.**
4. The early number appears to be sold ~5 cents worse than the late one, which
   costs about half the edge of the best cell in the study.
5. The distribution is thin-tailed around a zero median with long underwater
   stretches, so even the part that works would take a very long time to
   distinguish from luck by its results.

Whether any cell of the data clears the bar is Track 7's question, and it is
answered in [`atlas_gamma_assessment.md`](atlas_gamma_assessment.md).
