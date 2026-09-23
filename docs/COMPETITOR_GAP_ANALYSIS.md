# Atlas — Competitor Gap Analysis

Seven products. For each: what users are there for, whether Atlas *could*
provide it, and whether Atlas *should*.

`COMPETITOR_ANALYSIS.md` covered the design patterns. This covers the
information.

---

## The three-question test

For every capability:

1. **Why do users go there?** — the job, not the feature.
2. **Could Atlas provide it?** — checked against the warehouse.
3. **Should Atlas provide it?** — the Atlas Test: does it strengthen
   **research, analytics or context**, or does it copy another site?

Question 3 is the one that decides. Most answers to question 2 are yes.

---

## ESPN

**Users are there for:** live scores, news, injuries, schedules, standings,
video, and the fact that it is the default.

| Capability | Could Atlas? | Should Atlas? | Why |
|---|---|---|---|
| Live scores | yes (ESPN feed already used) | **no** | Atlas is pre-kickoff. Motion implies urgency; nothing on Atlas moves. |
| Schedules | **already has** | partly | the board is a schedule with an opinion attached |
| Standings | **yes**, derivable from `games` | **yes** | a conference race is context, and it is the cheapest retention item on the list |
| Injuries | **no free source** | if sourceable | genuine context; the only high-value item Atlas cannot reach |
| News and video | no | **no** | a newsroom is a different company |
| Box scores | derivable | **no** | the past belongs to reference sites; Atlas's version of "what happened" is the reliability record |
| FPI | **already in the warehouse, 0% shown** | **yes** | a second opinion is context, and Atlas has it already |

**Verdict:** ESPN wins on breadth and immediacy and Atlas should not contest
either. The two things worth taking are **standings** and **FPI** — and Atlas
already has both.

---

## The Athletic

**Users are there for:** writing. A named person's judgement, in long form,
about a team they follow.

| Capability | Could Atlas? | Should Atlas? |
|---|---|---|
| Beat reporting | no | **no** |
| Long-form analysis | in principle | **no** |
| A named voice | — | **no** |
| Charts that carry an argument | **yes** | **yes** — the research page already does this |

**Verdict:** the only thing to take is the *standard of presentation*, which
`COMPETITOR_ANALYSIS.md` already recorded. Content that requires a writer is
content Atlas cannot produce at the scale of 58 cards a week, and a weekly
essay would be the most expensive and least differentiated thing on the site.

**One exception worth naming:** The Athletic's accountability comes from a
byline. Atlas's equivalent is the reliability record — a model that publishes
its own failures. That is the same move, made by arithmetic instead of a
person, and it is currently not built.

---

## Action Network

**Users are there for:** odds comparison, line movement, public betting
percentages, and selections.

| Capability | Could Atlas? | Should Atlas? | Why |
|---|---|---|---|
| Odds across books | partly — one provider today | **no, as a shop; yes, as depth** | comparing prices is a transaction tool. Counting how many books agree is market information. Same data, different product. |
| Line movement | **yes** — tracker snapshots exist | **yes** | how a number got where it is, is context |
| Public betting percentages | no source | **no** | sourcing means a book partnership, which is step one toward affiliate revenue |
| Sharp money indicators | no | **no** | unverifiable; repeating it is repeating marketing |
| Selections | — | **never** | the one thing Atlas will not do |
| ATS records | derivable | **no** | a win-loss record, forbidden, and statistically empty at the sample sizes shown |

**Verdict:** this is the closest competitor and the most dangerous one to
learn from. The useful distinction: **Atlas can report the market; it cannot
help anyone transact in it.** Depth and movement pass. Everything else fails.

---

## BettorSheets

**Users are there for:** a dense sortable sheet of model numbers beside market
numbers.

| Capability | Could Atlas? | Should Atlas? |
|---|---|---|
| Model vs market, every game | **already has** | **yes** — it is the product |
| Sortable, dense table view | **yes**, easily | **partly** |
| Sort by difference | **yes** | **no** |

**Verdict:** Atlas already does the substance and does it better, because
every row carries a grade and BettorSheets' rows do not.

