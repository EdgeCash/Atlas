"""Atlas's own number for every scheduled NFL game: what the card shows.

    python -m atlas.models.nfl_projection        # prints the slate

Step 6 of `docs/MODEL_PLAN_NFL.md`, the NFL twin of
:mod:`atlas.models.ncaaf_projection`: the quarterback state model carried
through every game already played (steps 3-4), the calibrated total and
the 60x60 grid with its points lattice (step 5), one row per scheduled
game. Rows are keyed by ESPN's event id, which is what the odds poll, the
game metadata and the card key on, and carry ``sport = "nfl"``.

:func:`history` is the same machinery walked forward over completed
seasons, the model's probability against the closing line and what
happened, for the grade.
"""

from __future__ import annotations

import argparse
import hashlib
from dataclasses import dataclass, replace

import numpy as np
import pandas as pd

from atlas import config
from atlas.models import joint, kalman
from atlas.models import lattice as lat
from atlas.models import ncaaf_total as tm
from atlas.models import nfl_state as ns
from atlas.models import nfl_total as nt
from atlas.models import reference as ref
from atlas.research.nfl_dataset import (
    load_nfl_frame,
    load_passer_games,
    load_players,
    research_sample,
)
from atlas.util import get_logger

LOG = get_logger(__name__)

MODEL_NAME = "nfl-state-qb-v1"
SPORT = "nfl"
CHUNK = 200


@dataclass(frozen=True)
class Projector:
    season: int
    state: kalman.State
    spec: kalman.Spec
    choice: ns.Choice
    qb: ns.QBChoice
    total: tm.TotalFit
    grid: lat.Lattice
    record: ns.PasserRecord | None
    starters: dict
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

    def quarterback(self, qb_id) -> float | None:
        key = ("qb", str(qb_id))
        return self.state.value(key) if key in self.state.extra else None


def _version(season, choice, qb, total, assimilated, last) -> str:
    payload = "|".join([MODEL_NAME, str(season), f"{choice.q},{choice.phi},{choice.p_season},{choice.sigma}",
                        f"{qb.p0},{qb.new_mean},{qb.k_epa},{qb.k_obs},{qb.k_draft}", ",".join(f"{c:.4f}" for c in total.coef), str(assimilated), last])
    return hashlib.sha256(payload.encode()).hexdigest()[:12]


def _choices_for(season: int, choices, frame, levels):
    if choices:
        team, qb = choices
        s = season if season in team else max(team)
        if s != season:
            LOG.info("no tuned NFL hyperparameters for %s; using %s's", season, s)
        return team[s], qb[s]
    LOG.warning("no saved NFL hyperparameters; tuning in process, which is slow")
    c = ns.tune(frame, season, levels)
    return c, ns.tune_qb(frame, season, c, levels)


def fit(frame: pd.DataFrame, *, season: int | None = None, choices=None,
        passers: pd.DataFrame | None = None, players: pd.DataFrame | None = None) -> Projector:
    """Fit on every completed season, carry the state through this one.

    ``frame`` is the NFL research frame *with* scheduled games, as
    :func:`atlas.research.nfl_dataset.load_nfl_frame` returns it;
    ``passers`` the staged passer log, for a new quarterback's prior.
    """
    frame = nt.prepare(frame)
    record = ns.PasserRecord(passers, players) if passers is not None else None
    if season is None:
        season = int(frame["season"].max())
    completed = frame[frame["actual_margin"].notna()]
    sample = research_sample(frame)
    all_seasons = [int(s) for s in sorted(completed["season"].unique())]
    levels = {s: ns._levels(sample[sample["season"] < max(s, all_seasons[0] + 1)], s) for s in [*all_seasons, season]}
    choice, qb = _choices_for(season, choices, sample, levels)
    history = [s for s in all_seasons if s < season]
    fcs, state, starters = ns.run_qb(completed[completed["season"] < season], history, choice=choice, p0=qb.p0,
                                     new_mean=qb.new_mean, levels=levels, k_epa=qb.k_epa, record=record, k_obs=qb.k_obs,
                                     k_draft=qb.k_draft)
    train_fc = pd.concat([nt._with_forecasts(completed[completed["season"] == s], fcs[s])
                          for s in history[-ns.TUNING_SEASONS:]], ignore_index=True)
    train_fc = train_fc[train_fc["season_type"] == "regular"]
    total = tm.fit_total(train_fc, nt.ADJUSTMENTS)
    train = sample[sample["season"] < season]
    market = ref.market(train, train)
    grid = lat.fit(train["actual_margin"].to_numpy(), -train["closing_spread"].to_numpy(), market.sigma)
    total = replace(total, points_factor=tm.fit_points_lattice(train_fc, grid, total, nt.MAX_POINTS))
    this_season = completed[completed["season"] == season]
    if not this_season.empty:
        ns.run_qb(frame, [season], choice=choice, p0=qb.p0, new_mean=qb.new_mean, levels=levels, state=state,
                  starters=starters, k_epa=qb.k_epa, record=record, k_obs=qb.k_obs, k_draft=qb.k_draft)
    else:
        ns.new_season(state, choice.phi, choice.p_season)
    played = pd.concat([this_season["home_team_id"], this_season["away_team_id"]]).value_counts()
    base, hfa = levels[season]
    spec = ns._spec(choice.q, choice.sigma, base, hfa)
    last = str(this_season["kickoff"].max()) if not this_season.empty else ""
    version = _version(season, choice, qb, total, len(this_season), last)
    LOG.info("nfl projector %s: season %s, %d games assimilated, hfa fitted %.2f, total sigma %.2f",
             version, season, len(this_season), state.value(ns.HFA_KEY) if ns.HFA_KEY in state.extra else hfa, total.sigma)
    return Projector(season=season, state=state, spec=spec, choice=choice, qb=qb, total=total, grid=grid,
                     record=record, starters=starters, played={int(k): int(v) for k, v in played.items()},
                     assimilated=int(len(this_season)), version=version)


