"""Consensus test: does a computer consensus know something the close does not?

The frozen configuration of ``docs/CONSENSUS_PREREGISTRATION.md``. These
constants are committed before any holdout game is scored; the scoring code
comes in a later commit and reads them from here. If one of them were edited
after a result was seen, the test would be worthless. The git history is the
audit trail.
"""

from __future__ import annotations

SEED = 20260926
N_BOOTSTRAP = 10_000

# ---------------------------------------------------------------------------
# Frozen configuration - see docs/CONSENSUS_PREREGISTRATION.md
# ---------------------------------------------------------------------------

#: Point-in-time members only (atlas/staging/ratings.py). SP+ and the FPI
#: rating are the previous season's finals and are excluded by design.
MEMBERS: tuple[str, ...] = ("elo", "fpi_projection")

#: Where each member's implied-margin map is fitted. Nothing is chosen here.
FIT_SEASONS: tuple[int, ...] = (2016, 2017, 2018, 2019, 2020)
#: Each scored once.
HOLDOUT_SEASONS: tuple[int, ...] = (2021, 2022, 2023, 2024, 2025)

#: FBS against FBS, regular season, from this week on.
FIRST_WEEK = 5
#: A season enters only if at least one member covers this share of its games.
MIN_COVERAGE = 0.80
#: The FPI projection is clipped before its inverse normal.
FPI_PROB_CLIP = (0.01, 0.99)

#: The fixed selection fraction for Q1b and Q2, per season. No threshold scan.
SELECT_FRACTION = 0.10

# --- pre-registered pass criteria ------------------------------------------

#: American odds -> (break-even win rate, units returned by a win).
JUICE: dict[int, tuple[float, float]] = {
    -110: (110 / 210, 100 / 110),
    -115: (115 / 215, 100 / 115),
}
BREAK_EVEN = JUICE[-110][0]
#: Criterion 2: the lower bound of the 95% interval on the win rate.
MIN_CI_LOWER = 0.50
#: Criterion 3: holdout seasons that must individually clear break-even.
MIN_SEASONS_ABOVE = 4
#: Criterion 4: expected units must be positive at this price.
STRESS_PRICE = -115
#: Q1: the lower bound of the 95% interval on beta must exceed this.
MIN_BETA_LOWER = 0.0
#: Q2: the lower bound of the 95% interval on (agree - disagree) must exceed this.
MIN_AGREE_EDGE_LOWER = 0.0
