# Tech tab: one leaderboard, a handful of IPO and release dates, and no stock markets

**Takeaway.** The Tech tab holds **16 open events and 103 open markets** (gateway tag `tech`, id 414). Ten of the events, and nearly all the activity a bot could time, settle on a single page: the Arena (ex-LMArena) Text leaderboard. The rest are slow "by date" contracts on model releases, IPO confirmations and AI policy. There are no Mag-7 market-cap, stock-price, earnings, SpaceX-launch, Tesla-delivery or Apple-event contracts, and the one App Store pair (25 Sep) is closed. The edge the data supports is small and comes from reading the leaderboard. When it updated on 26 and 30 Sep and on 22 Oct, PMUS began repricing within 1–4 minutes but took 15–60 minutes to settle. After the 12:00 ET snapshot that fixes a monthly market, the already-decided winner kept trading at **0.98–0.99 (once at 0.87) for 54 minutes to 50 hours** before settlement. The books undercut both trades: the quote at the touch is often a few shares of "dust", and the soonest-settling Arena legs are 30–50¢ wide once you go past it. **Realistic value at a $135 account is about $3–15 a month for the whole tab**. That needs a live leaderboard reader that this sandbox could not run, because arena.ai returns a Cloudflare 403 here.

Labels: **measured** (endpoint and UTC time), **cited** (URL and date), **inference**. Gateway pulls were made on 25 Oct 2026 between 23:16 and 23:40Z at no more than 2 req/s. The raw data is in [`tech_data/`](tech_data/).

---

## Q1. What is under the Tech tab

**How the tab maps to the gateway.** The tab is the tag slug `tech`, not the event field `category`. `GET /v2/tags/tech/events?limit=200` returns 16 open events and, with `closed=true&active=false`, 15 closed ones (measured, 23:18Z). The `category` field on those events is mixed: `technology` 10, `finance` 4 (the three IPO events and Dario-out), `politics` 2 (AI safety bill, data-centre moratorium). That explains why the 24 Oct survey counted "10 technology" events. The tab has not grown since then; the earlier count was simply a different field. Subtags seen: `ai-rankings`, `rankings`, `model-releases`, `ai-models`, `ipos`, `business`, `ceos`, `ai` (measured, `/v1/events` listing, 23:16Z).

**Conventions common to every Tech market (measured from the listing and `/book`):**
- `feeCoefficient` is 0.0695, so the taker fee is 0.0695·p·(1−p) per contract.
- `orderPriceMinTickSize` is 0.01 and `minimumTradeQty` is 0.01.
- Contract expiries are 15 Jan / 15 Jul / 15 Nov, but markets settle soon after the event.

**Open families**

