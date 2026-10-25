# Home tab: the platform and automation layer every category shares (Polymarket US, as of 2026-10-25)

Labels: **[M]** measured (endpoint, UTC time), **[C]** cited (URL, date read), **[I]** inference. Read-only work. Nothing was authenticated, no orders were sent, and no repo code or git state was touched. Raw extracts are in `home_data/` beside this note (180 KB). This note builds on `reports/Polymarket US worker edge survey.md` and its notes and does not redo them. Where it disagrees with them, it says so in the last section.

## Takeaway

The venue offers a small account no informational edge. It does, however, run a subsidy that the earlier survey did not evaluate. The **Liquidity Incentive Program pays resting orders whether or not they fill**, sets no minimum account size, and scores size in *contracts* rather than dollars. On the 174 rewarded books sampled tonight, **105 of 348 market-sides had not reached the program's aggregate target size**, so that side's pool was going unpaid. Posting on the cheap side of a lopsided book turns $135 into thousands of contracts. On paper, a greedy $135 allocation across the sample earns **$11/day under a conservative reading of the pool rules and $51/day under the per-event reading the changelog implies**. That excludes a one-off Toronto-mayor pool. Realistically, after fills, competition and rule changes, it is **$2–15/day with a real chance of about $0**. That makes it the top item to *test*, ahead of the finish-line settlement-yield rule ($1–3/day in college-basketball season, already in `finish.py`). Two corrections to the existing worker come first because they cost hours and protect everything else:

- **Tick-size bug.** `account.order` formats every limit price to two decimals, but NFL moneylines tick at 0.0025 and CFB at 0.005. An NFL ask of 0.9975 becomes the invalid price "1.00", and a CFB ask of 0.985 becomes "0.98", which sits below the ask and never fills.
- **Compliance layer.** The worker needs the kill switch, throttle and audit trail that Rulebook 5.2(i)/(h) require, plus written API approval under Participant Agreement §19.

The WebSocket is worth building second. Contrary to the earlier survey, the worker's main listing path is *not* edge-cached; only its depth reads are.

## 1. What Home shows, and how the ten nav tabs map to the API

**Home page structure** [M: `https://polymarket.us/` HTML/RSC payload, 2026-10-25 23:19Z]. The sections are:

- **Featured markets** carousel. Five events: three of today's NFL games, `usho-midterms-2026-11-03` (House control) and `usse-tx-2026-11-03`.
- **Trending markets** rail. Five moneylines: four NFL, one NBA.
- **Popular leagues** rail. This is `GET /v2/tags/featured`, which returns 30 tags with `eventCount`.
- **Popular** grid, then an **NFL** section and a **Midterms** section.

There is **no "New" or "Breaking" section**. A `hide-from-new` tag exists on 32 recurring crypto and 6 metals events, which implies a "new" sort somewhere in the app [M]. `GET /v1/events?featured=true` returned 0 events, so the carousel is curated outside the public events filter [M, 23:20Z]. For sports, the documented `GET /v1/sports/{seriesId}/events?section=trending` endpoint has "the same structure as home page" [C: docs.polymarket.us/api-reference/sports/get-sports-events.md, read 2026-10-25].

**Tab → route → API mapping** [M: routes from `data-nav-tab` attributes on the home page; counts from `GET /v1/events?closed=false&limit=500&offset=0..4500`, fetched 2026-10-25 23:16Z, 4,861 open events; tag membership checked against `/v2/tags/featured` `eventCount`, which matched within ±3]:

