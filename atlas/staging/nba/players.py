"""One row per player-game from ESPN's box scores, as hoopR mirrors them: the props model's history.

Minutes and the counting stats a prop is written on, with whether the
player started and whether he dressed; the season by its start year; the
game's side and opponent by ESPN's team ids, which `games.py` keys the
schedule by too. A player who did not play keeps his row with no minutes,
so a projection can tell an absence from a quiet night.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from atlas.staging.nba import games as games_stage
from atlas.util import get_logger

LOG = get_logger(__name__)

STATS = ("points", "rebounds", "assists", "threes", "steals", "blocks")
PLAYER_COLUMNS = ["game_id", "season", "season_type", "date", "player_id", "player", "position", "team_id",
                  "team_abbr", "opponent_id", "is_home", "starter", "played", "minutes", *STATS, "fga", "fta",
                  "turnovers"]


def normalise(box: pd.DataFrame) -> pd.DataFrame:
    b = box.copy()
    num = lambda c: pd.to_numeric(b.get(c), errors="coerce")  # noqa: E731
    out = pd.DataFrame({
        "game_id": num("game_id").astype("int64"),
        "season": num("season").astype(int) - 1,
        "season_type": num("season_type").map(games_stage.SEASON_TYPES),
        "date": pd.to_datetime(b["game_date"], errors="coerce").dt.strftime("%Y-%m-%d"),
        "player_id": num("athlete_id").astype("Int64"),
        "player": b["athlete_display_name"].astype(str),
        "position": b.get("athlete_position_abbreviation", pd.Series("", index=b.index)).fillna("").astype(str).str[:1],
        "team_id": num("team_id").astype("Int64"), "team_abbr": b["team_abbreviation"].astype(str),
        "opponent_id": num("opponent_team_id").astype("Int64"),
        "is_home": b["home_away"].astype(str).str.lower() == "home",
        "starter": b["starter"].fillna(False).astype(bool),
        "minutes": num("minutes").fillna(0.0),
        "points": num("points").fillna(0.0), "rebounds": num("rebounds").fillna(0.0),
        "assists": num("assists").fillna(0.0), "threes": num("three_point_field_goals_made").fillna(0.0),
        "steals": num("steals").fillna(0.0), "blocks": num("blocks").fillna(0.0),
        "fga": num("field_goals_attempted").fillna(0.0), "fta": num("free_throws_attempted").fillna(0.0),
        "turnovers": num("turnovers").fillna(0.0),
    })
    dnp = b["did_not_play"].fillna(False).astype(bool) if "did_not_play" in b else pd.Series(False, index=b.index)
    out["played"] = (~dnp.to_numpy()) & (out["minutes"] > 0)
    out = out[out["season_type"].notna() & out["player_id"].notna()]
    out = out[out["team_abbr"].isin(games_stage.TEAMS)]
    return out.reindex(columns=PLAYER_COLUMNS).sort_values(["player_id", "date", "game_id"], kind="stable") \
        .reset_index(drop=True)


def build_players(raw: Path, seasons: list[int]) -> pd.DataFrame:
    box = games_stage.load(raw, "player_box", seasons)
    if box.empty:
        return pd.DataFrame(columns=PLAYER_COLUMNS)
    out = normalise(box)
    LOG.info("nba player games: %d rows, %d players, %d games", len(out), out["player_id"].nunique(),
             out["game_id"].nunique())
    return out


def results(players: pd.DataFrame) -> pd.DataFrame:
    """What each player did in each game, for grading a prop: the stats, and whether he played."""
    cols = ["game_id", "player_id", "player", "team_id", "played", *STATS]
    if players.empty:
        return pd.DataFrame(columns=cols)
    out = players[cols].copy()
    out["game_id"] = out["game_id"].astype(str)
    out["pra"] = out["points"] + out["rebounds"] + out["assists"]
    return out


