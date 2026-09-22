# Atlas Market Failure Report (Phase 1C, Track 5)

*Generated 2026-09-22 15:50 UTC.*

If the market has a weakness, the games it misses by four touchdowns are where
it should show. This track asks whether those games share anything a bettor
could have spotted in advance.

## How often the market is badly wrong

| Market | Miss of at least | Games | Share | Per season |
|---|---|---|---|---|
| margin | 21 | 1,016 | 0.1758 | 127.0000 |
| margin | 28 | 421 | 0.0729 | 52.6250 |
| margin | 35 | 151 | 0.0261 | 18.8750 |
| total | 21 | 1,128 | 0.1952 | 141.0000 |
| total | 28 | 449 | 0.0777 | 56.1250 |
| total | 35 | 161 | 0.0279 | 20.1250 |

The closing spread misses by 28+ points in **7.3%** of
games - about 53
games a season. It is not a rare event, and that is the first thing to
internalise: a 12-point average error implies a long tail, and a long tail is
compatible with perfect efficiency.

## What distinguishes the blow-ups?

| Characteristic | Rate in 28+ misses | Rate elsewhere | Lift | z | p |
|---|---|---|---|---|---|
| Either team changed quarterback | 0.3468 | 0.3035 | 1.1425 | 1.8537 | 0.0638 |
| Either team started a backup | 0.4038 | 0.3763 | 1.0730 | 1.1191 | 0.2631 |
| Either team used a committee | 0.2993 | 0.2080 | 1.4392 | 4.3953 | 0.0000 |
| Recurring rivalry fixture | 0.3777 | 0.4079 | 0.9259 | -1.2153 | 0.2242 |
| Bowl / postseason | 0.0214 | 0.0233 | 0.9162 | -0.2568 | 0.7973 |
| Top-10 vs top-10 | 0.0048 | 0.0125 | 0.3798 | -1.4107 | 0.1583 |
| Visitor travelled 1500+ miles | 0.0546 | 0.0590 | 0.9261 | -0.3662 | 0.7142 |
| Conference game | 0.7055 | 0.7181 | 0.9824 | -0.5555 | 0.5786 |
| Closing spread size (mean) | 10.6271 | 11.2602 | n/a | n/a | n/a |
| Wind (mean) | 7.5314 | 7.3633 | n/a | n/a | n/a |
| Closing total (mean) | 54.9311 | 54.1630 | n/a | n/a | n/a |

**One characteristic separates them, and it is the one that cannot be known in
advance.** Games where a team used a quarterback committee are
1.44x
more common among blow-ups - because a blow-up is *why* the committee
happened. Track 1 dismantles this at length. It is the same artefact seen from
the other end.

Everything a bettor could have known in advance - rivalry, bowl, ranked
matchup, travel, conference, wind, the size of the spread - is **flat**. The
games the market misses by four touchdowns look, beforehand, exactly like the
games it gets right.

## Do blow-ups cluster?

| Dimension | Group | Games | 28+ misses | Rate | z |
|---|---|---|---|---|---|
| home_conference | ACC | 677 | 49 | 0.0724 | -0.0485 |
| home_conference | American Athletic | 528 | 49 | 0.0928 | 1.7629 |
| home_conference | Big 12 | 567 | 48 | 0.0847 | 1.0805 |
| home_conference | Big Ten | 759 | 55 | 0.0725 | -0.0423 |
| home_conference | Conference USA | 472 | 42 | 0.0890 | 1.3475 |
| home_conference | FBS Independents | 201 | 16 | 0.0796 | 0.3676 |
| home_conference | Mid-American | 454 | 31 | 0.0683 | -0.3755 |
| home_conference | Mountain West | 471 | 33 | 0.0701 | -0.2337 |
| home_conference | Pac-12 | 411 | 25 | 0.0608 | -0.9388 |
| home_conference | SEC | 738 | 35 | 0.0474 | -2.6587 |
| home_conference | Sun Belt | 500 | 38 | 0.0760 | 0.2699 |
| season | 2,018 | 707 | 55 | 0.0778 | 0.5044 |
| season | 2,019 | 699 | 50 | 0.0715 | -0.1355 |
| season | 2,020 | 508 | 38 | 0.0748 | 0.1683 |
| season | 2,021 | 732 | 58 | 0.0792 | 0.6633 |
| season | 2,022 | 734 | 51 | 0.0695 | -0.3524 |
| season | 2,023 | 792 | 48 | 0.0606 | -1.3271 |
| season | 2,024 | 798 | 66 | 0.0827 | 1.0699 |
| season | 2,025 | 808 | 55 | 0.0681 | -0.5242 |

Nothing meaningful. The largest deviation is one conference sitting below the
league rate, on one of eleven conference tests plus eight season tests - the
arithmetic of nineteen tests predicts roughly one such result.

## The largest misses

| Season | Week | Home | Away | Closing spread | Actual margin | Residual | Absolute |
|---|---|---|---|---|---|---|---|
| 2,023 | 1 | Eastern Michigan | South Alabama | -17.8 | -49.0 | -66.8 | 66.8 |
| 2,018 | 13 | Duke | Wake Forest | -9.5 | -52.0 | -61.5 | 61.5 |
| 2,022 | 13 | Liberty | New Mexico State | -24.0 | -35.0 | -59.0 | 59.0 |
| 2,025 | 12 | Nevada | San José State | 9.5 | 45.0 | 54.5 | 54.5 |
| 2,020 | 15 | Arizona | Arizona State | 9.0 | -63.0 | -54.0 | 54.0 |
| 2,019 | 5 | Maryland | Penn State | 6.5 | -59.0 | -52.5 | 52.5 |
| 2,019 | 12 | Duke | Syracuse | -9.0 | -43.0 | -52.0 | 52.0 |
| 2,024 | 3 | Purdue | Notre Dame | 7.5 | -59.0 | -51.5 | 51.5 |
| 2,020 | 1 | Navy | BYU | 1.0 | -52.0 | -51.0 | 51.0 |
| 2,023 | 12 | Arkansas State | Texas State | 3.2 | 46.0 | 49.2 | 49.2 |
| 2,023 | 1 | Syracuse | South Florida | -4.2 | -45.0 | -49.2 | 49.2 |
| 2,022 | 9 | Rice | Charlotte | -15.0 | -33.0 | -48.0 | 48.0 |
| 2,024 | 14 | Tulsa | Florida Atlantic | -1.0 | -47.0 | -48.0 | 48.0 |
| 2,025 | 4 | San Diego State | California | 14.0 | 34.0 | 48.0 | 48.0 |
| 2,018 | 12 | Illinois | Iowa | 15.5 | -63.0 | -47.5 | 47.5 |

Read the list and the conclusion writes itself: these are ordinary games
between ordinary opponents that happened to go sideways. There is no recurring
pattern, no conference cluster, no weather cluster, no quarterback cluster
that was visible beforehand.

## Recommendation

**Stop mining the tail.** The market's large errors are variance, not
weakness. A 12-point mean absolute error on a sport where a single turnover
swings fourteen points produces a fat tail by construction, and nothing in
that tail is predictable from pre-kickoff information Atlas can see.

The one genuinely useful output of this track is a calibration fact for any
future Alpha: **17.6% of games miss by 21+ and
2.6% by 35+.** Any model that claims a tighter
distribution than that is miscalibrated, and any staking plan has to survive
it.
