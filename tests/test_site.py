"""The Atlas site build.

Two kinds of test. Most check that a page says what the specification says it
must. The last group checks the thing the whole product rests on: no page
tells a reader what to do, and the grade is computed rather than chosen.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from atlas.site import data, render, social
from atlas.site import drivers as driving
from atlas.site import grade as grading
from atlas.site.data import Card, Line, Side
from atlas.site.html import possessive

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


def _projection(margin_mean: float, total_mean: float) -> data.Projection:
    """A projection with the grid's numbers derived the way the model's would be."""
    return data.Projection(
        margin_mean=margin_mean, margin_sd=16.2, total_mean=total_mean, total_sd=16.0,
        home_mean=(total_mean + margin_mean) / 2, away_mean=(total_mean - margin_mean) / 2,
        p_home=0.5 + margin_mean / 60.0, total_lo=total_mean - 20, total_hi=total_mean + 20,
        top_home=round((total_mean + margin_mean) / 2), top_away=round((total_mean - margin_mean) / 2),
        top_p=0.003, hfa=2.5, pace_adj=-0.4, wind_adj=-0.2,
        home={"off": 6.1, "def": 3.2, "net": 9.3, "sd_off": 4.0, "sd_def": 4.1, "rank": 21, "games": 4},
        away={"off": 2.0, "def": -1.5, "net": 0.5, "sd_off": 4.2, "sd_def": 4.3, "rank": 60, "games": 4},
        teams=136, version="test", refreshed_at="2026-09-21T09:00:00+00:00",
    )


def _card(*, model_margin=-5.5, model_total=50.7, market_total=48.5, grade=True) -> Card:
    """The market has the away side by 7.5 (a home margin of -7.5);
    ``model_margin`` is the model's own home margin, so the default sits two
    points from the market."""
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
        books=1, projection=_projection(model_margin, model_total), grade=None,
    )
    if grade:
        difference = card.margin_difference
        card.grade = _grade(difference, week=card.week,
                            movement=card.spread.movement)
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
    assert "Most likely score" in page
    assert "A difference is not an edge" in page
    assert "Calibration by disagreement band" in page


def test_the_panels_are_native_and_need_no_javascript():
    """The card's panels run no code: they are native <details>. The one script
    a card loads is the deferred Follow script, and the Follow button is
    hidden until it runs, so without it the card loses nothing it shows."""
    page = _page(_card())
    assert page.count("<details") >= 6
    scripts = re.findall(r'<script src="([^"]+)"([^>]*)>', page)
    assert [(src.split("?")[0], rest.strip()) for src, rest in scripts] == [("../assets/games.js", "defer")]
    assert re.search(r'<button class="follow"[^>]* hidden ', page)
    inline = [tag for tag in re.findall(r"<script[^>]*>", page) if "src=" not in tag]
    assert all('type="application/ld+json"' in tag or 'type="application/json"' in tag for tag in inline), inline


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


def test_the_projection_is_the_models_own_number_to_one_decimal():
    """The product rule: Atlas's number is the model's number, never a blend
    with the market, and the headline is the distribution's mean to one
    decimal - 22.6–28.1, never 23–28."""
    card = _card(model_margin=-5.5, model_total=50.7, market_total=48.5)
    page = _page(card)
    tier1 = page.split('<div class="tier2">')[0]
    assert card.model_total == 50.7 and card.model_margin == -5.5
    assert card.projected_home == pytest.approx(22.6) and card.projected_away == pytest.approx(28.1)
    assert "28.1–22.6" in tier1
    assert "50.7" in tier1
    assert "48.5" in tier1                                  # the market, beside it
    assert card.margin_difference == pytest.approx(2.0)     # market has the away side by 7.5
    assert "Most likely score" in page


def test_over_probability_is_read_given_the_line():
    """With the line-given fit on the projection, the card's P(over) keeps
    only the real share of the model's gap; without it, the total's own sd."""
    card = _card(model_total=56.5, market_total=48.5)
    alone = card.over_probability
    assert alone == pytest.approx(stats.norm.sf((48.5 - 56.5) / 16.0))
    card.projection.over_shrink, card.projection.over_sd = 0.2, 16.5
    assert card.over_probability == pytest.approx(stats.norm.sf(-0.2 * 8.0 / 16.5))
    assert 0.5 < card.over_probability < alone
    card.projection.over_shrink = 0.0
    assert card.over_probability == pytest.approx(0.5)


def test_the_market_is_shown_first_with_its_open_and_move():
    """Market open, move and now come before Atlas's number, and the market
    never changes the number."""
    card = _card()
    page = _page(card)
    tier1 = page.split('<div class="tier2">')[0]
    answer = tier1[tier1.index('class="answer"'):]      # past the page's own <head>
    assert answer.index(">Market<") < answer.index("Atlas projects")
    assert "spread opened" in answer and "moved +4.0" in answer
    moved = _card()
    moved.spread = Line("margin", -11.5, -3.5, -110.0, -105.0)
    assert moved.model_margin == card.model_margin
    assert moved.projected_home == card.projected_home


def test_the_grade_is_computed_on_the_spread():
    """The headline is the score and the spread is the market that prices it,
    so the grade's disagreement is on the margin, not the total."""
    close = _card(model_margin=-7.0, model_total=70.0)     # far on the total, close on the spread
    far = _card(model_margin=4.0, model_total=48.5)        # the reverse
    assert close.grade.disagreement == pytest.approx(0.5)
    assert far.grade.disagreement == pytest.approx(11.5)
    assert far.grade.score < close.grade.score


