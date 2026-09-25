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
              "home_qb1_id", "home_qb2_id", "home_qb_id", "home_injured_out", "home_qb1_out", "home_qb2_out",
              "closing_spread", "actual_margin"):
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
    f = fits[SEASONS[1]]
    assert f.over_shrink is None or (0.0 <= f.over_shrink <= 1.0 and f.over_sigma > 0)
    tot = scored[scored["model"] == "total"].dropna(subset=["p_over"])
    assert tot["p_over"].between(0, 1).all() and "p_over_alone" in tot
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
    assert (out["top_home"] < 80).all()
    assert out["home_qb"].notna().all() and out["home_qb_pts"].notna().all() and (out["home_qb_sd"] > 0).all()
    # The state stops at the last game played: carried through the unplayed
    # schedule it would hold every remaining week's noise before project()
    # added it again.
    played = frame[frame["actual_margin"].notna() & (frame["season"] == projector.season)]
    if len(played):
        assert projector.state.week == int(played["week"].max())


def test_the_expected_starter_is_the_qb2_when_the_report_lists_the_qb1_out():
    """v1.1: the forecast follows the injury report, the update follows who played."""
    from atlas.models import kalman
    from atlas.models import nfl_state as ns

    spec = ns._spec(0.0, 9.0, 22.0, 2.0)
    state = kalman.initialise(np.array([1, 2]), np.zeros(2), np.zeros(2),
                              kalman.Spec(**{**spec.__dict__, "p0_off": 4.0, "p0_def": 4.0}))
    for incumbent in ("qb-a", "qb-b"):
        state.add(("qb", incumbent), 0.0, 9.0)
    kick = pd.Timestamp("2024-09-08", tz="UTC")

    def game(week, qb1, qb2, out, played):
        return {"game_id": f"g{week}", "season": 2024, "week": week, "kickoff": kick + pd.Timedelta(days=7 * week),
                "home_team_id": 1, "away_team_id": 2, "home_qb1_id": qb1, "home_qb2_id": qb2, "home_qb1_out": out,
                "home_qb_id": played, "away_qb1_id": "qb-b", "away_qb2_id": pd.NA, "away_qb1_out": 0.0,
                "away_qb_id": "qb-b", "actual_margin": 3.0, "actual_total": 44.0, "neutral_site": 0}

    games = pd.DataFrame([game(1, "qb-a", "qb-c", 0.0, "qb-a"), game(2, "qb-a", "qb-c", 1.0, "qb-c"),
                          game(3, "qb-a", "qb-c", 0.0, "qb-a")])
    fc = ns.run_season_qb(games, state, spec, p0=9.0, new_mean=-4.0, first_season=False, starters={})
    assert fc.loc[1, "mean"] < fc.loc[0, "mean"] - 2.0        # the report said the QB1 was out: the QB2 was expected
    assert fc.loc[2, "mean"] > fc.loc[1, "mean"]               # back to the QB1


def test_a_passer_record_is_strictly_before_kickoff():
    from atlas.models import nfl_state as ns

    log = pd.DataFrame({
        "passer_id": ["x", "x", "y"], "game_date": ["2023-09-10", "2023-09-17", "2023-09-10"],
        "dropbacks": [30, 30, 30], "qb_epa_per_dropback": [0.4, 0.2, -0.2],
    })
    rec = ns.PasserRecord(log)
    assert rec.league == pytest.approx((0.4 + 0.2 - 0.2) / 3)
    n, epa = rec.before("x", pd.Timestamp("2023-09-17", tz="UTC"))
    # The 17 September game is not yet played; the league is what it was before it.
    assert n == 30 and epa == pytest.approx(0.4 - (0.4 - 0.2) / 2)
    n, epa = rec.before("x", pd.Timestamp("2023-09-24", tz="UTC"))
    assert n == 60 and epa == pytest.approx(0.3 - rec.league)
    assert rec.before("x", pd.Timestamp("2023-09-10", tz="UTC")) == (0.0, 0.0)
    assert rec.before("nobody", pd.Timestamp("2024-01-01", tz="UTC")) == (0.0, 0.0)


