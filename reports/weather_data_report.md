# Atlas Weather Data Report (Phase 1B)

*Generated 2026-09-22 14:47 UTC. Measured figures are produced by
`python -m atlas.research.phase1b_report`.*

Phase 1A flagged weather as the highest-value missing measurement and could
not test it: CFBD's `/games/weather` sits behind a paid Patreon tier. Phase 1B
was asked whether a free archive could fill the gap.

**It can, and it now does.** Atlas has kickoff temperature, wind,
precipitation and humidity for **91.9% of the research sample**, from a
free, unmetered source, integrated into the warehouse.

**And it is worth nothing against the closing line.** The market prices
weather. That is a useful thing to have established rather than assumed.

---

## Section 1 - Weather sources

| Source | API key | Cost | Rate limit | Resolution | History | Verdict |
|---|---|---|---|---|---|---|
| Meteostat bulk files | none | free | none (static files) | hourly | decades | adopted |
| Open-Meteo archive API | none | free | daily quota per IP | hourly | 1940- | rejected - quota |
| CFBD /games/weather | required | paid tier | tier-gated | per game | 2018- | rejected - cost |
| NOAA NCEI GHCN-Daily | none | free | none | daily | decades | rejected - no kickoff hour |
| NWS api.weather.gov | none | free | courtesy | hourly | recent only | rejected - no history |

Notes from actually trying them:

* **Open-Meteo** is the obvious first choice and the wrong one for a
  nine-season backfill from shared infrastructure. The archive API is free and
  excellent, but it is metered per IP; from a shared egress address the daily
  quota was already exhausted, returning `Daily API request limit exceeded`.
  A backfill needs thousands of calls. On a dedicated IP it would be fine.
* **Meteostat** publishes the same class of station observations as **static
  gzipped files**, one per station. No key, no quota, no pagination - the
  delivery model matches the job. This is what Atlas uses.
* **CFBD weather** returns `401 ... requires a Patreon subscription at Tier 1
  or higher` on a free key, verified directly. It remains supported as a
  fallback in the collector, and is now redundant.
* **NOAA GHCN-Daily** is free and authoritative but daily. A daily mean
  temperature cannot answer what the wind was doing at an 8pm kickoff.

---

## Section 2 - Coverage

Each stadium is mapped to the nearest station with hourly coverage across the
seasons Atlas models; the kickoff hour is then read from that station's file
(nearest observation within two hours).

| Season | Games | With weather | Coverage | Mean temp (F) | Mean wind (mph) | Mean station distance (mi) |
|---|---|---|---|---|---|---|
| 2018 | 707 | 611 | 0.86 | 64.07 | 8.12 | 6.32 |
| 2019 | 699 | 612 | 0.88 | 64.08 | 8.11 | 6.30 |
| 2020 | 508 | 473 | 0.93 | 60.68 | 7.28 | 6.19 |
| 2021 | 732 | 672 | 0.92 | 65.97 | 7.35 | 6.34 |
| 2022 | 734 | 702 | 0.96 | 65.49 | 7.89 | 6.39 |
| 2023 | 792 | 736 | 0.93 | 66.87 | 7.23 | 6.54 |
| 2024 | 798 | 745 | 0.93 | 67.71 | 7.33 | 6.68 |
| 2025 | 808 | 761 | 0.94 | 67.39 | 7.18 | 6.54 |

Station distance is the thing to watch, and it is comfortable: the median
stadium sits about five miles from its station and none is beyond sixty.
Missing games are overwhelmingly gaps in a station's hourly record rather than
unmatched venues.

**Domes are handled explicitly.** The observed values are kept, and an
`_effective` set is derived that models what players experience: no wind and
room temperature indoors. Research can then test outdoor readings,
indoor-corrected readings, or both.

---

## Section 3 - Cost

Zero. No API key, no subscription, no quota. The whole backfill is roughly
140 station files, fetched once and cached; a rebuild re-reads them from disk.
Adding a season fetches nothing new unless a new stadium appears.

The only real cost is a dependency on a third-party mirror staying up. The
collector degrades to the CFBD path, and then to null columns, rather than
failing the build.

---

## Section 4 - Feasibility

Already done. `atlas/sources/meteostat.py` and `atlas/staging/weather.py` are
part of the standard build, and `make all` produces the weather columns with
no extra flags.

---

## Section 5 - Expected importance

Now measured rather than expected.

