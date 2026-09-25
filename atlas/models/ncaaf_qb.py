"""The college quarterback: a state for each starter, inside the season.

    python -m atlas.models.ncaaf_qb             # -> reports/ncaaf_qb.md

`docs/MODEL_PLAN_NCAAF.md` factor 9: a change of quarterback of record moves
the state's residual about -3.2 points, on a fifth of team-games, and was
never modelled because Atlas had no source for who plays. ESPN's box scores
(`atlas/sources/espn_cfb.py`, cached for college DFS) name him for every game:
the passer with the most attempts.

The college state (`atlas/models/ncaaf_state.py`) re-opens each season from
its preseason prior, which already carries returning production and the
portal. So the quarterback lives inside the season, as the NFL's does
across them (`atlas/models/nfl_state.py`, step 4):

* **Forecast** with the expected starter: the team's quarterback of record
  in its previous game this season, which is known before kickoff. In a
  team's first game there is none; the prior already assumes its starter.
* **Enter** a team's first starter at zero - he is who the prior assumed -
  and any later new starter at ``new_mean`` (the backup's price, as a prior),
  both with variance ``p0``; a quarterback carries ``QB_Q`` of process noise a
  week.
* **Learn** from who played: each side's points are its offence, its
  quarterback of record and the home boost against the opposing defence.

``p0`` and ``new_mean`` are chosen per test season on the three training
seasons before it, the team hyperparameters held at the state's own
(``reports/ncaaf_state_choices.json``). The surprise start is the limit: a
change is seen only after the game it happens in.

**Result: it fails, and the reason is measured** (``reports/ncaaf_qb.md``):
the quarterback's effect is concentrated in the game a new one starts, which
the record cannot foresee, and the team state absorbs it from that game. Not
wired into the card.

**The bar, fixed before scoring.** On 2021-25 regular season, against the
state as it stands: margin CRPS better on a paired game-by-game test with t
at or below -2, margin MAE no worse, better CRPS in at least three of five
seasons. The total, recalibrated on the same state's training forecasts, is
judged by the same paired test.
"""

from __future__ import annotations

import argparse
import itertools
from dataclasses import dataclass

import numpy as np
import pandas as pd

from atlas import config
from atlas.models import evaluate, kalman, scoring
from atlas.models import lattice as lat
from atlas.models import ncaaf_prior as prior_mod
from atlas.models import ncaaf_state as state_mod
from atlas.models import ncaaf_total as total_mod
from atlas.models import reference as ref
from atlas.util import get_logger

LOG = get_logger(__name__)

QB_Q = 0.05                          # process variance per week on a quarterback, as the NFL's
GRID = {"p0": (2.0, 4.0, 9.0, 16.0), "new_mean": (0.0, -2.0, -4.0, -6.0)}


@dataclass(frozen=True)
class QBChoice:
    p0: float
    new_mean: float
    loglik: float


def quarterbacks(box: pd.DataFrame) -> pd.DataFrame:
    """Each game's quarterback of record, home and away: the passer with the most attempts."""
    b = box[box["pass_att"].fillna(0) > 0].sort_values(["pass_att", "pass_yds"])
    q = b.groupby(["event", "home"], as_index=False).tail(1)
    q = q.assign(game_id=q["event"].astype(str))
    home = q[q["home"] == 1][["game_id", "player_id"]].rename(columns={"player_id": "home_qb_id"})
    away = q[q["home"] == 0][["game_id", "player_id"]].rename(columns={"player_id": "away_qb_id"})
    return home.merge(away, on="game_id", how="outer")


def attach(frame: pd.DataFrame, qbs: pd.DataFrame) -> pd.DataFrame:
    out = frame.drop(columns=[c for c in ("home_qb_id", "away_qb_id") if c in frame.columns])
    return out.assign(_gid=out["game_id"].astype(str)).merge(
        qbs.rename(columns={"game_id": "_gid"}), on="_gid", how="left").drop(columns="_gid").set_index(out.index)


