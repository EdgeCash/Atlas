"""DFS step 5: the lineup optimizer against brute force, and its rules."""

from __future__ import annotations

import itertools

import numpy as np
import pandas as pd
import pytest

from atlas.dfs import optimizer as op

TEAMS = {"A": "B", "B": "A", "C": "D", "D": "C"}


def _pool(seed: int, counts=(("QB", 3), ("RB", 5), ("WR", 7), ("TE", 3), ("DST", 3))) -> pd.DataFrame:
    """A slate: quarterbacks and defenses one to a team, the rest anywhere."""
    rng = np.random.default_rng(seed)
    rows, i = [], 0
    for position, n in counts:
        for k in range(n):
            i += 1
            team = list(TEAMS)[k % len(TEAMS)] if position in ("QB", "DST") else rng.choice(list(TEAMS))
            rows.append({"id": 100 + i, "draftable_id": 5000 + i, "position": position, "team": team,
                         "opponent": TEAMS[team], "salary": int(rng.integers(25, 80)) * 100,
                         "projection": float(np.round(rng.uniform(2, 28), 2)),
                         "game_start": f"2026-09-27T{13 + int(rng.integers(0, 8)):02d}:00:00Z"})
    return pd.DataFrame(rows)


def _brute(pool: pd.DataFrame, opts: op.Options) -> float:
    """The best legal lineup's projection, by enumerating every roster shape.

    Written independently of the optimizer's program: plain loops over
    every combination, each rule checked directly."""
    pos = pool["position"].to_numpy()
    team = pool["team"].to_numpy()
    opp = pool["opponent"].to_numpy()
    sal = pool["salary"].to_numpy()
    proj = pool["projection"].to_numpy()
    by = {p: np.flatnonzero(pos == p) for p in op.SLOTS}
    best = -np.inf
    for rb, wr, te in ((2, 4, 1), (3, 3, 1), (2, 3, 2)):
        for q, d in itertools.product(by["QB"], by["DST"]):
            for r in itertools.combinations(by["RB"], rb):
                for w in itertools.combinations(by["WR"], wr):
                    for t in itertools.combinations(by["TE"], te):
                        idx = np.array([q, d, *r, *w, *t])
                        if sal[idx].sum() > opts.cap:
                            continue
                        total = proj[idx].sum()
                        if total <= best:
                            continue
                        offense = idx[pos[idx] != "DST"]
                        if opts.no_defense_vs_offense and (team[offense] == opp[d]).any():
                            continue
                        if max(np.unique(team[idx], return_counts=True)[1]) > opts.max_per_team:
                            continue
                        catchers = idx[np.isin(pos[idx], ("WR", "TE"))]
                        if (team[catchers] == team[q]).sum() < opts.qb_stack:
                            continue
                        if opts.bring_back and not (team[offense[pos[offense] != "QB"]] == opp[q]).any():
                            continue
                        if len({frozenset((team[i], opp[i])) for i in idx}) < 2:     # DraftKings: two games
                            continue
                        best = total
    return best


@pytest.mark.parametrize("seed", range(6))
@pytest.mark.parametrize("opts", [op.Options(no_defense_vs_offense=False),
                                  op.Options(qb_stack=1, cap=44_000),
                                  op.Options(qb_stack=1, bring_back=True, max_per_team=4)],
                         ids=["plain", "stack-tight-cap", "stack-bring-back-team-cap"])
def test_optimizer_matches_brute_force(seed, opts):
    pool = _pool(seed)
    best = _brute(pool, opts)
    assert best > -np.inf                                               # every case here has a legal lineup
    lineup = op.optimize(pool, opts)[0]
    assert op.valid(lineup, opts) == []
    assert lineup["projection"].sum() == pytest.approx(best, abs=1e-6)


