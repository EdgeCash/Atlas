# Polymarket US category survey: Weather

Read-only survey, run 25 Oct 2026 23:16 UTC to 26 Oct 00:30 UTC. Labels: **measured** (my own pull, with endpoint and UTC time), **cited** (a source, with URL), **inference** (my reasoning). Scripts, raw outputs and the small data set are in `weather_data/` beside this note. The raw pulls (about 5,400 hourly and 1,770 minute price histories, NBS/MOS, ASOS, CLI) are in `/tmp/claude-0/-home-user-Atlas/edbc1613-2236-53ad-a912-f62e839307df/scratchpad/weather/raw/`.

## Takeaway

The weather tab is one Kalshi-mirrored product: daily high-temperature buckets for six US stations, plus two low-temperature series, a thin daily-rain ladder and two long-dated NASA-GISS ranking markets. PMUS quotes sit a median **0.5¢** from Kalshi's. The free-forecast edge is not there. A walk-forward model built on the National Blend of Models (NBM) and calibrated on 170 days of NWS CLI errors was beaten badly by the market on 734 settled events: per-event log loss was **1.51 for the model against 1.22 for the market** the evening before, and **1.41 against 1.05** on the morning of the day. Every "model probability − ask − fee > X" rule lost money, **−3.4¢ per contract (n = 1,914)** and **−1.6¢ (n = 2,018)**. The observation edge has also been taken. When an hourly METAR made a live bucket impossible, the market had already pushed that bucket's No ask to ≥ 0.98 a median **6 minutes before the METAR could be read** (n = 62). The winning bucket reached 95¢ a median **3.8 hours before** the 6-hour-maximum group confirmed it. The only residue is stale books on maker-outage days: 8 observation-certain mispricings at 28–90¢ across 275 events, 4 of them on one day (5 Sep). That is a **Test-grade sentinel worth roughly $0–1 a day** on a $135 account, not a model-based edge.

## Q1. What is listed today

