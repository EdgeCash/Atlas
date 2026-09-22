# Atlas Alpha Model - Specification

**Status:** recommendation, Phase 1A output. Nothing here has been built.
**Evidence:** [`reports/atlas_research_report_v1.md`](../reports/atlas_research_report_v1.md)
and the CSV tables beside it, generated from 5,778 FBS-vs-FBS games, 2018-2025,
measured leave-one-season-out.

---

## 1. The finding Alpha has to be built around

On this data, with these variables, **the closing line is not beatable and is
not improvable.**

| | Margin | Total |
|---|---|---|
| Closing line, used raw | MAE 12.22, R² 0.443 | MAE 12.71, R² 0.156 |
| Best non-market benchmark | MAE 12.92 (ESPN pre-game FPI projection) | MAE 13.15 (efficiency) |
| Best gain from *adding* anything to the closing line | **+0.0000** MAE (neutral site, t = 0.15) | **+0.0098** MAE (line movement, t = 1.23) |
| Best out-of-sample hit rate against the line | 50.8% (margin) | 52.0% (total) |

Break-even at -110 is 52.38%. Nothing cleared it. Every marginal gain over the
closing line is a small fraction of a point of MAE, none reaches a paired
per-game t-statistic of 2, and most are outright negative - the variable added
variance and no information. The report carries the error bar next to every
gain precisely so that a 0.01 MAE point estimate cannot be mistaken for an
edge.

That is not a disappointing result, it is a design constraint. It says the
Alpha model's job is **not** to be a better independent forecaster of margin.
An independent forecaster built from these public inputs lands ~0.7 to ~1.9
points of MAE worse than the line, which is a 5-15% error increase and would
lose steadily. The job is to find the narrow, specific situations where the
line is wrong, and to be silent everywhere else.

---

## 2. What Atlas Alpha should use

### 2.1 Architecture: market-anchored residual model

Alpha should predict the **residual against the closing line**, not the margin:

```
predicted_margin = market_margin + alpha_adjustment
predicted_total  = closing_total + alpha_adjustment_total
```

where `alpha_adjustment` is a heavily regularised model trained on
`actual_margin - market_margin`, and is **shrunk to zero by default**.

Reasons this and not a from-scratch margin model:

* The market already explains 44% of margin variance and 16% of total
  variance. A from-scratch model must re-derive all of that before it can add
  anything, and every feature it spends on re-deriving is a feature that can
  overfit.
* Residual modelling makes "no opinion" the default output, which matches the
  evidence: the honest prediction for the overwhelming majority of games is
  the line.
* It makes the success criterion legible. Alpha is working if and only if the
  residual model's out-of-sample MAE on `actual - market` is below the
  market's own, on held-out seasons. Phase 1A already provides that baseline.

### 2.2 Feature roles

