"""The product's language rules, enforced rather than trusted.

`docs/BRAND_GUIDE.md` forbids a list of words on every product surface unless
they are describing a betting market descriptively. That rule is the product
positioning: the moment a card says "play" or "lock", Atlas is a picks service
and the grade becomes marketing.

This mirrors `tests/test_live.py::test_the_tracker_never_computes_a_stake`,
which does the same job for the live tracker's source.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

#: Surfaces a reader can see. The research reports are deliberately excluded:
#: they are about betting markets and say so, at length.
SURFACES = (
    ROOT / "design",
    ROOT / "docs" / "PRODUCT_VISION.md",
    ROOT / "docs" / "BRAND_GUIDE.md",
    ROOT / "docs" / "UI_SYSTEM.md",
    ROOT / "docs" / "ATLAS_CARD_SPEC.md",
    ROOT / "docs" / "PREMIUM_PLAN.md",
)

#: Forbidden outside a descriptive reference to a betting market.
FORBIDDEN = (
    "bet", "bets", "betting", "wager", "wagers", "wagering", "lock", "locks",
    "play", "plays", "hammer", "smash", "unit", "units", "pick", "picks",
    "parlay", "roi", "bankroll", "kelly", "stake", "stakes", "staking",
    "fade", "tail", "sweat",
)

#: A line is cleared when the forbidden word is doing descriptive work. Two
#: kinds of context do that, and they are kept separate so each is auditable.
#:
#: This is a tripwire, not a proof: a sentence that both states a prohibition
#: and breaks it would pass. It exists to catch the drift that actually
#: happens - a driver label, a marketing line, a copied phrase - not an
#: adversary.
PROHIBITION_CUES = (
    "never", "forbidden", "does not", "do not", "may not", "must not",
    "no longer", "prohibited", "banned", "without", "rather than",
    "instead of", "cannot", "not a recommendation", "no selections",
    "picks service", "tout", "is what a", "would be",
)

#: A block-scoped escape for passages that *quote* the vocabulary rather than
#: use it: the brand guide's forbidden-word list, the anti-pattern tables, the
#: "never called" column of the naming table. The marker is visible in the
#: file, so every exemption is auditable in review rather than implicit.
QUOTE_OPEN = "lang-lint: quoting"
QUOTE_CLOSE = "lang-lint: end"

#: Football and CSS vocabulary that collides with the list.
DOMAIN_CUES = (
    "epa", "per play", "plays per game", "play-by-play", "successful play",
    "percentile", "combined plays", "fewer plays", "more plays",
    "% of plays", "of plays", "plays in", "plays per",
    "relative units", "px", "font", "responsive", "betting market",
    "the moneyline", "books quoting", "sportsbook",
)


def _surface_files() -> list[Path]:
    files: list[Path] = []
    for target in SURFACES:
        if target.is_dir():
            files.extend(sorted(p for p in target.rglob("*")
                                if p.suffix in (".html", ".css", ".md")))
        elif target.exists():
            files.append(target)
    return files


def test_the_surfaces_exist():
    """A passing language test over zero files proves nothing."""
    files = _surface_files()
    assert len(files) >= 9, f"expected the product surfaces, found {len(files)}"


@pytest.mark.parametrize("path", _surface_files(), ids=lambda p: p.name)
def test_no_forbidden_language_on_a_product_surface(path: Path):
    text = path.read_text()
    lowered = text.lower()
    offenders: list[str] = []

    quoting = False
    for number, line in enumerate(text.splitlines(), start=1):
        low = line.lower()
        if QUOTE_OPEN in low:
            quoting = True
            continue
        if QUOTE_CLOSE in low:
            quoting = False
            continue
        if quoting:
            continue
        for word in FORBIDDEN:
            if not re.search(rf"\b{re.escape(word)}\b", low):
                continue
            # A line is cleared if any allowed phrase appears on it: the
            # exception is scoped to the sentence, not to the file.
            if any(cue in low for cue in PROHIBITION_CUES + DOMAIN_CUES):
                continue
            offenders.append(f"{path.name}:{number}: {word!r} in {line.strip()[:90]}")

    assert not offenders, (
        "product surfaces may not use this vocabulary outside a descriptive "
        "reference to a betting market:\n" + "\n".join(offenders)
    )
    assert not quoting, f"{path.name} opens a quoting block and never closes it"
    assert lowered  # the file is not empty


def test_the_quoting_escape_is_scoped(tmp_path):
    """The escape must not leak past its closing marker, or one careless
    block silently disables the rule for the rest of a file."""
    path = tmp_path / "doc.md"
    path.write_text(
        "<!-- lang-lint: quoting -->\nnever say lock\n"
        "<!-- lang-lint: end -->\nAtlas likes this lock.\n"
    )
    with pytest.raises(AssertionError, match="lock"):
        test_no_forbidden_language_on_a_product_surface(path)


def test_the_rule_actually_bites(tmp_path):
    """A guard nobody has watched fire is decoration."""
    bad = tmp_path / "card.html"
    bad.write_text("<p>Atlas likes this play. Two units.</p>")
    text = bad.read_text().lower()
    hits = [w for w in FORBIDDEN if re.search(rf"\b{re.escape(w)}\b", text)]
    assert {"play", "units"} <= set(hits)


def test_no_side_is_ever_named_on_a_card():
    """The one thing Atlas will not do. A card that names a side becomes a
    selection the moment somebody screenshots it."""
    banned = re.compile(
        r"\b(take the|lay the|back the|we like|our pick|leans? (over|under)|"
        r"recommended side)\b", re.IGNORECASE,
    )
    for path in _surface_files():
        found = banned.findall(path.read_text())
        assert not found, f"{path.name} names a side: {found}"
