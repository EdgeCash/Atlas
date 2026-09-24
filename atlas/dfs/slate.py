"""This week's slate: every player in DraftKings' pool, projected, and lineups.

    python -m atlas.dfs.slate                   # the upcoming Main slate, from the record
    python -m atlas.dfs.slate --capture         # capture DraftKings' pools first
    python -m atlas.dfs.slate --label Thu-Mon   # another Classic slate

Step 5 of `docs/MODEL_PLAN_DFS.md`. The player model is walk-forward: a
season is projected by the model fitted on the seasons before it. This
runs that same fit for the season in progress, on the week about to be
played:

1. the slate's pool from the record DraftKings' capture keeps
   (`tracking/dfs_salaries.csv`), each player matched to nflverse's id -
   by name and team, then name and position, then the master player list
   (a rookie with no games yet);
2. a row per player for the coming game appended to a private copy of the
   player and defense tables, so every trend, the injury report, the depth
   chart and the game environment are computed exactly as the model was
   tested - from games before this one;
3. the projection: the chance he records a stat at all
   (`atlas/dfs/participation.py`) times what he scores if he does, with a
   10th-90th percentile range (the lines `make dfs-model` saves in
   `reports/dfs_ranges.json`, with the chance of not playing folded in);
4. the lineups with the most projected points under the cap.

Players DraftKings marks out, doubtful, on a reserve list or disabled are
left out of the lineups. Everything is written under ``data/dfs/`` - not
committed: the owner page (step 6) publishes it only encrypted.
"""

from __future__ import annotations

import argparse
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from atlas import config
from atlas.dfs import benchmarks as bm
from atlas.dfs import context, environment, model, participation, players, ranges
from atlas.dfs import optimizer as op
from atlas.sources import nflverse
from atlas.util import get_logger

LOG = get_logger(__name__)

#: DraftKings' team codes, where nflverse's differ.
DK_TEAM = {"LAR": "LA"}
#: DraftKings statuses a lineup can still use: healthy, questionable, probable.
PLAYABLE = {"", "Q", "P", "GTD"}
#: The owner's defaults: ten lineups, each at least two players apart, the
#: quarterback with one of his own receivers, no player in more than six.
OWNER = op.Options(n=10, min_unique=2, qb_stack=1, max_exposure=0.6)
EASTERN = timezone(timedelta(hours=-4))       # the season runs on daylight time until November


def out_dir(draft_group_id: int) -> Path:
    return config.paths().root / "data" / "dfs" / str(int(draft_group_id))


def choose_slate(slates: pd.DataFrame, label: str = "Main", now: datetime | None = None) -> pd.Series:
    """The next slate with this label that has not started more than a day ago."""
    now = now or datetime.now(timezone.utc)
    s = slates[slates["label"] == label].copy()
    s["start"] = pd.to_datetime(s["starts_at"], utc=True)
    s = s[s["start"] >= pd.Timestamp(now) - pd.Timedelta(days=1)].sort_values("start")
    if s.empty:
        raise LookupError(f"no upcoming {label} slate in the record")
    return s.iloc[0]


def with_games(pool: pd.DataFrame, schedule: pd.DataFrame) -> pd.DataFrame:
    """Each player's game in nflverse's terms: season, week, game id, opponent."""
    p = pool.copy()
    p["team"] = p["team"].replace(DK_TEAM)
    sides = p["game"].str.split(" @ ", n=1, expand=True)
    p["away"], p["home"] = sides[0].replace(DK_TEAM), sides[1].replace(DK_TEAM)
    p["opponent"] = np.where(p["team"] == p["home"], p["away"], p["home"])
    start = pd.to_datetime(p["game_start"], utc=True)
    p["gameday"] = start.dt.tz_convert(EASTERN).dt.strftime("%Y-%m-%d")
    s = schedule[schedule["game_type"] == "REG"][["game_id", "season", "week", "gameday", "home_team", "away_team"]]
    s = s.rename(columns={"home_team": "home", "away_team": "away"})
    return p.merge(s, on=["home", "away", "gameday"], how="left")


