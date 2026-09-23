# Atlas — Social Playbook

**Track 5.** One game. One card. One idea.

`SOCIAL_GROWTH_STRATEGY.md` is the thesis and `SOCIAL_CARD_REDESIGN.md` is the
template specification. This is the operating manual: what goes out, when, on
which channel, and who decides.

---

## The week

| Day | Post | Template | Channel |
|---|---|---|---|
| Tuesday | The reliability record, or a correction | A | Threads, X |
| Thursday | The week's board is up — one featured card | A | X, Threads |
| Friday | The drivers post on the weekend's biggest game | B | Instagram, X |
| Saturday am | **The marked-down card** | A | X, Threads, IG |
| Saturday | A line that has moved, and which way Atlas reads it | A | X |

**Five posts.** The failure mode is posting every card: 58 graphics a week
trains a reader that the cards are wallpaper, and the scarcity of the
marked-down card is most of its value.

---

## The Saturday post is the one that matters

The marked-down card, with the reason, every week.

Under V1 this post existed roughly never — the rubric produced one F on a
58-card slate and the same handful of A cards otherwise. Under V2 the slate
carries **eleven marked-down cards**, so the honest post is available whenever
it is true rather than whenever the arithmetic happens to allow it.

Nobody else in this category will ever publish a graphic whose conclusion is
*"our own number is 11 points from the market and history says do not trust
that."* It is the single most differentiated thing Atlas can put in a timeline.

---

## Per channel

### X

The highest-value channel and the highest-risk one.

- **Template A**, one card per post. Link in the post body, never the first
  reply — a link in the reply is a growth tactic and this is a publication.
- **Post copy restates the sentence already on the card.** A caption that adds
  a claim the graphic does not support is how the discipline erodes: the
  graphic is reviewed and tested, the caption is typed.
- **Quote-posts will attach recommendations to Atlas's cards whatever Atlas
  does.** The defence is not moderation; it is that the graphic itself cannot
  be read as one. That is a design property, checked by the build.
- **Reply to a wrong card.** A model that publicly notes when a badly graded
  card went badly is doing the thing the grade promises.

### Instagram

- **Template B**, the square. It is the feed's native shape and the drivers post
  has more to look at.
- **The carousel is available and mostly should not be used.** Three slides is
  three ideas; the rule is one. The exception is the reliability record, where
  slide 1 is the claim and slide 2 is the delivery.
- **Stories:** the marked-down card, full bleed, with a link sticker to that
  card. Stories are the only Atlas surface with a natural expiry, which suits
  a pre-kickoff product.
- **No Reels.** Motion implies urgency and nothing on Atlas moves.

### Threads

- Behaves like X, reads like a feed. **Template A**, and the sentence from the
  card as the post body.
- The channel most tolerant of the reliability-record post, which does badly on
  X and fine here. Tuesday's post lives here first.

---

## The four approved post shapes

**1. A marked-down card, with the reason.** The highest-value post Atlas makes.

**2. A disagreement, with the band's record attached.**

> *Atlas projects 52.3 against a market of 53.5. Cards that far out claimed 60%
> accuracy and delivered 52%.*

Never post the first sentence without the second. The disagreement is the hook;
the record is what makes it Atlas rather than a tout account.

**3. A line that moved, and which way Atlas reads it.**

> *The total opened 54.5 and is now 53.5. Atlas has moved the other way.*

Descriptive, no direction implied for the reader, and genuinely interesting to
a sports fan who has never placed a wager.

**4. The reliability record itself.** The least shareable post and the most
important one to have made, because it is what every other post stands on.

---

## Never

<!-- lang-lint: quoting -->
A side. A record of wins and losses. Units. A countdown. A screenshot of a bet
slip. Another account's pick with commentary. A percentage that implies a
return. A thread that builds to a recommendation. A reply arguing with someone
about a result.
<!-- lang-lint: end -->

Every one of these is available and every one converts better in the short run.
The entire value of the grade depends on Atlas never having posted one.

---

## Production

Nothing is made by hand.

```
make site          # writes site/social/{slug}-wide.png and -square.png
```

Six cards per build, chosen as a spread across the grade range, so a
marked-down card is always available and never has to be made specially. SVG is
the source; PNG is rasterised at 2×. Crests are embedded as base64 so a card
renders identically anywhere.

**The templates are tested like the pages are.** The rendered SVG is parsed as
XML and scanned for the forbidden vocabulary by `tests/test_site.py`, and
`scripts/audit_site.py` scans the built site. A template that could be filled
with a recommendation fails the build.

### The screenshot test

A card has to survive arriving with no caption, no thread, no profile and no
link. Three things make it pass, and all three are on the wide template:

1. **The numbers with their labels** — MARKET, ATLAS, DIFFERENCE.
2. **The grade with a word beside it** — `F 44 · LOW` is a claim; `F 44` is a
   symbol.
3. **A sentence saying what it means**, computed from the numbers on the card.

The footer carries *Grade = information quality, not a recommendation* on every
card, because the card travels without its page.

---

## Who decides

One person, one rule: **if a post needs a caption to be defensible, it is not a
post.** The graphic is the unit. The caption restates it.

A post that would be improved by a claim the card does not make is a post that
should not go out — and the fastest way to check is to ask whether the sentence
already on the graphic is the sentence you were about to type.

---

## The measure

**The marked-down card should outperform the A card.**

If it does, the positioning is working: the audience is here because Atlas says
when not to trust it. If Atlas's best-performing posts are its most confident
ones, the audience has misunderstood the product, and the next post is the
reliability record rather than a louder card.

Tracked in `POST_LAUNCH_METRICS.md` as the single most informative number in
the whole growth picture.
