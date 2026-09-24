"""College DFS: the private live record - what was projected, and what happened.

    python -m atlas.dfs.cfb_record          # the record's summary (needs ATLAS_OWNER_KEY)

Step 6 of `docs/MODEL_PLAN_DFS_CFB.md` is a decision - whether college
projections go public - and it is made from this record. Every priced
college player with a game is kept, one row per (game, DraftKings player),
rewritten by each heavy refresh until his game kicks off and never after:
the record is the projection the owner could have used, not one revised
once games were played.

College projections are the owner's, so the record is too. It lives in
``tracking/dfs_cfb_record/``, one file per week, compressed and sealed with
the owner key the same way as the owner page (`atlas/dfs/owner.py`), and is
committed with the rest of the tracking store, which is its backup. A week's
file is rewritten only while its games are to come, so the repository grows
by one small file a week, not a new copy of the season each day. Nothing
readable is written anywhere that is kept. A record the key cannot open -
the key was changed - is left exactly as it is and nothing is added to it.

After the games, each row is graded against the DraftKings points ESPN's box
score gives him: zero for a player who recorded nothing (the projection is
an expectation that includes the chance of not playing). A player with no
record when projected is found in the box score by name and team.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from atlas.dfs import cfb
from atlas.dfs import cfb_players as cp
from atlas.owner import sealed
from atlas.owner.sealed import Unreadable
from atlas.util import get_logger

LOG = get_logger(__name__)

COLUMNS = ["event", "season", "week", "game_start", "player_id_dk", "player_id", "matched_by", "name", "position",
           "team", "espn_team", "salary", "projection", "low", "high", "p_play", "if_plays", "projected_at"]
KEY = ["event", "player_id_dk"]


def path() -> Path:
    from atlas.live.store import tracking_dir

    return tracking_dir() / "dfs_cfb_record"


def projections_path() -> Path:
    """This refresh's college projections, readable, for the record to take in. Never kept."""
    from atlas.dfs import slate

    return slate.index_path().parent / "cfb_projections.csv"


def load(passphrase: str, where: Path | None = None) -> pd.DataFrame:
    """The record, opened; empty when there is none yet."""
    rows = sealed.load(where or path(), passphrase)
    if not rows:
        return pd.DataFrame(columns=COLUMNS)
    return pd.DataFrame(rows, columns=COLUMNS).astype({"event": str, "player_id": str})


def merge(record: pd.DataFrame, fresh: pd.DataFrame, now: datetime) -> tuple[pd.DataFrame, set]:
    """Fresh projections replace a row only while its game has not started;
    returns the record and the (season, week)s this refresh wrote to."""
    fresh = fresh.dropna(subset=["event", "projection"]).astype({"event": str, "player_id": str})
    start = pd.to_datetime(fresh["game_start"], utc=True, errors="coerce")
    fresh = fresh[start > pd.Timestamp(now)]
    if fresh.empty:
        return record.reset_index(drop=True), set()
    fresh = fresh.assign(projected_at=now.replace(microsecond=0).isoformat())
    for c in ("projection", "low", "high", "if_plays"):
        fresh[c] = fresh[c].astype(float).round(2)
    fresh["p_play"] = fresh["p_play"].astype(float).round(3)
    fresh = fresh.drop_duplicates(KEY, keep="last").reindex(columns=COLUMNS)
    # Only games still to come are in ``fresh``: a row whose game has started is never replaced.
    old = record.set_index(KEY)
    kept = old[~old.index.isin(fresh.set_index(KEY).index)].reset_index()
    parts = [kept.reindex(columns=COLUMNS), fresh] if len(kept) else [fresh]
    merged = pd.concat(parts, ignore_index=True).sort_values(["game_start", "event", "player_id_dk"])
    weeks = {(int(a), int(b)) for a, b in fresh[["season", "week"]].drop_duplicates().itertuples(index=False)}
    return merged.reset_index(drop=True), weeks


def seal(record: pd.DataFrame, passphrase: str, weeks: set, where: Path | None = None) -> list[Path]:
    """The given weeks' rows, compressed and sealed, one file each."""
    where = where or path()
    written = []
    for season, week in sorted(weeks):
        part = record[(record["season"].astype(int) == season) & (record["week"].astype(int) == week)]
        rows = json.loads(part.reindex(columns=COLUMNS).to_json(orient="records"))
        written.append(sealed.seal(rows, passphrase, sealed.week_file(where, season, week),
                                   names=[r["name"] for r in rows]))
    return written


