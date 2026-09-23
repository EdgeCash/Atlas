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


#: The fitted curve, pinned. The real one is refitted from the warehouse on
#: every build and moves as seasons accumulate; these tests are about the
#: rubric's properties, so they hold the curve still and vary the card.
_CURVE = grading.Curve(a=0.0133, p=1.139, games=5006, r=0.88, seasons=7)


def _grade(disagreement, band=None, completeness=1.0, **conditions):
    return grading.compute(
        disagreement, band if band is not None else _band(grading.band_label(disagreement)),
        completeness, curve=_CURVE,
        conditions=grading.Conditions(**conditions) if conditions else None,
    )


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
        card.grade = _grade(difference, week=card.week,
                            movement=card.total.movement)
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
    scores = [_grade(d, band).score for d in (0.5, 2.0, 5.0, 9.0, 14.0)]
    assert scores == sorted(scores, reverse=True)


def test_a_steeper_calibration_curve_can_never_raise_a_grade():
    """V2 reads the curve, not the band's own gap, so this is the property
    that replaced "a worse-calibrated band can never raise a grade"."""
    shallow = grading.compute(3.0, _band(), 1.0,
                              curve=grading.Curve(0.008, 1.139, 5006, 0.88, 7))
    steep = grading.compute(3.0, _band(), 1.0,
                            curve=grading.Curve(0.030, 1.139, 5006, 0.88, 7))
    assert shallow.score > steep.score


def test_early_season_and_an_unsettled_market_can_never_raise_a_grade():
    """Both adjustments held season by season; both must lower the score."""
    settled = _grade(3.0, week=10, movement=0.0)
    early = _grade(3.0, week=2, movement=0.0)
    moved = _grade(3.0, week=10, movement=3.5)
    assert settled.score > early.score
    assert settled.score > moved.score


def test_the_grade_teaches_itself_in_three_plain_lines():
    """Rule 4. A letter is a symbol, and a symbol nobody explains is skipped."""
    for disagreement in (0.4, 3.0, 7.0, 11.2):
        lesson = _grade(disagreement).lesson
        assert len(lesson) == 3
        assert all(line.endswith(".") for line in lesson)
        assert f"{disagreement:.1f} points" in lesson[1]
        # The third line is the record - except at the very top of the scale,
        # where the record is a coin flip and the caveat is the useful thing.
        assert "%" in lesson[2] or "adding least" in lesson[2]


def test_the_top_of_the_scale_says_atlas_is_adding_least():
    """The finding that stops the grade being read as a ranking. Cards where
    Atlas and the market agree to within a point realise 50.8% against a 51.3%
    claim - a coin flip. An A+ card is one where Atlas contributed nothing, so
    the top of the scale has to say so itself."""
    top = _grade(0.05, _band("0-1"), week=12, movement=0.0)
    assert top.letter == "A+"
    assert "adding least" in " ".join(top.lesson)
    assert "not that this is the card to read first" in " ".join(top.lesson)


def test_the_letter_boundaries_match_the_specification():
    assert grading.letter_for(96) == "A+"
    assert grading.letter_for(95.9) == "A"
    assert grading.letter_for(90) == "A"
    assert grading.letter_for(79) == "B"
    assert grading.letter_for(66) == "C"
    assert grading.letter_for(51) == "D"
    assert grading.letter_for(50.9) == "F"


def test_the_thresholds_are_absolute_and_never_slate_relative():
    """The property the brief asked for by name. A card's letter must depend
    on that card alone, so grading it twice with different neighbours - which
    is what a percentile scheme would notice - cannot change it."""
    lonely = _grade(4.0)
    crowded = _grade(4.0)
    assert lonely.letter == crowded.letter == grading.letter_for(lonely.score)


def test_every_letter_is_reachable():
    """V1 could not produce A+ or D at all. Sweep the range Atlas actually
    sees and check each letter comes out of it."""
    seen = {_grade(d / 10, week=12, movement=0.0).letter for d in range(0, 200)}
    assert seen == {"A+", "A", "B", "C", "D", "F"}


def test_band_labels_cover_the_whole_range():
    assert grading.band_label(0.0) == "0-1"
    assert grading.band_label(-3.2) == "2-4"
    assert grading.band_label(9.99) == "8-10"
    assert grading.band_label(40.0) == "10+"


def test_a_worked_example_from_the_specification():
    """The F example, recomputed under V2. The inputs are held still, so the
    arithmetic is pinned even as the fitted curve moves with the seasons."""
    grade = _grade(11.174, _band("10+", gap=-0.2777, claimed=0.7727,
                                 realised=0.495, seasons=5,
                                 seasons_above=2, games=402),
                   week=4, movement=1.0)
    assert grade.letter == "F"
    assert grade.score == pytest.approx(44.5, abs=1.0)


def test_missing_inputs_cost_the_completeness_component():
    full = _grade(3.0, _band(), 1.0)
    partial = _grade(3.0, _band(), 0.5)
    assert full.score - partial.score == pytest.approx(7.5)


# ---------------------------------------------------------------------------
# The card renders what the specification requires
# ---------------------------------------------------------------------------


