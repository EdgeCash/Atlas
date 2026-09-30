"""Assemble the NHL warehouse: ``data/warehouse/nhl.duckdb``.

    python -m atlas.staging.nhl.build              # 2010-11 to the current season
    python -m atlas.staging.nhl.build --seasons 2024 2025

Tables:

* ``games``         - one row per game (`games.py`): the final, the regulation
                      score, how it was decided, rest, ESPN's id;
* ``goals``         - every goal: when, by which side, in what state, with
                      the score before it (the grid's late-game layer reads it);
* ``team_games``    - per team-game, for and against: goals, shots on goal,
                      unblocked and all attempts and expected goals in each
                      strength state, the seconds spent in it, and penalties
                      taken and drawn;
* ``goalie_games``  - per goalie-game: started, shots and goals against,
                      saves, ice time, and the expected goals of the unblocked
                      attempts faced (goals saved above expected);
* ``skater_games``  - the game logs, the team by franchise code;
* ``odds``          - the archive's closing lines on each game it has.

Every row is a fact about a finished game or the schedule. What a projection
may see before puck drop is decided by the model, which only ever reads games
before the one it prices.

Every shot attempt with its geometry, state, outcome and expected goals from
its season's coefficients (``reports/nhl_xg.json``, `atlas/models/nhl_xg.py`)
is written to ``data/staging/nhl/shots.parquet`` rather than the warehouse:
two and a half million rows nothing reads at run time, rebuilt from the raw
cache in seconds, and kept out of the cached warehouse.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from atlas import config
from atlas.sources import nhl
from atlas.staging.nhl import games as games_stage
from atlas.staging.nhl import shots as shots_stage
from atlas.util import get_logger, write_parquet

LOG = get_logger(__name__)

STRENGTHS = shots_stage.STRENGTHS
#: Each state seen from the other side: a power play is the other team's short-handed time.
MIRROR = {"5v5": "5v5", "PP": "SH", "SH": "PP", "EV": "EV", "EN": "ENA", "ENA": "EN"}
COUNTS = {"goals": "goal", "sog": "on_target", "fenwick": "unblocked", "corsi": "attempt"}


def warehouse_path(warehouse: Path | None = None) -> Path:
    return (warehouse or config.paths().warehouse) / "nhl.duckdb"


def shots_path(staging: Path | None = None) -> Path:
    return (staging or config.paths().staging) / "nhl" / "shots.parquet"


def load_shots() -> pd.DataFrame:
    """Every shot attempt, staged by the last build."""
    return pd.read_parquet(shots_path())


def team_games(shots: pd.DataFrame, toi: pd.DataFrame, games: pd.DataFrame, penalties: pd.DataFrame) -> pd.DataFrame:
    """Per team-game, for and against, by strength state."""
    s = shots.assign(attempt=True)
    if "xg" not in s:
        s["xg"] = np.nan
    agg = {f"{name}": (col, "sum") for name, col in COUNTS.items()}
    agg["xg"] = ("xg", "sum")
    long = s.groupby(["game_id", "shooting_team", "strength"]).agg(**agg).reset_index()
    wide = long.pivot_table(index=["game_id", "shooting_team"], columns="strength",
                            values=[*COUNTS, "xg"], aggfunc="sum", fill_value=0)
    wide = wide.reindex(columns=pd.MultiIndex.from_product([[*COUNTS, "xg"], list(STRENGTHS)]), fill_value=0)
    wide.columns = [f"{m}_{k}" for m, k in wide.columns]
    wide = wide.reset_index().rename(columns={"shooting_team": "team"})
    g = games.set_index("game_id")
    base = pd.concat([pd.DataFrame({"game_id": games["game_id"], "team": games["home_team"],
                                    "opponent": games["away_team"], "is_home": True}),
                      pd.DataFrame({"game_id": games["game_id"], "team": games["away_team"],
                                    "opponent": games["home_team"], "is_home": False})], ignore_index=True)
    base = base[base["game_id"].map(g["completed"]).fillna(False).astype(bool)]
    out = base.merge(wide, on=["game_id", "team"], how="left")
    # Against: the opponent's for, in the mirrored state.
    against = wide.rename(columns={"team": "opponent"})
    renamed = {f"{m}_{k}": f"{m}a_{MIRROR[k]}" for m in [*COUNTS, "xg"] for k in STRENGTHS}
    out = out.merge(against.rename(columns=renamed), on=["game_id", "opponent"], how="left")
    out = out.merge(toi, on=["game_id", "team"], how="left")
    out = out.merge(penalties, on=["game_id", "team"], how="left")
    opp_pen = penalties.rename(columns={"team": "opponent", "penalties": "drawn", "pim": "pim_drawn"})
    out = out.merge(opp_pen, on=["game_id", "opponent"], how="left")
    numeric = [c for c in out.columns if c not in ("game_id", "team", "opponent", "is_home")]
    out[numeric] = out[numeric].fillna(0)
    goals = games.set_index("game_id")
    home = out["is_home"]
    out["goals_for"] = np.where(home, out["game_id"].map(goals["home_goals"]), out["game_id"].map(goals["away_goals"]))
    out["goals_against"] = np.where(home, out["game_id"].map(goals["away_goals"]),
                                    out["game_id"].map(goals["home_goals"]))
    out["season"] = out["game_id"].map(goals["season"])
    out["kickoff"] = out["game_id"].map(goals["kickoff"])
    out["season_type"] = out["game_id"].map(goals["season_type"])
    return out.sort_values(["kickoff", "game_id", "team"], kind="stable").reset_index(drop=True)


def penalties(raw_shots: pd.DataFrame, code: dict[int, str]) -> pd.DataFrame:
    """Penalties taken per team-game: the count that put a man in the box (minors, doubles, majors) and
    the minutes. The event's owner is the penalised side."""
    p = raw_shots[raw_shots["event"] == "penalty"].copy()
    if p.empty:
        return pd.DataFrame(columns=["game_id", "team", "penalties", "pim"])
    p["team"] = p["team_id"].map(code)
    p["counts"] = p["penalty_type"].isin(["MIN", "BEN", "MAJ"]).astype(int)
    return p.groupby(["game_id", "team"]).agg(penalties=("counts", "sum"),
                                               pim=("penalty_minutes", "sum")).reset_index()


