"""The DFS player projection model: opportunity inside Atlas's own game.

    python -m atlas.dfs.model                  # walk-forward; writes reports/dfs_projections.md
    python -m atlas.dfs.model --atlas-only     # also the model without the market, in the report

Step 3 of `docs/MODEL_PLAN_DFS.md`. A player's projected DraftKings points
from what was knowable before kickoff:

* the step 2 baseline - his own recent scoring, shrunk to his position -
  which the model corrects rather than replaces;
* the game, as Atlas's game model projected it - his team's points, the
  opponent's, the quarterback states, the wind (`atlas/dfs/environment.py`) -
  and as the betting market sees it: each team's points implied by the line;
* his role, from his earlier games only - snap, target, carry, red-zone and
  air-yards shares, volume - and each share times his team's projected
  points, the plan's "opportunity times efficiency" in a form a model learns;
* the week's news - his injury status, his depth-chart rank, the shares of
  teammates listed out, whether the usual quarterback is (`atlas/dfs/context.py`);
* for a quarterback, his passing and rushing trends; for a defense, its own
  sacks, takeaways and points allowed, and what the offense it faces has
  given up to earlier defenses.

One gradient-boosted model per position (scikit-learn's histogram
boosting), fitted to the baseline's residual with fixed, conservative
settings. A defense's projection is the average of that model's and one
built from its scoring parts (`atlas/dfs/defense.py`, step 4). Every
projection carries a 10th-90th percentile range (`atlas/dfs/ranges.py`,
step 4), fitted on the model's own out-of-sample misses. No outside projection is an input (the owner's decision). The
market's team totals are: Atlas-only, the model fell short of salary's
ranking at quarterback and defense, and the gap was the game environment,
so the owner added them (24 September 2026). The report keeps the
Atlas-only result beside it.

Walk-forward: each season fitted on the seasons before it (2013 on, when
snap counts begin). The spread of each projection is fitted on a held-out
season's residuals - a model that has seen its own training rows would
flatter itself - as |residual| = a + b x projection, by position.

The gate (plan §7, step 3): among each team's regulars, beat the baseline's
CRPS at every position, and rank each position's regulars at least as well
as salary does.
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

from atlas import config
from atlas.dfs import benchmarks as bm
from atlas.dfs import context, defense, environment, players, ranges
from atlas.sources import nflverse
from atlas.staging.nfl.games import FRANCHISE
from atlas.util import get_logger

LOG = get_logger(__name__)

FIRST_TRAIN = 2013                 # snap counts begin
FIRST_TEST = 2015
LONG_HALFLIFE = 16.0

OFFENSE_FEATURES = [
    "team_pts", "opp_pts", "proj_total", "proj_margin", "team_pts_trend", "env_lift", "home",
    "games_before", "dk_points_trend", "snap_pct_trend", "target_share_trend", "carry_share_trend",
    "rz_target_share_trend", "rz_carry_share_trend", "air_yards_share_trend", "targets_trend", "carries_trend",
    "pass_attempts_trend",
    "x_targets", "x_carries", "x_rz_targets", "x_rz_carries", "x_points",
    "dk_points_long", "status", "depth_rank", "vacated_targets", "vacated_carries", "vacated_pos_targets",
    "vacated_pos_carries", "qb1_out", "is_qb1", "qb_state", "wind", "baseline",
]
QB_FEATURES = ["passing_yards_trend", "passing_tds_trend", "rushing_yards_trend", "rushing_tds_trend",
               "passing_interceptions_trend", "passing_epa_trend", "rushing_yards_long", "passing_yards_long"]
DST_FEATURES = ["team_pts", "opp_pts", "proj_total", "proj_margin", "home", "games_before", "dk_points_trend",
                "dk_points_long", "sacks_trend", "takeaways_trend", "points_allowed_trend",
                "opp_sacks_taken_trend", "opp_giveaways_trend", "opp_dst_points_trend", "opp_qb_state", "wind", "baseline"]
#: The market's view of the game, beside Atlas's own (the owner's decision,
#: 24 September 2026, after the step 3 gate showed it was what the model lacked).
MARKET_FEATURES = ["mkt_pts", "mkt_opp"]
#: Stats of the player's own record, trended like the rest (players.py's halflife).
QB_TRENDS = ("passing_yards", "passing_tds", "rushing_yards", "rushing_tds", "passing_interceptions", "passing_epa")

#: Fixed and conservative: shallow trees, large leaves, few slow steps. The
#: first version (deeper trees, more steps) overfit the history it was given
#: and lost to the baseline it was built on; these were settled on 2015-2021
#: and not revisited on the seasons after.
PARAMS = dict(max_iter=100, learning_rate=0.03, max_leaf_nodes=7, min_samples_leaf=200, l2_regularization=5.0,
              random_state=0)

#: Training rows by position. A quarterback's model learns from starters -
#: the depth chart's first or the team's usual passer - since a backup's
#: kneel-downs and mop-up drives are another population.
STARTERS_ONLY = ("QB",)


def market_totals(raw=None) -> pd.DataFrame:
    """Each team's points as the line implies them: half the total, plus or
    minus half the spread. nflverse carries the closing line for played games
    and the current line for upcoming ones."""
    s = pd.read_parquet(nflverse.schedules_path(raw or config.paths().raw))
    s = s[s["game_type"] == "REG"]
    parts = [pd.DataFrame({"season": s["season"], "week": s["week"], "team": s[side].replace(FRANCHISE),
                           "mkt_pts": s["total_line"] / 2 + sign * s["spread_line"] / 2,
                           "mkt_opp": s["total_line"] / 2 - sign * s["spread_line"] / 2})
             for side, sign in (("home_team", 1), ("away_team", -1))]
    return pd.concat(parts, ignore_index=True)


def features(frame: pd.DataFrame, env: pd.DataFrame) -> pd.DataFrame:
    """The benchmark frame with each row's game environment and the interactions."""
    staging = config.paths().staging / "nfl"
    trends = pd.read_parquet(staging / "dfs_player_games.parquet")
    trend_cols = [c for c in trends.columns if c.endswith("_trend")]
    trends = trends[trends["season_type"] == "REG"][["season", "week", "player_id", "game_id", *trend_cols]]
    f = frame.merge(trends.drop(columns=["dk_points_trend"]), on=["season", "week", "player_id"], how="left")
    f = f.merge(_qb_trends(pd.read_parquet(staging / "dfs_player_games.parquet")), on=["season", "week", "player_id"],
                how="left")
    f = f.merge(_dst_trends(pd.read_parquet(staging / "dfs_dst_games.parquet")), on=["season", "week", "player_id"],
                how="left")
    news = pd.read_parquet(context.path()).drop(columns=["team"])
    f = f.merge(news, on=["season", "week", "player_id"], how="left")
    # The long view of his scoring, which a four-game trend forgets.
    f = f.sort_values(["player_id", "season", "week"])
    f["dk_points_long"] = f.groupby("player_id", sort=False)["target"].transform(
        lambda s: s.shift(1).ewm(halflife=LONG_HALFLIFE, ignore_na=True).mean())
    f = f.sort_index()
    # A defense's game id comes from its team and week.
    envr = env[["season", "week", "team", "game_id", "team_pts", "opp_pts", "proj_total", "proj_margin",
                "team_pts_trend", "home", "qb_state", "opp_qb_state", "wind"]]
    f = f.merge(envr.drop(columns=["game_id"]), on=["season", "week", "team"], how="left")
    f = f.merge(market_totals(), on=["season", "week", "team"], how="left")
    f["env_lift"] = f["team_pts"] - f["team_pts_trend"]
    f = _with_dst_parts(f, staging)
    pts = f["team_pts"]
    f["x_targets"] = f.get("target_share_trend") * pts
    f["x_carries"] = f.get("carry_share_trend") * pts
    f["x_rz_targets"] = f.get("rz_target_share_trend") * pts
    f["x_rz_carries"] = f.get("rz_carry_share_trend") * pts
    f["x_points"] = f["dk_points_trend"] * pts / f["team_pts_trend"].replace(0, np.nan)
    return f


