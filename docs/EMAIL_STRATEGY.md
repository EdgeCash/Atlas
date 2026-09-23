# Atlas — Email Strategy

**Track 3.** Two emails. No betting language. No recommendations.

Not built. This is the specification, and it is written so it could be built
from the same `Card` objects the site is built from — an email that is
assembled by hand is an email that drifts from the product inside a month.

---

## Two emails, two jobs

| | **The Weekly Board** | **The Daily Card** |
|---|---|---|
| Who | everyone | premium |
| When | Thursday 9am ET | each morning with games |
| Length | one screen on a phone | shorter |
| Job | *here is the week, and what Atlas trusts* | *here is today, in sixty seconds* |

Free readers get one email a week. That is the whole free tier of email, and it
is enough: the board is on the site and the email is a reason to go there, not
a replacement for it.

---

## The Weekly Board

```
  Atlas · Week of 24 September

  58 cards this week. 7 graded A or better, 11 marked down.
  ──────────────────────────────────────────────────────────

  FEATURED
  Ole Miss at Florida        Sat 3:30 PM ET · ABC
  FLA −3.5 · total 58.5      Atlas +0.4        A

  Texas at Tennessee         Sat 12:00 PM ET · ABC
  TEX −5.5 · total 55.5      Atlas −1.7        B

  Missouri at Mississippi St Sat 7:45 PM ET · SEC Network
  MSST −6.5 · total 58.5     Atlas −4.2        C
  ──────────────────────────────────────────────────────────

  RIVALRIES          four annual fixtures on the board
  [four rows]

  MARKED DOWN        11 cards
  Atlas sits furthest from the market on these, and history says
  that is where it has been least reliable.
  [three rows, then "see all eleven"]
  ──────────────────────────────────────────────────────────

  THIS WEEK IN THE RECORD
  One paragraph: what the reliability record did, or one thing
  the model got visibly wrong.

  See the full board →
```

**The sections mirror the board** — same order, same captions, same grade
meanings. An email that organises the week differently from the site teaches
two mental models for one product.

**"Marked down" is in the email, above the fold-equivalent.** It is the most
on-brand section Atlas has and the one no competitor sends.

---

## The Daily Card

One game, the one with the most going on — a ranked matchup, a line that has
moved, or a card whose grade changed during the week.

```
  Atlas · Saturday

  C Michigan at Miami        6:30 PM ET · CW
  MIA −41.5 · total 53.5     Atlas −11.2       F

  Atlas projects 11.2 points below the market. Cards this far
  out claimed 77% accuracy over seven seasons and delivered 50%,
  so Atlas marks its own card down.

  What the model is reading
  Miami success rate            99th percentile
  Central Michigan offence       8th percentile
  Combined plays per game       15th percentile

  Full card →        Everything else today →
```

Same three-number shape as the social card, same computed sentence. **The daily
email and the wide social template render the same content** — one is an image,
one is text, and neither is written by hand.

---

## Rules

**Language.** The same tripwire as the site. Whatever renders the email runs
through `scripts/audit_site.py`'s vocabulary check before it sends, and an
email that fails does not go out. This is not optional discipline — an email is
the surface furthest from review and closest to a reader's inbox.

<!-- lang-lint: quoting -->
**Never in an email:** a side, a lean, a record of wins and losses, units, a
countdown, a subject line implying urgency, a "don't miss", a figure that
implies a return.
<!-- lang-lint: end -->

**Subject lines** are descriptive and dull on purpose:

- *"Atlas · Week of 24 September — 58 cards, 11 marked down"*
- *"Atlas · Saturday — C Michigan at Miami, graded F"*

A subject line that creates urgency is the first place this product would start
lying, and it is the cheapest place to stop.

**No open-rate optimisation.** No emoji, no first-name interpolation, no
re-send to non-openers with a different subject. The email is a publication,
not a funnel.

---

## The one email Atlas should send that nobody else does

**A correction.** When a card graded A went badly, or the model was visibly
wrong, the weekly email says so in the "this week in the record" paragraph —
with the number.

It is the email equivalent of the F card, and it is the only thing in this
channel that cannot be copied by a product that sells confidence.

---

## Mechanics

**Plain HTML, no images except the crests, no tracking pixels beyond a single
open beacon.** Atlas's whole visual system is type and white space, which is
also what survives an email client. The card graphics are links, not
attachments.

**One-click unsubscribe in the header**, not the footer. A product that makes
leaving hard is making a claim about how much it trusts its own value.

**Sent from the build.** The same `build_cards()` call that produces the site
produces the email payload, so the email cannot describe a card that does not
exist, and a grade in an inbox always matches the grade on the page.

**No send without a green audit.** `make launch-check` is the gate for the
site; the email gets the same one.

---

## Measurement

Not opens. `POST_LAUNCH_METRICS.md` has the full set; for email specifically:

| Signal | What it would mean |
|---|---|
| Click-through to a **marked-down** card vs an A card | whether the honesty is the draw or the decoration |
| Weekly → site return rate | whether the email is a reason to visit or a replacement for visiting |
| Unsubscribe rate after a correction email | whether readers punish the thing that makes Atlas worth reading |

That last one is the one worth knowing. If corrections drive unsubscribes,
Atlas has the wrong audience, and the answer is not to stop sending
corrections.

---

## Not built

There is no sender, no list, no template renderer and no signup form. The
landing page offers the weekly email; nothing collects an address yet.

**Sequence:** ship the site → add the weekly board → add the daily card with
premium. The daily email is a premium feature and premium does not ship at
launch, so the daily email does not either.
