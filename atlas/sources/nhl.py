"""The NHL's own API, the odds archive and ESPN's event ids, cached one file per season, no key.

    python -m atlas.sources.nhl                    # the season in progress, then history up to the budget
    python -m atlas.sources.nhl --budget 0         # no budget: everything missing (a cold cache, ~20 minutes)
    python -m atlas.sources.nhl --seasons 2024 2025

Step 0 of `docs/MODEL_PLAN_NHL.md`. Seasons are numbered by the year they
start (2025 is 2025-26), as Atlas numbers football's. Everything lands under
``data/raw/nhl/``:

* ``teams``         - the NHL's team catalogue: id, code, name
* ``games``         - one row per regular-season and playoff game: date, puck
                      drop, teams, final score and ``period`` (3 regulation,
                      4 overtime, 5 shootout); one call a season
* ``team_games``    - goals and shots for and against, power play and penalty
                      kill per team-game; one call a season
* ``goalie_games``  - starts, shots against, saves and ice time per goalie-game
* ``skater_games``  - goals, assists, shots, hits, blocks, missed shots,
                      empty-net goals and ice time by strength per skater-game,
                      a month at a time (the API caps a query at 10,000 rows)
* ``shots``         - every shot attempt and penalty from the play-by-play,
                      trimmed: coordinates, shot type, shooter (and blocker), goalie in net,
                      the strength state, the score and the event before it
                      (for rebounds and rushes); one call a completed game,
                      kept for ever
* ``strength``      - seconds each game spent in each strength state, from the
                      same play-by-play: the denominators of every rate
* ``players``       - each season's roster spots: id, name, position, team
* ``odds``          - SportsBookReviewsOnline's archive, 2010-11 to 2022-23:
                      opening and closing moneylines, the puck line and its
                      price, opening and closing totals. A personal-use
                      archive: cached, used for the benchmark, never republished
* ``espn``          - ESPN's event id for every game, matched by date and teams,
                      the id the live tracker keys a game by

A completed season is fetched once; the season in progress is re-fetched on
every run (the play-by-play only for games not yet cached). History is
filled newest season first, up to a budget of play-by-play calls a run, so
a cold cache fills over a few heavy runs without holding one up. Nothing
here is point-in-time: what a projection may see is decided in staging.
The run never fails the heavy refresh: a source that errors is logged and
left for the next run.
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import re
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from atlas import config
from atlas.util import get_logger, http_get, session, write_parquet

LOG = get_logger(__name__)

STATS = "https://api.nhle.com/stats/rest/en"
WEB = "https://api-web.nhle.com/v1"
ESPN = "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/scoreboard"
SBRO = "https://www.sportsbookreviewsonline.com/scoresoddsarchives/nhl-odds-{slug}"
#: The archive needs a browser's user agent.
BROWSER = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"

#: The first season with coordinates in the play-by-play, and the first the plan measures.
FIRST_SEASON = 2010
#: The archive's seasons: complete from 2010-11 to 2021-22; 2022-23 stops on 27 November.
ODDS_SEASONS = range(2010, 2023)
#: Regular season and playoffs.
GAME_TYPES = (2, 3)
#: Play-by-play calls a run may make for history, beyond the season in progress.
PBP_BUDGET = 4000
WORKERS = 8

#: A franchise under its current code, through relocations: Atlanta became Winnipeg (2011), Phoenix
#: Arizona (2014), and Arizona's hockey operation Utah (2024), the Utah Hockey Club the Mammoth (2025).
FRANCHISE = {"ATL": "WPG", "PHX": "UTA", "ARI": "UTA"}
#: ESPN's abbreviations where they differ from the NHL's.
ESPN_CODES = {"NJ": "NJD", "SJ": "SJS", "TB": "TBL", "LA": "LAK", "UTAH": "UTA", "PHO": "PHX"}
#: The archive's team names, spaces and all, to the NHL's code in that season (Phoenix and Arizona
#: are one franchise; the code is the season's).
ODDS_NAMES = {
    "anaheim": "ANA", "arizona": "ARI", "arizonas": "ARI", "atlanta": "ATL", "boston": "BOS", "buffalo": "BUF",
    "calgary": "CGY", "carolina": "CAR", "chicago": "CHI", "colorado": "COL", "columbus": "CBJ", "dallas": "DAL",
    "detroit": "DET", "edmonton": "EDM", "florida": "FLA", "losangeles": "LAK", "minnesota": "MIN",
    "montreal": "MTL", "nyislanders": "NYI", "nyrangers": "NYR", "nashville": "NSH", "newjersey": "NJD",
    "ottawa": "OTT", "philadelphia": "PHI", "phoenix": "PHX", "pittsburgh": "PIT", "sanjose": "SJS",
    "seattle": "SEA", "seattlekraken": "SEA", "stlouis": "STL", "tampa": "TBL", "tampabay": "TBL",
    "toronto": "TOR", "vancouver": "VAN", "vegas": "VGK", "washington": "WSH", "winnipeg": "WPG",
    "winnipegjets": "WPG",
}

#: The play-by-play events kept: every shot attempt, and the penalties that set the strength.
SHOT_EVENTS = ("goal", "shot-on-goal", "missed-shot", "blocked-shot")
KEPT_EVENTS = (*SHOT_EVENTS, "penalty")
SHOT_COLUMNS = ["game_id", "season", "event_id", "sort_order", "period", "period_type", "seconds", "situation",
                "event", "team_id", "x", "y", "zone", "shot_type", "shooter_id", "blocker_id", "goalie_id", "home_defends",
                "home_score", "away_score", "prev_event", "prev_team_id", "prev_x", "prev_y", "prev_seconds",
                "penalty_type", "penalty_minutes", "drawn_by_id"]
STRENGTH_COLUMNS = ["game_id", "season", "situation", "seconds"]
PLAYER_COLUMNS = ["season", "player_id", "name", "position", "team_id"]


def nhl_dir(raw: Path) -> Path:
    return raw / "nhl"


def path(raw: Path, kind: str, season: int | None = None) -> Path:
    name = kind if season is None else f"{kind}_{season}"
    return nhl_dir(raw) / kind / f"{name}.parquet"


def season_id(season: int) -> str:
    """The NHL's id for a season: 2025 is ``20252026``."""
    return f"{season}{season + 1}"


