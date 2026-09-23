# Atlas — Retention Drivers

What brings somebody back, on what cycle, and what Atlas has.

---

## The problem, stated plainly

**Atlas has no daily reason to exist and a weak weekly one.**

The board shows this week's cards. A reader who has seen them has seen
everything. The cards do not change between Tuesday and Saturday in any way a
reader would notice, there is nothing to check, and nothing accumulates.

`POST_LAUNCH_METRICS.md` names this as a falsifiable claim; this document is
the analysis behind it.

---

## The three cycles

### Daily — *is there anything new today?*

The hardest cycle to earn and the easiest to fake. Most products fake it with
urgency: a new pick, a countdown, an alert.

| Candidate | Genuinely changes daily? | Atlas has it? | Verdict |
|---|---|---|---|
| Line movement | **yes** — this is the only thing that moves every day | tracker captures it; card shows open and current only | **the real daily driver** |
| Grade movement | **yes** under V2 — a card's letter moves with the market | computed; not tracked across the week | **the Atlas-shaped version** |
| Injuries | yes | no source | blocked |
| Live scores | game day only | reject | — |
| News | yes | no newsroom | reject |
| A "card of the day" | manufactured | — | **reject — it is a selection** |

**The finding:** Grade V2 accidentally created a daily product and nothing
surfaces it. A card graded B on Tuesday can be C by Saturday because the line
moved away from Atlas's number. That is a real, computed, honest daily change,
and it is currently invisible.

**"Six cards changed grade since Tuesday"** is a daily reason to visit that no
competitor can copy, because no competitor grades.

### Weekly — *the new slate*

The cycle Atlas is natively built for, and where it is currently adequate
rather than strong.

| Candidate | Atlas has it? | Retention value |
|---|---|---|
| The new board | ✓ | **high** — the product's heartbeat |
| Marked-down cards | ✓ | **high** — the most distinctive weekly artefact |
| Standings / conference race | derivable, not built | **high** |
| Poll rankings | collected, barely used | medium |
| The weekly email | specified, not built | **high** — the only push channel |
| Recent form | derivable, not built | medium |

**The finding:** the weekly cycle needs almost nothing new. A conference-race
view and the weekly email are both cheap, and both give a reader a reason to
open Atlas on a Tuesday rather than only on a Saturday.

### Seasonal — *does this accumulate?*

The cycle that decides whether Atlas is a tool or a habit.

| Candidate | Atlas has it? | Retention value |
|---|---|---|
| **The reliability record, updating in public** | data exists; **not built** | **highest of anything in this document** |
| Team pages that deepen as the season runs | partially built | high |
| Season-long grade distribution | computed every build | medium |
| Archive of past weeks | stored; not browsable | medium — and it is the premium surface |
| Research write-ups | exist as repo docs | medium |

---

## The ranking

Every retention candidate, ordered by how much a reader would come back for
it.

| # | Driver | Cycle | Atlas has the data? | Built? |
|---|---|---|---|---|
| 1 | **Was Atlas right?** — the public record | seasonal | **yes** | **no** |
| 2 | **Grade movement during the week** | daily | **yes** | **no** |
| 3 | **The weekly board** | weekly | yes | **yes** |
| 4 | **The weekly email** | weekly | yes | **no** |
| 5 | **Marked-down cards** | weekly | yes | **yes** |
| 6 | **Line movement history** | daily | **yes** | partly |
| 7 | **Standings / conference race** | weekly | **yes** | **no** |
| 8 | **Team pages that accumulate** | seasonal | yes | partly |
| 9 | **Recent form** | weekly | **yes** | **no** |
| 10 | **Poll rankings** | weekly | yes | barely |

**Six of the top ten are unbuilt, and every one of those six uses data Atlas
already has.**

---

## Why "was Atlas right" is first by a distance

It is the only item on this list that satisfies all four of:

- **It changes without new games.** A season's worth of graded cards keeps
  resolving; the record moves every week whether or not the reader watched.
- **It compounds.** Every week makes it more valuable, which is the definition
  of a reason to stay rather than a reason to visit.
- **Nobody else can build it.** It requires having published a per-item
  reliability claim in advance — which requires a grade — which nobody else
  has.
- **It is the product's own claim, audited.** Atlas says a grade means
  something. The record is the evidence. Without it, the grade is a promise.

It also converts Atlas's biggest liability into its strongest asset: a model
that is wrong sometimes is a model whose honesty can be checked.

**What it would show:** cards graded A, B, C and marked down, against what
actually happened. Claimed against realised, updating weekly, with the
sample size beside it. Exactly the research page's table, but *live* and
*about this season* rather than about seven finished ones.

**What it must not show:** a win-loss record, a hit rate framed as
performance, or anything that reads as a scoreboard. It is a calibration
record, and the difference is the whole product.

---

## Why grade movement is second

It is the only genuine **daily** change Atlas has, it is free, and it is a
side effect of a decision already made.

Under V1 a card had to cross a band boundary to change letters. Under V2 every
tick of the market moves the score. That means the board is quietly different
every day and a reader has no way to see it.

**What it would show:** on a card, the grade it opened at and the grade it
holds now. On the board, a count — *"six cards changed grade since Tuesday."*

**Cost:** storing one number per card per day. The tracker already writes
snapshots; this is a column, not a system.

**What it must not become:** an alert, a notification, or a reason to hurry.
It is a fact about the week, shown when a reader arrives — never pushed.

---

## The anti-drivers

Things that would raise return visits and should be rejected anyway.

| Anti-driver | Why it works | Why it is rejected |
|---|---|---|
| A daily card of the day | strongest possible daily habit | it is a selection with the word removed |
| Alerts when a line moves | high engagement | urgency; nothing on Atlas moves or interrupts |
| A public leaderboard of cards | ranking is addictive | the grade cannot honestly rank — see `GRADE_STRATEGY_V2.md` §5 |
| Win-loss record for Atlas | the number everybody wants | forbidden, and less informative than calibration |
| Streaks and badges | gamification retains | Atlas has nothing to gamify that is not a selection |
| Fantasy tools | very high weekly retention | no player model, no injuries, no starters |

Each of these would work. That is exactly why the rejection has to be written
down before anyone is looking at a traffic graph.

---

## The shape of a retained reader

If all of the above goes right:

| | |
|---|---|
| **Tuesday** | the new board is up; the weekly email arrives; the conference race moved |
| **Wednesday–Friday** | lines move, grades move, a handful of cards get marked down |
| **Saturday** | the board is the plan for the day |
| **Sunday** | the record updates: here is what Atlas said, here is what happened |
| **All season** | the record compounds, and the team pages deepen |

Atlas currently has **Saturday**, and a weak version of Tuesday.

The gap between that table and today's product is four unbuilt features, all
of which use data that is already in the warehouse.
