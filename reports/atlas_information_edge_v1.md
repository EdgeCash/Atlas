# Atlas Information Edge Report V1 (Phase 1C)

*Generated 2026-09-22 15:50 UTC. Every figure is produced by
`python -m atlas.research.phase1c_report`; none is hand-entered.*

Phase 1A found the closing line beats every public team-quality metric. Phase
1B found that opponent-adjusting those metrics improves Atlas's own forecast a
great deal and its edge over the market not at all. Phase 1C was asked to stop
measuring team quality and go looking for information asymmetries instead.

It found one candidate, and it retired the one the programme already had.

---

## The headline

**1. Phase 1B's quarterback signal was reverse causation, and is withdrawn.**

The 2.1-point "QB change" effect decomposes into:

| | Games | Residual | t |
|---|---|---|---|
| QB changed *during* the game | 1600 | **4.81** | 11.7 |
| New QB who took every snap (knowable pre-kickoff) | 870 | -0.97 | -1.9 |

Teams get their quarterback pulled *because* the game is going badly. The part
a bettor could have known in advance is worth nothing.

**2. Nothing in Tracks 1-5 survives multiple-testing correction.**

Phase 1C ran **44 pre-kickoff hypothesis tests** across quarterback
events, roster continuity, situational angles, market-failure characteristics
and line movement. 4 cleared p < 0.05 before correction, against the
2.2 that pure noise alone would produce. After
Benjamini-Hochberg across the pool: **0 survive**.

(6 further tests were run on *post-hoc* variables - things
knowable only after kickoff. They are excluded from the correction and
reported separately below, because a post-hoc measurement can be wildly
significant and still be worth nothing as information.)

**3. The one live candidate came from comparing against Velocity - and it is
a methodology fix, not a new variable.**

---

## 1. What information appears to move residuals?

**No pre-kickoff variable survived correction.** Not one.

Strongest pre-kickoff tests, ranked by raw p-value:

| Track | Test | Games | Estimate | t | p | q (FDR) | Survives |
|---|---|---|---|---|---|---|---|
| situational | Ranked vs ranked | 346 | n/a | 2.7033 | 0.0069 | 0.1859 | no |
| situational | Rematch after a 21+ point loss | 490 | n/a | -2.6335 | 0.0084 | 0.1859 | no |
| qb_pre_kickoff | prior_backup_start | 1,562 | 0.9649 | 2.4406 | 0.0148 | 0.1902 | no |
| situational | Recurring rivalry fixture | 2,344 | n/a | -2.3805 | 0.0173 | 0.1902 | no |
| roster_continuity | Returning production edge | 5,680 | 1.0760 | 1.8349 | 0.0666 | 0.5779 | no |
| line_movement | >= 3 | 318 | 1.5212 | 1.7045 | 0.0893 | 0.5779 | no |
| roster_continuity | New head coach | 1,674 | 0.6486 | 1.6862 | 0.0919 | 0.5779 | no |
| line_movement | 1..3 | 1,008 | 0.7907 | 1.6167 | 0.1063 | 0.5844 | no |
| situational | Top-10 vs top-10 | 69 | n/a | 1.4392 | 0.1501 | 0.6966 | no |
| market_failure | Top-10 vs top-10 | 5,778 | n/a | -1.4107 | 0.1583 | 0.6966 | no |
| market_failure | Recurring rivalry fixture | 5,778 | n/a | -1.2153 | 0.2242 | 0.8970 | no |
| line_movement | <= -3 | 340 | -0.9324 | -1.1528 | 0.2498 | 0.9008 | no |

For contrast, the **post-hoc** tests - excluded from the correction above
because they measure things knowable only after kickoff:

