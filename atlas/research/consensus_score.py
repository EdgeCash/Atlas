"""Consensus test: the scoring, run once, against the frozen pre-registration.

    python -m atlas.research.consensus_score      # -> reports/consensus_test.md

Everything this module decides was fixed before it was written, in
``docs/CONSENSUS_PREREGISTRATION.md`` and the constants of
:mod:`atlas.research.consensus_validation`, which this module reads and never
redefines. The holdout is scored **once**: the run refuses to overwrite an
existing report, because a second scoring is a second look.

Conventions (``docs/DATA_DICTIONARY.md``):

* ``actual_margin`` is home minus away;
* ``closing_spread`` is home-oriented, negative when the home side is
  favoured, so the line's implied home margin is ``-closing_spread``;
* ``ats_margin = actual_margin + closing_spread``: the home side covers when
  it is positive, and zero is a push (no action).
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

from atlas import config
from atlas.research import consensus_validation as cv
from atlas.util import get_logger

LOG = get_logger(__name__)

WIN_UNITS = {price: cv.JUICE[price][1] for price in cv.JUICE}


# ---------------------------------------------------------------------------
# The sample
# ---------------------------------------------------------------------------


def eligible(frame: pd.DataFrame) -> pd.DataFrame:
    """FBS against FBS (the research frame already is), regular season, week 5
    on, with a closing spread and a result."""
    week = pd.to_numeric(frame["week"], errors="coerce")
    keep = ((frame["season_type"] == "regular") & (week >= cv.FIRST_WEEK)
            & frame["closing_spread"].notna() & frame["actual_margin"].notna())
    out = frame[keep].copy()
    out["line"] = -out["closing_spread"].astype(float)
    out["ats"] = out["actual_margin"].astype(float) + out["closing_spread"].astype(float)
    return out


def members(games: pd.DataFrame) -> pd.DataFrame:
    """The raw inputs of each point-in-time member, unscaled."""
    out = pd.DataFrame(index=games.index)
    out["elo_diff"] = pd.to_numeric(games["home_pregame_elo"], errors="coerce") - pd.to_numeric(
        games["away_pregame_elo"], errors="coerce")
    neutral = games["neutral_site"].astype("boolean").fillna(False).astype(bool)
    out["home"] = (~neutral).astype(float)
    p = pd.to_numeric(games["fpi_home_win_prob"], errors="coerce").clip(*cv.FPI_PROB_CLIP)
    out["fpi_z"] = norm.ppf(p)
    return out


def coverage(games: pd.DataFrame, raw: pd.DataFrame, seasons) -> pd.DataFrame:
    """Per season: eligible games, and the share with at least one member.
    Read before any outcome is looked at; a season missing from the data
    is listed with zero games, so it is dropped by the rule and named."""
    any_member = raw["elo_diff"].notna() | raw["fpi_z"].notna()
    rows = []
    for season in seasons:
        mask = games["season"].astype(int) == season
        n = int(mask.sum())
        share = float(any_member[mask].mean()) if n else 0.0
        rows.append({"season": season, "games": n, "coverage": share,
                     "elo": float(raw.loc[mask, "elo_diff"].notna().mean()) if n else 0.0,
                     "fpi_projection": float(raw.loc[mask, "fpi_z"].notna().mean()) if n else 0.0,
                     "enters": n > 0 and share >= cv.MIN_COVERAGE})
    return pd.DataFrame(rows)


@dataclass(frozen=True)
class Maps:
    """The implied-margin maps, fitted on the fitting seasons only."""
    elo_a: float
    elo_b: float
    fpi_s: float
    n_elo: int
    n_fpi: int


def fit_maps(games: pd.DataFrame, raw: pd.DataFrame) -> Maps:
    """OLS with no intercept, against the actual home margin."""
    y = games["actual_margin"].astype(float)
    e = raw["elo_diff"].notna()
    X = raw.loc[e, ["elo_diff", "home"]].to_numpy(dtype=float)
    (a, b), *_ = np.linalg.lstsq(X, y[e].to_numpy(), rcond=None)
    f = raw["fpi_z"].notna()
    z = raw.loc[f, "fpi_z"].to_numpy(dtype=float)
    s = float(np.dot(z, y[f].to_numpy()) / np.dot(z, z)) if f.any() else float("nan")
    return Maps(float(a), float(b), s, int(e.sum()), int(f.sum()))


def consensus(raw: pd.DataFrame, maps: Maps) -> pd.Series:
    """The mean of the members available for each game; NaN with neither."""
    elo = maps.elo_a * raw["elo_diff"] + maps.elo_b * raw["home"]
    elo = elo.where(raw["elo_diff"].notna())
    fpi = maps.fpi_s * raw["fpi_z"]
    return pd.concat([elo, fpi], axis=1).mean(axis=1, skipna=True)


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------


def bootstrap(stat, *arrays, rng: np.random.Generator) -> tuple[float, float]:
    """Percentile 95% interval, resampling games."""
    n = len(arrays[0])
    draws = np.empty(cv.N_BOOTSTRAP)
    for i in range(cv.N_BOOTSTRAP):
        idx = rng.integers(0, n, n)
        draws[i] = stat(*(a[idx] for a in arrays))
    return float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5))


def beta(x: np.ndarray, y: np.ndarray) -> float:
    """OLS slope through the origin: y = beta * x."""
    return float(np.dot(x, y) / np.dot(x, x))


def select(games: pd.DataFrame, gap: pd.Series) -> pd.DataFrame:
    """Each season, the fixed fraction with the largest |gap|. Ties at the
    cut break by game_id, so the selection is deterministic."""
    frame = games.assign(gap=gap, absgap=gap.abs()).dropna(subset=["gap"])
    frame = frame[frame["gap"] != 0]
    picked = []
    for _, season in frame.groupby("season"):
        k = int(len(season) * cv.SELECT_FRACTION + 0.5)
        picked.append(season.sort_values(["absgap", "game_id"], ascending=[False, True]).head(k))
    return pd.concat(picked) if picked else frame.iloc[0:0]


def results(picked: pd.DataFrame) -> pd.DataFrame:
    """Taking the side of ``gap`` against the close: 1 a win, 0 a loss.
    Pushes are no action and dropped."""
    live = picked[picked["ats"] != 0]
    won = (np.sign(live["gap"]) == np.sign(live["ats"])).astype(int)
    return live.assign(won=won)


def units(won: np.ndarray, price: int) -> float:
    return float(np.sum(np.where(won == 1, WIN_UNITS[price], -1.0)))


def criteria(r: pd.DataFrame, rng: np.random.Generator) -> dict:
    """SIGNAL_PREREGISTRATION.md's four, as frozen in consensus_validation."""
    won = r["won"].to_numpy()
    n = len(won)
    rate = float(won.mean()) if n else float("nan")
    lo, hi = bootstrap(np.mean, won, rng=rng) if n else (float("nan"), float("nan"))
    by_season = r.groupby("season")["won"].agg(["mean", "size"])
    above = int((by_season["mean"] > cv.BREAK_EVEN).sum())
    u110, u115 = units(won, -110), units(won, cv.STRESS_PRICE)
    checks = {
        "1. pooled win rate > 52.38%": rate > cv.BREAK_EVEN,
        "2. 95% interval lower bound > 50.0%": lo > cv.MIN_CI_LOWER,
        f"3. at least {cv.MIN_SEASONS_ABOVE} holdout seasons above 52.38%": above >= cv.MIN_SEASONS_ABOVE,
        "4. positive units at -115": u115 > 0,
    }
    return {"n": n, "rate": rate, "ci": (lo, hi), "by_season": by_season, "above": above,
            "units_110": u110, "units_115": u115, "checks": checks, "passed": all(checks.values())}