def current_season(today: date | None = None) -> int:
    """The season in progress or next: from September a new one."""
    today = today or datetime.now(UTC).date()
    return today.year if today.month >= 9 else today.year - 1


def franchise(code: str | None) -> str | None:
    """A team's code as its franchise is known now."""
    if code is None or (isinstance(code, float) and np.isnan(code)):
        return None
    return FRANCHISE.get(str(code), str(code))


# ---------------------------------------------------------------------------
# The stats API: games and game logs
# ---------------------------------------------------------------------------


#: The stats API returns everything for ``limit=-1`` up to this many rows, and pages of at most 100
#: otherwise; an unsorted page can repeat or skip rows, so the fallback pages in a fixed order.
REST_CAP = 10000
PAGE = 100


def _rest(endpoint: str, cayenne: str, sess, **params) -> list[dict]:
    """Every row of a stats endpoint for the filter: all at once, or in sorted pages past the cap."""
    body = http_get(f"{STATS}/{endpoint}", sess=sess, timeout=60,
                    params={"cayenneExp": cayenne, "limit": -1, **params}).json()
    rows = body.get("data") or []
    total = int(body.get("total") or len(rows))
    if len(rows) >= total:
        return rows
    LOG.info("nhl: %s returned %d of %d rows at once; paging", endpoint, len(rows), total)
    order = '[{"property":"gameId","direction":"ASC"},{"property":"%s","direction":"ASC"}]' % (
        "teamId" if endpoint.startswith("team") else "id" if endpoint == "game" else "playerId")
    rows = []
    while len(rows) < total:
        page = http_get(f"{STATS}/{endpoint}", sess=sess, timeout=60,
                        params={"cayenneExp": cayenne, "limit": PAGE, "start": len(rows), "sort": order,
                                **params}).json().get("data") or []
        if not page:
            break
        rows.extend(page)
    return rows


