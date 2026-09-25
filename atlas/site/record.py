"""The public model record: every projection Atlas published before kickoff, against the final score.

The facts, and nothing chosen: each game's last projection made before its
kickoff (``tracking/projections.csv``, where a later model version adds a row
and never replaces one), the final score, how far the projection was from it,
and - where Atlas captured one - the market's number from before kickoff
(``tracking/snapshots.csv``, the last line before kickoff) and how far that
was. Every game with a projection and a final score is in it; none is left
out, and a game whose only projection was made after kickoff is counted as
not recorded rather than graded.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from atlas.util import get_logger

LOG = get_logger(__name__)

COLUMNS = ["sport", "season", "week", "game_id", "kickoff", "away", "home", "proj_away", "proj_home", "final_away",
           "final_home", "margin_miss", "total_miss", "winner_right", "market_margin", "market_total",
           "market_margin_miss", "market_total_miss", "model_version", "projected_at"]


def before_kickoff(projections: pd.DataFrame) -> pd.DataFrame:
    """Each game's last projection made before its kickoff."""
    if projections.empty:
        return projections
    p = projections.assign(sport=projections["sport"].fillna("ncaaf"))
    kick = pd.to_datetime(p["kickoff"], utc=True, errors="coerce")
    made = pd.to_datetime(p["refreshed_at"], utc=True, errors="coerce")
    p = p[made < kick].assign(_made=made[made < kick])
    return p.sort_values("_made").groupby(["sport", "game_id"], as_index=False).last().drop(columns="_made")


def finals(research: pd.DataFrame | None, nfl: pd.DataFrame | None, games: pd.DataFrame) -> pd.DataFrame:
    """Final home and away points per game: the warehouses', else the tracking store's completed games."""
    parts = []
    for frame in (research, nfl):
        if frame is not None and len(frame):
            f = frame.dropna(subset=["actual_margin", "actual_total"])
            parts.append(pd.DataFrame({"game_id": f["game_id"].astype(str),
                                       "final_home": (f["actual_total"] + f["actual_margin"]) / 2,
                                       "final_away": (f["actual_total"] - f["actual_margin"]) / 2}))
    if len(games):
        g = games[games["completed"].astype("string").str.lower().isin(["true", "1"])].dropna(
            subset=["home_score", "away_score"])
        parts.append(pd.DataFrame({"game_id": g["game_id"].astype(str), "final_home": g["home_score"].astype(float),
                                   "final_away": g["away_score"].astype(float)}))
    if not parts:
        return pd.DataFrame(columns=["game_id", "final_home", "final_away"])
    return pd.concat(parts, ignore_index=True).drop_duplicates("game_id", keep="first")


def market(snapshots: pd.DataFrame, games: pd.DataFrame) -> pd.DataFrame:
    """The market's home margin and total from its last line before kickoff, per game."""
    from atlas.live.grade import closing_lines

    if snapshots.empty or games.empty:
        return pd.DataFrame(columns=["game_id", "market_margin", "market_total"])
    closes = closing_lines(snapshots, games)
    wide = closes.groupby(["game_id", "market"])["close_line"].median().unstack()
    out = pd.DataFrame({"game_id": wide.index.astype(str)})
    out["market_margin"] = wide["margin"].to_numpy() if "margin" in wide else np.nan
    out["market_total"] = wide["total"].to_numpy() if "total" in wide else np.nan
    return out


