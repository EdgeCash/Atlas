# Atlas Signal Verification - Final Report

*Generated 2026-09-22 16:05 UTC. Criteria fixed in
[`docs/SIGNAL_PREREGISTRATION.md`](../docs/SIGNAL_PREREGISTRATION.md) and
committed before any holdout season was scored. Each experiment was scored
exactly once.*

---

# VERDICT: NO

**The selective NCAAF totals signal is not real.** It is the final artifact.

0 of 4 pre-registered criteria passed.

---

## The six required answers

**1. Is the signal real?**
**NO.** All four pre-registered criteria failed.

**2. What is the estimated true win rate?**
**51.65%**, 95% interval
[49.81%, 53.49%]. The interval contains 50%.
Break-even at -110 is 52.38%.

**3. What is the estimated true ROI?**
**-1.40%** per bet at -110, or -39.6 units on
2,825 bets. At -115 it is -3.44%.

**4. Does it survive holdout validation?**
**NO.** Each split was scored once, at a threshold frozen on its training
seasons alone:

| Experiment | Split | Threshold | Bets | Win rate | Units | ROI |
|---|---|---|---|---|---|---|
| A | train 2018-2024, test 2025 | 8 | 42 | 0.5000 | -1.9091 | -0.0455 |
| B | train 2018-2023, test 2024 | 7 | 88 | 0.5568 | 5.5455 | 0.0630 |
| C | train 2019-2025, test 2018 | 1 | 597 | 0.4891 | -39.5455 | -0.0662 |

**5. Does it survive season-by-season validation?**
**NO.** 4 positive, 1 neutral, 3 negative seasons -
against a pre-registered requirement of at least
5 of 7.

**6. Would you deploy real capital?**
**NO.**

---

## The pre-registered criteria, applied mechanically

| Criterion | Required | Observed | Verdict |
|---|---|---|---|
| 1. Pooled holdout win rate > 52.38% | > 0.5238 | 0.5165 | FAIL |
| 2. Bootstrap 95% CI lower bound > 50.0% | > 0.50 | 0.4981 | FAIL |
| 3. At least 5 of 7 walk-forward seasons clear -110 | >= 5 | 4.0000 | FAIL |
| 4. Positive expected units at -115 | > 0 units | -97.3043 | FAIL |

Not one passed. There is no reading of this in which the signal survives.

## Task 1 - true holdout

| Fold | Split | Threshold | Selectable | Bets | Wins | Win rate | Units | ROI | z |
|---|---|---|---|---|---|---|---|---|---|
| WF2019 | train 2018-2018, test 2019 | 1 | no | 587 | 313 | 0.5332 | 10.5455 | 0.0180 | 1.6097 |
| WF2020 | train 2018-2019, test 2020 | 1 | no | 427 | 249 | 0.5831 | 48.3636 | 0.1133 | 3.4359 |
| WF2021 | train 2018-2020, test 2021 | 1 | yes | 645 | 319 | 0.4946 | -36.0000 | -0.0558 | -0.2756 |
| WF2022 | train 2018-2021, test 2022 | 6 | yes | 317 | 149 | 0.4700 | -32.5455 | -0.1027 | -1.0671 |
| WF2023 | train 2018-2022, test 2023 | 7 | yes | 122 | 67 | 0.5492 | 5.9091 | 0.0484 | 1.0864 |
| WF2024 | train 2018-2023, test 2024 | 7 | yes | 88 | 49 | 0.5568 | 5.5455 | 0.0630 | 1.0660 |
| WF2025 | train 2018-2024, test 2025 | 8 | yes | 42 | 21 | 0.5000 | -1.9091 | -0.0455 | 0.0000 |

Pooled across 2018-2025 with every season scored once:
**51.65% on 2,825 bets, -39.6 units.**
Restricted to folds whose threshold was genuinely selectable, it falls to
**49.53%**.

## Task 2 - threshold freezing

The frozen threshold ranged **1 to 8 points** across experiments differing only
in which seasons they trained on. See
[`threshold_freeze_report.md`](threshold_freeze_report.md). There is no stable
threshold to freeze, which is what fitting noise looks like.