def _with_dst_parts(f: pd.DataFrame, staging) -> pd.DataFrame:
    """Each defense's expected points from its parts (`atlas/dfs/defense.py`), walk-forward."""
    comp = defense.components(pd.read_parquet(staging / "dfs_dst_games.parquet"))
    is_dst = f["position"] == "DST"
    d = f[is_dst].merge(comp, on=["season", "week", "player_id"], how="left").set_index(f.index[is_dst])
    parts = defense.walk_forward(d)
    for c in ("dst_parts", "exp_points_allowed"):
        f[c] = parts[c].reindex(f.index) if c in parts else np.nan
    return f


def _cols(position: str, market: bool = True) -> list[str]:
    cols = DST_FEATURES if position == "DST" else OFFENSE_FEATURES + (QB_FEATURES if position == "QB" else [])
    return cols + (MARKET_FEATURES if market else [])


def _ewm(frame: pd.DataFrame, by: str, col: str, halflife: float) -> pd.Series:
    """The shifted exponentially weighted mean: this row's history, not the row."""
    return frame.groupby(by, sort=False)[col].transform(lambda s: s.shift(1).ewm(halflife=halflife, ignore_na=True).mean())


def _qb_trends(player_games: pd.DataFrame) -> pd.DataFrame:
    q = player_games[(player_games["season_type"] == "REG") & (player_games["position"] == "QB")]
    q = q.sort_values(["player_id", "season", "week"]).copy()
    for col in QB_TRENDS:
        q[f"{col}_trend"] = _ewm(q, "player_id", col, players.HALFLIFE)
    for col in ("rushing_yards", "passing_yards"):
        q[f"{col}_long"] = _ewm(q, "player_id", col, LONG_HALFLIFE)
    return q[["season", "week", "player_id", *[f"{c}_trend" for c in QB_TRENDS], "rushing_yards_long",
              "passing_yards_long"]]


