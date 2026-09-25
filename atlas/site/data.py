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

#: Below this many games of a team's own evidence this season, the card says
#: the number is still mostly the preseason expectation.
THIN_EVIDENCE_GAMES = 2

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
class Projection:
    """Atlas's own number for the game, from ``tracking/projections.csv``.

    Means are decimal and never rounded; ``margin_mean`` is home minus away,
    positive when the home side is the stronger. ``home``/``away`` carry the
    state's view of each team in points above FBS average, with its rank and
    how many games of this season's evidence it rests on.
    """

    margin_mean: float
    margin_sd: float
    total_mean: float
    total_sd: float
    home_mean: float
    away_mean: float
    p_home: float
    total_lo: float
    total_hi: float
    top_home: int
    top_away: int
    top_p: float
    hfa: float = 0.0
    pace_adj: float = 0.0
    wind_adj: float = 0.0
    # P(over a posted total) given that total: the share of the model's gap
    # to the line that is real, and the sd about the line once it is taken.
    # Absent (rows published before the fit), P(over) reads off total_mean
    # and total_sd.
    over_shrink: float | None = None
    over_sd: float | None = None
    home: dict = field(default_factory=dict)
    away: dict = field(default_factory=dict)
    teams: int | None = None
    version: str = ""
    refreshed_at: str = ""

    @property
    def games_of_evidence(self) -> int | None:
        games = [side.get("games") for side in (self.home, self.away) if side.get("games") is not None]
        return None if not games else int(min(games))


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
    projection: Projection | None
    grade: grading.Grade | None
    drivers: list = field(default_factory=list)
    completeness: float = 1.0
    missing: list[str] = field(default_factory=list)
    cautions: list[str] = field(default_factory=list)
    postseason: bool = False
    sport: str = "ncaaf"
    matchup: object | None = None          # atlas.site.matchup.Matchup, attached by the build

    # -- derived -----------------------------------------------------------

    @property
    def slug(self) -> str:
        return f"{_slug(self.away.name)}-{_slug(self.home.name)}"

    @property
    def path(self) -> str:
        return f"{self.sport}/{self.slug}.html"

    @property
    def title(self) -> str:
        return f"{self.away.short} at {self.home.short}"

    # The model's number is the model's number. Nothing here blends it with
    # the market; the market is on the card for comparison.

    @property
    def model_margin(self) -> float | None:
        """Home minus away, the model's mean."""
        return None if self.projection is None else self.projection.margin_mean

    @property
    def model_total(self) -> float | None:
        return None if self.projection is None else self.projection.total_mean

    @property
    def market_margin(self) -> float | None:
        """The market's home margin. The live spread is captured home-oriented
        (`atlas/live/provider.py`): positive when the home side is favored,
        the same convention as the model's ``margin_mean``."""
        return self.spread.current

    @property
    def total_difference(self) -> float | None:
        if self.model_total is None or self.total.current is None:
            return None
        return self.model_total - self.total.current

    @property
    def margin_difference(self) -> float | None:
        """Model minus market on the home margin: positive means Atlas likes the home side more."""
        if self.model_margin is None or self.market_margin is None:
            return None
        return self.model_margin - self.market_margin

    @property
    def projected_home(self) -> float | None:
        return None if self.projection is None else self.projection.home_mean

    @property
    def projected_away(self) -> float | None:
        return None if self.projection is None else self.projection.away_mean

    @property
    def home_win_probability(self) -> float | None:
        """From the grid, key numbers and all."""
        return None if self.projection is None else self.projection.p_home

    @property
    def model_win_probability(self) -> float | None:
        return self.home_win_probability

    @property
    def over_probability(self) -> float | None:
        """P(total above the current market total), from the model's total.

        Read given the line where the projection carries that fit: most of a
        gap to the market is the model's own error, and the total's own sd
        would state every point of it as real.
        """
        p = self.projection
        if p is None or self.total.current is None:
            return None
        line = self.total.current
        if p.over_shrink is not None and p.over_sd is not None and p.over_sd > 0:
            return float(stats.norm.sf(-p.over_shrink * (p.total_mean - line) / p.over_sd))
        return float(stats.norm.sf((line - p.total_mean) / p.total_sd))

    @property
    def cover_probability(self) -> float | None:
        """P(home margin above the current market margin), from the model's margin."""
        if self.projection is None or self.market_margin is None:
            return None
        return float(stats.norm.sf((self.market_margin - self.projection.margin_mean) / self.projection.margin_sd))

    @property
    def model_favorite(self) -> Side:
        return self.home if (self.model_margin or 0.0) >= 0 else self.away

    @property
    def market_win_probability(self) -> float | None:
        """De-vigged from the two moneyline prices, where both are posted."""
        home = _implied(self.moneyline.get("home_close"))
        away = _implied(self.moneyline.get("away_close"))
        if home is None or away is None or (home + away) == 0:
            return None
        return home / (home + away)

    @property
    def favorite(self) -> Side:
        margin = self.spread.current or 0.0
        return self.home if margin >= 0 else self.away

    @property
    def spread_text(self) -> str:
        if self.spread.current is None:
            return "not posted"
        return f"{self.favorite.abbr} −{abs(self.spread.current):.1f}"


