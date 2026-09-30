"""The NHL game model end to end: state, grid, the §7 table (docs/MODEL_PLAN_NHL.md, steps 3 to 5).

    python -m atlas.models.nhl_model          # tune, walk forward, score; reports/nhl_model.md, reports/nhl_model.json
    python -m atlas.models.nhl_model --quick  # the stored choices, no tuning

Walks the state model (`nhl_state.py`) through every game since 2010-11,
turns each game's expected goals into the grid (`nhl_grid.py`), and scores
the forecasts beside the benchmarks (`nhl_benchmarks.py`), every forecast
made before puck drop from games already played:

* P(home, overtime included): Brier and log loss, on the market's games
  2010-22 pooled and 2021-22, and on every game from 2020-21;
* the regulation three-way: ranked probability score;
* the goal margin and the total: CRPS on the final score;
* calibration of the puck line and of the total at 5.5 and 6.5;
* the goalie test: the games a team's usual starter did not start;
* the prior test: each team's first twenty games against the rest.

Tuned on 2017-18 to 2019-20 by the log loss of P(home) and the regulation
goals' Poisson likelihood together; the home and back-to-back terms and the
grid's layers are fitted on 2010-11 to 2016-17. Never scored on a season
used to tune it. The choices, the terms and the layers go to
``reports/nhl_model.json`` for the live projection to reuse.
"""

from __future__ import annotations

import argparse
import itertools
import json
from dataclasses import asdict, replace
from pathlib import Path

import numpy as np
import pandas as pd

from atlas import config
from atlas.models import nhl_benchmarks as bench
from atlas.models import nhl_grid as grid
from atlas.models import nhl_state as st
from atlas.util import get_logger

LOG = get_logger(__name__)

FIT = range(2010, 2017)
TUNE = range(2017, 2020)
REPORT_FROM = 2020
VERSION = "nhl-v1"


def json_path(root: Path) -> Path:
    return root / "reports" / "nhl_model.json"


def report_path(root: Path) -> Path:
    return root / "reports" / "nhl_model.md"


def load_tables() -> dict[str, pd.DataFrame]:
    from atlas.staging.nhl import build as nhl_build

    return {t: nhl_build.load(t) for t in ("games", "team_games", "goalie_games", "goals", "odds")}