# ---------------------------------------------------------------------------
# Atlas's walk-forward margin (Q2)
# ---------------------------------------------------------------------------


def atlas_margins(frame: pd.DataFrame, choices_path: Path) -> pd.Series:
    """The college state model's walk-forward mean margin per game_id.

    Replays each holdout season with the hyperparameters its walk-forward
    tuning chose from earlier seasons only (``reports/ncaaf_state_choices.json``),
    exactly as ``ncaaf_state.run`` does, without re-tuning."""
    from atlas.models import ncaaf_prior as prior_mod
    from atlas.models import ncaaf_state as state
    from atlas.models import reference as ref

    choices = state.load_choices(choices_path)
    if not choices:
        raise SystemExit(f"no saved state choices at {choices_path}; run `make ncaaf-state` first")
    feats = prior_mod.team_seasons(frame)
    out = []
    first = min(cv.HOLDOUT_SEASONS)
    for season, _train, test in ref.walk_forward(frame, first_test_season=first):
        if season not in cv.HOLDOUT_SEASONS:
            continue
        if season not in choices:
            raise SystemExit(f"no saved state choice for {season}")
        c = choices[season]
        prior = prior_mod.fit(frame, feats, season=season)
        fc, _ = state._season_forecasts(test, prior, state._spec(c.q, c.p0, c.sigma, prior, c.rho))
        out.append(pd.Series(fc["mean"].to_numpy(dtype=float), index=test.loc[fc.index, "game_id"].to_numpy()))
    return pd.concat(out) if out else pd.Series(dtype=float)


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------


