"""The two numbers the DFS player model has to beat.

    python -m atlas.dfs.benchmarks          # writes reports/dfs_benchmarks.md

Step 2 of `docs/MODEL_PLAN_DFS.md`, walk-forward like every Atlas model:
each season is predicted from the seasons before it only.

* ``baseline`` - the floor. A player's exponentially weighted DraftKings
  points over his earlier games (halflife 4 games, carried across seasons),
  pulled toward his position's average by an amount fitted on the training
  seasons, so a player with two games of history is mostly the average.
* ``salary`` - the ceiling, the market's number. DraftKings' price, mapped
  to points by a line per position fitted on the training seasons. Salaries
  exist for 2014-2021 (RotoGuru's archive) and from 2026 on (Atlas's own
  capture), so this benchmark is scored on 2015-2021.

The main view is each team's regulars - its top quarterback, two running
backs, three receivers and tight end by salary (by prior form where there is
no salary), and every defense - the pool a lineup is actually built from.
Scored on all who played, the fringe (a minimum-salary backup's one catch)
dominates and flatters the baseline; the report shows both.

Both are scored on the player-weeks where the player recorded a stat. Whether
a player plays at all is a question for the injury report, which the model
answers in step 3; scoring it here would measure the injury report, not the
projection. Metrics: MAE; CRPS of a normal whose spread grows with the
projection (fitted by position on the training seasons); and the rank
correlation within each position's week, which is what the optimizer uses.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.stats import norm

from atlas import config
from atlas.util import get_logger

LOG = get_logger(__name__)

POSITIONS = ("QB", "RB", "WR", "TE", "DST")
HALFLIFE = 4.0
HISTORY_CAP = 8                    # games of history that count at full weight against the prior
SHRINK_GRID = (0.0, 0.5, 1.0, 2.0, 4.0, 8.0)
SALARY_SEASONS = range(2014, 2022)
FIRST_TEST = 2015

#: A team's regulars at each position: the pool a lineup is built from.
DEPTH = {"QB": 1, "RB": 2, "WR": 3, "TE": 1, "DST": 1}


def regulars(scored: pd.DataFrame) -> pd.DataFrame:
    """Each team's top players at each position that week, by salary where
    there is one and by the baseline projection (prior form) where not."""
    s = scored.copy()
    key = s["dk_salary"].where(s["dk_salary"].notna(), s["baseline"])
    s["depth"] = key.groupby([s["season"], s["week"], s["team"], s["position"]]).rank(ascending=False, method="first")
    return s[s["depth"] <= s["position"].map(DEPTH)]


def crps_normal(mu: np.ndarray, sigma: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Closed-form CRPS of a normal forecast; lower is better, in points."""
    sigma = np.maximum(np.asarray(sigma, dtype=float), 1e-6)
    z = (np.asarray(y, dtype=float) - mu) / sigma
    return sigma * (z * (2 * norm.cdf(z) - 1) + 2 * norm.pdf(z) - 1 / np.sqrt(np.pi))


def rank_correlation(frame: pd.DataFrame, pred: str, target: str = "target", min_players: int = 5) -> float:
    """Mean Spearman correlation within each season-week-position with enough players."""
    out = []
    for _, g in frame.groupby(["season", "week", "position"]):
        if len(g) >= min_players and g[pred].nunique() > 1:
            out.append(g[pred].rank().corr(g[target].rank()))
    return float(np.nanmean(out)) if out else float("nan")


def load(staging=None) -> pd.DataFrame:
    """Regular-season player-weeks and defense-weeks, one frame, with the target.

    The target is DraftKings' own recorded points where the archive has them
    and Atlas's reconciled computation otherwise.
    """
    staging = staging or config.paths().staging / "nfl"
    p = pd.read_parquet(staging / "dfs_player_games.parquet")
    p = p[p["season_type"] == "REG"].copy()
    d = pd.read_parquet(staging / "dfs_dst_games.parquet")
    d = d[d["season_type"] == "REG"].copy()
    d = d.assign(player_id="DST-" + d["team"], name=d["team"] + " DST", position="DST")
    d = d.sort_values(["player_id", "season", "week"])
    by = d.groupby("player_id", sort=False)
    d["games_before"] = by.cumcount()
    d["dk_points_trend"] = by["dk_points"].transform(lambda s: s.shift(1).ewm(halflife=HALFLIFE, ignore_na=True).mean())
    cols = ["season", "week", "team", "player_id", "name", "position", "dk_points", "dk_points_official", "dk_salary",
            "dk_points_trend", "games_before"]
    frame = pd.concat([p[[c for c in cols if c in p]], d[[c for c in cols if c in d]]], ignore_index=True)
    frame["target"] = frame["dk_points_official"].fillna(frame["dk_points"])
    return frame


