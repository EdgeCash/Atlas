"""Which Polymarket event is which Atlas game.

Polymarket names a game by its teams' short names ("Chiefs vs. Seahawks",
"Jacksonville State vs. New Mexico State", "Avalanche vs. Utah") and its
start; Atlas's games (``tracking/games.csv``, from ESPN's scoreboards) carry
full names and a kickoff. A pair matches when the sport is the same, the
starts are within :data:`SLACK` of each other, and each Polymarket name is
contained in the ESPN name on the same side - the away name in the away
team, the home in the home. A game that would match only with the sides
swapped is left unmatched and logged: a swapped match would invert every
spread.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime

import pandas as pd

from atlas.util import get_logger

LOG = get_logger(__name__)

#: Games this far ahead are matched and priced.
HORIZON = pd.Timedelta(days=8)
#: And this far back, so a game in progress keeps its quotes attached for the close.
BEHIND = pd.Timedelta(hours=6)
#: Polymarket's start and ESPN's kickoff may disagree by a little.
SLACK = pd.Timedelta(hours=3)

_WORDS = {"st": "state"}
#: Polymarket's short names that are not a substring of ESPN's, normalised.
ALIASES = {"umass": "massachusetts", "louisiana monroe": "ul monroe", "ul lafayette": "louisiana",
           "pitt": "pittsburgh", "uconn": "uconn", "usf": "south florida", "ucf": "ucf"}


def _plain(name) -> str:
    """Lowercased, accents and punctuation dropped, hyphens as spaces, parentheses kept as markers."""
    if name is None or (isinstance(name, float) and name != name):
        return ""
    text = unicodedata.normalize("NFKD", str(name))
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower()
    text = re.sub(r"['\u2019.,]", "", text).replace("-", " ")
    return re.sub(r"\s+", " ", text).strip()


def tokens(name) -> set[str]:
    """The words of a team name, lowercased, punctuation dropped, "St." read as "State"; a parenthetical
    qualifier ("Miami (FL)") is kept as its own word."""
    text = _plain(name)
    text = ALIASES.get(re.sub(r"\s*\(.*?\)", "", text).strip(), text)
    out = set()
    for w in re.sub(r"[()]", " ", text).split():
        out.add(_WORDS.get(w, w))
    return out


def qualifiers(name) -> set[str]:
    """The parenthetical words of a name: "fl" in "Miami (FL)"."""
    return {q.strip().lower() for q in re.findall(r"\((.*?)\)", _plain(name))}


def words(name) -> list[str]:
    """The words of a name in order, qualifiers dropped, as :func:`tokens` spells them."""
    text = _plain(name)
    text = ALIASES.get(re.sub(r"\s*\(.*?\)", "", text).strip(), text)
    text = re.sub(r"\(.*?\)", " ", text)
    return [_WORDS.get(w, w) for w in text.split()]


def score(poly_name, espn_name) -> int:
    """How well a Polymarket name names an ESPN team: 2 when it is the team's name less its mascot (one or
    two words) or the mascot itself; 1 when its words merely all appear in ESPN's ("Texas" in "Texas
    Tech"); 0 otherwise. Where both carry a qualifier they must agree ("Miami (OH)" is not "Miami (FL)")."""
    pq, eq = qualifiers(poly_name), qualifiers(espn_name)
    if pq and eq and pq != eq:
        return 0
    p, e = words(poly_name), words(espn_name)
    if not p or not e or not set(p) <= set(e):
        return 0
    if p == e or p == e[:-1] or p == e[-1:]:
        return 2
    # A two-word mascot ("Ragin' Cajuns", "Red Raiders"), unless the second-last word is a school's own
    # ("Oklahoma State Cowboys" is not Oklahoma).
    if p == e[:-2] and e[-2] not in ("state", "tech", "a&m", "southern", "northern", "central"):
        return 2
    return 1


def agrees(poly_name, espn_name) -> bool:
    return score(poly_name, espn_name) > 0


def sport_of(games: pd.DataFrame, projections: pd.DataFrame | None, nhl_projections: pd.DataFrame | None) -> pd.Series:
    """Each game's sport: the scoreboard's where recorded, else the projection that priced it."""
    out = games["sport"].astype("string") if "sport" in games else pd.Series([pd.NA] * len(games), index=games.index,
                                                                           dtype="string")
    known: dict[str, str] = {}
    if nhl_projections is not None and len(nhl_projections):
        known.update({str(g): "nhl" for g in nhl_projections["game_id"]})
    if projections is not None and len(projections) and "sport" in projections:
        known.update({str(g): str(s) for g, s in zip(projections["game_id"], projections["sport"], strict=True)})
    filled = games["game_id"].astype(str).map(known)
    out = out.where(out.notna() & (out != ""), filled)
    return out