def test_classic_never_takes_all_nine_from_one_game():
    rows = []
    for pos, n in (("QB", 1), ("RB", 3), ("WR", 4), ("TE", 2), ("DST", 1)):
        for k in range(n):
            for team, opp, proj in (("A", "B", 30.0), ("C", "D", 1.0)):     # one game far better than the other
                side = team if k % 2 == 0 or pos in ("QB", "DST") else opp
                rows.append({"id": f"{side}{pos}{k}", "position": pos, "team": side,
                             "opponent": "B" if side == "A" else "A" if side == "B" else "D" if side == "C" else "C",
                             "salary": 4000, "projection": proj})
    pool = pd.DataFrame(rows).drop_duplicates("id")
    lineup = op.optimize(pool, op.Options(no_defense_vs_offense=False))[0]
    assert op.valid(lineup, op.Options(no_defense_vs_offense=False)) == []
    assert (lineup["team"].isin(["C", "D"])).sum() >= 1


def _showdown_pool(seed: int, n: int = 12) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n):
        team = "A" if i % 3 else "B"
        flex = int(rng.integers(20, 120)) * 100
        rows.append({"id": 100 + i, "draftable_id": 5000 + i, "cpt_draftable_id": 6000 + i,
                     "position": ["QB", "RB", "WR", "TE", "K", "DST"][i % 6], "team": team,
                     "opponent": "B" if team == "A" else "A", "salary": flex, "cpt_salary": int(flex * 1.5),
                     "projection": float(np.round(rng.uniform(1, 30), 2))})
    return pd.DataFrame(rows)


def _showdown_brute(pool: pd.DataFrame, cap: int = op.SALARY_CAP) -> float:
    best = -np.inf
    rows = pool.to_dict(orient="records")
    for c in rows:
        others = [r for r in rows if r["id"] != c["id"]]
        for flex in itertools.combinations(others, 5):
            if c["cpt_salary"] + sum(r["salary"] for r in flex) > cap:
                continue
            if len({c["team"], *(r["team"] for r in flex)}) < 2:
                continue
            best = max(best, 1.5 * c["projection"] + sum(r["projection"] for r in flex))
    return best


@pytest.mark.parametrize("seed", range(5))
def test_showdown_matches_brute_force(seed):
    pool = _showdown_pool(seed)
    lineup = op.showdown(pool)[0]
    assert op.valid_showdown(lineup) == []
    assert lineup["projection"].sum() == pytest.approx(_showdown_brute(pool), abs=1e-6)
    captain = lineup.iloc[0]
    source = pool.set_index("id").loc[captain["id"]]
    assert captain["salary"] == source["cpt_salary"] and captain["draftable_id"] == source["cpt_draftable_id"]
    assert captain["projection"] == pytest.approx(1.5 * source["projection"])


def test_showdown_takes_both_teams_even_when_one_is_better():
    pool = _showdown_pool(1).assign(salary=2000, cpt_salary=3000)
    pool.loc[pool["team"] == "B", "projection"] = 0.1
    lineup = op.showdown(pool)[0]
    assert lineup["team"].nunique() == 2
    several = op.showdown(pool, op.Options(n=3, min_unique=2))
    assert len(several) == 3 and all(op.valid_showdown(lu) == [] for lu in several)
    assert len(set(several[0]["id"]) - set(several[1]["id"])) >= 2
    text = op.upload(several, "Showdown").splitlines()
    assert text[0] == "CPT,FLEX,FLEX,FLEX,FLEX,FLEX" and int(text[1].split(",")[0]) >= 6000


def test_tiers_takes_the_best_of_each_tier_across_two_games():
    rows = []
    for t in range(1, 7):
        for k, (team, opp) in enumerate((("A", "B"), ("C", "D"), ("A", "B"))):
            rows.append({"id": f"t{t}p{k}", "draftable_id": 10 * t + k, "position": "WR", "team": team,
                         "opponent": opp, "tier": t, "projection": 20.0 - k if team == "A" else 5.0})
    pool = pd.DataFrame(rows)
    lineup = op.tiers(pool)[0]
    assert op.valid_tiers(lineup) == []
    brute = max(sum(combo_p for combo_p, _ in combo) for combo in itertools.product(
        *[[(r["projection"], r["team"]) for r in rows if r["tier"] == t] for t in range(1, 7)])
        if len({tm for _, tm in combo}) >= 2)
    assert lineup["projection"].sum() == pytest.approx(brute)
    assert op.upload([lineup], "Tiers").startswith("T1,T2,T3,T4,T5,T6\n")