def goalie_games(goalies: pd.DataFrame, shots: pd.DataFrame, games: pd.DataFrame, code: dict[str, str]) -> pd.DataFrame:
    """Per goalie-game: the log, and the expected goals of the unblocked attempts faced."""
    g = goalies.copy()
    g["team"] = g["team"].map(lambda c: code.get(c, c))
    g["opponent"] = g["opponent"].map(lambda c: code.get(c, c))
    faced = shots[shots["unblocked"] & shots["goalie_id"].notna()]
    if "xg" in faced and faced["xg"].notna().any():
        per = faced.groupby(["game_id", "goalie_id"]).agg(unblocked_faced=("unblocked", "sum"),
                                                          xga=("xg", "sum"), ga_pbp=("goal", "sum")).reset_index()
    else:
        per = faced.groupby(["game_id", "goalie_id"]).agg(unblocked_faced=("unblocked", "sum"),
                                                          ga_pbp=("goal", "sum")).reset_index()
        per["xga"] = np.nan
    per = per.rename(columns={"goalie_id": "player_id"})
    per["player_id"] = per["player_id"].astype("int64")
    out = g.merge(per, on=["game_id", "player_id"], how="left")
    out["gsax"] = out["xga"] - out["ga_pbp"]
    info = games.set_index("game_id")
    out["season"] = out["game_id"].map(info["season"])
    out["kickoff"] = out["game_id"].map(info["kickoff"])
    out["season_type"] = out["game_id"].map(info["season_type"])
    return out.sort_values(["kickoff", "game_id", "team"], kind="stable").reset_index(drop=True)


def odds(raw: Path, seasons: list[int], games: pd.DataFrame) -> pd.DataFrame:
    """The archive's lines on each game, matched by date and both teams by franchise."""
    o = games_stage.load(raw, "odds", seasons)
    if o.empty:
        return o
    o = o.assign(home=o["home"].map(nhl.franchise), away=o["away"].map(nhl.franchise))
    key = games.assign(d=games["date"].astype(str))[["game_id", "d", "home_team", "away_team"]]
    out = o.merge(key, left_on=["date", "home", "away"], right_on=["d", "home_team", "away_team"], how="left")
    missing = out["game_id"].isna()
    if missing.any():
        # The archive dates a late game by the Eastern date, a day on from the NHL's local one, or the reverse.
        for shift in (-1, 1):
            d = (pd.to_datetime(out.loc[missing, "date"]) + pd.Timedelta(days=shift)).dt.strftime("%Y-%m-%d")
            alt = out.loc[missing, ["home", "away"]].assign(d=d.to_numpy()).merge(
                key, left_on=["d", "home", "away"], right_on=["d", "home_team", "away_team"], how="left")
            out.loc[missing, "game_id"] = alt["game_id"].to_numpy()
            missing = out["game_id"].isna()
    LOG.info("nhl odds: %d of %d archive games matched", int(out["game_id"].notna().sum()), len(out))
    out = out.dropna(subset=["game_id"]).assign(game_id=lambda f: f["game_id"].astype("int64"))
    return out.drop(columns=["d", "home_team", "away_team"]).drop_duplicates("game_id")


