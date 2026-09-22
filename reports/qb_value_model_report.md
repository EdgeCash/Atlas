# Atlas Quarterback Value Model (Phase 1C, Track 1)

*Generated 2026-09-22 15:50 UTC. Every figure is produced by
`python -m atlas.research.phase1c_report`; none is hand-entered.*

## The headline, and it is a correction

Phase 1B reported that a quarterback change is worth about 2.1 points of
market residual, positive in 8 of 8 seasons, and called it "the only non-zero
signal in the programme". Phase 1C decomposed that signal and **it does not
survive.**

The effect is real in the data and almost entirely **reverse causation**. A
team that changes quarterback mid-game does so *because* the game went badly.
Splitting changes by whether the replacement played the whole game separates
the two cleanly:

| Event | Games | Mean residual | t |
|---|---|---|---|
| QB changed *during* this game | 1600 | **4.81** | 11.7 |
| QB change, any kind (Phase 1B's measure) | 1509 | 2.10 | 5.2 |
| **New QB who then took ~every snap** (decided before kickoff) | 870 | **-0.97** | -1.9 |

A quarterback change that a pre-kickoff observer *could have known about* is
worth **-0.97 points** - if anything slightly negative, and not
significant. The entire 2.1-point effect lives in quarterbacks being pulled
during games the bettor could not have anticipated.

## Method

Every event is built from the **quarterback of record** - the passer with the
most attempts - derived from play-by-play for 8 seasons.
That is a retrospective fact, so none of it is a warehouse column and none of
it is a deployable feature. What it measures is *the value of knowing*
something in advance, which is the right question for an information-edge
phase.

Effects are **signed and folded**: a home-team event and an away-team event
are the same phenomenon mirrored, so folding doubles the sample. A positive
value means the team with the event **underperformed** the closing line.

## 1. Which QB events matter most?

### Contemporaneous (post-hoc - an upper bound, not a feature)

| Event | Games | Mean | Median | SE | t | p | CI low | CI high |
|---|---|---|---|---|---|---|---|---|
| in_game_rotation | 1,600 | 4.810 | 5.000 | 0.412 | 11.689 | 0.000 | 4.036 | 5.586 |
| committee_game | 1,062 | 5.592 | 6.500 | 0.505 | 11.071 | 0.000 | 4.597 | 6.563 |
| backup_start | 1,665 | 3.288 | 3.000 | 0.380 | 8.649 | 0.000 | 2.528 | 4.019 |
| qb_change | 1,509 | 2.102 | 1.750 | 0.402 | 5.229 | 0.000 | 1.339 | 2.877 |
| new_starter | 1,045 | 2.073 | 1.000 | 0.478 | 4.335 | 0.000 | 1.141 | 2.991 |
| inexperienced_starter | 1,684 | 1.300 | 1.000 | 0.389 | 3.343 | 0.001 | 0.569 | 2.049 |
| planned_change | 870 | -0.974 | -1.500 | 0.506 | -1.925 | 0.055 | -2.029 | -0.004 |
| first_year_player | 826 | 0.863 | 1.000 | 0.554 | 1.557 | 0.120 | -0.240 | 1.944 |
| returning_starter | 2,335 | -0.363 | -0.500 | 0.318 | -1.143 | 0.253 | -0.990 | 0.250 |
| transfer_starter | 2,307 | -0.047 | 0.000 | 0.318 | -0.148 | 0.883 | -0.681 | 0.530 |

### Pre-kickoff (what a bettor could actually have known)

Each event as it stood in the team's **previous** game. A previous game cannot
be caused by a game that has not happened, so any effect here is information
rather than artefact.

| Event | Games | Mean | Median | SE | t | p |
|---|---|---|---|---|---|---|
| prior_backup_start | 1,562 | 0.965 | 1.000 | 0.395 | 2.441 | 0.015 |
| prior_qb_change | 1,369 | -0.441 | -0.500 | 0.416 | -1.061 | 0.289 |
| prior_first_year_player | 720 | 0.344 | 0.500 | 0.572 | 0.601 | 0.548 |
| prior_transfer_starter | 2,170 | -0.161 | 0.000 | 0.333 | -0.482 | 0.630 |
| prior_committee_game | 1,102 | -0.183 | -0.500 | 0.463 | -0.396 | 0.692 |
| prior_returning_starter | 2,223 | 0.113 | 0.000 | 0.327 | 0.347 | 0.729 |
| prior_new_starter | 1,122 | 0.101 | 0.250 | 0.468 | 0.216 | 0.829 |
| prior_inexperienced_starter | 1,708 | -0.057 | 0.500 | 0.384 | -0.148 | 0.883 |
| prior_planned_change | 770 | -0.037 | 0.500 | 0.552 | -0.068 | 0.946 |
| prior_in_game_rotation | 1,779 | 0.019 | 0.500 | 0.361 | 0.054 | 0.957 |

**Everything collapses.** The largest pre-kickoff effect is
prior_backup_start at 0.96 points (t = 2.44),
and with eight tests in this table alone that is where noise lives.

## 2. What is the median impact?

| Quantile | QB change | No event |
|---|---|---|
| 0.05 | -22.50 | -25.00 |
| 0.10 | -17.55 | -19.50 |
| 0.25 | -8.50 | -10.00 |
| 0.50 | 1.75 | 0.00 |
| 0.75 | 12.50 | 10.50 |
| 0.90 | 22.05 | 20.00 |
| 0.95 | 28.00 | 25.00 |

## 3. What is the distribution?

The quantile table above is the answer, and it is the reason the mean is
misleading. The event and control distributions are nearly the same shape -
the whole difference is a shift of a point or two in the middle, on a
distribution whose 5th-to-95th range spans fifty points. There is no fat tail
of "backup QB, blowout loss" games; there is a barely-moved distribution.

## 4. Does impact vary by conference, team strength or venue?

| Dimension | Group | Games | Mean | SE | t | p |
|---|---|---|---|---|---|---|
| event_conference | Mid-American | 136 | 4.259 | 1.325 | 3.213 | 0.002 |
| event_conference | Big Ten | 147 | 2.971 | 1.208 | 2.459 | 0.015 |
| event_conference | Pac-12 | 98 | 3.962 | 1.729 | 2.291 | 0.024 |
| event_conference | Sun Belt | 160 | 2.733 | 1.211 | 2.257 | 0.025 |
| event_conference | American Athletic | 137 | 2.745 | 1.379 | 1.990 | 0.049 |
| event_conference | ACC | 169 | 2.050 | 1.173 | 1.747 | 0.082 |
| event_conference | FBS Independents | 64 | 2.832 | 1.977 | 1.432 | 0.157 |
| event_conference | Mountain West | 150 | 1.502 | 1.341 | 1.120 | 0.265 |
| event_conference | Big 12 | 146 | 0.979 | 1.239 | 0.791 | 0.431 |
| event_conference | SEC | 141 | 0.856 | 1.155 | 0.741 | 0.460 |
| event_conference | Conference USA | 161 | -0.385 | 1.343 | -0.287 | 0.775 |
| event_side | home | 736 | 2.540 | 0.580 | 4.376 | 0.000 |
| event_side | away | 773 | 1.686 | 0.557 | 3.025 | 0.003 |
| mismatch | 3-7 | 390 | 3.247 | 0.797 | 4.074 | 0.000 |
| mismatch | 7-14 | 393 | 2.596 | 0.812 | 3.198 | 0.001 |
| mismatch | pick'em | 298 | 1.591 | 0.841 | 1.892 | 0.059 |
| mismatch | 14-24 | 290 | 1.409 | 0.945 | 1.491 | 0.137 |
| mismatch | 24+ | 138 | 0.022 | 1.283 | 0.017 | 0.987 |
| event_team_role | favourite | 502 | 3.158 | 0.731 | 4.322 | 0.000 |
| event_team_role | underdog | 1,007 | 1.576 | 0.479 | 3.288 | 0.001 |

## 5. Does the market partially price the information?

Measured on `planned_change` only - the market cannot price a quarterback
being pulled in the second quarter, so asking whether it prices *that* is not
a well-formed question.

| Measure | Games | Mean | SE | t | p |
|---|---|---|---|---|---|
| line move toward the non-event side (points) | 792 | -0.311 | 0.085 | -3.658 | 0.000 |
| line move, games with no event (control) | 4,470 | 0.152 | 0.083 | 1.820 | 0.069 |
| residual after the move (points) | 792 | -0.628 | 0.531 | -1.183 | 0.237 |
| residual | line moved >= 0.5 | 685 | -0.812 | 0.578 | -1.406 | 0.160 |
| residual | line barely moved | 107 | 0.547 | 1.342 | 0.407 | 0.685 |

## 6. How much advantage remains?

**On this evidence, none that Atlas can reach.**

- The pre-kickoff-knowable part of a quarterback change measures
  -0.97 points, t = -1.92.
- Every lagged event measures within noise of zero.
- Per-season, the *contemporaneous* effect is positive in most seasons - which
  is exactly what an artefact of blowouts looks like, since blowouts happen
  every season.

| Season | Games | Mean | SE | t | p |
|---|---|---|---|---|---|
| 2023.000 | 212 | 3.317 | 1.055 | 3.143 | 0.002 |
| 2021.000 | 201 | 2.458 | 1.087 | 2.262 | 0.025 |
| 2019.000 | 158 | 2.484 | 1.168 | 2.128 | 0.035 |
| 2024.000 | 193 | 2.361 | 1.165 | 2.027 | 0.044 |
| 2018.000 | 164 | 2.527 | 1.260 | 2.005 | 0.047 |
| 2025.000 | 231 | 1.766 | 0.972 | 1.818 | 0.070 |
| 2022.000 | 217 | 1.142 | 1.073 | 1.064 | 0.288 |
| 2020.000 | 133 | 0.425 | 1.487 | 0.286 | 0.776 |

## What this changes

Phase 1B's recommendation was to price a commercial pre-kickoff quarterback
feed as the highest-value item on the roadmap. **That recommendation is
withdrawn.** The number that justified it was measuring the consequences of
games, not the information available before them. A feed that told Atlas
tomorrow's starter with perfect accuracy would, on this evidence, be worth
approximately nothing against the closing line.

The honest residual caveat: this analysis cannot see *injury news* as such. It
sees line-up outcomes. A star quarterback ruled out on Thursday appears here
as a `planned_change`, and planned changes measure zero - but a season-ending
injury to a Heisman contender is not the median planned change. If anyone
still wants to test the quarterback hypothesis, the test is a small,
hand-labelled sample of high-profile absences, not another feed.