@dataclass
class Fit:
    shrink: dict[str, float]
    mean: dict[str, float]
    salary: dict[str, tuple[float, float]]
    spread: dict[tuple[str, str], tuple[float, float]]


def _baseline(frame: pd.DataFrame, shrink: dict, mean: dict) -> np.ndarray:
    n = frame["games_before"].clip(upper=HISTORY_CAP).to_numpy(dtype=float)
    mu = frame["position"].map(mean).to_numpy(dtype=float)
    k = frame["position"].map(shrink).to_numpy(dtype=float)
    trend = frame["dk_points_trend"].to_numpy(dtype=float)
    trend = np.where(np.isnan(trend), mu, trend)
    return np.where(n + k > 0, (n * trend + k * mu) / np.maximum(n + k, 1e-9), mu)


def _salary(frame: pd.DataFrame, lines: dict) -> np.ndarray:
    a = frame["position"].map(lambda p: lines.get(p, (np.nan, np.nan))[0]).to_numpy(dtype=float)
    b = frame["position"].map(lambda p: lines.get(p, (np.nan, np.nan))[1]).to_numpy(dtype=float)
    return a + b * frame["dk_salary"].to_numpy(dtype=float)


def _spread(pred: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    """|residual| = a + b * prediction, as a normal's sd: sqrt(pi/2) * mean |residual|."""
    ok = ~np.isnan(pred) & ~np.isnan(y)
    if ok.sum() < 30:
        return (float(np.nanstd(y - pred)), 0.0)
    X = np.column_stack([np.ones(ok.sum()), pred[ok]])
    coef, *_ = np.linalg.lstsq(X, np.abs(y[ok] - pred[ok]), rcond=None)
    return (float(coef[0] * np.sqrt(np.pi / 2)), float(coef[1] * np.sqrt(np.pi / 2)))


def fit(train: pd.DataFrame) -> Fit:
    mean = train.groupby("position")["target"].mean().to_dict()
    shrink = {}
    for pos, g in train.groupby("position"):
        errs = {k: np.mean(np.abs(_baseline(g, {pos: k}, mean) - g["target"].to_numpy())) for k in SHRINK_GRID}
        shrink[pos] = min(errs, key=errs.get)
    salary = {}
    priced = train.dropna(subset=["dk_salary"])
    for pos, g in priced.groupby("position"):
        X = np.column_stack([np.ones(len(g)), g["dk_salary"].to_numpy(dtype=float)])
        coef, *_ = np.linalg.lstsq(X, g["target"].to_numpy(dtype=float), rcond=None)
        salary[pos] = (float(coef[0]), float(coef[1]))
    spread = {}
    for pos, g in train.groupby("position"):
        y = g["target"].to_numpy(dtype=float)
        spread[("baseline", pos)] = _spread(_baseline(g, shrink, mean), y)
        gp = g.dropna(subset=["dk_salary"])
        if len(gp):
            spread[("salary", pos)] = _spread(_salary(gp, salary), gp["target"].to_numpy(dtype=float))
    return Fit(shrink, mean, salary, spread)


def predict(frame: pd.DataFrame, f: Fit) -> pd.DataFrame:
    out = frame.copy()
    out["baseline"] = _baseline(out, f.shrink, f.mean)
    out["salary"] = _salary(out, f.salary)
    for model in ("baseline", "salary"):
        a = out["position"].map(lambda p, m=model: f.spread.get((m, p), (np.nan, 0.0))[0]).to_numpy(dtype=float)
        b = out["position"].map(lambda p, m=model: f.spread.get((m, p), (np.nan, 0.0))[1]).to_numpy(dtype=float)
        out[f"{model}_sd"] = np.maximum(a + b * out[model].to_numpy(dtype=float), 1.0)
    return out


def walk_forward(frame: pd.DataFrame, *, first_test: int = FIRST_TEST) -> pd.DataFrame:
    seasons = sorted(int(s) for s in frame["season"].unique())
    parts = []
    for season in seasons:
        if season < first_test:
            continue
        f = fit(frame[frame["season"] < season])
        parts.append(predict(frame[frame["season"] == season], f))
    return pd.concat(parts, ignore_index=True)


def summarise(scored: pd.DataFrame, models: tuple[str, ...], by: list[str] | None = None) -> pd.DataFrame:
    rows = []
    groups = scored.groupby(by) if by else [((), scored)]
    for key, g in groups:
        key = key if isinstance(key, tuple) else (key,)
        for m in models:
            gg = g.dropna(subset=[m])
            if gg.empty:
                continue
            y = gg["target"].to_numpy(dtype=float)
            rows.append({**dict(zip(by or [], key, strict=True)), "model": m, "player-weeks": len(gg),
                         "mae": float(np.mean(np.abs(gg[m] - y))),
                         "crps": float(np.mean(crps_normal(gg[m].to_numpy(), gg[f"{m}_sd"].to_numpy(), y))),
                         "rank corr": rank_correlation(gg, m)})
    return pd.DataFrame(rows)


def render(salaried: pd.DataFrame, recent: pd.DataFrame) -> str:
    """The regulars first; everyone who played second; the baseline alone on recent seasons."""
    from atlas.models.evaluate import markdown

    def fmt(t: pd.DataFrame) -> pd.DataFrame:
        t = t.copy()
        for c in ("mae", "crps"):
            t[c] = t[c].map("{:.3f}".format)
        t["rank corr"] = t["rank corr"].map("{:.3f}".format)
        return t

    both = ("baseline", "salary")
    parts = [
        "# DFS benchmarks", "",
        "The two numbers the player model has to beat (`atlas/dfs/benchmarks.py`, step 2 of "
        "`docs/MODEL_PLAN_DFS.md`), walk-forward: every season predicted from the seasons before it only. "
        "`baseline` is each player's recent DraftKings points, pulled toward his position's average by a fitted "
        "amount; `salary` is DraftKings' price mapped to points by a line per position. The target is DraftKings' "
        "recorded points. Scored on player-weeks where the player recorded a stat (inactive players are the injury "
        "report's question, step 3). Lower MAE and CRPS are better; higher rank correlation (within each "
        "position's week) is better, and it is the figure the optimizer lives on.", "",
        f"## Salary era, {int(salaried['season'].min())}-{int(salaried['season'].max())}: each team's regulars", "",
        "Each team's top quarterback, two running backs, three receivers and tight end by salary, and every "
        "defense: the pool a lineup is built from.", "",
        markdown(fmt(summarise(regulars(salaried), both))), "",
        "### By position", "", markdown(fmt(summarise(regulars(salaried), both, ["position"]))), "",
        "### By season", "", markdown(fmt(summarise(regulars(salaried), both, ["season"]))), "",
        "### Everyone who played, by position", "",
        "The fringe - a minimum-salary backup with one catch - is most of these rows; the baseline reads a "
        "player's own tiny history and a straight salary line cannot, so this view flatters the baseline.", "",
        markdown(fmt(summarise(salaried, both, ["position"]))), "",
    ]
    if not recent.empty:
        parts += [f"## Baseline only, {int(recent['season'].min())}-{int(recent['season'].max())} (no salaries exist)",
                  "", "The floor on the seasons the model will also be judged on; regulars chosen by prior form.", "",
                  markdown(fmt(summarise(regulars(recent), ("baseline",), ["position"]))), ""]
    return "\n".join(parts).rstrip() + "\n"


def main() -> None:
    argparse.ArgumentParser(description="DFS benchmarks, walk-forward").parse_args()
    frame = load()
    scored = walk_forward(frame)
    salaried = scored[scored["season"].isin(SALARY_SEASONS) & scored["dk_salary"].notna()]
    recent = scored[scored["season"] > max(SALARY_SEASONS)]
    recent = recent[recent["season"] < int(frame["season"].max())]          # whole seasons only
    out = config.paths().root / "reports" / "dfs_benchmarks.md"
    out.write_text(render(salaried, recent))
    LOG.info("wrote %s\n%s", out,
             summarise(regulars(salaried), ("baseline", "salary"), ["position"]).round(3).to_string(index=False))


if __name__ == "__main__":
    main()
