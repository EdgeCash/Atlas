# Atlas — Waitlist Strategy

**Track 8.** No payments. No subscriptions. No monetisation.

Rule 3 is absolute: nothing in this document builds a checkout, and selling
before product-market fit is forbidden. What follows is a list, a form and a
name — nothing else.

---

## What the list is actually for

Not "future customers". **A way to find out whether anyone comes back.**

`POST_LAUNCH_METRICS.md` names the problem plainly: there is currently no
reason to visit Atlas between slates. The board shows this week; a reader who
has seen it has seen everything. The weekly email is the first thing that gives
a reader a reason to return, and the list is how that gets tested.

So the list's success measure is not its size. It is **the click-through from
the weekly email to a marked-down card**, because that is the same positioning
test the social playbook runs, in a channel where the audience opted in.

---

## The offer

One email a week. That is the whole thing.

> **Atlas sends one email a week.** The board, the rivalries, the cards it has
> marked down, and one paragraph on what the record did. No selections, no
> urgency, one click to leave.

What the offer is **not**:

- Not "early access". There is nothing to be early to, and publishing to a list
  first would make the free card a stale card.
- Not "founding member pricing". There is no price.
- Not "be the first to know". Nothing on Atlas is time-sensitive.
- Not gated content. The site is complete without the list.

An honest offer for a weekly email converts worse than a manufactured one. It
also produces a list whose behaviour means something, which is the point.

---

## The signup flow

Three fields is three too many. **One field, one button, no account.**

```
  ┌────────────────────────────────────────────────┐
  │  Atlas sends one email a week.                 │
  │                                                │
  │  The board, the rivalries, the cards it has    │
  │  marked down, and one paragraph on what the    │
  │  record did. No selections, no urgency, one    │
  │  click to leave.                               │
  │                                                │
  │  [ your email            ] [ Join the list ]   │
  │                                                │
  │  No spam, no daily digest, no selling your     │
  │  address. Unsubscribe is in the header of      │
  │  every email.                                  │
  └────────────────────────────────────────────────┘
```

**Where it appears:**

| Surface | Placement | Why |
|---|---|---|
| Landing page | after "Why Atlas exists" | a reader who got that far has been convinced by the argument |
| Research page | at the foot | the most engaged surface on the site |
| Card | **nowhere** | the card is the product and it does not ask for anything |
| Board | **nowhere** | Rule 1: the board is the product |

**No modal, ever.** No exit-intent, no scroll-triggered overlay, no "wait —
before you go". A product whose whole claim is that it does not push would lose
that claim the first time it interrupted somebody.

**Double opt-in.** A confirmation email before anything is sent. It costs
signups and it means the list is real.

**Unsubscribe in the header of every email**, not the footer. A product that
makes leaving hard is making a claim about how much it trusts its own value.

### What gets stored

Email address, signup date, and the page it came from. Nothing else — no name,
no favourite team, no behavioural profile. There is no account system and
nothing to sign into.

---

## Founding members

**The concept, and the version Atlas should ship.**

A founding-member programme usually means "pay now, cheaper later". That is a
sale, and Rule 3 forbids it. So the useful version is the other kind:

> **Founding readers are the people who were here before Atlas could prove
> anything.**

What they get — none of which costs money or creates an obligation:

1. **Named, if they want to be.** A single page listing founding readers who
   opt in. No leaderboard, no tiers, no badges on anything.
2. **The first look at the reliability record** when it ships — not early
   access to cards, but a note saying "this is the thing we said we would
   build, here it is."
3. **Asked.** Before the paid tier exists, founding readers get the actual
   question: *what would you pay for, and what would you be annoyed to see
   behind a boundary?* That is the only thing on this list worth more than the
   emails.
4. **Grandfathered, in writing, into free access to everything that is free
   today** — the grade, the research, the methodology, the record. Not a
   discount on a future thing; a guarantee about the present thing.

What they do **not** get: a price, a promise of a price, a countdown, a cap, or
"only 500 spots". Artificial scarcity on a free list is the most transparent
manipulation available, and it would be the first dishonest thing on the site.

### The cap question

There is no cap. A "first 1,000 founding members" badge would create urgency,
which `BRAND_GUIDE.md` forbids on every other surface. The window closes when
the paid tier ships, and that is stated up front.

---

## Sequence

| Stage | What exists | What the list does |
|---|---|---|
| **Launch** | the site, free, complete | collect addresses; send nothing yet |
| **Week 2–4** | first weekly emails | test whether the email drives returns |
| **Then** | public reliability record | the first "here is the thing we promised" |
| **Later** | archive and depth | ask founding readers what to charge for, before deciding |

**Nothing is sent until the weekly email exists and passes the same audit the
site does.** A list collected at launch and left silent for a month is better
than an email sent before it was ready — and `EMAIL_STRATEGY.md` already
specifies the sender, the shape and the language gate.

---

## What this must never become

- **A funnel.** No lead scoring, no drip sequence, no re-send to non-openers
  with a different subject line.
- **A dark pattern.** No pre-checked boxes, no signup as a side effect of
  anything else, no "unsubscribe from all" that means "unsubscribe from one".
- **An asset.** The list is never sold, rented, shared with a book, or used to
  seed an ad audience.
- **A reason to write differently.** The weekly email is a publication, and its
  subject lines stay descriptive and dull on purpose.

---

## What is built

Nothing. There is no form on the site, no sender, no storage and no list.

This is the specification. Building it needs: a form that posts to a single
endpoint, double opt-in, a stored address with a signup date, and an
unsubscribe link that works on the first click. That is a small piece of work
and it is the only server-side thing in the entire product — which is itself a
reason to be sure the weekly email is worth having before adding it.
