"""Expected goals: the chance an unblocked shot attempt becomes a goal, from where and how it was taken.

    python -m atlas.models.nhl_xg     # fit on 2010-11 to 2019-20, check on 2020-21 on; reports/nhl_xg.{json,md}

Step 2 of `docs/MODEL_PLAN_NHL.md`. A logistic regression, as the plan says:
distance and angle (with their squares, a log and their product), whether
the shot came from behind the goal line, the shot type, a rebound and a
rush (each also against distance or angle), and the strength state. The net
being empty is its own small model on distance alone: an empty net is a
different game. A blocked attempt is given none: whether it would have
been dangerous is unknowable, and it never reached the goalie.

**Fitted walk-forward, a season at a time.** The plan said fit 2010-19
once and check 2020-26; the check found the recording moved under it. From
2021-22 the NHL's tracking records twice the rebounds (10% of unblocked
attempts against 5%) and twice the attempts inside ten feet, each converting
less often, and a model fitted on 2010-19 rated 2025-26's attempts at 1.14
goals per goal scored. So each season's expected goals come from a model
fitted on the three seasons before it (2010-11 to 2012-13, which have no three
before them, from the model fitted on themselves: the state's burn-in, never
scored). Every number is still made before the season it describes. The
coefficients for every season live in ``reports/nhl_xg.json`` beside the
report, as the other models' tuned choices do; the warehouse build applies
them and fits a new season's from the three before it the first time it
meets one.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from atlas import config
from atlas.util import get_logger

LOG = get_logger(__name__)

FIRST = 2010
#: Seasons each season's model is fitted on: the ones just before it.
WINDOW = 3
VERSION = "nhl-xg-v2"
SHOT_TYPES = ("snap", "slap", "backhand", "tip-in", "deflected", "wrap-around", "other", "unknown")   # wrist is the base
OTHER_TYPES = ("bat", "poke", "between-legs", "cradle")
STATES = ("PP", "SH", "EV", "ENA")                                                             # 5v5 is the base
MAX_DISTANCE = 100.0


def json_path(root: Path) -> Path:
    return root / "reports" / "nhl_xg.json"


def report_path(root: Path) -> Path:
    return root / "reports" / "nhl_xg.md"


def _type(t) -> str:
    if t is None or (isinstance(t, float) and np.isnan(t)) or pd.isna(t):
        return "unknown"
    t = str(t)
    return "other" if t in OTHER_TYPES else t


def design(shots: pd.DataFrame) -> tuple[np.ndarray, list[str]]:
    """The model's columns for non-empty-net unblocked attempts."""
    d = np.minimum(pd.to_numeric(shots["distance"], errors="coerce").fillna(MAX_DISTANCE).to_numpy(float),
                   MAX_DISTANCE) / 10.0
    a = pd.to_numeric(shots["angle"], errors="coerce").fillna(45.0).to_numpy(float)
    behind = (a > 90).astype(float)
    a = np.minimum(a, 90.0) / 10.0
    reb = shots["rebound"].astype(bool).to_numpy(float)
    rush = shots["rush"].astype(bool).to_numpy(float)
    types = shots["shot_type"].map(_type)
    cols = {"d": d, "d2": d ** 2, "logd": np.log1p(d), "a": a, "a2": a ** 2, "ad": a * d, "behind": behind,
            "rebound": reb, "rebound_a": reb * a, "rush": rush, "rush_d": rush * d}
    for t in SHOT_TYPES:
        cols[f"type_{t}"] = (types == t).to_numpy(float)
    st = shots["strength"].astype(str)
    for s in STATES:
        cols[f"state_{s}"] = (st == s).to_numpy(float)
    names = list(cols)
    return np.column_stack([cols[n] for n in names]), names


def _en_design(shots: pd.DataFrame) -> np.ndarray:
    d = np.minimum(pd.to_numeric(shots["distance"], errors="coerce").fillna(100.0).to_numpy(float), 200.0) / 10.0
    return np.column_stack([d, d ** 2])