def build(seasons: list[int] | None = None) -> dict[str, pd.DataFrame]:
    paths = config.paths().ensure()
    raw = paths.raw
    seasons = seasons or list(range(nhl.FIRST_SEASON, nhl.current_season() + 1))
    code_by_id = games_stage.codes(raw)
    games = games_stage.build_games(raw, seasons)
    skaters = games_stage.load(raw, "skater_games", seasons)
    goalies = games_stage.load(raw, "goalie_games", seasons)
    raw_shots = games_stage.load(raw, "shots", seasons)
    by_code = {c: nhl.franchise(c) for c in pd.concat([skaters.get("team", pd.Series(dtype=str)),
                                                       goalies.get("team", pd.Series(dtype=str))]).dropna().unique()}
    roster = shots_stage.rosters(skaters, goalies, by_code)
    shots = shots_stage.features(raw_shots, games, roster, code_by_id) if len(raw_shots) else pd.DataFrame()
    from atlas.models import nhl_xg

    # Each season's coefficients, a new season's fitted from the three before it the first time it appears.
    shots = nhl_xg.apply(shots, nhl_xg.ensure(shots, nhl_xg.load(paths.root), paths.root))
    toi = shots_stage.toi(games_stage.load(raw, "strength", seasons), games)
    teams = team_games(shots, toi, games, penalties(raw_shots, code_by_id)) if len(shots) else pd.DataFrame()
    goals = shots[shots["goal"]][["game_id", "season", "period", "seconds", "shooting_team", "is_home", "strength",
                                  "score_diff", "shooter_id", "goalie_id"]] if len(shots) else pd.DataFrame()
    tables = {
        "games": games, "goals": goals, "team_games": teams,
        "goalie_games": goalie_games(goalies, shots, games, by_code) if len(goalies) else pd.DataFrame(),
        "skater_games": skaters.assign(team=skaters["team"].map(lambda c: by_code.get(c, c)))
        if len(skaters) else skaters,
        "odds": odds(raw, seasons, games),
    }
    staging = paths.staging / "nhl"
    staging.mkdir(parents=True, exist_ok=True)
    write_parquet(games, staging / "games.parquet")
    if len(shots):
        write_parquet(shots, shots_path(paths.staging))
    db = warehouse_path(paths.warehouse)
    if db.exists():
        db.unlink()                      # rewritten whole: a dropped table leaves no pages behind
    con = duckdb.connect(str(db))
    try:
        for name, frame in tables.items():
            if frame is None or frame.empty:
                continue
            con.register("frame", frame)
            con.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM frame")
            con.unregister("frame")
    finally:
        con.close()
    LOG.info("nhl warehouse: %s", ", ".join(f"{k} {len(v):,}" for k, v in tables.items() if v is not None))
    return tables


def load(table: str, warehouse: Path | None = None) -> pd.DataFrame:
    """One table of the NHL warehouse."""
    db = warehouse_path(warehouse)
    if not db.exists():
        raise FileNotFoundError(db)
    con = duckdb.connect(str(db), read_only=True)
    try:
        return con.execute(f"SELECT * FROM {table}").df()
    finally:
        con.close()


def main() -> None:
    ap = argparse.ArgumentParser(description="Build the NHL warehouse")
    ap.add_argument("--seasons", type=int, nargs="*")
    args = ap.parse_args()
    try:
        build(args.seasons)
    except Exception as error:  # noqa: BLE001 - the NHL never fails the heavy refresh
        from atlas.util import where

        LOG.error("nhl warehouse not built: %s at %s", type(error).__name__, where(error))


if __name__ == "__main__":
    main()
