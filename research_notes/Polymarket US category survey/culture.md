# Culture tab: data-sourced markets are priced before the source publishes, and the few gaps that remain are worth a few dollars

**Takeaway.** The culture tab listed 149 events and 1,698 markets on 25 October 2026. Every market had a 1¢ tick and a fee coefficient of 0.0695. Most of them are not tradable at any useful size. About half of the Billboard tops of book and a quarter of the Oscars tops are dust orders smaller than one share: Billboard's displayed median spread is 1¢, but its real spread at 10 shares or more is 91¢. Nine of the twelve data-sourced families resolve from a public number that the crowd already prices, usually a day ahead. On Netflix, the eventual #1 was asked at 0.98 or higher one minute before publication in 33 of 44 taped weeks. On Billboard, the #1 sat at 0.97–0.99 for days in 18 of 20 weeks that had a listed winner. DWTS eliminations repriced within 1–3 minutes, with a live crowd watching. The source therefore almost never makes anything newly knowable that PMUS has not already priced. The two real windows are both small:

- **Rotten Tomatoes (RT) ladders.** Books stay open for 3–16 minutes after the 10:00 ET observation, and trades were measured there after the score was fixed.
- **Billboard 200 Sunday news.** In one of 20 weeks the album race flipped at 19:00 UTC on a Sunday. Stale bids worth about $190 were swept within 2 minutes, and stale asks worth about $5 within 3 minutes.

The best use of the worker in this tab is a small, scheduled RT observation-window sniper, at roughly **$5–15 a month** on a $135 account. Billboard sniping is worth only an occasional opportunistic watch. Everything else in culture should be skipped.

Conventions. **Measured** = read by me from the named endpoint at the stated UTC time. **Cited** = a published source, with URL and date. **Inference** = my reasoning, not directly observed. Scratch work and raw pulls are in `/tmp/claude-0/-home-user-Atlas/edbc1613-2236-53ad-a912-f62e839307df/scratchpad/culture/`. The kept data is in `culture_data/` beside this note (356 KB). Nothing in the repository was modified, and no order was placed.

Fee arithmetic used throughout: taker fee = 0.0695·p·(1−p), which is 0.07¢ at 0.99, 0.20¢ at 0.97, 1.6¢ at 0.70 and 1.74¢ at 0.50.

---

## 1. Today's culture listing

**Source (measured).** `GET /v1/events?closed=false&categories=culture&limit=500`, read 2026-10-25 23:16 UTC: 149 events and 1,698 markets. Every market had tick 0.01 and `feeCoefficient` 0.0695. Real books came from `GET /v1/markets/{slug}/book` for 713 markets between 23:47 and 23:58 UTC. That covered all non-awards markets, every quoted Grammys market and a 35% random sample of quoted Oscars markets. "Real" bid and ask means the best level with at least 10 shares. "Lifetime $" is the book's `stats.notionalTraded`. Daily dollars come from the venue's Time & Sales files (`polymarketexchange.com/files/time-and-sales/YYYYMMDD-time-and-sales.csv`, measured).