def fit(shots: pd.DataFrame, seasons: tuple[int, ...]) -> dict:
    """The coefficients, fitted on the unblocked attempts of ``seasons``."""
    from sklearn.linear_model import LogisticRegression

    u = shots[shots["unblocked"] & shots["season"].isin(seasons)]
    main = u[u["strength"] != "EN"]
    x, names = design(main)
    mu, sd = x.mean(axis=0), x.std(axis=0)
    sd[sd == 0] = 1.0
    model = LogisticRegression(C=1e4, max_iter=2000)
    model.fit((x - mu) / sd, main["goal"].to_numpy(int))
    coef = model.coef_[0] / sd
    intercept = float(model.intercept_[0] - (model.coef_[0] * mu / sd).sum())
    en = u[u["strength"] == "EN"]
    en_model = LogisticRegression(C=1e4, max_iter=2000).fit(_en_design(en), en["goal"].to_numpy(int))
    return {"version": VERSION, "seasons": list(seasons), "columns": names, "coef": [float(c) for c in coef],
            "intercept": intercept, "en_coef": [float(c) for c in en_model.coef_[0]],
            "en_intercept": float(en_model.intercept_[0]), "attempts": int(len(main)), "en_attempts": int(len(en))}


def training(season: int) -> tuple[int, ...]:
    """The seasons a season's model is fitted on."""
    if season < FIRST + WINDOW:
        return tuple(range(FIRST, FIRST + WINDOW))
    return tuple(range(season - WINDOW, season))


def fit_all(shots: pd.DataFrame, seasons, have: dict | None = None) -> dict:
    """{season: coefficients} for every season asked for, reusing those already fitted."""
    out = dict(have or {})
    present = set(int(x) for x in shots["season"].unique())
    for season in sorted(set(int(x) for x in seasons)):
        if str(season) in out:
            continue
        train = training(season)
        if not set(train) <= present:
            continue
        out[str(season)] = fit(shots, train)
        LOG.info("nhl xg: %d fitted on %d-%d (%d attempts)", season, train[0], train[-1], out[str(season)]["attempts"])
    return out


def params_for(model: dict, season: int) -> dict | None:
    """The coefficients for a season: its own, else the latest before it."""
    by = model.get("by_season", {})
    if str(season) in by:
        return by[str(season)]
    earlier = [int(k) for k in by if int(k) <= season]
    return by[str(max(earlier))] if earlier else None


def predict_one(shots: pd.DataFrame, params: dict) -> np.ndarray:
    """P(goal) for each attempt under one season's coefficients."""
    out = np.zeros(len(shots))
    if shots.empty:
        return out
    unblocked = shots["unblocked"].astype(bool).to_numpy()
    en = (shots["strength"].astype(str) == "EN").to_numpy()
    main = unblocked & ~en
    if main.any():
        x, names = design(shots[main])
        if names != params["columns"]:
            raise ValueError("the xG columns changed since the coefficients were fitted")
        out[main] = 1.0 / (1.0 + np.exp(-(params["intercept"] + x @ np.asarray(params["coef"]))))
    emp = unblocked & en
    if emp.any():
        z = params["en_intercept"] + _en_design(shots[emp]) @ np.asarray(params["en_coef"])
        out[emp] = 1.0 / (1.0 + np.exp(-z))
    return out


def predict(shots: pd.DataFrame, model: dict) -> np.ndarray:
    """P(goal) for each attempt, each season under its own coefficients."""
    out = np.full(len(shots), np.nan)
    seasons = shots["season"].to_numpy()
    for season in np.unique(seasons):
        params = params_for(model, int(season))
        if params is None:
            continue
        mask = seasons == season
        out[mask] = predict_one(shots[mask], params)
    return out


def load(root: Path | None = None) -> dict | None:
    p = json_path(root or config.paths().root)
    return json.loads(p.read_text()) if p.exists() else None


def save(model: dict, root: Path | None = None) -> Path:
    p = json_path(root or config.paths().root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(model, indent=1) + "\n")
    return p