def test_a_low_grade_card_leads_with_its_low_confidence():
    """Rule 4: the grade is the centrepiece, and on a weak card it has to be
    the first thing a reader takes in."""
    card = _card(model_margin=4.0)
    assert card.grade.low
    page = _page(card)
    tier1 = page.split('<div class="tier2">')[0]
    assert "Historically unreliable" in tier1
    assert 'class="card grade-hero f"' in tier1 or 'class="card grade-hero d"' in tier1
    assert tier1.index("grade-mark") < tier1.index("Be careful about")


def test_cautions_are_specific_to_the_card():
    """Rule 5, question 5. A caution that appears on every card is read as
    decoration, so the wide-disagreement one must only fire when it applies."""
    loud = _card(model_margin=7.5)
    quiet = _card(model_margin=-7.0)
    assert any("points away from the market" in c for c in loud.cautions)
    assert not any("points away from the market" in c for c in quiet.cautions)
    assert len(loud.cautions) <= 3


def test_no_caution_uses_research_vocabulary():
    """Track 3. A caution is read by somebody who arrived from a link and has
    never seen Atlas. "The 10+ band" is a sentence from a research report."""
    jargon = ("band", "calibration", "out of sample", "walk-forward",
              "point-in-time", "unanchored", "percentile")
    for card in (_card(model_margin=7.5), _card(model_margin=0.5),
                 _card(model_margin=-5.5)):
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
    lambda: _page(_card(model_margin=4.0)),
    lambda: render.nfl_page(),
    lambda: render.board_page([_card(), _card(model_margin=4.0)], sport="ncaaf"),
    lambda: render.homepage([_card()], [_nfl_card()]),
    lambda: render.premium_page(),
    lambda: render.about_page(_card(), card_count=58),
    lambda: render.faq_page(),
    lambda: render.not_found_page(),
], ids=["card-a", "card-f", "nfl", "ncaaf-board", "home", "premium", "about", "faq", "404"])
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
    lambda: _page(_card(model_margin=4.0)),
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


def test_the_grade_is_labeled_as_information_quality():
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


# ---------------------------------------------------------------------------
# The NFL card and board (NFL plan step 6)
# ---------------------------------------------------------------------------


def _nfl_card(**kw) -> Card:
    card = _card(**kw)
    card.sport = "nfl"
    card.home = _side("home", "Buffalo Bills", "#00338D")
    card.away = _side("away", "Kansas City Chiefs", "#E31837")
    card.home.conference, card.away.conference = None, None
    card.drivers = driving.select(card, _POOL)
    card.cautions = data.cautions(card)
    return card


