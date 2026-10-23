"""The NFL's player weeks: nflverse's weekly box scores as one table, and each team's week beside them.

``player_games`` is one row per player per game he appeared in, from
nflverse's ``stats_player`` (every player's box score per week, 1999 on;
Atlas keeps 2011 on): the passing, rushing and receiving counts a prop is
written on, the team he played for and the opponent, whether he was at
home, and the kickoff from the schedule. ``team_weeks`` is one row per team
per game: its pass and rush attempts, what its opponent recorded against
it, and the team total the closing line implied - the opportunity a player's
share is taken of, and the game around him.

Point in time is the model's business (`atlas/models/nfl_props.py`): a row
here is what happened, and what the model may see before a kickoff is every
row earlier than it.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from atlas.sources import nflverse
from atlas.staging.nfl.games import FRANCHISE
from atlas.util import get_logger

LOG = get_logger(__name__)

FIRST_SEASON = 2011
#: The positions a prop is written on; a fullback is a running back.
POSITIONS = {"QB": "QB", "RB": "RB", "FB": "RB", "WR": "WR", "TE": "TE"}
COUNTS = ["attempts", "completions", "passing_yards", "passing_tds", "carries", "rushing_yards", "rushing_tds",
          "targets", "receptions", "receiving_yards", "receiving_tds"]
#: The stats a prop is priced on, and what each team's week records as allowed.
PROP_STATS = ("receiving_yards", "receptions", "rushing_yards", "passing_yards", "touchdowns", "passing_tds")
COLUMNS = ["game_id", "espn_id", "season", "week", "season_type", "kickoff", "player_id", "player", "position",
           "team", "opponent", "home", *COUNTS, "touchdowns", "touches", "played"]
TEAM_COLUMNS = ["game_id", "espn_id", "season", "week", "season_type", "kickoff", "team", "opponent", "home",
                "pass_attempts", "rush_attempts", "plays", "implied_total", *[f"allow_{s}" for s in PROP_STATS]]


def load_weeks(raw: Path, seasons: list[int]) -> pd.DataFrame:
    """nflverse's player weeks for ``seasons``, as cached (the season in progress is re-fetched by the
    ingest, not here)."""
    parts = []
    for season in seasons:
        try:
            parts.append(pd.read_parquet(nflverse.fetch_player_stats(raw, season)))
        except Exception as error:  # noqa: BLE001 - a season the release does not have yet
            LOG.warning("nfl player weeks %s not read: %s", season, type(error).__name__)
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def _kickoff(sched: pd.DataFrame) -> pd.Series:
    local = pd.to_datetime(sched["gameday"].astype(str) + " " + sched["gametime"].fillna("13:00").astype(str),
                           errors="coerce")
    return local.dt.tz_localize("America/New_York", nonexistent="shift_forward", ambiguous="NaT").dt.tz_convert("UTC")


def normalise(stats: pd.DataFrame, sched: pd.DataFrame) -> pd.DataFrame:
    """The player weeks in Atlas's columns: offensive positions, the schedule's kickoff and ESPN id, home
    or away, and the touchdowns and touches a prop counts; a franchise that moved under its current code."""
    if stats.empty:
        return pd.DataFrame(columns=COLUMNS)
    s = stats[stats["position"].isin(POSITIONS)].copy()
    s["position"] = s["position"].map(POSITIONS)
    s = s[s["season_type"].isin(["REG", "POST"])]
    games = sched[["game_id", "espn", "home_team", "away_team", "gameday", "gametime"]].copy()
    games["kickoff"] = _kickoff(games)
    games["espn_id"] = pd.to_numeric(games["espn"], errors="coerce").astype("Int64")
    out = s.merge(games[["game_id", "espn_id", "home_team", "kickoff"]], on="game_id", how="inner")
    for c in COUNTS:
        out[c] = pd.to_numeric(out[c], errors="coerce").fillna(0.0)
    out["home"] = (out["team"] == out["home_team"]).astype(float)
    # A franchise that moved keeps its history under its current code (St. Louis to LA, Oakland to LV).
    out["team"] = out["team"].map(lambda c: FRANCHISE.get(c, c))
    out["opponent"] = out["opponent_team"].map(lambda c: FRANCHISE.get(c, c))
    out["player"] = out["player_display_name"]
    out["season_type"] = out["season_type"].map({"REG": "regular", "POST": "postseason"})
    out["touchdowns"] = out["rushing_tds"] + out["receiving_tds"]
    out["touches"] = out["carries"] + out["targets"]
    out["played"] = True
    out["kickoff"] = out["kickoff"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    out = out.sort_values(["kickoff", "game_id", "team", "player_id"], kind="stable")
    return out[COLUMNS].reset_index(drop=True)


def implied_totals(sched: pd.DataFrame) -> pd.DataFrame:
    """Each team's implied total from the closing line: (total ± spread) / 2, the spread the home team's."""
    g = sched[["game_id", "home_team", "away_team", "spread_line", "total_line"]].copy()
    for c in ("home_team", "away_team"):
        g[c] = g[c].map(lambda code: FRANCHISE.get(code, code))
    spread = pd.to_numeric(g["spread_line"], errors="coerce")
    total = pd.to_numeric(g["total_line"], errors="coerce")
    home = pd.DataFrame({"game_id": g["game_id"], "team": g["home_team"], "implied_total": (total + spread) / 2.0})
    away = pd.DataFrame({"game_id": g["game_id"], "team": g["away_team"], "implied_total": (total - spread) / 2.0})
    return pd.concat([home, away], ignore_index=True)


def team_weeks(players: pd.DataFrame, sched: pd.DataFrame) -> pd.DataFrame:
    """One row per team-game: its pass and rush attempts, what its opponent recorded against it, and the
    team total the closing line implied."""
    if players.empty:
        return pd.DataFrame(columns=TEAM_COLUMNS)
    keys = ["game_id", "espn_id", "season", "week", "season_type", "kickoff", "team", "opponent", "home"]
    own = players.groupby(keys, dropna=False).agg(pass_attempts=("attempts", "sum"), rush_attempts=("carries", "sum"),
                                                  **{s: (s, "sum") for s in PROP_STATS}).reset_index()
    own["plays"] = own["pass_attempts"] + own["rush_attempts"]
    allowed = own[["game_id", "team", *PROP_STATS]].rename(columns={"team": "opponent",
                                                                  **{s: f"allow_{s}" for s in PROP_STATS}})
    out = own.merge(allowed, on=["game_id", "opponent"], how="left")
    out = out.merge(implied_totals(sched), on=["game_id", "team"], how="left")
    return out.sort_values(["kickoff", "game_id", "team"], kind="stable")[TEAM_COLUMNS].reset_index(drop=True)


def build(raw: Path, seasons: list[int] | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(player_games, team_weeks) for ``seasons`` (2011 to the season in progress by default)."""
    seasons = seasons or list(range(FIRST_SEASON, nflverse.current_season() + 1))
    sched = pd.read_parquet(nflverse.fetch_schedules(raw, refresh=False))
    players = normalise(load_weeks(raw, seasons), sched)
    teams = team_weeks(players, sched)
    LOG.info("nfl player weeks: %d rows, %d team-games, seasons %s-%s", len(players), len(teams),
             seasons[0], seasons[-1])
    return players, teams


def results(players: pd.DataFrame) -> pd.DataFrame:
    """What each player did in each game, for grading a prop: keyed by the ESPN game id."""
    cols = ["game_id", "player_id", "player", "team", "played", *PROP_STATS]
    if players.empty:
        return pd.DataFrame(columns=cols)
    out = players[players["espn_id"].notna()].copy()
    out["game_id"] = out["espn_id"].astype("int64").astype(str)
    return out[cols].reset_index(drop=True)