def _dst_trends(dst: pd.DataFrame) -> pd.DataFrame:
    """A defense's own form, and the form of the offense it faces: what that
    offense has given up to the defenses before this one."""
    d = dst[dst["season_type"] == "REG"].sort_values(["season", "week"]).copy()
    d["takeaways"] = d["interceptions"] + d["fumble_recoveries"]
    d["points"] = d["dk_points_official"].fillna(d["dk_points"])
    d = d.sort_values(["team", "season", "week"])
    for col in ("sacks", "takeaways", "points_allowed"):
        d[f"{col}_trend"] = _ewm(d, "team", col, players.HALFLIFE)
    d = d.sort_values(["opponent", "season", "week"])
    offense = pd.DataFrame({
        "season": d["season"], "week": d["week"], "team": d["opponent"],
        "opp_sacks_taken_trend": _ewm(d, "opponent", "sacks", players.HALFLIFE),
        "opp_giveaways_trend": _ewm(d, "opponent", "takeaways", players.HALFLIFE),
        "opp_dst_points_trend": _ewm(d, "opponent", "points", players.HALFLIFE)})
    own = d[["season", "week", "team", "opponent", "sacks_trend", "takeaways_trend", "points_allowed_trend"]]
    out = own.merge(offense.rename(columns={"team": "opponent"}), on=["season", "week", "opponent"], how="left")
    return out.assign(player_id="DST-" + out["team"]).drop(columns=["team", "opponent"])


def _training_rows(train: pd.DataFrame, position: str) -> pd.DataFrame:
    g = train[train["position"] == position]
    if position in STARTERS_ONLY:
        g = g[(g["depth_rank"] == 1) | (g["is_qb1"] == 1)]
    return g


def _fit(train: pd.DataFrame, position: str, market: bool = True) -> HistGradientBoostingRegressor:
    """The correction to the baseline: what the game, the role and the week's
    news add to a player's own recent scoring."""
    g = _training_rows(train, position)
    model = HistGradientBoostingRegressor(**PARAMS)
    model.fit(g[_cols(position, market)].to_numpy(dtype=float), (g["target"] - g["baseline"]).to_numpy(dtype=float))
    return model


def _predict(model: HistGradientBoostingRegressor, rows: pd.DataFrame, position: str,
             market: bool = True) -> np.ndarray:
    pred = rows["baseline"].to_numpy(dtype=float) + model.predict(rows[_cols(position, market)].to_numpy(dtype=float))
    if position == "DST" and "dst_parts" in rows:
        # A defense: the average of this model and the one built from its parts.
        parts = rows["dst_parts"].to_numpy(dtype=float)
        pred = np.where(np.isnan(parts), pred, (pred + parts) / 2)
    return pred


def _with_baseline(rows: pd.DataFrame, history: pd.DataFrame) -> pd.DataFrame:
    """The step 2 baseline, its shrinkage fitted on ``history`` only, as a feature and the anchor."""
    f = bm.fit(history)
    return rows.assign(baseline=bm._baseline(rows, f.shrink, f.mean))


