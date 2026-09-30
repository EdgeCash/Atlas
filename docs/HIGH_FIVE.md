# High Five

From 30 September 2026. The social-media project: one Daily High Five, the
five best game wagers and the five best props of the day across every sport on
the board, and a five-leg parlay on the days one is worth putting out. The
measure is the record of those plays: what they did, win or lose. Code:
`atlas/owner/highfive.py`. It lives on the owner page, under its own tab, and
nowhere else.

## Not public

The owner page is a row of ciphertext: not linked, not in the sitemap,
`noindex`. High Five adds a section to the plays box's ciphertext that names
its own tab, and the page's script (`atlas/site/assets/owner.js`) deliberately
does **not** list that tab (an unknown tab is placed after the known ones), so
neither the page nor the script carries the project's name in the clear
(`tests/test_owner_highfive.py` checks both). The records are sealed with the
owner key like the rest (`tracking/owner_highfive/`,
`tracking/owner_highfive_parlays/`). Only this document and the code name it;
the tab appears after More once the passphrase opens the page.

## What is chosen

Built on every run from what the board already prices; nothing new is fetched.

* **Five wagers.** The board's positive-expected-value legs
  (`atlas/owner/board.py`, the NHL's `nhl_board.py`): football totals and the
  NHL's moneyline, puck line and total on Atlas's probability, football spreads
  on the price against the consensus (Atlas adds nothing there). Each game's
  best side at the book paying best for it, at most one a game, the five highest
  expected values. The row says which kind of edge it is.
* **Five props.** PrizePicks' standard lines (More and Less both offered),
  the likelier side of each by the books' fair probability, as the pick'em
  prices it, from 54%. One a player, at most two a game, the five likeliest.
* **A five-leg parlay.** Only when one sportsbook has five positive-EV legs in
  five different games: that book's five best. Never a same-game parlay. Its
  expected value is the product of (1 + EV) over the legs, so it is positive
  whenever it exists, and compounds the model's errors as it compounds the
  edges; the record is the test. Most days there is none.

A day with fewer than five qualifying plays of a kind logs fewer. Nothing is
padded with a negative-EV wager or a coin-flip prop to reach five.

## When it is logged

Once per kind per day, at the first run at or after 10:00 ET on the day (the
parlays' and the pick'em's moment), at the book, line and price shown, sealed
and never revised. Before then the tab's tables are live and marked
provisional. Props log separately from wagers, so a late PrizePicks posting
does not hold up the wagers. The day is today Eastern, or the next day with
games once today's are done.

## How it is graded

Win, loss or push on the final score for wagers (units at the price logged: a
win pays the price, a loss is one unit), on ESPN's box score for props (a
player who did not play is void and drops out of the count; a whole-number tie
is a push), and the parlay as the Daily parlays grade it (a pushed leg drops
out and the odds reduce). Props have no units: PrizePicks pays by slip, so
they carry a hit rate beside the probability they were logged at. The record is
**not** graded on closing-line value, by design: the High Five is judged on what
the plays won.

The tab shows, for wagers, props and all plays together: won-lost-push, hit
rate (with the expected rate beside it), units for wagers and the parlay, a day
by day line, and the latest graded plays. Nothing should be read from fewer
than about a hundred plays.

## Known limits

* Wager edges come from two measures on one scale. Totals and NHL markets use
  Atlas's probability, whose calibration shows the model's disagreement with
  the market is real but smaller than it looks; spreads use the price against
  the consensus. The best EV of the day is often a shopping edge at one book
  on a quote that may already have moved; the row shows the book and its
  price, and the record is graded at that price.
* A quote's age is not a filter. The parlays tab flags quotes past 90 minutes;
  the High Five does not drop them.
* Football moneylines are not priced by the board, so they cannot be a wager
  (the NHL's are).
* Props are ranked by probability of the likelier side, not by payout.
* The record is a daily sample of ten plays: about 3,650 a year. Early numbers
  are noise, and the record says so.
