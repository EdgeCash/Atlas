"""NFL plan step 1: the staging's conventions, on a synthetic nflverse tree."""

from __future__ import annotations

import os

import numpy as np
import pandas as pd
import pytest

from atlas.staging.nfl import build as nfl_build
from atlas.staging.nfl import efficiency as nfl_eff
from atlas.staging.nfl import games as nfl_games
from atlas.testing.synthetic_nfl import CODES, WEEKS, write_synthetic_nfl_raw

SEASONS = [2023, 2024]


@pytest.fixture(scope="module")
def nfl_tree(tmp_path_factory):
    base = tmp_path_factory.mktemp("nfl_data")
    write_synthetic_nfl_raw(base / "raw", SEASONS)
    return base


@pytest.fixture(scope="module")
def nfl_frame(nfl_tree, request):
    """The research frame from a full build into a temporary data dir."""
    old = os.environ.get("ATLAS_DATA_DIR")
    os.environ["ATLAS_DATA_DIR"] = str(nfl_tree)
    os.environ["ATLAS_OFFLINE"] = "1"
    try:
        frame = nfl_build.build(SEASONS)
    finally:
        if old is None:
            os.environ.pop("ATLAS_DATA_DIR", None)
        else:
            os.environ["ATLAS_DATA_DIR"] = old
    return frame


def test_games_follow_atlas_conventions(nfl_tree):
    from atlas.sources import nflverse

    games = nfl_games.normalise(nflverse.load_schedules(nfl_tree / "raw", SEASONS))
    assert set(games["season_type"]) == {"regular", "postseason"}
    assert (games[games["game_type"] == "WC"]["season_type"] == "postseason").all()
    # nflverse's spread_line is positive when the home side is favoured; Atlas's
    # closing_spread is the book's home line, negative then.
    row = games.iloc[0]
    sched = nflverse.load_schedules(nfl_tree / "raw", SEASONS).set_index("game_id").loc[row["game_id"]]
    assert row["closing_spread"] == -sched["spread_line"]
    assert games["kickoff"].dt.tz is not None and str(games["kickoff"].dt.tz) == "UTC"
    assert games["neutral_site"].sum() == len(SEASONS)                # one neutral game a season
    assert games["venue_dome"].sum() > 0 and games["completed"].sum() == len(games) - len(CODES) // 2
    assert (games["actual_margin"] == games["home_score"] - games["away_score"]).where(games["completed"] == 1, True).all()


def test_a_relocated_franchise_keeps_its_id(nfl_tree):
    from atlas.sources import nflverse

    games = nfl_games.normalise(nflverse.load_schedules(nfl_tree / "raw", SEASONS))
    raiders = games[(games["home_team"] == "LV") | (games["away_team"] == "LV")]
    assert set(raiders["season"]) == set(SEASONS)                     # "OAK" in 2023 became "LV"
    ids = set(raiders.loc[raiders["home_team"] == "LV", "home_team_id"]) | set(raiders.loc[raiders["away_team"] == "LV", "away_team_id"])
    assert ids == {nfl_games.TEAM_ID["LV"]}
    assert len(nfl_games.TEAM_ID) == 32 and len(set(nfl_games.TEAM_ID.values())) == 32


def test_efficiency_excludes_garbage_time_and_names_the_quarterback_of_record(nfl_tree):
    pbp = pd.read_parquet(nfl_tree / "raw" / "nfl" / "pbp_2023.parquet")
    eff = nfl_eff.season_efficiency(pbp, 2023)
    one = eff.iloc[0]
    game = pbp[(pbp["game_id"] == one["game_id"]) & (nfl_games.team_id(pbp["posteam"]) == one["team_id"])]
    clean = game[~((game["qtr"] == 4) & (game["score_differential"].abs() > 16))]
    assert one["off_plays"] == len(clean) and len(clean) < len(game)   # the fifth drive was garbage time
    assert abs(one["off_epa"] - clean["epa"].mean()) < 1e-9
    assert one["qb_id"] == f"qb-{nfl_games.TEAMS[int(one['team_id']) - 1]}"   # most dropbacks, not the mop-up passer
    assert one["drives"] == 5 and 0 <= one["td_rate"] <= 1
    assert abs(one["points_for"] + one["points_against"] - (game["home_score"].iloc[0] + game["away_score"].iloc[0])) < 1e-9
    assert 5 <= one["pace"] <= 90


