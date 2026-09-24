"""The college DFS player model: the NFL model's form, college's inputs.

    python -m atlas.dfs.cfb_model           # walk-forward; writes reports/dfs_cfb_projections.md

Step 3 of `docs/MODEL_PLAN_DFS_CFB.md`. A college player's projected
DraftKings points from what was knowable before kickoff:

* the step 2 baseline - his recent scoring shrunk to his position - which
  the model corrects rather than replaces;
* **the game as the betting market sees it**: each team's points implied by
  the line (half the total, less half the team's own spread), from Atlas's
  odds history, every season from 2014. Atlas's own college game model is
  walk-forward only from 2021, so the line is the environment here;
* **his role** from earlier games only: shares of his team's carries,
  catches, receiving yards and passes, his volume and recent scoring, and
  each share times his team's implied points;
* home or away.

College has no targets, snap counts, injury report or depth chart, so there
is nothing here for the week's news; that is the model's known gap.

One gradient-boosted model per position, fitted to the baseline's residual
with the NFL model's settings; the spread of each projection from a
held-out season; ranges from the model's own out-of-sample misses
(`atlas/dfs/ranges.py`). The gate: beat the baseline's CRPS at QB, RB, WR
and K among each team's regulars, and 80% ranges that cover 76-84%.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

from atlas import config
from atlas.dfs import benchmarks as bm
from atlas.dfs import cfb_players as cp
from atlas.dfs import model as nfl_model
from atlas.dfs import ranges
from atlas.util import get_logger

LOG = get_logger(__name__)

FIRST_TRAIN = 2014
FIRST_TEST = cp.FIRST_TEST
PARAMS = nfl_model.PARAMS
LONG_HALFLIFE = 16.0
FEATURES = ["team_pts", "opp_pts", "proj_total", "proj_margin", "home", "games_before", "dk_points_trend",
            "dk_points_long", "rush_share_trend", "rec_share_trend", "rec_yds_share_trend", "pass_share_trend",
            "rush_car_trend", "rec_trend", "pass_att_trend", "rec_yds_trend", "rush_yds_trend",
            "x_rush", "x_rec", "x_rec_yds", "x_pass", "baseline"]


def odds_path(raw: Path | None = None) -> Path:
    return (raw or config.paths().raw) / "odds" / "cfb_line_odds.parquet"


def abbr_map(odds_teams: pd.DataFrame, box_teams: pd.DataFrame) -> dict[str, str]:
    """The odds file's team codes to ESPN's, learned from games where one side's
    codes agree: then the other side's pair names the same team."""
    votes: dict[tuple[str, str], int] = {}
    o = odds_teams.groupby("game_id")["abbr"].apply(lambda s: sorted(set(s))).to_dict()
    b = box_teams.groupby("game_id")["team"].apply(lambda s: sorted(set(s))).to_dict()
    for gid, codes in o.items():
        teams = b.get(gid)
        if not teams or len(codes) != 2 or len(teams) != 2:
            continue
        common = set(codes) & set(teams)
        if len(common) == 2:
            for c in codes:
                votes[(c, c)] = votes.get((c, c), 0) + 1
        elif len(common) == 1:
            (same,) = common
            other_o = next(c for c in codes if c != same)
            other_b = next(t for t in teams if t != same)
            votes[(same, same)] = votes.get((same, same), 0) + 1
            votes[(other_o, other_b)] = votes.get((other_o, other_b), 0) + 1
    best: dict[str, tuple[str, int]] = {}
    for (code, team), n in votes.items():
        if n > best.get(code, ("", 0))[1]:
            best[code] = (team, n)
    return {code: team for code, (team, _) in best.items()}


