"""The game each player plays in, as Atlas's own game model saw it before kickoff.

    python -m atlas.dfs.environment        # writes data/staging/nfl/dfs_team_environment.parquet

Step 3 of `docs/MODEL_PLAN_DFS.md` anchors every player projection in the
game model's projection of his team's points. This produces that history:
for every NFL game from 2011, each side's projected points before kickoff,
from the same joint Kalman filter (team offense and defense, quarterback
state, fitted home advantage) that projects the game cards
(`atlas/models/nfl_state.py`), with each quarterback's own state going in,
and the wind - the one game-level term Atlas's total model found real (a
dome is zero wind; `atlas/models/nfl_total.py`).

The filter runs continuously from 2011, one season at a time, each season
forecast from the state the games before it left. Each season uses its own
tuned hyperparameters where the NFL state model has them (2020 on, each
tuned on earlier seasons only); earlier seasons use 2020's, which were tuned
on 2017-2019 - a look-ahead of four smoothing constants, not of results, for
those three seasons. The cleanest test of anything built on this is
2022-2025.
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from atlas import config
from atlas.models import nfl_state as ns
from atlas.research.nfl_dataset import (
    load_nfl_frame,
    load_passer_games,
    load_players,
    research_sample,
)
from atlas.util import get_logger, write_parquet

LOG = get_logger(__name__)


def path():
    return config.paths().staging / "nfl" / "dfs_team_environment.parquet"


def build(warehouse=None) -> pd.DataFrame:
    paths = config.paths()
    frame = load_nfl_frame(warehouse or paths.warehouse)
    sample = research_sample(frame)
    completed = frame[frame["actual_margin"].notna()]
    team_choices, qb_choices = ns.load_choices(ns.choices_path(paths.root))
    first_tuned = min(team_choices)
    try:
        record = ns.PasserRecord(load_passer_games(paths.warehouse), load_players(paths.warehouse))
    except Exception as error:  # noqa: BLE001 - an older warehouse has no passer log
        LOG.warning("no passer log (%s); new quarterbacks get the flat prior", error)
        record = None
    seasons = sorted(int(s) for s in frame["season"].unique())
    levels = {s: ns._levels(sample[sample["season"] < max(s, seasons[0] + 1)], s) for s in seasons}
    teams = np.unique(np.r_[frame["home_team_id"], frame["away_team_id"]])

    state, starters, parts = None, {}, []
    for season in seasons:
        key = season if season in team_choices else first_tuned
        choice, qb = team_choices[key], qb_choices[key]
        games = frame[frame["season"] == season]
        # Completed games are assimilated; this season's scheduled games are
        # forecast but, having no result, teach the filter nothing.
        fcs, state, starters = ns.run_qb(games, [season], choice=choice, p0=qb.p0, new_mean=qb.new_mean,
                                         levels=levels, state=state, starters=starters, teams=teams, k_epa=qb.k_epa,
                                         record=record, k_obs=qb.k_obs, k_draft=qb.k_draft)
        fc = fcs[season]
        wind = pd.to_numeric(games.get("weather_wind"), errors="coerce")
        dome = pd.to_numeric(games.get("venue_dome", 0), errors="coerce").fillna(0)
        g = games.assign(wind=np.where(dome == 1, 0.0, wind), home_pts=fc["home_pts"].to_numpy(), away_pts=fc["away_pts"].to_numpy(),
                         home_qb_state=fc["home_qb_state"].to_numpy(), away_qb_state=fc["away_qb_state"].to_numpy())
        for side, other in (("home", "away"), ("away", "home")):
            parts.append(pd.DataFrame({
                "game_id": g["game_id"].to_numpy(), "season": g["season"].to_numpy(), "week": g["week"].to_numpy(),
                "season_type": g["season_type"].to_numpy(), "team": g[f"{side}_team"].to_numpy(),
                "opponent": g[f"{other}_team"].to_numpy(), "home": 1 if side == "home" else 0,
                "team_pts": g[f"{side}_pts"].to_numpy(), "opp_pts": g[f"{other}_pts"].to_numpy(),
                "qb_state": g[f"{side}_qb_state"].to_numpy(), "opp_qb_state": g[f"{other}_qb_state"].to_numpy(),
                "wind": g["wind"].to_numpy(), "completed": g["actual_margin"].notna().to_numpy(),
            }))
    env = pd.concat(parts, ignore_index=True)
    env["proj_total"] = env["team_pts"] + env["opp_pts"]
    env["proj_margin"] = env["team_pts"] - env["opp_pts"]
    # The team's usual projected points over its earlier games: this week's
    # projection against it says whether the environment is richer than usual.
    env = env.sort_values(["team", "season", "week"])
    env["team_pts_trend"] = env.groupby("team")["team_pts"].transform(
        lambda s: s.shift(1).ewm(halflife=4, ignore_na=True).mean())
    env = env.sort_values(["season", "week", "game_id", "home"], ascending=[True, True, True, False])
    write_parquet(env.reset_index(drop=True), path())
    LOG.info("environment: %d team-games, %d seasons, %d completed", len(env), len(seasons), int(completed.shape[0]))
    return env


def main() -> None:
    argparse.ArgumentParser(description="The game model's pre-kickoff team projections, 2011 on").parse_args()
    build()


if __name__ == "__main__":
    main()
