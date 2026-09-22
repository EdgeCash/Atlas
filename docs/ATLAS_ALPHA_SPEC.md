# Atlas Alpha Model - Specification

**Status:** recommendation, amended after Phase 1B. Nothing here has been built.
**Evidence:** [`reports/atlas_research_report_v1.md`](../reports/atlas_research_report_v1.md),
[`reports/opponent_adjustment_report.md`](../reports/opponent_adjustment_report.md),
[`reports/weather_data_report.md`](../reports/weather_data_report.md),
[`reports/qb_availability_report.md`](../reports/qb_availability_report.md)
and the CSV tables beside them, generated from 5,778 FBS-vs-FBS games,
2018-2025, measured leave-one-season-out.

> ### Phase 1B amendment
>
> Phase 1A's top recommendation was to opponent-adjust the efficiency metrics.
> Phase 1B did it, and the result splits in two:
>
> * **Against Atlas's own metrics and the public ratings: a decisive win.**
>   Adjusted efficiency removes 0.53 points of margin MAE against raw
>   (t = 7.3) and now beats SP+ (14.19) and FPI (14.10) outright at 13.42.
> * **Against the closing line: still exactly nothing.** Every residual model
>   lands on the baseline, adjusted no better than raw.
>
> Two further hypotheses were tested. **Weather is now measured** from a free
> source and is priced by the market - no feature set clears its error bar.
> **Quarterback availability is not**, and a retrospective probe shows a team
> starting a different quarterback than the week before underperforms the
> closing line by roughly 2.3 points, significant in 6 of 8 seasons. That is
> the only non-zero signal either phase has produced.
>
> Changes below are marked **[1B]**.

---

## 1. The finding Alpha has to be built around

On this data, with these variables, **the closing line is not beatable and is
not improvable.**

| | Margin | Total |
|---|---|---|
| Closing line, used raw | MAE 12.22, R² 0.443 | MAE 12.71, R² 0.156 |
| Best non-market benchmark | MAE 12.92 (ESPN pre-game FPI projection) | MAE 13.15 (efficiency) |
| Best gain from *adding* anything to the closing line | **+0.0056** MAE (returning production, t = 1.05) | **+0.0098** MAE (line movement, t = 1.23) |
| Best out-of-sample hit rate against the line | 51.0% (margin) | 52.0% (total) |

Break-even at -110 is 52.38%. Nothing cleared it. Every marginal gain over the
closing line is a small fraction of a point of MAE, none reaches a paired
per-game t-statistic of 2, and most are outright negative - the variable added
variance and no information. The report carries the error bar next to every
gain precisely so that a 0.01 MAE point estimate cannot be mistaken for an
edge.

