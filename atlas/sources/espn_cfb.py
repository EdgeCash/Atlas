"""College football player box scores from ESPN, one game at a time.

    python -m atlas.sources.espn_cfb                  # the budgeted refresh
    python -m atlas.sources.espn_cfb --budget 3000    # a bigger bite of the backfill

Step 1 of `docs/MODEL_PLAN_DFS_CFB.md`. Atlas's college play-by-play carries
no player names, and college has no nflverse; ESPN's public game summary is
the per-player record: passing, rushing, receiving, fumbles lost, return
touchdowns and kicking, with ESPN athlete ids. Two things DraftKings scores
are not in the box and are read from the scoring plays' text: each field
goal's distance ("Jake Weinberg 36 Yd Field Goal") and successful two-point
conversions ("(X Pass to Y for Two-Point Conversion)").

The history is about 870 games a season, one call each. Rather than one
long backfill, every heavy refresh fetches up to ``BUDGET`` games it does
not have yet - the season in progress first, then the newest seasons back -
and the raw cache keeps them. The season's list of games comes from the
FBS scoreboard, one call a week.

Never fails the run: a game that cannot be read is skipped and tried again
next time.
"""

from __future__ import annotations

import argparse
import re
import time
from pathlib import Path

import pandas as pd

from atlas import config
from atlas.util import _guard_offline, get_logger, http_get, session, write_parquet

LOG = get_logger(__name__)

SCOREBOARD = ("https://site.api.espn.com/apis/site/v2/sports/football/college-football/scoreboard"
              "?groups=80&dates={season}&seasontype={kind}&week={week}&limit=300")
SUMMARY = "https://site.api.espn.com/apis/site/v2/sports/football/college-football/summary?event={event}"
FIRST_SEASON = 2014
BUDGET = 2000                       # games a refresh may fetch
PAUSE = 0.15                        # seconds between calls
REGULAR_WEEKS = range(1, 17)
STAT_COLUMNS = ["pass_cmp", "pass_att", "pass_yds", "pass_td", "pass_int", "rush_car", "rush_yds", "rush_td",
                "rec", "rec_yds", "rec_td", "fum_lost", "kr_td", "pr_td", "fg_made", "fg_att", "xp_made", "xp_att",
                "fg_0_39", "fg_40_49", "fg_50", "two_pt"]
COLUMNS = ["season", "week", "season_type", "event", "team", "opponent", "home", "player_id", "name",
           *STAT_COLUMNS]


def box_dir(raw: Path | None = None) -> Path:
    return (raw or config.paths().raw) / "cfb_players"


def box_path(raw: Path | None, season: int) -> Path:
    return box_dir(raw) / f"box_{season}.parquet"


def games_path(raw: Path | None, season: int) -> Path:
    return box_dir(raw) / f"games_{season}.parquet"


def _num(value) -> float:
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return 0.0


def _made_att(value) -> tuple[float, float]:
    m = re.match(r"\s*(\d+)\s*/\s*(\d+)", str(value or ""))
    return (float(m.group(1)), float(m.group(2))) if m else (0.0, 0.0)


def _norm(name: str) -> str:
    return re.sub(r"[^a-z]", "", str(name or "").lower())


FIELD_GOAL = re.compile(r"^\s*(.+?)\s+(\d+)\s+Yd\s+Field\s+Goal", re.IGNORECASE)
TWO_PASS = re.compile(r"\(([^()]+?)\s+Pass\s+to\s+([^()]+?)\s+for\s+Two-Point\s+Conversion\)", re.IGNORECASE)
TWO_RUN = re.compile(r"\(([^()]+?)\s+Run\s+for\s+Two-Point\s+Conversion\)", re.IGNORECASE)


