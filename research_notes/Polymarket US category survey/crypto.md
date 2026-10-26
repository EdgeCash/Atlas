# Crypto on Polymarket US: options-priced books with one durable model gap

**Takeaway.** Crypto on Polymarket US (57 events, 1,546 markets, all settled on CF Benchmarks indices) is a bot market whose money is in the BTC 15- and 5-minute up/down windows, which trade **$10–16M a day**. Those windows reprice from exchange feeds within seconds: mid-window, the venue's mid beats a live BRTI-plus-realized-vol model at every horizon, and trading the model's disagreements with 1–5 minutes left loses **2–9¢ per contract**. The automated ladders (hourly, daily and weekly strikes and touches) are quoted by one programmatic maker whose mids sit on the Deribit options surface, and **no quote clears the fee against the options-implied fair value**. Their far-OTM touches are overpriced at the 3–5¢ floor ask, but nobody bids them, so a taker cannot sell. The one robust, persistent, executable gap is in the liquid hand-listed **year-end BTC tails**. "Hit $150k by 31 Dec" bids 0.03–0.04 against a fair value of 0.004–0.007 on every model, "$100k by 30 Nov" bids 0.11 against 0.066–0.081, and "dips to $40k" bids 0.05 against 0.015–0.020. Selling them (buying No) earns **+1.5 to +3.8¢ per contract after the fee (1.6–4.2% of outlay over 1–2 months)**, roughly **$1.5–2 a month** on $135, with a correlated $20–40 tail if BTC moves ±40–50%. Everything else is Skip. That includes a deep-in-the-money hourly-ladder rule that showed +6.4¢ on the price tape but came mostly from one-sided books' fabricated display prices, with no discount in a live hour.

Labels used throughout: **[M]** measured (endpoint and UTC time given), **[C]** cited (URL, date), **[I]** inference. Scripts, raw pulls and outputs are in `/tmp/claude-0/-home-user-Atlas/edbc1613-2236-53ad-a912-f62e839307df/scratchpad/crypto/`, and a small copy of the outputs is in `crypto_data/` beside this note. Nothing was authenticated, no order was placed and no repository code was modified. Gateway traffic stayed at or below 2 requests per second.

---

## Q1. Today's crypto listing: families, settlement, fees, depth