def predict_season(frame: pd.DataFrame, season: int, market: bool = True) -> pd.DataFrame:
    """Fit on the seasons before ``season``, predict it; the spread from a held-out season."""
    history = frame[frame["season"] < season]
    train = _with_baseline(history[history["season"] >= FIRST_TRAIN], history)
    inner_history = frame[frame["season"] < season - 1]
    inner = _with_baseline(inner_history[inner_history["season"] >= FIRST_TRAIN], inner_history)
    holdout = _with_baseline(frame[frame["season"] == season - 1], inner_history)
    test = _with_baseline(frame[frame["season"] == season], history)
    test["model"] = np.nan
    test["model_sd"] = np.nan
    for position in bm.POSITIONS:
        if len(_training_rows(train, position)) < 200:
            continue
        model = _fit(train, position, market)
        m = test["position"] == position
        test.loc[m, "model"] = _predict(model, test[m], position, market)
        # The spread: a model fitted without the held-out season, scored on it.
        h = holdout[holdout["position"] == position]
        if len(_training_rows(inner, position)) >= 200 and len(h):
            a, b = bm._spread(_predict(_fit(inner, position, market), h, position, market),
                              h["target"].to_numpy(dtype=float))
        else:
            g = train[train["position"] == position]
            a, b = bm._spread(_predict(model, g, position, market), g["target"].to_numpy(dtype=float))
        test.loc[m, "model_sd"] = np.maximum(a + b * test.loc[m, "model"].to_numpy(dtype=float), 1.0)
    return test


def walk_forward(frame: pd.DataFrame, *, first_test: int = FIRST_TEST, market: bool = True) -> pd.DataFrame:
    seasons = sorted(int(s) for s in frame["season"].unique())
    return pd.concat([predict_season(frame, s, market) for s in seasons if s >= first_test], ignore_index=True)


def run(*, market: bool = True) -> pd.DataFrame:
    """Benchmarks and model on the same rows, walk-forward.

    ``market=False`` refits without the closing line's team totals: the
    Atlas-only model, kept as the record of what the market adds.
    """
    frame = bm.load()
    scored = bm.walk_forward(frame)
    env = pd.read_parquet(environment.path())
    # One season earlier than the scored ones: its misses are what the
    # first scored season's ranges are fitted on.
    model = walk_forward(features(frame, env), first_test=FIRST_TEST - 1, market=market)
    model = model.merge(ranges.walk_forward(model, first=FIRST_TEST), on=["season", "week", "player_id"], how="left")
    keep = ["season", "week", "player_id", "model", "model_sd", "model_lo", "model_hi", "team_pts", "opp_pts",
            "dst_parts", *MARKET_FEATURES]
    return scored.merge(model[keep], on=["season", "week", "player_id"], how="left")


def _weekly_ranks(frame: pd.DataFrame, pred: str) -> pd.Series:
    out = {}
    for key, g in frame.groupby(["season", "week", "position"]):
        if len(g) >= 5 and g[pred].nunique() > 1:
            out[key] = g[pred].rank().corr(g["target"].rank())
    return pd.Series(out, dtype=float)


def gate(regulars: pd.DataFrame) -> pd.DataFrame:
    """Per position: CRPS against the baseline's, rank correlation against
    salary's, and the rank gap's standard error over weeks (paired, week by week)."""
    t = bm.summarise(regulars, ("model", "baseline", "salary"), ["position"]).pivot(
        index="position", columns="model", values=["crps", "rank corr", "mae"])
    out = pd.DataFrame({
        "crps model": t[("crps", "model")], "crps baseline": t[("crps", "baseline")],
        "rank model": t[("rank corr", "model")], "rank salary": t[("rank corr", "salary")],
    })
    diff = (_weekly_ranks(regulars, "model") - _weekly_ranks(regulars, "salary")).dropna()
    by_pos = diff.groupby(level=2)
    out["rank gap se"] = by_pos.std() / np.sqrt(by_pos.size())
    out["beats baseline"] = out["crps model"] < out["crps baseline"]
    out["ranks as well as salary"] = out["rank model"] >= out["rank salary"]
    return out.reset_index()


