"""The NHL's numbers for the games ahead: the stored model walked to today, each game gridded.

    python -m atlas.models.nhl_projection      # the next eight days' games, to the terminal

Step 6 of `docs/MODEL_PLAN_NHL.md`. The heavy refresh calls :func:`publish`,
which walks the state (`nhl_state.py`) through every completed game with the
choices tuned in ``reports/nhl_model.json`` - nothing is refitted here - and
prices every scheduled game in the horizon through its season's grid
(`nhl_grid.py`). A season the stored choices have no layers for (a new one)
gets them fitted from the three before it, and saved.

Each row keeps what a later price needs: both sides' expected goals, the
expected starter's goals saved and each candidate goalie's with the chance he
starts, so a confirmed starter re-prices the game without the walk
(:func:`reprice`).

Beside the projections, :func:`history` gives the walk-forward forecast for
every completed game, the record the card's grade and the owner board's
calibration read.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from atlas import config
from atlas.models import nhl_grid as grid
from atlas.models import nhl_model
from atlas.models import nhl_state as st
from atlas.util import get_logger

LOG = get_logger(__name__)

HORIZON = timedelta(days=8)
LINES = (4.5, 5.5, 6.5, 7.5)


def choices(root: Path | None = None) -> dict | None:
    p = nhl_model.json_path(root or config.paths().root)
    return json.loads(p.read_text()) if p.exists() else None


def _layers(stored: dict) -> grid.Layers:
    return grid.Layers.from_json(stored["layers"])


def walk(tables: dict, stored: dict) -> tuple[pd.DataFrame, st.Model, pd.DataFrame]:
    """The state walked through every game in the warehouse with the stored choices: (forecasts, the model
    as it stands now, the games)."""
    spec = st.Spec(**stored["spec"])
    model = st.Model.new(spec)
    model.home5, model.b2b = stored["terms"]["home5"], stored["terms"]["b2b"]
    games = nhl_model.games_frame(tables["games"])
    completed = games[games["completed"].astype(bool)]
    f, model = st.walk(completed, tables["team_games"], tables["goalie_games"], spec, model=model)
    return f, model, games


def ensure_layers(stored: dict, tables: dict, forecasts: pd.DataFrame, games: pd.DataFrame, seasons,
                  root: Path | None = None) -> grid.Layers:
    """The stored layers, with any season asked for that has none fitted from the three before it and saved."""
    layers = _layers(stored)
    missing = [int(s) for s in seasons if int(s) not in layers.by_season]
    if missing:
        lam = forecasts.set_index("game_id")[["lambda_home", "lambda_away", "home_edge"]]
        fresh = grid.fit(tables["goals"], games, lam, missing)
        layers.by_season.update(fresh.by_season)
        stored["layers"] = layers.to_json()
        nhl_model.json_path(root or config.paths().root).write_text(json.dumps(stored, indent=1) + "\n")
        LOG.info("nhl projection: layers fitted for %s", ", ".join(str(s) for s in sorted(fresh.by_season)))
    return layers


def _goalies(model: st.Model, team: str, day: pd.Timestamp, names: dict) -> list[dict]:
    """The team's candidate starters: the chance each starts and his goals saved per 60."""
    out = []
    for g, p in sorted(model.starter_probs(team, day).items(), key=lambda kv: -kv[1]):
        k = model.goalies.index.get(g)
        out.append({"id": int(g), "name": names.get(int(g)), "p": round(float(p), 4),
                    "gsax": round(float(model.goalies.x[k]), 4) if k is not None else 0.0})
    return out


def row(model: st.Model, layer: grid.Season, game, day: pd.Timestamp, names: dict,
        home_starter=None, away_starter=None) -> dict:
    """One game priced: expected goals, the grid's probabilities, the goalies behind them."""
    e = model.expect(game.home_team, game.away_team, day, home_b2b=bool(game.home_b2b), away_b2b=bool(game.away_b2b),
                     home_starter=home_starter, away_starter=away_starter)
    s = grid.summary(e["lambda_home"], e["lambda_away"], layer, lines=LINES, edge=e["home_edge"])
    top = s.pop("top")
    s.pop("grid")
    return {"game_id": int(game.game_id), "espn_id": _int(getattr(game, "espn_id", None)), "season": int(game.season),
            "kickoff": pd.Timestamp(game.kickoff).isoformat(), "home_team": game.home_team, "away_team": game.away_team,
            "home_b2b": bool(game.home_b2b), "away_b2b": bool(game.away_b2b),
            **{k: _round(v) for k, v in e.items()}, **{k: _round(v) for k, v in s.items()},
            "top": json.dumps([[h, a, round(p, 4)] for h, a, p in top]),
            "home_goalies": json.dumps(_goalies(model, game.home_team, day, names)),
            "away_goalies": json.dumps(_goalies(model, game.away_team, day, names))}


