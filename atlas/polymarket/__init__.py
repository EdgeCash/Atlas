"""Atlas on Polymarket: the one venue the model is priced against.

Polymarket lists a moneyline, a ladder of spreads and a ladder of totals on
every NFL, NBA, NHL and college football game, as binary contracts that cost
their price and pay one dollar. Its prices are public, read without a key
from its Gamma and CLOB APIs (`source.py`), so unlike every sportsbook
before it the market Atlas is measured against can be captured, timestamped
and committed in the clear (``tracking/polymarket_quotes.csv``).

The package does four things, in this order on every run:

1. **capture** the quotes on the games Atlas projects (`source.py`,
   `match.py`);
2. **price** each contract by Atlas, anchored to Polymarket's own
   probability by how much of Atlas's disagreement has turned out real on
   the walk-forward record (`pricing.py`);
3. **take and grade paper positions** at the venue's taker fee, logged once
   and never revised, in a sealed record (`positions.py`);
4. **report**: the owner page's sections (`page.py`) and a public page about
   the model with no position on it (`report.py`).

Nothing here buys anything.
"""
