# Atlas — Feature Roadmap

The sequencing, and the final Top 10.

Nothing here is built. This is what Atlas should eventually become and in what
order.

---

## The Top 10

Ranked by traffic, retention and subscriber value **without harming Atlas's
identity**. Data availability was checked against the repository.

### 1 · The public reliability record

*What Atlas said, and what happened. Updating weekly, all season.*

| | |
|---|---|
| Traffic | medium — it is not a search destination |
| Retention | **highest of anything in this study** |
| Subscriber value | **it is what the paid archive is made of** |
| Data | `outcomes` + the live tracker. **Have it.** |
| Difficulty | M |

The only feature that compounds, changes without new games, and cannot be
copied — it requires having published a per-item reliability claim in advance,
which requires a grade, which nobody else has.

A grade without a record is a promise. **Must be calibration — claimed against
realised, with sample sizes — never a win-loss record.**

### 2 · A second market data provider

*Real depth behind every number.*

| | |
|---|---|
| Traffic | low directly |
| Retention | high — market depth is a daily reason to look |
| Subscriber value | high — snapshot history is a premium surface |
| Data | **needs a new source.** The only item in the Top 10 that does. |
| Difficulty | M |

Every card says `1 book quoting`. A bettor leaves because one number is not a
market, and the grade carries a component with no information in it. **The
reader's need and the model's need are the same need**, which is the strongest
signal a feature is right.

### 3 · The "other models" panel

*SP+, FPI, Elo, beside Atlas. No verdict.*

| | |
|---|---|
| Traffic | **high** — "SP+ rankings" is a real search query |
| Retention | medium |
| Subscriber value | low — this must be free |
| Data | **in the warehouse. Shown on zero pages.** |
| Difficulty | **S** |

The best value-per-hour item in the entire study. 20 columns of `ratings` —
SP+ overall and split, FPI, FPI win probability, pregame Elo — all
point-in-time safe, all computed on every build, all invisible.

It also strengthens the grade: a reader can see when Atlas is the outlier
rather than taking Atlas's word for its own uncertainty.

### 4 · Grade movement

*The letter this card opened at, and the letter it holds now.*

| | |
|---|---|
| Traffic | low |
| Retention | **high — the only genuine daily change Atlas has** |
| Subscriber value | medium |
| Data | computed; needs one stored number per card per day |
| Difficulty | M |

Grade V2 created a daily product by accident and nothing surfaces it. *"Six
cards changed grade since Tuesday"* is a reason to visit that no competitor
can copy.

**Never an alert.** Shown when a reader arrives, never pushed.

### 5 · Standings and the conference race

| | |
|---|---|
| Traffic | **high** — a durable, seasonal search query |
| Retention | **high** — weekly, and it changes whether or not you watched |
| Subscriber value | low |
| Data | derivable from `games` |
| Difficulty | S |

The cheapest high-retention item on the list, and the one most likely to bring
in readers who have never heard of a calibration gap.

### 6 · The weekly email

| | |
|---|---|
| Traffic | it *is* traffic |
| Retention | **high — the only push channel Atlas will ever have** |
| Subscriber value | the free tier's email is the paid tier's proof |
| Data | have |
| Difficulty | M |

Specified in `EMAIL_STRATEGY.md`. Needs a sender and the waitlist form from
`WAITLIST_STRATEGY.md`.

### 7 · The full context block

*Rest, travel, weather, dome, neutral site.*

| | |
|---|---|
| Traffic | low |
| Retention | low |
| Subscriber value | low |
| Data | **in the warehouse. Rest and travel are parsed into the card object and then dropped.** |
| Difficulty | **S** |

Low on value and high on the list because it is nearly free, and because
"rest and travel are computed but not rendered" is the kind of thing that is
embarrassing once someone notices.

### 8 · Team page depth

*Form curve, schedule strength, every Atlas card that team has had.*

| | |
|---|---|
| Traffic | **high — the only surface that improves rather than staling** |
| Retention | high |
| Subscriber value | medium |
| Data | derivable |
| Difficulty | M |

Game cards have a one-week shelf life and no inbound links. Team pages
accumulate. For search, this is the durable base.

### 9 · Line movement history

*Every snapshot, not just open and current.*

| | |
|---|---|
| Traffic | low |
| Retention | medium |
| Subscriber value | **high — this is a premium surface** |
| Data | the tracker already stores it |
| Difficulty | S |

Free readers see open and current; premium sees every snapshot. A clean
free/paid boundary that costs the free reader nothing.

### 10 · The compact board table

*A dense view for a laptop. Sortable by time, grade and team.*

| | |
|---|---|
| Traffic | medium |
| Retention | medium |
| Subscriber value | low |
| Data | have |
| Difficulty | M |

The one genuine gap against BettorSheets. **Not sortable by difference** —
that turns a research tool into a ranked list of opportunities without anyone
deciding to.

---

## Sequencing

### Now — before anything else on this list

Two items from `LAUNCH_CHECKLIST.md` outrank every feature here:

1. **The jurisdiction question.** Legal, blocking, not a product decision.
2. **A scheduled refresh and rebuild.** Without it the board goes stale
   mid-week. It is the one operational gap a reader would notice.

### Phase A — the card, completed *(weeks)*

Top 10 items **3**, **7**, and the derivable parts of **8**.

All rendering. No new sources, no new research, no new page types. The theme:
**stop hiding what is already computed.** 192 of 219 measures currently reach
nobody.

Ship these first because they are cheap, they are safe, and they make the card
materially better without touching anything approved.

### Phase B — the record *(a month)*

Top 10 items **1** and **4**.

The strategic phase. Everything in `ATLAS_ECOSYSTEM_VISION.md` Layer 2, and
the only work in this roadmap that a competitor could not copy.

Do it before premium. The archive is what premium sells and the record is what
makes the archive worth paying for.

### Phase C — depth and distribution *(a season)*

Top 10 items **2**, **5**, **6**, **8** in full, **9**, **10**.

Market depth is here rather than in Phase A only because it needs a new
source; if a provider is easy to add, it moves up.

### Phase D — the paid tier

Only after Phase B has been live long enough that the record is worth
something. `FREE_VS_PREMIUM_FINAL.md` already draws the line: this week is
free, history and depth are paid.

### Never

Live scores · ATS records · odds comparison · public betting percentages ·
sharp-money indicators · fantasy tools · player projections · news · box
scores · a card of the day · alerts · leaderboards · gamification · other
sports · a forum.

Each is argued in `TOP_25_FEATURES.md`. Each would work. That is why the
rejection is written down now rather than decided later in front of a traffic
graph.

---

## What this roadmap is really saying

**Atlas does not have a feature problem. It has a publishing problem.**

Of the Top 10: **six** use data sitting in the warehouse today, **three** are
derivable from files already downloaded, and **one** needs a new source.

The biggest strategic move available — the public reliability record — needs
no new data at all. It needs Atlas to keep score of itself in public, which is
what it has been claiming to do since Phase 3.

---

## The one-line version

> Show what is already computed. Then publish whether it was right. Then sell
> the archive of both.
