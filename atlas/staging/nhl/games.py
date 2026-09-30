"""One row per NHL game, from the NHL's game list, with ESPN's id and each side's rest.

The final score is the NHL's: a shootout adds one goal to its winner. The
regulation score beside it is what sixty minutes produced, and needs no
play-by-play: overtime is sudden death, so its winner scored exactly one
goal more than regulation left, and a shootout's winner's extra goal is the
shootout's. ``home_goals`` and ``away_goals`` take the shootout goal off, as
`docs/MODEL_PLAN_NHL.md` §3 counts them.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from atlas.sources import nhl
from atlas.util import get_logger

LOG = get_logger(__name__)

#: The 32 franchises by their current code, in a fixed order so the integer ids are stable.
TEAMS = ["ANA", "BOS", "BUF", "CAR", "CBJ", "CGY", "CHI", "COL", "DAL", "DET", "EDM", "FLA", "LAK", "MIN", "MTL",
         "NJD", "NSH", "NYI", "NYR", "OTT", "PHI", "PIT", "SEA", "SJS", "STL", "TBL", "TOR", "UTA", "VAN", "VGK",
         "WPG", "WSH"]
TEAM_ID = {code: i + 1 for i, code in enumerate(TEAMS)}
EASTERN = "America/New_York"

GAME_COLUMNS = [
    "game_id", "espn_id", "season", "season_type", "game_type", "date", "kickoff", "home_team", "away_team",
    "home_team_id", "away_team_id", "home_espn_id", "away_espn_id", "home_score", "away_score", "home_goals",
    "away_goals", "reg_home", "reg_away", "decision", "actual_margin", "actual_total", "home_days_rest",
    "away_days_rest", "home_b2b", "away_b2b", "completed",
]


def load(raw: Path, kind: str, seasons: list[int]) -> pd.DataFrame:
    """Every cached season of one raw table."""
    parts = [pd.read_parquet(p) for s in seasons if (p := nhl.path(raw, kind, s)).exists()]
    parts = [p for p in parts if len(p)]
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def codes(raw: Path) -> dict[int, str]:
    """The NHL's team id to its franchise's current code."""
    teams = pd.read_parquet(nhl.path(raw, "teams"))
    return {int(i): nhl.franchise(c) for i, c in zip(teams["team_id"], teams["code"], strict=True)}


def decision(period, game_type) -> str | None:
    """How a completed game was decided: in regulation, in overtime, or by a shootout (regular season
    only: a playoff game's fifth period is its second overtime)."""
    if pd.isna(period):
        return None
    p = int(period)
    if p <= 3:
        return "REG"
    return "SO" if p == 5 and int(game_type) == 2 else "OT"


def normalise(games: pd.DataFrame, code: dict[int, str], espn: pd.DataFrame | None = None) -> pd.DataFrame:
    g = games.copy()
    g["season_type"] = np.where(g["game_type"] == 3, "postseason", "regular")
    g["home_team"] = g["home_id"].map(code)
    g["away_team"] = g["away_id"].map(code)
    g["home_team_id"] = g["home_team"].map(TEAM_ID).astype("Int64")
    g["away_team_id"] = g["away_team"].map(TEAM_ID).astype("Int64")
    start = pd.to_datetime(g["start_et"], errors="coerce")
    g["kickoff"] = start.dt.tz_localize(EASTERN, ambiguous="NaT", nonexistent="NaT").dt.tz_convert("UTC")
    g["completed"] = g["state"].isin(nhl.FINAL_STATES)
    done = g["completed"]
    g["decision"] = [decision(p, t) if c else None for p, t, c in zip(g["period"], g["game_type"], done, strict=True)]
    hs = pd.to_numeric(g["home_score"], errors="coerce").where(done)
    as_ = pd.to_numeric(g["away_score"], errors="coerce").where(done)
    g["home_score"], g["away_score"] = hs, as_
    so, ot = g["decision"] == "SO", g["decision"] == "OT"
    home_won = hs > as_
    # The shootout goal off the winner; the overtime goal off the winner for the regulation score.
    g["home_goals"] = hs - (so & home_won).astype(int)
    g["away_goals"] = as_ - (so & ~home_won).astype(int)
    g["reg_home"] = hs - ((so | ot) & home_won).astype(int)
    g["reg_away"] = as_ - ((so | ot) & ~home_won).astype(int)
    g["actual_margin"] = g["home_goals"] - g["away_goals"]
    g["actual_total"] = g["home_goals"] + g["away_goals"]
    g = add_rest(g)
    if espn is not None and len(espn):
        e = espn.dropna(subset=["game_id"]).drop_duplicates("game_id", keep="last")
        e = e.assign(game_id=e["game_id"].astype("int64"))
        g = g.merge(e[["game_id", "espn_id", "home_espn_id", "away_espn_id"]], on="game_id", how="left")
    else:
        g["espn_id"] = g["home_espn_id"] = g["away_espn_id"] = pd.NA
    for c in ("espn_id", "home_espn_id", "away_espn_id"):
        g[c] = pd.to_numeric(g[c], errors="coerce").astype("Int64")
    return g.reindex(columns=GAME_COLUMNS).sort_values(["kickoff", "game_id"], kind="stable").reset_index(drop=True)


def add_rest(g: pd.DataFrame) -> pd.DataFrame:
    """Days since each side's previous game (any game, the season's first has none), and whether it
    is the second night of a back-to-back."""
    day = pd.to_datetime(g["date"], errors="coerce")
    long = pd.concat([pd.DataFrame({"game_id": g["game_id"], "team": g["home_team"], "day": day, "side": "home"}),
                      pd.DataFrame({"game_id": g["game_id"], "team": g["away_team"], "day": day, "side": "away"})])
    long = long.sort_values(["team", "day", "game_id"], kind="stable")
    long["rest"] = long.groupby("team")["day"].diff().dt.days
    wide = long.pivot_table(index="game_id", columns="side", values="rest", aggfunc="first")
    out = g.copy()
    out["home_days_rest"] = out["game_id"].map(wide.get("home", pd.Series(dtype=float)))
    out["away_days_rest"] = out["game_id"].map(wide.get("away", pd.Series(dtype=float)))
    # A first game of the season carries the summer; it is not a back-to-back.
    out["home_b2b"] = out["home_days_rest"] == 1
    out["away_b2b"] = out["away_days_rest"] == 1
    return out


def build_games(raw: Path, seasons: list[int]) -> pd.DataFrame:
    games = load(raw, "games", seasons)
    espn = load(raw, "espn", seasons)
    if games.empty:
        return pd.DataFrame(columns=GAME_COLUMNS)
    return normalise(games, codes(raw), espn)
