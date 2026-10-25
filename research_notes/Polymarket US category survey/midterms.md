# Midterms tab: one mispriced Senate ladder, a small election-night yield, and nothing to race

Scope: the polymarket.us **Midterms** tab (event families `ushr`, `ushrmov`, `usse`, `usgub`, `*to`, `*close`, `ushrsc`, `ussec`, `ussegubc`, `usbm`, `usho`, `hrep-*`, `senate-*`, `balpow`, `housepop*`, `bluewave`/`bluetsu`, `26mid`, `demvrep`), read from the public gateway between 23:16 and about 00:45 UTC on 25–26 October 2026, nine days before the 3 November election. This note builds on `reports/Polymarket US worker edge survey.md` and its three research notes and does not repeat them. Every finding is labelled **[M]** measured (endpoint and UTC time), **[C]** cited (URL and date) or **[I]** inference. Scripts and raw pulls are in `/tmp/claude-0/-home-user-Atlas/edbc1613-2236-53ad-a912-f62e839307df/scratchpad/midterms/` and `.../scratchpad/midterms_scripts/`. The small data set is in `midterms_data/` beside this note. Fee throughout: taker 0.0695·p·(1−p) per contract, which `feeCoefficient` confirms on every politics market [M].

## Takeaway

The one trade on this tab worth building before election day is internal and model-free. Polymarket US's thin **Democratic Senate seat ladder** (`senate-demst`, a few thousand shares ever traded on its top rungs) prices "Democrats ≥ 55 seats" at a 0.25 bid. Its own liquid **Republican seat buckets** (`senate-gop`, 1.2M shares traded on "45 or less") offer "Republicans ≤ 45" at 0.13. Because D ≥ 55 forces R ≤ 45, buying R≤45 Yes and D≥55 No costs **$0.90 for a guaranteed $1.00**. At 23:39Z the books held **215 such pairs: $196 of outlay for $19 of locked profit** [M]. On a $135 account that is about **$13–15**, and on the hourly tape the same gap has been open in roughly a third of hours since 14 October [M]. Everything else in the scan is crumbs: 25 of 2,585 consistency checks were positive after fees, and only that one has more than a dollar of depth behind it. On election night the realistic trade is the **settlement-yield trade from the sports survey, applied to called races**. On 47 settled primaries on this venue, settlement came a **median 15.3 hours after polls closed**, winners sat at **0.97–0.99 for minutes to hours** before settlement, and a clean "decided" rule entered after a two-hour wait averaged **0.986, about 1.3% net per cycle**, worth roughly **$2–5 across the week** at this account size. Racing AP or state results feeds is not worth trying. Prices reach 0.99 within 5–25 minutes of poll close in clear races and run hours ahead of AP in close ones, AP and Decision Desk data are enterprise-priced, and the one PMUS-specific price gap people cite (control markets about 2.4¢ below global Polymarket) is matched by Kalshi, so it is a US-versus-offshore gap with nothing to harvest.

## 1. Today's midterm listing, liquidity tiers, and what changed since 24 October

**Counts [M]** (`GET /v1/events?closed=false&limit=500&offset=0…4500`, pulled 23:16Z 25 Oct): 4,861 open events, 1,245 politics events with 6,824 markets, essentially unchanged from 24 October (1,245 events then too). Only 23 politics markets were created since 20 October. The midterm-relevant ones are two Kansas county Senate markets (`usse-ks-sed`, `usse-ks-lea`, created 20 Oct) and two new closest-Senate-race legs (MN, SC, 23 Oct). Midterm families by event and market count:

