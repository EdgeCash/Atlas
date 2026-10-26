# Commodities tab on Polymarket US: what is listed, how it is priced, and whether the worker can use it

Read 25–26 October 2026, 23:16–00:30 UTC, from the public gateway (`gateway.polymarket.us`) and free data sources. Read-only: no authentication, no orders, no repository code changed. Each finding is labelled **measured** (endpoint and UTC time), **cited** (URL and date) or **inference**. Scripts and compact data are in `commodities_data/` beside this note (1.4 MB). Fee convention as in the prior survey: taker fee = 0.0695·p·(1−p) per contract. Makers pay nothing below $10M of monthly maker volume.

## Takeaway

The Commodities tab is small. It holds **11 open events**: gold and silver Up/Down windows (15-minute, hourly, daily; listed only since 22 Oct 2026), AAA national-average gasoline (a daily ladder plus 2026 high/low ladders), and BLS ground beef (2026 high/low). It has **no oil, natural gas, copper, eggs or grains**. Only two families carry real money. The gas year-end ladders have traded 35k–107k contracts per strike. The gold/silver 15-minute windows trade a median of 360 and 105 contracts per window. Everything else trades from zero to a few hundred contracts.

Where a model can be built, the market is either efficient or ahead of the model:
- **Metals.** After launch day, the 15-minute quotes sit within a median 2.2¢ of a lognormal fair value computed on the venue's own Chainlink feed, and a taker trading model-vs-quote gaps earns nothing.
- **Gas daily ladder.** An informed bidder set the correct 0.5¢ bracket on 4 of 4 nights. My best nowcast hits about 16%.

Two small, model-based edges remain:
1. **Late-window "certainty" buys in the metals 15-minute windows.** Measured at +0.8 to +2.9¢ per contract after fee, over 26–50 windows, with at most one loss; 49 of the 50 windows fall on 23 Oct, the only full trading day since launch.
2. **Selling the upside tails of the gas year-end ladder.** Bids of 0.11–0.40 sit against model fair values of 0.01–0.21, a gap of 3–19¢, but the money is locked until January and exposed to an oil shock.

At $135 the first is worth perhaps **$2–8 a day if it survives a live test**. The second is worth **$5–15 once**. Neither justifies more than a test.

## Q1. What is under the Commodities tab

### Takeaway
The tab corresponds to the event tag `commodities` (tag id 1284, label "Commodities"). It is not a gateway `category`: the metals events carry `category: "finance"` and the gas and beef events `category: "macro"`. On 25 Oct 23:16Z it held 11 open events with 45 markets in four product families. Settled history is short: metals from 22 Oct, the daily gas ladder from 21 Oct (plus two September one-offs), and gas monthly high/low for September.

### Measured findings
- **Listing.** `GET /v1/events?closed=false&limit=500&offset=0…4500` at 23:16Z returned 4,861 open events. Categories: sports 3,316, politics 1,245, culture 149, crypto 57, macro 39, climate 21, finance 16, technology 10, geopolitics 4, science 4. Tag `commodities`: 11 events. Tags `gold`, `silver`: 3 each. Tag `gas`: 3. Tag `metals`: 6.
- **Closed history.** `GET /v1/events?tagSlug=commodities&closed=true&limit=500` returned 427 events. Gold and silver each have 158 events in the 15-minute series (113 resolved), 48 hourly (27 resolved) and 3 daily (2 resolved). Gas: 7 `usgas-day` events, plus `usgas-highm/lowm-2026-09-30`. Upcoming metals windows are listed as "closed" until they start (cited: metals FAQ below).
- **Not listed.** There is nothing on WTI or Brent, natural gas, copper, platinum, corn, wheat, eggs or coffee. Kalshi lists many of these (e.g. `KXOIL`, `KXNGAS`, `KXEGGS`, 140+ AAA state series), and Polymarket US does not (measured: `api.elections.kalshi.com/trade-api/v2/series?category=Economics`, 23:22Z).