def test_an_nfl_card_lives_under_nfl_and_links_its_team_pages():
    """Same card, a different sport: it publishes under nfl/, its structured
    data points each team at its NFL team page, and every word of the card is
    the same audited copy."""
    import json

    card = _nfl_card()
    assert card.path.startswith("nfl/") and card.path.endswith(".html")
    page = _page(card)
    block = re.search(r'<script type="application/ld\+json">(.+?)</script>', page, re.S).group(1)
    payload = json.loads(block)
    assert "NFL" in payload["description"]
    assert [team["url"].split("/", 3)[-1] for team in payload["competitor"]] == [
        "nfl/team/kansas-city-chiefs.html", "nfl/team/buffalo-bills.html"]
    assert 'href="../nfl.html" aria-current="page"' in page
    assert "Atlas projects" in page and "not a recommendation" in page.lower()


def test_the_nfl_board_has_the_college_layout_and_says_so_when_empty():
    """One layout for both sports: the same head, filter bar, featured row,
    next kickoffs and grade blocks - and no conference filter where there are
    no conferences."""
    cards = [_nfl_card(), _nfl_card(model_margin=4.0)]
    board = render.nfl_page(cards, freshness={"projection": "x", "market": "y"})
    college = render.board_page([_card(), _card(model_margin=4.0)], sport="ncaaf")
    for page in (board, college):
        for piece in ('class="board-head"', 'class="board-bar"', "<h2>Featured</h2>", "<h2>Next kickoffs</h2>",
                      'class="featured"', "assets/atlas.js"):
            assert piece in page, piece
    assert "<h1>NFL</h1>" in board and "<h1>College football</h1>" in college
    assert 'id="conf"' not in board and 'id="conf"' in college
    assert 'href="nfl/' in board and 'href="../nfl.html"' not in board
    assert 'href="nfl.html" aria-current="page"' in board and 'href="ncaaf.html" aria-current="page"' in college
    empty = render.nfl_page([], bands={}, freshness=None)
    assert "No NFL games are scheduled" in empty
    for page in (board, empty):
        text = _visible_text(page)
        assert not any(re.search(rf"\b{w}\b", text) for w in FORBIDDEN if w not in ("unit", "units")), page[:200]


def _nfl_team_card():
    card = _nfl_card()
    card.home.team_id, card.away.team_id = 2, 12
    card.projection.home.update({"off": 3.2, "def": 1.1, "net": 4.3, "sd_off": 1.6, "sd_def": 1.5, "rank": 3,
                                 "games": 2, "qb": "J.Allen", "qb_pts": 4.4, "qb_sd": 1.7})
    card.projection.teams = 32
    return card


def test_an_nfl_team_page_shows_the_rating_the_quarterback_and_the_record():
    """The rating and quarterback come from the team's next card; the record is
    what Atlas published before kickoff beside the final; every word is audited."""
    from datetime import UTC, datetime

    from atlas.site.data import Result

    card = _nfl_team_card()
    results = [Result(kickoff=datetime(2026, 9, 14, 17, tzinfo=UTC), opponent="Jets", home=True,
                      atlas=6.5, market=4.5, final=10.0),
               Result(kickoff=datetime(2026, 9, 7, 17, tzinfo=UTC), opponent="Dolphins", home=False,
                      atlas=-1.0, market=2.0, final=3.0)]
    page = render.nfl_team_page(card.home, cards=[card], pool=_POOL, results=results,
                                freshness={"projection": "x", "market": "y"})
    text = _visible_text(page)
    # The offense is the forecast's: the team's own plus its expected starter's.
    assert "+7.6" in page and "team +3.2 · J.Allen +4.4" in page and "+8.7" in page
    assert "1st of 2 with a card this week" in text and "buffalo&#x27;s margin" in text
    assert possessive("Bills") == "Bills'" and possessive("Buffalo") == "Buffalo's"
    assert page.count("<tr>") >= 3 and "Closer" in page and "Atlas missed the final margin by 3.8" in page
    assert 'href="../../nfl/' in page and 'href="../../nfl.html" aria-current="page"' in page
    assert 'rel="canonical"' in page and "nfl/team/buffalo-bills.html" in page
    assert "not a recommendation" in text and 'class="freshness"' in page
    assert not any(re.search(rf"\b{w}\b", text) for w in FORBIDDEN if w not in ("unit", "units")), text[:300]
    empty = render.nfl_team_page(card.home, cards=[card], pool=_POOL, results=[])
    assert "No completed game this season" in empty


