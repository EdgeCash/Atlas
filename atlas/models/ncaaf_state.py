"""The NCAAF state model: the preseason prior, updated by every game.

    python -m atlas.models.ncaaf_state          # -> reports/ncaaf_state.md

Step 3 of `docs/MODEL_PLAN_NCAAF.md`. Each season opens with the step-2
prior for every FBS team (off, def, in points) and a diagonal prior
variance; every FBS-vs-FBS game is then forecast strictly before kickoff and
assimilated afterwards through the joint Kalman filter in
:mod:`atlas.models.kalman`. The covariance is the opponent adjustment.

Hyperparameters - process noise per week, prior variance, observation noise
- are chosen per test season by walk-forward: the filter is run on every
earlier season that has its own point-in-time prior, and the setting with
the best Gaussian predictive log-likelihood on those seasons' games wins.
The test season never touches its own hyperparameters.

Scored beside the references and the prior with the shared harness. The
plan says v1 is done when it beats Elo on every score in every week bucket.
"""

from __future__ import annotations

import argparse
import itertools
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from atlas import config
from atlas.models import evaluate, kalman
from atlas.models import lattice as lat
from atlas.models import ncaaf_prior as prior_mod
from atlas.models import reference as ref
from atlas.research.dataset import load_research_frame, research_sample
from atlas.util import get_logger

LOG = get_logger(__name__)

FIRST_TEST_SEASON = 2021

#: The hyperparameter grid. Variances are in points²; ``q`` per week.
GRID = {
    "q": (0.0, 1.0, 2.0, 4.0, 8.0),
    "p0": (2.0, 5.0, 10.0, 20.0, 40.0, 80.0),
    "sigma": (9.0, 10.0, 11.0, 12.0, 13.0),
}

#: Prior variance for a training season run from a *zero* prior. Fixed, not
#: on the grid: a season that knows nothing wants a large p0 and a season with
#: a real prior wants a small one, and letting the grid see both would let the
#: zero-prior seasons pick p0 for the seasons that actually use it.
ZERO_PRIOR_P0 = 100.0

#: Tune on at most this many of the most recent training seasons. Recency is
#: the point - the game drifts - and it bounds the cost of the grid.
TUNING_SEASONS = 3


@dataclass(frozen=True)
class Choice:
    q: float
    p0: float
    sigma: float
    loglik: float
    seasons: tuple[int, ...]


def choices_path(root: Path) -> Path:
    """Where the tuned hyperparameters are written, so downstream models
    (the total, the grid) reuse the state's choice instead of re-tuning."""
    return root / "reports" / "ncaaf_state_choices.json"


def save_choices(choices: dict[int, Choice], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({str(s): asdict(c) for s, c in sorted(choices.items())}, indent=1) + "\n")


def load_choices(path: Path) -> dict[int, Choice] | None:
    if not path.exists():
        return None
    raw = json.loads(path.read_text())
    return {int(s): Choice(q=c["q"], p0=c["p0"], sigma=c["sigma"], loglik=c["loglik"],
                           seasons=tuple(int(x) for x in c["seasons"])) for s, c in raw.items()}


def _spec(q: float, p0: float, sigma: float, prior: prior_mod.Prior) -> kalman.Spec:
    """Off and def share q and p0 in v1; base and boost come from the prior's points fit."""
    return kalman.Spec(q_off=q, q_def=q, p0_off=p0, p0_def=p0, sigma=sigma,
                       base=prior.points.intercept, boost=prior.points.boost)


def _season_forecasts(games: pd.DataFrame, prior: prior_mod.Prior, spec: kalman.Spec) -> pd.DataFrame:
    teams = prior.teams
    state = kalman.initialise(teams["team_id"].to_numpy(), teams["off"].to_numpy(),
                              teams["def"].to_numpy(), spec)
    return kalman.run_season(games, state, spec), state


def _gaussian_loglik(fc: pd.DataFrame, margin: np.ndarray) -> float:
    r = margin - fc["mean"].to_numpy()
    v = fc["sd"].to_numpy() ** 2
    # A game the state could not forecast (a team it does not carry) is left
    # out rather than turning the whole score into NaN, which ``ll > best``
    # would then never beat, silently keeping the first grid point.
    return float(np.nanmean(-0.5 * np.log(2 * np.pi * v) - r ** 2 / (2 * v)))


