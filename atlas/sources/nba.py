"""The NBA from hoopR's ESPN mirror and the odds archive, cached one file per season, no key.

    python -m atlas.sources.nba                    # the season in progress, then every missing season
    python -m atlas.sources.nba --seasons 2024 2025

Seasons are numbered by the year they start (2025 is 2025-26), as Atlas
numbers hockey's; hoopR numbers them by the year they end, and the file
names say so. Everything lands under ``data/raw/nba/``:

* ``schedule``  - one row per game from ESPN's schedule, as hoopR mirrors
                  it (sportsdataverse): ESPN's event id (the id the live
                  tracker keys a game by), the tip, both teams with ESPN's
                  ids and abbreviations, the final score, the neutral-site
                  flag and the status; the All-Star weekend rides along and
                  staging drops it;
* ``team_box``  - each team's box score per game: points, field goals, free
                  throws, rebounds, turnovers;
* ``odds``      - SportsBookReviewsOnline's archive, 2007-08 to 2022-23: the
                  opening and closing spread and total and the closing
                  moneyline each way. A personal-use archive: cached, used for
                  the model's record, never republished. The archive stops
                  after 2022-23; from there the market is Polymarket's own
                  close, kept by the live run.

A completed season is fetched once; the season in progress is re-fetched
on every run. The run never fails the heavy refresh: a source that errors
is logged and left for the next run.
"""

from __future__ import annotations

import argparse
import re
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd

from atlas import config
from atlas.util import get_logger, http_get, session, write_parquet

LOG = get_logger(__name__)

HOOPR = "https://raw.githubusercontent.com/sportsdataverse/hoopR-nba-data/main/nba/{kind}/parquet/{name}_{file}.parquet"
HOOPR_KINDS = {"schedule": ("schedules", "nba_schedule"), "team_box": ("team_box", "team_box")}
SBRO = "https://www.sportsbookreviewsonline.com/scoresoddsarchives/nba-odds-{slug}/"
#: The archive needs a browser's user agent.
BROWSER = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"

#: The first season with the odds archive; the model's record starts here.
FIRST_SEASON = 2007
ODDS_SEASONS = range(2007, 2023)
#: A spread never reaches this; a total never falls below it. How the archive's one column is read.
SPREAD_CEILING = 60.0

SCHEDULE_COLUMNS = ["id", "date", "season", "season_type", "type_abbreviation", "status_type_name",
                    "status_type_completed", "neutral_site", "home_id", "home_abbreviation", "home_display_name",
                    "home_score", "away_id", "away_abbreviation", "away_display_name", "away_score"]
BOX_COLUMNS = ["game_id", "season", "team_id", "team_abbreviation", "team_home_away", "team_score", "opponent_team_id",
               "field_goals_attempted", "free_throws_attempted", "offensive_rebounds", "total_turnovers", "assists",
               "three_point_field_goals_attempted"]

#: The archive's spellings to ESPN's abbreviation of the day. Seattle and New Jersey are the franchises
#: that moved (Oklahoma City in 2008, Brooklyn in 2012); the schedule spells them as they were.
ODDS_NAMES = {
    "atlanta": "ATL", "boston": "BOS", "brooklyn": "BKN", "charlotte": "CHA", "chicago": "CHI", "cleveland": "CLE",
    "dallas": "DAL", "denver": "DEN", "detroit": "DET", "goldenstate": "GS", "houston": "HOU", "indiana": "IND",
    "laclippers": "LAC", "lalakers": "LAL", "memphis": "MEM", "miami": "MIA", "milwaukee": "MIL", "minnesota": "MIN",
    "newjersey": "NJ", "neworleans": "NO", "newyork": "NY", "oklahomacity": "OKC", "orlando": "ORL",
    "philadelphia": "PHI", "phoenix": "PHX", "portland": "POR", "sacramento": "SAC", "sanantonio": "SA",
    "seattle": "SEA", "toronto": "TOR", "utah": "UTAH", "washington": "WSH",
}


def nba_dir(raw: Path) -> Path:
    return raw / "nba"


def path(raw: Path, kind: str, season: int) -> Path:
    return nba_dir(raw) / f"{kind}_{season}.parquet"


def file_season(season: int) -> int:
    """hoopR's number for a season: the year it ends."""
    return season + 1


def current_season(today: date | None = None) -> int:
    """The season in progress or next up: October starts one."""
    today = today or datetime.now(UTC).date()
    return today.year if today.month >= 10 else today.year - 1


def odds_slug(season: int) -> str:
    return f"{season}-{str(season + 1)[-2:]}"


# ---------------------------------------------------------------------------
# hoopR
# ---------------------------------------------------------------------------


def _hoopr(kind: str, season: int, sess) -> pd.DataFrame:
    folder, name = HOOPR_KINDS[kind]
    url = HOOPR.format(kind=folder, name=name, file=file_season(season))
    r = http_get(url, sess=sess, timeout=120, retries=3)
    return pd.read_parquet(pd.io.common.BytesIO(r.content))


