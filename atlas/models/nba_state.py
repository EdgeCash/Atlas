"""The NBA game model: a joint Kalman state over every team's offence and defence, in points.

    python -m atlas.models.nba_state            # -> reports/nba_state.md and reports/nba_state_choices.json

The filter is `atlas/models/kalman.py`, the one the NFL runs, on points
scored: each game is two observations, the home side's and the away's,
assimilated as a margin and a total. What the NBA needs that football does
not is a clock: a team plays three or four times a week, so the process
noise is added by the week of the season (`atlas/staging/nba/games.py`
numbers them from the first regular-season tip) and a season's prior is
last season's state regressed toward the mean. Hyperparameters (the process
variance, the between-season regression and innovation, the noise sd) are
tuned on the training seasons before each test season by the predictive
log-likelihood of regular-season margins; the noise correlation between the
two sides' points is measured on the chosen filter.

The total is fitted on the state's own total (`atlas/models/ncaaf_total.py`:
``actual_total ~ 1 + state_total``), and the line-given reading of P(over) -
how much of the gap between the model's total and a posted total is real -
on the training seasons' closing totals.

Scored walk-forward against the references (naive, Elo, the closing line) on
every season the odds archive covers, 2012-13 to 2022-23: the test season
never touches its own hyperparameters. The record it leaves - each game's
claimed probability at the close and what happened - is what the Polymarket
pricing reads the share of Atlas's disagreement from.
"""

from __future__ import annotations

import argparse
import itertools
import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path

import numpy as np
import pandas as pd

from atlas import config
from atlas.models import elo, evaluate, kalman, scoring
from atlas.models import lattice as lat
from atlas.models import ncaaf_total as tm
from atlas.models import reference as ref
from atlas.research.nba_dataset import load_nba_frame, research_sample
from atlas.util import get_logger

LOG = get_logger(__name__)

SPORT = "nba"
FIRST_TEST_SEASON = 2012
TUNING_SEASONS = 3
WINDOW_SEASONS = 3
#: A side's points sd of about 11 makes a margin sd of about 13 with the correlation the fit finds.
GRID = {"q": (0.0, 0.3, 1.0), "phi": (0.4, 0.6, 0.8), "p_season": (5.0, 15.0, 45.0), "sigma": (10.5, 12.0)}
#: Points a side can score: the total's support runs to twice this.
MAX_POINTS = 200
ORDER = ("naive", "elo", "state", "market")
EDGE_BUCKETS = ((0, 2), (2, 4), (4, 6), (6, 99))
MIN_LINES = 200


@dataclass(frozen=True)
class Choice:
    q: float
    phi: float
    p_season: float
    sigma: float
    loglik: float
    seasons: tuple[int, ...]
    rho: float = 0.0


def choices_path(root: Path) -> Path:
    return root / "reports" / "nba_state_choices.json"


def save_choices(choices: dict[int, Choice], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({str(s): asdict(c) for s, c in sorted(choices.items())}, indent=1) + "\n")


def load_choices(path: Path) -> dict[int, Choice] | None:
    if not path.exists():
        return None
    raw = json.loads(path.read_text())
    return {int(s): Choice(**{**c, "seasons": tuple(c.get("seasons", ()))}) for s, c in raw.items()}


# ---------------------------------------------------------------------------
# The filter
# ---------------------------------------------------------------------------


def _levels(train: pd.DataFrame, season: int) -> tuple[float, float]:
    """League points per team-game and home advantage on the margin, from the most recent training
    seasons, regular season, true home games."""
    recent = train[(train["season"] >= season - WINDOW_SEASONS) & (train["season_type"] == "regular")]
    if recent.empty:
        recent = train
    base = float(recent["actual_total"].mean() / 2.0)
    home = recent[pd.to_numeric(recent.get("neutral_site", pd.Series(0, index=recent.index)), errors="coerce")
                  .fillna(0) == 0]
    return base, float(home["actual_margin"].mean())


def _spec(q: float, sigma: float, base: float, hfa: float, rho: float = 0.0) -> kalman.Spec:
    return kalman.Spec(q_off=q, q_def=q, p0_off=0.0, p0_def=0.0, sigma=sigma, base=base, boost=hfa, rho=rho)


