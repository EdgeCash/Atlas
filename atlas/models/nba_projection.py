"""Project every NBA game ahead from the state model, and keep its record for the pricing.

    python -m atlas.models.nba_projection           # the slate ahead, to the terminal

Step 6 of `docs/MODEL_PLAN_NBA.md`: the state fitted on every completed
season with the saved hyperparameters (`reports/nba_state_choices.json`),
carried through the games this season has played, and asked about the
games inside :data:`HORIZON`. One row per game keyed by ESPN's event id in
the columns ``tracking/projections.csv`` keeps, ``sport = "nba"``. The
record (:func:`history`) is the walk-forward's claimed probabilities at the
close, in the columns ``tracking/calibration.csv`` keeps.
"""

from __future__ import annotations

import argparse
import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd

from atlas import config
from atlas.models import kalman, scoring
from atlas.models import lattice as lat
from atlas.models import nba_state as ns
from atlas.models import ncaaf_total as tm
from atlas.models import reference as ref
from atlas.research.nba_dataset import load_nba_frame, research_sample
from atlas.util import get_logger

LOG = get_logger(__name__)

MODEL_NAME = "nba-state-v1"
SPORT = "nba"
HORIZON = timedelta(days=8)


@dataclass(frozen=True)
class Projector:
    season: int
    state: kalman.State
    spec: kalman.Spec
    choice: ns.Choice
    total: tm.TotalFit
    grid: lat.Lattice
    played: dict[int, int]
    assimilated: int
    version: str

    def team(self, team_id: int) -> dict | None:
        if team_id not in self.state.index:
            return None
        frame = self.state.frame()
        frame["rank"] = frame["net"].rank(ascending=False, method="min").astype(int)
        row = frame[frame["team_id"] == team_id].iloc[0]
        return {"off": float(row["off"]), "def": float(row["def"]), "net": float(row["net"]),
                "sd_off": float(row["sd_off"]), "sd_def": float(row["sd_def"]),
                "rank": int(row["rank"]), "teams": int(len(frame)), "games": int(self.played.get(team_id, 0))}


def _version(season, choice, total, assimilated, last) -> str:
    payload = "|".join([MODEL_NAME, str(season), f"{choice.q},{choice.phi},{choice.p_season},{choice.sigma},{choice.rho}",
                        ",".join(f"{c:.4f}" for c in total.coef), str(assimilated), last])
    return hashlib.sha256(payload.encode()).hexdigest()[:12]


def _choice_for(season: int, choices, frame, levels) -> ns.Choice:
    if choices:
        s = season if season in choices else max(choices)
        if s != season:
            LOG.info("no tuned NBA hyperparameters for %s; using %s's", season, s)
        return choices[s]
    LOG.warning("no saved NBA hyperparameters; tuning in process, which is slow")
    return ns.tune(frame, season, levels)


def fit(frame: pd.DataFrame, *, season: int | None = None, choices: dict[int, ns.Choice] | None = None) -> Projector:
    """Fit on every completed season, carry the state through this one. ``frame`` is the NBA research
    frame with the schedule, as :func:`atlas.research.nba_dataset.load_nba_frame` returns it."""
    frame = frame.sort_values(["kickoff", "game_id"]).reset_index(drop=True)
    if season is None:
        season = int(frame["season"].max())
    completed = frame[frame["actual_margin"].notna()]
    all_seasons = [int(s) for s in sorted(completed["season"].unique())]
    levels = {s: ns._levels(completed[completed["season"] < max(s, all_seasons[0] + 1)], s)
              for s in [*all_seasons, season]}
    choice = _choice_for(season, choices, completed, levels)
    history = [s for s in all_seasons if s < season]
    fcs, state = ns.run(completed[completed["season"] < season], history, q=choice.q, phi=choice.phi,
                        p_season=choice.p_season, sigma=choice.sigma, levels=levels, rho=choice.rho)
    train_fc = pd.concat([ns.with_forecasts(completed[completed["season"] == h], fcs[h])
                          for h in history[-ns.TUNING_SEASONS:]], ignore_index=True)
    total = ns.fit_total(train_fc)
    # The margin's lattice on the seasons the archive prices, at the market's sd; a plain normal when none.
    train = research_sample(completed[completed["season"] < season])
    if len(train) >= ns.MIN_LINES:
        market = ref.market(train, train)
        grid = lat.fit(train["actual_margin"].to_numpy(), -train["closing_spread"].to_numpy(), market.sigma)
    else:
        sigma = float(np.std(completed["actual_margin"].to_numpy(dtype=float)))
        grid = lat.Lattice(support=lat.DEFAULT_SUPPORT, factor=np.ones(len(lat.DEFAULT_SUPPORT)), sigma=sigma, games=0)
    this_season = completed[completed["season"] == season]
    if not this_season.empty:
        ns.run(completed, [season], q=choice.q, phi=choice.phi, p_season=choice.p_season, sigma=choice.sigma,
               levels=levels, state=state, rho=choice.rho)
    else:
        ns.new_season(state, choice.phi, choice.p_season)
    played = pd.concat([this_season["home_team_id"], this_season["away_team_id"]]).value_counts()
    base, hfa = levels[season]
    spec = ns._spec(choice.q, choice.sigma, base, hfa, choice.rho)
    last = str(this_season["kickoff"].max()) if not this_season.empty else ""
    version = _version(season, choice, total, len(this_season), last)
    LOG.info("nba projector %s: season %s, %d games assimilated, hfa %.2f, total sigma %.2f", version, season,
             len(this_season), hfa, total.sigma)
    return Projector(season=season, state=state, spec=spec, choice=choice, total=total, grid=grid,
                     played={int(k): int(v) for k, v in played.items()}, assimilated=int(len(this_season)),
                     version=version)