def test_several_lineups_differ_and_respect_exposure():
    pool = _pool(7, counts=(("QB", 4), ("RB", 12), ("WR", 16), ("TE", 8), ("DST", 4)))
    opts = op.Options(n=6, min_unique=3, max_exposure=0.5)
    lineups = op.optimize(pool, opts)
    assert len(lineups) == 6
    sets = [set(lu["id"]) for lu in lineups]
    for a, b in itertools.combinations(sets, 2):
        assert len(a - b) >= 3
    counts = pd.Series([pid for s in sets for pid in s]).value_counts()
    assert counts.max() <= 3                                           # half of six
    totals = [lu["projection"].sum() for lu in lineups]
    assert totals == sorted(totals, reverse=True)                       # best first
    for lu in lineups:
        assert op.valid(lu, opts) == []


def test_locks_excludes_and_the_flex_goes_late():
    pool = _pool(3, counts=(("QB", 4), ("RB", 8), ("WR", 12), ("TE", 5), ("DST", 4)))
    top = op.optimize(pool)[0]
    banned = top["id"].iloc[0]
    locked = pool[(pool["position"] == "WR") & ~pool["id"].isin(top["id"])]["id"].iloc[0]
    lineup = op.optimize(pool, op.Options(locks=[locked], excludes=[banned]))[0]
    assert locked in set(lineup["id"]) and banned not in set(lineup["id"])
    assert list(lineup["slot"]) == op.UPLOAD_SLOTS
    flex = lineup[lineup["slot"] == "FLEX"].iloc[0]
    same = lineup[(lineup["position"] == flex["position"]) & (lineup["slot"] != "FLEX")]
    assert (same["game_start"] <= flex["game_start"]).all()


def test_an_impossible_request_says_so():
    pool = _pool(4)
    with pytest.raises(op.Infeasible):
        op.optimize(pool, op.Options(cap=10_000))
    lock = pool["id"].iloc[0]
    with pytest.raises(op.Infeasible):
        op.optimize(pool, op.Options(locks=[lock], excludes=[lock]))


def test_upload_file_is_draftkings_header_then_ids():
    lineups = op.optimize(_pool(5), op.Options(n=2))
    text = op.upload_csv(lineups)
    lines = text.strip().split("\n")
    assert lines[0] == "QB,RB,RB,WR,WR,WR,TE,FLEX,DST" and len(lines) == 3
    assert [int(x) for x in lines[1].split(",")] == list(lineups[0]["draftable_id"])


# ---------------------------------------------------------------------------
# The live slate: games, names, ranges with a chance of not playing
# ---------------------------------------------------------------------------


def test_slate_players_find_their_game_and_opponent():
    from atlas.dfs import slate

    pool = pd.DataFrame([
        {"name": "Puka Nacua", "team": "LAR", "game": "LAR @ DEN", "game_start": "2026-09-28T00:20:00.0000000Z"},
        {"name": "Broncos", "team": "DEN", "game": "LAR @ DEN", "game_start": "2026-09-28T00:20:00.0000000Z"},
    ])
    schedule = pd.DataFrame([{"game_id": "2026_03_LA_DEN", "season": 2026, "week": 3, "gameday": "2026-09-27",
                              "home_team": "DEN", "away_team": "LA", "game_type": "REG"}])
    got = slate.with_games(pool, schedule)
    assert list(got["team"]) == ["LA", "DEN"] and list(got["opponent"]) == ["DEN", "LA"]
    assert list(got["week"]) == [3, 3]                     # a Sunday night kickoff is Sunday in Eastern time


