"""Production-ready social cards.

Two formats, rendered as SVG and rasterised to PNG at 2x: 1200x675 for the
timeline and 1080x1080 for the drivers post. Both carry the game, the market,
the Atlas projection, the grade, the key drivers and the link back.

Neither template can express a selection. There is no side, no record, no
countdown and no figure that implies a return — a template that cannot be
filled without one of those would be a broken template.
"""

from __future__ import annotations

import base64
from pathlib import Path

from atlas import config
from atlas.site.data import Card
from atlas.site.html import day_and_clock, esc, num, signed
from atlas.util import get_logger

LOG = get_logger(__name__)


def _capped(value: float | None) -> float | None:
    """99% is the most certainty a card will print. 100% reads as a promise."""
    if value is None:
        return None
    return min(0.99, max(0.01, value))

SITE = "atlas.football"
TAGLINE = "RESEARCH · ANALYTICS · CONTEXT"

TONE_COLOUR = {
    "a": "#0ca30c", "b": "#2a78d6", "c": "#fab219",
    "d": "#ec835a", "f": "#d03b3b",
}

#: Light surfaces, the same tokens the site uses. A social card that arrives
#: dark in a bright timeline looks like every other betting graphic.
BG = "#fbfaf8"
SURFACE = "#ffffff"
BORDER = "#e6e4df"
INK = "#14181f"
INK_2 = "#3d4652"
INK_3 = "#6b7480"


def _wrap(text: str, limit: int) -> list[str]:
    words, lines, current = text.split(), [], ""
    for word in words:
        trial = f"{current} {word}".strip()
        if len(trial) > limit and current:
            lines.append(current)
            current = word
        else:
            current = trial
    if current:
        lines.append(current)
    return lines


def _font(size: float, weight: int = 400, fill: str = INK, spacing: float = 0.0) -> str:
    return (f'font-family="ui-sans-serif,system-ui,-apple-system,Segoe UI,Inter,'
            f'Helvetica,Arial,sans-serif" font-size="{size}" font-weight="{weight}" '
            f'fill="{fill}" letter-spacing="{spacing}"')


def _cell(x: float, y: float, w: float, h: float, label: str, value: str,
          note: str, value_fill: str = INK) -> str:
    return f"""<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="14"
        fill="{SURFACE}" stroke="{BORDER}"/>
  <text x="{x + 22}" y="{y + 32}" {_font(13, 640, INK_3, 1.1)}>{esc(label.upper())}</text>
  <text x="{x + 22}" y="{y + 76}" {_font(40, 700, value_fill, -1.2)}>{esc(value)}</text>
  <text x="{x + 22}" y="{y + 102}" {_font(14, 400, INK_3)}>{esc(note)}</text>"""


def _grade_mark(x: float, y: float, size: float, card: Card) -> str:
    if card.grade is None:
        return ""
    colour = TONE_COLOUR[card.grade.tone]
    return f"""<rect x="{x}" y="{y}" width="{size}" height="{size}" rx="{size * 0.26}"
        fill="none" stroke="{colour}" stroke-width="3"/>
  <text x="{x + size / 2}" y="{y + size * 0.60}" text-anchor="middle"
        {_font(size * 0.49, 720, colour, -1.5)}>{esc(card.grade.letter)}</text>
  <text x="{x + size / 2}" y="{y + size * 0.82}" text-anchor="middle"
        {_font(size * 0.13, 640, colour, 1.0)}>{card.grade.score:.0f}</text>"""


def _crest(side, x: float, y: float, size: float) -> str:
    """A team mark, embedded.

    Base64 rather than a file reference: the SVG is handed to whoever wants it
    and has to render the same everywhere, including in tools that will not
    follow a relative path.
    """
    if not side.logo:
        return ""
    path = config.paths().data / "site" / "logos" / side.logo
    if not path.exists():
        return ""
    data = base64.b64encode(path.read_bytes()).decode()
    return (f'<image x="{x}" y="{y}" width="{size}" height="{size}" '
            f'href="data:image/png;base64,{data}" '
            f'preserveAspectRatio="xMidYMid meet"/>')


def _accent(card: Card, width: float) -> str:
    from atlas.site.render import accents

    home, away = accents(card)
    return (f'<rect x="0" y="0" width="{width / 2}" height="8" fill="{away}"/>'
            f'<rect x="{width / 2}" y="0" width="{width / 2}" height="8" fill="{home}"/>')


