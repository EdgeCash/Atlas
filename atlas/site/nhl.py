"""The NHL on the site: its board and a card per game (docs/MODEL_PLAN_NHL.md, step 6).

The football card is built around a spread; the NHL's market is a price. So
the NHL card keeps the football card's grammar - the five-second view, the
grade as the centrepiece with its disclaimer, the one-tap panels, the same
layout, crests and audited vocabulary - and says hockey's numbers in it:

* **the answer**: Atlas's chance for each side, overtime and the shootout
  included, beside DraftKings' moneyline with its margin taken out, and the
  projected score;
* **the grade**: the rubric the football cards use (`atlas/site/grade.py`),
  its disagreement measured in points of win probability and its calibration
  curve fitted on the NHL's own walk-forward record against the closing line
  (`atlas/models/nhl_projection.calibration`);
* **the panels**: the market (moneyline, puck line, total, as they opened and
  stand), Atlas's grid (the regulation three-way, overtime, the puck line both
  ways, the total at every half-goal line, the likeliest scores), the
  expected starting goalies, and what the model reads for each team.

A card is built for every game in the next eight days that has a projection
(``tracking/nhl_projections.csv``, written by the heavy refresh) and leaves
the site once the puck drops.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import pandas as pd

from atlas.site.data import Side, _slug
from atlas.site.html import clock, day_and_clock, eastern, esc, num, pct, price, table
from atlas.util import get_logger

LOG = get_logger(__name__)

SPORT = "nhl"
UNIT = "points of win probability"
#: The market the grade reads: the NHL's record is kept on the moneyline.
GRADED_MARKET = "moneyline"
#: The team colours when ESPN's metadata has none.
SLATE = "#6b7480"

DISCLOSURE = (
    "<b>What this card is.</b> Research, analytics and market context. Atlas "
    "does not publish selections, does not size anything and does not project "
    "returns. Every figure is computed out of sample from a point-in-time "
    "database: nothing attached to a game uses information that did not exist "
    "before puck drop."
)


@dataclass
class NhlCard:
    game_id: int
    season: int
    kickoff: datetime
    home: Side
    away: Side
    projection: dict
    moneyline: dict = field(default_factory=dict)
    puck: dict = field(default_factory=dict)
    total: dict = field(default_factory=dict)
    venue: str | None = None
    city: str | None = None
    tv: str | None = None
    week: int = 99
    grade: object = None
    sport: str = SPORT

    @property
    def slug(self) -> str:
        return f"{_slug(self.away.name)}-at-{_slug(self.home.name)}"

    @property
    def path(self) -> str:
        return f"nhl/{self.slug}.html"

    @property
    def title(self) -> str:
        return f"{self.away.short} at {self.home.short}"

    @property
    def p_home(self) -> float:
        return float(self.projection["p_home"])

    @property
    def market_home(self) -> float | None:
        """DraftKings' home chance with the margin taken out, or None without both prices."""
        h, a = self.moneyline.get("home"), self.moneyline.get("away")
        if h is None or a is None:
            return None
        from atlas.models.nhl_projection import market_home

        return float(market_home([h], [a])[0])

    @property
    def disagreement(self) -> float | None:
        """Atlas's home chance less the market's, in points of win probability."""
        m = self.market_home
        return None if m is None else 100.0 * (self.p_home - m)


# ---------------------------------------------------------------------------
# Building the cards
# ---------------------------------------------------------------------------


def _latest(projections: pd.DataFrame) -> pd.DataFrame:
    if projections.empty:
        return projections
    p = projections.sort_values("refreshed_at", kind="stable")
    return p.groupby("game_id", as_index=False).tail(1)


