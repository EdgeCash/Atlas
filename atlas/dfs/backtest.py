"""The lineups each projection would have built, and what they scored.

    python -m atlas.dfs.backtest            # writes reports/dfs_lineups.md

Step 5 of `docs/MODEL_PLAN_DFS.md`, and the plan's last metric (§5): for
every Sunday main slate of 2015-2021 - the seasons with DraftKings' own
salaries - the optimizer builds the lineup with the most projected points
under the cap from each of three projections, and the lineup is scored by
what its players actually recorded:

* ``model`` - Atlas's player model, walk-forward (`atlas/dfs/model.py`);
* ``salary`` - DraftKings' price mapped to points, the market's own view;
* ``baseline`` - each player's recent scoring, shrunk to his position.

``best possible`` is the lineup built from the outcomes themselves, the
ceiling no projection reaches, to give the numbers a scale.

The main slate is the Sunday games kicking off between noon and 5pm
Eastern - the 1pm and late-afternoon windows, without London's morning
games or the night games - which is how DraftKings has built it.

A caveat stated up front: the pool is the players who recorded a stat that
week. A player ruled out before kickoff is not in it, which is what the
final injury report and the inactive list, 90 minutes before kickoff, tell
anyone building a lineup; a player who was active and recorded nothing is
also missing, which slightly flatters every projection alike.
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from atlas import config
from atlas.dfs import optimizer as op
from atlas.dfs import participation
from atlas.sources import nflverse
from atlas.staging.nfl.games import FRANCHISE
from atlas.util import get_logger

LOG = get_logger(__name__)

PROJECTIONS = ("model", "salary", "baseline")
#: Where each projection lives in a pool: the optimizer's ``salary`` column is
#: the price, so the salary benchmark's points move aside.
COLUMN = {"model": "model", "salary": "salary_points", "baseline": "baseline", "best possible": "target"}
SEASONS = tuple(range(2015, 2022))       # the seasons with DraftKings' own salaries
MAIN_WINDOW = ("12:00", "17:00")        # Eastern kickoff times on the Sunday main slate


def main_slate(raw=None) -> pd.DataFrame:
    """Every team-week on the Sunday main slate, with its opponent and kickoff."""
    s = pd.read_parquet(nflverse.schedules_path(raw or config.paths().raw))
    s = s[(s["game_type"] == "REG") & (s["weekday"] == "Sunday")]
    s = s[(s["gametime"] >= MAIN_WINDOW[0]) & (s["gametime"] < MAIN_WINDOW[1])]
    parts = [pd.DataFrame({"season": s["season"], "week": s["week"], "team": s[side].replace(FRANCHISE),
                           "opponent": s[other].replace(FRANCHISE), "game_start": s["gameday"] + "T" + s["gametime"]})
             for side, other in (("home_team", "away_team"), ("away_team", "home_team"))]
    return pd.concat(parts, ignore_index=True)


def pools(scored: pd.DataFrame, slate: pd.DataFrame) -> pd.DataFrame:
    """Scored player-weeks with a salary, on the main slate, in the optimizer's shape."""
    p = scored.dropna(subset=["dk_salary", "target"]).merge(slate, on=["season", "week", "team"], how="inner")
    p = p[p["position"].isin(list(op.SLOTS))]
    p = p.rename(columns={"salary": "salary_points"})
    return p.assign(id=p["player_id"], salary=p["dk_salary"].astype(int))


def week(pool: pd.DataFrame, opts: op.Options | None = None) -> dict:
    """One week: each projection's lineup and what it scored."""
    out = {}
    for name in (*PROJECTIONS, "best possible"):
        p = pool.assign(projection=pool[COLUMN[name]])
        try:
            lineup = op.optimize(p, opts)[0]
        except op.Infeasible:
            out[name] = np.nan
            continue
        out[name] = float(lineup["target"].sum())
        out[f"{name} projected"] = float(lineup["projection"].sum())
    return out


def run(scored: pd.DataFrame | None = None, seasons: tuple[int, ...] = SEASONS) -> pd.DataFrame:
    if scored is None:
        from atlas.dfs import model

        scored = model.run()
    slate = main_slate()
    p = pools(scored[scored["season"].isin(list(seasons))], slate)
    rows = []
    for (season, wk), g in p.groupby(["season", "week"]):
        if g["position"].value_counts().reindex(list(op.SLOTS), fill_value=0).lt(3).any():
            continue                                    # a thin week (a bye-heavy or partial archive week)
        rows.append({"season": int(season), "week": int(wk), "players": len(g), **week(g)})
        LOG.info("backtest %d week %d: %s", season, wk, {k: round(v, 1) for k, v in rows[-1].items()
                                                         if k in PROJECTIONS})
    return pd.DataFrame(rows)