def match(pool: pd.DataFrame, player_games: pd.DataFrame, master: pd.DataFrame | None = None) -> pd.DataFrame:
    """nflverse's id for each DraftKings player; ``matched_by`` says how."""
    p = pool.copy()
    p["key"] = p["name"].map(players.norm_name)
    p["player_id"], p["matched_by"] = None, None
    is_dst = p["position"] == "DST"
    p.loc[is_dst, "player_id"] = "DST-" + p.loc[is_dst, "team"]
    p.loc[is_dst, "matched_by"] = "team"
    last = player_games.sort_values(["season", "week"]).groupby("player_id").tail(1)
    last = last.assign(key=last["name"].map(players.norm_name))
    recent = last[last["season"] >= last["season"].max() - 2]
    stages = [("name and team", recent, ["key", "team"]), ("name and position", recent, ["key", "position"])]
    if master is not None and len(master):
        m = master.rename(columns={"gsis_id": "player_id", "latest_team": "team"})
        m = m.assign(key=m["display_name"].map(players.norm_name)).dropna(subset=["player_id"])
        stages += [("player list, name and team", m, ["key", "team"]),
                   ("player list, name and position", m, ["key", "position"])]
    for label, cands, keys in stages:
        todo = p["player_id"].isna()
        if not todo.any():
            break
        unique = cands.drop_duplicates(keys, keep=False)[[*keys, "player_id"]].rename(columns={"player_id": "found"})
        hit = p.loc[todo, [*keys]].reset_index().merge(unique, on=keys, how="inner").set_index("index")["found"]
        p.loc[hit.index, "player_id"] = hit
        p.loc[hit.index, "matched_by"] = label
    unmatched = p["player_id"].isna()
    p.loc[unmatched, "player_id"] = "DK-" + p.loc[unmatched, "player_id_dk"].astype(str)
    p.loc[unmatched, "matched_by"] = "none (no history)"
    return p.drop(columns=["key"])


def _augment(pool: pd.DataFrame, staging: Path, into: Path) -> None:
    """Copy the player and defense tables into ``into`` with a row per pool
    player for the coming game, trends recomputed so each is pre-game."""
    into.mkdir(parents=True, exist_ok=True)
    pg = pd.read_parquet(staging / "dfs_player_games.parquet")
    off = pool[pool["position"] != "DST"]
    new = pd.DataFrame({"season": off["season"].astype(int), "week": off["week"].astype(int), "season_type": "REG",
                        "game_id": off["game_id"], "team": off["team"], "opponent": off["opponent"],
                        "player_id": off["player_id"], "name": off["name"], "position": off["position"]})
    pg = pg.merge(new[["season", "week", "player_id"]], on=["season", "week", "player_id"], how="left", indicator=True)
    pg = pg[pg["_merge"] == "left_only"].drop(columns="_merge")
    pg = players.with_trends(pd.concat([pg, new], ignore_index=True))
    pg.to_parquet(into / "dfs_player_games.parquet", index=False)
    dst = pd.read_parquet(staging / "dfs_dst_games.parquet")
    d = pool[pool["position"] == "DST"]
    new_d = pd.DataFrame({"game_id": d["game_id"], "team": d["team"], "season": d["season"].astype(int),
                          "week": d["week"].astype(int), "season_type": "REG", "opponent": d["opponent"]})
    dst = dst.merge(new_d[["season", "week", "team"]], on=["season", "week", "team"], how="left", indicator=True)
    dst = dst[dst["_merge"] == "left_only"].drop(columns="_merge")
    pd.concat([dst, new_d], ignore_index=True).to_parquet(into / "dfs_dst_games.parquet", index=False)


def project(pool: pd.DataFrame, *, staging: Path | None = None, lines: dict | None = None) -> pd.DataFrame:
    """The pool with ``projection``, ``low`` and ``high``: the walk-forward
    model for the season in progress, on the coming week."""
    staging = staging or config.paths().staging / "nfl"
    playable = pool.dropna(subset=["season", "week"])
    season = int(playable["season"].mode().iloc[0])
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        _augment(playable, staging, tmp)
        context.build(staging=tmp)
        frame = bm.load(tmp)
        full = model.features(frame, pd.read_parquet(environment.path()), staging=tmp)
        fitted = model.predict_season(full, season)
        news = pd.read_parquet(context.path(tmp))
        aug = pd.read_parquet(tmp / "dfs_player_games.parquet")
    keys = playable[["season", "week", "player_id", "position"]].astype({"season": int, "week": int})
    got = keys.merge(fitted[["season", "week", "player_id", "model", "model_sd"]],
                     on=["season", "week", "player_id"], how="left")
    got = got.join(ranges.apply(got.dropna(subset=["model"]), lines if lines is not None else ranges.load()))
    got["p_play"] = play_probability(got, news, aug, staging)
    got["if_plays"] = got["model"]
    got["projection"] = got["p_play"] * got["model"]
    got["low"] = mixture_quantile(got["p_play"], got["model"], got["model_lo"], got["model_hi"], ranges.LOW)
    got["high"] = mixture_quantile(got["p_play"], got["model"], got["model_lo"], got["model_hi"], ranges.HIGH)
    keep = ["season", "week", "player_id", "p_play", "if_plays", "projection", "low", "high"]
    return pool.merge(got[keep], on=["season", "week", "player_id"], how="left")