## Task 3 - season stability

| Season | Bets | Wins | Win rate | Units | ROI | z | Verdict |
|---|---|---|---|---|---|---|---|
| 2018 | 597 | 292 | 0.4891 | -39.5455 | -0.0662 | -0.5321 | negative |
| 2019 | 587 | 313 | 0.5332 | 10.5455 | 0.0180 | 1.6097 | positive |
| 2020 | 427 | 249 | 0.5831 | 48.3636 | 0.1133 | 3.4359 | positive |
| 2021 | 645 | 319 | 0.4946 | -36.0000 | -0.0558 | -0.2756 | negative |
| 2022 | 317 | 149 | 0.4700 | -32.5455 | -0.1027 | -1.0671 | negative |
| 2023 | 122 | 67 | 0.5492 | 5.9091 | 0.0484 | 1.0864 | positive |
| 2024 | 88 | 49 | 0.5568 | 5.5455 | 0.0630 | 1.0660 | positive |
| 2025 | 42 | 21 | 0.5000 | -1.9091 | -0.0455 | 0.0000 | neutral |

**Can the signal survive bad seasons?** The question does not arise. It does
not survive the *average* season. The two profitable years carrying the record
(2019, 2020) are the two whose threshold could not be selected without a
fallback, and 2020 was a pandemic-shortened season with unusual scoring.

## Task 4 - juice sensitivity

| Price | Break-even | Observed | Edge | Units | ROI | Profitable |
|---|---|---|---|---|---|---|
| -105 | 0.5122 | 0.5165 | 0.0043 | 23.5238 | 0.0083 | yes |
| -110 | 0.5238 | 0.5165 | -0.0073 | -39.6364 | -0.0140 | no |
| -115 | 0.5349 | 0.5165 | -0.0184 | -97.3043 | -0.0344 | no |
| -120 | 0.5455 | 0.5165 | -0.0290 | -150.1667 | -0.0532 | no |

Profitable at **-105 only**, by 0.43% - and -105
on college totals is not a price that exists at size. At -110 it loses
40 units; at -120 it loses
150.

## Task 5 - bootstrap

P(true rate > 52.38%) = **22.2%**.
P(> 53%) = **7.0%**. P(> 55%) = **0.0%**.
Full detail in [`bootstrap_signal_report.md`](bootstrap_signal_report.md).

## Task 6 - failure analysis

| Cause | Implicated | Evidence |
|---|---|---|
| Threshold sensitivity | yes | the frozen threshold ranged 1 to 8 points across experiments that differ only in which seasons they trained on |
| Season instability | yes | 4 of 7 walk-forward seasons cleared -110; season win rates span 0.470 to 0.583 |
| Holdout collapse | yes | Phase 1C's in-sample scan read 52.4% at a 4-point cut; the pooled true holdout reads 0.5165 |
| Sample size | yes | bets per season ranged 42 to 645; the highest-threshold folds bet fewer than 100 games, where a 55% read is noise |
| Multiple testing | yes | Phase 1C scanned eight thresholds on the full sample and reported the best; this phase scanned none on holdout data and the apparent edge disappeared |
| Market adaptation | no | at a fixed 4-point threshold the win rate averaged 0.522 in 2019-2021 and 0.534 in 2022-2025 - no trend consistent with the market learning; the signal was never there to adapt to |
| Sample variance | yes | the bootstrap 95% interval on the pooled holdout is [0.4981, 0.5349] - it contains 50% |

The diagnostic worth stating separately: holding the threshold **fixed at 4
points** across every walk-forward season - removing the selection rule
entirely - gives 52.36%
on 2,225 bets.