def _advance(state: kalman.State, weeks: int, spec: kalman.Spec) -> None:
    if weeks <= 0:
        return
    n2 = 2 * state.n
    diag = np.full(len(state.x), QB_Q * weeks)
    diag[:state.n] = spec.q_off * weeks
    diag[state.n:n2] = spec.q_def * weeks
    state.P[np.diag_indices_from(state.P)] += diag


def run_season_qb(games: pd.DataFrame, state: kalman.State, spec: kalman.Spec, *, p0: float,
                  new_mean: float) -> pd.DataFrame:
    """Forecast each game with each side's expected starter, then learn from who played."""
    g = games.sort_values(["kickoff", "week"])
    n = state.n
    cols = {c: (g[c].to_numpy() if c in g else np.full(len(g), None))
            for c in ("home_team_id", "away_team_id", "home_qb_id", "away_qb_id")}
    weeks = g["week"].to_numpy(dtype=int)
    neutral = pd.to_numeric(g["neutral_site"], errors="coerce").fillna(0).to_numpy(dtype=float) \
        if "neutral_site" in g else np.zeros(len(g))
    margins, totals = g["actual_margin"].to_numpy(dtype=float), g["actual_total"].to_numpy(dtype=float)
    means, sds, hps, aps = (np.full(len(g), np.nan) for _ in range(4))
    starters: dict = {}
    r = spec.sigma ** 2

    def enter(team, qb) -> int | None:
        if qb is None or pd.isna(qb):
            return None
        key = ("qb", str(qb))
        if key not in state.extra:
            # The team's first starter is who the prior assumed; a later one is a change.
            state.add(key, 0.0 if team not in starters else new_mean, p0)
        return state.extra[key]

    for i in range(len(g)):
        week = int(weeks[i])
        if state.week is None:
            state.week = week
        elif week > state.week:
            _advance(state, week - state.week, spec)
            state.week = week
        h, a = cols["home_team_id"][i], cols["away_team_id"][i]
        if h not in state.index or a not in state.index:
            continue
        ih, ia = state.index[h], state.index[a]
        boost = 0.0 if neutral[i] else spec.boost
        qh = state.extra.get(("qb", str(starters[h]))) if h in starters else None
        qa = state.extra.get(("qb", str(starters[a]))) if a in starters else None
        hp = [ih] + ([qh] if qh is not None else [])
        ap = [ia] + ([qa] if qa is not None else [])
        mh, _ = kalman.row_forecast(state, hp, [n + ia])
        ma, _ = kalman.row_forecast(state, ap, [n + ih])
        _, var = kalman.row_forecast(state, hp + [n + ih], ap + [n + ia])
        mh, ma = spec.base + boost + mh, spec.base + ma
        means[i], sds[i], hps[i], aps[i] = mh - ma, np.sqrt(var + 2.0 * r), mh, ma
        m, t = margins[i], totals[i]
        if np.isnan(m) or np.isnan(t):
            continue
        rh, ra = cols["home_qb_id"][i], cols["away_qb_id"][i]
        qh_rec = enter(h, rh) if rh is not None and not pd.isna(rh) else qh
        qa_rec = enter(a, ra) if ra is not None and not pd.isna(ra) else qa
        if rh is not None and not pd.isna(rh):
            starters[h] = rh
        if ra is not None and not pd.isna(ra):
            starters[a] = ra
        kalman.row_update(state, [ih] + ([qh_rec] if qh_rec is not None else []), [n + ia],
                          (t + m) / 2.0 - spec.base - boost, r)
        kalman.row_update(state, [ia] + ([qa_rec] if qa_rec is not None else []), [n + ih], (t - m) / 2.0 - spec.base, r)
    out = pd.DataFrame({"mean": means, "sd": sds, "home_pts": hps, "away_pts": aps}, index=g.index)
    return out.reindex(games.index)