The one real gap is **a dense view**. The board is a card-first experience
designed for a phone; a reader with 58 games and a laptop wants a table. That
is a legitimate view of data Atlas already has — but it must not be sortable
by difference, because sorting by difference turns a research tool into a
ranked list of opportunities without anyone deciding to.

**Recommendation:** a compact table view, sortable by kickoff, grade and team.
Not by difference.

---

## CBS Sports

**Users are there for:** scores, fantasy, news, and expert picks.

| Capability | Could Atlas? | Should Atlas? |
|---|---|---|
| Fantasy tools | technically | **no** — no player model, no injuries, no starters |
| Expert picks | — | **never** |
| Scores and news | — | **no** |

**Verdict:** nothing to take. CBS is the clearest illustration of the failure
mode — a site that does five things adequately and nothing better than anyone
else.

---

## Pro Football Reference / Sports Reference

**Users are there for:** the authoritative historical record. Every game, every
season, every split, permanently addressable and never wrong.

| Capability | Could Atlas? | Should Atlas? | Why |
|---|---|---|---|
| Complete historical results | **has nine seasons** | **partly** | not as a reference archive — Sports Reference wins that outright — but as *Atlas's own* history |
| Head-to-head records | **derivable** | **yes** | context on a card, not a database |
| Season splits and team history | **has** | **partly** | the team page is the right home for a compact version |
| Permanent, citable URLs | **yes** | **yes** | Atlas's team pages are the only surface that improves rather than staling |

**Verdict:** the most instructive comparison in this list.

Sports Reference is the durable, linkable, trusted layer of this category, and
it got there by being complete and never editorialising. Atlas cannot compete
on completeness of the historical record — but it holds one historical record
nobody else has: **what Atlas said, and what happened.**

That is the Atlas-shaped version of a reference site, and it is the highest
item on the retention list.

---

## The gap map

| | ESPN | Athletic | Action | BettorSheets | CBS | Sports Ref | **Atlas** |
|---|---|---|---|---|---|---|---|
| Live scores | ✓ | — | ✓ | — | ✓ | — | **reject** |
| Schedules | ✓ | — | ✓ | ✓ | ✓ | ✓ | ✓ |
| Standings | ✓ | — | — | — | ✓ | ✓ | **gap, have data** |
| Injuries | ✓ | ✓ | ✓ | — | ✓ | — | **gap, no source** |
| Model vs market | — | — | ✓ | ✓ | — | — | ✓ |
| Line movement | — | — | ✓ | partly | — | — | **gap, have data** |
| Odds across books | — | — | ✓ | ✓ | — | — | **reject as a shop** |
| Multiple model opinions | ✓ (FPI) | — | — | — | — | — | **gap, have data** |
| Historical record | ✓ | — | — | — | ✓ | ✓✓ | partial |
| **Per-item reliability** | — | — | — | — | — | — | **only Atlas** |
| **Publishes own failures** | — | — | — | — | — | — | **only Atlas** |
| Selections | — | — | ✓ | ✓ | ✓ | — | **never** |

Two rows have a single tick and both of them are Atlas. Everything else on the
board is available somewhere, usually better resourced.

---

## What this means for expansion

**Atlas cannot win breadth and should stop considering it.** ESPN has more
data, CBS has more surfaces, Sports Reference has more history, Action has
more market tools. A one-stop platform built by matching them feature for
feature would be the sixth-best version of each.

**The one-stop question has a different answer.** A reader does not want every
fact on one page; they want *to stop needing another tab for the question they
came with*. Atlas's readers came with a question about **whether a number is
worth trusting** — and for that question, the missing tabs are:

1. *What do other models say?* — SP+, FPI, Elo. **In the warehouse. Not shown.**
2. *How did this number get here?* — line movement. **In the tracker. Not shown.**
3. *How many books agree?* — market depth. **One provider. Tracker change.**
4. *How has this team actually been?* — form, standings, head-to-head.
   **Derivable. Not built.**
5. *Was Atlas right last time?* — **Nobody has this. Not built.**

Five gaps. Four are rendering. One is the product's whole reason to exist and
is the only thing on this page no competitor could copy.
