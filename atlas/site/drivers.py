"""Section 6: three to five drivers, in English.

The spec is explicit that a card carries three to five drivers and never more,
that each one gets a plain sentence, and that every value carries its FBS
percentile — "95th percentile" is readable, "+0.283 adjusted EPA" alone is
not.

Drivers are ranked by how much they move the projection, so the list is the
model's own reasoning rather than a fixed set of stats.
"""

from __future__ import annotations

from dataclasses import dataclass

from atlas.util import get_logger

LOG = get_logger(__name__)

MAX_DRIVERS = 4


@dataclass(frozen=True)
class Driver:
    name: str
    magnitude: str
    sentence: str
    share: float          # 0..1, how far the bar fills from the centre
    toward_home: bool
    scale_left: str
    scale_right: str
    #: Which side this driver favours, or None where it favours neither -
    #: pace belongs to the game, not to a team. The brief view shows the
    #: favoured team's mark, because three identical dots read as three
    #: negatives and colour alone may never carry meaning.
    favours: str | None = None


def _ordinal(value: float | None) -> str:
    if value is None:
        return "unranked"
    pct = max(1, min(99, round(value * 100)))
    suffix = "th" if 11 <= pct % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(pct % 10, "th")
    return f"{pct}{suffix} percentile"


def _pct(pool, metric, value):
    from atlas.site.data import percentile

    return percentile(pool, metric, value)


def select(card, pool: dict) -> list[Driver]:
    """The drivers that explain this card, strongest first."""
    home, away = card.home, card.away
    candidates: list[tuple[float, Driver]] = []

    def add(weight: float, driver: Driver) -> None:
        candidates.append((abs(weight), driver))

    # --- offensive efficiency -------------------------------------------
    h, a = home.metrics.get("adj_off_epa"), away.metrics.get("adj_off_epa")
    if h is not None and a is not None:
        gap = h - a
        leader, trailer = (home, away) if gap > 0 else (away, home)
        add(gap * 10, Driver(
            name="Offensive efficiency",
            magnitude=f"{leader.abbr} +{abs(gap):.2f} EPA/play",
            sentence=(
                f"{leader.short}'s offence sits in the "
                f"{_ordinal(_pct(pool, 'adj_off_epa', max(h, a)))} of FBS on "
                f"opponent-adjusted EPA; {trailer.short}'s is "
                f"{_ordinal(_pct(pool, 'adj_off_epa', min(h, a)))}."
            ),
            share=min(0.48, abs(gap) * 1.6),
            toward_home=gap > 0,
            scale_left=away.short, scale_right=home.short,
            favours=leader.key,
        ))

    # --- success rate ----------------------------------------------------
    h, a = home.metrics.get("adj_success_rate"), away.metrics.get("adj_success_rate")
    if h is not None and a is not None:
        gap = h - a
        leader, trailer = (home, away) if gap > 0 else (away, home)
        add(gap * 12, Driver(
            name="Success rate",
            magnitude=f"{leader.abbr} +{abs(gap) * 100:.1f} pts",
            sentence=(
                f"{leader.short} succeeds on {max(h, a) * 100:.1f}% of plays "
                f"({_ordinal(_pct(pool, 'adj_success_rate', max(h, a)))}) against "
                f"{trailer.short}'s {min(h, a) * 100:.1f}% "
                f"({_ordinal(_pct(pool, 'adj_success_rate', min(h, a)))})."
            ),
            share=min(0.48, abs(gap) * 2.4),
            toward_home=gap > 0,
            scale_left=away.short, scale_right=home.short,
            favours=leader.key,
        ))

    # --- defence ---------------------------------------------------------
    h, a = home.metrics.get("adj_def_success_rate"), away.metrics.get("adj_def_success_rate")
    if h is not None and a is not None:
        # Lower is better on defence, so the sign flips.
        gap = a - h
        leader, trailer = (home, away) if gap > 0 else (away, home)
        best, worst = min(h, a), max(h, a)
        add(gap * 11, Driver(
            name="Defensive success allowed",
            magnitude=f"{leader.abbr} −{abs(gap) * 100:.1f} pts",
            sentence=(
                f"{leader.short} allows a successful play {best * 100:.1f}% of the "
                f"time ({_ordinal(_pct(pool, 'adj_def_success_rate', best))} — lower "
                f"is better); {trailer.short} {worst * 100:.1f}%."
            ),
            share=min(0.48, abs(gap) * 2.4),
            toward_home=gap > 0,
            scale_left=away.short, scale_right=home.short,
            favours=leader.key,
        ))

    # --- pace and possessions -------------------------------------------
    h, a = home.metrics.get("plays_per_game"), away.metrics.get("plays_per_game")
    if h is not None and a is not None:
        combined = h + a
        share_of_league = _pct(pool, "plays_per_game", combined / 2) or 0.5
        # The bar and the magnitude describe *pace*. Labelling this driver with
        # the total difference would put a number on it that the sentence then
        # contradicts - the bar has to mean what the words say.
        fast = share_of_league > 0.5
        add(6.0, Driver(
            name="Pace and possessions",
            magnitude=f"{combined:.0f} plays · {_ordinal(share_of_league)}",
            sentence=(
                f"A combined {combined:.0f} plays per game — the "
                f"{_ordinal(share_of_league)} of this season's games. "
                + ("Few possessions, which pulls the projected total down."
                   if share_of_league < 0.4 else
                   "A fast game, which lifts the projected total."
                   if share_of_league > 0.6 else
                   "A middling number of possessions either way.")
            ),
            share=min(0.48, abs(share_of_league - 0.5) * 0.9),
            toward_home=fast,
            scale_left="fewer plays", scale_right="more plays",
        ))

    # --- explosiveness ---------------------------------------------------
    h, a = home.metrics.get("adj_explosiveness"), away.metrics.get("adj_explosiveness")
    if h is not None and a is not None:
        gap = h - a
        leader, trailer = (home, away) if gap > 0 else (away, home)
        add(gap * 4, Driver(
            name="Explosiveness",
            magnitude=f"{leader.abbr} +{abs(gap):.2f}",
            sentence=(
                f"{leader.short}'s explosiveness is "
                f"{_ordinal(_pct(pool, 'adj_explosiveness', max(h, a)))} against "
                f"{trailer.short}'s "
                f"{_ordinal(_pct(pool, 'adj_explosiveness', min(h, a)))}."
            ),
            share=min(0.48, abs(gap) * 0.9),
            toward_home=gap > 0,
            scale_left=away.short, scale_right=home.short,
            favours=leader.key,
        ))

    candidates.sort(key=lambda pair: pair[0], reverse=True)
    return [driver for _, driver in candidates[:MAX_DRIVERS]]