| # | Family (events) | Contract wording (abridged) | Settlement source and time | Open mkts | Lifetime notional / OI (measured, `/book` stats) | Touch and depth (measured 23:26Z) |
|---|---|---|---|---|---|---|
| A1 | Arena #1 company, month-end (`company1-2026-10-31`) | "Yes if Google has the #1 ranked AI model on the Arena AI Text Arena leaderboard on October 31, 2026 at 12:00 PM ET (Style Control Off)… ties → highest Score … then alphabetical" | arena.ai/leaderboard/text/overall-no-style-control, 12:00 ET snapshot | 12 | $314k / 62.9k | Google bid 0.86 × **3.9 sh**, ask 0.87 × **3.4 sh**, then 0.88 × 2.3, 0.90 × 63; next real bid **0.42**. Anthropic: bid 0.01 × 4, cheapest real ask 0.16 × 2.7, 0.27 × 28 |
| A2 | Arena #1 company, year-end (`company1-2026-12-31`) | Same wording, 31 Dec 12:00 ET | Same | 12 | $1.34M / 193k | Anthropic 0.48 × 1,103 / 0.49 × **0.02**, then 0.52 × 3.5, 0.55 × 342; Google 0.37 × 118 / 0.38 × 5,071 |
| A3 | #1 at any point in 2026 (`company1-dur2026`) | "#1 … at any point between Contract Issuance and Dec 31… if tied for rank #1, both … considered #1" (Google leg resolved Yes 30 Sep 20:54Z) | Same, continuous | 10 | $800k / 52.8k | 1¢ quotes, but Meta, OpenAI and Amazon asks are 1-share dust ($25 fills at 0.13–0.76) |
| A4 | #1 coding model, year-end (`code1-2026-12-31`) | Same, "Coding" category | arena …/text/coding-no-style-control, 31 Dec 12:00 ET | 12 | $404k / 60.6k | Anthropic 0.69 × 707 / 0.70 × 201 |
| A5 | Best Chinese company, month-end (`cmpny-china-1-2026-10-31`) | "Yes if Xiaomi is the Chinese company with the highest ranked AI model… Oct 31 12:00 PM ET… Chinese companies include but are not limited to…" | Same, 12:00 ET | 11 | $109k / 19.5k | Xiaomi 0.61 × 170 / 0.62 × **4.2**, then 0.64–0.65 (186 sh), then 0.96+; Moonshot has no bid, asks 0.31 × 4.4, then 0.64 |
| A6 | Chinese model #1 any time in 2026 (`chinese-arena-ovrall-1`) | "any Chinese company has the #1 ranked AI model… at any point… Dec 31" | Same | 1 | $174k / 14.5k | 0.12 × 14,002 / 0.13 × 13,905 |
| B | Model release by date (`openai-gpt-7`, `openai-gpt-astra-6pt1`, `anthropic-claude-6`, `xai-grok-5`) | "releases a … model numbered 6.0 or greater… accessible and usable to the general public… closed beta … does not qualify" | "Outcome sourced from [lab]"; deadline 23:59 ET | 8 | $1.31M / 21.2k | Genuinely 1¢ wide: 2,000–4,500 sh at the touch on most legs (GPT-7 0.79/0.80, Astra-6.1 Oct 0.11/0.12, Claude 6 Dec 0.24/0.25, Grok 5 0.38/0.39) |
| C | IPO confirmed (`2026ipos`, `anthropic`, `openai`) | "confirmed when i) SEC declares … S-1 … effective, ii) the IPO is priced (424B4 / pricing release) or iii) an exchange assigns a ticker and approves listing" | Company, SEC, exchange; 23:59 ET | 32 | $7.09M / 285k (Anthropic event alone $4.44M) | Anthropic Nov-30 0.69 × 1,165 / 0.70 × 4,262; Dec-31 0.80 / 0.81 × 4,188; field longshots 0.01/0.02 with 30–40k bid at 0.01 |
| D | CEO out (`daramo-anthceo`) | "departure… officially announced by Dec 31" | Anthropic / Amodei | 1 | $132k / 14.9k | 0.04 × 10,457 / 0.05 × 4,386 |
| E | AI policy (`usleg-aisfty`, `anyst-datactrmor`) | Federal AI-safety law by date; any state data-centre moratorium by date | Congress / state legislatures | 4 | $72k / 4.0k | 0.49/0.50, 0.12/0.13, 0.87/0.88, 0.41/0.42; 1¢ wide with 70–15,000 sh |

Tab total: about **$11.7M lifetime notional, roughly $120k a day on average** across the 16 events (measured; `notionalTraded` summed from `/book` stats, divided by days since `createdAt`). Volume concentrates in the IPO events and the year-end Arena event.

**Closed families (from `/v2/tags/tech/events?closed=true`, measured):**
- Monthly Arena #1 and best-Chinese for Jul, Aug and Sep. Winners: Anthropic three times; Alibaba, Alibaba, Xiaomi.
- Release-by-date ladders: Gemini 3.5 Pro (No), Gemini 4 (No by 30 Sep, Yes by 31 Oct, resolved 20 Oct 14:19Z), GPT-6 (resolved Yes 8 Sep 15:48Z), next Opus (24 Sep), next Sonnet (28 Sep), next Haiku (7 Oct), Claude Mythos (12 Jun).
- A one-off **#1 Free / #1 Paid App Store on 25 Sep** pair (Muse from Meta, Shadowrocket). It sat at the 0.50/0.50 placeholder until about 15:56Z and resolved at 21:12Z.

