"""Polymarket US events and markets in the gateway's shape, for tests.

The shapes are the ones `atlas/polymarket/source.py` and `props.py` read,
as the API served them on 23 October 2026: an event with its two teams
listed away first; a market with a long and a short side, the long side's
best bid and ask, a fee coefficient and a status.
"""

from __future__ import annotations

OPEN = "MARKET_STATUS_OPEN"
FEE = 0.0695


def team(team_id: int, name: str, safe: str | None = None, abbreviation: str | None = None) -> dict:
    return {"id": team_id, "name": name, "safeName": safe or name, "abbreviation": abbreviation or name[:3].lower(),
            "alias": name.split()[-1]}


def market(mid, kind: str, question: str, long_label: str, short_label: str, bid: float, ask: float, *,
           line=None, long_team=None, short_team=None, fee: float = FEE, status: str = OPEN, slug: str | None = None,
           start: str = "2026-10-24T19:30:00Z", side_ids=None, tick: float = 0.01) -> dict:
    side_ids = side_ids or (f"s{mid}a", f"s{mid}b")
    return {"id": str(mid), "slug": slug or f"m{mid}", "question": question, "sportsMarketType": kind, "line": line,
            "status": status, "active": True, "closed": False, "feeCoefficient": fee,
            "bestBidQuote": {"value": f"{bid:.4f}", "currency": "USD"},
            "bestAskQuote": {"value": f"{ask:.4f}", "currency": "USD"}, "gameStartTime": start,
            "minimumTradeQty": 0.01, "orderPriceMinTickSize": tick, "outcomes": [long_label, short_label],
            "marketSides": [
                {"id": side_ids[0], "description": long_label, "long": True, "teamId": long_team, "price": f"{bid:.4f}"},
                {"id": side_ids[1], "description": short_label, "long": False, "teamId": short_team,
                 "price": f"{ask:.4f}"}]}


def moneyline(mid, sport: str, away: dict, home: dict, bid: float, ask: float, **kw) -> dict:
    """The away team is the long side, as the gateway lists it."""
    return market(mid, f"{sport}_team_full_game_winner", f"Who will win {away['name']} vs {home['name']}?",
                  away["alias"], home["alias"], bid, ask, long_team=away["id"], short_team=home["id"], **kw)


def spread(mid, sport: str, named: dict, other: dict, handicap: float, bid: float, ask: float, **kw) -> dict:
    """The team the question names is the long side, at ``handicap``; the other side is its negative."""
    return market(mid, f"{sport}_team_full_game_spread",
                  f"Will the {named['name']} cover {abs(handicap):g} vs the {other['name']}?",
                  f"{handicap:+.2f}", f"{-handicap:+.2f}", bid, ask, line=abs(handicap), long_team=named["id"],
                  short_team=other["id"], **kw)


def total(mid, sport: str, away: dict, home: dict, line: float, bid: float, ask: float, **kw) -> dict:
    return market(mid, f"{sport}_team_full_game_total",
                  f"Will the total in {away['name']} vs. {home['name']} be more than {line:g}?", "Over", "Under",
                  bid, ask, line=line, **kw)


def prop(mid, kind: str, player: str, n: int, bid: float, ask: float, team: dict | None = None, **kw) -> dict:
    """"Will Name record at least N stat": the long side is Yes, on the player's team."""
    stat = kind.rsplit("_", 1)[-1]
    return market(mid, kind, f"Will {player} record at least {n} {stat} in the game?", "Yes", "No", bid, ask,
                  line=n, long_team=team["id"] if team else None, short_team=team["id"] if team else None, **kw)


def event(eid, slug: str, away: dict, home: dict, markets: list[dict], start: str = "2026-10-24T19:30:00Z") -> dict:
    return {"id": str(eid), "slug": slug, "title": f"{away['name']} vs. {home['name']}", "startTime": start,
            "startDate": start, "active": True, "closed": False, "teams": [away, home], "markets": markets}