def project(projector: Projector, scheduled: pd.DataFrame) -> pd.DataFrame:
    """One row per scheduled game, keyed by ESPN's event id."""
    p = projector
    rows = scheduled[(scheduled["home_team_id"].isin(p.state.index)) &
                     (scheduled["away_team_id"].isin(p.state.index))].copy()
    if rows.empty:
        return pd.DataFrame()
    if "wind_effective" not in rows:
        rows = nt.prepare(rows)
    # Forecast every scheduled game from the state as it stands: a copy, so
    # nothing is assimilated (there is nothing to assimilate).
    state = kalman.State(teams=p.state.teams, x=p.state.x.copy(), P=p.state.P.copy(), week=p.state.week,
                         index=dict(p.state.index))
    state.extra.update(p.state.extra)
    fc = ns.run_season_qb(rows.assign(actual_margin=np.nan, actual_total=np.nan), state, p.spec, p0=p.qb.p0,
                          new_mean=p.qb.new_mean, starters=dict(p.starters), k_epa=p.qb.k_epa, record=p.record, k_obs=p.qb.k_obs,
                          k_draft=p.qb.k_draft)
    rows["state_total"] = (fc["home_pts"] + fc["away_pts"]).to_numpy()
    total_mean = p.total.mean(rows)
    support = tm.total_support(nt.MAX_POINTS)
    total_pmf = lat.discretise(total_mean, p.total.sigma, support)
    margin_pmf = p.grid.pmf(fc["mean"].to_numpy(dtype=float), fc["sd"].to_numpy(dtype=float))
    parts = []
    for start in range(0, len(rows), CHUNK):
        sl = slice(start, start + CHUNK)
        J = joint.build(margin_pmf[sl], p.grid.support, total_pmf[sl], support, max_points=nt.MAX_POINTS)
        parts.append(J.reweight(p.total.points_factor).summary())
    summary = pd.concat(parts, ignore_index=True)
    coef = dict(zip(p.total.names, p.total.coef[1:], strict=True))
    fill = p.total.fill
    wind = pd.to_numeric(rows.get("wind_effective"), errors="coerce").to_numpy(dtype=float)
    wind_adj = coef.get("wind_effective", 0.0) * (np.where(np.isnan(wind), fill.get("wind_effective", 0.0), wind)
                                                 - fill.get("wind_effective", 0.0))
    neutral = pd.to_numeric(rows.get("neutral_site", 0), errors="coerce").fillna(0).to_numpy(dtype=float)
    hfa = state.value(ns.HFA_KEY) if ns.HFA_KEY in state.extra else p.spec.boost
    views = {side: [p.team(int(t)) for t in rows[f"{side}_team_id"]] for side in ("home", "away")}
    out = pd.DataFrame({
        "game_id": pd.to_numeric(rows["espn_id"], errors="coerce").astype("Int64").to_numpy(),
        "sport": SPORT, "season": rows["season"].to_numpy(), "week": rows["week"].to_numpy(),
        "kickoff": rows["kickoff"].to_numpy(), "home_team_id": rows["home_team_id"].to_numpy(),
        "away_team_id": rows["away_team_id"].to_numpy(), "neutral_site": neutral,
        "margin_mean": summary["margin_mean"].to_numpy(), "margin_sd": fc["sd"].to_numpy(),
        "total_mean": summary["total_mean"].to_numpy(), "total_sd": p.total.sigma,
        "home_mean": summary["home_mean"].to_numpy(), "away_mean": summary["away_mean"].to_numpy(),
        "p_home": summary["p_home"].to_numpy(), "total_lo": summary["total_lo"].to_numpy(),
        "total_hi": summary["total_hi"].to_numpy(), "top_home": summary["top_home"].to_numpy(),
        "top_away": summary["top_away"].to_numpy(), "top_p": summary["top_p"].to_numpy(),
        "hfa": np.where(neutral > 0, 0.0, hfa), "pace_adj": 0.0, "wind_adj": wind_adj,
        "model_version": p.version,
    })
    for side in ("home", "away"):
        for key in ("off", "def", "net", "sd_off", "sd_def", "rank", "games"):
            out[f"{side}_{key}"] = [v[key] if v else np.nan for v in views[side]]
    out["teams"] = views["home"][0]["teams"] if views["home"] and views["home"][0] else np.nan
    out["nfl_game_id"] = rows["game_id"].to_numpy()
    return out.dropna(subset=["game_id"])


