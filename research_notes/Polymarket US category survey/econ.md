# Econ tab: the release window is closed, and what is left is mostly rules and tails

**Takeaway.** The post-print whipsaw the prior survey flagged is gone. Since the 2 October jobs report, every BLS ladder on Polymarket US (CPI, core CPI, payrolls, unemployment) has gone to `MARKET_STATE_CLOSED` with its last trade *before* 8:30:00 ET. A BLS release parser would therefore have nothing to trade into, so it should not be built. The FOMC, GDP and foreign central-bank markets still trade after the announcement. On the FOMC they repriced to 0.99/0.01 inside the decision minute, which leaves a crumb of about 0.9¢ per share for roughly ten minutes of capital lock.

Across 255 Econ markets, the model-versus-market gaps either match Kalshi tick for tick or depend on how the model is specified. The ladder "violations" are all 0.01-share dust. The edges that survive are small, rule- and tail-driven, and mostly one-off:

- **October CPI year-on-year has no October figure.** BLS has said it will not publish October 2026 12-month changes because October 2025 was never collected. Several October YoY legs are therefore priced against an outcome the contract's own fallback (September's 3.7% headline / 2.6% core) mostly decides already, worth about **$5–7 once**.
- **Floor-tick Fed and unemployment longshots.** "Fed cut in 2026" is bid at 7¢ against a leg-implied 1–3%. Buying the No sides pays about **$3 over 11 weeks** on $75.
- **The FOMC post-decision 0.99 sweep** is worth about **$1 per meeting**.

Realistic total for a $135 account over the next 60 days: **$8–12**, nearly all one-offs.

Labels used throughout:
- **[M]** = measured (endpoint and UTC time given).
- **[C]** = cited (URL and date).
- **[I]** = inference.

All gateway reads were unauthenticated, public and paced at ≤2 req/s. Raw data and scripts are in `econ_data/` beside this note.

---

## 1. Today's Econ listing

**Scope.** The Econ tab is the tag `economics` (label "Econ"). [M] `GET /v1/events?closed=false&limit=500` (10 pages, 2026-10-25 23:16Z) returned 4,861 open events, 50 of them tagged `economics`, and `closed=true&tagSlug=economics` returned 51 closed ones.

Of the 50 open events:
- 39 are category `macro`.
- 11 are `finance` or `politics` side-bets (IPO confirmations, CEO departures, Musk net worth, Powell/Cook tenure).
- Gas and beef (6 events) belong to the commodities agent and are excluded below.