def games_frame(games: pd.DataFrame) -> pd.DataFrame:
    g = games[games["season_type"].isin(["regular", "postseason"])].copy()
    g["kickoff"] = pd.to_datetime(g["kickoff"], utc=True)
    return g.dropna(subset=["kickoff", "home_team", "away_team"]).sort_values(["kickoff", "game_id"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# One run: walk, fit the terms and the layers, grid every game
# ---------------------------------------------------------------------------


def run(tables: dict, spec: st.Spec, *, home5: float | None = None, b2b: float | None = None,
        layers: grid.Layers | None = None, confirmed: bool = False) -> tuple[pd.DataFrame, dict]:
    games = games_frame(tables["games"])
    tg, gg = tables["team_games"], tables["goalie_games"]
    model = st.Model.new(spec)
    if home5 is not None:
        model.home5 = home5
    if b2b is not None:
        model.b2b = b2b
    f, _ = st.walk(games, tg, gg, spec, confirmed=confirmed, model=model)
    terms = {"home5": model.home5, "b2b": model.b2b}
    if home5 is None or b2b is None:
        # The home and rest terms from the fit seasons' residuals, then the walk again with them.
        dh, db = st.fit_terms(f, games, FIT)
        model = st.Model.new(spec)
        model.home5 = 0.12 + dh / 0.8
        model.b2b = -0.15 + db
        terms = {"home5": model.home5, "b2b": model.b2b}
        f, _ = st.walk(games, tg, gg, spec, confirmed=confirmed, model=model)
    f = f.merge(games[["game_id", "season", "season_type", "kickoff", "home_team", "away_team", "completed",
                       "home_score", "away_score", "reg_home", "reg_away", "decision", "home_b2b", "away_b2b"]],
                on="game_id", how="left")
    if layers is None:
        lam = f.set_index("game_id")[["lambda_home", "lambda_away", "home_edge"]]
        layers = grid.fit(tables["goals"], games, lam, games["season"].unique())
    return with_grid(f, layers), {"terms": terms, "layers": layers}


def with_grid(f: pd.DataFrame, layers: grid.Layers) -> pd.DataFrame:
    rows = []
    for lh, la, season, edge in zip(f["lambda_home"], f["lambda_away"], f["season"], f["home_edge"], strict=True):
        s = grid.summary(float(lh), float(la), layers.get(int(season)), edge=float(edge))
        tcdf = grid.total_cdf(s["grid"])
        margins, mcdf = grid.margin_cdf(s["grid"])
        rows.append({k: v for k, v in s.items() if k not in ("grid", "top")} | {"_tcdf": tcdf, "_mcdf": mcdf,
                                                                                  "top": s["top"]})
    extra = pd.DataFrame(rows, index=f.index).drop(columns=["lambda_home", "lambda_away"])
    return pd.concat([f, extra], axis=1)


# ---------------------------------------------------------------------------
# Scores
# ---------------------------------------------------------------------------


def rps3(p_home: np.ndarray, p_tie: np.ndarray, outcome: np.ndarray) -> float:
    """Ranked probability score on the regulation three-way (home, tie, away): outcome 0, 1 or 2."""
    c1 = p_home
    c2 = p_home + p_tie
    o1 = (outcome == 0).astype(float)
    o2 = (outcome <= 1).astype(float)
    return float(np.mean(((c1 - o1) ** 2 + (c2 - o2) ** 2) / 2.0))


def crps_discrete(cdfs: list[np.ndarray], support: np.ndarray, values: np.ndarray) -> float:
    out = []
    for cdf, v in zip(cdfs, values, strict=True):
        step = (support >= v).astype(float)
        out.append(float(np.sum((cdf - step) ** 2)))
    return float(np.mean(out))


def scores(f: pd.DataFrame, mask: pd.Series) -> dict:
    part = f[mask & f["completed"].astype(bool)]
    if part.empty:
        return {}
    y = (part["home_score"] > part["away_score"]).astype(float).to_numpy()
    reg_out = np.where(part["reg_home"] > part["reg_away"], 0, np.where(part["reg_home"] == part["reg_away"], 1, 2))
    final_total = (part["home_score"] + part["away_score"]).to_numpy()
    final_margin = (part["home_score"] - part["away_score"]).to_numpy()
    n = grid.N
    return {
        "n": len(part), "brier": bench.brier(part["p_home"], y), "log_loss": bench.log_loss(part["p_home"], y),
        "rps": rps3(part["p_reg_home"].to_numpy(), part["p_ot"].to_numpy(), reg_out),
        "crps_total": crps_discrete(list(part["_tcdf"]), np.arange(2 * n - 1), final_total),
        "crps_margin": crps_discrete(list(part["_mcdf"]), np.arange(-(n - 1), n), final_margin),
        "goals_ll": st.poisson_loglik(np.r_[part["lambda_home"], part["lambda_away"]],
                                      np.r_[part["reg_home"], part["reg_away"]]),
    }


def calibration(f: pd.DataFrame, mask: pd.Series) -> pd.DataFrame:
    """Predicted against actual for the puck line and the totals, by bucket of predicted probability."""
    part = f[mask & f["completed"].astype(bool)]
    margin = part["home_score"] - part["away_score"]
    total = part["home_score"] + part["away_score"]
    checks = {"home -1.5": (part["p_home_minus_1_5"], margin >= 2), "away -1.5": (part["p_away_minus_1_5"], margin <= -2),
              "over 5.5": (part["p_over_5.5"], total > 5.5), "over 6.5": (part["p_over_6.5"], total > 6.5),
              "home wins": (part["p_home"], margin > 0), "overtime": (part["p_ot"], part["decision"] != "REG")}
    rows = []
    for name, (p, hit) in checks.items():
        rows.append({"market": name, "predicted": float(p.mean()), "actual": float(hit.mean()), "n": len(p),
                     "brier": bench.brier(p, hit.astype(float))})
    return pd.DataFrame(rows)


def starter_cut(f: pd.DataFrame, goalie_games: pd.DataFrame) -> pd.Series:
    """Games where a side's usual starter did not start: the goalie that team started most in its last
    twenty games before this one was not in net."""
    g = goalie_games[goalie_games["started"] == 1][["game_id", "team", "player_id", "kickoff"]].sort_values("kickoff")
    usual = {}
    history: dict = {}
    for r in g.itertuples(index=False):
        h = history.setdefault(r.team, [])
        if len(h) >= 10:
            common = pd.Series(h[-20:]).mode().iloc[0]
            usual[(r.game_id, r.team)] = r.player_id != common
        h.append(r.player_id)
    return f.apply(lambda r: bool(usual.get((r["game_id"], r["home_team"]), False)
                                  or usual.get((r["game_id"], r["away_team"]), False)), axis=1)


def early_cut(f: pd.DataFrame) -> pd.Series:
    """Games inside either side's first twenty of the season."""
    g = f.sort_values("kickoff")
    n = {}
    flag = []
    for r in g.itertuples(index=False):
        k = (r.season, r.home_team)
        j = (r.season, r.away_team)
        flag.append(n.get(k, 0) < 20 or n.get(j, 0) < 20)
        n[k] = n.get(k, 0) + 1
        n[j] = n.get(j, 0) + 1
    return pd.Series(flag, index=g.index).reindex(f.index)


# ---------------------------------------------------------------------------
# Tuning
# ---------------------------------------------------------------------------

GRID = {
    "q5": (0.002, 0.004),
    "phi": (0.85, 0.95),
    "r5": (5.0, 10.0),
    "r_f": (6.0, 12.0),
}
#: Held while tuning: where the earlier rounds settled (the goalie's noise, the observation's blend).
TUNE_BASE = {"r_g": 2.0, "blend": 0.6}
#: The home and back-to-back terms held while tuning (the untuned walk's fit on 2010-17).
TUNE_TERMS = {"home5": 0.30, "b2b": -0.10}

_TABLES: dict = {}


def _trial(values: tuple) -> dict:
    """One setting, walked through the tuning seasons only and scored on them."""
    tables = _TABLES
    keys = list(GRID)
    spec = replace(st.Spec(), **TUNE_BASE, **dict(zip(keys, values, strict=True)))
    games = games_frame(tables["games"])
    games = games[games["season"] <= max(TUNE)]
    model = st.Model.new(spec)
    model.home5, model.b2b = TUNE_TERMS["home5"], TUNE_TERMS["b2b"]
    f, _ = st.walk(games, tables["team_games"], tables["goalie_games"], spec, model=model)
    f = f.merge(games[["game_id", "season", "season_type", "kickoff", "home_team", "away_team", "completed",
                       "home_score", "away_score", "reg_home", "reg_away", "decision", "home_b2b", "away_b2b"]],
                on="game_id", how="left")
    lam = f.set_index("game_id")[["lambda_home", "lambda_away", "home_edge"]]
    layers = grid.fit(tables["goals"], games, lam, TUNE)
    part = with_grid(f[f["season"].isin(TUNE)].reset_index(drop=True), layers)
    s = scores(part, part["season_type"] == "regular")
    return {**dict(zip(keys, values, strict=True)), **{k: s[k] for k in ("log_loss", "brier", "goals_ll")}}


def tune(tables: dict, workers: int = 4) -> tuple[st.Spec, pd.DataFrame]:
    import multiprocessing as mp

    global _TABLES
    _TABLES = tables
    combos = list(itertools.product(*GRID.values()))
    ctx = mp.get_context("fork")
    with ctx.Pool(workers) as pool:
        trials = pool.map(_trial, combos)
    for t in trials:
        LOG.info("nhl tune %s: log loss %.5f, goals %.5f", {k: t[k] for k in GRID}, t["log_loss"], t["goals_ll"])
    base = replace(st.Spec(), **TUNE_BASE)
    keys = list(GRID)
    t = pd.DataFrame(trials)
    # Both: the win probability and the goals it rests on, each ranked.
    t["rank"] = t["log_loss"].rank() + (-t["goals_ll"]).rank()
    best = t.sort_values(["rank", "log_loss"]).iloc[0]
    return replace(base, **{k: float(best[k]) for k in keys}), t


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def benchmark_frame(tables: dict) -> tuple[pd.DataFrame, dict]:
    return bench.forecasts(tables["games"], tables["odds"])


def windows(f: pd.DataFrame) -> list[tuple[str, pd.Series]]:
    """The plan's rows: every game with a closing line (the playoffs too), then each season out of sample."""
    reg = f["season_type"] == "regular"
    has_market = f["market"].notna()
    return [("Pooled 2010-22, games with a closing line", has_market & f["season"].between(2010, 2021)),
            ("2021-22, games with a closing line", has_market & (f["season"] == 2021)),
            ("Out of sample 2020-26, every game", reg & f["season"].between(REPORT_FROM, 2025))] + \
        [(f"{s}-{str(s + 1)[-2:]}", reg & (f["season"] == s)) for s in range(REPORT_FROM, 2026)]


def write_report(f: pd.DataFrame, confirmed: pd.DataFrame, choices: dict, trials: pd.DataFrame | None,
                 root: Path) -> Path:
    order = ("naive", "elo", "poisson", "atlas", "market")
    lines = ["# NHL game model v1 (steps 3 to 5)", "",
             "Generated by `python -m atlas.models.nhl_model`. Every forecast is made before puck drop from games "
             "already played. Atlas prices the expected starting goalie; the confirmed-starter column prices the "
             "goalie who did start, as the price reads once the starter is known at warm-ups.", "",
             "## P(home wins, overtime included): Brier / log loss (games)", "",
             "| Window | " + " | ".join(order) + " | atlas, confirmed starter |", "|---|" + "---|" * (len(order) + 1)]
    fc = f.assign(atlas=f["p_home"], atlas_confirmed=confirmed["p_home"].to_numpy())
    passes = []
    for label, mask in windows(fc):
        part = fc[mask & fc["completed"].astype(bool)]
        y = (part["home_score"] > part["away_score"]).astype(float)
        cells = []
        for m in (*order, "atlas_confirmed"):
            if part[m].notna().all() and len(part):
                cells.append(f"{bench.brier(part[m], y):.4f} / {bench.log_loss(part[m], y):.4f} ({len(part):,})")
            else:
                cells.append("—")
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
        if len(part):
            b = {m: bench.brier(part[m], y) for m in ("elo", "poisson", "atlas")}
            passes.append((label, b["atlas"] < b["elo"] and b["atlas"] < b["poisson"]))
    ok = all(p for _, p in passes)
    lines += ["", f"**v1's bar - beat Elo and the goals-based Poisson model on every row out of sample: "
                  f"{'met' if ok else 'not met'}.**" + ("" if ok else " Rows where it is not: "
                                                        + ", ".join(lbl for lbl, p in passes if not p) + ".")]
    oos = (f["season_type"] == "regular") & f["season"].between(REPORT_FROM, 2025)
    s = scores(f, oos)
    lines += ["", "## The rest of the grid, out of sample 2020-26", "",
              f"- Regulation three-way, ranked probability score: {s['rps']:.4f}",
              f"- CRPS on the final total: {s['crps_total']:.3f}; on the final margin: {s['crps_margin']:.3f}",
              f"- Regulation goals, Poisson log likelihood per side-game: {s['goals_ll']:.4f}", "",
              "| Market | Predicted | Actual | Games | Brier |", "|---|---|---|---|---|"]
    for r in calibration(f, oos).itertuples():
        lines.append(f"| {r.market} | {r.predicted:.3f} | {r.actual:.3f} | {r.n:,} | {r.brier:.4f} |")
    cut = starter_cut(f, f.attrs.get("goalie_games", pd.DataFrame())) if "goalie_games" in f.attrs else None
    lines += ["", "## The goalie test and the prior test, out of sample", "",
              "| Games | Atlas log loss | Elo log loss | Games |", "|---|---|---|---|"]
    tests = [("every game", oos)]
    if cut is not None:
        tests += [("a usual starter out", oos & cut), ("both usual starters in", oos & ~cut)]
    early = early_cut(f)
    tests += [("either side in its first 20", oos & early), ("the rest", oos & ~early)]
    for label, mask in tests:
        part = fc[mask & fc["completed"].astype(bool)]
        y = (part["home_score"] > part["away_score"]).astype(float)
        lines.append(f"| {label} | {bench.log_loss(part['atlas'], y):.4f} | {bench.log_loss(part['elo'], y):.4f} | "
                     f"{len(part):,} |")
    spec = choices["spec"]
    lines += ["", "## Choices", "",
              f"State: {json.dumps(spec)}. Home 5-on-5 term {choices['terms']['home5']:+.3f} goals per 60; "
              f"back-to-back {choices['terms']['b2b']:+.3f} goals.", "",
              "The grid's layers, each season's fitted on the three before it:", "",
              "| Season | Goals before 55:00 per expected goal | Level-score inflation at 55:00 | Gap stretch | "
              "Overtime intercept | Overtime slope |", "|---|---|---|---|---|---|"]
    for season, layer in choices["layers"].items():
        lines.append(f"| {season} | {layer['early']:.3f} | {layer['tie']:+.3f} | {layer['stretch']:.2f} | "
                     f"{layer['ot_intercept']:+.3f} | {layer['ot_slope']:+.3f} |")
    lines += ["", "(Seasons 2010-11 to 2012-13 use layers fitted on themselves: the burn-in, never scored.)"]
    lines += ["", "Tuned on 2017-20 in rounds: first the 5-on-5 process noise, the summer carry, the observation "
              "noises and the blend of expected goals and unblocked attempts (settling the goalie's noise at 2.0 "
              "and the blend at 0.6: expected goals six parts, attempts four); then, with the finishing state "
              "added, its noise; then the edges of both."]
    if trials is not None and len(trials):
        lines += ["", f"The last round, {len(trials)} settings; the best five:", "",
                  "| " + " | ".join(GRID) + " | log loss | goals |", "|" + "---|" * (len(GRID) + 2)]
        for r in trials.sort_values("rank").head(5).itertuples():
            lines.append("| " + " | ".join(f"{getattr(r, k):g}" for k in GRID) + f" | {r.log_loss:.5f} | {r.goals_ll:.5f} |")
    out = report_path(root)
    out.write_text("\n".join(lines) + "\n")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="The NHL game model: tune, walk, score")
    ap.add_argument("--quick", action="store_true", help="the stored choices; no tuning")
    args = ap.parse_args()
    root = config.paths().root
    tables = load_tables()
    trials = None
    if args.quick and json_path(root).exists():
        stored = json.loads(json_path(root).read_text())
        spec = st.Spec(**stored["spec"])
    else:
        spec, trials = tune(tables)
    f, fitted = run(tables, spec)
    layers = fitted["layers"]
    confirmed, _ = run(tables, spec, home5=fitted["terms"]["home5"], b2b=fitted["terms"]["b2b"], layers=layers,
                       confirmed=True)
    b, _ = benchmark_frame(tables)
    f = f.merge(b[["game_id", "naive", "elo", "poisson", "market"]], on="game_id", how="left")
    confirmed = confirmed.set_index("game_id").reindex(f["game_id"]).reset_index()
    f.attrs["goalie_games"] = tables["goalie_games"]
    choices = {"version": VERSION, "spec": asdict(spec), "terms": fitted["terms"], "layers": layers.to_json()}
    json_path(root).write_text(json.dumps(choices, indent=1) + "\n")
    print(write_report(f, confirmed, choices, trials, root))


if __name__ == "__main__":
    main()
