# The daily plays

From 30 September 2026. The few wagers a day that pass a tested bar, however
few, logged once and graded on what they did. Rule `daily-v1`, frozen in
[`DAILY_PLAYS_PREREGISTRATION.md`](DAILY_PLAYS_PREREGISTRATION.md) before the
record began. Code: `atlas/owner/highfive.py` (the file keeps the name of the
project it began as). It lives on the owner page under its own tab, **Daily**,
and nowhere else.

## Where it came from

It began as the *Daily High Five*: the five best game wagers and five best
props of the day across every sport, and a five-leg parlay on the days one
existed, for a social-media record. Before that record began, the rule was
run on the current model's walk-forward against the close
([`reports/highfive_backtest.md`](../reports/highfive_backtest.md),
`python -m atlas.research.highfive_backtest`), and it did not survive:

- ranking by expected value and taking the loudest five landed at or below
  the base rate (47.7% over 6,945 plays under the model's own probabilities);
  by quintile of Atlas's disagreement with the close, hit rate is flat in
  every football market and worst in the loudest NHL quintile;
- five positive-EV plays a day rarely exist at the close (about 2.5 do), and
  padding to five cost about a point of hit rate;
- the props had nothing to test against.

What did survive: in the NHL, Atlas's picks on the side the market already
favours hit 61% against a market fair of 58% over ten seasons, while its
underdog picks overclaimed by four points and added nothing. So the fixed
five was dropped for fewer, more consistent plays, and the owner's decision
was to put out one or two plays a day that win rather than volume.

## Not public

The owner page is ciphertext: not linked, not in the sitemap, `noindex`. The
tab is named only inside the plays box's ciphertext; the page's script
(`atlas/site/assets/owner.js`) deliberately does not list it (an unknown tab is
placed after the known ones), so neither the page nor its script carries the
project in the clear (`tests/test_owner_highfive.py` checks both). The record
is sealed with the owner key like the rest (`tracking/owner_highfive/`).

## What is chosen

Built on every run from what the board already prices; nothing new is fetched.

- **NHL**: the side the market favours (vig-free consensus probability at
  least 0.50), when Atlas, shrunk toward the market by the board's 0.46, still
  has positive expected value at the best takeable book; ranked by it.
- **Football**: totals and spreads on Atlas's side of the line, ranked by the
  price edge at the best book against the consensus, when it is positive.
  The size of Atlas's disagreement is not the rank.
- One play a game, at most five a day, no minimum. Nothing is padded.

## When it is logged, how it is graded

Once a day, at the first run at or after 10:00 ET on the day, at the book,
line and price shown, sealed and never revised. Before then the tab is live
and marked provisional. Graded win, loss or push on the final score, in units
at the price logged. There is no closing-line grading, by design.

Two labels ride with each play, recorded so the record can test them and never
used as filters: `form`, the model's hit rate over its last 100 decided
walk-forward results in the play's market when the play was logged (a filter
on it looked good in the backtest and is exactly the kind of thing that looks
good in a backtest), and `p_fair`, the market's probability of the side.

The tab shows the day's plays, then the record split as pre-registered (all
plays, NHL, football, form at or above 50%, form below), each with
won-lost-push, hit rate with its 95% range, break-even at the prices taken
beside the mean probability logged, units and per play; a day-by-day line;
and the latest graded plays. Nothing is read from fewer than 100 decided
plays.

## Known limits

- Football plays bet the price. The board's research puts the best-of-books
  price at one to two percent; a quote may have moved by the time it is
  logged, and the record is graded at the price logged, not at a price
  anyone got.
- Football moneylines are not priced by the board, so they cannot be a play
  (the NHL's are).
- The NHL evidence is 2013-22 at the close; the live rule is chosen at 10 ET
  from a dozen books. That is the record's test to run.