def environment(box: pd.DataFrame, raw: Path | None = None) -> pd.DataFrame:
    """Each (event, team): its points implied by the line, and its opponent's."""
    o = pd.read_parquet(odds_path(raw), columns=["game_id", "market_type", "abbr", "lines"])
    o = o.dropna(subset=["game_id", "lines"])
    o["game_id"] = o["game_id"].astype("int64")
    spread = o[o["market_type"] == "spread"].groupby(["game_id", "abbr"])["lines"].median().rename("spread")
    spread = spread.reset_index()
    total = o[(o["market_type"] == "total") & o["abbr"].isin(["over", "under"])].groupby("game_id")["lines"]
    total = total.median().rename("total").reset_index()
    teams = box[["event", "team"]].drop_duplicates().assign(game_id=lambda d: pd.to_numeric(d["event"]).astype("int64"))
    mapping = abbr_map(spread, teams)
    spread["team"] = spread["abbr"].map(mapping)
    spread = spread.dropna(subset=["team"]).drop_duplicates(["game_id", "team"])
    env = teams.merge(spread[["game_id", "team", "spread"]], on=["game_id", "team"], how="left")
    env = env.merge(total, on="game_id", how="left")
    env["team_pts"] = env["total"] / 2 - env["spread"] / 2
    env["opp_pts"] = env["total"] - env["team_pts"]
    env["proj_total"], env["proj_margin"] = env["total"], env["team_pts"] - env["opp_pts"]
    return env[["event", "team", "team_pts", "opp_pts", "proj_total", "proj_margin"]]


def features(table: pd.DataFrame, env: pd.DataFrame) -> pd.DataFrame:
    """Scored rows with the game and the interactions."""
    f = cp.frame(table).merge(env, on=["event", "team"], how="left")
    f = f.sort_values(["player_id", "order"])
    f["dk_points_long"] = f.groupby("player_id", sort=False)["target"].transform(
        lambda s: s.shift(1).ewm(halflife=LONG_HALFLIFE, ignore_na=True).mean())
    f = f.sort_index()
    pts = f["team_pts"]
    for share, name in (("rush_share_trend", "x_rush"), ("rec_share_trend", "x_rec"),
                        ("rec_yds_share_trend", "x_rec_yds"), ("pass_share_trend", "x_pass")):
        f[name] = f[share] * pts
    return f.assign(week=f["order"])


def _with_baseline(rows: pd.DataFrame, history: pd.DataFrame) -> pd.DataFrame:
    fit = bm.fit(history)
    return rows.assign(baseline=bm._baseline(rows, fit.shrink, fit.mean))


def _fit(train: pd.DataFrame, position: str) -> HistGradientBoostingRegressor:
    g = train[train["position"] == position]
    return HistGradientBoostingRegressor(**PARAMS).fit(g[FEATURES].to_numpy(dtype=float),
                                                       (g["target"] - g["baseline"]).to_numpy(dtype=float))


def _predict(model, rows: pd.DataFrame) -> np.ndarray:
    return rows["baseline"].to_numpy(dtype=float) + model.predict(rows[FEATURES].to_numpy(dtype=float))


def predict_season(f: pd.DataFrame, season: int) -> pd.DataFrame:
    """Fit on the seasons before, predict ``season``; the spread from a held-out season."""
    history = f[f["season"] < season]
    train = _with_baseline(history[history["season"] >= FIRST_TRAIN], history)
    inner_history = f[f["season"] < season - 1]
    inner = _with_baseline(inner_history[inner_history["season"] >= FIRST_TRAIN], inner_history)
    holdout = _with_baseline(f[f["season"] == season - 1], inner_history)
    test = _with_baseline(f[f["season"] == season], history)
    test["model"], test["model_sd"] = np.nan, np.nan
    for position in cp.POSITIONS:
        if (train["position"] == position).sum() < 200:
            continue
        model = _fit(train, position)
        m = test["position"] == position
        test.loc[m, "model"] = _predict(model, test[m])
        h = holdout[holdout["position"] == position]
        if (inner["position"] == position).sum() >= 200 and len(h):
            a, b = bm._spread(_predict(_fit(inner, position), h), h["target"].to_numpy(dtype=float))
        else:
            g = train[train["position"] == position]
            a, b = bm._spread(_predict(model, g), g["target"].to_numpy(dtype=float))
        test.loc[m, "model_sd"] = np.maximum(a + b * test.loc[m, "model"].to_numpy(dtype=float), 1.0)
    return test


def walk_forward(f: pd.DataFrame, *, first_test: int = FIRST_TEST) -> pd.DataFrame:
    seasons = sorted(int(s) for s in f["season"].unique())
    return pd.concat([predict_season(f, s) for s in seasons if s >= first_test], ignore_index=True)


