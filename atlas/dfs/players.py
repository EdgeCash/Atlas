"""The DFS player-game table: every offensive player's game, and every defense's.

    python -m atlas.dfs.players             # 2011 to the current season

Step 1 of `docs/MODEL_PLAN_DFS.md`. One row per player-game (QB, RB, WR, TE)
and one per defense-game, with:

* DraftKings points (:mod:`atlas.dfs.scoring`), the thing the model predicts;
* the box score it came from;
* opportunity - the share of the team's snaps, targets, carries and
  red-zone looks (inside the 20) the player had, because opportunity is
  mostly signal and efficiency mostly noise;
* point-in-time trends of each, from the player's earlier games only (the
  row's own game never informs its features);
* where RotoGuru's archive has the player-week (2014-2021), DraftKings' own
  recorded points and salary - the scoring check and the salary benchmark.

Written to ``data/staging/nfl/`` and the NFL warehouse as ``dfs_player_games``
and ``dfs_dst_games``.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from atlas import config
from atlas.dfs import scoring
from atlas.sources import nflverse, rotoguru
from atlas.staging.nfl.build import warehouse_path
from atlas.staging.nfl.games import FRANCHISE
from atlas.util import get_logger, write_parquet

LOG = get_logger(__name__)

#: RotoGuru's team codes, where they differ from nflverse's current ones.
ROTOGURU_TEAM = {"gnb": "GB", "jac": "JAX", "kan": "KC", "lar": "LA", "stl": "LA", "lvr": "LV", "oak": "LV",
                 "nor": "NO", "nwe": "NE", "sdg": "LAC", "sfo": "SF", "tam": "TB"}

#: Half-life, in games, of the point-in-time trends. A player's role moves
#: week to week but mostly persists; four games is the plan's starting value
#: and step 3 tunes it.
HALFLIFE = 4.0

TRENDS = ("dk_points", "snap_pct", "target_share", "carry_share", "rz_target_share", "rz_carry_share",
          "air_yards_share", "pass_attempts", "carries", "targets")

STAT_COLUMNS = ["completions", "attempts", "passing_yards", "passing_tds", "passing_interceptions", "sacks_suffered",
                "carries", "rushing_yards", "rushing_tds", "receptions", "targets", "receiving_yards", "receiving_tds",
                "receiving_air_yards", "target_share", "air_yards_share", "wopr", "passing_epa", "rushing_epa",
                "receiving_epa"]


def norm_name(name) -> str:
    """Lower case, no punctuation, no generational suffix: "C.J. Uzomah" -> "cj uzomah"."""
    if not isinstance(name, str):
        return ""
    name = name.lower().replace("’", "'")
    name = re.sub(r"[.'\-]", "", name)
    name = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b", "", name)
    return re.sub(r"\s+", " ", name).strip()


def _seasons(raw: Path, seasons: list[int], path_fn) -> list[int]:
    return [s for s in seasons if path_fn(raw, s).exists()]


# ---------------------------------------------------------------------------
# Offense
# ---------------------------------------------------------------------------


def _snaps(raw: Path, seasons: list[int]) -> pd.DataFrame:
    """Offensive snaps and snap share per player-game, keyed by nflverse's player id.

    Snap counts are keyed by Pro Football Reference's id; the weekly rosters
    carry both, so they translate.
    """
    frames = []
    # The master player list translates nearly every snap row (99.8%+ in every
    # season checked); the weekly rosters, the fallback, only 68-86%.
    if nflverse.players_path(raw).exists():
        master = pd.read_parquet(nflverse.players_path(raw), columns=["pfr_id", "gsis_id"]).dropna()
    else:
        master = pd.DataFrame(columns=["pfr_id", "gsis_id"])
    for s in _seasons(raw, seasons, nflverse.snap_counts_path):
        snaps = pd.read_parquet(nflverse.snap_counts_path(raw, s),
                                columns=["season", "week", "pfr_player_id", "team", "offense_snaps", "offense_pct"])
        ids = master
        if ids.empty and nflverse.rosters_path(raw, s).exists():
            ids = pd.read_parquet(nflverse.rosters_path(raw, s), columns=["pfr_id", "gsis_id"]).dropna()
        snaps = snaps.merge(ids.drop_duplicates("pfr_id"), left_on="pfr_player_id", right_on="pfr_id", how="inner")
        frames.append(snaps.rename(columns={"gsis_id": "player_id", "offense_pct": "snap_pct"})
                      [["season", "week", "player_id", "offense_snaps", "snap_pct"]])
    if not frames:
        return pd.DataFrame(columns=["season", "week", "player_id", "offense_snaps", "snap_pct"])
    return pd.concat(frames, ignore_index=True).drop_duplicates(["season", "week", "player_id"])


def _red_zone(raw: Path, seasons: list[int]) -> pd.DataFrame:
    """Targets and carries inside the opponent's 20, per player-game, and their team shares."""
    frames = []
    for s in _seasons(raw, seasons, nflverse.pbp_path):
        p = pd.read_parquet(nflverse.pbp_path(raw, s),
                            columns=["season", "week", "posteam", "yardline_100", "play_type",
                                     "receiver_player_id", "rusher_player_id"])
        rz = p[(p["yardline_100"] <= 20) & p["play_type"].isin(["pass", "run"])]
        targets = rz.dropna(subset=["receiver_player_id"]).groupby(["season", "week", "posteam", "receiver_player_id"]).size()
        carries = rz[rz["play_type"] == "run"].dropna(subset=["rusher_player_id"]) \
            .groupby(["season", "week", "posteam", "rusher_player_id"]).size()
        t = targets.rename("rz_targets").reset_index().rename(columns={"receiver_player_id": "player_id"})
        c = carries.rename("rz_carries").reset_index().rename(columns={"rusher_player_id": "player_id"})
        both = t.merge(c, on=["season", "week", "posteam", "player_id"], how="outer").fillna(0)
        team = both.groupby(["season", "week", "posteam"])[["rz_targets", "rz_carries"]].transform("sum")
        both["rz_target_share"] = both["rz_targets"] / team["rz_targets"].replace(0, np.nan)
        both["rz_carry_share"] = both["rz_carries"] / team["rz_carries"].replace(0, np.nan)
        frames.append(both.rename(columns={"posteam": "team"}))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def offense_games(raw: Path, seasons: list[int]) -> pd.DataFrame:
    """One row per offensive player-game with DraftKings points and opportunity."""
    frames = [pd.read_parquet(nflverse.player_stats_path(raw, s))
              for s in _seasons(raw, seasons, nflverse.player_stats_path)]
    stats = pd.concat(frames, ignore_index=True)
    stats["position"] = stats["position"].replace(scoring.POSITION)
    stats = stats[stats["position"].isin(scoring.OFFENSE)].copy()
    stats["team"] = stats["team"].replace(FRANCHISE)
    stats["opponent_team"] = stats["opponent_team"].replace(FRANCHISE)
    stats["dk_points"] = scoring.offense_points(stats)
    stats["name"] = [a if isinstance(a, str) else b for a, b in zip(stats["player_display_name"], stats["player_name"],
                                                                     strict=True)]
    team_carries = stats.groupby(["season", "week", "team"])["carries"].transform("sum")
    stats["carry_share"] = stats["carries"].fillna(0) / team_carries.replace(0, np.nan)
    stats["pass_attempts"] = stats["attempts"]
    keep = ["season", "week", "season_type", "game_id", "team", "opponent_team", "player_id", "name", "position",
            "dk_points", "carry_share", "pass_attempts", *STAT_COLUMNS]
    out = stats[[c for c in dict.fromkeys(keep) if c in stats]].rename(columns={"opponent_team": "opponent"})
    out = out.merge(_snaps(raw, seasons), on=["season", "week", "player_id"], how="left")
    rz = _red_zone(raw, seasons)
    if not rz.empty:
        out = out.merge(rz, on=["season", "week", "team", "player_id"], how="left")
    for c in ("rz_targets", "rz_carries"):
        out[c] = out[c].fillna(0) if c in out else 0.0
    return out.sort_values(["season", "week", "team", "player_id"]).reset_index(drop=True)