@dataclass
class Outcome:
    coverage: pd.DataFrame
    fit_seasons: list[int]
    holdout_seasons: list[int]
    maps: Maps
    n_holdout: int
    beta: float
    beta_ci: tuple[float, float]
    q1_pass: bool
    q1b: dict
    q2_agree: dict | None
    q2_disagree_n: int
    q2_disagree_rate: float
    q2_edge_ci: tuple[float, float]
    q2_pass: bool
    q2_unsplit: int
    decision: str


def score(frame: pd.DataFrame, atlas: pd.Series | None) -> Outcome:
    """Score the frozen test on ``frame`` (the FBS research frame). ``atlas``
    maps game_id to Atlas's walk-forward margin; None skips Q2."""
    rng = np.random.default_rng(cv.SEED)
    games = eligible(frame)
    raw = members(games)

    cov = coverage(games, raw, [*cv.FIT_SEASONS, *cv.HOLDOUT_SEASONS])
    entering = set(cov.loc[cov["enters"], "season"].astype(int))
    fit_seasons = [s for s in cv.FIT_SEASONS if s in entering]
    holdout = [s for s in cv.HOLDOUT_SEASONS if s in entering]
    if not fit_seasons or not holdout:
        raise SystemExit(f"coverage rule leaves fit={fit_seasons} holdout={holdout}; nothing to score")

    season = games["season"].astype(int)
    fit_mask, hold_mask = season.isin(fit_seasons), season.isin(holdout)
    maps = fit_maps(games[fit_mask], raw[fit_mask])

    every = games[hold_mask].copy()
    every["consensus"] = consensus(raw[hold_mask], maps)
    hold = every[every["consensus"].notna()]
    x = (hold["consensus"] - hold["line"]).to_numpy(dtype=float)
    y = hold["ats"].to_numpy(dtype=float)

    # Q1: every holdout game.
    b = beta(x, y)
    b_ci = bootstrap(beta, x, y, rng=rng)
    q1_pass = b_ci[0] > cv.MIN_BETA_LOWER

    # Q1b: the consensus's own strongest disagreements.
    q1b = criteria(results(select(hold, hold["consensus"] - hold["line"])), rng)

    # Q2: Atlas's strongest disagreements, split by agreement.
    q2_agree, dis_n, dis_rate, edge_ci, q2_pass = None, 0, float("nan"), (float("nan"), float("nan")), False
    q2_unsplit = 0
    if atlas is not None:
        # Selected from every eligible holdout game, as pre-registered; a
        # selected game with no consensus cannot be split and is counted.
        every["atlas"] = every["game_id"].map(atlas)
        with_atlas = every[every["atlas"].notna()]
        picked = results(select(with_atlas, with_atlas["atlas"] - with_atlas["line"]))
        q2_unsplit = int(picked["consensus"].isna().sum())
        picked = picked[picked["consensus"].notna()]
        agree_mask = np.sign(picked["consensus"] - picked["line"]) == np.sign(picked["gap"])
        agree, disagree = picked[agree_mask], picked[~agree_mask]
        q2_agree = criteria(agree, rng)
        dis_n = len(disagree)
        dis_rate = float(disagree["won"].mean()) if dis_n else float("nan")
        if len(agree) and dis_n:
            a_won, d_won = agree["won"].to_numpy(), disagree["won"].to_numpy()
            draws = np.empty(cv.N_BOOTSTRAP)
            for i in range(cv.N_BOOTSTRAP):
                draws[i] = (a_won[rng.integers(0, len(a_won), len(a_won))].mean()
                            - d_won[rng.integers(0, len(d_won), len(d_won))].mean())
            edge_ci = (float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5)))
        q2_pass = bool(q2_agree["passed"] and edge_ci[0] > cv.MIN_AGREE_EDGE_LOWER)

    if q1_pass and q2_pass:
        decision = ("Q1 and Q2 pass. Freeze a college spreads rule (v3): Atlas's strongest 10% where the "
                    "consensus agrees, with its own sealed record from the day it is frozen.")
    elif q1_pass:
        decision = ("Q1 passes, Q2 does not. The consensus carries information but does not sharpen Atlas's "
                    "selections. No rule; the consensus stays a label on the owner page.")
    else:
        decision = "Q1 fails. No rule. The consensus is a label on the owner page and nothing more."

    return Outcome(cov, fit_seasons, holdout, maps, len(hold), b, b_ci, q1_pass, q1b, q2_agree,
                   dis_n, dis_rate, edge_ci, q2_pass, q2_unsplit, decision)