| Tab | Web route | Gateway selector (use `tagSlug=` or tag walk) | Gateway `category` values inside | Open events | Primary open markets* | All markets (`marketCounts.numMarkets`) | Two-sided (listing) | Median spread | ≤1¢ | Live now | Reward program code(s) → listed pool/period† |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **Home** | `/` | none (all) | all 10 | 4,861 | 25,400 | 72,690 | 51% | 1¢ | 59% | 78 | all: $71,326 over 197 programs |
| **Midterms** | `/midterms` (+ `/midterms/key-races`, `state-by-state`, `national-outcomes`, `downballot`, `local-races`, `race-props`, `combos`, `top-issues`, `polymap`, `all-markets`) | tag `midterms` | politics 1,198 | 1,198 | 6,449 | 6,449 | 32% | 2¢ | 48% | 0 | POL `midterms_*`, `elections_boosted_*`, `politics_t4_coverage`: ≈$1,377 |
| **Sports** | `/sports` (`/sports/{league}`, `/sports/{league}/{event}`) | `category=sports` (tag `sports`; leagues via `/v2/leagues/{slug}/events`) | sports 3,316 (+1 finance) | 3,317 | 14,894 | 62,184 | 63% | 1¢ | 64% | 40 | SPR: $67,484 (live $62,033) |
| **Crypto** | `/category/crypto` | tag `crypto` / `category=crypto` | crypto 57 (+1 politics) | 58 | 1,540 | 1,540 | 28% | 5¢ | 10% | 32 | CRY: $400 |
| **Commodities** | `/category/commodities` | tag `commodities` | finance 6 (gold/silver Up/Down), macro 5 (US gas, beef) | 11 | 45 | 45 | 60% | 1¢ | 78% | 6 | MAC `usgas_daily_ladder`: $200 (+ part of `macro_low` $15) |
| **Politics** | `/category/politics` | tag `politics` (superset of Midterms) | politics 1,245, geopolitics 4, macro 1 | 1,250 | 6,815 | 6,815 | 34% | 1¢ | 52% | 0 | POL (non-midterm) ≈$1,000 + GEO $15 |
| **Weather** | `/category/weather` | tag `weather` | climate 21 | 21 | 119 | 119 | 46% | 2¢ | 44% | 0 | CLI: $185 |
| **Tech** | `/category/tech` | tag `tech` | technology 10, finance 4, politics 2 | 16 | 103 | 103 | 67% | 1¢ | 99% | 0 | TECH: $100 (two programs) |
| **Culture** | `/category/culture` | tag `culture` | culture 149, science 4, finance 1, politics 1 | 155 | 1,699 | 1,699 | 29% | 4.5¢ | 44% | 0 | CUL $365 + SCI $60 |
| **Econ** | `/category/economics` | tag `economics` | macro 39, finance 9, politics 2 | 50 | 278 | 278 | 71% | 1¢ | 82% | 0 | MAC `macro_high` $75, `macro_strategic` $50 |

\* Since 2026-10-15, `GET /v1/events`, `/v2/leagues/{slug}/events` and `/v2/sports/{slug}/events` return **only each event's primary market**. Spreads, totals and props need `GET /v1/events/{id}` or `/v1/events/slug/{slug}` [C: docs.polymarket.us/changelog.md, entry 2026-10-09, read 2026-10-25]. Counts of "markets" built from the listing are therefore primary-only. Use `marketCounts.numMarkets` for totals.
† Pools are from the rewards page payload [M: `https://polymarket.us/rewards`, 23:21Z]. They are per time period. Whether a pool is per event or shared across all listed markets is ambiguous; see §3.2.

Notes for the other nine agents:

- **Tabs are tag-driven; categories are the gateway's coarse buckets.** The gateway's 10 `category` values are sports, politics, culture, crypto, macro, climate, finance, technology, geopolitics and science [M]. The web tabs use tags, which cut across categories. Commodities is finance plus macro. Econ includes Elon Musk net-worth, the Anthropic CEO market and 2026 IPOs. Tech includes finance-category AI-company markets. "aliens" appears on both Politics and Culture.
- **Filter parameters** on `GET /v1/events` include `tagSlug`, `tagIds`, `categories`, `live`, `ended`, `featured`, `seriesId`, `sportsMarketTypes`, `startTimeMin/Max` and `finishedTimestampMin/Max` [C: docs.polymarket.us/api-reference/events/get-events.md, read 2026-10-25].
- **Fee coefficient** is 0.0695 on every listed primary market except **408 table-tennis markets at 0.10**, the first time 0.10 has been observed live. **Tick sizes**: 0.01 on 24,262 markets, 0.001 on 902, 0.005 on 203. Major-league moneylines tick at NFL 0.0025, CFB 0.005, MLB 0.005, and NBA/NHL 0.01 [M: listing, 23:16Z].
- **Reward program category codes** are SPR, POL, CRY, MAC, CUL, CLI, TECH, SCI and GEO. The institutional refdata uses `eventCategory` (e.g. `CRY`; metals are `FIN`/`COMMODITY`) [C: changelog 2026-10-22].
- **Undocumented 5-minute crypto windows.** `btc-`, `eth-`, `sol-` and `xrp-updown-5m-*` events are open (earliest current one created 2026-10-25 12:00Z), but the Crypto FAQ lists only 15- and 60-minute windows [M; C: docs.polymarket.us/faqs/crypto-faqs.md].

## 2. The automation toolkit as of 2026-10-25

