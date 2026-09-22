"""Small HTML helpers.

The site has no template engine on purpose: it is a build-time tool in a
Python repository, four page types deep, and the reports and dashboard in this
codebase already generate HTML this way. Adding a runtime dependency to render
static documents would be a cost with no return.
"""

from __future__ import annotations

from html import escape as _escape


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
