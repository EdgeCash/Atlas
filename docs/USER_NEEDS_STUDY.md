# Atlas — User Needs Study

What a sports fan, a bettor and a fantasy player leave Atlas to find, and what
it would take to keep them.

Every "data availability" judgement below was checked against the repository
rather than guessed. The warehouse holds **219 distinct measures**; the product
surfaces **27** of them.

---

## The finding that reorders everything

Before asking what Atlas is missing, it is worth knowing what Atlas already
has and does not show.

| Table | Measures | Shown on a page |
|---|---|---|
| `adjusted_efficiency_metrics` | 111 | 6 |
| `efficiency_metrics` | 36 | 2 |
| `games` | 29 | 5 |
| `context` | 22 | 2 |
| `ratings` | 20 | **0** |
| `talent` | 13 | **0** |
| `market_lines` | 13 | 10 |
| `outcomes` | 7 | 0 |

**192 of 219 computed measures never reach a reader.** Two whole tables —
SP+, FPI, Elo, recruiting rank, roster talent, returning production — are
completely unused by the product.

So the honest framing of this study is not *"what should Atlas add?"* It is
**"what should Atlas show?"**, followed by a much shorter list of things it
genuinely does not have.

---

## Persona 1 — the sports fan

*Watches games. Has never placed a wager. Arrived from a link.*

### Before the game

| Need | Frequency | Leaves Atlas? | Atlas has it? |
|---|---|---|---|
| Who is playing, when, on what channel | every visit | no | **shown** |
| Is this game any good | every visit | **yes** | rank shown; no "how close is this expected to be" |
| Team records | every visit | no | **shown** |
| Rankings (AP / Coaches poll) | weekly | **yes** | collected, used only to flag a ranked matchup |
| Standings and conference race | weekly | **yes** | derivable from `games`; **not built** |
| Recent form — last five results | every visit | **yes** | derivable; **not built** |
| Head-to-head history | occasionally | **yes** | derivable from `games`; used only for rivalry detection |
| Weather | when it matters | **yes** | temp and wind shown; humidity, precipitation and dome flag computed and hidden |
| Injuries | every visit | **yes** | **no source** |
| Where to watch | every visit | no | **shown** |

### During and after

Atlas is a **pre-kickoff product** by design. Live scores, drive charts and
box scores are all hard leaves, and all three should stay leaves — see
`ATLAS_ECOSYSTEM_VISION.md`.

The one post-game need worth taking seriously is **"was Atlas right?"**, which
nothing else can answer and which Atlas currently does not either.

### What a fan actually leaves for, ranked

| Rank | Need | Value | Frequency | Retention | Complexity | Data |
|---|---|---|---|---|---|---|
| 1 | **Injuries** | high | every visit | high | medium | **none free** |
| 2 | **Standings / conference race** | high | weekly | high | low | **have** |
| 3 | **Recent form** | medium | every visit | medium | low | **have** |
| 4 | **Poll rankings** | medium | weekly | medium | low | **have** |
| 5 | **Head-to-head history** | medium | occasional | low | low | **have** |
| 6 | **Full weather** | medium | seasonal | low | trivial | **have** |
| 7 | **Live scores** | high | game day | high | high | ESPN, but reject |

Items 2–6 are all *already computed and hidden*. Item 1 is the one Atlas
cannot get.

---

## Persona 2 — the bettor

*Reads the board. Already has three tabs open.*

Atlas does not serve this persona's transaction and never will. But this
persona is a large share of the traffic, and what they leave for is
diagnostic.

| Need | Leaves Atlas? | Atlas has it? | Should Atlas show it? |
|---|---|---|---|
| Line at multiple books | **yes** | **one provider only** | **yes** — as market depth, not as a price shop |
| Line movement history | partly | open and current only; snapshots exist in the tracker | **yes** |
| Injuries | **yes** | no source | if sourceable |
| Depth charts | **yes** | no source | no |
| Weather | **yes** | partly | **yes** |
| Team trends (ATS, over/under records) | **yes** | derivable | **no** — see below |
| Historical results vs the number | **yes** | `outcomes` has all of it | **carefully** |
| Public betting percentages | **yes** | no source | **no** |
| Sharp/steam indicators | **yes** | no | **no** |
| Closing line value | **yes** | researched in Phases 3–5 | **no** — published as a record, not a tool |

### The three hard rejects, and why

**Against-the-spread records.** "7-3 ATS in their last ten" is the single most
requested statistic in this category and it is the one Atlas must never
publish. It is a win-loss record, which `BRAND_GUIDE.md` forbids, and it is
also close to meaningless: ten games is noise, and the framing invites exactly
the reading Atlas exists to prevent.

