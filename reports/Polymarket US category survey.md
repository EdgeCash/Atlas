# Polymarket US by tab: where an automated account can still make money

Survey date 25–26 October 2026. One research agent per Polymarket US nav tab (Home, Midterms, Sports, Crypto, Commodities, Politics, Weather, Tech, Culture, Econ). The ten notes, with their data and scripts, are in `research_notes/Polymarket US category survey/`. Every figure below comes from those notes, which label each one measured, cited or inferred and give the source. Figures assume the current account: about $135, $1–$25 orders, today's 45-second worker. This report supersedes the ranking in `reports/Polymarket US worker edge survey.md` (24 Oct) wherever the two disagree. The disagreements are listed at the end.

## Headline

No tab gives a small account an information edge that survives the fee. The money left is structural, one-off or subsidised:

- **A riskless Senate seat-ladder pair, open before 3 Nov.** About $14 on $135, and the best single trade found.
- **The Liquidity Incentive Program.** It pays resting orders whether or not they fill. It is the largest recurring upside at $2–15/day realistic, with a real chance of ~$0.
- **A handful of overpriced tails to sell.** BTC year-end tails, PMUS-only political longshots, Fed and unemployment floor tails, and the October CPI year-on-year fallback. Together, tens of dollars over two to three months.
- **A few event-time snipers worth logging before building.** Rotten Tomatoes at 10:00 ET, the Arena leaderboard at month-end, the Fed decision, the election-night called winner, and the CFB finish line.

The earlier #1, finish-line settlement yield, is mostly a tape artefact. In live books nobody sells the winner after the final whistle.

Three worker bugs must be fixed before any live order:

- Prices are rounded to the cent (`atlas/polymarket/account.py:101`).
- Depth is read from `/bbo` totals (`atlas/polymarket/source.py:347`).
- College basketball is missing from the leagues `atlas/polymarket/source.py` reads.

## Fix first: three worker bugs and the compliance layer

These are confirmed against the code. They affect every strategy below.

1. **Tick rounding.** `account.order()` formats the limit price with `:.2f`.
   - NFL moneylines tick at 0.0025, CFB at 0.005, and House/Senate control at 0.001.
   - An NFL ask of 0.9975 becomes "1.00", and a CFB 0.985 becomes "0.98", which never fills.
   - Fix: format to the market's `orderPriceMinTickSize` (Home, Sports, Midterms).
2. **Depth from `/bbo`.** `source.depth()` treats `/bbo`'s `askShares` as the size at the best ask. It is the whole side of the book: about 50× too big on midterm books (Midterms) and up to 4,400× (Politics).
   - Both the $2,000 depth gate in `positions.py` and the finish rule's sizing in `finish.py` rely on it.
   - Fix: size from `/v1/markets/{slug}/book` levels. `/book` is also edge-cached for 30 s (Home, Sports), so production depth should come from the authenticated markets WebSocket.
3. **Missing league.** `source.py` doesn't read college basketball. It lists in early November.
4. **Compliance.** Rulebook 5.2(i)/(h) requires order throttles, price collars, kill switches and an audit trail. Participant Agreement §19 conditions live API use on written approval: email Polymarket US support. Also plan around the weekly Thursday 06:00–08:00 ET maintenance, which cancels all orders.

On data freshness: the worker's main feed, `/v2/leagues/{slug}/events`, is **not** edge-cached, so its prices are 0–45 s old, not 0–75 s. Only `/bbo`, `/book`, `/v1/events` and the listing are cached for 30 s (Home and Sports agree).

## Ranked plan