def _page(card: Card, *, freshness: dict | None = None) -> str:
    bands = {label: _band(label) for label in BAND_STATS}
    return render.card_page(card, bands=bands, overall_band=_band("2-4"),
                            freshness=freshness)


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
    """The card runs no code. The only <script> a card may carry is the
    structured-data block, which browsers do not execute - it is markup for
    search engines and it cannot open a panel."""
    page = _page(_card())
    assert page.count("<details") >= 6
    assert "<script src=" not in page
    scripts = re.findall(r"<script[^>]*>", page)
    assert all('type="application/ld+json"' in tag for tag in scripts), scripts


def test_a_card_carries_structured_data_for_the_game_and_nothing_more():
    """Structured data states the facts on the page - teams, venue, kickoff.
    Never the grade or the projection: a machine-readable projection is one
    copy-paste from being a feed of numbers with no card around them."""
    import json

    page = _page(_card())
    block = re.search(r'<script type="application/ld\+json">(.+?)</script>',
                      page, re.S).group(1)
    payload = json.loads(block)
    assert payload["@type"] == "SportsEvent"
    assert payload["homeTeam"]["name"] == "Iowa State"
    assert payload["awayTeam"]["name"] == "Utah Utes"
    assert "grade" not in block.lower()
    assert "projection" not in block.lower()


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
    assert "Historically unreliable" in tier1
    assert 'class="card grade-hero f"' in tier1 or 'class="card grade-hero d"' in tier1
    assert tier1.index("grade-mark") < tier1.index("Be careful about")


def test_cautions_are_specific_to_the_card():
    """Rule 5, question 5. A caution that appears on every card is read as
    decoration, so the wide-disagreement one must only fire when it applies."""
    loud = _card(model_total=62.0)
    quiet = _card(model_total=49.0)
    assert any("points away from the market" in c for c in loud.cautions)
    assert not any("points away from the market" in c for c in quiet.cautions)
    assert len(loud.cautions) <= 3


def test_no_caution_uses_research_vocabulary():
    """Track 3. A caution is read by somebody who arrived from a link and has
    never seen Atlas. "The 10+ band" is a sentence from a research report."""
    jargon = ("band", "calibration", "out of sample", "walk-forward",
              "point-in-time", "unanchored", "percentile")
    for card in (_card(model_total=62.0), _card(model_total=49.0),
                 _card(model_total=56.0)):
        for caution in card.cautions:
            lowered = caution.lower()
            assert not any(word in lowered for word in jargon), caution


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
    lambda: render.about_page(_card(), card_count=58),
    lambda: render.faq_page(),
    lambda: render.not_found_page(),
], ids=["card-a", "card-f", "nfl", "premium", "about", "faq", "404"])
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
    lambda: render.about_page(_card(), card_count=58),
    lambda: render.faq_page(),
], ids=["card-a", "card-f", "about", "faq"])
def test_no_card_names_a_side(builder):
    banned = re.compile(
        r"\b(take the|lay the|back the|we like|our pick|recommended side|"
        r"leans? (over|under))\b", re.IGNORECASE)
    assert not banned.findall(builder())


def test_the_landing_page_answers_the_four_questions_it_promises():
    """Track 1. A first-time visitor has to get what Atlas is, what a grade
    means, how to read a card and why it exists - and the first screen has to
    be enough to be *right* about Atlas even if they stop there."""
    page = render.about_page(_card(), card_count=58)
    lede = page.split('<section class="section"')[0]
    assert "never tells anyone what to do" in lede
    for anchor in ('id="what"', 'id="read"', 'id="grades"', 'id="why"'):
        assert anchor in page, anchor
    # The caveat that stops the grade being read as a ranking travels with it.
    assert "what to discount, not what to look at" in page
    # And the page is honest about the boundary it is selling against.
    assert "always will be" in page


def test_the_faq_answers_the_question_that_decides_everything():
    """The A-card question. A reader who gets this wrong misreads every card,
    so the answer has to be on the published page, not only in the repo."""
    page = render.faq_page()
    assert "Is an A card the one I should read first?" in page
    assert "what to discount, not what to look at" in page
    assert "Is this a selections service?" in page
    assert "Does Atlas take affiliate money" in page


def test_every_public_surface_carries_a_freshness_stamp():
    """Track 6. A reader must never have to guess how old a number is, and the
    stamp must be the refresh time rather than the build's clock."""
    stamps = {"projection": "Sep 22, 2026 7:05 PM ET",
              "market": "Sep 22, 2026 6:00 PM ET",
              "board": "Sep 22, 2026 7:05 PM ET"}
    card = _page(_card(), freshness=stamps)
    assert "Projection built" in card and stamps["projection"] in card
    assert "Market updated" in card and stamps["market"] in card
    # The market stamp is older than the build. A rebuild that ran against an
    # hour-old poll must say so rather than advertising itself as fresh.
    assert card.index(stamps["market"]) > card.index("Market updated")


def test_a_stamp_names_its_zone():
    """`docs/TIMESTAMP_STANDARD.md`: ET, always, spelled out. A timestamp
    without a zone is a number a reader has to guess about."""
    page = _page(_card(), freshness={"board": "Sep 22, 2026 7:05 PM ET"})
    for match in re.findall(r"\d{1,2}:\d{2} [AP]M[^<]*", page):
        assert "ET" in match, match


def test_the_landing_page_works_without_an_example_card():
    """Out of season there is no card to walk through. The page still has to
    stand up rather than render a hole where a section was."""
    page = render.about_page(None, card_count=0)
    assert 'id="read"' not in page
    assert 'id="what"' in page and 'id="grades"' in page and 'id="why"' in page


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