**Authentication.**
- API keys are self-serve at polymarket.us/developer after in-app KYC. The signature is Ed25519 over `timestamp + method + path`, carried in the `X-PM-Access-Key`, `X-PM-Timestamp` and `X-PM-Signature` headers. The timestamp must be within **30 s** of server time [C: docs.polymarket.us/api-reference/authentication.md, read 2026-10-25]. `account.Signer` already does this correctly.
- **Approval.** Participant Agreement v1.4 (updated 2026-08-06) §19 still says you "shall not access or use the System in a live production environment unless and until you have received written approval to do so" [C: polymarketexchange.com/files/legal/latest/participant-agreement, read 2026-10-25]. The docs describe no approval step beyond creating a key. [I] One email to support@polymarket.us that describes the bot covers §19, and it is the same email the Rate Limits page asks for when requesting higher limits.

**Market data.**
- **Public gateway** (`gateway.polymarket.us`, no key) covers events, markets, `/bbo`, `/book`, `/v1/price-history`, `/settlement`, tags, series, sports and leagues.
- **Edge caching, measured 2026-10-25 23:21–23:31Z:**
  - Cached with `Cache-Control: public, max-age=30`: `/v1/markets/{slug}/bbo` and `/book` (`CF-Cache-Status: HIT`, Age 12–29), the `/v1/events` listing and `?slug=` (HIT), and `/v1/price-history` (MISS on a first read).
  - **Not cached:** `/v2/leagues/{slug}/events` returned `CF-Cache-Status: DYNAMIC` with no Cache-Control.
  - The cache key includes the query string: a `/bbo` request with an extra unique parameter was a MISS and returned a `lastPriceSample.ts` 12 s newer than the cached copy. [I] That is a way around the cache, but it defeats the CDN and draws on the shared 25 req/s per IP. The documented route is the WebSocket.
- **Markets WebSocket** `wss://api.polymarket.us/v1/ws/markets` needs authentication, with the handshake signed over `timestamp+"GET"+path`. It offers:
  - `SUBSCRIPTION_TYPE_MARKET_DATA`: full book and stats.
  - `MARKET_DATA_LITE`: BBO, level counts, last trade and OI.
  - `TRADE`: prints with maker and taker side.
  - Up to **100 markets per subscription**, an optional `responsesDebounced` flag, and server heartbeats.

  Market states include SUSPENDED, HALTED and `MATCH_AND_CLOSE_AUCTION` [C: docs.polymarket.us/api-reference/websocket/markets.md and overview.md, read 2026-10-25].
- **Private WebSocket** `/v1/ws/private` streams ORDER, ORDER_SNAPSHOT, POSITION (before/after positions with decimal fields), ACCOUNT_BALANCE and RFQ. Leave `marketSlugs` empty to get all markets [C: …/websocket/private.md].
- **Python and TypeScript SDKs** exist (`polymarket_us`, `polymarket-us`) and include a websocket module [C: …/sdks/python/websocket.md].

**Orders (Retail API, `api.polymarket.us`)** [C: …/orders/create-order.md and the orders overview, read 2026-10-25].
- **Types and time in force.** `LIMIT` or `MARKET` (market orders take `cashOrderQty` and `slippageTolerance`). TIF is `DAY`, `GTC`, `GTD` (with `goodTillTime`), `IOC` or `FOK`.
- **Post-only**: `participateDontInitiate` (rejected if it would match).
- **Other request fields**: `synchronousExecution` with `maxBlockTime`; `manualOrderIndicator` AUTOMATIC; `intent` or `outcomeSide` with `action`.
- **Endpoints**: preview, modify, cancel, batched create/cancel/modify, **cancel-all** (`POST /v1/orders/open/cancel`, optionally by slug), and **close-position** (`POST /v1/order/close-position`).
- **Portfolio**: `/v1/portfolio/positions`, `/v1/portfolio/activities` and `/v1/account/balances`. Incentive earnings are at `/v1/incentives/earnings`, and the authenticated program schedule at `/v1/incentives`.
- **Not on the Retail API** [C: …/institutional/fix-api/fix-stop-orders.md, fix-self-match-prevention.md, fix-session-management.md]: stop orders, conditional orders, self-match-prevention IDs and cancel-on-disconnect. All four exist only on institutional FIX. [I] A retail bot must build its own dead-man switch. Short-dated **GTD** orders (e.g. 15–60 minutes, re-posted) are the natural substitute.