def _slug(name: str) -> str:
    return "".join(c.lower() if c.isalnum() else "-" for c in name).strip("-").replace("--", "-")


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


def _scheduled(sport: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(the sport's research frame, its scheduled rows keyed by ESPN's game id)."""
    if sport == "nfl":
        from atlas.research.nfl_dataset import load_nfl_frame

        frame = load_nfl_frame()
        scheduled = frame[frame["actual_margin"].isna()].copy()
        # The NFL frame is keyed by nflverse's id; the live layer by ESPN's.
        scheduled = scheduled.dropna(subset=["espn_id"]).assign(game_id=lambda d: d["espn_id"].astype("int64"))
        return frame, scheduled
    frame = load_research_frame()
    return frame, frame[frame["actual_margin"].isna()].copy()


def build_cards(*, horizon: int = 8, refresh_meta: bool = False, sport: str = "ncaaf") -> list[Card]:
    """Every scheduled game Atlas can publish a card for, in one sport."""
    frame, scheduled = _scheduled(sport)
    if scheduled.empty:
        LOG.warning("no scheduled %s games in the warehouse - rebuild it with scheduled games", sport)
        return []

    store = Store.open()
    projections = store.read("projections")
    if not projections.empty:
        projections = projections[projections["sport"].fillna("ncaaf").astype(str) == sport]
    snapshots = store.read("snapshots")
    metadata = espn_meta.fetch(espn_meta.days_ahead(horizon), refresh=refresh_meta, sport=sport)
    bands = grading.calibration_bands(sport=sport)
    curve = grading.calibration_curve(sport=sport)

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
        card = _card(row, info, projections, snapshots, pool, bands, curve, sport=sport)
        if card is not None:
            cards.append(card)

    cards.sort(key=lambda c: (c.kickoff, c.title))
    LOG.info("built %d %s cards", len(cards), sport)
    return cards


def _projection(projections: pd.DataFrame, game_id: int) -> Projection | None:
    """The newest projection for a game, or None where the model has none."""
    if projections.empty:
        return None
    block = projections[projections["game_id"].astype("Int64") == game_id]
    if block.empty:
        return None
    row = block.sort_values("refreshed_at").iloc[-1]
    means = {k: _num(row.get(k)) for k in ("margin_mean", "margin_sd", "total_mean", "total_sd",
                                            "home_mean", "away_mean", "p_home", "total_lo", "total_hi", "top_p")}
    if any(v is None for v in means.values()):
        return None

    def side(prefix: str) -> dict:
        out = {k: _num(row.get(f"{prefix}_{k}")) for k in ("off", "def", "net", "sd_off", "sd_def", "rank", "games",
                                                            "qb_pts", "qb_sd")}
        out = {k: (int(v) if k in ("rank", "games") and v is not None else v) for k, v in out.items()}
        name = row.get(f"{prefix}_qb")
        out["qb"] = None if name is None or pd.isna(name) or not str(name).strip() else str(name)
        return out

    teams = _num(row.get("teams"))
    return Projection(
        **means,
        top_home=int(_num(row.get("top_home")) or 0), top_away=int(_num(row.get("top_away")) or 0),
        hfa=_num(row.get("hfa")) or 0.0, pace_adj=_num(row.get("pace_adj")) or 0.0,
        wind_adj=_num(row.get("wind_adj")) or 0.0,
        over_shrink=_num(row.get("total_over_shrink")), over_sd=_num(row.get("total_over_sd")),
        home=side("home"), away=side("away"), teams=None if teams is None else int(teams),
        version=str(row.get("model_version") or ""), refreshed_at=str(row.get("refreshed_at") or ""),
    )


def _card(row, info, projections, snapshots, pool, bands, curve, sport: str = "ncaaf") -> Card | None:
    from atlas.site import drivers as driving

    game_id = int(row["game_id"])
    home_meta, away_meta = info["home"], info["away"]
    projection = _projection(projections, game_id)

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
    if projection is None:
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
        projection=projection,
        grade=None,
        completeness=completeness,
        missing=missing,
        postseason=str(row.get("season_type") or "regular") != "regular",
        sport=sport,
    )

    difference = card.margin_difference
    if difference is not None:
        band = bands.get(grading.band_label(difference))
        if band is not None:
            card.grade = grading.compute(
                difference, band, completeness, curve=curve,
                conditions=grading.Conditions(week=int(row["week"]),
                                              movement=card.spread.movement),
            )
    card.drivers = driving.select(card, pool)
    card.cautions = cautions(card)
    return card


@dataclass
class Result:
    """One completed game, from one team's side: what Atlas said before kickoff and what happened.

    Margins are the team's own, positive when it wins by that much.
    """

    kickoff: datetime
    opponent: str
    home: bool
    atlas: float
    market: float | None
    final: float

    @property
    def atlas_error(self) -> float:
        return abs(self.final - self.atlas)

    @property
    def market_error(self) -> float | None:
        return None if self.market is None else abs(self.final - self.market)


def team_results(cards: list[Card], frame: pd.DataFrame, projections: pd.DataFrame) -> dict[int, list[Result]]:
    """This season's completed games that Atlas projected *before* kickoff, per team, newest first.

    Keyed by ESPN's team id, as a card's sides are. A projection counts only
    if it was published before the game started: the last one before kickoff
    is the number Atlas stood behind, and a later one is not a forecast.
    """
    if not cards or frame.empty or projections.empty or "espn_id" not in frame:
        return {}
    season = max(c.season for c in cards)
    games, ids, names = _team_map(cards, frame)
    done = games[(games["season"] == season) & games["actual_margin"].notna()]
    if done.empty:
        return {}
    proj = projections.copy()
    proj["game_id"] = pd.to_numeric(proj["game_id"], errors="coerce").astype("Int64")
    proj["published"] = pd.to_datetime(proj["refreshed_at"], utc=True, errors="coerce")
    done = done.assign(kick=pd.to_datetime(done["kickoff"], utc=True, errors="coerce"))
    merged = proj.merge(done[["espn", "kick", "home_team_id", "away_team_id", "home_team", "away_team",
                              "actual_margin", "closing_spread"]],
                        left_on="game_id", right_on="espn", suffixes=("", "_game"))
    merged = merged[merged["published"] < merged["kick"]].sort_values("published")
    last = merged.drop_duplicates("game_id", keep="last")
    out: dict[int, list[Result]] = {}
    for _, g in last.iterrows():
        margin = _num(g["margin_mean"])
        if margin is None:
            continue
        close = _num(g["closing_spread"])
        for prefix, other, sign in (("home", "away", 1.0), ("away", "home", -1.0)):
            espn_team = ids.get(int(g[f"{prefix}_team_id_game"]))
            if espn_team is None:
                continue
            opponent = names.get(int(g[f"{other}_team_id_game"])) or str(g[f"{other}_team"])
            out.setdefault(espn_team, []).append(Result(
                kickoff=g["kick"].to_pydatetime(), opponent=opponent, home=prefix == "home",
                atlas=sign * margin, market=None if close is None else -sign * close,
                final=sign * float(g["actual_margin"])))
    for rows in out.values():
        rows.sort(key=lambda r: r.kickoff, reverse=True)
    return out


def _team_map(cards: list[Card], frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[int, int], dict[int, str]]:
    """(games keyed by ESPN id, warehouse team id -> ESPN team id, warehouse team id -> short name).

    The warehouse numbers NFL teams its own way and the cards carry ESPN's;
    a card's game is the one place both are known.
    """
    games = frame.dropna(subset=["espn_id"]).assign(espn=lambda d: d["espn_id"].astype("int64"))
    by_espn = games.set_index("espn")
    ids: dict[int, int] = {}
    names: dict[int, str] = {}
    for card in cards:
        if card.game_id not in by_espn.index:
            continue
        row = by_espn.loc[card.game_id]
        for side, prefix in ((card.home, "home"), (card.away, "away")):
            ids[int(row[f"{prefix}_team_id"])] = side.team_id
            names[int(row[f"{prefix}_team_id"])] = side.short
    return games, ids, names


def team_win_loss(cards: list[Card], frame: pd.DataFrame) -> dict[int, str]:
    """Each team's regular-season record this season, from the warehouse, keyed by ESPN team id.

    ESPN's scoreboard carries no record on a game that has not started, so the
    record is counted from the results rather than left blank.
    """
    if not cards or frame.empty or "espn_id" not in frame:
        return {}
    season = max(c.season for c in cards)
    games, ids, _ = _team_map(cards, frame)
    done = games[(games["season"] == season) & games["actual_margin"].notna()
                 & (games.get("season_type", "regular") == "regular")]
    tally: dict[int, list[int]] = {}
    for _, g in done.iterrows():
        m = float(g["actual_margin"])
        for prefix, sign in (("home", 1.0), ("away", -1.0)):
            espn_team = ids.get(int(g[f"{prefix}_team_id"]))
            if espn_team is None:
                continue
            counts = tally.setdefault(espn_team, [0, 0, 0])
            counts[0 if sign * m > 0 else 1 if sign * m < 0 else 2] += 1
    return {team: f"{won}-{lost}" + (f"-{tied}" if tied else "") for team, (won, lost, tied) in tally.items()}


def offense_with_quarterback(view: dict) -> float | None:
    """The side's offense as the forecast uses it: the team's own plus its expected starter's.

    The state carries the quarterback separately and adds him to the offense
    for the game; a reader comparing offenses should see what the forecast adds.
    """
    off = view.get("off")
    if off is None:
        return None
    return off + (view.get("qb_pts") or 0.0)


def cautions(card: Card) -> list[str]:
    """Design rule 5, question 5: what should make a reader careful here?

    Specific to this game and computed, not a boilerplate warning. A card with
    nothing to flag says so rather than inventing a worry, because a caution
    that appears on every card is read as decoration within a week.
    """
    out: list[str] = []
    band = card.grade.band if card.grade else None
    difference = card.margin_difference

    evidence = card.projection.games_of_evidence if card.projection else None
    if evidence is not None and evidence <= THIN_EVIDENCE_GAMES:
        thin = min((card.home, card.away),
                   key=lambda s: (card.projection.home if s is card.home else card.projection.away).get("games", 0))
        out.append(
            f"Atlas has seen {evidence} game{'s' if evidence != 1 else ''} from {thin.short} this "
            "season, so its number here is still mostly its preseason expectation."
        )
    if card.postseason:
        out.append(
            ("A playoff game. " if card.sport == "nfl" else "A bowl or playoff game. ")
            + "Atlas is fitted on the regular season only; "
            + ("motivation and rest are not in its number." if card.sport == "nfl"
               else "opt-outs and motivation are not in its number.")
        )
    if band and difference is not None and abs(difference) >= 6:
        # The grade block directly above already gives this game's
        # claimed-versus-delivered figures, so repeating them here spent a
        # caution on a sentence the reader has just read. This says the part
        # the grade does not: what a reader should do about it. And it says
        # it without the word "band", which is research vocabulary that means
        # nothing to somebody who arrived from a link.
        out.append(
            f"Atlas is {abs(difference):.1f} points away from the market on the spread. "
            "That is the range where its projection has been least worth "
            "leaning on — read the drivers and the market context instead."
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
    total_move, model_direction = card.total.movement, card.total_difference
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
    """When this build ran, in the product's one timestamp format.

    Only ever the build's own clock. Anything a reader is told about how
    current the *market* is comes from the poll's recorded time, never from
    here - a rebuild that ran against a failed poll must not advertise itself
    as fresh market data.
    """
    from atlas.site.html import stamp

    return stamp(datetime.now(UTC))