| Track | Test | Games | Estimate | t | p |
|---|---|---|---|---|---|
| roster_continuity | QB change (reference) | 1,509 | 2.1022 | 5.2290 | 0.0000 |
| market_failure | Either team used a committee | 5,778 | n/a | 4.3953 | 0.0000 |
| roster_continuity | QB continuity edge (today's starter - post-hoc) | 5,109 | 1.8744 | 4.0089 | 0.0001 |
| market_failure | Either team changed quarterback | 5,778 | n/a | 1.8537 | 0.0638 |
| market_failure | Either team started a backup | 5,778 | n/a | 1.1191 | 0.2631 |
| roster_continuity | Transfer QB | 5,778 | -0.0472 | -0.1467 | 0.8834 |

The significant ones are the largest effects measured anywhere in the
programme - and every one of them is useless, because none could be known
before kickoff. That contrast is the whole lesson of Phase 1C.

The one thing that does move the residual is not a variable at all. It is a
**method**: scoring a totals model by how often it is right on its biggest
disagreements, rather than by mean error.

| Disagreement ≥ | Bets | Win rate | z | Clears -110? |
|---|---|---|---|---|
| 0 | 5,708 | 0.5200 | 3.0178 | no |
| 1 | 4,800 | 0.5210 | 2.9156 | no |
| 2 | 3,885 | 0.5176 | 2.1980 | no |
| 3 | 3,091 | 0.5205 | 2.2843 | no |
| 4 | 2,380 | 0.5244 | 2.3778 | yes |
| 6 | 1,285 | 0.5261 | 1.8691 | no |
| 8 | 649 | 0.5393 | 2.0019 | yes |
| 10 | 282 | 0.5461 | 1.5483 | no |

Atlas rises from 52.0% flat to 53.9% at the
8-point cut. Velocity, independently, reports 51.6% rising to 53.4%. Two
models, two samples, one shape.

## 2. What information appears completely priced?

Everything else the programme has tested. To put it in one place:

| Family | Phase | Verdict |
|---|---|---|
| Raw efficiency (EPA, success rate, explosiveness, havoc, finishing, pace) | 1A | priced |
| SP+, FPI, Elo, recruiting, returning production, roster talent | 1A | priced |
| Weather (temperature, wind, precipitation, humidity) | 1B | priced |
| Opponent-adjusted efficiency | 1B | priced |
| Quarterback change, backup starts, committees, transfers, experience | 1C | priced, or reverse causation |
| Head-coach change, roster churn | 1C | priced |
| Bye week, short rest, travel, rivalry, revenge, ranked matchups, bowls | 1C | priced |
| Open-to-close line movement, book disagreement | 1C | priced |
| Market failure tails (21/28/35-point misses) | 1C | variance, not weakness |

The closing spread is, on this evidence, a complete summary of publicly
available information about a college football game.

## 3. What information appears worth collecting live?

**Very little, and less than Phase 1B implied.**

- The entire open-to-close information flow is worth
  0.22
  points of spread MAE. Any live-collection programme is fighting for a
  fraction of that.
- Pre-kickoff quarterback status, the thing Phase 1B recommended buying, now
  measures zero.
- A **timestamped line archive** is the one data purchase still defensible,
  and only to evaluate the totals candidate properly - not to chase sides.

## 4. What should Atlas Alpha focus on?

### One direction: selective NCAAF totals, tested to destruction

Not because the evidence is strong - it is thin - but because it is the only
direction in three phases that two independent models both point at, and
because the alternative directions are now measured and empty.

What "tested to destruction" means, concretely:

1. **Hold out 2025 entirely.** Fit nothing on it, choose nothing on it,
   measure the cut once.
2. **Pre-register the threshold** before looking. Eight thresholds were
   scanned here; the best of eight is biased upward.
3. **Model real friction**: actual juice (often worse than -110 on college
   totals), actual limits, actual availability at the posted number.
4. **Require the season split to hold.** At the 4-point cut Atlas is above
   break-even in 5 of 8 seasons; Velocity gets 6
   of 10. A genuine edge should not need the good seasons.

If it fails any of those, the correct conclusion is that college football is
efficient to Atlas's reach, and the programme should stop.

### Why not sides

| Disagreement ≥ | Bets | Win rate | z |
|---|---|---|---|
| 0 | 5,671 | 0.4974 | -0.3851 |
| 1 | 4,893 | 0.4966 | -0.4718 |
| 2 | 4,200 | 0.4986 | -0.1852 |
| 3 | 3,567 | 0.4948 | -0.6195 |
| 4 | 2,924 | 0.4962 | -0.4068 |
| 6 | 1,931 | 0.4925 | -0.6599 |
| 8 | 1,210 | 0.4876 | -0.8624 |
| 10 | 767 | 0.4602 | -2.2026 |

Flat and declining, confirmed independently by Velocity at 50.1%. Sides are
closed.

## 5. What should Atlas ignore?

- **Any further team-quality work.** Three phases, three families of metric,
  one answer.
- **Quarterback and roster feeds.** The signal that justified them was an
  artefact.
- **Situational angles.** Free, public, computable, and worth zero.
- **The market-failure tail.** It is variance; the 28-point misses look
  identical to everything else beforehand.
- **Closing-line value on sides.** The whole open-to-close window is worth a
  fifth of a point.

---

## A note on what this phase did to itself

Phase 1C's most useful output is that it **falsified its own predecessor's
headline finding**. The Phase 1B quarterback result was produced honestly, with
error bars and a season-by-season check, and it was still wrong - because the
measurement conflated "what happened in the game" with "what was knowable
before it".

Two guards now exist so it does not recur:

1. Every quarterback and continuity variable is reported in both a
   contemporaneous and a **lagged, pre-kickoff** form, and only the second is
   allowed to support a conclusion.
2. Every p-value in the phase goes into **one pooled FDR correction**, so a
   track cannot produce a finding simply by running enough tests.

Both are cheap. Neither existed before this phase, and the first one cost the
programme its only signal.
