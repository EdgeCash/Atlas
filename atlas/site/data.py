"""Assembling one matchup card's worth of data.

Three sources, joined on ESPN's game id:

``warehouse``   opponent-adjusted, point-in-time features for both teams
``tracking``    Atlas's number, and the line as it opened and stands now
``espn``        venue, broadcast, records, ranks and team colours

Every figure that reaches a card passes through here, and anything missing
stays missing: a card reports what it does not have rather than filling the
gap.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

import numpy as np
import pandas as pd
from scipy import stats

from atlas.live.store import Store
from atlas.research.dataset import load_research_frame
from atlas.site import grade as grading
from atlas.site import meta as espn_meta
from atlas.util import get_logger

LOG = get_logger(__name__)

#: Fitted in `reports/atlas_beta_framework.md`. The spread weight is 1.00
#: because the model's contribution could not be told apart from zero.
MARKET_WEIGHT = {"margin": 1.00, "total": 0.89}

#: Out-of-sample residual standard deviations around the closing number.
RESIDUAL_SD = {"margin": 15.413, "total": 15.956}

#: Inputs a complete card needs. Missing ones cost the completeness component.
REQUIRED_FEATURES = (
    "adj_off_epa", "adj_success_rate", "adj_def_success_rate",
    "adj_explosiveness", "adj_pace", "plays_per_game",
)


@dataclass
class Side:
    key: str
    name: str
    short: str
    abbr: str
    colour: str
    logo: str | None = None
    record: str | None = None
    rank: int | None = None
    team_id: int | None = None
    conference: str | None = None
    rest_days: float | None = None
    travel_miles: float | None = None
    metrics: dict = field(default_factory=dict)


@dataclass
class Line:
    """One market, as it opened and as it stands."""

    market: str
    open_line: float | None
    current: float | None
    open_price: float | None
    price: float | None

    @property
    def movement(self) -> float | None:
        if self.open_line is None or self.current is None:
            return None
        return self.current - self.open_line


@dataclass
class Card:
    game_id: int
    season: int
    week: int
    kickoff: datetime
    home: Side
    away: Side
    venue: str | None
    city: str | None
    state: str | None
    tv: str | None
    neutral: bool
    conference_game: bool
    weather: dict
    spread: Line
    total: Line
    moneyline: dict
    books: int
    model_margin: float | None
    model_total: float | None
    grade: grading.Grade | None
    drivers: list = field(default_factory=list)
    completeness: float = 1.0
    missing: list[str] = field(default_factory=list)
    cautions: list[str] = field(default_factory=list)

    # -- derived -----------------------------------------------------------

    @property
    def slug(self) -> str:
        return f"{_slug(self.away.name)}-{_slug(self.home.name)}"

    @property
    def path(self) -> str:
        return f"ncaaf/{self.slug}.html"

    @property
    def title(self) -> str:
        return f"{self.away.short} at {self.home.short}"

    @property
    def anchored_margin(self) -> float | None:
        return _blend(self.spread.current, self.model_margin, MARKET_WEIGHT["margin"])

    @property
    def anchored_total(self) -> float | None:
        return _blend(self.total.current, self.model_total, MARKET_WEIGHT["total"])

    @property
    def total_difference(self) -> float | None:
        if self.model_total is None or self.total.current is None:
            return None
        return self.model_total - self.total.current

    @property
    def margin_difference(self) -> float | None:
        if self.model_margin is None or self.spread.current is None:
            return None
        return self.model_margin - self.spread.current

    @property
    def projected_home(self) -> float | None:
        if self.anchored_total is None or self.anchored_margin is None:
            return None
        return (self.anchored_total + self.anchored_margin) / 2

    @property
    def projected_away(self) -> float | None:
        if self.anchored_total is None or self.anchored_margin is None:
            return None
        return (self.anchored_total - self.anchored_margin) / 2

    @property
    def home_win_probability(self) -> float | None:
        if self.anchored_margin is None:
            return None
        return float(stats.norm.cdf(self.anchored_margin / RESIDUAL_SD["margin"]))

    @property
    def over_probability(self) -> float | None:
        if self.anchored_total is None or self.total.current is None:
            return None
        edge = self.anchored_total - self.total.current
        return float(stats.norm.cdf(edge / RESIDUAL_SD["total"]))

    @property
    def model_win_probability(self) -> float | None:
        if self.model_margin is None:
            return None
        return float(stats.norm.cdf(self.model_margin / RESIDUAL_SD["margin"]))

    @property
    def market_win_probability(self) -> float | None:
        """De-vigged from the two moneyline prices, where both are posted."""
        home = _implied(self.moneyline.get("home_close"))
        away = _implied(self.moneyline.get("away_close"))
        if home is None or away is None or (home + away) == 0:
            return None
        return home / (home + away)

    @property
    def favourite(self) -> Side:
        margin = self.spread.current or 0.0
        return self.home if margin >= 0 else self.away

    @property
    def spread_text(self) -> str:
        if self.spread.current is None:
            return "not posted"
        return f"{self.favourite.abbr} −{abs(self.spread.current):.1f}"


def _slug(name: str) -> str:
    return "".join(c.lower() if c.isalnum() else "-" for c in name).strip("-").replace("--", "-")


def _blend(market: float | None, model: float | None, weight: float) -> float | None:
    if market is None:
        return model
    if model is None:
        return market
    return weight * market + (1 - weight) * model


def _implied(price: object) -> float | None:
    """American odds to an implied probability, vig included."""
    if price in (None, "", "OFF"):
        return None
    try:
        value = float(str(price).replace("+", ""))
    except ValueError:
        return None
    if value == 0:
        return None
    return 100 / (value + 100) if value > 0 else -value / (-value + 100)


def _num(value: object) -> float | None:
    number = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return None if number is None or not np.isfinite(number) else float(number)


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------


def percentile_pool(frame: pd.DataFrame, season: int) -> dict[str, np.ndarray]:
    """Both sides of every game this season, per metric, for percentiles."""
    current = frame[frame["season"] == season]
    pool: dict[str, np.ndarray] = {}
    for metric in REQUIRED_FEATURES:
        home = pd.to_numeric(current.get(f"home_{metric}"), errors="coerce")
        away = pd.to_numeric(current.get(f"away_{metric}"), errors="coerce")
        values = pd.concat([home, away]).dropna().to_numpy()
        if len(values):
            pool[metric] = np.sort(values)
    return pool


def percentile(pool: dict[str, np.ndarray], metric: str, value: float | None) -> float | None:
    values = pool.get(metric)
    if values is None or value is None:
        return None
    return float(np.searchsorted(values, value) / len(values))


def build_cards(*, horizon: int = 8, refresh_meta: bool = False) -> list[Card]:
    """Every scheduled game Atlas can publish a card for."""
    frame = load_research_frame()
    scheduled = frame[frame["actual_margin"].isna()].copy()
    if scheduled.empty:
        LOG.warning(
            "no scheduled games in the warehouse - "
            "run `python -m atlas.warehouse.build --include-scheduled`"
        )
        return []

    store = Store.open()
    numbers = store.read("numbers")
    snapshots = store.read("snapshots")
    metadata = espn_meta.fetch(espn_meta.days_ahead(horizon), refresh=refresh_meta)
    bands = grading.calibration_bands("total")
    curve = grading.calibration_curve("total")

    season = int(scheduled["season"].max())
    pool = percentile_pool(frame, season)
    now = pd.Timestamp.now(tz="UTC")

    cards: list[Card] = []
    for _, row in scheduled.iterrows():
        game_id = int(row["game_id"])
        info = metadata.get(game_id)
        if info is None:
            continue
        kickoff = pd.to_datetime(info["kickoff"], utc=True, errors="coerce")
        if pd.isna(kickoff) or kickoff < now:
            continue
        card = _card(row, info, numbers, snapshots, pool, bands, curve)
        if card is not None:
            cards.append(card)

    cards.sort(key=lambda c: (c.kickoff, c.title))
    LOG.info("built %d cards", len(cards))
    return cards


def _card(row, info, numbers, snapshots, pool, bands, curve) -> Card | None:
    from atlas.site import drivers as driving

    game_id = int(row["game_id"])
    home_meta, away_meta = info["home"], info["away"]

    model = {}
    block = numbers[numbers["game_id"].astype("Int64") == game_id] if not numbers.empty else numbers
    if not block.empty:
        block = block.sort_values("refreshed_at")
        for market in ("margin", "total"):
            rows = block[block["market"] == market]
            if not rows.empty:
                model[market] = _num(rows.iloc[-1]["prediction"])

    lines = {}
    quotes = snapshots[snapshots["game_id"].astype("Int64") == game_id] if not snapshots.empty else snapshots
    books = 0
    if not quotes.empty:
        quotes = quotes.sort_values("captured_at")
        books = int(quotes["book"].nunique())
        for market in ("margin", "total"):
            rows = quotes[quotes["market"] == market]
            if rows.empty:
                continue
            lines[market] = Line(
                market=market,
                open_line=_num(rows.iloc[0]["open_line"]),
                current=_num(rows.iloc[-1]["line"]),
                open_price=_num(rows.iloc[0]["open_price"]),
                price=_num(rows.iloc[-1]["price"]),
            )
    empty = lambda m: Line(m, None, None, None, None)  # noqa: E731

    metrics_home = {m: _num(row.get(f"home_{m}")) for m in REQUIRED_FEATURES}
    metrics_away = {m: _num(row.get(f"away_{m}")) for m in REQUIRED_FEATURES}
    present = sum(1 for m in REQUIRED_FEATURES
                  if metrics_home[m] is not None and metrics_away[m] is not None)
    completeness = present / len(REQUIRED_FEATURES)

    missing = []
    if not lines:
        missing.append("no market posted")
    if not model:
        missing.append("no Atlas number yet")
    if present < len(REQUIRED_FEATURES):
        missing.append("some team metrics unavailable")

    home = Side(
        key="home", name=home_meta["name"], short=home_meta["short"] or home_meta["name"],
        abbr=home_meta["abbr"] or "", colour=home_meta["colour"] or "#3d4652",
        logo=home_meta.get("logo"),
        record=home_meta["record"], rank=home_meta["rank"], team_id=home_meta["id"],
        conference=row.get("home_conference"), rest_days=_num(row.get("home_days_rest")),
        travel_miles=_num(row.get("home_travel_distance")), metrics=metrics_home,
    )
    away = Side(
        key="away", name=away_meta["name"], short=away_meta["short"] or away_meta["name"],
        abbr=away_meta["abbr"] or "", colour=away_meta["colour"] or "#9aa1aa",
        logo=away_meta.get("logo"),
        record=away_meta["record"], rank=away_meta["rank"], team_id=away_meta["id"],
        conference=row.get("away_conference"), rest_days=_num(row.get("away_days_rest")),
        travel_miles=_num(row.get("away_travel_distance")), metrics=metrics_away,
    )

    card = Card(
        game_id=game_id,
        season=int(row["season"]),
        week=int(row["week"]),
        kickoff=pd.to_datetime(info["kickoff"], utc=True).to_pydatetime(),
        home=home, away=away,
        venue=info.get("venue"), city=info.get("city"), state=info.get("state"),
        tv=info.get("tv"), neutral=bool(info.get("neutral")),
        conference_game=bool(info.get("conference_game")),
        weather={
            "temp": _num(row.get("weather_temp")),
            "wind": _num(row.get("weather_wind")),
            "precip": _num(row.get("weather_precip")),
        },
        spread=lines.get("margin", empty("margin")),
        total=lines.get("total", empty("total")),
        moneyline=info.get("moneyline") or {},
        books=books,
        model_margin=model.get("margin"),
        model_total=model.get("total"),
        grade=None,
        completeness=completeness,
        missing=missing,
    )

    difference = card.total_difference
    if difference is not None:
        band = bands.get(grading.band_label(difference))
        if band is not None:
            card.grade = grading.compute(
                difference, band, completeness, curve=curve,
                conditions=grading.Conditions(week=int(row["week"]),
                                              movement=card.total.movement),
            )
    card.drivers = driving.select(card, pool)
    card.cautions = cautions(card)
    return card


def cautions(card: Card) -> list[str]:
    """Design rule 5, question 5: what should make a reader careful here?

    Specific to this game and computed, not a boilerplate warning. A card with
    nothing to flag says so rather than inventing a worry, because a caution
    that appears on every card is read as decoration within a week.
    """
    out: list[str] = []
    band = card.grade.band if card.grade else None
    difference = card.total_difference

    if band and difference is not None and abs(difference) >= 6:
        out.append(
            f"Atlas sits {abs(difference):.1f} points from the market. Cards in "
            f"the {band.label} band have claimed {band.claimed:.0%} accuracy and "
            f"delivered {band.realised:.0%}."
        )
    if card.books <= 1:
        out.append(
            "One book is quoting this game, so the market number has no depth "
            "behind it and may move sharply."
        )
    if card.spread.current is not None and abs(card.spread.current) >= 24:
        out.append(
            f"A {abs(card.spread.current):.0f}-point spread. Lopsided games have "
            "the widest range of outcomes and the least useful history."
        )
    # Deliberately not here: "it is week 4". That is true of every card on the
    # board this week, and a caution that appears on every card is read as
    # decoration within a week. It belongs once, on the board.
    if card.completeness < 1.0:
        missing = int(round((1 - card.completeness) * len(REQUIRED_FEATURES)))
        out.append(
            f"{missing} of {len(REQUIRED_FEATURES)} team metrics are missing, "
            "which lowers the data-completeness component of the grade."
        )
    total_move, model_direction = card.total.movement, difference
    if total_move and model_direction and (total_move > 0) != (model_direction > 0):
        out.append(
            "Atlas and the market have moved opposite ways on the total since "
            "it opened."
        )
    return out[:3]


#: A pairing counts as a rivalry when it has been played in at least this many
#: of the seasons the warehouse holds. Computed, not curated: Atlas has no
#: editorial list of rivalries and inventing one would be a claim the data
#: cannot support. An unbroken annual series is what a rivalry is operationally,
#: and the board states the definition beside the section so it can be argued
#: with.
RIVALRY_SEASONS = 8


def rivalry_pairs(frame: pd.DataFrame | None = None) -> set[frozenset]:
    """Team-id pairs that meet nearly every season.

    Keyed on ESPN team ids rather than names: the warehouse and the scoreboard
    spell half of college football differently, and a name join silently
    returns nothing.
    """
    frame = load_research_frame() if frame is None else frame
    played = frame.dropna(subset=["away_team_id", "home_team_id"])
    pairs: dict[frozenset, set] = {}
    for away, home, season in zip(played["away_team_id"], played["home_team_id"],
                                  played["season"], strict=True):
        pairs.setdefault(frozenset((int(away), int(home))), set()).add(int(season))
    return {pair for pair, seasons in pairs.items() if len(seasons) >= RIVALRY_SEASONS}


def is_rivalry(card: Card, pairs: set[frozenset]) -> bool:
    if card.home.team_id is None or card.away.team_id is None:
        return False
    return frozenset((int(card.home.team_id), int(card.away.team_id))) in pairs


def generated_at() -> str:
    return datetime.now(UTC).strftime("%d %b %Y %H:%M UTC")