def ensure(shots: pd.DataFrame, model: dict | None, root: Path | None = None) -> dict | None:
    """The stored coefficients, with any season in ``shots`` that has none fitted from the three before it
    and saved. A season is fitted once and never refitted."""
    if shots is None or shots.empty:
        return model
    model = model or {"version": VERSION, "window": WINDOW, "by_season": {}}
    before = set(model["by_season"])
    model["by_season"] = fit_all(shots, shots["season"].unique(), model["by_season"])
    if set(model["by_season"]) != before:
        save(model, root)
    return model


def apply(shots: pd.DataFrame, model: dict | None) -> pd.DataFrame:
    """The shots with an ``xg`` column; left empty when there are no coefficients."""
    if shots is None or shots.empty:
        return shots
    out = shots.copy()
    out["xg"] = predict(out, model) if model and model.get("by_season") else np.nan
    return out


# ---------------------------------------------------------------------------
# The check
# ---------------------------------------------------------------------------


def _log_loss(y: np.ndarray, p: np.ndarray) -> float:
    p = np.clip(p, 1e-9, 1 - 1e-9)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def _auc(y: np.ndarray, p: np.ndarray) -> float:
    from sklearn.metrics import roc_auc_score

    return float(roc_auc_score(y, p))


def check(shots: pd.DataFrame, params: dict) -> dict:
    """Scores by season, calibration by decile out of sample, and what team-game xG says about goals."""
    u = shots[shots["unblocked"]].copy()
    u["xg"] = predict(u, params)
    rows = []
    for season, part in u.groupby("season"):
        y, p = part["goal"].to_numpy(int), part["xg"].to_numpy()
        base = np.full(len(y), y.mean())
        rows.append({"season": int(season), "attempts": len(part), "goals": int(y.sum()), "xg": float(p.sum()),
                     "ratio": float(y.sum() / p.sum()), "log_loss": _log_loss(y, p), "base_log_loss": _log_loss(y, base),
                     "auc": _auc(y, p) if y.min() != y.max() else float("nan"),
                     "fit": int(season) in training(int(season))})
    out_of = u[u["season"] >= FIRST + WINDOW]
    deciles = pd.qcut(out_of["xg"], 10, labels=False, duplicates="drop")
    calib = out_of.groupby(deciles).agg(mean_xg=("xg", "mean"), goal_rate=("goal", "mean"), n=("goal", "size"))
    by_state = out_of.groupby("strength").agg(attempts=("goal", "size"), goals=("goal", "sum"), xg=("xg", "sum"))
    return {"seasons": pd.DataFrame(rows), "calibration": calib.reset_index(drop=True),
            "by_state": by_state.reset_index()}


def team_game_signal(team_games: pd.DataFrame) -> pd.DataFrame:
    """Split-half reliability within a season of 5-on-5 xG share, shot share and goal share (odd against
    even games), the median across team-seasons' seasons: xG earns its place if it is steadier than goals."""
    t = team_games[team_games["season_type"] == "regular"].copy()
    games = t.groupby("season")["game_id"].nunique()
    t = t[t["season"].isin(games[games >= 500].index)]          # a season far enough along to halve
    t = t.sort_values(["season", "team", "kickoff"])
    t["n"] = t.groupby(["season", "team"]).cumcount()
    rows = []
    for season, part in t.groupby("season"):
        half = part.assign(odd=part["n"] % 2)
        agg = half.groupby(["team", "odd"]).agg(xgf=("xg_5v5", "sum"), xga=("xga_5v5", "sum"), sf=("sog_5v5", "sum"),
                                                sa=("soga_5v5", "sum"), gf=("goals_5v5", "sum"),
                                                ga=("goalsa_5v5", "sum")).reset_index()
        agg["xg_share"] = agg["xgf"] / (agg["xgf"] + agg["xga"])
        agg["shot_share"] = agg["sf"] / (agg["sf"] + agg["sa"])
        agg["goal_share"] = agg["gf"] / (agg["gf"] + agg["ga"])
        w = agg.pivot(index="team", columns="odd")
        rows.append({"season": int(season), **{m: float(np.corrcoef(w[m][0], w[m][1])[0, 1])
                                               for m in ("xg_share", "shot_share", "goal_share")}})
    return pd.DataFrame(rows)


