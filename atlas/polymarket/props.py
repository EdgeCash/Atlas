"""Player props on Polymarket US: Atlas's projection beside the market's price, a record, and paper positions.

Polymarket US lists, on each NBA, NHL and NFL game, a ladder of player
props as Yes/No markets on "Will Name record at least N stat": points,
rebounds, assists, threes, steals, blocks and the first three combined in
the NBA; points, goals and assists in the NHL; yards, receptions,
touchdowns, attempts, completions and carries in the NFL. Every run:

1. **reads** them with the game markets (`prop_quotes`), matches each to
   the Atlas game (`atlas/polymarket/match.py`) and the player to Atlas's
   snapshot of him on the team the venue lists him on (`atlas/models/nba_props.py`,
   `atlas/models/nhl_props.py`), and keeps each player-stat's main line in
   ``tracking/polymarket_props.csv`` with Atlas's probability of the over as
   it stood;
2. **grades** the record: once a game is final, each kept prop against the
   box score and the venue's close, into ``tracking/prop_record.csv``, the
   record the share of Atlas's disagreement is fitted on, a sport at a time;
3. **prices** every prop contract: the market's probability, Atlas's, and
   the fair one - the market pulled toward Atlas by that share, zero until
   the record says otherwise - then the fee, expected value and Kelly
   (`atlas/polymarket/pricing.py`);
4. **takes paper positions** by the same rule as the game markets, one per
   player-stat, in their own sealed record (``tracking/polymarket_prop_positions/``),
   graded on the box score (a player who did not play is a push, as the
   venue settles him at the last fair price) and against the close.

"At least N" is the over at N - 1/2: the line kept is the half-line, so a
record row reads as a sportsbook's would. ESPN's injury report is read every
run (`atlas/sources/nba_availability.py`) and applied to the NBA before any
of it: a player listed Out is priced at a 3% chance of taking the court, a
game-time decision at 55% and nine tenths of his minutes, his minutes go to
his teammates, and the chance of not playing goes to the market's own price,
as the venue settles it (`atlas/models/nba_props.AVAILABILITY`). The model's
own record still counts a player who did not play as a push: it measures the
rate model, not the report.

Nothing here buys anything.
"""

from __future__ import annotations

import math
import re
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from atlas.live.store import SCHEMA
from atlas.models import nba_props, nfl_props, nhl_props
from atlas.polymarket import match, page, positions, pricing, source
from atlas.util import get_logger, offline

LOG = get_logger(__name__)

SPORTS = ("nba", "nhl", "nfl")
#: The venue's ``sportsMarketType`` of each prop Atlas projects, by sport.
PROP_TYPES = {
    "nba": {"basketball_player_points": "points", "basketball_player_rebounds": "rebounds",
            "basketball_player_assists": "assists", "basketball_player_threes": "threes",
            "basketball_player_steals": "steals", "basketball_player_blocks": "blocks",
            "basketball_player_points_rebounds_assists": "pra"},
    "nhl": {"hockey_player_points": "points", "hockey_player_goals": "goals", "hockey_player_assists": "assists"},
    "nfl": {"football_player_receiving_yards": "receiving_yards", "football_player_receptions": "receptions",
            "football_player_rushing_yards": "rushing_yards", "football_player_passing_yards": "passing_yards",
            "football_player_touchdowns": "touchdowns", "football_player_passing_touchdowns": "passing_tds",
            "football_player_passing_completions": "completions", "football_player_passing_attempts": "attempts",
            "football_player_rushing_attempts": "carries", "football_player_scrimmage_yards": "scrimmage_yards"},
}
#: "Will Name record at least N points" (the NBA, the NHL) and "Will Name record N+ receiving yards" (the NFL).
QUESTION = re.compile(r"^Will\s+(?P<player>.+?)\s+record\s+(?:at\s+least\s+(?P<n>\d+(?:\.\d+)?)\s|"
                      r"(?P<n2>\d+(?:\.\d+)?)\+\s)", re.IGNORECASE)
PROP_COLUMNS = SCHEMA["polymarket_props"]
RECORD_COLUMNS = SCHEMA["prop_record"]
POSITION_COLUMNS = [*positions.COLUMNS, "player", "stat", "atlas_mean"]
TAB = "Props"
MAX_POSITIONS = 10
TOP_ROWS = 15

#: A player's name as a key: lowercased, accents and punctuation dropped, suffixes dropped.
key = nba_props.name_key


def path() -> Path:
    from atlas.live.store import tracking_dir

    return tracking_dir() / "polymarket_prop_positions"


# ---------------------------------------------------------------------------
# Reading the venue
# ---------------------------------------------------------------------------


