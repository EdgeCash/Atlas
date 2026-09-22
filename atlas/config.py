"""Central configuration: paths, seasons and research constants.

Everything that a run depends on is resolved here so that a rebuild is
reproducible from a single place.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Scope
# ---------------------------------------------------------------------------

#: First season Atlas covers. Betting-line coverage before 2018 is patchy and
#: the mission scope is 2018-present.
FIRST_SEASON = 2018

#: Last season to attempt. Seasons with no published data are skipped with a
#: warning rather than failing the build.
LAST_SEASON = int(os.environ.get("ATLAS_LAST_SEASON", "2026"))

#: Divisions treated as "major college football". Research tables are
#: restricted to FBS-vs-FBS games; non-FBS games still feed the point-in-time
#: team histories because they really were played before the next game.
FBS_DIVISIONS = ("fbs",)

#: Regular season + postseason. Exhibition/spring games are excluded.
SEASON_TYPES = ("regular", "postseason")


def seasons() -> list[int]:
    return list(range(FIRST_SEASON, LAST_SEASON + 1))


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Paths:
    root: Path = REPO_ROOT
    data: Path = field(default_factory=lambda: REPO_ROOT / "data")
    raw: Path = field(default_factory=lambda: REPO_ROOT / "data" / "raw")
    staging: Path = field(default_factory=lambda: REPO_ROOT / "data" / "staging")
    warehouse: Path = field(default_factory=lambda: REPO_ROOT / "data" / "warehouse")
    reports: Path = field(default_factory=lambda: REPO_ROOT / "reports")
    docs: Path = field(default_factory=lambda: REPO_ROOT / "docs")

    @property
    def duckdb(self) -> Path:
        return self.warehouse / "atlas.duckdb"

    def ensure(self) -> Paths:
        for p in (self.raw, self.staging, self.warehouse, self.reports, self.docs):
            p.mkdir(parents=True, exist_ok=True)
        return self


def paths() -> Paths:
    """Resolve paths, honouring ATLAS_DATA_DIR for tests and alternate runs."""
    override = os.environ.get("ATLAS_DATA_DIR")
    if override:
        base = Path(override).resolve()
        return Paths(
            root=base,
            data=base,
            raw=base / "raw",
            staging=base / "staging",
            warehouse=base / "warehouse",
            reports=base / "reports",
            docs=base / "docs",
        )
    return Paths()


# ---------------------------------------------------------------------------
# Point-in-time / modelling constants
# ---------------------------------------------------------------------------

#: Shrinkage weight (in "prior games") applied when blending a team's
#: in-season running mean toward its previous-season final mean. The
#: previous-season value is known before a season starts, so using it is
#: point-in-time safe and keeps weeks 1-3 usable.
PRIOR_SEASON_SHRINKAGE_GAMES = 4.0

#: Minimum prior games (in-season) before an unshrunk in-season feature is
#: considered trustworthy. Used for reporting coverage, not for filtering.
MIN_PRIOR_GAMES = 2

#: Plays inside "garbage time" are dropped from efficiency aggregates.
#: Thresholds follow the widely used win-probability-free heuristic.
GARBAGE_TIME_MARGIN = {1: 38, 2: 28, 3: 22, 4: 16}

#: A drive that reaches the opponent's 40-yard line is a "scoring opportunity".
SCORING_OPPORTUNITY_YARDS_TO_GOAL = 40

#: Random seed for every stochastic step (model fits, permutation importance).
SEED = 20180101

#: Home-field advantage is estimated per fold rather than hard-coded; this is
#: only the starting value for optimisers.
HFA_PRIOR_POINTS = 2.5