Source: [gateway events, `categories=climate`](https://gateway.polymarket.us/v1/events?closed=false&limit=500&categories=climate), pulled 23:16 UTC on 25 Oct (measured). The `category` filter is ignored; `categories` works. There were 21 open events. There is **no snowfall, hurricane, monthly-temperature or monthly-global-anomaly listing**.

| Family (series slug) | Cities / station | Buckets | Settlement source | Timing | Tick / fee | Spread & depth (measured) | Volume (measured, `/book` stats 23:17 UTC) |
|---|---|---|---|---|---|---|---|
| Daily high, `weather-daily-high-*` (`temp-{nyc,mia,mdw,lax,sfo,phl}high-YYYY-MM-DD`) | KNYC Central Park, KMIA, KMDW (Chicago **Midway**), KLAX, KSFO, KPHL | 6: two open tails plus four 2°F buckets, e.g. "68 to 69" (slug `gte68lt69f` means 68 or 69 inclusive) | Final NWS Daily Climate Report (CLI) for that station. CLI day = midnight–midnight **local standard time** | Listed about 09:45 UTC the day before. Market `endDate` is 09:00–12:00 UTC on D+1. FAQ: "Settlement occurs at 8:00 AM ET on the day following… may be delayed until 11:00 AM ET" if the CLI conflicts with the 24-h METAR ([Weather FAQs](https://docs.polymarket.us/faqs/weather-faqs.md), cited) | 0.01 / 0.0695·p(1−p) on every market | For tomorrow's (26 Oct) 25 two-sided legs priced 5–95¢: median spread **2¢**, p90 6¢. Top-of-ask **median $10**, p25 $4. **$124 within 5¢ of the ask** (median). 11 of 48 tops changed between snapshots 8 minutes apart (23:28 vs 23:36 UTC) | Settlement-day high events traded 5.6k–65k shares and **$1.9k–10.2k notional** (NYC $9,951; MIA $10,188; LAX $7,968; SFO $5,733; MDW $1,985; PHL $1,941). The day before: $150–870 per event |
| Daily low, `weather-daily-low-{nyc,chicago}` | KNYC, KMDW | Same 6-bucket ladder | CLI minimum | Same | Same | Wider: 4–7¢ on the live legs, 28-share levels | $377–1,604 on settlement day |
| Daily rain, `rain-daily` | KNYC, **KORD** (not Midway), KMIA, KPHL, KLAX, KSFO | 1 Yes/No per city | Any METAR/SPECI present-weather group with RA (not VCSH, RE, RMK), counted in local standard time. Source: aviationweather.gov raw METAR. CLI fallback | Market `endDate` is about 10 days out | Same | Five of six cities show only a **0.99 Yes ask with no bid** (placeholder). Miami is 0.86/0.93 | **45–80 shares a day**, ~$40–70 |
| Hottest-year rank (`yr-httst`), 2026 and 2027 | Global, NASA GISS LOTI "No_Smoothing" | 1st / 2nd / 3rd / 4th / ≤5th | GISS table | Ends Mar 2027 / Mar 2028 | Same | 1¢ wide (2026 "1st" 0.84/0.85) | $28k notional lifetime (2026) |
| SJC below 40°F in December | KSJC | 1 market | CLI | Jan 2027 | Same | **Empty book** | 0 |

The settled history is 904 closed climate events (894 temperature, 10 rain), 23 Apr – 24 Oct 2026, 5,423 markets, all resolved, all on the same tick and fee. The five original cities run from 23 Apr; PHL and the two low series from 16 Oct (measured, `closed=true&categories=climate`, two pages).

Mechanics that matter (measured unless noted):

- **The tape is not a quote tape.** `/v1/price-history` returns `longPrice` = Yes best ask and `shortPrice` = No best ask (= 1 − Yes bid) while both sides exist. When a side is empty it reports a filler instead. For example, a dead bucket with no Yes bid prints `shortPrice` 0.99, and the NYC-low "40 to 41" leg printed 0.78 with no bid at all (checked against `/bbo` at 23:3x UTC). Of 400,269 minute points, 7.5% were crossed (implied bid > ask). Every backtest below drops crossed points, and depth is never visible in history.
- **IEM's CLI JSON matched the settlement on 893 of 894 events.** The one miss (LAX 22 Oct, JSON 71) is an IEM parse error: the CLI text reads 72, which is what settled ([IEM CLI text](https://mesonet.agron.iastate.edu/api/1/nwstext/202610230848-KLOX-CDUS46-CLILAX), measured). Settle off the CLI text, not the JSON.
- **The CLI high is usually above the hourly METAR maximum.** Using only T-group (0.1°C) temperatures from hourly and special METARs (IEM ASOS archive), the CLI high equalled the METAR maximum on 307 of 874 days (35%). It was **+1°F on 470 (54%), +2 on 84 (9.6%), +3–4 on 12**, because the peak falls between observations. Adding the 6-hour maximum groups (`1snTTT` at 00/06/12/18Z) makes the match exact on 859 of 874 (98.3%). One day went the other way: KNYC on 27 Aug had a single 80°F spike (and a 6-h group of 81) that the forecaster removed, and the CLI read 77. Specials without a T-group turn whole-°C values into ±1°F errors (4 such cases). A running hourly maximum is therefore a lower bound on the CLI high in **873 of 874 cases**, but not an estimate of it.
- **Kalshi lists the same six cities with identical bucket edges.** At 23:32–23:35 UTC, 28 matched two-sided legs for 26 Oct showed a **median |PMUS mid − Kalshi mid| of 0.5¢ (max 1.5¢)**, with PMUS spreads 2¢ against Kalshi's 1¢. Kalshi traded 1.5–4× PMUS's contracts on the settlement-day events (NY 126k, MIA 140k contracts) ([Kalshi markets API](https://api.elections.kalshi.com/trade-api/v2/markets?series_ticker=KXHIGHNY&status=open), measured). Kalshi's rules use the same "final CLI, delayed if inconsistent with 6-h/24-h METAR highs, local standard time" language ([Kalshi weather help](https://help.kalshi.com/markets/popular-markets/weather-markets), cited).

## Q2. Forecast-model fair value against the book

**Data used (measured).**
- NBM station text (NBS) for all six stations, every 00/06/12/18Z run from 15 Apr to 25 Oct, from the [IEM MOS archive](https://mesonet.agron.iastate.edu/cgi-bin/request/mos.py?station=KNYC&model=NBS&sts=2026-04-15T00:00Z&ets=2026-10-26T00:00Z&format=csv). It gives `txn` (the 12-h max/min) and `xnd` (the NBM's own standard deviation).
- The NWS gridpoint forecast ([api.weather.gov](https://api.weather.gov/gridpoints/OKX/34,45)).
- The Open-Meteo ECMWF-IFS 51-member ensemble. **The Open-Meteo forecast API (HRRR, NBM, GFS) returned "Daily API request limit exceeded"** from this shared IP at 23:27 UTC, so HRRR could not be pulled. Only 4 of 6 ensemble calls succeeded.

**Error statistics (measured, CLI − NBS `txn`, high temperature, 25 May–24 Oct):**

| NBS run used | n | bias | SD of error | MAE | share within ±1°F | mean NBM `xnd` | SD(error/xnd) |
|---|---|---|---|---|---|---|---|
| D−1 12Z | 859 | −0.27 | 2.70 | 2.01 | 47% | 2.20 | 1.36 |
| D−1 18Z | 859 | −0.26 | 2.63 | 1.96 | 49% | 2.19 | 1.29 |
| D 00Z | 859 | −0.28 | 2.58 | 1.92 | 50% | 2.16 | 1.26 |
| D 12Z | 864 | −0.29 | 2.36 | 1.77 | 54% | 1.93 | 1.30 |

- Station biases are large and drift: KNYC ran −1.2°F (−1.9 in June, −0.3 in October), KLAX +0.6 (+1.8 in October), KSFO −0.7 with an SD of 3.0–3.6.
- The NBM's `xnd` understates the real spread by about 1.3×.
- Errors are fat-tailed: kurtosis 4.5, and 16% of days miss by ≥ 4°F.

The model is walk-forward. For each event it uses only CLI residuals from earlier dates: 70% the station's empirical residual distribution and 30% pooled residuals, with ±1°F smoothing. A second variant uses a Gaussian with a 30-day rolling bias and SD = k·`xnd`. Each was scored at two decision points against the venue's hourly tape: **T1**, 20:00 UTC on D−1 using the 18Z run, and **T2**, 14:00 UTC on D using the 12Z run (9–10 am ET). Hourly histories cover all 5,423 markets (`/v1/price-history?fidelity=60&fixedInterval=INTERVAL_ALL`, pulled 23:20–00:26 UTC).

| | Events | Log loss, model | Log loss, market (normalised mid) | Brier per event, model / market |
|---|---|---|---|---|
| T1 (evening before) | 734 | **1.514** | **1.220** | 0.749 / 0.635 |
| T2 (morning of) | 737 | **1.410** | **1.048** | 0.718 / 0.569 |
| Gaussian variant, best k = 1.3, T1 / T2 | 142 / 143 | 1.573 / 1.483 | 1.090 / 0.941 | |

(All measured.) The market is far sharper than the free NBM. Its favourite bucket carries 50–60% where the NBM's error distribution allows about 30–35% for any 2°F bucket, and it is about right to do so.

**Calibration of the venue (measured, Yes ask bin → realised win rate):**

| Yes ask bin | T1: n, mean ask, won | T2: n, mean ask, won |
|---|---|---|
| 0.00–0.05 | 1,142, 0.026, **0.008** | 1,711, 0.020, **0.005** |
| 0.05–0.15 | 1,179, 0.085, **0.051** | 877, 0.084, **0.050** |
| 0.15–0.30 | 870, 0.217, 0.189 | 592, 0.216, 0.186 |
| 0.30–0.50 | 885, 0.385, 0.366 | 649, 0.390, 0.368 |
| 0.50–0.70 | 294, 0.562, 0.517 | 447, 0.583, **0.521** |
| 0.70–0.85 | 23, 0.766, 0.783 | 98, 0.753, **0.694** |
| 0.85–0.95 | 8, 0.897, 0.875 | 27, 0.898, 0.778 |

Every bin wins less often than its ask, as it must with a 2¢ spread. The gap to the mid is small (mid 0.554 against a 0.521 win rate in the T2 0.50–0.70 bin). So the published global-Polymarket finding, that favourites are overpriced in the hours before the peak ([arXiv 2610.13593](https://arxiv.org/html/2610.13593), cited: −11 pp in the 70–90% bin at 6 h, and "do not establish executable trading profits"), shows up here only weakly and only inside the spread.

Rules a taker can actually execute, with clustered standard errors (measured, `weather_data/scripts/simple_rules.py`):

| Rule (one point per bucket, crossed prints excluded) | T1: per contract (event-clustered se) | T2 |
|---|---|---|
| Buy No on the favourite (Yes ask 0.50–0.95) at the real No ask | −5.2¢ (2.7), 298 events | **−1.4¢ (2.0)**, 550 events |
| Buy Yes on the favourite | −5.7¢ (2.8) | −8.0¢ (2.0) |
| Buy No on 5–15¢ longshots | +0.0¢ (0.7) | +0.0¢ (0.9) |
| Buy No on 2–5¢ longshots | +0.2¢ (0.8) | +0.6¢ (0.7) |
| **Model rule, q − ask − fee > 0.05 (both sides)** | **−3.4¢, n = 1,914** | **−1.6¢, n = 2,018** |
| Model rule, > 0.10 | −4.1¢, n = 1,147 | −1.2¢, n = 1,434 |
| 50/50 model–market blend, > 0.05 | −4.0¢, n = 905 | −1.4¢, n = 1,174 |

Of 24 rule/threshold cells, two came out positive: 30% model weight with X ≥ 0.10 at T1 (n = 52, +9.4¢ ± 5.3; n = 15, +34¢ ± 8.3). Those are what multiple testing produces and do not support a rule.

**Today's books against the model (measured, NBS 18Z run on 25 Oct against `/book` at 23:27:54 UTC; table `weather_data/live_model_vs_book_2026-10-25T2327Z.csv`).** The model says every favourite for 26 Oct is overpriced by 25–37 points:

| Leg | Model | Book |
|---|---|---|
| NYC 68–69 | 0.33 | 0.60 / 0.64 |
| MIA 83–84 | 0.45 | 0.66 / 0.69 |
| LAX 77–78 | 0.34 | 0.70 / 0.71 |
| PHL 70–71 | 0.23 | 0.52 / 0.58 |
| SFO 66–67 | 0.25 | 0.51 / 0.53 |

It also flags NYC "67 or below" at +26¢ on the Yes side. Kalshi priced the same legs within a cent, and the raw ECMWF ensemble centres agreed with the market rather than the NBS: NYC 67.7, SFO 66.9. The backtest says this pattern is the model being blunt, not the market being wrong. Sharp market favourites at 0.50–0.70 won 52%, not the ~31% the model assigned them (inference from the T2 table).

The better models are an obvious upgrade: hourly NBM runs, HRRR, ECMWF/AIFS, station-specific ML bias correction. They would cost a dedicated IP or a paid weather API (Open-Meteo commercial is roughly tens of dollars a month; inference) and weeks of building. They would have to close a **0.36-nat log-loss gap** before they even reached the market, against Kalshi weather bots that already do exactly this ([vendor claims summarised here](https://www.botforkalshi.com/blog/can-you-bet-on-the-weather), cited, unverified).

## Q3. The intraday observation edge

**Lower-bound kills (measured, `weather_data/scripts/lag2.py`).** The test covers 275 high-temperature events from 1 Sep to 24 Oct with minute histories on day D (`fidelity=1`, 14:00Z D to 09:00Z D+1) and IEM ASOS METAR/SPECI with T-groups. A spike filter rejects any rise of more than 3°F over the previous observation. A "kill" is the first moment the running maximum exceeds a bucket's upper edge, which makes that bucket impossible (1 exception in 874 days, above). A kill is "marginal" if the bucket's mid was ≥ 5¢ thirty minutes earlier, giving **62 marginal kills**:

- 4 minutes after the METAR (when it can first be read on aviationweather.gov), the bucket's No ask was already ≥ 0.98 in **55 of 62**.
- 60 of the 62 reached No ≥ 0.98 inside the window. Measured from that moment, they got there a **median 6 minutes earlier**. The 10th, 25th, 75th and 90th percentiles were −32, −25, −3 and −2 minutes, so at least 90% had moved before the METAR could be read.
- The makers are reading data faster than hourly METAR. api.weather.gov serves 5-minute ASOS readings for KMDW, though in whole °C (71.6°F = 22°C). The KNYC feed had gaps: no 18, 20 or 21Z observations on 25 Oct (measured 23:40 UTC). On NYC 13 Oct the "70 or below" leg fell from 0.95 to 0.77 between 00:30 and 00:39Z, twenty minutes before the 00:51Z METAR showed the late warming.
- Seven kills had a No ask below 0.98 at that moment, and five of those were crossed fillers with no Yes bid (not executable). The two uncrossed ones were both SFO on 5 Sep: 71–72 still showed a Yes ask of 0.60 and a No ask of 0.44 for 241 minutes after the observed maximum passed 72, and 69–70 showed a No ask of 0.92. LAX on 9 Sep later turned into an uncrossed "84 or below" No at 0.28 for 61 minutes.

**Upper-side lock at 00:05Z (measured).** The rule: true maximum so far = max(T-group observations, 6-h maximum groups from the 18Z and 00Z METARs), and the current temperature is ≥ 3°F below it. In the **239 events that qualified, the bucket holding that maximum won 234 (97.9%)**. The five misses all show the station-vs-CLI subtleties:

| Station, date | What happened |
|---|---|
| NYC 13 Oct | The maximum came at 9:51 pm EDT; the 24-h group read 71 |
| NYC 17 Oct | The maximum fell in the first LST hour |
| PHL 15 Oct | CLI 73 against a METAR/6-h maximum of 70 |
| LAX 11 Oct | CLI 74 against 73 |
| LAX 22 Oct | No 6-h group at 00Z; CLI 72 against a METAR maximum of 71 |

In three of the five (NYC 17 Oct, PHL 15 Oct, LAX 11 Oct) the market already priced the "locked" bucket at 0.01 at 00:05Z: it knew better than the rule. In the other two it was as wrong as the rule (0.95 on NYC 13 Oct, which fell to 0.01 later in the night; 0.93 on LAX 22 Oct). It was also earlier. The eventual winner first showed a Yes ask ≥ 0.95 (with an implied bid ≥ 0.90) a **median 230 minutes before 00:05Z** (quartiles −315 and −160; n = 272).

**Late favourites (measured, `late.py`, one point per event and hour).** Buckets asked at 0.97 or more at 17, 19 and 21 LST won **53 of 57 (93.0%)** against a 97.9% break-even. The losses were real station-vs-CLI cases:

- LAX 22 Oct, 70–71 at 0.98 all evening: the CLI found a 72 peak between observations, and the 00Z METAR had no 6-h group.
- NYC 13 Oct: the late-night maximum above.
- SFO 5 and 11 Sep.

At 13–15 LST, 0.97+ asks won 60 of 62, for −0.9 to −1.0¢ per contract. The "buy the locked-in favourite at 97–98¢" settlement-yield idea does not pay here (measured). It is the mirror of the sports finish-line trade, but the "final" signal (CLI) lands 12–16 hours after the market is priced, and the tail risk is real.

**Repricing time, short answer:** on a normal day PMUS reprices impossible buckets **before** an hourly METAR can be read. Hours-long lags happen only on stale-book days. Low-activity days (price changes per market between 16 and 23Z) were **5 Sep at 19.4 and 5 Oct at 17.2, against a median of 74** (measured).

## Q4. Backtest and replay

Every rule tested is in the Q2 and Q3 tables. Sample sizes: 734–737 events (May 25–Oct 24) for the model rules, 275 events (Sep 1–Oct 24) for the observation rules, and minute tapes for 1,770 markets.

The one positive-expectation pattern is the **stale-book sentinel**. It fires when an observation-certain outcome (a spike-filtered lower-bound kill, or the 00:05Z 6-h lock with a ≥ 3°F drop) is offered at an uncrossed price ≤ 0.90, and the market is not already at ≤ 0.10 on the "certain" side (that filter would have excluded all 4 lock-rule errors, which is in-sample tuning).

- Over 275 events it found **8 instances on 5 dates, and all 8 won**:

| Date | Leg | Price |
|---|---|---|
| 5 Sep | SFO 73–74 | Yes 0.32 |
| 5 Sep | NYC 79–80 | Yes 0.34 |
| 5 Sep | LAX ≥ 81 | Yes 0.83 |
| 5 Sep | SFO 71–72 | No 0.44 |
| 9 Sep | LAX ≤ 84 | No 0.28 |
| 18 Sep | SFO 68–69 | Yes 0.40 |
| 26 Sep | NYC ≤ 61 | Yes 0.90 (3 minutes) |
| 15 Oct | MDW 65–66 | Yes 0.31, for 331 minutes |

- The ≤ 0.10 filter also threw away two 5 Sep winners: MDW 83–84 at 0.01 and MIA 92–93 at 0.10. That is the price of the filter.

- The average edge is about **+50¢ per contract**, but the depth behind those quotes is unknown, and top-of-book on normal days is a median $10 (measured).
- Rough dollars (inference): about 1 hit a week, each filling $5–25 at around +50%, comes to **$3–12 a week, roughly $0–1.5 a day**. This is a sample from one maker's bad days, and it could be zero next quarter.

## Q5. Competition

- **Who makes the PMUS book (measured and inference).** Resting sizes cluster at 8, 28, 16, 1, 100 and 2,028 shares across many legs (Oct 26 snapshot). There are 0.01 / 0.99 walls of 7,500–470,000 shares on dead buckets. Quotes stay within 0.5¢ of Kalshi's. This looks like one or two automated cross-venue makers hedging on Kalshi. Their absence on 5 Sep and 5 Oct is visible on the tape.
- **Kalshi.** Kalshi runs the same buckets at roughly 2–4× PMUS volume, with 1¢ spreads (measured). Vendors sell "weather edge" bots and scrapers, and one bot reportedly made about $1,800 on GFS-ensemble disagreement >8% before it stopped working (cited via search summaries, [botforkalshi](https://www.botforkalshi.com/tools/kalshi-weather-edge), [apify scrapers](https://apify.com/lergassy/kalshi-weather-scraper); unverified vendor claims).
- **The academic evidence** on Polymarket weather finds no edge over public forecasts ([arXiv 2610.13593](https://arxiv.org/html/2610.13593), cited).

## Build spec (Test grade only: nothing clears the bar for a real model edge)

**Stale-book weather sentinel**, `atlas/polymarket/weather_sentinel.py` (proposed).

- **Data.**
  - IEM or aviationweather.gov METAR/SPECI for the six stations every 5 minutes, using T-groups and 6-h / 24-h groups. Free.
  - The CLI text on D+1 for grading.
  - PMUS `/v1/events?categories=climate&closed=false` every 5 minutes, then `/book` on the at most 6 candidate legs.
  - No forecast model, no WebSocket needed. The stale windows lasted 16–536 minutes, so the 45-second poll and the 30-second edge cache are fine.
- **Rule.**
  - **(a) Kill.** The spike-filtered running maximum (2 consecutive T-group observations ≥ edge + 1, LST day) puts a bucket below the maximum. Buy **No** if the No ask is ≤ 0.85 and a Yes bid really exists in `/book`.
  - **(b) Lock**, after the 00Z METAR (or the 24-h group at local midnight LST for the west):
    - The 6-h groups cover 12–00Z.
    - The current temperature is ≥ 4°F below the maximum.
    - The NBS overnight `tmp` path stays ≥ 3°F below the maximum.
    - No warm-front signature (temperature not rising in the last 2 observations).

    Buy **Yes** on the bucket holding the maximum if the ask is between 0.30 and 0.85.
  - Never act if the market sits at ≤ 0.10 on the "certain" side. Never act on lows or rain.
- **Sizing.** $5 per order for the first 30 days, then the worker's $25 cap. At most 3 concurrent positions. Capital stays locked until the 8 am ET settlement on D+1.
- **Kill conditions.**
  - Any loss on a "certain" trade: stop and audit the station/CLI logic.
  - Fewer than 2 fills in 60 days: retire it as not worth the upkeep.
  - Fills averaging under 20 shares: retire it.
  - PMUS changes settlement wording or delists cities.

## Ranked strategies

| Rank | Strategy | Verdict | Realistic $ at $135 | What the worker needs | Main risks |
|---|---|---|---|---|---|
| 1 | Stale-book sentinel: observation-certain bucket offered ≤ 0.85 on maker-outage days | **Test** ($5 clips, instrumented) | ~$0–1/day (8 hits in 275 events, 5 dates; depth unknown) | METAR parser with T-group, 6-h/24-h groups, spike filter and LST day; climate-category poll every 5 min; `/book` read to confirm a real bid/ask; CLI-text grader | One-sided depth of a few shares; CLI ≠ METAR (night maxima, between-observation peaks, QC'd spikes); overfitted filter; outages may stop |
| 2 | Passive maker selling favourites (realised 52% against a 58¢ ask at T2) | Skip for now (Test only on paper) | ≤ $0.5/day, unproven | Resting orders, cancel-on-move, WebSocket | Adverse selection by Kalshi-hedged makers; no rebates; mispricing sits inside the 2¢ spread |
| 3 | NBM/MOS fair-value taker (any threshold) | **Skip** | Negative: −1.6 to −3.4¢ per contract | NBS ingest and calibration (free) | Market log loss 0.29–0.36 nats better than the model |
| 4 | Buy evening favourites at 0.97–0.98 (settlement yield) | **Skip** | Negative: 53/57 won against 97.9% break-even | Nothing new | Station-vs-CLI tails; capital locked 12–16 h |
| 5 | Hourly-METAR lag (sell newly impossible buckets) | **Skip** | ~0 on normal days | METAR feed | Market moves a median 6 min before the METAR is readable |
| 6 | Longshot No (2–15¢) | **Skip** | ~0 (+0.0 to +0.6¢ ± 0.7–0.9) | Nothing new | Fee and spread eat it |
| 7 | Rain ladder | **Skip** | ~0 | METAR present-weather parser | 45–80 shares a day; once rain is observed nobody sells the winner (KMIA 25 Oct: −RA at 14:53Z, book bid 0.41 with no ask) |
| 8 | Hottest-year rank / SJC December | **Skip** | ~0 | n/a | 4–17-month capital lock, 1¢ spread, or an empty book |