# ---------------------------------------------------------------------------
# Template A — 1200 x 675
# ---------------------------------------------------------------------------


def wide(card: Card) -> str:
    """One game, one idea.

    The earlier version carried three stat cells, three drivers and a
    three-line note, and read as a dashboard someone had screenshotted. A post
    gets one glance: the teams, three numbers, the grade, and the single thing
    the model is reading.
    """
    W, H = 1200, 675
    title_lines = _wrap(card.title, 26)
    difference = card.total_difference

    # One cursor down the canvas, as in `square`. The earlier version placed
    # the kickoff line and the MARKET label from two different expressions and
    # they landed on top of each other whenever the title fitted on one line.
    crests = (_crest(card.away, 72, 150, 72)
              + _crest(card.home, 160, 150, 72))
    step = 64
    y = 292
    title = "".join(
        f'<text x="72" y="{y + i * step}" {_font(58, 700, INK, -2.0)}>{esc(line)}</text>'
        for i, line in enumerate(title_lines)
    )
    y += (len(title_lines) - 1) * step
    meta = " · ".join(filter(None, [day_and_clock(card.kickoff), card.tv]))
    meta_y = y + 44
    row_y = meta_y + 78

    grade_colour = TONE_COLOUR[card.grade.tone] if card.grade else INK_3
    grade_block = _grade_mark(W - 72 - 128, row_y - 72, 128, card) if card.grade else ""
    grade_label = (
        f'<text x="{W - 72 - 64}" y="{row_y + 86}" text-anchor="middle" '
        f'{_font(15, 620, grade_colour, 0.6)}>{esc(_grade_word(card))}</text>'
        if card.grade else ""
    )

    # A screenshot has to explain itself, so the wide card spends its last
    # block on a sentence rather than on a fourth statistic. The drivers are
    # the square card's job; this one's job is what the numbers mean.
    read_lines = _wrap(_read(card), 78)[:2]
    read_block = ""
    if read_lines and row_y + 44 < H - 196:
        read_block = (
            f'<text x="72" y="{H - 188}" {_font(13, 640, INK_3, 1.2)}>'
            "WHAT THIS MEANS</text>"
            + "".join(
                f'<text x="72" y="{H - 156 + i * 32}" {_font(24, 500, INK_2, -0.3)}>'
                f"{esc(line)}</text>"
                for i, line in enumerate(read_lines)
            )
        )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}"
     viewBox="0 0 {W} {H}" role="img"
     aria-label="{esc(card.title)}: market {esc(card.spread_text)}, total {num(card.total.current)}. Atlas projects {num(card.anchored_total)} and grades this card {esc(card.grade.letter if card.grade else "ungraded")}.">
  <rect width="{W}" height="{H}" fill="{BG}"/>
  {_accent(card, W)}
  <text x="72" y="92" {_font(23, 680, INK, -0.4)}>Atlas</text>
  <text x="147" y="92" {_font(23, 500, INK_3, -0.4)}>Sports Intelligence</text>
  <text x="{W - 72}" y="92" text-anchor="end" {_font(14, 600, INK_3, 2.6)}>{TAGLINE}</text>
  <line x1="72" y1="120" x2="{W - 72}" y2="120" stroke="{BORDER}"/>

  {crests}
  {title}
  <text x="72" y="{meta_y}" {_font(19, 400, INK_3)}>{esc(meta)}</text>

  <text x="72" y="{row_y - 34}" {_font(13, 640, INK_3, 1.2)}>MARKET</text>
  <text x="72" y="{row_y + 14}" {_font(44, 700, INK, -1.6)}>{esc(card.spread_text)}</text>
  <text x="72" y="{row_y + 44}" {_font(17, 400, INK_3)}>total {num(card.total.current)}</text>

  <text x="430" y="{row_y - 34}" {_font(13, 640, INK_3, 1.2)}>ATLAS</text>
  <text x="430" y="{row_y + 14}" {_font(44, 700, INK, -1.6)}>{num(card.anchored_total)}</text>
  <text x="430" y="{row_y + 44}" {_font(17, 400, INK_3)}>projected total</text>

  <text x="700" y="{row_y - 34}" {_font(13, 640, INK_3, 1.2)}>DIFFERENCE</text>
  <text x="700" y="{row_y + 14}" {_font(44, 700, _diff_colour(difference), -1.6)}>{signed(difference)}</text>
  <text x="700" y="{row_y + 44}" {_font(17, 400, INK_3)}>on the total</text>

  {grade_block}{grade_label}
  {read_block}

  <line x1="72" y1="{H - 96}" x2="{W - 72}" y2="{H - 96}" stroke="{BORDER}"/>
  <text x="72" y="{H - 56}" {_font(18, 620, INK_2)}>{SITE}/{esc(card.slug)}</text>
  <text x="{W - 72}" y="{H - 56}" text-anchor="end" {_font(16, 400, INK_3)}>Grade = information quality, not a recommendation</text>