| Variable | Use it? | Role |
|---|---|---|
| **Market spread / total** | **Yes - as the anchor** | Not a feature. The origin the model predicts deviations from. |
| **EPA (offense and defense)** | **Yes - core state** | The primary description of team strength. Strongest efficiency family for totals (standalone gain 0.331), near-strongest for margin (2.060). Use opponent-adjusted (see §4). |
| **Success Rate** | **Yes - core state** | The best single efficiency variable for margin (standalone gain 2.116, ahead of EPA). Keep both: success rate is the frequency component, EPA the value component, and they disagree often enough to be worth separating. |
| **Pace** | **Totals only** | Standalone gain 0.319 on totals - third best non-market variable - and 0.001 on margin, i.e. nothing. Use as a possession-count term in the total model. Never as a strength term in the margin model. |
| **FPI** | **Yes, but only the game projection** | ESPN's pre-game *matchup* projection is the best non-market margin predictor in the study (MAE 12.92). The *season rating* used as a prior-season value is much weaker (MAE 14.10). Role: an independent second opinion for disagreement detection, not a feature in the primary fit. |
| **SP+** | **Provisionally yes, as a preseason prior only** | Not measurable in this build (CFBD key required). Given that every other season-level rating tested behaved as a weak prior, SP+ should enter as a week-0 prior that decays as in-season efficiency accumulates - not as a standing feature. Re-run the study with a key before committing. |
| **Elo (pre-game)** | **Yes - as the cold-start prior** | MAE 13.11 standalone, and it is genuinely pre-game with no staleness. Best available week-1-to-4 stand-in before efficiency stabilises. |
| **Explosiveness** | **Fold into EPA, do not use standalone** | Standalone gain 0.094 on margin. It is mostly the tail of EPA. Keep it as a diagnostic, not a feature. |
| **Finishing Drives** | **Weak yes, with suspicion** | Standalone gain 1.010 on margin, but it is heavily red-zone-luck driven and should be expected to regress. Use only if it survives a stability test across seasons. |
| **Havoc** | **No** | Standalone gain 0.394, negative marginal value over market, and it is largely a byproduct of opponent pass rate. |
| **Recruiting / Returning Production** | **Unmeasured - hold** | CFBD-only, not available in this build. Expected role is preseason prior alongside SP+, decaying to zero by ~week 5. Do not wire in until measured. |
| **Weather** | **Unmeasured - hold, but prioritise** | CFBD-only. Wind in particular is the one variable in the brief with a well-documented totals effect that this build could not test. This is the highest-value missing measurement. |
| **Rest** | **No** | Standalone gain **-0.007** on margin. Negative. |
| **Travel** | **No** | Standalone gain **-0.004** on margin. Negative. |
| **Neutral site** | **Structural control only** | Needed so home-field advantage is applied correctly. Not a predictor. |
| **Line movement** | **No, as used here** | Standalone gain -0.057 on margin. The *aggregate* open-to-close move carries nothing. A path-aware version (steam, reverse line movement, book disagreement) is a different variable and is untested. |

### 2.3 Explicitly excluded from Alpha v1

Rest, travel, havoc, neutral site as a predictor, open-to-close line movement
as a scalar, season-level SP+/FPI ratings as standing features, and
explosiveness as an independent input. Each either measured negative or was
subsumed by a variable already in the set.

---

## 3. Model form

**Margin**

```
target      = actual_margin - market_margin
features    = opponent-adjusted EPA diff, success rate diff,
              (FPI game projection - market_margin), Elo diff residual,
              preseason prior residual (SP+ / recruiting / returning), 
              structural: neutral site
estimator   = ridge or a depth-2 GBM, strongly regularised
output gate = emit an opinion only when |adjustment| exceeds a threshold
              calibrated so the emission rate is single-digit percent
```

**Total**

```
target      = actual_total - closing_total
features    = EPA sum, success rate sum, pace / plays-per-game sum,
              explosiveness sum, weather (wind, temperature, precipitation)
estimator   = same
```

Totals deserve their own model with sum-form features, not difference-form
ones. This study shows why: pace is the third most informative non-market
variable for totals and is worth nothing for margin, and that only becomes
visible once features are built in sum form.

---

## 4. The three things most likely to create an actual edge

Phase 1A tested the variables in the brief. None of them beat the line. The
work that follows should go where this study did **not** look:

1. **Opponent adjustment.** Every efficiency feature here is a raw average of
   a team's prior games. It does not know that one team played three top-10
   defences and the other played three bottom-20 ones. SP+ and FPI both do
   adjust, and both beat raw efficiency in this study. Opponent-adjusting the
   Atlas efficiency features is the single highest-expected-value change, and
   it needs no new data.
2. **Roster availability.** Quarterback status is the largest single
   information asymmetry in college football and appears nowhere in this
   warehouse. Nothing in the current feature set can represent it.
3. **Weather, properly.** Wind is the one brief variable with a well-attested
   totals effect and it is the one this build could not measure at all.

A fourth, lower-confidence avenue: line *path* rather than line movement -
which book moved first, how far the market disagreed with itself, and when.
The scalar open-to-close move measured negative; that does not clear the
path.

---

## 5. What would make Alpha ready to build

- [ ] Re-run Phase 1A with `CFBD_API_KEY` set, so SP+, recruiting, returning
      production and weather are measured rather than assumed.
- [ ] Add opponent adjustment to the efficiency features and re-measure the
      `gain over market` column. If it is still zero, no feature-level work on
      this data will produce an edge.
- [ ] Establish a roster/QB availability source.
- [ ] Only then: build the residual model, and hold it to beating the market's
      MAE on held-out seasons before any wagering logic is discussed.

Until those are done, the correct output of Atlas is the closing line.