| Family | What it is | Events | Markets | Tier (from `/book`, 23:2xZ) |
|---|---|---|---|---|
| `usho` / `usse-midterms` | House / Senate control | 1 / 1 | 2 / 2 | **1**: 0.1¢ tick, $6k at the touch, 85M / 39M shares traded |
| `usse`, `usgub` | Senate / governor winner (incl. 15 county sub-markets) | 52 / 42 | 105 / 90 | **1**: 1¢ spread, median touch $675 / $1,816, 405M / 175M shares traded |
| `balpow` | Balance of power (4 outcomes) | 1 | 4 | 1: $14k at touch, 5.3M median traded |
| `senate-gop` | Exact R Senate seats (≤45 … 57+) | 1 | 13 | **1–2**: 1¢ spread, 0.6–1.2M shares traded per bucket |
| `senate-demst`, `hrep-demst`, `hrep-rep` | ≥N seat ladders | 1 / 1 / 1 | 7 / 10 / 12 | **2**: 1¢ spread but $13 median touch; top rungs 2.5–3.6k shares ever traded |
| `ushr` | House winner per district | 455 | 891 | 2: 1–2¢ spread, $13 median touch |
| `ussegubc`, `ussec` | Senate+Gov combos / multi-state Senate combos (incl. 128-outcome 7-state map) | 9 / 5 | 36 / 157 | 2–3: combos $24 touch; `ussec` 0.1¢ tick but $3 touch |
| `housepopw`, `housepop`, `bluewave`, `bluetsu`, `26mid`, `demvrep` | Popular vote, waves, governors count | 1 each | 2–13 | 2 |
| `ushrmov`, `ussemov`, `usgubmov` | Margin-of-victory buckets | 409 / 34 / 35 | 3,803 / 330 / 337 | **3**: 86–90% one-sided or unquoted |
| `usseto`, `usgubto`, `hrep-to` | Turnout thresholds/buckets | 35 / 10 / 1 | 246 / 70 / 10 | 3: median spread 59–62¢ (0.01/0.99 placeholders) |
| `ushrsc`, `usseclose`, `usgubclose` | State seat counts, closest race | 19 / 13 / 5 | 113 / 39 / 25 | 3: 16–98¢ spreads, most pairs unquoted |
| `usbm`, `ref`, `usag`, `ussos`, `usltgov`, `usmayor` | Ballot measures, down-ballot | 21 / 2 / 12 / 7 / 4 / 4 | 21–24 each | 3 (mayors 1¢) |

**Prices versus 24 October [M]**: Senate control D 0.630/0.632 (0.632/0.633 then), House control D 0.900/0.901 (0.905/0.906), D House ≥218 0.88/0.90, D Senate ≥51 0.68/0.69, balance-of-power D sweep 0.64/0.65.

