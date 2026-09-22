"""The Atlas site build.

Two kinds of test. Most check that a page says what the specification says it
must. The last group checks the thing the whole product rests on: no page
tells a reader what to do, and the grade is computed rather than chosen.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from atlas.site import data, render, social
from atlas.site import drivers as driving
from atlas.site import grade as grading
from atlas.site.data import Card, Line, Side

#: A synthetic percentile pool, so drivers render without a warehouse.
_POOL = {
    metric: np.linspace(low, high, 200)
    for metric, (low, high) in {
        "adj_off_epa": (-0.2, 0.4), "adj_success_rate": (0.3, 0.6),
        "adj_def_success_rate": (0.28, 0.5), "adj_explosiveness": (0.8, 1.5),
        "adj_pace": (24.0, 33.0), "plays_per_game": (44.0, 66.0),
    }.items()
}


#: Representative statistics per band, so a fixture card lands in a band whose
#: history looks like that band's rather than inheriting a default.
BAND_STATS = {
    "0-1": (751, 0.513, 0.522, 0.0095, 7, 3),
    "1-2": (776, 0.536, 0.521, -0.0153, 7, 5),
    "2-4": (1254, 0.571, 0.522, -0.0491, 7, 4),
    "4-6": (884, 0.617, 0.528, -0.0884, 7, 5),
    "6-8": (610, 0.660, 0.525, -0.1358, 7, 5),
    "8-10": (329, 0.703, 0.526, -0.1776, 7, 5),
    "10+": (402, 0.774, 0.510, -0.2639, 5, 3),
}


def _band(label="2-4", **overrides) -> grading.Band:
    games, claimed, realised, gap, seasons, above = BAND_STATS.get(
        label, BAND_STATS["2-4"])
    fields = {"label": label, "games": games, "claimed": claimed,
              "realised": realised, "gap": gap, "seasons": seasons,
              "seasons_above": above}
    fields.update(overrides)
    return grading.Band(**fields)


def _side(key: str, name: str, colour: str) -> Side:
    return Side(key=key, name=name, short=name.split()[0], abbr=name[:3].upper(),
                colour=colour, record="3-1", conference="Big 12",
                metrics={"adj_off_epa": 0.2, "adj_success_rate": 0.48,
                         "adj_def_success_rate": 0.33, "adj_explosiveness": 1.1,
                         "adj_pace": 28.0, "plays_per_game": 52.0})


def _card(*, model_total=50.7, market_total=48.5, grade=True) -> Card:
    card = Card(
        game_id=1, season=2026, week=5,
        kickoff=datetime.now(UTC) + timedelta(days=2),
        home=_side("home", "Iowa State", "#C8102E"),
        away=_side("away", "Utah Utes", "#CC0000"),
        venue="Jack Trice Stadium", city="Ames", state="IA", tv="FOX",
        neutral=False, conference_game=True,
        weather={"temp": 64.0, "wind": 8.0, "precip": 0.0},
        spread=Line("margin", -11.5, -7.5, -110.0, -105.0),
        total=Line("total", 49.5, market_total, -110.0, -105.0),
        moneyline={"home_open": "+370", "home_close": "+270",
                   "away_open": "-485", "away_close": "-340"},
        books=1, model_margin=-7.1, model_total=model_total, grade=None,
    )
    if grade:
        difference = card.total_difference
        card.grade = grading.compute(difference, _band(grading.band_label(difference)), 1.0)
    card.drivers = driving.select(card, _POOL)
    card.cautions = data.cautions(card)
    return card


# ---------------------------------------------------------------------------
# The grade is computed
# ---------------------------------------------------------------------------


def test_the_rubric_weights_sum_to_one_hundred():
    assert sum(grading.WEIGHTS.values()) == 100


def test_a_larger_disagreement_can_never_raise_a_grade():
    """The product's central claim. If this ever inverts, Atlas is shouting
    loudest where its model is weakest, like everything else in the category."""
    band = _band()
    scores = [grading.compute(d, band, 1.0).score for d in (0.5, 2.0, 5.0, 9.0, 14.0)]
    assert scores == sorted(scores, reverse=True)


def test_a_worse_calibrated_band_can_never_raise_a_grade():
    tight = grading.compute(3.0, _band(gap=-0.01), 1.0)
    loose = grading.compute(3.0, _band(gap=-0.26), 1.0)
    assert tight.score > loose.score


def test_the_letter_boundaries_match_the_specification():
    assert grading.letter_for(90) == "A+"
    assert grading.letter_for(89.9) == "A"
    assert grading.letter_for(80) == "A"
    assert grading.letter_for(70) == "B"
    assert grading.letter_for(60) == "C"
    assert grading.letter_for(50) == "D"
    assert grading.letter_for(49.9) == "F"


def test_band_labels_cover_the_whole_range():
    assert grading.band_label(0.0) == "0-1"
    assert grading.band_label(-3.2) == "2-4"
    assert grading.band_label(9.99) == "8-10"
    assert grading.band_label(40.0) == "10+"


def test_a_worked_example_from_the_specification():
    """Spec §5: the F example. The inputs are the spec's, so the arithmetic
    is pinned even if the band table moves as seasons accumulate."""
    grade = grading.compute(11.174, _band("10+", gap=-0.2777, claimed=0.7727,
                                          realised=0.495, seasons=5,
                                          seasons_above=2, games=402), 1.0)
    assert grade.letter == "F"
    assert grade.score == pytest.approx(33.0, abs=1.0)


def test_missing_inputs_cost_the_completeness_component():
    full = grading.compute(3.0, _band(), 1.0)
    partial = grading.compute(3.0, _band(), 0.5)
    assert full.score - partial.score == pytest.approx(7.5)


# ---------------------------------------------------------------------------
# The card renders what the specification requires
# ---------------------------------------------------------------------------


def _page(card: Card) -> str:
    bands = {label: _band(label) for label in BAND_STATS}
    return render.card_page(card, bands=bands, overall_band=_band("2-4"))


def test_tier_one_is_visible_without_opening_anything():
    """The five-second view. Everything here must be in the page before a
    reader taps anything: game, market, Atlas, difference, grade, why."""
    page = _page(_card())
    tier1 = page.split('<div class="tier2">')[0]
    assert "Jack Trice Stadium" in tier1          # game
    assert "Market" in tier1 and "48.5" in tier1  # market
    assert "Atlas projects" in tier1              # projection
    assert "Difference" in tier1                  # difference
    assert 'class="grade-mark"' in tier1          # grade, dominant
    assert ">Why</h2>" in tier1                   # why
    assert "Be careful about" in tier1            # rule 5, question 5


def test_every_section_is_still_on_the_page_behind_a_panel():
    """Rule 1 is hide, not remove. A reader who wants the detail must be one
    tap away from all of it, and it must be in the DOM for search and print."""
    page = _page(_card())
    for summary in ("Market detail", "Projection detail",
                    "How this grade was computed", "All drivers",
                    "Market movement", "Reliability record"):
        assert summary in page, f"missing panel: {summary}"
    # The detail itself, not just the summary.
    assert "Unanchored model" in page
    assert "A difference is not an edge" in page
    assert "Calibration by disagreement band" in page


def test_the_panels_are_native_and_need_no_javascript():
    page = _page(_card())
    assert page.count("<details") >= 6
    assert "<script" not in page


def test_the_projection_is_anchored_and_the_raw_model_is_shown_beside_it():
    """The spec's central display rule: publish the accurate number, show the
    correction rather than hiding it."""
    card = _card(model_total=50.7, market_total=48.5)
    page = _page(card)
    assert card.anchored_total == pytest.approx(48.742, abs=0.01)
    assert "48.7" in page
    assert "50.7" in page
    assert "Unanchored model" in page


def test_the_spread_projection_equals_the_market():
    """Weight 1.00 on spreads. The model's contribution could not be told
    apart from zero, so Atlas publishes the market's number."""
    card = _card()
    assert card.anchored_margin == card.spread.current