def play_probability(rows: pd.DataFrame, news: pd.DataFrame, player_games: pd.DataFrame,
                     staging: Path) -> np.ndarray:
    """P(records a stat) for each offensive row (`atlas/dfs/participation.py`); 1 for a defense.

    Fitted on every depth-chart listing before this week, so the season in
    progress counts: a rookie who has started playing is known to."""
    r = rows.merge(news[["season", "week", "player_id", "status", "depth_rank", "is_qb1"]],
                   on=["season", "week", "player_id"], how="left")
    history = participation.table(staging=staging)
    first = r[["season", "week"]].min()
    before = history[participation._order(history["season"], history["week"]) <
                     participation._order(first["season"], first["week"])]
    fitted = participation.fit(before)
    offense = r["position"] != "DST"
    p = np.ones(len(r))
    if offense.any():
        p[offense.to_numpy()] = participation.predict(fitted, participation.features(r[offense], player_games))
    return p


def mixture_quantile(p, if_plays, low, high, level: float) -> np.ndarray:
    """A quantile of "0 with probability 1 - p, else the player's own range".

    The mixture's quantile at ``level`` is the conditional one at
    (level - (1 - p)) / p, or zero below that. The conditional quantiles
    between the 10th and 90th are read off the line through the projection
    (taken as the middle) and the range's ends - an approximation, stated."""
    p = np.asarray(p, dtype=float)
    mid, lo, hi = (np.asarray(x, dtype=float) for x in (if_plays, low, high))
    with np.errstate(divide="ignore", invalid="ignore"):
        cond = (level - (1 - p)) / p
    span = ranges.HIGH - 0.5
    up = mid + (hi - mid) * (cond - 0.5) / span
    down = mid + (mid - lo) * (cond - 0.5) / (0.5 - ranges.LOW)
    q = np.where(cond >= 0.5, up, down)
    return np.where(cond <= 0, 0.0, q)


def lineups(projected: pd.DataFrame, opts: op.Options = OWNER) -> list[pd.DataFrame]:
    """The owner's lineups from the playable part of the pool."""
    ok = projected["status"].fillna("").astype(str).str.upper().isin(PLAYABLE) & ~projected["disabled"].astype(bool)
    p = projected[ok].dropna(subset=["projection"])
    p = p.assign(id=p["player_id_dk"], draftable_id=p["draftable_id"])
    return op.optimize(p, opts)


def run(label: str = "Main", *, capture: bool = False, now: datetime | None = None) -> Path:
    from atlas.live.store import Store

    store = Store.open()
    if capture:
        from atlas.sources import draftkings

        draftkings.capture(store)
    slate = choose_slate(store.read("dfs_slates"), label, now)
    group = int(slate["draft_group_id"])
    pool = store.read("dfs_salaries")
    pool = pool[pool["draft_group_id"] == group].rename(columns={"player_id": "player_id_dk"})
    if pool["draftable_id"].isna().all():
        raise LookupError("the record has no draftable ids for this slate; run with --capture")
    raw = config.paths().raw
    pool = with_games(pool, pd.read_parquet(nflverse.schedules_path(raw)))
    master_path = nflverse.players_path(raw)
    master = pd.read_parquet(master_path) if master_path.exists() else None
    pg = pd.read_parquet(config.paths().staging / "nfl" / "dfs_player_games.parquet")
    pool = match(pool, pg, master)
    projected = project(pool)
    out = out_dir(group)
    out.mkdir(parents=True, exist_ok=True)
    cols = ["name", "position", "team", "opponent", "salary", "status", "projection", "low", "high", "p_play",
            "if_plays", "matched_by",
            "player_id", "player_id_dk", "draftable_id", "game_start"]
    projected.sort_values("projection", ascending=False)[cols].to_csv(out / "projections.csv", index=False,
                                                                      float_format="%.2f")
    built = lineups(projected)
    (out / "lineups_upload.csv").write_text(op.upload_csv(built))
    readable = pd.concat([lu.assign(lineup=i + 1) for i, lu in enumerate(built)])
    readable[["lineup", "slot", "name", "team", "salary", "projection", "low", "high"]].to_csv(
        out / "lineups.csv", index=False, float_format="%.2f")
    unmatched = int((projected["matched_by"] == "none (no history)").sum())
    LOG.info("%s slate %d: %d players projected (%d without history), %d lineups -> %s", label, group,
             int(projected["projection"].notna().sum()), unmatched, len(built), out)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Project a DraftKings Classic slate and build lineups")
    parser.add_argument("--label", default="Main")
    parser.add_argument("--capture", action="store_true", help="capture DraftKings' pools first")
    args = parser.parse_args()
    run(args.label, capture=args.capture)


if __name__ == "__main__":
    main()
