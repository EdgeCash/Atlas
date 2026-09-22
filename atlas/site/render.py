"""Rendering the approved design into pages.

Nothing here invents design. The tokens, components, type scale and chart
rules come from `docs/UI_SYSTEM.md`; the eight sections and their order come
from `docs/ATLAS_CARD_SPEC.md`; the voice and the forbidden vocabulary come
from `docs/BRAND_GUIDE.md`.
"""

from __future__ import annotations

from atlas.site.data import MARKET_WEIGHT, Card
from atlas.site.html import (
    clock,
    day_and_clock,
    day_clock,
    eastern,
    esc,
    minus,
    num,
    pct,
    price,
    signed,
    table,
)
from atlas.util import get_logger

LOG = get_logger(__name__)

TAGLINE = "Research. Analytics. Context."

#: The sentence that appears on every card, unchanged.
CARD_DISCLOSURE = (
    "<b>What this card is.</b> Research, analytics and market context. Atlas "
    "does not publish selections, does not size anything and does not project "
    "returns. Every figure is computed out of sample from a point-in-time "
    "database: nothing attached to a game uses information that did not exist "
    "before kickoff."
)

#: Two accents closer than this read as the same colour, so the away team
#: falls back to slate. `docs/UI_SYSTEM.md`, team accent rule 4.
COLLISION = 60.0


def _rgb(hex_colour: str) -> tuple[int, int, int]:
    value = hex_colour.lstrip("#")
    if len(value) != 6:
        return (61, 70, 82)
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _distance(a: str, b: str) -> float:
    ra, ga, ba = _rgb(a)
    rb, gb, bb = _rgb(b)
    return ((ra - rb) ** 2 + (ga - gb) ** 2 + (ba - bb) ** 2) ** 0.5


def accents(card: Card) -> tuple[str, str]:
    """Team accents for the header rule, with the collision rule applied."""
    home, away = card.home.colour, card.away.colour
    if _distance(home, away) < COLLISION:
        away = "#6b7480"
    return home, away


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------


