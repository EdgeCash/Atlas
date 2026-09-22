# Point-in-time correctness

Atlas has one non-negotiable rule:

> **A feature attached to a game may only use information that existed before
> that game kicked off.**

This document says how each field family satisfies it, where the rule was
hardest to satisfy, and how the claim is tested rather than asserted.

---

## 1. Why this is the hard part

Almost every convenient college-football data source is published *after* the
season. A season-level SP+ or FPI rating for 2022 is the rating that season
produced; joining it to a week-3 2022 game tells the model who was good that
year. Season-level team stats have the same defect. The result is a model that
looks excellent in backtest and is worthless in front of a live line.

The rule costs accuracy - a week-2 feature genuinely knows less than a week-12
one - and paying that cost honestly is the point of the warehouse.

---

## 2. How each field family complies

| Family | Source timing | Treatment |
|---|---|---|
| Scores, margin, total | After the game | **Outcomes only.** Never used as a feature. |
| Closing / opening spread, total, moneyline | Posted before kickoff | Used as-is. The closing line is the last number posted, so it is pre-kickoff by definition. |
| Efficiency: EPA, success rate, explosiveness, havoc, finishing drives, pace | Derived from plays in past games | Rebuilt as a **prior-games-only** average (§3). |
| Opponent-adjusted efficiency (`adj_*`) | Same plays, solved as a schedule graph | Solved **per week** from strictly earlier weeks only (§3a). |
| FPI season rating | End of season | Only the **previous** season's value is joined. |
| FPI game projection | Published before kickoff | Used as-is. |
| CFBD pre-game Elo | Carried on the schedule, pre-game | Used as-is. |
| SP+ | End of season | Only the **previous** season's value is joined. |
| Recruiting rank, roster talent, returning production | Fixed before the season starts | Same-season value is safe and is used. |
| Days rest | From the schedule | Gap since that team's own previous game. |
| Travel distance, neutral site, venue | Known when the schedule is published | Used as-is. |
| Weather | Nearest station's observation at the kickoff hour | Kickoff conditions, not an outcome. Used as-is. |

---

## 3. The prior-games-only average

For a team's game *n*, a per-game metric is averaged over games *1 … n-1* of
that season only. That leaves weeks 1-3 with almost no sample, so the running
mean is shrunk toward an anchor that was already known before the season
started:

```
feature(game n) = (sum of games 1..n-1  +  k * anchor) / ((n-1) + k)
```

* `anchor` is the team's **previous season** mean for that metric.
* If the team has no previous season (new FBS member, FCS opponent), the
  anchor falls back to the **league's** previous-season mean.
* `k = 4` (`config.PRIOR_SEASON_SHRINKAGE_GAMES`), i.e. the prior season is
  worth about four games of current-season evidence and is outweighed from
  roughly week 5 on.

Both anchors are facts from before the season, so the guarantee holds for
week 1 exactly as it does for week 12. `n_prior_games` is carried alongside
every feature so a consumer can see how much of a value is history and how
much is prior.

### 3a. The opponent-adjusted variant

Opponent adjustment cannot be done one game at a time - it solves all teams
simultaneously - so it uses a slightly coarser clock. For season *S* week *w*,
the solve uses **only games from season *S* in weeks strictly before *w***,
shrunk toward season *S-1*'s final ratings by the same ridge weight (4 games).

Week is the right unit because any game in a week can kick off before any
other. Solving per week therefore cannot see sideways within a week, at the
cost of ignoring the Tuesday game when rating the Saturday one. That is
conservative in the safe direction.

Two details that would break the guarantee if got wrong, and are tested:

* **Weights must be normalised.** Observations are weighted by play count so a
  40-play game counts less than an 80-play one. Play counts average ~56, so
  leaving them raw would make a "4 game" prior worth 0.07 of a game and hand
  back a near-unshrunk, wildly noisy week-1 rating. Weights are normalised to
  mean 1 so the ridge stays in units of games - the same units the raw
  features' shrinkage uses, which is also what makes raw-vs-adjusted a fair
  comparison.
* **The prior is trimmed to teams that actually played.** Otherwise the team
  index grows every season and the solve slowly fills with teams that no
  longer exist.

Two more choices worth stating because they change the numbers:

* **Garbage time is dropped** before aggregation, using the standard
  per-quarter margin thresholds (38/28/22/16). Overtime is never garbage time.
* **Efficiency accumulates over *all* games a team played**, including games
  against FCS opponents, because those games really happened and really do
  inform the next one. Only the *research sample* is restricted to
  FBS-vs-FBS.

---

## 4. What is *not* corrected for

Stated plainly, because it matters for interpreting the report:

* ~~**No opponent adjustment.**~~ **Fixed in Phase 1B.** The raw metrics are
  still carried unchanged, and the `adj_*` family now sits beside them. The
  prediction that this was why raw efficiency trailed SP+/FPI turned out to be
  right for margin - adjusted efficiency now beats both - and irrelevant for
  the market residual, which it did not move at all.
* **No in-season rating archive.** Atlas has no weekly SP+ or FPI history, so
  the only leak-free way to use those ratings is the previous season's value.
  The ESPN pre-game game projection is the exception and is used directly.
* **Line timing.** The "closing" line is the final value in the historical
  feed. Where a book stopped updating early, that value is stale rather than
  truly closing. It is never *later* than kickoff, so it cannot leak; it can
  only make the market benchmark slightly worse than the real close.

---

## 5. How the claim is tested

Four independent checks, all in CI:

1. **Brute-force equivalence.** The vectorised implementation is compared
   row-by-row against a deliberately slow reimplementation that, for each row,
   filters to that team's strictly earlier games and averages them
   (`tests/test_point_in_time.py::test_matches_brute_force_recomputation`).
2. **Tamper test.** Changing a *later* game's metric must leave every earlier
   game's feature bit-identical
   (`test_changing_a_future_game_cannot_change_an_earlier_feature`).
3. **First-game test.** With no in-season history, the feature must equal the
   previous-season anchor exactly - it cannot contain anything from the
   current season (`test_shrinkage_uses_previous_season_not_current`).
4. **Leakage scan.** Every candidate feature's correlation with every outcome
   is measured and anything above 0.98 fails. A synthetic "outcome in
   disguise" feature is injected in the test suite to prove the scan fires
   (`tests/test_research.py::test_leakage_scan_catches_an_outcome_in_disguise`).
5. **Adjustment tamper test.** Inflating every observation from week 6 onward
   must leave the week-1-to-6 ratings bit-identical
   (`tests/test_opponent_adjustment.py::test_point_in_time_ratings_never_use_the_current_week`),
   with a companion check that week 1 is fitted on zero in-season
   observations.

The scan's live output is Appendix B of the research report.

### One thing deliberately left outside the warehouse

The quarterback-of-record series in
`scripts/research_qb_availability.py` is knowable only at kickoff, so it is
**not** a warehouse column. It lives in a research script precisely so it
cannot be picked up by accident as a feature. See
[`reports/qb_availability_report.md`](../reports/qb_availability_report.md).

---

## 6. Evaluation is folded by season, not at random

A random train/test split lets a model learn a season's own scoring
environment from that season's other games - close enough to leakage to
matter, and enough to flatter a totals model badly. Every number Atlas
reports is **leave-one-season-out**: fit on all seasons but one, predict the
held-out season, repeat. A test asserts that a signal present in only one
season cannot be picked up when that season is held out
(`test_leave_one_season_out_never_trains_on_the_held_out_season`).