def fetch_teams(raw: Path, *, refresh: bool = False) -> Path:
    dest = path(raw, "teams")
    if dest.exists() and not refresh:
        return dest
    body = http_get(f"{STATS}/team", sess=session(), timeout=60).json()
    teams = pd.DataFrame([{"team_id": int(t["id"]), "code": t.get("triCode"), "name": t.get("fullName")}
                          for t in body.get("data") or []])
    return write_parquet(teams, dest)


def fetch_games(raw: Path, season: int, *, refresh: bool = False) -> Path:
    dest = path(raw, "games", season)
    if dest.exists() and not refresh:
        return dest
    rows = _rest("game", f"season={season_id(season)} and gameType>=2 and gameType<=3", session())
    games = pd.DataFrame([{
        "game_id": int(g["id"]), "season": season, "game_type": int(g["gameType"]), "date": g.get("gameDate"),
        "start_et": g.get("easternStartTime"), "home_id": g.get("homeTeamId"), "away_id": g.get("visitingTeamId"),
        "home_score": g.get("homeScore"), "away_score": g.get("visitingScore"), "period": g.get("period"),
        "state": g.get("gameStateId"),
    } for g in rows])
    return write_parquet(games.sort_values("game_id").reset_index(drop=True), dest)


def _game_log(kind: str, season: int, sess, month: tuple[str, str] | None = None) -> list[dict]:
    cayenne = f"seasonId={season_id(season)} and gameTypeId>=2 and gameTypeId<=3"
    if month:
        cayenne += f' and gameDate>="{month[0]}" and gameDate<"{month[1]}"'
    return _rest(kind, cayenne, sess, isAggregate="false", isGame="true")


TEAM_FIELDS = {"gameId": "game_id", "teamId": "team_id", "homeRoad": "home_road", "gameDate": "date",
               "goalsFor": "goals_for", "goalsAgainst": "goals_against", "shotsForPerGame": "shots_for",
               "shotsAgainstPerGame": "shots_against", "powerPlayPct": "pp_pct", "penaltyKillPct": "pk_pct",
               "faceoffWinPct": "faceoff_pct", "wins": "win", "otLosses": "ot_loss",
               "winsInShootout": "so_win", "winsInRegulation": "reg_win"}
GOALIE_FIELDS = {"gameId": "game_id", "playerId": "player_id", "goalieFullName": "name", "teamAbbrev": "team",
                 "opponentTeamAbbrev": "opponent", "homeRoad": "home_road", "gameDate": "date",
                 "gamesStarted": "started", "shotsAgainst": "shots_against", "saves": "saves",
                 "goalsAgainst": "goals_against", "timeOnIce": "toi", "wins": "win", "losses": "loss",
                 "otLosses": "ot_loss", "shutouts": "shutout"}
SKATER_FIELDS = {
    "summary": {"gameId": "game_id", "playerId": "player_id", "skaterFullName": "name", "positionCode": "position",
                "teamAbbrev": "team", "opponentTeamAbbrev": "opponent", "homeRoad": "home_road", "gameDate": "date",
                "goals": "goals", "assists": "assists", "points": "points", "shots": "shots",
                "ppPoints": "pp_points", "ppGoals": "pp_goals", "shPoints": "sh_points", "plusMinus": "plus_minus",
                "penaltyMinutes": "pim", "timeOnIcePerGame": "toi"},
    "realtime": {"gameId": "game_id", "playerId": "player_id", "hits": "hits", "blockedShots": "blocks",
                 "missedShots": "missed_shots", "giveaways": "giveaways", "takeaways": "takeaways",
                 "emptyNetGoals": "en_goals", "shotAttemptsBlocked": "shots_blocked_against"},
    "timeonice": {"gameId": "game_id", "playerId": "player_id", "evTimeOnIce": "toi_ev", "ppTimeOnIce": "toi_pp",
                  "shTimeOnIce": "toi_sh", "shifts": "shifts"},
}