# ---------------------------------------------------------------------------
# The report
# ---------------------------------------------------------------------------


def _pct(x: float) -> str:
    return "—" if x != x else f"{x * 100:.2f}%"


def _yes(ok: bool) -> str:
    return "pass" if ok else "**fail**"


def _criteria_table(c: dict) -> list[str]:
    lines = ["| Criterion | Result | |", "|---|---|---|"]
    values = [
        f"{_pct(c['rate'])} of {c['n']}",
        f"{_pct(c['ci'][0])} (95% interval {_pct(c['ci'][0])} to {_pct(c['ci'][1])})",
        f"{c['above']} of {len(c['by_season'])}",
        f"{c['units_115']:+.1f} units (at -110: {c['units_110']:+.1f})",
    ]
    for (name, ok), value in zip(c["checks"].items(), values, strict=True):
        lines.append(f"| {name} | {value} | {_yes(ok)} |")
    lines += ["", "| Season | Win rate | n |", "|---|---|---|"]
    for season, row in c["by_season"].iterrows():
        lines.append(f"| {season} | {_pct(row['mean'])} | {int(row['size'])} |")
    return lines


def render(o: Outcome) -> str:
    dropped = [int(s) for s in o.coverage.loc[~o.coverage["enters"], "season"]]
    lines = [
        "# Consensus test — result",
        "",
        "Scored once against `docs/CONSENSUS_PREREGISTRATION.md`, with the constants of "
        "`atlas/research/consensus_validation.py`. College, FBS against FBS, regular season, "
        f"week {cv.FIRST_WEEK} on, against the closing spread. Owner page only.",
        "",
        "## Decision",
        "",
        o.decision,
        "",
        "## Coverage (read before any outcome)",
        "",
        "| Season | Games | Any member | Elo | FPI projection | Enters |",
        "|---|---|---|---|---|---|",
    ]
    for _, r in o.coverage.iterrows():
        lines.append(f"| {int(r['season'])} | {int(r['games'])} | {_pct(r['coverage'])} | {_pct(r['elo'])} | "
                     f"{_pct(r['fpi_projection'])} | {'yes' if r['enters'] else 'no'} |")
    lines += [
        "",
        f"Fitting seasons used: {', '.join(map(str, o.fit_seasons))}. "
        f"Holdout seasons scored: {', '.join(map(str, o.holdout_seasons))}."
        + (f" Dropped by the coverage rule: {', '.join(map(str, dropped))}." if dropped else ""),
        "",
        "## Implied-margin maps (fitting seasons only)",
        "",
        f"- Elo: margin = {o.maps.elo_a:.4f} × (home Elo − away Elo) + {o.maps.elo_b:.2f} × home "
        f"({o.maps.n_elo} games)",
        f"- FPI projection: margin = {o.maps.fpi_s:.2f} × Φ⁻¹(p) ({o.maps.n_fpi} games)",
        "",
        "## Q1: does the consensus know something the close does not?",
        "",
        f"(actual margin − close) = β × (consensus − close), over {o.n_holdout} holdout games.",
        "",
        f"β = {o.beta:.4f}, 95% interval {o.beta_ci[0]:.4f} to {o.beta_ci[1]:.4f}: **{_yes(o.q1_pass)}** "
        "(the lower bound must be above 0).",
        "",
        "### Q1b: the consensus's strongest 10% each season, its side against the close",
        "",
        *_criteria_table(o.q1b),
        "",
        f"All four required: **{_yes(o.q1b['passed'])}**. Q1b does not change the decision; "
        "it is the tradable version of Q1, reported as pre-registered.",
        "",
        "## Q2: does agreement make Atlas's strongest spread disagreements better?",
        "",
    ]
    if o.q2_agree is None:
        lines.append("Not scored: Atlas's walk-forward margins were not available.")
    else:
        lines += [
            "Atlas's strongest 10% each season, where the consensus is on the same side of the close:",
            "",
            *_criteria_table(o.q2_agree),
            "",
            f"Where it disagrees: {_pct(o.q2_disagree_rate)} of {o.q2_disagree_n}. "
            f"Selected but without a consensus, so in neither group: {o.q2_unsplit}.",
            "",
            f"Agree minus disagree, 95% interval {_pct(o.q2_edge_ci[0])} to {_pct(o.q2_edge_ci[1])} "
            "(the lower bound must be above 0).",
            "",
            f"Both required: **{_yes(o.q2_pass)}**. Power was stated in advance: this population is small, "
            "so a fail here means not shown, not absent.",
        ]
    lines += [
        "",
        "## Conventions",
        "",
        f"Bootstrap of {cv.N_BOOTSTRAP:,} resamples by game, percentile intervals, seed {cv.SEED}. "
        "Pushes are no action. A win at -110 returns +0.909 units and a loss costs 1.000.",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Score the pre-registered consensus test, once.")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--skip-q2", action="store_true", help="score Q1 only (no state model replay)")
    args = ap.parse_args(argv)
    paths = config.paths()
    out = args.out or (paths.root / "reports" / "consensus_test.md")
    if out.exists():
        LOG.error("%s exists: the holdout is scored once. Refusing to score it again.", out)
        return 2

    from atlas.models import ncaaf_state as state
    from atlas.research.dataset import load_research_frame

    frame = state.every_game(load_research_frame(paths.warehouse))
    atlas = None if args.skip_q2 else atlas_margins(frame, state.choices_path(paths.root))
    outcome = score(frame, atlas)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(outcome))
    LOG.info("wrote %s: %s", out, outcome.decision)
    return 0


if __name__ == "__main__":
    sys.exit(main())