| Family (event slug / series) | Contract wording (verbatim core) | Settlement source and time | Tick / fee | Spread, depth, volume (measured 23:19–23:51Z) |
|---|---|---|---|---|
| Gold / silver Up/Down 15m (`gold-updown-15m`, `silver-updown-15m`; products CPAUSP / CPAGSP) | "settle to Up if the price of gold at 7:30PM ET … is greater than or equal to the price of gold at 7:15PM ET … Chainlink XAU/USD spot price data stream (XAU/USD-Streams-ForexPrice), rounded to the nearest cent" (silver: XAG/USD, 3 decimals) | Single Chainlink spot value at window start and end (not an average). Trading ends at window end. Settlement posts a median **58 s** after the end (p10 53 s, p90 71 s; 202 windows) | 0.01 / 0.0695 | Median spread **1¢**. Top of book 2–115 contracts (gold 0.22×50 / 0.23×47). Contracts traded per window: gold median 360 (max 2,177; 16 of 113 untraded), silver median 105 (27 untraded) |
| Gold / silver Up/Down 1h and daily | Same wording, 1-hour or 22h45m window (6:15 PM ET to 5:00 PM ET) | Same | 0.01 / 0.0695 | **No market**: no bid, ask 0.99×25 (gold) or 0.99×1 (silver). Hourly median spread 10¢. Traded: gold 1h median 4 contracts, daily 0 |
| AAA gas daily ladder (`usgas-day-2026-10-26`, product AAAGASPC) | "settle to Yes if the US national average price of regular gas is greater than $4.2750 for October 26, 2026 … as published by AAA at 10:00 AM ET on that date" | Trading closes **00:00 ET** at the start of the date (event `endDate` 04:00Z). Settled at 14:05:01–02Z (10:05 ET) on Oct 21–25. Settles No if AAA has not published within 3 days | 0.01 / 0.0695; strikes 0.5¢ apart (17 strikes) | 0–668 contracts traded per strike per day. Decided strikes bid 0.99×4,555 with no offer. The live boundary strike quoted 0.32×100 / 0.41×100 |
| AAA gas 2026 high / low (`usgas-high-2026-12-31`, `usgas-low-2026-12-31`) | "greater than $4.60 [less than $4.00] for any date from September 9, 2026 through December 31, 2026, inclusive. Outcome sourced from AAA" | AAA daily; market expiry 15 Jan 2027 | 0.01 / 0.0695 | Traded 8k–107k per strike, open interest 211–2,632. Top quotes are often dust (<0.1 contract). Size-≥1 spread is 1¢ on the tails (e.g. >5.00 at 0.26×36 / 0.27×3,505) and up to 70¢ on the inner strikes (e.g. <4.00 at 0.26×66 / 0.96×1,077) |
| BLS ground beef 2026 high / low (`usbeef-hi-yr`, `usbeef-lw-yr`, product GBAPC) | "U.S. city average price of ground beef, 100% beef, per pound for any month from September 2026 through December 2026 is greater than or equal to $7.00 … taken as first published" (BLS series APU0000703112) | Monthly BLS CPI average-price release, 08:30 ET. Expiry 28 Jan 2027 | 0.01 / 0.0695 | Traded 54–3,126 per strike (≤ $6.80: 51,582). Large maker offers of ~3,250 contracts at many strikes above bids of 2–80 contracts |

