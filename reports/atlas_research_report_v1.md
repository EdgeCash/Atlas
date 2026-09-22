# Atlas Research Report V1

*Generated 2026-09-22 14:08 UTC from `data/warehouse/atlas.duckdb`. Every figure in this
document is produced by `python -m atlas.research.report`; none is hand-entered.*

Atlas Phase 1A asks one question: **which variables actually predict college
football games?** It does not project, simulate or wager. The answer below is
measured out-of-sample, leave-one-season-out, on a point-in-time-correct
warehouse in which no feature attached to a game was unknown at its kickoff.

CFBD enrichment was **enabled** for this build: `sp_plus`, `talent`, `recruiting`, `returning` are populated. Still missing: `weather` (/games/weather: Unauthorized. This endpoint requires a Patreon subscription at Tier 1 or higher.).

---

## Section 1 - Data Coverage

Research sample: **5,778 FBS-vs-FBS games** across **8 seasons (2018-2025)**, drawn from 5,996 completed FBS-vs-FBS games in the warehouse.

| Season | Games | Spread | Total | Efficiency | FPI | Mean total | Mean abs margin |
|---|---|---|---|---|---|---|---|
| 2018 | 707 | 707 | 707 | 662 | 697 | 56.61 | 17.39 |
| 2019 | 699 | 699 | 699 | 699 | 699 | 55.63 | 17.78 |
| 2020 | 508 | 508 | 508 | 508 | 508 | 57.50 | 16.62 |
| 2021 | 732 | 732 | 732 | 732 | 700 | 54.95 | 16.81 |
| 2022 | 734 | 734 | 734 | 734 | 724 | 54.34 | 15.79 |
| 2023 | 792 | 792 | 792 | 792 | 770 | 53.33 | 16.18 |
| 2024 | 798 | 798 | 798 | 798 | 787 | 53.69 | 16.11 |
| 2025 | 808 | 808 | 808 | 808 | 784 | 52.34 | 16.38 |

### How point-in-time correctness is enforced

| Field family | Source | Why it cannot leak |
|---|---|---|
| Results, venue, schedule | CFBD games mirror | Outcome only; never used as a feature |
| Closing / opening lines, moneyline | Historical sportsbook feed | Posted before kickoff |
| Efficiency (EPA, success rate, explosiveness, havoc, finishing drives, pace) | Play-by-play, aggregated per game | A game's feature averages that team's **strictly earlier** games, shrunk toward its **previous season** mean |
| FPI (rating) | ESPN | **Previous season's** final rating only |
| FPI game projection | ESPN pre-game predictor | Published before kickoff |
| Elo | CFBD pre-game Elo | Pre-game by construction |
| SP+ | CFBD | **Previous season's** rating only |
| Recruiting, returning production | CFBD | Fixed before the season starts |
| Rest, travel, neutral site | Schedule + venue geography | Known when the schedule is published |
| Weather | CFBD kickoff observation | Kickoff conditions, not a result |

The vectorised point-in-time implementation is checked row-by-row against a
brute-force recomputation in the test suite, and a correlation scan flags any
feature that tracks an outcome more tightly than football allows.

---

## Section 2 - Market Performance

The closing consensus line, used exactly as posted.

| Metric | Value |
|---|---|
| Margin MAE | 12.224 |
| Margin RMSE | 15.455 |
| Margin R² | 0.443 |
| Total MAE | 12.705 |
| Total RMSE | 16.043 |
| Total R² | 0.156 |
| Games | 5,778 |

Per-season stability of the market margin benchmark:

| Season | Games | MAE | RMSE | Bias |
|---|---|---|---|---|
| 2018 | 707 | 12.376 | 15.768 | 0.623 |
| 2019 | 699 | 12.200 | 15.471 | -0.924 |
| 2020 | 508 | 12.832 | 15.978 | 0.840 |
| 2021 | 732 | 12.565 | 15.608 | 0.521 |
| 2022 | 734 | 12.037 | 15.298 | 0.769 |
| 2023 | 792 | 12.132 | 15.315 | 0.131 |
| 2024 | 798 | 12.103 | 15.452 | -0.741 |
| 2025 | 808 | 11.819 | 15.011 | -0.864 |

---

## Section 3 - SP+ Performance

| Metric | Value |
|---|---|
| Margin MAE | 14.177 |
| Margin RMSE | 17.853 |
| Total MAE | 13.570 |
| Total RMSE | 17.168 |
| Games | 5,778 |