def season_forecasts(games: pd.DataFrame, prior: prior_mod.Prior, spec: kalman.Spec,
                     qb: QBChoice | None) -> pd.DataFrame:
    """The state's forecasts for a season, with the quarterback when ``qb`` is given."""
    if qb is None:
        fc, _ = state_mod._season_forecasts(games, prior, spec)
        return fc
    teams = prior.teams
    state = kalman.initialise(teams["team_id"].to_numpy(), teams["off"].to_numpy(), teams["def"].to_numpy(), spec)
    return run_season_qb(games, state, spec, p0=qb.p0, new_mean=qb.new_mean)


def _training(frame, feats, season, like):
    seasons = [int(s) for s in sorted(frame["season"].unique()) if s < season][-state_mod.TUNING_SEASONS:]
    out = []
    for s in seasons:
        games = frame[(frame["season"] == s) & (frame["season_type"] == "regular")]
        try:
            p, zero = prior_mod.fit(frame, feats, season=s), False
        except ValueError:
            p, zero = state_mod._zero_prior(games, like, s), True
        out.append((s, games, p, zero))
    return out


def tune(frame: pd.DataFrame, feats: pd.DataFrame, season: int, choice: state_mod.Choice,
         like: prior_mod.Prior, grid: dict = GRID) -> QBChoice:
    """The quarterback prior, on the three training seasons, team hyperparameters held."""
    usable = _training(frame, feats, season, like)
    best = None
    for p0, new_mean in itertools.product(grid["p0"], grid["new_mean"]):
        ll = 0.0
        for _, games, p, zero in usable:
            spec = state_mod._spec(choice.q, state_mod.ZERO_PRIOR_P0 if zero else choice.p0, choice.sigma, p)
            fc = season_forecasts(games, p, spec, QBChoice(p0, new_mean, 0.0))
            ll += state_mod._gaussian_loglik(fc, games["actual_margin"].to_numpy(dtype=float)) * len(fc)
        if best is None or ll > best.loglik:
            best = QBChoice(p0, new_mean, ll)
    return best


def _training_totals(frame, feats, season, choice, like, qb):
    """The training seasons' state forecasts, as the total model fits its calibration on them."""
    parts = []
    for _, games, p, zero in _training(frame, feats, season, like):
        spec = state_mod._spec(choice.q, state_mod.ZERO_PRIOR_P0 if zero else choice.p0, choice.sigma, p)
        fc = season_forecasts(games, p, spec, qb)
        parts.append(_with(games, fc))
    return pd.concat(parts, ignore_index=True)


def _with(games: pd.DataFrame, fc: pd.DataFrame) -> pd.DataFrame:
    out = games.copy()
    out["m_mean"], out["m_sd"] = fc["mean"].to_numpy(), fc["sd"].to_numpy()
    out["state_total"] = (fc["home_pts"] + fc["away_pts"]).to_numpy()
    return out.dropna(subset=["m_mean"])