def _fresh(teams: np.ndarray, phi: float, p_season: float, spec: kalman.Spec) -> kalman.State:
    """Every team at league average with the AR(1)'s stationary variance."""
    stationary = p_season / max(1.0 - phi ** 2, 1e-6)
    spec0 = kalman.Spec(**{**asdict(spec), "p0_off": stationary, "p0_def": stationary})
    return kalman.initialise(teams, np.zeros(len(teams)), np.zeros(len(teams)), spec0)


def new_season(state: kalman.State, phi: float, p_season: float) -> None:
    """Regress every strength toward the mean and widen its uncertainty. In place."""
    state.x *= phi
    state.P *= phi * phi
    state.P[np.diag_indices_from(state.P)] += p_season
    state.week = None


def run(frame: pd.DataFrame, seasons: list[int], *, q: float, phi: float, p_season: float, sigma: float,
        levels: dict[int, tuple[float, float]], state: kalman.State | None = None,
        teams: np.ndarray | None = None, rho: float = 0.0) -> tuple[dict[int, pd.DataFrame], kalman.State]:
    """Run the filter through ``seasons`` in order, from ``state`` or from scratch. Returns the pre-tip
    forecasts per season (indexed as ``frame``) and the state after the last one."""
    if teams is None:
        teams = np.unique(np.r_[frame["home_team_id"].dropna().astype(int), frame["away_team_id"].dropna().astype(int)])
    forecasts = {}
    for i, season in enumerate(seasons):
        base, hfa = levels[season]
        spec = _spec(q, sigma, base, hfa, rho)
        if state is None:
            state = _fresh(teams, phi, p_season, spec)
        elif i > 0 or state.week is not None:
            new_season(state, phi, p_season)
        games = frame[frame["season"] == season]
        forecasts[season] = kalman.run_season(games, state, spec)
    return forecasts, state


def _loglik(fc: pd.DataFrame, games: pd.DataFrame) -> float:
    reg = (games["season_type"] == "regular") & games["actual_margin"].notna()
    r = games.loc[reg, "actual_margin"].to_numpy(dtype=float) - fc.loc[reg, "mean"].to_numpy()
    v = fc.loc[reg, "sd"].to_numpy() ** 2
    return float(np.sum(-0.5 * np.log(2 * np.pi * v) - r ** 2 / (2 * v)))


def tune(frame: pd.DataFrame, season: int, levels: dict[int, tuple[float, float]], *, grid: dict = GRID,
         min_train_seasons: int = 2, fit_rho: bool = True) -> Choice:
    """Hyperparameters chosen on the training seasons before ``season``: every candidate runs the filter
    from the first season, and the most recent training seasons are scored by the regular season's
    Gaussian predictive log-likelihood. The test season never touches its own."""
    seasons = [int(s) for s in sorted(frame["season"].unique()) if s < season]
    if len(seasons) < min_train_seasons:
        raise ValueError(f"need {min_train_seasons} training seasons before {season}")
    scored = seasons[-TUNING_SEASONS:]
    train = frame[frame["season"] < season]
    teams = np.unique(np.r_[train["home_team_id"].dropna().astype(int), train["away_team_id"].dropna().astype(int)])
    best = None
    for q, phi, p_season, sigma in itertools.product(grid["q"], grid["phi"], grid["p_season"], grid["sigma"]):
        fcs, _ = run(train, seasons, q=q, phi=phi, p_season=p_season, sigma=sigma, levels=levels, teams=teams)
        ll = sum(_loglik(fcs[s], train[train["season"] == s]) for s in scored)
        if best is None or ll > best.loglik:
            best = Choice(q, phi, p_season, sigma, ll, tuple(scored))
    if best is None or not fit_rho:
        return best
    fcs, _ = run(train, seasons, q=best.q, phi=best.phi, p_season=best.p_season, sigma=best.sigma, levels=levels,
                 teams=teams)
    block = train[train["season"].isin(scored) & train["actual_margin"].notna()]
    fc = pd.concat([fcs[s] for s in scored]).reindex(block.index)
    spec = _spec(best.q, best.sigma, *levels[scored[-1]])
    rho = kalman.noise_correlation(fc, block["actual_margin"].to_numpy(dtype=float),
                                   block["actual_total"].to_numpy(dtype=float), spec)
    return replace(best, sigma=kalman.with_correlation(spec, rho).sigma, rho=rho)


# ---------------------------------------------------------------------------
# The total, and the walk-forward
# ---------------------------------------------------------------------------


