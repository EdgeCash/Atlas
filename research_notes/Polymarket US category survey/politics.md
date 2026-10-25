# Polymarket US category survey: Politics (non-midterm)

## Takeaway

The non-midterm Politics tab is 47 events and 355 open markets. Most are long-dated "who/whether by date X" contracts settled by announcements or news. Only a handful settle from a source a bot can poll: the RealClearPolitics (RCP) approval average, Brazil's TSE count, IMF PortWatch transit counts, and Senate roll calls.

None of those sources gave a "decided but not yet repriced" window that a 45-second poller can take:
- Polymarket US (PMUS) moved with global Polymarket within a minute or two on Brazil's runoff night.
- RCP, the TSE and senate.gov refused requests from this machine.
- The weekly RCP approval ladder on PMUS is only fractional shares deep.

The one persistent, one-sided pattern is a longshot premium: some PMUS-only bets cost 2–4¢ more than on global Polymarket, every day for 30 days. Examples are aliens, the US leaving NATO, and Trump resigning in 2026. A US account can take it by buying NO on PMUS. It is worth roughly **$4–6 per ~2.5-month cycle on a $135 account (about $1.50–2 a month)**, and it carries one large tail risk: the venue appears to have settled 56 voided markets at $0.50.

The infrastructure finding matters more than any strategy. In `/bbo`, `bidShares`/`askShares` are not the size at the best price. They are the total resting shares on that whole side of the book, rounded to two significant figures, including orders far from the touch. On 13 markets they were up to 4,400× the size actually available at the best bid or ask. The worker must size its orders from `/book` or the WebSocket.

Labels used below: **[M]** = measured (endpoint and UTC time given); **[C]** = cited (URL); **[I]** = inference. All reads were public and unauthenticated, made on 25 Oct 2026 between 23:16 and 23:45 UTC unless stated otherwise. Raw files are in `politics_data/` next to this note; the scripts are in `politics_data/scripts/`.

---

## Q1. What is listed: families, wording, sources, spreads, depth, volume

**[M]** `GET /v1/events?closed=false&limit=500&offset=0..4500` (23:16Z) returned 4,861 open events:
- 1,245 were `politics` and 4 were `geopolitics`.
- Removing the midterm families (ushr, ushrmov, usse, usgub, …, 1,189 events) leaves 60 events.
- 13 of those 60 are midterm-adjacent and are left to the midterm agent: 6 CNN exit-poll `extpl` events, 2 state referenda, the TX railroad commissioner, the NC Supreme Court, the Guam governor, an `intlcombo`, and `mcconnell-resign`.

That leaves **47 events and 355 open markets**:
- 277 markets are quoted on both sides.
- The median spread is 1¢, and 77% of two-sided markets are exactly 1¢ wide.
- 134.7M shares have traded in total, with 4.27M shares of open interest.

Every market reports `feeCoefficient` 0.0695 (taker fee = 0.0695·p·(1−p)).

**[M]** `/bbo` sizes are whole-side depth, not touch size. At 23:39–23:45Z, `/v1/markets/{slug}/book` was compared with `/bbo` on 13 markets (`politics_data/books_xv.json`). In every case `bidShares`/`askShares` matched the sum of all bid or offer levels in `/book`, rounded to two significant figures. For example, Newsom's bids show 100,000 in `/bbo` against 101,164 summed over 12 levels in `/book`.

| Market | `/bbo` bidShares / askShares | `/book` best bid qty / best ask qty | `/book` whole-side total |
|---|---|---|---|
| Gavin Newsom, Democratic nominee | 100,000 / 430,000 | 243 / 97 | 101,164 / 431,839 |
| Aliens confirmed by Dec 31 | 69,000 / 68,000 | 5,080 / 17,365 | 69,036 / 68,845 |
| JD Vance, 2028 winner | 96,000 / 360,000 | 15,016 / 5,129 | 96,153 / 365,985 |
| Trump resigns by end-2027 | 82,000 / 7,300 | 50 / 125 | 82,425 / 7,354 |
| Trump approval 38.7–38.9 | 250 bid side | **0.58 shares** at 0.60 (the 250 sit at 0.02) | — |

The best-price size ranged from 1.25× the `/bbo` figure (Hormuz bids) down to 1/4,400 of it (Newsom offers). The prior survey's "5.4M shares at 0.905" on House control is presumably whole-side depth too, so it should be re-read from `/book` before anyone relies on it **[I]**.

### Families (non-midterm)