def upcoming(games: pd.DataFrame, now: datetime, projections: pd.DataFrame | None = None,
             nhl_projections: pd.DataFrame | None = None) -> pd.DataFrame:
    """Atlas's games from a few hours ago to the horizon, with their sport."""
    if games.empty:
        return games.iloc[0:0].assign(sport=pd.Series(dtype="string"))
    g = games.assign(sport=sport_of(games, projections, nhl_projections))
    kick = pd.to_datetime(g["kickoff"], utc=True, errors="coerce")
    g = g[(kick > pd.Timestamp(now) - BEHIND) & (kick <= pd.Timestamp(now) + HORIZON) & g["sport"].notna()]
    return g.reset_index(drop=True)


PAIR_COLUMNS = ["event_id", "game_id", "sport", "kickoff", "season", "week", "home_team", "away_team", "label"]


def label(away, home) -> str:
    return f"{away} @ {home}"


def match(quotes: pd.DataFrame, games: pd.DataFrame) -> pd.DataFrame:
    """One row per Polymarket event matched to an Atlas game."""
    if quotes.empty or games.empty:
        return pd.DataFrame(columns=PAIR_COLUMNS)
    events = quotes.drop_duplicates("event_id")[["event_id", "sport", "game_start", "away", "home"]]
    kick = pd.to_datetime(games["kickoff"], utc=True, errors="coerce")
    rows = []
    for ev in events.itertuples():
        start = pd.to_datetime(ev.game_start, utc=True, errors="coerce")
        if pd.isna(start):
            continue
        near = games[(games["sport"].astype(str) == str(ev.sport)) & ((kick - start).abs() <= SLACK)]
        best, best_key = None, None
        swapped = False
        for g in near.itertuples():
            gap = abs(pd.to_datetime(g.kickoff, utc=True) - start)
            a, h = score(ev.away, g.away_team), score(ev.home, g.home_team)
            if a and h:
                key = (-(a + h), gap)
                if best is None or key < best_key:
                    best, best_key = g, key
            elif agrees(ev.away, g.home_team) and agrees(ev.home, g.away_team):
                swapped = True
        if best is None:
            if swapped:
                LOG.info("polymarket: %s matches an Atlas game only with the sides swapped; left unmatched",
                         ev.event_id)
            continue
        rows.append({"event_id": ev.event_id, "game_id": str(best.game_id), "sport": str(ev.sport),
                     "kickoff": best.kickoff, "season": getattr(best, "season", None),
                     "week": getattr(best, "week", None), "home_team": best.home_team, "away_team": best.away_team,
                     "label": label(best.away_team, best.home_team), "_score": -best_key[0], "_gap": best_key[1]})
    if not rows:
        return pd.DataFrame(columns=PAIR_COLUMNS)
    pairs = pd.DataFrame(rows).sort_values(["_score", "_gap"], ascending=[False, True], kind="stable")
    # One event per game: the better-named, then the closest start, wins when two events claim one game.
    pairs = pairs.drop_duplicates("game_id", keep="first").drop(columns=["_score", "_gap"])
    return pairs.reindex(columns=PAIR_COLUMNS).reset_index(drop=True)


def attach(quotes: pd.DataFrame, pairs: pd.DataFrame) -> pd.DataFrame:
    """The quotes with their Atlas game, where matched; every quote is kept, matched or not."""
    if quotes.empty:
        return quotes
    q = quotes.drop(columns=[c for c in ("game_id", "kickoff", "season", "week", "home_team", "away_team", "label")
                             if c in quotes and c != "game_id"])
    if pairs.empty:
        return q.assign(kickoff=None, season=None, week=None, home_team=None, away_team=None, label=None)
    p = pairs.drop(columns="sport").rename(columns={"game_id": "_game"})
    out = q.merge(p, on="event_id", how="left")
    out["game_id"] = out["_game"].where(out["_game"].notna(), out["game_id"] if "game_id" in out else None)
    return out.drop(columns="_game")
