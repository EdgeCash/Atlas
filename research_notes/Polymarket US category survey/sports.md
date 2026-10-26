# Sports on Polymarket US: the finish-line yield is mostly a display artefact

**Takeaway.** The settlement-yield trade that the earlier survey ranked first is close to nonexistent for a taker once it is measured on the live book instead of the price-history tape. The tape's display price is clamped to 0.99, and it keeps printing that 0.99 while the winner's side of the book has no sellers at all. In all seven finishes observed live tonight (3 NFL, 2 NBA, 1 NHL, 1 AHL; table below), the winner was bid at the top tick (0.9975 in the NFL, 0.99 in the NBA/NHL) with **zero shares offered**, from 22 seconds to 26 minutes before the final whistle until the book closed 40–93 seconds after it. Across 249 recently settled US-major games, a winner ask at or below 0.985 existed inside the real post-final window in **10 games (4%)**: 4 low-attention CFB, 3 MLB, 2 NFL and 0 of 84 NBA/NHL. The earlier survey reported 18% at ≤0.98. The best final signal is the earliest of the gateway's own event (`ended`, `period: "FT"`, `finishedTimestamp`, set in real time), ESPN's scoreboard and the league API, provided they agree on the winner. The gateway led ESPN by 6–57 s in five of six games, but in the NHL game ESPN and api-web led it by 33–43 s. The market prices the result before any of them. My recommendation is to keep `finish.py` as a paper record with two cheap fixes, run a one-Saturday live test of the 0.985 asks in CFB/MLB, and expect at most about $1–2 a week from it. The tennis/table-tennis "reverse favourite-longshot" lead does not hold on 2,922 kick-offs (3–8 times the earlier cells): favourites and underdogs both lose about the fee plus half a cent, and nothing else in the Sports tab (props, combos, futures, ladders against Atlas's models) shows an edge after fee and spread.

Labels: **[M]** measured here (endpoint and UTC time given); **[C]** cited (URL, accessed 2026-10-25); **[I]** inference. Scratch data and scripts are in `sports_data/` beside this note.

---

## What this note changes in the earlier survey

| Earlier claim (`reports/Polymarket US worker edge survey.md`) | What I found | Basis |
|---|---|---|
| Winner ask ≤0.99 after the recorded finish in 43% of games, ≤0.98 in 18%, ≤0.97 in 11.5% | The tape's `longPrice`/`shortPrice` are display prices clamped to [0.01, 0.99]. For DEN–ARI the tape printed 0.99 every minute from 23:03 to 23:29 UTC, while the `/book` read every 3–5 s showed the Broncos bid 0.9975 with **no offers** from 23:23:19 to expiry. Inside each game's real tradable window (from `finishedTimestamp` to the moment the book expired), a winner ask ≤0.98 appeared in 2 of 249 games (0.8%) and ≤0.985 in 10 (4%) | [M] `/v1/price-history?symbol=aec-nfl-den-ari-2026-10-25&fixedInterval=INTERVAL_1H`, 23:29 UTC; `/v1/markets/aec-nfl-den-ari-2026-10-25/book`, 23:18–23:29 UTC; tape-in-window study below |
| The ask reaches 1.00 a median 0.77 min after the finish, but 22–55% of games are still below 1.00 after 15 min | The tape goes to 1.00/0 when the market resolves. Trading actually stops earlier, when the book is wiped (`state: MARKET_STATE_EXPIRED`, market status `RESOLVING`): NBA median 2.9 min after the finish, NHL 2.4, NFL 5.5, MLB 3.3, CFB 33.9. Tonight it was 40–93 s | [M] `/v1/markets/{slug}/bbo` → `lastPriceSample.ts` on 249 games; live event polls |
| `finishedTimestamp` lags the end of two-sided trading by a median 2.7 min, so it cannot be a real-time final signal | Tonight it was written at the gateway's FT (DEN–ARI 23:27:53, GB–DET 23:30:47, LAR–LV 23:35:11, LAL–UTA 23:37:02, IND–BKN 00:33:22) and visible on the event within 1–6 s. In the NHL the gateway's FT itself lagged the league's `FINAL` by about 43 s (NYI–DAL). The "lag" the earlier survey measured is the market deciding **before** the whistle, so it says nothing about the timestamp. Separately, in 12 of 36 recent NBA games `finishedTimestamp` was written hours late (up to about 40 h), so it cannot be trusted after the fact | [M] `/v1/events?slug=…` polled every 3–6 s; `windows.jsonl` |
| The worker reads asks up to 75 s old because the gateway is edge-cached for 30 s | True of `/v1/events`, `/v1/markets/{slug}/bbo` and `/v1/markets/{slug}/book` (`cache-control: public, max-age=30`, `cf-cache-status: HIT`, `age` up to 29). But the worker's own listing, `/v2/leagues/{slug}/events`, comes back `cf-cache-status: DYNAMIC` (not cached). Its book is fresh; only the depth read in `source.depth` (`/bbo`) is stale | [M] response headers 23:16–23:57 UTC |
| Tennis/table-tennis kick-off calibration tilts against favourites (ATP/WTA 0.6–0.7 favourites 59.7% vs a 66.7 cost) | Not on a larger sample: ATP/WTA, ITF and Setka favourites and underdogs both lose roughly the fee, with underdogs slightly worse. ATP/WTA 0.6–0.7 favourites won 64.6% against a 64.2% ask (n = 407), so the earlier gap disappeared (see Q3) | [M] 2,922 kick-offs, `/v1/price-history` |

---

## Q1. Settlement yield

### 1a. What is already built

- `atlas/polymarket/finish.py` is complete as a paper rule and wired into `worker.tick` [M, code read]. It treats a game as final when the event's `ended` is true or `period` ∈ {FT, VFT, F, FINAL, F/OT, …}. It takes a paper position when the moneyline ask is between 0.90 and 0.99, reads depth via `source.depth` (`/bbo`, which is 30-s cached), and grades by `/settlement`. Only "decided" positions (ask ≤0.99 and bid ≥0.98) go to `orders.place(rule="finish")`, and only when `LIVE_RULES` names it. `tracking/finish.csv` is still empty (header only, read 2026-10-25 23:09), so the rule has never fired.
- The worker polls `/v2/leagues/{nfl,nhl,cfb,nba}/events` every 45 s while games are live; CBB and MLB are not in `source.LEAGUES` [M, code read]. It keeps the 45-s pace while any game is over but unsettled (`finish.pending`).
- Two mismatches with the measured book [I]:
  1. In the NBA and NHL (tick 0.01) the top tick is 0.99, so once the bid reaches 0.99 no ask can exist. `decided()` (ask ≤0.99, bid ≥0.98) therefore fires only in the short spell while the bid is 0.98 and someone offers at 0.99, which tonight ended before the whistle.
  2. In the NFL (tick 0.0025) and CFB/MLB (0.005) the decided side trades at 0.9975 or 0.995, which `finish.take` never sees as ≤0.99. The 0.985 asks it *would* catch are the only ones that exist, and they occur in low-attention games where `/bbo` depth matters most.

### 1b. Final signals, measured tonight

Polls: gateway event-by-slug and `/book` every 3–6 s per hot game (the `/book` URL had a unique query string, which returned `cf-cache-status: MISS`, i.e. fresh); ESPN `site.api.espn.com/apis/site/v2/sports/{league}/scoreboard` every 5–8 s (`cache-control: max-age=5`). The NBA's `cdn.nba.com` live scoreboard returned **HTTP 403** to this environment on every call and is not usable from a server without browser headers (not attempted further). NHL `api-web.nhle.com/v1/score/now` answers through a 307 redirect. Times are UTC, 25 Oct 2026.

| Game | Market stopped offering the winner at ≤0.99 (last poll with an ask ≤0.99) | Gateway `period` FT / `ended` true (first poll; `finishedTimestamp`) | ESPN `STATUS_FINAL` (first poll; previous in-progress poll) | ESPN minus gateway | Book → `RESOLVING`/`EXPIRED` | Window after FT | Market `RESOLVED` | Winner asks ≤0.99 after FT |
|---|---|---|---|---|---|---|---|---|
| NFL DEN @ ARI 30–16 | 23:22:18 (5.6 min before FT) | 23:27:55 (23:27:53) | 23:27:58 (23:27:47) | +5.6 s | 23:29:16 | 84 s | 23:32:10 (4.3 min) | none in 16 polls; bid 0.9975 × 545k shares |
| NFL GB @ DET 17–20 (walk-off FG) | 23:30:25 (22 s before FT) | 23:30:48 (23:30:47); score 17–20 first at 23:30:44 "End Q4" | 23:30:57, **with the score still 17–17** | +10.6 s | 23:32:19 | 93 s | 23:35:08 (4.4 min) | none in 20 polls; Packers offered at 0.0025 × 600–900k, no Lions sellers |
| NFL LAR @ LV 35–21 | never ≤0.99 in the polls (≥4 min left) | 23:35:12 (23:35:11) | 23:36:07 (23:36:01) | +56.9 s | 23:36:36 | 85 s | 23:40:00 (4.8 min) | none in 23 polls |
| NBA LAL @ UTA 132–123 | 23:35:12 (110 s before FT) | 23:37:05 (23:37:02) | 23:37:14 (23:37:08 showed 0.0 on the clock, still in progress) | +12.9 s | 23:37:54 | 53 s | 23:41:52 (4.8 min) | none in 15 polls; bid 0.99 × 36k–112k shares, no offers |
| NHL NYI @ DAL 3–6 | 00:19:57 (8.7 min before FT) | 00:28:48 (00:28:42); "End P3" from 00:27:49 | 00:28:09 (00:27:58); NHL api-web `FINAL` 00:27:59 (`OVER` 00:27:47) | **−32 s (ESPN and the NHL API led the gateway)** | book `CLOSED` 00:29:24, `RESOLVING` 00:30:26 | 42 s to `CLOSED` | 00:33:27 (4.8 min) | none in 5 polls; Dallas bid 0.99 × 17.9k, no Dallas sellers |
| AHL CGY @ ABB 2–4 | 00:24:19 (3 min before FT) | 00:27:23 (00:27:21) | not on ESPN's NHL board | — | 00:28:14 | 54 s | 00:31:12 (3.9 min) | none in 7 polls; winner bid 0.99 × 2.5k |
| NBA IND @ BKN 136–109 | 00:07:11 (26 min before FT) | 00:33:26 (00:33:22) | 00:33:39 (00:33:31) | +17.7 s | 00:34:01 | 40 s | — | none in 7 polls; bid 0.99 × 158k–170k |

What the table says [M → I]:

- **The gateway event is usually, not always, the fastest public final signal.** It is fed by Sportradar (`sportradarGameId` on the event; `eventState.updatedAt` advances every few seconds in play). In basketball and football its `period` goes `Q4` → `End Q4` → `FT` (with `live: false`, `ended: true`, `finishedTimestamp` set) within about 4 s of the horn, and it led ESPN by 6–57 s (5 of 5). In the NHL it sat at `End P3` for 53 s and posted `FT` 43 s after api-web's `FINAL` and 33 s after ESPN. api-web is edge-cached (`s-maxage=19`), and ESPN's scoreboard is `max-age=5`. ESPN once reported `STATUS_FINAL` with a stale tied score (GB–DET). A rule that took the winner from ESPN's score alone would have had no winner, or the wrong one.
- **The market leads every feed.** The winner's sellers disappear 22 s to 26 minutes before the whistle, because the result is priced the moment it becomes near-certain. The post-final window (40–93 s tonight; historically 2–6 minutes in NBA/NHL/NFL/MLB and about 34 minutes in CFB) is real, but in these seven games it contained nothing to buy.
- **Competition sits on the bid, not the ask.** After the whistle 1.9k–80k shares traded, all into resting top-tick bids (sellers wanting cash before settlement). The bid queue at the top tick was 2.5k (AHL) to 900k shares deep, so the "yield" goes to makers with queue priority. A $25 bid joining at the whistle would wait behind 10^4–10^5 shares, while only 10^3–10^4 trade before expiry. A bid joined earlier is the in-play standing-order trade that `reports/standing_order_backtest.md` measured at −4 to −10 points.
- **Settlement is fast once trading stops.** `RESOLVED` came 3.9–4.8 min after FT tonight (n = 6). The settlement endpoint answers `Settlement not found` until then. Capital lock after a fill would be minutes, not hours, for these leagues [M].

### 1c. Window length, and the tape inside it, on 249 settled games

From the closed listing (`/v1/events?closed=true&tagSlug={league}&startDateMin=…`, read 23:30–23:44 UTC) I took recent games. Each one's book expiry is `lastPriceSample.ts` from `/bbo`; its tape (`/v1/price-history`, fidelity 1, read 23:44–23:55 UTC) is restricted to the window from `finishedTimestamp` to expiry.

| League (tick) | Games | FT → book expiry, median (p10–p90) min | Last price at expiry (winner) | Games with winner ask ≤0.985 in the window | …and loser ask ≤0.02 | Games with winner ≤0.98 in the 5 min **before** FT |
|---|---|---|---|---|---|---|
| NBA (0.01) | 24 (12 more had a bad `finishedTimestamp`) | 2.9 (2.5–3.7) | 0.99 in 36/36 | 0 | 0 | 6 |
| NHL (0.01) | 60 | 2.4 (1.6–21.4) | 0.99 in 60/60 | 0 | 0 | 28 |
| NFL (0.0025) | 53 | 5.5 (4.0–15.7) | 0.9975 in 52/54 | 2 (0.9775 for 4 min; 0.985 for 6 min) | 1 | 28 |
| CFB (0.005) | 55 | 33.9 (4.1–83.8) | 0.995 in 57/60 | 5 (four at 0.985 for 13–75 min, all FCS/Ivy: Bryant–Brown, Harvard–Cornell, UT Martin–Tennessee St, Stonehill–Towson; one at 0.96 for 35 min, N. Dakota–N. Iowa) | 4 | 7 |
| MLB (0.005) | 57 | 3.3 (1.2–8.1) | 0.995 in 60/60 | 3 (0.985 for 1–23 min) | 3 | 32 |
| **All** | **249** | | | **10 (4.0%)** | **8 (3.2%)** | **101 (41%)** |

The tape cannot separate a real 0.99 ask from the clamp, so the NBA/NHL "0" means no ask ≤0.98. Whether a 0.99 ask exists after FT in those leagues can only be seen on the live book, and tonight's answer was no [M]. The last column is the "decided but not finished" tail, which is the in-play favourite trade (`reports/favorites_backtest.md`: about −1 point late on a tight book), not settlement yield [I].

### 1d. Depth at 0.97–0.99 in the finish window

On the seven live finishes: **0 shares offered on the winner at ≤0.99 at any of 93 polls after FT.** Before FT the depth was plentiful: DEN–ARI with 1:54 left had 34k–160k Broncos shares at ≤0.99 (best 0.9875) for about two minutes, and LAL–UTA with 1:28 left had 24k at 0.99. At that point the game is not over, which makes it the favourites trade [M, `/book` 23:19–23:36 UTC]. For the ten historical 0.985 cases the tape gives top-of-book price only, so their depth is unmeasured.

### 1e. Is there competition taking the 0.98s?

There are no 0.98s to take in the books observed. The decided side's sellers are met by a 10^4–10^5-share bid wall at the top tick within seconds, and in GB–DET the winner's offers vanished at the kick, about 17 s before the gateway even posted the score [M]. Bürgi–Deng–Whelan's maker/taker finding and the Kalshi "endgame sweep" anecdotes in the earlier survey describe the same thing from the other side: the near-certainty premium is harvested by resting bids [I].

### 1f. Verdict

As a taker strategy, settlement yield is worth **≈$0** in the NBA, NHL and NFL. The residue is low-attention CFB (FCS/Ivy) and some MLB, where an ask of 0.985 can sit for 13–75 minutes after FT. That is 1.4% net of fee on a lock of under an hour, in about 7% of CFB games and 5% of MLB games, with unmeasured depth [M/I]. See the build spec for the version worth testing.

---

## Q2. What is in season over the next three months, and opportunities per day

Games per day are the earlier survey's settled-game counts from the venue's own listing (median / p90 of days with games) [M, prior]. "Real finish-window opportunities" applies the per-league rate in 1c [I].

| League | Window | Games/day on PMUS | Tick | Real finish-window asks ≤0.985 per day | Note |
|---|---|---|---|---|---|
| NFL | Sundays and TNF/MNF through 10 Jan 2027 (win-total markets end 2027-01-10 [M]); playoffs mid-Jan; final 14 Feb (`nfl-champ-2027-02-14-matchup` [M]) | 1 median, 10 on Sundays | 0.0025 | ~0.4 per Sunday | 2/53 historical; 0/3 tonight |
| CFB | Saturdays through 28 Nov (win totals end 2026-11-28 [M]); conference title games 5 Dec (`cfb-accchamp-2026-12-05` [M]); bowls; CFP final 25 Jan 2027 (`cfb-champ-2027-01-25` [M]) | 3 median, 65 on Saturdays | 0.005 | ~4 per Saturday (7%), FCS/Ivy only | windows of about 34 min; depth unmeasured |
| NBA | all season (began 20 Oct) | 6 / 11 | 0.01 | 0 | 0/24 historical, 0/2 live |
| NHL | all season | 5 / 12 | 0.01 | 0 | 0/60 historical, 0/1 live (plus 0/1 AHL) |
| CBB | from 2 Nov 2026 ([ESPN press release](https://espnpressroom.com/press-release/espn-and-sec-announce-2026-27-mens-college-basketball-schedule-with-more-than-230-games-across-espn-networks/); [Wikipedia](https://en.wikipedia.org/wiki/2026%E2%80%9327_NCAA_Division_I_men%27s_basketball_season), accessed 2026-10-25) | 32.5 / 83 | not yet listed; NBA-like 0.01 likely [I] | unknown; worth one night of polling on 2 Nov | the March games lack `lastPriceSample`, so it could not be measured |
| MLB | World Series games 3–7, 26–31 Oct ([MLB.com](https://www.mlb.com/news/2026-mlb-playoff-and-world-series-schedule?lctg=5526748)); then nothing until spring | ≤1 | 0.005 | ~0.05 | 3/57 historical |
| Tennis / table tennis | year-round (ATP/WTA into mid-Nov, AO in January; Setka about 400/day) | hundreds | 0.01 | not measured; the earlier survey found tennis never settles inside 15 min | professional makers, integrity risk |

**Expected settlement-yield opportunities: ≈4–5 a week, almost all on CFB Saturdays, ending with the bowls** [I]. At $25 and 1.4% that is **≤$1.50 a week gross if every one fills in full**, and nothing in the NBA/NHL winter. The earlier survey's "$1–3 a day, CBB-led" is not supported.

---

## Q3. Pregame reverse favourite-longshot in tennis and table tennis

**Method [M].** Closed events by `tagSlug` ∈ {atp, wta, itf, table-tennis} on every third day from 1 Jul to 24 Oct 2026: 29,903 matches listed, from which I drew a random sample per group. For each match, the last 1-minute tape point at or before the scheduled start with both display prices strictly inside (0.01, 0.99) and summing to ≤1.04 (a tight book) gives the kick-off asks. Only binary settlements are kept, and the cost is ask + fee with Θ = 0.0695 for tennis and 0.10 for table tennis (the current schedule, [docs.polymarket.us/fees](https://docs.polymarket.us/fees.md)). Edge = win rate − mean cost, in points ± SE (matches are independent). Endpoints: `/v1/events?closed=true&tagSlug=…&startDateMin=…&startDateMax=…`, then `/v1/price-history?symbol=…&timestamp.startTimestamp=start−1800&timestamp.endTimestamp=start+300&fidelity=1`, read 23:21 UTC 25 Oct to 00:43 UTC 26 Oct.

**Sample.** 3,600 matches drawn; 2,922 had a tight quote within 15 min of the start and a binary settlement. 561 had no tight pre-start quote (often an empty book until the first point), 91 settled at a non-binary price (walkovers/retirements at LFMP), and 26 had only a stale quote. The kick-off book is 1¢ wide in every large group. Table tennis is costed at Θ = 0.10.

*Edge from buying the favourite at the kick-off ask, by the favourite's ask (points, ± SE, n):*

| Group | 0.50–0.60 | 0.60–0.70 | 0.70–0.80 | 0.80–0.90 | 0.90–0.99 | All |
|---|---|---|---|---|---|---|
| ATP/WTA | −3.0 ± 2.7 (349) | −1.2 ± 2.4 (407) | −3.3 ± 2.5 (318) | +0.7 ± 2.5 (196) | −1.3 ± 3.0 (77) | **−1.9 ± 1.2 (1,347)** |
| ITF | −0.4 ± 4.7 (115) | −1.5 ± 4.2 (128) | −1.0 ± 3.8 (128) | −4.3 ± 3.6 (124) | −4.6 ± 3.3 (86) | **−2.2 ± 1.8 (581)** |
| Setka Cup (Θ 0.10) | −1.1 ± 2.4 (430) | −3.4 ± 2.8 (307) | −3.0 ± 3.8 (142) | −3.2 ± 5.6 (49) | +8.7 (5) | **−2.2 ± 1.6 (933)** |
| WTT, TT Elite, TT Cup, Czech Liga Pro | cells of 1–12 | | | | | −2.0 ± 7.0 (35, WTT) |

*Edge from buying the underdog at the kick-off ask, same buckets:*

| Group | 0.50–0.60 | 0.60–0.70 | 0.70–0.80 | 0.80–0.90 | 0.90–0.99 | All |
|---|---|---|---|---|---|---|
| ATP/WTA | −1.5 ± 2.7 | −3.2 ± 2.4 | −0.5 ± 2.5 | −3.8 ± 2.5 | −0.7 ± 3.1 | **−2.1 ± 1.2** |
| ITF | −4.7 ± 4.7 | −3.3 ± 4.2 | −3.5 ± 3.8 | +0.7 ± 3.6 | +1.8 ± 3.3 | **−2.0 ± 1.8** |
| Setka Cup | −5.5 ± 2.4 | −3.1 ± 2.8 | −2.7 ± 3.8 | −1.3 ± 5.6 | −12.8 (5) | **−4.1 ± 1.6** |

*Calibration in the cells the earlier survey flagged:* ATP/WTA favourites priced 0.60–0.70 won **64.6%** against a mean ask of 64.2% (n = 407; earlier: 59.7% vs 66.7, n = 186). ITF 0.60–0.70 won **64.8%** vs 64.8% (n = 128; earlier: −13.0 ± 5.5). Setka 0.60–0.70 won **63.2%** vs 64.3% (n = 307; earlier: −9.6 ± 4.5). By month (Jul–Oct) the underdog edge on ATP/WTA ran −2.9, +2.9, −5.5 and −2.8; on Setka −3.1, −3.8, −0.7 and −4.0. No month is significantly positive [M].

**Verdict.** **It does not hold.** Kick-off prices in tennis and table tennis are calibrated to within about a point in every well-populated cell. Both sides lose roughly the fee (0.4–1.7¢) plus half the 1¢ spread, and the underdog side loses slightly more because the fee is charged on p(1−p) per contract while the payout is smaller. The earlier cells were small-sample noise, which is what Lyócsa & Výrost's data-snooping-corrected tennis result predicted ([muni.cz](https://muni.cz/en/research/publications/1397002), cited in the earlier survey). **Skip.** If ITF favourites at 0.80–0.99 really are overpriced (−4.3 and −4.6, each about 1.3 SE), that would argue for buying the ITF underdog at 0.80+. The cell is not significant, it sits in the tier with 44 of the ITIA's 68 alerts, and it should not be traded.

---

## Q4. What the earlier survey did not cover

**Player props.** PMUS lists NBA/NHL/NFL player ladders (`atlas/polymarket/props.py` prices them). Over 111,410 archived quotes the median bid-ask spread was 6¢ NBA, 2¢ NFL and 5¢ NHL [M, `tracking/polymarket_props.csv`]. Where Atlas's probability and the PMUS close are both recorded and the player played (`tracking/prop_record.csv`, 23–25 Oct), **Atlas's Brier is worse than the close**: NBA 0.2707 vs 0.2550 (626 contracts, 11 games), NHL 0.3542 vs 0.3523 (584, 12) [M]. Buying overs where Atlas exceeds the close by 5–15 points showed +3 to +4¢ a contract in the NBA (n = 144–331), but that is 11 games of correlated contracts with the unders at −8 to −11¢. It is noise, not a signal [I]. **Skip;** let `prop_record.csv` grow, since a share above zero there would surface without a code change.

**Combos/parlays.** Combos are priced by makers through RFQ, which needs an authenticated account (`/api-reference/rfqs/*`; up to 1,000 new combo instruments a week; [Combos FAQs](https://docs.polymarket.us/faqs/combos-faqs.md)). The taker fee follows a steeper curve, `C·p·[0.0695(1−p) + 0.06(1−p)^4]` ([fees](https://docs.polymarket.us/fees.md)): 10.2% of outlay at p = 0.10 against 6.3% for a single, 7.1% vs 5.2% at 0.25, and the same as a single above about 0.7 [M, computed]. Combo fills carry no maker rebate, and a void leg settles at the last fair market price (LFMP), not as a push. Combos cannot be priced from public data, cost more, and pay the RFQ maker's correlation margin [I]. **Skip.**

**Futures and season-long markets.** There are 2,156 open futures events (11,549 `SPORTS_MARKET_TYPE_FUTURE` markets): champions, awards, stat leaders, team win totals, player season totals [M, full open listing, 23:23 UTC]. Quoted legs have a 1¢ median spread, but many legs are unquoted. Win-total lines that become mathematically decided are switched to `SOLVED` and settled early: Michigan's two decided lines were `SOLVED` while the live ones traded 0.06–0.57. So the "decided but unsettled" yield does not survive into futures either [M]. Locks run to January–June 2027 and there is no interest on cash [C, earlier survey]. The World Series winner is 0.836/0.837 vs 0.157/0.158 (asks sum to 0.995, which turns negative after two fees of about 0.94¢ each) [M]. **Skip.**

**Spread and total ladders against Atlas's models.** The anchoring record that decides how much of Atlas's disagreement is real is 0% for NCAAF moneyline and spread, 1% NFL, 4% NBA and 28% NHL. Football totals follow a hit-rate curve that holds the NFL at one half ([`reports/polymarket_model.md`](../../reports/polymarket_model.md), rebuilt 2026-10-25 23:07). The NHL's 28% is not an edge: Atlas's NHL Brier is 0.2381 against a 0.2358 consensus close over 2022–26 ([`reports/nhl_market_recent.md`](../../reports/nhl_market_recent.md)), the pre-registered puck-line test lost −27.7 units on 635 bets ([`reports/nhl_puckline_fresh.md`](../../reports/nhl_puckline_fresh.md)), and NHL main lines quote 4¢ wide on PMUS, so a 28% share needs a 13-point disagreement to clear half the spread plus the fee [I]. The CFB total ties the market on Brier (0.247 vs 0.247) and loses on CRPS (9.126 vs 8.847) ([`reports/ncaaf_total.md`](../../reports/ncaaf_total.md)). **Skip** any new ladder strategy. The existing model rule already takes the few NCAAF totals the record permits.

**Does Atlas show any edge against PMUS?** No measured cell does. The favourites paper record (`reports/polymarket_model.md`) is −1.5 to −2.5 points in play (n = 95–119 per threshold) and positive but tiny pregame (+1.7 ± 5.2 at 0.80 on 40 graded, +7.1 on 10). It is the only thing worth watching, and it is the same "pregame favourite" the tennis test above finds flat.

---

## Settlement-yield build spec (what is worth building, sized to what was measured)

The trade as specified (buy 0.97–0.99 around the whistle in NBA/NHL/CBB) should **not** be built as a live rule. What is worth an afternoon:

**1. Fix the paper rule so it records the truth (Build, cost about 2 h).**
- *Signal:* the gateway event read every tick (`ended` true, or `period` == "FT"/"F/OT"/"FT/OT"; `live` false). The worker already has this from `/v2/leagues/{slug}/events`, which is uncached. ESPN's scoreboard (and api-web for the NHL) can trigger first but must **agree on the winner** with the gateway's score: if either reports a different winner or a tie, skip. Do not use the NBA cdn (403 from servers). Measured: gateway ahead of ESPN by 6–57 s in basketball and football, behind ESPN and api-web by 33–43 s in the one NHL game.
- *Price band:* per-market tick. A position is "decided" when the winner's ask ≤ 1 − 2·tick and the loser's ask ≤ 0.02. That is ≤0.98 in NBA/NHL/CBB, ≤0.99 in CFB/MLB (0.005 tick; the measured asks were at 0.985) and ≤0.995 in the NFL. This keeps the earlier survey's two-sided gate and drops the 0.99s that cannot exist.
- *Depth:* read `/v1/markets/{slug}/book` (not `/bbo`) for the shares at ≤ the band, and log them. Both are 30-s cached at the edge, so a production version should use `SUBSCRIPTION_TYPE_MARKET_DATA` on `wss://api.polymarket.us/v1/ws/markets` (authenticated; [Markets WebSocket](https://docs.polymarket.us/api-reference/websocket/markets.md)) for the ≤5 games in their final period, not cache-busting.
- *Leagues:* add `cfb` (already there), `mlb` and `cbb` to the worker's league list, and keep the quick pace until the market leaves `MARKET_STATUS_OPEN` (it goes to `RESOLVING`, the book goes `MARKET_STATE_EXPIRED`), not until settlement.
- *Logging (per position):* gateway FT time and `finishedTimestamp`; ESPN final time and score; first and last tick the winner had an ask in band; best ask; shares at ≤ band; loser ask; `RESOLVING` and `RESOLVED` times; `sharesTraded` before and after (traded volume in the window); settlement. `finish.csv` already has most of these columns. Add `tick`, `resolving_at` and `window_s`.

**2. One-Saturday live test in CFB/MLB at the 0.985 asks (Test, cost $0 at risk beyond the clip).**
- *Rule:* gateway FT + ESPN non-contradiction + market `MARKET_STATUS_OPEN` + winner ask ≤ 1 − 2·tick (0.985 for 0.005-tick leagues) + loser ask ≤0.02 + book depth at that ask ≥ the clip.
- *Sizing:* **FOK** (not IOC, to avoid dust fills) for min($10, shares at the ask × price) per game, at most 3 open at once, ≤$30 open. Fees round to the nearest cent ([fees](https://docs.polymarket.us/fees.md)): $10 at 0.985 is 10.15 contracts, fee $0.01, net $0.14.
- *Kill conditions:* any loss, or any settlement at a non-binary price (LFMP or tie), stops the rule pending review. So does any case where the gateway and ESPN disagree on the winner, a market that reopens after `RESOLVING`, or a fill that is partial or not at the expected price.
- *Pass bar:* ≥10 fills over the CFB regular season with 0 losses, and median depth at the ask ≥$25. Otherwise retire it.
- *Expected value:* ≈4 chances a Saturday × $10 × 1.4% ≈ $0.55 a Saturday; at $25 clips, $1.40 [I]. The real purpose is to learn whether those 0.985 asks have depth.

**3. Do not build** a maker version (top-tick bids after the whistle: no fills behind 10^4–10^5 shares; before the whistle: the standing-order result), nor an NBA/NHL/NFL taker version.

---

## Ranked strategy table (Sports tab, $135 account)

| Rank | Strategy | Verdict | Realistic $ at $135 | What the worker needs | Main risks |
|---|---|---|---|---|---|
| 1 | Keep `finish.py` as an honest paper record: tick-aware band, gateway FT plus ESPN veto, `/book` depth, `RESOLVING` logged; add CFB/MLB/CBB | **Build** (about 2 h) | $0 (measurement) | League list +3, tick from `orderPriceMinTickSize`, ESPN scoreboard read, `/book` depth, extra columns | none; it is paper |
| 2 | Settlement yield at 0.985 on low-attention CFB (FCS/Ivy) and MLB after the gateway's FT | **Test** one month, FOK $10 | ≈$0.50–1.50 a week during CFB, $0 after the bowls | Item 1 plus a live FOK path under rule `finish` | unmeasured depth; a 30–75-min lock; FCS result corrections; one loss erases about 70 wins |
| 3 | Pregame reverse FLB in tennis/table tennis | **Skip** (verified on 2,922 kick-offs) | −$0.50 per $25 order (−2 points) | — | fee 0.10 on table tennis; integrity at ITF/Setka |
| 4 | Settlement yield in NBA/NHL/NFL (the earlier #1) | **Skip** | $0: no winner ask ≤0.99 after FT in 7 of 7 live finishes; 0/84 historical ≤0.985 in NBA/NHL, 2/53 in the NFL | — | the "0.99 ask" is the display clamp |
| 5 | Top-tick resting bids on the decided side (maker settlement yield) | **Skip** | ≈$0 (no fills behind 2.5k–900k-share queues; earlier = standing-order losses) | GTC and post-only | adverse selection before FT, queue position after |
| 6 | Player props on Atlas's numbers | **Skip** (keep recording) | negative at 2–6¢ spreads | nothing new | Atlas's Brier is worse than the close |
| 7 | Spread/total ladders and moneylines on Atlas's game models | **Skip** beyond the existing NCAAF-totals rule | ≈$0 | nothing new | NHL model worse than the close; NFL/NBA shares 1–4% |
| 8 | Futures and season-long markets | **Skip** | ≈$0, lock until 2027 | — | decided lines are `SOLVED` early; no carry |
| 9 | Combos/parlays | **Skip** | negative | authenticated RFQ | higher fee curve, maker correlation margin, LFMP legs |

---

## Data and scripts (`sports_data/`)

- `sports_latency.json`: per-game final-signal and book timeline for tonight's seven live finishes. `live_polls_2026-10-25.jsonl.gz`: the raw polls behind it (gateway event, `/book` summary with ≥0.95/≤0.05 levels and `sharesTraded`, ESPN, NHL api-web, NBA cdn 403s), 23:18–00:36 UTC.
- `windows.jsonl`: 330 recently settled games (249 usable) with `finishedTimestamp`, book-expiry time and last price. `window_tape.jsonl`: their 1-minute tapes around the window.
- `pregame_summary.txt`: the Q3 tables. `pregame_sample.csv`: per-match kick-off asks and results.
- `scripts/`: the poller (`poll.py`), `latency.py`, `window_fetch.py`, `window_tape.py`, `tape_analyze.py`, `pregame_fetch.py`, `pregame_analyze.py`. All are read-only against public endpoints. The poller adds a unique query string to `/book` and `/v1/events?slug=` to bypass the 30-s edge cache. That kept this measurement fresh at ≤3 req/s but goes against the docs' "cache ≥30 s" guidance, and production code should use the WebSocket instead.
