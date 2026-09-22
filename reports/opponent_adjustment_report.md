# Atlas Opponent Adjustment Report (Phase 1B)

*Generated 2026-09-22 14:47 UTC from `data/warehouse/atlas.duckdb`. Every figure is
produced by `python -m atlas.research.phase1b_report`; none is hand-entered.*

Phase 1A ended with one recommendation above all others: **opponent-adjust the
efficiency metrics**. Raw EPA does not know that one team played three top-10
defences and the other played three bottom-20 ones, and the two published
systems that do adjust - SP+ and FPI - both beat Atlas's raw efficiency.

Phase 1B does the adjustment and measures what it is worth. The answer splits
cleanly in two, and the split is the whole finding:

* **Against raw efficiency and against the published ratings, adjustment is a
  decisive win.** It removes 0.531 points of margin MAE
  (t = 7.3) and moves Atlas from behind SP+ and FPI to ahead of
  both.
* **Against the closing line, it is worth nothing at all.** Not less than
  before - the same nothing. Every residual model lands on the baseline.

Research sample: **5,778 FBS-vs-FBS games**, 2018-2025,
leave-one-season-out throughout.

---

## Method

Each metric is one stream of observations in which an **actor** produces a
value against an **opponent**:

    value = mu + actor_effect + opponent_effect + hfa * (home - 0.5)

For EPA the actor is the offence, so a single solve yields both what a team
produces against an average defence (`adj_off_epa`) and what it allows to an
average offence (`adj_def_epa`). For havoc the defence is the actor.

| Method | What it does | Cost |
|---|---|---|
| **A - simple** | One pass: subtract each opponent's raw average, then average | Under-corrects; the averages it subtracts are themselves unadjusted |
| **B - iterative** | Alternate actor and opponent solves to convergence (Gauss-Seidel) | Converges in ~20 iterations |
| **C - network** | One ridge least-squares solve over the whole schedule graph (Massey/SRS) | Exact; handles unbalanced and weakly connected schedules directly |

**Point-in-time.** For season *S* week *w*, the solve uses only games from
season *S* in weeks strictly before *w*, shrunk toward season *S-1*'s final
ratings. Week is the unit of time because any game in a week can kick off
before any other, so a per-week solve cannot see sideways. The shrinkage is
the same device and the same strength (4 games) that the raw features use, so
raw and adjusted are compared on equal footing rather than one being smoothed
more than the other.

**Weighting.** Observations are weighted by play count - a 40-play game says
less than an 80-play one - normalised so the average game weighs exactly 1.
The normalisation matters more than it sounds: play counts average ~56, so
leaving them raw would have made a "4 game" prior worth 0.07 of a game and
handed back wildly noisy early-season ratings.

---

## Section 1 - Raw vs Adjusted Metrics

Out-of-sample MAE for each metric family, raw and adjusted, on every target.

| Metric | Raw MAE | Adjusted MAE | Improvement | Raw R² | Adj R² |
|---|---|---|---|---|---|
| EPA | 14.1545 | 13.5863 | 0.5682 | 0.2496 | 0.3170 |
| Success Rate | 14.0985 | 13.6305 | 0.4679 | 0.2586 | 0.3118 |
| Explosiveness | 16.1208 | 15.9745 | 0.1463 | 0.0181 | 0.0435 |
| Havoc | 15.8203 | 14.7668 | 1.0535 | 0.0594 | 0.1944 |
| Finishing Drives | 15.2052 | 14.1898 | 1.0155 | 0.1336 | 0.2541 |
| Pace | 16.2055 | 16.2200 | -0.0145 | 0.0009 | -0.0010 |
| Full efficiency model | 13.9506 | 13.4193 | 0.5313 | 0.2708 | 0.3315 |

*(margin; the other targets are in Sections 4 and 5)*

Paired game-by-game, with a standard error, so a small improvement cannot be
mistaken for a real one:

| Metric | Target | MAE gain | SE | t | Material? |
|---|---|---|---|---|---|
| EPA | margin | 0.5682 | 0.0738 | 7.6945 | yes |
| EPA | total | -0.0124 | 0.0318 | -0.3893 | no |
| EPA | residual_margin | -0.0000 | 0.0018 | -0.0180 | no |
| EPA | residual_total | 0.0040 | 0.0060 | 0.6645 | no |
| Success Rate | margin | 0.4679 | 0.0696 | 6.7184 | yes |
| Success Rate | total | 0.0688 | 0.0265 | 2.5938 | yes |
| Success Rate | residual_margin | -0.0001 | 0.0015 | -0.0508 | no |
| Success Rate | residual_total | 0.0029 | 0.0054 | 0.5483 | no |
| Explosiveness | margin | 0.1463 | 0.0334 | 4.3783 | yes |
| Explosiveness | total | 0.0342 | 0.0217 | 1.5768 | no |
| Explosiveness | residual_margin | 0.0001 | 0.0025 | 0.0272 | no |
| Explosiveness | residual_total | -0.0013 | 0.0035 | -0.3859 | no |
| Havoc | margin | 1.0535 | 0.0914 | 11.5296 | yes |
| Havoc | total | -0.0121 | 0.0063 | -1.9268 | no |
| Havoc | residual_margin | -0.0038 | 0.0038 | -0.9898 | no |
| Havoc | residual_total | -0.0041 | 0.0032 | -1.2697 | no |
| Finishing Drives | margin | 1.0155 | 0.0897 | 11.3166 | yes |
| Finishing Drives | total | 0.0826 | 0.0444 | 1.8632 | no |
| Finishing Drives | residual_margin | 0.0009 | 0.0042 | 0.2066 | no |
| Finishing Drives | residual_total | -0.0008 | 0.0084 | -0.0959 | no |
| Pace | margin | -0.0145 | 0.0057 | -2.5225 | no |
| Pace | total | -0.0582 | 0.0211 | -2.7624 | no |
| Pace | residual_margin | -0.0029 | 0.0039 | -0.7420 | no |
| Pace | residual_total | 0.0007 | 0.0053 | 0.1238 | no |
| Full efficiency model | margin | 0.5313 | 0.0731 | 7.2718 | yes |
| Full efficiency model | total | -0.0509 | 0.0356 | -1.4283 | no |
| Full efficiency model | residual_margin | 0.0075 | 0.0072 | 1.0420 | no |
| Full efficiency model | residual_total | -0.0076 | 0.0089 | -0.8532 | no |

### Method A vs B vs C

| Method | Target | Features | MAE | RMSE | R² |
|---|---|---|---|---|---|
| simple (A) | margin | 9 | 13.7183 | 17.3650 | 0.2974 |
| simple (A) | total | 9 | 13.3290 | 16.7767 | 0.0771 |
| simple (A) | residual_margin | 9 | 12.2289 | 15.4635 | -0.0011 |
| simple (A) | residual_total | 9 | 12.7308 | 16.0534 | -0.0020 |
| iterative (B) | margin | 9 | 13.4193 | 16.9386 | 0.3315 |
| iterative (B) | total | 9 | 13.2166 | 16.6566 | 0.0903 |
| iterative (B) | residual_margin | 9 | 12.2230 | 15.4561 | -0.0001 |
| iterative (B) | residual_total | 9 | 12.7320 | 16.0537 | -0.0020 |
| network (C) | margin | 9 | 13.4193 | 16.9386 | 0.3315 |
| network (C) | total | 9 | 13.2166 | 16.6566 | 0.0903 |
| network (C) | residual_margin | 9 | 12.2230 | 15.4561 | -0.0001 |
| network (C) | residual_total | 9 | 12.7320 | 16.0537 | -0.0020 |

Methods B and C agree to four decimal places on every target, which is what
should happen - they solve the same system, one by iteration and one in closed
form. Method A is measurably worse on margin, exactly as the theory predicts:
a single pass subtracts opponent averages that have not themselves been
adjusted, so it under-corrects. **Use C**: it is exact, it is the fastest of
the three here, and it degrades gracefully when the schedule graph is weakly
connected.

---