**Limits and failure modes.**
- **Rate limit**: 25 req/s per source IP *and* Cloudflare location, shared across keys. RFQ and combo endpoints are limited to 1 req/s. On a 429, wait ≥1 s and back off exponentially. Under load, a **5-second latency stopgap** rejects orders with the message "Global Rate Limit Exceeded", which is not a real rate limit. Pure cancels are never rejected this way [C: …/api-reference/rate-limits.md, read 2026-10-25].
- **Maintenance**: every Thursday 6–8 AM ET (exchange since 2026-09-24; clearinghouse standing window since 2026-10-15, when deposits and withdrawals are also off). All open orders are cancelled before it, the API returns 503, and books reopen empty [C: docs.polymarket.us/faqs/general-faqs.md; Clearinghouse Notice 2026-10-14 PDF]. The trading day ends at 5 PM ET. Gold and silver trade Sunday 6:15 PM to Friday 5 PM ET with a daily 5:00–6:15 PM ET break [C: …/trading-hours.md].
- **Outages are frequent enough to design for** [M: `status.polymarketexchange.com/api/v2/incidents.json`, 23:30Z]. Since 2026-06-01 there have been 10 "critical" incidents, nine of them matching-engine or systems-offline, lasting 16–299 minutes; the longest were 245 min on Aug 27 and 299 min on Sep 5 ("Open orders will be cancelled"). There has been none since Sep 5. Other incidents: "Resolutions payouts delayed" for 23 min (Aug 28), "Position holdings degraded… delays on positions and resolutions" for 59 min (Oct 9), and "Position streaming delayed" for 10 min (Sep 13).

**Rulebook duties for automated systems.** The current Rulebook is dated **September 30, 2026** (file last-modified 2026-10-02) [C: polymarketexchange.com/files/legal/latest/rulebook, read 2026-10-25]. The earlier survey cited the March version; the relevant text is unchanged:
- **5.2(h)**: keep an electronic audit trail "capturing order entry, modification, cancellation, and execution timestamps sufficient to reconstruct all trading activity".
- **5.2(i)**: automated systems "must implement pre-trade risk controls including order throttles, price collars, and kill switches".
- **5.3(b)–(c)**: the exchange may cap order rates, and participants must have controls against excessive messaging.
- **5.3(d)**: no orders without sufficient funds.
- **7.2(q)**: no self-matching across commonly controlled accounts, "whether Orders are entered directly, via API, or through an FCM".
- **7.2(m)**: no structuring of orders to evade surveillance; a pattern can be a violation even if each order is permissible.
- **7.2(n)**: no orders creating a "false, misleading, or artificial appearance of activity".
- **3.15**: incentive-program modifications take effect no earlier than 10 business days after a 40.6(a) filing.

**New since 2026-10-23.**
- No new changelog entries. The RSS feed's latest item is 2026-10-22 (gold and silver Up/Down markets, which populate the Commodities tab) [C: docs.polymarket.us/changelog/rss.xml].
- Notices [C: docs.polymarket.us/notices-and-filings.md]:
  - **PMX-2026-64** (filed 2026-10-23, effective 2026-11-06): rebate tiers move to a trailing 30-day window. Thresholds, coefficients and the zero maker fee are unchanged, so it does nothing at $135.
  - Amended Deposit Incentive Program (2026-10-21).
- The fee page still shows the Oct 19 schedule: taker 0.0695, table tennis 0.10, maker rebate only from $10M of monthly maker volume [C: docs.polymarket.us/fees.md, read 2026-10-25].
- Table tennis at 0.10 is now live on 408 markets [M].
- A Toronto-mayor reward program was created on 10-23 [M].

## 3. Cross-category mechanics

### 3.1 New listings open empty and tighten over hours

Method [M: `GET /v1/price-history?fidelity=1&fixedInterval=INTERVAL_ALL` for 76 markets created 3–72 h before 2026-10-25 23:16Z; summary in `home_data/new_listing_tapes_2026-10-25.json`]. The tape is [long ask, short ask] per minute. "Tight" means the two asks sum to ≤1.03.

| Group (n) | First tape minute after creation (median) | Sum of asks at first minute | Minutes to first tight book | Never tight | |Δmid| over the 3 h after tightening |
|---|---|---|---|---|---|
| Sports fixtures (14) | 1.3 min | 1.94 (empty) | 836 min (n=7) | 6 of 13 | 2¢ |
| US gas daily ladder (14) | 229 min | 1.44 | 245 min | 1 | 10¢ |
| Weather daily (14) | 254 min | 1.17 | 272 min | 2 | 7¢ |
| New politics (14: Toronto, Knesset, Trump approval) | ~1,600 min | 1.29 | ~1,900 min | 3 | 2¢ |
| Metals (6) | — | 1.39 | 677 min (n=2) | 2 | — |

