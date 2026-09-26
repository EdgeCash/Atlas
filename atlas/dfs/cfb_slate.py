"""This week's college slates: every priced player projected, and lineups.

    python -m atlas.dfs.cfb_slate           # the upcoming college Classic and Showdown slates

Step 5 of `docs/MODEL_PLAN_DFS_CFB.md`. The college model is walk-forward:
a season is projected by the model fitted on the seasons before it. This
runs that same fit on the games about to be played:

1. each slate's pool from the record DraftKings' capture keeps, matched to
   ESPN's teams (by whose names match most) and players (name and team,
   then name and position - a transfer keeps his record), and each game to
   ESPN's upcoming game by its two teams;
2. a row per player for the coming game appended to the player-game table,
   so every trend is computed as tested - from games before this one;
3. the game as the line implies it now (the market Atlas captures for its
   game cards), the projection and its range, and the chance he records a
   stat (`atlas/dfs/cfb_participation.py`);
4. the owner's lineups for each slate: five for Classic (the SUPERFLEX
   included) and five for each Showdown;
5. every priced player's projection, for the private record
   (`atlas/dfs/cfb_record.py`).

Written under ``data/dfs/`` like the NFL's, never committed; the owner page
seals them.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from atlas import config
from atlas.dfs import cfb, ranges
from atlas.dfs import cfb_model as cm
from atlas.dfs import cfb_participation as part
from atlas.dfs import cfb_players as cp
from atlas.dfs import optimizer as op
from atlas.dfs import slate as nfl_slate
from atlas.sources import espn_cfb
from atlas.util import get_logger, where

LOG = get_logger(__name__)

LINEUPS = {
    "Classic": op.Options(roster=op.CFB_CLASSIC, no_defense_vs_offense=False, n=5, min_unique=2, max_exposure=0.8),
    "Showdown": op.Options(n=5, min_unique=2, max_exposure=0.8),
}
POSITIONS = {"QB": "QB", "RB": "RB", "WR": "WR", "TE": "WR", "K": "K"}


def ranges_path() -> Path:
    return config.paths().root / "reports" / "dfs_cfb_ranges.json"


def upcoming(slates: pd.DataFrame, now: datetime | None = None) -> pd.DataFrame:
    now = now or datetime.now(timezone.utc)
    s = slates[slates["sport"] == "cfb"].copy() if "sport" in slates else slates.iloc[0:0]
    s["start"] = pd.to_datetime(s["starts_at"], utc=True)
    return s[s["start"] > pd.Timestamp(now)].sort_values(["start", "game_type", "label"]).reset_index(drop=True)


def live_environment(store, events: pd.DataFrame) -> pd.DataFrame:
    """Each upcoming (event, team): points implied by the latest captured line.

    The store's margin is the home side's expected margin; a team's points are
    half the total plus or minus half of it."""
    snaps = store.read("snapshots")
    if snaps.empty:
        return pd.DataFrame(columns=["event", "team", "team_pts", "opp_pts", "proj_total", "proj_margin"])
    snaps = snaps.sort_values("captured_at").drop_duplicates(["game_id", "book", "market"], keep="last")
    lines = snaps.groupby(["game_id", "market"])["line"].median().unstack()
    rows = []
    for e in events.itertuples():
        gid = int(e.event)
        if gid not in lines.index:
            continue
        margin, total = lines.loc[gid].get("margin"), lines.loc[gid].get("total")
        if pd.isna(margin) or pd.isna(total):
            continue
        home_pts, away_pts = total / 2 + margin / 2, total / 2 - margin / 2
        for team, pts, opp in ((e.home, home_pts, away_pts), (e.away, away_pts, home_pts)):
            rows.append({"event": str(e.event), "team": team, "team_pts": pts, "opp_pts": opp,
                         "proj_total": total, "proj_margin": pts - opp})
    return pd.DataFrame(rows, columns=["event", "team", "team_pts", "opp_pts", "proj_total", "proj_margin"])


def match_games(pool: pd.DataFrame, teams: dict, events: pd.DataFrame) -> pd.DataFrame:
    """Each DraftKings game to ESPN's upcoming event by its two teams, within a day and a half."""
    sides = pool["game"].str.split(r" @ | vs ", n=1, expand=True, regex=True)
    p = pool.assign(dk_away=sides[0], dk_home=sides[1])
    p["espn_team"] = p["team"].map(teams)
    p["a"], p["h"] = p["dk_away"].map(teams), p["dk_home"].map(teams)
    ev = events.assign(key=[frozenset((h, a)) for h, a in zip(events["home"], events["away"], strict=True)],
                       at=pd.to_datetime(events["date"], utc=True, errors="coerce"))
    start = pd.to_datetime(p["game_start"], utc=True, errors="coerce")
    got = []
    for i, row in p.iterrows():
        m = ev[(ev["key"] == frozenset((row["h"], row["a"])))]
        m = m[(m["at"] - start[i]).abs() <= pd.Timedelta(hours=36)]
        got.append(m.iloc[0] if len(m) else None)
    p["event"] = [g["event"] if g is not None else None for g in got]
    p["week"] = [g["week"] if g is not None else None for g in got]
    p["season_type"] = [g["season_type"] if g is not None else None for g in got]
    p["espn_home"] = [g["home"] if g is not None else None for g in got]
    p["espn_away"] = [g["away"] if g is not None else None for g in got]
    return p