def _ranges_section(regs: pd.DataFrame, everyone: pd.DataFrame, recent_regs: pd.DataFrame, markdown) -> list[str]:
    """Step 4's gate: how often the 80% range holds the outcome."""
    lo, hi = ranges.GATE

    def fmt(t: pd.DataFrame) -> pd.DataFrame:
        t = t.copy()
        for c in ("coverage", "below", "above"):
            t[c] = t[c].map("{:.1%}".format)
        t["width"] = t["width"].map("{:.1f}".format)
        return t

    by_pos = ranges.coverage(regs, ["position"])
    held = bool(by_pos["coverage"].between(lo, hi).all())
    overall = float(ranges.coverage(regs)["coverage"].iloc[0])
    parts = [
        f"## Ranges, 2015-2021, each team's regulars: {'the gate passes' if held else 'the gate does not pass'}", "",
        "Each projection carries a range from its 10th to its 90th percentile (`atlas/dfs/ranges.py`): per "
        "position, a linear quantile regression of the model's out-of-sample misses on the projection, fitted on "
        "the seasons before. DraftKings points are lopsided - a floor near zero, a long tail of touchdown weeks - so "
        "the two ends are fitted separately rather than drawn as a normal curve. The gate (plan §7, step 4): the "
        f"80% range holds {lo:.0%}-{hi:.0%} of outcomes at every position. Overall: {overall:.1%}. `below` and "
        "`above` should each be near 10%; `width` is the range in points.", "", markdown(fmt(by_pos)), "",
        "### Everyone who played, 2015-2021", "", markdown(fmt(ranges.coverage(everyone, ["position"]))), "",
    ]
    if not recent_regs.empty:
        parts += ["### Regulars, 2022-2025", "", markdown(fmt(ranges.coverage(recent_regs, ["position"]))), "",
                  "### Regulars by season", "",
                  markdown(fmt(ranges.coverage(pd.concat([regs, recent_regs]), ["season"]))), ""]
    return parts


def _defense_section(regs: pd.DataFrame, recent_regs: pd.DataFrame, markdown) -> list[str]:
    """How the defense built from its parts compares, alone and in the blend."""
    rows = []
    for label, r in (("2015-2021", regs), ("2022-2025", recent_regs)):
        d = r[(r["position"] == "DST")].dropna(subset=["dst_parts", "model"])
        if d.empty:
            continue
        for name, col in (("blend (published)", "model"), ("parts alone", "dst_parts"), ("baseline", "baseline")):
            rows.append({"seasons": label, "projection": name,
                         "mae": f"{np.mean(np.abs(d['target'] - d[col])):.3f}",
                         "rank corr": f"{bm.rank_correlation(d, col):.3f}"})
    if not rows:
        return []
    return [
        "## Defenses", "",
        "A defense's projection is the average of the player model's and one built from its parts "
        "(`atlas/dfs/defense.py`): expected sacks, takeaways and return touchdowns, each a Poisson rate on the "
        "defense's form, the opposing offense's and both teams' projected points; the league's rate for safeties, "
        "blocks and returned conversions; and DraftKings' points-allowed bonus averaged over the spread of the "
        "opponent's score. Chosen on 2015-2021 from three candidates (the player model alone, the parts alone, the "
        "average); 2022-2025 is the unchosen test.", "", markdown(pd.DataFrame(rows)), "",
    ]