def _market(snapshots: pd.DataFrame, game_id: int) -> tuple[dict, dict, dict]:
    """(moneyline, puck line, total) from the poll's DraftKings rows for one game: open and current."""
    s = snapshots[snapshots["game_id"].astype("int64") == int(game_id)]
    s = s.sort_values("captured_at", kind="stable")

    def pick(market: str) -> tuple[dict | None, dict | None]:
        part = s[s["market"] == market]
        return (part.iloc[0].to_dict(), part.iloc[-1].to_dict()) if len(part) else (None, None)

    ml0, ml = pick("moneyline")
    pl0, pl = pick("margin")
    t0, t = pick("total")
    f = lambda v: None if v is None or pd.isna(v) else float(v)  # noqa: E731
    money = {"home": f(ml["price"]), "away": f(ml["other_price"]), "home_open": f(ml0["open_price"]) or f(ml0["price"]),
             "away_open": f(ml0["other_price"])} if ml else {}
    puck = {"home_line": f(pl["line"]), "home_price": f(pl["price"]), "away_price": f(pl["other_price"])} if pl else {}
    total = {"line": f(t["line"]), "over": f(t["price"]), "under": f(t["other_price"]),
             "open_line": f(t0["open_line"]) or f(t0["line"])} if t else {}
    return money, puck, total


def _side(meta_side: dict | None, fallback_name: str, logos: dict) -> Side:
    m = meta_side or {}
    name = m.get("name") or fallback_name
    team_id = m.get("id")
    return Side(key=_slug(name), name=name, short=m.get("short") or name.split(" ")[-1], abbr=m.get("abbr") or "",
                colour=m.get("colour") or SLATE, logo=logos.get(int(team_id)) if team_id else None,
                record=m.get("record"), team_id=team_id)