def test_the_nfl_board_links_every_team_page():
    card = _nfl_team_card()
    board = render.nfl_page([card], bands={}, freshness=None,
                            teams={"buffalo-bills": card.home, "kansas-city-chiefs": card.away})
    assert 'href="nfl/team/buffalo-bills.html"' in board and 'href="nfl/team/kansas-city-chiefs.html"' in board


def test_team_results_keep_only_projections_published_before_kickoff():
    from atlas.site.data import team_results

    card = _nfl_team_card()
    card.season = 2026
    frame = pd.DataFrame({
        "espn_id": [card.game_id, 900], "season": [2026, 2026], "home_team_id": [4, 4], "away_team_id": [16, 20],
        "home_team": ["BUF", "BUF"], "away_team": ["KC", "NYJ"], "kickoff": [card.kickoff, "2026-09-14T17:00:00Z"],
        "actual_margin": [np.nan, 7.0], "closing_spread": [np.nan, -4.5]})
    projections = pd.DataFrame({
        "game_id": [900, 900, 900], "sport": "nfl", "home_team_id": 4, "away_team_id": 20,
        "margin_mean": [5.0, 6.0, 9.9],
        "refreshed_at": ["2026-09-12T08:00:00Z", "2026-09-13T08:00:00Z", "2026-09-15T08:00:00Z"]})
    out = team_results([card], frame, projections)
    assert list(out) == [card.home.team_id]                     # the Jets have no card, so no page
    r = out[card.home.team_id][0]
    assert r.atlas == 6.0 and r.market == 4.5 and r.final == 7.0 and r.opponent == "NYJ" and r.home
    assert team_results([card], frame, projections.iloc[2:]) == {}   # published after kickoff: not a forecast


def test_an_ungraded_card_still_carries_the_disclaimer_and_says_why():
    """The launch audit blocks a card without the disclaimer; a game no book has
    priced yet is ungraded, and must not fail the deploy or blame history."""
    card = _nfl_card()
    card.grade = None
    card.spread = Line("margin", None, None, None, None)
    text = _visible_text(_page(card))
    assert "not a recommendation" in text and "no market is posted yet" in text


def test_the_nfl_offense_driver_includes_the_expected_quarterback():
    """The forecast adds each side's quarterback to its offense; the driver must compare the same thing."""
    card = _nfl_team_card()
    card.projection.away.update({"off": 3.0, "def": 0.0, "qb_pts": -2.0})
    offense = next(d for d in driving._model_drivers(card) if d[1].name.startswith("Offense"))
    assert offense[0] == pytest.approx((3.2 + 4.4) - (3.0 - 2.0))
    assert "with its expected quarterback" in offense[1].sentence and "the NFL average" in offense[1].sentence


def test_team_win_loss_counts_this_seasons_regular_season_results():
    from atlas.site.data import team_win_loss

    card = _nfl_team_card()
    card.season = 2026
    frame = pd.DataFrame({
        "espn_id": [card.game_id, 900, 901, 902], "season": [2026, 2026, 2026, 2025],
        "season_type": ["regular"] * 4, "home_team_id": [4, 4, 16, 4], "away_team_id": [16, 20, 4, 20],
        "actual_margin": [np.nan, 7.0, 3.0, -10.0]})
    assert team_win_loss([card], frame) == {card.home.team_id: "1-1", card.away.team_id: "1-0"}


