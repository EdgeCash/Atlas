# Atlas — Top 25 Candidate Features

Every candidate that survived the Atlas Test, plus the rejects listed
separately so the reasoning is on the record.

**Scales.** User value, retention and strategic fit: 1–5. Difficulty: S
(hours), M (days), L (weeks), XL (a project). Data: **have** (in the
warehouse), **derive** (computable from what is downloaded), **collect** (new
source needed), **none** (no free source).

---

## The 25

| # | Feature | Value | Retention | Difficulty | Fit | Data |
|---|---|---|---|---|---|---|
| 1 | **Public reliability record** — what Atlas said, what happened, updating weekly | 5 | **5** | M | **5** | have |
| 2 | **Second market provider** — real depth behind every number | 5 | 4 | M | **5** | collect |
| 3 | **Other models panel** — SP+, FPI, Elo beside Atlas on every card | **5** | 3 | **S** | **5** | **have, 0% shown** |
| 4 | **Grade movement** — the letter this card opened at, and holds now | 4 | **5** | M | **5** | have |
| 5 | **Line movement history** — every snapshot, not just open and current | 4 | 4 | S | 5 | have |
| 6 | **Standings / conference race** | 4 | **5** | S | 4 | derive |
| 7 | **Weekly email** | 4 | **5** | M | 4 | have |
| 8 | **Recent form** — last five, by efficiency not score | 4 | 3 | S | 4 | derive |
| 9 | **Full context block** — rest, travel, weather, dome, neutral site | 4 | 2 | **S** | **5** | **have, 0% shown** |
| 10 | **Head-to-head history** on a card | 3 | 2 | S | 4 | derive |
| 11 | **Compact board table** — dense view, sortable by time/grade/team | 4 | 3 | M | 4 | have |
| 12 | **Talent block** — recruiting rank, returning production, roster talent | 3 | 2 | **S** | 4 | **have, 0% shown** |
| 13 | **Extra drivers** — havoc, finishing drives, red zone | 3 | 2 | S | 4 | have |
| 14 | **Season grade distribution** — where this card sits against the season | 3 | 3 | S | 5 | have |
| 15 | **Archive of past weeks** | 3 | 4 | M | 4 | have |
| 16 | **Team page depth** — form curve, schedule strength, card history | 4 | 4 | M | 4 | derive |
| 17 | **Poll rankings, full table** | 3 | 3 | S | 3 | have |
| 18 | **Schedule strength, point-in-time** | 3 | 3 | M | 4 | derive |
| 19 | **Conference pages** | 3 | 3 | M | 3 | derive |
| 20 | **A model-disagreement view** — where Atlas, SP+ and FPI disagree most | 3 | 3 | M | **5** | have |
| 21 | **Explainer pages** — what EPA is, what calibration is | 3 | 2 | M | 4 | none |
| 22 | **Data export** (premium) | 2 | 2 | S | 3 | have |
| 23 | **Card permalinks by week** — stable URLs for past cards | 2 | 3 | S | 4 | have |
| 24 | **Weather detail page** — the seasonal explainer | 2 | 1 | M | 3 | have |
| 25 | **Injuries** — if a licensable source is ever found | **5** | 4 | **XL** | 4 | **none** |

---

## Notes on the ones that need them

**#1 Public reliability record.** The highest item in this document and in
`RETENTION_DRIVERS.md`. It is the only feature that compounds, the only one
that changes without new games, and the only one no competitor can build
because it requires having published a per-item reliability claim in advance.

It must be a **calibration** record — claimed against realised, with sample
sizes — and never a win-loss record.

**#2 Second market provider.** The one feature where the reader's need and the
model's need are identical. Every card says `1 book quoting`; a bettor leaves
because one number is not a market, and the grade has a component that
currently carries no information. One change fixes both.

