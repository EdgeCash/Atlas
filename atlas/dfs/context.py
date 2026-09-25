"""The week's news around a player, as it stood before kickoff.

    python -m atlas.dfs.context            # writes data/staging/nfl/dfs_player_context.parquet

What the player model's history cannot know and DraftKings' salary partly
does: who is hurt this week and where the team has him on its depth chart.
One row per player-week the injury report or the depth chart names:

* ``status`` - his own game status on the week's final injury report:
  0 none, 1 questionable, 2 doubtful, 3 out;
* ``depth_rank`` - his rank at his position on the week's depth chart
  (1 the starter). Before 2025 nflverse publishes one chart per week; from
  2025 it publishes daily snapshots, and the latest before kickoff is used;
* ``vacated_targets`` / ``vacated_carries`` - the target and carry shares
  of teammates listed out or doubtful, each at the share he held going into
  his absence; ``vacated_pos_*`` the same, from teammates at his position;
* ``qb1_out`` - the team's usual quarterback is listed out or doubtful.

All of it is published before the game: the final report on the Friday
(Saturday for a Monday game), the depth chart during the week.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from atlas import config
from atlas.sources import nflverse
from atlas.staging.nfl.games import FRANCHISE, snapshot_time
from atlas.util import get_logger, write_parquet

LOG = get_logger(__name__)

STATUS = {"Questionable": 1, "Doubtful": 2, "Out": 3}
OFFENSE = {"QB": "QB", "RB": "RB", "HB": "RB", "FB": "RB", "WR": "WR", "TE": "TE"}
#: A share goes stale: a teammate last seen this many weeks ago vacates nothing.
STALE_WEEKS = 20
HALFLIFE = 4.0
QB_GAMES = 8


def path(staging: Path | None = None) -> Path:
    return (staging or config.paths().staging / "nfl") / "dfs_player_context.parquet"


def _order(season, week) -> np.ndarray:
    return np.asarray(season, dtype="int64") * 100 + np.asarray(week, dtype="int64")


def injuries(raw: Path, seasons: list[int]) -> pd.DataFrame:
    frames = []
    for season in seasons:
        p = nflverse.injuries_path(raw, season)
        if not p.exists():
            continue
        i = pd.read_parquet(p)
        i = i[i["game_type"].astype(str) == "REG"] if "game_type" in i else i
        i = i.assign(week=pd.to_numeric(i["week"], errors="coerce"), team=i["team"].replace(FRANCHISE),
                     status=i["report_status"].map(STATUS).fillna(0))
        frames.append(i.dropna(subset=["week", "gsis_id"])[["season", "week", "team", "gsis_id", "status"]])
    if not frames:
        return pd.DataFrame(columns=["season", "week", "team", "player_id", "status"])
    out = pd.concat(frames, ignore_index=True).rename(columns={"gsis_id": "player_id"})
    out["season"], out["week"] = out["season"].astype(int), out["week"].astype(int)
    # A player listed twice in a week keeps his latest (the highest) status.
    return out.groupby(["season", "week", "team", "player_id"], as_index=False)["status"].max()


def _kickoffs(raw: Path) -> pd.DataFrame:
    s = pd.read_parquet(nflverse.schedules_path(raw))
    s = s[s["game_type"] == "REG"]
    at = pd.to_datetime(s["gameday"] + " " + s["gametime"].fillna("13:00"), errors="coerce")
    at = at.dt.tz_localize("America/New_York", ambiguous="NaT", nonexistent="NaT").dt.tz_convert("UTC")
    parts = [pd.DataFrame({"season": s["season"], "week": s["week"], "team": s[side].replace(FRANCHISE),
                           "kickoff": at}) for side in ("home_team", "away_team")]
    return pd.concat(parts, ignore_index=True).dropna(subset=["kickoff"])


def depth(raw: Path, seasons: list[int]) -> pd.DataFrame:
    frames, snapshots = [], []
    for season in seasons:
        p = nflverse.depth_charts_path(raw, season)
        if not p.exists():
            continue
        d = pd.read_parquet(p)
        if "pos_rank" in d:                                   # 2025 on: daily snapshots
            d = d[d["pos_abb"].isin(list(OFFENSE))]
            snapshots.append(pd.DataFrame({
                "team": d["team"].replace(FRANCHISE), "player_id": d["gsis_id"],
                "depth_rank": pd.to_numeric(d["pos_rank"], errors="coerce"),
                "dt": snapshot_time(d["dt"])}).dropna())
            continue
        d = d[(d["formation"] == "Offense") & d["depth_position"].astype(str).str.strip().isin(list(OFFENSE))]
        if "game_type" in d:
            d = d[d["game_type"].astype(str) == "REG"]
        frames.append(pd.DataFrame({
            "season": d["season"].astype(int), "week": pd.to_numeric(d["week"], errors="coerce"),
            "team": d["club_code"].replace(FRANCHISE), "player_id": d["gsis_id"],
            "depth_rank": pd.to_numeric(d["depth_team"], errors="coerce")}).dropna())
    if snapshots:
        snap = pd.concat(snapshots, ignore_index=True)
        # Each player's best rank in each snapshot, then the latest snapshot before his kickoff.
        snap = snap.groupby(["team", "player_id", "dt"], as_index=False)["depth_rank"].min().sort_values("dt")
        kick = _kickoffs(raw).sort_values("kickoff")
        kick = kick[kick["season"] >= int(snap["dt"].dt.year.min())]
        latest = snap.groupby(["team", "dt"], as_index=False).size()[["team", "dt"]].sort_values("dt")
        chosen = pd.merge_asof(kick, latest, left_on="kickoff", right_on="dt", by="team", direction="backward")
        chosen = chosen.dropna(subset=["dt"])
        frames.append(chosen.merge(snap, on=["team", "dt"])[["season", "week", "team", "player_id", "depth_rank"]])
    if not frames:
        return pd.DataFrame(columns=["season", "week", "team", "player_id", "depth_rank"])
    out = pd.concat(frames, ignore_index=True)
    out["season"], out["week"] = out["season"].astype(int), out["week"].astype(int)
    return out.groupby(["season", "week", "team", "player_id"], as_index=False)["depth_rank"].min()


def _shares(player_games: pd.DataFrame) -> pd.DataFrame:
    """Each player's shares going *out* of each game: the trend including it."""
    g = player_games[player_games["season_type"] == "REG"].sort_values(["player_id", "season", "week"]).copy()
    by = g.groupby("player_id", sort=False)
    for col in ("target_share", "carry_share", "pass_attempts"):
        g[f"{col}_after"] = by[col].transform(lambda s: s.ewm(halflife=HALFLIFE, ignore_na=True).mean())
    g["order"] = _order(g["season"], g["week"])
    return g[["player_id", "position", "order", "target_share_after", "carry_share_after", "pass_attempts_after"]]