def with_forecasts(games: pd.DataFrame, fc: pd.DataFrame) -> pd.DataFrame:
    """``games`` with the state's forecast beside it: the margin's mean and sd, each side's points and the
    state's total."""
    f = fc.reindex(games.index)
    out = games.copy()
    out["margin_mean"], out["margin_sd"] = f["mean"].to_numpy(), f["sd"].to_numpy()
    out["home_pts"], out["away_pts"] = f["home_pts"].to_numpy(), f["away_pts"].to_numpy()
    out["state_total"] = out["home_pts"] + out["away_pts"]
    return out


def fit_total(train_fc: pd.DataFrame) -> tm.TotalFit:
    """The total calibrated on the training seasons' forecasts, with P(over) at a line fitted where the
    archive has closes."""
    train = train_fc.dropna(subset=["state_total", "actual_total"])
    train = train[train["season_type"] == "regular"] if (train["season_type"] == "regular").sum() > MIN_LINES else train
    return tm.fit_over(train, tm.fit_total(train, adjustments=()))


def total_support() -> np.ndarray:
    return tm.total_support(MAX_POINTS)


def p_cover(grid_: lat.Lattice, mean: np.ndarray, sd: np.ndarray, closing_spread: np.ndarray) -> np.ndarray:
    """P(the home side covers the closing spread | no push), from the lattice on the state's margin."""
    pmf = grid_.pmf(np.asarray(mean, dtype=float), np.asarray(sd, dtype=float))
    line = -np.asarray(closing_spread, dtype=float)
    out = np.full(len(line), np.nan)
    for i, ln in enumerate(line):
        if not np.isfinite(ln):
            continue
        above = pmf[i][grid_.support > ln].sum()
        below = pmf[i][grid_.support < ln].sum()
        out[i] = above / (above + below) if above + below > 0 else np.nan
    return out


def walk_forward(frame: pd.DataFrame, *, first_test_season: int = FIRST_TEST_SEASON, grid: dict = GRID,
                 min_train_seasons: int = 2, fit_rho: bool = True, choices: dict[int, Choice] | None = None):
    """Tune on the past, forecast each season the archive prices, score beside the references.

    ``frame`` is every completed game (the state learns from all of them); the seasons scored are those
    with a closing line. Returns (scored, choices, finals, table): the per-model scores, the hyperparameters
    per test season, the state after each, and one row per scored game with the margin's and the total's
    forecast and their claimed probabilities at the close.
    """
    frame = elo.attach(frame[frame["actual_margin"].notna()]).sort_values(["kickoff", "game_id"]).reset_index(drop=True)
    sample = research_sample(frame).set_index("game_id")
    all_seasons = [int(s) for s in sorted(frame["season"].unique())]
    scored, chosen, finals, tables = [], {}, {}, []
    for season, train, test in ref.walk_forward(frame[frame["game_id"].isin(sample.index)],
                                                first_test_season=first_test_season,
                                                min_train_seasons=min_train_seasons):
        levels = {s: _levels(frame[frame["season"] < max(s, all_seasons[0] + 1)], s) for s in all_seasons}
        if choices and season in choices:
            choice = choices[season]
        else:
            choice = tune(frame, season, levels, grid=grid, min_train_seasons=min_train_seasons, fit_rho=fit_rho)
        chosen[season] = choice
        history = [s for s in all_seasons if s < season]
        fcs, state = run(frame[frame["season"] < season], history, q=choice.q, phi=choice.phi,
                         p_season=choice.p_season, sigma=choice.sigma, levels=levels, rho=choice.rho)
        season_fc, state = run(frame, [season], q=choice.q, phi=choice.phi, p_season=choice.p_season,
                               sigma=choice.sigma, levels=levels, state=state, rho=choice.rho)
        finals[season] = state
        fc = season_fc[season].reindex(test.index)
        refs = ref.all_references(train, test)
        grid_ = lat.fit(train["actual_margin"].to_numpy(), -train["closing_spread"].to_numpy(), refs["market"].sigma)
        models = {k: refs[k] for k in ("naive", "elo", "market") if k in refs}
        models["state"] = ref.Forecast("state", fc["mean"].to_numpy(dtype=float), fc["sd"].to_numpy(dtype=float),
                                       hfa=levels[season][1])
        s = evaluate.score(test, models, grid_, season=season)
        scored.append(s)
        # The total on the training seasons' own forecasts, then this season's.
        train_fc = pd.concat([with_forecasts(frame[frame["season"] == h], fcs[h]) for h in history[-TUNING_SEASONS:]],
                             ignore_index=True)
        tfit = fit_total(train_fc)
        test_fc = with_forecasts(test, fc)
        total_mean = tfit.mean(test_fc)
        line = pd.to_numeric(test_fc["closing_total"], errors="coerce").to_numpy(dtype=float)
        p_over = tfit.p_over(total_mean, line, support=total_support())
        pmf = grid_.pmf(fc["mean"].to_numpy(dtype=float), fc["sd"].to_numpy(dtype=float))
        tables.append(pd.DataFrame({
            "game_id": test["game_id"].to_numpy(), "season": season, "week": test["week"].to_numpy(),
            "season_type": test["season_type"].to_numpy(), "kickoff": test["kickoff"].to_numpy(),
            "home_team_id": test["home_team_id"].to_numpy(), "away_team_id": test["away_team_id"].to_numpy(),
            "margin_mean": fc["mean"].to_numpy(dtype=float), "margin_sd": fc["sd"].to_numpy(dtype=float),
            "state_total": test_fc["state_total"].to_numpy(dtype=float), "total_mean": total_mean,
            "total_sigma": tfit.sigma, "p_home": scoring.home_win_probability(pmf, grid_.support),
            "p_cover": p_cover(grid_, fc["mean"].to_numpy(), fc["sd"].to_numpy(), test["closing_spread"].to_numpy()),
            "p_over": p_over, "closing_spread": test["closing_spread"].to_numpy(dtype=float), "closing_total": line,
            "actual_margin": test["actual_margin"].to_numpy(dtype=float),
            "actual_total": test["actual_total"].to_numpy(dtype=float),
        }))
        LOG.info("season %s: q=%.2f phi=%.2f p_season=%.0f sigma=%.1f rho=%.2f (tuned on %s); base %.1f hfa %.2f; "
                 "%d games; total sigma %.2f", season, choice.q, choice.phi, choice.p_season, choice.sigma,
                 choice.rho, choice.seasons, levels[season][0], levels[season][1], len(test), tfit.sigma)
    out = pd.concat(scored, ignore_index=True) if scored else pd.DataFrame()
    table = pd.concat(tables, ignore_index=True) if tables else pd.DataFrame()
    return out, chosen, finals, table