def test_the_home_page_features_the_best_matchups_in_each_sport():
    """Three from each board, chosen the way each board chooses its featured
    row, with the way to every game in that sport under them."""
    college = [_card() for _ in range(5)]
    college[3].home.rank = 4
    college[3].away.rank = 9
    nfl = [_nfl_team_card(), _nfl_card(), _nfl_card(model_margin=4.0), _nfl_card()]
    nfl[0].projection.away = {"off": 5.0, "def": 4.0}          # the two best-rated teams meet here
    home = render.homepage(college, nfl, freshness={"board": "x"})
    assert "<h2>College football</h2>" in home and "<h2>NFL</h2>" in home
    assert home.count('class="card card-pad feature"') == 6
    assert 'href="ncaaf.html">All 5 college games this week' in home
    assert 'href="nfl.html">All 4 NFL games this week' in home
    assert render.featured_cards(college, "ncaaf")[0] is college[3]          # the ranked matchup leads
    assert render.featured_cards(nfl, "nfl")[0] is nfl[0]                   # the best-rated teams lead
    assert 'href="index.html" aria-current="page">Home' in home
    assert "Atlas projects" in home and home.count('class="feature-score"') == 6
    empty = render.homepage([_card()], [])
    assert "No NFL games are scheduled in the next week" in empty


def test_the_nav_names_both_sports():
    page = render.layout(title="t", body="", depth=1, active="nfl")
    assert 'href="../ncaaf.html">NCAAF' in page and 'href="../nfl.html" aria-current="page">NFL' in page
    assert 'class="logo" href="../index.html"' in page and 'href="../index.html">Home' in page


def test_a_featured_tile_shows_the_projected_score_away_first():
    card = _card()
    tile = render._featured_cell(card)
    assert "Atlas projects" in tile
    away, home = f"{card.projected_away:.1f}", f"{card.projected_home:.1f}"
    assert tile.index(f"{card.away.abbr} {away}") < tile.index(f"{card.home.abbr} {home}")
    card.projection = None
    assert "Atlas projects" not in render._featured_cell(card)


def test_a_board_offers_every_game_as_a_tile_and_as_a_row():
    """Tiles/List: each graded game is a row and a tile under its grade, both
    carrying what the filters read; featured tiles are not filtered; the
    switch sits in the filter bar."""
    cards = [_card(), _card(model_margin=4.0), _card(model_margin=-12.0)]
    for i, card in enumerate(cards):
        card.game_id = 100 + i
    board = render.board_page(cards, sport="ncaaf")
    graded = sum(1 for c in cards if c.grade)
    assert board.count('class="card card-pad feature game-tile"') >= graded
    # A view is one kind of thing: every list on the board has its tiles, so
    # the Tiles view never mixes rows in among the tiles.
    assert 'class="card game-list"' not in board
    assert board.count('class="card game-list view-list"') == board.count('class="featured view-tiles"') >= 2
    for card in cards:
        if card.grade:
            assert board.count(f'data-game="{card.game_id}"') >= 2          # a row and a tile, at least
    featured = re.search(r"<h2>Featured</h2>.*?</section>", board, re.S).group(0)
    assert "data-game" not in featured
    assert 'class="view-btn" data-view="tiles"' in board and 'class="view-btn" data-view="list"' in board
    assert 'localStorage.getItem("atlas-view")' in board
    assert "view-btn" not in render.homepage([_card()], [_nfl_card()])


def test_tiles_say_they_open_the_full_card_and_assets_are_versioned():
    """Every tile carries a Details chip; the stylesheet and script are linked
    by a content hash, so a deploy never pairs new pages with a cached old
    stylesheet."""
    tile = render._featured_cell(_card())
    assert 'class="details-chip"' in tile and tile.startswith('<article class="card card-pad feature"')
    assert f'<a class="stretch" href="{_card().path}">' in tile
    board = render.board_page([_card()], sport="ncaaf")
    assert re.search(r'href="assets/atlas\.css\?v=[0-9a-f]{10}"', board)
    assert re.search(r'src="assets/atlas\.js\?v=[0-9a-f]{10}"', board)
    deep = render.layout(title="t", body="", depth=2)
    assert re.search(r'href="\.\./\.\./assets/atlas\.css\?v=[0-9a-f]{10}"', deep)