## Section 2 - Schedule Strength Impact

If schedules were balanced, opponent adjustment could not change anything.
They are not. This is the mean opponent quality faced, per team-season, on the
defensive-EPA scale (lower = faced tougher defences):

| Season | Teams | Mean | SD | Easiest | Hardest | Spread |
|---|---|---|---|---|---|---|
| 2018 | 219 | -0.0125 | 0.0556 | -0.2006 | 0.2937 | 0.4943 |
| 2019 | 217 | -0.0230 | 0.0610 | -0.3873 | 0.1826 | 0.5699 |
| 2020 | 141 | -0.0170 | 0.0457 | -0.1981 | 0.0917 | 0.2899 |
| 2021 | 227 | 0.0188 | 0.0642 | -0.2079 | 0.2318 | 0.4397 |
| 2022 | 293 | -0.0036 | 0.0468 | -0.1285 | 0.1420 | 0.2705 |
| 2023 | 274 | -0.0049 | 0.0503 | -0.1103 | 0.1442 | 0.2545 |
| 2024 | 299 | -0.0128 | 0.0630 | -0.2185 | 0.2675 | 0.4859 |
| 2025 | 310 | 0.0000 | 0.0627 | -0.1353 | 0.2310 | 0.3664 |
| 2026 | 228 | -0.0067 | 0.0580 | -0.2034 | 0.1407 | 0.3440 |

The gap between the hardest and easiest schedule runs **0.25 to 0.57 EPA per
play**. Against a league standard deviation of roughly 0.06 in team quality,
that is a schedule effect several times larger than the differences the metric
is trying to measure. The premise of the phase holds.

*(This table uses end-of-season opponent ratings. It is a description of the
past, never a model input - the features themselves only ever use ratings that
existed before kickoff.)*

---

## Section 3 - Margin Improvements

| Model | Features | MAE | RMSE | R² |
|---|---|---|---|---|
| Elo | 1 | 13.1047 | 16.4963 | 0.3659 |
| Adjusted + SP+ + FPI | 16 | 13.3440 | 16.7871 | 0.3434 |
| Adjusted efficiency (full) | 12 | 13.3906 | 16.8856 | 0.3357 |
| Raw + Adjusted | 18 | 13.4100 | 16.9206 | 0.3329 |
| Adjusted efficiency (matched) | 9 | 13.4193 | 16.9386 | 0.3315 |
| Raw efficiency | 9 | 13.9506 | 17.6905 | 0.2708 |
| FPI | 1 | 14.1031 | 17.8104 | 0.2609 |
| SP+ | 3 | 14.1925 | 17.8748 | 0.2555 |

Three things to read out of this:

1. **Adjustment recovers most of the gap to the best public systems.** Raw
   efficiency was behind SP+ and FPI in Phase 1A. Adjusted efficiency is now
   ahead of both, by a wide margin.
2. **It largely subsumes them.** Adding SP+ and FPI on top of adjusted
   efficiency moves MAE very little, which says the published ratings were
   mostly contributing the opponent adjustment Atlas was missing.
3. **Elo is still competitive.** CFBD's pre-game Elo is a single number and
   holds its own against a twelve-feature adjusted model. Elo is a pure
   result-based rating, so this says a meaningful share of what efficiency
   measures is already visible in who beat whom.

---

## Section 4 - Total Improvements

| Model | Features | MAE | RMSE | R² |
|---|---|---|---|---|
| Raw + Adjusted | 18 | 13.1583 | 16.5809 | 0.0985 |
| Raw efficiency | 9 | 13.1657 | 16.6085 | 0.0955 |
| Adjusted + SP+ + FPI | 16 | 13.2103 | 16.6524 | 0.0907 |
| Adjusted efficiency (full) | 12 | 13.2148 | 16.6528 | 0.0907 |
| Adjusted efficiency (matched) | 9 | 13.2166 | 16.6566 | 0.0903 |
| SP+ | 3 | 13.5695 | 17.1675 | 0.0336 |
| FPI | 1 | 13.8477 | 17.4881 | -0.0028 |
| Elo | 1 | 13.8502 | 17.4898 | -0.0030 |