def scoring_extras(plays: list[dict]) -> tuple[dict, dict]:
    """From the scoring plays: field-goal distances by kicker, and two-point
    conversions by player (passer and receiver both, as DraftKings scores it)."""
    kicks: dict[str, list[int]] = {}
    twos: dict[str, int] = {}
    for p in plays or []:
        text = p.get("text") or ""
        m = FIELD_GOAL.search(text)
        if m and "no good" not in text.lower() and "missed" not in text.lower():
            kicks.setdefault(_norm(m.group(1)), []).append(int(m.group(2)))
        for m in TWO_PASS.finditer(text):
            for who in (m.group(1), m.group(2)):
                twos[_norm(who)] = twos.get(_norm(who), 0) + 1
        for m in TWO_RUN.finditer(text):
            twos[_norm(m.group(1))] = twos.get(_norm(m.group(1)), 0) + 1
    return kicks, twos


def parse(summary: dict, season: int, week: int, season_type: str) -> pd.DataFrame:
    """One row per player with a line in the game's box score."""
    header = (summary.get("header") or {}).get("competitions", [{}])[0]
    sides = {c.get("team", {}).get("abbreviation"): c.get("homeAway") for c in header.get("competitors", [])}
    event = str((summary.get("header") or {}).get("id") or "")
    kicks, twos = scoring_extras(summary.get("scoringPlays", []))
    players: dict[tuple[str, str], dict] = {}
    for team_box in (summary.get("boxscore") or {}).get("players", []) or []:
        team = team_box.get("team", {}).get("abbreviation")
        opponent = next((t for t in sides if t != team), None)
        for cat in team_box.get("statistics", []) or []:
            labels = cat.get("labels") or []
            for a in cat.get("athletes", []) or []:
                ath = a.get("athlete") or {}
                pid = str(ath.get("id") or "")
                if not pid:
                    continue
                row = players.setdefault((team, pid), {
                    "season": season, "week": week, "season_type": season_type, "event": event, "team": team,
                    "opponent": opponent, "home": 1 if sides.get(team) == "home" else 0,
                    "player_id": pid, "name": ath.get("displayName"), **{c: 0.0 for c in STAT_COLUMNS}})
                st = dict(zip(labels, a.get("stats") or [], strict=False))
                name = cat.get("name")
                if name == "passing":
                    row["pass_cmp"], row["pass_att"] = _made_att(st.get("C/ATT"))
                    row["pass_yds"], row["pass_td"], row["pass_int"] = (_num(st.get("YDS")), _num(st.get("TD")),
                                                                         _num(st.get("INT")))
                elif name == "rushing":
                    row["rush_car"], row["rush_yds"], row["rush_td"] = (_num(st.get("CAR")), _num(st.get("YDS")),
                                                                         _num(st.get("TD")))
                elif name == "receiving":
                    row["rec"], row["rec_yds"], row["rec_td"] = (_num(st.get("REC")), _num(st.get("YDS")),
                                                                  _num(st.get("TD")))
                elif name == "fumbles":
                    row["fum_lost"] = _num(st.get("LOST"))
                elif name == "kickReturns":
                    row["kr_td"] = _num(st.get("TD"))
                elif name == "puntReturns":
                    row["pr_td"] = _num(st.get("TD"))
                elif name == "kicking":
                    row["fg_made"], row["fg_att"] = _made_att(st.get("FG"))
                    row["xp_made"], row["xp_att"] = _made_att(st.get("XP"))
    out = pd.DataFrame(list(players.values()), columns=COLUMNS)
    if out.empty:
        return out
    keys = out["name"].map(_norm)
    for i, key in keys.items():
        dists = kicks.get(key, [])
        out.at[i, "fg_0_39"] = sum(1 for d in dists if d < 40)
        out.at[i, "fg_40_49"] = sum(1 for d in dists if 40 <= d < 50)
        out.at[i, "fg_50"] = sum(1 for d in dists if d >= 50)
        out.at[i, "two_pt"] = twos.get(key, 0)
    return out


def _fetch_json(url: str, sess) -> dict:
    _guard_offline(url)
    return http_get(url, sess=sess, timeout=30).json()