</svg>"""


#: Matches `render.DIFFERENCE_FLOOR`. Below a point, Atlas and the market are
#: indistinguishable out of sample, so the number is not worth a colour.
DIFFERENCE_FLOOR = 1.0


def _diff_colour(value: float | None) -> str:
    if value is None or abs(value) < DIFFERENCE_FLOOR:
        return INK
    return "#2a78d6" if value > 0 else "#e34948"


def _read(card: Card) -> str:
    """The card in one plain sentence, for someone who arrived from a repost.

    It is written from the numbers already on the graphic, so a reader who
    only ever sees the image still leaves with the right impression - and the
    right impression on a badly graded card is "do not lean on this".
    """
    difference = card.total_difference
    band = card.grade.band if card.grade else None
    if difference is None or band is None:
        return ("Atlas publishes a projection and a grade for how much that "
                "projection has historically been worth.")
    direction = "above" if difference > 0 else "below"
    if abs(difference) < 1.0:
        return ("Atlas and the market land on the same number \u2014 which is where "
                "this model has been most reliable, and where it adds least.")
    if card.grade and card.grade.low:
        return (f"Atlas projects {abs(difference):.1f} points {direction} the "
                f"market. Cards this far out claimed {band.claimed:.0%} accuracy "
                f"over seven seasons and delivered {band.realised:.0%}.")
    return (f"Atlas projects {abs(difference):.1f} points {direction} the "
            f"market. Cards in that range claimed {band.claimed:.0%} accuracy "
            f"and delivered {band.realised:.0%}.")


def _grade_word(card: Card) -> str:
    if card.grade is None:
        return ""
    return {"A+": "VERY HIGH", "A": "HIGH", "B": "SOLID",
            "C": "MIXED", "D": "LOW", "F": "LOW"}[card.grade.letter]


def _short_note(card: Card) -> str:
    """A two-line version of the grade's meaning, written for this canvas.

    The card's own headline is written for a page that can give it four lines.
    Truncating it mid-sentence on an image is worse than saying less.
    """
    if card.grade is None:
        return "Not enough history to grade this card."
    band = card.grade.band
    if card.grade.low:
        return (f"Cards {band.label} points from the market claimed "
                f"{band.claimed:.0%} accuracy and delivered {band.realised:.0%}. "
                "Atlas grades its own card down.")
    if card.grade.letter in ("A+", "A"):
        return ("Atlas and the market agree closely, in the band where this "
                "model has been most consistent.")
    return (f"A {abs(card.total_difference or 0):.1f}-point difference, in a band "
            f"that claimed {band.claimed:.0%} and delivered {band.realised:.0%}.")


def _grade_title(card: Card) -> str:
    if card.grade is None:
        return "Ungraded card"
    return {"A+": "High-reliability card", "A": "High-reliability card",
            "B": "Solid card", "C": "Mixed card",
            "D": "Low-reliability card", "F": "Low-reliability card"}[card.grade.letter]


# ---------------------------------------------------------------------------
# Template B — 1080 x 1080
# ---------------------------------------------------------------------------


def square(card: Card) -> str:
    W = H = 1080
    title_lines = _wrap(card.title, 20)
    drivers = card.drivers[:3]
    note_lines = _wrap(_short_note(card), 40)[:3]
    colour = TONE_COLOUR[card.grade.tone] if card.grade else INK_3

    # One cursor down the canvas. The previous version computed each block's
    # position from the one before it in a single expression and the blocks
    # overlapped; a cursor is harder to get wrong and easier to read.
    # The crests occupy 152..228; the title clears them rather than sharing
    # the band, which is what the first cursor version still got wrong.
    y = 296
    crests = _crest(card.away, 56, 152, 76) + _crest(card.home, 148, 152, 76)
    title = "".join(
        f'<text x="56" y="{y + i * 60}" {_font(52, 700, INK, -1.8)}>{esc(line)}</text>'
        for i, line in enumerate(title_lines)
    )
    y += (len(title_lines) - 1) * 60 + 44

    meta = day_and_clock(card.kickoff) + (f" · {card.tv}" if card.tv else "")
    meta_line = f'<text x="56" y="{y}" {_font(19, 400, INK_3)}>{esc(meta)}</text>'
    y += 38

    cells = (_cell(56, y, 470, 126, "Market total", num(card.total.current),
                   f"opened {num(card.total.open_line)}")
             + _cell(554, y, 470, 126, "Atlas projects", num(card.anchored_total),
                     f"unanchored model {num(card.model_total)}"))
    y += 126 + 56

    driver_block = f'<text x="56" y="{y}" {_font(13, 640, INK_3, 1.1)}>WHAT THE MODEL IS READING</text>'
    y += 16
    for i, driver in enumerate(drivers):
        row = y + 30 + i * 48
        driver_block += (
            f'<text x="56" y="{row}" {_font(20, 620, INK)}>{esc(driver.name)}</text>'
            f'<text x="{W - 56}" y="{row}" text-anchor="end" {_font(20, 400, INK_2)}>'
            f"{esc(driver.magnitude)}</text>"
            f'<line x1="56" y1="{row + 16}" x2="{W - 56}" y2="{row + 16}" stroke="{BORDER}"/>'
        )
    y += 30 + len(drivers) * 48 + 34

    # The grade is the conclusion, so it sits on the footer rule rather than
    # wherever the drivers happened to end - otherwise the slack in the layout
    # collects underneath it and the card reads as unfinished.
    box_h = 60 + len(note_lines) * 26
    y = max(y, H - 92 - 44 - box_h)
    box = (f'<rect x="56" y="{y}" width="{W - 112}" height="{box_h}" rx="16" '
           f'fill="{SURFACE}" stroke="{colour}"/>'
           + _grade_mark(84, y + (box_h - 96) / 2, 96, card)
           + f'<text x="208" y="{y + 44}" {_font(20, 640, INK, -0.3)}>'
             f"{esc(_grade_title(card))}</text>"
           + "".join(
               f'<text x="208" y="{y + 74 + i * 26}" {_font(16, 400, INK_3)}>'
               f"{esc(line)}</text>"
               for i, line in enumerate(note_lines)))

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}"
     viewBox="0 0 {W} {H}" role="img"
     aria-label="{esc(card.title)}: what the Atlas model is reading, and the grade it assigns.">
  <rect width="{W}" height="{H}" fill="{BG}"/>
  {_accent(card, W)}
  <text x="56" y="92" {_font(22, 680, INK, -0.4)}>Atlas</text>
  <text x="126" y="92" {_font(22, 500, INK_3, -0.4)}>Sports Intelligence</text>
  <line x1="56" y1="118" x2="{W - 56}" y2="118" stroke="{BORDER}"/>
  {crests}
  {title}
  {meta_line}
  {cells}
  {driver_block}
  {box}
  <line x1="56" y1="{H - 92}" x2="{W - 56}" y2="{H - 92}" stroke="{BORDER}"/>
  <text x="56" y="{H - 56}" {_font(16, 600, INK_2)}>{SITE}/{esc(card.slug)}</text>
  <text x="{W - 56}" y="{H - 56}" text-anchor="end" {_font(16, 400, INK_3)}>Research. Analytics. Context.</text>
</svg>"""


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def write(card: Card, out: Path, *, png: bool = True) -> list[Path]:
    """Both templates for one card, as SVG and (optionally) PNG at 2x."""
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for name, svg in (("wide", wide(card)), ("square", square(card))):
        path = out / f"{card.slug}-{name}.svg"
        path.write_text(svg)
        written.append(path)
        if png:
            written.append(_raster(path, svg))
    return [p for p in written if p is not None]


def _raster(svg_path: Path, svg: str) -> Path | None:
    try:
        import cairosvg
    except ImportError:  # pragma: no cover - optional
        LOG.warning("cairosvg unavailable; SVG only")
        return None
    png_path = svg_path.with_suffix(".png")
    cairosvg.svg2png(bytestring=svg.encode(), write_to=str(png_path), scale=2)
    return png_path
