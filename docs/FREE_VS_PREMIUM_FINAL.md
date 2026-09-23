# Atlas — Free vs Premium, Final

**Track 2.** The launch split, and the rule that produced it.

> **The credibility layer is free, permanently.** Grades. Research.
> Methodology. Reliability.

Implemented on `/premium.html`. There is still no payment path — premium is
specified, not sold.

---

## The line

**This week is free. History, depth and delivery are paid.**

| | Free forever | Premium |
|---|---|---|
| This week's board, every game | ✓ | ✓ |
| The Atlas grade, and its three-line explanation | ✓ | ✓ |
| Market number, Atlas projection, the difference | ✓ | ✓ |
| Why — the three leading drivers | ✓ | ✓ |
| Be careful about | ✓ | ✓ |
| How the grade was computed | ✓ | ✓ |
| Reliability record and calibration | ✓ **always** | ✓ |
| Research and methodology | ✓ **always** | ✓ |
| Team pages and season profiles | ✓ | ✓ |
| Social cards | ✓ | ✓ |
| Past weeks and past seasons | this week only | ✓ |
| Every driver, with percentiles | top three | ✓ |
| Full market history, snapshot by snapshot | open and current | ✓ |
| How a card's grade has moved during the week | — | ✓ |
| Daily and weekly email | weekly board | ✓ |
| Data export | — | ✓ |

---

## What changed from the earlier framework, and why

The previous `PREMIUM_PLAN.md` put **the Atlas difference** and **the grade
component breakdown** behind the boundary. Both are now free. Two reasons, and
the second is the real one.

**It was not coherent.** The difference is on every board row and on every
social card. A card that hid the number its own board row displays would be
a boundary a reader could walk around in one click, which is worse than no
boundary — it teaches people that the product is playing games with them.

**It was the wrong thing to gate.** The dangerous artefact is a difference
*without a grade beside it*: a big number, no context, screenshot-ready. A
difference *with* a grade beside it, and a "be careful about" section under it,
is the product working. Charging for the safety rails and giving away the
number they restrain is exactly backwards.

So the line moved to one that can actually be held: **everything needed to
judge a card this week is free**, and what is paid is work Atlas does that
costs money to keep doing.

---

## The four rules behind the line

**1. Evidence is never behind a boundary.** The grade, the research, the
methodology and the reliability record are free permanently. A reliability
record that costs money is not a record — it is a marketing asset. A reader
who has paid nothing must still be able to check every claim Atlas makes.

**2. A card is never half visible.** An incomplete card is a card a reader
cannot check, and an unverifiable card is worth less than no card. Every free
card is complete: the market number, the projection, the difference, why, the
cautions, and the grade with its arithmetic.

**3. Nothing is ever blurred.** A premium surface is absent and named, never
teased. A blurred number is an advertisement wearing the clothes of
information, and the moment Atlas ships one it becomes a product that sells
curiosity instead of research.

**4. No affiliate revenue, ever.** Books pay for traffic that converts to
deposits. Taking that money would mean Atlas earns more when readers act — an
interest directly opposed to the product's only claim. This is the rule most
likely to cost real money and the one least open to revisiting.

---

## What premium is actually selling

Not access. **Time depth and delivery.**

- **Past weeks and seasons.** The archive is where the reliability record lives
  as a browsable thing rather than a summary table. It is also the most
  expensive thing Atlas maintains, because point-in-time correctness has to
  hold for every historical snapshot.
- **Every driver rather than the leading three.** The free card answers *why*;
  premium answers *why, exhaustively*, with percentiles.
- **The full market history.** The free card shows open and current. Premium
  shows every snapshot the tracker captured, which is what somebody studying
  line movement actually needs.
- **Grade movement during the week.** New under V2: a card's letter now moves
  as the market does. Watching that move is a genuinely new thing to sell and
  it did not exist before this sprint.
- **The daily email and export.** Delivery, not information.

---

## What premium will never become

- **A side, at any price.** The research established there is no edge worth
  acting on. A paid tier that implied otherwise would be contradicted by the
  free reliability record on the same page.
- **A card of the day**, a "top card", a ranked list, or anything else that
  amounts to a selection with the word removed.
- **Early access.** Publishing a card to paying readers first and everyone else
  later would make the free card a stale card, which breaks rule 2.
- **A tier where the grade differs.** One number, one letter, same for
  everyone. The moment there is a "premium grade" the free grade becomes
  marketing.

---

## Launch posture

**Premium does not ship at launch.** The page explains the split and says
plainly that there is no way to subscribe.

That is deliberate. The paid surface is mostly the archive and the reliability
record as a browsable history, and neither exists yet — the tracker has been
accumulating since Phase 5 against a two-season horizon. Selling a subscription
whose main asset is still being collected would be selling a promise, which is
the specific thing this product exists not to do.

**Sequence:** ship free → build the public reliability record → open the
archive → then, and only then, charge for it.
