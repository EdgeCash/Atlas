"""Rendering the approved design into pages.

Nothing here invents design. The tokens, components, type scale and chart
rules come from `docs/UI_SYSTEM.md`; the eight sections and their order come
from `docs/ATLAS_CARD_SPEC.md`; the voice and the forbidden vocabulary come
from `docs/BRAND_GUIDE.md`.
"""

from __future__ import annotations

import os

from atlas.site.data import Card
from atlas.site.grade import seasons_word
from atlas.site.html import (
    clock,
    day_and_clock,
    day_clock,
    eastern,
    esc,
    minus,
    num,
    pct,
    possessive,
    price,
    signed,
    stamp,
    table,
)
from atlas.util import get_logger

LOG = get_logger(__name__)

TAGLINE = "Research. Analytics. Context."

#: Where beta feedback goes. A mailto rather than a form: a form needs a
#: server, and the one thing this product does not have is a server. It is
#: also the only visible addition RC1 makes to a frozen design - one footer
#: link, no button, no modal, nothing on the board or the card.
FEEDBACK_EMAIL = "beta@atlas.football"

#: The canonical origin. Search engines need one spelling of every page, and a
#: social card posted from a preview build must still point at production.
#:
#: Overridable because the site has to be publishable before the domain is
#: bought: on GitHub Pages it lives at a project subpath, and a canonical that
#: claims a domain nobody has registered yet is worse than no launch at all.
#: The default stays production, so nothing changes for a normal build.
SITE_URL = os.environ.get("ATLAS_SITE_URL", "https://atlas.football").rstrip("/")


def asset(name: str) -> str:
    """``assets/<name>?v=<content hash>``.

    Pages link the stylesheet and script by a name that changes whenever the
    file does. Pages lets a browser reuse a cached asset for ten minutes and
    Safari often longer, so a plain name served new pages with the old
    stylesheet after every deploy - both board views at once, an unstyled
    switch. A new name is a file the browser has never cached.
    """
    import hashlib
    from pathlib import Path

    body = (Path(__file__).resolve().parent / "assets" / name).read_bytes()
    return f"assets/{name}?v={hashlib.sha256(body).hexdigest()[:10]}"

#: The sentence that appears on every card, unchanged.
CARD_DISCLOSURE = (
    "<b>What this card is.</b> Research, analytics and market context. Atlas "
    "does not publish selections, does not size anything and does not project "
    "returns. Every figure is computed out of sample from a point-in-time "
    "database: nothing attached to a game uses information that did not exist "
    "before kickoff."
)

def freshness_badge(*pairs, root: str = "") -> str:
    """One or more "Label: timestamp ET" stamps.

    `docs/DATA_FRESHNESS.md`: every stamp is the time of the last *successful*
    refresh of that thing, never the time the page was built. A board that
    rebuilt at 7:05 against a market captured at 6:00 says 6:00, because that
    is when the information a reader is looking at was last true.
    """
    items = "".join(
        f'<span class="stamp"><b>{esc(label)}</b> {esc(value)}</span>'
        for label, value in pairs if value
    )
    if not items:
        return ""
    return (f'<p class="freshness">{items}'
            f'<a href="{root}status.html">Data status</a></p>')


