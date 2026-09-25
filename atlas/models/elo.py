"""A walk-forward Elo, FiveThirtyEight's NFL parameters, for the benchmarks.

    home_elo, away_elo = pregame ratings before every game, in kickoff order

College carries a pregame Elo on its game rows; the NFL frame does not, so
this computes one. Each game's ratings are those before it kicked off - the
update happens after the row is written - and a new season regresses every
team a third of the way to the mean. The ratings are in Elo points; divide
the difference by 25 for a margin in points, which is how the reference
model reads it.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Params:
    k: float = 20.0
    home_field: float = 48.0          # Elo points, about 1.9 points of margin
    mean: float = 1505.0
    revert: float = 1 / 3             # share of the gap to the mean given back each new season
    points_per_elo: float = 1 / 25    # 25 Elo points per point of margin


FIVETHIRTYEIGHT = Params()


def _expected(diff: float) -> float:
    return 1.0 / (1.0 + 10.0 ** (-diff / 400.0))


def _mov_multiplier(margin: float, diff: float) -> float:
    """FiveThirtyEight's margin-of-victory multiplier, damped for favourites."""
    winner_diff = diff if margin > 0 else -diff
    return np.log(abs(margin) + 1.0) * (2.2 / (winner_diff * 0.001 + 2.2))


def pregame(games: pd.DataFrame, params: Params = FIVETHIRTYEIGHT) -> pd.DataFrame:
    """Pregame Elo for every row of ``games``, which needs ``game_id``,
    ``season``, ``kickoff``, ``home_team_id``, ``away_team_id``,
    ``actual_margin`` and ``neutral_site``. Unplayed games get the ratings as
    they stand and update nothing."""
    g = games.sort_values(["kickoff", "game_id"])
    rating: dict = {}
    last_season = None
    home_out, away_out = np.empty(len(g)), np.empty(len(g))
    neutral = pd.to_numeric(g.get("neutral_site", pd.Series(0, index=g.index)), errors="coerce").fillna(0).to_numpy()
    margins = pd.to_numeric(g["actual_margin"], errors="coerce").to_numpy()
    for i, (season, h, a) in enumerate(zip(g["season"], g["home_team_id"], g["away_team_id"], strict=True)):
        if season != last_season:
            for t in list(rating):
                rating[t] = rating[t] + params.revert * (params.mean - rating[t])
            last_season = season
        rh, ra = rating.get(h, params.mean), rating.get(a, params.mean)
        home_out[i], away_out[i] = rh, ra
        m = margins[i]
        if np.isnan(m):
            continue
        diff = rh - ra + (0.0 if neutral[i] else params.home_field)
        exp = _expected(diff)
        actual = 1.0 if m > 0 else 0.0 if m < 0 else 0.5
        shift = params.k * _mov_multiplier(m, diff) * (actual - exp) if m != 0 else params.k * (actual - exp)
        rating[h], rating[a] = rh + shift, ra - shift
    out = pd.DataFrame({"game_id": g["game_id"].to_numpy(), "home_elo": home_out, "away_elo": away_out}, index=g.index)
    out["elo_diff"] = (out["home_elo"] - out["away_elo"]) * params.points_per_elo
    return out.reindex(games.index)


def attach(games: pd.DataFrame, params: Params = FIVETHIRTYEIGHT) -> pd.DataFrame:
    """``games`` with ``home_pregame_elo``, ``away_pregame_elo`` and ``elo_diff`` added."""
    e = pregame(games, params)
    out = games.copy()
    out["home_pregame_elo"], out["away_pregame_elo"], out["elo_diff"] = e["home_elo"], e["away_elo"], e["elo_diff"]
    return out
