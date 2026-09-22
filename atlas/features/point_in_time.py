"""Point-in-time feature construction.

The single rule Atlas enforces: a feature attached to a game may only use
information that existed before that game kicked off.

For per-game box-score metrics that means a team's feature for game *n* is
built from games *1..n-1* only. Weeks 1-3 would otherwise be unusable, so the
running mean is shrunk toward the team's **previous season** final mean, which
was known before the current season started, and then toward the league's
previous-season mean when a team has no history (new FBS members, FCS
opponents). Both fallbacks are pre-kickoff facts, so the guarantee holds.

    shrunk = (sum_of_prior_games + k * prior_anchor) / (n_prior_games + k)

with ``k = config.PRIOR_SEASON_SHRINKAGE_GAMES``.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from atlas import config

SORT_KEYS = ["team_id", "season", "kickoff", "game_id"]


def prior_season_means(
    frame: pd.DataFrame, value_cols: list[str], *, team_key: str = "team_id"
) -> pd.DataFrame:
    """Each team's full-season mean, keyed to the season it becomes usable in.

    A 2021 season mean is returned with ``season == 2022``: it is the anchor
    for the *following* season, which is the only season it can be used in
    without leaking.
    """
    season_mean = frame.groupby([team_key, "season"], as_index=False)[value_cols].mean()
    season_mean["season"] = season_mean["season"] + 1
    return season_mean.rename(columns={c: f"{c}__prior_season" for c in value_cols})


def league_prior_season_means(frame: pd.DataFrame, value_cols: list[str]) -> pd.DataFrame:
    """League-wide season means, also shifted forward one season."""
    league = frame.groupby("season", as_index=False)[value_cols].mean()
    league["season"] = league["season"] + 1
    return league.rename(columns={c: f"{c}__league_prior" for c in value_cols})


def add_point_in_time_features(
    frame: pd.DataFrame,
    value_cols: list[str],
    *,
    team_key: str = "team_id",
    shrinkage: float = config.PRIOR_SEASON_SHRINKAGE_GAMES,
    suffix: str = "_pit",
) -> pd.DataFrame:
    """Attach pre-kickoff versions of ``value_cols`` to a team-game frame.

    Returns a copy of ``frame`` with one ``<col><suffix>`` column per input
    column plus ``n_prior_games``.
    """
    missing = [c for c in value_cols if c not in frame.columns]
    if missing:
        raise KeyError(f"missing metric columns: {missing}")

    df = frame.sort_values(SORT_KEYS).reset_index(drop=True).copy()
    team_anchor = prior_season_means(df, value_cols, team_key=team_key)
    league_anchor = league_prior_season_means(df, value_cols)

    df = df.merge(team_anchor, on=[team_key, "season"], how="left")
    df = df.merge(league_anchor, on="season", how="left")

    keys = [df[team_key], df["season"]]
    df["n_prior_games"] = df.groupby(keys, sort=False).cumcount().astype("int64")

    for col in value_cols:
        values = df[col].astype(float)
        # Shift by one row inside each team-season: strictly prior games only.
        prior_sum = values.fillna(0.0).groupby(keys, sort=False).cumsum().groupby(
            keys, sort=False
        ).shift(1).fillna(0.0)
        prior_count = values.notna().astype(float).groupby(keys, sort=False).cumsum().groupby(
            keys, sort=False
        ).shift(1).fillna(0.0)

        anchor = df[f"{col}__prior_season"]
        anchor = anchor.fillna(df[f"{col}__league_prior"])

        with np.errstate(invalid="ignore", divide="ignore"):
            shrunk = (prior_sum + shrinkage * anchor) / (prior_count + shrinkage)
            unshrunk = prior_sum / prior_count.replace(0.0, np.nan)
        # When no anchor exists at all, fall back to the raw prior mean.
        df[f"{col}{suffix}"] = shrunk.where(anchor.notna(), unshrunk)

    drop = [f"{c}__prior_season" for c in value_cols] + [f"{c}__league_prior" for c in value_cols]
    return df.drop(columns=drop)


def to_matchup(
    team_features: pd.DataFrame,
    games: pd.DataFrame,
    feature_cols: list[str],
    *,
    prefix_home: str = "home_",
    prefix_away: str = "away_",
    diff_suffix: str = "_diff",
) -> pd.DataFrame:
    """Pivot per-team features onto one row per game with home/away/diff."""
    keep = ["game_id", "team_id", *feature_cols]
    tf = team_features[keep]

    home = tf.rename(columns={c: f"{prefix_home}{c}" for c in feature_cols})
    home = home.rename(columns={"team_id": "home_team_id"})
    away = tf.rename(columns={c: f"{prefix_away}{c}" for c in feature_cols})
    away = away.rename(columns={"team_id": "away_team_id"})

    out = games[["game_id", "home_team_id", "away_team_id"]].copy()
    out = out.merge(home, on=["game_id", "home_team_id"], how="left")
    out = out.merge(away, on=["game_id", "away_team_id"], how="left")
    for col in feature_cols:
        out[f"{col}{diff_suffix}"] = out[f"{prefix_home}{col}"] - out[f"{prefix_away}{col}"]
    return out
