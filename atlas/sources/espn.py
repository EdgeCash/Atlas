"""ESPN public endpoints used for FPI.

Two distinct FPI artefacts are collected, and they differ in what an Atlas
consumer is allowed to do with them:

``season_fpi``
    End-of-season FPI ratings on a net-points scale. Atlas only ever joins
    season ``S-1`` onto games in season ``S``; the same-season value is a
    post-hoc rating and would leak.

``game_predictor``
    ESPN's pre-game FPI projection for a specific matchup (win probability at
    the time of the BPI run). This is published before kickoff and is
    point-in-time safe as-is.
"""

from __future__ import annotations

import concurrent.futures as cf
from pathlib import Path

import pandas as pd

from atlas.util import get_logger, http_get, session, write_parquet

LOG = get_logger(__name__)

FPI_URL = "https://site.web.api.espn.com/apis/fitt/v3/sports/football/college-football/powerindex"
CORE = "https://sports.core.api.espn.com/v2/sports/football/leagues/college-football"


def season_fpi_path(raw: Path, season: int) -> Path:
    return raw / "espn_fpi" / f"fpi_{season}.parquet"


def predictor_path(raw: Path, season: int) -> Path:
    return raw / "espn_predictor" / f"predictor_{season}.parquet"


def fetch_season_fpi(raw: Path, season: int) -> Path:
    """End-of-season FPI for every FBS team."""
    dest = season_fpi_path(raw, season)
    if dest.exists():
        return dest
    sess = session()
    rows: list[dict] = []
    page = 1
    while True:
        payload = http_get(
            FPI_URL, sess=sess, params={"season": season, "limit": 50, "page": page}
        ).json()
        teams = payload.get("teams", [])
        if not teams:
            break
        names = _fpi_value_names(payload)
        for entry in teams:
            team = entry.get("team", {})
            values = _category_values(entry, "fpi")
            row = {
                "season": season,
                "team_id": int(team["id"]),
                "team": team.get("shortDisplayName") or team.get("displayName"),
            }
            for name, value in zip(names, values, strict=False):
                if name in ("fpi", "fpirank"):
                    row[name] = value
            rows.append(row)
        if page >= payload.get("pagination", {}).get("pages", 1):
            break
        page += 1
    df = pd.DataFrame(rows)
    if df.empty:
        LOG.warning("no FPI returned for %s", season)
    return write_parquet(df, dest)


def _fpi_value_names(payload: dict) -> list[str]:
    for cat in payload.get("categories", []):
        if cat.get("name") == "fpi":
            return list(cat.get("names", []))
    return []


def _category_values(entry: dict, name: str) -> list:
    for cat in entry.get("categories", []):
        if cat.get("name") == name:
            return list(cat.get("values", []))
    return []


def fetch_game_predictors(
    raw: Path, season: int, game_ids: list[int], *, workers: int = 8
) -> Path:
    """Pre-game FPI win projections for a season's games.

    One HTTP call per game; results are cached per season so a rebuild only
    fetches games it has never seen.
    """
    dest = predictor_path(raw, season)
    known: pd.DataFrame | None = None
    if dest.exists():
        known = pd.read_parquet(dest)
        have = set(known["game_id"].astype("int64"))
        game_ids = [g for g in game_ids if g not in have]
    if not game_ids:
        return dest

    LOG.info("fetching %d ESPN predictors for %s", len(game_ids), season)
    sess = session()

    def one(gid: int) -> dict | None:
        url = f"{CORE}/events/{gid}/competitions/{gid}/predictor"
        try:
            payload = http_get(url, sess=sess, retries=1, timeout=30).json()
        except Exception:  # noqa: BLE001 - absent predictors are expected
            return None
        home = _stat(payload.get("homeTeam", {}), "gameProjection")
        away = _stat(payload.get("awayTeam", {}), "gameProjection")
        if home is None and away is None:
            return None
        return {
            "game_id": gid,
            "season": season,
            "fpi_home_win_prob": None if home is None else home / 100.0,
            "fpi_away_win_prob": None if away is None else away / 100.0,
        }

    rows: list[dict] = []
    with cf.ThreadPoolExecutor(max_workers=workers) as pool:
        for result in pool.map(one, game_ids):
            if result:
                rows.append(result)
    df = pd.DataFrame(rows)
    if known is not None and not known.empty:
        df = pd.concat([known, df], ignore_index=True).drop_duplicates("game_id", keep="last")
    return write_parquet(df, dest)


def _stat(team_block: dict, name: str) -> float | None:
    for stat in team_block.get("statistics", []):
        if stat.get("name") == name:
            return stat.get("value")
    return None