Sources: [listing](https://gateway.polymarket.us/v1/events?closed=false&limit=500&offset=0), [book](https://gateway.polymarket.us/v1/markets/aaagaspc-usgas-high-2026-12-31-gt5pt00/book), [bbo](https://gateway.polymarket.us/v1/markets/cpausp-gold-updown-15m-2026-10-25-2315z/bbo); per-market data in `commodities_data/pmus_commodities_book_snap{1,2}.json`.

### Cited findings
- Gold and silver: "One automated market family … Up/Down … 15-minute, 1-hour and daily windows"; "listed in production from October 22, 2026"; "single spot values, not 60-second averages"; ties settle Up; "Trading ends at the end time regardless"; no listing from Fri 5:00 PM to Sun 6:15 PM ET, and none from 5:00 to 6:15 PM ET daily; 15-minute windows are listed ~12 h ahead — [Gold and Silver FAQs](https://docs.polymarket.us/faqs/metals-faqs.md) (read 25 Oct 2026).
- The settlement feed is public with no key: `GET /v1/asset-prices/history?assets=commodity:gold&bucket=ASSET_PRICE_BUCKET_1S`, "one value per second" — [Asset Prices API](https://docs.polymarket.us/api-reference/asset-prices/overview.md) (read 25 Oct 2026). Measured: that endpoint answers `cf-cache-status: DYNAMIC` (uncached), while `/bbo` and `/book` answer `public, max-age=30`, HIT (23:34Z).
- Fees: taker Θ 0.0695; maker Tier 1 (below $10M a month) "No maker rebate" — [Fee Schedule](https://docs.polymarket.us/fees.md) (read 25 Oct 2026).

### Inferences
- The tab is a recent grouping of new recurring metals series and a few macro-style commodity prints, much smaller than Kalshi's commodity range. Expect more series (oil, natural gas) to appear without notice. A worker should discover markets by `tagSlug=commodities` and `assetPriceTerms.asset.assetClass == ASSET_CLASS_COMMODITY`, not by hard-coded slugs.

## Q2. Fair value versus Polymarket US price

### Takeaway
- **Metals 15m.** A driftless lognormal on the venue's own Chainlink feed, with trailing-hour realised volatility, matches the book to within a median 2.2¢ (RMS 4.0¢). Brier scores are equal: gold model 0.156 vs market 0.158, silver 0.157 vs 0.156. Gap-trading earns nothing.
- **Metals, launch day.** On 22 Oct the books were stale and one-sided (Up bid 0.99 in windows that settled Down). That is gone now.
- **Gas daily.** My nowcast cuts error from 1.85¢ to 1.22¢ against no-change, but the market's informed bid is better still.
- **Gas year-end.** The ladder prices upside tails 3–19¢ above even my most generous pass-through model.
- **Beef high ladder.** Quoted at several to tens of times the random-walk fair value, but the bids that could be sold into are 2–57 contracts each.

### Measured findings: gold and silver
- **Data.** 284 resolved windows (`/v1/price-history?...&fidelity=1`, custom ranges, 23:28–23:30Z), settlements (`/v1/markets/{slug}/settlement`), and 57,241 five-second Chainlink candles per metal from 22 Oct 16:00Z to 25 Oct 23:30Z (`/v1/asset-prices/history`, 23:31Z). The 5-second candle open at `windowStart` equals the stamped `priceToBeat` in 282 of 284 windows; the other 2 had no candle.
- **Timestamp convention.** A price-history point stamped *t* reflects the book at about *t*+60 s. Mean squared model-vs-mid difference is lowest at a +60 s shift: gold 0.0169 vs 0.0281 unshifted; silver 0.0017 vs 0.0144. Any backtest on this endpoint must shift by a minute.
- **Calibration, excluding 22 Oct.**

  | Series | Rows | Windows | Median spread | RMS gap model − mid | Median gap | Brier model | Brier mid |
  |---|---|---|---|---|---|---|---|
  | gold-updown-15m | 1,232 | 88 | 1¢ | 4.0¢ | 2.2¢ | 0.156 | 0.158 |
  | silver-updown-15m | 1,232 | 88 | 1¢ | 4.0¢ | 2.2¢ | 0.157 | 0.156 |
  | gold-updown-1h | 1,239 | 21 | 10¢ | 4.2¢ | 2.9¢ | 0.155 | 0.157 |
  | silver-updown-1h | 1,239 | 21 | 10¢ | 3.9¢ | 2.7¢ | 0.164 | 0.160 |

- **Taker rule** (buy the side whose model probability exceeds ask + fee by a threshold, one entry per side per window, filled at the next minute's quote). 15m gold: +0.5¢ (threshold 2¢, n=81), −4.8¢ (5¢, n=34), −1.7¢ (10¢, n=6). Silver: −6.2¢ (2¢, n=88), +0.6¢ (5¢, n=27). Hourly silver: −18 to −22¢. Standard errors are 4–20¢, so every result is consistent with zero or negative.
- **Launch day (22 Oct 18–23Z).** The hourly model-vs-mid RMS was 20–92¢. For example, the 22:45Z gold window showed ask Up 0.99 / ask Down 0.01 (an Up bid of 0.99) for ten minutes while the model went to 0.00 and the window settled Down. Size was not recorded. From 23 Oct 00Z the hourly RMS gap fell to 2–6¢.
- **Late-window certainty** (last 5 minutes, model side ≥ threshold, ask ≤ 0.97, edge > 1¢, first signal per window, filled at the next minute's ask). Gold and silver 15m after launch day:

  | Model threshold | Windows (49–50 of them on 23 Oct) | Mean P&L per contract after fee | Losses |
  |---|---|---|---|
  | ≥ 0.95 | 50 | +2.9¢ | 1 |
  | ≥ 0.97 | 44 | +0.8¢ | 1 |
  | ≥ 0.99 | 26 | +2.5¢ | 0 |

  In the final stamped minute, the winning side's ask was ≥ 0.99 in 170 of 187 windows and ≤ 0.95 in 11. (Data: `commodities_data/metals_model_vs_quote_minute_rows.json`.)
- **Context.** GVZ 24.34, OVX 60.02, Brent $116.72 / WTI $103.27 on 23 Oct closes; gold futures $4,007.9, silver $53.71 ([CBOE GVZ history](https://cdn.cboe.com/api/global/us_indices/daily_prices/GVZ_History.csv), Yahoo chart API `GC=F`, `SI=F`, `BZ=F`, `CL=F`, read 23:35Z). For 15-minute windows the trailing realised volatility on Chainlink was used, not GVZ. GVZ is a 30-day figure and misses intraday seasonality.

### Measured findings: AAA gasoline
- **AAA levels.** The national average was **$4.2892** on 25 Oct (yesterday $4.2957, week ago $4.2988, month ago $4.4918, year ago $3.0591) — [gasprices.aaa.com](https://gasprices.aaa.com/) (cited, read 23:21Z). A 214-day contiguous daily series (26 Mar – 25 Oct 2026) was rebuilt from Kalshi's settled `KXAAAGASD` `expiration_value` (`/trade-api/v2/markets` and `/historical/markets`, 23:2x–23:4xZ). It agrees with the venue's own settlements (Oct 22: 4.2701, venue settled >4.2650 Yes / >4.2750 No). Since 9 Sep: max **$4.4918** (25 Sep), min **$4.2245** (9 Sep). File: `commodities_data/aaa_national_daily_2026-03-26_to_10-25.json`.
- **Daily dynamics.** The mean daily change is +0.14¢ (SD 2.10¢), with lag-1 autocorrelation of changes 0.75 and lag-2 0.45: retail prices are smooth and trending.
  - Walk-forward next-day RMSE over 146 days: no-change 1.85¢; AR(1) on changes 1.32¢; AR(2) + RBOB gap + 7-day RBOB change 1.22¢.
  - Full-sample coefficients: change(t) = 0.0275 + 0.78·change(t−1) − 0.28·change(t−2) + 0.029·(RBOB(t−1) − retail(t−1)) + 0.016·ΔRBOB(7d).
- **Daily ladder vs the market, Oct 21–25.** The informed bids pre-close (bid ≥ 0.79 on the strike just under the realised value, low bids on the next strike up) bracketed the realised value every time:

  | Date | Bid ≥ 0.79 at | Realised AAA | Margin above strike |
  |---|---|---|---|
  | 22 Oct | >4.2650 | 4.2701 | 0.51¢ |
  | 23 Oct | >4.2900 | 4.2926 | 0.26¢ |
  | 24 Oct | >4.2950 | 4.2957 | 0.07¢ |
  | 25 Oct | >4.2850 | 4.2892 | 0.42¢ |

  These bids appeared at 13:42–17:04Z on the day before, soon after AAA's previous-day figure. On 23 Oct the bracket needed a +2.25¢ jump that my AR model priced at about 10%.
  The price-history on these strikes also contains impossible crossed quotes (e.g. "ask 0.80" under a 0.98 bid) — placeholder display prices — so it cannot support a P&L backtest. Data: `commodities_data/pmus_gas_ladders_closed_quote_changes.json`.
- **Live test, pending.** For **26 Oct** at 23:20–23:51Z, the book bid 0.98×196 on >4.2750 and 0.98×101 on >4.2800, and quoted >4.2850 at 0.32–0.34 / 0.41–0.42. It implies a print of about $4.282–4.285. My AR nowcast says $4.2750 (SD 1.22¢): P(>4.275) 0.50, P(>4.280) 0.34, P(>4.285) 0.21. GasBuddy's live state table (23:45Z, population-weighted change −2.18¢/day, median −1.85¢) implies about $4.267–4.275. If AAA prints above $4.28 at 10:00 ET on 26 Oct, the informed bidder has won a fifth night and the nowcasts lost again. (GasBuddy state rows: `commodities_data/gasbuddy_states_2026-10-25T2345Z.json`.)
- **Year-end high/low ladders.** Partial-adjustment model, retail → RBOB + spread, with RBOB as GBM to 31 Dec (67 days). Specs: OLS-fitted (half-life 11.6 days) or fixed spread $0.95–1.10 with half-life 10 days; RBOB volatility 35–60% (OVX is 60). Retail minus 10-day-lagged RBOB averaged $0.87–1.00 by month, Apr–Oct. Prices are size-≥1 quotes from the 23:51Z book:

  | Strike | Model fair (range over 9 specs) | Market bid × size / ask × size | Gap (bid − top of model range) |
  |---|---|---|---|
  | > $4.60 | 0.14–0.32 | 0.43×21 / 0.53×12 | +11¢ |
  | > $4.80 | 0.07–0.21 | 0.40×11 / 0.41×26 | +19¢ |
  | > $5.00 | 0.03–0.15 | 0.26×36, 0.25×118, 0.22×821 / 0.27×3,505 | +11¢ |
  | > $5.20 | 0.01–0.11 | 0.16×97, 0.13×1,548 / 0.18×3,240 | +5¢ |
  | > $5.40 | 0.01–0.08 | 0.11×5,522 / 0.15×3,250 | +3¢ |
  | > $5.60 | 0.00–0.06 | 0.12×37, 0.10×5,037 / 0.13×3,065 | +6¢ |
  | < $4.00 | 0.41–0.69 | 0.26×66 / 0.96×1,077 (dust 0.53/0.54) | inside spread |
  | < $3.80 | 0.20–0.54 | 0.25×20 / 0.46×3,150 | inside |
  | < $3.60 | 0.08–0.40 | 0.13×1,812 / 0.24×245 | inside |
  | < $3.40 | 0.02–0.29 | 0.06×32,352 / 0.08×3,016 | inside |

  Scripts: `commodities_data/scripts/gas_model.py`, `gas_year_alt.py`.

### Measured findings: beef
- **BLS data.** The APU0000703112 September 2026 figure was **$6.792**. August was $6.923; 2026 monthly log changes have SD 1.69% (2023–26: mean +0.75%, SD 1.84%, lag-1 autocorrelation −0.16) — [BLS](https://data.bls.gov/timeseries/APU0000703112) (cited, read 25 Oct). The BLS API returned "daily threshold … reached" on this shared IP.
- **Model.** Simulate October–December from $6.792. Compare driftless (2026 SD) with the 2023–26 drift (+0.75% a month). Prices are size-≥1 bids at 23:51Z:

  | Strike | Fair, driftless | Fair, with drift | Market bid × size / ask × size |
  |---|---|---|---|
  | ≥ $7.00 | 0.19 | 0.46 | 0.98×1.9, 0.97×0.9 / 0.99×5,253 |
  | ≥ $7.10 | 0.08 | 0.27 | 0.17×57 / 0.90 (dust 0.19) |
  | ≥ $7.20 | 0.03 | 0.14 | 0.20×55 / 0.21×61 |
  | ≥ $7.30 | 0.01 | 0.06 | 0.03×269 (dust 0.22) / 0.23×3,359 |
  | ≥ $7.40 | 0.00 | 0.02 | 0.16×1.8 / 0.17×3,336 |
  | ≤ $6.80 | 1.00 (Sep 6.792 qualifies) | 1.00 | 0.99×7,569 / none |
  | ≤ $6.70 | 0.41 | 0.23 | 0.39×46 / 0.40×2 |
  | ≤ $6.60 | 0.19 | 0.09 | 0.29×6 / 0.30×28 |

  The executable edge sits in the stray bids. Selling ≥$7.00 at 0.98 (about 3 contracts), ≥$7.20 at 0.20 (55 contracts) and ≥$7.10 at 0.17 (57) is worth roughly $2–9 of expected value in total, with collateral locked until late January.
- **Release day.** At the 14 Oct 08:30 ET release of September ($6.792, which decided ≤$6.80 as Yes), the ≤$6.80 book stayed 0.45 bid / 0.98 ask from 12:00 to 16:00Z. Other strikes did not move either (`/v1/price-history` custom range, fetched 23:5xZ). By 15 Oct the bid had reached 0.97.

### Inferences
- **Metals.** Whoever makes the 15-minute books prices off the same or a faster feed. Their quotes track a 60-second-lagged Chainlink model to 2¢. If they hedge on COMEX futures, they probably see moves before Chainlink publishes them. A 45-second REST poller has nothing to add except when the outcome is all but settled and a resting offer is left behind.
- **Gas daily.** The bidder behind the 0.98–0.99 bids almost certainly has the station-level data that feeds AAA (AAA publishes OPIS-sourced averages), or an equivalent. Public scrapes (GasBuddy, RBOB) are a step behind.
- **Gas year-end.** The upside tails are bid by a few large resting buyers (5,000+ contract bids at 0.10–0.13), which looks like hedging or a view on an oil shock. In a regime with OVX at 60, Brent above $110 and a spring 2026 price spike (OVX 70.5 on 28 Apr), a GBM can understate jump risk. The 3–19¢ gap is a disagreement about tail risk, not a free lunch.
- **Beef.** These are neglected books. One programmatic maker posts ~3,250-contract offers on many strikes, and retail lifts them. The mispriced mid comes from that maker's offers and a few stray bids, not from a sellable bid stack.

### Gaps
- There is one full metals trading day since launch (23 Oct) plus a few launch-day and Sunday-evening hours, and historical depth at each quote is unknown (price-history stores prices, not sizes).
- The time of day AAA posts its figure was not observed directly.
- I found no news source that confirms why Brent is at $110 (one web search found nothing dated).

## Q3. Settlement-day mechanics: print time, repricing, stale-book windows

### Takeaway
None of the four families leaves a book open after the official value is known:
- **Metals** stop trading at the window end and settle about 1 minute later.
- **The daily gas ladder** closes at midnight ET, before AAA publishes, and settles at about 10:05 ET.
- **Beef** prints at 08:30 ET into a book where the decided side's offer was already 0.98–0.99.

The one stale-book episode was the metals launch day.

### Measured findings
- **Metals.** The last book sample on resolved windows falls a median 58 s after window end (all 238 with a sample: p10 53 s, p90 71 s). `priceToBeat` appears about 1 minute after window start (cited, FAQ), so the first minute trades blind. The worker can read the opening value itself from `/v1/asset-prices/history` at 1 s.
- **Gas daily.** Event `endDate` is 04:00Z; the last quote changes fall at 03:59–04:00Z. Expiry and settlement stamps were 14:05:01–14:05:02Z on Oct 21–25, and 13:17Z for the 30 Sep one-off. The informative moment is the *previous* day's AAA print: decisive bids moved at 13:41–13:47Z on 24 Oct and from 17:04Z on 22 Oct.
- **Gas monthly (Sep).** Expired 30 Sep at 16:27Z (high) and 16:48Z (low).
- **Beef.** On 14 Oct, the ≤$6.80 book was unchanged at 0.45/0.98 for four hours after the release (above).

### Inferences
- A release-time bot is pointless here unless the contracts change. On the evidence of 14 Oct, the next BLS prints (October data, 10 or 12 Nov; sources disagree — [eco3min](https://eco3min.fr/en/next-us-cpi-release/), [therighttrader](https://therighttrader.com/economic-calendar/cpi), read 25 Oct) are unlikely to expose large offers on the side the print decides.

## Q4. Ladder consistency

### Takeaway
No executable monotonicity violation of at least 1 contract exists in any commodities ladder at 23:51Z, and the earlier 23:20Z one was below 1 contract. All crossings are dust (0.01–0.5 contracts). The ladders are internally inconsistent in their mids, but the spread swallows it.

### Measured findings
- **Rule.** For "above" ladders, the bid of a higher strike must not exceed the ask of a lower one ("below" reversed), checked with and without a ≥1-contract filter (`commodities_data/scripts/ladder.py`).
  - **Beef high, 23:51Z.** Three crossings, each under 0.1 contract on one leg (e.g. buy ≥7.10 at 0.19 ×0.0, sell ≥7.30 at 0.22 ×0.0; net +0.7¢). None remain with the ≥1-contract filter.
  - **Gas daily, 23:20Z.** >4.2900 offered 0.10×11 while >4.2950 bid 0.21×0.3: +11¢ gross on 0.3 contracts. Gone by 23:51Z.
- **Non-monotone mids** (no arbitrage after spread): beef ≥7.10 at 0.18, ≥7.20 at 0.205, ≥7.30 at 0.225; gas-low <3.20 and <3.40 both at 0.06/0.07.
- **Joint high/low.** At 23:51Z the gas ladders priced >$4.60 at about 0.48 and <$4.00 at about 0.53 (dust mids; size-≥1 quotes 0.43/0.53 and 0.26/0.96). Every model spec gives P(>4.60) + P(<4.00) between 0.64 and 0.98, against about 1.0 from the dust mids. The market implies a strongly two-way gas distribution (inference).
- **Metals** have no ladders: one market per window, and no above/below or range families (cited, FAQ).

## Ranked strategies

$ figures are expected profit for a $135 account, after fee, under the measured or modelled edge. All are small.

| Rank | Strategy | Verdict | Realistic $ at $135 | What the worker needs | Main risks |
|---|---|---|---|---|---|
| 1 | **Metals 15m late-window certainty**: in the last 2–5 minutes of a gold/silver window, if P(side) ≥ 0.97 on the live Chainlink price, IOC-buy that side at ≤ 0.97 | **Test** (paper for 2 weeks, then $5 orders) | $2–8 a day if the measured +0.8 to +2.9¢ per contract holds at ~10–20 contracts a fill. One loss costs ~$15–19 | New rule module. Poll `/v1/asset-prices/history` (1 s, uncached) every 5–10 s in the final 5 minutes. Read the book over the authenticated Markets WebSocket (REST `/book` is cached 30 s). BUY_LONG / BUY_SHORT IOC with a 0.97 cap. Discover windows by series slug. Metals hours Sun 6:15 PM – Fri 5 PM ET | One full trading day of history (23 Oct); makers will close the gap. Chainlink single-value settlement makes a last-second jump decisive. The 30 s cache makes REST quotes phantom. A loss costs about 30–90 wins |
| 2 | **Gas year-end upside tails**: sell (BUY_SHORT) >$4.80 / >$5.00 / >$5.20 at bids 0.16–0.40 against model fair 0.01–0.21 | **Test, small, manual** | $5–15 once, on $60–100 of collateral locked until mid-January | AAA + RBOB pass-through model (`gas_year_alt.py`), daily refresh, one IOC per strike. No speed needed | Oil-shock tail (OVX 60, Brent above $110). The large tail bidders may be hedgers who know more. 2.5-month capital lock on a $135 account |
| 3 | **Beef stray bids**: sell ≥$7.00 at 0.98, ≥$7.20 at 0.20, ≥$7.10 at 0.17 | **Test, manual, one-off** | $2–9 in total, locked to late January | Nothing automated: a BLS random-walk table and three IOC orders | Beef has drifted up 0.75% a month since 2023. Stray bids may vanish. Thin books |
| 4 | **Gas daily ladder nowcast** (AR + RBOB + GasBuddy scrape) against the 0.98 bids | **Skip** unless the 26 Oct test (Q2) goes the nowcast's way | ~$0 expected. The informed bidder won 4 of 4 nights. Depth 100–200 contracts | AAA history, RBOB, a GasBuddy scrape (check its terms), and an evening order before 00:00 ET | Competing against better data. Placeholder quotes |
| 5 | **Release-time sniping** (BLS beef, AAA print) | **Skip** | $0: books are closed or already at 0.98–0.99 when the value prints | Release feed | None to harvest |
| 6 | **Metals model-gap taking at any time, or resting quotes off Chainlink** | **Skip** | Negative to zero (−6 to +1¢ per contract taker; 1¢ spreads already, no maker rebate below $10M) | Same feed | Adverse selection by makers who see the futures first |
| 7 | **Metals 1h/daily, ladder arbitrage, oil/natgas/ags** | **Skip** | $0: no books (0.99 placeholder offers), no ≥1-contract violations, no such listings | — | — |

Upgrades for this tab, with cost and benefit:
- **Markets WebSocket.** Removes the 30 s edge cache. Needed for rank 1, and costs an API key plus about 200 lines of code.
- **The venue's own uncached 1-second spot endpoint.** Free, and enough for metals; no CME data feed is needed. CME/COMEX real-time data would cost money and would only help a market maker.
- **Resting orders.** No fee at Tier 1, but no case here: metals spreads are 1¢ and the wide gas and beef books are wide because flow is thin.
