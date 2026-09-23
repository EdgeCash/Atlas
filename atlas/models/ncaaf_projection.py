"""Atlas's own number for every scheduled game: what the card shows.

    python -m atlas.models.ncaaf_projection      # prints the slate

Steps 2-5 of `docs/MODEL_PLAN_NCAAF.md`, run forward to today: the season's
preseason prior, the Kalman state carried through every game already played
this season, the calibrated total, the joint grid. One row per scheduled
FBS-vs-FBS game with the decimal means, the uncertainty, P(home), the
total's central range, the most probable exact score, and the state's view
of each team - the numbers the card's drivers are written from.

The market is never an input. It is on the card for comparison.

:func:`history` is the same machinery walked forward over the completed
seasons: the model's probability against the closing line and what
happened, one row per game and market. That is what the grade is built
from, so the grade describes this model and not an earlier one.
"""

from __future__ import annotations

import argparse
import hashlib
from dataclasses import dataclass

import numpy as np
import pandas as pd

from atlas import config
from atlas.models import joint, kalman
from atlas.models import lattice as lat
from atlas.models import ncaaf_prior as prior_mod
from atlas.models import ncaaf_state as state_mod
from atlas.models import ncaaf_total as total_mod
from atlas.models import reference as ref
from atlas.research.dataset import load_research_frame, research_sample
from atlas.util import get_logger

LOG = get_logger(__name__)

MODEL_NAME = "ncaaf-state-v1"
CHUNK = 200


@dataclass(frozen=True)
class Projector:
    """Everything fitted, as of the last completed game."""

    season: int
    prior: prior_mod.Prior
    state: kalman.State
    spec: kalman.Spec
    choice: state_mod.Choice
    total: total_mod.TotalFit
    grid: lat.Lattice
    played: dict[int, int]            # games of evidence per team this season
    assimilated: int                  # games this season the state has seen
    version: str

    def team(self, team_id: int) -> dict | None:
        """The state's view of one team, in points above FBS average."""
        if team_id not in self.state.index:
            return None
        frame = self.state.frame()
        frame["rank"] = frame["net"].rank(ascending=False, method="min").astype(int)
        row = frame[frame["team_id"] == team_id].iloc[0]
        return {"off": float(row["off"]), "def": float(row["def"]), "net": float(row["net"]),
                "sd_off": float(row["sd_off"]), "sd_def": float(row["sd_def"]),
                "rank": int(row["rank"]), "teams": int(len(frame)),
                "games": int(self.played.get(team_id, 0))}


def _version(season: int, choice: state_mod.Choice, total: total_mod.TotalFit,
             assimilated: int, last_kickoff: str) -> str:
    payload = "|".join([MODEL_NAME, str(season), f"{choice.q:.3f},{choice.p0:.3f},{choice.sigma:.3f}",
                        ",".join(f"{c:.4f}" for c in total.coef), str(assimilated), last_kickoff])
    return hashlib.sha256(payload.encode()).hexdigest()[:12]


def _choice_for(season: int, choices: dict[int, state_mod.Choice] | None, frame, feats, prior):
    """The season's tuned hyperparameters, else the most recent season's, else tune now."""
    if choices:
        if season in choices:
            return choices[season]
        latest = max(choices)
        LOG.info("no tuned hyperparameters for %s; using %s's", season, latest)
        return choices[latest]
    LOG.warning("no saved hyperparameters; tuning in process, which is slow")
    return state_mod.tune(frame, feats, season, like=prior)