def prop_quotes(events: list[dict], league: source.League, captured_at) -> pd.DataFrame:
    """One row per side of every player prop Atlas projects, across the events, as of ``captured_at``: the
    Yes side is the over at the half-line below "at least N", the No side the under."""
    types = PROP_TYPES.get(league.sport, {})
    stamp = pd.Timestamp(captured_at)
    stamp = (stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC"))
    stamp = stamp.replace(microsecond=0).isoformat()
    rows = []
    for event in events:
        away, home = source.teams(event, league)
        away_id, home_id = source.team_ids(event)
        for m in event.get("markets") or []:
            stat = types.get(str(m.get("sportsMarketType") or ""))
            if stat is None:
                continue
            q = QUESTION.match(str(m.get("question") or ""))
            sides = m.get("marketSides") or []
            if q is None or len(sides) != 2:
                continue
            long_, short = (sides[0], sides[1]) if sides[0].get("long", True) else (sides[1], sides[0])
            n = source._num(q.group("n") or q.group("n2"))
            if not math.isfinite(n):
                continue
            line = n - 0.5
            raw = long_.get("teamId")
            tid = int(raw) if raw is not None and str(raw).isdigit() else None
            team_side = "away" if tid is not None and tid == away_id else ("home" if tid is not None and tid == home_id
                                                                          else None)
            bid0, ask0 = source._round(source._num(m.get("bestBidQuote"))), source._round(source._num(m.get("bestAskQuote")))
            bids = [bid0, source._round(1.0 - ask0) if math.isfinite(ask0) else float("nan")]
            asks = [ask0, source._round(1.0 - bid0) if math.isfinite(bid0) else float("nan")]
            mids = [source._round((b + a) / 2.0) if math.isfinite(b) and math.isfinite(a) else float("nan")
                    for b, a in zip(bids, asks, strict=True)]
            spread = source._round(ask0 - bid0) if math.isfinite(ask0) and math.isfinite(bid0) else float("nan")
            start = source.game_start(m, event)
            open_ = source.accepting(m)
            for i, (side, which) in enumerate(((long_, "over"), (short, "under"))):
                rows.append({
                    "captured_at": stamp, "last_seen_at": stamp, "sport": league.sport, "game_id": None,
                    "event_id": str(event.get("id")), "event_slug": event.get("slug"),
                    "game_start": start.isoformat() if pd.notna(start) else None, "away": away, "home": home,
                    "player": q.group("player").strip(), "team_side": team_side, "stat": stat,
                    "market_id": str(m.get("id")), "market_slug": m.get("slug"), "token_id": str(side.get("id")),
                    "side": which, "long": i == 0, "line": line, "bid": bids[i], "ask": asks[i], "mid": mids[i],
                    "last": float("nan"), "spread": spread, "liquidity": float("nan"), "fee_rate": source.fee_rate(m),
                    "accepting": open_, "p_atlas": float("nan"), "atlas_mean": float("nan"), "status": "",
                })
    return pd.DataFrame(rows, columns=PROP_COLUMNS)


def main_lines(q: pd.DataFrame) -> pd.DataFrame:
    """What the record keeps of a player's stat: the line the market prices nearest to even, both sides."""
    if q.empty:
        return q
    mid = pd.to_numeric(q["mid"], errors="coerce")
    first = q["side"] == "over"
    off = (mid - 0.5).abs().where(first)
    keys = [q["event_id"], q["player"], q["stat"]]
    nearest = off.groupby(keys).transform("min")
    chosen = q["market_id"].where(first & (off == nearest))
    main = chosen.groupby(keys).transform("first")
    return q[(q["market_id"] == main).fillna(False)].reset_index(drop=True)


# ---------------------------------------------------------------------------
# Atlas's reading
# ---------------------------------------------------------------------------


def _nba_by_team(snap: dict) -> dict[tuple[int, str], pd.Series]:
    out: dict[tuple[int, str], pd.Series] = {}
    for row in snap["players"].itertuples(index=False):
        try:
            out[(int(row.team_id), key(row.player))] = row
        except (TypeError, ValueError):
            continue
    return out


def _nhl_by_team(snap: dict) -> dict[tuple[str, str], pd.Series]:
    return {(str(row.team), key(row.name)): row for row in snap["skaters"].itertuples(index=False)}


def _nfl_by_team(snap: dict) -> dict[tuple[str, str], pd.Series]:
    return {(str(row.team), key(row.player)): row for row in snap["players"].itertuples(index=False)}


def _nfl_codes(r) -> tuple[str | None, str | None]:
    """(away, home) nflverse codes from the Atlas game's ESPN team ids."""
    from atlas.staging.nfl.games import CODE_BY_ESPN_ID

    home_id, away_id = _team_ids(r)
    return CODE_BY_ESPN_ID.get(away_id), CODE_BY_ESPN_ID.get(home_id)


def _team_ids(r) -> tuple[int | None, int | None]:
    try:
        return int(r.home_team_id), int(r.away_team_id)
    except (TypeError, ValueError):
        return None, None


def _available(p: float, p_play: float, settle: float, side: str) -> float:
    """``p`` when the player plays; the chance he does not goes to the venue's settlement at the last price,
    ``settle`` what the over is paid then (the under its complement)."""
    if p_play >= 1.0 or not math.isfinite(settle):
        return p
    return p_play * p + (1.0 - p_play) * (settle if side == "over" else 1.0 - settle)


def expectations(q: pd.DataFrame, snaps: dict[str, dict | None], availability: pd.DataFrame | None = None,
                 codes: dict[str, tuple[str, str]] | None = None, totals: dict[str, tuple[float, float]] | None = None,
                 nfl_availability: pd.DataFrame | None = None,
                 nhl_availability: pd.DataFrame | None = None) -> pd.DataFrame:
    """Each prop with Atlas's expectation of the stat (when the player plays), his status on the injury
    report, and Atlas's probability of the side with his chance of playing in it. The player is found by
    name on the team the venue lists him on: in the NBA by the team's id in the snapshot, in the NHL by
    the team's code from the game projection (``codes``: game id to (away, home)), in the NFL by the
    team's code from the game's ESPN ids; ``totals`` is each NFL game's (away, home) implied total from
    Atlas's projection. Nan where he is not found."""
    out = q.copy()
    out["atlas_mean"] = np.nan
    out["p_atlas"] = np.nan
    out["status"] = ""
    if out.empty or "home_team_id" not in out:
        return out
    nba = snaps.get("nba")
    nhl = snaps.get("nhl")
    nfl = snaps.get("nfl")
    nba_adj = nba_props.adjust(nba, availability) if nba is not None else None
    nba_players = _nba_by_team(nba_adj) if nba_adj is not None else {}
    nhl_adj = nhl_props.adjust(nhl, nhl_availability) if nhl is not None else None
    nhl_players = _nhl_by_team(nhl_adj) if nhl_adj is not None else {}
    nfl_adj = nfl_props.adjust(nfl, nfl_availability) if nfl is not None else None
    nfl_players = _nfl_by_team(nfl_adj) if nfl_adj is not None else {}
    codes = codes or {}
    totals = totals or {}
    cache: dict[tuple, float] = {}
    means, probs, statuses = [], [], []
    for r in out.itertuples():
        mean_, p, status = float("nan"), float("nan"), ""
        sport, k, which = str(r.sport), key(r.player), str(r.team_side or "")
        mid = source._num(r.mid)
        settle = mid if str(r.side) == "over" else (1.0 - mid if math.isfinite(mid) else float("nan"))
        if sport == "nba" and nba_adj is not None:
            home_id, away_id = _team_ids(r)
            order = [(home_id, away_id, True), (away_id, home_id, False)]
            if which == "away":
                order.reverse()
            for team_id, opp_id, home in order:
                if team_id is None:
                    continue
                row = nba_players.get((team_id, k))
                if row is None:
                    continue
                ck = ("nba", team_id, k, opp_id, str(r.stat))
                if ck not in cache:
                    cache[ck] = nba_props.expect(nba_adj, row._asdict(), team_id, opp_id, home).get(str(r.stat), float("nan"))
                mean_ = cache[ck]
                status = str(row.status or "")
                d = nba_props.dispersion(nba_adj, str(r.stat))
                if math.isfinite(mean_) and math.isfinite(d):
                    p = nba_props.prob_available(mean_, float(r.line), str(r.side), d, float(row.p_play),
                                                 settle if math.isfinite(settle) else None)
                break
        elif sport == "nhl" and nhl is not None:
            away_code, home_code = codes.get(str(r.game_id), (None, None))
            order = [(home_code, away_code), (away_code, home_code)]
            if which == "away":
                order.reverse()
            for team, opp in order:
                if not team or not opp:
                    continue
                row = nhl_players.get((str(team), k))
                if row is None:
                    continue
                ck = ("nhl", team, k, opp, str(r.stat))
                if ck not in cache:
                    cache[ck] = nhl_props.expect(nhl, row._asdict(), str(team), str(opp), str(home_code), str(r.stat))
                mean_ = cache[ck]
                status = str(row.status or "")
                if math.isfinite(mean_):
                    dispersion, ratio = nhl_props.shape(nhl, str(r.stat))
                    p = _available(nhl_props.prob(mean_, float(r.line), str(r.side), dispersion, ratio),
                                   float(row.p_play), settle, str(r.side))
                break
        elif sport == "nfl" and nfl_adj is not None:
            away_code, home_code = _nfl_codes(r)
            away_total, home_total = totals.get(str(r.game_id), (None, None))
            order = [(home_code, away_code, True, home_total), (away_code, home_code, False, away_total)]
            if which == "away":
                order.reverse()
            for team, opp, home, implied in order:
                if not team or not opp:
                    continue
                row = nfl_players.get((str(team), k))
                if row is None:
                    continue
                ck = ("nfl", team, k, opp, str(r.stat))
                if ck not in cache:
                    cache[ck] = nfl_props.expect(nfl_adj, row._asdict(), str(team), str(opp), home, implied) \
                        .get(str(r.stat), float("nan"))
                mean_ = cache[ck]
                status = str(row.status or "")
                d = nfl_props.dispersion(nfl_adj, str(r.stat))
                if math.isfinite(mean_) and math.isfinite(d):
                    p = nba_props.prob_available(mean_, float(r.line), str(r.side), d, float(row.p_play),
                                                 settle if math.isfinite(settle) else None)
                break
        means.append(mean_)
        probs.append(p)
        statuses.append(status)
    out["atlas_mean"], out["p_atlas"], out["status"] = means, probs, statuses
    return out


# ---------------------------------------------------------------------------
# The record, and the share it gives
# ---------------------------------------------------------------------------

RESULT_COLUMNS = ["sport", "game_id", "player_key", "played", "points", "rebounds", "assists", "threes", "steals",
                  "blocks", "pra", "goals", *nfl_props.STATS, *nfl_props.COMBINED]


def results_frame(sport: str, games: pd.DataFrame | None, projections: pd.DataFrame | None = None) -> pd.DataFrame:
    """What each player did in each game, keyed for a prop: (sport, game id, the player's name key). The NBA's
    from the warehouse's player games; the NHL's from its skater games, whose game ids are the league's, mapped
    to Atlas's through the game projections."""
    if games is None or games.empty:
        return pd.DataFrame(columns=RESULT_COLUMNS)
    if sport == "nba":
        from atlas.staging.nba import players as players_stage

        r = players_stage.results(games)
        r["player_key"] = r["player"].map(key)
        r = r.drop_duplicates(["game_id", "player_key"], keep="last").assign(sport="nba", goals=np.nan)
        return r.reindex(columns=RESULT_COLUMNS)
    if sport == "nfl":
        from atlas.staging.nfl import players as nfl_stage

        r = nfl_stage.results(games)
        r["player_key"] = r["player"].map(key)
        r = r.drop_duplicates(["game_id", "player_key"], keep="last").assign(sport="nfl")
        return r.reindex(columns=RESULT_COLUMNS)
    if projections is None or projections.empty or "nhl_game_id" not in projections:
        return pd.DataFrame(columns=RESULT_COLUMNS)
    ids = {str(int(n)): str(g) for n, g in zip(pd.to_numeric(projections["nhl_game_id"], errors="coerce"),
                                                projections["game_id"], strict=True) if pd.notna(n)}
    s = games.assign(game_id=games["game_id"].astype(str).map(ids))
    s = s[s["game_id"].notna()]
    out = pd.DataFrame({"sport": "nhl", "game_id": s["game_id"].astype(str), "player_key": s["name"].map(key),
                        "played": True, "points": pd.to_numeric(s["points"], errors="coerce"),
                        "rebounds": np.nan, "assists": pd.to_numeric(s["assists"], errors="coerce"),
                        "threes": np.nan, "goals": pd.to_numeric(s["goals"], errors="coerce")})
    return out.drop_duplicates(["game_id", "player_key"], keep="last").reindex(columns=RESULT_COLUMNS)


def _value(results: pd.DataFrame, sport: str, game_id, player, stat) -> tuple[float, bool | None]:
    """(the stat the player recorded, whether he played); (nan, None) when the game is not in the results."""
    if results is None or results.empty:
        return float("nan"), None
    game = results[(results["sport"].astype(str) == str(sport)) & (results["game_id"].astype(str) == str(game_id))]
    if game.empty:
        return float("nan"), None
    r = game[game["player_key"] == key(player)]
    if r.empty:
        # The game is in the results (someone played) but he is not: he did not dress.
        return float("nan"), False
    row = r.iloc[0]
    return (float(row[stat]), bool(row["played"]))


def grade_record(kept: pd.DataFrame, graded: pd.DataFrame, results: pd.DataFrame, now: datetime) -> pd.DataFrame:
    """New rows for ``prop_record``: each kept over-side prop whose game has started and has a box score,
    not yet graded, with Atlas's probability of the over as kept, the close's, what the player recorded,
    and whether Atlas's side happened (a tie on a whole line, or a player who did not play, is one half)."""
    if kept.empty:
        return pd.DataFrame(columns=RECORD_COLUMNS)
    over = source.latest(kept[kept["side"] == "over"])
    over = over[over["game_id"].notna() & pd.to_numeric(over["p_atlas"], errors="coerce").notna()]
    done = set(graded["token_id"].astype(str)) if len(graded) else set()
    start = pd.to_datetime(over["game_start"], utc=True, errors="coerce")
    over = over[(start <= pd.Timestamp(now)) & ~over["token_id"].astype(str).isin(done)]
    rows = []
    for r in over.itertuples():
        value, played = _value(results, r.sport, r.game_id, r.player, r.stat)
        if played is None:
            continue
        line, p_atlas = float(r.line), float(r.p_atlas)
        p_close = source.close(kept, r.token_id, r.game_start)
        if not played or not math.isfinite(value) or value == line:
            won = 0.5
        else:
            atlas_over = p_atlas >= 0.5
            won = float((value > line) == atlas_over)
        rows.append({"token_id": str(r.token_id), "game_id": str(r.game_id), "kickoff": r.game_start,
                     "sport": str(r.sport), "player": r.player, "stat": r.stat, "line": line,
                     "p_atlas": round(p_atlas, 4), "p_close": round(p_close, 4) if math.isfinite(p_close) else np.nan,
                     "value": value if math.isfinite(value) else np.nan, "played": bool(played), "won": won,
                     "graded_at": pd.Timestamp(now).strftime("%Y-%m-%dT%H:%M:%SZ")})
    return pd.DataFrame(rows, columns=RECORD_COLUMNS)


def calibration_rows(record: pd.DataFrame) -> pd.DataFrame:
    """The prop record in the calibration table's columns, the moneyline way: ``claimed`` is Atlas's
    probability for its side, ``abs_edge`` the gap in points of probability between it and the close's
    probability for that side (negative when the close was the more confident), ``won`` what happened."""
    cols = ["game_id", "sport", "season", "week", "season_type", "market", "abs_edge", "claimed", "won", "kickoff"]
    if record is None or record.empty:
        return pd.DataFrame(columns=cols)
    r = record.dropna(subset=["p_atlas", "p_close"])
    r = r[r["won"] != 0.5]
    p = pd.to_numeric(r["p_atlas"], errors="coerce")
    c = pd.to_numeric(r["p_close"], errors="coerce")
    over = p >= 0.5
    claimed = np.where(over, p, 1 - p)
    market = np.where(over, c, 1 - c)
    kick = pd.to_datetime(r["kickoff"], utc=True, errors="coerce")
    return pd.DataFrame({"game_id": r["game_id"].to_numpy(), "sport": r["sport"].astype(str).to_numpy(),
                         "season": kick.dt.year.where(kick.dt.month >= 10, kick.dt.year - 1).to_numpy(),
                         "week": 0, "season_type": "regular", "market": "player",
                         "abs_edge": 100.0 * (claimed - market), "claimed": claimed,
                         "won": pd.to_numeric(r["won"], errors="coerce").to_numpy(), "kickoff": r["kickoff"].to_numpy()},
                        columns=cols)


# ---------------------------------------------------------------------------
# Pricing
# ---------------------------------------------------------------------------


def price(q: pd.DataFrame, calibration: pd.DataFrame | None) -> pd.DataFrame:
    """Every matched prop contract with Atlas's reading: the market's probability, Atlas's, the fair one by
    the sport's record's share, the fee, the cost, expected value and Kelly, in the columns the positions
    read."""
    cols = ["p_market", "p_raw", "p_ladder", "share", "p", "fee", "cost", "ev", "kelly", "market", "prop_key", "label",
            "kickoff"]
    if q.empty or "game_id" not in q:
        return q.assign(**{c: pd.Series(dtype=float) for c in cols})
    t = q[q["game_id"].notna()].copy()
    if t.empty:
        return t.assign(**{c: pd.Series(dtype=float) for c in cols})
    shares = {s: pricing.share(calibration, s, "player")[0] for s in set(t["sport"].astype(str))}
    t["p_market"] = pricing.market_probs(t)
    t["p_raw"] = pd.to_numeric(t["p_atlas"], errors="coerce")
    t["p_ladder"] = np.nan
    t["share"] = t["sport"].astype(str).map(shares).astype(float)
    t["p"] = np.where(t["p_raw"].notna() & t["p_market"].notna(),
                      t["p_market"] + t["share"] * (t["p_raw"] - t["p_market"]), t["p_market"])
    ask = pd.to_numeric(t["ask"], errors="coerce")
    rate = pd.to_numeric(t["fee_rate"], errors="coerce").fillna(0.0)
    t["fee"] = [pricing.fee(a, f) for a, f in zip(ask, rate, strict=True)]
    t["cost"] = ask + t["fee"]
    ok = (ask > 0) & (ask < 1) & (t["cost"] < 1) & t["p"].notna()
    t["ev"] = np.where(ok, t["p"] / t["cost"] - 1.0, np.nan)
    t["kelly"] = np.where(ok, ((t["p"] - t["cost"]) / (1.0 - t["cost"])).clip(lower=0.0), np.nan)
    t["market"] = "player:" + t["stat"].astype(str)
    t["prop_key"] = t["game_id"].astype(str) + "|" + t["player"].map(key) + "|" + t["stat"].astype(str)
    if "label" not in t or t["label"].isna().all():
        t["label"] = t["away"].astype(str) + " @ " + t["home"].astype(str)
    if "kickoff" not in t or t["kickoff"].isna().all():
        t["kickoff"] = t["game_start"]
    return t.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Positions on props
# ---------------------------------------------------------------------------


def grade_positions(record: pd.DataFrame, results: pd.DataFrame, quotes: pd.DataFrame, now: datetime) -> pd.DataFrame:
    """Each position with its outcome from the box score (a player who did not play is a push, as the venue
    settles him at the last fair price; so is a tie on a whole line), its return, and the venue's close for
    the contract. The exchange's own settlement, where it has one, overrides the box score."""
    if record.empty:
        return record.assign(outcome=pd.Series(dtype=str), profit=pd.Series(dtype=float), pnl=pd.Series(dtype=float),
                             close=pd.Series(dtype=float), clv=pd.Series(dtype=float))
    r = record.copy()
    kick = pd.to_datetime(r["kickoff"], utc=True, errors="coerce")
    outcomes = []
    for x in r.itertuples():
        value, played = _value(results, x.sport, x.game_id, x.player, x.stat)
        if played is None:
            outcomes.append("open")
        elif not played or not math.isfinite(value) or value == float(x.line):
            outcomes.append("push")
        else:
            over = value > float(x.line)
            outcomes.append("win" if over == (str(x.side) == "over") else "loss")
    r["outcome"] = outcomes
    cost = pd.to_numeric(r["cost"], errors="coerce")
    r["profit"] = np.select([r["outcome"] == "win", r["outcome"] == "loss"], [(1.0 - cost) / cost, -1.0], 0.0)
    r.loc[r["outcome"] == "open", "profit"] = np.nan
    r["pnl"] = pd.to_numeric(r["stake"], errors="coerce") * r["profit"]
    r = positions.apply_settlement(r, positions.settled(r, now))
    started = kick <= pd.Timestamp(now)
    r["close"] = [positions.closing(quotes, tok, k) if s else float("nan")
                  for tok, k, s in zip(r["token_id"], kick, started, strict=True)]
    r["clv"] = r["close"] - pd.to_numeric(r["ask"], errors="coerce")
    return r


# ---------------------------------------------------------------------------
# The owner page
# ---------------------------------------------------------------------------


def _contract(x) -> str:
    return f"{str(x.player)} {str(x.side)} {float(x.line):g} {str(x.stat)}"


def _atlas(x) -> str:
    m = pd.to_numeric(getattr(x, "atlas_mean", np.nan), errors="coerce")
    status = str(getattr(x, "status", "") or "")
    text = f"Atlas {float(m):.1f}" if pd.notna(m) else "Atlas –"
    return f"{text} · {status}" if status and status != "nan" else text


def sections(priced: pd.DataFrame, chosen: pd.DataFrame, graded: pd.DataFrame, now: datetime,
             note: str | None = None) -> list[dict]:
    logged = set(graded["position_id"]) if len(graded) else set()
    day = pd.Timestamp(chosen["day"].iloc[0]).strftime("%a %b %-d") if len(chosen) else \
        pd.Timestamp(positions.day_of(now)).strftime("%a %b %-d")
    rows = [[[x.label, page._eastern(x.kickoff)], [_contract(x), f"{_atlas(x)} · {str(x.sport).upper()}"],
             page._price(x), page._edge(x), [f"{float(x.stake):.1%}", "logged" if x.position_id in logged else ""]]
            for x in chosen.itertuples()]
    out = [{"title": f"Prop positions for {day} ({len(rows)})", "tab": TAB,
            "tables": [{"title": "", "head": [*page.HEAD, "Stake"], "stack": True,
                        "rows": rows or [[f"Nothing clears {positions.MIN_EV:+.0%} after the fee.", "", "", "", ""]]}],
            "notes": [
                "Paper only. The same rule as the game markets, one position per player's stat, at most "
                f"{MAX_POSITIONS} a day; a player who does not play is a push, as the venue settles him at the "
                "last fair price.",
                "Fair is the market's probability pulled toward Atlas's projection by the share of Atlas's "
                "disagreement the sport's prop record has shown to be real: zero until the record says otherwise, "
                "so at first nothing here clears the fee. In the NBA Atlas is minutes times a rate times the game "
                "(atlas/models/nba_props.py), with ESPN's injury report applied: a player listed out is priced at a "
                "3% chance of taking the court, a game-time decision at 55%. In the NHL it is ice time times a rate "
                "times the game (atlas/models/nhl_props.py).",
                *([note] if note else [])]}]
    tables = []
    upcoming = priced[pd.to_datetime(priced["kickoff"], utc=True, errors="coerce") > pd.Timestamp(now)] \
        if len(priced) else priced
    if len(upcoming):
        with_atlas = upcoming[pd.to_numeric(upcoming["p_raw"], errors="coerce").notna()]
        ok = positions.eligible(with_atlas, now) if len(with_atlas) else pd.Series(dtype=bool)
        best = with_atlas.assign(takeable=ok).sort_values(["takeable", "ev"], ascending=[False, False]) \
            .drop_duplicates(["prop_key"], keep="first").sort_values("ev", ascending=False)
        rows = [[[x.label, page._eastern(x.kickoff)],
                 [_contract(x), f"{_atlas(x)} · {str(x.sport).upper()}" + ("" if x.takeable else " · not takeable")],
                 page._price(x), page._edge(x)] for x in best.itertuples()]
        tables.append({"title": f"Best {min(TOP_ROWS, len(rows))} of {len(rows)} by expected value after the fee",
                       "head": page.HEAD, "stack": True, "rows": rows[:TOP_ROWS]})
        if len(rows) > TOP_ROWS:
            tables.append({"title": f"The other {len(rows) - TOP_ROWS}", "fold": True, "stack": True,
                           "head": page.HEAD, "rows": rows[TOP_ROWS:]})
    counts = []
    if len(priced):
        for (sport, stat), part in priced.groupby([priced["sport"].astype(str), priced["stat"].astype(str)]):
            counts.append([sport.upper(), stat, str(part["game_id"].nunique()), str(part["player"].nunique()),
                           str(len(part) // 2), str(int(pd.to_numeric(part["p_raw"], errors="coerce").notna().sum() // 2))])
    tables.append({"title": "Contracts this run, by stat", "fold": True,
                   "head": ["Sport", "Stat", "Games", "Players", "Contracts", "With Atlas"], "rows": counts})
    out.append({"title": "Props board", "tab": TAB, "tables": tables, "notes": [
        "Each player's stat at the contract that pays best, whether or not it clears the bar. Atlas is the "
        "expectation of the stat when he plays, beside his status on the injury report where he is listed; "
        "the probability priced is Atlas's with his chance of playing in it.",
        "Quotes are read from Polymarket US's public API every run; each player-stat's main line is kept in "
        "tracking/polymarket_props.csv."]})
    return out


def record_section(record: pd.DataFrame) -> dict | None:
    """What the graded prop record says so far: how often Atlas's side happened, by its confidence, a sport at
    a time."""
    if record is None or record.empty:
        return None
    r = record[record["won"] != 0.5].copy()
    if r.empty:
        return None
    p = pd.to_numeric(r["p_atlas"], errors="coerce")
    r["claimed"] = np.where(p >= 0.5, p, 1 - p)
    rows = []
    for sport, part_s in r.groupby(r["sport"].astype(str)):
        for lo, hi in ((0.5, 0.55), (0.55, 0.6), (0.6, 0.7), (0.7, 1.01)):
            part = part_s[(part_s["claimed"] >= lo) & (part_s["claimed"] < hi)]
            if len(part):
                rows.append([sport.upper(), f"{lo:.0%}–{min(hi, 1.0):.0%}", str(len(part)),
                             f"{part['claimed'].mean():.1%}", f"{pd.to_numeric(part['won']).mean():.1%}"])
    shares = []
    for sport in sorted(set(r["sport"].astype(str))):
        k, n = pricing.share(calibration_rows(record), sport, "player")
        shares.append(f"{sport.upper()} {k:.0%} on {n} graded")
    return {"title": f"Prop record: {len(r)} graded", "tab": TAB,
            "tables": [{"title": "", "head": ["Sport", "Atlas claimed", "props", "claimed", "happened"], "rows": rows}],
            "notes": [f"Every kept prop graded against the box score: what Atlas claimed for its side against how "
                      f"often it happened. The share of Atlas's disagreement with the close the pricing takes: "
                      f"{'; '.join(shares)}."]}


# ---------------------------------------------------------------------------
# One run
# ---------------------------------------------------------------------------


def _codes(projections: pd.DataFrame | None) -> dict[str, tuple[str, str]]:
    """Each NHL game's (away, home) team codes, from the latest projection of it."""
    if projections is None or projections.empty:
        return {}
    p = projections.sort_values("refreshed_at", kind="stable") if "refreshed_at" in projections else projections
    p = p.drop_duplicates("game_id", keep="last")
    return {str(g): (str(a), str(h)) for g, a, h in zip(p["game_id"], p["away_team"], p["home_team"], strict=True)}


def _totals(projections: pd.DataFrame | None) -> dict[str, tuple[float, float]]:
    """Each NFL game's (away, home) implied total from the latest Atlas projection of it: the total and the
    margin (home less away) split."""
    if projections is None or projections.empty or "sport" not in projections:
        return {}
    p = projections[projections["sport"].astype(str) == "nfl"]
    if p.empty:
        return {}
    p = p.sort_values("refreshed_at", kind="stable").drop_duplicates("game_id", keep="last") if "refreshed_at" in p else p
    out = {}
    for g, m, t in zip(p["game_id"], pd.to_numeric(p["margin_mean"], errors="coerce"),
                       pd.to_numeric(p["total_mean"], errors="coerce"), strict=True):
        if pd.notna(m) and pd.notna(t):
            out[str(g)] = ((float(t) - float(m)) / 2.0, (float(t) + float(m)) / 2.0)
    return out


def _load_snaps(snaps: dict | None) -> dict[str, dict | None]:
    out = dict(snaps or {})
    if "nba" not in out:
        out["nba"] = nba_props.load_state()
    if "nhl" not in out:
        out["nhl"] = nhl_props.load_state()
    if "nfl" not in out:
        out["nfl"] = nfl_props.load_state()
    return out


def _load_results(store, results: pd.DataFrame | None) -> pd.DataFrame:
    if results is not None:
        return results
    parts = []
    try:
        player_games, _ = nba_props.load_tables()
        parts.append(results_frame("nba", player_games))
    except Exception as error:  # noqa: BLE001 - a poll without the warehouse grades nothing this run
        LOG.info("props: no NBA player games to grade with (%s)", type(error).__name__)
    try:
        skaters = nhl_props.load_tables()["skater_games"]
        parts.append(results_frame("nhl", skaters, store.read("nhl_projections")))
    except Exception as error:  # noqa: BLE001
        LOG.info("props: no NHL skater games to grade with (%s)", type(error).__name__)
    try:
        weeks, _ = nfl_props.load_tables()
        parts.append(results_frame("nfl", weeks))
    except Exception as error:  # noqa: BLE001
        LOG.info("props: no NFL player weeks to grade with (%s)", type(error).__name__)
    parts = [p for p in parts if len(p)]
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=RESULT_COLUMNS)


def refresh(store, events: dict[str, list[dict]], pairs: pd.DataFrame, now: datetime, passphrase: str | None,
            *, snaps: dict | None = None, results: pd.DataFrame | None = None,
            availability: pd.DataFrame | None = None, nfl_availability: pd.DataFrame | None = None,
            nhl_availability: pd.DataFrame | None = None) -> tuple[list[dict], dict]:
    """The props step of the Polymarket run: the injury report, then read, keep, grade, price, position, for
    every sport with a snapshot. Returns (the owner page's sections, a coverage summary for the public
    report). Never raises."""
    from atlas.sources import nba_availability

    summary: dict = {"contracts": 0, "projected": 0, "games": 0, "graded": 0, "listed": 0, "sports": {}}
    try:
        snaps = _load_snaps(snaps)
        if all(v is None for v in snaps.values()):
            LOG.info("props: no player snapshot yet; nothing priced")
            return [{"title": "Props", "tab": TAB, "tables": [],
                     "notes": ["No player snapshot yet: the next heavy refresh writes one."]}], summary
        if availability is None and not offline() and snaps.get("nba") is not None:
            availability = nba_availability.capture(store, now)
        if nfl_availability is None and not offline() and snaps.get("nfl") is not None:
            nfl_availability = nba_availability.capture(store, now, sport="nfl")
        if nhl_availability is None and not offline() and snaps.get("nhl") is not None:
            nhl_availability = nba_availability.capture(store, now, sport="nhl")
        codes = _codes(store.read("nhl_projections"))
        totals = _totals(store.read("projections"))
        parts = []
        for sport in SPORTS:
            if snaps.get(sport) is None:
                continue
            q = prop_quotes(events.get(sport, []), source.LEAGUES[sport], now)
            if q.empty:
                continue
            if len(pairs):
                q = match.attach(q, pairs[pairs["sport"].astype(str) == sport])
            else:
                q = q.assign(kickoff=None, label=None, home_team_id=None, away_team_id=None)
            parts.append(q)
        q = pd.concat(parts, ignore_index=True) if parts else prop_quotes([], source.LEAGUES["nba"], now)
        q = expectations(q, snaps, availability, codes, totals, nfl_availability, nhl_availability)
        matched = q[q["game_id"].notna()] if len(q) else q
        kept = main_lines(matched) if len(matched) else matched
        record = store.read("polymarket_props")
        if len(kept):
            record, added = source.fold(record, kept.reindex(columns=PROP_COLUMNS), cols=PROP_COLUMNS)
            store.write("polymarket_props", record)
            LOG.info("props: %d prop contracts read, %d on matched games, %d kept, %d new rows", len(q), len(matched),
                     len(kept), added)
        results = _load_results(store, results)
        graded_record = store.read("prop_record")
        new = grade_record(record, graded_record, results, now)
        if len(new):
            store.append_new_only("prop_record", new)
            graded_record = store.read("prop_record")
            LOG.info("props: %d props graded into the record (%d in all)", len(new), len(graded_record))
        calibration = calibration_rows(graded_record)
        priced = price(matched, calibration) if len(matched) else price(q, calibration)
        for sport in SPORTS:
            m = matched[matched["sport"].astype(str) == sport] if len(matched) else matched
            pr = priced[priced["sport"].astype(str) == sport] if len(priced) else priced
            summary["sports"][sport] = {
                "contracts": int(len(m) // 2), "games": int(m["game_id"].nunique()) if len(m) else 0,
                "projected": int(pd.to_numeric(pr["p_raw"], errors="coerce").notna().sum() // 2) if len(pr) else 0,
                "graded": int((graded_record["sport"].astype(str) == sport).sum()) if len(graded_record) else 0,
                "listed": int(m[m["status"].astype(str).str.len() > 0]["player"].nunique()) if len(m) else 0}
        for k in ("contracts", "projected", "games", "graded", "listed"):
            summary[k] = sum(v[k] for v in summary["sports"].values())
        if not passphrase:
            return [], summary
        chosen, graded = positions.run(priced, results, record, passphrase, now, where=path(), unit="prop_key",
                                       columns=POSITION_COLUMNS, grader=grade_positions)
        out = sections(priced, chosen, graded, now)
        rec = record_section(graded_record)
        return ([*out, rec] if rec else out), summary
    except Exception as error:  # noqa: BLE001 - the type only
        from atlas.util import where

        LOG.error("props not refreshed: %s at %s", type(error).__name__, where(error))
        return [{"title": "Props", "tab": TAB, "tables": [],
                 "notes": [f"This run could not price the props ({type(error).__name__})."]}], summary