New listings are **not opened at a fair price by a maker**. They open empty or placeholder-wide and get filled in over hours. Creation is dominated by sports fixtures and recurring products: 1,311 events were created on 10-25, of which 1,290 in 24 h were sports, while bespoke non-sport listings run at about 1–2 a day [M]. [I] For a taker there is nothing to buy. For a maker, the first hours are an adversely selected book where the informed party is whoever has the model (gas, weather). The one clean way to be paid for being first is the LIP "early" pre-game periods (SPR early programs total $645), which pay resting size whether or not it fills.

### 3.2 Liquidity rewards: the one subsidy a small account can reach

**Rules** [C: docs.polymarket.us/incentives/liquidity.md and polymarket.us/rewards, read 2026-10-25].
- Every second a random book snapshot is scored at `DF^(ticks from best) × size`, with each side normalized to 1.0 *if aggregate resting size on that side reaches Target Size*.
- "Programs without a Max Spread score each side on its own, even if the other side is empty". Only 6 of 197 programs set a Max Spread [M].
- There is no per-trader cap, a $1.00 minimum payout, and payment within 5+2 business days. Nothing is paid for cancelled or postponed games. The overview lists the program as "Open… No signup or application needed" [C: …/incentives/overview.md].
- The rewards page says the pool is "shared across the program's markets — never summed per market". The changelog prices pools "per match" (ITF $300, cricket $500 split $25/$75/$400) and per event ("$2,500 … distributed pro-rata across eligible instruments"), and the page labels politics periods "Daily (per event)" [C: changelog, Jun–Jul 2026 entries]. [I] The pool is most likely per event per period. The earlier survey's "$52 across 338 ITF markets" reading is the conservative lower bound.

**Schedule tonight** [M: rewards page payload, 23:21Z; `home_data/rewards_programs_2026-10-25.json`]: 197 programs covering 85,229 market symbols with a listed $71,326 per period. Sports live periods carry $62,033 of it; politics $2,377; crypto $400; macro $340; culture $365; climate $185; tech $100; science $60; geopolitics $15.

**Can $135 earn anything?** [M: `GET /v1/markets/{slug}/book` for 174 markets in 23 non-sport programs with target sizes of 500–25,000, up to 8 per program, 23:22–23:24Z; `home_data/lip_capture_sample_2026-10-25.json`.]
- **Model.** My order joins the current best price on one side, *behind* existing orders at that price (time priority). Budgets are $5–$100 per side. Collateral is the price for bids and 1 − price for offers.
- **Unmet targets.** 105 of 348 sampled sides, including sides with no orders at all, had not reached Target Size, so those pools were being forfeited.
- **Cheap side.** On lopsided books, $50 posts 5,000 contracts at 1¢ collateral. Example: Toronto mayor, Bradford YES bid side, best bid 0.01 with 1,000 contracts against a 2,000 target. $10 of 1¢ bids qualifies the side and takes about half of it.
- **Greedy $135 allocation:**

| Reading of pool | All sampled | Excluding Toronto (expires 10-26) | Excluding Toronto, only sides on books ≥5¢ wide (low fill risk) |
|---|---|---|---|
| Conservative (pool ÷ all listed markets) | $48/day | **$11/day** (18 sides) | $3.5/day ($95 used) |
| Per-event (pool ÷ markets in the event) | — | **$51/day** | $21/day |

[I] These are paper numbers on one snapshot of eight markets per program. The haircuts:
1. Others re-quote once the side is paid.
2. Fills turn collateral into a position held to settlement. Many of these markets expire 2026-12-31 or later.
3. Pools, target sizes and Max Spread change by period. Max Spread was introduced on 2026-09-15 explicitly to stop one-sided far-from-mid quoting, and it already covers the UTR and Senate-map programs.
4. Sides earning under $1 per period are not paid, so effort should concentrate by program.
5. Rule 7.2(n) and the programs' anti-gaming language create a surveillance risk for quotes that exist only to farm.

A realistic range is **$2–15/day, with a real chance of about $0**. Even so, it is the largest expected value available to this account, and it costs only capital the account is not using. Whether rewards are credited as cash or as non-withdrawable promo credit is not documented.

### 3.3 Promotions [C: docs.polymarket.us/incentives/user-programs.md, read 2026-10-25]