def graded(projections: pd.DataFrame, finals_: pd.DataFrame, market_: pd.DataFrame,
           names: dict | None = None) -> pd.DataFrame:
    """One row per game with a projection made before kickoff and a final score."""
    p = before_kickoff(projections)
    if p.empty:
        return pd.DataFrame(columns=COLUMNS)
    p = p.assign(game_id=p["game_id"].astype(str)).merge(finals_, on="game_id", how="inner")
    p = p.merge(market_, on="game_id", how="left")
    fm = p["final_home"] - p["final_away"]
    ft = p["final_home"] + p["final_away"]
    pm = p["margin_mean"].astype(float)
    out = pd.DataFrame({
        "sport": p["sport"], "season": p["season"], "week": p["week"], "game_id": p["game_id"],
        "kickoff": p["kickoff"],
        "away": [(names or {}).get(g, (None, None))[1] for g in p["game_id"]],
        "home": [(names or {}).get(g, (None, None))[0] for g in p["game_id"]],
        "proj_away": p["away_mean"].astype(float).round(1), "proj_home": p["home_mean"].astype(float).round(1),
        "final_away": p["final_away"].astype(int), "final_home": p["final_home"].astype(int),
        "margin_miss": (pm - fm).abs().round(1), "total_miss": (p["total_mean"].astype(float) - ft).abs().round(1),
        # The side Atlas had ahead won; a tie in either is not counted as right.
        "winner_right": np.where((fm == 0) | (pm == 0), np.nan, (np.sign(pm) == np.sign(fm)).astype(float)),
        "market_margin": p["market_margin"], "market_total": p["market_total"],
        "market_margin_miss": (p["market_margin"] - fm).abs().round(1),
        "market_total_miss": (p["market_total"] - ft).abs().round(1),
        "model_version": p["model_version"], "projected_at": p["refreshed_at"],
    })
    return out.sort_values(["kickoff", "game_id"], ascending=[False, True]).reset_index(drop=True)


def summary(g: pd.DataFrame) -> dict:
    """A sport's record in a few numbers; the market's only on the games it has a number for."""
    if g.empty:
        return {"games": 0}
    both = g.dropna(subset=["market_margin_miss"])
    both_t = g.dropna(subset=["market_total_miss"])
    closer = both[both["margin_miss"] != both["market_margin_miss"]]
    return {
        "games": len(g), "margin_miss": float(g["margin_miss"].mean()), "total_miss": float(g["total_miss"].mean()),
        "winner_right": float(g["winner_right"].mean()), "winner_games": int(g["winner_right"].notna().sum()),
        "with_market": len(both), "atlas_margin_miss_there": float(both["margin_miss"].mean()) if len(both) else None,
        "market_margin_miss": float(both["market_margin_miss"].mean()) if len(both) else None,
        "with_market_total": len(both_t),
        "atlas_total_miss_there": float(both_t["total_miss"].mean()) if len(both_t) else None,
        "market_total_miss": float(both_t["market_total_miss"].mean()) if len(both_t) else None,
        "atlas_closer": int((closer["margin_miss"] < closer["market_margin_miss"]).sum()),
        "closer_of": len(closer),
    }


def weekly(g: pd.DataFrame) -> pd.DataFrame:
    return g.groupby(["season", "week"], as_index=False).agg(
        games=("game_id", "size"), margin_miss=("margin_miss", "mean"), total_miss=("total_miss", "mean"),
        winner_right=("winner_right", "mean"), market_margin_miss=("market_margin_miss", "mean"),
        market_total_miss=("market_total_miss", "mean")).sort_values(["season", "week"], ascending=False)


def build(store=None) -> pd.DataFrame:
    """The graded record from the tracking store and the warehouses. Never raises."""
    try:
        if store is None:
            from atlas.live.store import Store

            store = Store.open()
        research = nfl = None
        try:
            from atlas.research.dataset import load_research_frame

            research = load_research_frame()
        except Exception as error:  # noqa: BLE001
            LOG.info("record: no college warehouse (%s)", type(error).__name__)
        try:
            from atlas.research.nfl_dataset import load_nfl_frame

            nfl = load_nfl_frame()
        except Exception as error:  # noqa: BLE001
            LOG.info("record: no NFL warehouse (%s)", type(error).__name__)
        games = store.read("games")
        names = {str(g): (_short(h), _short(a)) for g, h, a in zip(games["game_id"], games["home_team"],
                                                                   games["away_team"], strict=True)} if len(games) else {}
        for frame in (research,):
            if frame is not None and {"home_team", "away_team"} <= set(frame.columns):
                names.update({str(g): (h, a) for g, h, a in zip(frame["game_id"], frame["home_team"],
                                                               frame["away_team"], strict=True)})
        return graded(store.read("projections"), finals(research, nfl, games),
                      market(store.read("snapshots"), games), names)
    except Exception as error:  # noqa: BLE001 - the site builds without it
        LOG.error("model record not built: %s", type(error).__name__)
        return pd.DataFrame(columns=COLUMNS)


def _short(name) -> str | None:
    """An NFL display name to its nickname ("Green Bay Packers" -> "Packers"); unambiguous in the NFL."""
    return str(name).split(" ")[-1] if isinstance(name, str) and name else None