| Season | Bets | Wins | Win rate | Units | ROI | z |
|---|---|---|---|---|---|---|
| 2019 | 330 | 176 | 0.5333 | 6.0000 | 0.0182 | 1.2111 |
| 2020 | 225 | 124 | 0.5511 | 11.7273 | 0.0521 | 1.5333 |
| 2021 | 400 | 193 | 0.4825 | -31.5455 | -0.0789 | -0.7000 |
| 2022 | 437 | 214 | 0.4897 | -28.4545 | -0.0651 | -0.4305 |
| 2023 | 314 | 173 | 0.5510 | 16.2727 | 0.0518 | 1.8059 |
| 2024 | 282 | 160 | 0.5674 | 23.4545 | 0.0832 | 2.2629 |
| 2025 | 237 | 125 | 0.5274 | 1.6364 | 0.0069 | 0.8444 |

That is the single most favourable honest reading available, and it lands
**0.0214% from break-even**
- a coin flip against the vig, netting
-0.9 units across seven
seasons. The most charitable version of the signal is indistinguishable from
zero.

Note also what is *not* implicated: **market adaptation**. At a fixed
threshold the win rate is no worse in recent seasons than early ones. The
market did not learn to price this. There was nothing to learn.

## Task 7 - capital allocation

| Bets | Units | ROI | Max drawdown | Longest losing streak | Profit factor |
|---|---|---|---|---|---|
| 2825.0000 | -39.6364 | -0.0140 | 80.7273 | 9.0000 | 0.9710 |

**Even if it were real, is it tradable?** No. A profit factor of
0.971 is a losing book. The maximum drawdown is
81 units - more than twice the pre-registered
40-unit tolerance - on a strategy whose total
return is negative. Anyone staking this would have sat through a
9-bet losing streak and an
81-unit hole to arrive at -39.6.

| Deployment check | Required | Observed | Verdict |
|---|---|---|---|
| Max drawdown < 40 units | < 40 | 80.7273 | FAIL |
| Profit factor > 1.05 | > 1.05 | 0.9710 | FAIL |
| P(true win rate > 53%) > 50% | > 0.5 | 0.0705 | FAIL |

---

## Recommendation: terminate Atlas Alpha

Per the phase brief, and without qualification.

Four phases have now tested, against the closing line:

| Phase | Tested | Result |
|---|---|---|
| 1A | Market, SP+, FPI, Elo, raw efficiency, recruiting, returning production, weather | all priced |
| 1B | Opponent-adjusted efficiency, free weather | all priced |
| 1C | Quarterback events, roster and staff continuity, situational angles, market failures, line movement - 50 tests | zero survivors after correction |
| This phase | The one remaining candidate, pre-registered and held out | fails all four criteria |

The closing line is a complete summary of the information Atlas can reach.
That is a real finding, arrived at honestly, and it is worth more than a
model that would have lost money slowly.

### What was actually built, and is worth keeping

The warehouse is not wasted by this verdict. It is a clean,
point-in-time-correct, reproducible research instrument for college football,
and the negative results are reusable: anyone starting this search again can
begin from "these forty variables are priced" rather than spending three
phases rediscovering it.

### If the search is ever restarted

Not with better features. Three phases say that direction is closed. The only
untested hypotheses left require **information the market does not have** -
which in practice means non-public, timely, or expensive:

- a timestamped line archive, to measure closing-line value rather than
  outcomes (Phase 1C measured the whole open-to-close window at 0.22 points,
  so the ceiling is low);
- genuinely private information, which is a different business with different
  legality;
- markets less efficient than FBS sides and totals - lower divisions, obscure
  props, live - each of which is a fresh research programme, not an extension
  of this one.

None of those is a reason to keep Atlas Alpha open today.

### The methodological record

Three things this programme got wrong and then caught, worth carrying forward:

1. **Phase 1B's quarterback signal** was reverse causation, caught in 1C by
   splitting contemporaneous from lagged variables.
2. **Phase 1C's totals signal** was threshold selection on the full sample,
   caught here by pre-registering and holding out.
3. **Phase 1B's opponent-adjustment weights** were silently rescaling the
   ridge prior to 0.07 games, caught by unit analysis before publication.

Each was found by asking what would have to be true for the result to be
false. That is the habit worth keeping, and it is the reason to trust this
report's NO more than the earlier reports' YES.