**Public betting percentages.** Sourcing them means a data partnership with a
book or an aggregator, which is the first step toward affiliate revenue.

**Sharp money indicators.** An unfalsifiable claim about who is on which side.
Atlas cannot verify it and would be repeating somebody's marketing.

### Where the bettor's need and Atlas's identity agree

**Market depth.** Every card says `1 book quoting`. A bettor leaves because
one number is not a market. Adding providers gives the reader real market
information *and* gives the grade a per-card input it currently lacks — the
same change serves the research and the reader.

That is the template for everything in this study: **a feature is right when
the reader's need and the model's need are the same need.**

---

## Persona 3 — the fantasy player

*Sets a lineup. Cares about individuals, not teams.*

This is the persona Atlas serves worst, and the gap is structural.

| Need | Atlas has it? |
|---|---|
| Player usage, target share, carry share | **derivable** from play-by-play already downloaded |
| Starters and depth charts | **no source** |
| Injuries | **no source** |
| Matchup strength by position | partly — team defensive splits exist, not positional |
| Team pace | **have**, shown as a driver |
| Snap counts | not in the retained columns |
| Projections | **no** — and Atlas has no player-level model |

### The honest verdict

**Atlas should not serve the fantasy player, and should say so.**

Three reasons:

1. **Fantasy needs starters and injuries**, and those are exactly the two
   things with no free reliable source. A fantasy surface without them is
   worse than no fantasy surface.
2. **Atlas has no player-level model**, and `ATLAS_CARD_SPEC.md` already
   reserves player pages on exactly this ground: *"a page that looked like one
   would imply research that does not exist."*
3. **It is a different product.** Fantasy is about individuals in isolation;
   Atlas is about a game as a system. Serving both means the grade has to mean
   two things.

The play-by-play files do contain player-level data, so usage statistics are
technically reachable. Reachable is not a reason.

---

## The master ranking

Every item any persona leaves for, scored on the brief's five axes. Complexity
and data availability were checked against the repository.

| Item | Value | Frequency | Retention | Complexity | Data | Verdict |
|---|---|---|---|---|---|---|
| Market depth (2nd+ provider) | high | every visit | **high** | medium | tracker change | **must have** |
| Was Atlas right — public record | high | weekly | **highest** | medium | `outcomes` + tracker | **must have** |
| Standings / conference race | high | weekly | high | low | **have** | **must have** |
| Recent form (last five) | medium | every visit | medium | low | **have** | **must have** |
| Other models: SP+, FPI, Elo | high | every visit | medium | **trivial** | **have, 0% shown** | **must have** |
| Full weather | medium | seasonal | low | **trivial** | **have** | **must have** |
| Rest and travel | medium | every visit | low | **trivial** | **have, 0% shown** | **must have** |
| Head-to-head history | medium | occasional | low | low | **have** | nice to have |
| Poll rankings, full table | medium | weekly | medium | low | collected | nice to have |
| Talent / recruiting / returning production | medium | seasonal | low | **trivial** | **have, 0% shown** | nice to have |
| Line movement history | medium | every visit | medium | low | tracker snapshots | nice to have |
| Havoc, finishing drives, red zone | medium | every visit | low | low | **have** | nice to have |
| Schedule strength | medium | weekly | medium | medium | derivable | nice to have |
| Injuries | **highest** | every visit | high | **high** | **no free source** | **blocked** |
| Live scores | high | game day | high | high | ESPN | **avoid** |
| Box scores | medium | post-game | medium | medium | derivable | **avoid** |
| Depth charts | high | every visit | medium | high | no source | **avoid** |
| Player usage / fantasy | high | weekly | high | high | derivable | **avoid** |
| ATS and over/under records | high | every visit | medium | low | derivable | **avoid** |
| Public betting percentages | high | every visit | medium | medium | no source | **avoid** |
| Sharp money indicators | medium | every visit | low | high | no source | **avoid** |
| News and analysis articles | medium | daily | high | **very high** | none | **avoid** |
| Odds comparison across books | high | every visit | medium | medium | partial | **avoid** |

---

## What this study concludes

**Seven of the eight "must have" items are already computed and hidden.** The
eighth — a public record of whether Atlas was right — is built on data Atlas
already stores.

The single most valuable thing to a user that Atlas *cannot* do is injuries.
Everything else at the top of the list is a rendering problem, not a data
problem.

And the items that would most obviously grow traffic — live scores, ATS
records, odds comparison, fantasy — are all in the reject column, because each
one would make Atlas a worse version of a site that already exists.
