"""One row per NBA game, from ESPN's schedule, with the archive's closing lines joined on.

ESPN's event id is the game id, as it is in the live tracker; ESPN's team
ids are the team ids (a franchise keeps its id through a move: Seattle is
Oklahoma City's, New Jersey is Brooklyn's). The season is the year it starts.
The week is the number of weeks since the season's first regular-season tip,
so the Kalman state adds its process noise at the same cadence football's
does; the play-in and the playoffs are the postseason.

The closing spread is the home handicap, negative when the home side is
favoured, as every Atlas frame carries it (``market_margin`` is its
negation); joined to the game by its local date and both abbreviations.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from atlas.sources import nba
from atlas.util import get_logger

LOG = get_logger(__name__)

EASTERN = "America/New_York"
#: ESPN's abbreviations for the thirty franchises and the two they were before they moved.
TEAMS = ["ATL", "BKN", "BOS", "CHA", "CHI", "CLE", "DAL", "DEN", "DET", "GS", "HOU", "IND", "LAC", "LAL", "MEM", "MIA",
         "MIL", "MIN", "NO", "NY", "OKC", "ORL", "PHI", "PHX", "POR", "SA", "SAC", "TOR", "UTAH", "WSH", "NJ", "SEA"]
SEASON_TYPES = {2: "regular", 3: "postseason", 5: "postseason"}

GAME_COLUMNS = [
    "game_id", "espn_id", "season", "season_type", "week", "kickoff", "date", "home_team", "away_team", "home_team_id",
    "away_team_id", "home_abbr", "away_abbr", "home_score", "away_score", "actual_margin", "actual_total",
    "neutral_site", "completed", "home_days_rest", "away_days_rest", "home_b2b", "away_b2b", "opening_spread",
    "opening_total", "closing_spread", "closing_total", "home_ml_close", "away_ml_close",
]


def load(raw: Path, kind: str, seasons: list[int]) -> pd.DataFrame:
    """Every cached season of one raw table."""
    parts = [pd.read_parquet(p) for s in seasons if (p := nba.path(raw, kind, s)).exists()]
    parts = [p for p in parts if len(p)]
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def normalise(schedule: pd.DataFrame, odds: pd.DataFrame | None = None) -> pd.DataFrame:
    s = schedule.copy()
    s = s[s["home_abbreviation"].isin(TEAMS) & s["away_abbreviation"].isin(TEAMS)]
    if "type_abbreviation" in s:
        s = s[s["type_abbreviation"].fillna("") != "ALLSTAR"]
    s = s[s["season_type"].isin(SEASON_TYPES)]
    g = pd.DataFrame({
        "game_id": pd.to_numeric(s["id"], errors="coerce").astype("int64"),
        "season": pd.to_numeric(s["season"], errors="coerce").astype(int) - 1,
        "season_type": s["season_type"].map(SEASON_TYPES),
        "kickoff": pd.to_datetime(s["date"], utc=True, errors="coerce"),
        "home_team": s["home_display_name"].astype(str), "away_team": s["away_display_name"].astype(str),
        "home_team_id": pd.to_numeric(s["home_id"], errors="coerce").astype("Int64"),
        "away_team_id": pd.to_numeric(s["away_id"], errors="coerce").astype("Int64"),
        "home_abbr": s["home_abbreviation"].astype(str), "away_abbr": s["away_abbreviation"].astype(str),
        "neutral_site": s["neutral_site"].fillna(False).astype(bool).astype(int),
    })
    g["espn_id"] = g["game_id"]
    done = s["status_type_completed"].fillna(False).astype(bool).to_numpy()
    hs = pd.to_numeric(s["home_score"], errors="coerce").where(done)
    as_ = pd.to_numeric(s["away_score"], errors="coerce").where(done)
    g["completed"] = done & hs.notna().to_numpy() & as_.notna().to_numpy()
    g["home_score"], g["away_score"] = hs.where(g["completed"]), as_.where(g["completed"])
    g["actual_margin"] = g["home_score"] - g["away_score"]
    g["actual_total"] = g["home_score"] + g["away_score"]
    g["date"] = g["kickoff"].dt.tz_convert(EASTERN).dt.strftime("%Y-%m-%d")
    g = g.dropna(subset=["kickoff"]).sort_values(["kickoff", "game_id"], kind="stable").reset_index(drop=True)
    g["week"] = weeks(g)
    g = add_rest(g)
    if odds is not None and len(odds):
        o = odds.dropna(subset=["home", "away"]).drop_duplicates(["date", "home", "away"], keep="last")
        o = o.rename(columns={"home": "home_abbr", "away": "away_abbr"})
        g = g.merge(o[["date", "home_abbr", "away_abbr", "opening_spread", "opening_total", "closing_spread",
                       "closing_total", "home_ml_close", "away_ml_close"]], on=["date", "home_abbr", "away_abbr"],
                    how="left")
    return g.reindex(columns=GAME_COLUMNS)


def weeks(g: pd.DataFrame) -> pd.Series:
    """Weeks since the season's first regular-season tip, from one."""
    first = g[g["season_type"] == "regular"].groupby("season")["kickoff"].min()
    start = g["season"].map(first)
    start = start.where(start.notna(), g.groupby("season")["kickoff"].transform("min"))
    days = (g["kickoff"] - start).dt.total_seconds() / 86400.0
    return (np.floor(days.clip(lower=0) / 7.0) + 1).astype(int)