def test_a_game_says_it_has_started_once_it_kicks_off():
    """The tile, the row and the card each carry a hidden "Game started" chip
    with the kickoff, for games.js to show at kickoff; never the word a tout
    would use."""
    card = _card()
    card.game_id = 900
    kickoff = f'data-kickoff="{card.kickoff.isoformat()}" hidden'
    chip = re.compile(r'<span class="started-chip" ([^>]*)>Game started</span>')
    tile, row, page = render._featured_cell(card), render._game_row(card), _page(card)
    for html in (tile, row, page):
        found = chip.findall(html)
        assert len(found) == 1 and found[0].startswith(kickoff), html[:200]
    hero = re.search(r'<div class="hero-meta-row">.*?</div>', page, re.S).group(0)
    assert "started-chip" in hero
    board = render.board_page([card], sport="ncaaf")
    # Every row and tile, and the featured tile, which the filters leave alone.
    assert board.count('class="started-chip"') == board.count('data-game="900"') + 1
    assert "lock" not in chip.search(page).group(0).lower()


def test_a_stadium_name_is_not_vocabulary(tmp_path):
    """Kelly/Shorts Stadium is Central Michigan's. The launch audit blocks the
    whole deploy on a forbidden word, so a venue must read as a name, as a
    player's does - the day its first game reached the board, every poll
    failed the audit. Run the real audit over the page, context rules and all."""
    from scripts.audit_site import audit

    card = _card()
    card.venue = "Kelly/Shorts Stadium"
    page = _page(card)
    assert '<span class="pn">Kelly/Shorts Stadium</span>' in page
    (tmp_path / "ncaaf").mkdir()
    (tmp_path / "ncaaf" / "card.html").write_text(page)
    blocking, _ = audit(tmp_path)
    assert blocking["forbidden vocabulary"] == []
    # Still escaped: a venue is data from a provider.
    card.venue = "<b>Field</b>"
    assert '<span class="pn">&lt;b&gt;Field&lt;/b&gt;</span>' in _page(card)


def test_every_game_can_be_followed_and_carries_its_details():
    """Follow buttons on tiles, rows and the card, each backed by the page's
    game data; the scoreboard page lists no games of its own and says where
    the list lives."""
    import json

    cards = [_card(), _card(model_margin=4.0)]
    for i, card in enumerate(cards):
        card.game_id = 700 + i
    board = render.board_page(cards, sport="ncaaf")
    blob = json.loads(re.search(r'<script type="application/json" id="atlas-games">(.+?)</script>', board).group(1))
    assert set(blob) == {"700", "701"}
    record = blob["700"]
    assert record["path"] == cards[0].path and record["date"].isdigit() and len(record["date"]) == 8
    # Who, when and where - never Atlas's numbers or the market's.
    assert set(record) == {"id", "sport", "title", "kickoff", "date", "when", "path", "away", "home"}
    assert board.count('data-follow="700"') >= 2                       # its row and its tile
    assert '<button class="follow compact"' in board                   # the row's star
    assert "<a class=\"game-row\"" not in board                       # rows are containers now
    home = render.homepage(cards, [])
    assert 'data-follow="700"' in home and 'id="atlas-games"' in home
    sb = render.scoreboard_page()
    assert 'id="scoreboard"' in sb and 'id="scores-empty"' in sb and "Saved on this device" in sb
    assert 'id="atlas-games"' not in sb
    assert 'href="scoreboard.html" aria-current="page">Scores' in sb
    text = _visible_text(sb)
    assert not any(re.search(rf"\b{w}\b", text) for w in FORBIDDEN if w not in ("unit", "units")), text[:300]