Adjustment does **not** help on totals. Raw efficiency edges out adjusted, and
the only metric family with a material gain is success rate. Pace gets
actively worse when adjusted.

That is not a failure of the method, it is a statement about the target. An
opponent adjustment redistributes credit between two teams; a total is their
sum, and the adjustment largely cancels. Where it does not cancel - pace - the
adjustment removes the very thing a totals model wants, because a slow team's
low play count is a property of that team, not a distortion to be corrected.

---

## Section 5 - Residual Improvements

**This is the question the phase exists to answer.** The target is
`actual_margin - market_margin`: what the closing line got wrong. The baseline
is "the market is exactly right", which scores MAE
12.224 on margin and
12.705 on totals.

| Model | Features | MAE | R² | Gain over market | t | Material? |
|---|---|---|---|---|---|---|
| Adjusted efficiency (matched) | 9 | 12.2230 | -0.0001 | 0.0013 | 0.1175 | no |
| Line movement | 2 | 12.2261 | -0.0002 | -0.0018 | -0.4050 | no |
| SP+ | 3 | 12.2267 | -0.0006 | -0.0024 | -0.4160 | no |
| FPI | 1 | 12.2274 | -0.0007 | -0.0031 | -2.1168 | no |
| Elo | 1 | 12.2288 | -0.0008 | -0.0045 | -2.4046 | no |
| Adjusted net EPA only | 2 | 12.2292 | -0.0011 | -0.0049 | -2.1142 | no |
| Adjusted efficiency (full) | 12 | 12.2294 | 0.0004 | -0.0051 | -0.3704 | no |
| Raw efficiency | 9 | 12.2305 | -0.0003 | -0.0061 | -0.5946 | no |
| Rest + travel | 2 | 12.2309 | -0.0010 | -0.0065 | -1.1991 | no |
| Adjusted + ratings | 17 | 12.2370 | -0.0006 | -0.0126 | -0.8360 | no |
| Weather (wind/temp/precip) | 5 | 12.2426 | -0.0028 | -0.0183 | -3.1686 | no |

| Model | Features | MAE | R² | Gain over market | t | Material? |
|---|---|---|---|---|---|---|
| Adjusted net EPA only | 2 | 12.7156 | 0.0001 | -0.0107 | -1.0243 | no |
| SP+ | 3 | 12.7158 | -0.0001 | -0.0109 | -1.1763 | no |
| Elo | 1 | 12.7163 | -0.0005 | -0.0114 | -1.5608 | no |
| FPI | 1 | 12.7192 | -0.0006 | -0.0144 | -2.1011 | no |
| Weather (wind/temp/precip) | 5 | 12.7203 | -0.0024 | -0.0154 | -2.0150 | no |
| Rest + travel | 2 | 12.7219 | -0.0012 | -0.0170 | -2.9678 | no |
| Line movement | 2 | 12.7232 | -0.0017 | -0.0183 | -2.5447 | no |
| Raw efficiency | 9 | 12.7245 | -0.0010 | -0.0196 | -1.4732 | no |
| Adjusted efficiency (matched) | 9 | 12.7320 | -0.0020 | -0.0272 | -1.9156 | no |
| Adjusted efficiency (full) | 12 | 12.7337 | -0.0019 | -0.0288 | -1.8966 | no |
| Adjusted + ratings | 17 | 12.7434 | -0.0034 | -0.0385 | -2.2191 | no |

And the same question asked the other way - does adjusted efficiency add
anything *on top of* the closing line?

| Model | Target | Market MAE | Combined MAE | Gain | t | Material? |
|---|---|---|---|---|---|---|
| market + raw efficiency | margin | 12.2265 | 12.2316 | -0.0051 | -0.4987 | no |
| market + adjusted efficiency | margin | 12.2265 | 12.2245 | 0.0021 | 0.1869 | no |
| market + adjusted (full) | margin | 12.2265 | 12.2311 | -0.0046 | -0.3314 | no |
| market + raw efficiency | total | 12.7029 | 12.7158 | -0.0130 | -1.6183 | no |
| market + adjusted efficiency | total | 12.7029 | 12.7222 | -0.0194 | -2.1104 | no |
| market + adjusted (full) | total | 12.7029 | 12.7223 | -0.0194 | -1.7870 | no |