def test_the_research_frame_is_point_in_time(nfl_frame):
    f = nfl_frame
    for c in ("home_adj_off_epa", "away_adj_def_epa", "adj_net_epa_diff", "home_off_epa_pit", "home_n_prior_games",
              "home_qb1_id", "home_qb_id", "home_injured_out", "home_qb1_out", "closing_spread", "actual_margin"):
        assert c in f.columns, c
    week1 = f[f["week"] == 1]
    assert (week1["home_n_prior_games"] == 0).all()                    # nothing from this season yet
    first = f[f["season"] == SEASONS[0]]
    assert first[first["week"] == 1]["home_adj_off_epa"].isna().all()       # nothing to rate on yet, so no rating
    assert first[first["week"] == 3]["home_adj_off_epa"].notna().all()      # two weeks of this season's games
    later = f[(f["season"] == SEASONS[1]) & (f["week"] == WEEKS - 1)]
    assert later["home_adj_off_epa"].notna().all() and later["home_adj_off_epa"].abs().max() > 0
    scheduled = f[f["completed"] == 0]
    assert len(scheduled) == len(CODES) // 2 and scheduled["home_adj_off_epa"].notna().all()
    assert (f["home_qb1_id"] == f["home_qb_id"]).all()                  # the synthetic QB1 always started
    assert f.loc[f["week"] == 4, "home_qb1_out"].max() == 1.0


def test_the_loader_reads_the_warehouse(nfl_frame, nfl_tree):
    from atlas.research.nfl_dataset import load_nfl_frame, research_sample

    frame = load_nfl_frame(nfl_tree / "warehouse")
    assert len(frame) == len(nfl_frame)
    assert (frame["market_margin"] == -frame["closing_spread"]).all()
    sample = research_sample(frame)
    assert len(sample) == int(nfl_frame["completed"].sum())
    assert np.isfinite(sample["actual_margin"]).all()


def test_snapshot_depth_charts_map_to_the_week_before_kickoff():
    """From 2025 nflverse publishes daily depth-chart snapshots with no week;
    the QB1 for a game is the latest snapshot before its kickoff."""
    games = pd.DataFrame({
        "game_id": ["2025_01_KC_BUF", "2025_02_BUF_KC"], "season": [2025, 2025], "week": [1, 2],
        "season_type": ["regular"] * 2,
        "kickoff": pd.to_datetime(["2025-09-07 17:00", "2025-09-14 17:00"], utc=True),
        "home_team_id": [nfl_games.TEAM_ID["BUF"], nfl_games.TEAM_ID["KC"]],
        "away_team_id": [nfl_games.TEAM_ID["KC"], nfl_games.TEAM_ID["BUF"]],
    })
    snaps = pd.DataFrame({
        "dt": ["2025-09-05T12:00:00Z", "2025-09-12T12:00:00Z", "2025-09-05T12:00:00Z", "2025-09-08T12:00:00Z"],
        "team": ["BUF", "BUF", "KC", "KC"], "player_name": ["Josh Allen", "Mitch Trubisky", "Patrick Mahomes", "Backup"],
        "gsis_id": ["allen", "trubisky", "mahomes", "backup"], "pos_abb": ["QB"] * 4, "pos_rank": [1, 1, 1, 1],
    })
    out = nfl_build._snapshot_qb1(snaps, games).set_index(["week", "team_id"])["qb1_id"]
    assert out[(1, nfl_games.TEAM_ID["BUF"])] == "allen"
    assert out[(2, nfl_games.TEAM_ID["BUF"])] == "trubisky"        # the change came before week 2
    assert out[(1, nfl_games.TEAM_ID["KC"])] == "mahomes" and out[(2, nfl_games.TEAM_ID["KC"])] == "backup"