# ---------------------------------------------------------------------------
# The record at the close, and the report
# ---------------------------------------------------------------------------


def calibration(table: pd.DataFrame) -> pd.DataFrame:
    """The model against the closing line, one row per game and market, in the columns
    ``tracking/calibration.csv`` keeps: the size of Atlas's disagreement with the line, the probability it
    claimed for its own side, and whether that side won (a push is one half)."""
    cols = ["game_id", "sport", "season", "week", "season_type", "market", "abs_edge", "claimed", "won", "kickoff"]
    if table.empty:
        return pd.DataFrame(columns=cols)
    t = table.dropna(subset=["closing_spread", "p_cover"])
    line = -t["closing_spread"].to_numpy(dtype=float)
    pc = t["p_cover"].to_numpy(dtype=float)
    margin = t["actual_margin"].to_numpy(dtype=float)
    home_side = pc >= 0.5
    happened = np.where(margin == line, 0.5, np.where(home_side, margin > line, margin < line).astype(float))
    rows = [pd.DataFrame({"game_id": t["game_id"].to_numpy(), "sport": SPORT, "season": t["season"].to_numpy(),
                          "week": t["week"].to_numpy(), "season_type": t["season_type"].to_numpy(), "market": "margin",
                          "abs_edge": np.abs(t["margin_mean"].to_numpy(dtype=float) - line),
                          "claimed": np.maximum(pc, 1 - pc), "won": happened, "kickoff": t["kickoff"].to_numpy()})]
    tot = table.dropna(subset=["closing_total", "p_over"])
    if not tot.empty:
        po = tot["p_over"].to_numpy(dtype=float)
        actual, ln = tot["actual_total"].to_numpy(dtype=float), tot["closing_total"].to_numpy(dtype=float)
        over = np.where(actual == ln, 0.5, (actual > ln).astype(float))
        won = np.where(over == 0.5, 0.5, np.where(po >= 0.5, over == 1.0, over == 0.0).astype(float))
        rows.append(pd.DataFrame({"game_id": tot["game_id"].to_numpy(), "sport": SPORT,
                                  "season": tot["season"].to_numpy(), "week": tot["week"].to_numpy(),
                                  "season_type": tot["season_type"].to_numpy(), "market": "total",
                                  "abs_edge": np.abs(tot["total_mean"].to_numpy(dtype=float) - ln),
                                  "claimed": np.maximum(po, 1 - po), "won": won, "kickoff": tot["kickoff"].to_numpy()}))
    return pd.concat(rows, ignore_index=True).reindex(columns=cols)


