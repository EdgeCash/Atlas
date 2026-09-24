"""Does an offence's early-down EPA make the NFL state model more accurate?

    python -m atlas.research.nfl_early_down     # -> reports/nfl_early_down.md

The state model (`atlas/models/nfl_state.py`, v1.2) learns each team from the
points of its games, and each quarterback also from his EPA per dropback.
Football analytics holds that EPA per play on first and second down is a
steadier read of an offence than its points or its all-down EPA. This tests
that as a third measurement channel (`nfl_state.EfficiencyRecord`): after
each game, an offence's EPA per play is a reading of its offence, its
quarterback and the home advantage against the opposing defence, weighted by
how many plays it rests on.

The protocol, fixed before any season was scored:

* **Candidates.** ``early_down``: first and second down; ``all_downs``: every
  down, the control that says whether "early" is what matters. Scrimmage
  plays, garbage time excluded (``config.GARBAGE_TIME_MARGIN``), as the
  efficiency tables are built.
* **Fitting.** The team and quarterback hyperparameters are the ones v1.2
  chose (``reports/nfl_state_choices.json``), held. Only the channel's weight
  ``k_eff`` - points per unit of EPA per play - is chosen, per test season, on
  the three training seasons before it by the same predictive log-likelihood;
  zero is on the grid, so a channel that does not help can switch itself off.
* **The bar.** A candidate passes if it improves CRPS on the reporting window
  (2023-25) and on every scored season pooled (2020-26), regular season, with
  mean absolute error no worse. Anything else is reported as a failure.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from atlas import config
from atlas.models import elo, evaluate
from atlas.models import lattice as lat
from atlas.models import nfl_benchmarks as nb
from atlas.models import nfl_state as ns
from atlas.models import reference as ref
from atlas.sources import nflverse
from atlas.staging.nfl.efficiency import _is_garbage_time, _scrimmage_plays
from atlas.staging.nfl.games import team_id
from atlas.util import get_logger

LOG = get_logger(__name__)

K_GRID = (0.0, 15.0, 30.0, 45.0, 60.0)
VARIANTS = {"early_down": (1, 2), "all_downs": (1, 2, 3, 4)}
COLUMNS = ["game_id", "posteam", "down", "epa", "rush", "pass", "play_type", "score_differential", "qtr"]


def team_game_epa(raw: Path, seasons: list[int], downs: tuple[int, ...]) -> pd.DataFrame:
    """Each offence's EPA per play in each game on ``downs``, garbage time out, and the per-play variance."""
    parts, sq, n = [], 0.0, 0
    for season in seasons:
        path = nflverse.pbp_path(raw, season)
        if not path.exists():
            continue
        pbp = pd.read_parquet(path, columns=COLUMNS).dropna(subset=["game_id", "posteam"])
        plays = _scrimmage_plays(pbp)
        plays = plays[~_is_garbage_time(plays) & pd.to_numeric(plays["down"], errors="coerce").isin(downs)]
        e = plays["epa"].astype(float)
        sq, n = sq + float(((e - e.mean()) ** 2).sum()), n + len(e)
        g = plays.assign(team_id=team_id(plays["posteam"])).groupby(["game_id", "team_id"], as_index=False).agg(
            epa=("epa", "mean"), plays=("epa", "size"))
        parts.append(g)
    out = pd.concat(parts, ignore_index=True)
    out["game_id"] = out["game_id"].astype(str)
    return out.assign(play_var=sq / max(n, 1))


def prepare(frame: pd.DataFrame) -> pd.DataFrame:
    frame = nb.with_qb_change(elo.attach(frame)).sort_values(["kickoff", "game_id"]).reset_index(drop=True)
    for c in ("home_qb_id", "away_qb_id", "home_qb1_id", "away_qb1_id", "home_qb2_id", "away_qb2_id",
              "home_qb1_out", "away_qb1_out"):
        if c not in frame.columns:
            frame[c] = pd.NA
    return frame


def _forecast(frame: pd.DataFrame, season: int, history: list[int], base: dict,
              eff: ns.EfficiencyRecord | None = None, k_eff: float = 0.0) -> pd.DataFrame:
    """The season forecast strictly before each kickoff, from a state run through ``history``."""
    _, st, starters = ns.run_qb(frame[frame["season"] < season], history, eff=eff, k_eff=k_eff, **base)
    fcs, _, _ = ns.run_qb(frame, [season], state=st, starters=starters, eff=eff, k_eff=k_eff, **base)
    return fcs[season]


