# Atlas Research Report V1

*Generated 2026-09-22 13:49 UTC from `data/warehouse/atlas.duckdb`. Every figure in this
document is produced by `python -m atlas.research.report`; none is hand-entered.*

Atlas Phase 1A asks one question: **which variables actually predict college
football games?** It does not project, simulate or wager. The answer below is
measured out-of-sample, leave-one-season-out, on a point-in-time-correct
warehouse in which no feature attached to a game was unknown at its kickoff.

CFBD enrichment was **not** enabled for this build (`CFBD_API_KEY` unset), so SP+, recruiting, returning production and kickoff weather are structurally present but empty. Every other result below is unaffected.

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

**Not measurable in this build.** SP+ is published only through the
CollegeFootballData API, which requires a free API key. Without `CFBD_API_KEY`
the `ratings.home_sp_plus` / `away_sp_plus` / `sp_plus_diff` columns exist and
are null, and the SP+ benchmark is reported as unavailable rather than being
silently replaced by a proxy.

Set the key and re-run `make all` to fill this section in; nothing else about
the pipeline changes. Atlas measures the next-best published rating, ESPN's
FPI, in Section 4, and its own pre-game Elo and efficiency baselines in
Section 5.

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
| Market + Everything | yes | 5,778 | 12.246 | 15.463 | 0.443 | sp_plus_diff, recruiting_rank_diff, talent_diff, returning_production_diff, weather_temp, weather_wind, weather_precip |
| FPI Game Projection | yes | 5,778 | 12.924 | 16.205 | 0.388 |  |
| Ratings + Efficiency (no market) | yes | 5,778 | 13.078 | 16.452 | 0.369 | sp_plus_diff |
| Elo Only | yes | 5,778 | 13.105 | 16.496 | 0.366 |  |
| Efficiency Only | yes | 5,778 | 13.959 | 17.697 | 0.270 |  |
| FPI Only | yes | 5,778 | 14.103 | 17.810 | 0.261 |  |
| SP+ + FPI | yes | 5,778 | 14.103 | 17.810 | 0.261 | sp_plus_diff |
| SP+ Only | no | 0 | n/a | n/a | n/a | sp_plus_diff |

### Full benchmark ladder - total

| Benchmark | Available | Games | MAE | RMSE | R² | Unavailable inputs |
|---|---|---|---|---|---|---|
| Market Only | yes | 5,778 | 12.703 | 16.027 | 0.158 |  |
| Market Closing Line (raw, unfitted) | yes | 5,778 | 12.705 | 16.043 | 0.156 |  |
| Market + Efficiency | yes | 5,778 | 12.714 | 16.039 | 0.156 |  |
| Market + Everything | yes | 5,778 | 12.717 | 16.049 | 0.155 | sp_plus_sum, talent_sum, returning_production_sum, weather_temp, weather_wind, weather_precip |
| Ratings + Efficiency (no market) | yes | 5,778 | 13.142 | 16.588 | 0.098 | sp_plus_sum |
| Efficiency Only | yes | 5,778 | 13.153 | 16.597 | 0.097 |  |
| FPI Only | yes | 5,778 | 13.848 | 17.488 | -0.003 |  |
| SP+ + FPI | yes | 5,778 | 13.848 | 17.488 | -0.003 | sp_plus_sum |
| Elo Only | yes | 5,778 | 13.850 | 17.490 | -0.003 |  |
| SP+ Only | no | 0 | n/a | n/a | n/a | sp_plus_sum |

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
| 7 | Finishing Drives | yes | 15.2052 | 1.0095 | -0.0011 | -1.7174 | no |
| 8 | Havoc | yes | 15.8203 | 0.3944 | -0.0008 | -0.5059 | no |
| 9 | Explosiveness | yes | 16.1208 | 0.0939 | -0.0023 | -0.5042 | no |
| 10 | Market Total | yes | 16.2128 | 0.0019 | n/a | n/a | n/a |
| 11 | Neutral Site | yes | 16.2130 | 0.0017 | 0.0000 | 0.1537 | no |
| 12 | Pace | yes | 16.2139 | 0.0008 | -0.0024 | -0.5600 | no |
| 13 | Travel | yes | 16.2188 | -0.0041 | -0.0013 | -0.2265 | no |
| 14 | Rest | yes | 16.2221 | -0.0074 | -0.0038 | -2.3141 | no |
| 15 | Line Movement | yes | 16.2716 | -0.0569 | -0.0006 | -0.2330 | no |
| n/a | SP+ | no | n/a | n/a | n/a | n/a | no |
| n/a | Recruiting | no | n/a | n/a | n/a | n/a | no |
| n/a | Returning Production | no | n/a | n/a | n/a | n/a | no |
| n/a | Weather | no | n/a | n/a | n/a | n/a | no |

### Ranked variables - total