def write_report(result: dict, signal: pd.DataFrame, params: dict, root: Path, fixed: pd.DataFrame | None = None) -> Path:
    s = result["seasons"]
    lines = ["# NHL expected goals (step 2)", "",
             "Generated by `python -m atlas.models.nhl_xg`. A logistic regression on unblocked shot attempts, the "
             "empty net modelled apart, each season's fitted on the three seasons before it (2010-11 to 2012-13 on "
             "themselves: the burn-in). Coefficients: `reports/nhl_xg.json`.", ""]
    if fixed is not None and len(fixed):
        lines += ["## Why walk-forward: the plan's fit, 2010-19 once", "",
                  "Fitted on 2010-11 to 2019-20 and never refitted, goals per expected goal by season:", "",
                  "| " + " | ".join(f"{r.season}-{str(r.season + 1)[-2:]}" for r in fixed.itertuples()) + " |",
                  "|" + "---|" * len(fixed),
                  "| " + " | ".join(f"{r.ratio:.3f}" for r in fixed.itertuples()) + " |", "",
                  "The NHL's tracking from 2021-22 records twice the rebounds and twice the attempts inside ten "
                  "feet, each converting less often; a fixed fit drifts to 0.88 by 2025-26.", ""]
    lines += ["## By season", "",
              "| Season | In its own fit? | Attempts | Goals | xG | Goals / xG | Log loss | League-rate log loss | AUC |",
              "|---|---|---|---|---|---|---|---|---|"]
    for r in s.itertuples():
        lines.append(f"| {r.season}-{str(r.season + 1)[-2:]} | {'burn-in' if r.fit else 'no'} | {r.attempts:,} | "
                     f"{r.goals:,} | {r.xg:,.0f} | {r.ratio:.3f} | {r.log_loss:.4f} | {r.base_log_loss:.4f} | "
                     f"{r.auc:.3f} |")
    lines += ["", "## Calibration out of sample (2013-14 on), by decile of xG", "", "| Mean xG | Goal rate | Attempts |",
              "|---|---|---|"]
    for r in result["calibration"].itertuples():
        lines.append(f"| {r.mean_xg:.3f} | {r.goal_rate:.3f} | {r.n:,} |")
    lines += ["", "## Out of sample, by strength state", "", "| State | Attempts | Goals | xG | Goals / xG |",
              "|---|---|---|---|---|"]
    for r in result["by_state"].itertuples():
        lines.append(f"| {r.strength} | {r.attempts:,} | {int(r.goals):,} | {r.xg:,.0f} | {r.goals / r.xg:.3f} |")
    if len(signal):
        med = signal[["xg_share", "shot_share", "goal_share"]].median()
        lines += ["", "## Is it signal? Split-half reliability of 5-on-5 shares, within a season", "",
                  "Odd games against even games, each team-season; the median across seasons.", "",
                  "| xG share | Shot share | Goal share |", "|---|---|---|",
                  f"| {med['xg_share']:.2f} | {med['shot_share']:.2f} | {med['goal_share']:.2f} |"]
    out = report_path(root)
    out.write_text("\n".join(lines) + "\n")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Fit and check the NHL expected-goals model")
    ap.add_argument("--refit", action="store_true", help="fit every season afresh")
    args = ap.parse_args()
    from atlas.staging.nhl import build as nhl_build

    root = config.paths().root
    shots = nhl_build.load_shots()
    model = None if args.refit else load(root)
    model = ensure(shots, model or {"version": VERSION, "window": WINDOW, "by_season": {}}, root)
    save(model, root)
    fixed_fit = {"by_season": {"2010": fit(shots, tuple(range(2010, 2020)))}}
    fixed = check(shots, fixed_fit)["seasons"]
    result = check(shots, model)
    # The team-game tables need the xG in them: rebuild with the coefficients just written.
    tables = nhl_build.build()
    signal = team_game_signal(tables["team_games"])
    print(write_report(result, signal, model, root, fixed))


if __name__ == "__main__":
    main()