def layout(*, title: str, body: str, depth: int = 0, description: str = "",
           active: str = "", social: str = "") -> str:
    root = "../" * depth
    nav_items = [
        ("Today", f"{root}index.html", "today"),
        ("NCAAF", f"{root}index.html", "ncaaf"),
        ("NFL", f"{root}nfl.html", "nfl"),
        ("Research", f"{root}research.html", "research"),
        ("Premium", f"{root}premium.html", "premium"),
    ]
    current = ' aria-current="page"'
    nav = "".join(
        f'<a href="{href}"{current if key == active else ""}>{esc(label)}</a>'
        for label, href, key in nav_items
    )
    meta_description = description or (
        "Research, analytics and market context for college football. "
        "Atlas does not publish selections."
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="{esc(meta_description)}">
<meta name="color-scheme" content="light dark">
<title>{esc(title)}</title>
<link rel="stylesheet" href="{root}assets/atlas.css">
{social}
</head>
<body>
<a class="skip" href="#main">Skip to content</a>
<nav class="nav">
  <div class="nav-inner">
    <a class="logo" href="{root}index.html">Atlas <span>Sports Intelligence</span></a>
    <div class="nav-links">{nav}</div>
  </div>
</nav>
<main class="wrap" id="main">
{body}
<footer>
  <div><b>Atlas Sports Intelligence</b> · {TAGLINE}</div>
  <div>Out-of-sample figures from a point-in-time database ·
    <a href="{root}research.html">how Atlas works</a> ·
    <a href="{root}research.html#grades">what grades mean</a></div>
  <div class="footer-note">Atlas publishes information. Readers make their own
    decisions.</div>
</footer>
</main>
</body>
</html>
"""


def social_tags(*, title: str, description: str, image: str | None = None) -> str:
    tags = [
        f'<meta property="og:title" content="{esc(title)}">',
        f'<meta property="og:description" content="{esc(description)}">',
        '<meta property="og:type" content="article">',
        '<meta name="twitter:card" content="summary_large_image">',
    ]
    if image:
        tags.append(f'<meta property="og:image" content="{esc(image)}">')
    return "\n".join(tags)


# ---------------------------------------------------------------------------
# Shared pieces
# ---------------------------------------------------------------------------


def grade_pill(card: Card, *, size: str = "") -> str:
    if card.grade is None:
        return '<span class="grade-pill none" title="No grade yet">–</span>'
    cls = f"grade-pill {card.grade.tone} {size}".strip()
    return (f'<span class="{cls}" aria-label="Grade {card.grade.letter}">'
            f"{card.grade.letter}</span>")


def kickoff_line(card: Card) -> str:
    local = eastern(card.kickoff)
    bits = [f'<span><b>{local.strftime("%a %-d %b")}</b> · {clock(card.kickoff)}</span>']
    if card.venue:
        place = card.venue + (f", {card.city}" if card.city else "")
        bits.append(f"<span>{esc(place)}</span>")
    bits.append(f'<span>{"Conference game" if card.conference_game else "Non-conference"}</span>')
    weather = card.weather
    if weather.get("temp") is not None:
        text = f'{weather["temp"]:.0f}°F'
        if weather.get("wind") is not None:
            text += f', {weather["wind"]:.0f} mph wind'
        bits.append(f"<span>{esc(text)}</span>")
    if card.tv:
        bits.append(f"<span><b>{esc(card.tv)}</b></span>")
    return f'<div class="kick">{"".join(bits)}</div>'


def team_block(side, *, align: str) -> str:
    rank = f'<span class="rank">#{side.rank}</span> ' if side.rank else ""
    meta = " · ".join(x for x in [side.conference, side.record] if x)
    return f"""<div class="team {align}">
  <span class="chip"></span>
  <div class="team-name">{rank}{esc(side.short)}</div>
  <div class="team-meta">{esc(meta)}</div>
</div>"""


# ---------------------------------------------------------------------------
# The card — eight sections, in the order the specification fixes
# ---------------------------------------------------------------------------


def card_page(card: Card, *, bands: dict, overall_band) -> str:
    """The card, in three tiers.

    Tier 1 is everything a reader needs in five seconds and is always visible:
    the game, the market, Atlas's number, the difference, the grade and the
    short reason. Tier 2 and 3 are the same information the research build
    always carried, behind native ``<details>`` — no JavaScript, no layout
    shift, and open by keyboard.
    """
    home_accent, away_accent = accents(card)
    body = "\n".join(filter(None, [
        _hero(card, home_accent, away_accent),
        _answer(card),
        _why_brief(card),
        _caution(card),
        '<div class="tier2">',
        _open_market(card),
        _open_projection(card),
        _open_grade(card),
        _open_drivers(card),
        _open_movement(card),
        _open_reliability(card, bands, overall_band),
        "</div>",
        f'<div class="disclosure card-foot">{CARD_DISCLOSURE}</div>',
    ]))
    description = (
        f"{card.title}: market {card.spread_text}, total "
        f"{num(card.total.current)}. Atlas projects {num(card.anchored_total)} "
        f"and grades this card {card.grade.letter if card.grade else 'ungraded'}."
    )
    return layout(
        title=f"{card.title} — Atlas Sports Intelligence",
        body=body, depth=1, description=description, active="ncaaf",
        social=social_tags(title=f"{card.title} · Atlas", description=description),
    )


# ---------------------------------------------------------------------------
# Tier 1 — the five-second view
# ---------------------------------------------------------------------------


def _logo(side, *, size: str = "", root: str = "../") -> str:
    """A logo, or the team's colour as a fallback chip.

    Humans read a mark faster than a name, so the identity is the logo where
    one exists and never a coloured square pretending to be one. ``root`` is
    the path back to the site root, which differs between the board and a
    card; getting it wrong renders a broken-image icon on every row.
    """
    cls = f"crest {size}".strip()
    if side.logo:
        return (f'<img class="{cls}" src="{root}assets/logos/{esc(side.logo)}" '
                f'alt="" width="56" height="56" loading="lazy">')
    return f'<span class="{cls} crest-fallback" aria-hidden="true"></span>'


def _team_column(side, *, align: str) -> str:
    rank = f'<span class="rank">#{side.rank}</span>' if side.rank else ""
    meta = " · ".join(x for x in [side.conference, side.record] if x)
    return f"""<div class="hero-team {align}">
  {_logo(side)}
  <div class="hero-names">
    <div class="hero-name">{rank}{esc(side.short)}</div>
    <div class="hero-meta">{esc(meta)}</div>
  </div>
</div>"""


def _hero(card: Card, home_accent: str, away_accent: str) -> str:
    bits = [day_and_clock(card.kickoff)]
    if card.tv:
        bits.append(card.tv)
    if card.venue:
        bits.append(card.venue)
    return f"""<div class="card hero" style="--team-home:{esc(home_accent)};--team-away:{esc(away_accent)}">
  <div class="hero-teams">
    {_team_column(card.away, align="away")}
    <div class="hero-at">at</div>
    {_team_column(card.home, align="home")}
  </div>
  <div class="hero-meta-row">{esc(" · ".join(bits))}</div>
</div>"""


def _answer(card: Card) -> str:
    """Market, Atlas, difference — and the grade, which dominates."""
    difference = card.total_difference
    grade_block = _grade_hero(card)
    return f"""<div class="answer">
  <div class="card answer-nums">
    <div class="answer-cell">
      <div class="stat-label"><span class="wide-only">Market</span><span class="narrow-only">Mkt</span></div>
      <div class="answer-value">{esc(card.spread_text)}</div>
      <div class="stat-note">total {num(card.total.current)}</div>
    </div>
    <div class="answer-cell">
      <div class="stat-label"><span class="wide-only">Atlas projects</span><span class="narrow-only">Atlas</span></div>
      <div class="answer-value">{_projected_score(card)}</div>
      <div class="stat-note">{esc(card.away.abbr)}–{esc(card.home.abbr)} ·
        total {num(card.anchored_total)}</div>
    </div>
    <div class="answer-cell">
      <div class="stat-label"><span class="wide-only">Difference</span><span class="narrow-only">Diff</span></div>
      <div class="answer-value {_diff_class(difference)}">{signed(difference)}</div>
      <div class="stat-note">on the total</div>
    </div>
  </div>
  {grade_block}
</div>"""


def _projected_score(card: Card) -> str:
    """Away first, as the title reads. The note names both abbreviations,
    because "15-29" on its own is a pair of numbers, not a scoreline."""
    if card.projected_home is None:
        return "—"
    return f"{card.projected_away:.0f}–{card.projected_home:.0f}"


#: Below this the difference is not a disagreement. The 0-1 band is where
#: Atlas and the market are indistinguishable out of sample, so colouring a
#: 0.3-point difference red says "look at this" about nothing.
DIFFERENCE_FLOOR = 1.0


def _diff_class(value: float | None) -> str:
    if value is None or abs(value) < DIFFERENCE_FLOOR:
        return "flat"
    return "move-up" if value > 0 else "move-down"


def _grade_hero(card: Card) -> str:
    """Rule 4: the grade is the centrepiece, not the spread."""
    if card.grade is None:
        return """<div class="card grade-hero none">
  <div class="grade-mark">–</div>
  <div class="grade-words"><div class="grade-title">Not graded</div>
    <p class="grade-line">Not enough history to grade this card.</p></div>
</div>"""
    g = card.grade
    title = {"A+": "Very high confidence", "A": "High confidence",
             "B": "Solid confidence", "C": "Mixed confidence",
             "D": "Low confidence", "F": "Low confidence"}[g.letter]
    return f"""<div class="card grade-hero {g.tone}">
  <div class="grade-mark">{g.letter}<small>{g.score:.0f}<span>/100</span></small></div>
  <div class="grade-words">
    <div class="grade-title">{esc(title)}</div>
    <p class="grade-line">How much weight this card's information deserves —
      not a recommendation.</p>
    <div class="grade-bar"><span style="width:{g.score:.0f}%"></span></div>
  </div>
</div>"""


def _why_brief(card: Card) -> str:
    """Rule 1: the reason, in three lines, before anything expands."""
    if not card.drivers:
        return ""
    def mark(driver) -> str:
        if driver.favours == "home":
            return _logo(card.home, size="tiny")
        if driver.favours == "away":
            return _logo(card.away, size="tiny")
        return '<span class="why-dot" aria-hidden="true"></span>'

    rows = "".join(
        f"""<li class="why-row">
  {mark(d)}
  <span class="why-name">{esc(d.name)}</span>
  <span class="why-val">{esc(d.magnitude)}</span>
</li>"""
        for d in card.drivers[:3]
    )
    return f"""<section class="section tight">
  <div class="section-head"><h2>Why</h2>
    <span class="note">what the model is reading</span></div>
  <ul class="card card-pad why-list">{rows}</ul>
</section>"""


def _caution(card: Card) -> str:
    """Rule 5, question 5: what should make a reader careful."""
    if not card.cautions:
        return ""
    tone = "crit" if card.grade and card.grade.low else "mute"
    items = "".join(f"<li>{esc(text)}</li>" for text in card.cautions)
    return f"""<section class="section tight">
  <div class="section-head"><h2>Be careful about</h2></div>
  <div class="card card-pad caution {tone}">
    <ul class="caution-list">{items}</ul>
  </div>
</section>"""


# ---------------------------------------------------------------------------
# Tier 2 — one tap
# ---------------------------------------------------------------------------


def _panel_card(bare: bool) -> str:
    """Inside a disclosure the panel already draws the border."""
    return "panel-inner" if bare else "card card-pad"


def _panel(summary: str, hint: str, body: str, *, open_: bool = False) -> str:
    return f"""<details class="panel"{" open" if open_ else ""}>
  <summary><span class="panel-title">{esc(summary)}</span>
    <span class="panel-hint">{esc(hint)}</span></summary>
  <div class="panel-body">{body}</div>
</details>"""


def _open_market(card: Card) -> str:
    hint = "open, current, movement, moneyline"
    return _panel("Market detail", hint, _s2_market(card, bare=True))


def _open_projection(card: Card) -> str:
    return _panel("Projection detail",
                  "score, win probability, the unanchored model",
                  _s3_projection(card, bare=True) + _s4_difference(card, bare=True))


def _open_grade(card: Card) -> str:
    return _panel("How this grade was computed",
                  "four components, one hundred points",
                  _s5_grade(card, bare=True))


def _open_drivers(card: Card) -> str:
    return _panel("All drivers", f"{len(card.drivers)} measured, with percentiles",
                  _s6_drivers(card, bare=True))


def _open_movement(card: Card) -> str:
    return _panel("Market movement", "how this number has moved since it opened",
                  _s7_market_intelligence(card, bare=True))


def _open_reliability(card: Card, bands: dict, overall_band) -> str:
    return _panel("Reliability record", "seven seasons, out of sample",
                  _s8_reliability(card, bands, overall_band, bare=True))


def _s2_market(card: Card, *, bare: bool = False) -> str:
    spread, total = card.spread, card.total
    fav, dog = card.favourite, (card.home if card.favourite is card.away else card.away)
    spread_rows = []
    if spread.current is not None:
        spread_rows = [
            [f'<span class="lead">{esc(fav.short)}</span>',
             minus(-abs(spread.open_line) if spread.open_line is not None else None),
             f'<span class="lead">{minus(-abs(spread.current))}</span>',
             _move_cell(spread.movement)],
            [f'<span class="lead">{esc(dog.short)}</span>',
             signed(abs(spread.open_line) if spread.open_line is not None else None),
             f'<span class="lead">{signed(abs(spread.current))}</span>',
             _move_cell(-spread.movement if spread.movement is not None else None)],
            ["Price", price(_int(spread.open_price)), price(_int(spread.price)), '<span class="flat">—</span>'],
        ]
    total_rows = []
    if total.current is not None:
        total_rows = [
            ['<span class="lead">Game total</span>', num(total.open_line),
             f'<span class="lead">{num(total.current)}</span>', _move_cell(total.movement)],
            ["Price (over)", price(_int(total.open_price)), price(_int(total.price)),
             '<span class="flat">—</span>'],
        ]

    ml = card.moneyline
    if ml.get("home_close") or ml.get("away_close"):
        market_prob = card.market_win_probability
        ml_block = f"""<div class="ml">
  <span class="ml-label">Moneyline · {esc(card.away.short)}</span>
  <span class="ml-vals">{price(ml.get("away_open"))} → <b>{price(ml.get("away_close"))}</b></span>
  <span class="ml-label">Moneyline · {esc(card.home.short)}</span>
  <span class="ml-vals">{price(ml.get("home_open"))} → <b>{price(ml.get("home_close"))}</b></span>
  <span class="ml-sub">De-vigged, the market gives {esc(card.home.short)} a
    {pct(market_prob)} chance. Books quoting: {card.books}.</span>
</div>"""
    else:
        ml_block = """<div class="ml">
  <span class="ml-label">Moneyline</span>
  <span class="ml-vals flat">not posted</span>
  <span class="ml-sub">No book prices a moneyline on this game. Atlas leaves
    the field empty rather than deriving one from the spread.</span>
</div>"""

    left = (table(["Spread", "Open", "Current", "Move"], spread_rows)
            if spread_rows else '<p class="note">No spread posted.</p>')
    right = (table(["Total", "Open", "Current", "Move"], total_rows)
             if total_rows else '<p class="note">No total posted.</p>')

    inner = f"""<div class="grid-2">
    <div class="{_panel_card(bare)}">{left}
      <p class="note top-gap">{_movement_sentence(card)}</p></div>
    <div class="{_panel_card(bare)}">{right}{ml_block}</div>
  </div>"""
    if bare:
        return inner + f'<p class="note top-gap">{esc(_book_label(card))}</p>'
    return f"""<section class="section">
  <div class="section-head"><h2>Market snapshot</h2>
    <span class="note">{esc(_book_label(card))}</span></div>
  {inner}
</section>"""


def _int(value: float | None) -> str | None:
    return None if value is None else f"{value:.0f}"


def _book_label(card: Card) -> str:
    if not card.books:
        return "no market posted"
    return f"DraftKings · {card.books} book{'s' if card.books != 1 else ''} quoting"


def _move_cell(movement: float | None) -> str:
    if movement is None or abs(movement) < 1e-9:
        return '<span class="flat">unchanged</span>'
    cls = "move-up" if movement > 0 else "move-down"
    return f'<span class="{cls}">{signed(movement)}</span>'


def _movement_sentence(card: Card) -> str:
    spread, total = card.spread, card.total
    parts = []
    if spread.movement:
        toward = card.home.short if spread.movement > 0 else card.away.short
        parts.append(f"The spread has moved {abs(spread.movement):.1f} toward {esc(toward)}")
    if total.movement:
        parts.append(f"the total has moved {abs(total.movement):.1f} "
                     f"{'up' if total.movement > 0 else 'down'}")
    if not parts:
        return "Neither number has moved since it opened."
    return " and ".join(parts) + " since the open."


def _s3_projection(card: Card, *, bare: bool = False) -> str:
    if card.anchored_total is None and card.anchored_margin is None:
        return ""
    fav = card.favourite
    score = ("—" if card.projected_home is None else
             f"{card.projected_away:.0f} – {card.projected_home:.0f}")
    over = card.over_probability
    over_label = "Over probability" if (over or 0) >= 0.5 else "Under probability"
    over_value = over if (over or 0) >= 0.5 else (None if over is None else 1 - over)
    win = card.home_win_probability
    win_side, win_value = (card.home, win)
    if win is not None and win < 0.5:
        win_side, win_value = card.away, 1 - win

    inner = f"""<div class="{_panel_card(bare)}">
    <div class="grid-3">
      <div class="stat"><div class="stat-label">Projected score</div>
        <div class="stat-value">{score}</div>
        <div class="stat-note">{esc(card.away.short)} – {esc(card.home.short)}</div></div>
      <div class="stat"><div class="stat-label">Projected spread</div>
        <div class="stat-value">{esc(fav.abbr)} {minus(-abs(card.anchored_margin)) if card.anchored_margin is not None else "—"}</div>
        <div class="stat-note">market {minus(-abs(card.spread.current)) if card.spread.current is not None else "—"}</div></div>
      <div class="stat"><div class="stat-label">Projected total</div>
        <div class="stat-value">{num(card.anchored_total)}</div>
        <div class="stat-note">market {num(card.total.current)}</div></div>
    </div>
    <div class="grid-3 divided">
      <div class="stat"><div class="stat-label">{esc(win_side.short)} win probability</div>
        <div class="stat-value">{pct(win_value)}</div>
        <div class="stat-note">from the projected margin</div></div>
      <div class="stat"><div class="stat-label">{over_label}</div>
        <div class="stat-value">{pct(over_value)}</div>
        <div class="stat-note">at the current total of {num(card.total.current)}</div></div>
      <div class="stat"><div class="stat-label">Unanchored model</div>
        <div class="stat-value">{num(card.model_total)}</div>
        <div class="stat-note">total, before market anchoring</div></div>
    </div>
  </div>
  <div class="disclosure top-gap">
    <b>Why the projection sits close to the market.</b> Atlas weights the
    market at <b>{MARKET_WEIGHT["total"]:.2f}</b> on totals and
    <b>{MARKET_WEIGHT["margin"]:.2f}</b> on spreads. Those weights were fitted,
    not chosen: across 5,778 games the model's own contribution to a spread was
    statistically indistinguishable from zero. A projection that ignored the
    market would be less accurate, and Atlas publishes the accurate one.
  </div>"""
    if bare:
        return inner
    return f"""<section class="section">
  <div class="section-head"><h2>Atlas projection</h2>
    <span class="note">market-anchored · out-of-sample model</span></div>
  {inner}
</section>"""


def _s4_difference(card: Card, *, bare: bool = False) -> str:
    if card.total_difference is None and card.margin_difference is None:
        return ""
    model_prob = card.model_win_probability
    market_prob = card.market_win_probability
    prob_gap = (None if model_prob is None or market_prob is None
                else (model_prob - market_prob) * 100)
    rows_ = [
        ['<span class="lead">Spread</span>',
         f"{esc(card.favourite.abbr)} {minus(-abs(card.model_margin)) if card.model_margin is not None else '—'}",
         f"{esc(card.favourite.abbr)} {minus(-abs(card.spread.current)) if card.spread.current is not None else '—'}",
         _diff_cell(card.margin_difference)],
        ['<span class="lead">Total</span>', num(card.model_total),
         num(card.total.current), _diff_cell(card.total_difference)],
        [f'<span class="lead">{esc(card.home.short)} win probability</span>',
         pct(model_prob), pct(market_prob) if market_prob else "not posted",
         _diff_cell(prob_gap, unit=" pts") if prob_gap is not None else '<span class="flat">—</span>'],
    ]
    band = card.grade.band if card.grade else None
    detail = (
        f"This game sits in the <b>{esc(band.label)}</b> band, where cards have "
        f"claimed {pct(band.claimed, 0)} accuracy and delivered "
        f"{pct(band.realised, 0)} across {band.games:,} games."
        if band else "No band statistics are available for this card."
    )
    inner = f"""<div class="{_panel_card(bare)}">
    <h3 class="top-gap">Atlas difference</h3>
    {table(["Measure", "Atlas model (unanchored)", "Market", "Difference"], rows_)}
    <div class="disclosure top-gap">
      <b>A difference is not an edge.</b> Atlas has measured what happens at
      every size of disagreement, and the gap between what the model claims and
      what it delivers widens as the disagreement grows. {detail}
    </div>
  </div>"""
    if bare:
        return inner
    return f"""<section class="section">
  <div class="section-head"><h2>Atlas difference</h2>
    <span class="note">model minus market, before anchoring</span></div>
  {inner}
</section>"""


def _diff_cell(value: float | None, unit: str = "") -> str:
    if value is None:
        return '<span class="flat">—</span>'
    if abs(value) < 0.05:
        return f'<span class="flat">{signed(value)}{unit}</span>'
    cls = "move-up" if value > 0 else "move-down"
    return f'<span class="{cls}">{signed(value)}{unit}</span>'


def _s5_grade(card: Card, *, bare: bool = False) -> str:
    if card.grade is None:
        return ""
    g = card.grade
    meters = "".join(
        f"""<div class="meter-row">
  <span class="meter-label">{esc(label)}</span>
  <span class="meter-track"><span class="meter-fill {g.tone}"
        style="width:{value * 100:.0f}%"></span></span>
  <span class="meter-val">{value * weight:.0f}/{weight}</span>
</div>"""
        for label, value, weight in g.components
    )
    title = {"A+": "High-reliability card", "A": "High-reliability card",
             "B": "Solid card", "C": "Mixed card",
             "D": "Low-reliability card", "F": "Low-reliability card"}[g.letter]
    inner = f"""  <div class="{_panel_card(bare)}">
    <div class="grade-wrap">
      <div class="grade {g.tone}">{g.letter}<small>{g.score:.0f}</small></div>
      <div><h3>{esc(title)}</h3>
        <p class="note top-gap-sm">{esc(g.headline)}</p></div>
    </div>
    <div class="card-pad divided">
      <div class="meter">{meters}</div>
      <p class="note top-gap">The grade describes how much weight the
        information deserves. It says nothing about which side of a market
        anyone should take, and Atlas does not publish that.
        <a href="../research.html#grades">How grades are computed</a>.</p>
    </div>
  </div>"""
    if bare:
        return inner
    return f"""<section class="section" id="grade">
  <div class="section-head"><h2>Atlas grade</h2>
    <span class="note">information quality — not a recommendation</span></div>
  {inner}
</section>"""


def _s6_drivers(card: Card, *, bare: bool = False) -> str:
    if not card.drivers:
        return ""
    items = []
    for driver in card.drivers:
        side = "pos" if driver.toward_home else "neg"
        colour = "var(--data-pos)" if driver.toward_home else "var(--data-neg)"
        items.append(f"""<div class="driver">
  <div class="driver-head">
    <span class="driver-name">{esc(driver.name)}</span>
    <span class="driver-edge" style="color:{colour}">{esc(driver.magnitude)}</span>
  </div>
  <p class="driver-text">{esc(driver.sentence)}</p>
  <div class="bar"><span class="bar-fill {side}" style="width:{driver.share * 100:.0f}%"></span></div>
  <div class="bar-scale"><span>{esc(driver.scale_left)}</span><span>{esc(driver.scale_right)}</span></div>
</div>""")
    extra = ""
    if card.grade and card.grade.low:
        extra = """<div class="disclosure top-gap">
  <b>Why the drivers can be right and the projection still weak.</b> Every
  driver above is measured and real. Turning several true statements into one
  number is where the model struggles on mismatches this large — there are few
  historical games like it, and the ones that exist behave inconsistently.
</div>"""
    inner = f'<div class="{_panel_card(bare)}">{"".join(items)}{extra}</div>'
    if bare:
        return inner
    return f"""<section class="section">
  <div class="section-head"><h2>Why Atlas sees it this way</h2>
    <span class="note">{len(card.drivers)} drivers · opponent-adjusted, pre-kickoff</span></div>
  {inner}
</section>"""


def _s7_market_intelligence(card: Card, *, bare: bool = False) -> str:
    total = card.total
    if total.current is None:
        return ""
    atlas_direction = (
        "up" if (card.total_difference or 0) > 0 else
        "down" if (card.total_difference or 0) < 0 else "flat"
    )
    market_direction = (
        f"down {abs(total.movement):.1f}" if (total.movement or 0) < 0 else
        f"up {total.movement:.1f}" if (total.movement or 0) > 0 else "unchanged"
    )
    agree = ((total.movement or 0) > 0) == ((card.total_difference or 0) > 0)
    reading = (
        "Atlas and the market have moved the same way on this total."
        if agree and total.movement else
        "Atlas and the market point opposite ways on this total. That is "
        "information, not a verdict."
    )
    chart = _movement_chart(card)
    rows_ = [
        ["Opening number", f'<span class="lead">{num(total.open_line)}</span>'],
        ["Current number", f'<span class="lead">{num(total.current)}</span>'],
        ["Market direction", f'<span class="lead">{esc(market_direction)}</span>'],
        ["Atlas direction", f'<span class="lead {"move-up" if atlas_direction == "up" else "move-down"}">'
                            f'{esc(atlas_direction)}</span>'],
    ]
    inner = f"""<div class="grid-2">
    <div class="{_panel_card(bare)}">
      <h3>Total, open to current</h3>
      {chart}
      {table(["Measure", "Value"], rows_)}
      <p class="note top-gap">{esc(reading)}</p>
    </div>
    <div class="card card-pad">
      <h3>Two findings that are not in conflict</h3>
      <p class="note top-gap-sm">Atlas has measured disagreement twice, against
        two different reference points, and they say different things.</p>
      {table(["Measured against", "What it predicts"], [
        ['<span class="lead">The closing number</span>',
         "the model's own failure — so a large difference lowers the grade"],
        ['<span class="lead">The opening number</span>',
         "which way the line moves — tracked publicly, not graded"],
      ])}
      <p class="note top-gap">A model far from the close is wrong; a model far
        from the open is early. The second finding is tracked in the open
        <a href="../research.html#clv">closing-line record</a> and is
        deliberately kept out of the grade.</p>
    </div>
  </div>"""
    if bare:
        return inner
    return f"""<section class="section">
  <div class="section-head"><h2>Market intelligence</h2>
    <span class="note">how this number has moved</span></div>
  {inner}
</section>"""


def _movement_chart(card: Card) -> str:
    total = card.total
    if total.open_line is None or total.current is None:
        return '<p class="note">No opening number recorded.</p>'
    values = [total.open_line, total.current]
    model = card.model_total
    low, high = min(values), max(values)
    if high - low < 1.0:
        low, high = low - 0.75, high + 0.75
    pad = (high - low) * 0.25
    low, high = low - pad, high + pad

    def y(value: float) -> float:
        return 96 - (value - low) / (high - low) * 72

    off_scale = model is not None and not (low <= model <= high)
    marker = ""
    if model is not None and not off_scale:
        marker = (f'<line x1="34" y1="{y(model):.1f}" x2="310" y2="{y(model):.1f}" '
                  f'class="rule"/><text x="310" y="{y(model) - 5:.1f}" class="label" '
                  f'text-anchor="end" fill="var(--data-pos)">Atlas {model:.1f}</text>')
    elif off_scale:
        marker = ('<text x="172" y="16" class="label" text-anchor="middle" '
                  f'fill="var(--data-neg)">Atlas {model:.1f} — beyond this range</text>')

    return f"""<svg viewBox="0 0 320 126" class="plot" role="img"
     aria-label="The total opened at {total.open_line:.1f} and is now {total.current:.1f}.">
  <line x1="34" y1="24" x2="310" y2="24" class="grid"/>
  <line x1="34" y1="60" x2="310" y2="60" class="grid"/>
  <line x1="34" y1="96" x2="310" y2="96" class="grid"/>
  <text x="28" y="28" class="axis" text-anchor="end">{high - (high - low) * 0.0:.1f}</text>
  <text x="28" y="64" class="axis" text-anchor="end">{(high + low) / 2:.1f}</text>
  <text x="28" y="100" class="axis" text-anchor="end">{low:.1f}</text>
  {marker}
  <polyline points="70,{y(total.open_line):.1f} 180,{y(total.open_line):.1f} 250,{y(total.current):.1f} 290,{y(total.current):.1f}"
            fill="none" stroke="var(--data-neutral)" stroke-width="2.5"
            stroke-linejoin="round" stroke-linecap="round"/>
  <circle cx="70" cy="{y(total.open_line):.1f}" r="4.5" fill="var(--data-neutral)"/>
  <circle cx="290" cy="{y(total.current):.1f}" r="5.5" fill="var(--ink-2)"/>
  <text x="70" y="118" class="axis" text-anchor="middle">open {total.open_line:.1f}</text>
  <text x="290" y="118" class="axis" text-anchor="middle">now {total.current:.1f}</text>
</svg>"""


def _s8_reliability(card: Card, bands: dict, overall_band, *, bare: bool = False) -> str:
    if card.grade is None:
        return ""
    band = card.grade.band
    chart = _calibration_chart(bands, band.label)
    rows_ = [
        ["Realised accuracy", f'<span class="lead">{pct(band.realised)}</span>',
         f'<span class="flat">{pct(overall_band.realised)}</span>'],
        ["Claimed accuracy", f'<span class="lead">{pct(band.claimed)}</span>',
         f'<span class="flat">{pct(overall_band.claimed)}</span>'],
        ["Calibration gap", f'<span class="lead {"move-down" if band.gap < -0.15 else ""}">'
                            f'{signed(band.gap * 100)} pts</span>',
         f'<span class="flat">{signed(overall_band.gap * 100)} pts</span>'],
        ["Seasons above 50%", f'<span class="lead">{band.seasons_above} of {band.seasons}</span>',
         '<span class="flat">—</span>'],
        ["Games measured", f'<span class="lead">{band.games:,}</span>',
         f'<span class="flat">{overall_band.games:,}</span>'],
    ]
    inner = f"""<div class="{_panel_card(bare)}">
    <div class="grid-2 wide-gap">
      <div>
        <h3>Calibration by disagreement band</h3>
        {chart}
        <p class="note top-gap-sm">Two series, labelled directly. The widening
          gap is why Atlas grades large disagreements <em>down</em>.</p>
      </div>
      <div>
        <h3>This band, seven seasons</h3>
        {table(["Measure", "This band", "All cards"], rows_)}
        <div class="disclosure top-gap">
          <b>Read the gap, not the claim.</b> Atlas's raw confidence numbers run
          high — a claimed {pct(band.claimed, 0)} has historically delivered
          {pct(band.realised, 0)}. The grade and the anchored projection both
          already correct for this. The claim is shown so the correction is
          visible rather than hidden.
        </div>
      </div>
    </div>
  </div>"""
    if bare:
        return inner
    return f"""<section class="section" id="reliability">
  <div class="section-head"><h2>Reliability</h2>
    <span class="note">how Atlas has performed on cards like this one</span></div>
  {inner}
</section>"""


def _calibration_chart(bands: dict, active: str) -> str:
    order = [b for b in ("0-1", "1-2", "2-4", "4-6", "6-8", "8-10", "10+") if b in bands]
    if len(order) < 3:
        return '<p class="note">Not enough history to plot.</p>'
    xs = [40 + i * (270 / (len(order) - 1)) for i in range(len(order))]
    lo, hi = 0.45, 0.82

    def y(value: float) -> float:
        return 18 + (hi - min(max(value, lo), hi)) / (hi - lo) * 96

    claimed = " ".join(f"{x:.0f},{y(bands[b].claimed):.1f}" for x, b in zip(xs, order, strict=False))
    realised = " ".join(f"{x:.0f},{y(bands[b].realised):.1f}" for x, b in zip(xs, order, strict=False))
    marks = ""
    for x, label in zip(xs, order, strict=False):
        if label != active:
            continue
        band = bands[label]
        marks = (
            f'<line x1="{x:.0f}" y1="{y(band.claimed):.1f}" x2="{x:.0f}" '
            f'y2="{y(band.realised):.1f}" stroke="var(--critical)" stroke-width="1.5"/>'
            f'<circle cx="{x:.0f}" cy="{y(band.claimed):.1f}" r="5" fill="var(--data-neg)" '
            f'stroke="var(--surface)" stroke-width="2"/>'
            f'<circle cx="{x:.0f}" cy="{y(band.realised):.1f}" r="5" fill="var(--data-pos)" '
            f'stroke="var(--surface)" stroke-width="2"/>'
            f'<text x="{min(x, 300):.0f}" y="132" class="label" '
            f'text-anchor="{"end" if x > 280 else "middle"}" '
            f'fill="var(--critical)">this card</text>'
        )
    active_x = next((x for x, label in zip(xs, order, strict=False) if label == active), None)
    ticks = "".join(
        f'<text x="{x:.0f}" y="132" class="axis" text-anchor="middle">{esc(label)}</text>'
        for x, label in zip(xs, order, strict=False)
        # A tick beside the "this card" marker collides with it, so the ends of
        # the scale are labelled and the middle is left to the marker.
        if label in ("0-1", "10+") and (active_x is None or abs(x - active_x) > 48)
    )
    return f"""<svg viewBox="0 0 330 142" class="plot" role="img"
     aria-label="Claimed versus realised accuracy by disagreement band. The gap widens as disagreement grows.">
  <line x1="34" y1="18"  x2="322" y2="18"  class="grid"/>
  <line x1="34" y1="66"  x2="322" y2="66"  class="grid"/>
  <line x1="34" y1="114" x2="322" y2="114" class="grid"/>
  <text x="28" y="22"  class="axis" text-anchor="end">82%</text>
  <text x="28" y="70"  class="axis" text-anchor="end">64%</text>
  <text x="28" y="118" class="axis" text-anchor="end">45%</text>
  <polyline points="{claimed}" fill="none" stroke="var(--data-neg)" stroke-width="2"
            stroke-linejoin="round"/>
  <polyline points="{realised}" fill="none" stroke="var(--data-pos)" stroke-width="2"
            stroke-linejoin="round"/>
  {marks}{ticks}
  <text x="322" y="16" class="label" text-anchor="end" fill="var(--data-neg)">claimed</text>
  <text x="322" y="110" class="label" text-anchor="end" fill="var(--data-pos)">realised</text>
</svg>"""


# ---------------------------------------------------------------------------
# Homepage
# ---------------------------------------------------------------------------


def homepage(cards: list[Card], *, bands: dict) -> str:
    """Rule 2: cards before navigation.

    The board is the first thing on the page. No hero, no marketing, no
    summary tiles above the fold — a reader who came for a game sees games,
    and the filters sit in a compact bar that stays with them as they scroll.
    """
    graded = [c for c in cards if c.grade]
    strong = sum(1 for c in graded if c.grade.letter in ("A+", "A"))
    weak = sum(1 for c in graded if c.grade.low)

    featured = sorted(
        graded,
        key=lambda c: (-(c.home.rank is not None) - (c.away.rank is not None),
                       -c.grade.score),
    )[:3]

    conferences = sorted({
        conf for card in cards for conf in (card.home.conference, card.away.conference) if conf
    })
    conf_options = "".join(f'<option value="{esc(c)}">{esc(c)}</option>' for c in conferences)

    by_day: dict[str, list[Card]] = {}
    for card in cards:
        by_day.setdefault(eastern(card.kickoff).strftime("%A, %-d %B"), []).append(card)
    day_blocks = "".join(
        f"""<section class="section tight">
  <div class="section-head"><h2>{esc(day)}</h2>
    <span class="note">{_plural(len(day_cards), "game")}</span></div>
  <div class="card game-list">{"".join(_game_row(c) for c in day_cards)}</div>
</section>"""
        for day, day_cards in by_day.items()
    )

    featured_block = ""
    if featured:
        featured_block = f"""<section class="section tight">
  <div class="section-head"><h2>Featured</h2>
    <span class="note">ranked matchups, highest-grade cards</span></div>
  <div class="featured">{"".join(_featured_cell(c) for c in featured)}</div>
</section>"""

    week = eastern(cards[0].kickoff).strftime("Week of %-d %B") if cards else "This week"

    body = f"""<div class="board-head">
  <h1>{esc(week)}</h1>
  <span class="board-note">{len(cards)} cards · {strong} graded A or better ·
    {weak} marked down</span>
</div>

<div class="board-bar" id="controls">
  <input class="search" type="search" id="q" placeholder="Search a team or conference"
         aria-label="Search games" autocomplete="off">
  <select id="conf" class="select" aria-label="Filter by conference">
    <option value="">All conferences</option>{conf_options}
  </select>
  <button class="filter" data-grade="" aria-pressed="true">All</button>
  <button class="filter" data-grade="A" aria-pressed="false">A &amp; up</button>
  <button class="filter" data-grade="B" aria-pressed="false">B &amp; up</button>
  <button class="filter" data-grade="low" aria-pressed="false">Marked down</button>
</div>
<p class="note board-count" id="count" aria-live="polite"></p>

{featured_block}

{day_blocks}

<div class="card card-pad nfl-strip">
  <div class="banner-row">
    <span class="badge mute">NFL · calibration in progress</span>
    <p class="note banner-text">Atlas's model is built and validated on college
      football. NFL cards do not publish until the model has been fitted and
      back-tested to the same standard. <a href="nfl.html">What that involves</a>.</p>
  </div>
</div>

<div class="disclosure top-gap">
  <b>About this week's numbers.</b> It is week {cards[0].week if cards else ""},
  so team profiles are still shrunk toward last season and efficiency figures
  move a lot between games. Atlas publishes research, analytics and market
  context; it does not publish selections, does not size anything and does not
  project returns.
</div>

<script src="assets/atlas.js" defer></script>"""

    return layout(title="Atlas Sports Intelligence — college football cards",
                  body=body, active="today")


def _row_crests(card: Card, root: str = "") -> str:
    return (f'<span class="row-crests">{_logo(card.away, size="small", root=root)}'
            f'{_logo(card.home, size="small", root=root)}</span>')


def _game_row(card: Card) -> str:
    grade_letter = card.grade.letter if card.grade else ""
    grade_key = ("low" if card.grade and card.grade.low
                 else grade_letter.rstrip("+") if grade_letter else "")
    haystack = " ".join(filter(None, [
        card.home.name, card.away.name, card.home.short, card.away.short,
        card.home.abbr, card.away.abbr, card.home.conference, card.away.conference,
    ])).lower()
    confs = "|".join(filter(None, [card.home.conference, card.away.conference]))
    difference = card.total_difference
    diff_text = (f"Atlas {signed(difference)}" if difference is not None
                 else "no Atlas number")
    ranks = "".join(
        f'<span class="rank">#{side.rank}</span>'
        for side in (card.away, card.home) if side.rank
    )
    meta = " · ".join(filter(None, [clock(card.kickoff), card.tv]))
    return f"""<a class="game-row" href="{esc(card.path)}"
   data-search="{esc(haystack)}" data-conf="{esc(confs)}" data-grade="{esc(grade_key)}">
  <div class="game-main">
    <div class="row-teams">{_row_crests(card)}
      <span class="game-teams">{esc(card.title)}</span>{ranks}</div>
    <div class="game-meta">{esc(meta)}</div>
  </div>
  <div class="game-right">
    <div class="game-numbers">
      <div class="game-line">{esc(card.spread_text)} · {num(card.total.current)}</div>
      <div class="game-meta">{esc(diff_text)}</div>
    </div>
    {grade_pill(card)}
  </div>
</a>"""


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def _featured_cell(card: Card) -> str:
    difference = card.total_difference
    return f"""<a class="card card-pad feature" href="{esc(card.path)}">
  <div class="feature-head">{_row_crests(card)}{grade_pill(card)}</div>
  <h3 class="feature-title">{esc(card.title)}</h3>
  <p class="note feature-meta">{esc(day_clock(card.kickoff))}{esc(" · " + card.tv if card.tv else "")}</p>
  <div class="feature-nums">
    <div><span class="stat-label">Market</span>
      <span class="feature-num">{esc(card.spread_text)}</span></div>
    <div><span class="stat-label">Total</span>
      <span class="feature-num">{num(card.total.current)}</span></div>
    <div><span class="stat-label">Atlas</span>
      <span class="feature-num">{num(card.anchored_total)}</span></div>
  </div>
  <p class="note feature-foot">Difference {signed(difference)} on the total</p>
</a>"""


# ---------------------------------------------------------------------------
# Team page
# ---------------------------------------------------------------------------


def team_page(team, *, cards: list[Card], pool: dict) -> str:
    from atlas.site.data import percentile

    def stat(metric: str, label: str, note: str, fmt) -> str:
        value = team.metrics.get(metric)
        rank = percentile(pool, metric, value)
        return f"""<div class="stat"><div class="stat-label">{esc(label)}</div>
  <div class="stat-value">{fmt(value)}</div>
  <div class="stat-note">{esc(_ordinal_note(rank, note))}</div></div>"""

    upcoming = [c for c in cards if team.team_id in (c.home.team_id, c.away.team_id)]
    schedule_rows = []
    for card in upcoming:
        opponent = card.away if card.home.team_id == team.team_id else card.home
        prefix = "vs" if card.home.team_id == team.team_id else "at"
        schedule_rows.append([
            esc(eastern(card.kickoff).strftime("%-d %b")),
            f"{prefix} {esc(opponent.short)}",
            esc(card.spread_text),
            num(card.total.current),
            f'<a href="../{esc(card.path)}">{grade_pill(card)}</a>',
        ])

    body = f"""<div class="card game-head" style="--team-home:{esc(team.colour)};--team-away:#9aa1aa">
  <div class="team-head">
    {_logo(team, size="large", root="../")}
    <div>
      <h1>{esc(team.name)}</h1>
      <p class="sub">{esc(" · ".join(filter(None, [team.conference, team.record])))}</p>
    </div>
  </div>
</div>

<section class="section">
  <div class="section-head"><h2>Season profile</h2>
    <span class="note">opponent-adjusted · percentile of FBS this season</span></div>
  <div class="card">
    <div class="grid-3">
      {stat("adj_off_epa", "Offensive EPA / play", "", lambda v: signed(v, 2))}
      {stat("adj_success_rate", "Success rate", "", lambda v: pct(v))}
      {stat("adj_explosiveness", "Explosiveness", "", lambda v: num(v, 2))}
    </div>
    <div class="grid-3 divided">
      {stat("adj_def_success_rate", "Defensive success allowed", "lower is better", lambda v: pct(v))}
      {stat("adj_pace", "Pace", "seconds per play", lambda v: num(v, 1) + "s" if v else "—")}
      {stat("plays_per_game", "Plays per game", "", lambda v: num(v, 1))}
    </div>
  </div>
  <p class="note top-gap">Every figure is opponent-adjusted and point-in-time:
    it uses only games played before the date shown, so a team's profile in
    week {upcoming[0].week if upcoming else ""} is what was knowable in week
    {upcoming[0].week if upcoming else ""}.</p>
</section>

<section class="section">
  <div class="section-head"><h2>Upcoming</h2>
    <span class="note">cards Atlas has published</span></div>
  <div class="card card-pad">
    {table(["Date", "Opponent", "Market", "Total", "Card"], schedule_rows)
     if schedule_rows else '<p class="note">No upcoming cards.</p>'}
  </div>
</section>

<div class="disclosure top-gap">
  <b>Player pages are reserved and not implemented.</b> Atlas has no
  player-level model, and a page that looked like one would imply research that
  does not exist.
</div>"""
    return layout(title=f"{team.name} — Atlas Sports Intelligence", body=body,
                  depth=1, active="ncaaf",
                  description=f"{team.name} season profile: opponent-adjusted "
                              "efficiency, pace and upcoming Atlas cards.")


def _ordinal_note(rank: float | None, extra: str) -> str:
    if rank is None:
        return extra or "no data"
    pct_value = max(1, min(99, round(rank * 100)))
    suffix = "th" if 11 <= pct_value % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(pct_value % 10, "th")
    text = f"{pct_value}{suffix} percentile"
    return f"{text} · {extra}" if extra else text


# ---------------------------------------------------------------------------
# Research, NFL and premium
# ---------------------------------------------------------------------------


def research_page(bands: dict, overall_band, *, card_count: int) -> str:
    band_rows = [
        [f'<span class="lead">{esc(b.label)}</span>', f"{b.games:,}",
         pct(b.claimed), pct(b.realised),
         f'<span class="{"move-down" if b.gap < -0.1 else "flat"}">{signed(b.gap * 100)} pts</span>',
         f"{b.seasons_above} of {b.seasons}"]
        for b in bands.values()
    ]
    body = f"""<header class="page-head">
  <h1>How Atlas works</h1>
  <p class="sub">Five phases of research sit behind every card. This page is
    the short version, and it is free because the evidence for a claim should
    never cost more than the claim.</p>
</header>

<section class="section" id="how">
  <div class="section-head"><h2>The short version</h2></div>
  <div class="card card-pad prose">
    <p>Atlas measures college football with an opponent-adjusted,
      point-in-time database: every figure attached to a game uses only
      information that existed before kickoff. The model is fitted on completed
      seasons and scored on seasons it has never seen.</p>
    <p>Then it does something most models do not. It compares itself to the
      market, and it publishes what that comparison found — which is that the
      market is the stronger forecast.</p>
    <p><b>Atlas weights the market at {MARKET_WEIGHT["total"]:.2f} on totals and
      {MARKET_WEIGHT["margin"]:.2f} on spreads.</b> Those weights were fitted
      across 5,778 games, not chosen. On spreads, the model's own contribution
      could not be told apart from zero, so the published spread is the
      market's number. The projection you see is the accurate one; the raw
      model sits beside it, labelled, so the correction is visible.</p>
  </div>
</section>

<section class="section" id="grades">
  <div class="section-head"><h2>What a grade means</h2></div>
  <div class="card card-pad prose">
    <p>A grade is <b>not</b> a recommendation. It answers one question: how
      much weight does the information on this card deserve?</p>
    <p>It is computed, never assigned. Four components, one hundred points:</p>
    {table(["Component", "Points", "What it measures"], [
      ['<span class="lead">Calibration</span>', "40",
       "how close claimed accuracy has been to realised accuracy in this card's disagreement band"],
      ['<span class="lead">Market agreement</span>', "25",
       "how far the unanchored model sits from the market"],
      ['<span class="lead">Signal stability</span>', "20",
       "how many seasons that band has finished above even"],
      ['<span class="lead">Data completeness</span>', "15",
       "how many of the required inputs are present"],
    ])}
    {table(["Score", "Grade"], [["90–100", '<span class="lead">A+</span>'],
                                ["80–89", '<span class="lead">A</span>'],
                                ["70–79", '<span class="lead">B</span>'],
                                ["60–69", '<span class="lead">C</span>'],
                                ["50–59", '<span class="lead">D</span>'],
                                ["below 50", '<span class="lead">F</span>']])}
  </div>
</section>

<section class="section" id="disagreement">
  <div class="section-head"><h2>Why large disagreements lower confidence</h2></div>
  <div class="card card-pad prose">
    <p>This is the least intuitive thing Atlas publishes, and the most
      important. A model that disagrees violently with the market looks
      exciting. Measured across {overall_band.games:,} out-of-sample games, it
      is the opposite.</p>
    {table(["Disagreement", "Games", "Claimed", "Realised", "Gap", "Seasons above 50%"], band_rows)}
    <p>Read the gap column. Where Atlas barely disagrees with the market, its
      claimed accuracy and its realised accuracy nearly match. Where it
      disagrees by ten points or more, it claimed
      {pct(bands["10+"].claimed, 0) if "10+" in bands else "—"} and delivered
      {pct(bands["10+"].realised, 0) if "10+" in bands else "—"}.</p>
    <p><b>So the loudest cards get the lowest grades.</b> Every other product in
      this category shouts hardest exactly where its model is weakest, because
      a big disagreement makes a compelling post. Atlas measured that and does
      the opposite, in public, on every card.</p>
  </div>
</section>

<section class="section" id="calibration">
  <div class="section-head"><h2>Calibration</h2></div>
  <div class="card card-pad prose">
    <p>Calibration asks whether a claimed 65% is a real 65%. Atlas's raw model
      is <b>overconfident</b>, and gets more so as it gets more confident: its
      top confidence bucket claims
      {pct(bands["10+"].claimed, 0) if "10+" in bands else "—"} and realises
      about {pct(bands["10+"].realised, 0) if "10+" in bands else "—"}.</p>
    <p>Two things on every card already correct for this. The projection is
      market-anchored, which collapses the error. And the grade is built from
      the calibration record itself, so a card in a badly-calibrated band
      cannot grade well no matter how interesting it looks.</p>
    <p>The claimed number is still shown, beside the realised one, because a
      correction you cannot see is a correction you cannot check.</p>
  </div>
</section>

<section class="section" id="clv">
  <div class="section-head"><h2>The second finding, kept separate</h2></div>
  <div class="card card-pad prose">
    <p>Atlas measured disagreement twice, against two different reference
      points, and got two different answers.</p>
    <p>Distance from the <b>closing</b> number predicts the model's own failure
      — that is the calibration table above, and it drives the grade. Distance
      from the <b>opening</b> number predicts which way the line will move,
      which is a fact about the market rather than about the football game.</p>
    <p>A model far from the close is wrong. A model far from the open is early.
      Atlas tracks the second finding in an open, pre-registered record with
      its own kill criteria, and deliberately keeps it out of the grade.</p>
  </div>
</section>

<section class="section">
  <div class="section-head"><h2>What Atlas does not do</h2></div>
  <div class="card card-pad prose">
    <p>Atlas does not publish selections. Not as a lean, not as an arrow, not
      as a highlighted row. Five phases of research established that Atlas has
      no edge worth acting on, and a product that implied otherwise would be
      saying something its own reliability record contradicts.</p>
    <p>{card_count} cards are published this week. None of them tells you what
      to do with the information.</p>
  </div>
</section>"""
    return layout(title="How Atlas works — Atlas Sports Intelligence", body=body,
                  active="research",
                  description="How the Atlas model works, what the A–F grades "
                              "mean, and why large disagreements lower confidence.")


def nfl_page() -> str:
    body = """<header class="page-head">
  <h1>NFL</h1>
  <p class="sub">Calibration in progress. Atlas does not publish NFL cards yet,
    and this page explains exactly why rather than saying "coming soon".</p>
</header>

<div class="card card-pad banner-low">
  <div class="banner-row">
    <span class="badge mute">Stage 1 of 3</span>
    <p class="note banner-text">Schedules and market context are the work of a
      data feed. Projections need a model. Grades need a model that has been
      measured for seven seasons — and until that sentence is true for the NFL,
      a grade would be decoration.</p>
  </div>
</div>

<section class="section">
  <div class="section-head"><h2>The three stages</h2></div>
  <div class="card card-pad">
""" + table(["Stage", "What ships", "What it needs"], [
        ['<span class="lead">1 — now</span>',
         "schedules, scores, team pages, market snapshot",
         "an odds and schedule feed"],
        ['<span class="lead">2</span>', "projections and drivers",
         "NFL play-by-play from 2018, the warehouse rebuilt, the model refitted"],
        ['<span class="lead">3</span>', "grades",
         "the same seven-season calibration study college football has"],
    ]) + """
    <p class="note top-gap">The warehouse, feature and model layers are
      sport-agnostic, so most of the college pipeline carries over. The binding
      constraint is the calibration study, which needs completed seasons and
      cannot be hurried.</p>
  </div>
</section>

<div class="disclosure top-gap">
  <b>Why not ship projections now?</b> Because the grade framework is the
  product, and its entire credibility comes from having been tested. Putting an
  untested model behind it would spend that credibility to fill a page.
</div>"""
    return layout(title="NFL — Atlas Sports Intelligence", body=body, active="nfl",
                  description="Atlas NFL cards are in calibration. The three "
                              "stages, and why grades come last.")


def premium_page() -> str:
    compare = table(["", "Free", "Premium"], [
        ['<span class="lead">Every game, every week</span>', "✓", "✓"],
        ['<span class="lead">Atlas grade (the letter)</span>', "✓", "✓"],
        ['<span class="lead">Reliability record</span>', "✓ always", "✓"],
        ['<span class="lead">Research and methodology</span>', "✓", "✓"],
        ['<span class="lead">Team pages</span>', "✓", "✓"],
        ['<span class="lead">Projected spread and total</span>', "✓", "✓"],
        ['<span class="lead">Projected score and win probability</span>',
         '<span class="flat">—</span>', "✓"],
        ['<span class="lead">Opening numbers and movement</span>',
         '<span class="flat">—</span>', "✓"],
        ['<span class="lead">Moneyline and de-vigged probabilities</span>',
         '<span class="flat">—</span>', "✓"],
        ['<span class="lead">Atlas difference</span>', '<span class="flat">—</span>', "✓"],
        ['<span class="lead">Grade component breakdown</span>',
         '<span class="flat">—</span>', "✓"],
        ['<span class="lead">All drivers with percentiles</span>',
         '<span class="lead">top driver</span>', "✓"],
        ['<span class="lead">Market intelligence</span>',
         '<span class="flat">—</span>', "✓"],
        ['<span class="lead">Historical database and export</span>',
         '<span class="flat">—</span>', "✓"],
    ])
    body = f"""<header class="page-head">
  <h1>Premium</h1>
  <p class="sub">Atlas sells depth. It does not sell honesty — the grade and the
    reliability record are free, permanently.</p>
</header>

<div class="card card-pad banner-low">
  <div class="banner-row">
    <span class="badge mute">Framework only</span>
    <p class="note banner-text">Premium is specified and not yet available.
      There is no payment path on this site and no way to subscribe.</p>
  </div>
</div>

<section class="section">
  <div class="section-head"><h2>What each tier includes</h2></div>
  <div class="card card-pad">{compare}</div>
</section>

<section class="section">
  <div class="section-head"><h2>Why these lines</h2></div>
  <div class="card card-pad prose">
    <p><b>The grade letter is free.</b> It is the product's honesty in one
      character, and it has to be in front of everyone — including people who
      only ever see a screenshot.</p>
    <p><b>The reliability record is free, permanently.</b> It is the evidence.
      A reliability record that costs money is not a record, it is a claim.</p>
    <p><b>The Atlas difference section is entirely paid.</b> It is the part
      closest to being misread as a recommendation, and it carries the most
      caveats. Putting it where a reader has already seen the grade is a
      product-safety decision as much as a commercial one.</p>
    <p><b>No affiliate revenue, ever.</b> Books pay for traffic that converts
      to deposits. Taking that money would mean Atlas earns more when readers
      act — an interest directly opposed to the product's only claim.</p>
  </div>
</section>

<section class="section">
  <div class="section-head"><h2>What premium will never become</h2></div>
  <div class="card card-pad prose">
    <p>Atlas will not publish a side, at any price. The research established
      that there is no edge worth acting on; a paid tier that implied otherwise
      would be contradicted by the free reliability record on every card.</p>
    <p>No blurred numbers. No card of the day. No countdowns. Premium sections
      show one line describing what is behind them and a single link.</p>
  </div>
</section>"""
    return layout(title="Premium — Atlas Sports Intelligence", body=body,
                  active="premium",
                  description="What Atlas premium includes, what stays free "
                              "permanently, and why.")