def render(weeks: pd.DataFrame, play: pd.DataFrame | None = None) -> str:
    from atlas.models.evaluate import markdown

    names = (*PROJECTIONS, "best possible")

    def table(by: str | None) -> pd.DataFrame:
        groups = weeks.groupby(by) if by else [("2015-2021", weeks)]
        out = []
        for key, g in groups:
            row = {by or "seasons": key, "slates": len(g)}
            for n in names:
                row[n] = f"{g[n].mean():.1f}"
            out.append(row)
        return pd.DataFrame(out)

    head = []
    for other in ("salary", "baseline"):
        d = weeks["model"] - weeks[other]
        head.append({"model against": other, "slates": len(d), "model higher": f"{(d > 0).mean():.0%}",
                     "mean difference": f"{d.mean():+.1f}", "standard error": f"{d.std() / np.sqrt(len(d)):.1f}"})
    calib = pd.DataFrame([{"projection": n, "projected": f"{weeks[f'{n} projected'].mean():.1f}",
                           "scored": f"{weeks[n].mean():.1f}"} for n in PROJECTIONS])
    parts = [
        "# DFS lineups, 2015-2021", "",
        "Every Sunday main slate with DraftKings' own salaries: the lineup with the most projected points under "
        "the $50,000 cap, built by Atlas's optimizer (`atlas/dfs/optimizer.py`) from each projection, and scored "
        "by what its nine players actually recorded (`atlas/dfs/backtest.py`). One lineup per projection per "
        "slate, no defense facing its own lineup's offense, no other rule. `best possible` is the lineup built "
        "from the outcomes themselves - the ceiling, for scale.", "",
        "## Actual points of each projection's lineup", "", markdown(table(None)), "",
        "`salary` is DraftKings' price read as a projection: one straight line per position, so its optimizer "
        "simply spends the cap where a dollar buys the most. It is the market's view taken literally, not a way "
        "anyone would build a lineup - the fair comparison for the model's ranking is step 3's.", "",
        "## Head to head", "", markdown(pd.DataFrame(head)), "",
        "## Projected against scored", "",
        "What each lineup was projected to score and what it did. A lineup chosen as the highest projection is "
        "chosen partly for its projection's errors, so every projection's best lineup scores below its own "
        "number; the smaller the gap, the less the projection fooled its optimizer.", "", markdown(calib), "",
        "## By season", "", markdown(table("season")), "",
    ]
    if play is not None:
        simple = play["by_depth"].fillna(play["played"].mean())
        rel = participation.reliability(play)
        for c in ("predicted", "observed"):
            rel[c] = rel[c].map("{:.1%}".format)
        parts += [
            "## Who plays at all", "",
            "The backtest's pool is the players who recorded a stat; a live slate's pool is everyone DraftKings "
            "prices. For the live slate, each player's projection is multiplied by the chance he records a stat "
            "(`atlas/dfs/participation.py`): fitted on every quarterback, running back, receiver and tight end on "
            "a depth chart, from his position, depth-chart rank, injury status, games played, snap share and "
            "weeks since his last game. Walk-forward, "
            f"{int(play['season'].min())}-{int(play['season'].max())}, {len(play):,} listings:", "",
            f"- Brier score {participation.brier(play):.3f}, against {np.mean((simple - play['played']) ** 2):.3f} "
            "for the share of earlier listings at the same position and depth who played (lower is better).", "",
            "Predicted against observed, by tenths of the prediction:", "", markdown(rel), "",
        ]
    parts += [
        "## Caveats", "",
        "- **The pool** is the players who recorded a stat that week: a player ruled out beforehand is not in it "
        "(the injury report and the inactive list say so before lock), and neither is an active player who "
        "recorded nothing, which flatters every projection alike.",
        "- **The main slate** is reconstructed from kickoff times (Sunday, noon to 5pm Eastern); DraftKings' "
        "own slate for a given week may have differed by a game.",
        "- **Nothing here is a return.** A lineup's points say how well a projection ranks players under a cap. "
        "They say nothing about winning a contest, which depends on the field, the entry fee and DraftKings' rake.",
        "",
    ]
    return "\n".join(parts).rstrip() + "\n"


def main() -> None:
    argparse.ArgumentParser(description="Backtest the optimizer's lineups, 2015-2021").parse_args()
    weeks = run()
    t = participation.table()
    play = participation.walk_forward(t)
    play["by_depth"] = participation.by_depth(t).loc[play.index]
    out = config.paths().root / "reports" / "dfs_lineups.md"
    out.write_text(render(weeks, play))
    LOG.info("wrote %s: %d slates\n%s", out, len(weeks), weeks[[*PROJECTIONS, "best possible"]].mean().round(1))


if __name__ == "__main__":
    main()