def test_a_low_grade_card_leads_with_its_low_confidence():
    """Rule 4: the grade is the centrepiece, and on a weak card it has to be
    the first thing a reader takes in."""
    card = _card(model_total=60.0)
    assert card.grade.low
    page = _page(card)
    tier1 = page.split('<div class="tier2">')[0]
    assert "Low confidence" in tier1
    assert 'class="card grade-hero f"' in tier1 or 'class="card grade-hero d"' in tier1
    assert tier1.index("grade-mark") < tier1.index("Be careful about")


def test_cautions_are_specific_to_the_card():
    """Rule 5, question 5. A caution that appears on every card is read as
    decoration, so the wide-disagreement one must only fire when it applies."""
    loud = _card(model_total=62.0)
    quiet = _card(model_total=49.0)
    assert any("points from the market" in c for c in loud.cautions)
    assert not any("points from the market" in c for c in quiet.cautions)
    assert len(loud.cautions) <= 3


def test_a_card_with_no_market_still_publishes():
    card = _card(grade=False)
    card.total = Line("total", None, None, None, None)
    card.spread = Line("margin", None, None, None, None)
    card.cautions = []
    page = _page(card)
    assert "Atlas Sports Intelligence" in page
    assert "No spread posted" in page or "no market posted" in page
    assert "Not graded" in page