def project(projector: Projector, scheduled: pd.DataFrame) -> pd.DataFrame:
    """One row per scheduled game, keyed by ESPN's event id, in the projections table's columns."""
    p = projector
    rows = scheduled[scheduled["home_team_id"].isin(p.state.index) & scheduled["away_team_id"].isin(p.state.index)].copy()
    if rows.empty:
        return pd.DataFrame()
    state = kalman.State(teams=p.state.teams, x=p.state.x.copy(), P=p.state.P.copy(), week=p.state.week,
                         index=dict(p.state.index))
    state.extra.update(p.state.extra)
    fc = kalman.run_season(rows.assign(actual_margin=np.nan, actual_total=np.nan), state, p.spec)
    fc = fc.reindex(rows.index)
    rows["state_total"] = (fc["home_pts"] + fc["away_pts"]).to_numpy()
    total_mean = p.total.mean(rows)
    margin_mean, margin_sd = fc["mean"].to_numpy(dtype=float), fc["sd"].to_numpy(dtype=float)
    pmf = p.grid.pmf(margin_mean, margin_sd)
    neutral = pd.to_numeric(rows.get("neutral_site", pd.Series(0, index=rows.index)), errors="coerce").fillna(0) \
        .to_numpy(dtype=float)
    views = {side: [p.team(int(t)) for t in rows[f"{side}_team_id"]] for side in ("home", "away")}
    out = pd.DataFrame({
        "game_id": pd.to_numeric(rows["espn_id"], errors="coerce").astype("Int64").to_numpy(),
        "sport": SPORT, "season": rows["season"].to_numpy(), "week": rows["week"].to_numpy(),
        "kickoff": rows["kickoff"].to_numpy(), "home_team_id": rows["home_team_id"].to_numpy(),
        "away_team_id": rows["away_team_id"].to_numpy(), "neutral_site": neutral,
        "margin_mean": margin_mean, "margin_sd": margin_sd, "total_mean": total_mean, "total_sd": p.total.sigma,
        "total_over_shrink": np.nan if p.total.over_shrink is None else p.total.over_shrink,
        "total_over_sd": np.nan if p.total.over_sigma is None else p.total.over_sigma,
        "home_mean": (total_mean + margin_mean) / 2.0, "away_mean": (total_mean - margin_mean) / 2.0,
        "p_home": scoring.home_win_probability(pmf, p.grid.support),
        "total_lo": total_mean - 1.2816 * p.total.sigma, "total_hi": total_mean + 1.2816 * p.total.sigma,
        "top_home": np.nan, "top_away": np.nan, "top_p": np.nan,
        "hfa": np.where(neutral > 0, 0.0, p.spec.boost), "pace_adj": 0.0, "wind_adj": 0.0, "wind_mph": np.nan,
        "model_version": p.version,
    })
    for side in ("home", "away"):
        for key in ("off", "def", "net", "sd_off", "sd_def", "rank", "games"):
            out[f"{side}_{key}"] = [v[key] if v else np.nan for v in views[side]]
    out["teams"] = views["home"][0]["teams"] if views["home"] and views["home"][0] else np.nan
    return out.dropna(subset=["game_id"])


def ahead(frame: pd.DataFrame, now: datetime, season: int, horizon: timedelta = HORIZON) -> pd.DataFrame:
    """The season's games not yet played that tip inside the horizon."""
    kick = pd.to_datetime(frame["kickoff"], utc=True, errors="coerce")
    return frame[frame["actual_margin"].isna() & (frame["season"] == season) & (kick > pd.Timestamp(now))
                 & (kick <= pd.Timestamp(now) + horizon)]


def history(paths=None, *, first_test_season: int = ns.FIRST_TEST_SEASON) -> pd.DataFrame:
    """The model against the closing line, walk-forward, for the pricing (``sport = "nba"``)."""
    paths = paths or config.paths()
    frame = load_nba_frame(paths.warehouse)
    choices = ns.load_choices(ns.choices_path(paths.root))
    _, _, _, table = ns.walk_forward(frame, first_test_season=first_test_season, choices=choices)
    return ns.calibration(table)


def main() -> None:
    ap = argparse.ArgumentParser(description="Project every NBA game ahead")
    ap.add_argument("--season", type=int, default=None)
    ap.add_argument("--days", type=int, default=HORIZON.days)
    args = ap.parse_args()
    paths = config.paths()
    frame = load_nba_frame(paths.warehouse)
    projector = fit(frame, season=args.season, choices=ns.load_choices(ns.choices_path(paths.root)))
    out = project(projector, ahead(frame, datetime.now(UTC), projector.season, timedelta(days=args.days)))
    with pd.option_context("display.width", 200, "display.max_rows", 100):
        cols = ["kickoff", "away_team_id", "home_team_id", "away_mean", "home_mean", "total_mean", "p_home", "home_rank",
                "away_rank"]
        print(out[cols].round(3).to_string(index=False) if len(out) else "no games ahead")
    LOG.info("%d projections, model %s", len(out), projector.version)


if __name__ == "__main__":
    main()