def render(scored: pd.DataFrame, atlas_only: pd.DataFrame | None = None) -> str:
    from atlas.models.evaluate import markdown

    def fmt(t: pd.DataFrame) -> pd.DataFrame:
        t = t.copy()
        for c in ("mae", "crps", "rank corr"):
            if c in t:
                t[c] = t[c].map("{:.3f}".format)
        return t

    def fmt_gate(g: pd.DataFrame) -> pd.DataFrame:
        g = g.copy()
        for c in ("crps model", "crps baseline", "rank model", "rank salary", "rank gap se"):
            g[c] = g[c].map("{:.3f}".format)
        for c in ("beats baseline", "ranks as well as salary"):
            g[c] = g[c].map({True: "yes", False: "no"})
        return g

    salaried = scored[scored["season"].isin(bm.SALARY_SEASONS) & scored["dk_salary"].notna()]
    regs = bm.regulars(salaried)
    last_full = int(scored["season"].max())
    recent = scored[(scored["season"] > max(bm.SALARY_SEASONS)) & (scored["season"] < last_full)]
    g = gate(regs)
    passed = bool(g["beats baseline"].all() and g["ranks as well as salary"].all())
    missed = g.loc[~g["ranks as well as salary"], "position"].tolist()
    three = ("model", "baseline", "salary")
    parts = [
        "# DFS player projections", "",
        "Atlas's player model (`atlas/dfs/model.py`, step 3 of `docs/MODEL_PLAN_DFS.md`): the step 2 baseline, "
        "corrected by one gradient-boosted model per position that reads the game as Atlas's own game model projected "
        "it and as the line implies it, each player's role from his earlier games, and the week's injury report and "
        "depth chart. No outside projection is an input. Walk-forward: every season predicted from the seasons "
        "before it. Scored on players who recorded a stat, beside the step 2 benchmarks on the same rows.", "",
        f"## The gate, 2015-2021, each team's regulars: {'passes' if passed else 'does not pass'}", "",
        "Beat the baseline's CRPS at every position, and rank each position's regulars at least as well as "
        "DraftKings' salary does. `rank gap se` is the standard error of the model-minus-salary rank correlation, "
        "paired week by week.", "", markdown(fmt_gate(g)), "",
    ]
    if missed:
        parts += [f"Short of salary's ranking at: {', '.join(missed)}.", ""]
    if atlas_only is not None:
        ao = atlas_only[atlas_only["season"].isin(bm.SALARY_SEASONS) & atlas_only["dk_salary"].notna()]
        aregs = bm.regulars(ao)
        env = pd.DataFrame([{"position": pos, "Atlas team points": bm.rank_correlation(r, "team_pts"),
                             "line's team points": bm.rank_correlation(r, "mkt_pts")}
                            for pos, r in aregs.groupby("position")])
        for c in ("Atlas team points", "line's team points"):
            env[c] = env[c].map("{:.3f}".format)
        parts += [
            "## Without the market", "",
            "The same model with the line's team totals left out - Atlas's game model the only view of the game. "
            "It beat the baseline everywhere but fell short of salary's ranking at quarterback and defense:", "",
            markdown(fmt_gate(gate(aregs))), "",
            "Each team's projected points alone, as a ranking of its regulars against the week's others, show why: "
            "the line knows more about how many points a team will score than Atlas's game model does, and salary "
            "carries that knowledge.", "", markdown(env), "",
        ]
    parts += _ranges_section(regs, salaried, bm.regulars(recent), markdown)
    parts += _defense_section(regs, bm.regulars(recent), markdown)
    parts += [
        "## Salary era, 2015-2021, regulars", "", markdown(fmt(bm.summarise(regs, three))), "",
        "### By position", "", markdown(fmt(bm.summarise(regs, three, ["position"]))), "",
        "### By season", "", markdown(fmt(bm.summarise(regs, three, ["season"]))), "",
    ]
    if not recent.empty:
        parts += [f"## {int(recent['season'].min())}-{int(recent['season'].max())}, regulars (no salaries; "
                  "every game-model setting tuned on earlier seasons only)", "",
                  markdown(fmt(bm.summarise(bm.regulars(recent), ("model", "baseline"), ["position"]))), ""]
    parts += ["## Caveats", "",
              "- **The game model's history.** The environment is Atlas's NFL game model run from 2011. From 2020 "
              "each season uses settings tuned on earlier seasons only; before 2020 it uses 2020's, tuned on "
              "2017-2019 - a look-ahead of four smoothing constants, not of results, for those three seasons. The "
              "2022-2025 table carries no such caveat.",
              "- **The line** is the closing line for past games; live, it is the line as it stands at the "
              "refresh, which moves toward the close through the week.",
              "- **The wind** is the recorded game-time wind; live, it is the forecast, which is close by kickoff "
              "and less so earlier in the week.",
              "- **The model's settings** (the boosting's size, the starters-only quarterback rows) were chosen on "
              "2015-2021, the seasons this gate scores, from four candidates. The 2022-2025 table is the "
              "unchosen test.", ""]
    return "\n".join(parts).rstrip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="DFS player projections, walk-forward")
    parser.add_argument("--atlas-only", action="store_true",
                        help="also refit without the market's team totals, for the report")
    args = parser.parse_args()
    scored = run()
    atlas_only = run(market=False) if args.atlas_only else None
    out = config.paths().root / "reports" / "dfs_projections.md"
    out.write_text(render(scored, atlas_only))
    salaried = scored[scored["season"].isin(bm.SALARY_SEASONS) & scored["dk_salary"].notna()]
    LOG.info("wrote %s\n%s", out, gate(bm.regulars(salaried)).round(3).to_string(index=False))


if __name__ == "__main__":
    main()
