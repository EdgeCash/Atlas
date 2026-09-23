"""Small HTML helpers.

The site has no template engine on purpose: it is a build-time tool in a
Python repository, four page types deep, and the reports and dashboard in this
codebase already generate HTML this way. Adding a runtime dependency to render
static documents would be a cost with no return.
"""

from __future__ import annotations

from datetime import datetime
from html import escape as _escape
from zoneinfo import ZoneInfo

#: Every kickoff on the board is a US college game, and every reader of it
#: thinks in Eastern. ESPN hands kickoffs over in UTC, which is correct for
#: storage and unreadable on a card: "19:30 UTC" is a unit conversion, not a
#: time, and a card that asks a sports fan to do arithmetic has already lost
#: the five seconds it had. Eastern is the league's own clock, so it is the
#: one the product prints, always labelled.
EASTERN = ZoneInfo("America/New_York")


def eastern(when: datetime) -> datetime:
    return when.astimezone(EASTERN)


def clock(when: datetime) -> str:
    """"3:30 PM ET" - the time alone, for a row that already has the date."""
    local = eastern(when)
    return f"{local.strftime('%-I:%M %p')} ET"


def day_and_clock(when: datetime) -> str:
    """"Sat 26 Sep · 3:30 PM ET" - the whole thing, for a card header."""
    local = eastern(when)
    return f"{local.strftime('%a %-d %b')} · {clock(when)}"


def day_clock(when: datetime) -> str:
    """"Sat 3:30 PM ET" - the board's compact form."""
    local = eastern(when)
    return f"{local.strftime('%a')} {clock(when)}"


def stamp(when: datetime) -> str:
    """"Sep 22, 2026 7:05 PM ET" - the one freshness format.

    `docs/TIMESTAMP_STANDARD.md`: every visible timestamp in the product uses
    this, in Eastern, with the zone named. A timestamp without a zone is a
    number a reader has to guess about, and a product whose whole claim is
    that its information is current cannot be vague about when.
    """
    local = eastern(when)
    return f"{local.strftime('%b %-d, %Y')} {clock(when)}"


def esc(value: object) -> str:
    return _escape(str(value), quote=True)


def num(value: float | None, digits: int = 1, dash: str = "—") -> str:
    if value is None:
        return dash
    return f"{value:.{digits}f}"


def signed(value: float | None, digits: int = 1, dash: str = "—") -> str:
    if value is None:
        return dash
    return f"{value:+.{digits}f}".replace("-", "−")


def minus(value: float | None, digits: int = 1, dash: str = "—") -> str:
    """A real minus sign. A hyphen in a price column looks like a typo."""
    if value is None:
        return dash
    return f"{value:.{digits}f}".replace("-", "−")


def pct(value: float | None, digits: int = 1, dash: str = "—") -> str:
    if value is None:
        return dash
    return f"{value * 100:.{digits}f}%"


def price(value: object, dash: str = "—") -> str:
    if value in (None, "", "OFF"):
        return dash
    text = str(value)
    return text.replace("-", "−")


def rows(pairs: list[tuple[str, str]], *, lead: bool = True) -> str:
    body = "".join(
        f'<tr><td>{label}</td><td class="{"lead" if lead else ""}">{value}</td></tr>'
        for label, value in pairs
    )
    return f'<table class="rows"><tbody>{body}</tbody></table>'


def table(headers: list[str], body_rows: list[list[str]]) -> str:
    head = "".join(f"<th>{esc(h)}</th>" for h in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>"
        for row in body_rows
    )
    return f'<table class="rows"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'