**#3 Other models panel.** The cheapest high-value item on the list by a
distance. SP+, FPI, Elo and FPI's own win probability are **already in the
warehouse, already point-in-time safe, and shown on zero pages.** A panel
reading *"SP+ has Miami by 38, FPI by 44, Atlas by 41.5"* is context in the
strictest sense — a second opinion, presented without a verdict.

It also strengthens the grade's honesty: a reader can see when Atlas is the
outlier.

**#4 Grade movement.** Grade V2 created a daily product by accident and
nothing surfaces it. Cost is one stored number per card per day.

**#9 Full context block.** Rest days, travel distance, humidity, precipitation,
dome and neutral-site flags are all computed and **rendered nowhere** — rest
and travel are even parsed into the `Side` object and then dropped. This is a
template change, not a feature.

**#11 Compact board table.** The one genuine gap against BettorSheets. **Must
not be sortable by difference** — sorting by difference turns a research tool
into a ranked list of opportunities without anyone deciding to.

**#20 Model-disagreement view.** The most Atlas-shaped idea in this list. Not
*"where is the value"* but *"where do the public models disagree with each
other"*, which is a genuinely interesting question about the sport and says
nothing about what anyone should do.

**#25 Injuries.** Ranked last on feasibility, not on value — it is the single
most valuable item to every persona. There is no free reliable source, and a
partial injury feed is worse than none because readers would assume
completeness.

---

## The rejects, and why

Each of these would plausibly raise traffic. Each fails the Atlas Test: it
copies another site rather than strengthening research, analytics or context.

| Rejected | Would it work? | Why it is rejected |
|---|---|---|
| **Live scores and in-game updates** | yes, hugely | Atlas is pre-kickoff. Motion implies urgency; nothing on Atlas moves. ESPN wins this outright. |
| **ATS / over-under records** | yes | a win-loss record, forbidden by `BRAND_GUIDE.md`, and statistically empty at the sample sizes people quote |
| **Odds comparison across books** | yes | price shopping is a transaction tool, and it is one step from affiliate revenue |
| **Public betting percentages** | yes | sourcing requires a book partnership |
| **Sharp money / steam indicators** | yes | unverifiable; publishing it is repeating somebody's marketing |
| **Fantasy tools, usage, depth charts** | yes | no player model, no injuries, no starters. `ATLAS_CARD_SPEC.md` already reserves player pages on this ground |
| **Player projections** | yes | would imply research that does not exist |
| **News, articles, beat coverage** | yes | a newsroom is a different company |
| **Box scores and recaps** | moderately | the past belongs to Sports Reference; Atlas's version of "what happened" is the reliability record |
| **A card of the day** | very strongly | a selection with the word removed |
| **Alerts on line movement** | yes | urgency, and a push Atlas has no right to send |
| **A leaderboard of cards** | yes | the grade cannot honestly rank — `GRADE_STRATEGY_V2.md` §5 |
| **Streaks, badges, gamification** | yes | nothing to gamify that is not a selection |
| **Other sports** | yes | NCAAF only, NFL staged. Every sport added divides the calibration work |
| **A community or forum** | yes | moderation is a company, and the first thread would be people posting selections under Atlas's brand |

---

## The pattern in the rejects

Every rejected feature falls into one of three shapes:

1. **It requires a verdict Atlas will not give** — picks, leaderboards,
   rankings by difference, cards of the day.
2. **It requires being a different company** — a newsroom, a moderation team,
   a live data operation, an odds marketplace.
3. **It requires research that does not exist** — player projections, fantasy
   rankings, anything player-level.

If a future feature does not fit one of those three shapes, it is probably
worth considering. If it does, the answer is already written down.

---

## What the list adds up to

Of the 25:

- **9 use data already in the warehouse and shown on zero pages.**
- **6 are derivable** from files already downloaded.
- **1 needs a new source** (#2, market depth) and it is the second-ranked item.
- **1 is blocked** with no free source (#25, injuries).

**The single most striking number in this study: 192 of 219 computed measures
never reach a reader.** Atlas's expansion problem is not a data problem. It is
a publishing problem.
