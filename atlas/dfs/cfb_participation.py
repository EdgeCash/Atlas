"""College: whether a player records a stat this week.

    python -m atlas.dfs.cfb_participation      # writes reports/dfs_cfb_participation.md

Step 5 of `docs/MODEL_PLAN_DFS_CFB.md`. The college model projects points
if a player plays; a live slate's pool is every player DraftKings prices,
and college has no depth chart or injury report to say who will. So the
roster is read from the record: a team's candidates for a game are the
players who recorded a stat for it in any of its previous eight games, and
the outcome is whether they record one in this one.

Inputs, all from earlier games: how many of the team's last four and last
eight games he played in, whether he played in the last one, how many
games since he last did, his career games, his recent scoring, his
position, and how deep into the season it is (a first game follows an
off-season). Walk-forward like everything else; scored by Brier score
against the simple alternative, his share of the team's last four games.

A player DraftKings prices who is not a candidate - a freshman, or a
transfer before his first game for his new team - has no record here; he
gets ``NEW_PLAYER``, a flat chance, stated as a guess.
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier

from atlas import config
from atlas.dfs import cfb_players as cp
from atlas.util import get_logger

LOG = get_logger(__name__)

WINDOW = 8
FEATURES = ["played_4", "played_8", "played_last", "games_since", "career", "points_trend", "is_qb", "is_rb",
            "is_wr", "is_k", "team_game", "new_season"]
PARAMS = dict(max_iter=150, learning_rate=0.05, max_leaf_nodes=15, min_samples_leaf=200, l2_regularization=1.0,
              random_state=0)
NEW_PLAYER = 0.3                    # a priced player with no record for his team: a stated guess
FIRST_TEST = cp.FIRST_TEST


def team_games(table: pd.DataFrame) -> pd.DataFrame:
    """Each team's games in order, with the season and its game number in that season."""
    g = table[["team", "event", "season", "order"]].drop_duplicates(["team", "event"]).sort_values(["team", "order"])
    g["k"] = g.groupby("team").cumcount()
    g["team_game"] = g.groupby(["team", "season"]).cumcount() + 1
    return g.reset_index(drop=True)


def candidates(table: pd.DataFrame, upcoming: pd.DataFrame | None = None) -> pd.DataFrame:
    """One row per (team game, candidate): the features and, for a played game, whether he recorded a stat.

    ``upcoming`` adds rows (team, event, season, order) for games not yet played."""
    played = table[["team", "event", "season", "order", "player_id", "position", "dk_points"]]
    games = team_games(pd.concat([played, upcoming], ignore_index=True) if upcoming is not None else played)
    app = played.merge(games[["team", "event", "k"]], on=["team", "event"])
    rows = []
    for team, tg in games.groupby("team", sort=False):
        a = app[app["team"] == team]
        if a.empty:
            continue
        players = a["player_id"].unique()
        index = {p: i for i, p in enumerate(players)}
        n_games = int(tg["k"].max()) + 1
        m = np.zeros((len(players), n_games), dtype=bool)
        pts = np.full((len(players), n_games), np.nan)
        m[a["player_id"].map(index).to_numpy(), a["k"].to_numpy()] = True
        pts[a["player_id"].map(index).to_numpy(), a["k"].to_numpy()] = a["dk_points"].to_numpy(dtype=float)
        pos = a.drop_duplicates("player_id", keep="last").set_index("player_id")["position"]
        seasons = tg.sort_values("k")["season"].to_numpy()
        for g in tg.itertuples():
            k = int(g.k)
            if k == 0:
                continue
            lo = max(0, k - WINDOW)
            window = m[:, lo:k]
            cand = np.flatnonzero(window.any(axis=1))
            if not len(cand):
                continue
            last4 = m[cand, max(0, k - 4):k].sum(axis=1)
            last8 = window[cand].sum(axis=1)
            last_idx = np.array([np.flatnonzero(m[i, :k]).max() for i in cand])
            career = m[cand, :k].sum(axis=1)
            recent_pts = np.array([np.nanmean(pts[i, max(0, k - 4):k]) if m[i, max(0, k - 4):k].any()
                                   else np.nanmean(pts[i, lo:k]) for i in cand])
            ids = players[cand]
            p = pos.reindex(ids).to_numpy()
            rows.append(pd.DataFrame({
                "team": team, "event": g.event, "season": g.season, "order": g.order, "player_id": ids,
                "played_4": last4, "played_8": last8, "played_last": m[cand, k - 1].astype(int),
                "games_since": k - last_idx, "career": career, "points_trend": recent_pts,
                "is_qb": (p == "QB").astype(int), "is_rb": (p == "RB").astype(int),
                "is_wr": (p == "WR").astype(int), "is_k": (p == "K").astype(int),
                "team_game": g.team_game, "new_season": int(seasons[k] != seasons[k - 1]),
                "played": m[cand, k].astype(int) if k < m.shape[1] else 0,
            }))
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=["played", *FEATURES])


def fit(train: pd.DataFrame) -> HistGradientBoostingClassifier:
    return HistGradientBoostingClassifier(**PARAMS).fit(train[FEATURES].to_numpy(dtype=float),
                                                        train["played"].to_numpy(dtype=int))


def predict(model: HistGradientBoostingClassifier, rows: pd.DataFrame) -> np.ndarray:
    return model.predict_proba(rows[FEATURES].to_numpy(dtype=float))[:, 1]


def walk_forward(c: pd.DataFrame, *, first: int = FIRST_TEST) -> pd.DataFrame:
    parts = []
    for season in sorted(int(s) for s in c["season"].unique()):
        if season < first:
            continue
        test = c[c["season"] == season]
        parts.append(test.assign(p_play=predict(fit(c[c["season"] < season]), test)))
    return pd.concat(parts, ignore_index=True)


def render(scored: pd.DataFrame) -> str:
    from atlas.dfs import participation as nfl
    from atlas.models.evaluate import markdown

    simple = scored["played_4"] / 4.0
    rel = nfl.reliability(scored)
    for c in ("predicted", "observed"):
        rel[c] = rel[c].map("{:.1%}".format)
    brier = float(np.mean((scored["p_play"] - scored["played"]) ** 2))
    base = float(np.mean((simple - scored["played"]) ** 2))
    parts = [
        "# College: who records a stat", "",
        "`atlas/dfs/cfb_participation.py`, step 5 of `docs/MODEL_PLAN_DFS_CFB.md`. A team's candidates for a game "
        "are the players who recorded a stat for it in any of its previous eight games; the model reads their "
        "recent appearances, career, scoring, position and the point in the season. Walk-forward, "
        f"{int(scored['season'].min())}-{int(scored['season'].max())}, {len(scored):,} candidate-games.", "",
        f"- Brier score {brier:.3f}, against {base:.3f} for his share of the team's last four games (lower is "
        "better).",
        f"- A priced player with no record for his team - a freshman, or a transfer before his first game - gets "
        f"a flat {NEW_PLAYER:.0%}, a stated guess: the record cannot measure him.", "",
        "Predicted against observed, by tenths of the prediction:", "", markdown(rel), "",
    ]
    return "\n".join(parts).rstrip() + "\n"


def main() -> None:
    argparse.ArgumentParser(description="College participation model, walk-forward").parse_args()
    table = pd.read_parquet(cp.path())
    scored = walk_forward(candidates(table))
    out = config.paths().root / "reports" / "dfs_cfb_participation.md"
    out.write_text(render(scored))
    LOG.info("wrote %s", out)


if __name__ == "__main__":
    main()