def run() -> pd.DataFrame:
    """Baseline and model on the same rows, walk-forward, with ranges."""
    table = pd.read_parquet(cp.path())
    box_teams = table[["event", "team"]]
    f = features(table, environment(box_teams))
    last_full = int(f["season"].max())
    f = f[f["season"] < last_full] if (f["season"] == last_full).sum() < 1000 else f
    base = cp.walk_forward(f)
    model = walk_forward(f, first_test=FIRST_TEST - 1)
    model = model.merge(ranges.walk_forward(model, first=FIRST_TEST), on=["season", "week", "player_id"], how="left")
    keep = ["season", "week", "player_id", "model", "model_sd", "model_lo", "model_hi"]
    return base.merge(model[keep], on=["season", "week", "player_id"], how="left")


def gate(regs: pd.DataFrame) -> pd.DataFrame:
    t = bm.summarise(regs, ("model", "baseline"), ["position"]).pivot(index="position", columns="model",
                                                                       values=["crps", "rank corr", "mae"])
    cov = ranges.coverage(regs, ["position"]).set_index("position")
    out = pd.DataFrame({"crps model": t[("crps", "model")], "crps baseline": t[("crps", "baseline")],
                        "rank model": t[("rank corr", "model")], "rank baseline": t[("rank corr", "baseline")],
                        "in range": cov["coverage"]})
    out["beats baseline"] = out["crps model"] < out["crps baseline"]
    out["ranges hold"] = out["in range"].between(*ranges.GATE)
    return out.reset_index()


def render(scored: pd.DataFrame) -> str:
    from atlas.models.evaluate import markdown

    regs = cp.regulars(scored)
    g = gate(regs)
    passed = bool(g["beats baseline"].all() and g["ranges hold"].all())
    gt = g.copy()
    for c in ("crps model", "crps baseline", "rank model", "rank baseline"):
        gt[c] = gt[c].map("{:.3f}".format)
    gt["in range"] = gt["in range"].map("{:.1%}".format)
    for c in ("beats baseline", "ranges hold"):
        gt[c] = gt[c].map({True: "yes", False: "no"})

    def fmt(t):
        t = t.copy()
        for c in ("mae", "crps", "rank corr"):
            t[c] = t[c].map("{:.3f}".format)
        return t

    seasons = f"{int(scored['season'].min())}-{int(scored['season'].max())}"
    line = scored["team_pts"].notna().mean()
    parts = [
        "# College DFS player projections", "",
        "Atlas's college player model (`atlas/dfs/cfb_model.py`, step 3 of `docs/MODEL_PLAN_DFS_CFB.md`): the "
        "step 2 baseline corrected by one gradient-boosted model per position that reads the game as the line "
        "implies it and each player's role from his earlier games. Walk-forward: every season predicted from the "
        f"seasons before it. {line:.0%} of scored player-games have a line.", "",
        f"## The gate, {seasons}, each team's regulars: {'passes' if passed else 'does not pass'}", "",
        "Beat the baseline's CRPS at every position, and 80% ranges that hold 76-84% of outcomes.", "",
        markdown(gt), "",
        "## By season", "", markdown(fmt(bm.summarise(regs, ("model", "baseline"), ["season"]))), "",
        "## Everyone who recorded a stat", "",
        markdown(fmt(bm.summarise(scored, ("model", "baseline"), ["position"]))), "",
        "## Caveats", "",
        "- College has no targets, snap counts, injury report or depth chart: the model knows a player's role only "
        "from what he has done, and nothing of the week's news.",
        "- Scored on the games where a player recorded a stat; whether he plays at all is a separate estimate for "
        "live slates.", "",
    ]
    return "\n".join(parts).rstrip() + "\n"


def main() -> None:
    argparse.ArgumentParser(description="College DFS player projections, walk-forward").parse_args()
    scored = run()
    out = config.paths().root / "reports" / "dfs_cfb_projections.md"
    out.write_text(render(scored))
    done = scored.dropna(subset=["model", "target"])
    ranges.save(ranges.fit(done), f"{int(done['season'].min())}-{int(done['season'].max())}",
                config.paths().root / "reports" / "dfs_cfb_ranges.json")
    LOG.info("wrote %s\n%s", out, gate(cp.regulars(scored)).round(3).to_string(index=False))


if __name__ == "__main__":
    main()
