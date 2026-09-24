"""One row per NFL game, from the nflverse schedules file.

Everything here is a fact about the game as scheduled or as it finished.
The two quarterback columns are the quarterbacks *of record* - who did
start - which is knowable at kickoff at the earliest; the pre-kickoff
expectation (the depth chart's QB1) is a separate column from a separate
file, and the model's features are built from that one.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from atlas.sources import nflverse
from atlas.util import get_logger, write_parquet

LOG = get_logger(__name__)

#: A franchise keeps its id through a relocation: the Rams, Chargers and
#: Raiders are the same teams in 2015 and 2025.
FRANCHISE = {"STL": "LA", "SD": "LAC", "OAK": "LV"}

#: The 32 franchises, by their current nflverse code, in a fixed order so the
#: integer ids are stable across rebuilds.
TEAMS = ["ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE", "DAL", "DEN", "DET", "GB", "HOU", "IND",
         "JAX", "KC", "LA", "LAC", "LV", "MIA", "MIN", "NE", "NO", "NYG", "NYJ", "PHI", "PIT", "SEA", "SF",
         "TB", "TEN", "WAS"]
TEAM_ID = {code: i + 1 for i, code in enumerate(TEAMS)}

GAME_COLUMNS = [
    "game_id", "espn_id", "season", "week", "season_type", "game_type", "kickoff", "home_team", "away_team",
    "home_team_id", "away_team_id", "neutral_site", "home_score", "away_score", "actual_margin", "actual_total",
    "overtime", "closing_spread", "closing_total", "moneyline_home", "moneyline_away", "home_days_rest",
    "away_days_rest", "div_game", "roof", "venue_dome", "surface", "weather_temp", "weather_wind", "stadium",
    "home_qb_id", "away_qb_id", "home_qb_name", "away_qb_name", "home_coach", "away_coach", "referee",
    "completed",
]


def franchise(code: pd.Series) -> pd.Series:
    return code.astype("string").map(lambda c: FRANCHISE.get(c, c))


def team_id(code: pd.Series) -> pd.Series:
    return franchise(code).map(TEAM_ID).astype("Int64")


def build_games(raw: Path, staging: Path, seasons: list[int], *, include_scheduled: bool = True) -> pd.DataFrame:
    sched = nflverse.load_schedules(raw, seasons)
    out = normalise(sched, include_scheduled=include_scheduled)
    write_parquet(out, staging / "nfl" / "games.parquet")
    return out


def normalise(sched: pd.DataFrame, *, include_scheduled: bool = True) -> pd.DataFrame:
    s = sched.copy()
    if not include_scheduled:
        s = s[s["result"].notna()]
    gametime = s["gametime"].fillna("13:00").replace("", "13:00")
    kickoff = pd.to_datetime(s["gameday"].astype(str) + " " + gametime.astype(str), errors="coerce")
    kickoff = kickoff.dt.tz_localize("America/New_York", ambiguous="NaT", nonexistent="shift_forward").dt.tz_convert("UTC")
    home_score = pd.to_numeric(s["home_score"], errors="coerce")
    away_score = pd.to_numeric(s["away_score"], errors="coerce")
    spread = pd.to_numeric(s["spread_line"], errors="coerce")
    roof = s["roof"].fillna("").astype(str)
    out = pd.DataFrame({
        "game_id": s["game_id"].astype(str),
        # ESPN's event id: what the odds poll, the metadata and the site key on.
        "espn_id": pd.to_numeric(s["espn"], errors="coerce").astype("Int64") if "espn" in s else pd.NA,
        "season": s["season"].astype(int),
        "week": s["week"].astype(int),
        "season_type": np.where(s["game_type"] == "REG", "regular", "postseason"),
        "game_type": s["game_type"].astype(str),
        "kickoff": kickoff,
        "home_team": franchise(s["home_team"]),
        "away_team": franchise(s["away_team"]),
        "home_team_id": team_id(s["home_team"]),
        "away_team_id": team_id(s["away_team"]),
        "neutral_site": (s["location"].astype(str) == "Neutral").astype(int),
        "home_score": home_score,
        "away_score": away_score,
        "actual_margin": home_score - away_score,
        "actual_total": home_score + away_score,
        "overtime": pd.to_numeric(s["overtime"], errors="coerce"),
        # nflverse's spread_line is positive when the home side is favoured;
        # Atlas's closing_spread is the book's home line, negative then.
        "closing_spread": -spread,
        "closing_total": pd.to_numeric(s["total_line"], errors="coerce"),
        "moneyline_home": pd.to_numeric(s["home_moneyline"], errors="coerce"),
        "moneyline_away": pd.to_numeric(s["away_moneyline"], errors="coerce"),
        "home_days_rest": pd.to_numeric(s["home_rest"], errors="coerce"),
        "away_days_rest": pd.to_numeric(s["away_rest"], errors="coerce"),
        "div_game": pd.to_numeric(s["div_game"], errors="coerce").fillna(0).astype(int),
        "roof": roof,
        "venue_dome": roof.isin(["dome", "closed"]).astype(int),
        "surface": s["surface"].fillna("").astype(str).str.strip(),
        "weather_temp": pd.to_numeric(s["temp"], errors="coerce"),
        "weather_wind": pd.to_numeric(s["wind"], errors="coerce"),
        "stadium": s["stadium"].astype("string"),
        "home_qb_id": s["home_qb_id"].astype("string"),
        "away_qb_id": s["away_qb_id"].astype("string"),
        "home_qb_name": s["home_qb_name"].astype("string"),
        "away_qb_name": s["away_qb_name"].astype("string"),
        "home_coach": s["home_coach"].astype("string"),
        "away_coach": s["away_coach"].astype("string"),
        "referee": s["referee"].astype("string"),
        "completed": s["result"].notna().astype(int),
    })
    out = out.dropna(subset=["home_team_id", "away_team_id", "kickoff"])
    out = out.sort_values(["kickoff", "game_id"]).reset_index(drop=True)
    LOG.info("nfl games: %d rows, %d completed, seasons %s-%s", len(out), int(out["completed"].sum()),
             out["season"].min(), out["season"].max())
    return out[GAME_COLUMNS]


def to_long(games: pd.DataFrame) -> pd.DataFrame:
    """Two rows per game: each team with its opponent and whether it was home."""
    home = games.rename(columns={"home_team_id": "team_id", "away_team_id": "opponent_id"})
    home = home[["game_id", "season", "week", "season_type", "kickoff", "team_id", "opponent_id"]].assign(is_home=1)
    away = games.rename(columns={"away_team_id": "team_id", "home_team_id": "opponent_id"})
    away = away[["game_id", "season", "week", "season_type", "kickoff", "team_id", "opponent_id"]].assign(is_home=0)
    return pd.concat([home, away], ignore_index=True).sort_values(["kickoff", "game_id", "is_home"]).reset_index(drop=True)


def load(staging: Path) -> pd.DataFrame:
    return pd.read_parquet(staging / "nfl" / "games.parquet")