def _pick(rows: list[dict], fields: dict[str, str]) -> pd.DataFrame:
    return pd.DataFrame([{new: r.get(old) for old, new in fields.items()} for r in rows],
                        columns=list(fields.values()))


def fetch_team_games(raw: Path, season: int, *, refresh: bool = False) -> Path:
    dest = path(raw, "team_games", season)
    if dest.exists() and not refresh:
        return dest
    frame = _pick(_game_log("team/summary", season, session()), TEAM_FIELDS)
    return write_parquet(frame.sort_values(["game_id", "team_id"]).reset_index(drop=True), dest)


def fetch_goalie_games(raw: Path, season: int, *, refresh: bool = False) -> Path:
    dest = path(raw, "goalie_games", season)
    if dest.exists() and not refresh:
        return dest
    frame = _pick(_game_log("goalie/summary", season, session()), GOALIE_FIELDS)
    return write_parquet(frame.sort_values(["game_id", "player_id"]).reset_index(drop=True), dest)


def months(season: int) -> list[tuple[str, str]]:
    """Month windows from September to the following July: each under the API's row cap."""
    out = []
    first = date(season, 9, 1)
    for i in range(11):
        y, m = first.year + (first.month - 1 + i) // 12, (first.month - 1 + i) % 12 + 1
        ny, nm = y + (m // 12), m % 12 + 1
        out.append((f"{y}-{m:02d}-01", f"{ny}-{nm:02d}-01"))
    return out


def fetch_skater_games(raw: Path, season: int, *, refresh: bool = False) -> Path:
    dest = path(raw, "skater_games", season)
    if dest.exists() and not refresh:
        return dest
    sess = session()
    jobs = [(kind, window) for kind in SKATER_FIELDS for window in months(season)]
    with cf.ThreadPoolExecutor(max_workers=WORKERS) as pool:
        pages = list(pool.map(lambda job: _game_log(f"skater/{job[0]}", season, sess, job[1]), jobs))
    frames = {}
    for kind, fields in SKATER_FIELDS.items():
        rows = [r for (k, _), page in zip(jobs, pages, strict=True) if k == kind for r in page]
        frames[kind] = _pick(rows, fields).drop_duplicates(["game_id", "player_id"])
    frame = frames["summary"].merge(frames["realtime"], on=["game_id", "player_id"], how="left").merge(
        frames["timeonice"], on=["game_id", "player_id"], how="left")
    return write_parquet(frame.sort_values(["game_id", "player_id"]).reset_index(drop=True), dest)


# ---------------------------------------------------------------------------
# Play-by-play: shots, penalties and time by strength
# ---------------------------------------------------------------------------


def clock(text) -> int | None:
    """"MM:SS" to seconds."""
    try:
        m, s = str(text).split(":")
        return int(m) * 60 + int(s)
    except (TypeError, ValueError):
        return None


def period_start(number: int) -> int:
    """Seconds of game time before a period starts: regulation and playoff periods are twenty minutes,
    and a regular-season overtime starts where the third ends."""
    return 1200 * (number - 1)


def trim(payload: dict, season: int) -> tuple[list[dict], list[dict], list[dict]]:
    """One game's play-by-play to (shot and penalty rows, seconds per strength state, roster spots)."""
    game_id = int(payload["id"])
    plays = sorted(payload.get("plays") or [], key=lambda p: (p.get("sortOrder") or 0))
    shots: list[dict] = []
    strength: dict[str, int] = {}
    prev = None
    home_score = away_score = 0
    last_t = None
    last_situation = None
    for p in plays:
        pd_ = p.get("periodDescriptor") or {}
        number = int(pd_.get("number") or 0)
        ptype = str(pd_.get("periodType") or "")
        if ptype == "SO":
            break
        within = clock(p.get("timeInPeriod"))
        t = None if within is None else period_start(number) + within
        situation = str(p.get("situationCode") or "") or None
        kind = p.get("typeDescKey")
        # Time in each strength state: from one event to the next, in the state before the change.
        if kind == "period-start":
            last_t, last_situation = t, situation
        elif t is not None and last_t is not None and last_situation and t >= last_t:
            strength[last_situation] = strength.get(last_situation, 0) + (t - last_t)
            last_t = t
            if situation:
                last_situation = situation
        elif situation:
            last_situation = situation
        d = p.get("details") or {}
        if kind in KEPT_EVENTS:
            row = {
                "game_id": game_id, "season": season, "event_id": p.get("eventId"), "sort_order": p.get("sortOrder"),
                "period": number, "period_type": ptype, "seconds": t, "situation": situation, "event": kind,
                "team_id": d.get("eventOwnerTeamId"), "x": d.get("xCoord"), "y": d.get("yCoord"),
                "zone": d.get("zoneCode"), "shot_type": d.get("shotType"),
                "shooter_id": d.get("shootingPlayerId") or d.get("scoringPlayerId"),
                "blocker_id": d.get("blockingPlayerId"),
                "goalie_id": d.get("goalieInNetId"), "home_defends": p.get("homeTeamDefendingSide"),
                "home_score": home_score, "away_score": away_score,
                "prev_event": prev.get("typeDescKey") if prev else None,
                "prev_team_id": ((prev.get("details") or {}).get("eventOwnerTeamId")) if prev else None,
                "prev_x": ((prev.get("details") or {}).get("xCoord")) if prev else None,
                "prev_y": ((prev.get("details") or {}).get("yCoord")) if prev else None,
                "prev_seconds": prev.get("_t") if prev else None,
                "penalty_type": d.get("typeCode") if kind == "penalty" else None,
                "penalty_minutes": d.get("duration") if kind == "penalty" else None,
                "drawn_by_id": d.get("drawnByPlayerId") if kind == "penalty" else None,
            }
            if kind == "penalty":
                row["shooter_id"] = d.get("committedByPlayerId")
            shots.append(row)
        if kind == "goal":
            home_score = d.get("homeScore", home_score)
            away_score = d.get("awayScore", away_score)
        if kind not in ("period-start", "period-end", "game-end", "stoppage", "delayed-penalty"):
            prev = {**p, "_t": t}
    spots = [{"season": season, "player_id": s.get("playerId"),
              "name": " ".join(x for x in ((s.get("firstName") or {}).get("default"),
                                          (s.get("lastName") or {}).get("default")) if x),
              "position": s.get("positionCode"), "team_id": s.get("teamId")}
             for s in payload.get("rosterSpots") or []]
    rows = [{"game_id": game_id, "season": season, "situation": k, "seconds": v} for k, v in sorted(strength.items())]
    return shots, rows, spots


def _pbp(game_id: int, sess) -> dict | None:
    try:
        return http_get(f"{WEB}/gamecenter/{game_id}/play-by-play", sess=sess, timeout=30, retries=2).json()
    except Exception as error:  # noqa: BLE001 - a missing game is fetched next run
        LOG.warning("nhl: play-by-play %s not fetched (%s)", game_id, type(error).__name__)
        return None


FINAL_STATES = (6, 7)       # the stats API's gameStateId: 6 final, 7 official


def fetch_shots(raw: Path, season: int, *, budget: int | None = None, workers: int = WORKERS) -> int:
    """The play-by-play of every completed game not yet cached, up to ``budget`` calls. Returns calls made."""
    games_path = path(raw, "games", season)
    if not games_path.exists():
        return 0
    games = pd.read_parquet(games_path)
    done = games[games["state"].isin(FINAL_STATES)]["game_id"].astype(int).tolist()
    dests = {k: path(raw, k, season) for k in ("shots", "strength", "players")}
    have = {k: (pd.read_parquet(p) if p.exists() else None) for k, p in dests.items()}
    cached = set(have["strength"]["game_id"].astype(int)) if have["strength"] is not None else set()
    todo = [g for g in done if g not in cached]
    if budget is not None:
        todo = todo[-budget:] if budget > 0 else []      # the latest games first
    if not todo:
        return 0
    LOG.info("nhl %d: fetching %d games' play-by-play (%d cached)", season, len(todo), len(cached))
    sess = session()
    shots, strength, spots = [], [], []
    with cf.ThreadPoolExecutor(max_workers=workers) as pool:
        for payload in pool.map(lambda g: _pbp(g, sess), todo):
            if not payload:
                continue
            a, b, c = trim(payload, season)
            shots.extend(a)
            strength.extend(b)
            spots.extend(c)
    fresh = {"shots": pd.DataFrame(shots, columns=SHOT_COLUMNS), "strength": pd.DataFrame(strength,
                                                                                         columns=STRENGTH_COLUMNS),
             "players": pd.DataFrame(spots, columns=PLAYER_COLUMNS)}
    for kind, frame in fresh.items():
        old = have[kind]
        out = frame if old is None or old.empty else pd.concat([old, frame], ignore_index=True)
        if kind == "players":
            out = out.drop_duplicates(["season", "player_id", "team_id"], keep="last")
        elif kind == "strength":
            out = out.drop_duplicates(["game_id", "situation"], keep="last")
        else:
            out = out.drop_duplicates(["game_id", "event_id"], keep="last")
        sort = {"shots": ["game_id", "sort_order"], "strength": ["game_id", "situation"],
                "players": ["player_id", "team_id"]}[kind]
        write_parquet(_typed(out).sort_values(sort, kind="stable").reset_index(drop=True), dests[kind])
    return len(todo)


def _typed(frame: pd.DataFrame) -> pd.DataFrame:
    """Numbers as numbers, so a season's files concatenate without object columns."""
    out = frame.copy()
    for c in out.columns:
        if c in ("situation", "event", "period_type", "zone", "shot_type", "home_defends", "prev_event",
                 "penalty_type", "name", "position"):
            out[c] = out[c].astype("string")
        else:
            out[c] = pd.to_numeric(out[c], errors="coerce")
    return out


# ---------------------------------------------------------------------------
# The odds archive
# ---------------------------------------------------------------------------


def odds_slug(season: int) -> str:
    """The archive's page name: 2020-21, played in 2021 alone, is ``2021``."""
    return "2021" if season == 2020 else f"{season}-{str(season + 1)[-2:]}"


def _american(text) -> float | None:
    t = str(text).strip().lower()
    if t in ("pk", "even", "ev"):
        return 100.0
    try:
        v = float(t)
    except ValueError:
        return None
    return v if abs(v) >= 100 else None


def _number(text) -> float | None:
    try:
        return float(str(text).strip().replace("½", ".5"))
    except ValueError:
        return None


def parse_odds(html: str, season: int) -> pd.DataFrame:
    """The archive's table to one row per game: the date, the two teams by the NHL's code, the final
    score, the opening and closing moneyline each way, the puck line and its prices, and the opening
    and closing total with the over's and the under's prices."""
    rows = [re.findall(r"<td[^>]*>(.*?)</td>", r, re.S) for r in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S)]
    rows = [[re.sub(r"<[^>]+>", "", c).strip() for c in r] for r in rows if r]
    body = [r for r in rows if len(r) >= 12 and r[0].isdigit()]
    out = []
    for v, h in zip(body[0::2], body[1::2], strict=False):
        if v[2] != "V" or h[2] != "H":
            continue
        mmdd = int(v[0])
        month, day = mmdd // 100, mmdd % 100
        year = season if month >= 8 else season + 1
        wide = len(v) >= 16                    # 2014-15 on: the puck line and its price
        row = {"season": season, "date": f"{year}-{month:02d}-{day:02d}",
               "away": ODDS_NAMES.get(re.sub(r"[^a-z]", "", v[3].lower())),
               "home": ODDS_NAMES.get(re.sub(r"[^a-z]", "", h[3].lower())),
               "away_final": _number(v[7]), "home_final": _number(h[7]),
               "away_ml_open": _american(v[8]), "home_ml_open": _american(h[8]),
               "away_ml_close": _american(v[9]), "home_ml_close": _american(h[9])}
        rest_v, rest_h = (v[10:], h[10:])
        if wide:
            row.update(home_pl=_number(h[10]), home_pl_price=_american(h[11]), away_pl_price=_american(v[11]))
            rest_v, rest_h = v[12:], h[12:]
        else:
            row.update(home_pl=None, home_pl_price=None, away_pl_price=None)
        row.update(total_open=_number(rest_v[0]), over_open=_american(rest_v[1]), under_open=_american(rest_h[1]),
                   total_close=_number(rest_v[2]) if len(rest_v) > 2 else None,
                   over_close=_american(rest_v[3]) if len(rest_v) > 3 else None,
                   under_close=_american(rest_h[3]) if len(rest_h) > 3 else None)
        out.append(row)
    return pd.DataFrame(out)


