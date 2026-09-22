# Atlas — Social Growth Strategy

Assume X, Instagram and Threads are the primary growth channels. Assume every
post is seen for about a second and a half, at about 500px wide, by someone who
has never heard of Atlas.

**One card. One game. One idea.**

---

## The only metric that matters

Not followers, not impressions: **the share of people who see a card and then
open one.**

A card that gets reposted by an account with a large following and sends nobody
to the site has cost Atlas the cost of making it. A card that reaches 400 people
and sends 40 of them to a matchup page has worked.

This has a design consequence. Every template carries the URL of the specific
card it is about, not a homepage link, because the post is an excerpt of a
document and the document is the product.

---

## The screenshot test

> A user screenshots Atlas. The screenshot explains itself.

This is the strictest test in the brief, because a screenshot arrives with no
caption, no thread, no profile and no link. It has to survive being wrong about
its own context.

Three things make a card pass it, and all three are now on the wide template:

1. **The numbers with their labels.** MARKET, ATLAS, DIFFERENCE — a reader who
   knows nothing can tell which is which.
2. **The grade with a word beside it.** `F 33` alone is a symbol. `F 33 · LOW`
   is a claim.
3. **A sentence saying what it means**, computed from the numbers already on the
   card:

   > *Atlas projects 11.2 points below the market. Cards this far out claimed
   > 77% accuracy over seven seasons and delivered 50%.*

That sentence replaced a driver statistic. A fourth number would have been more
information and less meaning, and a screenshot has room for one idea.

The footer carries the disclaimer on every card, because the card will travel
without its page: **Grade = information quality, not a recommendation.**

---

## Two templates, two jobs

| Template | Size | Job |
|---|---|---|
| **A** | 1200 × 675 | *This is the number, and this is how much Atlas trusts it.* |
| **B** | 1080 × 1080 | *This is why the model reads the game the way it does.* |

Full specification in `SOCIAL_CARD_REDESIGN.md`. A is the default post. B is
for the game where the drivers are the story, and it is the one to use when a
card grades badly.

---

## What to post

### The four shapes, in order of how much they are worth

**1. A card Atlas graded F, with the reason.**

The single most valuable post Atlas can make, and the one no competitor will
ever make. It is a product saying *do not lean on this* about its own output,
with seven seasons of evidence for why. It is credible precisely because it
costs something.

Cadence: whenever one exists. On the 26 September slate there was exactly one.

**2. A disagreement, with the band's record attached.**

> *Atlas projects 52.3 against a market of 53.5. Cards that far out claimed 60%
> accuracy and delivered 52%.*

The disagreement is the hook; the record is what makes it Atlas rather than a
tout account. Never post the first half without the second.

**3. A line that moved, and which way Atlas reads it.**

> *The total opened 54.5 and is now 53.5. Atlas has moved the other way.*

Descriptive, no direction implied for the reader, and it is genuinely
interesting to a sports fan who has never placed a wager.

**4. The reliability record itself.**

Calibration by disagreement band, claimed against realised. It is the least
shareable post and the most important one to have made, because it is what every
other post is standing on.

### What never to post

<!-- lang-lint: quoting -->
A side. A record of wins and losses. Units. A countdown. A screenshot of a bet
slip. Another account's pick with commentary. A percentage that implies a
return. A thread that builds to a recommendation.
<!-- lang-lint: end -->

Every one of these is available and every one of them converts better in the
short run. The entire value of the grade depends on Atlas never having posted
one.

---

## Per-channel

### X

The highest-value channel and the highest-risk one. Quote-posts will attach
recommendations to Atlas's cards whatever Atlas does; the defence is that the
graphic itself cannot be read as one.

- Template A, one card per post, link in the post body not the first reply.
- Post copy restates the sentence on the card. A caption that adds a claim the
  graphic does not support is the fastest way to lose the discipline.
- Reply to a wrong card. A model that publicly notes when a badly graded card
  went badly is doing the thing the grade promises.

### Instagram

- Template B. The square is the feed's native shape and the drivers post has
  more to look at.
- The carousel is available and mostly should not be used: three slides is three
  ideas, and the rule is one.
- Stories: the F card, full bleed, with the link sticker to that card.

### Threads

- Behaves like X, reads like a feed. Template A, and the sentence from the card
  as the post body.
- The channel most tolerant of the reliability-record post, which does badly on
  X and fine here.

---

## Cadence

Per slate, not per day:

| Post | When |
|---|---|
| One F card | Whenever the slate produces one |
| Two or three disagreement cards | Thursday through Saturday morning |
| One movement card | When a line has moved 2+ points |
| The reliability record | Once a month, and after any week Atlas was visibly wrong |

That is roughly five posts a week. The failure mode is posting every card:
58 graphics a week trains a reader that the cards are wallpaper, and the
scarcity of the F card is most of its value.

---

## Production

Cards are generated on every site build, for a spread of grades:

```
site/social/{slug}-wide.svg     1200 × 675
site/social/{slug}-wide.png     2× raster
site/social/{slug}-square.svg   1080 × 1080
site/social/{slug}-square.png   2× raster
```

SVG is the source; the PNG is rasterised from it at 2×. Crests are embedded as
base64 so a card renders identically anywhere. Nothing is made by hand, so
nothing can drift from the card it describes.

**The templates are tested like the pages are.** The rendered SVG is parsed as
XML and scanned for the forbidden vocabulary by `tests/test_site.py`. A template
that could be filled with a recommendation would fail the build.

---

## The growth thesis, stated plainly

Atlas will grow slower than a picks account and it should.

The audience that shares a card because it is interesting is a different
audience from the one that shares a pick because it won, and only the first one
is still there after a bad month. The product's whole position — *research,
analytics, context* — is a bet that a smaller audience with no reason to leave
is worth more than a larger one that arrived for a reason Atlas cannot repeat.

The measurable version: **the F card should outperform the A card.** If it does,
the positioning is working. If Atlas's best-performing posts are its most
confident ones, the audience has misunderstood the product and the next post
should be the reliability record.
