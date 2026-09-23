# Atlas — FAQ

Written to be published. Plain answers, no hedging, and the uncomfortable ones
answered first.

---

## What is Atlas?

Every college football game gets a card: what the betting market says, what
Atlas projects, what is driving the difference between them, and a letter for
how much that card's information has historically been worth.

Atlas never tells anyone what to do with it.

## Is this a picks service?

No. No card names a side — not as a lean, not as an arrow, not as a highlighted
row, not "for entertainment". Every page is checked at build time by a test
that fails if a side appears anywhere, and again by an audit over all 181 built
pages.

## So what is it for?

Understanding games better. What the market thinks, what a model thinks, where
they differ, and — the part nothing else publishes — **how much that difference
has historically been worth.**

## Do I need to know anything about betting?

No. The market number is used as a reference point because it is the best
public forecast of a game that exists; you do not need to have any interest in
it beyond that.

One thing on the card does assume the notation: `MIA −41.5` means Miami is
favoured by 41.5 points. Everything else — the projection, the difference, the
grade, the drivers — is in plain English.

## Do I need to understand modelling?

No. The card's first screen is written for somebody who does not, and the grade
explains itself in three plain sentences on every card. The technical detail is
behind panels and on the research page, where you can go if you want it.

---

## The grade

## What does the grade mean?

How much weight the information on that card deserves. Not how good the game
is, not how confident anyone should be about an outcome.

| | |
|---|---|
| **A+** | Atlas and the market land on the same number. Reliable — and Atlas is adding least here. |
| **A** | Closely aligned. Strong calibration. |
| **B** | A moderate difference, where the claim and the delivery stay close. |
| **C** | A wide difference. The claim starts to run ahead of the delivery. |
| **D** | A large difference. Atlas commonly struggles this far out. |
| **F** | A very large difference, where Atlas has been least reliable. It marks its own card down. |

## Is an A card a better game to watch?

No. The grade says nothing about the game — it is about Atlas's own numbers.

## Is an A card the one I should read first?

**No, and this is the least intuitive thing about Atlas.** Cards where Atlas and
the market agree to within a point have realised 50.8% against a 51.3% claim
across 760 games — statistically a coin flip. They grade highest because they
are the most reliable, and they are the most reliable **because Atlas has added
nothing to them.**

The grade tells you what to discount, not what to look at.

## Why does a big difference lower the grade? Shouldn't a big disagreement be interesting?

It is interesting. It is also, measured across seven seasons out of sample,
where the model is worst. Cards claiming 77% accuracy delivered 50%.

Everything else in this category shouts loudest where its model disagrees most.
Atlas grades itself down there, because that is what the evidence says.

## Who assigns the grades?

Nobody. `grade.compute()` is the rubric in code, and nothing about a grade is
entered by hand or adjusted afterwards. The calibration curve behind it is
refitted from seven seasons of data on every build, so the site cannot drift
away from the research it cites.

## Why do so few cards get A+?

Because the thresholds were set once from seven seasons of results and then
fixed, and only about 6% of cards historically reach it. Atlas does not grade on
a curve — a curve would make the same card mean something different depending
on which Saturday you looked at it.

## Can a card's grade change during the week?

Yes. The grade depends partly on how far Atlas sits from the market, and the
market moves. A card graded B on Tuesday can be graded C by Saturday if the
line moves away from Atlas's number.

## What does "marked down" mean?

A card graded D or F. There is a filter for them on the board, because the
cards Atlas trusts least are the ones a reader most needs to know about.

---

## The numbers

## Where do the market numbers come from?

A live tracker that records the spread, the total and the prices as they open
and as they move. Currently one provider posts the numbers Atlas captures,
which is why every card says `1 book quoting` — a known limitation, named on
the card and in the launch plan.

## What is "the difference"?

Atlas's projected game total minus the market's. A positive number means Atlas
projects more points than the market; negative, fewer.

It is coloured only when it exceeds one point, because below that the two are
statistically indistinguishable and colouring it would be shouting about
nothing.

## Why does Atlas use the market at all?

Because seven seasons of out-of-sample testing said the market is the better
forecast. Atlas weights it at 0.89 on totals; on spreads the model's own
contribution could not be told apart from zero, so the published spread is the
market's number.

Atlas publishes the accurate number and shows the raw model beside it, labelled,
so the correction is visible rather than hidden.

## What is "point-in-time"?

Every figure attached to a game uses only information that existed before
kickoff. A team's profile in week 4 is what was knowable in week 4 — no
hindsight, ever, anywhere in the database.

## What is a driver?

One of the things the model is reading on this game — offensive efficiency,
success rate, pace — with the crest of the team it favours and how each side
ranks against the rest of the country.

---

## Coverage

## Which sports?

College football only. NFL is staged behind calibration: the model has to be
fitted and back-tested to the same standard before NFL cards publish, and the
NFL page explains the three stages.

No other sports are planned.

## Why not publish NFL projections now, without grades?

Because the grade framework is the product, and its credibility comes entirely
from having been tested. Putting an untested model behind it would spend that
credibility to fill a page.

## How many games?

Every FBS game on the slate. 58 this week.

---

## Money

## Is Atlas free?

Yes. The grade, the research, the methodology, the reliability record, and
everything needed to judge a card this week are free and always will be.

## Will there be a paid tier?

Eventually — for history, depth and delivery: past weeks and seasons, every
driver rather than the leading three, the full market history snapshot by
snapshot, and email. Not the grade, not the research, not the record.

There is no payment path on the site and no way to subscribe.

## Does Atlas take affiliate money from sportsbooks?

No, and it never will. Books pay for traffic that converts to deposits, which
would mean Atlas earns more when readers act — an interest directly opposed to
the product's only claim.

## Is anything blurred or teased?

No. A premium surface is absent and named, never blurred. A blurred number is
an advertisement wearing the clothes of information.

---

## Trust

## How do I know the record is real?

It is recomputed from the database on every build rather than transcribed, and
the research page shows claimed accuracy against realised accuracy for every
band of disagreement, with the number of games behind each row.

If Atlas ever quietly stopped matching its own research, the build would say so
before a reader did.

## Has Atlas been wrong?

Constantly, and the product is built around saying so. The whole grading system
exists because the research found the model's confident cards were its worst
ones.

## What is the most on-brand thing Atlas publishes?

A card it has graded F, with the reason. Nobody else in this category will ever
post one.

## Does Atlas track me?

Server logs and a single first-party counter. No third-party analytics script,
no ad pixel, no cross-site identity, no account. There is nothing to sign into.

## Can I get this by email?

A weekly board email is planned. There is no sender yet, so nothing is
collecting addresses.

---

## Practical

## Does the site work without JavaScript?

Yes. Every page is complete before anything loads. The only script is 40 lines
of filtering on the board; the card's expanding panels are native HTML.

## Why is it so plain?

Because it is a research product, and because a page that loads instantly on a
phone on a stadium network beats a page that looks impressive on a laptop.

## Can I use the numbers?

The cards are public. There is no API and no export yet; export is on the
premium list.

## Who makes Atlas?

A research project that became a product. Every phase of the work — the
warehouse, the model, the calibration study, the grading framework and the
product itself — is documented in the repository.