def match_players(pool: pd.DataFrame, table: pd.DataFrame) -> pd.DataFrame:
    """ESPN's athlete id for each DraftKings player: name and team, then name and
    position over the last two seasons (a transfer keeps his record)."""
    recent = table[table["season"] >= table["season"].max() - 1].sort_values("order")
    last = recent.groupby("player_id").tail(1).assign(key=lambda d: d["name"].map(cfb.norm_name))
    p = pool.assign(key=pool["name"].map(cfb.norm_name))
    p["player_id"], p["matched_by"] = None, None
    for label, keys, cands in (("name and team", ["key", "espn_team"], last.rename(columns={"team": "espn_team"})),
                               ("name and position", ["key", "position"], last)):
        todo = p["player_id"].isna()
        unique = cands.drop_duplicates(keys, keep=False)[[*keys, "player_id"]].rename(columns={"player_id": "found"})
        hit = p.loc[todo, keys].reset_index().merge(unique, on=keys).set_index("index")["found"]
        p.loc[hit.index, "player_id"] = hit
        p.loc[hit.index, "matched_by"] = label
    # Two DraftKings players on one record: the name-and-team match keeps it.
    rank = p["matched_by"].map({"name and team": 0, "name and position": 1})
    twice = p.assign(rank=rank).sort_values("rank").duplicated("player_id") & p["player_id"].notna()
    p.loc[twice[twice].index, ["player_id", "matched_by"]] = None
    none = p["player_id"].isna()
    p.loc[none, "player_id"] = "DKC-" + p.loc[none, "player_id_dk"].astype(str)
    p.loc[none, "matched_by"] = "none (no history)"
    return p.drop(columns=["key"])


def project(players: pd.DataFrame, table: pd.DataFrame, env_live: pd.DataFrame) -> pd.DataFrame:
    """Projection, range and chance of playing for each matched player's coming game."""
    season = int(table["season"].max())
    ok = players.dropna(subset=["event"]).drop_duplicates(["event", "player_id"])
    order = season * 1000 + np.where(ok["season_type"] == "postseason", 100, 0) + ok["week"].astype(int).clip(upper=99)
    new = pd.DataFrame({
        "season": season, "week": ok["week"].astype(int), "season_type": ok["season_type"], "event": ok["event"],
        "team": ok["espn_team"], "opponent": np.where(ok["espn_team"] == ok["espn_home"], ok["espn_away"],
                                                      ok["espn_home"]),
        "home": (ok["espn_team"] == ok["espn_home"]).astype(int), "player_id": ok["player_id"], "name": ok["name"],
        "position": ok["position"], "fbs": True, "order": order,
    })
    base = table.drop(columns=[c for c in table.columns if c.endswith("_trend") or c == "games_before"])
    aug = cp.with_trends(pd.concat([base, new], ignore_index=True))
    env = pd.concat([cm.environment(aug[["event", "team"]].dropna()), env_live], ignore_index=True)
    env = env.drop_duplicates(["event", "team"], keep="last")
    f = cm.features(aug, env)
    fitted = cm.predict_season(f, season)
    keys = new[["event", "player_id"]]
    fitted = fitted.drop_duplicates(["event", "player_id"], keep="last")
    got = keys.merge(fitted[["event", "player_id", "position", "model"]], on=["event", "player_id"], how="left")
    got = got.join(ranges.apply(got.dropna(subset=["model"]), ranges.load(ranges_path())))
    # Whether he plays: the candidates for each upcoming team game.
    upcoming_games = new[["team", "event", "season", "order"]].drop_duplicates(["team", "event"])
    c = part.candidates(table, upcoming_games)
    history = c[~c["event"].isin(upcoming_games["event"])]
    live = c[c["event"].isin(upcoming_games["event"])]
    if len(live) and len(history):
        live = live.assign(p_play=part.predict(part.fit(history), live))
        live = live.sort_values("played_8").drop_duplicates(["event", "player_id"], keep="last")
        got = got.merge(live[["event", "player_id", "p_play"]], on=["event", "player_id"], how="left")
    else:
        got["p_play"] = np.nan
    got["p_play"] = got["p_play"].fillna(part.NEW_PLAYER)
    got["if_plays"] = got["model"]
    got["projection"] = got["p_play"] * got["model"]
    got["low"] = nfl_slate.mixture_quantile(got["p_play"], got["model"], got["model_lo"], got["model_hi"], ranges.LOW)
    got["high"] = nfl_slate.mixture_quantile(got["p_play"], got["model"], got["model_lo"], got["model_hi"],
                                             ranges.HIGH)
    keep = ["event", "player_id", "p_play", "if_plays", "projection", "low", "high"]
    return players.merge(got[keep], on=["event", "player_id"], how="left")