| # | Variable | Available | Standalone MAE | Standalone gain | Gain over market | t | Material? |
|---|---|---|---|---|---|---|---|
| 1 | Market Total | yes | 12.7029 | 1.1431 | n/a | n/a | n/a |
| 2 | EPA | yes | 13.5146 | 0.3314 | -0.0029 | -0.6712 | no |
| 3 | Pace | yes | 13.5266 | 0.3193 | 0.0029 | 0.3689 | no |
| 4 | Success Rate | yes | 13.5695 | 0.2765 | -0.0014 | -0.3259 | no |
| 5 | Line Movement | yes | 13.6836 | 0.1623 | 0.0098 | 1.2323 | no |
| 6 | Explosiveness | yes | 13.6890 | 0.1569 | -0.0012 | -1.0826 | no |
| 7 | Finishing Drives | yes | 13.7870 | 0.0589 | -0.0011 | -0.2673 | no |
| 8 | Market Spread | yes | 13.8216 | 0.0244 | n/a | n/a | n/a |
| 9 | Neutral Site | yes | 13.8363 | 0.0096 | 0.0032 | 0.6513 | no |
| 10 | Rest | yes | 13.8459 | 0.0000 | -0.0047 | -2.5787 | no |
| 11 | Havoc | yes | 13.8473 | -0.0013 | -0.0018 | -1.6657 | no |
| 12 | Travel | yes | 13.8473 | -0.0014 | -0.0007 | -0.4498 | no |
| 13 | FPI | yes | 13.8477 | -0.0017 | -0.0009 | -0.2191 | no |
| 14 | Elo | yes | 13.8502 | -0.0043 | 0.0025 | 0.5407 | no |
| n/a | SP+ | no | n/a | n/a | n/a | n/a | no |
| n/a | FPI Game Projection | no | n/a | n/a | n/a | n/a | no |
| n/a | Recruiting | no | n/a | n/a | n/a | n/a | no |
| n/a | Returning Production | no | n/a | n/a | n/a | n/a | no |
| n/a | Weather | no | n/a | n/a | n/a | n/a | no |

### Permutation importance inside one model - margin

| Feature | MAE increase when shuffled |
|---|---|
| closing_spread | 5.6256 |
| fpi_home_win_prob | 0.1509 |
| elo_diff | 0.0417 |
| def_epa_diff | 0.0231 |
| pace_diff | 0.0188 |
| success_rate_diff | 0.0123 |
| travel_distance | 0.0107 |
| def_success_rate_diff | 0.0053 |
| explosiveness_diff | 0.0040 |
| off_epa_diff | 0.0027 |
| spread_movement | 0.0013 |
| finishing_drives_diff | 0.0008 |
| havoc_diff | -0.0038 |
| plays_per_game_diff | -0.0055 |
| fpi_diff | -0.0096 |

### Permutation importance inside one model - total

| Feature | MAE increase when shuffled |
|---|---|
| closing_total | 1.6807 |
| elo_sum | 0.0429 |
| pace_sum | 0.0183 |
| finishing_drives_sum | 0.0174 |
| fpi_sum | 0.0167 |
| def_explosiveness_sum | 0.0114 |
| def_success_rate_sum | 0.0081 |
| travel_distance | 0.0059 |
| success_rate_sum | 0.0044 |
| rest_abs | -0.0005 |
| plays_per_game_sum | -0.0033 |
| havoc_sum | -0.0053 |
| off_epa_sum | -0.0098 |
| total_movement | -0.0129 |
| explosiveness_sum | -0.0133 |

### Direction of effect (standardised ridge coefficients, margin)

| Feature | Std. coefficient |
|---|---|
| closing_spread | -12.808 |
| def_epa_diff | 2.226 |
| def_success_rate_diff | -1.682 |
| fpi_home_win_prob | 0.880 |
| def_explosiveness_diff | -0.756 |
| elo_diff | 0.713 |
| havoc_diff | 0.422 |
| off_epa_diff | -0.375 |
| travel_distance | 0.368 |
| spread_movement | 0.317 |
| success_rate_diff | 0.271 |
| explosiveness_diff | -0.263 |

### ATS and totals outcomes

Break-even at -110 is **52.4%**.

**Against the spread (home cover)**

| Feature set | n | Accuracy | Log loss | Base rate |
|---|---|---|---|---|
| all features (incl. market) | 5,671 | 0.5011 | 0.6950 | 0.5020 |
| non-market features only | 5,671 | 0.4983 | 0.6947 | 0.5020 |
| market line only | 5,671 | 0.4916 | 0.6934 | 0.5020 |

**Totals (over hit)**

| Feature set | n | Accuracy | Log loss | Base rate |
|---|---|---|---|---|
| all features (incl. market) | 5,708 | 0.5137 | 0.6939 | 0.4937 |
| non-market features only | 5,708 | 0.5102 | 0.6946 | 0.4937 |
| market line only | 5,708 | 0.5179 | 0.6924 | 0.4937 |

### Beating the closing line

