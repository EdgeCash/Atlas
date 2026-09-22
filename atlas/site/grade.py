"""The Atlas grade, computed.

`docs/ATLAS_CARD_SPEC.md` §5 defines a four-component rubric out of 100. This
module is that definition in code; nothing about a grade is entered by hand,
and a test pins the two worked examples from the spec.

The grade is **not a recommendation**. It measures how much weight the rest of
the card deserves, and it is built so that the loudest cards score lowest —
because that is what seven seasons of calibration say should happen.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from atlas.research import beta_report as beta
from atlas.research import market_aware as ma
from atlas.util import get_logger

LOG = get_logger(__name__)

#: Component weights, out of 100.
WEIGHTS = {"calibration": 40, "agreement": 25, "stability": 20, "completeness": 15}

#: A calibration gap this wide scores zero. The worst band Atlas measures sits
#: at −0.278, so the scale has headroom without being generous.
GAP_SCALE = 0.35

#: A disagreement this large scores zero on agreement. Chosen from the band
#: table: 10+ points is where realised accuracy collapses to chance.
DISAGREEMENT_SCALE = 12.0

#: Score floors for each letter.
LETTERS = ((90, "A+"), (80, "A"), (70, "B"), (60, "C"), (50, "D"), (0, "F"))

#: Bands, matching `atlas.research.market_aware.EDGE_BUCKETS`.
BANDS = ((0, 1), (1, 2), (2, 4), (4, 6), (6, 8), (8, 10), (10, 1000))


def band_label(disagreement: float) -> str:
    edge = abs(float(disagreement))
    for low, high in BANDS:
        if low <= edge < high:
            return f"{low}-{high}" if high < 1000 else f"{low}+"
    return "10+"


@dataclass(frozen=True)
class Band:
    """What history says about cards in one disagreement band."""

    label: str
    games: int
    claimed: float
    realised: float
    gap: float
    seasons: int
    seasons_above: int

    @property
    def stability(self) -> float:
        return self.seasons_above / self.seasons if self.seasons else 0.0


@dataclass(frozen=True)
class Grade:
    letter: str
    score: float
    calibration: float
    agreement: float
    stability: float
    completeness: float
    band: Band
    headline: str

    @property
    def components(self) -> list[tuple[str, float, int]]:
        return [
            ("Calibration", self.calibration, WEIGHTS["calibration"]),
            ("Market agreement", self.agreement, WEIGHTS["agreement"]),
            ("Signal stability", self.stability, WEIGHTS["stability"]),
            ("Data completeness", self.completeness, WEIGHTS["completeness"]),
        ]

    @property
    def tone(self) -> str:
        return {"A+": "a", "A": "a", "B": "b", "C": "c", "D": "d", "F": "f"}[self.letter]

    @property
    def low(self) -> bool:
        return self.letter in ("D", "F")


def letter_for(score: float) -> str:
    for floor, letter in LETTERS:
        if score >= floor:
            return letter
    return "F"


def compute(disagreement: float, band: Band, completeness: float) -> Grade:
    """The rubric. Four components, one letter."""
    calibration = max(0.0, 1.0 - abs(band.gap) / GAP_SCALE)
    agreement = max(0.0, 1.0 - abs(float(disagreement)) / DISAGREEMENT_SCALE)
    stability = band.stability
    completeness = min(1.0, max(0.0, float(completeness)))

    score = (
        WEIGHTS["calibration"] * calibration
        + WEIGHTS["agreement"] * agreement
        + WEIGHTS["stability"] * stability
        + WEIGHTS["completeness"] * completeness
    )
    letter = letter_for(score)
    return Grade(
        letter=letter,
        score=score,
        calibration=calibration,
        agreement=agreement,
        stability=stability,
        completeness=completeness,
        band=band,
        headline=_headline(letter, band, disagreement),
    )


def _headline(letter: str, band: Band, disagreement: float) -> str:
    if letter in ("A+", "A"):
        return (
            "Atlas and the market agree closely, and this disagreement band has "
            "been among the model's most consistent across seven seasons."
        )
    if letter == "B":
        return (
            "A moderate disagreement in a band where the model's claim and its "
            "realised accuracy stay reasonably close."
        )
    if letter == "C":
        return (
            "The disagreement is wide enough that the model's historical claim "
            "runs well ahead of what it delivered."
        )
    return (
        f"Atlas sits {abs(disagreement):.1f} points from the market. Cards in "
        f"the {band.label} band claimed {band.claimed:.0%} accuracy and "
        f"delivered {band.realised:.0%} — read the drivers and the market "
        "context, and treat the projection as weak."
    )


# ---------------------------------------------------------------------------
# The calibration table the rubric reads
# ---------------------------------------------------------------------------


def calibration_bands(market_name: str = "total") -> dict[str, Band]:
    """Claimed vs realised accuracy by band, computed from the warehouse.

    Recomputed at build time rather than transcribed, so the site can never
    drift from the research it cites. Seven seasons, out of sample, under the
    walk-forward protocol every earlier phase used.
    """
    from atlas.research.dataset import load_research_frame, research_sample

    frame = ma.prepare(research_sample(load_research_frame()))
    market = beta.markets(frame)[market_name]
    scored = ma.walk_forward(frame, market)

    audit = ma.edge_audit(scored, market).set_index("bucket")
    bucketed = ma.bucket_edges(scored, market)
    probs = ma.to_probability(bucketed, market, 0.0)
    outcomes = pd.to_numeric(bucketed[market.outcome], errors="coerce")
    bucketed["won"] = ma.realised(probs, outcomes)

    bands: dict[str, Band] = {}
    for label, block in bucketed.groupby("edge_bucket", observed=True):
        label = str(label)
        if label not in audit.index:
            continue
        per_season = block.dropna(subset=["won"]).groupby("season")["won"].agg(["size", "mean"])
        per_season = per_season[per_season["size"] >= 25]
        row = audit.loc[label]
        bands[label] = Band(
            label=label,
            games=int(row["games"]),
            claimed=float(row["claimed"]),
            realised=float(row["actual"]),
            gap=float(row["calibration_gap"]),
            seasons=int(len(per_season)),
            seasons_above=int((per_season["mean"] > 0.5).sum()),
        )
    LOG.info("calibration bands: %d computed for %s", len(bands), market_name)
    return bands


def overall(bands: dict[str, Band]) -> Band:
    """The all-cards row every reliability table shows beside the band row."""
    games = sum(b.games for b in bands.values()) or 1
    weight = lambda b: b.games / games  # noqa: E731 - local and obvious
    return Band(
        label="all cards",
        games=games,
        claimed=float(np.sum([b.claimed * weight(b) for b in bands.values()])),
        realised=float(np.sum([b.realised * weight(b) for b in bands.values()])),
        gap=float(np.sum([b.gap * weight(b) for b in bands.values()])),
        seasons=max((b.seasons for b in bands.values()), default=0),
        seasons_above=0,
    )