def _zero_prior(games: pd.DataFrame, like: prior_mod.Prior, season: int) -> prior_mod.Prior:
    """A prior that knows nothing: every team at league average.

    Used to tune on a training season that has no point-in-time prior of its
    own (the first two seasons of any frame). The filter then learns the
    season from scratch, which is also the state-only ablation.
    """
    teams = np.unique(np.r_[games["home_team_id"], games["away_team_id"]])
    table = pd.DataFrame({"season": season, "team_id": teams, "net": 0.0, "off": 0.0, "def": 0.0})
    return prior_mod.Prior(season=season, net=like.net, points=like.points, teams=table)


def tune(frame: pd.DataFrame, feats: pd.DataFrame, season: int, *, grid: dict = GRID,
         like: prior_mod.Prior | None = None) -> Choice:
    """Pick hyperparameters on the training seasons.

    A training season is run from its own point-in-time prior where one
    exists, and from a zero prior at ``ZERO_PRIOR_P0`` where it does not, so
    ``p0`` is chosen only by seasons that really use it. ``like`` supplies
    base points and home boost for the zero-prior case; it must be fitted on
    seasons before ``season``, which the caller's prior is.
    """
    train_seasons = [int(s) for s in sorted(frame["season"].unique()) if s < season][-TUNING_SEASONS:]
    if not train_seasons:
        raise ValueError(f"no training season before {season}")
    if like is None:
        like = prior_mod.fit(frame, feats, season=season)
    games = {s: frame[(frame["season"] == s) & (frame["season_type"] == "regular")] for s in train_seasons}
    usable = []
    for s in train_seasons:
        try:
            usable.append((s, prior_mod.fit(frame, feats, season=s), False))
        except ValueError:
            usable.append((s, _zero_prior(games[s], like, s), True))
    any_real = any(not zero for _, _, zero in usable)
    p0_grid = grid["p0"] if any_real else (float(np.median(grid["p0"])),)
    best = None
    for q, p0, sigma in itertools.product(grid["q"], p0_grid, grid["sigma"]):
        ll = 0.0
        for s, p, zero in usable:
            spec = _spec(q, ZERO_PRIOR_P0 if zero else p0, sigma, p)
            fc, _ = _season_forecasts(games[s], p, spec)
            ll += _gaussian_loglik(fc, games[s]["actual_margin"].to_numpy(dtype=float)) * len(fc)
        if not np.isfinite(ll):
            continue
        if best is None or ll > best.loglik:
            best = Choice(q, p0, sigma, ll, tuple(int(s) for s, _, _ in usable))
    return best


def run(frame: pd.DataFrame, *, first_test_season: int = FIRST_TEST_SEASON, grid: dict = GRID):
    """Walk-forward: tune on the past, forecast the season, score beside everything."""
    feats = prior_mod.team_seasons(frame)
    scored, choices, finals = [], {}, {}
    for season, train, test in ref.walk_forward(frame, first_test_season=first_test_season):
        prior = prior_mod.fit(frame, feats, season=season)
        choice = tune(frame, feats, season, grid=grid, like=prior)
        choices[season] = choice
        spec = _spec(choice.q, choice.p0, choice.sigma, prior)
        fc, state = _season_forecasts(test, prior, spec)
        finals[season] = state
        refs = ref.all_references(train, test)
        grid_ = lat.fit(train["actual_margin"].to_numpy(), -train["closing_spread"].to_numpy(),
                        refs["market"].sigma)
        keep = {k: refs[k] for k in ("naive", "prior_fpi", "elo", "atlas_epa", "market") if k in refs}
        state_fc = ref.Forecast("state", fc["mean"].to_numpy(dtype=float), fc["sd"].to_numpy(dtype=float))
        prior_fc = prior_mod.game_forecast(prior, test)
        scored.append(evaluate.score(test, {**keep, "prior": prior_fc, "state": state_fc}, grid_, season=season))
        LOG.info("season %s: q=%.1f p0=%.0f sigma=%.0f (tuned on %s); %d games", season, choice.q,
                 choice.p0, choice.sigma, choice.seasons, len(test))
    return pd.concat(scored, ignore_index=True), choices, finals