def test_a_night_game_is_not_its_own_history():
    """Kickoffs are UTC and the passer log is dated in Eastern time: a Sunday
    night kickoff is Monday in UTC, and must still not see its own line."""
    from atlas.models import nfl_state as ns

    log = pd.DataFrame({
        "passer_id": ["x", "x"], "game_date": ["2023-09-10", "2023-09-17"],
        "dropbacks": [30, 40], "qb_epa_per_dropback": [-0.1, 0.5],
    })
    rec = ns.PasserRecord(log)
    sunday_night = pd.Timestamp("2023-09-18T00:20:00Z")      # 8:20pm ET on the 17th
    n, _ = rec.before("x", sunday_night)
    assert n == 30


def test_the_league_level_is_only_what_had_been_played():
    """A walk-forward season must not be centred on seasons still to come."""
    from atlas.models import nfl_state as ns

    log = pd.DataFrame({
        "passer_id": ["x", "y"], "game_date": ["2015-09-13", "2024-09-08"],
        "dropbacks": [30, 30], "qb_epa_per_dropback": [0.0, 0.3],
    })
    rec = ns.PasserRecord(log)
    assert rec.league_at(pd.Timestamp("2016-01-01")) == pytest.approx(0.0)
    assert rec.league_at(pd.Timestamp("2025-01-01")) == pytest.approx(0.15)


def test_a_passer_record_knows_each_game_line():
    """v1.2: the record also answers for one passer in one game, and carries
    the per-dropback variance the observation noise scales from."""
    from atlas.models import nfl_state as ns

    log = pd.DataFrame({
        "passer_id": ["x", "x", "y"], "game_id": ["g1", "g2", "g1"], "passer_name": ["X", "X", "Y"],
        "game_date": ["2023-09-10", "2023-09-17", "2023-09-10"],
        "dropbacks": [30, 30, 30], "qb_epa_per_dropback": [0.4, 0.2, -0.2],
    })
    rec = ns.PasserRecord(log)
    n, epa = rec.game("x", "g1")
    assert n == 30 and epa == pytest.approx(0.4 - (0.4 - 0.2) / 2)    # the league through that Sunday
    assert rec.game("x", "g9") == (0.0, 0.0) and rec.game("nobody", "g1") == (0.0, 0.0)
    assert rec.play_var > 0 and rec.names == {"x": "X", "y": "Y"}
    assert ns.PasserRecord(log.drop(columns=["game_id"])).by_game == {}


def test_the_epa_channel_separates_the_quarterback_from_the_offence():
    """v1.2: two sides score the same points all season, but the home passer's
    EPA per dropback is high and the away passer's low. Without the channel
    the quarterback states cannot tell; with it, they can."""
    from atlas.models import kalman
    from atlas.models import nfl_state as ns

    kick = pd.Timestamp("2024-09-08", tz="UTC")
    games = pd.DataFrame([{"game_id": f"g{w}", "season": 2024, "week": w, "kickoff": kick + pd.Timedelta(days=7 * w),
                           "home_team_id": 1, "away_team_id": 2, "home_qb1_id": "qb-a", "home_qb_id": "qb-a",
                           "away_qb1_id": "qb-b", "away_qb_id": "qb-b", "actual_margin": 0.0, "actual_total": 44.0,
                           "neutral_site": 1} for w in range(1, 7)])
    log = pd.DataFrame({"passer_id": ["qb-a", "qb-b"] * 6, "game_id": [f"g{w}" for w in range(1, 7) for _ in (0, 1)],
                        "game_date": [str((kick + pd.Timedelta(days=7 * w)).date()) for w in range(1, 7) for _ in (0, 1)],
                        "dropbacks": [35] * 12, "qb_epa_per_dropback": [0.3, -0.3] * 6})
    rec = ns.PasserRecord(log)

    def run(k_obs):
        spec = ns._spec(0.0, 9.0, 22.0, 2.0)
        state = kalman.initialise(np.array([1, 2]), np.zeros(2), np.zeros(2),
                                  kalman.Spec(**{**spec.__dict__, "p0_off": 4.0, "p0_def": 4.0}))
        for qb in ("qb-a", "qb-b"):
            state.add(("qb", qb), 0.0, 9.0)
        ns.run_season_qb(games, state, spec, p0=9.0, new_mean=-2.0, first_season=False, starters={},
                         record=rec, k_obs=k_obs)
        return state

    off, on = run(0.0), run(20.0)
    assert abs(off.value(("qb", "qb-a")) - off.value(("qb", "qb-b"))) < 0.5   # points alone: nothing to tell
    assert on.value(("qb", "qb-a")) > 2.0 > -2.0 > on.value(("qb", "qb-b"))    # the channel tells
    # A quarterback the log does not carry is untouched by the channel.
    assert ns.quarterbacks(on, rec)["points"].iloc[0] == pytest.approx(on.value(("qb", "qb-a")))