def test_slate_matches_names_by_team_then_position_then_the_player_list():
    from atlas.dfs import slate

    games = pd.DataFrame([
        {"season": 2026, "week": 2, "player_id": "g1", "name": "D.J. Moore", "team": "BUF", "position": "WR"},
        {"season": 2025, "week": 18, "player_id": "g2", "name": "Travis Kelce", "team": "KC", "position": "TE"},
        {"season": 2026, "week": 2, "player_id": "g3", "name": "Josh Allen", "team": "BUF", "position": "QB"},
        {"season": 2026, "week": 2, "player_id": "g4", "name": "Josh Allen", "team": "JAX", "position": "LB"},
    ])
    master = pd.DataFrame([{"gsis_id": "g9", "display_name": "Jeremiyah Love", "latest_team": "ARI",
                            "position": "RB"}])
    pool = pd.DataFrame([
        {"name": "DJ Moore", "team": "BUF", "position": "WR", "player_id_dk": 1},
        {"name": "Travis Kelce", "team": "NYJ", "position": "TE", "player_id_dk": 2},     # moved teams
        {"name": "Josh Allen", "team": "BUF", "position": "QB", "player_id_dk": 3},
        {"name": "Jeremiyah Love", "team": "ARI", "position": "RB", "player_id_dk": 4},   # a rookie
        {"name": "Nobody Known", "team": "ARI", "position": "WR", "player_id_dk": 5},
        {"name": "Bills", "team": "BUF", "position": "DST", "player_id_dk": 6},
    ])
    got = slate.match(pool, games, master).set_index("player_id_dk")
    assert got.loc[1, "player_id"] == "g1" and got.loc[1, "matched_by"] == "name and team"
    assert got.loc[2, "player_id"] == "g2" and got.loc[2, "matched_by"] == "name and position"
    assert got.loc[3, "player_id"] == "g3"
    assert got.loc[4, "player_id"] == "g9" and got.loc[4, "matched_by"].startswith("player list")
    assert got.loc[5, "player_id"] == "DK-5" and got.loc[6, "player_id"] == "DST-BUF"


def test_a_chance_of_not_playing_widens_the_range_downward():
    from atlas.dfs import slate

    p = np.array([1.0, 0.95, 0.5, 0.05])
    mid, lo, hi = np.full(4, 12.0), np.full(4, 3.0), np.full(4, 25.0)
    low = slate.mixture_quantile(p, mid, lo, hi, 0.10)
    high = slate.mixture_quantile(p, mid, lo, hi, 0.90)
    assert low[0] == pytest.approx(3.0) and high[0] == pytest.approx(25.0)      # certain to play: his own range
    assert low[2] == 0 and low[3] == 0 and high[3] == 0                         # likely out: the floor is zero
    assert 0 < low[1] < 3.0 and 12.0 < high[2] < 25.0


def test_the_next_slate_with_the_label_is_chosen():
    from datetime import datetime, timezone

    from atlas.dfs import slate

    slates = pd.DataFrame([
        {"draft_group_id": 1, "label": "Main", "starts_at": "2026-09-20T17:00:00+00:00"},
        {"draft_group_id": 2, "label": "Main", "starts_at": "2026-09-27T17:00:00+00:00"},
        {"draft_group_id": 3, "label": "Thu-Mon", "starts_at": "2026-09-25T00:15:00+00:00"},
    ])
    assert slate.choose_slate(slates, "Main", datetime(2026, 9, 24, tzinfo=timezone.utc))["draft_group_id"] == 2
    with pytest.raises(LookupError):
        slate.choose_slate(slates, "Main", datetime(2026, 10, 5, tzinfo=timezone.utc))


def test_play_history_uses_only_earlier_games():
    from atlas.dfs import participation

    games = pd.DataFrame([
        {"season": 2025, "week": w, "season_type": "REG", "player_id": "p", "snap_pct": 0.8} for w in (1, 2, 3)
    ])
    rows = pd.DataFrame([{"season": 2025, "week": 3, "player_id": "p"}, {"season": 2025, "week": 6, "player_id": "p"},
                         {"season": 2025, "week": 1, "player_id": "q"}])
    h = participation.history(games, rows)
    assert list(h["games_before"]) == [2, 3, 0]
    assert list(h["weeks_since"]) == [1, 3, 99]
    assert h["snap_after"].iloc[0] == pytest.approx(0.8) and np.isnan(h["snap_after"].iloc[2])