**A correction to the prior survey and to the worker [M]**. On `/v1/markets/{slug}/bbo`, `bidShares`/`askShares` are the **whole side of the book summed and rounded to two significant figures, not the size at the touch**. For Senate control at 23:19Z, the BBO said 5,500,000 shares a side; `/book` showed 1,893 bid and 21,449 offered at the touch, with the 21 bid levels summing to 5,506,642. On `senate-demst-gte51`, the BBO said 2,500, while the book had 1.88 at the touch and 2,594 across 7 levels. Across 973 books on this tab, the touch is a **median 1.8% of the listed ask depth** ([bbo](https://gateway.polymarket.us/v1/markets/paccc-usse-midterms-2026-11-03-dem/bbo), [book](https://gateway.polymarket.us/v1/markets/paccc-usse-midterms-2026-11-03-dem/book)). So the "5.4 million shares at 0.1¢" in the prior survey is total resting depth. More importantly, `atlas/polymarket/source.py:depth()` multiplies `askShares` by the ask to get "dollars at the ask", which is what `positions.py`'s $2,000-depth gate and `finish.py`'s `ask_shares` use. Those figures overstate fillable size by about 50× at the median, and the fix is to read `/book`. A second small one: `account.order()` formats the limit with `:.2f`, so on the 0.001-tick control markets a buy at 0.632 would be sent as 0.63 and an IOC would not fill [M, code read].

## 2. Settlement: sources, timing, runoffs, RCV, contested results, lockup

**Terms [C]** ([House election product filing ptc08062614399, Aug 2026](https://www.cftc.gov/filings/ptc/ptc08062614399.pdf); the Senate, governor and seat-count templates carry the same source block):
- **Primary source**: "the official state electoral authority responsible for certifying the results". **Secondary sources**: Reuters, AP, Bloomberg, AFP, NYT, WSJ, FT, WaPo, BBC, France 24, DW, NHK, Al Jazeera, Axios, Politico, Semafor, NPR, ABC, CBS, NBC, CNN, Fox News, MSNBC.
- **Accelerated settlement**: "may be settled on an accelerated basis if a qualifying outcome occurs before the Expiration Date. In the absence of confirmation from a Primary Source, the Exchange … may accept the consensus of Secondary Sources". A qualifying declaration is "a formal projection by its centralized decision desk" or an unambiguous news statement. "Leading," "on track" and "likely" do not count. This applies both to Yes and to "definitively cannot be satisfied". The rule is permissive ("may"), not a promise of AP-call settlement.
- **Expiration**: "the earlier of (i) the day of the release of the qualifying data … or (ii) two years after". Settlement is "no later than the day after the Expiration Date". Listed `endDate`s of 2027-01-15, 2027-02-02 for control, and 2026-11-18 on later listings are placeholders, not deadlines [M].
- **Recounts and contested results**: if certification is "delayed, withheld, or subject to formal contest, challenge, annulment, recount … and such contention or recount may materially impact the Contract Outcome, the Contract will remain open until the Underlying is finally determined". Annulled results keep the contract open for a re-run, a cancelled election may settle at last fair price, and "Final Settlements … will not be subject to appeal or revision". AP retractions after settlement do not reverse a payout.
- **Runoffs**: winner, control and seat markets all say "the determination of the winner includes any runoff" and "runoffs … will determine attribution of the relevant seat, even if they take place after November 2026" [M, market descriptions]. **Georgia's** general runoff is **1 December 2026** ([georgia.gov](https://georgia.gov/node/34081), accessed 25 Oct). PMUS lists `usse-frw-ga` ("first round outright winner") at 0.94/0.95 and `usgub-frw-ga` at 0.96/0.97 [M], so the venue prices about a 5% chance that Georgia Senate capital stays locked to December. **Louisiana** moved to closed party primaries, its Senate nominees were settled by the 27 June runoffs, and 3 November is the general ([WAFB, 29 Jun 2026](https://www.wafb.com/2026/06/29/letlow-davis-win-senate-primary-runoffs-louisiana-will-face-off-november/)). No December Senate runoff is reported.
- **Ranked choice**: Maine (D 0.595, a decisive Senate race) and Alaska (D 0.735) tabulate RCV after the first count. Alaska's 2022 RCV tabulation ran on **23 November, 15 days after the election** ([ADN, 23 Nov 2022](https://www.adn.com/politics/2022/11/23/watch-live-at-4-pm-alaskas-ranked-choice-vote-tabulation-in-the-2022-election)). The `ushrmov`/`ussemov` "most votes" (`dwin`) legs are therefore not the same proposition as the winner market in GA (runoff) or ME/AK (RCV) [I].
- **Independents**: control and seat markets include independents only if they announce a caucus. Otherwise "settlement may be postponed until … January 4th, 11:59 PM ET". Dan Osborn (I-NE, 0.25/0.26) is the live case. If he wins without declaring, any control or seat contract whose outcome hinges on him can be locked until 4 January [M, descriptions; I on impact].
- **Combos** (`ussegubc`, `ussec`, `bluewave`, `bluetsu`) settle off the constituent PMUS contracts, and "if an independent or third-party candidate wins either of these elections, this market will settle to No" [M].

**How fast this venue actually settled elections [M]**. Market `endDate` on resolved markets is rewritten to the settlement timestamp, for example `enwc-ussep-la-2026-06-27-rep-jullet` → 2026-06-28T04:27:24Z. This uses the 61 closed 2026 primary events in the sibling scratch file `politics/raw/closed_politics.json` (gateway closed listing) and assumes poll-close times by state. Full table: `midterms_data/pmus_primary_nights.csv`.

| Settlement after last poll close | Primaries | Examples |
|---|---|---|
| Same night, 2–5 h | 10 | LA Senate R runoff 3.5 h, AL Senate R 3.4 h, MA Senate D 2.0 h, MN Senate D 4.3 h, GA Gov R 4.4 h |
| Next day, 11–22 h (business hours ET) | 27 | all NY House 17.6 h, AZ House 15.3–15.4 h, MI 15.3 h, NH 15.5 h, RI 14.3 h |
| 1.7–9 days | 6 | NY-04 / NY-13 40–42 h, SC Charleston 86 h, GA Senate R 197 h (runoff), IA Senate D 208 h |
| ~14 days (round 03:00Z timestamp) | 14 | **every Florida primary settled 2 Sep 03:00Z, 14 days after the 18 Aug vote**, SC 9 Jun (runoff) |
| Weeks to months | 3 | SD Gov R 57 days, OK Gov R 71 days (runoffs) |

Across the 47 with non-round timestamps, the median is **15.3 hours**. The Florida cluster settled on, or alongside, the state's certification timeline rather than on AP calls [I from timing]. So "accelerated settlement" happens, but it is applied manually, mostly next business day, and not uniformly by state.

**Expected lockup by family for the general [I]**. Called House, Senate and governor races in fast-count states settle Wednesday or Thursday (4–5 Nov). Slow-count states (CA, WA, OR, NV, AZ, AK) and close races take days to weeks, and Florida may wait for certification. Control and seat ladders lock until the chamber is arithmetically decided: Kalshi's "AP calls the Senate majority" market prices a call before 5 Nov at 0.71–0.78, before 14 Nov at 0.86–0.90 and before 19 Nov at 0.90–0.98 ([Kalshi KXAPCALLSENATE](https://api.elections.kalshi.com/trade-api/v2/markets?series_ticker=KXAPCALLSENATE&status=open), read 23:2xZ) [M]. Margin and turnout ladders need official vote totals, so they settle at certification, which means weeks.

## 3. Internal-consistency arbitrage: full scan, re-read, survival

**Method [M]**. All 1,045 markets in the aggregate, Senate, governor, combo and ladder families, plus 246 flagged House/margin legs, were read from `/v1/markets/{slug}/book` at 23:20–23:33Z (≤1.7 req/s). The 2,585 checks were then re-read at 23:37Z, and the top 31 legs every ~9 minutes until about 00:45Z (`watch.jsonl`). Cost is each leg's touch (ask for Yes; 1 − bid for No) plus taker fee, against the guaranteed payoff. Checks:
- (a) every mutually exclusive set, buy-all-Yes (needs exhaustiveness) and buy-all-No;
- (b) every ordered pair in `hrep-demst`, `hrep-rep`, `senate-demst`, `usseto`, `usgubto` for monotonicity;
- (c) cross-market implications: D≥51 ⇒ D Senate control; Senate control ⇒ D≥50; D≥k ⇒ R≤100−k against the `senate-gop` buckets; R≥51 ⇒ R control; House control against both House ladders and mutual exclusivity of D≥a with R≥b for a+b ≥ 436; balance-of-power synthetic control in both directions; bluewave/bluetsu against their legs (upper and Fréchet lower bounds); House popular-vote winner against the D margin buckets; each `ussegubc`/`ussec` combo against its state legs; `ushrmov` buckets and `dwin` against the `ushr` winner.

Full output: `midterms_data/consistency_scan_2026-10-25T2337Z.csv`.

**Result**: 25 of 2,585 checks are positive after fees on the touch. Grouped by what survives:

| Opportunity | Edge per $1 set after fees | Touch depth | Executable now (walking the book) | Verdict |
|---|---|---|---|---|
| **Buy `senate-gop-lte45` Yes (0.13) + buy `senate-demst-gte55` No (bid 0.25)**. D≥55 ⇒ R≤45 | **9.9¢ (11%)** | 52–124 pairs | **215 pairs, $195.6 cost, $19.4 profit** (23:39Z) | **Real, survives re-read** (see watch log below) |
| Buy R 45-or-less + 46 + 47 buckets + `gte53` No. D≥53 ⇒ R≤47 | 4.1¢ (4.3%) | 11 | 11 pairs, $0.47 | Real, too small |
| Buy Senate control D Yes (0.632) + `gte51` No. D≥51 ⇒ control | 1.7–1.8¢ | 1.88 | 7 pairs, $0.07 | Real, nothing behind the touch (next bid 0.67, then 0.61) |
| Buy R 51…57+ buckets + Senate control R No. R≥51 ⇒ R control | 0.8–0.9¢ | 69–994 | 8 legs | Fee drag and 8-leg legging, Skip |
| `ussegubc-me`: Jackson D Yes + No on D-sweep and R-gov/D-sen (always pays $2) | 1.7¢ | 11 | ~$0.2 | Real, tiny |
| `ussegubc-ga`: R Gov leg vs combos (pays $2) | 1.35¢ | 131 | ~$1.7 | Real, small |
| `ussegubc-mn` legs | 0.1–0.8¢ | 10–6,600 | <$0.5 | Skip |
| Two-candidate buy-both-Yes at 0.97–0.99 (`ushr` CO-07, NY-20, CA-26, AL-05, MI-08, OR-05, `usse-nm`, `usgub-ny-nas`, Oakland mayor) | 0.5–1.5¢ | 2–1,850 | <$1 each | Not riskless: third-party or write-in winner pays $0 (inference). 0.5% for ≥2 weeks. Skip |
| `ushrmov` `dwin` vs `ushr` D (GA-07, TN-06 etc.) | 0.7–7¢ | 1 share | — | 1-share placeholders, and not the same event in runoff/RCV states. Skip |
| `usgubclose-ny-pa`, `ushrmov-pa-10` | "48–93%" | 0.1–1 share | — | Placeholder quotes. Skip |

**Persistence [M]** (hourly `/v1/price-history?fidelity=60`, which stores the long side's best ask, 14–25 Oct, n = 270 hours):
- The ask of D≥55 exceeded the ask of R≤45 by more than 4¢ in **47%** of hours and by more than 8¢ in **31%**. With a 1¢ spread on the D≥55 rung, a gap over ~3–4¢ in asks means the pair is fee-positive, so this has been a recurring state of the ladder, not one stale order.
- The D≥53 vs R≤47 pair shows the same 47%/26% pattern.
- D≥51 vs the R≤49 buckets never crossed (median −6¢).
- D≥51 vs control was above 4¢ in 29% of hours.

The cause looks structural [I]: the `senate-demst` ladder (created 22 Sep–13 Oct, 2.6–3.6k shares traded on its top rungs) is thin retail flow priced well above both its own venue's bucket market and Kalshi (PMUS D≥53 0.445 vs Kalshi's D 53+ buckets 0.375, read 23:2xZ, [Kalshi KXDSENATESEATS](https://api.elections.kalshi.com/trade-api/v2/markets?series_ticker=KXDSENATESEATS&status=open)). Meanwhile the `senate-gop` buckets are maker-quoted with 10^4–10^5 shares behind them.

**Watch log of the top pair [M]** (`/book` every ~9.5 min, 23:39Z → about 00:45Z; filled in below from `watch.jsonl`): WATCH_SUMMARY

**Fraction that survives**: of 25 fee-positive signals, 1 survives re-read with tradeable depth (D≥55/R≤45, about $19 of profit capacity), 4 survive at under $2 each, about 10 are not riskless (third-party exposure) and about 10 are 0.1–1-share placeholders. So roughly 4% of the positive signals, and about 90% of the dollars sit in one pair. The House-ladder leaks the prior survey flagged (`hrep-demst` ≥215 vs ≥218, ≥235 vs ≥240) no longer cross after fees. The best House-ladder pair is −1.3¢, and the ≥215/≥218/≥220 midpoints sit flat-to-inverted at 0.895/0.89/0.895 but inside the 1–2¢ spread [M]. No House-control vs seat-ladder, balance-of-power, bluewave/bluetsu or popular-vote inconsistency survived fees. The district sum (233.6 expected D seats over 425 priced districts, 30 unpriced) cannot be tested against the ladder without a correlation model [M/I].

**Lockup and residual risk of the top pair [I]**. Both legs resolve once Republicans are certain to hold at least 46 seats, which needs 15 Republican wins among the 35 races plus the 31 R seats not up. On current prices that is election night or Wednesday, if the venue accelerates seat-ladder settlement as it did for primaries. The payoff is $1 in every outcome, because D ≥ 55 and R ≥ 46 cannot both happen in a 100-seat chamber. The risks are venue-side: settlement postponed to 4 January under the independent-caucus clause (only matters if the count hinges on Osborn), a void at last fair price (no trigger applies), or a fat-finger leg. Legging risk is real: the 194-share 0.25 bid on D≥55 is a single resting order, so take that leg first.

## 4. Election-night playbook for a bot

**How prices moved on past nights [M]** (global Polymarket `clob.polymarket.com/prices-history?fidelity=1`, minute midpoints; file `midterms_data/global_polymarket_election_nights_minute.json`):

| Night | Poll close (UTC) | Winner ≥0.95 | Winner ≥0.99 | AP call | Venue settled (`closedTime`) |
|---|---|---|---|---|---|
| 2024 President (Trump) | 00:00–04:00 | 04:43 (11:43 PM ET) | 06:21 (1:21 AM ET) | 10:34 (5:34 AM ET) [C] | 15:17, ~4.7 h after AP |
| 2024 Pennsylvania | 01:00 | 04:45 | 06:24 | early morning, 6 Nov [C] | 20:29 6 Nov |
| 2025 NJ Governor (Sherrill) | 01:00 | 01:07 | **01:16** | 02:00–03:00, per the "AP call" market [M] | 05:35 |
| 2025 NYC Mayor (Mamdani) | 02:00 | (0.95 pre-close) | **02:06** | ~02:30 [I] | 05:44 |
| 2025 VA Governor (Spanberger) | 00:00 | 0.99 all day | 0.99 all day | 00:00–01:00, per the "AP call" market [M] | 04:08 |

AP-call buckets come from Polymarket's resolved "When will the AP call…" markets: VA "7–8 PM" and NJ "9–10 PM" ([gamma event](https://gamma-api.polymarket.com/events?slug=when-will-the-ap-call-the-new-jersey-governor-election)). The 2024 AP call time and the 95% at 11:43 PM ET are as widely reported ([Forbes, 6 Nov 2024](https://www.forbes.com/sites/dereksaul/2024/11/06/election-betting-odds-trump-hits-99-on-polymarket-kalshi-as-more-election-results-come-in/); [arXiv 2507.08921](https://arxiv.org/html/2507.08921)).

The pattern: in a blowout, the market reaches 0.99 **6–16 minutes after polls close**, before AP. In a close national race it reaches 0.95 about **six hours before AP**. After the call the price sits at 0.995–0.999, so the post-call discount on the deep global books is 0.1–0.5¢. That is nothing after a 0.035¢ fee and a multi-hour lock.

**PMUS's own primary nights [M]** (61 events, minute `longPrice` = best ask, `/v1/price-history` with explicit timestamps; `pmus_primary_nights.csv`):
- The winner's ask reached 0.99 a median **23.5 minutes after poll close** (n = 52). In 9 events it never printed 0.99 before settlement.
- PMUS books then sat **below 1.00 for hours**. Examples of minutes with the winner's ask in [0.97, 0.99): LA Senate R runoff 119 min (AP called it inside an hour, [WAFB](https://www.wafb.com/2026/06/29/letlow-davis-win-senate-primary-runoffs-louisiana-will-face-off-november/), with settlement 3.5 h after close), AL Senate R 110, NY-07 887, RI-02 818, GA Senate R 742, AZ-04 324, FL Senate D 255. That is the "decided but not 1.00" window. It is wider on PMUS than on the global venue because PMUS settles next business day and its non-control books are thin.
- **A naive rule fails** [M]: "buy when the winner's ask is 0.95–0.99 and every other candidate is ≤0.05" fired on 44 events and was wrong once (**FL-07**: Mills ask 0.99 / Eli 0.03 at 23:11Z, 11 minutes after polls closed, then Eli 0.99 at 00:26Z and Eli settled Yes). That is 2.3%, above the 0.93% break-even at 0.99. Florida reports early votes first, the classic early-returns trap [I].
- With a **two-hour wait after the last poll close and 30 minutes of persistence**: 43 signals, **0 wrong**, mean entry **0.986**, i.e. about **1.3% net per cycle** after the 0.09¢ fee. Settlement followed a median ~15 h later, and 14 days in Florida.
- n = 43 cannot bound the miss rate below the 1.4% break-even at 0.986: the rule-of-three upper bound is 7% [I]. That is why the live version should also require a call from a named secondary source.

**Can a results-feed bot beat the market? [I, with C]**
- AP's Elections API and Decision Desk HQ's API are sold by contract. DDHQ's only public price is for its broadcast product, at $15–30k a year ([ddhq.io/broadcast](https://ddhq.io/broadcast), accessed 25 Oct). Neither is available to a $135 account.
- Free state SOS / Clarity JSON feeds give raw counts. Turning them into "decided" before AP is a modelling contest against the professional makers who already quote these books, and the global and PMUS tapes show those makers moving within minutes of poll close.
- The worker's data path is a 45-second poll behind a 30-second edge cache (prior survey), so it would see a move 0–75 s late even with a perfect feed.
- The authenticated WebSocket removes the cache. It is worth having for correctness (depth, fills) but buys no race.
- The one feed-driven edge that does not require beating anyone is the **post-call yield**: after AP (or two of the listed networks) has called a race, buy the winner's ask at ≤0.99 and wait for PMUS's next-day settlement.

**Liquidity and plumbing on the night [M/C]**:
- Election night is Tuesday. Daylight saving ends Sunday 1 November, so ET = UTC−5 on 3 November and the first polls close at 7 PM ET = 00:00Z on 4 November.
- **Thursday 5 November 06:00–08:00 ET is the weekly maintenance window**: "All open orders are canceled", the API returns 503, and books reopen empty ([General FAQs](https://docs.polymarket.us/faqs/general-faqs.md)). Any resting order from election night is gone by Thursday morning.
- PMUS touch depth on district and Senate winner markets is $13–$675 at the median. A $25 clip is fine in Senate and governor races and may walk 1–3 ticks in House races, so read `/book`, not `/bbo`.
- Fees at 0.97–0.99 are 0.07–0.20¢ per contract.

## 5. Pre-election fair value: PMUS vs Kalshi vs global Polymarket vs models

**Measured at 23:2x–23:4xZ 25 Oct [M]** (PMUS `/book`; [Kalshi markets API](https://api.elections.kalshi.com/trade-api/v2/markets); [gamma-api](https://gamma-api.polymarket.com/events?slug=which-party-will-win-the-senate-in-2026); `midterms_data/senate_races_kalshi_global_2026-10-25.json`). D win probability as mid-price:

| Contract | PMUS | Kalshi | Global PM | Models [C] |
|---|---|---|---|---|
| Senate control D | 0.631 | 0.625 | 0.655 | DDHQ 56–57%, VoteHub 60%, Silver Bulletin 76.4% ([Newsweek, 23 Oct](https://www.newsweek.com/who-will-win-the-midterms-what-polls-show-10-days-out-12610772)) |
| House control D | 0.9005 | 0.9025 | 0.925 | Silver Bulletin 95% |
| D Senate ≥51 seats | 0.685 | 0.685 (51+52+53+ buckets) | — | DDHQ "51 seats" |
| TX (Talarico) | 0.635 | 0.635 | 0.625 | DDHQ 57%; SB poll avg D+2.4 |
| ME (Jackson) | 0.595 | 0.605 | 0.615 | DDHQ 56% |
| OH (Brown) | 0.685 | 0.675 | 0.665 | DDHQ 57% |
| MI (El-Sayed) | 0.685 | — | 0.71 | DDHQ 68% |
| IA (Turek) | 0.425 | 0.415 | 0.415 | toss-up |
| AK (Peltola) | 0.735 | 0.755 | 0.745 | DDHQ 61% |
| KS (Hamilton) | 0.405 | 0.395 | 0.385 | DDHQ R 65% |
| NE (Ricketts R) | 0.745 | 0.745 | 0.74 | — |
| NC / GA / NH / MN | 0.955 / 0.945 / 0.895 / 0.825 | 0.965 / 0.9455 / 0.895 / 0.84 | 0.9765 / 0.961 / 0.915 / 0.86 | — |
| SC (Andrews) / FL (Nixon) / MS (Colom) | 0.205 / 0.105 / 0.115 | 0.205 / 0.105 / 0.105 | 0.185 / 0.09 / 0.125 | DDHQ SC R 70% |

- **PMUS tracks Kalshi within 0–2¢ race by race.** The two US venues sit together, and global Polymarket is 1.5–3.5¢ more Democratic on control and on safe-D seats. The prior survey's "Senate control 2.3¢ below global" re-measures as −2.4¢ against global and +0.6¢ against Kalshi. House control is now −2.4¢ against global (−0.9¢ on 24 Oct) and −0.2¢ against Kalshi. This is a US-versus-offshore clientele gap that a US account can only take one-sidedly, and nothing says it closes before settlement.
- The models disagree by 20 points on Senate control (56–76%), so there is no consensus fair value to lean on. Buying PMUS's Senate D at 0.632 because Silver Bulletin says 76% means betting one model against the market, which is not a mechanical edge.
- The one PMUS-specific mispricing is inside PMUS: the top of the `senate-demst` ladder is rich against the venue's own buckets and against Kalshi. Section 3 harvests it without taking a view.
- Favourites at 97–99¢ before the election remain a skip (prior survey). The 2026 primary evidence on the global venue agrees: favourites at 95¢+ on the morning of the vote won 141 of 143, and favourites overall lost 4¢ per dollar ([Bitquery, 2026](https://bitquery.io/investigations/how-accurate-is-polymarket-primaries)).

## Ranked strategies, dollars, and the nine-day plan

| Rank | Strategy | Verdict | Realistic $ at $135 | What the worker needs | Main risks |
|---|---|---|---|---|---|
| 1 | **Senate ladder hedge**: buy `scc-senate-gop-2026-11-03-lte45` Yes + `scc-senate-demst-2026-11-03-gte55` No (and the 53/47 twin when it reopens) | **Build now** (one-off script, then an hourly scanner) | **$13–15 once** at today's books (148 pairs × ~9.9¢). Repeat entries possible: the gap was open in ~31% of hours | `/book` reads, two IOC legs (BUY_SHORT for the No leg), thin leg first, kill switch, ledger rows, pair cost ≤ $0.95 gate | Legging (the 0.25 bid is one 194-share order); capital locked to settlement (likely 4–6 Nov, possibly 4 Jan under the caucus clause); venue misreads its own seat counts |
| 2 | **Post-call settlement yield**: after a race is called by AP or two listed networks **and** ≥2 h past last poll close **and** the winner ask has been 0.95–0.99 for 30 min with all others ≤0.05, buy at ≤0.99 | **Test small** on election night | **$2–5 over 4–6 Nov** (~1.3% per cycle, 1–3 cycles, capital-bound) | Free call signal (wire-service race-call pages or a human toggle), `/book` depth read, per-state exclusion list, settlement-latency log | A called race un-called or recounted; Florida-style 14-day locks; ME/AK RCV; GA runoff; 0.99 asks that are 1-share placeholders |
| 3 | Small riskless combo/leg and control/ladder trades (`ussegubc-ga`, `-me`, control vs D≥51) | Opportunistic add-on to #1's scanner | <$2 total | Same scanner, 3-leg support | 1–11 shares deep; 3-leg legging |
| 4 | Results-feed race (state SOS JSON, AP, DDHQ) to beat the market | **Skip** | negative to $0 | Paid feed ($15k+/yr) or a model | Market reaches 0.99 6–25 min after close and runs hours ahead of AP; 30 s cache |
| 5 | One-sided "PMUS is cheap vs global" or model-based race bets | **Skip** | ±, unhedged | — | PMUS ≈ Kalshi; models span 56–76% |
| 6 | Election favourites at 97–99¢ pre-election; two-candidate buy-both at 0.97–0.99 | Skip | ≈$1–2 per cycle | — | Weeks of lock; third-party winner pays $0 |
| 7 | Margin, turnout, closest-race, state seat-count ladders | Skip | $0 | — | 86–90% unquoted; placeholder 0.01/0.99 books; settle at certification |

**Dated action list (all times ET unless noted)**

- **Sun 25 – Mon 26 Oct.**
  - Fix `source.depth()` to read `/v1/markets/{slug}/book`; `bidShares`/`askShares` are whole-book totals.
  - Make `account.order()` format the price to the market's `orderPriceMinTickSize` (3 decimals on 0.001-tick markets).
  - Dry-run trade #1 through the existing preview path: sell `gte55` (BUY_SHORT at 0.75) first, then buy `lte45` at ≤0.15. Require pair cost (both fees included) ≤ $0.95.
  - Then go live at $1, then size to ≤ $100 of the account, keeping ~$35 free for election night.
- **Mon 26 Oct – Mon 2 Nov.** Run the consistency scan hourly against `/book` on the ~60 legs in `senate-gop`, `senate-demst`, the control markets and `ussegubc` (≤1 req/s; reuse `midterms_scripts/scan.py` logic). Re-enter #1 whenever a pair clears 3¢ after fees. Log each pair's fills, cost and timestamps.
- **Thu 29 Oct 06:00–08:00.** Maintenance: resting orders cancelled, API 503. The scanner should pause and resume.
- **Sun 1 Nov.** DST ends. Re-check every poll-close time in the night script: ET = UTC−5 on Nov 3.
- **Mon 2 Nov.** Freeze new pre-election entries. Prepare the night exclusion list: FL (14-day settlement in primaries), ME and AK (RCV), GA (runoff), CA/WA/OR/NV/AZ (slow counts), any race the market has within 0.10–0.90 at 10 PM. Confirm the kill switch and $25 clip cap.
- **Tue 3 Nov, 19:00 ET (00:00Z Nov 4) onward.**
  - Run rule #2 only on races ≥2 h past their last poll close, with a recorded call from AP or two listed networks, a 30-minute persistent clean book, ask ≤0.99, depth read from `/book`.
  - Spend no more than the free cash, at ≤$25 a race. No resting orders overnight; none would survive Thursday's maintenance anyway.
- **Wed 4 Nov.** Expect most called races to settle ~15 h after poll close (late morning to afternoon ET). Log each settlement time and recycle freed cash into newly called races. Check whether the Senate ladders settle on the night's arithmetic.
- **Thu 5 Nov 06:00–08:00.** Maintenance: all orders cancelled. Re-arm after 08:00.
- **6–30 Nov.** Track remaining settlements: Alaska RCV around the third week of November (2022 precedent: day 15), Maine RCV, the Georgia runoff on 1 Dec if `frw-ga` resolves No, Osborn's caucus statement (control and seat legs could otherwise wait until 4 Jan). Write up the per-state settlement latencies; that table is the only durable asset for 2028.