**No model cleared the bar.**
Adjusted efficiency does not explain the market residual better than raw
efficiency does, because neither explains it at all. Both land on the
baseline, and so do SP+, FPI, Elo, weather, line movement, rest and travel.

The contrast with Section 3 is the point. The same features that removed
0.53 points of margin MAE remove **zero** residual MAE. Everything
opponent adjustment recovered was information the closing line already had.

---

## Section 6 - Feature Rankings

Standalone out-of-sample power of each metric, raw and adjusted, ranked by MAE
removed from the baseline.

### Margin

| # | Metric | Kind | MAE | Gain | t |
|---|---|---|---|---|---|
| 1 | adj_success_rate | adjusted | 14.4925 | 1.7222 | 15.3499 |
| 2 | success_rate | raw | 14.6855 | 1.5292 | 14.3224 |
| 3 | adj_off_epa | adjusted | 14.7123 | 1.5023 | 14.1385 |
| 4 | off_epa | raw | 14.8041 | 1.4105 | 13.7538 |
| 5 | adj_def_success_rate | adjusted | 14.8945 | 1.3202 | 12.7194 |
| 6 | adj_def_epa | adjusted | 15.0208 | 1.1939 | 11.9095 |
| 7 | adj_finishing_drives | adjusted | 15.0564 | 1.1583 | 11.9203 |
| 8 | def_success_rate | raw | 15.0752 | 1.1394 | 11.4409 |
| 9 | def_epa | raw | 15.1471 | 1.0676 | 10.8724 |
| 10 | finishing_drives | raw | 15.2052 | 1.0095 | 11.0709 |
| 11 | adj_havoc_allowed | adjusted | 15.3364 | 0.8783 | 9.9058 |
| 12 | adj_def_finishing_drives | adjusted | 15.3485 | 0.8662 | 9.6512 |
| 13 | adj_havoc | adjusted | 15.7119 | 0.5027 | 7.1585 |
| 14 | havoc | raw | 15.8203 | 0.3944 | 5.9549 |
| 15 | adj_explosiveness | adjusted | 16.0809 | 0.1338 | 3.0720 |
| 16 | adj_def_explosiveness | adjusted | 16.1309 | 0.0838 | 2.2801 |
| 17 | explosiveness | raw | 16.1417 | 0.0730 | 2.1475 |
| 18 | def_explosiveness | raw | 16.1951 | 0.0196 | 0.7023 |
| 19 | pace | raw | 16.2055 | 0.0091 | 0.6589 |
| 20 | adj_pace | adjusted | 16.2081 | 0.0066 | 0.4882 |
| 21 | adj_def_pace | adjusted | 16.2242 | -0.0096 | -0.7664 |

### Total

| # | Metric | Kind | MAE | Gain | t |
|---|---|---|---|---|---|
| 1 | pace | raw | 13.5311 | 0.3149 | 6.5022 |
| 2 | adj_pace | adjusted | 13.5833 | 0.2626 | 5.7647 |
| 3 | adj_explosiveness | adjusted | 13.6855 | 0.1605 | 4.9217 |
| 4 | adj_def_epa | adjusted | 13.6929 | 0.1531 | 4.5265 |
| 5 | adj_def_success_rate | adjusted | 13.7174 | 0.1286 | 4.3641 |
| 6 | off_epa | raw | 13.7174 | 0.1286 | 4.0647 |
| 7 | explosiveness | raw | 13.7219 | 0.1241 | 4.3794 |
| 8 | adj_def_finishing_drives | adjusted | 13.7285 | 0.1174 | 3.4834 |
| 9 | def_epa | raw | 13.7442 | 0.1018 | 3.7248 |
| 10 | success_rate | raw | 13.7635 | 0.0824 | 3.1432 |
| 11 | def_success_rate | raw | 13.7668 | 0.0792 | 3.4253 |
| 12 | finishing_drives | raw | 13.7870 | 0.0589 | 2.4826 |
| 13 | adj_off_epa | adjusted | 13.7887 | 0.0573 | 2.0207 |
| 14 | adj_finishing_drives | adjusted | 13.7976 | 0.0484 | 2.0176 |
| 15 | def_explosiveness | raw | 13.7996 | 0.0464 | 1.9616 |
| 16 | adj_def_explosiveness | adjusted | 13.8182 | 0.0278 | 1.3639 |
| 17 | adj_success_rate | adjusted | 13.8245 | 0.0215 | 1.0131 |
| 18 | adj_def_pace | adjusted | 13.8286 | 0.0174 | 1.3052 |
| 19 | havoc | raw | 13.8473 | -0.0013 | -0.2577 |
| 20 | adj_havoc | adjusted | 13.8495 | -0.0036 | -1.9115 |
| 21 | adj_havoc_allowed | adjusted | 13.8533 | -0.0074 | -2.6171 |