def evaluate_qb(frame: pd.DataFrame, *, first_test_season: int = 2021) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Walk-forward: the state as it stands and with the quarterback, margin and total."""
    feats = prior_mod.team_seasons(frame)
    choices = state_mod.load_choices(state_mod.choices_path(config.paths().root)) or {}
    margins, totals, picked, sides = [], [], {}, []
    for season, train, test in ref.walk_forward(frame, first_test_season=first_test_season):
        prior = prior_mod.fit(frame, feats, season=season)
        choice = choices.get(season) or state_mod.tune(frame, feats, season, like=prior)
        qb = tune(frame, feats, season, choice, prior)
        picked[season] = qb
        spec = state_mod._spec(choice.q, choice.p0, choice.sigma, prior)
        test = test[test["season_type"] == "regular"]
        refs = ref.all_references(train, test)
        grid_ = lat.fit(train["actual_margin"].to_numpy(), -train["closing_spread"].to_numpy(), refs["market"].sigma)
        models = {k: refs[k] for k in ("elo", "market") if k in refs}
        y = test["actual_total"].to_numpy(dtype=int)
        for name, q in (("state", None), ("state_qb", qb)):
            fc = season_forecasts(test, prior, spec, q)
            models[name] = ref.Forecast(name, fc["mean"].to_numpy(dtype=float), fc["sd"].to_numpy(dtype=float))
            if q is None:
                sides.append(_side_residuals(test, fc, season))
            tfit = total_mod.fit_total(_training_totals(frame, feats, season, choice, prior, q))
            mean = tfit.mean(_with(test, fc).reindex(test.index))
            pmf = lat.discretise(mean, tfit.sigma, total_mod.TOTAL_SUPPORT)
            totals.append(pd.DataFrame({"season": season, "game_id": test["game_id"].to_numpy(), "model": name,
                                        "crps": scoring.crps(pmf, total_mod.TOTAL_SUPPORT, y),
                                        "mae": scoring.mae(mean, y)}))
        scored = evaluate.score(test, models, grid_, season=season)
        margins.append(scored.assign(game_id=np.tile(test["game_id"].to_numpy(), len(models))))
        LOG.info("season %s: qb p0=%.0f new=%+.0f", season, qb.p0, qb.new_mean)
    margins = pd.concat(margins, ignore_index=True)
    margins.attrs["where"] = where_it_misses(pd.concat(sides, ignore_index=True))
    return margins, pd.concat(totals, ignore_index=True), picked


def _side_residuals(test: pd.DataFrame, fc: pd.DataFrame, season: int) -> pd.DataFrame:
    """Each team's points less the state's forecast of them, game by game, with its quarterback of record."""
    parts = []
    for side, pts, fpts in (("home", (test["actual_total"] + test["actual_margin"]) / 2, fc["home_pts"]),
                            ("away", (test["actual_total"] - test["actual_margin"]) / 2, fc["away_pts"])):
        parts.append(pd.DataFrame({"season": season, "team": test[f"{side}_team_id"], "kickoff": test["kickoff"],
                                   "qb": test.get(f"{side}_qb_id"), "resid": pts - fpts}))
    return pd.concat(parts, ignore_index=True)


def where_it_misses(sides: pd.DataFrame) -> pd.DataFrame:
    """The state's miss on a team's points: the game a new quarterback starts, his next start, the rest."""
    d = sides.dropna(subset=["resid", "qb"]).sort_values(["team", "season", "kickoff"]).copy()
    g = d.groupby(["team", "season"])
    d["prev"], d["prev2"], d["n"] = g["qb"].shift(1), g["qb"].shift(2), g.cumcount()
    d = d[d["n"] >= 2]
    groups = {"the game a new quarterback starts - unforeseeable from the record": d["qb"] != d["prev"],
              "his next start - foreseeable from the record": (d["qb"] == d["prev"]) & (d["prev"] != d["prev2"]),
              "a settled starter": (d["qb"] == d["prev"]) & (d["prev"] == d["prev2"])}
    return pd.DataFrame([{"team-games": label, "count": int(m.sum()),
                          "mean miss (points)": f"{d.loc[m, 'resid'].mean():+.2f}",
                          "standard error": f"{d.loc[m, 'resid'].std(ddof=1) / np.sqrt(m.sum()):.2f}"}
                         for label, m in groups.items()])


def paired(scored: pd.DataFrame, a: str = "state_qb", b: str = "state") -> dict:
    w = scored[scored["model"].isin([a, b])].pivot_table(index=["season", "game_id"], columns="model", values="crps")
    d = (w[a] - w[b]).dropna()
    se = float(d.std(ddof=1) / np.sqrt(len(d)))
    by = scored.groupby(["season", "model"])["crps"].mean().unstack()
    mae = scored.groupby("model")["mae"].mean()
    return {"change": float(d.mean()), "se": se, "t": float(d.mean() / se), "seasons": int((by[a] < by[b]).sum()),
            "of": len(by), "mae": float(mae[a] - mae[b])}


def render(margins: pd.DataFrame, totals: pd.DataFrame, picked: dict) -> str:
    md, fmt, summarise = evaluate.markdown, evaluate.formatted, evaluate.summarise
    cols = ["crps", "brier", "log_margin", "mae", "ece"]
    order = ("elo", "state", "state_qb", "market")
    m, t = paired(margins), paired(totals)
    m_pass = m["t"] <= -2 and m["mae"] <= 0 and m["seasons"] >= 3
    t_pass = t["t"] <= -2
    tot = totals.groupby("model")[["crps", "mae"]].mean().reset_index()
    tot_by = totals.groupby(["season", "model"])["crps"].mean().unstack().reset_index()
    for c in ("crps", "mae"):
        tot[c] = tot[c].map("{:.3f}".format)
    for c in ("state", "state_qb"):
        tot_by[c] = tot_by[c].map("{:.3f}".format)
    parts = [
        "# College: the quarterback state", "",
        "`atlas/models/ncaaf_qb.py`. The college state as it stands (`state`) and with a quarterback state inside "
        "the season (`state_qb`): forecast with the team's previous quarterback of record, learned from who "
        "played, a new starter entering at a prior tuned on the training seasons. Regular season 2021-25, "
        "walk-forward. The bar, fixed before scoring: margin CRPS better on a paired test with t at or below -2, "
        "MAE no worse, better in three seasons of five; the total judged by the same paired test.", "",
        "## Verdict", "",
        f"- **Margin: {'passes' if m_pass else 'fails'}** - paired CRPS change {m['change']:+.4f} (standard error "
        f"{m['se']:.4f}, t {m['t']:+.2f}); MAE change {m['mae']:+.3f}; better in {m['seasons']} of {m['of']} seasons.",
        f"- **Total: {'passes' if t_pass else 'fails'}** - paired CRPS change {t['change']:+.4f} (standard error "
        f"{t['se']:.4f}, t {t['t']:+.2f}); MAE change {t['mae']:+.3f}; better in {t['seasons']} of {t['of']} seasons.",
        "",
        "## Why: where the state misses", "",
        "The state's miss on a team's points (actual less forecast), regular season 2021-25. The quarterback's "
        "effect is in the game a new one starts - which the record shows only afterwards - and by his next start "
        "the team's own state has already absorbed it from that game's points. A quarterback state learned from "
        "the record has nothing left to add; what would help is knowing the starter before kickoff, which no "
        "source Atlas has provides for college.", "",
        md(margins.attrs["where"]), "",
        "## Quarterback prior chosen per season", "",
        md(pd.DataFrame([{"season": s, "prior variance": q.p0, "new starter (points)": q.new_mean}
                         for s, q in sorted(picked.items())])), "",
        "## Margin, regular season 2021-25", "",
        md(fmt(summarise(margins, order=order), cols)), "",
        "## Margin by season", "", md(fmt(summarise(margins, ["season"], order=order), cols)), "",
        "## Total, regular season 2021-25", "", md(tot), "",
        "## Total CRPS by season", "", md(tot_by), "",
    ]
    return "\n".join(parts).rstrip() + "\n"


def main() -> None:
    argparse.ArgumentParser(description="The college quarterback state, walk-forward").parse_args()
    from atlas.research.dataset import load_research_frame, research_sample
    from atlas.sources import espn_cfb

    frame = attach(research_sample(load_research_frame()), quarterbacks(espn_cfb.load()))
    margins, totals, picked = evaluate_qb(frame)
    out = config.paths().root / "reports" / "ncaaf_qb.md"
    out.write_text(render(margins, totals, picked))
    LOG.info("wrote %s", out)


if __name__ == "__main__":
    main()