| Family (slug prefix) | Events / open mkts | Typical wording | Settlement source named | Machine-readable? | Spread, depth at top (`/book`) | Shares traded |
|---|---|---|---|---|---|---|
| 2028 presidency: `usp`, `usp-party`, `uspres-nom-dem/rep`, `uspres28` (who announces a run in 2026) | 5 / 93 | "wins the 2028 … election" / "wins and accepts the … nomination" / "publicly and unambiguously declare" | Govt authorities / parties / the candidates | No (news) | 1¢; 10³–4×10⁴ shares | 72.4M (largest family) |
| Personnel "announced out" (`apdc-*`: Hegseth, Patel, Alito, Powell, Burnham, `trumpadmin`) | 7 / 21 | "departure … officially announced by Dec 31" | The person, the agency, the White House | No (statements) | 1¢; 500–8,000 shares | 7.3M |
| "Formally out" (`opdc-*`: Lisa Cook, Delcy Rodríguez, Zelenskyy, Trump resigns, world leaders) | 5 / 35 | "formally ceases to hold" | Governments | No | 1¢ (world leaders often 10–25¢) | 2.0M |
| Next holder (`nphc-*`: SCOTUS, press secretary; `ncpdc`: next cabinet member out) | 3 / 69 | "next person to assume …" | White House / Senate | No | SCOTUS is 1¢/99¢ placeholders; press secretary 1–3¢ | 0.3M |
| Senate confirmations (`nocc-*`: FDA Overton, Navy Hung Cao) | 2 / 5 | "confirmed by the US Senate by …" | US Senate | Partly (roll-call XML; congress.gov API needs a key) | 1¢ on liquid legs, 48¢ on the FDA Dec leg | 0.47M |
| Legislation (`lawec-*`: SAVE Act, crypto market structure, AI safety) | 3 / 4 | "enacted into U.S. federal law by …" | Congress and the White House | Partly (congress.gov) | 1¢; 10⁴–5×10⁴ shares | 5.7M |
| Geopolitics, data-sourced (`stsc-*`: Hormuz ≥60, Bab el-Mandeb ≤10, 7-day MA of transits) | 2 / 2 | "7-day moving average of transit calls … according to IMF PortWatch" | IMF PortWatch | **Yes** (ArcGIS REST, see Q2) | 1¢; ~20,000 shares on Hormuz | 5.7M |
| Geopolitics, event (`mowc` NATO, `pintc` meetings, `dipcc` Iran deal, `iarc` arrests, `usgcc` aliens) | 9 / 36 | "formally initiates withdrawal" / "meets in person" / "signs … instrument" / "arrested" / "definitively states" | Governments, news agencies | No | 1¢ mostly; aliens 5,080 bid / 17,365 offered | 22.2M (aliens alone 15.7M) |
| Approval rating (`parc-trmpapprv-wk` weekly buckets, `trumpapprove-lw-yr` "how low") | 2 / 13 | "RCP Average 'Approve' … between 38.4 and 38.6, inclusive, at 5:00 PM ET on Friday" | RealClearPolitics / RealClearPolling | **Yes in principle** (blocked from here, Q2) | Placeholders; 0.01–22 shares | **45 shares this week; 0 on the year-low ladder** |
| Foreign elections (`ewc`/`mlaec`/`pwincis`/`vmc`: Brazil, Bulgaria, Israel PM and Knesset, Argentina, France, Spain, Serbia, Sweden) | 10 / 81 | Winner incl. runoff / first PM to form a government / most seats / margin buckets | National election bodies (TSE named for the Brazil margin) | **Yes** for TSE; others vary | Brazil 1–2¢; margin ladders ask-only; Serbia/Spain/Sweden empty | 20.6M |

Event descriptions are in `nonmid_open.json` (scratchpad) and BBO rows are in `politics_data/bbo_rows.json`.

**[M]** Several families on the requested list are **not on the PMUS politics listing today**:
- no mention or speech markets;
- no executive-order or Federal Register counts;
- no Truth Social or X post counts;
- no Supreme Court case outcomes;
- no open shutdown market. The single `gsc-usfedgvmt-by-2026-10-01` market resolved No.