That is not a disappointing result, it is a design constraint. It says the
Alpha model's job is **not** to be a better independent forecaster of margin.
An independent forecaster built from these public inputs lands ~0.7 to ~2.0
points of MAE worse than the line, which is a 5-16% error increase and would
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
| **EPA (offense and defense)** | **Yes - core state, adjusted [1B]** | The primary description of team strength. Use `adj_off_epa` / `adj_def_epa`: adjustment removes 0.57 points of margin MAE over raw EPA (t = 7.7). |
| **Success Rate** | **Yes - core state, adjusted [1B]** | The best single metric for margin in both forms, and `adj_success_rate` is now the single best of all 21 metrics ranked (gain 1.72). Keep both success rate and EPA: frequency and value components disagree often enough to be worth separating. |
| **Pace** | **Totals only - and keep it RAW [1B]** | Standalone gain 0.319 on totals, ~0 on margin. Adjustment makes pace measurably *worse* on both targets (t = -2.5 margin, -2.8 total): a slow team's low play count is a property of that team, not a distortion to correct. Use raw `pace` and `plays_per_game` in the totals model only. |
| **FPI** | **Only the game projection - drop the rating [1B]** | ESPN's pre-game *matchup* projection is still the best non-market margin predictor (MAE 12.92). The season rating (14.10) is now beaten by Atlas's own adjusted efficiency (13.42) and adds nothing on top of it, so drop it as a feature. Keep the game projection as an independent second opinion for disagreement detection. |
| **SP+** | **Preseason prior only - demoted [1B]** | Measured. Weakest margin benchmark tested (14.18), and adding it to adjusted efficiency moves margin MAE from 13.39 to 13.34 - within noise. It was standing in for the opponent adjustment Atlas was missing; now that Atlas does the adjustment itself, SP+ is redundant as a standing feature. Keep `sp_plus_off` / `sp_plus_def` as a **week-0 prior** for the totals model, where its offence/defence split still carries real information (13.57, best non-market totals rating). |
| **Elo (pre-game)** | **Yes - as the cold-start prior** | MAE 13.11 standalone, and it is genuinely pre-game with no staleness. Best available week-1-to-4 stand-in before efficiency stabilises. |
| **Explosiveness** | **Fold into EPA, do not use standalone** | Standalone gain 0.094 raw, 0.134 adjusted. Mostly the tail of EPA either way. Diagnostic, not a feature. |
| **Finishing Drives** | **Yes, adjusted [1B]** | Adjustment nearly doubles it: standalone gain 1.010 raw to 1.158 adjusted, and the paired improvement is the second largest of any metric (t = 11.3). The red-zone-luck concern stands, so still subject to a stability check, but it is no longer a marginal call. |
| **Havoc** | **Promoted to a weak yes, adjusted [1B]** | Phase 1A rejected raw havoc at gain 0.394. Adjusted havoc gains 0.503 and the raw-to-adjusted improvement is the *largest* of any metric (t = 11.5) - havoc was the metric most distorted by schedule, which is what you would expect from something so dependent on opponent pass rate. Include `adj_havoc` and `adj_havoc_allowed` in the margin model; both still contribute nothing over the market. |
| **Recruiting** | **Preseason prior only** | Measured. Standalone gain 1.245 on margin - a genuinely informative variable, ahead of havoc and explosiveness - but its marginal value over the closing line is **negative** (t = -2.12) and it is negative for totals too. It knows roughly what the market already knows about a roster. Role: a week-0 prior, decaying to zero by ~week 5, never a standing feature. |
| **Returning Production** | **No** | Measured. Standalone gain 0.087 on margin, essentially nothing, and **-0.014 on totals**. Its one positive marginal number (+0.0056 on margin, t = 1.05) does not clear its own noise. Exclude from v1. |
| **Weather** | **Measured, and excluded [1B]** | Solved with free Meteostat station data - 89% coverage, median station 5 miles from the stadium, no API key. Scoring does fall about three points from calm to 15-20 mph wind, **and the closing total falls with it**: no wind band's over rate is two standard errors from 50%, and no weather feature set clears its error bar on any target. The market prices weather. Keep the data, give it no role in v1. |
| **Rest** | **No** | Standalone gain **-0.007** on margin. Negative. |
| **Travel** | **No** | Standalone gain **-0.004** on margin. Negative. |
| **Neutral site** | **Structural control only** | Needed so home-field advantage is applied correctly. Not a predictor. |
| **Line movement** | **No, as used here** | Standalone gain -0.057 on margin. The *aggregate* open-to-close move carries nothing. A path-aware version (steam, reverse line movement, book disagreement) is a different variable and is untested. |

### 2.3 Explicitly excluded from Alpha v1

Rest, travel, returning production, weather **[1B]**, neutral site as a
predictor, open-to-close line movement as a scalar, season-level SP+/FPI
ratings as standing margin features **[1B]**, adjusted pace **[1B]**, and
explosiveness as an independent input. Each either measured negative, failed
to clear its own noise, or was subsumed by a variable already in the set.

Havoc and finishing drives move **out** of this list in their adjusted forms
**[1B]**.

---

## 3. Model form