def _round(v):
    return round(float(v), 4) if isinstance(v, (int, float, np.floating)) else v


def _int(v):
    try:
        return None if v is None or pd.isna(v) else int(v)
    except (TypeError, ValueError):
        return None


def project(tables: dict, stored: dict, now: datetime, *, root: Path | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(the projections for the games ahead, the walk-forward forecasts of every completed game)."""
    forecasts, model, games = walk(tables, stored)
    kick = pd.to_datetime(games["kickoff"], utc=True)
    ahead = games[(~games["completed"].astype(bool)) & (kick > pd.Timestamp(now)) & (kick <= pd.Timestamp(now) + HORIZON)]
    seasons = set(ahead["season"].unique()) | set(games.loc[games["completed"].astype(bool), "season"].unique())
    layers = ensure_layers(stored, tables, forecasts, games, seasons, root)
    names = _names(tables)
    rows = []
    for game in ahead.itertuples(index=False):
        day = pd.Timestamp(game.kickoff).tz_convert("America/New_York").normalize()
        rows.append(row(model, layers.get(int(game.season)), game, day, names))
    history = nhl_model.with_grid(forecasts.merge(
        games[["game_id", "season", "season_type", "kickoff", "home_team", "away_team", "completed", "home_score",
               "away_score", "reg_home", "reg_away", "decision"]], on="game_id", how="left"), layers)
    return pd.DataFrame(rows), history.drop(columns=["_tcdf", "_mcdf"], errors="ignore")


def _names(tables: dict) -> dict:
    g = tables["goalie_games"]
    return dict(zip(g["player_id"].astype(int), g["name"], strict=False)) if "name" in g else {}


def reprice(projection: dict, layer: grid.Season, *, home_starter: int | None = None,
            away_starter: int | None = None) -> dict:
    """A projection with a confirmed starter in place of the expected one: each side's expected goals move by
    the gap between the expected goalie's goals saved and the confirmed one's, and the grid is read again."""
    lh, la = float(projection["lambda_home"]), float(projection["lambda_away"])
    for side, starter, other in (("away", away_starter, "home"), ("home", home_starter, "away")):
        if starter is None:
            continue
        pool = {g["id"]: g for g in json.loads(projection[f"{side}_goalies"])}
        confirmed = pool.get(int(starter), {"gsax": 0.0})["gsax"]
        shift = float(projection[f"goalie_{side}"]) - confirmed          # the other side scores this much more
        if other == "home":
            lh = max(lh + shift, 0.3)
        else:
            la = max(la + shift, 0.3)
    s = grid.summary(lh, la, layer, lines=LINES, edge=float(projection.get("home_edge", 0.0)))
    s.pop("grid")
    top = s.pop("top")
    return {**projection, **{k: _round(v) for k, v in s.items()},
            "top": json.dumps([[h, a, round(p, 4)] for h, a, p in top]),
            "home_starter": home_starter, "away_starter": away_starter}


# ---------------------------------------------------------------------------
# The heavy refresh's step
# ---------------------------------------------------------------------------

VERSION = "nhl-v1"


def market_home(ml_home, ml_away) -> np.ndarray:
    """The home side's probability from both moneyline prices, the margin taken out."""
    from atlas.models.nhl_benchmarks import implied

    h, a = implied(ml_home), implied(ml_away)
    return h / (h + a)


def closes(snapshots: pd.DataFrame, games: pd.DataFrame) -> pd.DataFrame:
    """ESPN's last DraftKings moneyline before puck drop per NHL game in the tracking store: (game_id, p_market)."""
    if snapshots.empty or games.empty:
        return pd.DataFrame(columns=["game_id", "p_market"])
    g = games[games["sport"].astype(str) == "nhl"] if "sport" in games else games.iloc[0:0]
    ml = snapshots[(snapshots["market"] == "moneyline") & snapshots["game_id"].isin(g["game_id"])].copy()
    if ml.empty:
        return pd.DataFrame(columns=["game_id", "p_market"])
    kick = pd.to_datetime(g.set_index("game_id")["kickoff"], utc=True, errors="coerce")
    ml["t"] = pd.to_datetime(ml["captured_at"], utc=True, errors="coerce")
    ml = ml[ml["t"] <= ml["game_id"].map(kick)].sort_values("t").groupby("game_id").tail(1)
    ml = ml.dropna(subset=["price", "other_price"])
    return pd.DataFrame({"game_id": ml["game_id"].astype("int64"),
                         "p_market": market_home(ml["price"], ml["other_price"])})


def week_of(kickoff: pd.Series, season: pd.Series) -> pd.Series:
    """Weeks since each season's first puck drop, from 1: the grade's early-season test reads it."""
    k = pd.to_datetime(kickoff, utc=True)
    first = k.groupby(season).transform("min")
    return ((k - first).dt.days // 7 + 1).astype(int)


def calibration(history: pd.DataFrame, market: pd.DataFrame) -> pd.DataFrame:
    """The grade's record: each completed game with a closing price, Atlas's side against the market's
    (percentage points of win probability), what Atlas claimed for it and whether it won."""
    cols = ["game_id", "sport", "season", "week", "season_type", "market", "abs_edge", "claimed", "won", "kickoff"]
    h = history[history["completed"].astype(bool)].merge(market, on="game_id", how="inner")
    if h.empty:
        return pd.DataFrame(columns=cols)
    edge = h["p_home"] - h["p_market"]
    home = edge >= 0
    won_home = h["home_score"] > h["away_score"]
    return pd.DataFrame({
        "game_id": h["game_id"], "sport": "nhl", "season": h["season"], "week": week_of(h["kickoff"], h["season"]),
        "season_type": h["season_type"], "market": "moneyline", "abs_edge": (100 * edge.abs()).round(3),
        "claimed": np.where(home, h["p_home"], 1 - h["p_home"]).round(4),
        "won": np.where(home, won_home, ~won_home).astype(int),
        "kickoff": pd.to_datetime(h["kickoff"], utc=True).dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
    })[cols]


def publish(store, now: datetime, *, tables: dict | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """The rows the heavy refresh stores: (``nhl_projections`` keyed by ESPN's event id, the ``calibration``
    rows). The archive's closes grade 2010-11 to 2022-23; the tracking store's DraftKings closes the seasons
    since, as they are played."""
    stored = choices()
    if stored is None:
        raise FileNotFoundError("reports/nhl_model.json")
    tables = tables or nhl_model.load_tables()
    rows, history = project(tables, stored, now)
    stamp = now.replace(microsecond=0).isoformat()
    if len(rows):
        rows = rows.dropna(subset=["espn_id"]).rename(columns={"game_id": "nhl_game_id", "espn_id": "game_id"})
        rows = rows.assign(game_id=rows["game_id"].astype("int64"), model_version=VERSION, refreshed_at=stamp)
    archive = tables["odds"].dropna(subset=["home_ml_close", "away_ml_close"])
    market = pd.DataFrame({"game_id": archive["game_id"].astype("int64"),
                           "p_market": market_home(archive["home_ml_close"], archive["away_ml_close"])})
    espn = tables["games"].dropna(subset=["espn_id"])
    live = closes(store.read("snapshots"), store.read("games"))
    if len(live):
        to_nhl = dict(zip(espn["espn_id"].astype("int64"), espn["game_id"].astype("int64"), strict=True))
        live = live.assign(game_id=live["game_id"].map(to_nhl)).dropna(subset=["game_id"])
        market = pd.concat([market, live.assign(game_id=live["game_id"].astype("int64"))], ignore_index=True)
    # The first three seasons' grids were fitted on themselves (the burn-in): never in the record.
    history = history[history["season"] >= grid.FIRST + grid.WINDOW]
    cal = calibration(history, market.drop_duplicates("game_id", keep="last"))
    # The record keys a game by ESPN's id where there is one, as the rest of the store does.
    to_espn = dict(zip(espn["game_id"].astype("int64"), espn["espn_id"].astype("int64"), strict=True))
    cal["game_id"] = [to_espn.get(int(g), int(g)) for g in cal["game_id"]]
    return rows, cal


def main() -> None:
    argparse.ArgumentParser(description="The NHL's numbers for the games ahead").parse_args()
    stored = choices()
    if stored is None:
        raise SystemExit("no reports/nhl_model.json: run `make nhl-model` first")
    rows, _ = project(nhl_model.load_tables(), stored, datetime.now(UTC))
    cols = ["kickoff", "away_team", "home_team", "lambda_away", "lambda_home", "p_home", "p_ot", "total_mean",
            "p_over_5.5", "p_over_6.5", "p_home_minus_1_5", "p_away_minus_1_5"]
    with pd.option_context("display.width", 220, "display.max_rows", 200):
        print(rows[cols].to_string(index=False) if len(rows) else "no NHL games in the horizon")


if __name__ == "__main__":
    main()