def vacated(report: pd.DataFrame, player_games: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Per team-week and position: the shares of players listed out or doubtful."""
    absent = report[report["status"] >= 2].copy()
    absent["order"] = _order(absent["season"], absent["week"])
    shares = _shares(player_games).sort_values("order")
    absent = pd.merge_asof(absent.sort_values("order"), shares, on="order", by="player_id",
                           direction="backward", allow_exact_matches=False, suffixes=("", "_last"))
    # How long ago the share was earned, in season-weeks (approximate across seasons).
    last = shares.groupby("player_id")["order"].apply(np.array)
    absent = absent.dropna(subset=["position"])
    fresh = absent.apply(lambda r: _weeks_since(r["order"], last.get(r["player_id"])) <= STALE_WEEKS, axis=1) \
        if len(absent) else pd.Series(dtype=bool)
    absent = absent[fresh.astype(bool)] if len(absent) else absent
    keys = ["season", "week", "team"]
    team = absent.groupby(keys, as_index=False).agg(vacated_targets=("target_share_after", "sum"),
                                                    vacated_carries=("carry_share_after", "sum"))
    pos = absent.groupby([*keys, "position"], as_index=False).agg(vacated_pos_targets=("target_share_after", "sum"),
                                                                  vacated_pos_carries=("carry_share_after", "sum"))
    return team, pos


def _weeks_since(order: int, seen) -> float:
    if seen is None:
        return np.inf
    earlier = seen[seen < order]
    if not len(earlier):
        return np.inf
    last = int(earlier.max())
    return (order // 100 - last // 100) * 18 + (order % 100 - last % 100)


def usual_qb(player_games: pd.DataFrame) -> pd.DataFrame:
    """Each team-week's usual quarterback: the most pass attempts, by trend, going in."""
    q = player_games[(player_games["season_type"] == "REG") & (player_games["position"] == "QB")]
    s = _shares(q).merge(q.assign(order=_order(q["season"], q["week"]))[["player_id", "order", "team"]],
                         on=["player_id", "order"])
    weeks = player_games[player_games["season_type"] == "REG"][["season", "week", "team"]].drop_duplicates()
    weeks = weeks.assign(order=_order(weeks["season"], weeks["week"]))
    rows = []
    for team, w in weeks.groupby("team"):
        t = s[s["team"] == team]
        if t.empty:
            continue
        # Each quarterback's attempt trend carried forward from his last game
        # for this team, as it stood before each week; the highest is the usual
        # one. A quarterback who has missed QB_GAMES straight team games
        # (traded, cut, on injured reserve) is no longer the usual one.
        wide = t.pivot_table(index="order", columns="player_id", values="pass_attempts_after").sort_index()
        wide = wide.ffill(limit=QB_GAMES - 1)
        prior = pd.merge_asof(w[["order"]].sort_values("order"), wide.reset_index(), on="order",
                              direction="backward", allow_exact_matches=False)
        vals = prior.drop(columns=["order"])
        best = vals.fillna(-1).idxmax(axis=1).where(vals.notna().any(axis=1))
        rows.append(pd.DataFrame({"order": prior["order"].to_numpy(), "team": team, "qb1_id": best.to_numpy()}))
    out = pd.concat(rows, ignore_index=True)
    return out.assign(season=out["order"] // 100, week=out["order"] % 100).drop(columns=["order"])


def build(seasons: list[int] | None = None, staging: Path | None = None) -> pd.DataFrame:
    """The context table, from ``staging``'s player-games (the NFL staging directory by default)."""
    paths = config.paths()
    staging = staging or paths.staging / "nfl"
    player_games = pd.read_parquet(staging / "dfs_player_games.parquet")
    seasons = seasons or sorted(int(s) for s in player_games["season"].unique())
    report = injuries(paths.raw, seasons)
    chart = depth(paths.raw, seasons)
    team_vac, pos_vac = vacated(report, player_games)
    qb1 = usual_qb(player_games)
    qb1 = qb1.merge(report.rename(columns={"player_id": "qb1_id", "status": "qb1_status"}),
                    on=["season", "week", "team", "qb1_id"], how="left")
    qb1["qb1_out"] = (qb1["qb1_status"].fillna(0) >= 2).astype(int)

    # One row per player-week the model scores: its own rows, with the week's news.
    rows = player_games[player_games["season_type"] == "REG"][["season", "week", "team", "player_id", "position"]]
    keys = ["season", "week", "team", "player_id"]
    out = rows.merge(report, on=keys, how="left").merge(chart, on=keys, how="left")
    out = out.merge(team_vac, on=["season", "week", "team"], how="left")
    out = out.merge(pos_vac, on=["season", "week", "team", "position"], how="left")
    out = out.merge(qb1[["season", "week", "team", "qb1_id", "qb1_out"]], on=["season", "week", "team"], how="left")
    out["status"] = out["status"].fillna(0)
    for c in ("vacated_targets", "vacated_carries", "vacated_pos_targets", "vacated_pos_carries", "qb1_out"):
        out[c] = out[c].fillna(0)
    out["is_qb1"] = (out["player_id"] == out["qb1_id"]).astype(int)
    out = out.drop(columns=["qb1_id", "position"])
    write_parquet(out, path(staging))
    LOG.info("context: %d player-weeks; injury status for %d, depth rank for %d", len(out),
             int((out["status"] > 0).sum()), int(out["depth_rank"].notna().sum()))
    return out


def main() -> None:
    argparse.ArgumentParser(description="Injury report and depth chart context per player-week").parse_args()
    build()


if __name__ == "__main__":
    main()