def season_games(season: int, fetch, *, pause: float = PAUSE) -> pd.DataFrame:
    """Every FBS game of a season from the scoreboard: id, week, type, completed."""
    rows = []
    weeks = [(2, w) for w in REGULAR_WEEKS] + [(3, 1)]
    for kind, week in weeks:
        try:
            board = fetch(SCOREBOARD.format(season=season, kind=kind, week=week))
        except Exception as error:  # noqa: BLE001 - a missing week is retried next time
            LOG.warning("espn cfb %s week %s: %s", season, week, type(error).__name__)
            continue
        for e in board.get("events", []) or []:
            if int((e.get("season") or {}).get("year", season)) != season:
                continue
            comp = (e.get("competitions") or [{}])[0]
            rows.append({"event": str(e["id"]), "season": season, "week": week if kind == 2 else 99,
                         "season_type": "regular" if kind == 2 else "postseason",
                         "completed": bool(((comp.get("status") or {}).get("type") or {}).get("completed"))})
        time.sleep(pause)
    return pd.DataFrame(rows, columns=["event", "season", "week", "season_type", "completed"]).drop_duplicates("event")


def refresh(raw: Path | None = None, *, budget: int = BUDGET, seasons: list[int] | None = None,
            current: int | None = None, pause: float = PAUSE, fetch=None) -> dict:
    """Fetch up to ``budget`` completed games not yet in the cache, the season
    in progress first, then the newest seasons back. Never raises."""
    from atlas.sources.nflverse import current_season

    raw = raw or config.paths().raw
    current = current or current_season()
    seasons = seasons or list(range(current, FIRST_SEASON - 1, -1))
    sess = session()
    fetch = fetch or (lambda url: _fetch_json(url, sess))
    fetched = failed = 0
    for season in seasons:
        if fetched >= budget:
            break
        gpath, bpath = games_path(raw, season), box_path(raw, season)
        games = pd.read_parquet(gpath) if gpath.exists() else None
        # A finished season's list of games is final; the one in progress is re-read.
        if games is None or season == current or not games["completed"].all():
            games = season_games(season, fetch, pause=pause)
            if games.empty:
                continue
            write_parquet(games, gpath)
        have = pd.read_parquet(bpath) if bpath.exists() else pd.DataFrame(columns=COLUMNS)
        done = set(have["event"].astype(str))
        todo = games[games["completed"] & ~games["event"].astype(str).isin(done)]
        parts = []
        for g in todo.itertuples():
            if fetched >= budget:
                break
            try:
                parts.append(parse(fetch(SUMMARY.format(event=g.event)), season, int(g.week), g.season_type))
                fetched += 1
            except Exception as error:  # noqa: BLE001 - tried again next time
                failed += 1
                LOG.debug("espn cfb game %s: %s", g.event, type(error).__name__)
            time.sleep(pause)
        if parts:
            new = pd.concat([p for p in parts if not p.empty], ignore_index=True)
            write_parquet(pd.concat([have, new], ignore_index=True) if len(have) else new, bpath)
        LOG.info("espn cfb %s: %d of %d completed games cached", season,
                 len(done) + sum(1 for p in parts if not p.empty), int(games["completed"].sum()))
    return {"fetched": fetched, "failed": failed}


def load(raw: Path | None = None, seasons: list[int] | None = None) -> pd.DataFrame:
    """Every cached player-game."""
    raw = raw or config.paths().raw
    paths = sorted(box_dir(raw).glob("box_*.parquet"))
    frames = [pd.read_parquet(p) for p in paths
              if seasons is None or int(p.stem.split("_")[1]) in seasons]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=COLUMNS)


def main() -> None:
    parser = argparse.ArgumentParser(description="ESPN college football player box scores, budgeted")
    parser.add_argument("--budget", type=int, default=BUDGET)
    parser.add_argument("--seasons", type=int, nargs="*")
    args = parser.parse_args()
    try:
        LOG.info("espn cfb: %s", refresh(budget=args.budget, seasons=args.seasons))
    except Exception as error:  # noqa: BLE001 - never fail the heavy run
        LOG.warning("espn cfb refresh failed: %s", type(error).__name__)


if __name__ == "__main__":
    main()