def _passers(paths) -> pd.DataFrame | None:
    try:
        return load_passer_games(paths.warehouse)
    except Exception as error:  # noqa: BLE001 - an older warehouse has no passer log
        LOG.warning("no passer log in the warehouse (%s); new quarterbacks get the flat prior", error)
        return None


def _players(paths) -> pd.DataFrame:
    """Draft picks for the new-quarterback prior; empty (the centre for everyone) if not staged."""
    return load_players(paths.warehouse)


def history(paths=None, *, first_test_season: int = nt.FIRST_TEST_SEASON) -> pd.DataFrame:
    """The model against the closing line, walk-forward, for the grade (``sport = "nfl"``)."""
    paths = paths or config.paths()
    frame = research_sample(load_nfl_frame(paths.warehouse))
    choices = ns.load_choices(ns.choices_path(paths.root))
    scored, table, _ = nt.run(frame, first_test_season=first_test_season, choices=choices, passers=_passers(paths),
                              players=_players(paths))
    t = table.dropna(subset=["closing_spread", "closing_total", "p_cover"])
    line = -t["closing_spread"].to_numpy(dtype=float)
    p_cover = t["p_cover"].to_numpy(dtype=float)
    margin = t["actual_margin"].to_numpy(dtype=float)
    home_side = p_cover >= 0.5
    happened = np.where(margin == line, 0.5, np.where(home_side, margin > line, margin < line).astype(float))
    rows = [pd.DataFrame({"game_id": t["game_id"].to_numpy(), "sport": SPORT, "season": t["season"].to_numpy(),
                          "week": t["week"].to_numpy(), "season_type": t["season_type"].to_numpy(), "market": "margin",
                          "abs_edge": np.abs(t["margin_mean"].to_numpy(dtype=float) - line),
                          "claimed": np.maximum(p_cover, 1 - p_cover), "won": happened})]
    tot = scored[scored["model"] == "total"].dropna(subset=["p_over", "over"])
    if not tot.empty:
        p_over = tot["p_over"].to_numpy(dtype=float)
        over = tot["over"].to_numpy(dtype=float)
        won = np.where(over == 0.5, 0.5, np.where(p_over >= 0.5, over == 1.0, over == 0.0).astype(float))
        rows.append(pd.DataFrame({"game_id": tot["game_id"].to_numpy(), "sport": SPORT, "season": tot["season"].to_numpy(),
                                  "week": tot["week"].to_numpy(), "season_type": tot["season_type"].to_numpy(),
                                  "market": "total",
                                  "abs_edge": np.abs(tot["mean"].to_numpy(dtype=float) - tot["line"].to_numpy(dtype=float)),
                                  "claimed": np.maximum(p_over, 1 - p_over), "won": won}))
    return pd.concat(rows, ignore_index=True)


def main() -> None:
    ap = argparse.ArgumentParser(description="Project every scheduled NFL game")
    ap.add_argument("--season", type=int, default=None)
    args = ap.parse_args()
    paths = config.paths()
    frame = load_nfl_frame(paths.warehouse)
    projector = fit(frame, season=args.season, choices=ns.load_choices(ns.choices_path(paths.root)),
                    passers=_passers(paths), players=_players(paths))
    scheduled = frame[frame["actual_margin"].isna() & (frame["season"] == projector.season)]
    out = project(projector, scheduled)
    with pd.option_context("display.width", 200, "display.max_rows", 100):
        print(out[["week", "nfl_game_id", "away_mean", "home_mean", "total_mean", "p_home", "top_away", "top_home", "top_p"]]
              .round(3).to_string(index=False))
    LOG.info("%d projections, model %s", len(out), projector.version)


if __name__ == "__main__":
    main()