**Not on the venue at all:** Mag-7 market caps or stock prices, earnings beats, SpaceX launches, Tesla deliveries, Apple/Google/OpenAI event outcomes, and app-store rankings beyond the one closed pair (measured: none in the 4,861-event open listing or the closed Tech tag).

**Adjacent in other tabs:**
- Econ tab (tags `economics/business/ceos`): Elon Musk Bloomberg net-worth ladders for 31 Oct, 31 Dec and "hit by Dec 31" ($1.53M lifetime), plus Musk-out and Altman-out.
- Crypto tab: `mag7-stablecoin`. It is quoted 0.02 bid against 0.32–0.44 ask with 150–330 shares, so it is effectively dead.

**A data trap for the worker (measured, `/bbo` against `/book`, 23:21–23:27Z):**
- `/bbo` `bidShares` and `askShares` are **aggregate resting depth, rounded**, not the size at the touch. Example: Oct-31 Google `/bbo` showed ask 0.87 × "1400", but `/book` had 3.4 shares at 0.87 and about 1,303 across all eleven ask levels.
- Of the 103 open Tech markets, 12 have fewer than 10 shares at the best ask. For 37 of them, a $25 Yes order fills more than 1¢ above the displayed ask.
- Among the 42 markets with an ask between 5¢ and 95¢, 31 fill $25 within 1¢. All 11 that do not are multi-outcome Arena or IPO-field legs.
- **Sum-of-asks "arbitrage" is an illusion here.** The China Oct-31 event shows a best-ask sum of 0.80 and the Oct-31 #1 event 1.01. Walking the books, one full set costs **1.10 and 1.14** after fee, and 25 sets cost 1.42 and 1.29 per set (measured, `/book`).

---

## Q2. Machine-readable resolution sources and how fast PMUS reprices