def fetch_schedule(raw: Path, season: int, *, refresh: bool = False, sess=None) -> Path:
    dest = path(raw, "schedule", season)
    if dest.exists() and not refresh:
        return dest
    frame = _hoopr("schedule", season, sess or session())
    keep = [c for c in SCHEDULE_COLUMNS if c in frame.columns]
    return write_parquet(frame[keep].copy(), dest)


def fetch_team_box(raw: Path, season: int, *, refresh: bool = False, sess=None) -> Path:
    dest = path(raw, "team_box", season)
    if dest.exists() and not refresh:
        return dest
    frame = _hoopr("team_box", season, sess or session())
    keep = [c for c in BOX_COLUMNS if c in frame.columns]
    return write_parquet(frame[keep].copy(), dest)


# ---------------------------------------------------------------------------
# The odds archive
# ---------------------------------------------------------------------------


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
    t = str(text).strip().lower().replace("½", ".5")
    if t in ("pk", "pick"):
        return 0.0
    try:
        return float(t)
    except ValueError:
        return None


def _spread_and_total(v, h) -> tuple[float | None, float | None]:
    """The archive puts one number on each row of a game: the favourite's spread on its row, the total on
    the other's. Returns (the home handicap, the total): negative when the home side is favoured."""
    a, b = _number(v), _number(h)
    if a is None and b is None:
        return None, None
    if a is not None and (b is None or a < SPREAD_CEILING <= b):
        return a, b                        # the visitor is the favourite: the home side gets the points
    if b is not None and (a is None or b < SPREAD_CEILING <= a):
        return -b, a                       # the home side is the favourite
    return None, None


def parse_odds(html: str, season: int) -> pd.DataFrame:
    """The archive's table to one row per game: the date, the two teams by ESPN's abbreviation, the final
    score, the opening and closing spread (the home handicap) and total, and the closing moneylines."""
    rows = [re.findall(r"<td[^>]*>(.*?)</td>", r, re.S) for r in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S)]
    rows = [[re.sub(r"<[^>]+>", "", c).strip() for c in r] for r in rows if r]
    body = [r for r in rows if len(r) >= 12 and r[0].isdigit()]
    out = []
    for v, h in zip(body[0::2], body[1::2], strict=False):
        if v[2] != "V" or h[2] != "H":
            continue
        mmdd = int(v[0])
        month, day = mmdd // 100, mmdd % 100
        year = season if month >= 9 else season + 1
        open_spread, open_total = _spread_and_total(v[9], h[9])
        close_spread, close_total = _spread_and_total(v[10], h[10])
        out.append({"season": season, "date": f"{year}-{month:02d}-{day:02d}",
                    "away": ODDS_NAMES.get(re.sub(r"[^a-z]", "", v[3].lower())),
                    "home": ODDS_NAMES.get(re.sub(r"[^a-z]", "", h[3].lower())),
                    "away_final": _number(v[8]), "home_final": _number(h[8]),
                    "opening_spread": open_spread, "opening_total": open_total,
                    "closing_spread": close_spread, "closing_total": close_total,
                    "away_ml_close": _american(v[11]), "home_ml_close": _american(h[11])})
    return pd.DataFrame(out, columns=["season", "date", "away", "home", "away_final", "home_final", "opening_spread",
                                      "opening_total", "closing_spread", "closing_total", "away_ml_close",
                                      "home_ml_close"])


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
        LOG.warning("nba odds %d: %d games with a team name not in the map", season, len(unknown))
    return write_parquet(frame, dest)


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------


def _safely(label: str, fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except Exception as error:  # noqa: BLE001 - one source's outage is not the run's
        LOG.warning("nba %s not fetched: %s", label, type(error).__name__)
        return None


def run(raw: Path | None = None, seasons: list[int] | None = None) -> None:
    raw = raw or config.paths().raw
    live = current_season()
    seasons = seasons or list(range(FIRST_SEASON, live + 1))
    sess = session()
    for season in sorted(seasons, reverse=True):
        refresh = season == live
        _safely(f"{season} schedule", fetch_schedule, raw, season, refresh=refresh, sess=sess)
        _safely(f"{season} team box", fetch_team_box, raw, season, refresh=refresh, sess=sess)
        _safely(f"{season} odds", fetch_odds, raw, season)
    LOG.info("nba raw cache: %s", nba_dir(raw))


def main() -> None:
    ap = argparse.ArgumentParser(description="The NBA's schedule, box scores and odds archive, cached")
    ap.add_argument("--seasons", type=int, nargs="*", help="start years; default 2007 to the current season")
    args = ap.parse_args()
    run(seasons=args.seasons or None)


if __name__ == "__main__":
    main()
