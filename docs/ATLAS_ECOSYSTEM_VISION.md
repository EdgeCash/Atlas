# Atlas — Ecosystem Vision

How Atlas becomes a one-stop sports intelligence platform without becoming
ESPN, CBS, an affiliate site, or a picks service.

---

## The question is wrong, slightly

"One-stop" usually means *every fact on one page*. Measured that way Atlas
loses, permanently and by a lot: ESPN has more data, CBS has more surfaces,
Sports Reference has more history, Action Network has more market tools.
Matching them feature for feature produces the sixth-best version of each.

The useful reading is different. A reader does not want every fact. They want
**to stop needing another tab for the question they arrived with**.

So the strategy is not *cover everything*. It is:

> **Own one question completely, and answer every follow-up it generates.**

Atlas's question is: **how much is this number worth?**

Everything a reader needs to answer *that* belongs on Atlas. Everything else
is somebody else's question, and linking out is not a failure.

---

## The five follow-up questions

A reader who accepts Atlas's question asks these next, in this order. They are
the entire expansion surface.

| # | Follow-up | Where they go today | Atlas has the data? |
|---|---|---|---|
| 1 | *What do other models say?* | ESPN for FPI, elsewhere for SP+ | **yes — and shows none of it** |
| 2 | *How did this number get here?* | Action Network | **yes — tracker snapshots** |
| 3 | *How many books agree?* | an odds screen | **no — one provider** |
| 4 | *How has this team actually been?* | ESPN, Sports Reference | **derivable** |
| 5 | *Was Atlas right last time?* | **nowhere — nobody has this** | **yes — unbuilt** |

**Four of five are rendering problems.** One needs a data source. And the
fifth — the only one with no competitor at all — is the one that would make
the other four matter.

That is the whole ecosystem strategy. It is much smaller than it sounds.

---

## What Atlas becomes

> **The place you go to find out whether a number is worth trusting — and the
> only place that keeps score of its own answer.**

Three layers, in the order they should be built.

### Layer 1 — the card, completed

The card already answers *what the market says*, *what Atlas says*, *why*, and
*how much to trust it*. It should also answer:

- **what everyone else says** — SP+, FPI, Elo, side by side, no verdict
- **how the number got here** — the full movement history, not just open and
  current
- **who is playing under what conditions** — rest, travel, weather, dome,
  neutral site, all computed and currently rendered nowhere
- **how these two have gone before** — head-to-head, and recent form by
  efficiency rather than by score

None of this is new data. All of it is currently in a parquet file that no
reader can see.

### Layer 2 — the record

**The thing nothing else in the category can build.**

Atlas publishes a per-item reliability claim in advance. That makes a public,
updating record of whether those claims held not just possible but obligatory
— a grade without a record is a promise.

It is also the only surface that:

- changes without new games being played,
- compounds rather than refreshing,
- and converts the product's biggest liability into its strongest asset.

A model that is sometimes wrong is a model whose honesty can be checked. That
is worth more than a model that is never seen to be wrong.

### Layer 3 — the season

Team pages that deepen as the season runs, the conference race, the archive,
schedule strength. The layer that makes Atlas a place rather than a tool.

This is also where premium lives, per `FREE_VS_PREMIUM_FINAL.md`: **this week
is free; history, depth and delivery are paid.** Layer 3 is what the paid tier
is made of, which is why it should not be built before Layer 2 makes it worth
paying for.

---

## What Atlas does not become

### Not ESPN

ESPN's job is **immediacy and breadth**. Atlas's is **judgement about a
number**. Atlas will not carry live scores, video, news or box scores, and
should link out for them without apology.

The failure mode is specific: the first live score on Atlas creates a reason
for the page to move, and everything about the product's credibility comes
from being the thing in this category that does not move.

### Not CBS Sports

CBS is what happens when a product does five things adequately. Atlas does one
thing that nobody else does at all. The moment it adds fantasy tools it has
two products, each half-resourced, and the grade has to mean two things.

### Not an affiliate site

No affiliate revenue, ever — `FREE_VS_PREMIUM_FINAL.md` rule 4. This is the
rule most likely to cost real money and the one least open to revisiting.

The tell is subtle and worth naming: **odds comparison is the gateway.** It
looks like information, it is genuinely useful, and it is one product meeting
away from a "bet now" button. Atlas can report **how many books agree** —
market depth, which is information — and must not build **where to get the
best price**, which is a transaction tool.

### Not a picks service

The line is already drawn and tested. What this study adds is the list of
features that would cross it **without ever using the word**: a card of the
day, a leaderboard, sorting the board by difference, ATS records, sharp-money
indicators. Each is a selection with the noun removed.

---

## The Atlas Test, as a usable rule

Every proposed feature must strengthen **research**, **analytics** or
**context**:

- **Research** — does it show how Atlas knows something, or whether it was
  right?
- **Analytics** — does it measure something, out of sample, that a reader
  could check?
- **Context** — does it help a reader understand the game, without implying
  what to do about it?

If none, it copies another site. Reject.

Two sharpening questions, because "context" is where discipline erodes:

1. **Would this feature be equally useful to someone who never wagers?** If
   no, it is a transaction tool wearing a context costume.
2. **Could this be screenshotted and read as a recommendation?** If yes, it
   needs the grade beside it or it does not ship.

---

## The one-stop claim, honestly stated

Atlas will never be where a reader gets everything. It can be where they get
**the answer to one question, completely**, and that is a defensible position
in a way that breadth is not.

The finished sentence:

> **Atlas is where you find out what a game's numbers are worth — and the only
> place that publishes whether it was right.**

Two clauses. The first is the product. The second is the moat, and it is
currently unbuilt.

---

## The measurement

`POST_LAUNCH_METRICS.md` already names the number this vision lives or dies
by: **the share of readers who open a marked-down card.**

The ecosystem version of the same test: **does the reliability record become
the most-visited page on the site within a season?**

If it does, Atlas is a research product with an audience. If the most-visited
page is the board and nothing else, Atlas is a weekly utility — useful, but
replaceable by anyone who copies the card.