- **Deposit and Trading Incentive Program.** Campaigns L, M, N and O are live: deposit $1,000/$500/$100/$50 and receive $250/$100/$25/$10, "based on prior deposit and trading activity". Re-activation campaigns A–H ended on 10-25. The trading leg counts only fills at $0.10–$0.90.
- **Deposit Incentive Program**: $25 for a first deposit of $10 or more, new users only.
- **Refer-a-Friend**: $25 to each side, up to 50 referrals. Self-referral voids it.
- All of these pay **promotional trading credits**: usable for positions and fees, not withdrawable, and spent after existing collateral. [I] If the app shows the account Campaign N, a $100 top-up worth $25 of credit is the cheapest "bigger account" available. None of these programs is an automation strategy.

### 3.4 Capital lockup and settlement latency

- **Collateral.** Long positions post 100% of the price and short positions 100% of 1 − price. There is no release on favourable moves. Resting orders lock collateral per instrument, and a fill elsewhere can auto-cancel orders that become unfunded [C: docs.polymarket.us/market-structure/collateral-and-margin.md; earlier survey].
- **No yield** on idle cash.

| Category | Settlement timing | Source |
|---|---|---|
| Sports games | Winner ask reaches 1.00 a median 0.77 min after the recorded finish (NBA/NHL/CBB); 22–55% not settled within 15 min (NHL/NFL/CFB); tennis never settled within 15 min. Cash-credit latency unmeasured | [M] earlier survey tape |
| Crypto Up/Down / ladders | ~1 min / ~15 min | [C] crypto FAQ |
| Gold / silver Up/Down | ~1 min after Chainlink publishes the close | [C] metals FAQ |
| Weather daily | 8:00 AM ET the next day; up to 11:00 AM if the CLI and METAR disagree | [C] docs.polymarket.us/faqs/weather-faqs.md |
| US gas daily | `payoutEstimateTime` 2026-10-26T14:00Z (`AAA_DAILY_UPDATE`); the only open event carrying the field | [M] listing |
| Politics / midterms | After certification; House endDate 2027-02-02 | [C] earlier survey |
| Futures and long-dated (Dec 31 / 2027) | At expiry | [C] market rules |
| Any category during an incident | Resolution payouts were delayed 23–59 min on Aug 28 and Oct 9 | [M] status API |

[I] For the $135 account, the binding constraint is the **number of dollars simultaneously locked**, not edge per trade. Finish-line clips recycle within minutes. LIP fills on long-dated markets do not, so LIP quoting should prefer markets that settle within days, or sides where a fill is cheap: 1–5¢ collateral per contract.

### 3.5 Official tools that matter

| Need | Available on Retail? |
|---|---|
| Auto-cancel | Yes. The venue cancels all orders before maintenance, on clarifications, and when an order becomes unfunded; it does not cancel on disconnect |
| Dead-man switch | Build it: GTD orders with a short `goodTillTime`, plus `POST /v1/orders/open/cancel` |
| Stop or conditional orders | No (FIX only) |
| Self-match prevention | No (FIX only) |
| Batch create/modify/cancel | Yes |
| Close position | Yes |
| Portfolio / activities / balances | Yes, REST and private WS |
| Incentive schedule and earnings | Yes (`/v1/incentives`, `/v1/incentives/earnings`, authenticated) |
| Settlement read | Public `/v1/markets/{slug}/settlement` (404 until settled) |

## 4. Architecture: the ideal small-account worker, and the delta from the current one

**What the worker does today** (read 2026-10-25):
- **Data path.** `worker.py` polls `/v2/leagues/{nfl,nhl,cfb,nba}/events` every 45 s while a game is live and every 180 s otherwise. This endpoint is **uncached** [M], so top-of-book is 0–45 s old plus request time. The finish rule's depth comes from cached `/bbo` (`source.depth`, `source.py:347`), so it is up to 30 s staler than the price it accompanies.
- **Order path.** Rules → `orders.place` → `account.order`: a limit at the logged ask, IOC, `synchronousExecution`, with `maxBlockTime` 10 s.
- **Controls.**
  - Mode and arming phrase come from environment variables. On the always-on box, changing them needs a service restart.
  - Caps: $25 per order, $100 per day, $250 open. The open cap is above the account size, so it never binds.
  - Stop: $50 loss over 3 days. Floor: 50% of the bankroll or of peak equity.
  - Ledger: one sealed row per order, stamped `placed_at` at 1-second resolution, with no exchange timestamps or execution IDs.
  - Git commit and push on every tick that changes the record.