def with_trends(games: pd.DataFrame, *, halflife: float = HALFLIFE) -> pd.DataFrame:
    """Point-in-time trends: each player's exponentially weighted history
    *before* the row's game, carried across seasons. ``games_before`` counts
    the games that history rests on."""
    g = games.sort_values(["player_id", "season", "week"]).copy()
    by = g.groupby("player_id", sort=False)
    g["games_before"] = by.cumcount()
    for col in TRENDS:
        if col not in g:
            continue
        g[f"{col}_trend"] = by[col].transform(lambda s: s.shift(1).ewm(halflife=halflife, ignore_na=True).mean())
    return g.sort_values(["season", "week", "team", "player_id"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Defense
# ---------------------------------------------------------------------------


def dst_games(raw: Path, seasons: list[int]) -> pd.DataFrame:
    frames = []
    for s in _seasons(raw, seasons, nflverse.pbp_path):
        events = scoring.dst_events(pd.read_parquet(nflverse.pbp_path(raw, s)))
        frames.append(events)
    out = pd.concat(frames, ignore_index=True)
    out["team"] = out["team"].replace(FRANCHISE)
    out["opponent"] = out["opponent"].replace(FRANCHISE)
    out["points_allowed"] = scoring.points_allowed(out)
    out["dk_points"] = scoring.dst_points(out)
    return out.sort_values(["season", "week", "team"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# DraftKings' own record: RotoGuru 2014-2021
# ---------------------------------------------------------------------------


def archive(raw: Path) -> pd.DataFrame:
    frames = [pd.read_parquet(rotoguru.season_path(raw, s)) for s in rotoguru.SEASONS
              if rotoguru.season_path(raw, s).exists()]
    if not frames:
        return pd.DataFrame(columns=list(rotoguru.COLUMNS.values()))
    a = pd.concat(frames, ignore_index=True)
    a["team_n"] = a["team"].map(lambda t: ROTOGURU_TEAM.get(t, str(t).upper()))
    a["key"] = a["name"].map(lambda n: norm_name(" ".join(reversed([p.strip() for p in str(n).split(",", 1)]))))
    a["last"] = a["name"].map(lambda n: norm_name(str(n).split(",", 1)[0]))
    return a


def match_archive(arch: pd.DataFrame, games: pd.DataFrame) -> pd.DataFrame:
    """Each archive offense row with the nflverse player it is, and how it was matched.

    In order: the same normalized name on the same team that week (the same
    position preferred, which separates two teammates of one name); then the
    same last name at the same position, if only one; then identical
    DraftKings points at the same position, if only one - which catches a
    player who changed his name. ``stage`` records which, and "none" is left
    unmatched: a player the archive lists at 0.00 with no stats at all.
    """
    off = arch[arch["position"] != "Def"].copy().reset_index(drop=True)
    g = games[games["season_type"] == "REG"].copy()
    g["key"] = g["name"].map(norm_name)
    g["last"] = g["name"].map(lambda n: norm_name(n).split(" ")[-1] if isinstance(n, str) else "")
    cols = ["season", "week", "team", "player_id", "position", "dk_points", "key", "last"]
    g = g[cols].rename(columns={"position": "position_nv", "dk_points": "dk_computed"})

    # Stage one, as a join: the same name on the same team that week. Two
    # candidates of one name are separated by position; still two is left.
    m = off.reset_index().merge(g, left_on=["season", "week", "team_n", "key"],
                                right_on=["season", "week", "team", "key"], how="inner", suffixes=("", "_g"))
    m["same_pos"] = m["position_nv"] == m["position"]
    m = m.sort_values(["index", "same_pos"], ascending=[True, False])
    n = m.groupby("index")["same_pos"].transform("sum")
    m = m[(m.groupby("index")["index"].transform("size") == 1) | (m["same_pos"] & (n == 1))]
    m = m.drop_duplicates("index")
    off["player_id"] = pd.NA
    off["dk_computed"] = np.nan
    off["stage"] = "none"
    off.loc[m["index"], "player_id"] = m["player_id"].to_numpy()
    off.loc[m["index"], "dk_computed"] = m["dk_computed"].to_numpy()
    off.loc[m["index"], "stage"] = "name"
    used = set(zip(m["season"], m["week"], m["player_id"], strict=True))

    by_week = {k: v for k, v in g.groupby(["season", "week", "team"])}
    stages = (
        ("last name", lambda a, c: c[(c["last"] == a["last"]) & (c["position_nv"] == a["position"])]),
        ("points", lambda a, c: c[(c["position_nv"] == a["position"]) & ((c["dk_computed"] - a["dk_points"]).abs() <= 0.05)]),
    )
    for stage, pick in stages:
        for i, a in off[off["stage"] == "none"].iterrows():
            if stage == "points" and a["dk_points"] == 0:
                continue                      # zero matches anyone who did nothing; not evidence
            cands = by_week.get((a["season"], a["week"], a["team_n"]))
            if cands is None:
                continue
            cands = cands[[(a["season"], a["week"], pid) not in used for pid in cands["player_id"]]]
            hits = pick(a, cands)
            if len(hits) == 1:
                hit = hits.iloc[0]
                off.at[i, "player_id"] = hit["player_id"]
                off.at[i, "dk_computed"] = hit["dk_computed"]
                off.at[i, "stage"] = stage
                used.add((a["season"], a["week"], hit["player_id"]))
    return off


def build(seasons: list[int] | None = None) -> dict[str, pd.DataFrame]:
    paths = config.paths().ensure()
    raw = paths.raw
    seasons = seasons or list(range(nflverse.FIRST_SEASON, nflverse.current_season() + 1))
    games = with_trends(offense_games(raw, seasons))
    dst = dst_games(raw, seasons)
    arch = archive(raw)
    if not arch.empty:
        matched = match_archive(arch, games)
        m = matched.dropna(subset=["player_id"])[["season", "week", "player_id", "dk_points", "dk_salary"]]
        games = games.merge(m.rename(columns={"dk_points": "dk_points_official", "dk_salary": "dk_salary"}),
                            on=["season", "week", "player_id"], how="left")
        d = arch[arch["position"] == "Def"][["season", "week", "team_n", "dk_points", "dk_salary"]]
        dst = dst.merge(d.rename(columns={"team_n": "team", "dk_points": "dk_points_official"}),
                        on=["season", "week", "team"], how="left")
    staging = paths.staging / "nfl"
    staging.mkdir(parents=True, exist_ok=True)
    write_parquet(games, staging / "dfs_player_games.parquet")
    write_parquet(dst, staging / "dfs_dst_games.parquet")
    con = duckdb.connect(str(warehouse_path(paths.warehouse)))
    try:
        con.register("g", games)
        con.execute("CREATE OR REPLACE TABLE dfs_player_games AS SELECT * FROM g")
        con.register("d", dst)
        con.execute("CREATE OR REPLACE TABLE dfs_dst_games AS SELECT * FROM d")
    finally:
        con.close()
    LOG.info("dfs: %d player-games, %d defense-games, seasons %s-%s", len(games), len(dst), seasons[0], seasons[-1])
    return {"players": games, "dst": dst}


def main() -> None:
    ap = argparse.ArgumentParser(description="Build the DFS player-game and defense-game tables")
    ap.add_argument("--seasons", type=int, nargs="*", default=None)
    build(ap.parse_args().seasons)


if __name__ == "__main__":
    main()