#: Most first-time visitors arrive on a card, from a link, knowing nothing
#: about Atlas - so the card has to offer the explanation rather than assume a
#: reader will find the nav. One line, at the end of the five-second view,
#: which is exactly where somebody who is confused has got to.
NEW_HERE = (
    '<p class="new-here">New to Atlas? '
    '<a href="../about.html">What a card is, and what a grade means</a></p>'
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
           active: str = "", social: str = "", canonical: str | None = None,
           structured: str = "") -> str:
    root = "../" * depth
    # Home shows the best matchups from both sports; then one entry per
    # sport, each its full board. The name at the left is home too.
    nav_items = [
        ("Home", f"{root}index.html", "home"),
        ("NCAAF", f"{root}ncaaf.html", "ncaaf"),
        ("NFL", f"{root}nfl.html", "nfl"),
        ("DFS", f"{root}dfs.html", "dfs"),
        ("Scores", f"{root}scoreboard.html", "scores"),
        ("Record", f"{root}record.html", "record"),
        ("Research", f"{root}research.html", "research"),
        ("Premium", f"{root}premium.html", "premium"),
        ("About", f"{root}about.html", "about"),
    ]
    current = ' aria-current="page"'
    nav = "".join(
        f'<a href="{href}"{current if key == active else ""}>{esc(label)}</a>'
        for label, href, key in nav_items
    )
    meta_description = description or (
        "Research, analytics and market context for college football and the NFL. "
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
<link rel="stylesheet" href="{root}{asset("atlas.css")}">
<script src="{root}{asset("games.js")}" defer></script>
{f'<link rel="canonical" href="{esc(SITE_URL)}/{esc(canonical)}">' if canonical is not None else ""}
{social}
{structured}
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
    <a href="{root}about.html">new here</a> ·
    <a href="{root}faq.html">questions</a> ·
    <a href="{root}status.html">data status</a> ·
    <a href="mailto:{FEEDBACK_EMAIL}?subject=Atlas%20beta%20feedback">feedback</a> ·
    <a href="{root}research.html">how Atlas works</a> ·
    <a href="{root}research.html#grades">what grades mean</a></div>
  <div class="footer-note">Atlas publishes information. Readers make their own
    decisions.</div>
</footer>
</main>
</body>
</html>
"""


def social_tags(*, title: str, description: str, image: str | None = None,
                url: str | None = None) -> str:
    tags = [
        f'<meta property="og:title" content="{esc(title)}">',
        f'<meta property="og:description" content="{esc(description)}">',
        '<meta property="og:site_name" content="Atlas Sports Intelligence">',
        '<meta property="og:type" content="article">',
        '<meta name="twitter:card" content="summary_large_image">',
        f'<meta name="twitter:title" content="{esc(title)}">',
        f'<meta name="twitter:description" content="{esc(description)}">',
    ]
    if url:
        tags.append(f'<meta property="og:url" content="{esc(SITE_URL)}/{esc(url)}">')
    if image:
        # Absolute, because a link unfurled inside another product cannot
        # resolve a relative path.
        tags.append(f'<meta property="og:image" content="{esc(SITE_URL)}/{esc(image)}">')
        tags.append(f'<meta name="twitter:image" content="{esc(SITE_URL)}/{esc(image)}">')
    return "\n".join(tags)


def json_ld(payload: dict) -> str:
    """One structured-data block. Search engines read it; nobody sees it.

    Only facts that are already visible on the page go in here - a page whose
    markup claims something its body does not is the kind of thing that gets a
    site demoted, and it would be dishonest besides.
    """
    import json

    return ('<script type="application/ld+json">'
            + json.dumps(payload, separators=(",", ":"))
            + "</script>")


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
        city = f", {esc(card.city)}" if card.city else ""
        bits.append(f"<span>{player_name(card.venue)}{city}</span>")
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


def card_page(card: Card, *, bands: dict, overall_band,
              social_image: bool = False, freshness: dict | None = None) -> str:
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
        freshness_badge(
            ("Projection built", (freshness or {}).get("projection", "")),
            ("Market updated", (freshness or {}).get("market", "")),
            root="../",
        ),
        NEW_HERE,
        '<div class="tier2">',
        _open_market(card),
        _open_projection(card),
        _open_matchup(card),
        _open_grade(card),
        _open_drivers(card),
        _open_movement(card),
        _open_reliability(card, bands, overall_band),
        "</div>",
        f'<div class="disclosure card-foot">{CARD_DISCLOSURE}</div>',
        games_blob([card]),
    ]))
    description = (
        f"{card.title}: market {card.spread_text}, total "
        f"{num(card.total.current)}. Atlas projects {_projected_score(card)} "
        f"and grades this card {card.grade.letter if card.grade else 'ungraded'}."
    )
    return layout(
        title=f"{card.title} — Atlas projection and grade",
        body=body, depth=1, description=description, active=card.sport,
        canonical=card.path,
        social=social_tags(title=f"{card.title} · Atlas", description=description,
                           url=card.path,
                           image=f"social/{card.slug}-wide.png" if social_image else None),
        structured=_card_schema(card),
    )


def _card_schema(card: Card) -> str:
    """SportsEvent. Teams, venue and kickoff - the facts on the page, nothing
    else.

    Deliberately *not* the page's meta description, which names the grade and
    the projection. Structured data is for the game; a machine-readable grade
    is one copy-paste away from being a feed of letters with no card around
    them, and the card is the thing that makes a letter mean anything.
    """
    competitors = [
        {"@type": "SportsTeam", "name": side.name, "url": f"{SITE_URL}/{team_path(side, card.sport)}"}
        for side in (card.away, card.home)
    ]
    payload = {
        "@context": "https://schema.org",
        "@type": "SportsEvent",
        "name": card.title,
        "description": f"{card.away.name} at {card.home.name}, "
                       f"{'NFL' if card.sport == 'nfl' else 'college football'}.",
        "startDate": card.kickoff.isoformat(),
        "eventStatus": "https://schema.org/EventScheduled",
        "sport": "American Football",
        "url": f"{SITE_URL}/{card.path}",
        "homeTeam": competitors[1],
        "awayTeam": competitors[0],
        "competitor": competitors,
    }
    if card.venue:
        location = {"@type": "Place", "name": card.venue}
        if card.city:
            location["address"] = {
                "@type": "PostalAddress", "addressLocality": card.city,
                "addressRegion": card.state or "", "addressCountry": "US",
            }
        payload["location"] = location
    return json_ld(payload)


def _team_slug(side) -> str:
    from atlas.site.data import _slug

    return _slug(side.name)


def team_path(side, sport: str = "ncaaf") -> str:
    """Where a team's page lives: ``team/`` for college, ``nfl/team/`` for the NFL."""
    return f"nfl/team/{_team_slug(side)}.html" if sport == "nfl" else f"team/{_team_slug(side)}.html"


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
    bits = [esc(day_and_clock(card.kickoff))]
    if card.tv:
        bits.append(esc(card.tv))
    if card.venue:
        # A stadium is a name, not vocabulary: Kelly/Shorts is Central
        # Michigan's, and the audit would otherwise read a stakes formula.
        bits.append(player_name(card.venue))
    return f"""<div class="card hero" style="--team-home:{esc(home_accent)};--team-away:{esc(away_accent)}">
  <div class="hero-teams">
    {_team_column(card.away, align="away")}
    <div class="hero-at">at</div>
    {_team_column(card.home, align="home")}
  </div>
  <div class="hero-meta-row">{" · ".join(bits)} {_started_chip(card)}</div>
  <div class="hero-follow">{_follow_button(card)}</div>
</div>"""


def _answer(card: Card) -> str:
    """Market first, Atlas's own number second, the difference, and the grade,
    which dominates. The market is the reference, never an input."""
    difference = card.margin_difference
    grade_block = _grade_hero(card)
    return f"""<div class="answer">
  <div class="card answer-nums">
    <div class="answer-cell">
      <div class="stat-label">Market</div>
      <div class="answer-value">{esc(card.spread_text)}</div>
      <div class="stat-note">total {num(card.total.current)}{_market_move_note(card)}</div>
    </div>
    <div class="answer-cell">
      <div class="stat-label"><span class="wide-only">Atlas projects</span><span class="narrow-only">Atlas</span></div>
      <div class="answer-value">{_projected_score(card)}</div>
      <div class="stat-note">{esc(card.away.abbr)}–{esc(card.home.abbr)} ·
        total {num(card.model_total)}</div>
    </div>
    <div class="answer-cell">
      <div class="stat-label">Difference</div>
      <div class="answer-value {_diff_class(difference)}">{signed(difference)}</div>
      <div class="stat-note">on the spread · total {signed(card.total_difference)}</div>
    </div>
  </div>
  {grade_block}
</div>"""


def _market_move_note(card: Card) -> str:
    """Where the spread opened, when it has moved: open, move and now in one line."""
    move = card.spread.movement
    if move is None or abs(move) < 0.05 or card.spread.open_line is None:
        return ""
    opener = card.home if card.spread.open_line >= 0 else card.away
    return (f" · spread opened {esc(opener.abbr)} {minus(-abs(card.spread.open_line))}, "
            f"moved {signed(move)} toward {esc(card.home.abbr if move > 0 else card.away.abbr)}")


def _projected_score(card: Card) -> str:
    """Away first, as the title reads, to one decimal: the mean of the
    model's score distribution is not an integer and is not rounded to one.
    The note names both abbreviations, because "15.4–29.1" on its own is a
    pair of numbers, not a scoreline."""
    if card.projected_home is None:
        return "—"
    return f"{card.projected_away:.1f}–{card.projected_home:.1f}"


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
        # An ungraded card is still a card: it carries the same disclaimer, and
        # it says why there is no grade rather than implying a lack of history
        # when the real reason is that no book has priced the game yet.
        reason = ("No market is posted yet, so there is nothing to grade Atlas's number against."
                  if card.spread.current is None else "Not enough history to grade this card.")
        return f"""<div class="card grade-hero none">
  <div class="grade-mark">–</div>
  <div class="grade-words"><div class="grade-title">Not graded</div>
    <p class="grade-line">{esc(reason)}</p>
    <p class="grade-foot">A grade is how much weight a card's information deserves —
      not a recommendation.</p></div>
</div>"""
    g = card.grade
    # Rule 4: the grade teaches. A letter is a symbol, and a symbol a reader
    # has to be taught is a symbol they skip - so every card teaches it again,
    # in plain English, from its own numbers.
    headline, alignment, record = g.lesson
    return f"""<div class="card grade-hero {g.tone}">
  <div class="grade-mark">{g.letter}<small>{g.score:.0f}<span>/100</span></small></div>
  <div class="grade-words">
    <div class="grade-title">{esc(headline)}</div>
    <p class="grade-line">{esc(alignment)}</p>
    <p class="grade-line quiet">{esc(record)}</p>
    <div class="grade-bar"><span style="width:{g.score:.0f}%"></span></div>
    <p class="grade-foot">How much weight this card's information deserves —
      not a recommendation.</p>
  </div>
</div>"""


def _why_brief(card: Card) -> str:
    """Rule 1: the reason, in three lines, before anything expands."""
    if not card.drivers:
        return ""
    def mark(driver) -> str:
        if driver.favors == "home":
            return _logo(card.home, size="tiny")
        if driver.favors == "away":
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
    hint = "where the line opened, where it is now, and the prices"
    return _panel("Market detail", hint, _s2_market(card, bare=True))


def _open_projection(card: Card) -> str:
    return _panel("Projection detail",
                  "the projected score, the chance of winning, the total's range and the most likely exact score",
                  _s3_projection(card, bare=True) + _s4_difference(card, bare=True))


def _open_matchup(card: Card) -> str:
    m = card.matchup
    if m is None:
        return ""
    return _panel("Matchup",
                  f"how each offense compares with the defense it faces, season to date, "
                  f"ranked among {m.teams} {m.universe}",
                  _matchup_body(card))


def _matchup_value(stat, value: float | None) -> str:
    if value is None:
        return "—"
    if stat.kind == "pct":
        return pct(value, 0)
    if stat.key == "turnover_margin":
        return signed(value, 2)
    return num(value, 2 if stat.kind == "rate" else 1)


def _matchup_rank(stat, rank: int | None, teams: int) -> str:
    if rank is None:
        return ""
    if stat.higher_is_better is None:
        return f'<span class="mu-rank">{_ordinal(rank)} most</span>'
    tier = " r-top" if rank <= teams / 3 else " r-low" if rank > 2 * teams / 3 else ""
    return f'<span class="mu-rank{tier}">{_ordinal(rank)}</span>'


def _matchup_row(label: str, left_stat, left, right_stat, right, teams: int, sides) -> str:
    """One figure, the left team against the right. The better rank gets the
    small crest beside the label; a tie, or a figure with no better (pace),
    gets none."""
    lv, lr = left.values.get(left_stat.key), left.ranks.get(left_stat.key)
    rv, rr = right.values.get(right_stat.key), right.ranks.get(right_stat.key)
    edge = ""
    if left_stat.higher_is_better is not None and lr is not None and rr is not None and lr != rr:
        side = sides[0] if lr < rr else sides[1]
        mark = (f'<img class="crest tiny" src="../assets/logos/{esc(side.logo)}" alt="" width="18" height="18">'
                if side.logo else "")
        edge = f'<span class="mu-edge">{mark}<span class="sr">edge {esc(side.short)}</span></span>'
    left_win = " win" if edge and lr < rr else ""
    right_win = " win" if edge and rr < lr else ""
    return f"""<div class="mu-row">
  <div class="mu-val{left_win}">{_matchup_value(left_stat, lv)}{_matchup_rank(left_stat, lr, teams)}</div>
  <div class="mu-stat">{esc(label)}{edge}</div>
  <div class="mu-val right{right_win}">{_matchup_value(right_stat, rv)}{_matchup_rank(right_stat, rr, teams)}</div>
</div>"""


def _matchup_body(card: Card) -> str:
    from atlas.site.matchup import PAIR_LABELS, PAIRS, SITUATIONAL

    m = card.matchup
    away, home = card.away, card.home

    def head(left: str, right: str) -> str:
        return f"""<div class="mu-head"><span>{left}</span><span class="mu-vs">vs</span>
  <span class="right">{right}</span></div>"""

    def group(off_side, off_line, def_side, def_line) -> str:
        rows = "".join(
            _matchup_row(PAIR_LABELS[o.key], o, off_line, d, def_line, m.teams, (off_side, def_side))
            for o, d in PAIRS)
        return (f'<div class="mu-group">{head(esc(off_side.short) + " offense", esc(def_side.short) + " defense")}'
                f"{rows}</div>")

    situational = "".join(
        _matchup_row(s.label, s, m.away, s, m.home, m.teams, (away, home))
        for s in SITUATIONAL if s.key in m.away.values and s.key in m.home.values)
    through = f" through {esc(m.through)}" if m.through else ""
    sacks = ("College counts sack yardage as rushing, as the NCAA does."
             if card.sport == "ncaaf" else "Passing yards are net of sack yardage, as the NFL counts them.")
    return f"""<p class="note">Season to date{through}: {esc(away.short)} {_plural(m.away.games, "game")},
  {esc(home.short)} {_plural(m.home.games, "game")}. Ranks are among {m.teams} {esc(m.universe)}, 1st the best;
  the crest marks which side ranks better on each line.</p>
{group(away, m.away, home, m.home)}
{group(home, m.home, away, m.away)}
<div class="mu-group">{head(esc(away.short), esc(home.short))}
  <div class="mu-sub">Situational</div>{situational}</div>
<p class="note top-gap">Figures come from completed games only, so every one was known before kickoff. They are
  raw, not adjusted for opponents - All drivers has Atlas's adjusted view. {esc(sacks)}</p>"""


def _open_grade(card: Card) -> str:
    return _panel("How this grade was computed",
                  "the four things that set the letter, out of a hundred",
                  _s5_grade(card, bare=True))


def _open_drivers(card: Card) -> str:
    return _panel("All drivers",
                  f"all {len(card.drivers)} things the model is reading, and how "
                  "each team ranks against the rest of the country",
                  _s6_drivers(card, bare=True))


def _open_movement(card: Card) -> str:
    return _panel("Market movement",
                  "how far the market has moved since the number opened, "
                  "and which way",
                  _s7_market_intelligence(card, bare=True))


def _open_reliability(card: Card, bands: dict, overall_band) -> str:
    return _panel("Reliability record",
                  "what Atlas claimed and what it delivered, across the "
                  "seasons it never saw while being built",
                  _s8_reliability(card, bands, overall_band, bare=True))


def _s2_market(card: Card, *, bare: bool = False) -> str:
    spread, total = card.spread, card.total
    fav, dog = card.favorite, (card.home if card.favorite is card.away else card.away)
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
    if card.projection is None:
        return ""
    p = card.projection
    fav = card.model_favorite
    score = f"{card.projected_away:.1f} – {card.projected_home:.1f}"
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
        <div class="stat-value">{esc(fav.abbr)} {minus(-abs(card.model_margin))}</div>
        <div class="stat-note">market {minus(-abs(card.spread.current)) if card.spread.current is not None else "—"}</div></div>
      <div class="stat"><div class="stat-label">Projected total</div>
        <div class="stat-value">{num(card.model_total)}</div>
        <div class="stat-note">market {num(card.total.current)} · 80% range {p.total_lo:.0f}–{p.total_hi:.0f}</div></div>
    </div>
    <div class="grid-3 divided">
      <div class="stat"><div class="stat-label">{esc(win_side.short)} win probability</div>
        <div class="stat-value">{pct(win_value)}</div>
        <div class="stat-note">from the score grid</div></div>
      <div class="stat"><div class="stat-label">{over_label}</div>
        <div class="stat-value">{pct(over_value)}</div>
        <div class="stat-note">at the current total of {num(card.total.current)}</div></div>
      <div class="stat"><div class="stat-label">Most likely score</div>
        <div class="stat-value">{p.top_away}–{p.top_home}</div>
        <div class="stat-note">{pct(p.top_p)} of the grid — one cell of 6,400</div></div>
    </div>
  </div>
  <div class="disclosure top-gap">
    <b>How this number is made.</b> Every FBS team starts the season at a
    preseason expectation built from last season's ratings, roster talent,
    recruiting, returning production and the coaching situation. After every
    game a filter updates each team's offense and defense, opponent-adjusted,
    and the two teams' numbers meet here with the home advantage. The total
    adds the teams' pace and the wind. The market is never an input; it is
    shown so you can see where Atlas differs and read why.
  </div>"""
    if bare:
        return inner
    return f"""<section class="section">
  <div class="section-head"><h2>Atlas projection</h2>
    <span class="note">Atlas's own number · out-of-sample model</span></div>
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
         f"{esc(card.model_favorite.abbr)} {minus(-abs(card.model_margin)) if card.model_margin is not None else '—'}",
         f"{esc(card.favorite.abbr)} {minus(-abs(card.spread.current)) if card.spread.current is not None else '—'}",
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
    {table(["Measure", "Atlas model", "Market", "Difference"], rows_)}
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
    <span class="note">model minus market</span></div>
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
    conditions = "".join(
        f'<p class="note top-gap-sm">{esc(note)}</p>' for note in g.condition_notes)
    inner = f"""  <div class="{_panel_card(bare)}">
    <div class="grade-wrap">
      <div class="grade {g.tone}">{g.letter}<small>{g.score:.0f}</small></div>
      <div><h3>{esc(title)}</h3>
        <p class="note top-gap-sm">{esc(g.headline)}</p></div>
    </div>
    <div class="card-pad divided">
      <div class="meter">{meters}</div>
      <p class="note top-gap">Atlas sits <b>{g.disagreement:.1f} points</b> from
        the market. The calibration curve, fitted to every completed season
        out of sample, expects cards at that distance to fall <b>{abs(g.expected_gap):.1%}</b>
        short of what they claim — which is where the calibration component
        above comes from.</p>
      {conditions}
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
        <p class="note top-gap-sm">Two series, labeled directly. The widening
          gap is why Atlas grades large disagreements <em>down</em>.</p>
      </div>
      <div>
        <h3>This band, {seasons_word(band)}</h3>
        {table(["Measure", "This band", "All cards"], rows_)}
        <div class="disclosure top-gap">
          <b>Read the gap, not the claim.</b> Atlas's raw confidence numbers run
          high — a claimed {pct(band.claimed, 0)} has historically delivered
          {pct(band.realised, 0)}. The grade already corrects for this. The
          claim is shown so the correction is visible rather than hidden.
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
        # the scale are labeled and the middle is left to the marker.
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


#: How many games the "next kickoffs" section shows.
NEXT_KICKOFFS = 5

#: The grade sections, and the caption each one carries. The caption is not
#: decoration: a board grouped by letter reads as a ranking of what to look at
#: first, and the letter does not mean that. Saying what it does mean, on the
#: heading, is the cheapest place to stop the misreading.
GRADE_SECTIONS = (
    (("A+", "A"), "Graded A",
     "Atlas and the market are closely aligned. Reliable numbers — and the "
     "cards where Atlas is adding least."),
    (("B",), "Graded B",
     "A moderate disagreement, in the range where the model's claim and its "
     "realised accuracy stay close."),
    (("C",), "Graded C",
     "A wide disagreement. The model's historical claim starts to run ahead "
     "of what it delivered."),
    (("D", "F"), "Marked down",
     "A large disagreement, in the range where Atlas has been least reliable "
     "across every season it never saw. Atlas marks these down itself."),
)


def _is_rivalry(card: Card, pairs: set) -> bool:
    from atlas.site.data import is_rivalry

    return is_rivalry(card, pairs)


def _views(cards: list[Card], *, dates: bool) -> str:
    """The same games twice, as rows and as tiles; the reader's view decides
    which shows (the stylesheet, and the Tiles/List switch on the board)."""
    rows = "".join(_game_row(c, dates=dates) for c in cards)
    tiles = "".join(_featured_cell(c, filterable=True) for c in cards)
    return (f'<div class="card game-list view-list">{rows}</div>'
            f'<div class="featured view-tiles">{tiles}</div>')


def _board_section(title: str, note: str, cards: list[Card], *,
                   dates: bool = False, tiles: bool = False) -> str:
    """One block of games. Silent when it has nothing in it - an empty section
    with a heading tells a reader the product is broken. ``tiles`` offers the
    block in both views; without it, it is a list in either."""
    if not cards:
        return ""
    games = (_views(cards, dates=dates) if tiles
             else f'<div class="card game-list">{"".join(_game_row(c, dates=dates) for c in cards)}</div>')
    return f"""<section class="section tight">
  <div class="section-head"><h2>{esc(title)}</h2>
    <span class="note">{esc(note)}</span></div>
  {games}
</section>"""


def _grade_block(letters: tuple, label: str, caption: str,
                 cards: list[Card]) -> str:
    block = [c for c in cards if c.grade and c.grade.letter in letters]
    if not block:
        return ""
    block.sort(key=lambda c: (-c.grade.score, c.kickoff))
    return f"""<section class="section tight">
  <div class="section-head"><h2>{esc(label)}</h2>
    <span class="note">{_plural(len(block), "card")}</span></div>
  <p class="note section-caption">{esc(caption)}</p>
  {_views(block, dates=True)}
</section>"""


#: What each sport's board is called, and how its featured row is chosen.
SPORTS = {
    "ncaaf": {"name": "College football", "short": "college", "path": "ncaaf.html",
              "featured": "ranked matchups, highest-grade cards"},
    "nfl": {"name": "NFL", "short": "NFL", "path": "nfl.html",
            "featured": "the highest-rated teams on Atlas's model"},
}

#: How many matchups a featured row shows, on a board and on the home page.
FEATURED = 3


def featured_cards(cards: list[Card], sport: str, n: int = FEATURED) -> list[Card]:
    """The best matchups on a board.

    College: games between ranked teams first, then the grade. The NFL has no
    poll, so its best matchups are the games between the two best teams on
    Atlas's own rating - each side's net, its expected quarterback included -
    then the grade. Graded cards only, where there are any: a featured card
    without a grade is a matchup with half its card missing.
    """
    pool = [c for c in cards if c.grade] or list(cards)

    def score(card: Card) -> float:
        return card.grade.score if card.grade else 0.0

    if sport == "nfl":
        from atlas.site.data import offense_with_quarterback

        def strength(card: Card) -> float:
            p = card.projection
            if p is None or not p.home or not p.away:
                return float("-inf")
            total = 0.0
            for view in (p.home, p.away):
                off, dfn = offense_with_quarterback(view), view.get("def")
                if off is None or dfn is None:
                    return float("-inf")
                total += off + dfn
            return total

        return sorted(pool, key=lambda c: (-strength(c), -score(c), c.kickoff))[:n]
    return sorted(pool, key=lambda c: (-(c.home.rank is not None) - (c.away.rank is not None),
                                       -score(c), c.kickoff))[:n]


def _featured_row(cards: list[Card], sport: str, *, heading: str = "Featured", more: str = "",
                  root: str = "") -> str:
    featured = featured_cards(cards, sport)
    if not featured:
        return ""
    return f"""<section class="section tight">
  <div class="section-head"><h2>{esc(heading)}</h2>
    <span class="note">{esc(SPORTS[sport]["featured"])}</span></div>
  <div class="featured">{"".join(_featured_cell(c, root=root) for c in featured)}</div>
  {more}
</section>"""


def board_page(cards: list[Card], *, sport: str = "ncaaf", rivalries: set | None = None,
               freshness: dict | None = None, teams: dict | None = None, bands: dict | None = None) -> str:
    """Rule 1: the board is the product. One layout for both sports.

    The board is the first thing on the page. No hero, no marketing, no
    summary tiles above the fold — a reader who came for a game sees games,
    and the filters sit in a compact bar that stays with them as they scroll.

    Sections, in order: featured matchups, rivalries (college), the next
    kickoffs, then every card grouped by grade. The grade blocks carry a
    caption saying what the letter means, because a board sorted by a letter
    reads as a ranking of what to look at first and the letter does not mean
    that — the most reliable cards are the ones where Atlas agrees with the
    market, which is to say the ones where Atlas has said least.
    """
    info = SPORTS[sport]
    graded = [c for c in cards if c.grade]
    strong = sum(1 for c in graded if c.grade.letter in ("A+", "A"))
    weak = sum(1 for c in graded if c.grade.low)

    conferences = sorted({
        conf for card in cards for conf in (card.home.conference, card.away.conference) if conf
    })
    conf_select = ""
    if conferences:
        options = "".join(f'<option value="{esc(c)}">{esc(c)}</option>' for c in conferences)
        conf_select = f"""<select id="conf" class="select" aria-label="Filter by conference">
    <option value="">All conferences</option>{options}
  </select>"""

    rivalry_cards = [c for c in cards if rivalries and _is_rivalry(c, rivalries)]
    upcoming = sorted(cards, key=lambda c: c.kickoff)[:NEXT_KICKOFFS]
    grade_blocks = "".join(
        _grade_block(letters, label, caption, cards)
        for letters, label, caption in GRADE_SECTIONS
    )
    week = eastern(min(c.kickoff for c in cards)).strftime("Week of %-d %B") if cards else "This week"

    if cards:
        board = f"""<div class="board-bar" id="controls">
  <input class="search" type="search" id="q" placeholder="Search teams"
         aria-label="Search games" autocomplete="off">
  {conf_select}
  <span class="bar-break" aria-hidden="true"></span>
  <button class="filter" data-grade="" aria-pressed="true">All</button>
  <button class="filter" data-grade="A" aria-pressed="false">A &amp; up</button>
  <button class="filter" data-grade="B" aria-pressed="false">B &amp; up</button>
  <button class="filter" data-grade="low" aria-pressed="false">Marked down</button>
  <div class="view-toggle" role="group" aria-label="Show games as">
    <button class="view-btn" data-view="tiles" aria-pressed="false">Tiles</button>
    <button class="view-btn" data-view="list" aria-pressed="false">List</button>
  </div>
</div>
<p class="note board-count" id="count" aria-live="polite"></p>

{_featured_row(cards, sport)}

{_board_section("Rivalries", "played in at least eight of the last nine seasons", rivalry_cards, tiles=True)}

{_board_section("Next kickoffs", "the next five games on the board", upcoming, dates=True, tiles=True)}

{grade_blocks}"""
    else:
        board = f"""<div class="card card-pad banner-low">
  <p class="note banner-text">No {esc(info["short"])} games are scheduled in the next week, or the warehouse has not
    been built yet. The model, its record and how it is graded are on <a href="research.html">Research</a>.</p>
</div>"""

    if sport == "nfl":
        disclosure = """<b>How the NFL number is made.</b> Every team's offense and defense are carried from
  season to season, regressed toward the mean, and updated after every game by a filter that adjusts for the
  opponent; a quarterback state travels with the player; the home advantage is fitted, not assumed; the total
  adds the wind. The market is never an input. Measured out of sample on 2023-2025, the number is closer to the
  final margin than Elo and not as close as the closing line, and the grade is built from that record."""
    else:
        disclosure = f"""<b>About this week's numbers.</b> It is week {cards[0].week if cards else ""},
  so team profiles are still shrunk toward last season and efficiency figures move a lot between games."""
    disclosure += """ Atlas publishes research, analytics and market context; it does not publish selections,
  does not size anything and does not project returns."""

    # A reader's Tiles/List choice is applied before the games paint, so a
    # returning reader never sees the other view flash first.
    body = f"""<script>try{{var v=localStorage.getItem("atlas-view");if(v==="tiles"||v==="list")document.documentElement.dataset.view=v}}catch(e){{}}</script>
<div class="board-head">
  <h1>{esc(info["name"])}</h1>
  <span class="board-note">{esc(week)} · {_plural(len(cards), "card")} · {strong} graded A or better ·
    {weak} marked down</span>
</div>

{freshness_badge(("Projection built", (freshness or {}).get("projection", "")),
                 ("Market updated", (freshness or {}).get("market", "")))}

<p class="new-here board-new-here">Every game gets a card — and a letter for how
  much that card's information has historically been worth.
  <a href="about.html">How to read one</a></p>

{board}

{_team_strip(teams) if sport == "nfl" else ""}

<div class="disclosure top-gap">
  {disclosure}
</div>

{games_blob(cards)}
<script src="{asset("atlas.js")}" defer></script>"""

    description = (
        f"Every {info['short']} game this week: the market number, the Atlas "
        f"projection, and a grade for how much each card is worth. "
        f"{len(cards)} cards, {weak} marked down."
    )
    title = f"{info['name']} cards this week | Atlas"
    return layout(title=title, body=body, active=sport, description=description,
                  canonical=info["path"], social=social_tags(title=title, description=description,
                                                             url=info["path"]))


def nfl_page(cards: list[Card] | None = None, *, bands: dict | None = None,
             freshness: dict | None = None, teams: dict | None = None) -> str:
    """The NFL board: the college board's layout, from the NFL's own model."""
    return board_page(cards or [], sport="nfl", freshness=freshness, teams=teams)


def homepage(cards: list[Card], nfl_cards: list[Card] | None = None, *, bands: dict | None = None,
             rivalries: set | None = None, freshness: dict | None = None) -> str:
    """The front door: the best matchups in each sport, and the way to every game.

    Three of each, chosen the way each board chooses its featured row, with a
    link to the full board under them. Everything else lives on the boards.
    """
    nfl_cards = nfl_cards or []
    sections = []
    for sport, block in (("ncaaf", cards), ("nfl", nfl_cards)):
        info = SPORTS[sport]
        if block:
            more = (f'<p class="more-link"><a class="button ghost" href="{info["path"]}">'
                    f'All {_plural(len(block), info["short"] + " game")} this week</a></p>')
            sections.append(_featured_row(block, sport, heading=info["name"], more=more))
        else:
            sections.append(f"""<section class="section tight">
  <div class="section-head"><h2>{esc(info["name"])}</h2></div>
  <p class="note">No {esc(info["short"])} games are scheduled in the next week.</p>
</section>""")
    first = min((c.kickoff for c in [*cards, *nfl_cards]), default=None)
    week = eastern(first).strftime("Week of %-d %B") if first else "This week"
    total = len(cards) + len(nfl_cards)
    body = f"""<div class="board-head">
  <h1>This week's best matchups</h1>
  <span class="board-note">{esc(week)} · {_plural(total, "card")} across college football and the NFL</span>
</div>

{freshness_badge(("Updated", (freshness or {}).get("board", "")))}

<p class="new-here board-new-here">Every game gets a card: what the market says, what Atlas
  projects, and a letter for how much that card's information has historically been worth.
  <a href="about.html">How to read one</a></p>

{"".join(sections)}

{games_blob([*featured_cards(cards, "ncaaf"), *featured_cards(nfl_cards, "nfl")])}
<div class="disclosure top-gap">
  <b>Why these games.</b> College matchups between ranked teams come first; in the NFL, the games between
  the highest-rated teams on Atlas's own model. The grade breaks ties. Being featured says a game is a big
  one, not that its card is worth more: Atlas publishes research, analytics and market context, and it
  does not publish selections.
</div>"""
    description = (f"This week's best college football and NFL matchups: the market number, the Atlas "
                   f"projection, and a grade for how much each card is worth. {total} cards.")
    return layout(title="Atlas Sports Intelligence — this week's college football and NFL cards",
                  body=body, active="home", description=description, canonical="",
                  social=social_tags(title="Atlas Sports Intelligence", description=description, url=""))


def scoreboard_page() -> str:
    """My scoreboard: the games a reader follows, with live scores.

    Nothing about it is on the server. The list lives in the reader's browser,
    stored from the page the game was followed on, and the scores come to it
    straight from ESPN's public scoreboard. It is a way to keep up with games
    without leaving - no record, no tally, no projection and nothing about the
    market.
    """
    body = """<div class="board-head">
  <h1>My scoreboard</h1>
  <span class="board-note">The games you follow, with live scores</span>
</div>

<p class="note" id="scores-status" aria-live="polite"></p>

<div id="scoreboard" class="scoreboard"></div>

<div class="card card-pad" id="scores-empty">
  <p class="note banner-text">You are not following any games yet. Tap <b>☆ Follow</b> on any game on the
    <a href="ncaaf.html">NCAAF</a> or <a href="nfl.html">NFL</a> board, or on a card, and it appears here
    with its live score.</p>
</div>

<div class="disclosure top-gap">
  <b>Saved on this device.</b> The games you follow are kept in this browser only - Atlas has no
  accounts and never sees the list. Scores come to your browser directly from ESPN's public scoreboard and
  refresh every minute while a game you follow is on. A game drops off four days after it is played.
</div>"""
    description = "Follow games from the Atlas boards and see their live scores in one place."
    return layout(title="My scoreboard | Atlas", body=body, active="scores",
                  description=description, canonical="scoreboard.html")


def player_name(name) -> str:
    """A person's or a place's name, marked so the launch audit reads it as a
    name: a quarterback called Lock, a receiver called Kelly or Kelly/Shorts
    Stadium is not vocabulary."""
    return f'<span class="pn">{esc(name)}</span>'


#: On every DFS page (plan §1): who DFS is for, and where to get help. The
#: audit fails a DFS page without it.
DFS_NOTE = """<b>DFS is gambling for adults.</b> DraftKings contests are open only to adults (18, 19 or 21 and
  older, by state) in the states where DraftKings offers them. If it stops being fun, help is at
  <a href="https://www.draftkings.com/responsible-gaming" rel="noopener">DraftKings' responsible gaming
  page</a> and on 1-800-GAMBLER."""


def _dfs_num(value, digits: int = 1) -> str:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "–"
    return "–" if v != v else f"{v:.{digits}f}"


def _dfs_pct(value) -> str:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "–"
    return "–" if v != v else f"{round(v * 100):d}%"


def _dfs_table(players: list[dict]) -> str:
    rows = []
    for p in players:
        status = f' <span class="dfs-status">{esc(p["status"])}</span>' if p.get("status") else ""
        rows.append(
            f'<tr data-pos="{esc(p["position"])}"><td class="lead">{player_name(p["name"])}{status}</td>'
            f'<td>{esc(p["position"])}</td><td>{esc(p["team"])}</td><td>{esc(p.get("opponent") or "")}</td>'
            f'<td>${int(p["salary"]):,}</td><td><b>{_dfs_num(p["projection"])}</b></td>'
            f'<td>{_dfs_num(p["low"])}–{_dfs_num(p["high"])}</td><td>{_dfs_pct(p.get("p_play"))}</td></tr>')
    return ('<div class="table-scroll"><table class="rows dfs-table"><thead><tr><th>Player</th><th>Pos</th>'
            '<th>Team</th><th>Opp</th><th>Salary</th><th>Projection</th><th>Range</th><th>Plays</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div>')


def _dfs_when(iso) -> str:
    from datetime import datetime

    try:
        return stamp(datetime.fromisoformat(str(iso).replace("Z", "+00:00")))
    except (TypeError, ValueError):
        return ""


def _dfs_started(iso) -> bool:
    from datetime import datetime, timezone

    try:
        return datetime.fromisoformat(str(iso).replace("Z", "+00:00")) <= datetime.now(timezone.utc)
    except (TypeError, ValueError):
        return False


def _dfs_board(slate: dict | None, players: list[dict]) -> str:
    if not slate or not players:
        return ('<div class="card card-pad"><p class="note banner-text">No slate is posted yet. DraftKings '
                'posts the next Sunday main slate early in the week, and its projections appear here with the '
                'next morning\'s refresh.</p></div>')
    likely = [p for p in players if not (float(p.get("p_play") or 0) < 0.25)]
    unlikely = [p for p in players if float(p.get("p_play") or 0) < 0.25]
    head = (f'<p class="freshness"><span class="stamp"><b>Projected</b> {esc(_dfs_when(slate.get("projected_at")))}'
            f'</span><span class="stamp"><b>First kickoff</b> {esc(_dfs_when(slate.get("starts_at")))}</span></p>')
    if _dfs_started(slate.get("starts_at")):
        head += ('<p class="note">This slate has started. Its projections are shown as they were published before '
                 'the first kickoff; the next slate replaces them once DraftKings posts it.</p>')
    buttons = "".join(
        f'<button type="button" class="dfs-chip" data-filter="{p}" aria-pressed="{"true" if p == "All" else "false"}">'
        f'{p}</button>' for p in ("All", "QB", "RB", "WR", "TE", "DST"))
    more = ""
    if unlikely:
        more = (f'<details class="card card-pad top-gap dfs-more"><summary>Players less likely to play '
                f'({len(unlikely)})</summary>{_dfs_table(unlikely)}</details>')
    return (f'{head}\n<div class="dfs-filters" role="group" aria-label="Position">{buttons}</div>\n'
            f'<div class="card card-pad">{_dfs_table(likely)}</div>\n{more}')


def _dfs_history(history: dict | None) -> str:
    if not history or not history.get("positions"):
        return '<p class="note">The walk-forward record is published with the model.</p>'
    rows = "".join(
        f'<tr><td class="lead">{esc(pos)}</td><td>{r["player_weeks"]:,}</td><td>{r["mae"]:.2f}</td>'
        f'<td>{r["baseline_mae"]:.2f}</td><td>{r["rank"]:.3f}</td><td>{r["coverage"]:.0%}</td>'
        f'<td>{r["salary_era_rank"]:.3f}</td><td>{r["salary_rank"]:.3f}</td></tr>'
        for pos, r in history["positions"].items())
    return f"""<div class="table-scroll"><table class="rows dfs-record">
  <thead><tr><th>Position</th><th>Player-weeks</th><th>Miss</th><th>Recent form's miss</th><th>Ranking</th>
    <th>In range</th><th>Ranking {esc(history['salary_seasons'])}</th><th>Salary's ranking</th></tr></thead>
  <tbody>{rows}</tbody>
</table></div>
<p class="note">Each team's regulars - its top quarterback, two running backs, three receivers, tight end and
  defense - every season {esc(history['seasons'])}, each projected by a model fitted only on the seasons before
  it. <b>Miss</b> is the average distance from the projection to the points scored; <b>recent form's miss</b> is
  the same for the player's recent average, the simplest alternative. <b>Ranking</b> is how well the projections
  order each position's players in a week (a correlation: 1 is perfect, 0 is chance). <b>In range</b> is how
  often the points landed inside the range, built to hold four outcomes in five. DraftKings' own salaries exist
  for {esc(history['salary_seasons'])}, and the last two columns compare the rankings there.</p>"""


def _dfs_live(live: dict | None) -> str:
    if live and live.get("slates"):
        n = live["slates"]
        return (f"<p>{n} slate{'s' if n != 1 else ''} graded, {live['players']:,} players: an average miss of "
                f"{live['mae']:.2f} points, {live['coverage']:.0%} inside their range, a ranking of "
                f"{_dfs_num(live['rank'], 3)}. Every priced player counts, including those who did not play and "
                f"scored zero.</p>")
    return ("<p>The live record starts with the first slate Atlas publishes: its projections are kept as they "
            "stood before kickoff and graded against the points scored once the games are played.</p>")


def dfs_page(slate: dict | None, players: list[dict], *, history: dict | None, live: dict | None) -> str:
    """The public DFS area (`docs/MODEL_PLAN_DFS.md`, step 7): each player's
    projection with its range and chance of playing, and the model's record.

    The reader decides; the page arranges. No lineup is shown, nothing is
    featured or highlighted, and the list is every priced player by
    projection. Walled off from the cards, which keep their promise.
    """
    body = f"""<div class="board-head">
  <h1>DFS projections</h1>
  <span class="board-note">DraftKings NFL Classic · Sunday main slate</span>
</div>

<div class="disclosure dfs-what">
  <b>What this page is.</b> Every player DraftKings has priced for the slate, with Atlas's projection of his
  DraftKings points, a range that should hold four outcomes in five, and the chance he plays at all. It is a set
  of numbers, not a lineup: Atlas does not build or feature one here, and nothing on this page promises anything
  about a contest. {DFS_NOTE}
</div>

{_dfs_board(slate, players)}

<section class="section" id="record">
  <div class="section-head"><h2>The record</h2></div>
  <div class="card card-pad prose">
    <h3>Live</h3>
    {_dfs_live(live)}
    <h3>Walk-forward, before launch</h3>
    {_dfs_history(history)}
  </div>
</section>

<section class="section" id="how">
  <div class="section-head"><h2>How the projections work</h2></div>
  <div class="card card-pad prose">
    <p>Each projection starts from the player's recent DraftKings scoring and corrects it with what is known before
      kickoff: his share of his team's snaps, targets, carries and red-zone touches; the game as Atlas's own NFL model
      sees it; the injury report and the depth chart, including the targets and carries a teammate's absence leaves
      behind; and, for a defense, its pass rush and takeaways against the offense it faces. Unlike the game cards,
      the DFS model also reads the betting market's implied team totals - measured honestly, they know more about
      how many points a team will score than Atlas's game model does.</p>
    <p>The projection is an average that already counts the chance a player does not play; <b>Plays</b> is that
      chance. The <b>Range</b> runs from the 10th to the 90th percentile, and it is lopsided on purpose: DraftKings
      points have a floor near zero and occasional very big touchdown weeks. No outside projections are used.</p>
  </div>
</section>

<div class="disclosure top-gap">
  <b>Walled off from the cards.</b> On its game cards Atlas does not publish selections - research, analytics and
  market context only - and this page does not change that. {DFS_NOTE}
</div>
<script src="{asset("dfs.js")}" defer></script>"""
    description = ("DraftKings NFL projections from Atlas's own model: every priced player with a range, the "
                   "chance he plays, and the model's out-of-sample record.")
    return layout(title="DFS projections | Atlas", body=body, active="dfs", description=description,
                  canonical="dfs.html")


def record_page(sports: dict[str, dict], *, since: str, grades: dict[str, list[dict]] | None = None,
                grades_since: str | None = None) -> str:
    """The public model record (`atlas/site/record.py`): every projection Atlas
    published before kickoff, against the final score, with the market's
    pre-kickoff number beside it where Atlas captured one. Facts only: every
    graded game is in it, nothing is chosen or highlighted, and nothing says
    what to do with it."""
    names = {"ncaaf": "College football", "nfl": "NFL"}
    parts = []
    for sport in ("ncaaf", "nfl"):
        data = sports.get(sport) or {}
        s = data.get("summary") or {"games": 0}
        parts.append(f'''<section class="section" id="{sport}">
  <div class="section-head"><h2>{names[sport]}</h2></div>
  <div class="card card-pad prose">{_record_summary(s)}</div>
  {_record_grades((grades or {}).get(sport), grades_since) if grades is not None else ""}
  {_record_weeks(data.get("weekly") or [])}
  {_record_games(data.get("latest") or [], s.get("games", 0))}
</section>''')
    body = f"""<div class="board-head">
  <h1>Model record</h1>
  <span class="board-note">Every projection, graded against the final score</span>
</div>

<div class="disclosure">
  <b>What this page is.</b> Each game's projection as Atlas published it before kickoff, the final score, and how
  far apart they were - with the market's number from before kickoff beside it where Atlas captured one. Every game
  Atlas projected before kickoff and has a final score for is here; none is left out and none is featured. The record
  starts {esc(since)}, with the first games Atlas projected before kickoff.
</div>

{"".join(parts)}

<section class="section" id="how">
  <div class="section-head"><h2>How the record is kept</h2></div>
  <div class="card card-pad prose">
    <p><b>Before kickoff, and only then.</b> A projection counts only if it was made before its game kicked off. Each
      refresh records a new projection for every game still to be played; a change to the model adds a new row rather
      than replacing one, and a game in progress is never projected again. A game whose only projection was made after
      kickoff is left out, not graded.</p>
    <p><b>The miss.</b> How far the projected margin (home points less away points) and the projected total were from
      the final ones, in points. <b>Winner</b> is how often the side Atlas had ahead won; a projected or final tie is
      not counted.</p>
    <p><b>The grades.</b> Each card's grade is kept as it was last published before kickoff, with the spread it was
      graded against. <b>Claimed</b> is Atlas's own probability, on that card, that the final margin would land on its
      side of that spread; <b>realised</b> is how often it did, a push counting half; the <b>gap</b> is realised less
      claimed. The grade's claim is that higher letters carry smaller gaps: an A card's probability should sit nearer
      what happens than a D card's. It is a calibration record, the same measure as the seasons on
      <a href="research.html">Research</a>, and not a count of results.</p>
    <p><b>The market.</b> DraftKings' last margin and total before kickoff, as Atlas captured them, graded the same
      way on the same games. A game with no captured line is graded for Atlas alone, and the comparison uses only the
      games that have both.</p>
    <p><b>Before this season.</b> How the models did on past seasons they never saw is on <a href="research.html">
      Research</a>; this page is the live record only.</p>
    <p><a href="record.csv" download>Download every graded game (CSV)</a></p>
  </div>
</section>"""
    description = ("Atlas's model record: every projection published before kickoff, graded against the final "
                   "score, with the market's pre-kickoff number beside it.")
    return layout(title="Model record | Atlas", body=body, active="record", description=description,
                  canonical="record.html")


def _record_grades(rows: list[dict] | None, since: str | None) -> str:
    """Claimed against realised, by grade letter (`atlas/site/grade_record.py`)."""
    start = f" It began on {esc(since)}; nothing earlier was kept." if since else ""
    total = next((r for r in rows or [] if r["letter"] == "All"), None)
    if not total or not total["cards"]:
        return ('<div class="card card-pad top-gap prose"><h3>By grade</h3><p>No graded card yet. Each card\'s '
                'grade is kept as it was published before kickoff, and counts here once its game is final.'
                f'{start}</p></div>')
    body = []
    for r in rows:
        if not r["cards"]:
            body.append([esc(r["letter"]), "0", "—", "—", "—"])
            continue
        few = ' <span class="note">few</span>' if r["few"] and r["letter"] != "All" else ""
        label = f"<b>{esc(r['letter'])}</b>" if r["letter"] == "All" else esc(r["letter"])
        body.append([label, f"{r['cards']}{few}", pct(r["claimed"]), pct(r["realised"]),
                     signed(r["gap"] * 100)])
    return ('<div class="card card-pad top-gap record-table"><h3>By grade</h3>'
            f'<p class="note">Each card\'s grade as last published before kickoff: Atlas\'s claimed probability on '
            f'the spread against how often it happened.{start} A letter with few cards is noise, not a reading.</p>'
            + table(["Grade", "Cards", "Claimed", "Realised", "Gap, pts"], body) + "</div>")


def _record_summary(s: dict) -> str:
    if not s.get("games"):
        return "<p>No game is graded yet. The first games are graded the morning after they are final.</p>"
    lines = [f"<p><b>{s['games']}</b> games graded. Atlas's projected margin was <b>{num(s['margin_miss'])}</b> "
             f"points from the final one on average, its total <b>{num(s['total_miss'])}</b>; the side it had ahead "
             f"won <b>{pct(s['winner_right'], 0)}</b> of {s['winner_games']} games.</p>"]
    if s.get("with_market"):
        lines.append(f"<p>On the {s['with_market']} games with a captured market margin, Atlas's margin was "
                     f"{num(s['atlas_margin_miss_there'])} points from the final one on average and the market's "
                     f"{num(s['market_margin_miss'])}; Atlas's was the closer of the two in {s['atlas_closer']} of "
                     f"{s['closer_of']} games where they differed.")
        if s.get("with_market_total"):
            lines[-1] += (f" On the {s['with_market_total']} with a captured market total, Atlas's total missed by "
                          f"{num(s['atlas_total_miss_there'])} and the market's by {num(s['market_total_miss'])}.")
        lines[-1] += "</p>"
    return "".join(lines)


def _pair(a, b) -> str:
    """"12.4 · 12.9": a margin miss and a total miss, together."""
    return "—" if a is None and b is None else f"{num(a)} · {num(b)}"


def _record_weeks(weeks: list[dict]) -> str:
    if not weeks:
        return ""
    rows = [[f"Wk {w['week']}<br><span class=\"note\">{w['games']} games</span>",
             _pair(w["margin_miss"], w["total_miss"]), pct(w["winner_right"], 0),
             _pair(w.get("market_margin_miss"), w.get("market_total_miss"))] for w in weeks]
    return ('<div class="card card-pad top-gap record-table"><h3>By week</h3>'
            '<p class="note">Misses are margin · total, in points, averaged over the week.</p>'
            + table(["Week", "Atlas miss", "Winner", "Market miss"], rows) + "</div>")


def _record_games(games: list[dict], total: int) -> str:
    if not games:
        return ""
    rows = [[f"{esc(g['away'] or '?')} @ {esc(g['home'] or '?')}<br><span class=\"note\">projected "
             f"{num(g['proj_away'])}–{num(g['proj_home'])} · final {g['final_away']}–{g['final_home']}</span>",
             _pair(g["margin_miss"], g["total_miss"]), _pair(g.get("market_margin_miss"), g.get("market_total_miss"))]
            for g in games]
    shown = (f"The latest {len(games)} of {total}; every one is in the download below."
             if total > len(games) else "Every graded game.")
    return (f'<div class="card card-pad top-gap record-table"><h3>Game by game</h3><p class="note">{shown} Scores '
            'are away–home; misses are margin · total, in points.</p>'
            + table(["Game", "Atlas miss", "Market miss"], rows) + "</div>")


def owner_page(record: dict | None) -> str:
    """The owner's DFS page: ciphertext and the means to open it, nothing else.

    ``record`` is `atlas/dfs/owner.py`'s output - an encrypted box, or the
    reason there is none. The lineups exist in readable form only in the
    browser that typed the passphrase. Not linked from the site, not in the
    sitemap, and asks search engines not to index it.
    """
    import json

    record = record or {"box": None, "reason": "Nothing has been built yet."}
    island = json.dumps({"box": record.get("box")}).replace("</", "<\\/")
    built = record.get("built_at")
    when = ""
    if built:
        from datetime import datetime

        try:
            when = f" Last built {esc(stamp(datetime.fromisoformat(built)))}."
        except (TypeError, ValueError):
            when = ""
    if record.get("box"):
        state = f"<p class=\"note\">This week's lineups, encrypted.{when}</p>"
    else:
        state = f"<p class=\"note\">{esc(record.get('reason') or 'Nothing to open.')}{when}</p>"
    body = f"""<div class="board-head">
  <h1>Owner</h1>
  <span class="board-note">Private DFS lineups · opened in this browser only</span>
</div>

<div class="card card-pad">
  {state}
  <form id="owner-form" class="owner-form" autocomplete="on">
    <input type="text" name="username" value="atlas-owner" autocomplete="username" hidden>
    <label for="owner-pass">Passphrase</label>
    <input id="owner-pass" name="password" type="password" autocomplete="current-password" required>
    <button class="button" type="submit">Open</button>
  </form>
  <p class="note" id="owner-status" aria-live="polite"></p>
</div>

<div id="owner-out"></div>

<div class="disclosure top-gap">
  <b>What this page is.</b> The page holds only ciphertext. The passphrase you type derives the key here, in
  this browser, and the lineups are decrypted into this tab's memory - nothing is stored or sent. They are the
  most projected points under DraftKings' cap from Atlas's DFS model; they promise nothing about any contest.
  {DFS_NOTE}
</div>

<script type="application/json" id="owner-box">{island}</script>
<script src="../{asset("owner.js")}" defer></script>"""
    html = layout(title="Owner | Atlas", body=body, depth=1, description="Private page.",
                  canonical=None)
    return html.replace("<head>\n", "<head>\n<meta name=\"robots\" content=\"noindex, nofollow\">\n", 1)


def _row_crests(card: Card, root: str = "") -> str:
    return (f'<span class="row-crests">{_logo(card.away, size="small", root=root)}'
            f'{_logo(card.home, size="small", root=root)}</span>')


def _follow_button(card: Card, *, compact: bool = False) -> str:
    """Follow a game onto My scoreboard. Hidden until the script runs: without
    it the button could do nothing, and a button that does nothing is a bug."""
    cls = "follow compact" if compact else "follow"
    return (f'<button class="{cls}" type="button" data-follow="{card.game_id}" aria-pressed="false" hidden '
            f'aria-label="Follow {esc(card.title)} on My scoreboard">'
            f'<span class="follow-icon" aria-hidden="true">☆</span><span class="follow-text">Follow</span></button>')


def _game_record(card: Card) -> dict:
    """What My scoreboard needs to show a followed game without this page:
    stored in the reader's browser when they follow it.

    Who, when and where the card is - never Atlas's numbers. A machine-readable
    projection is one copy-paste from being a feed of numbers with no card
    around them (the same rule as the structured data), and a scoreboard needs
    the score, not the projection."""
    def side(s) -> dict:
        return {"abbr": s.abbr, "short": s.short, "logo": f"assets/logos/{s.logo}" if s.logo else None}

    return {
        "id": str(card.game_id), "sport": card.sport, "title": card.title,
        "kickoff": card.kickoff.isoformat(), "date": eastern(card.kickoff).strftime("%Y%m%d"),
        "when": day_clock(card.kickoff), "path": card.path,
        "away": side(card.away), "home": side(card.home),
    }


def games_blob(cards: list[Card]) -> str:
    """Every game on a page, for the Follow buttons, as one JSON block."""
    import json

    payload = json.dumps({str(c.game_id): _game_record(c) for c in cards}, separators=(",", ":"))
    payload = payload.replace("</", "<\\/")          # a team name can never close the script
    return f'<script type="application/json" id="atlas-games">{payload}</script>'


def _game_attrs(card: Card) -> str:
    """What the board's filters read, on a row and on a tile alike: the game,
    the text a search matches, the conferences and the grade."""
    grade_letter = card.grade.letter if card.grade else ""
    grade_key = ("low" if card.grade and card.grade.low
                 else grade_letter.rstrip("+") if grade_letter else "")
    haystack = " ".join(filter(None, [
        card.home.name, card.away.name, card.home.short, card.away.short,
        card.home.abbr, card.away.abbr, card.home.conference, card.away.conference,
    ])).lower()
    confs = "|".join(filter(None, [card.home.conference, card.away.conference]))
    return (f'data-game="{card.game_id}" data-search="{esc(haystack)}" data-conf="{esc(confs)}" '
            f'data-grade="{esc(grade_key)}"')


def _started_chip(card: Card) -> str:
    """"Game started", shown by the browser from kickoff on.

    A card leaves the site at the first build after kickoff, but a build can
    be fifteen minutes away on a game day and longer when a scheduled run is
    late, and a page already open does not rebuild at all. Until then the
    game still reads as upcoming, with a market that is no longer the market.
    So the chip is rendered hidden with the kickoff time, and games.js shows
    it once the reader's clock passes kickoff. Without the script nothing
    shows, which is the page as it was.

    Not "locked": that is the one word for this a reader would expect, and it
    is also a tout's word (audit_site.FORBIDDEN)."""
    return (f'<span class="started-chip" data-kickoff="{esc(card.kickoff.isoformat())}" hidden '
            f'title="Kicked off {esc(day_clock(card.kickoff))}. These numbers are from before '
            f'kickoff and no longer update.">Game started</span>')


def _game_row(card: Card, *, dates: bool = False) -> str:
    """One board row. ``dates`` adds the day, which a section that is not
    grouped by day needs and a day block does not."""
    difference = card.total_difference
    diff_text = (f"Atlas {signed(difference)}" if difference is not None
                 else "no Atlas number")
    # One rank chip for the row, the better of the two: two of them beside a
    # long matchup title was pushing the title into the numbers column.
    best = min((s.rank for s in (card.away, card.home) if s.rank), default=None)
    ranks = f' <span class="rank">#{best}</span>' if best else ""
    when = day_clock(card.kickoff) if dates else clock(card.kickoff)
    meta = " · ".join(filter(None, [when, card.tv]))
    # The row is a container whose title link stretches across it, so the
    # whole row still opens the card and the Follow button is a real button.
    return f"""<div class="game-row" {_game_attrs(card)}>
  <div class="game-main">
    <div class="row-teams">{_row_crests(card)}
      <a class="stretch game-teams" href="{esc(card.path)}">{esc(card.title)}</a>{ranks}</div>
    <div class="game-meta">{esc(meta)} {_started_chip(card)}</div>
  </div>
  <div class="game-right">
    <div class="game-numbers">
      <div class="game-line">{esc(card.spread_text)} · {num(card.total.current)}</div>
      <div class="game-meta">{esc(diff_text)}</div>
    </div>
    {grade_pill(card)}
    {_follow_button(card, compact=True)}
  </div>
</div>"""


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def _featured_cell(card: Card, *, root: str = "", filterable: bool = False) -> str:
    """One matchup tile. ``filterable`` makes it a board tile the search and
    grade filters act on; a featured tile stays put while a reader filters."""
    difference = card.total_difference
    classes = "card card-pad feature game-tile" if filterable else "card card-pad feature"
    attrs = f" {_game_attrs(card)}" if filterable else ""
    return f"""<article class="{classes}"{attrs}>
  <div class="feature-head">{_row_crests(card, root=root)}{grade_pill(card)}</div>
  <h3 class="feature-title"><a class="stretch" href="{root}{esc(card.path)}">{esc(card.title)}</a></h3>
  <p class="note feature-meta">{esc(day_clock(card.kickoff))}{esc(" · " + card.tv if card.tv else "")}
    {_started_chip(card)}</p>
  <div class="feature-nums">
    <div><span class="stat-label">Market</span>
      <span class="feature-num">{esc(card.spread_text)}</span></div>
    <div><span class="stat-label">Total</span>
      <span class="feature-num">{num(card.total.current)}</span></div>
    <div><span class="stat-label">Atlas</span>
      <span class="feature-num">{num(card.model_total)}</span></div>
  </div>
  {_feature_score(card)}
  <div class="feature-end">
    <p class="note feature-foot">Difference {signed(difference)} on the total</p>
    <p class="feature-line">{esc(card.spread_text)} · total {num(card.total.current)}
      <span class="feature-line-diff">Atlas {signed(difference)}</span></p>
    <div class="feature-actions">{_follow_button(card)}
      <span class="details-chip">Details <span aria-hidden="true">→</span></span></div>
  </div>
</article>"""


def _feature_score(card: Card) -> str:
    """Atlas's projected score on a featured tile: away first, as the title
    reads, each to one decimal and named by its abbreviation - the same number
    the card's own projection shows, never rounded to a scoreline."""
    if card.projected_home is None or card.projected_away is None:
        return ""
    return f"""<div class="feature-score">
    <span class="stat-label">Atlas projects</span>
    <span class="feature-score-line"><span>{esc(card.away.abbr)} {num(card.projected_away)}</span>
      <span class="feature-score-dash">–</span><span>{esc(card.home.abbr)} {num(card.projected_home)}</span></span>
  </div>"""


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
    slug = _team_slug(team)
    description = (
        f"{team.name}: opponent-adjusted efficiency, pace and form, all "
        f"point-in-time, with every upcoming Atlas card and its grade."
    )
    return layout(title=f"{team.name} — season profile and Atlas cards",
                  body=body, depth=1, active="ncaaf",
                  description=description,
                  canonical=f"team/{slug}.html",
                  social=social_tags(title=f"{team.name} · Atlas",
                                     description=description,
                                     url=f"team/{slug}.html"),
                  structured=json_ld({
                      "@context": "https://schema.org",
                      "@type": "SportsTeam",
                      "name": team.name,
                      "sport": "American Football",
                      "url": f"{SITE_URL}/team/{slug}.html",
                      **({"memberOf": {"@type": "SportsOrganization",
                                       "name": team.conference}}
                         if team.conference else {}),
                  }))


def nfl_team_page(team, *, cards: list[Card], pool: dict, results: list | None = None,
                  freshness: dict | None = None) -> str:
    """One NFL team: Atlas's rating of it, its expected quarterback, its
    season profile, the cards it is on, and every game this season Atlas
    projected before kickoff beside how it finished.

    The rating and the quarterback are read from the team's next card, so the
    page and the card can never disagree about the same number. The offense
    is the forecast's: the team's own plus its expected starter's, and the
    rank is by that net across every team with a card this week.
    """
    from atlas.site.data import offense_with_quarterback, percentile

    root = "../../"
    upcoming = [c for c in cards if team.team_id in (c.home.team_id, c.away.team_id)]
    views = _nfl_views(cards)
    view = views.get(team.team_id, {})
    offense = offense_with_quarterback(view)
    defense = view.get("def")
    net = offense + defense if offense is not None and defense is not None else None
    nets = sorted((offense_with_quarterback(v) + v["def"] for v in views.values()
                   if offense_with_quarterback(v) is not None and v.get("def") is not None), reverse=True)
    rank_note = f"{_ordinal(nets.index(net) + 1)} of {len(nets)} with a card this week" if net is not None \
        else "not yet rated"
    games = view.get("games")
    qb, qb_pts, qb_sd = view.get("qb"), view.get("qb_pts"), view.get("qb_sd")
    who = possessive(team.short)

    def rating(label: str, value: float | None, note: str) -> str:
        return f"""<div class="stat"><div class="stat-label">{esc(label)}</div>
  <div class="stat-value">{signed(value)}</div>
  <div class="stat-note">{esc(note)}</div></div>"""

    if qb and qb_pts is not None:
        offense_note = f"team {signed(view.get('off'))} · {qb} {signed(qb_pts)}"
        qb_line = (f"<b>Expected starter: {player_name(qb)}.</b> {signed(qb_pts)} of that offense is his (± {num(qb_sd)}), "
                   "and it travels with him: the model rates the quarterback and the team separately and adds "
                   "them for the game. He is the depth chart's first quarterback unless the injury report lists "
                   "him out.")
    elif qb:
        offense_note = "points scored above average"
        qb_line = (f"<b>Expected starter: {player_name(qb)}.</b> The model has not rated him yet; until he plays, the "
                   "offense carries a new quarterback's prior.")
    else:
        offense_note = "points scored above average"
        qb_line = "No expected starter is listed yet."
    sd_def = view.get("sd_def")
    defense_note = (f"± {num(sd_def)} · " if sd_def is not None else "") + "points held below average"

    def stat(metric: str, label: str, note: str, fmt) -> str:
        value = team.metrics.get(metric)
        pct_rank = percentile(pool, metric, value)
        return f"""<div class="stat"><div class="stat-label">{esc(label)}</div>
  <div class="stat-value">{fmt(value)}</div>
  <div class="stat-note">{esc(_ordinal_note(pct_rank, note))}</div></div>"""

    schedule_rows = []
    for card in upcoming:
        opponent = card.away if card.home.team_id == team.team_id else card.home
        prefix = "vs" if card.home.team_id == team.team_id else "at"
        schedule_rows.append([
            esc(eastern(card.kickoff).strftime("%-d %b")),
            f"{prefix} {esc(opponent.short)}",
            esc(card.spread_text),
            num(card.total.current),
            f'<a href="{root}{esc(card.path)}">{grade_pill(card)}</a>',
        ])

    results = results or []
    result_rows = [[
        esc(eastern(r.kickoff).strftime("%-d %b")),
        f"{'vs' if r.home else 'at'} {esc(r.opponent)}",
        signed(r.atlas), signed(r.market) if r.market is not None else "—", signed(r.final, 0),
        "Atlas" if r.market is not None and r.atlas_error < r.market_error
        else "Market" if r.market is not None and r.market_error < r.atlas_error else "Level",
    ] for r in results]
    if results:
        atlas_mae = sum(r.atlas_error for r in results) / len(results)
        paired = [r for r in results if r.market is not None]
        market_mae = sum(r.market_error for r in paired) / len(paired) if paired else None
        summary = (f"Over {_plural(len(results), 'game')}, Atlas missed the final margin by {num(atlas_mae)} "
                   f"points on average" + (f" and the closing line by {num(market_mae)}." if market_mae is not None
                                           else "."))
        record_block = (table(["Date", "Opponent", "Atlas margin", "Closing margin", "Final", "Closer"],
                              result_rows) + f'<p class="note top-gap">{esc(summary)} A handful of games '
                        "says little about a model; the full record is on the Research page.</p>")
    else:
        record_block = ('<p class="note">No completed game this season has a projection Atlas published '
                        "before kickoff yet. Each one is added here after it is played.</p>")

    stamp_line = freshness_badge(("Projection built", (freshness or {}).get("projection", "")),
                                 ("Market updated", (freshness or {}).get("market", "")), root=root)
    evidence = (f"after {_plural(games, 'game')} this season" if games
                else "before any game this season, so it is still mostly last season carried forward")
    body = f"""<div class="card game-head" style="--team-home:{esc(team.colour)};--team-away:#9aa1aa">
  <div class="team-head">
    {_logo(team, size="large", root=root)}
    <div>
      <h1>{esc(team.name)}</h1>
      <p class="sub">{esc(" · ".join(filter(None, ["NFL", team.record])))}</p>
    </div>
  </div>
</div>

<section class="section">
  <div class="section-head"><h2>How Atlas rates them</h2>
    <span class="note">points a game against an average NFL team · {esc(rank_note)}</span></div>
  <div class="card">
    <div class="grid-3">
      {rating("Offense", offense, offense_note)}
      {rating("Defense", defense, defense_note)}
      {rating("Net", net, "offense plus defense")}
    </div>
    <p class="note card-pad qb-line">{qb_line}</p>
  </div>
  <p class="note top-gap">The rating is the model's own, {esc(evidence)}: every team's offense and
    defense, and every quarterback, are carried from season to season and updated after each game,
    adjusted for the opponent. The ± is how unsure the model still is. These are the numbers the
    team's card uses.</p>
</section>

<section class="section">
  <div class="section-head"><h2>Season profile</h2>
    <span class="note">opponent-adjusted · percentile of the NFL this season</span></div>
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
  <p class="note top-gap">Every figure is point-in-time: it uses only games played before the
    team's next kickoff.</p>
</section>

<section class="section">
  <div class="section-head"><h2>Upcoming</h2>
    <span class="note">cards Atlas has published</span></div>
  <div class="card card-pad">
    {table(["Date", "Opponent", "Market", "Total", "Card"], schedule_rows)
     if schedule_rows else '<p class="note">No upcoming cards.</p>'}
  </div>
</section>

<section class="section">
  <div class="section-head"><h2>This season, before and after</h2>
    <span class="note">{esc(who)} margin · what Atlas published before kickoff</span></div>
  <div class="card card-pad">{record_block}</div>
</section>

{stamp_line}
<div class="disclosure top-gap">
  <b>A rating is not a recommendation.</b> Atlas publishes its own number beside the market's and grades how
  much weight it deserves; it never says what to do with either.
</div>"""
    path = team_path(team, "nfl")
    description = (f"{team.name}: Atlas's NFL rating of the offense, defense and expected quarterback, the "
                   "season profile, upcoming cards, and every projection this season beside the result.")
    return layout(title=f"{team.name} — Atlas NFL rating and cards", body=body, depth=2, active="nfl",
                  description=description, canonical=path,
                  social=social_tags(title=f"{team.name} · Atlas", description=description, url=path),
                  structured=json_ld({
                      "@context": "https://schema.org", "@type": "SportsTeam", "name": team.name,
                      "sport": "American Football", "url": f"{SITE_URL}/{path}",
                      "memberOf": {"@type": "SportsOrganization", "name": "NFL"},
                  }))


def _nfl_views(cards: list[Card]) -> dict[int, dict]:
    """Each team's side of the projection on its earliest card, keyed by ESPN team id."""
    views: dict[int, dict] = {}
    for card in sorted(cards, key=lambda c: c.kickoff):
        if card.projection is None:
            continue
        for side, view in ((card.home, card.projection.home), (card.away, card.projection.away)):
            if side.team_id is not None and view:
                views.setdefault(side.team_id, view)
    return views


def _ordinal(n: int) -> str:
    suffix = "th" if 11 <= n % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


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


# ---------------------------------------------------------------------------
# About — the thirty-second page
# ---------------------------------------------------------------------------


def about_page(example: Card | None, *, card_count: int) -> str:
    """What Atlas is, what a grade means, how to read a card, and why it exists.

    Built from a real card rather than a mock, so the walkthrough cannot drift
    away from the product it is describing. A first-time visitor should be able
    to stop after the first screen and still be right about what Atlas is.
    """
    walkthrough = _card_walkthrough(example) if example else ""
    letters = table(
        ["Grade", "What it means", "Share of the record"],
        [['<span class="lead">A+</span>',
          "Atlas and the market land on the same number. Reliable — and Atlas "
          "is adding least here.", "6%"],
         ['<span class="lead">A</span>',
          "Closely aligned. Strong calibration.", "14%"],
         ['<span class="lead">B</span>',
          "A moderate difference, in the range where the claim and the delivery "
          "stay close.", "31%"],
         ['<span class="lead">C</span>',
          "A wide difference. The claim starts to run ahead of the delivery.", "25%"],
         ['<span class="lead">D</span>',
          "A large difference. Atlas commonly struggles this far out.", "15%"],
         ['<span class="lead">F</span>',
          "A very large difference, in the range where Atlas has been least "
          "reliable. Atlas marks its own card down.", "10%"]])

    body = f"""<header class="lede">
  <h1>Atlas grades its own numbers.</h1>
  <p class="lede-text">Every college football game gets a card: what the market
    says, what Atlas projects, what is driving the difference — and a letter
    saying how much that card's information has historically been worth.
    <b>Atlas never tells anyone what to do with it.</b></p>
  <div class="lede-actions">
    <a class="button" href="index.html">See this week's board</a>
    <a class="button ghost" href="#read">How to read a card</a>
  </div>
</header>

<section class="section" id="what">
  <div class="section-head"><h2>What Atlas is</h2></div>
  <div class="grid-2">
    <div class="card card-pad prose">
      <h3>A research desk, published</h3>
      <p>Atlas models {card_count} college football games a week from a
        point-in-time database — every figure uses only what was knowable
        before kickoff, going back to 2018.</p>
      <p>The number is Atlas's own. Every team starts a season at a preseason
        expectation and is updated after every game, opponent-adjusted, and
        the projection is the mean of a full score distribution, to one
        decimal. The market is never an input: it sits beside Atlas's number
        so you can see where they differ and what is driving it.</p>
      <p>And then it does the thing nothing else in this category does: it
        grades itself, in public, on every card, using its own historical
        record.</p>
    </div>
    <div class="card card-pad prose">
      <h3>What Atlas is not</h3>
      <ul class="plain">
        <li><b>Not a selections service.</b> No card names a side. Not as a
          lean, not as an arrow, not as a highlighted row. The
          <a href="dfs.html">DFS page</a> is separate and says what it is:
          player projections for DraftKings contests, with their ranges and
          record, and no lineup.</li>
        <li><b>Not a sportsbook.</b> Nothing here can be acted on from this
          page, and nothing is sized.</li>
        <li><b>Not a record of wins and losses.</b> The record Atlas publishes
          is calibration: what it claimed, against what it delivered.</li>
        <li><b>Not urgent.</b> No countdowns, no alerts, nothing on any Atlas
          page moves.</li>
      </ul>
    </div>
  </div>
</section>

{walkthrough}

<section class="section" id="grades">
  <div class="section-head"><h2>What the grades mean</h2>
    <span class="note">computed, never assigned</span></div>
  <div class="card card-pad prose">
    <p>A grade answers one question: <b>how much weight does the information on
      this card deserve?</b> It is not a rating of the game and it is not a
      recommendation.</p>
    {letters}
    <p>The thresholds are <b>absolute</b> and were set once from the out-of-sample record
      of results. The same card grades the same on a quiet Tuesday and on
      championship Saturday, so a screenshot means the same thing whenever it
      was taken.</p>
    <div class="disclosure">
      <b>A top grade does not mean "read this one first."</b> Cards where Atlas
      and the market agree to within a point have realised 50.8% against a
      51.3% claim across 760 games — statistically a coin flip. They grade
      highest because they are the most reliable, and they are the most
      reliable because Atlas has added nothing to them. The grade tells you
      what to discount, not what to look at.
    </div>
    <p class="note"><a href="research.html#grades">The full rubric, the four
      components and the calibration curve behind them</a>.</p>
  </div>
</section>

<section class="section" id="why">
  <div class="section-head"><h2>Why Atlas exists</h2></div>
  <div class="card card-pad prose">
    <p>Every model in this category publishes its numbers with the same
      confidence every week. None of them tells you which of those numbers has
      historically been worth anything.</p>
    <p>Atlas measured that, and the answer was uncomfortable: <b>the further its
      model sits from the market, the worse it does.</b> Across every season it never saw
      out of sample, cards claiming 77% accuracy delivered 50%. The loudest
      cards are the weakest ones.</p>
    <p>Most products would bury that. Atlas made it the largest element on the
      card. A grade that can say F is the only kind of grade worth anything,
      and it is the reason the A means something too.</p>
    <p class="note"><a href="research.html">The out-of-sample record, the
      methodology, and every number behind this page</a> ·
      <a href="faq.html">questions</a>.</p>
  </div>
</section>

<section class="section">
  <div class="card card-pad prose">
    <h3>Start here</h3>
    <p><a href="index.html">This week's board</a> · <a
      href="research.html">how Atlas works</a> · <a href="research.html#grades">what
      grades mean</a> · <a href="premium.html">what is free and what is not</a></p>
    <p class="note">Everything that makes Atlas checkable — the grades, the
      research, the methodology and the reliability record — is free and
      always will be.</p>
  </div>
</section>"""

    description = (
        "Atlas grades its own college football numbers. Every game gets a "
        "card: the market, the projection, and a letter for how much that "
        "card has historically been worth."
    )
    return layout(
        title="What Atlas is, and how to read a card",
        body=body, active="about", description=description,
        canonical="about.html",
        social=social_tags(title="Atlas Sports Intelligence",
                           description=description, url="about.html"),
        structured=json_ld({
            "@context": "https://schema.org",
            "@type": "Organization",
            "name": "Atlas Sports Intelligence",
            "url": SITE_URL,
            "slogan": TAGLINE,
            "description": description,
        }),
    )


#: The walkthrough's numbered notes, in the order a reader meets them.
CARD_STEPS = (
    ("The game", "Both teams with their crests, rank, record and conference, "
                 "then kickoff, broadcast and venue. You should recognize the "
                 "game before you read a word."),
    ("The market", "What the betting market currently says — the spread and "
                   "the game total. This is the reference everything else is "
                   "measured against, not a price to act on."),
    ("Atlas", "What Atlas projects: the score to one decimal, and the total "
              "underneath it. The model's own number - the market is not an "
              "input to it."),
    ("The difference", "How far Atlas sits from the market on the spread, with "
                       "the total beneath. This is the number the grade is "
                       "mostly about — and a large one is a warning, not an "
                       "opportunity."),
    ("The grade", "A letter, a score out of 100, and three lines explaining "
                  "itself: what the letter says, what Atlas did, and the "
                  "out-of-sample record behind it."),
    ("Why", "The three things the model is reading, each with the crest of the "
            "team it favors."),
    ("Be careful about", "Up to three warnings computed from this game — a "
                         "thin market, a lopsided spread, a missing metric. A "
                         "card with nothing to flag says nothing."),
    ("Everything else", "Market detail, the projection's arithmetic, how the "
                        "grade was computed, all the drivers, how the line has "
                        "moved, and the reliability record — each one tap away."),
)


def _card_walkthrough(card: Card) -> str:
    steps = "".join(
        f'<li class="step"><span class="step-n">{i}</span>'
        f'<div><b>{esc(name)}</b><p class="note">{esc(text)}</p></div></li>'
        for i, (name, text) in enumerate(CARD_STEPS, start=1)
    )
    return f"""<section class="section" id="read">
  <div class="section-head"><h2>How to read a card</h2>
    <span class="note">eight things, in the order you meet them</span></div>
  <div class="card card-pad prose">
    <p>Every card is the same shape. The first screen answers five questions —
      who is playing, what the market says, what Atlas says, why, and what
      should make you careful — and everything else is one tap below it.</p>
    <ol class="steps">{steps}</ol>
    <p class="note top-gap">Worked example:
      <a href="{esc(card.path)}">{esc(card.title)}</a>, graded
      <b>{esc(card.grade.letter) if card.grade else "—"}</b>.</p>
  </div>
</section>"""


#: The published FAQ. Grouped, because a flat list of thirty questions is a
#: wall; the uncomfortable ones come first inside each group, because burying
#: them is the thing this product exists not to do.
FAQ = (
    ("What Atlas is", (
        ("What is Atlas?",
         "Every college football game gets a card: what the betting market "
         "says, what Atlas projects, what is driving the difference between "
         "them, and a letter for how much that card's information has "
         "historically been worth. Atlas never tells anyone what to do with "
         "it."),
        ("Is this a selections service?",
         "No. No card names a side \u2014 not as a lean, not as an arrow, not as a "
         "highlighted row. Every page is checked at build time by a test that "
         "fails if a side appears anywhere, and again by an audit over all "
         "179 built pages."),
        ("What is the DFS page?",
         "A separate part of Atlas for DraftKings' NFL daily fantasy contests: "
         "every player DraftKings has priced for the Sunday main slate, with "
         "Atlas's projection of his points, a range that should hold four "
         "outcomes in five, and the chance he plays at all - beside the "
         "model's record. It shows no lineup and features no player. DFS is "
         "gambling, for adults, where it is legal."),
        ("Why does the DFS model read the betting market when the cards do not?",
         "Because it was measured. Built on Atlas's game model alone, the DFS "
         "model ranked quarterbacks and defenses a little worse than "
         "DraftKings' own prices; the gap was how many points each team would "
         "score, which the market's implied team totals know better. The "
         "cards compare Atlas with the market, so the market can never be one "
         "of their inputs; the DFS page compares its projections with what "
         "players score, so it can."),
        ("Do I need to know anything about betting?",
         "No. The market number is a reference point because it is the best "
         "public forecast of a game that exists. One thing does assume the "
         "notation - \u201cMIA \u221241.5\u201d means Miami is favored by "
         "41.5 points \u2014 and everything else is in plain English."),
        ("Do I need to understand modeling?",
         "No. The card's first screen is written for somebody who does not, "
         "and the grade explains itself in three plain sentences on every "
         "card. The technical detail is behind panels and on the research "
         "page."),
    )),
    ("The grade", (
        ("Is an A card the one I should read first?",
         "No, and this is the least intuitive thing about Atlas. Cards where "
         "Atlas and the market agree to within a point have realised 50.8% "
         "against a 51.3% claim across 760 games \u2014 statistically a coin flip. "
         "They grade highest because they are the most reliable, and they are "
         "the most reliable because Atlas has added nothing to them. The "
         "grade tells you what to discount, not what to look at."),
        ("Why does a large difference lower the grade?",
         "Because, measured across every completed season out of sample, that is where "
         "the model is worst. Cards claiming 77% accuracy delivered 50%. "
         "Everything else in this category shouts loudest where its model "
         "disagrees most; Atlas grades itself down there."),
        ("Is an A card a better game to watch?",
         "No. The grade says nothing about the game. It is about how much "
         "weight Atlas's own numbers on that card deserve."),
        ("Who assigns the grades?",
         "Nobody. The rubric is code, nothing is entered by hand or adjusted "
         "afterwards, and the calibration curve behind it is refitted from "
         "the full record on every build \u2014 so the site cannot drift "
         "away from the research it cites."),
        ("Why do so few cards get A+?",
         "The thresholds were set once from the out-of-sample record and then "
         "fixed, and about 6% of cards historically reach A+. Atlas does not "
         "grade on a curve: a curve would make the same card mean something "
         "different depending on which Saturday you looked at it."),
        ("Can a card's grade change during the week?",
         "Yes. The grade depends partly on how far Atlas sits from the "
         "market, and the market moves. A card graded B on Tuesday can be "
         "graded C by Saturday if the line moves away from Atlas's number."),
        ("What does \u201cmarked down\u201d mean?",
         "A card graded D or F. There is a filter for them on the board, "
         "because the cards Atlas trusts least are the ones a reader most "
         "needs to know about."),
    )),
    ("The numbers", (
        ("What is \u201cthe difference\u201d?",
         "Atlas's projected home margin minus the market's spread, with the "
         "total beneath it. Positive means Atlas likes the home side more "
         "than the market does; negative, less. It is coloured only above one "
         "point, because below that the two are statistically "
         "indistinguishable."),
        ("Why does Atlas show the market at all?",
         "Because it is the reference. Atlas's number is its own - the market "
         "is never an input to it - and the card puts the two side by side "
         "so the difference, and the reasons behind it, are the product. "
         "Measured out of sample, the closing line is the closer forecast, "
         "and the grade is built from exactly that record."),
        ("What is \u201cpoint-in-time\u201d?",
         "Every figure attached to a game uses only information that existed "
         "before kickoff. A team's profile in week 4 is what was knowable in "
         "week 4 - no hindsight, anywhere in the database."),
        ("Why does every card say one book is quoting?",
         "Because the live tracker currently captures a single provider. It "
         "is a real limitation, it is named on the card rather than hidden, "
         "and adding a second provider is the highest-value item on the "
         "roadmap."),
    )),
    ("Coverage", (
        ("Which sports?",
         "College football and the NFL, each from its own model, fitted and "
         "back-tested to the same standard and graded from its own record. "
         "No other sports are planned."),
        ("Is the NFL card the same as the college one?",
         "The same card: the market first, Atlas's own number second, the "
         "drivers third, and a grade. The model underneath differs where the "
         "sport does \u2014 the NFL carries a quarterback state and a fitted "
         "home advantage, and no preseason recruiting or talent inputs."),
    )),
    ("Money", (
        ("Is Atlas free?",
         "Yes. The grade, the research, the methodology, the reliability "
         "record and everything needed to judge a card this week are free and "
         "always will be."),
        ("Will there be a paid tier?",
         "Eventually, for history, depth and delivery \u2014 past weeks and "
         "seasons, every driver rather than the leading three, the full "
         "market history, and email. Not the grade, not the research, not the "
         "record. There is no payment path on this site."),
        ("Does Atlas take affiliate money from sportsbooks?",
         "No, and it never will. Books pay for traffic that converts to "
         "deposits, which would mean Atlas earns more when readers act \u2014 an "
         "interest directly opposed to the product's only claim."),
        ("Is anything blurred or teased?",
         "No. A premium surface is absent and named, never blurred. A blurred "
         "number is an advertisement wearing the clothes of information."),
    )),
    ("Trust", (
        ("How do I know the record is real?",
         "It is recomputed from the database on every build rather than "
         "transcribed, and the research page shows claimed accuracy against "
         "realised accuracy for every band of disagreement, with the number "
         "of games behind each row."),
        ("Has Atlas been wrong?",
         "Constantly, and the product is built around saying so. The grading "
         "system exists because the research found the model's most confident "
         "cards were its worst ones."),
        ("Does Atlas track me?",
         "Server logs and a single first-party counter. No third-party "
         "analytics, no ad pixel, no cross-site identity, no account. There "
         "is nothing to sign into."),
    )),
    ("Practical", (
        ("Does the site work without JavaScript?",
         "Yes. Every page is complete before anything loads. The only script "
         "is 40 lines of filtering on the board; the card's expanding panels "
         "are native HTML."),
        ("Why is it so plain?",
         "Because it is a research product, and because a page that loads "
         "instantly on a phone on a stadium network beats a page that looks "
         "impressive on a laptop."),
        ("Can I get this by email?",
         "A weekly board email is planned. There is no sender yet, so nothing "
         "is collecting addresses."),
    )),
)


def faq_page() -> str:
    groups = "".join(
        f"""<section class="section" id="{esc(title.lower().replace(' ', '-'))}">
  <div class="section-head"><h2>{esc(title)}</h2></div>
  <div class="card card-pad faq">""" + "".join(
            f"<h3>{esc(q)}</h3><p>{esc(a)}</p>" for q, a in items
        ) + """</div>
</section>"""
        for title, items in FAQ
    )
    description = (
        "What Atlas is, what the grades mean, why a large difference lowers a "
        "grade, what is free, and what Atlas will never publish."
    )
    body = f"""<header class="page-head">
  <h1>Questions</h1>
  <p class="sub">The plain answers, including the uncomfortable ones. If
    something here is unclear, it is a problem with the page rather than with
    the reader.</p>
</header>
{groups}
<div class="disclosure top-gap">
  <b>Still unclear?</b> <a href="about.html">What Atlas is and how to read a
  card</a> · <a href="research.html">how the model works</a> ·
  <a href="research.html#grades">the full grade rubric</a>
</div>"""
    return layout(title="Questions about Atlas | Atlas Sports Intelligence",
                  body=body, active="about", description=description,
                  canonical="faq.html",
                  social=social_tags(title="Questions about Atlas",
                                     description=description, url="faq.html"))


def status_page(summary) -> str:
    """Track 7. What Atlas knows about its own state, published.

    A static site fails quietly: the board keeps serving and the only symptom
    of a poller that died on Thursday is a market number that stopped moving.
    This page is the version of that a reader can check for themselves, which
    is the same discipline as publishing the reliability record - a claim
    nobody can audit is a claim.
    """
    def block(title: str, note: str, rows) -> str:
        if not rows:
            return ""
        items = "".join(
            f"""<div class="status-row{' bad' if not row.ok else ''}">
  <span class="status-label">{esc(row.label)}</span>
  <span class="status-value">{esc(row.value)}</span>
  <span class="status-note">{esc(row.note)}</span>
</div>"""
            for row in rows
        )
        return f"""<section class="section">
  <div class="section-head"><h2>{esc(title)}</h2>
    <span class="note">{esc(note)}</span></div>
  <div class="card status-list">{items}</div>
</section>"""

    checks = "".join(
        f"""<div class="status-row{' bad' if not c.ok else ''}">
  <span class="status-label">{esc(c.name)}</span>
  <span class="status-value">{esc(c.status)}</span>
  <span class="status-note">{esc(c.detail)}</span>
</div>"""
        for c in summary.checks
    )
    healthy = summary.healthy
    body = f"""<header class="page-head">
  <h1>Data status</h1>
  <p class="sub">How current everything on this site is, and what is
    producing it. Atlas rebuilds on a schedule from free sources; when
    something stops, this page says so before a reader has to guess.</p>
</header>

<div class="card card-pad banner-low">
  <div class="banner-row">
    <span class="badge {'mute' if healthy else 'warn'}">{'All systems reporting' if healthy else 'Degraded'}</span>
    <p class="note banner-text">{esc(summary.mode)}.</p>
  </div>
</div>

{block("Freshness", "the last successful run of each task", summary.freshness_rows)}
{block("Providers", "where the information comes from", summary.provider_rows)}
{block("Tracker", "opinions published, and how many have been scored",
       summary.tracker_rows)}

<section class="section">
  <div class="section-head"><h2>Health checks</h2>
    <span class="note">the same checks the operator's alert runs on</span></div>
  <div class="card status-list">{checks}</div>
</section>

<div class="disclosure top-gap">
  <b>What the timestamps mean.</b> Every stamp on this site is the time of the
  last <b>successful</b> refresh of that thing, in Eastern — never the time a
  page was built and never your browser's clock. A rebuild that ran against a
  failed market poll shows the market's older time, because that is when the
  numbers a reader is looking at were last true.
</div>"""
    return layout(title="Data status | Atlas Sports Intelligence", body=body,
                  description="How current Atlas's information is: the last "
                              "refresh, the last market poll, provider status "
                              "and the state of the live tracker.",
                  canonical="status.html")


def not_found_page() -> str:
    body = """<header class="lede">
  <h1>That page is not here.</h1>
  <p class="lede-text">Cards come down when the game has been played. The board
    always has this week's.</p>
  <div class="lede-actions">
    <a class="button" href="/index.html">This week's board</a>
    <a class="button ghost" href="/about.html">What Atlas is</a>
  </div>
</header>"""
    # No canonical and no indexing: a 404 that claims a canonical URL tells a
    # crawler the missing page is the real one.
    return layout(title="Not found | Atlas Sports Intelligence", body=body,
                  description="That page is not here. Cards come down once "
                              "the game has been played, and the board always "
                              "has this week's.",
                  structured='<meta name="robots" content="noindex">')


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
    <p>The projection is the model's own. Each team opens the season at a
      preseason expectation built from last season's ratings, talent,
      recruiting, returning production and the coaching situation; after every
      game a filter updates its offense and defense, opponent-adjusted; the
      total adds pace and wind; and the score is the mean of a full
      distribution over every possible final, to one decimal.</p>
    <p>Then it does something most models do not. It compares itself to the
      market, and it publishes what that comparison found. Walked forward
      over five seasons it never saw, Atlas's number is closer to the final
      margin than a rating system or a preseason ranking and not as close as
      the closing line. The market is not an input to the model; it is the
      reference the grade is measured against.</p>
  </div>
</section>

<section class="section" id="grades">
  <div class="section-head"><h2>What a grade means</h2></div>
  <div class="card card-pad prose">
    <p>A grade is <b>not</b> a recommendation. It answers one question: how
      much weight does the information on this card deserve?</p>
    <p>It is computed, never assigned. Four components, one hundred points:</p>
    {table(["Component", "Points", "What it measures"], [
      ['<span class="lead">Calibration</span>', "45",
       "how far short of its claim a card this far from the market has historically fallen, read from a curve fitted to every completed season out of sample"],
      ['<span class="lead">Market agreement</span>', "25",
       "how far Atlas's number sits from the market on the spread"],
      ['<span class="lead">Card conditions</span>', "15",
       "how mature the season is, and how settled the market has been since the number opened"],
      ['<span class="lead">Data completeness</span>', "15",
       "how many of the required inputs are present"],
    ])}
    {table(["Score", "Grade", "Share of the record"],
           [["96–100", '<span class="lead">A+</span>', "6%"],
            ["90–95", '<span class="lead">A</span>', "14%"],
            ["79–89", '<span class="lead">B</span>', "31%"],
            ["66–78", '<span class="lead">C</span>', "25%"],
            ["51–65", '<span class="lead">D</span>', "15%"],
            ["below 51", '<span class="lead">F</span>', "10%"]])}
    <p>The six thresholds were chosen once, from the distribution of scores
      across the out-of-sample record, and then fixed. They are <b>absolute</b>: a card's
      letter depends on that card and on nothing else on the board, so the same
      card grades the same on a quiet Tuesday and on championship Saturday.
      Atlas does not grade on a curve, because a curve would make a screenshot
      mean something different depending on the week it was taken.</p>
    <p><b>A top grade is not a signal to read that card first.</b> Cards where
      Atlas and the market agree to within a point have realised 50.8% against
      a 51.3% claim across 760 games — statistically a coin flip. They grade
      highest because they are the most reliable, and they are the most
      reliable because Atlas has added nothing to them. The grade tells a
      reader what to discount, not what to look at.</p>
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
    <p>Calibration asks whether a claimed 65% is a real 65%. Against the
      closing number Atlas is <b>overconfident</b>, and gets more so as it
      gets more confident: its top confidence bucket claims
      {pct(bands["10+"].claimed, 0) if "10+" in bands else "—"} and realises
      about {pct(bands["10+"].realised, 0) if "10+" in bands else "—"}.</p>
    <p>The grade corrects for this on every card. It is built from the
      calibration record itself, so a card in a badly-calibrated band cannot
      grade well no matter how interesting it looks.</p>
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
    description = ("How the Atlas model works, what the A-F grades mean, and "
                   "why a large disagreement lowers confidence rather than "
                   "raising it.")
    return layout(title="How Atlas works, and what the grades mean | Atlas",
                  body=body, active="research", canonical="research.html",
                  description=description,
                  social=social_tags(title="How Atlas works",
                                     description=description,
                                     url="research.html"))


def _team_strip(teams: dict | None) -> str:
    """Every NFL team with a page this week, by name, so the pages can be reached from the site."""
    if not teams:
        return ""
    links = "".join(
        f'<a class="team-link" href="{esc(team_path(side, "nfl"))}">{_logo(side, size="small", root="")}'
        f"<span>{esc(side.short)}</span></a>"
        for _, side in sorted(teams.items(), key=lambda kv: kv[1].short)
    )
    return f"""<section class="section">
  <div class="section-head"><h2>Teams</h2><span class="note">Atlas's rating of each, and its season</span></div>
  <div class="card card-pad team-strip">{links}</div>
</section>"""


def premium_page() -> str:
    """The launch split: this week is free, the archive and the depth are paid.

    The earlier framework put the Atlas difference behind the boundary. That is
    no longer coherent - the difference is on every board row and on every
    social card - and it was never the dangerous artefact. A difference without
    a grade beside it is; a difference with one is the product. So the line
    moved to a shape that can actually be held: everything needed to judge a
    card this week is free, and what is paid is history, depth and delivery.
    """
    compare = table(["", "Free forever", "Premium"], [
        ['<span class="lead">This week\'s board, every game</span>', "✓", "✓"],
        ['<span class="lead">The Atlas grade, and its three-line explanation</span>', "✓", "✓"],
        ['<span class="lead">Market number, Atlas projection, the difference</span>', "✓", "✓"],
        ['<span class="lead">Why — the three leading drivers</span>', "✓", "✓"],
        ['<span class="lead">Be careful about</span>', "✓", "✓"],
        ['<span class="lead">How the grade was computed</span>', "✓", "✓"],
        ['<span class="lead">Reliability record and calibration</span>', "✓ always", "✓"],
        ['<span class="lead">Research and methodology</span>', "✓ always", "✓"],
        ['<span class="lead">Team pages and season profiles</span>', "✓", "✓"],
        ['<span class="lead">Social cards</span>', "✓", "✓"],
        ['<span class="lead">Past weeks and past seasons</span>',
         '<span class="flat">this week only</span>', "✓"],
        ['<span class="lead">Every driver, with percentiles</span>',
         '<span class="lead">top three</span>', "✓"],
        ['<span class="lead">Full market history, snapshot by snapshot</span>',
         '<span class="lead">open and current</span>', "✓"],
        ['<span class="lead">How a card\'s grade has moved during the week</span>',
         '<span class="flat">—</span>', "✓"],
        ['<span class="lead">Daily and weekly email</span>',
         '<span class="lead">weekly board</span>', "✓"],
        ['<span class="lead">Data export</span>', '<span class="flat">—</span>', "✓"],
    ])
    body = f"""<header class="page-head">
  <h1>Premium</h1>
  <p class="sub">Atlas sells history, depth and delivery. It does not sell
    honesty — the grade, the research, the methodology and the reliability
    record are free, permanently, and everything you need to judge this week\'s
    card is free with them.</p>
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
    <p><b>The credibility layer is free, permanently.</b> The grade, the
      research, the methodology and the reliability record. Evidence for a
      claim should never cost more than the claim, and a reliability record
      that costs money is not a record — it is a marketing asset.</p>
    <p><b>Everything needed to judge this week\'s card is free.</b> The market
      number, the projection, the difference, why, and what should make you
      careful. A card that is half visible is a card a reader cannot check, and
      an unverifiable card is worth less than no card.</p>
    <p><b>What is paid is history, depth and delivery.</b> Past weeks, every
      driver rather than the leading three, the full snapshot-by-snapshot
      market history, the daily email and export. None of it changes what a
      free reader concludes about a game; all of it is work Atlas does that
      costs money to keep doing.</p>
    <p><b>No affiliate revenue, ever.</b> Books pay for traffic that converts
      to deposits. Taking that money would mean Atlas earns more when readers
      act — an interest directly opposed to the product\'s only claim.</p>
    <p><b>Nothing is ever blurred.</b> A premium surface is absent and named,
      never teased. A blurred number is an advertisement wearing the clothes of
      information.</p>
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
    return layout(title="What is free and what is premium | Atlas",
                  body=body, active="premium", canonical="premium.html",
                  description="What Atlas premium includes, what stays free "
                              "permanently, and why the credibility layer is "
                              "never behind a boundary.")