def test_qb_choices_round_trip_with_the_observation_gain(tmp_path):
    from atlas.models import nfl_state as ns

    team = {2024: ns.Choice(0.5, 0.4, 10.0, 8.5, -1.0, (2021, 2022, 2023))}
    qb = {2024: {"p0": 9.0, "new_mean": -2.0, "loglik": -1.0, "seasons": [2021, 2022, 2023], "k_epa": 15.0,
                 "k_obs": 20.0}}
    ns.save_choices(team, qb, tmp_path / "c.json")
    loaded_team, loaded_qb = ns.load_choices(tmp_path / "c.json")
    assert loaded_team == team and loaded_qb[2024] == ns.QBChoice(9.0, -2.0, -1.0, (2021, 2022, 2023), 15.0, 20.0)


def test_quarterback_draft_reads_the_rosters(tmp_path):
    """v1.3: a pick for a drafted quarterback, an empty pick for an undrafted
    one, and nobody whose draft status the rosters never state."""
    from atlas.sources import nflverse
    from atlas.staging.nfl.build import PLAYER_COLUMNS, quarterback_draft

    nfl = tmp_path / "nfl"
    nfl.mkdir()
    pd.DataFrame({
        "gsis_id": ["a", "a", "b", "c", "d"], "position": ["QB", "QB", "QB", "QB", "WR"],
        "full_name": ["A", "A", "B", "C", "D"], "draft_number": [1.0, None, None, None, 5.0],
        "entry_year": [2020, 2020, 2021, None, 2020], "rookie_year": [2020, 2020, 2021, None, 2020],
    }).to_parquet(nflverse.rosters_path(tmp_path, 2021))
    out = quarterback_draft(tmp_path, [2020, 2021]).set_index("passer_id")
    assert list(out.reset_index().columns) == PLAYER_COLUMNS
    assert set(out.index) == {"a", "b"}                          # c: status unknown; d: not a quarterback
    assert out.loc["a", "draft_number"] == 1.0 and pd.isna(out.loc["b", "draft_number"])
    assert quarterback_draft(tmp_path / "none", [2021]).empty