**Concrete defects to fix first.**
1. **Tick rounding** (`account.py:101`). `f"{price:.2f}"` breaks on 0.0025- and 0.005-tick markets [M: NFL moneylines 0.0025 (33 open), CFB 0.005 (201)]. Long buys: 0.9975 → "1.00" (invalid), 0.985 → "0.98" (below the ask, no fill), 0.8525 → "0.85" (below the ask). Short buys round unpredictably in the other direction. Fix: round toward marketable to `tick` (ceil for long, floor of 1 − ask for short), send 4 decimals, and refuse prices outside [tick, 1 − tick]. `source.quotes` already captures `tick`.
2. **No college basketball** (`source.py:70–75`). `LEAGUES` lacks `cbb`. CBB games are not listed yet (only the `cbb-champ` future is open [M]), but CBB was the finish rule's largest source in the earlier survey (median 32.5 settled games/day). Add the league as soon as games list, around the first week of November.
3. **Favorites live orders.** The rule measured at about −1 point late in games. Set `LIVE_RULES=finish` only.

**Target design (small account, single process, one IP).**
- **Data path.**
  - (a) Keep the uncached `/v2/leagues/{slug}/events` poll at 30–45 s as the game-state source (`live`, `period`, `ended`), with a free score feed as a cross-check for "final".
  - (b) Authenticated markets WS: `MARKET_DATA_LITE` for every live moneyline (one subscription per 100), and `MARKET_DATA` (full book) for finish candidates and every market the bot quotes. This replaces the cached `/bbo` and `/book` reads.
  - (c) Private WS for ORDER, POSITION and ACCOUNT_BALANCE: real fill reports, plus a direct measurement of fill-to-settlement-credit minutes per league.
  - (d) `GET /v1/incentives` hourly to pick reward-program targets, and `/v1/incentives/earnings` daily to verify payment.
  - (e) Poll `status.polymarketexchange.com` every 5 min.
- **Order path.**
  - Takers: tick-correct IOC, sized to the depth at or under the limit from the WS book. Use FOK when a partial fill would be worse than none.
  - Makers (LIP): post-only (`participateDontInitiate`) GTD orders with `goodTillTime` 30–60 min, refreshed by batch modify. Re-post after the Thursday 08:00 ET reopen and after any SUSPENDED → OPEN transition.
  - A `cancel-all` path behind the kill switch.
- **Risk controls** (5.2(i)):
  - Throttle: ≤10 order messages per minute and ≤2 per second.
  - Price collar: a limit within 1 tick of the WS best at send time; never above 0.99 or below 0.01.
  - Exposure: per-market cap; total collateral (resting plus unsettled) ≤ 90% of equity read from the private WS.
  - Kill switch: a file or flag checked every loop, plus a SIGTERM handler, both of which cancel all orders and stop.
  - Auto-kill after 3 consecutive rejects, on a balance mismatch against the ledger, or on an open status incident.
  - No new orders 10 minutes before maintenance.
  - Keep the existing loss stop and floor.
- **Logging** (5.2(h)): an append-only JSONL file per request and response, recording local send and receive timestamps, `transactTime`, order ID, and execution IDs with `lastPx`, `lastShares`, aggressor flag and commission. Log cancels and modifies too. Reconcile daily against `/v1/portfolio/activities`. Keep the sealed weekly ledger as the owner-facing summary.
- **Compliance.**
  - Email support@polymarket.us describing the bot. This gets written approval on file under §19 and opens the higher-limits path.
  - Run exactly one account. 7.2(q) makes a second account an unnecessary risk.
  - Keep `manualOrderIndicator=AUTOMATIC`.

**Honest cost and benefit of each upgrade.**

| Upgrade | Cost | Benefit |
|---|---|---|
| Tick fix | ~1 hour | Unblocks NFL, CFB and MLB orders |
| Compliance layer | ~½ day | Protects the account; no edge |
| WebSocket (markets + private) | 1–2 days, plus reconnect, heartbeat and 503 handling | Removes the 30-s cache from depth reads; turns the finish rule from a ~45-s poll into seconds-level reaction while asks still sit below 1.00 (that window closes a median 0.77 min after the finish); measures cash-lock time. [I] Worth perhaps +$0.3–1/day in CBB season and required for safe LIP quoting |
| LIP quoter | ~1–2 days on top of the WS | The largest upside ($2–15/day realistic) |
| External score feed | $0 for public league JSON; $30–59/month for The Odds API | Earlier "final" signal |
| Bigger account | — | LIP and the finish rule both scale roughly linearly until share or depth binds. Not worth it until a week of realised P&L is positive |

## 5. Ranked strategies and upgrades

