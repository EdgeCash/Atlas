# Atlas — Beta Feedback Loop

**Track 6.** How a beta reader tells Atlas something, and what happens next.

---

## The one visible change RC1 makes

A single footer link, beside *data status*:

> Atlas Sports Intelligence · Research. Analytics. Context.
> Out-of-sample figures from a point-in-time database · new here · questions ·
> data status · **feedback** · how Atlas works · what grades mean

`mailto:beta@atlas.football?subject=Atlas%20beta%20feedback`.

### Why a link and not a button

**Because the design is frozen.** A feedback button is a product surface: it
needs a position, a state, a hover, a mobile treatment and a decision about
whether it floats. A footer link needs none of those and is already inside an
approved component.

**Because a form needs a server.** The one thing Atlas does not have is a
server. A form means an endpoint, spam handling, storage, and the first piece
of inbound infrastructure in the whole product — for something a mailto does
adequately at beta scale.

**Because nothing on Atlas interrupts.** No modal, no exit-intent, no "how are
we doing?" slide-up. A product whose claim is that it does not push would lose
that claim the first time it interrupted somebody.

If beta volume makes the mailbox unworkable, the upgrade path is a hosted form
linked from the same place — no change to any Atlas surface.

---

## Three flows, one inbox

Triage by what the message is, not by where it came from.

### 1. A bug

*Something is wrong with what Atlas shows.*

| | |
|---|---|
| Severity 1 | **a named side, a forbidden word, a card asserting something false** — the audit should have caught it; fix and add the check that would have |
| Severity 2 | a wrong number, a broken page, a stale timestamp that is not stale |
| Severity 3 | layout, wrapping, a typo |

**Every severity-1 bug produces a test before it produces a fix.** The whole
apparatus — `test_site.py`, `audit_site.py`, `validate_seo.py` — exists
because "we'll be careful" is not a control. A category that got through is a
category the gate did not cover.

**First question for any data bug:** does `/status.html` already explain it? A
stale market number during a provider outage is the system working. The status
page is the first place to look, and if it did not explain it, that is itself
the bug.

### 2. A feature request

*Atlas should also do X.*

Answer it against `TOP_25_FEATURES.md` and `ATLAS_FEATURE_ROADMAP.md`, which
were written precisely so this question has an answer that is not a mood:

- **Already on the roadmap** — say where, and what it is behind.
- **Already rejected, with a reason** — fifteen are, individually argued. Send
  the reason. *"Live scores"*, *"ATS records"* and *"fantasy"* will all arrive
  and all three are answered.
- **New** — run the Atlas Test from `ATLAS_ECOSYSTEM_VISION.md`: does it
  strengthen research, analytics or context, or does it copy another site?

**Feature requests are data, not a queue.** Ten people asking for the same
thing is a finding; one person asking is a conversation.

### 3. A disagreement with the model

*Your number is wrong about this game.*

The most valuable category and the one most likely to be mishandled.

- If the card graded **D or F**, Atlas already said so. Point at the grade —
  and note it, because a reader arguing with a card that marked itself down
  means the marking is not visible enough.
- If the card graded **A or B** and was badly wrong, that is exactly what the
  reliability record exists to capture. Log it; do not adjust the model.
- **Never hand-adjust a card.** `grade.compute()` is the rubric in code and
  nothing is entered by hand. A single exception ends the claim.

---

## Response standard

| | |
|---|---|
| Acknowledge | within two days |
| Severity 1 | same day, and the fix ships with a test |
| Severity 2 | next heavy refresh |
| Severity 3 | batched |
| Feature request | a real answer, pointing at the document that decided it |

**Reply in Atlas's voice.** `BRAND_GUIDE.md` governs an email as much as a
page: plain, specific, willing to say when something is weak. An answer that
says *"you're right, that's a bug, here is the test we added"* is worth more
than a roadmap promise.

---

## What beta is actually for

Not bug count. **Testing whether the positioning survives contact.**

`POST_LAUNCH_METRICS.md` and `ANALYTICS_SPEC_FINAL.md` name the numbers; the
inbox answers the questions numbers cannot:

1. **Did they understand it?** If beta readers ask *"so which one do I bet?"*,
   the twenty-second test failed no matter what the audit says.
2. **Did the grade land?** If nobody mentions the grade, it is decoration. If
   people argue with it, it is working.
3. **Did the honesty read as honesty or as weakness?** The single most
   important unknown. A reader who says *"why would I use a model that admits
   it's wrong"* has understood the product exactly and rejected it — and that
   is a finding, not a failure to communicate.
4. **What did they open another tab for?** `USER_NEEDS_STUDY.md` predicted
   injuries first and standings second. Beta says whether that was right.

---

## What does not change during beta

- **No design changes** from feedback alone. One reader disliking the layout
  is taste; twenty failing the same task is a finding.
- **No grade changes.** The thresholds were set once from seven seasons and
  fixed. A reader who does not like an F is the system working.
- **No new features.** `ATLAS_FEATURE_ROADMAP.md` has the order, and the
  reliability record is first.
- **No language exceptions.** Every request to add a forbidden word gets the
  same answer.

---

## Before launch

- [ ] `beta@atlas.football` exists and somebody reads it.
- [ ] Auto-reply pointing at `/faq.html` — most first messages are answered
      there, and it costs nothing.
- [ ] One place to log what arrives. A file in the repository is enough at
      this scale.

---

## The measure

At the end of beta, one question:

> **Did anyone say the thing Atlas is for?**

Not "this is useful" — *"I opened the card and it told me not to trust it, and
I checked, and it was right."*

If nobody says a version of that, the product is well built and has not landed,
and the answer is the reliability record rather than another feature.