| Family (slug) | Events / mkts | Contract wording (abridged) and settlement source | Exact timing | Quoted 2-sided / displayed median spread | Real (≥10 sh) median spread | Dust at top of book | Lifetime $ (books read) | Typical daily $ (T&S) |
|---|---|---|---|---|---|---|---|---|
| `oscars` (`tac-oscars-03-14-2027-*`, `oscars-nom-*`) | 49 / 725 | "settle to Yes if X wins Best … at the 99th Academy Awards", source AMPAS | Nominations 21 Jan 2027 ([casino.org](https://casino.org/news/the-2027-oscars-odds), undated); ceremony 14 Mar 2027 | 273 / 0.235 | 0.86 | 31 of 123 | $0.96M (sample) | $0.5–2.7k |
| `grammys` | 43 / 424 | "wins Album of the Year at the 69th Grammys", source Recording Academy | Nomination events dated 16 Nov 2026; ceremony 7 Feb 2027 | 10 / 0.80 | 0.80 | 0 | $13k | ~0 |
| `cma` | 12 / 60 | "wins … at the 60th CMA Awards, scheduled 18 Nov 2026", source CMA | 18 Nov 2026 | 5 / 0.86 | 0.86 | 0 | $3.9k | ~0 |
| `bilbrd` weekly (`ccrc-bilbrd-1song/1album-YYYY-MM-DD`) | 2 / 24 | "#1 song on the Hot 100 / #1 album on the Billboard 200 chart dated Week of Oct 31"; Billboard "typically updates each Tuesday … Friday–Thursday data" | Tracking Fri–Thu; Billboard 200 news on Sunday (about 19:00–20:00 UTC, measured below); Hot 100 news Monday (inference); full chart Tuesday; PMUS settled 16:20–23:51 UTC on Tuesdays | 1 / 0.01 | — (one-sided) | — | — | $0.5k |
| `bilbrd` season (`any2026`, `any-10-27`), rank ladder (`houwif`) | 4 / 82 | "has a #1 album on any Billboard 200 chart released after Contract Issuance and dated in 2026"; "Housewife … is the #2 song" | Last chart dated 26 Dec 2026 | 59 / 0.01 | 0.91 | 52 of 106 (all `bilbrd`) | $354k | <$1k |
| `ntflx` | 4 / 40 | "#1 on the Netflix Global Top 10 Movies (English) / Top 10 in United States chart published on Oct 27", source netflix.com/tudum/top10 | Week Mon–Sun; published Tuesday (`Last-Modified: Tue, 20 Oct 2026 18:59:19 GMT` on the TSV, measured); PMUS settled a median 47 min later | 1 / 0.48 | 0.50 | 2 | $104 | $0–3k |
| `t` (Rotten Tomatoes, `rotc-t-*-gteNN`) | 8 / 57 | "Tomatometer score of NN or more on [date] at 10:00 AM ET", source Rotten Tomatoes | Observation 10:00 ET Monday (14:00 UTC in EDT); settled 3–16 min after | 37 / 0.09 | 0.09 | 7 | $387k | $0.1–9k on observation days |
| `dwts` | 5 / 63 | "officially eliminated by Oct 27 11:59 PM PT"; "ranked #1 on the Week 7 judges' leaderboard"; season winner; source ABC | Live Tuesday 8–10 PM ET on ABC and Disney+ ([ABC7](https://abc7news.com/story/dancing-stars-season-35-what-know-cast-premiere-date-more/19835675/), 2026); elimination about 01:57–02:00 UTC | 47 / 0.01 | 0.14 | 19 | $721k | $1–11k on show nights |
| `sptfy` (Wrapped) | 4 / 48 | "ranked #1 artist globally / top song in the US … 2026 Spotify Wrapped", source Spotify | Event start 2 Dec 2026 17:00 UTC (Wrapped release) | 21 / 0.01 | 0.01 | 2 | $3.18M | $0.3–7k |
| `gsearch` | 8 / 68 | "#1 in Google's Year in Search Global 'Actors' list for 2026", source trends.withgoogle.com/year-in-search | December; market end 15 Jan 2027 | 6 / 0.98 | 0.98 | 0 | $2.2k | ~0 |
| `2026` (TIME POY, `tpoyc-*`) | 1 / 25 | "explicitly named TIME Person of the Year … or pictured on the cover if associated with the named concept", source TIME | Early December (inference) | 25 / 0.01 | 0.01 | 5 | $1.49M | $0.3–1.3k |
| `sma` | 1 / 21 | "named People's Sexiest Man Alive 2026", source People | November (inference) | 0 | — | 0 | $430 | ~0 |
| `2027-02-14` (halftime headliner) | 1 / 30 | "named in the first official headliner announcement by 14 Feb 2027" | — | 1 / 0.48 | — | 0 | $606 | ~0 |
| `gtavi` | 1 / 2 | "Rockstar releases GTA VI in the US by Dec 31 / Nov 19" | 19 Nov 2026 | 2 / 0.01 | 0.01 | 0 | $5.77M | $1–10k |
| `nfl` (Taylor Swift / Madison Beer attendance), `tsa` (Streamer Awards) | 6 / 29 | Attendance counts, source NFL; award winners, Streamer Awards 12 Nov | — | 1 | — | 0 | <$50 | 0 |

Three structural facts matter more than any spread.

1. **Dust tops (measured).** The listing's `bestBid/Ask` is often a fractional-share order. Examples from `/book` at 23:2x UTC:
   - Lil Baby "#1 album in 2026": bid 0.53 × 0.10 share and ask 0.54 × 0.02 share. Behind those, the next real levels are 0.05 × 500 and 0.95 × 114.
   - Elon Musk TIME POY: bid 0.20 × 0.01, with the real bid at 0.11 × 13.

   The listing-based spreads in the prior survey (and the median spreads above) overstate liquidity in Billboard, DWTS and Oscars. A worker must read `/book` and filter by size.
2. **Unlisted winners (measured).** In 3 of 52 settled Netflix events and 4 of the album weeks, every listed market settled No because the actual #1 was not listed. This week, the US-show event omits *Nobody Wants This: Season 3*, which Kalshi prices at 0.58/0.62 to be #1. PMUS's 10 listed US-show titles can be bought together for real asks summing to **0.28**. That looks like a Dutch book but is a trap: the favourite is missing.
3. **The minute tape is not a trade record (measured).** `/v1/price-history` returns display prices. When one side is empty it falls back to another price, so crossed prints such as ask 0.69 against bid 0.99 are common in culture books (docs: "`longPrice` … normally derived from the best ask … not individual trades", [Get Price History](https://docs.polymarket.us/api-reference/price-history/get-price-history.md), read 25 Oct 2026). Every stale-window claim below was therefore checked against the Time & Sales tape ([Time & Sales Report](https://docs.polymarket.us/faqs/execution-tape.md), read 25 Oct 2026).

## 2. Data-source edges: what a bot can poll, how early, and how long PMUS stayed stale

### What can be polled (measured 25 Oct 2026, a handful of requests each)

| Source | Unauthenticated machine-readable path | robots.txt / access | What it gives, and how early |
|---|---|---|---|
| Spotify Charts | `https://charts-spotify-com-service.spotify.com/public/v0/charts` → HTTP 200, 84 KB JSON: weekly global top 50 tracks, albums and artists, ranks only, dated 2026-10-22. `/auth/v0/charts/regional-global-daily/latest` → **401** | No robots file served | Weekly ranks only. Daily and country charts with stream counts need a login |
| Kworb | `kworb.net/spotify/country/global_daily.html` (daily global chart with stream counts and deltas), `us_daily_totals.html` (4 MB), `songs_2026.html` | `User-agent: * Allow: /` | A daily mirror of Spotify with streams. Wrapped counts all streams and Kworb only charted ones, so it is a nowcast, not the settlement number |
| Netflix Top 10 | `www.netflix.com/tudum/top10/data/all-weeks-global.tsv` and `all-weeks-countries.tsv` (32 MB) | `User-agent: * Disallow: /`. Only named crawlers (Googlebot, ClaudeBot, Claude-User and others) are allowed `/tudum`. A generic bot polling it **breaks robots** | The weekly chart at publication. `Last-Modified` was 18:59:19 UTC on Tuesday 20 Oct |
| FlixPatrol (daily Netflix ranks) | — | Cloudflare managed challenge (HTTP 403) on robots.txt itself | Not usable by a bot |
| Billboard | Chart-beat articles and RSS | `User-agent: *` allows articles. `anthropic-ai`, `ChatGPT-User`, `CCBot` and others are disallowed site-wide, so I did not fetch billboard.com | Billboard 200 #1 news on Sunday. The full chart is posted Tuesday ("full chart will be posted Tuesday, Oct 27", [Billboard via search](https://www.billboard.com/music/chart-beat/olivia-rodrigo-you-seem-pretty-sad-back-to-no1-billboard200-1236367607/), 25 Oct 2026) |
| HITS Daily Double | First-week album projections | Not tested | Projections circulate over the release weekend ([Revolt, Sun 6 Jun 2021](https://www.revolt.tv/article/2021-06-06/52000/first-week-projections-place-lil-baby-and-lil-durks-the-voice-of-the-heroes-atop-the-charts/)) |
| Rotten Tomatoes | `www.rottentomatoes.com/m/{slug}` HTML embeds `criticsScore` with `likedCount`, `notLikedCount`, `reviewCount` and `scorePercent` | Allows `/m/`; disallows `/napi/` | Live score and counts. At about 23:25 UTC on 25 Oct: Clayface 75% (120/160), Wildwood 100% (117/117), Godzilla Minus Zero 96% (44/46), Wild Horse Nine 93% (89/96) |
| Box Office Mojo / The Numbers | — | BOM: `User-agent: * Disallow: /` (only named crawlers allowed). The Numbers: no `*` block | **No box-office market is listed on PMUS** (measured), so this does not matter today |
| Google Trends, YouTube | — | — | No PMUS YouTube market. The Year-in-Search markets (`gsearch`) are unquoted. Year in Search ranks breakout queries rather than volume (inference), so Trends is a poor nowcast |

### Netflix (52 settled events, 13 weeks)

- **Measured.** From the venue's minute tape (`/v1/price-history`, 30–48 h custom windows, pulled 25 Oct 23:2x–00:4x UTC), taking T = Tuesday 18:59 UTC (the one measured publication time):
  - The eventual #1 was asked at **≥0.98 at T−24h in 31 of 44 taped events and at T−1 min in 33**. Its ask was ≤0.90 at T−1 min in only 4.
  - PMUS settled a **median 47 minutes after T** (range 21–265; 4 events settled more than a day late, the 18 Aug week on 2 Sep).
  - The display ask was ≤0.97 for some minute in the first hour after T in 12 events. The Time & Sales tape shows almost nothing traded there: on 8 Sep only a 2-share 0.99 print after publication, and on 20 Oct three trades all day in the whole family.
- **Measured.** The uncertainty is resolved on Monday from Netflix's daily in-app Top 10 and similar nowcasts. In the 8 Sep week, *GTA VI: An Extended Look* traded at 0.81 (global) and 0.43–0.44 (US) on Monday evening ET before losing to *The Whisper Man*.
- **Stale-after-source window: none measurable.** The winner was already at 0.98–0.99 before publication. The residual is a 1¢ settlement crumb, roughly 0.9% over about 47 minutes, on books that rarely have an ask.

### Billboard (25 settled events)

- **Measured.** In 18 of 20 events with a listed winner, the #1's ask was 0.97–0.99 on the daily tape several days before the Tuesday chart. In 4 album weeks the actual #1 was not listed.
- **Measured, the one flip.** Billboard 200 dated 8 Aug. The listed favourite *you seem pretty sad…* (0.85) lost to *I'm The Problem* (asked 0.18–0.23). Time & Sales (`20260802-time-and-sales.csv`) shows:
  - **19:00:49 UTC** Sunday 2 Aug: Rodrigo bids sold from 0.80 down to 0.45 (about 130 shares). Further sells at 0.45–0.36 for about 280 shares followed until 19:02:21, then 0.07.
  - **19:04:06 UTC**: one buyer swept Wallen's asks at 0.18–0.48, **22 shares in total**.
  - The next Wallen trade was at 0.97 at 19:42.

  So the stale window after the news was **about 1.5 minutes on the bids (≈$190 of profit to whoever sold Rodrigo) and about 3 minutes on the asks (≈$17 of profit, on $5 of stale offers)**.
- **Measured, today.** The Billboard 200 for 31 Oct (Rodrigo back at #1) moved the PMUS bid from 0.90 to 0.99 at **19:51 UTC on Sunday 25 Oct** (`INTERVAL_6H` tape). That is consistent with a Sunday-afternoon ET news time.
- **Cited/measured.** Kalshi closes its Billboard markets at **Sunday 23:59 ET** (`KXTOPSONG-26OCT31` close 2026-10-26T03:59Z) and its Netflix markets at Monday 23:59 ET, "the day before" publication. PMUS keeps trading until Tuesday. So PMUS is the only venue open when the source publishes.

### Rotten Tomatoes (11 settled ladders, 117 markets)

- **Is the score knowable hours before 10:00 ET? Yes, almost entirely (inference from measured page data).** RT shows liked and total counts live. With 46–160 reviews in, one more review moves the score by 0.6–2 points, so only the bucket containing the current score is uncertain. The ladders reflect this. At T−1h, legs away from the current score were 0.97–0.99 or 0.01–0.02, and the at-score legs were mid-priced, for example:
  - Digger ≥50 / ≥51 at 0.64–0.65 (both Yes) and ≥52 at 0.30 (No).
  - Sense and Sensibility ≥75 at 0.58 (Yes) and ≥80 at 0.22 (No).
  - Social Reckoning ≥56 at 0.19 (No).
  - Street Fighter ≥55 at 0.28 (No).

  (Source: `culture_data/rt_observation_window.csv`.)
- **Measured.** Books were not halted at 10:00 ET. Settlement came 3–16 minutes later, and Time & Sales shows trades after the score was fixed:
  - Digger ≥52 at **0.30 × 6.35 shares at 10:05:59 ET** (settled No).
  - Digger ≥80 at 0.01 at 10:05:13.
  - Street Fighter ≥40 at 0.99 × 25 at 10:01:34, and ≥45 at 0.12–0.16 (dust) at 10:01:35.

  The display tape barely moved between T and settlement (0–1 changes per ladder, except two ladders flattened at 14:03 UTC), so the stale quotes sat untouched for **3–16 minutes**.
- **Today (measured 23:30 UTC on 25 Oct, observation 14:00 UTC on 26 Oct).**
  - Clayface sits at exactly 75.0% (120/160). PMUS ≥75 shows bid 0.56 × 25 / ask 0.59, and ≥80 is asked 0.02 × 6,011. Kalshi's "above 73" is 0.96/0.97 and "above 77" 0.00/0.01, which agrees.
  - Wildwood is at 100% (117/117). PMUS ≥85–≥95 bid 0.94–0.96 with **no asks at all**. Kalshi's "above 97" is 0.99/1.00.

  A certain Yes is not on offer, so there is nothing to buy before T.

### DWTS (9 settled events)

- **Measured.** Elimination prints land about 01:57–02:00 UTC (9:57–10:00 PM ET). The eliminated contestant reached 0.99/0.99 within 1–3 minutes, for example Sarah Jane Nader 0.40 → 0.92 at 01:54 and 0.99 at 02:02 on 17 Sep, and Ciara Miller 0.16 → 0.99 at 01:59 on 7 Oct.
- **Measured.** The books trade continuously through the show: 1,325 trades and $5.3k in `dwts-s35-elim` on the 20 Oct show day, hundreds of them in the last ten minutes.
- **Inference.** The show streams live on Disney+ nationwide, so the West Coast's later broadcast gives no information edge. The crowd is watching the same feed and is faster than a 45-second REST poll.

### Spotify Wrapped, Google, TIME, People

- **Measured.** These resolve on a single release day. Prices match Kalshi:
  - Bad Bunny global top artist: PMUS 0.86/0.87, Kalshi `KXTOPARTIST` 0.87/0.89.
  - Bad Bunny top Spotify album: Kalshi 0.88/0.91 (PMUS lists no album market).
- **Inference.** A Kworb nowcast could size a 5-week hold at about 13¢ of No-side risk. But Wrapped methodology surprises are the whole risk, and the information arrives for everyone at once, so this is not a bot trade.

## 3. Awards: precursors against PMUS, and announcement night

- **Cited.** Gold Derby's experts still had *The Odyssey* first in Best Picture on 6 Oct 2026 ([World of Reel](https://www.worldofreel.com/blog/2026/10/6/oscars-2027-the-odyssey-is-still-the-the-best-picture-frontrunner)). PMUS showed 0.45/0.46 and Kalshi `KXOSCARPIC-27-ODY` 0.45/0.46 (measured), so the market already holds the precursor consensus. In 2026 the venue favourites won 19 of 24 categories (prior survey).
- **Measured.** PMUS awards books are wide at real size:
  - Oscars real spread 0.86; Grammys 0.80; CMA 0.86.
  - Sums of real asks in winner sets run 2.4–6.9 (CMA, Grammys). Best Picture is 0.69 across the 18 sampled markets.
- **Lockup.** Positions would be held until 18 Nov (CMA), 7 Feb (Grammys) or 14 Mar (Oscars).
- **Verdict.** A precursor-driven bot would pay 10–40¢ of spread for information the market already has, and lock $25 clips for 1–4 months. Skip.
- **Announcement night, 98th Oscars (measured, Time & Sales `20260316`).** The night traded $35k across categories, $16.6k of it in Best Actor. Trading was 1-share sweeps of ladders: one taker printed *Timothée Chalamet* at 0.70→0.98 in eleven 1-share fills at 21:58:07 ET. Michael B. Jordan traded at 0.68–0.73 between 21:56 and 21:58 ET and at 0.97–0.99 from 22:04 ET.
- **Measured.** The display tape showed winners reaching 1.00 2–10 minutes after the evident announcement time, with crossed fallback prices in between. The 2026 Emmys (15 Sep file) traded $44k in total.
- **Inference.** Ceremony nights are thin, fast and broadcast live. A 45-second taker is late and pays a 1-share-ladder price.

## 4. Cross-venue: Kalshi (measured about 23:25 UTC on 25 Oct, `api.elections.kalshi.com/trade-api/v2/markets?series_ticker=…&status=open`)

| Market | PMUS displayed (real) | Kalshi bid/ask | Note |
|---|---|---|---|
| Netflix US movie, Animals | 0.89/0.90 (0.89/0.94) | 0.90/0.93 | Aligned. Kalshi closes Mon 23:59 ET |
| Netflix global show, Below | 0.02/0.97 real | 0.91/0.93 | PMUS one-sided |
| Netflix US show | Favourite not listed | *Nobody Wants This S3* 0.58/0.62 | PMUS set is a trap (see §1) |
| Hot 100 #1 Oct 31, Choosin' Texas | 0.96/0.97 | 0.93/0.95 | Kalshi closes tonight before Monday news |
| Billboard 200 #1 Oct 31, Rodrigo | 0.99 bid, no ask | 0.99/1.00 | Both settled in effect |
| Lil Baby #1 album in 2026 | 0.53/0.54 dust (real 0.05/0.95) | 0.73/0.78, vol24 0 | Gap is dust against a stale Kalshi quote |
| DWTS week 7 elim, J. Olson / T. Cameron | 0.62/0.63, 0.58/0.62 | 0.65/0.67, 0.59/0.60 | Aligned |
| DWTS winner, Ezra Frech | 0.59/0.63 | 0.58/0.59 | Aligned |
| TIME POY, Mamdani / Musk | 0.30/0.32, 0.20/0.21 dust (real 0.08/0.16) | 0.28/0.29, 0.07/0.08 | Musk gap closed on real size between 23:2x and 23:5x UTC |
| GTA VI by Nov 19 / Dec 31 | 0.92/0.93, 0.96/0.97 | 0.93/0.94, 0.95/0.96 | Aligned |
| Spotify global top artist, Bad Bunny | 0.86/0.87 | 0.87/0.89 | Aligned |
| RT Clayface ≥75 / Wildwood ≥95 | 0.56/0.59 / 0.95 bid | above 73: 0.96/0.97; above 97: 0.99/1.00 | Consistent |
| Sexiest Man Alive | Noah Wyle not listed; no bids | Noah Wyle 0.86/0.87 | Every PMUS leg is likely No; nothing to sell into |

The prior survey found that PMUS moves with Kalshi within the minute. In culture the venues are aligned within the real spread, and **Kalshi deliberately stops trading before the source publishes** (Netflix, Billboard, RT at 10:00 ET). So Kalshi cannot supply a fresh signal at the moment that matters. Global Polymarket was not pulled (inference: the prior survey found it lags PMUS).

## 5. Ladder and bucket consistency (measured, real books ≥10 shares, 23:47–23:58 UTC)

- **RT ladders (7 open).** No monotonicity violation, meaning no case where a higher threshold's real bid exceeded a lower threshold's real ask. The Wildwood display bids look non-monotone (≥92 bid 0.96 above ≥90 bid 0.94), but with no asks on those legs nothing is executable.
- **Exclusive sets.** No set had a real-ask sum below 1.00 with full coverage. The only sub-1 sum (Netflix US show, 0.28) excludes the favourite. Sums of real bids above 1.00 appear only as dust (DWTS winner displayed 1.03, real 0.91).
- **Rank ladder `bilbrd-houwif`.** Real asks sum to 5.45 and real bids to 0. Empty.
- **Conclusion.** A consistency scanner finds nothing in culture. Ladder value lives only in the RT post-observation window, where the score, not the ladder, decides.

## Ranked strategy table

| Rank | Strategy | Verdict | Realistic $ at $135 | What the worker needs | Main risks |
|---|---|---|---|---|---|
| 1 | **RT observation-window sniper.** At 10:00:00 ET on each `t-*` date, read the RT page (`likedCount/reviewCount`). Take real asks on legs the score now decides (Yes below the score, No at or above score+1). Stop at settlement, 3–16 min later | **Test**, small and instrumented | **$5–15/month** (about 2 ladders a week; 0–3 stale legs each; real depth near the touch has a median of about $60) | A scheduler for the listed observation dates; an RT HTML parser that computes the score itself; `/book` reads (or WebSocket) every few seconds from 10:00:00 to settlement; IOC at the real ask; a size filter; a per-ladder cap of $10–25 | RT displayed-score rounding or caching against the settlement snapshot; a market closed early; depth of 6–25 shares; competition (trades seen at 10:01–10:06); a resolution dispute |
| 2 | **Billboard 200 Sunday-news watch.** Poll a Billboard chart-beat RSS or social feed every 10–15 s from about 18:30 to 21:00 UTC on Sunday. If the #1 differs from the PMUS favourite, sell the favourite (buy No) into real bids and buy the new #1 | Opportunistic add-on | $0–5/month on average, very lumpy (1 flip in 20 weeks; that flip left about $190 of stale bids for 90 s) | A feed parser; WebSocket or `/book`, since a 45-second cached poll misses a 90-second window; two IOC legs | Rare events; a 1.5–3 min window; the 30 s edge cache; Billboard's robots policy and terms; a mis-parse sells the wrong title |
| 3 | Settlement crumbs on decided culture markets (Netflix after Tuesday 19:00 UTC, Billboard on Tuesday, RT after 10:00) | Skip as a separate rule; fold into the sports settlement-yield rule if built | <$1/month (0.9% on the few asks that exist; most decided legs have no ask) | Nothing new | No sellers at 0.99; late settlements (4 of 52 Netflix events settled more than a day late) |
| 4 | Netflix / Spotify / Kworb nowcast pre-publication | Skip | ≈$0 (winner ≥0.98 a day before publication in 31 of 44 weeks) | Daily-rank source (FlixPatrol is behind Cloudflare; Netflix robots disallow generic bots) | Unlisted winners; one-sided books |
| 5 | DWTS live elimination and high score | Skip | ≈$0 | A live-show feed | A live crowd reprices in 1–3 minutes |
| 6 | Awards precursor bot (Gold Derby, guild awards) | Skip | Negative after 10–40¢ spreads | Precursor scraper | 1–4 month lockup; consensus already priced |
| 7 | Cross-venue (Kalshi) culture gaps | Skip | ≈$0 | Kalshi REST | Gaps are dust or stale; Kalshi closes before the source |
| 8 | Ladder and Dutch-book scanner | Skip | $0 | — | Zero real violations; the only sub-1 set is a missing-favourite trap |
| 9 | Google Year in Search, Sexiest Man Alive, halftime, attendance, Streamer Awards | Skip | $0 | — | Unquoted books |

**What to build if anything.** Ranks 1 and 2 share one prerequisite with the sports finish-line rule: replace the 45-second cached gateway poll with the authenticated markets WebSocket, or at least `/book` reads, for a short scheduled window, and filter the top of book by size so that dust prints are ignored. Without that, every culture "edge" the worker sees on the listing is either a fractional-share order or a 30-second-old cache. Data files: `culture_data/open_culture_markets_20261025.csv` (listing plus real books), `netflix_publication_window.json`, `billboard_weekly_winner_pricing.csv`, `rt_observation_window.csv`, `tas_bilbrd_1album_20260808_trades.csv`, `tas_rt_20261005_trades.csv`, `tas_rt_20261019_trades.csv` and `kalshi_culture_open_20261025.csv`.