def evaluate_channels(frame: pd.DataFrame, choices: dict, qb_choices: dict, record: ns.PasserRecord,
                      channels: dict[str, ns.EfficiencyRecord], *, first_test_season: int = ns.FIRST_TEST_SEASON,
                      k_grid: tuple[float, ...] = K_GRID) -> tuple[pd.DataFrame, dict]:
    """Walk-forward: v1.2 as it stands, and v1.2 with each channel, scored beside the references."""
    all_seasons = [int(s) for s in sorted(frame["season"].unique())]
    scored, picked = [], {name: {} for name in channels}
    for season, train, test in ref.walk_forward(frame, first_test_season=first_test_season):
        if season not in choices or season not in qb_choices:
            continue
        levels = {s: ns._levels(frame[frame["season"] < max(s, all_seasons[0] + 1)], s) for s in all_seasons}
        choice, qbc = choices[season], qb_choices[season]
        history = [s for s in all_seasons if s < season]
        scored_seasons = history[-ns.TUNING_SEASONS:]
        base = dict(choice=choice, p0=qbc.p0, new_mean=qbc.new_mean, levels=levels, k_epa=qbc.k_epa, record=record,
                    k_obs=qbc.k_obs, k_draft=qbc.k_draft)

        refs = ref.all_references(train, test)
        grid_ = lat.fit(train["actual_margin"].to_numpy(), -train["closing_spread"].to_numpy(), refs["market"].sigma)
        models = {k: refs[k] for k in ("naive", "elo", "market") if k in refs}
        fc = _forecast(frame, season, history, base)
        models["v1.2"] = ref.Forecast("v1.2", fc["mean"].to_numpy(dtype=float), fc["sd"].to_numpy(dtype=float))
        for name, eff in channels.items():
            # The weight, chosen on the three training seasons before this one only.
            best, best_ll = 0.0, None
            train_frame = frame[frame["season"] < season]
            for k in k_grid:
                fcs, _, _ = ns.run_qb(train_frame, history, eff=eff, k_eff=k,
                                      teams=np.unique(np.r_[train_frame["home_team_id"], train_frame["away_team_id"]]),
                                      **base)
                ll = sum(ns._loglik(fcs[s], train_frame[train_frame["season"] == s]) for s in scored_seasons)
                if best_ll is None or ll > best_ll:
                    best, best_ll = k, ll
            picked[name][season] = best
            fc = _forecast(frame, season, history, base, eff, best)
            models[name] = ref.Forecast(name, fc["mean"].to_numpy(dtype=float), fc["sd"].to_numpy(dtype=float))
        scored.append(evaluate.score(test, models, grid_, season=season))
        LOG.info("season %s: k_eff %s", season, {n: picked[n][season] for n in channels})
    return pd.concat(scored, ignore_index=True), picked


def verdict(reg: pd.DataFrame, name: str) -> tuple[bool, str]:
    window = reg[reg["season"].isin(ns.REPORT_SEASONS)]

    def m(d, model, col):
        return float(d.loc[d["model"] == model, col].mean())

    better = (m(window, name, "crps") < m(window, "v1.2", "crps") and m(reg, name, "crps") < m(reg, "v1.2", "crps")
              and m(reg, name, "mae") <= m(reg, "v1.2", "mae"))
    text = (f"window CRPS {m(window, name, 'crps'):.3f} vs {m(window, 'v1.2', 'crps'):.3f}; pooled CRPS "
            f"{m(reg, name, 'crps'):.3f} vs {m(reg, 'v1.2', 'crps'):.3f}; pooled MAE {m(reg, name, 'mae'):.2f} vs "
            f"{m(reg, 'v1.2', 'mae'):.2f}")
    return better, text


def render(scored: pd.DataFrame, picked: dict) -> str:
    md, fmt, summarise = evaluate.markdown, evaluate.formatted, evaluate.summarise
    cols = ["crps", "brier", "log_margin", "mae", "ece"]
    order = ("naive", "elo", "v1.2", *picked, "market")
    reg = scored[scored["season_type"] == "regular"]
    window = reg[reg["season"].isin(ns.REPORT_SEASONS)]
    verdicts = {name: verdict(reg, name) for name in picked}
    lines = [f"- **{name}: {'passes' if ok else 'fails'}** - {text}." for name, (ok, text) in verdicts.items()]
    parts = [
        "# NFL: does early-down EPA make the state model more accurate?", "",
        "`atlas/research/nfl_early_down.py`. v1.2 is the state model as it stands; each candidate adds one "
        "measurement per offence per game - its EPA per play on those downs, garbage time out - read as its "
        "offence, quarterback and home advantage against the opposing defence, weighted by its plays. The team "
        "and quarterback hyperparameters are v1.2's, held; only the channel's weight is chosen, per season, on the "
        "three seasons before it. The bar, fixed before scoring: better CRPS on 2023-25 and on 2020-26 pooled, "
        "mean absolute error no worse. Lower is better everywhere.", "",
        "## Verdict", "", *lines, "",
        "## Weight chosen per season (points per unit of EPA per play; 0 = switched off)", "",
        md(pd.DataFrame([{"season": s, **{n: picked[n][s] for n in picked}} for s in sorted(next(iter(
            picked.values())))])), "",
        f"## Reporting window, regular season {ns.REPORT_SEASONS[0]}-{ns.REPORT_SEASONS[-1]}", "",
        md(fmt(summarise(window, order=order), cols)), "",
        "## Every scored season pooled, regular season", "", md(fmt(summarise(reg, order=order), cols)), "",
        "## By season", "", md(fmt(summarise(reg, ["season"], order=order), cols)), "",
    ]
    return "\n".join(parts).rstrip() + "\n"


def main() -> None:
    argparse.ArgumentParser(description="Early-down EPA as a measurement channel in the NFL state model").parse_args()
    from atlas.research.nfl_dataset import (
        load_nfl_frame,
        load_passer_games,
        load_players,
        research_sample,
    )

    paths = config.paths()
    frame = prepare(research_sample(load_nfl_frame(paths.warehouse)))
    loaded = ns.load_choices(ns.choices_path(paths.root))
    if loaded is None:
        raise SystemExit("run `make nfl-state` first: the test holds v1.2's hyperparameters")
    choices, qb_choices = loaded
    record = ns.PasserRecord(load_passer_games(paths.warehouse), load_players(paths.warehouse))
    seasons = [int(s) for s in sorted(frame["season"].unique())]
    channels = {name: ns.EfficiencyRecord(team_game_epa(paths.raw, seasons, downs))
                for name, downs in VARIANTS.items()}
    scored, picked = evaluate_channels(frame, choices, qb_choices, record, channels)
    out = paths.root / "reports" / "nfl_early_down.md"
    out.write_text(render(scored, picked))
    LOG.info("wrote %s", out)


if __name__ == "__main__":
    main()