SP+ is used as the **previous season's** rating, mapped to a margin by a
leave-one-season-out fit that also carries home-field advantage.

---

## Section 4 - FPI Performance

Two distinct FPI artefacts, because they are not equally informative.

**FPI rating (previous season's final value, mapped to margin):**

| Metric | Value |
|---|---|
| Margin MAE | 14.103 |
| Margin RMSE | 17.810 |
| Total MAE | 13.848 |
| Total RMSE | 17.488 |

**FPI pre-game game projection (ESPN's own matchup forecast, published before kickoff):**

| Target | Games | MAE | RMSE | R² |
|---|---|---|---|---|
| margin | 5,778 | 12.924 | 16.205 | 0.388 |

The gap between the two is the value of in-season updating: a stale
preseason-equivalent rating is materially worse than the same system's
current view of the same matchup.

---

## Section 5 - Feature Importance Ranking

### Full benchmark ladder - margin

| Benchmark | Available | Games | MAE | RMSE | R² | Unavailable inputs |
|---|---|---|---|---|---|---|
| Market Closing Line (raw, unfitted) | yes | 5,778 | 12.224 | 15.455 | 0.443 |  |
| Market Only | yes | 5,778 | 12.227 | 15.461 | 0.443 |  |
| Market + Efficiency | yes | 5,778 | 12.232 | 15.462 | 0.443 |  |
| Market + Everything | yes | 5,778 | 12.242 | 15.468 | 0.443 | weather_temp, weather_wind, weather_precip |
| FPI Game Projection | yes | 5,778 | 12.924 | 16.205 | 0.388 |  |
| Ratings + Efficiency (no market) | yes | 5,778 | 13.085 | 16.459 | 0.369 |  |
| Elo Only | yes | 5,778 | 13.105 | 16.496 | 0.366 |  |
| Efficiency Only | yes | 5,778 | 13.959 | 17.697 | 0.270 |  |
| SP+ + FPI | yes | 5,778 | 14.094 | 17.772 | 0.264 |  |
| FPI Only | yes | 5,778 | 14.103 | 17.810 | 0.261 |  |
| SP+ Only | yes | 5,778 | 14.177 | 17.853 | 0.257 |  |

### Full benchmark ladder - total

| Benchmark | Available | Games | MAE | RMSE | R² | Unavailable inputs |
|---|---|---|---|---|---|---|
| Market Only | yes | 5,778 | 12.703 | 16.027 | 0.158 |  |
| Market Closing Line (raw, unfitted) | yes | 5,778 | 12.705 | 16.043 | 0.156 |  |
| Market + Efficiency | yes | 5,778 | 12.714 | 16.039 | 0.156 |  |
| Market + Everything | yes | 5,778 | 12.729 | 16.059 | 0.154 | weather_temp, weather_wind, weather_precip |
| Ratings + Efficiency (no market) | yes | 5,778 | 13.148 | 16.601 | 0.096 |  |
| Efficiency Only | yes | 5,778 | 13.153 | 16.597 | 0.097 |  |
| SP+ Only | yes | 5,778 | 13.570 | 17.168 | 0.034 |  |
| SP+ + FPI | yes | 5,778 | 13.579 | 17.178 | 0.032 |  |
| FPI Only | yes | 5,778 | 13.848 | 17.488 | -0.003 |  |
| Elo Only | yes | 5,778 | 13.850 | 17.490 | -0.003 |  |

### Ranked variables - margin

`Standalone gain` is MAE removed from a constant baseline by that variable
alone. `Gain over market` is MAE removed **on top of** the closing spread -
the only column that says whether a variable carries information the market
has not already priced. It is a paired per-game comparison, so it comes with a
t-statistic; `Material?` is `yes` only when t > 2, because over ~5,700 games a
gain of 0.01 MAE is indistinguishable from zero.

| # | Variable | Available | Standalone MAE | Standalone gain | Gain over market | t | Material? |
|---|---|---|---|---|---|---|---|
| 1 | Market Spread | yes | 12.2265 | 3.9881 | n/a | n/a | n/a |
| 2 | FPI Game Projection | yes | 12.9241 | 3.2906 | -0.0091 | -1.8367 | no |
| 3 | Elo | yes | 13.1047 | 3.1099 | -0.0055 | -2.1164 | no |
| 4 | Success Rate | yes | 14.0985 | 2.1162 | -0.0050 | -3.2470 | no |
| 5 | FPI | yes | 14.1031 | 2.1116 | -0.0006 | -1.0567 | no |
| 6 | EPA | yes | 14.1545 | 2.0602 | -0.0019 | -0.5787 | no |
| 7 | SP+ | yes | 14.1925 | 2.0222 | -0.0004 | -0.0769 | no |
| 8 | Recruiting | yes | 14.9698 | 1.2449 | -0.0078 | -2.1202 | no |
| 9 | Finishing Drives | yes | 15.2052 | 1.0095 | -0.0011 | -1.7174 | no |
| 10 | Havoc | yes | 15.8203 | 0.3944 | -0.0008 | -0.5059 | no |
| 11 | Explosiveness | yes | 16.1208 | 0.0939 | -0.0023 | -0.5042 | no |
| 12 | Returning Production | yes | 16.1277 | 0.0870 | 0.0056 | 1.0500 | no |
| 13 | Market Total | yes | 16.2128 | 0.0019 | n/a | n/a | n/a |
| 14 | Neutral Site | yes | 16.2130 | 0.0017 | 0.0000 | 0.1537 | no |
| 15 | Pace | yes | 16.2139 | 0.0008 | -0.0024 | -0.5600 | no |
| 16 | Travel | yes | 16.2188 | -0.0041 | -0.0013 | -0.2265 | no |
| 17 | Rest | yes | 16.2221 | -0.0074 | -0.0038 | -2.3141 | no |
| 18 | Line Movement | yes | 16.2716 | -0.0569 | -0.0006 | -0.2330 | no |
| n/a | Weather | no | n/a | n/a | n/a | n/a | no |

### Ranked variables - total

| # | Variable | Available | Standalone MAE | Standalone gain | Gain over market | t | Material? |
|---|---|---|---|---|---|---|---|
| 1 | Market Total | yes | 12.7029 | 1.1431 | n/a | n/a | n/a |
| 2 | EPA | yes | 13.5146 | 0.3314 | -0.0029 | -0.6712 | no |
| 3 | Pace | yes | 13.5266 | 0.3193 | 0.0029 | 0.3689 | no |
| 4 | Success Rate | yes | 13.5695 | 0.2765 | -0.0014 | -0.3259 | no |
| 5 | SP+ | yes | 13.5698 | 0.2761 | 0.0004 | 0.0679 | no |
| 6 | Line Movement | yes | 13.6836 | 0.1623 | 0.0098 | 1.2323 | no |
| 7 | Explosiveness | yes | 13.6890 | 0.1569 | -0.0012 | -1.0826 | no |
| 8 | Finishing Drives | yes | 13.7870 | 0.0589 | -0.0011 | -0.2673 | no |
| 9 | Market Spread | yes | 13.8216 | 0.0244 | n/a | n/a | n/a |
| 10 | Neutral Site | yes | 13.8363 | 0.0096 | 0.0032 | 0.6513 | no |
| 11 | Rest | yes | 13.8459 | 0.0000 | -0.0047 | -2.5787 | no |
| 12 | Havoc | yes | 13.8473 | -0.0013 | -0.0018 | -1.6657 | no |
| 13 | Travel | yes | 13.8473 | -0.0014 | -0.0007 | -0.4498 | no |
| 14 | FPI | yes | 13.8477 | -0.0017 | -0.0009 | -0.2191 | no |
| 15 | Elo | yes | 13.8502 | -0.0043 | 0.0025 | 0.5407 | no |
| 16 | Recruiting | yes | 13.8593 | -0.0133 | -0.0032 | -3.0269 | no |
| 17 | Returning Production | yes | 13.8597 | -0.0138 | -0.0041 | -0.7851 | no |
| n/a | FPI Game Projection | no | n/a | n/a | n/a | n/a | no |
| n/a | Weather | no | n/a | n/a | n/a | n/a | no |

### Permutation importance inside one model - margin

| Feature | MAE increase when shuffled |
|---|---|
| closing_spread | 5.2855 |
| fpi_home_win_prob | 0.1406 |
| elo_diff | 0.0330 |
| pace_diff | 0.0205 |
| talent_diff | 0.0179 |
| returning_production_diff | 0.0171 |
| def_epa_diff | 0.0168 |
| explosiveness_diff | 0.0138 |
| travel_distance | 0.0138 |
| havoc_diff | 0.0131 |
| success_rate_diff | 0.0122 |
| rest_diff | 0.0093 |
| def_explosiveness_diff | 0.0090 |
| spread_movement | 0.0088 |
| off_epa_diff | 0.0036 |

### Permutation importance inside one model - total

| Feature | MAE increase when shuffled |
|---|---|
| closing_total | 1.6771 |
| success_rate_sum | 0.0209 |
| finishing_drives_sum | 0.0139 |
| talent_sum | 0.0120 |
| elo_sum | 0.0114 |
| sp_plus_def_sum | 0.0107 |
| def_explosiveness_sum | 0.0095 |
| sp_plus_off_sum | 0.0074 |
| total_movement | 0.0071 |
| pace_sum | 0.0058 |
| explosiveness_sum | 0.0032 |
| fpi_sum | -0.0002 |
| def_success_rate_sum | -0.0033 |
| rest_abs | -0.0059 |
| plays_per_game_sum | -0.0062 |

### Direction of effect (standardised ridge coefficients, margin)

| Feature | Std. coefficient |
|---|---|
| closing_spread | -12.578 |
| sp_plus_diff | 3.741 |
| sp_plus_def_diff | 2.391 |
| sp_plus_off_diff | -2.328 |
| def_epa_diff | 2.255 |
| def_success_rate_diff | -1.732 |
| fpi_home_win_prob | 0.907 |
| def_explosiveness_diff | -0.781 |
| elo_diff | 0.763 |
| returning_production_diff | 0.455 |
| havoc_diff | 0.428 |
| off_epa_diff | -0.414 |

### ATS and totals outcomes

Break-even at -110 is **52.4%**.

**Against the spread (home cover)**

| Feature set | n | Accuracy | Log loss | Base rate |
|---|---|---|---|---|
| all features (incl. market) | 5,671 | 0.5013 | 0.6950 | 0.5020 |
| non-market features only | 5,671 | 0.4997 | 0.6948 | 0.5020 |
| market line only | 5,671 | 0.4916 | 0.6934 | 0.5020 |

**Totals (over hit)**

| Feature set | n | Accuracy | Log loss | Base rate |
|---|---|---|---|---|
| all features (incl. market) | 5,708 | 0.5126 | 0.6944 | 0.4937 |
| non-market features only | 5,708 | 0.5107 | 0.6949 | 0.4937 |
| market line only | 5,708 | 0.5179 | 0.6924 | 0.4937 |

### Beating the closing line

Out-of-sample hit rate when siding with each benchmark against the market
number:

| Benchmark | Target | Picks | Hit rate |
|---|---|---|---|
| Market Only | margin | 5,671 | 0.4927 |
| Market Only | total | 5,708 | 0.5172 |
| SP+ Only | margin | 5,671 | 0.4950 |
| SP+ Only | total | 5,708 | 0.5173 |
| FPI Only | margin | 5,671 | 0.4893 |
| FPI Only | total | 5,708 | 0.5198 |
| SP+ + FPI | margin | 5,671 | 0.4943 |
| SP+ + FPI | total | 5,708 | 0.5180 |
| Elo Only | margin | 5,671 | 0.4955 |
| Elo Only | total | 5,708 | 0.5193 |
| FPI Game Projection | margin | 5,671 | 0.5013 |
| Efficiency Only | margin | 5,671 | 0.4950 |
| Efficiency Only | total | 5,708 | 0.5147 |
| Ratings + Efficiency (no market) | margin | 5,671 | 0.4902 |
| Ratings + Efficiency (no market) | total | 5,708 | 0.5163 |
| Market + Efficiency | margin | 5,671 | 0.5078 |
| Market + Efficiency | total | 5,708 | 0.5152 |
| Market + Everything | margin | 5,671 | 0.5101 |
| Market + Everything | total | 5,708 | 0.5124 |

---

## Section 6 - Preliminary Conclusions

### What predicts margin

1. **The closing spread, by a wide margin.** It is the single strongest variable in the sample and no combination of the others reaches it.
2. Among non-market variables the ranking is **FPI Game Projection, Elo, Success Rate**.
3. In-season efficiency beats stale ratings: a system's *current* view of a matchup (ESPN's pre-game FPI projection, CFBD pre-game Elo) clearly outperforms the same family's previous-season rating.

### What predicts total

1. **The closing total**, again by a wide margin.
2. Among non-market variables: **EPA, Pace, Success Rate**.
3. Totals are intrinsically harder than margins here: the market's own R² on totals is far below its R² on margins, so there is less structure for anything to capture.

### Does anything beat the market?

On margin, the largest marginal gain over the closing spread was **0.0056 MAE** (Returning Production); on totals **0.0098 MAE** (Line Movement). Both are point estimates; what matters is whether either clears its own error bar.

**No candidate variable improved on the closing line by more than its own noise.** The largest point estimates are a small fraction of a point of MAE and none reaches a paired t-statistic of 2; most marginal gains are outright negative. The closing spread and closing total already contain everything these public variables know. Atlas should treat the market as the prior it must justify departing from, not as one input among many.

Outcome classification is consistent with that: ATS accuracy with the full feature set was **0.5013** and totals **0.5126**, against a 52.4% break-even.

### What is not yet measured

These candidate variables could not be evaluated at all in this build. They are wired end-to-end; each is blocked on its source:

* **Weather** - /games/weather: Unauthorized. This endpoint requires a Patreon subscription at Tier 1 or higher.

Measured for one target but not the other (no meaningful form exists on the other side): **FPI Game Projection**.

---

## Appendix A - Feature coverage in the research sample

| Feature | Present | Coverage |
|---|---|---|
| closing_spread | yes | 1.000 |
| closing_spread_abs | yes | 1.000 |
| closing_total | yes | 1.000 |
| elo_diff | yes | 1.000 |
| elo_sum | yes | 1.000 |
| neutral_site_flag | yes | 1.000 |
| fpi_home_win_prob | yes | 1.000 |
| recruiting_rank_diff | yes | 0.998 |
| talent_sum | yes | 0.996 |
| talent_diff | yes | 0.996 |
| def_success_rate_sum | yes | 0.992 |
| finishing_drives_diff | yes | 0.992 |
| explosiveness_sum | yes | 0.992 |
| def_success_rate_diff | yes | 0.992 |
| def_epa_sum | yes | 0.992 |
| def_epa_diff | yes | 0.992 |
| plays_per_game_diff | yes | 0.992 |
| pace_sum | yes | 0.992 |
| plays_per_game_sum | yes | 0.992 |
| finishing_drives_sum | yes | 0.992 |
| explosiveness_diff | yes | 0.992 |
| off_epa_diff | yes | 0.992 |
| off_epa_sum | yes | 0.992 |
| havoc_sum | yes | 0.992 |
| success_rate_sum | yes | 0.992 |
| success_rate_diff | yes | 0.992 |
| pace_diff | yes | 0.992 |
| havoc_diff | yes | 0.992 |
| def_explosiveness_diff | yes | 0.992 |
| def_explosiveness_sum | yes | 0.992 |
| sp_plus_off_sum | yes | 0.984 |
| sp_plus_off_diff | yes | 0.984 |
| sp_plus_def_diff | yes | 0.984 |
| sp_plus_diff | yes | 0.984 |
| sp_plus_def_sum | yes | 0.984 |
| returning_production_sum | yes | 0.983 |
| returning_production_diff | yes | 0.983 |
| fpi_diff | yes | 0.981 |
| fpi_sum | yes | 0.981 |
| travel_distance | yes | 0.942 |
| travel_distance_diff | yes | 0.942 |
| rest_diff | yes | 0.930 |
| rest_abs | yes | 0.930 |
| total_movement | yes | 0.912 |
| spread_movement | yes | 0.911 |
| weather_precip | yes | 0.000 |
| weather_temp | yes | 0.000 |
| weather_wind | yes | 0.000 |

## Appendix B - Leakage scan

Strongest absolute correlations between any candidate feature and an outcome.
Anything above 0.98 would be an outcome in disguise; nothing here is close.

| Target | Feature | n | Correlation | Suspicious |
|---|---|---|---|---|
| actual_margin | closing_spread | 5,778 | -0.6659 | no |
| actual_margin | fpi_home_win_prob | 5,776 | 0.6238 | no |
| actual_margin | elo_diff | 5,778 | 0.6052 | no |
| actual_margin | fpi_diff | 5,669 | 0.5166 | no |
| actual_margin | sp_plus_diff | 5,684 | 0.5122 | no |
| actual_margin | success_rate_diff | 5,733 | 0.4489 | no |
| actual_margin | off_epa_diff | 5,733 | 0.4308 | no |
| actual_margin | sp_plus_def_diff | 5,684 | -0.4082 | no |
| actual_total | closing_total | 5,778 | 0.3990 | no |
| actual_margin | def_success_rate_diff | 5,733 | -0.3941 | no |
| actual_margin | sp_plus_off_diff | 5,684 | 0.3916 | no |
| actual_margin | def_epa_diff | 5,733 | -0.3866 | no |

## Appendix C - Reproducing this report

```bash
make all          # ingest -> staging -> warehouse -> research
# or, step by step
python -m atlas.ingest
python -m atlas.warehouse.build
python -m atlas.research.report
```