def fit(frame: pd.DataFrame, *, season: int | None = None,
        choices: dict[int, state_mod.Choice] | None = None) -> Projector:
    """Fit on every completed season, carry the state through this one.

    ``frame`` is the research frame *with* scheduled games. Completed seasons
    teach the prior, the hyperparameters, the total calibration and the
    lattice, exactly as the walk-forward reports do; this season's completed
    games are assimilated by the filter in kickoff order.
    """
    completed = frame[frame["actual_margin"].notna()]
    sample = research_sample(frame)
    if season is None:
        season = int(frame["season"].max())
    feats = prior_mod.team_seasons(frame)
    prior = prior_mod.fit(sample, feats, season=season)
    choice = _choice_for(season, choices, sample, feats, prior)
    spec = state_mod._spec(choice.q, choice.p0, choice.sigma, prior)

    teams = prior.teams
    state = kalman.initialise(teams["team_id"].to_numpy(), teams["off"].to_numpy(),
                              teams["def"].to_numpy(), spec)
    this_season = completed[completed["season"] == season].sort_values(["kickoff", "week"])
    if not this_season.empty:
        kalman.run_season(this_season, state, spec)
    played = pd.concat([this_season["home_team_id"], this_season["away_team_id"]]).value_counts()
    played = {int(k): int(v) for k, v in played.items()}

    total = total_mod.fit_total(total_mod._training_forecasts(sample, feats, season, choice, prior))
    train = sample[sample["season"] < season]
    if train["closing_spread"].notna().any():
        market = ref.market(train, train)
        grid = lat.fit(train["actual_margin"].to_numpy(), -train["closing_spread"].to_numpy(), market.sigma)
    else:
        grid = lat.Lattice(support=lat.DEFAULT_SUPPORT, factor=np.ones(len(lat.DEFAULT_SUPPORT)),
                           sigma=prior.net.resid_sd, games=0)
    last = str(this_season["kickoff"].max()) if not this_season.empty else ""
    version = _version(season, choice, total, len(this_season), last)
    LOG.info("projector %s: season %s, %d games assimilated, q=%.1f p0=%.0f sigma=%.0f, total sigma %.2f",
             version, season, len(this_season), choice.q, choice.p0, choice.sigma, total.sigma)
    return Projector(season=season, prior=prior, state=state, spec=spec, choice=choice, total=total,
                     grid=grid, played=played, assimilated=int(len(this_season)), version=version)


def project(projector: Projector, scheduled: pd.DataFrame) -> pd.DataFrame:
    """One row per scheduled game the state has both teams for."""
    p = projector
    rows = scheduled[(scheduled["home_team_id"].isin(p.state.index)) &
                     (scheduled["away_team_id"].isin(p.state.index))].copy()
    if rows.empty:
        return pd.DataFrame()
    neutral = pd.to_numeric(rows.get("neutral_site", 0), errors="coerce").fillna(0).to_numpy(dtype=float)
    means, sds, hps, aps = (np.zeros(len(rows)) for _ in range(4))
    for i, (h, a, n) in enumerate(zip(rows["home_team_id"], rows["away_team_id"], neutral, strict=True)):
        means[i], sds[i], hps[i], aps[i] = kalman.forecast(p.state, h, a, 0.0 if n else 1.0, p.spec)
    rows["state_total"] = hps + aps
    total_mean = p.total.mean(rows)
    total_pmf = lat.discretise(total_mean, p.total.sigma, total_mod.TOTAL_SUPPORT)
    margin_pmf = p.grid.pmf(means, sds)
    parts = []
    for start in range(0, len(rows), CHUNK):
        sl = slice(start, start + CHUNK)
        parts.append(joint.build(margin_pmf[sl], p.grid.support, total_pmf[sl], total_mod.TOTAL_SUPPORT).summary())
    summary = pd.concat(parts, ignore_index=True)

    fill = p.total.fill
    coef = dict(zip(p.total.names, p.total.coef[1:], strict=True))

    def adjustment(name: str) -> np.ndarray:
        if name not in coef or name not in rows:
            return np.zeros(len(rows))
        v = pd.to_numeric(rows[name], errors="coerce").to_numpy(dtype=float)
        return coef[name] * (np.where(np.isnan(v), fill.get(name, 0.0), v) - fill.get(name, 0.0))

    views = {side: [p.team(int(t)) for t in rows[f"{side}_team_id"]] for side in ("home", "away")}
    out = pd.DataFrame({
        "game_id": rows["game_id"].to_numpy(), "season": rows["season"].to_numpy(),
        "week": rows["week"].to_numpy(), "kickoff": rows["kickoff"].to_numpy(),
        "home_team_id": rows["home_team_id"].to_numpy(), "away_team_id": rows["away_team_id"].to_numpy(),
        "neutral_site": neutral,
        # Every headline number is a mean of the grid, so the score, the spread
        # and the total agree with each other to the last decimal. The grid is
        # bounded at 0-79 points a side, which moves a lopsided game's means a
        # little from the state's and the calibration's own; the sds are those
        # inputs' and are used only for probabilities at a line.
        "margin_mean": summary["margin_mean"].to_numpy(), "margin_sd": sds,
        "total_mean": summary["total_mean"].to_numpy(), "total_sd": p.total.sigma,
        "home_mean": summary["home_mean"].to_numpy(), "away_mean": summary["away_mean"].to_numpy(),
        "p_home": summary["p_home"].to_numpy(),
        "total_lo": summary["total_lo"].to_numpy(), "total_hi": summary["total_hi"].to_numpy(),
        "top_home": summary["top_home"].to_numpy(), "top_away": summary["top_away"].to_numpy(),
        "top_p": summary["top_p"].to_numpy(),
        "hfa": np.where(neutral > 0, 0.0, p.spec.boost),
        "pace_adj": adjustment("adj_pace_sum"), "wind_adj": adjustment("weather_wind_effective"),
        "model_version": p.version,
    })
    for side in ("home", "away"):
        for key in ("off", "def", "net", "sd_off", "sd_def", "rank", "games"):
            out[f"{side}_{key}"] = [v[key] if v else np.nan for v in views[side]]
    out["teams"] = views["home"][0]["teams"] if views["home"] and views["home"][0] else np.nan
    return out