def _week(games: pd.DataFrame, season: int, kickoff: pd.Timestamp) -> int:
    nhl = games[(games["sport"].astype(str) == SPORT) & (pd.to_numeric(games["season"], errors="coerce") == season)] \
        if "sport" in games else games.iloc[0:0]
    first = pd.to_datetime(nhl["kickoff"], utc=True, errors="coerce").min()
    if pd.isna(first):
        return 99
    return int((kickoff - first).days // 7 + 1)


def build_cards(store, meta: dict, logos: dict, now: datetime, *, bands: dict | None = None,
                curve=None) -> list[NhlCard]:
    """A card for every projected NHL game still to be played, graded where the market has priced it."""
    from atlas.site import grade as grading

    projections = _latest(store.read("nhl_projections"))
    if projections.empty:
        return []
    snapshots, games = store.read("snapshots"), store.read("games")
    names = dict(zip(games["game_id"].astype(str), zip(games["home_team"], games["away_team"], strict=True),
                     strict=True)) if len(games) else {}
    out = []
    for r in projections.to_dict("records"):
        kick = pd.Timestamp(r["kickoff"])
        kick = kick.tz_localize("UTC") if kick.tzinfo is None else kick
        if kick <= pd.Timestamp(now):
            continue
        gid = int(r["game_id"])
        record = meta.get(gid, {})
        home_name, away_name = names.get(str(gid), (r["home_team"], r["away_team"]))
        money, puck, total = _market(snapshots, gid)
        card = NhlCard(game_id=gid, season=int(r["season"]), kickoff=kick.to_pydatetime(),
                       home=_side(record.get("home"), home_name, logos), away=_side(record.get("away"), away_name, logos),
                       projection=r, moneyline=money, puck=puck, total=total, venue=record.get("venue"),
                       city=record.get("city"), tv=record.get("tv"), week=_week(games, int(r["season"]), kick))
        if card.disagreement is not None and bands and curve is not None:
            band = bands.get(grading.band_label(card.disagreement)) or grading.overall(bands)
            card.grade = grading.compute(card.disagreement, band, 1.0, curve=curve,
                                         conditions=grading.Conditions(week=card.week), unit=UNIT)
        out.append(card)
    out.sort(key=lambda c: c.kickoff)
    LOG.info("nhl cards: %d built, %d graded", len(out), sum(1 for c in out if c.grade))
    return out


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _pill(card: NhlCard) -> str:
    if card.grade is None:
        return '<span class="grade-pill none" title="No grade yet">–</span>'
    return (f'<span class="grade-pill {card.grade.tone}" aria-label="Grade {card.grade.letter}">'
            f"{card.grade.letter}</span>")


def _crests(card: NhlCard, root: str) -> str:
    from atlas.site.render import _logo

    return (f'<span class="row-crests">{_logo(card.away, size="small", root=root)}'
            f'{_logo(card.home, size="small", root=root)}</span>')


def _row(card: NhlCard) -> str:
    market = card.market_home
    chance = f"Atlas {card.home.short} {pct(card.p_home, 0)}"
    if market is not None:
        chance += f" · market {pct(market, 0)}"
    line = f"total {num(card.total.get('line'))}" if card.total.get("line") is not None else "no total posted"
    meta = " · ".join(filter(None, [clock(card.kickoff), card.tv]))
    return f"""<div class="game-row" data-game="{card.game_id}">
  <div class="game-main">
    <div class="row-teams">{_crests(card, "")}
      <a class="stretch game-teams" href="{esc(card.path)}">{esc(card.title)}</a></div>
    <div class="game-meta">{esc(meta)}</div>
  </div>
  <div class="game-right">
    <div class="game-numbers">
      <div class="game-line">{esc(chance)}</div>
      <div class="game-meta">{esc(line)} · Atlas {num(card.projection.get("total_mean"))} goals</div>
    </div>
    {_pill(card)}
  </div>
</div>"""


def board_page(cards: list[NhlCard], *, freshness: dict | None = None) -> str:
    """Every NHL game ahead, a day at a time, soonest first."""
    from atlas.site.render import freshness_badge, layout

    if cards:
        by_day: dict[str, list[NhlCard]] = {}
        for c in cards:
            by_day.setdefault(eastern(c.kickoff).strftime("%A %-d %B"), []).append(c)
        blocks = "".join(f"""<section class="section tight">
  <div class="section-head"><h2>{esc(day)}</h2><span class="note">{len(day_cards)} game{'s' if len(day_cards) != 1 else ''}</span></div>
  <div class="card game-list">{"".join(_row(c) for c in day_cards)}</div>
</section>""" for day, day_cards in by_day.items())
    else:
        blocks = '<p class="note">No NHL game in the next eight days has an Atlas number yet.</p>'
    body = f"""<section class="section tight">
  <div class="section-head"><h1>NHL</h1>
    <span class="note">each side's chance, overtime and the shootout included, beside the market's</span></div>
  <p class="note section-caption">A card's grade is how much weight its information deserves, from the NHL
    model's own record against the closing line — not a ranking, and not a recommendation.</p>
</section>
{freshness_badge(("Projections built", (freshness or {}).get("projection", "")),
                 ("Market updated", (freshness or {}).get("market", "")))}
{blocks}"""
    return layout(title="NHL — Atlas projections and grades", body=body, active=SPORT, canonical="nhl.html",
                  description="Atlas's NHL numbers: each side's chance, the projected score and the total, beside "
                              "the market, with a grade from the model's own record. Atlas does not publish selections.")


def _answer(card: NhlCard) -> str:
    p = card.projection
    market = card.market_home
    top = json.loads(p.get("top") or "[]")
    likely = f"{card.home.short} {top[0][0]}, {card.away.short} {top[0][1]} ({pct(top[0][2], 0)})" if top else "—"
    market_line = (f"The market, its margin taken out: {card.home.short} {pct(market, 0)}, "
                   f"{card.away.short} {pct(1 - market, 0)}." if market is not None
                   else "No moneyline is posted yet.")
    return f"""<section class="section tight">
  <div class="card card-pad answer">
    <div class="answer-line"><b>Atlas:</b> {esc(card.home.short)} {pct(card.p_home, 0)},
      {esc(card.away.short)} {pct(1 - card.p_home, 0)} to win, overtime and the shootout included.</div>
    <p class="note">{esc(market_line)}</p>
    <p class="note">Projected score {esc(card.home.short)} {num(p.get("home_mean"))},
      {esc(card.away.short)} {num(p.get("away_mean"))} · the likeliest final {esc(likely)}.</p>
  </div>
</section>"""


def _grade_hero(card: NhlCard) -> str:
    if card.grade is None:
        reason = ("No moneyline is posted yet, so there is nothing to grade Atlas's number against."
                  if card.market_home is None else "Not enough history to grade this card.")
        return f"""<div class="card grade-hero none">
  <div class="grade-mark">–</div>
  <div class="grade-words"><div class="grade-title">Not graded</div>
    <p class="grade-line">{esc(reason)}</p>
    <p class="grade-foot">A grade is how much weight a card's information deserves —
      not a recommendation.</p></div>
</div>"""
    g = card.grade
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


def _drivers(card: NhlCard) -> list[tuple[str, str]]:
    """What the model reads, each side's edge in expected goals a game, largest first."""
    p = card.projection
    h, a = card.home.short, card.away.short
    items = [
        ("5-on-5 play", 0.8 * ((p["off_home"] - p["def_away"]) - (p["off_away"] - p["def_home"]))),
        ("Special teams", 0.1 * ((p["pp_home"] - p["pk_away"]) - (p["pp_away"] - p["pk_home"]))),
        ("Finishing", p["finish_home"] - p["finish_away"]),
        ("Goaltending", p["goalie_home"] - p["goalie_away"]),
        ("Home ice", p.get("home_edge", 0.0)),
    ]
    out = []
    for name, value in sorted(items, key=lambda kv: -abs(kv[1]))[:3]:
        if abs(value) < 0.01:
            continue
        out.append((name, f"{h if value > 0 else a} +{abs(value):.2f} goals a game"))
    if card.projection.get("home_b2b") in (True, "True", 1) or card.projection.get("away_b2b") in (True, "True", 1):
        tired = [s for s, b in ((h, p.get("home_b2b")), (a, p.get("away_b2b"))) if b in (True, "True", 1)]
        out.append(("Rest", f"{' and '.join(tired)} on the second night of a back-to-back"))
    return out


def _why(card: NhlCard) -> str:
    items = _drivers(card)
    if not items:
        return ""
    rows = "".join(f'<li class="why-row"><span class="why-dot" aria-hidden="true"></span>'
                   f'<span class="why-name">{esc(n)}</span><span class="why-val">{esc(v)}</span></li>'
                   for n, v in items)
    return f"""<section class="section tight">
  <div class="section-head"><h2>Why</h2><span class="note">what the model is reading</span></div>
  <ul class="card card-pad why-list">{rows}</ul>
</section>"""


def _panel(summary: str, hint: str, body: str) -> str:
    from atlas.site.render import _panel as panel

    return panel(summary, hint, body)


def _market_panel(card: NhlCard) -> str:
    m, pl, t = card.moneyline, card.puck, card.total
    if not (m or pl or t):
        return _panel("Market snapshot", "not posted yet", '<p class="note">DraftKings has not priced this game yet.</p>')
    rows = []
    if m:
        rows.append([esc(card.away.short), price(_i(m.get("away_open"))), f'<b>{price(_i(m.get("away")))}</b>'])
        rows.append([esc(card.home.short), price(_i(m.get("home_open"))), f'<b>{price(_i(m.get("home")))}</b>'])
    body = table(["Moneyline", "Open", "Current"], rows) if rows else ""
    extra = []
    if pl.get("home_line") is not None:
        fav = card.home.short if pl["home_line"] > 0 else card.away.short
        dog = card.away.short if pl["home_line"] > 0 else card.home.short
        fav_price = pl["home_price"] if pl["home_line"] > 0 else pl["away_price"]
        dog_price = pl["away_price"] if pl["home_line"] > 0 else pl["home_price"]
        extra.append([f"{esc(fav)} −1.5", price(_i(fav_price))])
        extra.append([f"{esc(dog)} +1.5", price(_i(dog_price))])
    if t.get("line") is not None:
        extra.append([f"Over {num(t['line'])}", price(_i(t.get("over")))])
        extra.append([f"Under {num(t['line'])}", price(_i(t.get("under")))])
    if extra:
        body += table(["Puck line and total", "Price"], extra)
    market = card.market_home
    if market is not None:
        body += (f'<p class="note top-gap">De-vigged, the moneyline gives {esc(card.home.short)} a '
                 f'{pct(market)} chance. DraftKings, through ESPN.</p>')
    return _panel("Market snapshot", "moneyline, puck line, total", body)


def _numbers_panel(card: NhlCard) -> str:
    p = card.projection
    three = [[esc(card.home.short) + " in regulation", pct(p.get("p_reg_home"))],
             ["Level after sixty minutes", pct(p.get("p_ot"))],
             [esc(card.away.short) + " in regulation", pct(p.get("p_reg_away"))],
             [esc(card.home.short) + " by two or more", pct(p.get("p_home_minus_1_5"))],
             [esc(card.away.short) + " by two or more", pct(p.get("p_away_minus_1_5"))]]
    totals = [[f"More than {line}", pct(p.get(f"p_over_{line}"))] for line in ("4.5", "5.5", "6.5", "7.5")
              if p.get(f"p_over_{line}") is not None]
    top = json.loads(p.get("top") or "[]")
    scores = ", ".join(f"{card.home.short} {h}–{a} ({pct(q, 0)})" for h, a, q in top)
    body = (table(["Outcome", "Atlas"], three) + table(["Goals in the game", "Atlas"], totals)
            + f'<p class="note top-gap">Expected goals: {esc(card.home.short)} {num(p.get("home_mean"), 2)}, '
              f'{esc(card.away.short)} {num(p.get("away_mean"), 2)}, overtime\'s goal included. The likeliest '
              f'finals: {esc(scores)}.</p>')
    return _panel("Atlas's numbers", "the whole score grid", body)


def _goalies_panel(card: NhlCard) -> str:
    rows = []
    for side, key in ((card.away, "away_goalies"), (card.home, "home_goalies")):
        for g in json.loads(card.projection.get(key) or "[]")[:3]:
            rows.append([esc(side.short), esc(g.get("name") or f"#{g['id']}"), pct(g.get("p"), 0),
                         f"{g.get('gsax', 0.0):+.2f}"])
    if not rows:
        return ""
    body = (table(["Team", "Goalie", "Chance he starts", "Goals saved a game"], rows)
            + '<p class="note top-gap">Atlas prices the expected starter: each goalie by his share of recent starts, '
              'marked down after a start the night before. Goals saved are above expected, a game at the league\'s '
              'shot volume, shrunk hard: a season of starts is still mostly noise.</p>')
    return _panel("Goalies", "the expected starters", body)


def _model_panel(card: NhlCard) -> str:
    p = card.projection
    rows = [["5-on-5 offence", f"{p['off_away']:+.2f}", f"{p['off_home']:+.2f}"],
            ["5-on-5 defence", f"{p['def_away']:+.2f}", f"{p['def_home']:+.2f}"],
            ["Power play", f"{p['pp_away']:+.2f}", f"{p['pp_home']:+.2f}"],
            ["Penalty kill", f"{p['pk_away']:+.2f}", f"{p['pk_home']:+.2f}"],
            ["Finishing", f"{p['finish_away']:+.2f}", f"{p['finish_home']:+.2f}"]]
    body = (table(["Per 60 minutes, against the league", esc(card.away.short), esc(card.home.short)], rows)
            + '<p class="note top-gap">Expected goals for and against at 5-on-5 and on special teams, and goals '
              'scored over expected, each carried across seasons and updated after every game.</p>')
    return _panel("What the model reads", "each team, against the league", body)


def _reliability_panel(card: NhlCard, bands: dict, overall_band) -> str:
    if not bands:
        return ""
    from atlas.site import grade as grading

    active = grading.band_label(card.disagreement) if card.disagreement is not None else None
    order = [label for label in (f"{lo}-{hi}" if hi < 1000 else f"{lo}+" for lo, hi in grading.BANDS) if label in bands]
    rows = [[("<b>" + esc(label) + "</b>") if label == active else esc(label), f"{bands[label].games:,}",
             pct(bands[label].claimed), pct(bands[label].realised)] for label in order]
    if overall_band is not None:
        rows.append(["All cards", f"{overall_band.games:,}", pct(overall_band.claimed), pct(overall_band.realised)])
    body = (table(["Points of win probability from the market", "Games", "Atlas claimed", "Delivered"], rows)
            + '<p class="note top-gap">The NHL model walked forward over every season since 2013-14 it never saw, '
              'against the closing moneyline: how often the side Atlas rated above the market won.</p>')
    return _panel("Reliability", "the model's own record", body)


def _i(v) -> str | None:
    """An American price as text: +130, -150."""
    return None if v is None else f"+{v:.0f}" if v > 0 else f"{v:.0f}"


def card_page(card: NhlCard, *, bands: dict | None = None, overall_band=None, freshness: dict | None = None) -> str:
    from atlas.site.render import NEW_HERE, _logo, freshness_badge, layout, social_tags

    bits = [esc(day_and_clock(card.kickoff))]
    if card.tv:
        bits.append(esc(card.tv))
    if card.venue:
        bits.append(esc(card.venue + (f", {card.city}" if card.city else "")))
    hero = f"""<section class="hero card">
  <div class="hero-teams">
    <div class="hero-team left">{_logo(card.away)}<div class="hero-names"><div class="hero-name">{esc(card.away.short)}</div>
      <div class="hero-meta">{esc(card.away.record or "")}</div></div></div>
    <div class="hero-at">at</div>
    <div class="hero-team right">{_logo(card.home)}<div class="hero-names"><div class="hero-name">{esc(card.home.short)}</div>
      <div class="hero-meta">{esc(card.home.record or "")}</div></div></div>
  </div>
  <div class="hero-kick">{" · ".join(bits)}</div>
</section>"""
    body = "\n".join(filter(None, [
        hero, _answer(card), _grade_hero(card), _why(card),
        freshness_badge(("Projection built", (freshness or {}).get("projection", "")),
                        ("Market updated", (freshness or {}).get("market", "")), root="../"),
        NEW_HERE, '<div class="tier2">', _market_panel(card), _numbers_panel(card), _goalies_panel(card),
        _model_panel(card), _reliability_panel(card, bands or {}, overall_band), "</div>",
        f'<div class="disclosure card-foot">{DISCLOSURE}</div>',
    ]))
    market = card.market_home
    description = (f"{card.title}: Atlas gives {card.home.short} {pct(card.p_home, 0)} to win"
                   + (f" against the market's {pct(market, 0)}" if market is not None else "")
                   + f", a projected {num(card.projection.get('total_mean'))} goals"
                   + f", graded {card.grade.letter if card.grade else 'ungraded'}.")
    return layout(title=f"{card.title} — Atlas NHL projection and grade", body=body, depth=1,
                  description=description, active=SPORT, canonical=card.path,
                  social=social_tags(title=f"{card.title} · Atlas", description=description, url=card.path),
                  structured=_schema(card))


def _schema(card: NhlCard) -> str:
    """SportsEvent: the teams, the venue and the puck drop - the facts on the page, never the numbers."""
    from atlas.site.render import SITE_URL, json_ld

    teams = [{"@type": "SportsTeam", "name": side.name} for side in (card.away, card.home)]
    payload = {"@context": "https://schema.org", "@type": "SportsEvent", "name": card.title,
               "description": f"{card.away.name} at {card.home.name}, NHL.", "startDate": card.kickoff.isoformat(),
               "eventStatus": "https://schema.org/EventScheduled", "sport": "Ice Hockey",
               "url": f"{SITE_URL}/{card.path}", "homeTeam": teams[1], "awayTeam": teams[0], "competitor": teams}
    if card.venue:
        payload["location"] = {"@type": "Place", "name": card.venue}
    return json_ld(payload)


def write(out: Path, cards: list[NhlCard], *, bands: dict | None, overall_band, freshness: dict | None) -> list[str]:
    """Write the board and every card; returns the paths written, for the sitemap."""
    (out / "nhl").mkdir(parents=True, exist_ok=True)
    (out / "nhl.html").write_text(board_page(cards, freshness=freshness))
    paths = ["nhl.html"]
    for card in cards:
        (out / card.path).write_text(card_page(card, bands=bands, overall_band=overall_band, freshness=freshness))
        paths.append(card.path)
    return paths