def _edge_table(cal: pd.DataFrame, market: str) -> pd.DataFrame:
    c = cal[(cal["market"] == market) & (cal["season_type"] == "regular") & (cal["won"] != 0.5)]
    rows = []
    for lo, hi in EDGE_BUCKETS:
        part = c[(c["abs_edge"] >= lo) & (c["abs_edge"] < hi)]
        rows.append({"Atlas's disagreement": f"{lo}-{hi if hi < 99 else ''} points".replace("-  points", "+ points"),
                     "games": len(part), "claimed": f"{part['claimed'].mean():.1%}" if len(part) else "",
                     "won": f"{part['won'].mean():.1%}" if len(part) else ""})
    return pd.DataFrame(rows)


def render(scored: pd.DataFrame, choices: dict[int, Choice], table: pd.DataFrame) -> str:
    lines = ["# NBA game model: the Kalman state, walk-forward", "",
             "Each season is forecast by a filter tuned only on the seasons before it and scored beside the "
             "references on every game the odds archive prices. Scores: CRPS and MAE on the margin, Brier on "
             "the home win, the expected calibration error of the home win probability.", ""]
    reg = scored[scored["season_type"] == "regular"] if len(scored) else scored
    if len(reg):
        lines += ["## Regular season, every scored season pooled", "",
                  evaluate.markdown(evaluate.formatted(evaluate.summarise(reg, order=ORDER))), "",
                  "## By season", "",
                  evaluate.markdown(evaluate.formatted(evaluate.summarise(reg, by=["season"], order=ORDER)
                                                       .sort_values(["season", "model"]))), ""]
    if choices:
        lines += ["## Hyperparameters", "", "| season | q | phi | p_season | sigma | rho | tuned on |", "|---|---|---|---|---|---|---|"]
        lines += [f"| {s} | {c.q:.2f} | {c.phi:.2f} | {c.p_season:.0f} | {c.sigma:.2f} | {c.rho:.2f} | "
                  f"{', '.join(str(x) for x in c.seasons)} |" for s, c in sorted(choices.items())]
        lines.append("")
    if len(table):
        t = table.dropna(subset=["total_mean", "closing_total", "actual_total"])
        t = t[t["season_type"] == "regular"]
        if len(t):
            lines += ["## The total", "",
                      f"Regular season, {len(t)} games with a closing total. Mean absolute error of the model's "
                      f"total {np.abs(t['total_mean'] - t['actual_total']).mean():.2f}, of the closing total "
                      f"{np.abs(t['closing_total'] - t['actual_total']).mean():.2f}, of the state's raw total "
                      f"{np.abs(t['state_total'] - t['actual_total']).mean():.2f}.", ""]
        cal = calibration(table)
        lines += ["## The record at the close", "",
                  "What Atlas's side of the closing line has been worth, by the size of its disagreement with "
                  "the line: the probability it claimed against what happened. This is what the Polymarket "
                  "pricing reads (`atlas/polymarket/pricing.py`).", "",
                  "### Spread", "", evaluate.markdown(_edge_table(cal, "margin")), "",
                  "### Total", "", evaluate.markdown(_edge_table(cal, "total")), ""]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description="The NBA state model, walk-forward")
    ap.add_argument("--first-test-season", type=int, default=FIRST_TEST_SEASON)
    ap.add_argument("--no-tune", action="store_true", help="use the saved hyperparameters")
    args = ap.parse_args()
    paths = config.paths()
    frame = load_nba_frame(paths.warehouse)
    saved = load_choices(choices_path(paths.root)) if args.no_tune else None
    scored, choices, finals, table = walk_forward(frame, first_test_season=args.first_test_season, choices=saved)
    save_choices(choices, choices_path(paths.root))
    out = paths.reports / "nba_state.md"
    out.write_text(render(scored, choices, table))
    LOG.info("wrote %s and %s", out, choices_path(paths.root))


if __name__ == "__main__":
    main()