def history(frame: pd.DataFrame, *, choices: dict[int, state_mod.Choice] | None = None,
            first_test_season: int = total_mod.FIRST_TEST_SEASON) -> pd.DataFrame:
    """The model against the closing line, walk-forward, for the grade.

    One row per completed game and market (``margin``, ``total``):
    ``abs_edge`` is how far the model sat from the closing number,
    ``claimed`` the probability it gave its own side of that number, and
    ``won`` whether that side happened (a push counts half).
    """
    sample = research_sample(frame)
    scored, table, _ = total_mod.run(sample, first_test_season=first_test_season, choices=choices)
    t = table.dropna(subset=["closing_spread", "closing_total"])
    line = -t["closing_spread"].to_numpy(dtype=float)
    p_cover = t["p_cover"].to_numpy(dtype=float)
    margin = t["actual_margin"].to_numpy(dtype=float)
    home_side = p_cover >= 0.5
    happened = np.where(margin == line, 0.5, np.where(home_side, margin > line, margin < line).astype(float))
    rows = [pd.DataFrame({
        "game_id": t["game_id"].to_numpy() if "game_id" in t else np.arange(len(t)),
        "season": t["season"].to_numpy(), "week": t["week"].to_numpy(),
        "season_type": t["season_type"].to_numpy(), "market": "margin",
        "abs_edge": np.abs(t["margin_mean"].to_numpy(dtype=float) - line),
        "claimed": np.maximum(p_cover, 1 - p_cover), "won": happened,
    })]
    tot = scored[(scored["model"] == "total")].dropna(subset=["p_over", "over"])
    if not tot.empty:
        p_over = tot["p_over"].to_numpy(dtype=float)
        over_side = p_over >= 0.5
        over = tot["over"].to_numpy(dtype=float)
        won = np.where(over == 0.5, 0.5, np.where(over_side, over == 1.0, over == 0.0).astype(float))
        rows.append(pd.DataFrame({
            "game_id": tot["game_id"].to_numpy() if "game_id" in tot else np.arange(len(tot)),
            "season": tot["season"].to_numpy(), "week": tot["week"].to_numpy(),
            "season_type": tot["season_type"].to_numpy(), "market": "total",
            "abs_edge": np.abs(tot["mean"].to_numpy(dtype=float) - tot["line"].to_numpy(dtype=float)),
            "claimed": np.maximum(p_over, 1 - p_over), "won": won,
        }))
    return pd.concat(rows, ignore_index=True)


def main() -> None:
    ap = argparse.ArgumentParser(description="Project every scheduled NCAAF game")
    ap.add_argument("--season", type=int, default=None)
    args = ap.parse_args()
    paths = config.paths()
    frame = load_research_frame(paths.warehouse)
    projector = fit(frame, season=args.season, choices=state_mod.load_choices(state_mod.choices_path(paths.root)))
    scheduled = frame[frame["actual_margin"].isna() & (frame["season"] == projector.season)]
    out = project(projector, scheduled)
    names = pd.concat([frame[["home_team_id", "home_team"]].rename(columns={"home_team_id": "t", "home_team": "n"}),
                       frame[["away_team_id", "away_team"]].rename(columns={"away_team_id": "t", "away_team": "n"})]
                      ).drop_duplicates("t").set_index("t")["n"]
    show = out.assign(home=out["home_team_id"].map(names), away=out["away_team_id"].map(names))
    with pd.option_context("display.width", 200, "display.max_rows", 200):
        print(show[["week", "away", "home", "away_mean", "home_mean", "total_mean", "p_home", "top_away", "top_home",
                    "top_p", "margin_sd"]].round(3).to_string(index=False))
    LOG.info("%d projections, model %s", len(out), projector.version)


if __name__ == "__main__":
    main()