| Rank | Strategy / upgrade | Verdict | Realistic $ at $135 | What the worker needs | Main risks |
|---|---|---|---|---|---|
| 1 | LIP quoting: post-only GTD on unmet or thin sides of no-Max-Spread programs, cheap side first (1–5¢ collateral), short-dated markets preferred | **Test** ($20–50 for 7 days, then read `/v1/incentives/earnings`) | $2–15/day; paper $11–51/day; could be ~$0 | Resting orders (`participateDontInitiate`, GTD), `/v1/incentives` schedule, WS full book, batch modify, cancel-all, re-post after maintenance, per-side inventory cap | Pool semantics unverified; fills lock capital to expiry; Max Spread or target changes; competitors re-quote; $1 minimum payout; surveillance view of farm-only quotes (7.2(n)); credit may be non-cash |
| 2 | Finish-line settlement yield (`finish.py`), with `cbb` added | **Build** (already built; keep live at $5–25 clips) | $1–3/day typical in CBB season, $5–7 on strong days, ~$0 in summer | Tick-correct price; `cbb` league; depth from WS or `/book` rather than cached `/bbo`; independent final signal | Thin depth at 0.98–0.99; ties and last-fair-price voids; faster competition; settlement credit delays during incidents |
| 3 | Order-path correctness (tick rounding, fresh-book collar, depth-sized IOC/FOK) | **Build** now | $0 direct; stops rejected or never-filled orders on NFL/CFB/MLB | `account.order` rounding to `tick`; collar check against a fresh book | None material |
| 4 | Compliance and risk layer (file kill switch with cancel-all, throttle, JSONL audit trail, status gating, §19 email) | **Build** now | $0; protects API access and the account | Code above; one email | Over-tight stops idle the bot |
| 5 | Authenticated markets and private WebSocket | **Build** after 3–4 | +$0.3–1/day on rule 2 [I]; prerequisite for rule 1 | WS client, reconnect, heartbeat and 503 handling, ≤100 markets per subscription | Silent stream stalls (status history shows position-stream delays); added complexity |
| 6 | Deposit and Trading promo (Campaign N/O if shown) | **Do once, manually** | +$10–25 credit, one-off | Nothing | Credit not withdrawable; eligibility depends on account history |
| 7 | Independent score feed for "final" | **Test** | Fewer late or false finish entries | Public league scoreboard JSON | Feed errors produce premature "final" signals |
| 8 | Larger account ($500+) | **Defer** until 1–2 show realised profit | Scales rules 1–2 roughly 3–4× | — | Same per-trade risk, larger dollars |
| 9 | Being first quoter on new listings (outside LIP early pools) | **Skip** | ≈$0, negative after adverse selection | Listing watcher | Model-driven informed flow (gas, weather) |
| 10 | Favorites rule live orders | **Skip** (set `LIVE_RULES=finish`) | −$0.25 per $25 order on average | — | Measured −1 point late |
| 11 | Spread-only market making, Dutch books, cross-venue lag, referrals | **Skip** | ≈$0 (earlier survey); referrals are manual and capped | — | As in the earlier survey |

## Contradictions with, and corrections to, the earlier survey

1. **The worker's main data path is not edge-cached.** The earlier survey said the worker reads asks 0–75 s old. `/v2/leagues/{slug}/events`, which `worker.py` polls, returns `CF-Cache-Status: DYNAMIC` with no Cache-Control [M, 23:31Z]. In 24 paired live reads, its quotes matched a cache-busted `/bbo` read taken 2–8 s later in 17 of 24, against 16 of 24 for the cached `/bbo` [M: `home_data/quote_freshness_2026-10-25.json`]. Staleness is therefore 0–45 s for prices. The 30-s cache hits only the finish rule's depth reads and anything built on `/v1/events` or `/book`.
2. **Market making is not worthless to a small account.** The earlier survey ranked market making "Skip" on rebate and spread grounds only. The Liquidity Incentive Program pays resting size whether or not it fills, has no size floor, and on tonight's books about 30% of sampled rewarded sides were unpaid for lack of size.
3. **Reward pools are probably per event, not per program.** The earlier survey's "ITF ML Live paid $52 across 338 markets" reads the pool as a program total. Changelog wording ("$300 per match", "distributed pro-rata across eligible instruments") and the page's "Daily (per event)" label point to per-event pools, which would make the low-tier pools it used as evidence up to the number of events larger [I].
4. **Table-tennis fee observed.** Θ = 0.10 is now live on 408 open markets; it was unobserved on 10-24.
5. **Rulebook version.** The current Rulebook is the **September 30, 2026** version, not March 20; the automation rules are unchanged.
6. **Market counts.** The earlier "22,192 / 26,592 open markets" were primary markets only, because the listing returns only primary markets since 10-15. Including ladders and props, the venue lists **72,690** markets today.