# ---------------------------------------------------------------------------
# College: Classic with the SUPERFLEX, Showdown with UTIL
# ---------------------------------------------------------------------------

CFB = op.Options(roster=op.CFB_CLASSIC, no_defense_vs_offense=False)


def _cfb_pool(seed: int, counts=(("QB", 4), ("RB", 5), ("WR", 7))) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows, i = [], 0
    for position, n in counts:
        for k in range(n):
            i += 1
            team = list(TEAMS)[k % len(TEAMS)] if position == "QB" else rng.choice(list(TEAMS))
            rows.append({"id": 200 + i, "draftable_id": 7000 + i, "position": position, "team": team,
                         "opponent": TEAMS[team], "salary": int(rng.integers(30, 90)) * 100,
                         "projection": float(np.round(rng.uniform(2, 30), 2)),
                         "game_start": f"2026-09-26T{12 + int(rng.integers(0, 10)):02d}:00:00Z"})
    return pd.DataFrame(rows)


def _cfb_brute(pool: pd.DataFrame, cap: int = op.SALARY_CAP) -> float:
    """Every eight-player set with a legal shape: 1-2 QB, 2-4 RB, 3-5 WR, two games."""
    best = -np.inf
    rows = pool.to_dict(orient="records")
    for combo in itertools.combinations(range(len(rows)), 8):
        picked = [rows[i] for i in combo]
        if sum(r["salary"] for r in picked) > cap:
            continue
        n = {p: sum(r["position"] == p for r in picked) for p in ("QB", "RB", "WR")}
        if not (1 <= n["QB"] <= 2 and 2 <= n["RB"] <= 4 and 3 <= n["WR"] <= 5):
            continue
        if len({frozenset((r["team"], r["opponent"])) for r in picked}) < 2:
            continue
        best = max(best, sum(r["projection"] for r in picked))
    return best


@pytest.mark.parametrize("seed", range(4))
def test_college_classic_matches_brute_force(seed):
    pool = _cfb_pool(seed)
    best = _cfb_brute(pool)
    assert best > -np.inf
    lineup = op.optimize(pool, CFB)[0]
    assert op.valid(lineup, CFB) == []
    assert list(lineup["slot"]) == ["QB", "RB", "RB", "WR", "WR", "WR", "FLEX", "S-FLEX"]
    assert lineup["projection"].sum() == pytest.approx(best, abs=1e-6)


def test_college_superflex_takes_a_second_quarterback_when_it_is_best():
    pool = _cfb_pool(2).assign(salary=4000)
    pool.loc[pool["position"] == "QB", "projection"] = 40.0                   # quarterbacks far ahead
    lineup = op.optimize(pool, CFB)[0]
    assert (lineup["position"] == "QB").sum() == 2
    assert lineup.loc[lineup["slot"] == "S-FLEX", "position"].item() == "QB"
    assert lineup.loc[lineup["slot"] == "FLEX", "position"].item() in ("RB", "WR")
    assert op.upload([lineup], "Classic", "cfb").startswith("QB,RB,RB,WR,WR,WR,FLEX,S-FLEX\n")


def test_college_showdown_uses_util_slots():
    pool = _showdown_pool(3)
    pool.loc[pool["position"].isin(["TE", "DST"]), "position"] = "WR"
    lineup = op.showdown(pool, flex_label="UTIL")[0]
    assert op.valid_showdown(lineup, flex_label="UTIL") == []
    assert list(lineup["slot"]) == ["CPT"] + ["UTIL"] * 5
    assert op.upload([lineup], "Showdown", "cfb").startswith("CPT,UTIL,UTIL,UTIL,UTIL,UTIL\n")
