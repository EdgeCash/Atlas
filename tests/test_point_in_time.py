"""The point-in-time guarantee is the whole product. Test it hard."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from atlas.features.point_in_time import add_point_in_time_features, to_matchup
from atlas.research.validation import recompute_pit_by_brute_force


def _frame(values_by_team: dict[int, list[float]], season: int = 2021) -> pd.DataFrame:
    rows = []
    for team, values in values_by_team.items():
        for i, value in enumerate(values):
            rows.append(
                {
                    "team_id": team,
                    "season": season,
                    "game_id": 1000 + i,
                    "kickoff": pd.Timestamp(f"{season}-09-01", tz="UTC") + pd.Timedelta(days=7 * i),
                    "metric": value,
                }
            )
    return pd.DataFrame(rows)


def test_first_game_has_no_in_season_history():
    df = _frame({1: [10.0, 20.0, 30.0]})
    out = add_point_in_time_features(df, ["metric"], shrinkage=0.0)
    assert np.isnan(out.loc[out["n_prior_games"] == 0, "metric_pit"].iloc[0])


def test_uses_strictly_prior_games_only():
    df = _frame({1: [10.0, 20.0, 30.0, 40.0]})
    out = add_point_in_time_features(df, ["metric"], shrinkage=0.0).sort_values("game_id")
    assert out["metric_pit"].tolist()[1:] == [10.0, 15.0, 20.0]


def test_changing_a_future_game_cannot_change_an_earlier_feature():
    base = _frame({1: [10.0, 20.0, 30.0, 40.0]})
    tampered = base.copy()
    tampered.loc[tampered["game_id"] == 1003, "metric"] = 999.0

    a = add_point_in_time_features(base, ["metric"], shrinkage=0.0).sort_values("game_id")
    b = add_point_in_time_features(tampered, ["metric"], shrinkage=0.0).sort_values("game_id")
    # Every row before the tampered game must be untouched.
    pd.testing.assert_series_equal(
        a[a["game_id"] < 1003]["metric_pit"],
        b[b["game_id"] < 1003]["metric_pit"],
        check_names=False,
    )


def test_shrinkage_uses_previous_season_not_current():
    rows = []
    for season, values in ((2020, [4.0, 4.0]), (2021, [100.0, 100.0])):
        rows.append(_frame({1: values}, season=season))
    df = pd.concat(rows, ignore_index=True)
    out = add_point_in_time_features(df, ["metric"], shrinkage=2.0)
    first_2021 = out[(out["season"] == 2021) & (out["n_prior_games"] == 0)].iloc[0]
    # No 2021 history yet, so the value must be exactly the 2020 mean.
    assert first_2021["metric_pit"] == pytest.approx(4.0)


def test_matches_brute_force_recomputation(synthetic_build):
    from atlas.staging import efficiency, games

    paths = synthetic_build["paths"]
    eff = efficiency.load(paths.staging)
    long = games.load_long(paths.staging)
    frame = long[["game_id", "team_id", "season", "kickoff"]].merge(
        eff[["game_id", "team_id", "off_epa"]], on=["game_id", "team_id"], how="left"
    )
    fast = add_point_in_time_features(frame, ["off_epa"])
    slow = recompute_pit_by_brute_force(frame, "off_epa", sample=300)
    joined = fast.loc[slow.index, ["off_epa_pit"]].join(slow)
    both = joined.dropna()
    assert len(both) > 100
    np.testing.assert_allclose(both["off_epa_pit"], both["brute_force"], rtol=1e-9, atol=1e-9)


def test_to_matchup_builds_symmetric_differences():
    tf = pd.DataFrame(
        {"game_id": [1, 1], "team_id": [10, 20], "x_pit": [3.0, 1.0]}
    )
    games_df = pd.DataFrame({"game_id": [1], "home_team_id": [10], "away_team_id": [20]})
    out = to_matchup(tf, games_df, ["x_pit"])
    assert out.loc[0, "x_pit_diff"] == 2.0