def render(scored: pd.DataFrame, choices: dict[int, Choice], finals: dict[int, kalman.State],
           frame: pd.DataFrame) -> str:
    seasons = sorted(choices)
    reg = scored[scored["season_type"] == "regular"]
    md, fmt = evaluate.markdown, evaluate.formatted
    order = ("naive", "prior_fpi", "elo", "atlas_epa", "prior", "state", "market")
    parts = [
        "# NCAAF state model",
        "",
        f"Walk-forward, seasons {seasons[0]}-{seasons[-1]}. Each season opens with its own preseason "
        "prior and every FBS-vs-FBS regular-season game is forecast strictly before kickoff, then "
        "assimilated by the joint Kalman filter in `atlas/models/kalman.py`. Hyperparameters are "
        "chosen on the earlier seasons only. Same lattice and scoring as the benchmarks.",
        "",
        "## Hyperparameters chosen, per season",
        "",
        md(pd.DataFrame([{"season": s, "q per week": c.q, "prior var p0": c.p0, "sigma (pts)": c.sigma,
                          "tuned on": ", ".join(map(str, c.seasons))} for s, c in choices.items()])),
        "",
        "## Regular season, pooled",
        "",
        md(fmt(evaluate.summarise(reg, order=order))),
        "",
        "## By week bucket, regular season",
        "",
        "The prior owns weeks 1-2; the state has to own everything after.",
        "",
    ]
    r = reg.copy()
    r["week_bucket"] = evaluate.bucket(r["week"], evaluate.WEEK_BUCKETS, "wk")
    parts += [md(fmt(evaluate.summarise(r, ["week_bucket"], order=order))), "",
              "## By season, regular", "",
              md(fmt(evaluate.summarise(reg, ["season"], order=order))), ""]
    r["spread_bucket"] = evaluate.bucket(r["abs_spread"], evaluate.SPREAD_BUCKETS, "|spread|")
    parts += ["## By closing spread, regular season", "",
              md(fmt(evaluate.summarise(r, ["spread_bucket"], order=order))), ""]
    bowls = scored[scored["season_type"] != "regular"]
    if not bowls.empty:
        parts += ["## Bowls and playoffs (never fitted, always scored)", "",
                  md(fmt(evaluate.summarise(bowls, order=order))), ""]
    parts += ["## Reliability, home-win probability (regular season)", ""]
    from atlas.models import scoring
    for name in ("state", "elo", "market"):
        d = reg[reg["model"] == name]
        if d.empty:
            continue
        t = scoring.reliability(d["p_home"], d["won"])
        parts += [f"### {name}", "",
                  md(t.assign(forecast=t["forecast"].map("{:.3f}".format), observed=t["observed"].map("{:.3f}".format),
                              gap=t["gap"].map("{:+.3f}".format))), ""]
    names = pd.concat([frame[["home_team_id", "home_team"]].rename(columns={"home_team_id": "team_id", "home_team": "team"}),
                       frame[["away_team_id", "away_team"]].rename(columns={"away_team_id": "team_id", "away_team": "team"})]
                      ).drop_duplicates("team_id").set_index("team_id")["team"]
    last = finals[seasons[-1]].frame()
    last["team"] = last["team_id"].map(names)
    last = last.sort_values("net", ascending=False)
    show = pd.concat([last.head(10), last.tail(10)])[["team", "net", "off", "def", "sd_off", "sd_def"]]
    for c in ("net", "off", "def"):
        show[c] = show[c].map("{:+.1f}".format)
    for c in ("sd_off", "sd_def"):
        show[c] = show[c].map("{:.1f}".format)
    parts += [f"## End of {seasons[-1]}: the state's top and bottom ten by net", "",
              "`sd_*` is the filter's remaining uncertainty about the team, in points.", "",
              md(show), ""]
    return "\n".join(parts).rstrip() + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description="NCAAF state model, walk-forward")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--first-test-season", type=int, default=FIRST_TEST_SEASON)
    args = ap.parse_args()
    paths = config.paths()
    frame = research_sample(load_research_frame(paths.warehouse))
    scored, choices, finals = run(frame, first_test_season=args.first_test_season)
    out = args.out or (paths.root / "reports" / "ncaaf_state.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(scored, choices, finals, frame))
    save_choices(choices, choices_path(paths.root) if args.out is None else out.with_suffix(".choices.json"))
    reg = scored[scored["season_type"] == "regular"]
    LOG.info("wrote %s\n%s", out, evaluate.summarise(reg).to_string(index=False))


if __name__ == "__main__":
    main()