def fetch_odds(raw: Path, season: int, *, refresh: bool = False) -> Path | None:
    if season not in ODDS_SEASONS:
        return None
    dest = path(raw, "odds", season)
    if dest.exists() and not refresh:
        return dest
    sess = session()
    sess.headers["User-Agent"] = BROWSER
    html = http_get(SBRO.format(slug=odds_slug(season)), sess=sess, timeout=60, retries=2).text
    frame = parse_odds(html, season)
    unknown = frame[frame["home"].isna() | frame["away"].isna()]
    if len(unknown):
        LOG.warning("nhl odds %d: %d games with a team name not in the map", season, len(unknown))
    return write_parquet(frame, dest)


# ---------------------------------------------------------------------------
# ESPN's event ids
# ---------------------------------------------------------------------------


def espn_day(day: str, sess) -> list[dict]:
    """ESPN's NHL events on an Eastern date: id, puck drop and both teams by the NHL's code."""
    body = http_get(ESPN, sess=sess, params={"dates": day.replace("-", ""), "limit": 100}, timeout=30,
                    retries=2).json()
    out = []
    for e in body.get("events") or []:
        comp = (e.get("competitions") or [{}])[0]
        sides = {c.get("homeAway"): (c.get("team") or {}) for c in comp.get("competitors") or []}
        home, away = sides.get("home") or {}, sides.get("away") or {}
        out.append({"espn_id": int(e["id"]), "espn_date": day, "start": e.get("date"),
                    "home": ESPN_CODES.get(home.get("abbreviation"), home.get("abbreviation")),
                    "away": ESPN_CODES.get(away.get("abbreviation"), away.get("abbreviation")),
                    "home_espn_id": pd.to_numeric(home.get("id"), errors="coerce"),
                    "away_espn_id": pd.to_numeric(away.get("id"), errors="coerce")})
    return out