| Family | Source a bot can poll | Access test (measured) | Observed PMUS reaction | Verdict on lag |
|---|---|---|---|---|
| Arena (A1–A6) | Live: `arena.ai/leaderboard/text/overall-no-style-control`. Mirror: HF dataset `lmarena-ai/leaderboard-dataset`, config `text` = no style control, columns `rating`, `rating_lower/upper`, `rank`, `vote_count`, `leaderboard_publish_date` | arena.ai and lmarena.ai: **HTTP 403 Cloudflare challenge** from this IP (23:23Z). HF parquet: 200 OK. **HF commits land 03:02–03:07Z the next day** (all 21 `Update text` commits Aug–Oct) | Three update episodes below; first move within 1–4 min | The mirror is 5–7 h behind PMUS, so it is useless for timing and good for backtests. Only a live read of arena.ai is fast enough |
| Model releases (B) | Lab blogs/RSS, API model lists | Not tested (needs keys) | GPT-6: ask 0.99 at 03:47Z 2 Sep, but bid 0.55–0.77 for a day; 0.99 on 3 Sep; resolved 8 Sep. Gemini 4: announced 30 Sep as limited "Fairwind" access ([SmartScope, 1 Oct 2026](https://smartscope.blog/en/blog/gemini-4-argon-access-introductory-pricing-2026/), cited); "by 30 Sep" resolved No, "by 31 Oct" ≥0.99 from about 13 Oct, resolved 20 Oct. Sonnet whipsawed 0.40↔0.99 for two days before resolving 28 Sep 18:29Z | The delay is **rule interpretation** ("general public"?), not data latency. A feed cannot resolve it |
| IPO (C) | SEC EDGAR full-text search (`efts.sec.gov/LATEST/search-index`), `data.sec.gov/submissions`, `getcurrent` Atom | 200 OK. **No public Anthropic S-1 on EDGAR at 23:4xZ 25 Oct** (FTS for S-1/S-1A/EFFECT/424B4, measured); Anthropic filed confidentially 1 Jun and a public S-1 was reported "as early as Oct 23" ([Yahoo Finance, 22 Oct 2026](https://finance.yahoo.com/markets/stocks/articles/ai-giant-anthropic-files-public-160911679.html), cited) | No IPO resolution on PMUS with a usable tape (SHEIN sat at 0.99 for a month before resolving 7 Sep) | EDGAR is clean and authoritative for triggers (i) and (ii). This is a headline event, so expect repricing within minutes (inference) |
| App Store (closed) | `rss.marketingtools.apple.com/api/v2/us/apps/top-free/10/apps.json` | 200 OK, `cache-control: max-age=0`, top-5 live (23:34Z) | 25 Sep pair stayed unquoted until about 4 min before the noon snapshot | Source is perfect, but the venue does not list this family |
| Elon NW (Econ, adjacent) | Bloomberg page is not scrapeable; proxy is TSLA + SPCX closes (Yahoo chart API 200 OK; CBOE delayed options 200 OK) | — | `hit-1t`: 0.97 → 0.99 at 20:14–20:23Z on 5 Oct, within 15–25 min of the US close; resolved 15:12Z on 6 Oct | Market prices the close before Bloomberg prints. A 45 s poller gains nothing on timing |

**The three leaderboard updates, minute by minute (measured, `/v1/price-history` custom ranges, `fidelity=1`; "x/y" = `longPrice` / 1−`shortPrice`):**

- **26 Sep, Xiaomi MiMo-V2.6-Pro becomes the top Chinese model** (dataset publish date 25 Sep; HF commit 03:05Z on 26 Sep).
  - `cmpny-china-1-2026-09-30-xiaomi` went 0.02 → **0.88 at 01:34Z**, sagged to 0.71 by 01:57, spiked to 0.98, and the bid side climbed from 0.11 to 0.80 between 01:58 and 02:40Z.
  - It settled at 1.00 on 30 Sep, so the winner was buyable at 0.71–0.88 for about an hour after the update.
  - A false start at 11:46Z on 25 Sep (0.51, decaying to 0.02 by 13:41Z) shows what reacting to rumour costs.
- **30 Sep, Gemini 4 Argon takes overall #1** (1533 vs 1518).
  - `company1-dur2026-google`: 0.41 → 0.52 (20:12Z) → 0.70 → 0.45 (20:20) → 0.96 (20:22) → 0.99 (20:28). It **resolved Yes at 20:54Z**.
  - `company1-2026-10-31-google`: listed at 15:22Z that day, it swung 0.05 → 0.98 → 0.43 → 0.92 → 0.65 → 0.90 between 20:24 and 22:19Z.
  - `company1-2026-12-31-anthro`: drifted 0.72 → 0.42 over 30 minutes.
- **22 Oct, about 12:00Z, Claude Opus 5.5 retakes coding #1** (1545.0 vs 1539.3).
  - `code1-2026-12-31-google` spiked 0.16 → 0.54 at 12:04Z, then fell to 0.04–0.11 by 12:45.
  - `code1-…-anthro` only moved 0.60 → 0.65 by 17:44Z and is 0.69/0.70 three days later (measured).

**Settlement window after the noon-ET snapshot (measured, 1-minute history; winner `longPrice` between 16:00Z and resolution):**

| Event | Snapshot → resolution | Winner price in window |
|---|---|---|
| #1 Jul (Anthropic) | 16:00 → 22:23Z (383 min) | 0.99 throughout |
| #1 Aug (Anthropic) | 16:00 → 16:54Z (54 min) | 0.99 |
| #1 Sep (Anthropic) | 16:00 → 17:39Z (99 min) | 0.98 |
| China Jul (Alibaba) | 31 Jul 16:00 → 2 Aug 18:29Z (50 h) | 0.99 ask (bid 0.89–0.99) |
| China Aug (Alibaba) | 16:00 → 16:54Z | 0.99 |
| China Sep (Xiaomi) | 16:00 → 17:39Z | **0.87** |

After fee, 0.99 pays 0.93%, 0.98 pays 1.86% and 0.87 pays 12.2% per contract held to settlement. The tape is display prices, so depth in those windows is unknown. Right now, though, the Oct-31 books carry resting offers at **Google 0.98 × 40 and 0.99 × 480, and Xiaomi 0.96 × 113, 0.97 × 100, 0.98 × 100 and 0.99 × 25,203** (measured, `/book` 23:26Z). Whether those survive past 12:00 ET on 31 Oct is the single most useful thing to observe next.

**How the venue reads "Rank" (inference from the dataset):** If ties were scored the "Rank (UB)" way, where confidence intervals overlap, Alibaba (2–6 Aug), Meta (6 Aug) and Google (2–13 Sep) would each have tied for #1. That would have triggered `company1-dur2026` legs that in fact never resolved. Google resolved only when it became the outright highest score on 30 Sep. PMUS therefore behaves as if #1 means the highest Arena score, which is how a bot should model it.

**How often the leaderboard changes:** 6–10 publish dates a month (Jun–Oct, measured from the HF dataset). Company-changing #1 events since July:
- Overall: one (Google, 30 Sep).
- Chinese: two (Alibaba's Qwen3.8 jump on 2 Aug kept the same company; Xiaomi on 25–26 Sep).
- Coding: two (Google on 30 Sep, Anthropic on 22 Oct).

---

## Q3. Market-cap and stock-price markets: fair value from option implied vol

**The Tech tab has none.** The only equity-driven PMUS contracts are the Econ-tab Elon Musk net-worth ladders, because Bloomberg's figure is mostly TSLA plus SPCX. SpaceX listed in June 2026, ticker SPCX on EDGAR (measured).

The 31-Oct ladder settles on the figure for Friday 30 Oct, since 31 Oct is not a trading day.

**Inputs (measured):**
- CBOE delayed chains: TSLA 30-Oct ATM IV **0.395** (spot 372.45, 22:28Z 25 Oct); SPCX 30-Oct ATM IV **0.53** (spot 147.58, 24 Oct).
- 1-month realised vol: 0.35 (TSLA) and 0.64 (SPCX).

**Assumptions (inference):** about two-thirds of the net worth is in SpaceX and one-third in Tesla, with correlation 0.5. That gives a blended IV of about 0.43, so σ over the 5 trading days is about 6.1%. The ladder's own median is about $930B (P>900B ≈ 0.65, P>950B ≈ 0.31).

| Threshold (31 Oct) | PMUS bid/ask (measured 23:26Z) | Lognormal fair (inference) | Global PM bucket-implied (measured 23:30Z) |
|---|---|---|---|
| > $950B | 0.31 / 0.32 | ≈0.36 | ≈0.37–0.43 |
| > $1T | 0.12 / 0.13 | ≈0.12 | 0.12–0.20 |
| > $1.05T | 0.09 / 0.10 | ≈0.02 | — |
| > $1.1T | 0.04 / 0.05 | ≈0.003 | ≤0.055 |
| > $1.15T | 0.02 / 0.03 | ≈0 | — |
| > $1.2T | **0.04 / 0.05** (bids 400 @ 0.04, 517 @ 0.03, 532 @ 0.02) | ≈0 | 0.002 / 0.009 |

**Readings:**
- The middle of the ladder agrees with option-implied vol to within a few cents.
- The upper tail is rich. Buying No on >$1.2T at 0.96 earns about +3.5¢ a contract after the 0.27¢ fee if the fair value is right, roughly **$0.9 on a $25 clip**, and the global venue agrees the tail is under 1%.
- >$1.15T asks 0.03 against a >$1.2T bid of 0.04. That is a monotonicity violation, but only 27 shares deep.

**Risks:** Bloomberg's methodology (a revaluation of private holdings can move the figure by tens of billions overnight), the assumed composition, and a 24-to-1 payoff against the seller.

---

## Q4. Cross-venue: PMUS against global Polymarket and Kalshi

| Contract (rules matched on source and style control) | PMUS bid/ask (23:26Z) | Global PM (23:30Z) | Kalshi (about 23:36Z) |
|---|---|---|---|
| #1 end Oct – Google | 0.86 × 4 / 0.87 × 3 (real 0.42 / 0.90) | 0.838 / 0.858 | KXLLM1 0.86 / 0.87; KXTOPMODEL Gemini 0.84 / 0.88 |
| #1 end Oct – Anthropic | 0.01 / 0.03 dust (real ask 0.16–0.27) | 0.132 / 0.143 | 0.12 / 0.14 |
| #1 end 2026 – Anthropic | 0.48 / 0.49 dust (real 0.52 × 3.5, 0.55 × 342) | 0.53 / 0.54 | **0.56 / 0.57** |
| #1 end 2026 – Google | 0.37 / 0.38 × 5,071 | 0.35 / 0.36 | **0.305 / 0.306** |
| Best Chinese end Oct – Xiaomi | 0.61 / 0.62 (real 0.64–0.65) | 0.625 / 0.675 | — |
| Best Chinese end Oct – Moonshot | — / 0.31 × 4 | 0.25 / 0.30 | — |
| Chinese #1 by Dec 31 | **0.12 × 14,002 / 0.13 × 13,905** | 0.07 / 0.08 | KXBESTLLMCHINA unquoted |
| GPT Astra 6.1 by Oct 31 / Dec 31 | 0.11 / 0.12; 0.86 / 0.87 | 0.11 / 0.12; 0.84 / 0.86 | — |
| Claude 6 by Mar 31 2027 | 0.44 / 0.45 | 0.37 / 0.41 | — |
| Anthropic IPO by Nov 30 | 0.69 / 0.70 (rule includes pricing) | 0.63 / 0.64 (rule requires listed and trading) | — |

**A month of PMUS against Kalshi (measured; PMUS `INTERVAL_1M` 3-hour points against Kalshi hourly candle bid/ask, 25 Sep – 25 Oct, about 240 points each):**
- **PMUS Anthropic year-end runs a median 2.1¢ below Kalshi.** It was below in 90% of samples and more than 3¢ below in 28%.
- Google year-end has a median gap of −0.2¢, but in the last day it opened to +4–7¢ rich on PMUS.
- OpenAI year-end matches (+0.3¢).
- Oct-31 Google shows a median of −3¢, which is unreliable because PMUS's display prices are dust.

The one persistent, one-sided, size-backed gap is **PMUS "Chinese #1 by Dec 31" at 0.12/0.13 against global 0.07/0.08**. On PMUS you can buy No at 0.88 for up to about 14,000 contracts. If the global price is right, the expected value is about +3.8¢ a contract after fee, or 4.3% locked until mid-January (inference; the closest a Chinese model has come since June was Qwen3.8-Max, 8 points behind on 6 Aug; the best Chinese model is now 35 points behind).

Two practical limits:
- US persons can only view global Polymarket, so it is a signal source.
- A PMUS–Kalshi hedge on the year-end market costs about 3.5¢ round trip and nets 0–3¢ at today's gaps, with a 10:00 ET (Kalshi) against 12:00 ET (PMUS) snapshot mismatch.

---

## Q5. Is there enough liquidity for $1–$25 clips?

**Yes for the binary "by date" markets; no for the Arena monthly markets that settle soonest.**

- **Release, IPO-date, CEO and policy binaries** (B, C dated legs, D, E) are 1¢ wide with 1,000–18,000 shares at the touch. A $25 clip fills at the displayed ask.
- **The year-end Arena lead legs** take $25 at the touch: Google 0.38 × 5,071, Anthropic coding 0.70 × 201, Chinese-#1 0.13 × 13,905.
- **The Oct-31 Arena legs are a few shares deep at the touch, then 3–48¢ gaps:**
  - Google Oct-31: $25 of Yes fills at an average 0.895; $25 of No at 0.557, meaning the next bid after 0.86 is 0.42.
  - Xiaomi: $25 fills at 0.638.
  - Moonshot: $25 fills at 0.586.
  - Anthropic Oct-31: $25 fills at 0.35.
- **Longshots in multi-outcome events have no bids at all.** 34 of 103 markets are one-sided.

All measured, `/book`, 23:26Z, `liq_rows.json`.

The worker therefore needs `/book` (or the WebSocket full-book stream) and a VWAP cap on every order. Neither the listing quotes nor `/bbo` sizes can be trusted.

---

## Ranked strategies

| Rank | Strategy | Verdict | Realistic $ at $135 | What the worker needs | Main risks |
|---|---|---|---|---|---|
| 1 | **Arena settlement-window yield.** After the 12:00 ET snapshot, buy the decided winner of the month-end #1 and best-Chinese markets at ≤0.98–0.99 (occasionally lower) and hold to settlement 1–50 h later | **Test** (watch 31 Oct read-only first), then Build | Typically $0.25–0.50 per settlement per $25 clip; $1–9 when stale 0.96–0.98 offers survive (they rest there now); about $1–5 a month for 2 settlements, more at year-end (4 Arena events on 31 Dec) | Live arena.ai read at 16:00Z (residential IP or headless browser; Cloudflare blocks datacentre IPs), model→company map, ordinal-#1 rule, `/book` VWAP-capped IOC, settlement-latency log | Failed or misread leaderboard; an update landing between the last read and 12:00 ET; offers pulled at the snapshot; capital locked until clearing; a resolution dispute |
| 2 | **Arena update snipe.** Poll the leaderboard every 30–60 s; on a change in company ranking, reprice every Arena leg from a score/vote model and take mispriced legs in the first 1–10 min | **Test** | $2–10 a month (about 1–2 company-changing updates a month across A1–A6; each gave roughly 10–40 minutes of prices 10–50¢ from final on thin books) | Same reader plus a fair-value model (score gap, CI, vote accrual); WebSocket market data so the 30 s `/bbo` cache does not eat the window; multi-leg IOC | Repricing starts within 1–4 min, so faster bots are present; dust books cap fills at tens of shares; rumour spikes (the 25 Sep Xiaomi false start); rule edge cases |
| 3 | **Fade rich tails in the Elon net-worth ladders** (Econ tab): buy No at ≥0.95 on month-end thresholds about 25%+ away, priced against TSLA/SPCX option IV | **Test, small** | About $1–3 per month-end ladder (e.g. >$1.2T No at 0.96: +3.5¢ × 26 contracts ≈ $0.9 per $25) | Yahoo/CBOE reads for spot and IV, a net-worth composition estimate, IOC on No | Bloomberg methodology or revaluation jumps; a wrong composition; one loss erases about 25 wins |
| 4 | **Cross-venue lean.** Buy PMUS No on "Chinese #1 by Dec 31" at 0.88 (global 0.07/0.08); buy PMUS year-end Anthropic only at ≤0.53 when Kalshi is ≥0.56 | **Test** | About $1–3 over 2.5 months per $25 clip (≈4% expected, locked until 15 Jan) | Read-only gamma and Kalshi feeds, price-gap rule, patience | Venues may be pricing different rules (snapshot time, tie rules); the gap is a signal, not an arbitrage; capital tied up until January |
| 5 | **EDGAR IPO watcher** (Anthropic public S-1, EFFECT, 424B4) | Test only if cheap | Unknown; at most a few dollars, once | EDGAR FTS/Atom poll at ≤10 req/s with a User-Agent | Heavily watched headline repriced in seconds; the PMUS trigger (pricing) differs from global's (listing) |
| 6 | Model-release detection (GPT Astra 6.1, Claude 6, Grok 5, GPT-7) | **Skip** | ≈$0 | — | Resolution turns on "general public" interpretation; GPT-6 and Sonnet whipsawed for a day or more after the news |
| 7 | Sum-of-asks / full-set arbitrage in multi-outcome Arena events | **Skip** | Negative | — | The displayed sum (0.80, 1.01) is dust; a real set costs 1.10–1.16 |
| 8 | Mag-7 caps, stock prices, earnings, launches, deliveries, App Store | **N/A** | $0 | — | Not listed (App Store: one closed pair) |
| 9 | Worker upgrades | WebSocket **Build** if 1 or 2 goes live; resting orders **Skip** for Arena | — | WebSocket book stream; `/book` depth on every decision | Resting bids on thin Arena books are filled mostly when a leaderboard update has just made them wrong |

**Overall:** Tech is a small, slow tab for a taker bot. Its one structural feature is that ten events settle on a single public page that updates a few times a week, with PMUS taking minutes to tens of minutes to absorb each update. Turning that into money needs a reliable live leaderboard read, which this survey could not obtain from a datacentre IP, plus `/book`-aware sizing. Even then the ceiling is in the low tens of dollars a month. The cheapest next step costs nothing: on **31 Oct, 15:30–18:00Z**, poll `/book` for `aimrc-company1-2026-10-31-google` and `aimrc-cmpny-china-1-2026-10-31-xiaomi` every 30 s to see whether the 0.96–0.99 offers survive past the snapshot, and record when PMUS settles.