| Feature set | Target | n | MAE | Gain over baseline | t | Material? |
|---|---|---|---|---|---|---|
| Wind only (dome-corrected) | margin | 5,778 | 16.2085 | 0.0061 | 0.4904 | no |
| Wind only (dome-corrected) | total | 5,778 | 13.8388 | 0.0071 | 0.7654 | no |
| Wind only (dome-corrected) | residual_margin | 5,778 | 12.2278 | -0.0035 | -2.0226 | no |
| Wind only (dome-corrected) | residual_total | 5,778 | 12.7135 | -0.0086 | -1.3855 | no |
| Wind + wind squared | margin | 5,778 | 16.2139 | 0.0008 | 0.0610 | no |
| Wind + wind squared | total | 5,778 | 13.8401 | 0.0059 | 0.6351 | no |
| Wind + wind squared | residual_margin | 5,778 | 12.2340 | -0.0097 | -3.5796 | no |
| Wind + wind squared | residual_total | 5,778 | 12.7128 | -0.0079 | -1.2162 | no |
| Temperature only | margin | 5,778 | 16.2050 | 0.0097 | 0.5015 | no |
| Temperature only | total | 5,778 | 13.8406 | 0.0053 | 0.5839 | no |
| Temperature only | residual_margin | 5,778 | 12.2298 | -0.0055 | -1.7732 | no |
| Temperature only | residual_total | 5,778 | 12.7206 | -0.0157 | -2.8428 | no |
| Precipitation only | margin | 5,778 | 16.2195 | -0.0049 | -0.4023 | no |
| Precipitation only | total | 5,778 | 13.8484 | -0.0024 | -0.9047 | no |
| Precipitation only | residual_margin | 5,778 | 12.2323 | -0.0080 | -2.7737 | no |
| Precipitation only | residual_total | 5,778 | 12.7225 | -0.0176 | -2.9448 | no |
| All weather | margin | 5,778 | 16.2063 | 0.0083 | 0.3926 | no |
| All weather | total | 5,778 | 13.8441 | 0.0018 | 0.1330 | no |
| All weather | residual_margin | 5,778 | 12.2426 | -0.0183 | -3.1686 | no |
| All weather | residual_total | 5,778 | 12.7203 | -0.0154 | -2.0150 | no |

Against the market residual specifically:

| Model | Target | Features | MAE | Gain over market | t | Material? |
|---|---|---|---|---|---|---|
| Weather (wind/temp/precip) | residual_margin | 5 | 12.2426 | -0.0183 | -3.1686 | no |
| Weather (wind/temp/precip) | residual_total | 5 | 12.7203 | -0.0154 | -2.0150 | no |

**Nothing material.**

The raw relationship is there, and it is exactly the one folklore predicts -
and the market has already priced it:

| Wind band | Games | Closing total | Actual total | Residual | Over rate | z | Significant? |
|---|---|---|---|---|---|---|---|
| dome / calm | 807 | 55.019 | 55.772 | 0.753 | 0.520 | 1.131 | no |
| 0-5 mph | 1,022 | 54.194 | 55.071 | 0.877 | 0.526 | 1.638 | no |
| 5-10 mph | 1,971 | 54.485 | 55.110 | 0.625 | 0.499 | -0.113 | no |
| 10-15 mph | 1,176 | 54.061 | 54.186 | 0.125 | 0.472 | -1.906 | no |
| 15-20 mph | 245 | 53.495 | 52.861 | -0.634 | 0.448 | -1.610 | no |
| 20+ mph | 86 | 50.985 | 52.116 | 1.131 | 0.488 | -0.218 | no |

Scoring does fall as wind rises - about three points from calm to 15-20 mph.
But the **closing total falls with it**, and the residual column is what
matters: no band's over rate is more than two standard errors from 50%. The
20+ mph band reverses sign on 86 games, which is what noise looks like.

---

## Recommendation

1. **Keep the weather data.** It is free, it is integrated, and it costs
   nothing to carry. Establishing that a variable is priced is worth as much
   as finding one that is not - it closes a hypothesis.
2. **Do not give weather a role in Atlas Alpha v1.** No feature set cleared
   its own error bar on any target.
3. **The one place it might still earn its keep** is as an interaction rather
   than a main effect - extreme wind against a pass-heavy offence, for
   instance. Atlas now has the data to test that whenever there is a reason
   to. There is no reason to yet: the main effect is zero, and searching
   interactions without a prior is how a research programme finds noise.
