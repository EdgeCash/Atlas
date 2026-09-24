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


def test_nfl_benchmarks_score_the_synthetic_league(nfl_frame):
    """Step 2's harness runs on the NFL frame: naive, Elo, adjusted EPA and the market, walk-forward."""
    from atlas.models import nfl_benchmarks as nb
    from atlas.research.nfl_dataset import research_sample

    sample = research_sample(nfl_frame)
    scored = nb.score_frame(sample, first_test_season=SEASONS[1], min_train_seasons=1)
    assert set(scored["model"]) >= {"naive", "elo", "market"}
    assert scored["qb_change"].dropna().isin([0.0, 1.0]).all()
    assert np.isfinite(scored["crps"]).all()
    text = nb.render(scored)
    assert "## Regular season, every scored season pooled" in text and "quarterback" in text.lower()


# ---------------------------------------------------------------------------
# Step 3: the state, carried across seasons
# ---------------------------------------------------------------------------

SMALL_GRID = {"q": (0.0, 2.0), "phi": (0.67,), "p_season": (25.0,), "sigma": (9.5,)}


def test_a_new_season_regresses_the_state_toward_the_mean():
    from atlas.models import kalman
    from atlas.models import nfl_state as ns

    spec = ns._spec(1.0, 9.5, 22.0, 2.0)
    state = kalman.initialise(np.array([1, 2]), np.array([10.0, -4.0]), np.array([2.0, 0.0]), spec)
    state.P[:] = np.eye(4) * 4.0
    state.week = 18
    ns.new_season(state, phi=0.5, p_season=10.0)
    assert state.off(1) == 5.0 and state.off(2) == -2.0 and state.defense(1) == 1.0
    assert state.P[0, 0] == pytest.approx(4.0 * 0.25 + 10.0)
    assert state.week is None


def test_the_nfl_state_runs_walk_forward_and_beats_naive(nfl_frame):
    from atlas.models import nfl_state as ns
    from atlas.research.nfl_dataset import research_sample

    sample = research_sample(nfl_frame)
    scored, choices, finals, _ = ns.walk_forward(sample, first_test_season=SEASONS[1], grid=SMALL_GRID, min_train_seasons=1)
    assert set(choices) == {SEASONS[1]}
    pooled = ns.evaluate.summarise(scored[scored["season_type"] == "regular"], order=ns.ORDER).set_index("model")
    assert pooled.loc["state", "crps"] < pooled.loc["naive", "crps"]
    assert np.isfinite(scored[scored["model"] == "state"]["crps"]).all()
    final = finals[SEASONS[1]].frame()
    assert len(final) == 8 and final["net"].abs().max() > 0
    assert "## The quarterback test" in ns.render(scored, choices, finals, nfl_frame)


def test_a_switch_to_an_unseen_quarterback_lowers_the_forecast():
    """Two teams, one game a week. When the home side's expected starter is a
    quarterback the state has never seen, the forecast drops by the new-QB
    prior; when the incumbent is back, it recovers."""
    from atlas.models import kalman
    from atlas.models import nfl_state as ns

    spec = ns._spec(0.0, 9.0, 22.0, 2.0)
    state = kalman.initialise(np.array([1, 2]), np.zeros(2), np.zeros(2),
                              kalman.Spec(**{**spec.__dict__, "p0_off": 4.0, "p0_def": 4.0}))
    kick = pd.Timestamp("2024-09-08", tz="UTC")

    def game(week, home_qb1, home_qb, margin=3.0):
        return {"game_id": f"g{week}", "season": 2024, "week": week, "kickoff": kick + pd.Timedelta(days=7 * week),
                "home_team_id": 1, "away_team_id": 2, "home_qb1_id": home_qb1, "home_qb_id": home_qb,
                "away_qb1_id": "qb-b", "away_qb_id": "qb-b", "actual_margin": margin, "actual_total": 44.0,
                "neutral_site": 0}

    games = pd.DataFrame([game(1, "qb-a", "qb-a"), game(2, "qb-a", "qb-a"), game(3, "qb-new", "qb-new"),
                          game(4, "qb-a", "qb-a")])
    starters: dict = {}
    for incumbent in ("qb-a", "qb-b"):                           # seen in earlier seasons, so at zero
        state.add(("qb", incumbent), 0.0, 9.0)
    fc = ns.run_season_qb(games, state, spec, p0=9.0, new_mean=-4.0, first_season=False, starters=starters)
    assert fc.loc[2, "mean"] < fc.loc[1, "mean"] - 2.0          # the unseen starter costs most of the prior
    assert fc.loc[3, "mean"] > fc.loc[2, "mean"]                 # the incumbent's return gives it back
    assert ("qb", "qb-new") in state.extra and state.value(("qb", "qb-new")) > -4.0   # it learned from week 3
    assert starters[1] == "qb-a" and state.value(ns.HFA_KEY) > 0


def test_the_nfl_total_and_grid_run_walk_forward(nfl_frame):
    from atlas.models import nfl_state as ns
    from atlas.models import nfl_total as nt
    from atlas.research.nfl_dataset import research_sample

    sample = research_sample(nfl_frame)
    fixed = ({SEASONS[1]: ns.Choice(0.0, 0.67, 25.0, 9.5, 0.0, ())},
             {SEASONS[1]: ns.QBChoice(9.0, -2.0, 0.0, ())})
    frame = nt.prepare(sample)
    from atlas.models import reference as ref
    # one training season on the synthetic league
    monkey = ref.walk_forward
    ref.walk_forward = lambda f, first_test_season, **kw: monkey(f, first_test_season=first_test_season, min_train_seasons=1)
    try:
        scored, table, fits = nt.run(frame, first_test_season=SEASONS[1], choices=fixed)
    finally:
        ref.walk_forward = monkey
    assert set(scored["model"]) == {"naive", "state_raw", "total", "market"}
    assert (table["home_mean"] + table["away_mean"] - table["total_mean"]).abs().max() < 1e-6
    assert ((table["top_home"] < nt.MAX_POINTS) & (table["top_away"] < nt.MAX_POINTS)).all()
    assert fits[SEASONS[1]].points_factor.shape == (nt.MAX_POINTS,)
    assert "## The exact score" in nt.render(scored, table, fits)


def test_the_nfl_projector_projects_the_scheduled_slate(nfl_frame):
    """Step 6: one row per scheduled game keyed by ESPN's id, sport nfl, means
    that add up, and the state's view of each team for the drivers."""
    from atlas.models import nfl_projection as pj
    from atlas.models import nfl_state as ns

    frame = nfl_frame.copy()
    frame["espn_id"] = pd.Series(range(400000000, 400000000 + len(frame)), index=frame.index, dtype="Int64")
    fixed = ({SEASONS[1]: ns.Choice(0.0, 0.67, 25.0, 9.5, 0.0, ())},
             {SEASONS[1]: ns.QBChoice(9.0, -2.0, 0.0, ())})
    projector = pj.fit(frame, choices=fixed)
    scheduled = frame[frame["actual_margin"].isna() & (frame["season"] == projector.season)]
    out = pj.project(projector, scheduled)
    assert len(out) == len(scheduled) and (out["sport"] == "nfl").all()
    assert set(out["game_id"]) == set(scheduled["espn_id"].astype(int))
    assert (out["home_mean"] + out["away_mean"] - out["total_mean"]).abs().max() < 1e-6
    assert ((out["p_home"] > 0) & (out["p_home"] < 1)).all()
    assert out["home_rank"].between(1, 8).all() and out["teams"].iloc[0] == 8
    assert projector.quarterback("qb-KC") is not None
    assert (out["top_home"] < 60).all()