| # | Strategy | Tab | Verdict | Realistic $ at $135 | Needs | Main risks |
|---|---|---|---|---|---|---|
| 1 | **Senate seat-ladder pair**: buy `scc-senate-gop-2026-11-03-lte45` Yes (~0.13) + buy `scc-senate-demst-2026-11-03-gte55` No (~0.75, i.e. sell into the 0.25 bid). Pays ≥ $1 in every outcome, since 46 R + 55 D > 100 seats | Midterms | **Act before 3 Nov** (re-read `/book` first) | ~$14 locked on ~$133, once; re-enter when the gap reopens (it cleared fees in ~31% of hours since 14 Oct) | Two IOC legs, thin leg first (the 0.25 bid was one 194-share order), tick-correct prices | Legging; capital locked to ~4–6 Nov (to 4 Jan if Osborn wins and won't name a caucus); void or settlement dispute |
| 2 | **Liquidity Incentive Program quoting**: post-only GTD orders on rewarded sides below their target size, cheap side first, short-dated markets | Home | **Test** with $20–50 for 7 days, then read `/v1/incentives/earnings` | $2–15/day; $11–51/day on paper; could be ~$0 | Resting orders (`participateDontInitiate`, GTD), `/v1/incentives`, WebSocket book, batch modify, cancel-all, re-post after maintenance | Pool rules not verified; fills lock capital until expiry; competitors; $1 minimum payout; surveillance view of quote-only orders |
| 3 | **Tail seller** (one daily-check module): buy No at the bid on overpriced tails | Crypto, Politics, Econ | **Test**, small | BTC year-end tails ($150k by 31 Dec, $100k by 30 Nov, $40k dip): +1.5 to +3.8¢/contract, ~$1.5–2/month. PMUS-only longshots (US leaves NATO, aliens, Trump resigns): ~3¢/share, $4–6 per 2.5 months. Fed-cut/unemployment floors: ~$3 over 11 weeks | Daily read, bid-side IOC, per-leg cap, total tail-exposure cap | Correlated: a ±40–50% BTC move costs $20–40. Lockup to Dec/Jan. Voided markets may settle at $0.50 |
| 4 | **October CPI YoY fallback**: BLS will not publish October 12-month changes, so the contract falls back to September (3.7% headline, 2.6% core); five legs are decided under every reading | Econ | **Do once**, after written confirmation from support | ~$6–7 on ~$95 | Written confirmation of the settlement path | Settles at last fair price instead; lockup to ~Feb 2027 |
| 5 | **Event-time snipers**, logged before going live | Culture, Tech, Econ, Midterms, Sports | **Test** (log-only first) | Rotten Tomatoes 10:00 ET reads: $5–15/month. Arena month-end winner and leaderboard updates: $3–15/month. Fed decision 0.99 window: ~$1/meeting. Election night, called winner 2 h after poll close: $2–5. CFB finish line, $10 FOK at 0.985: $0.50–1.50/week | Source readers: RT page; Arena (blocked from cloud IPs, so needs a residential IP or headless browser); Fed press release; race calls. `/book` or WebSocket depth | Tiny depth (~$60 at RT); source access; competitors already at 0.99 |
| 6 | **Weather maker-outage sentinel**: take observation-certain mispricings on days the usual maker is absent | Weather | **Test** | $0–1/day | METAR/CLI reader, `/book` depth | Unknown depth (8 hits on 5 days, all won) |
| 7 | **Metals 15-min late favourite**: buy the side the model rates ≥ 0.99 at ask ≤ 0.97 in the last ~5 min | Commodities | **Test** with caution | $1–4/day | WebSocket and Chainlink spot | Edge mostly from one day; one live 0.96 reversal (≈ −$45) |
| — | Skip | — | **Skip** | — | — | — |

The Skip list: BLS release parser (CPI/jobs markets now close before 8:30 ET); finish-line yield in NBA/NHL/NFL; in-play favourites and low-attention leagues; tennis/table-tennis reverse favourite-longshot (fails on 2,922 kick-offs); props/combos/futures and Atlas models vs PMUS; cross-venue lag (PMUS tracks Kalshi within the minute); forecast-model weather (loses to the market on 734 events); crypto up/down and auto-quoted ladders (0 of 120 quotes beat options fair value after fee); awards precursor bots; Netflix/Spotify/Billboard nowcasts; DWTS; new-listing first quoter; commodities futures-model gaps (books too thin to trade size).

**Capital.** The binding constraint is dollars locked at once, not edge.
- #1 uses nearly the whole account until early November.
- After that, split the account: LIP test $20–50, tail seller capped at ~$40 total, CPI fallback ~$95 if confirmed. The CPI fallback and the tail seller cannot both be full-size on $135.
- The snipers recycle within hours and need little standing capital.

## What each tab came back with

- **Home (platform).**
  - The tabs follow gateway tags (`midterms`, `crypto`, `commodities`, `politics`, `weather`, `tech`, `culture`, `economics`), not the `category` field. Sports is `category=sports`.
  - There are 4,861 open events and 72,690 markets in total.
  - The LIP is the one subsidy a small account can reach.
  - Taker fee is 0.0695·p(1−p), except table tennis at 0.10 (now on 408 markets). There is no maker rebate below $10M/month.
- **Midterms.**
  - 2,585 consistency checks; 25 positive after fees; about 4% of those survived with real depth.
  - The seat-ladder pair is the standout.
  - Primaries on this venue settled a median 15.3 h after poll close (Florida took 14 days).
  - A naive "decided at poll close" rule failed once in 44 (FL-07). Waiting 2 h after poll close and requiring a race call held 43 of 43 at an average entry of 0.986.
  - PMUS matches Kalshi within 0–2¢ race by race.
  - DST ends 1 Nov; Thursday maintenance falls on 29 Oct and 5 Nov.
- **Sports.**
  - The price-history tape stops at 0.99 and keeps printing it with no sellers on the book.
  - In 7 live games the winner had no offers from before the whistle until trading stopped, 40–93 s after the final.
  - A real ask ≤ 0.985 after the final appeared in 4% of 249 games, none in the NBA or NHL.
  - The gateway's own final flag beat ESPN by 6–57 s in 5 of 6 games. ESPN once showed FINAL with a stale tied score.
- **Crypto.**
  - The hourly, daily and weekly ladders are quoted by one programmatic maker priced off options.
  - Up/down prices beat a live model at every horizon.
  - Only the hand-listed year-end BTC tails are mispriced, and the gap has held for a month.
- **Commodities.**
  - 11 events: gold/silver up/down on Chainlink, AAA gas daily and year-end ladders, BLS beef. No oil, natural gas or grains.
  - No stale-book window at settlement.
- **Politics (non-midterm).**
  - 47 events / 355 markets, books 1¢ wide.
  - No "decided but not repriced" window: Brazil's runoff tracked global Polymarket, and confirmations were priced 0.90–0.99 before the vote.
  - RCP, the Brazil results feed and senate.gov all refused requests from a server.
- **Weather.**
  - Six cities' daily highs on NWS CLI, mirrored from Kalshi.
  - Prices beat a calibrated NBM model.
  - Impossible buckets repriced a median 6 min *before* the METAR was readable.
  - Late 0.97+ favourites won 53/57, below break-even.
- **Tech.**
  - 16 events: Arena leaderboard, model release dates, IPOs (Anthropic alone $4.4M).
  - The month-end winner traded at 0.98–0.99 for 54 min to 50 h after the snapshot in 5 of 6 months.
  - Free check: poll `/book` on the Oct-31 legs from 15:30 to 18:00 UTC.
- **Culture.**
  - Books are far thinner than the listing shows: Billboard is 91¢ wide at 10 shares.
  - The actual Netflix or album #1 was sometimes not listed at all.
  - Rotten Tomatoes quotes sat untouched 3–16 min after the 10:00 ET observation.
- **Econ.**
  - Since 2 Oct, CPI, payroll and unemployment markets close before the 8:30 print. Through 11 Sep they traded 1–5 h after it.
  - FOMC 28 Oct: PMUS 0.93/0.94 no change vs Kalshi 0.92/0.93 and FedWatch 90–92%, so nothing before the decision.
  - The threshold-ladder scan found only 0.01-share dust.

## Calendar (times ET)

| Date | What |
|---|---|
| Mon 26 Oct – Mon 2 Nov | Midterms #1: re-read `/book` on the two Senate legs, enter if the pair still clears ~3¢ after fees, re-scan hourly |
| Wed 28 Oct, 14:00 | FOMC: log the post-decision 0.99 window (11–29 min historically) |
| Thu 29 Oct, 06:00–08:00 | Maintenance: all orders cancelled |
| Sat 31 Oct, 11:30–14:00 (15:30–18:00 UTC) | Arena month-end: log whether 0.96–0.98 offers survive the noon snapshot |
| Sun 1 Nov | Clocks fall back; re-check every poll-close time |
| Tue 3 Nov, 19:00 onward | Election night: log called winners at 0.97–0.99 two hours after poll close; exclude FL, ME, AK, GA, CA, WA, OR, NV and AZ |
| Thu 5 Nov, 06:00–08:00 | Maintenance |
| Early Nov | College basketball lists; add `cbb` to `source.py` |
| Fri 6 Nov / Tue 10 Nov | Jobs and CPI: confirm markets still close before the print; CPI fallback settles if confirmed |

## Where this overturns the 24 October survey

1. **Finish-line yield is mostly a tape artefact.** It falls from #1 to a CFB-only test worth ~$0.50–1.50/week. The 18% "ask ≤ 0.98 after finish" came from a tape that caps at 0.99. Live books show no sellers, and trading stops 40–93 s after the final.
2. **Market making is not worthless to a small account.** The LIP pays resting size, unfilled orders included, with no account-size floor.
3. **The macro release parser (#3 before) is dead.** CPI, jobs and unemployment markets now close before the 8:30 print.
4. **Pregame reverse favourite-longshot in tennis and table tennis (#4 before) fails.** On 2,922 kick-offs prices are calibrated, and both sides lose ~2 points after fees.
5. **The worker's prices are 0–45 s old, not 0–75 s.** Only its depth reads hit the 30-s cache.
6. **The earlier market counts covered only main markets.** The venue has 72,690 markets, not ~26,600.