**Fee, tick and depth convention.** Every one of the 255 non-commodity Econ markets has `feeCoefficient` 0.0695 and `orderPriceMinTickSize` 0.01 [M]. The CPIC rule permits a $0.001 tick, but no Econ market uses one [C: [CPIC rules](https://www.polymarketexchange.com/files/products/PMUS%20-%20CPIC%20-%20(2026.04.06).pdf)].

Quotes below are the best level with at least 5 shares, from `/v1/markets/{slug}/book` read 23:17–23:21Z and re-read 23:41–23:43Z [M]. **Traded** = lifetime `sharesTraded`.

### Wording, source and settlement by family

| Family (slugs) | Exact wording | Release / vintage | Settlement observed |
|---|---|---|---|
| FOMC decision: `usfed-fomc-2026-10-28`, `-12-09` | 5 buckets: 50+ cut / 25 cut / no change / 25 hike / 50+ hike, on the **upper bound**. Off-grid moves round to the nearest displayed option, halves away from zero. | Fed statement, 2:00 pm ET | Sep 16 resolved 18:11Z; Jul 29 18:29Z; Jun 17 20:34Z [M] |
| Fed yearly: `usfed-2026` (cut), `usfed-hike2` (another hike), `fed-gt25bps` (single cut >25bp), `fedfnds-ondt-2027` (≥X% on 31 Dec 2027) | Hike/cut counts "between Contract Issuance and December 31, 2026, 11:59 PM ET", including emergency meetings. `hike2` was issued 22 Sep, after the 16 Sep hike. | Federal Reserve | Settle about 15 Jan 2027 |
| CPI ladders: `uscpi-october-yoy`, `-mom`, `uscpicore-october-yoy`, `-mom` | **"above X%"** (strict). YoY is "before seasonal adjustment"; MoM is seasonally adjusted. Uses the BLS one-decimal figure from the initial release; revisions ignored. | BLS CPI, 10 Nov 8:30 ET | Sep CPI resolved 14:55Z, 2h25m after release [M] |
| Jobs: `usnfp-sa-october`, `usunemp-sa-october` | **"above X"** (strict). Payrolls "change in total nonfarm"; U-3 SA rate. | BLS Employment Situation, 6 Nov 8:30 ET | Sep report resolved 14:35Z (NFP) and 16:21Z (U-3) [M] |
| Unemployment range: `usunemp-sa-hi-yr` (≥X), `-lw-yr` (≤X) | Inclusive. Any monthly print Oct–Dec 2026, first-published. | BLS (Nov 6, Dec 4, Jan 8) | About 23 Jan 2027 |
| GDP: `us-saa-q3-2026-10-29` | **"above X%"** SAAR real GDP, advance estimate only. | BEA, 29 Oct 8:30 ET [C: [BEA schedule](https://www.bea.gov/news/schedule), read 2026-10-25] | Q2 resolved 4h after release [M] |
| Mortgage: `usmort30-hi-yr` (≥X), `-lw-yr` (≤X) | "Any weekly 30-Year FRM average released by Freddie Mac **after Contract Issuance**" (markets created 9 Oct), first-published. | Freddie Mac PMMS, Thursdays at noon ET | About 15 Jan 2027 |
| Foreign central banks: `boc-10-28`, `ecb-10-29`, `boj-10-30`, `bcb-11-04`, `boe-11-05`; `cut-by`/`hike-by-2026-12-31` sets | Same 5-bucket rounding rule. ECB uses the deposit facility rate. | Each central bank | Hours after the decision |
| Long-dated: `usdebt-hi-2027`, `ustariff-fy2027`, `uscompl-2026`, `usnim-2026`, `ussnap-40m`, `usrealwage`, `usunion`, `usrx`/`usrentcpi-fall-2027` | ≥ thresholds or Yes/No, all on first-published figures. | Treasury, Census, USDA, BLS | 2027–28 |

**Strict versus inclusive in practice.** The CPIC rulebook's generic example reads "at or above the specified threshold", but every listed contract says "above". The venue has settled strictly every time a print landed on a threshold [M]:

| Release | Print (derived from BLS index or level) | Contract on the threshold | Settled |
|---|---|---|---|
| Sep CPI YoY | 336.940/324.800 → 3.74% → **3.7** | ">3.7%" | No |
| Sep core YoY | 339.287/330.804 → 2.56% → **2.6** | ">2.6%" | No |
| Sep CPI MoM | 336.298/334.131 → **0.6** | ">0.6%" | No |
| Sep U-3 | 7,109/170,262 → 4.175% → **4.2** | ">4.2%" | No |
| Aug U-3 | **4.1** | ">4.1%" | No |
| Sep NFP | 159,044 − 159,015 = **+29k** | ">50k" | No |

Index and level sources: [BLS API](https://api.bls.gov/publicAPI/v2/timeseries/data/) read 2026-10-25 23:2xZ, and [FRED](https://fred.stlouisfed.org/graph/fredgraph.csv?id=UNEMPLOY). Wording has drifted over time: May–July listings said "at least X" or "exactly X" (inclusive), and current ones say "above X" (strict).

**Slugs can lie.** In the July CPI event, `...-gt4pt2pct` was titled and described as "Above 3.4%" and settled **0.5/0.5** [M: closed listing]. A parser must read the threshold from `description`, never from the slug.

### Quotes, depth and volume (2026-10-25 23:17–23:43Z) [M]

| Market | Bid × size | Ask × size | Traded (shares) | Read |
|---|---|---|---|---|
| FOMC Oct: no change | 0.93 × 12,141 | 0.94 × 8,907 | 7.19M ($4.35M) | Deep, 1¢ |
| FOMC Oct: +25 | 0.05 × 63,490 | 0.07 × 5,074 | 5.31M | |
| FOMC Oct: −25, ±50 | none | 0.01 × 19k–615k | 3.7–5.3M each | Floor tick |
| FOMC Dec: +25 / no change / +50 | 0.73 / 0.23 / 0.03 | 0.74 / 0.24 / 0.04 | 0.37M / 0.90M / 0.33M | 1¢ |
| Another hike 2026 | 0.74 × 6,152 | 0.75 × 2,062 | 835k | |
| Cut in 2026 | 0.07 × 5,639 | 0.08 × 2,969 | 5.47M | |
| Cut >25bp by Dec 31 | 0.03 × 56,243 | 0.04 × 137 | 168k | |
| GDP Q3 >1.5 / >2.0 / >2.5 | 0.96 / 0.89 / 0.79 | 0.97 / 0.90 / 0.80 | 131k / 161k / 259k | Hundreds to thousands of shares |
| U-3 Oct >4.0 / >4.1 / >4.2 / >4.3 | 0.93 / 0.70 / 0.33 / 0.07 | 0.94 / 0.71 / 0.34 / 0.08 | 11k / 21k / 13k / 5k | 7–1,400 shares at the touch |
| NFP Oct >0 / >50k / >100k / >150k | 0.85 / 0.58 / 0.28 / 0.06 | 0.86 / 0.59 / 0.29 / 0.07 | 18k / 4.6k / 8.5k / 5.2k | 29–154 shares at the touch |
| CPI MoM Oct >0.1 / >0.2 / >0.3 / >0.4 | 0.90 / 0.65 / 0.24 / 0.07 | 0.91 / 0.66 / 0.25 / 0.08 | 0.5k–1.8k | |
| Core MoM Oct >0.0 / >0.1 / >0.2 / >0.3 | 0.94 / 0.74 / 0.41 / 0.16 | 0.95 / 0.75 / 0.42 / 0.17 | 85–416 | 6–765 shares |
| CPI YoY Oct (12 legs) | mostly 0.01–0.02 × 250 | mostly 0.98 × 250 | 65–1,046 | Placeholder book |
| Core YoY Oct (15 legs) | mostly 0.01–0.02 × 250 | mostly 0.98 × 250 | 0–402 | Placeholder book |
| Mortgage ≥7.50 / ≥8.00; ≤7.00 | 0.29 / 0.08; 0.58 × 5 | 0.99 / 0.09; 0.60 × 21 | 43 / 9,038; 65 | Other legs 0.02/0.98 placeholders |
| ECB no change; BoC +25; BoE +25; BoJ no change | 0.98; 0.79; 0.95; 0.96 | 0.99; 0.82; 0.98; 0.97 | 1–289k | Tens to hundreds of shares |

The **0.02/0.98 × 250 placeholder** books are someone quoting both extremes with no view. They sit on most CPI YoY, core YoY, mortgage, Fed-funds-2027 and central-bank-set legs, and carry no information.

**Dust orders.** 0.01-share offers at off-market prices sit at the top of many thin books. Examples: core YoY >3.0% ask 0.06 × **0.01** shares; CPI YoY >3.6% ask 0.71 × 0.01. `/bbo` reports these as `bestAsk` [M: [core >3.0 bbo](https://gateway.polymarket.us/v1/markets/cpic-uscpicore-october-yoy-2026-11-10-gt3pt0pct/bbo) vs `/book`, 23:16Z]. A worker that trusts `/bbo` will see phantom arbitrage. It must read `/book` and require a minimum size.

---

## 2. Model fair value

**Method.** For each family, turn the model into ladder probabilities. A threshold "> k" on a one-decimal print means the unrounded value is ≥ k + 0.05. Then compute the after-fee EV of buying Yes at the ask or No at 1 − bid.

### FOMC 28 Oct: no gap

| Source | No change | +25 |
|---|---|---|
| PMUS [M 23:17Z] | 0.93/0.94 | 0.05/0.07 |
| Kalshi `KXFEDDECISION-26OCT` [M, [orderbook API](https://api.elections.kalshi.com/trade-api/v2/events?series_ticker=KXFEDDECISION) 23:3xZ] | 0.92/0.93 | 0.06/0.08 |
| CME FedWatch [C: [Yardeni](https://yardeniquicktakes.com/economic-week-ahead-october-26-30), [Seoul Economic Daily](https://en.sedaily.com/international/2026/10/26/us-economists-see-fed-holding-rates-on-the-28th-hiking-in), 23–26 Oct] | 90–92% | 8–9% |

Reuters' poll had 94 of 100 economists for a hold. The current target range is 3.75–4.00%, after a 16 September hike. Kalshi's `KXFED-26OCT` ">4.00%" at 0.07/0.08 agrees.

FedWatch's 8–9% hike reading is the usual futures-implied overstatement of a small move: risk premium plus the methodology. A Fed study found Kalshi's macro expectations at least as accurate as the alternatives [C: [Motley Fool on the Fed paper](https://fool.com/investing/2026/03/16/federal-reserve-research-kalshi-prediction-markets)]. Buying PMUS +25 at 0.07 against a 0.08–0.09 FedWatch figure is worth +0.5–1.5¢ before a 0.45¢ fee.

Over 14 days of hourly closes, PMUS and Kalshi had a median mid gap of 0.0¢ on both Oct no-change and +25, with |gap| ≥ 2¢ in 4–6% of hours [M: `pmus_kalshi_hourly_14d.json.gz`].

### Dec FOMC and the yearly Fed contracts: one live gap and two floor-tick tails

**Dec FOMC.** PMUS +25 at 0.73/0.74 and no change at 0.23/0.24 match Kalshi's 0.74/0.75 and 0.23/0.24 (median gap −1.0¢ and 0.0¢). FedWatch has a December hike at 76–84% [C, same sources].

**"Another Fed hike in 2026" (`usfed-hike2`), 0.74/0.75 [M]. Live gap, 2 days old.**
- Any December hike implies this contract pays, so P(another hike) ≥ P(Dec hike). PMUS's own December hike bids sum to 0.73 + 0.03 = **0.76**, above the 0.75 ask.
- Adding the October hike path, P ≈ 0.06 + 0.94 × P(Dec hike | no Oct hike) ≈ **0.79–0.81** [I].
- That is 4–6¢ of edge after the 1.3¢ fee. It is not an arbitrage: the hedge legs cost more than $1 after fees.
- It is not persistent either. Over 797 hourly points since 22 Sep the hike2 ask sat a median **7¢ above** the December-hike bid sum, and crossed below it only on 24–25 Oct [M: `fed_legs_hourly.json.gz`].
- Verdict: a directional one-clip trade with a 23% chance of losing 75¢.

**"Fed cut in 2026" (`usfed-2026`), bid 0.07 × 5,639.**
- The only paths are the Oct and Dec meetings, whose cut legs sit at the 0.01 floor (Dec −25 at 0.01/0.02), or an emergency cut by a Fed that is hiking.
- Fair is about 2% [I], with FedWatch's December cut near 1% [C].
- Buy No at 0.93 → **+4–5¢ per share**, locked about 11.5 weeks.

**"Cut >25bp by Dec 31" (`fed-gt25bps`), bid 0.03 × 56k.** Buy No at 0.97 → about **+2.5¢**.

### CPI and core CPI MoM (Cleveland Fed nowcast)

**Model.** Cleveland Fed nowcast for October as of 23 Oct: CPI MoM **0.253**, core **0.211**. Its October YoY nowcasts are 3.75% headline and 2.48% core [M: [nowcast_month.json](https://www.clevelandfed.org/-/media/files/webcharts/inflationnowcasting/nowcast_month.json), read 2026-10-25 23:3xZ].

**Error distribution.** I backtested the nowcast's last value before each release against the actual print, 2013–2026, n = 157 [M: `cleveland_nowcast_mom_backtest.json`]:

| Window | Headline RMSE | Core RMSE |
|---|---|---|
| Last 36 months | 0.112 | 0.111 |
| Last 60 months | 0.167 | 0.135 |

The tails are fat: −0.36 in June 2026, +0.19 in April. The last two core prints beat the nowcast by +0.09 and +0.13.

**Ladder probabilities** (empirical 36- and 60-month errors, normal with SD 0.12):

| Threshold | PMUS | Kalshi | Model P(Yes) | Model says |
|---|---|---|---|---|
| CPI >0.1 | 0.90/0.91 | 0.89/0.90 | 0.77–0.92 | No +0 to +13¢ |
| CPI >0.2 | 0.65/0.66 | 0.61/0.66 | 0.51–0.64 | No +1 to +12¢ |
| CPI >0.3 | 0.24/0.25 | 0.22/0.23 | 0.17–0.21 | No +3 to +6¢ |
| Core >0.1 | 0.74/0.75 | 0.75/0.76 | 0.70–0.78 | ±3¢ |
| Core >0.2 | 0.41/0.42 | 0.39/0.40 | 0.31–0.37 | No +2 to +8¢ |
| Core >0.3 | 0.16/0.17 | 0.16/0.17 | 0.06–0.12 | No +3 to +8¢ |

**Reading.** The nowcast-based model says both venues are 2–10¢ rich on the upper legs, so the side would be No. But:
- The gap is against **both** venues, not PMUS alone.
- Its size changes with the error window chosen.
- The core nowcast is a known laggard that the last two prints beat.
- Validating it would take years at one release a month.

Verdict: paper-track only. This is a model disagreement, not a venue mispricing. Consensus forecasts for October CPI do not exist yet; they form in the week before 10 Nov.

### Unemployment and NFP (random walk on the unrounded rate)

**Unemployment.** September's unrounded U-3 was 7,109/170,262 = **4.175%**, so it printed at the low edge of 4.2 [M: [FRED UNEMPLOY/CLF16OV](https://fred.stlouisfed.org/graph/fredgraph.csv?id=UNEMPLOY), 23:5xZ]. Monthly changes of the unrounded rate (2012–19 and 2022–26, n = 150) have SD 0.116.

| Threshold | PMUS | Kalshi | Model, no drift | Model, +0.04/month drift (Jul–Sep trend) |
|---|---|---|---|---|
| >4.1 | 0.70/0.71 | 0.68/0.72 | 0.53 | ≈0.68 |
| >4.2 | 0.33/0.34 | 0.32/0.34 | 0.20 | ≈0.30 |

The "edge" (No +12–16¢) disappears once the trend is included. Both venues price the trend, so the gap comes from the model choice rather than the market.

**NFP.** The PMUS ladder implies a median of about 55k and an SD of about 52–79k. NFP deviations from the trailing three-month average had **SD 99k** in 2023–26 [M]. A wider distribution says the tails are cheap:

| Leg | PMUS ask | Model (mean 55k, SD 80k) |
|---|---|---|
| ">150k" Yes | 0.07 | ≈0.12 |
| ">−50k" No | 0.04 | ≈0.10 |

That is +4–5¢ per leg, but it rests on one dispersion assumption, on books 25–350 shares deep. Kalshi has the same shape (T125000 at 0.12/0.17).

Verdict: paper-track. The sample to test against is 4 PMUS releases.

### GDP Q3 (29 Oct): no gap

**Model inputs:**
- GDPNow 3.5% (20 Oct; next update 27 Oct) [C: [Atlanta Fed commentaries](https://www.atlantafed.org/research-and-data/data/gdpnow/current-and-past-gdpnow-commentaries), 2026-10-25].
- NY Fed Staff Nowcast 2.67% (16 Oct) [C, secondary: [fattail.ai preview](https://fattail.ai/q3-gdp-2026-preview/), 22 Oct].
- Continuum Economics 2.8%; SPF 2.5% (August).

**Market.** Kalshi implies a median of about 3.2: >3.0 at 0.63/0.64, >3.5 at 0.28/0.32.

**Model.** A blend centred near 3.0–3.2 with SD about 1.0 gives P(>2.5) ≈ 0.70–0.80 and P(>2.0) ≈ 0.85–0.90. PMUS's 0.79/0.80 and 0.89/0.90 sit inside that range. GDPNow alone (3.5) gives 0.81/0.90, which is exactly the PMUS price.

PMUS ran a median 0.0¢ from Kalshi's GDP legs, and the best one-sided capture against Kalshi's bid was 0.4–0.9¢ [M]. No trade.

**Release-date mismatch.** Kalshi's market closes 30 Oct 12:29Z, while BEA's release is 29 Oct [M/C]. That is Kalshi's problem, not a PMUS edge.

### Mortgage rates (PMMS and MND)

**Inputs:**
- PMMS releases since issuance: 7.40 (15 Oct) and 7.32 (22 Oct). The year's high after issuance is therefore 7.40 [M: [FRED MORTGAGE30US](https://fred.stlouisfed.org/graph/fredgraph.csv?id=MORTGAGE30US)].
- MND daily: 7.33% on 23 Oct [C: [Mortgage News Daily](https://www.mortgagenewsdaily.com/mortgage-rates), 2026-10-25].
- 10-year Treasury: 4.96% on 22 Oct, down 17bp in a day [M: FRED DGS10].

**Model.** Weekly PMMS moves have an SD of roughly 0.10, so over ten weekly prints the reflection-principle touch probabilities are [I]:

| Leg | PMUS | Model touch probability | Trade |
|---|---|---|---|
| ≤7.00 | 0.58/0.60 | ≈0.28–0.33 | Buy No at 0.42 → +25¢, but only **5 shares** bid |
| ≥8.00 | 0.08/0.09 | ≈0.03–0.05 | Buy No at 0.92 → +3¢, on 35 shares |
| ≤7.30 | placeholder | ≈0.65+ | Unbuyable: ask 0.99 |

Capacity is under $10 in total; the books are too thin to trade.

### Persistence and side

**Where the gaps exist, they all point the same way: buy No on the near-impossible tail.** That covers the cut-in-2026 contract, cut >25bp, unemployment ≤3.6% (bid 0.06 × 1,000 while U-3 sits at 4.2 and rising), mortgage ≥8.00, and the NFP and CPI upper legs under the models above. This is the 1¢ floor tick plus a longshot bias on thin books. Kalshi shows the same pattern, so a one-sided PMUS buyer is harvesting the bias itself, not a lag at one venue.

Only the Fed-cut tails and unemployment ≤3.6 are model-robust: their fair value is near 0 under any reasonable model.

---

## 3. Release-time execution

**Measurement.** 1-minute book-derived history around 31 past releases [M: `/v1/price-history?symbol=…&timestamp.startTimestamp=…&fidelity=1`, pulled 23:25–23:30Z]. Per the docs, `longPrice` is the Yes display price from the best ask, and `shortPrice` is 1 − best bid [C: [price-history docs](https://docs.polymarket.us/api-reference/price-history/get-price-history.md)]. The window ran from release −120 to +240 minutes.

I also read each closed market's `state` and `lastTradeSetTime` from `/book` [M: `closed_econ_market_states.json`].

### BLS markets now close at the print

| Release | Market state | Last trade relative to 8:30:00 ET | Trading after print? |
|---|---|---|---|
| Jul jobs (Aug 7) | EXPIRED | +87 min | Yes |
| Jul CPI (Aug 12) | EXPIRED | +111 min | Yes |
| Aug jobs (Sep 4) | EXPIRED | +243 to +316 min | Yes |
| Aug CPI (Sep 11) | EXPIRED | +165 min | Yes |
| **Sep jobs (Oct 2)** | **CLOSED** | **−24 to −54 min** | **No** |
| **Sep CPI, core, MoM (Oct 14)** | **CLOSED** | **−0.7 to −12 min** | **No** |
| FOMC Jul 29 / Sep 16 | EXPIRED | +27 / +11 min | Yes |
| GDP Q2 (Jul 30) | EXPIRED | +231 min | Yes |
| BoI Oct 21 / CBR Oct 23 | EXPIRED | +5.5 / +51 min | Yes |

On 14 Oct, the book froze at its 12:30Z state for good. CPI YoY ">3.6%", which settled **Yes**, still shows a Yes ask of **0.47** eleven days later. That can only be a closed market, not an unattended one.

The docs only say "trading may be paused without prior notice" [C: [Trading Hours](https://docs.polymarket.us/learn/trading/access-and-limits/trading-hours.md)]. The CPIC rule's last-trading time is still 11:59:59 PM ET on expiration day [C: CPIC rules]. So this is a **practice, not a published rule**. It may be keyed to `gameStartTime`, which equals the release time on the upcoming Nov 6 and Nov 10 markets [I]. Kalshi likewise closes its data markets one minute before the release (13:29Z for CPI and jobs, 17:59Z for FOMC) [M: Kalshi `close_time`].

### The windows that used to exist (now closed for BLS)

Each entry is the winning side's ask from +1 minute onward [M: `post_release_windows.txt`]. Depth is not on the tape: history is top-of-book only, and the prior survey saw "a few thousand shares" in these ladders.

- **June CPI, 14 Jul (printed 3.5%).**
  - ">3.6%" No ask 0.26 at +1 to +3 min (73¢ edge).
  - ">3.8%" No ≤0.61 at +6 to +23 min.
  - ">3.9%" No 0.89 for 18 min.
- **July CPI, 12 Aug (printed exactly 3.4%) — the strict-versus-inclusive trap.** On "Above 3.4%" the Yes bid rose from 0.16 to 0.63–0.68 at +2 to +4 min, then printed **0.99 at +5 min** before collapsing at +6. Buyers were treating 3.4 as satisfying "above 3.4". A strict-semantics parser could have bought No at 0.32–0.37 for several minutes, about 60¢ edge.
- **August CPI, 11 Sep.** ">3.3%" (settled Yes) ask 0.81 for 36 min; ">3.4%" No 0.89 for 16 min.
- **August jobs, 4 Sep.** U-3 ">4.1%" No 0.35, intermittently over the following 4 hours (67 minutes in total); NFP ">100k" (settled Yes) ask 0.41 for most of four hours.

### Still open after the release: FOMC, GDP, foreign central banks

- **FOMC.**
  - Sep 16: +25 went 0.89 → **0.99** in the 18:00 minute and No change 0.23 → 0.01.
  - Jul 29: No change 0.83 → 0.99.
  - The winner's ask then sat at **0.99** until resolution, 11–29 min later. The last trade on Sep 16 +25 was at 0.99, 18:10:06Z [M].
  - The tape shows nothing cheaper than 0.99 after the minute. The crumb is 1 − 0.99 − 0.07¢ fee = **0.93¢ per share** for about ten minutes of capital.
- **GDP Q2.** ">2.0%" (settled No) went from 0.96 to 0.06 inside the release minute, and nothing ≤0.97 survived past +1 min [M].
- **Foreign central banks.** Books of tens to a few thousand shares. BoE Sep ">25 hike" No 0.95 for about 170 min and CBR Oct "−25" No 0.92 are 1–5¢ crumbs on hundreds of shares.

### Can a parser take these windows?

**BLS.** No: there is nothing to trade into.
- Releases go out at 8:30:00 ET. The keyless BLS API refused service after 3 requests from this shared IP ("daily threshold … reached") [M, 23:5xZ], and FRED's CSV was available instead [M]; neither matters once the market is closed.
- Both semantics are now confirmed strict in settlement, so if PMUS ever reopens post-release trading, the July-style "3.4 is not above 3.4" error is the specific trade to be ready for.

**FOMC.** A parser does not need to beat the venue: the venue's own 0.99/0.01 consensus forms inside the minute. The value is the 0.93¢ settlement yield. The worker needs:
- an 18:00:00 trigger;
- a `/book` read: the public `/bbo` is 30-second cached, so a sub-minute read requires the authenticated WebSocket;
- a two-sided agreement check.

**GDP (29 Oct, 8:30 ET).** Unknown whether PMUS will close it at the print. The event's `gameStartTime` is a stale 31 Jul, so a `gameStartTime`-keyed close would not apply [I]. The Q2 reprice finished inside one minute, which is too fast for a 45-second poller.

### Next 60 days of releases with attached PMUS markets

See the calendar at the end of the note.

---

## 4. Ladder monotonicity and bucket sums

**Scan.** Every "above" ladder (CPI ×4, U-3, NFP, GDP), every ≥ ladder (mortgage-high, unemployment-high, debt, tariff, completions, migration, Fed funds 2027) and every ≤ ladder (mortgage-low, unemployment-low) was scanned for

  bid(less-likely leg) > ask(more-likely leg) + both fees,

walking `/book` levels for executable depth. The six central-bank bucket sets were checked for Σask < 1 and Σbid > 1. Two snapshots were taken, 23:17Z and 23:43Z [M: `scan_snapshot2.txt`].

**Result: zero survivors.**
- The scan flagged 11 "violations" in each snapshot (CPI YoY, core YoY, core MoM, tariff). Every one had **0.01–0.03 shares** of executable size, i.e. dust orders, worth $0.00.
- Bucket sums:

| Meeting | Σ ask | Σ bid |
|---|---|---|
| FOMC Oct | 1.04 | 0.98 |
| FOMC Dec | 1.05 | 1.00 |
| ECB | 1.04 | 0.99 |
| BoC | 1.03 | 0.98 |
| BoJ | 1.07 | 0.97 |
| BoE | 1.13 | 0.97 |

  No Dutch book.

**Cross-family checks:**
- Another hike vs Dec legs: 1¢ gross inversion, negative after fees (see §2).
- Cut-2026 vs cut legs: consistent.
- Unemployment hi/lo-yr vs Oct legs: consistent.

The prior survey's core-CPI ">2.9 / >3.0" inversion is gone: >2.9 ask 0.14 × 23, >3.0 bid 0.01 × 7,600.

---

## 5. Cross-venue gaps against Kalshi

**Coverage.** Kalshi lists the same October jobs, CPI MoM, core MoM, GDP and FOMC events. It does **not** list October CPI YoY or core YoY: its YoY series start at November [M: [Kalshi events API](https://api.elections.kalshi.com/trade-api/v2/events?series_ticker=KXCPIYOY), 23:3xZ]. That is consistent with BLS not publishing an October YoY figure (§6).

**14 days of hourly closes, 14 matched pairs** [M: Kalshi candlesticks and PMUS `fidelity=60` history]:
- Median mid gap: 0.0¢ (FOMC Oct, Dec no change, NFP 50k, GDP) up to +1.0¢ (U-3 >4.2) and +2.0¢ (CPI >0.3).
- A one-sided PMUS buy beat Kalshi's opposite quote plus fee in 0–27% of hours.
- The median edge when positive was **0.2–0.5¢**, rising to 1.4–2.3¢ only on the thin CPI MoM legs, in runs of a median 1.5–6 hours.
- Typical PMUS depth at those prices is tens to hundreds of shares.

At $25 per clip this is cents per hit. It matches the prior survey: same-minute tracking, nothing persistent.

The one persistent difference is the GDP release date (Kalshi 30 Oct, BEA 29 Oct). It is not tradeable.

---

## 6. The rule-driven trade: October CPI year-on-year has no October figure

**What BLS has said** [C: [BLS shutdown FAQ, Q16](https://www.bls.gov/cpi/additional-resources/2025-federal-government-shutdown-impact-cpi-faq.htm), last modified 2026-09-16, read 2026-10-25 23:3xZ]:

> "For most CPI series, BLS could not publish October 2025 indexes. As a result, BLS will not publish 12-month percent changes for October 2026 for indexes where October 2025 data are not available."

BLS also "will not publish an all items or an all items less food and energy estimate for October 2025". The BLS API shows `2025 M10 '-'` for CUUR0000SA0 and CUUR0000SA0L1E [M].

**What the contract says.** `uscpi-october-yoy` and `uscpicore-october-yoy` were listed on 16 Oct, after the FAQ. Their terms say:

> "If the BLS does not publish CPI YoY for October 2026 on the scheduled release date, the first figure officially published … will be used. If no qualifying figure is published within three months … this market will resolve based on data from the most recent previous month with available data."

That points to **September 2026: headline 3.7%, core 2.6%**. The CPIC rulebook alternatively allows "last fair market prices or … Contract Outcome Review" if data are "indefinitely delayed or cancel[led]" [C: CPIC rules].

**Legs that settle the same way under every interpretation** [I]. Three readings are possible:
- (a) the fallback to September (3.7 / 2.6);
- (b) the Cleveland-style October YoY nowcast (3.75 / 2.48);
- (c) a geometric-mean imputation of October 2025 (≈3.9–4.0 / ≈2.8, my estimate).

These legs come out the same under all three:
- headline ">3.2…>3.6%" → Yes;
- headline ">4.1%" → No;
- core ">2.3%, >2.4%" → Yes.

**Executable now** [M 23:43Z book]:

| Leg | Buy | Size | Edge | EV |
|---|---|---|---|---|
| Headline >4.1 | No at 0.92 / 0.93 | 48 / 9 shares | | $4.21 |
| Headline >3.6 | Yes at 0.96 | 23 shares | 3.7¢ | $0.88 |
| Headline >3.5 | Yes at 0.92 | 5 shares | | $0.38 |
| Core >2.4 | Yes at 0.96 | 14 shares | | $0.54 |
| Headline >3.2 | Yes at 0.66 | 2.4 shares | | $0.80 |

Total: about **$6–7 EV on about $95**. Beyond that, roughly 2,500 shares per leg are offered at the 0.98–0.99 placeholders, worth about 1–2¢ each.

**Risks:**
- PMUS settles at last fair market price instead. The loss would be small, since these legs are bought near their current mids.
- Capital is locked up to about 10 Feb 2027 if the three-month clause runs its course.

**Do first:** ask PMUS support in writing how these two events will settle.

---

## 7. Build spec: an FOMC and rate-decision settlement sweep (not a BLS parser)

A full release parser does not clear the bar. BLS markets close at the print; FOMC and GDP reprice inside the release minute. What does clear it, barely, is a narrow extension of the settlement-yield rule the prior survey already recommends. Cost is about one day of work; benefit about $1 per FOMC and cents per foreign central bank.

**Trigger.** A scheduled clock event at decision time plus 30 seconds:

| Event | Decision time (UTC) |
|---|---|
| FOMC Oct 28 | 18:00:00 |
| FOMC Dec 9 | 19:00:00 |
| BoC | 13:45 |
| ECB | 13:15 |
| BoE | 12:00 |

**Confirmation (both required):**
1. Fetch the Fed press release from federalreserve.gov (or its RSS feed) and match the regex `target range for the federal funds rate (at|to) (\d+(?:-\d+/\d+)?) to (\d+(?:-\d+/\d+)?) percent`. Map the change in the upper bound to a bucket using the contract's rounding rule.
2. On PMUS, the matching bucket's best ask is ≤ 0.99 with ≥ N shares, and every other bucket's best Yes bid is ≤ 0.01.

If (1) and (2) disagree, do nothing.

**Data path.** Use the authenticated market WebSocket, or `/book` with no CDN cache. Do not use `/bbo`: its `max-age=30` cache and dust tops make it unusable here [M].

**Orders.**
- `ORDER_INTENT_BUY_LONG` on the winner at 0.99.
- `ORDER_INTENT_BUY_SHORT` (i.e. No at 0.99) on up to four losers.
- IOC, `quantity = min(depth, clip)`, with `feeCoefficient` read per market.
- Cap the whole account at one event at a time.

**Logging.** Fill price, size, and minutes to credited settlement (Sep 16 resolved in 11 min; Jul 29 in 29 min; Jun 17 in 154 min).

**Kill switch.** Abort if the release has not appeared by +5 min, or if any loser's bid is above 0.02.

**Break-even accuracy.** 99.07% at 0.99. The press-release check and the venue's two-sided agreement are what make that safe.

**Two observation-only add-ons:**
- **GDP 29 Oct:** log PMUS GDP legs at 1 Hz over the WebSocket from 12:25–12:40Z to see whether the venue closes at the print.
- **Nov 6 and Nov 10:** confirm the BLS close-at-release practice continues.

If PMUS ever reopens post-release trading on BLS markets, revisit the full parser. Its spec would be:
- an 8:30:00 poll of the bls.gov release page (the keyless BLS API rate-limits shared IPs);
- the threshold parsed from `description`, using strict semantics;
- No-side buys on legs the print has made impossible.

---

## 8. Ranked strategies

| Rank | Strategy | Verdict | Realistic $ at $135 | What the worker needs | Main risks |
|---|---|---|---|---|---|
| 1 | October CPI YoY legs robust to the rule (headline >4.1 No, >3.2–3.6 Yes; core >2.3–2.4 Yes) | **Test**, one-off, after PMUS confirms the settlement treatment | $5–7 once, on about $95 | A static order list from `/book`; BUY_SHORT for the No legs; min-size filter | PMUS uses LFMP or another fallback; capital locked to about Feb 2027; thin depth |
| 2 | Floor-tick Fed and unemployment tail No's (cut-2026 No @0.93, cut>25bp No @0.97, U-3 ≤3.6 No @0.94) | **Test**, small, hold to settlement | About $3 over 11 weeks on $75 | Fixed slug list; buy No ≤ the stated price; per-market `feeCoefficient` | Emergency cut or labour shock; about 11 weeks of lock; longshot bias can persist |
| 3 | FOMC / central-bank post-decision 0.99 sweep | **Build**, as an extension of the settlement-yield rule | $0.5–1.2 per FOMC (2 in the window); cents per foreign central bank | WebSocket or `/book`, Fed release check, two-sided gate, kill switch | Bad parse (−99¢ per share), unseen depth, faster competitors |
| 4 | "Another hike 2026" Yes @≤0.75 against Dec legs ≥0.76 | **Test**, one clip at most, only while ask ≤ Dec bid sum | +$1–1.5 EV per $25, SD about $14 | One cross-family monitor | 23% chance of losing the clip; gap only 2 days old |
| 5 | GDP 29 Oct release behaviour | **Test**, observe only | $0 | 1 Hz WebSocket logger | None; this is information |
| 6 | BLS release parser (CPI, NFP, U-3) | **Skip** | $0: markets close at 8:30 | — | Revisit only if PMUS reopens post-release trading |
| 7 | Model-vs-market ladders (Cleveland CPI, U-3 random walk, NFP tails, GDPNow, PMMS/MND) | **Skip** for trading; paper-track | $0 (paper) | Nowcast feeds, a calibration log | Gaps flip sign with model spec; Kalshi prices the same; one event a month |
| 8 | Ladder monotonicity / bucket sums | **Skip** | $0 today: all hits were dust | `/book` min-size filter (needed anyway to avoid phantom asks) | Dust orders, placeholder books |
| 9 | Cross-venue PMUS vs Kalshi | **Skip** | $0.1–0.5 per hit | Kalshi keyless REST | 0.2–0.5¢ median edge on tens–hundreds of shares |
| 10 | Foreign central-bank pre-decision, mortgage, debt, tariff, long-dated | **Skip** | < $1 | — | 15–97¢ spreads, placeholder books, 2027–28 settlement |

**What to do around the FOMC on 28 October:**
- **Before 18:00Z, nothing.** PMUS 0.93/0.94, Kalshi 0.92/0.93 and FedWatch 90–92% hold all agree.
- **At 18:00–18:10Z, optionally:** if rank 3 is built and the statement and venue agree, buy the decided bucket and the losers' No at 0.99. If not built, stay out: the 45-second poller cannot see a sub-minute book through a 30-second cache.
- **Afterwards:** the Dec legs and `usfed-hike2` will reprice. Re-check rank 4 only after the dust settles.
- **Same day:** BoC at 13:45Z. Its books are 18–5,300 shares and not worth a rule.

---

## 9. Calendar: next 60 days of tradeable releases (26 Oct – 24 Dec 2026)

Times are UTC; US daylight time ends 1 Nov, so 8:30 ET is 12:30Z through Oct and 13:30Z from November. Sources: BLS schedules for [empsit](https://www.bls.gov/schedule/news_release/empsit.htm) and [CPI](https://www.bls.gov/schedule/news_release/cpi.htm), [BEA schedule](https://www.bea.gov/news/schedule), and PMUS event `startTime`/`gameStartTime` [M], read 2026-10-25.

| Date | Time (UTC) | Release | PMUS markets | Post-release trading? |
|---|---|---|---|---|
| Tue 27 Oct | ~16:00 | GDPNow final Q3 update (model input) | — | — |
| Wed 28 Oct | 13:45 | Bank of Canada | `boc-2026-10-28` | Likely yes [I] |
| Wed 28 Oct | 18:00 | **FOMC** | `usfed-fomc-2026-10-28`; also moves `-12-09`, `usfed-hike2`, `usfed-2026`, `fed-gt25bps`, `fedfnds-ondt-2027` | Yes so far (Jul, Sep) |
| Thu 29 Oct | 12:30 | **GDP Q3 advance** + Sept PCE | `us-saa-q3-2026-10-29` | Unknown — observe |
| Thu 29 Oct | 13:15 | ECB | `ecb-2026-10-29` | Likely yes [I] |
| Thu 29 Oct | 16:00 | Freddie Mac PMMS | `usmort30-hi/lw-yr` | n/a (weekly) |
| Fri 30 Oct | ~03:00 | Bank of Japan | `boj-2026-10-30` | Likely yes [I] |
| Wed 4 Nov | ~21:30 | Brazil Copom | `bcb-2026-11-04` | Likely yes [I] |
| Thu 5 Nov | 12:00 | Bank of England | `boe-2026-11-05` | Likely yes [I] |
| Thu 5 Nov | 17:00 | PMMS | `usmort30-*` | n/a |
| Fri 6 Nov | 13:30 | **Employment Situation (Oct)** | `usunemp-sa-october`, `usnfp-sa-october`, `usunemp-sa-hi/lw-yr` | Expect **closed at print** |
| Tue 10 Nov | 13:30 | **CPI (Oct)**; YoY not published by BLS | `uscpi-october-yoy/mom`, `uscpicore-october-yoy/mom` | Expect **closed at print**; YoY legs go to the fallback rule |
| ~Thu 12 Nov | 19:00 | Monthly Treasury Statement (Oct) [I] | `ustariff-fy2027` | n/a |
| 12, 19 Nov; Wed 25 Nov; 3, 10, 17 Dec; ~23 Dec | 17:00 | PMMS weekly (Wed 25 Nov for Thanksgiving [I]) | `usmort30-*` | n/a |
| Wed 25 Nov | 13:30 | PCE (Oct), GDP Q3 second estimate | none listed | — |
| Fri 4 Dec | 13:30 | Employment Situation (Nov) | `usunemp-sa-hi/lw-yr`; a November ladder is likely to be listed [I] | Expect closed |
| Wed 9 Dec | 19:00 | **FOMC** | `usfed-fomc-2026-12-09`, `usfed-hike2`, `usfed-2026`, `fed-gt25bps` | Yes so far |
| Thu 10 Dec | 13:30 | CPI (Nov); YoY published normally | November ladders likely to be listed [I] | Expect closed |
| Daily | — | Treasury Debt to the Penny | `usdebt-hi-2027-12-31` | n/a |

Not yet listed on PMUS and unverified: December meetings of the BoC, ECB, BoE and BoJ.

---

### Files

`econ_data/` (1.2 MB):
- book snapshots: `pmus_econ_books_2026-10-25T2343Z.json`, `pmus_econ_top_of_book_2026-10-25T2317Z.json`;
- closed-market states and 1-minute histories (`.gz`);
- the post-release window table;
- monotonicity scan output;
- contract descriptions;
- the Cleveland nowcast backtest;
- a Kalshi snapshot and 14 days of PMUS–Kalshi hourly history;
- `scripts/` (Python, read-only public endpoints).

No repository code was modified, and no authenticated or order endpoint was called.
