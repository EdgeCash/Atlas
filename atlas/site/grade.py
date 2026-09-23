"""The Atlas grade, computed. Version 2.

`docs/GRADE_V2_IMPLEMENTATION.md` is the specification; `GRADE_STRATEGY_V2.md`
is the research behind it. Nothing about a grade is entered by hand.

V1 looked calibration up in a seven-row table of disagreement bands, which made
the score a step function: seven clusters, four reachable letters, 67% of a
real slate at A. The bands turned out to be an artifact of the research
report's own buckets. Re-slicing the same seven seasons finely shows a smooth,
monotone, near-linear relationship between the size of a disagreement and the
calibration gap, and it holds out of sample in every season tested.

V2 therefore fits the curve instead of reading the table. The score is
continuous, every letter is reachable, and the thresholds are absolute: a
card's letter depends on that card and not on what else is on the board.

The grade is **not a recommendation**. It measures how much weight the rest of
the card deserves, and it is built so that the loudest cards score lowest.

One consequence is worth stating where it cannot be missed. Cards where Atlas
and the market agree to within a point realise 50.8% against a 51.3% claim -
a coin flip, p = 0.69. An A+ card is one where Atlas has contributed nothing.
So the grade prioritises in one direction only: it says what to discount, not
what to look at first. `_lesson` says so on every card at the top of the scale.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from atlas import config
from atlas.util import get_logger

LOG = get_logger(__name__)

#: Component weights, out of 100. Signal stability is gone: it measured "in how
#: many of seven seasons did this band beat 50%", and there are no bands now.
WEIGHTS = {"calibration": 45, "agreement": 25, "conditions": 15, "completeness": 15}

#: A calibration gap this wide scores zero. The worst the curve reaches inside
#: the measured range is about −0.26, so the scale has headroom.
GAP_SCALE = 0.35

#: A disagreement this large scores zero on agreement. 10+ points is where
#: realised accuracy collapses to chance.
DISAGREEMENT_SCALE = 12.0

#: Score floors for each letter. Chosen once from the seven-season distribution
#: of V2 scores so that A+ and F are both rare and every letter is reachable -
#: and then fixed. Calibrating thresholds against history is not grading on a
#: curve: a curve recomputes the boundaries from whoever turned up this week,
#: so the same card takes a different letter on a different Saturday. These do
#: not move unless the research moves.
LETTERS = ((96, "A+"), (90, "A"), (79, "B"), (66, "C"), (51, "D"), (0, "F"))

#: Measured in `GRADE_REWORK_OPTIONS.md` §C2 and stable season by season: weeks
#: 1-4 calibrate worse in 6 of 7 seasons, and a total that has moved 1.5 or
#: more since it opened calibrates worse in 5 of 6. Both worsen the gap, which
#: lowers the grade, which is the direction the evidence points.
EARLY_SEASON_WEEKS = 4
EARLY_SEASON_PENALTY = -0.028
UNSETTLED_MOVE = 1.5
UNSETTLED_PENALTY = -0.022

#: Bands, matching `atlas.research.market_aware.EDGE_BUCKETS`. V2 does not
#: grade from these - it fits a curve - but the reliability record on the card
#: and the research page still report by band, because a table of seven rows is
#: how a reader checks a curve.
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
class Curve:
    """Calibration gap as a function of how far Atlas sits from the market.

    ``gap(d) = -a * d ** p``, fitted to finely sliced out-of-sample results.
    The fitted exponent is near 1, so the relationship is close to linear; the
    coefficient moves by a factor of about 2.5 across seasons, which is why
    this is refitted on every build rather than transcribed.
    """

    a: float
    p: float
    games: int
    r: float
    seasons: int

    def gap(self, disagreement: float) -> float:
        d = max(abs(float(disagreement)), 0.05)
        return -self.a * d ** self.p


@dataclass(frozen=True)
class Conditions:
    """The two things besides the disagreement that move a card's grade.

    Both were measured against seven seasons and both held season by season:
    early-season cards calibrate worse (6 of 7), and cards whose total has
    moved since it opened calibrate worse (5 of 6). They are small - two to
    three points of calibration gap against twenty-seven across the range -
    and they are the only inputs that separate two cards the market treats
    the same way.
    """

    week: int = 99
    movement: float | None = None

    @property
    def early(self) -> bool:
        return self.week <= EARLY_SEASON_WEEKS

    @property
    def unsettled(self) -> bool:
        return self.movement is not None and abs(self.movement) >= UNSETTLED_MOVE

    @property
    def penalty(self) -> float:
        return ((EARLY_SEASON_PENALTY if self.early else 0.0)
                + (UNSETTLED_PENALTY if self.unsettled else 0.0))

    @property
    def score(self) -> float:
        """0-1. Half for a mature season, half for a settled market."""
        maturity = 0.5 if not self.early else 0.5 * min(1.0, max(0, self.week - 1) / 4)
        settled = 0.5 if not self.unsettled else 0.2
        return min(1.0, maturity + settled)


@dataclass(frozen=True)
class Grade:
    letter: str
    score: float
    calibration: float
    agreement: float
    conditions: float
    completeness: float
    band: Band
    headline: str
    lesson: list[str]
    disagreement: float
    expected_gap: float
    condition_notes: list[str]

    @property
    def components(self) -> list[tuple[str, float, int]]:
        return [
            ("Calibration", self.calibration, WEIGHTS["calibration"]),
            ("Market agreement", self.agreement, WEIGHTS["agreement"]),
            ("Card conditions", self.conditions, WEIGHTS["conditions"]),
            ("Data completeness", self.completeness, WEIGHTS["completeness"]),
        ]

    @property
    def tone(self) -> str:
        return {"A+": "a", "A": "a", "B": "b", "C": "c", "D": "d", "F": "f"}[self.letter]

    @property
    def low(self) -> bool:
        return self.letter in ("D", "F")

    @property
    def word(self) -> str:
        """The letter in one word, for a social card and a board caption."""
        return {"A+": "Very high", "A": "High", "B": "Solid",
                "C": "Mixed", "D": "Low", "F": "Low"}[self.letter]


def letter_for(score: float) -> str:
    for floor, letter in LETTERS:
        if score >= floor:
            return letter
    return "F"


def compute(disagreement: float, band: Band, completeness: float, *,
            curve: Curve, conditions: Conditions | None = None) -> Grade:
    """The rubric. Four components, one letter, nothing entered by hand."""
    conditions = conditions or Conditions()
    expected_gap = curve.gap(disagreement) + conditions.penalty

    calibration = max(0.0, 1.0 - abs(expected_gap) / GAP_SCALE)
    agreement = max(0.0, 1.0 - abs(float(disagreement)) / DISAGREEMENT_SCALE)
    condition_score = conditions.score
    completeness = min(1.0, max(0.0, float(completeness)))

    score = (
        WEIGHTS["calibration"] * calibration
        + WEIGHTS["agreement"] * agreement
        + WEIGHTS["conditions"] * condition_score
        + WEIGHTS["completeness"] * completeness
    )
    letter = letter_for(score)
    return Grade(
        letter=letter,
        score=score,
        calibration=calibration,
        agreement=agreement,
        conditions=condition_score,
        completeness=completeness,
        band=band,
        headline=_headline(letter, band, disagreement),
        lesson=_lesson(letter, band, disagreement, expected_gap),
        disagreement=abs(float(disagreement)),
        expected_gap=expected_gap,
        condition_notes=_condition_notes(conditions),
    )


def _condition_notes(conditions: Conditions) -> list[str]:
    out = []
    if conditions.early:
        out.append(
            f"It is week {conditions.week}. Team profiles are still shrunk "
            "toward last season, and early-season cards have calibrated worse "
            "in six of seven seasons."
        )
    if conditions.unsettled:
        out.append(
            f"The total has moved {abs(conditions.movement):.1f} points since "
            "it opened. Cards on a market that has moved have calibrated worse "
            "in five of six seasons."
        )
    if not out:
        out.append(
            "The season is mature enough for the team profiles to have "
            "settled, and the market has not moved much since it opened."
        )
    return out


def _lesson(letter: str, band: Band, disagreement: float,
            expected_gap: float) -> list[str]:
    """Three plain-English lines: what the letter says, what Atlas did, and
    what the record behind it is.

    The grade is the least self-explanatory thing on the card - a letter is a
    symbol, and a symbol a reader has to be taught is a symbol they skip. Each
    card teaches it again, in words, from its own numbers.
    """
    edge = abs(float(disagreement))
    near = "this close to" if edge < 2 else "this far from"
    size = ("small" if edge < 1 else "modest" if edge < 2 else "moderate" if edge < 4
            else "wide" if edge < 6 else "large" if edge < 10 else "very large")
    claim = (f"Across {seasons_word(band)}, cards {near} the market claimed "
             f"{band.claimed:.0%} accuracy and delivered {band.realised:.0%}.")

    if letter == "A+":
        return [
            "Historically reliable.",
            f"Atlas and the market land on the same number, {edge:.1f} points apart.",
            "Agreement is where this model is most reliable, and where it is "
            "adding least — a top grade means trust the number, not that this "
            "is the card to read first.",
        ]
    if letter == "A":
        return [
            "Historically reliable.",
            f"Atlas and the market are closely aligned, {edge:.1f} points apart.",
            claim,
        ]
    if letter == "B":
        return [
            "Historically sound.",
            f"A {size} disagreement of {edge:.1f} points.",
            claim + " The claim runs a little ahead of the delivery.",
        ]
    if letter == "C":
        return [
            "Mixed record.",
            f"A {size} disagreement of {edge:.1f} points.",
            claim + " That gap is where this grade comes from.",
        ]
    if letter == "D":
        return [
            "Historically unreliable.",
            f"A {size} disagreement of {edge:.1f} points.",
            claim + " Atlas commonly struggles this far out.",
        ]
    return [
        "Historically unreliable.",
        f"A {size} disagreement of {edge:.1f} points.",
        claim + " Atlas marks its own card down.",
    ]


def seasons_word(band: Band) -> str:
    """"five seasons", from the record itself, never transcribed."""
    words = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven",
             8: "eight", 9: "nine", 10: "ten"}
    n = int(band.seasons)
    return f"{words.get(n, str(n))} season{'s' if n != 1 else ''}"


def _headline(letter: str, band: Band, disagreement: float) -> str:
    if letter in ("A+", "A"):
        return (
            "Atlas and the market agree closely, and this disagreement band has "
            f"been among the model's most consistent across {seasons_word(band)}."
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


#: The market the grade is computed on. The card's headline is the projected
#: score, and the spread is the market that prices it.
GRADED_MARKET = "margin"


def calibration_bands(market_name: str = GRADED_MARKET) -> dict[str, Band]:
    """Claimed vs realised accuracy by band, from the model's own record.

    The record is the model walked forward over every completed season it
    never saw while being built (`atlas/models/ncaaf_projection.history`),
    written to the tracking store by the weekly refresh so a build never
    drifts from it. Recomputed here on every build, never transcribed.
    """
    frame = _scored(market_name)
    frame["band"] = frame["abs_edge"].map(band_label)
    bands: dict[str, Band] = {}
    for label, block in frame.groupby("band"):
        per_season = block.groupby("season")["won"].agg(["size", "mean"])
        per_season = per_season[per_season["size"] >= 25]
        claimed, realised = float(block["claimed"].mean()), float(block["won"].mean())
        bands[str(label)] = Band(
            label=str(label),
            games=int(len(block)),
            claimed=claimed,
            realised=realised,
            gap=realised - claimed,
            seasons=int(len(per_season)),
            seasons_above=int((per_season["mean"] > 0.5).sum()),
        )
    LOG.info("calibration bands: %d computed for %s", len(bands), market_name)
    return bands


#: Slice width for the curve fit, in points of disagreement. Narrow enough
#: that the shape is not an artifact of the slicing, wide enough that each
#: slice carries a usable number of games.
SLICE = 0.5
MIN_SLICE_GAMES = 40


def calibration_curve(market_name: str = GRADED_MARKET) -> Curve:
    """Fit ``gap(d) = -a * d ** p`` to seven seasons, out of sample.

    The seven-band table this replaced was a reporting convention, not a
    property of the data: sliced at half a point instead, the relationship
    between the size of a disagreement and the calibration gap is smooth and
    close to linear. Refitted on every build, because the coefficient moves by
    about 2.5x across seasons and a transcribed constant would drift.
    """
    frame = _scored(market_name)

    edges, gaps, weights = [], [], []
    upper = float(frame["abs_edge"].quantile(0.995))
    lo = 0.0
    while lo < upper:
        block = frame[(frame["abs_edge"] >= lo) & (frame["abs_edge"] < lo + SLICE)]
        if len(block) >= MIN_SLICE_GAMES:
            edges.append(lo + SLICE / 2)
            gaps.append(float(block["won"].mean() - block["claimed"].mean()))
            weights.append(len(block))
        lo += SLICE

    edges_a, gaps_a = np.asarray(edges), np.asarray(gaps)
    negative = gaps_a < 0
    if negative.sum() < 4:
        raise RuntimeError("not enough negatively calibrated slices to fit a curve")

    # Least squares in log space: log(-gap) = log(a) + p * log(d). Slices where
    # the model happened to beat its claim carry no information about the decay
    # and are left out of the fit rather than clamped.
    coef = np.polyfit(np.log(edges_a[negative]), np.log(-gaps_a[negative]), 1)
    p_exp, a_coef = float(coef[0]), float(np.exp(coef[1]))
    predicted = -a_coef * edges_a ** p_exp
    r = float(np.corrcoef(predicted, gaps_a)[0, 1])

    curve = Curve(a=a_coef, p=p_exp, games=int(len(frame)), r=r,
                  seasons=int(frame["season"].nunique()))
    LOG.info("calibration curve: gap(d) = -%.4f * d^%.3f  (r=%.2f, n=%d)",
             curve.a, curve.p, curve.r, curve.games)
    return curve


def _scored(market_name: str) -> pd.DataFrame:
    """The model's record against the closing number, for one market.

    Read from the tracking store's ``calibration`` table, which the weekly
    refresh writes. If it is missing - a fresh checkout, a test - the record
    is built in process from the warehouse, which is slower but the same.
    """
    from atlas.live.store import Store

    table = Store.open().read("calibration")
    if table.empty:
        from atlas.models import ncaaf_projection, ncaaf_state
        from atlas.research.dataset import load_research_frame

        paths = config.paths()
        LOG.warning("no calibration table; building the model's record in process")
        table = ncaaf_projection.history(
            load_research_frame(paths.warehouse),
            choices=ncaaf_state.load_choices(ncaaf_state.choices_path(paths.root)))
    frame = table[table["market"] == market_name].copy()
    for column in ("abs_edge", "claimed", "won", "season"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame.dropna(subset=["abs_edge", "claimed", "won"]).reset_index(drop=True)


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