**Margin**

```
target      = actual_margin - market_margin
features    = adj_off_epa_diff, adj_def_epa_diff,
              adj_success_rate_diff, adj_def_success_rate_diff,
              adj_havoc_diff, adj_finishing_drives_diff,
              (FPI game projection - market_margin), Elo diff residual,
              preseason prior residual (SP+ / recruiting)
estimator   = ridge or a depth-2 GBM, strongly regularised
output gate = emit an opinion only when |adjustment| exceeds a threshold
              calibrated so the emission rate is single-digit percent
```

No `neutral_site` term: the closing line already prices home advantage, so a
residual model must not refit it. **[1B]**

**Total**

```
target      = actual_total - closing_total
features    = adj_off_epa_sum, adj_def_epa_sum, adj_success_rate_sum,
              RAW pace_sum and plays_per_game_sum,
              sp_plus_off_sum and sp_plus_def_sum as a week-0 prior
estimator   = same
```

Pace stays raw and weather is out. **[1B]** Adjustment hurts pace on both
targets, and weather did not clear its error bar anywhere.

Totals deserve their own model with sum-form features, not difference-form
ones. This study shows why twice over: pace is the third most informative
non-market variable for totals and is worth nothing for margin, and SP+ goes
from the *worst* margin rating to the *best* non-market totals rating once its
offence and defence components are carried separately. Neither becomes visible
until features are built in sum form.

---

## 4. The three things most likely to create an actual edge

Phase 1A tested the variables in the brief. None of them beat the line. The
work that follows should go where this study did **not** look:

1. ~~**Opponent adjustment.**~~ **Done in Phase 1B, and settled.** It was the
   right call for Atlas's own accuracy - 0.53 points of margin MAE, and Atlas
   now beats SP+ and FPI rather than trailing them - and it moved the market
   residual by nothing. The hypothesis that raw metrics were why Phase 1A
   found no edge is now **rejected**.
2. **Roster availability.** Now the clear leader. Quarterback status is the
   largest single information asymmetry in college football, it appears
   nowhere in this warehouse, and Phase 1B measured its value: a team starting
   a different quarterback than the week before underperforms the closing line
   by ~2.3 points, significant in 6 of 8 seasons. That is an upper bound on
   perfect pre-kickoff knowledge, not an achievable edge - but it is the only
   number in this programme that is not zero.
3. ~~**Weather, properly.**~~ **Done in Phase 1B, and priced.** Free, 89%
   coverage, no material effect on any target once the closing total is
   accounted for.

A fourth, lower-confidence avenue: line *path* rather than line movement -
which book moved first, how far the market disagreed with itself, and when.
The scalar open-to-close move measured negative; that does not clear the path.

**What Phase 1B rules out.** Three independent families of team-quality
measurement - raw efficiency, Atlas's adjusted efficiency, and the published
adjusted ratings - all land on the same residual baseline. Measuring team
quality more precisely is no longer a promising direction. The next hypothesis
has to concern information the market does not have.

---

## 5. What would make Alpha ready to build

- [x] Re-run Phase 1A with `CFBD_API_KEY` set - SP+, roster talent, recruiting
      and returning production measured.
- [x] **Measure weather, especially wind against totals.** Done with free
      Meteostat data. The market prices it.
- [x] **Add opponent adjustment and re-measure the `gain over market` column.**
      Done. It is still zero. The conditional in the Phase 1A version of this
      line - *"if it is still zero, no feature-level work on this data will
      produce an edge"* - has now fired.
- [ ] **Establish a pre-kickoff roster / QB availability source.** Now the
      only open item that could change the answer. Commercial feeds are the
      only route with history; start capturing announced starters weekly in
      parallel, since that archive only becomes valuable with age.
- [ ] Only then: build the residual model, and hold it to beating the market's
      MAE on held-out seasons before any wagering logic is discussed.

Until that is done, the correct output of Atlas is the closing line.