Tariffs appear only as `ustariff-fy2027` (customs revenue) under `macro`, which belongs to the Econ agent. Global Polymarket does list mention markets, for example "What will Andy Burnham say at the next Prime Minister's Questions" (found via [gamma public-search](https://gamma-api.polymarket.com/public-search?q=Andy%20Burnham%20Announced%20Out%20as%20UK%20PM)), but PMUS does not.

**[M]** The settled non-midterm politics history is short. `GET /v1/events?closed=true&categories=politics` returned 84 closed events. The non-primary ones are:
- Attorney General (`attgen`) and `attgen-todblanche`
- DNI Clayton
- the government shutdown market
- two press-secretary events (`presssec-repkl`, `katzac-presssec`)
- Brazil round-1 winner and round-1 margin
- the Clacton by-election
- one weekly approval event (`trmpapprv-wk-2026-10-23`)
- the 2028 Republican and Democratic VP-nominee events

There are also 28 already-resolved dated legs inside open events, for example the July and August "by" legs, the Hormuz monthly legs, and five resolved "Trump meets X" legs.

**[M]** Of these, `uspres-vpnom-rep-2028` and `uspres-vpnom-dem-2028` (56 markets) were closed on 20–22 October with prices between 0.02 and 0.25. `/v1/markets/{slug}/settlement` returns `0.5` for every one of them, which reads like a void at $0.50. This is unverified: the field could also be a placeholder (see Q4 for why it matters).

---

## Q2. Data-sourced families: lag from source to PMUS price, and whether a "decided but not repriced" window exists

### 2a. RCP approval (`trmpapprv-wk`, weekly Friday 5:00 PM ET snapshot)

**[C]** Contract terms come from the [PARC product filing](https://www.polymarketexchange.com/files/products/PMUS%20-%20PARC%20-%20(2026.09.29).pdf) (29 Sep 2026):
- The primary source is RealClearPolitics.
- Each market is a single observation "as displayed by the designated Source at the specified observation date and time".
- Precision is whatever the source displays (one decimal).
- Settlement is no later than the next day.
- A clearly erroneous value delays settlement by up to 7 days.
- "No data → last fair market price".
- The product is open to anyone, except people with inside access to RCP data.

**[M]** RCP is not friendly to a bot. `curl` to `https://www.realclearpolling.com/polls/approval/donald-trump/approval-rating` returned **HTTP 403** (23:19Z), and so did WebFetch. A worker would need a headless browser or a third-party mirror.

**[M]** The PMUS book is empty:
- Only one week has settled (Oct 23: 38.6–38.8 paid 1). Its eight buckets traded **about 200 shares in the whole week**.
- This week's eight buckets have traded **45 shares** in total.
- `/book` at 23:39Z showed stale lots: 38.7–38.9 bid 0.60 × **0.58 shares**; Below 37.8 bid 0.40 × **22**; 38.1–38.3 ask 0.03 × **0.04**; 38.4–38.6 ask 0.94 × 3.05.
- Bids sum to 1.01 and asks to 3.52 (`politics_data/apr_oct30_snapshot2.json`).

**[M]** Kalshi runs the same underlying with an 11:00 AM ET snapshot (`KXAPRPOTUS`, settlement source RealClearPolitics) and real liquidity: **143,000–184,000 contracts a week** across eight buckets in October ([Kalshi markets API](https://api.elections.kalshi.com/trade-api/v2/markets?event_ticker=KXAPRPOTUS-26OCT23)). Its Oct 30 buckets are offset 0.1 from PMUS (for example 38.0–38.2 against PMUS 38.1–38.3).

Mapping Kalshi mids onto the PMUS buckets, assuming the probability is spread evenly across the tenths in each bucket **[I]**, gives fair values of:

| PMUS bucket | ≤37.7 | 37.8–38.0 | 38.1–38.3 | 38.4–38.6 | 38.7–38.9 | 39.0–39.2 | 39.3–39.5 | ≥39.6 |
|---|---|---|---|---|---|---|---|---|
| Fair (from Kalshi) | 0.06 | 0.10 | 0.15 | 0.21 | 0.20 | 0.14 | 0.09 | 0.05 |

Every resting PMUS quote is mispriced by 10–40¢ against these values, but the whole edge on the book is **about $7.40**:
- buy NO on Below 37.8 at 0.60 against a fair 0.94: 22 shares × 33¢ ≈ $7.30;
- plus cents on the fractional lots.

**[M]** How long the outcome stays in doubt. This used Kalshi's 1-minute candles for the winning bucket in the 10 settled weeks from 21 Aug to 23 Oct (`/series/KXAPRPOTUS/markets/{ticker}/candlesticks`; `politics_data/k_apr_lag.json`). The cell shows the winner's bid/ask:

| Minutes before 11:00 ET | T−180 | T−60 | T−30 | T−10 | T−2 |
|---|---|---|---|---|---|
| Median across 10 weeks | 0.47/0.50 | 0.75/0.78 | 0.92/0.95 | 0.96/0.98 | 0.97/1.00 |
| Worst week (Sep 18) | 0.42/0.46 | 0.16/0.22 | 0.26/0.33 | 0.75/0.82 | 0.87/0.96 |

On Oct 16 the winning bucket ("Above 38.7") was still bid 0.36 / ask 0.90 at T−2. RCP keeps adding polls through the morning, so the outcome is genuinely uncertain until minutes before the snapshot. By the time it is effectively decided (T−10), Kalshi's winner is already 0.96–0.99.

**[I]** On PMUS, the six hours between Kalshi's 11:00 snapshot and PMUS's 5:00 PM snapshot are the only place a source-read could lead. Kalshi's API exposes the RCP value at 11:00 (`expiration_value`, e.g. 38.8 on Oct 23). On Oct 23, however, the PMUS winning bucket's ask had already been 0.99 since 17:06Z the day before (`politics_data/apr_oct23.json`). There was no cheap ask to buy.

**Verdict:** no repeatable window; at most a few dollars of stale-quote cleanup a week.

### 2b. Brazil TSE count (`ewc-pres-bra-2026-10-04`, runoff tonight; `vmc-presmov-...-r2`)

**[M]** The TSE results JSON was not reachable from this proxy:
- `resultados.tse.jus.br/oficial/comum/config/ele-c.json` returned 200 and gave the round-2 code 6258.
- `.../ele2026/6258/dados-simplificados/br/br-c0001-e006258-r.json` returned **404 or 429 alternately** for the whole 23:19–23:41Z run (`politics_data/bra_live.jsonl`).

**[M]** The count is cited from news. At 19:39 BRT (22:39Z), with 10.4% of sections counted, Lula had 50.46% ([mixvale](https://www.mixvale.com.br/2026/10/25/apuracao-das-eleicoes2026-aponta-lula-com-5046-e-flaviobolsonaro-se-aproxima-com-4954-no-tse/)). Lula had 50.01% at 47.6% and 50.23% at 53.1% ([mixvale](https://www.mixvale.com.br/2026/10/25/retomada-do-pt-lula-lidera-2o-turno-das-eleicoes-2026-com-5023-dos-votos-apos-5313-das-urnas-apuradas-pelo-tse-contra-flaviobolsonaro/)). Counting was paused between 17:06 and 19:00 BRT. **[C]**

**[M]** PMUS against global Polymarket, minute by minute, 19:00–23:25Z tonight. Sources are PMUS `/v1/price-history?fidelity=1` (stored long-side ask) and [CLOB prices-history](https://clob.polymarket.com/prices-history) for the Lula token (`politics_data/minute.json`, `g_bra_minute.json`):
- The median |PMUS ask − global| was **1.4¢**; 18.5% of minutes were ≥3¢ apart and 2.6% ≥10¢.
- Change correlation peaked at **0.47 with PMUS leading by 2 minutes**. The prior survey found that CLOB timestamps run up to about a minute behind, so read this as "no PMUS lag".
- Lula went 0.23 → 0.25 (20:00Z) → 0.45 (22:01Z) → 0.74 (22:31Z) → 0.92 (23:16Z) on PMUS, against 0.23 → 0.24 → 0.40 → 0.73 → 0.89 on global.
- The 23:41Z book was 0.94/0.95.

On round 1 (Oct 4) PMUS's ask sat a median 5.5¢ above global, with 70% of minutes ≥3¢ apart. That is a wide, thin book rather than a lag.

**[M]** Settlement lag: the round-1 winner market went ≥0.97 at about 22:00Z on Oct 4 and settled at 13:40Z on Oct 5 (**16 hours**). The round-1 margin buckets settled on Oct 6 at 19:44Z (**about 45 hours**).

**[M]** The round-2 margin ladder on PMUS is ask-only, with no bids on any of the 8 buckets:
- Lula 0–4% ask 0.88, matching global's Lula <4% at 0.87/0.88 ([gamma](https://gamma-api.polymarket.com/events?slug=brazil-presidential-election-second-round-margin-of-victory));
- Lula 4–8% ask 0.99 (global 0.12–0.13);
- Lula ≥12% ask 0.41 (global 0.001).

There is nothing to sell into and nothing cheap to buy.

### 2c. Senate confirmations and "announced out" events (news-timed)

**[M]** Minute histories from `/v1/price-history?fidelity=1` (`politics_data/minute.json`):

| Event (external time) | PMUS behaviour | Settled after the decisive move |
|---|---|---|
| Clayton confirmed as DNI, 51–47, Tue 28 Jul ([Gray DC](https://www.fox19.com/2026/07/29/senate-confirms-jay-clayton-new-dni/)) | "By Aug 7" leg: 0.94 at 12:00Z → 0.90 at 20:20Z → 0.98 at 23:21Z. The Dec 18 leg was already 0.97 before the vote | 16–40 h (settled 15:00Z Jul 29) |
| Blanche confirmed as AG, 50–49, about 4:30 AM ET Sat 8 Aug = 08:30Z ([Mediaite](https://www.mediaite.com/media/news/senate-votes-before-sunrise-to-confirm-todd-blanche-as-u-s-attorney-general/); [Axios](https://www.axios.com/2026/08/08/todd-blanche-trump-attorney-general-confirmed)) | "Next AG = Blanche" was already 0.99 at 16:00Z Aug 7. The "confirmed by Aug 7" leg fell 0.76 → 0.04 between 19:00Z and 21:11Z Aug 7, as it became clear the vote would slip past the 03:59Z deadline; it settled 0 | 60 h for the "Next AG" leg |
| Leavitt out as press secretary, 12 Aug | 0.22 → 0.41 at 17:34Z → 0.96 at 19:35Z | 24 h |
| Zacharia "transitioning out", 16 Oct ([Fox affiliates](https://www.fox29.com/news/katie-zacharia-possibly-out-white-house-press-secretary)) | Oct-31 leg 0.20 → 0.75 within one minute at 17:05Z, 0.98 by 17:35Z | 27 h |

**[I]** The Senate legs were priced 0.90–0.99 before the vote, because cloture votes and whip counts announce the outcome ahead of time. The "announced out" legs jump within a minute of the news. A roll-call poller would buy at 0.97–0.99 a contract that settles 16–60 hours later. That is the same thin settlement-yield trade as in sports, at a few events a month and with no source edge.

**[M]** The sources were also blocked: `senate.gov/.../vote_menu_119_2.xml` returned **403**, and `api.congress.gov` with `DEMO_KEY` returned **429 OVER_RATE_LIMIT**. A real api.data.gov key is free but was not tested.

### 2d. IMF PortWatch (Hormuz, Bab el-Mandeb)

**[M]** PortWatch is easy to poll. The query was `services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/Daily_Chokepoints_Data/FeatureServer/0/query?where=portname='Strait of Hormuz'…` (23:44Z), and the layer metadata gives `dataLastEditDate`:
- Data runs to **2026-10-18**, and the last edit was 2026-10-20 10:51Z, so publication is weekly with a 2–8-day data lag.
- Hormuz transits over the last 14 days were 0–8 a day (7-day MA 3.7–4.1) against a threshold of ≥60.
- Bab el-Mandeb's 7-day MA was 24.7–29.6 against a threshold of ≤10.

PMUS prices these at 0.11/0.12 and 0.17/0.18, identical to global (gap 0.0¢ over 30 days, `politics_data/persist_summary.json`).

**[M]** No threshold has ever been crossed. All 7 resolved monthly legs (Hormuz Jun 30–Sep 30, Bab Jul 31 and Aug 31) settled No, **7–9 days after month-end** (for example, the Aug 31 legs settled on Sep 9), because settlement waits for PortWatch to publish.

**[I]** A crossing would become public on a Tuesday-morning publication. A bot polling `dataLastEditDate` every few minutes could see it first. With current values about 15× away from the thresholds, that is a once-a-year event at best. It is worth keeping as a $0-cost alert, not a strategy.

### 2e. Government shutdown

**[M]** The only market (`gsc-usfedgvmt-by-2026-10-01`) sat at 0.00–0.01 for its final 24 hours and settled No about 28 hours after the deadline. No shutdown market is open now.

---

## Q3. Cross-venue: persistent one-sided gaps a US account can take

**[M]** Snapshot method. For every non-midterm PMUS event, the [gamma public-search](https://gamma-api.polymarket.com/public-search) found the global equivalent (23:25–23:35Z). Markets were then matched by name or date: 187 matched pairs (`politics_data/xv_matched.json`).

After discarding pairs that are not the same contract, PMUS sits within ±1.5¢ of global on most liquid markets. Discarded pairs:
- French and Bulgarian overall winner (PMUS) against first-round winner (global);
- cabinet "next out" (global has "None before 2027" and ends 2026; PMUS runs to end-2027);
- wrong date legs.

Examples of agreement: JD Vance 2028 0.20/0.21 against 0.201/0.204; Hormuz 0.11/0.12 against 0.11/0.12; Israel PM Eizenkot 0.49/0.50 against 0.505.

**[M]** Persistence was tested on 11 pairs using 30 days of hourly data: PMUS stored ask minus ½¢ against global CLOB `interval=max&fidelity=60` (`politics_data/persist_summary.json`). Kalshi quotes are from `/events?series_ticker=…&with_nested_markets=true` at 23:30Z.

| Contract | Mean PMUS − global, 30 days | Days with the same sign | Kalshi now | PMUS now (bid/ask, top size from `/book`) | Trade on PMUS |
|---|---|---|---|---|---|
| US withdraws from NATO by Dec 31 | **+3.9¢** | 30/30 | — | 0.05/0.06 (23,525 bid) | buy NO at 0.95 |
| Aliens confirmed by Dec 31 | **+2.3¢** | 30/30 | 0.045/0.046 | 0.07/0.08 (5,080) | buy NO at 0.93 |
| Trump resigns by Dec 31 2026 | **+2.6¢** | 30/30 | — | 0.05/0.06 (309) | buy NO at 0.95 |
| Hegseth out by Dec 31 | **+6.2¢** (+3¢ now) | 29/30 | — | 0.28/0.29 (547) | buy NO at 0.72 |
| AOC, Democratic nominee | **−3.5¢** | 30/30 | 0.13/0.14 | 0.13/0.14 | none (PMUS equals Kalshi; global is the outlier) |
| Newsom, Democratic nominee | +0.8¢ (+4¢ last week) | 17/30 | 0.14/0.15 | 0.19/0.20 (243) | buy NO at 0.81 |
| Zelenskyy out by Jun 30 2027 | +20.7¢ (listing period), +5¢ last 3 days | 18/18 | — | 0.27/0.28 (190) | buy NO at 0.73 |
| Trump meets Putin in 2026 | −2.4¢ (both signs) | 19/30 | — | 0.74/0.75 (13 offered) | none (too thin, unstable) |
| US–Iran 1-year enrichment moratorium | −1.2¢ (−8¢ last 2 days) | 22/30 | — | 0.03/0.04 (**2.6 offered**) | none (no size) |
| JD Vance, 2028 winner | +0.1¢ | — | 0.20/0.21 | 0.20/0.21 | none |
| Hormuz back to normal | −0.3¢ | — | — | 0.11/0.12 | none |

A further pair was checked against Kalshi only, because global has no 2027 leg. **[M]** Trump resigning by end-2027 trades **0.27/0.28 on PMUS** (49.7 shares bid), while Kalshi's "resign before his term ends" (before Jan 2029) trades **0.21/0.22** ([KXTRUMPRESIGN](https://api.elections.kalshi.com/trade-api/v2/events?series_ticker=KXTRUMPRESIGN)). The PMUS contract has the shorter window, so it cannot be worth more. That is a ≥5¢ inconsistency in PMUS's disfavour.

**[I]** The pattern looks like the persistent Senate-control discount in the prior survey: a clientele effect, not a lag. PMUS charges a 2–4¢ premium on attention-grabbing US longshots (aliens, NATO exit, Trump resigning, Hegseth out). Nothing forces it to converge before resolution, so the edge is paid only at settlement.

Edge after fee and lockup. Fair values come from global, or the global/Kalshi midpoint where both exist. The holding period is assumed to be the deadline plus 14 days.

| Trade | Price | Fair | Fee | Net edge / share | Return | Days | Annualised | $ at a $40 clip |
|---|---|---|---|---|---|---|---|---|
| NATO exit, NO | 0.95 | 0.987 | 0.33¢ | 3.3¢ | 3.5% | 82 | 15.6% | $1.40 |
| Aliens, NO | 0.93 | 0.964 | 0.45¢ | 2.9¢ | 3.1% | 82 | 13.9% | $1.25 |
| Trump resigns 2026, NO | 0.95 | 0.984 | 0.33¢ | 3.0¢ | 3.2% | 82 | 14.1% | $1.27 (top size 309) |
| Trump meets Pope Leo, NO | 0.92 | 0.967 | 0.51¢ | 4.2¢ | 4.6% | 82 | 20.3% | $0.43 (top size 102) |
| Hegseth out, NO | 0.72 | 0.755 | 1.40¢ | 2.1¢ | 2.9% | 82 | 13.0% | $1.17 |
| Trump resigns 2027, NO (vs Kalshi) | 0.73 | ≥0.785 | 1.37¢ | ≥4.1¢ | ≥5.7% | 447 | ≥4.6% | ~$2.07 (top size 50) |
| Newsom nominee, NO | 0.81 | 0.849 | 1.07¢ | 2.8¢ | 3.5% | 670 | 1.9% | $1.38 |

**[I]** A four-leg, Dec-31 basket (NATO, aliens, Trump-2026, Hegseth), deployed at about $135, would earn roughly **$4–6 in expectation by mid-January, about $1.50–2 a month**. The sum is about 14–16% annualised against roughly 4% on idle cash elsewhere, since PMUS pays none. The edge assumes the global/Kalshi price is fair. If global itself overprices longshots, as the longshot-bias literature suggests, the real edge is larger.

**[M]** Kalshi and global often disagree with each other on the thin arrest markets. Tom Homan, for example, is 0.07/0.11 on Kalshi and 0.117/0.138 on global, so `iarc` markets have no usable consensus.

---

## Q4. Long-dated political markets: favourite-longshot bias, time value, cheap NO

**[C]** No interest is paid on cash or positions, and margin is 100% of the amount at risk ([PARC filing](https://www.polymarketexchange.com/files/products/PMUS%20-%20PARC%20-%20(2026.09.29).pdf); prior survey). Published evidence (cited in `non_sport_contracts.md`) agrees:
- On Kalshi, the bias slope for Politics is small and not significant: 0.022, s.e. 0.021 ([Bürgi, Deng & Whelan](https://www.karlwhelan.com/Papers/Kalshi.pdf)).
- On Intrade, the favourite edge disappears at a 15–25% discount rate ([Page & Clemen 2013](https://people.duke.edu/~clemen/bio/Published%20Papers/45.PredictionMarkets-Page&Clemen-EJ-2013.pdf)).

**[M]** Evidence from this venue (`politics_data/resolved_legs_summary.json`):
- **All 21 dated "by date" longshot legs that reached their deadline resolved No.** Their Yes ask seven days before the deadline was 0.01–0.18 (median about 0.04).
- In the final 24 hours these books often showed 0.5–0.99 placeholder asks, because offers were pulled.
- The sample is too small to calibrate, and the stored price is the ask, not a trade.
- Deadline legs settle **10–18 hours** after an "announced out" deadline, **7–9 days** after a PortWatch month-end, and **16–60 hours** after an event-driven Yes.
- Listed `endDate`s for Dec-31 legs are Jan 15, which is the worst case for how long capital stays tied up.

**[M]** The void risk can wipe out a cheap-NO book. The 56 `uspres-vpnom` markets were closed on 20–22 October while trading at 0.02–0.25, and the settlement endpoint returns 0.50 for each. If that is a real $0.50 cancel, a NO bought at 0.98 lost 48¢, the profit from about 16 winning 3¢ trades. The contract rules allow last-fair-price or Exchange-determined settlement in edge cases (PARC "No Data by Expiration"; Rulebook 10.4). **[I]** At least one void in 56 markets happened in the venue's first six months of politics, so a cheap-NO strategy should treat about 1–2% per position per year as void risk and avoid markets the venue might delist: brand-new long-dated families and markets with ill-defined terms.

**[I]** Time-value arithmetic. Buying NO at q with fair value f, held T days, returns (f − q − fee)/q. At this venue's fee, a 2¢ mispricing on a 5¢ longshot is about 1.7¢ net (1.8%). That is worth taking at 82 days (8% annualised), roughly break-even against cash at 6 months (3.6%), and not worth it at 2028 horizons (1–2%). **Only Dec-31-2026 legs justify the lockup.** The 2028 nominee and winner markets, despite being the deepest family, should be skipped for buy-and-hold.

---

## Q5. Ladder and bucket consistency

**[M]** Dated monotonic ladders were checked on 12 pairs across 8 events (trump-resig, zelenskyy, delrod, fda, navsec, usiran-nucl, usleg-aisfty, nato-anyct). **There were no violations**: an earlier leg's bid was never above a later leg's ask.

**[M]** Mutually exclusive sets:

| Event | Sum of bids | Sum of asks | Notes |
|---|---|---|---|
| 2028 winner | 0.93 | 1.22 | — |
| Democratic nominee | 0.77 | 0.95 | — |
| Republican nominee | 0.76 | 0.90 | Unlisted names make an ask-sum below 1 not an arb |
| Israel PM | 0.91 | 1.01 | — |
| Argentina | 0.86 | 0.97 | — |
| France | 0.97 | 1.08 | — |
| Brazil | 1.00 | 1.12 | — |
| Party 2028 | **1.02** | 1.04 | Buying NO on both costs 0.98 for a payoff of ≥1, but fees add 3.3¢, so it nets −1.3¢ and is locked to 2028 |
| Approval week | 1.01 | 3.52 | Fractional lots |
| Knesset | 0.96 | 2.51 | — |
| SCOTUS | 0.17 | 13.57 | 1¢/99¢ placeholders on 17 names |

**[M]** Cross-event check: no 2028-winner bid exceeds the same person's nominee ask. The Democratic names in the winner market sum to 0.54/0.69, against the Democratic party market at 0.63/0.64; these are consistent.

**[M]** One logical inversion. In the Iran-deal ladder, "≤5% enrichment cap" trades 0.13/0.14 while "any % cap" trades 0.11/0.12, but a ≤5% cap implies a cap. Buying "any cap" YES at 0.12 plus "≤5%" NO at 0.87 costs 0.99 plus 1.5¢ fee for a payoff of ≥1. It is −0.5¢ in the worst case and +1¢ if any cap above 5% is agreed. It is not fee-positive as a hedge.

**[M]** Margin and bucket ladders (Brazil round 2) are ask-only on PMUS, with sums of 3.29. The asks are overpriced placeholders: there are no bids to sell into, and the asks are too expensive to buy.

**[I]** Ladder consistency is not a source of edge in non-midterm politics. The only fee-positive inconsistencies are the approval-bucket stale lots (Q2a), which hold a few dollars at most.

---

## Ranked strategy table

| Rank | Strategy | Verdict | Realistic $ at a $135 account | What the worker needs | Main risks |
|---|---|---|---|---|---|
| 0 | Size from `/book` (or the WebSocket book), never `/bbo` `bidShares`/`askShares`, which are whole-side totals | **Build** (infrastructure, applies to all strategies) | Prevents sizing against depth that is not at the touch; no direct $ | `source.depth()` currently computes `ask_dollars = askShares × ask` from `/bbo`. Replace it with the best-level qty from `/book`, or walk the levels up to a price limit; keep IOC/FOK | `/book` may be edge-cached as well; check its `Cache-Control` |
| 1 | PMUS longshot premium: buy NO on PMUS-only overpriced Dec-31 longshots (NATO exit, aliens, Trump-2026 resign, Hegseth, Pope meeting) when PMUS is ≥2¢ above both global and Kalshi | **Test**, small and manual-mapped | ≈$4–6 per ~2.5-month cycle (≈$1.50–2 a month); about 14–20% annualised on capital locked to mid-January | Ability to buy the short side; a hand-maintained PMUS↔global/Kalshi mapping file (wording checked); a daily read-only pull of gamma/CLOB and Kalshi; `/book` depth; hold-to-settlement mode with a position cap per market; a resting GTC order at the PMUS bid+1¢ as maker to save the fee | A $0.50 void (VP-nominee precedent); the consensus price itself being wrong; contract-wording mismatches; capital locked 80+ days; fee increases |
| 2 | RCP approval weekly ladder: take stale PMUS lots against the Kalshi-implied bucket distribution (Kalshi buckets offset 0.1; adjust for 11 AM vs 5 PM ET) | **Test** as an opportunistic add-on | $0–10 a week; this week ≈$7 (one 22-share lot) | Kalshi keyless REST for `KXAPRPOTUS`; a bucket-mapping function; `/book` reads; short-side buys; no RCP scraping needed | Fractional depth; RCP changing between 11 AM and 5 PM; RCP 403 makes settlement hard to verify independently |
| 3 | Foreign-election post-call yield (buy the winner at 0.97–0.99 after the count is decisive; Brazil, Israel, Bulgaria) | **Test**, as watch-only first | $0.50–2 per election night; settles 16–45 h later | Count feed from a host that the TSE or other election body does not block, or simply global Polymarket at ≥0.98 as the trigger; `/book` depth | PMUS moves with global within about 1–2 minutes; thin books (Knesset ~500 shares); recounts and coalition rules (`mlaec` "first to form a government" can take months) |
| 4 | Polling settlement sources to front-run repricing (RCP, TSE, PortWatch, senate.gov roll calls, congress.gov) | **Skip** (keep a PortWatch `dataLastEditDate` alert only) | ≈$0 | — | Sources blocked from this IP (RCP 403, TSE 404/429, senate.gov 403, congress.gov DEMO_KEY 429); outcomes priced before the source updates (Senate 0.90–0.99 before votes; Kalshi approval 0.96+ by T−10); PortWatch thresholds about 15× away |
| 5 | Cross-venue lag (follow global moves on event nights) | **Skip** | ≈$0 | — | Brazil tonight: median gap 1.4¢, PMUS not lagging; the prior survey found the same for politics and macro |
| 6 | 2028 and other multi-year longshot NO / favourite buys | **Skip** | <$1 a year | — | 1–2% annualised after fee; void risk; capital tied up 21+ months |
| 7 | Exclusive-set / ladder / Dutch-book arbitrage | **Skip** | $0 | — | Only fee-negative inversions found (party bids 1.02, Iran caps) |
| 8 | Margin and bucket ladders, SCOTUS / Serbia / Spain placeholder books | **Skip** | $0 | — | Ask-only books at 1¢/99¢ placeholders; nothing to sell into |

**Bottom line [I]:** non-midterm politics gives a 45-second taker no information edge. Every data source the contracts name is either priced ahead of its publication or blocked to a simple poller. What survives is a patient, small, settlement-held trade against PMUS's own retail longshot premium, worth about $1.50–2 a month on $135. The one change that pays everywhere is reading depth from `/book` instead of the whole-side `/bbo` size fields.