def update(passphrase: str, *, now: datetime | None = None, table: pd.DataFrame | None = None,
           where: Path | None = None) -> dict:
    """Take in this refresh's projections, grade what has been played, and
    return the summary for the owner page. Never raises."""
    now = now or datetime.now(timezone.utc)
    try:
        record = load(passphrase, where)
    except Unreadable as error:
        LOG.error("college record: the owner key does not open it (%s); left as it is", error)
        return {"games": 0, "note": "The college record could not be opened with this key."}
    try:
        fresh_path = projections_path()
        if fresh_path.exists():
            record, weeks = merge(record, pd.read_csv(fresh_path, dtype={"event": str, "player_id": str}), now)
            if weeks:
                seal(record, passphrase, weeks, where)
                LOG.info("college record: %d rows; week(s) %s written", len(record), sorted(weeks))
        if table is None:
            table = pd.read_parquet(cp.path()) if cp.path().exists() else None
        return summary(graded(record, table)) if table is not None else {"games": 0}
    except Exception as error:  # noqa: BLE001
        LOG.error("college record not updated: %s", type(error).__name__)
        return {"games": 0}


def graded(record: pd.DataFrame, table: pd.DataFrame) -> pd.DataFrame:
    """Rows whose game is in the box scores, with the points he scored."""
    if record.empty:
        return record.assign(actual=pd.Series(dtype=float))
    played = set(table["event"].astype(str))
    g = record[record["event"].astype(str).isin(played)].copy()
    if g.empty:
        return g.assign(actual=pd.Series(dtype=float))
    box = table[table["event"].astype(str).isin(played)][["event", "player_id", "team", "name", "dk_points"]]
    box = box.assign(event=box["event"].astype(str), player_id=box["player_id"].astype(str))
    by_id = box.drop_duplicates(["event", "player_id"]).set_index(["event", "player_id"])["dk_points"]
    g["actual"] = [by_id.get((e, p), np.nan) for e, p in zip(g["event"], g["player_id"], strict=True)]
    # No record when projected: found by name and team in the game's box score.
    named = box.assign(key=box["name"].map(cfb.norm_name)).drop_duplicates(["event", "team", "key"], keep=False)
    by_name = named.set_index(["event", "team", "key"])["dk_points"]
    missing = g["actual"].isna()
    g.loc[missing, "actual"] = [by_name.get((e, t, cfb.norm_name(n)), np.nan) for e, t, n in
                                zip(g.loc[missing, "event"], g.loc[missing, "espn_team"], g.loc[missing, "name"],
                                    strict=True)]
    g["actual"] = g["actual"].fillna(0.0)             # recorded nothing: DraftKings scores him zero
    return g


def regulars(g: pd.DataFrame) -> pd.DataFrame:
    """Each team's top projected quarterback, two running backs, three receivers and kicker."""
    depth = g.groupby(["event", "espn_team", "position"])["projection"].rank(ascending=False, method="first")
    return g[depth <= g["position"].map(cp.DEPTH).fillna(0)]


def _numbers(g: pd.DataFrame) -> dict:
    if g.empty:
        return {"players": 0}
    inside = (g["actual"] >= g["low"]) & (g["actual"] <= g["high"])
    ranks = []
    for _, s in g.groupby(["season", "week", "position"]):
        if len(s) >= 5 and s["projection"].nunique() > 1:
            ranks.append(s["projection"].rank().corr(s["actual"].rank()))
    return {"players": len(g), "mae": float(np.mean(np.abs(g["actual"] - g["projection"]))),
            "coverage": float(inside.mean()), "rank": float(np.nanmean(ranks)) if ranks else float("nan")}


def summary(g: pd.DataFrame) -> dict:
    """The record in a few numbers: every priced player, and each team's regulars."""
    if g.empty:
        return {"games": 0}
    return {"games": int(g["event"].nunique()), "weeks": int(g[["season", "week"]].drop_duplicates().shape[0]),
            "all": _numbers(g), "regulars": _numbers(regulars(g))}


def main() -> None:
    argparse.ArgumentParser(description="The private college DFS record's summary").parse_args()
    from atlas.dfs import owner

    passphrase = os.environ.get(owner.SECRET, "")
    if not passphrase.strip():
        raise SystemExit(f"{owner.SECRET} is not set")
    print(json.dumps(summary(graded(load(passphrase), pd.read_parquet(cp.path()))), indent=1))


if __name__ == "__main__":
    main()