Out-of-sample hit rate when siding with each benchmark against the market
number:

| Benchmark | Target | Picks | Hit rate |
|---|---|---|---|
| Market Only | margin | 5,671 | 0.4927 |
| Market Only | total | 5,708 | 0.5172 |
| FPI Only | margin | 5,671 | 0.4893 |
| FPI Only | total | 5,708 | 0.5198 |
| SP+ + FPI | margin | 5,671 | 0.4893 |
| SP+ + FPI | total | 5,708 | 0.5198 |
| Elo Only | margin | 5,671 | 0.4955 |
| Elo Only | total | 5,708 | 0.5193 |
| FPI Game Projection | margin | 5,671 | 0.5013 |
| Efficiency Only | margin | 5,671 | 0.4950 |
| Efficiency Only | total | 5,708 | 0.5147 |
| Ratings + Efficiency (no market) | margin | 5,671 | 0.4920 |
| Ratings + Efficiency (no market) | total | 5,708 | 0.5186 |
| Market + Efficiency | margin | 5,671 | 0.5078 |
| Market + Efficiency | total | 5,708 | 0.5152 |
| Market + Everything | margin | 5,671 | 0.5031 |
| Market + Everything | total | 5,708 | 0.5158 |

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

On margin, the largest marginal gain over the closing spread was **0.0000 MAE** (Neutral Site); on totals **0.0098 MAE** (Line Movement). Both are point estimates; what matters is whether either clears its own error bar.

**No candidate variable improved on the closing line by more than its own noise.** The largest point estimates are a small fraction of a point of MAE and none reaches a paired t-statistic of 2; most marginal gains are outright negative. The closing spread and closing total already contain everything these public variables know. Atlas should treat the market as the prior it must justify departing from, not as one input among many.

Outcome classification is consistent with that: ATS accuracy with the full feature set was **0.5011** and totals **0.5137**, against a 52.4% break-even.

### What is not yet measured

These candidate variables could not be evaluated at all in this build, because their only source is the CollegeFootballData API: **Recruiting, Returning Production, SP+, Weather**. They are wired end-to-end; they need `CFBD_API_KEY` and a rebuild.

Measured for one target but not the other (no meaningful form exists on the other side): **FPI Game Projection**.

SP+ in particular is the one required benchmark this build cannot report, and it is the most likely of the missing variables to matter, since it is an efficiency-based rating rather than a résumé rating.

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
| def_epa_sum | yes | 0.992 |
| def_epa_diff | yes | 0.992 |
| explosiveness_diff | yes | 0.992 |
| explosiveness_sum | yes | 0.992 |
| def_success_rate_sum | yes | 0.992 |
| def_success_rate_diff | yes | 0.992 |
| plays_per_game_diff | yes | 0.992 |
| plays_per_game_sum | yes | 0.992 |
| finishing_drives_sum | yes | 0.992 |
| finishing_drives_diff | yes | 0.992 |
| havoc_sum | yes | 0.992 |
| havoc_diff | yes | 0.992 |
| off_epa_sum | yes | 0.992 |
| off_epa_diff | yes | 0.992 |
| success_rate_sum | yes | 0.992 |
| success_rate_diff | yes | 0.992 |
| pace_diff | yes | 0.992 |
| pace_sum | yes | 0.992 |
| def_explosiveness_sum | yes | 0.992 |
| def_explosiveness_diff | yes | 0.992 |
| fpi_sum | yes | 0.981 |
| fpi_diff | yes | 0.981 |
| travel_distance_diff | yes | 0.942 |
| travel_distance | yes | 0.942 |
| rest_diff | yes | 0.930 |
| rest_abs | yes | 0.930 |
| total_movement | yes | 0.912 |
| spread_movement | yes | 0.911 |
| recruiting_rank_diff | yes | 0.000 |
| sp_plus_diff | yes | 0.000 |
| sp_plus_sum | yes | 0.000 |
| returning_production_diff | yes | 0.000 |
| returning_production_sum | yes | 0.000 |
| talent_sum | yes | 0.000 |
| talent_diff | yes | 0.000 |
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
| actual_margin | success_rate_diff | 5,733 | 0.4489 | no |
| actual_margin | off_epa_diff | 5,733 | 0.4308 | no |
| actual_total | closing_total | 5,778 | 0.3990 | no |
| actual_margin | def_success_rate_diff | 5,733 | -0.3941 | no |
| actual_margin | def_epa_diff | 5,733 | -0.3866 | no |
| actual_margin | finishing_drives_diff | 5,733 | 0.3715 | no |
| actual_margin | closing_spread_abs | 5,778 | 0.3023 | no |
| actual_margin | havoc_diff | 5,733 | 0.2522 | no |

## Appendix C - Reproducing this report

```bash
make all          # ingest -> staging -> warehouse -> research
# or, step by step
python -m atlas.ingest
python -m atlas.warehouse.build
python -m atlas.research.report
```
