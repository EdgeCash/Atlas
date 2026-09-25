"""Opponent-adjusted efficiency per team-game.

Turns the raw per-game efficiency box scores into ratings that account for who
a team played, using :mod:`atlas.features.opponent_adjustment`. The rating
attached to a game is the one that stood *before* that week kicked off, so the
adjusted features are point-in-time correct in exactly the way the raw ones
are, and the raw-vs-adjusted comparison is therefore fair.

All three adjustment methods are computed and stored. ``network`` (Method C)
is the primary one and carries the unsuffixed column names the Phase 1B brief
specifies; the other two are kept so the report can show what the choice of
method is worth.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from atlas import config
from atlas.features.opponent_adjustment import METHODS, point_in_time_ratings, schedule_strength
from atlas.staging import efficiency as efficiency_stage
from atlas.staging import games as games_stage
from atlas.util import get_logger, write_parquet

LOG = get_logger(__name__)

PRIMARY_METHOD = "network"

#: Added to a postseason week so that the bowls sort after the regular season
#: (atlas/dfs/cfb_slate.py orders college weeks the same way).
POSTSEASON_WEEK_OFFSET = 100


@dataclass(frozen=True)
class MetricStream:
    """One metric, modelled as an actor producing a value against an opponent."""

    name: str
    value_column: str
    actor_output: str
    opponent_output: str
    weight_column: str | None = None
    note: str = ""


#: Every adjusted metric the brief asks for comes out of one of these six
#: solves: each fit yields the actor's rating and what it lets opponents do.
STREAMS: tuple[MetricStream, ...] = (
    MetricStream("epa", "off_epa", "adj_off_epa", "adj_def_epa", "off_plays",
                 "offense is the actor; the fit also yields defensive EPA allowed"),
    MetricStream("success", "success_rate", "adj_success_rate", "adj_def_success_rate",
                 "off_plays"),
    MetricStream("explosiveness", "explosiveness", "adj_explosiveness",
                 "adj_def_explosiveness", "off_plays"),
    MetricStream("havoc", "havoc", "adj_havoc", "adj_havoc_allowed", "def_plays",
                 "defense is the actor here - havoc is something a defense does"),
    MetricStream("finishing", "finishing_drives", "adj_finishing_drives",
                 "adj_def_finishing_drives", None),
    MetricStream("pace", "pace", "adj_pace", "adj_def_pace", None),
)


def adjusted_columns(method: str = PRIMARY_METHOD) -> list[str]:
    suffix = "" if method == PRIMARY_METHOD else f"_{method}"
    out = []
    for stream in STREAMS:
        out.append(f"{stream.actor_output}{suffix}")
        out.append(f"{stream.opponent_output}{suffix}")
    return out


def all_adjusted_columns() -> list[str]:
    return [c for method in METHODS for c in adjusted_columns(method)]


def build_adjusted(
    raw: Path,
    staging: Path,
    *,
    methods: tuple[str, ...] = METHODS,
    include_scheduled: bool = False,
) -> pd.DataFrame:
    eff = efficiency_stage.load(staging)
    long = games_stage.load_long(staging)
    base = long[["game_id", "season", "week", "kickoff", "team_id", "opponent_id", "is_home"]].copy()
    # Postseason weeks restart at 1. The point-in-time window is "weeks before
    # this one", so without an offset December's bowls would fall inside the
    # window of every regular-season week from week 2 on.
    post = long["season_type"].eq("postseason") if "season_type" in long else False
    base["week"] = base["week"] + np.where(post, POSTSEASON_WEEK_OFFSET, 0)

    result = long[["game_id", "season", "week", "team_id"]].assign(_rating_week=base["week"])
    # A week whose games have not kicked off yet contributes no observations,
    # so it would otherwise never be solved for and every scheduled game would
    # come back with a null rating.
    extra_weeks = base[["season", "week"]].drop_duplicates() if include_scheduled else None
    strengths = []
    for stream in STREAMS:
        obs = _observations(base, eff, stream)
        if obs.empty:
            LOG.warning("stream %s has no observations", stream.name)
            continue
        for method in methods:
            ratings = point_in_time_ratings(obs, method=method, extra_weeks=extra_weeks)
            suffix = "" if method == PRIMARY_METHOD else f"_{method}"
            renamed = ratings.rename(
                columns={
                    "actor_rating": f"{stream.actor_output}{suffix}",
                    "opponent_rating": f"{stream.opponent_output}{suffix}",
                }
            )
            keep = ["season", "week", "team_id",
                    f"{stream.actor_output}{suffix}", f"{stream.opponent_output}{suffix}"]
            result = result.merge(renamed[keep].rename(columns={"week": "_rating_week"}),
                                  on=["season", "_rating_week", "team_id"], how="left")
            if method == PRIMARY_METHOD:
                strength = schedule_strength(obs, ratings)
                strength["stream"] = stream.name
                strengths.append(strength)
        LOG.info("adjusted stream %s across %d methods", stream.name, len(methods))

    result = result.drop(columns="_rating_week")
    write_parquet(result, staging / "adjusted_efficiency.parquet")
    if strengths:
        write_parquet(pd.concat(strengths, ignore_index=True),
                      staging / "schedule_strength.parquet")
    return result


def _observations(base: pd.DataFrame, eff: pd.DataFrame, stream: MetricStream) -> pd.DataFrame:
    columns = ["game_id", "team_id", stream.value_column]
    if stream.weight_column and stream.weight_column in eff.columns:
        columns.append(stream.weight_column)
    if stream.value_column not in eff.columns:
        return pd.DataFrame()

    obs = base.merge(eff[columns], on=["game_id", "team_id"], how="inner")
    obs = obs.rename(columns={stream.value_column: "value"})
    if stream.weight_column and stream.weight_column in obs.columns:
        obs = obs.rename(columns={stream.weight_column: "weight"})
    return obs.dropna(subset=["value"])


def load(staging: Path) -> pd.DataFrame:
    return pd.read_parquet(staging / "adjusted_efficiency.parquet")


def load_schedule_strength(staging: Path) -> pd.DataFrame:
    return pd.read_parquet(staging / "schedule_strength.parquet")


def main() -> None:
    paths = config.paths().ensure()
    build_adjusted(paths.raw, paths.staging)


if __name__ == "__main__":
    main()