def test_a_missing_moneyline_is_never_derived():
    card = _card()
    card.moneyline = {}
    page = _page(card)
    assert "not posted" in page
    assert "deriving one from the spread" in page


def test_team_accents_fall_back_when_two_teams_collide():
    """Iowa State cardinal and Utah crimson would read as one colour."""
    home, away = render.accents(_card())
    assert home == "#C8102E"
    assert away == "#6b7480"

    card = _card()
    card.away.colour = "#0a254e"
    _, away = render.accents(card)
    assert away == "#0a254e"


# ---------------------------------------------------------------------------
# The rules
# ---------------------------------------------------------------------------


FORBIDDEN = ("bet", "wager", "stake", "lock", "smash", "hammer", "unit",
             "picks", "parlay", "bankroll", "kelly", "roi")

#: Football and market vocabulary that collides with the list.
ALLOWED_CONTEXT = ("per play", "of plays", "plays per game", "plays · ",
                   "percentile", "combined", "betting market")


def _visible_text(page: str) -> str:
    page = re.sub(r"<script.*?</script>", " ", page, flags=re.S)
    page = re.sub(r"<style.*?</style>", " ", page, flags=re.S)
    return re.sub(r"<[^>]+>", " ", page).lower()


@pytest.mark.parametrize("builder", [
    lambda: _page(_card()),
    lambda: _page(_card(model_total=60.0)),
    lambda: render.nfl_page(),
    lambda: render.premium_page(),
], ids=["card-a", "card-f", "nfl", "premium"])
def test_no_page_tells_a_reader_what_to_do(builder):
    """`docs/BRAND_GUIDE.md`: the vocabulary is a product constraint, not a
    style preference, and it is checked rather than trusted."""
    text = _visible_text(builder())
    offenders = []
    for word in FORBIDDEN:
        for match in re.finditer(rf"\b{word}\b", text):
            window = text[max(0, match.start() - 60):match.end() + 60]
            if any(phrase in window for phrase in ALLOWED_CONTEXT):
                continue
            offenders.append(f"{word!r} in ...{window.strip()}...")
    assert not offenders, "page uses forbidden vocabulary:\n" + "\n".join(offenders)


@pytest.mark.parametrize("builder", [
    lambda: _page(_card()),
    lambda: _page(_card(model_total=60.0)),
], ids=["card-a", "card-f"])
def test_no_card_names_a_side(builder):
    banned = re.compile(
        r"\b(take the|lay the|back the|we like|our pick|recommended side|"
        r"leans? (over|under))\b", re.IGNORECASE)
    assert not banned.findall(builder())


def test_every_card_repeats_the_difference_disclaimer():
    assert "A difference is not an edge" in _page(_card())


def test_the_grade_is_labelled_as_information_quality():
    page = _page(_card())
    flat = " ".join(page.split())
    assert "not a recommendation" in flat
    assert "How much weight this card's information deserves" in flat
    assert "says nothing about which side of a market anyone should take" in flat


# ---------------------------------------------------------------------------
# Social templates
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("template", [social.wide, social.square],
                         ids=["1200x675", "1080x1080"])
def test_social_templates_are_well_formed_and_carry_the_required_fields(template):
    from xml.etree import ElementTree

    card = _card()
    svg = template(card)
    ElementTree.fromstring(svg)          # parses, so it will rasterise
    assert "Atlas" in svg
    assert card.grade.letter in svg
    assert social.SITE in svg
    text = _visible_text(svg)
    for word in ("bet", "wager", "lock", "unit", "picks"):
        assert not re.search(rf"\b{word}\b", text), f"social template leaked {word!r}"


def test_social_templates_use_the_declared_canvas():
    card = _card()
    assert 'width="1200" height="675"' in social.wide(card)
    assert 'width="1080" height="1080"' in social.square(card)