def test_a_rookie_opens_on_his_draft_slot_and_it_fades_with_his_record():
    from atlas.models import kalman
    from atlas.models import nfl_state as ns

    assert ns.draft_score(1) == pytest.approx(np.log(64.0))
    assert ns.draft_score(64) == pytest.approx(0.0)
    assert ns.draft_score(None) == ns.draft_score(260) < 0

    players = pd.DataFrame({"passer_id": ["top", "late", "vet"], "name": ["T", "L", "V"],
                            "draft_number": [1.0, None, 1.0], "entry_year": [2024, 2024, 2015]})
    log = pd.DataFrame({"passer_id": ["vet"] * 20, "game_id": [f"v{i}" for i in range(20)],
                        "game_date": [str(d.date()) for d in pd.date_range("2015-09-10", periods=20, freq="7D")],
                        "dropbacks": [40] * 20, "qb_epa_per_dropback": [0.0] * 20})
    rec = ns.PasserRecord(log, players)
    assert rec.draft_of("top") > 0 > rec.draft_of("late") and rec.draft_of("nobody") == 0.0
    assert rec.names["top"] == "T"

    kick = pd.Timestamp("2024-09-08", tz="UTC")
    spec = ns._spec(0.0, 9.0, 22.0, 2.0)

    def opening(qb):
        state = kalman.initialise(np.array([1, 2]), np.zeros(2), np.zeros(2),
                                  kalman.Spec(**{**spec.__dict__, "p0_off": 4.0, "p0_def": 4.0}))
        state.add(("qb", "opp"), 0.0, 4.0)
        game = pd.DataFrame([{"game_id": "g1", "season": 2024, "week": 1, "kickoff": kick, "home_team_id": 1,
                              "away_team_id": 2, "home_qb1_id": qb, "home_qb_id": qb, "away_qb1_id": "opp",
                              "away_qb_id": "opp", "actual_margin": np.nan, "actual_total": np.nan,
                              "neutral_site": 1}])
        ns.run_season_qb(game, state, spec, p0=4.0, new_mean=-2.0, starters={}, record=rec, k_draft=1.0)
        return state.value(("qb", qb))

    assert opening("top") > -2.0 > opening("late")               # the slot speaks for a rookie
    assert opening("vet") == pytest.approx(-2.0, abs=0.5)         # 800 dropbacks: the slot has faded


def test_the_efficiency_channel_reads_an_offence_through_its_plays():
    """Two sides score the same points, but the home offence moves the ball far
    better per play. Off, the channel leaves the state as the points leave it;
    on, the home offence reads stronger, by more when the reading rests on more plays."""
    from atlas.models import kalman
    from atlas.models import nfl_state as ns

    kick = pd.Timestamp("2024-09-08", tz="UTC")
    games = pd.DataFrame([{"game_id": f"g{w}", "season": 2024, "week": w, "kickoff": kick + pd.Timedelta(days=7 * w),
                           "home_team_id": 1, "away_team_id": 2, "home_qb1_id": pd.NA, "home_qb_id": pd.NA,
                           "away_qb1_id": pd.NA, "away_qb_id": pd.NA, "actual_margin": 0.0, "actual_total": 44.0,
                           "neutral_site": 1} for w in range(1, 7)])

    def eff(plays):
        return ns.EfficiencyRecord(pd.DataFrame({
            "game_id": [f"g{w}" for w in range(1, 7) for _ in (0, 1)], "team_id": [1, 2] * 6,
            "epa": [0.2, -0.2] * 6, "plays": [plays] * 12, "play_var": 1.8}))

    def run(record, k_eff):
        spec = ns._spec(0.0, 9.0, 22.0, 2.0)
        state = kalman.initialise(np.array([1, 2]), np.zeros(2), np.zeros(2),
                                  kalman.Spec(**{**spec.__dict__, "p0_off": 4.0, "p0_def": 4.0}))
        fc = ns.run_season_qb(games, state, spec, p0=9.0, new_mean=0.0, first_season=False, starters={},
                              eff=record, k_eff=k_eff)
        return state, fc

    base, base_fc = run(None, 0.0)
    off, off_fc = run(eff(40), 0.0)
    assert np.allclose(off_fc["mean"], base_fc["mean"]) and np.allclose(off.x, base.x)     # off is off
    thin, _ = run(eff(12), 30.0)
    thick, _ = run(eff(40), 30.0)
    gap = lambda s: s.x[0] - s.x[1]  # noqa: E731 - home offence over away offence
    assert gap(thick) > gap(thin) > gap(base) + 0.1
    assert ns.EfficiencyRecord(pd.DataFrame({"game_id": ["g"], "team_id": [1], "epa": [0.1], "plays": [5],
                                             "play_var": 1.0})).game("g", 1) == (5.0, 0.0)   # centred on the league


def test_a_bare_date_snapshot_is_not_known_before_that_days_kickoff():
    from atlas.staging.nfl.games import snapshot_time

    out = snapshot_time(pd.Series(["2025-09-07", "2025-09-05T12:00:00Z"]))
    assert out.iloc[0] == pd.Timestamp("2025-09-07T23:59:59Z")
    assert out.iloc[1] == pd.Timestamp("2025-09-05T12:00:00Z")