def fetch_espn_ids(raw: Path, season: int, *, refresh_days: int = 0) -> Path | None:
    """ESPN's event id for every game of the season, matched by date and both teams. Dates already
    read are kept; the last ``refresh_days`` before today are read again (a postponement moves a game)."""
    games_path, teams_path = path(raw, "games", season), path(raw, "teams")
    if not games_path.exists() or not teams_path.exists():
        return None
    dest = path(raw, "espn", season)
    have = pd.read_parquet(dest) if dest.exists() else pd.DataFrame()
    games = pd.read_parquet(games_path)
    today = datetime.now(UTC).date()
    day = games["date"].astype(str)
    # Played games, and those of the next fortnight; a playoff game never needed stays unplayed.
    wanted = games[games["state"].isin(FINAL_STATES) | ((day >= str(today - timedelta(days=3)))
                                                        & (day <= str(today + timedelta(days=14))))]
    matched = set(have["game_id"].dropna().astype(int)) if len(have) else set()
    stale = {str(today - timedelta(days=i)) for i in range(refresh_days + 1)}
    todo = sorted({str(d) for d, g in zip(wanted["date"], wanted["game_id"], strict=True)
                   if int(g) not in matched or str(d) in stale})
    if not todo and len(have):
        return dest
    sess = session()
    rows = []
    with cf.ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for part in pool.map(lambda d: _espn_or_none(d, sess), todo):
            rows.extend(part)
    fresh = pd.DataFrame(rows)
    events = fresh if have.empty else pd.concat([have[~have["espn_date"].isin(todo)], fresh], ignore_index=True)
    return write_parquet(match_espn(games, pd.read_parquet(teams_path), events), dest)