**Settlement.** [C] Every automated market settles on a CF Benchmarks real-time index: BRTI for BTC and `ETHUSD_RTI`, `SOLUSD_RTI` and `XRPUSD_RTI` for the others (`assetPriceTerms.indexSymbol` in the gateway listing). The statistic depends on the family ([Crypto FAQs](https://docs.polymarket.us/faqs/crypto-faqs.md), read 25 Oct 2026):

- **Up/Down, Above/Below and Range:** the simple average of the 60 one-second index prints in `[T−60 s, T)`, rounded to two decimals.
- **One-Touch:** a rolling 60-second, 20% trimmed mean, monitored continuously. It can settle Yes early.
- **Hand-listed year-end markets:** the same trimmed-mean touch, or a trimmed mean over the 60 seconds ending at 12:00 AM ET on 1 January 2027 for the range buckets.
- **Ties:** a flat up/down window settles Up, and a print exactly at the strike settles Yes.
- **Settlement timing:** "typically within a minute" for up/down and "within about fifteen minutes" for ladders. Settlement is deferred if the index data is incomplete.

[M] The index is public and needs no key: `GET gateway.polymarket.us/v1/asset-prices/history?assets=crypto:btc&bucket=ASSET_PRICE_BUCKET_1S`, returning up to 3,600 candles per call, not edge-cached (`cf-cache-status: DYNAMIC`) and current to the second at 00:05Z on 26 Oct. Averaging its 5-second closes over each settlement minute reproduced the stamped `settlementPrice` of 721 BTC 15-minute windows within a median of −$0.02 (p5/p95 ±$1.7).

**Fee and tick.** [M] `feeCoefficient` = 0.0695 on all 1,546 crypto markets (taker fee 0.0695·p·(1−p) per contract), with a tick of 0.01 and a minimum quantity of 0.01 on every market ([listing](https://gateway.polymarket.us/v1/events?closed=false&limit=500&offset=0&categories=crypto), 25 Oct 23:20Z). [C] Since 19 Oct, makers below $10M of monthly maker volume pay no fee and get no rebate. Crypto makers had received an extra 17% weekly maker rebate until 15 Oct ([Changelog, 12 Oct 2026 entry](https://docs.polymarket.us/changelog.md)). Fees are rounded per fill to the cent, half to even ([Fee Schedule](https://docs.polymarket.us/fees.md)).

**Families, depth and volume.** [M] Books are from `/v1/markets/{slug}/book` for all 759 BTC and ETH ladder markets (snapshots 25 Oct 23:20Z and 23:57Z). SOL and XRP spreads are from the listing's two-sided quotes. Notional is from the exchange's Time & Sales files for trade-days 22 Oct (Thursday) and 24 Oct (Saturday) ([manifest](https://www.polymarketexchange.com/files/time-and-sales/manifest.json)), price × quantity summed.

| Family (BTC unless noted) | Expiry / grid | Index statistic | Open markets | Two-sided / one-sided | Median spread (two-sided) | Median top size | Notional Thu / Sat |
|---|---|---|---|---|---|---|---|
| Up/Down 5m | rolling, from 22 Oct 16:30Z | 60-s avg, open and close | 1 live | two-sided | 1–2¢ | ~700–2,100 sh | $0.67M / **$11.5M** |
| Up/Down 15m | rolling; listed ~12 h ahead | 60-s avg | 1 live | two-sided | **1.0¢** (all hours) | ~2,000 sh; 4–8k within 5¢ | **$16.3M / $10.3M** |
| Up/Down 1h | rolling | 60-s avg | 1 live | two-sided | 1¢ | 500–600 sh | $0.68M / $0.42M |
| Up/Down 1d | 5 PM ET | 60-s avg | 1 | two-sided, thin | 1–3¢ | 70–5,000 | $34k / $42k |
| Above/Below hourly | $100 grid, ~160 strikes | 60-s avg | 163 | 10 / 34 | 3.5¢ | 25–33 sh | $118k / $176k |
| Above/Below daily (5 PM ET) | $250 grid | 60-s avg | 55 | 27 / 28 | 5¢ | 56 / 5,000 | $21k / $34k |
| Above/Below weekly (Fri 5 PM ET) | $500 grid | 60-s avg | 83 | 37 / 46 | 4¢ | 5,000 / 5,000 | $1.0k / $1.5k |
| Range hourly / daily / weekly | same grids | 60-s avg | 164 / 56 / 84 | 8 / 14 / 16 two-sided | 4–13¢ | 2,550–5,000 | $3.5k / $1.5–5.9k / <$0.5k |
| One-Touch weekly (high, low) | $2,500 grid | rolling 60-s trimmed mean | 8 + 8 | 1–3 / 5–7 | 7–8¢ | 3,000 | < $200 |
| One-Touch monthly (Oct) | $2,500 grid | trimmed mean | 8 + 10 | 0–2 / 6–8 | 8¢ | 3,000 | < $200 |
| **Hand-listed year-end** ("how high/low this year", "$100k again", "$150k", year-end range) | to 1 Jan 2027 05:00Z | trimmed mean | 57 | 41 two-sided | **1¢** | 2k–340k sh | $0.2–7k |
| ETH ladders (hourly / daily / weekly / weekly hit) | $5–20 grids | ETHUSD_RTI | 95 / 33 / 83 / 16 | 16 / 24 / 52 / 6 two-sided | 6–10¢ | 5,000 / 3,000 | $9.6–13.9k hourly, <$0.4k others |
| ETH Up/Down 15m / 5m / 1h | rolling | ETHUSD_RTI | 1 each | two-sided | 2¢ (60% of minutes >1¢) | 100–600 sh | $0.32M / $0.37M (15m) |
| SOL, XRP ladders | — | SOLUSD_RTI / XRPUSD_RTI | 281 / 113 | mostly one-sided | 8–18¢ | — | ≤ $0.4k |
| SOL, XRP Up/Down 15m | rolling | — | 1 each | two-sided | 1–4¢ | — | $0.13–0.15M |
| `mag7-stablecoin` | 31 Dec | official announcement | 7 | two-sided | 40¢ | — | — |

[M] **Ladder volume is tiny.** The weekly ladders had traded `sharesTraded` = 0 on 66 of 83 strikes at 23:57Z. The automated families together are under 2% of crypto notional. The flow is retail-sized: the median BTC 15-minute trade was **$4.30–4.85** and the 90th percentile $63–76.

---

## Q2. Model fair value against PMUS bid/ask

### Method

[M] Fair probabilities were computed for every quoted BTC and ETH ladder strike from four models:

- **(a) Deribit options smile.** Mark IVs from `public/get_book_summary_by_currency` (920 BTC options), using the OTM side, interpolated linearly in log-moneyness and linearly in total variance between expiries, with Deribit futures as forwards and the smile held fixed in moneyness as spot moves. "Above X" contracts were priced as the strike derivative of call prices across the smile (`f_iv`). One-touch contracts were priced three ways:
  - Black–Scholes one-touch at the barrier strike's IV (`iv(BS@K)`).
  - Twice the smile digital (`f_alt`).
  - **Local-vol Monte Carlo** (`f_lv`): short-maturity local vol from the smile, σ_loc = σ²/(σ − kσ'); 20,000 paths with a Brownian-bridge correction for crossings between steps. It matches the closed form at flat vol (0.0985 against 0.1002). This is the smile-consistent price and the one quoted below.
- **(b) Realized vol.** Coinbase hourly returns over 7 days (BTC 28%, ETH 42%; a 24-hour 1-minute RV of 22% and 36%), flat vol and zero drift (`f_rv`).
- **(c) Empirical.** A vol-normalized bootstrap of Coinbase daily highs, lows and closes since 2017 (BTC 3,799 days), with each path scaled by its trailing 30-day RV (`f_emp`).

Edge for buying Yes = fair − ask − fee(ask). Edge for buying No = bid − fair − fee(bid), since buying No on this venue means hitting the Yes bid. The 60-second averaging and trimmed-mean monitoring move barriers by about 0.03% and were ignored.

[M] Surface at 23:20Z on 25 Oct: BTC ATM IV 35.6% (26 Oct expiry), 34.4% (30 Oct) and 37.4% (25 Dec); ETH 50.8–52.9%. Implied vol was 7–14 points above realized: the weekend 1-minute RV was 22% for BTC.

### (a) Automated ladders sit on the options surface; no quote clears the fee

[M] Across both snapshots, against the smile-consistent fair value, BTC and ETH weekly and daily Above/Below ladders and weekly and monthly One-Touch ladders gave:

- **0 of 119–120 BTC weekly quotes** with positive EV after the fee. The best was −0.0¢ at 85,000.
- 4–7 of 82–83 BTC daily quotes with positive EV, the best +1.0¢.
- 0 of 10–11 quotes in each BTC and ETH One-Touch ladder.
- At most +0.7¢ in the ETH weekly ladder.

Examples at 23:20Z:

- BTC weekly 81,000: 0.39/0.43 against IV fair 0.421.
- BTC weekly 83,000: 0.18/0.23 against 0.184.
- BTC monthly "dips to $75k": 0.13/0.21 against `f_lv` 0.207.
- ETH weekly "reaches $2,700": 0.01/0.07 against 0.049.

The mid tracks the options price strike by strike, so the maker evidently prices from Deribit or an equivalent surface [I]. Full tables are in `crypto_data/model_gaps_by_family.txt`, and per-strike CSVs are in `crypto_data/fv_*.csv`.

[M] **Realized vol shows gaps; implied vol does not.** Against the realized-vol and empirical models, the same books show +1 to +4¢ "sell the wings" gaps: 17–19 BTC weekly quotes above +1¢ and 18 BTC daily quotes above +1¢ under realized vol. That gap is the variance risk premium, implied vol (34–36%) over weekend realized vol (22–28%). Taking it is a short-vol bet, not a pricing error. It only pays if realized vol stays below implied vol, and on the hourly backtest below, the daily-ladder version with implied vol (DVOL) gives −1 to +2¢ ± 2–5¢.

### (b) Far-OTM touches: overpriced at the ask, but in the automated ladders there is no bid to sell into

[M] The automated maker keeps a floor ask of **0.03–0.05 on every far-OTM strike**:

| Example (23:20Z) | Ask | `f_lv` | `f_emp` |
|---|---|---|---|
| BTC weekly "reaches $100k" | 0.03 | 0.001 | 0.002 |
| BTC monthly "$102.5k" | 0.04 | 0.001 | 0.003 |
| ETH weekly "$3,200" | 0.04 | 0.003 | — |

So the far-OTM touch **is** overpriced at the ask, by 2.5–4¢, as the longshot literature predicts. The Kalshi crypto bias slope (0.058) is the steepest of any category in [Bürgi, Deng & Whelan, Jan 2026](https://www.karlwhelan.com/Papers/Kalshi.pdf) [C]. But those strikes have **no bid at all**: 0 shares bid on 6–7 of 8 BTC weekly-high strikes. A taker cannot sell them.

[I] The only way in is a resting Yes offer below the floor, which is zero-fee for a Tier-1 maker. For example, a No bid at 0.98 is a Yes offer at 0.02 against a fair of 0.001–0.005. It would earn about 1.5–2¢ per fill. [M] But fills would be rare: the month's flow in these strikes came while BTC was near them (the October "$90k" touch traded 0.63 on 5 Oct and 0.06 on 25 Oct, `price-history INTERVAL_1M`), and weekly-hit notional is under $200 a day. Verdict: not worth building now.

### (c) The hand-listed year-end ladder: a robust, persistent tail premium that a taker can capture

[M] These are the liquid crypto books: 1¢ wide, 2k–340k shares at the touch, and 0.3–7.6M shares traded per market since listing. Every model agrees the far tails are rich. Values at 23:20Z and 23:57Z (identical to ±0.1¢) are below. "EV" is buying No at the bid against `f_lv`, after the fee. The full table is in `crypto_data/yearend_tail_table.txt`.

| Market (to 1 Jan 2027 unless noted) | Bid × size | `f_lv` | IV (BS@K) | Empirical | EV ¢/contract | EV % of outlay |
|---|---|---|---|---|---|---|
| Hit $150k (`btc-150k-12-31`) | 0.04 × 85k | 0.004 | 0.006 | 0.007 | **+3.4** | 3.5% |
| Hit $150k (`hitprice-high-…-150k`) | 0.03 × 123–126k | 0.004 | 0.006 | 0.007 | +2.4 | 2.5% |
| Hit $140k / $130k / $120k | 0.03 / 0.03 / 0.04 | 0.006 / 0.011 / 0.022 | 0.009 / 0.015 / 0.029 | 0.012 / 0.020 / 0.039 | +2.2 / +1.7 / +1.5 | 1.6–2.3% |
| Hit $100k by 30 Nov (36 days) | 0.11 × 4.3k | 0.066 | 0.072 | 0.081 | **+3.7** | 4.1% |
| Hit $100k by 31 Dec | 0.21 × 2.4–3.0k | 0.166 | 0.167 | 0.186 | +3.2 | 4.0% |
| Hit $150k by 30 Nov | 0.02 × 217k | 0.000 | 0.000 | 0.000 | +1.9 | 1.9% |
| Above $200k (both listings) | 0.01 × 116–195k | 0.001 | 0.002 | 0.000 | +0.9 | 0.9% |
| Dips to $40k | 0.05 × 47.6k | 0.015 | 0.043 | 0.020 | **+3.2** | 3.3% |
| Dips to $45k / $50k | 0.05–0.06 / 0.07 | 0.028 / 0.046 | 0.059 / 0.084 | 0.027 / 0.034 | +1.9–2.8 / +2.0 | 2.0–2.9% |
| *Dips to $75k (opposite sign)* | ask 0.58 | 0.682 | 0.698 | **0.500** | buy Yes +8.5 under options, −8 under empirical | model-dependent; not used |

[M] **The gap has persisted for at least a month.** From `price-history INTERVAL_1M fidelity=180`, the $150k-by-31-Dec contract quoted 0.05/0.04 on 25 Sep, 3, 10 and 25 Oct and 0.07/0.06 on 18 Oct. The "how high this year" $140k and $150k strikes held 0.04–0.07 throughout, and the $40k dip held 0.06/0.05 on every sample date. Three snapshots over 80 minutes (23:20Z, 23:57Z, 00:39Z) gave the same EVs to ±0.4¢ while BTC moved $140.

[I] **Downside "dip" markets are a different case.** Here the market sits between the options price (which carries the put-skew crash premium) and the empirical rate. It underprices $70–75k dips against options and overprices them against history, so it is a risk-premium question, not a mispricing.

[I] **What the trade is.** It sells lottery tickets, collecting the longshot premium the literature documents: favourite-longshot slopes are positive and strongest in crypto on Kalshi, and Cardozo & Rivero-Wildemauwe find robust two-sided bias in crypto on global Polymarket ([arXiv 2609.12878](https://arxiv.org/pdf/2609.12878)) [C]. Size is not a constraint at $135. The constraints are:

- capital locked to year end, or exited early at the bid;
- the legs are correlated: all upside legs lose together on a BTC melt-up to $100k+, and all downside legs together on a crash to $40–50k;
- model risk in the skew;
- a possible fee increase. The coefficient rose three times in 2026 ([prior survey](../../reports/Polymarket%20US%20worker%20edge%20survey.md)).

### (d) Hourly and daily ladders: a deep-in-the-money "maker premium" on the tape, not confirmed on live books

[M] **Tape backtest.** On 65 settled BTC hourly ladders and all 6 settled daily ladders, I used `price-history` custom ranges at fidelity=1, strikes within ±0.8% (hourly) or ±5% (daily) of spot one hour or six hours out, against BRTI 5-second closes and Deribit DVOL ([get_volatility_index_data](https://www.deribit.com/api/v2/public/get_volatility_index_data?currency=BTC&resolution=3600)). The rule was: buy the side priced 0.80–0.99 when the model said it was cheap by more than 2¢. This looked very strong:

- **Hourly, 15 minutes left:** 167–172 trades over 62 ladders, mean **+6.4¢ ± 0.7¢** (SE clustered by ladder), 1 loss, average cost 0.926 against model 0.995. It held with a 60–120 s stale spot and a 60–120 s execution delay (+5.6 to +6.4¢), and with DVOL instead of realized vol (+5.8 ± 1.4¢ across the 15/30/45-minute checkpoints).
- **Daily, 2–6 hours left:** +5.6–5.8¢, 0 losses in 146–170 trades, but only 6 independent days.

[M] **The tape's display price is not a quote when one side of the book is empty.** On the 00:00Z ladder I compared the live `/book` at 23:25Z with that minute's bars:

| Strike | Live book | Bar showed |
|---|---|---|
| 79,600 | bid 0.57, **no ask** | 0.83/0.82 |
| 79,700 | bid 0.95, **no ask** | 0.99/0.98 |
| 80,800 | **no bid**, ask 0.04 | ask 0.04 / bid 0.05 (crossed) |

When I kept only bars that were two-sided and ≤8¢ wide at both decision and execution, the hourly edge collapsed to **+1.9 ± 4.0¢ (n = 24) at 15 minutes and −3.6 ± 5.8¢ at 30 minutes**. Daily stayed positive but rests on 6 days and 15–29 trades (`crypto_data/ladder_itm_backtest.txt`). So most of the apparent edge came from bars with no real ask.

[M] **Real deep-in-the-money asks do exist.** At 00:18Z on 26 Oct, with BRTI at 79,962 and 42 minutes left, strike 79,500 was **bid 0.92 × 14 / ask 0.94 × 45**. Its fair value was 0.97 (DVOL, 39%) to 0.999 (realized vol), against a cost of 0.944 including the fee. Strike 79,400 was 0.94/0.97 × 31. Sizes were 12–50 shares, which is one or two $25 clips.

[M] **Forward test, one ladder.** I read the real `/book` of every strike within ±1.2% of spot on the 01:00Z ladder at 30, 20, 15, 10 and 5 minutes before expiry (26 Oct 00:30–00:55Z), alongside gateway BRTI, 1-hour realized vol (42–47% that hour) and DVOL (38.7%). Settlement was computed from 60 BRTI one-second prints at 79,986.47. Of the 34 two-sided deep-in-the-money quotes (cost 0.80–0.99), the maker priced the likely side **as rich or richer than both models**: median EV −2.3¢ (realized vol) and −0.2¢ (DVOL). Only **one** quote cleared +2¢ under realized vol: strike 80,000 No at 0.91 × 5 shares with 5 minutes left, +2.6¢ model, +8.4¢ realized. All 34 won, but that is one correlated hour (`crypto_data/live_itm_eval.txt`). In this hour the live books show no repeatable deep-in-the-money discount.

[I] **Verdict: Test as a no-money forward log, not Build.** The tape signal was mostly an artefact of one-sided books, and the first live hour showed the maker pricing deep in the money at or above fair. Whether a real premium appears in calmer hours has to be settled on live books, not the tape. If it is, the per-hour capacity is a few hundred dollars and capital turns over hourly. It is the crypto twin of the sports "settlement yield" in the prior survey, with crash-in-15-minutes risk instead of a mis-read final.

---

## Q3. Short-dated up/down mid-window: the PMUS price already is the conditional probability

[M] **Data.** 1,490 settled windows (BTC 15m 629, BTC 1h 159, BTC 5m 299, ETH 15m 265; 18–25 Oct) from `/v1/price-history?symbol=…&timestamp.startTimestamp=…&fidelity=1`, plus BRTI 5-second candles for 18–25 Oct (132,173 per asset).

[M] **Bar timing.** A price-history bar stamped *t* is the book at **t + 60 s**. Mean |last trade − bar mid| was 0.0076 at +60 s against 0.096 at +0 s, across 2,701 bar-trade pairs from Time & Sales; ladders showed the same.

[M] **Model.** P(Up) = Φ(ln(S/O) / (σ√(τ − 40 s))), where:

- S is BRTI read up to 5 s before the quote time;
- O is `priceToBeat`;
- τ is the time remaining; the −40 s accounts for the closing 60-second average;
- σ is trailing realized vol from 60-second BRTI returns over 15 minutes, 60 minutes, 24 hours, or a blend. 5-second BRTI returns are smoothed and understate vol.

Only two-sided books (spread ≤ 5¢) were kept.

| Series | Minutes left | n | Brier, PMUS mid | Brier, best model | Taker rule at 1–5 min left (edge > 2¢ / > 5¢), ¢ per contract ± SE |
|---|---|---|---|---|---|
| BTC 15m | 1–2 | 148 | **0.106** | 0.124 | −2.3 ± 1.9 / −3.9 ± 2.4 (n = 404 / 243) |
| | 3–5 | 791 | **0.153** | 0.161 | |
| | 5–10 | 2,880 | **0.164** | 0.167 | |
| BTC 5m | 1–2 / 3–5 | 123 / 575 | **0.120 / 0.175** | 0.125 / 0.177 | −5.9 ± 2.6 / −6.6 ± 3.0 |
| BTC 1h | 3–5 / 5–10 | 100 / 398 | **0.106 / 0.106** | 0.110 / 0.109 | −8.1 ± 4.2 / −8.7 ± 4.8 |
| ETH 15m | 3–5 / 5–10 | 324 / 1,151 | **0.143 / 0.169** | 0.143 / 0.169 | +0.4 ± 3.1 / +2.9 ± 4.4 |

[M] **The market beats a live model at every horizon.** Its implied vol (median 22.1%, IQR 16.8–29.5%) equals trailing 60-minute realized vol (22.2%), not 24-hour vol (30.6%). Its mid is calibrated: the 0.1–0.9 bins win at 0.151, 0.240, 0.309, 0.445, 0.535, 0.647, 0.733 and 0.848 against mids of 0.150–0.849.

[M] **The advantage lives in the last few seconds of spot.** Reading spot ≤5 s *after* the quote, which a bot cannot do, turns the BTC 15-minute taker rule from −3.5¢ to +1.9 ± 2.2¢. That says the market had already absorbed everything except the last few seconds [I].

[M] **Buying the favourite at the ask is also flat.** At 0.85–0.985 with 1–15 minutes left, results range from −2.8 to +2.4¢ ± 1–4¢ (BTC 15m, 5m and 1h, ETH 15m). On traded prices folded to the favourite (Time & Sales 20/22/24 Oct, SE clustered by window), BTC 15-minute calibration was within ±1 point except the 0.60–0.70 bin (+4.7 ± 2.1, one of seven bins).

[M] **The market moves too fast for a 45-second poll.** The 15-minute mid moves a median **9¢ per minute** (mean 11¢, 71% of minutes ≥5¢) with 1–10 minutes left. A 45-second poll reading a 30-second-cached `/bbo` is 30–75 s behind and would be adversely selected on every fill.

**Answer: no measurable edge** for a bot computing the conditional probability from live spot with 1–5 minutes left. Do not build it.

---

## Q4. Who makes these books and how fast they reprice

[C] **Who the makers might be.** Jump Trading receives Polymarket equity that scales with the liquidity it provides to the US exchange ([Decrypt](https://decrypt.co/357519/jump-trading-earn-stakes-polymarket-kalshi), Feb 2026; [Finance Magnates](https://www.financemagnates.com/forex/prop-firm-jump-trading-to-take-stakes-in-kalshi-and-polymarket-report/)). Polymarket has recruited an in-house market-making desk ([Cointelegraph](https://cointelegraph.com/news/polymarket-in-house-market-making-desk-trade-users)). The amended Series-Based Market Maker Program names "cryptocurrency price contracts" as eligible series, requires ≥5% of a series' maker notional, and pays out of taker fees ([CFTC filing 09302630733](https://www.cftc.gov/filings/orgrules/rules09302630733.pdf), Sept 2026). No source names the maker of the crypto books.

[M] **What the books show.**

- Every automated ladder carries the same fingerprint: 5,000/5,250/5,300-share clips on above/range ladders, 3,000 on touches, 250–500 on inner levels, with the mid on the Deribit surface. That is one programmatic options-aware quoter [I].
- The 15-minute and 5-minute up/down books are 1¢ wide in every 6-hour block, weekend included, with ~2,000 shares at the touch.
- The year-end hand-listed books are quoted far deeper (100k+ shares at 0.01–0.04), consistent with a different participant who is comfortable warehousing tails [I].

[M] **Reprice speed against the index.**

- PMUS BTC 15-minute trade prices, turned into implied moves, correlate with BRTI moves over the **next 2–20 seconds** (correlation 0.14–0.16, flat across those lags) and not with past BRTI moves (≤0.02 at lags of +2 s and beyond). Sample: 5,116 two-second intervals, 22 and 24 Oct 14:00–16:00Z, Time & Sales against the 1-second BRTI.
- That is because the published BRTI is smoothed at the second scale: lag-1 autocorrelation of 1-second returns is 0.985 and annualized vol is 6.9% at 1 s against 43.6% at 60 s. It also trails Coinbase: in a live 240-second test on 26 Oct, Coinbase ticker moves showed up in BRTI over the following 0–9 s. At the minute scale BRTI tracks Coinbase closes within 0.8 bps (SD).
- So makers price off exchange feeds that lead the index by seconds [I].

[I] **Latency a bot would need.** Exchange WebSocket feeds (Coinbase/Kraken/Binance) and the authenticated PMUS markets WebSocket, with a decision-to-order path well under a second. The Q3 results show that even a 1–5 s handicap leaves a simple model behind the market. The global-venue history points the same way: the 15-minute latency arbitrage there is described as lasting "milliseconds" after fees arrived ([Finance Magnates, 16 Mar 2026](https://www.financemagnates.com/trending/prediction-markets-are-turning-into-a-bot-playground/)). The current worker (45-second REST, 30-second edge cache) is two orders of magnitude too slow for up/down. For the year-end tails, latency is irrelevant: a daily check is enough.

---

## Q5. Weekends, overnight, settlement integrity, index against spot

[M] **No weekend or overnight degradation.**

- BTC 15-minute mean spread was 1.05–1.10¢ in every 6-hour UTC block and 1.05¢ on weekends against 1.08¢ on weekdays.
- Weekend books were slightly harder to beat: mean |mid − model| was 0.052 against 0.039, and the model's Brier worsened more than the market's.
- Saturday notional was lower in 15m ($10.3M against $16.3M on Thursday) but shifted into the 5-minute windows ($11.5M).
- Thursday volume dipped at 08–12Z ($1.0M per 4-hour block against $2.4–3.7M); Saturday's quietest block was also 08–12Z ($1.25M).

[M] **The weekend regime that matters is implied vol over realized vol.** 1-minute RV was 18.7–24.6% on 24–25 Oct against 29–32% on weekdays, while Deribit ATM IV stayed at 34–36% (DVOL 38.8). Options-priced ladders therefore look rich to a realized-vol model on weekends. That is the variance premium, not an inefficiency.

[C] **Maintenance.** Up/down windows that would overlap the Thursday 6:00–8:00 AM ET maintenance are not listed, and open orders are cancelled before it ([Crypto FAQs](https://docs.polymarket.us/faqs/crypto-faqs.md); [General FAQs](https://docs.polymarket.us/faqs/general-faqs.md)).

[M] **Settlement integrity.** I checked 8,264 settled up/down markets, 18–25 Oct:

- The outcome matched the stamped `settlementPrice` against `priceToBeat` in every case.
- **14 exact ties** (0.17%), all on SOL, XRP and ETH windows, all settled Up as the rules say. In SOL 15m, ties are 0.55% of windows, a small structural tilt toward Up in the cheaper coins.
- One market (`xrp-updown-1h-2026-10-22-1000z`) settled with no stamped settlement price.
- No disputes or busts were found in the docs or press. The rules allow a 7-day postponement for source errors ([prior survey, QCX filing](https://www.cftc.gov/filings/orgrules/rules09112624948.pdf)).

[M] **Index against spot.**

- Coinbase 1-minute close against BRTI at the same second: median −0.35 bps, p1/p99 −2.3/+1.3 bps (4,320 minutes, 23–25 Oct). That is $2–18 on BTC, irrelevant to ladders.
- It does matter at the finish of up/down windows: deciding the 15-minute outcome from Coinbase minute closes instead of BRTI averages **disagreed on 23 of 287 windows (8%)**, all of them flat windows with a median move of 0.7 bp. A bot that settles in its head from one exchange print is wrong about one window in twelve near the money.

---

## Ranked strategies for a $135 account

| Rank | Strategy | Verdict | Realistic $ at $135 | What the worker needs | Main risks |
|---|---|---|---|---|---|
| 1 | **Sell year-end BTC tails** (buy No at the bid): $150k by 31 Dec (0.04), $100k by 30 Nov (0.11), $130–150k "how high" (0.03), $40–50k dips (0.05–0.07). Keep only legs where the bid exceeds the local-vol, IV and empirical fair values all by ≥1.5¢ after the fee. | **Test** (small, now) | EV +1.5 to +3.8¢ per contract, 1.6–4.2% of outlay over 1–2 months: **≈ $1.5–2 a month** on ~$100 deployed. Worst plausible case −$20 to −40 (a ±40–50% BTC move). | Once-a-day job: Deribit book summary (no key), the local-vol touch pricer in `crypto_data/scripts/`, `/book` on ~20 slugs, IOC No at bid ≤ $25 per leg, cap of 3 upside and 2 downside legs, re-price daily, exit if the gap closes. Read `feeCoefficient` per market. | Correlated tail (melt-up or crash); capital locked to 1 Jan; skew model risk on dips (use downside legs only where empirical also agrees); fee hikes; the "after creation" touch definition |
| 2 | **Hourly / daily ladder deep-in-the-money** (buy the 0.90–0.97 side that a realized-vol model calls ≥0.99, at 15 min (hourly) or 2–6 h (daily) left) | **Test** (log only, no orders) | Probably ≈ $0. Two-sided tape +1.9 ± 4.0¢ (n = 24). Live 01:00Z ladder: 1 of 34 deep-in-the-money quotes cleared +2¢ (5 shares). Upper bound if a premium appears in calm hours: $0–5 a day on 12–50-share clips. | Real `/book` (or WebSocket) at decision time, never price-history; BRTI from `/v1/asset-prices/history` plus 60-second RV; minimum two-sided book; a flash-move kill switch; one ladder at a time | Phantom display prices; 15-minute crash tail correlated across strikes; 12–50-share depth; maker repricing once others take the asks |
| 3 | Weekly/daily ladder "sell the wing" on realized vol < implied vol | Skip (it is a short-vol bet) | −$1 to +$2 a week, sign set by realized vol | Options plus RV feeds, resting or taker orders | Vol spikes; a 4–6¢ spread eats the premium |
| 4 | Resting Yes offers under the 3–5¢ floor asks on far-OTM weekly/monthly touches (zero maker fee) | Skip for now | < $1 a week; strikes trade under $200 a day | GTC, `participateDontInitiate`, cancel before Thursday maintenance | Queue behind the maker; rare fills; touch risk |
| 5 | Up/down mid-window conditional-probability taker (15m/5m/1h, 1–5 min left) | **Skip** | Negative: −2 to −9¢ per contract measured | Would need sub-second exchange WebSocket + PMUS WebSocket; still behind | Market mid beats the model at every horizon; 9¢ median 1-minute moves |
| 6 | Up/down favourite at 0.85–0.985 / final-seconds "certainty" | Skip | ≈ $0 (−2.8 to +2.4¢ ± 1–4¢) | — | No sellers on the winner in the last 20–180 s (prior survey); 8% Coinbase-vs-BRTI flips on flat windows |
| 7 | Cross-venue lag (Coinbase spot against ladders) | Skip | $0 | — | Ladders reprice within the minute (prior survey) and makers lead the index by seconds |
| 8 | SOL/XRP ladders, `mag7` | Skip | — | — | 8–40¢ spreads, one-sided books |

**What to change in the worker regardless.** Read the crypto books from `/book` or the WebSocket, never from `price-history` or the listing. The listing omits one-sided quotes (14 of 30 sampled markets differed from `/bbo`), and price-history invents the missing side. Use the free `/v1/asset-prices/history` endpoint as the BRTI source; it is not cached. Keep crypto strategies on a daily cadence unless the worker moves to WebSockets and exchange feeds, because nothing at the 45-second scale is harvestable here.

---

### Data in `crypto_data/`

- `model_gaps_by_family.txt`: per-family count of quotes with positive EV under each model, both snapshots.
- `fv_20261025T2320Z.csv`, `fv_20261025T2357Z.csv`: every BTC and ETH ladder quote with bid, ask, depth, `f_iv`, `f_rv`, `f_emp`, `f_alt`, `f_lv` and EVs.
- `yearend_tail_table.txt`: the Q2(c) table.
- `ud_result_*.txt`: the Q3 Brier, calibration and taker-sim output per series.
- `updown_trade_calibration.txt`: the folded calibration from Time & Sales.
- `ladder_backtest.txt`, `ladder_itm_backtest.txt`: the Q2(d) tape backtests, loose and strict.
- `tas_volume_by_family.txt`: Thursday and Saturday notional by family.
- `trade_vs_brti_leadlag.txt`: the Q4 lead-lag.
- `live_itm.jsonl`, `live_itm_eval.txt`: the forward test of live hourly-ladder books (01:00Z ladder, 26 Oct; partial 02:00Z rows).
- `fv_20261026T0039Z.csv`, `model_gaps_0039Z.txt`: the third snapshot.
- `scripts/`: snapshot, fair-value, local-vol, up/down and ladder backtest code (read-only, public endpoints).