def run(store=None, *, now: datetime | None = None, raw: Path | None = None) -> list[dict]:
    """Every upcoming college slate built; returns what was built for the index."""
    if store is None:
        from atlas.live.store import Store

        store = Store.open()
    todo = upcoming(store.read("dfs_slates"), now)
    if todo.empty:
        return []
    salaries = store.read("dfs_salaries")
    salaries = salaries[salaries["draft_group_id"].isin(todo["draft_group_id"])].rename(
        columns={"player_id": "player_id_dk"})
    if salaries.empty:
        return []
    salaries = salaries.assign(position=salaries["position"].map(POSITIONS).fillna(salaries["position"]))
    table = pd.read_parquet(cp.path())
    players_ = salaries.sort_values("draft_group_id").drop_duplicates("player_id_dk")[
        ["player_id_dk", "name", "position", "team", "game", "game_start", "status", "disabled"]]
    season = int(table["season"].max())
    teams = cfb.team_map(players_, table[table["season"] >= season - 1])
    events_path = espn_cfb.games_path(raw, season)
    events = pd.read_parquet(events_path) if events_path.exists() else pd.DataFrame(columns=espn_cfb.GAME_COLUMNS)
    events = events[~events["completed"]] if len(events) else events
    players_ = match_players(match_games(players_, teams, events), table)
    projected = project(players_, table, live_environment(store, events))
    per_player = projected[["player_id_dk", "player_id", "matched_by", "p_play", "if_plays", "projection", "low",
                            "high", "espn_team"]].drop_duplicates("player_id_dk")
    built = []
    for _, slate in todo.iterrows():
        group, kind, label = int(slate["draft_group_id"]), slate["game_type"], slate["label"]
        pool = salaries[salaries["draft_group_id"] == group].merge(per_player, on="player_id_dk", how="left")
        if pool.empty:
            LOG.info("college %s %s (%d): listed, no player pool posted yet; skipped", kind, label, group)
            continue
        sides = pool["game"].str.split(r" @ | vs ", n=1, expand=True, regex=True)
        pool["opponent"] = np.where(pool["team"] == sides[0], sides[1], sides[0])
        out = nfl_slate.out_dir(group)
        out.mkdir(parents=True, exist_ok=True)
        cols = ["name", "position", "team", "opponent", "salary", "cpt_salary", "status", "projection", "low", "high",
                "p_play", "if_plays", "matched_by", "player_id", "player_id_dk", "draftable_id", "cpt_draftable_id",
                "game_start"]
        pool.sort_values("projection", ascending=False)[cols].to_csv(out / "projections.csv", index=False,
                                                                      float_format="%.2f")
        meta = {"draft_group_id": group, "game_type": kind, "label": label, "starts_at": str(slate["starts_at"]),
                "sport": "cfb"}
        (out / "slate.json").write_text(json.dumps(meta) + "\n")
        p = nfl_slate._playable(pool)
        try:
            made = (op.showdown(p, LINEUPS["Showdown"], flex_label="UTIL") if kind == "Showdown"
                    else op.optimize(p, LINEUPS["Classic"]))
        except op.Infeasible:
            made = []
        except Exception as error:  # noqa: BLE001 - the type and the place only; one slate never costs the others
            LOG.error("college %s %s (%d): lineups not built: %s at %s", kind, label, group, type(error).__name__,
                      where(error))
            made = []
        (out / "lineups_upload.csv").write_text(op.upload(made, kind, "cfb"))
        cols = ["lineup", "slot", "name", "team", "salary", "projection", "low", "high"]
        readable = pd.concat([lu.assign(lineup=i + 1) for i, lu in enumerate(made)]) if made else \
            pd.DataFrame(columns=cols)
        readable[cols].to_csv(out / "lineups.csv", index=False, float_format="%.2f")
        built.append({**meta, "lineups": len(made)})
        LOG.info("college %s %s (%d): %d lineups", kind, label, group, len(made))
    # Every priced player's projection, for the private record (`atlas/dfs/cfb_record.py`).
    classic = todo.loc[todo["game_type"] == "Classic", "draft_group_id"]
    salary = salaries[salaries["draft_group_id"].isin(classic)].groupby("player_id_dk")["salary"].max()
    from atlas.dfs import cfb_record

    projected.assign(season=season, salary=projected["player_id_dk"].map(salary)).reindex(
        columns=[c for c in cfb_record.COLUMNS if c != "projected_at"]).to_csv(
        cfb_record.projections_path(), index=False, float_format="%.3f")
    unmatched = int((projected["matched_by"] == "none (no history)").sum())
    no_game = int(projected["event"].isna().sum())
    LOG.info("college DFS: %d slates, %d players (%d without history, %d without a game)", len(built),
             len(projected), unmatched, no_game)
    return built


def main() -> None:
    argparse.ArgumentParser(description="Project the upcoming college DraftKings slates").parse_args()
    run()


if __name__ == "__main__":
    main()