def _espn_or_none(day: str, sess) -> list[dict]:
    try:
        return espn_day(day, sess)
    except Exception as error:  # noqa: BLE001 - a day not read is read next run
        LOG.warning("nhl: ESPN %s not read (%s)", day, type(error).__name__)
        return []


def match_espn(games: pd.DataFrame, teams: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    """ESPN's events with the NHL game id each is, by both teams on the same date or the next (a
    late West Coast game can fall on the next Eastern date)."""
    cols = ["espn_id", "espn_date", "start", "home", "away", "home_espn_id", "away_espn_id", "game_id"]
    if events.empty:
        return pd.DataFrame(columns=cols)
    code = dict(zip(teams["team_id"], teams["code"], strict=True))
    g = games.assign(home=games["home_id"].map(code).map(franchise), away=games["away_id"].map(code).map(franchise))
    e = events.drop(columns=["game_id"], errors="ignore").assign(
        _home=events["home"].map(franchise), _away=events["away"].map(franchise))
    key = {(str(d), h, a): int(i) for d, h, a, i in zip(g["date"], g["home"], g["away"], g["game_id"], strict=True)}
    ids = []
    for d, h, a in zip(e["espn_date"], e["_home"], e["_away"], strict=True):
        hit = key.get((d, h, a))
        if hit is None:
            prev = str(date.fromisoformat(d) - timedelta(days=1))
            hit = key.get((prev, h, a))
        ids.append(hit)
    out = e.assign(game_id=ids).drop(columns=["_home", "_away"])
    return out.reindex(columns=cols).sort_values(["espn_date", "espn_id"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------


def _safely(label: str, fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except Exception as error:  # noqa: BLE001 - one source's failure is logged; the next run tries again
        from atlas.util import where

        LOG.warning("nhl: %s failed: %s at %s", label, type(error).__name__, where(error))
        return None


#: Minutes a run may spend on history before it leaves the rest for the next run.
HISTORY_MINUTES = 12


def ingest(raw: Path, seasons: list[int], *, current: int, budget: int | None = PBP_BUDGET,
           minutes: float | None = HISTORY_MINUTES) -> dict:
    """The season in progress in full, then history newest first: the play-by-play up to ``budget``
    calls, and no new season started after ``minutes``."""
    import time

    started = time.monotonic()
    _safely("teams", fetch_teams, raw, refresh=current in seasons)
    calls = 0
    for season in sorted(seasons, reverse=True):
        live = season == current
        if not live and minutes is not None and time.monotonic() - started > minutes * 60:
            LOG.info("nhl ingest: %d and earlier left for the next run", season)
            break
        for label, fn in (("games", fetch_games), ("team games", fetch_team_games),
                          ("goalie games", fetch_goalie_games), ("skater games", fetch_skater_games)):
            _safely(f"{season} {label}", fn, raw, season, refresh=live)
        _safely(f"{season} odds", fetch_odds, raw, season)
        _safely(f"{season} ESPN ids", fetch_espn_ids, raw, season, refresh_days=3 if live else 0)
        left = None if budget is None or live else max(budget - calls, 0)
        made = _safely(f"{season} play-by-play", fetch_shots, raw, season, budget=left) or 0
        if not live:
            calls += made
    LOG.info("nhl ingest: %d seasons, %d history play-by-play calls this run", len(seasons), calls)
    return {"seasons": len(seasons), "history_calls": calls}


def main() -> None:
    ap = argparse.ArgumentParser(description="The NHL's API, the odds archive and ESPN's ids, cached")
    ap.add_argument("--seasons", type=int, nargs="*", help="start years; default 2010 to the current season")
    ap.add_argument("--budget", type=int, default=PBP_BUDGET,
                    help="history play-by-play calls this run; 0 means no limit, in calls or in time")
    args = ap.parse_args()
    current = current_season()
    seasons = args.seasons or list(range(FIRST_SEASON, current + 1))
    unlimited = args.budget == 0
    ingest(config.paths().raw, seasons, current=current, budget=None if unlimited else args.budget,
           minutes=None if unlimited else HISTORY_MINUTES)


if __name__ == "__main__":
    main()