### Market residual (margin)

| # | Metric | Kind | MAE | Gain | t | Material? |
|---|---|---|---|---|---|---|
| 1 | pace | raw | 12.2258 | -0.0014 | -0.3590 | no |
| 2 | adj_def_finishing_drives | adjusted | 12.2261 | -0.0018 | -0.4106 | no |
| 3 | adj_havoc | adjusted | 12.2263 | -0.0019 | -0.5128 | no |
| 4 | adj_pace | adjusted | 12.2268 | -0.0025 | -0.6107 | no |
| 5 | adj_explosiveness | adjusted | 12.2269 | -0.0026 | -0.5515 | no |
| 6 | havoc | raw | 12.2272 | -0.0029 | -1.4863 | no |
| 7 | adj_def_epa | adjusted | 12.2275 | -0.0032 | -1.9790 | no |
| 8 | adj_def_success_rate | adjusted | 12.2275 | -0.0032 | -1.4310 | no |
| 9 | def_epa | raw | 12.2276 | -0.0033 | -1.4748 | no |
| 10 | explosiveness | raw | 12.2277 | -0.0033 | -0.7271 | no |
| 11 | def_success_rate | raw | 12.2280 | -0.0037 | -2.4115 | no |
| 12 | success_rate | raw | 12.2281 | -0.0037 | -2.2869 | no |

---

## Recommendation

**Opponent adjustment is worth doing, and it does not justify Atlas Alpha on
its own.** Both halves of that sentence are load-bearing.

Worth doing, because:

* it is the largest single improvement Atlas has made to its own view of a
  game - 0.53 points of margin MAE, t = 7.3;
* it moves Atlas ahead of SP+ and FPI rather than behind them, which means
  Atlas no longer needs them as features;
* it costs about twenty seconds of compute and no new data.

Not sufficient, because the residual is untouched. Phase 1A concluded that the
closing line already contained everything the public variables knew. Phase 1B
tested the single best hypothesis for why that might have been an artefact -
that Atlas's metrics were unadjusted and therefore handicapped - and the
hypothesis is now rejected. The metrics are adjusted, they are better than the
public ratings, and the line is still not beatable with them.

What this changes for the Alpha specification:

1. **Replace raw efficiency with adjusted efficiency everywhere**, using
   Method C. Keep raw pace and raw plays-per-game for the totals model, where
   adjustment measurably hurts.
2. **Drop SP+ and FPI as features.** They were standing in for the adjustment
   Atlas now does itself, and they add nothing once it does.
3. **Stop looking for an edge in team-quality metrics.** Three separate
   families - raw efficiency, adjusted efficiency, published adjusted ratings -
   all land on the same residual baseline. The next hypothesis has to be about
   information the market does not have, not about measuring team quality more
   precisely.

The companion reports point at where that information might be:
[weather](weather_data_report.md) (measured, and the market prices it) and
[quarterback availability](qb_availability_report.md) (not measured by the
market in a way Atlas can see, and the one place this phase found a signal
that moves the residual).