def add_rest(g: pd.DataFrame) -> pd.DataFrame:
    """Days since each side's previous game and whether it is the second night of a back-to-back."""
    day = pd.to_datetime(g["date"], errors="coerce")
    long = pd.concat([pd.DataFrame({"game_id": g["game_id"], "team": g["home_team_id"], "day": day, "side": "home"}),
                      pd.DataFrame({"game_id": g["game_id"], "team": g["away_team_id"], "day": day, "side": "away"})])
    long = long.sort_values(["team", "day", "game_id"], kind="stable")
    long["rest"] = long.groupby("team")["day"].diff().dt.days
    wide = long.pivot_table(index="game_id", columns="side", values="rest", aggfunc="first")
    out = g.copy()
    out["home_days_rest"] = out["game_id"].map(wide.get("home", pd.Series(dtype=float)))
    out["away_days_rest"] = out["game_id"].map(wide.get("away", pd.Series(dtype=float)))
    out["home_b2b"] = out["home_days_rest"] == 1
    out["away_b2b"] = out["away_days_rest"] == 1
    return out


def build_games(raw: Path, seasons: list[int]) -> pd.DataFrame:
    schedule = load(raw, "schedule", seasons)
    if schedule.empty:
        return pd.DataFrame(columns=GAME_COLUMNS)
    odds = load(raw, "odds", seasons)
    return normalise(schedule, odds if len(odds) else None)


def team_games(raw: Path, seasons: list[int]) -> pd.DataFrame:
    """Each team's box score per game with a possessions estimate (field goal attempts less offensive
    rebounds, plus turnovers and 0.44 of free throw attempts) and its points per hundred of them."""
    box = load(raw, "team_box", seasons)
    if box.empty:
        return pd.DataFrame(columns=["game_id", "season", "team_id", "team_abbr", "is_home", "points", "possessions",
                                     "points_per_100"])
    b = box.copy()
    num = lambda c: pd.to_numeric(b.get(c), errors="coerce")  # noqa: E731
    poss = num("field_goals_attempted") - num("offensive_rebounds") + num("total_turnovers") \
        + 0.44 * num("free_throws_attempted")
    out = pd.DataFrame({"game_id": pd.to_numeric(b["game_id"], errors="coerce").astype("int64"),
                        "season": pd.to_numeric(b["season"], errors="coerce").astype(int) - 1,
                        "team_id": pd.to_numeric(b["team_id"], errors="coerce").astype("Int64"),
                        "team_abbr": b["team_abbreviation"].astype(str), "is_home": b["team_home_away"] == "home",
                        "points": num("team_score"), "possessions": poss})
    out["points_per_100"] = 100.0 * out["points"] / out["possessions"].where(out["possessions"] > 0)
    return out.sort_values(["game_id", "is_home"]).reset_index(drop=True)
