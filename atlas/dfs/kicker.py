"""Kickers: the one Showdown position the player model does not cover.

    python -m atlas.dfs.kicker                # walk-forward; writes reports/dfs_kickers.md
    python -m atlas.dfs.kicker --reconcile    # also checks the scoring against DraftKings' live averages

DraftKings' Classic lineup has no kicker; Showdown Captain Mode does. A
kicker's points come from field goals (3, 4 or 5 by distance) and extra
points (1), so his week is mostly his team's: how many drives stall in
range and how many end in the end zone. The model reads exactly that:

* the game - both teams' projected points from Atlas's game model and from
  the betting line, and the wind (a dome is none);
* the kicker's own recent attempts (field goals, long ones, extra points)
  and scoring, from his earlier games only;

and corrects his recent scoring, shrunk to the league's, with one small
gradient-boosted model - the same form and settings as the player model
(`atlas/dfs/model.py`). Walk-forward: each season fitted on the seasons
before it. Ranges are the 10th and 90th percentiles of the model's own
out-of-sample misses (`atlas/dfs/ranges.py`).

The gate (the Showdown extension of `docs/MODEL_PLAN_DFS.md`): the scoring
matches DraftKings' own; the model beats the baseline's CRPS on 2015-2025;
the 80% ranges cover 76-84%.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

from atlas import config
from atlas.dfs import benchmarks as bm
from atlas.dfs import environment, ranges, scoring
from atlas.dfs import model as player_model
from atlas.sources import nflverse
from atlas.staging.nfl.games import FRANCHISE
from atlas.util import get_logger

LOG = get_logger(__name__)

FIRST_TRAIN = 2011
FIRST_OOS = 2013                   # the first season predicted: it and the next calibrate the spread and ranges
FIRST_TEST = 2015
HALFLIFE, LONG_HALFLIFE = 4.0, 16.0
SHRINK_GRID = (0.0, 1.0, 2.0, 4.0, 8.0, 16.0)
TRENDS = ("dk_points", "fg_att", "pat_att", "long_att")
FEATURES = ["team_pts", "opp_pts", "proj_total", "proj_margin", "mkt_pts", "mkt_opp", "wind", "home",
            "games_before", "dk_points_trend", "dk_points_long", "fg_att_trend", "pat_att_trend", "long_att_trend",
            "baseline"]
PARAMS = player_model.PARAMS


def report_path() -> Path:
    return config.paths().root / "reports" / "dfs_kickers.md"


def lines_path() -> Path:
    return config.paths().root / "reports" / "dfs_kicker_lines.json"


def games(raw: Path | None = None, seasons: list[int] | None = None) -> pd.DataFrame:
    """One row per kicker-game in the regular season, with his DraftKings points."""
    raw = raw or config.paths().raw
    seasons = seasons or list(range(nflverse.FIRST_SEASON, nflverse.current_season() + 1))
    frames = [pd.read_parquet(nflverse.player_stats_path(raw, s)) for s in seasons
              if nflverse.player_stats_path(raw, s).exists()]
    s = pd.concat(frames, ignore_index=True)
    s = s[s["season_type"] == "REG"]
    kicked = s.get("fg_att", 0).fillna(0) + s.get("pat_att", 0).fillna(0)
    s = s[(s["position"] == "K") | (kicked > 0)].copy()
    long_cols = [c for c in ("fg_made_50_59", "fg_made_60_", "fg_missed_50_59", "fg_missed_60_") if c in s]
    return pd.DataFrame({
        "season": s["season"].astype(int), "week": s["week"].astype(int), "season_type": "REG",
        "team": s["team"].replace(FRANCHISE), "opponent": s["opponent_team"].replace(FRANCHISE),
        "player_id": s["player_id"], "name": s["player_display_name"].fillna(s["player_name"]),
        "dk_points": scoring.kicker_points(s), "fg_att": s["fg_att"].fillna(0),
        "pat_att": s["pat_att"].fillna(0), "long_att": s[long_cols].fillna(0).sum(axis=1),
    }).reset_index(drop=True)


def with_trends(g: pd.DataFrame) -> pd.DataFrame:
    """Shifted trends: each row's history before its game, carried across seasons."""
    g = g.sort_values(["player_id", "season", "week"]).copy()
    by = g.groupby("player_id", sort=False)
    g["games_before"] = by.cumcount()
    for col in TRENDS:
        g[f"{col}_trend"] = by[col].transform(lambda x: x.shift(1).ewm(halflife=HALFLIFE, ignore_na=True).mean())
    g["dk_points_long"] = by["dk_points"].transform(
        lambda x: x.shift(1).ewm(halflife=LONG_HALFLIFE, ignore_na=True).mean())
    return g.sort_values(["season", "week", "team"]).reset_index(drop=True)


def frame(g: pd.DataFrame, env: pd.DataFrame | None = None, market: pd.DataFrame | None = None) -> pd.DataFrame:
    """Kicker-games with their game's environment and the line's team totals."""
    env = env if env is not None else pd.read_parquet(environment.path())
    market = market if market is not None else player_model.market_totals()
    cols = ["season", "week", "team", "team_pts", "opp_pts", "proj_total", "proj_margin", "home", "wind"]
    f = with_trends(g).merge(env[cols], on=["season", "week", "team"], how="left")
    f = f.merge(market, on=["season", "week", "team"], how="left")
    return f.assign(target=f["dk_points"])


def _shrink(train: pd.DataFrame) -> tuple[float, float]:
    """The league's mean, and how many games of a kicker's own history outweigh it."""
    mean = float(train["target"].mean())
    best = min(SHRINK_GRID, key=lambda k: np.mean(np.abs(_baseline(train, mean, k) - train["target"])))
    return mean, best


def _baseline(rows: pd.DataFrame, mean: float, k: float) -> np.ndarray:
    n = rows["games_before"].clip(upper=bm.HISTORY_CAP).to_numpy(dtype=float)
    trend = rows["dk_points_trend"].fillna(mean).to_numpy(dtype=float)
    return np.where(n + k > 0, (n * trend + k * mean) / np.maximum(n + k, 1e-9), mean)


def predict(train: pd.DataFrame, test: pd.DataFrame) -> pd.DataFrame:
    """Fit on ``train``, predict ``test``: the baseline and the model."""
    mean, k = _shrink(train)
    train = train.assign(baseline=_baseline(train, mean, k))
    test = test.assign(baseline=_baseline(test, mean, k))
    fitted = HistGradientBoostingRegressor(**PARAMS).fit(
        train[FEATURES].to_numpy(dtype=float), (train["target"] - train["baseline"]).to_numpy(dtype=float))
    return test.assign(model=test["baseline"].to_numpy() + fitted.predict(test[FEATURES].to_numpy(dtype=float)))


def walk_forward(f: pd.DataFrame, *, first: int = FIRST_OOS) -> pd.DataFrame:
    done = f.dropna(subset=["target"])
    parts = [predict(done[(done["season"] >= FIRST_TRAIN) & (done["season"] < s)], done[done["season"] == s])
             for s in sorted(int(x) for x in done["season"].unique()) if s >= first]
    return pd.concat(parts, ignore_index=True)


def score(oos: pd.DataFrame, *, first: int = FIRST_TEST) -> pd.DataFrame:
    """Each season from ``first`` with spreads and ranges fitted on the seasons before it."""
    parts = []
    for season in sorted(int(s) for s in oos["season"].unique()):
        if season < first:
            continue
        past, now = oos[oos["season"] < season], oos[oos["season"] == season].copy()
        for name in ("model", "baseline"):
            a, b = bm._spread(past[name].to_numpy(dtype=float), past["target"].to_numpy(dtype=float))
            now[f"{name}_sd"] = np.maximum(a + b * now[name].to_numpy(dtype=float), 1.0)
        lines = ranges.fit(past.assign(position="K"))
        now = now.join(ranges.apply(now.assign(position="K"), lines))
        parts.append(now)
    return pd.concat(parts, ignore_index=True)


def summary(scored: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for name in ("model", "baseline"):
        y, mu = scored["target"].to_numpy(dtype=float), scored[name].to_numpy(dtype=float)
        rows.append({"projection": name, "kicker-games": len(scored), "mae": float(np.mean(np.abs(y - mu))),
                     "crps": float(np.mean(bm.crps_normal(mu, scored[f"{name}_sd"].to_numpy(dtype=float), y))),
                     "rank corr": bm.rank_correlation(scored.assign(position="K"), name)})
    return pd.DataFrame(rows)


def reconcile(pools: list[dict], g: pd.DataFrame, season: int) -> pd.DataFrame:
    """DraftKings' own points-per-game for each pool kicker against Atlas's scoring of the same games."""
    from atlas.dfs import players

    seen, rows = set(), []
    this = g[g["season"] == season].assign(key=lambda x: x["name"].map(players.norm_name))
    for pool in pools:
        stat = next((s.get("id") for s in pool.get("draftStats", []) or [] if s.get("abbr") == "FPPG"), 90)
        for d in pool.get("draftables", []) or []:
            if d.get("position") != "K" or d.get("playerId") in seen:
                continue
            seen.add(d.get("playerId"))
            fppg = next((a.get("value") for a in d.get("draftStatAttributes", []) or [] if a.get("id") == stat), None)
            try:
                fppg = float(fppg)
            except (TypeError, ValueError):
                continue                              # no games yet this season
            mine = this[this["key"] == players.norm_name(d.get("displayName"))]
            rows.append({"kicker": d.get("displayName"), "draftkings": fppg,
                         "atlas": float(mine["dk_points"].mean()) if len(mine) else np.nan, "games": len(mine)})
    out = pd.DataFrame(rows, columns=["kicker", "draftkings", "atlas", "games"])
    out["agrees"] = (out["draftkings"] - out["atlas"]).abs() <= 0.05
    return out


def _fetch_pools() -> list[dict]:
    from atlas.sources import draftkings as dk
    from atlas.util import http_get, session

    sess = session()
    lobby = http_get(dk.LOBBY, sess=sess, timeout=30).json()
    groups = dk.slates(lobby, types=(dk.SHOWDOWN,))
    return [http_get(dk.DRAFTABLES.format(group=gid), sess=sess, timeout=30).json() for gid in groups["draft_group_id"]]


def render(scored: pd.DataFrame, rec: pd.DataFrame | None, season: int) -> str:
    from atlas.models.evaluate import markdown

    table = summary(scored)
    m, b = table.set_index("projection").loc["model"], table.set_index("projection").loc["baseline"]
    cov = ranges.coverage(scored.assign(position="K"))
    by_season = ranges.coverage(scored.assign(position="K"), ["season"])
    beats = m["crps"] < b["crps"]
    covered = bool(ranges.GATE[0] <= cov["coverage"].iloc[0] <= ranges.GATE[1])
    scoring_ok = rec is None or (len(rec) > 0 and bool(rec["agrees"].all()))
    passed = beats and covered and (rec is not None and scoring_ok)

    def fmt(t):
        t = t.copy()
        for c in ("mae", "crps", "rank corr"):
            if c in t:
                t[c] = t[c].map("{:.3f}".format)
        for c in ("coverage", "below", "above"):
            if c in t:
                t[c] = t[c].map("{:.1%}".format)
        if "width" in t:
            t["width"] = t["width"].map("{:.1f}".format)
        return t

    parts = [
        "# DFS kickers", "",
        "Atlas's kicker model for DraftKings Showdown (`atlas/dfs/kicker.py`): the kicker's recent scoring, shrunk "
        "to the league's, corrected for his game - both teams' projected points from Atlas's game model and the "
        "line, the wind - and his recent attempts. Walk-forward: each season fitted on the seasons before it.", "",
        f"## The gate: {'passes' if passed else 'does not pass' if rec is not None else 'passes on the model; scoring check not run'}", "",
        "- **Scoring matches DraftKings'**: "
        + ("not checked in this run (`--reconcile`)." if rec is None else
           f"{int(rec['agrees'].sum())} of {len(rec)} kickers in DraftKings' {season} Showdown pools have exactly "
           f"the points per game Atlas computes (field goal 0-39 yards 3, 40-49 yards 4, 50+ yards 5, extra point "
           f"1, no penalty for a miss)."),
        f"- **Beats the baseline's CRPS**, {int(scored['season'].min())}-{int(scored['season'].max())}: "
        f"{m['crps']:.3f} against {b['crps']:.3f} - {'yes' if beats else 'no'}.",
        f"- **80% ranges cover 76-84%**: {cov['coverage'].iloc[0]:.1%} - {'yes' if covered else 'no'}.", "",
        "## Model against the baseline", "", markdown(fmt(table)), "",
        "## Ranges by season", "", markdown(fmt(by_season)), "",
    ]
    if rec is not None and len(rec):
        r = rec.copy()
        r["draftkings"] = r["draftkings"].map("{:.1f}".format)
        r["atlas"] = r["atlas"].map("{:.2f}".format)
        r["agrees"] = r["agrees"].map({True: "yes", False: "no"})
        parts += [f"## Scoring against DraftKings, {season} so far", "", markdown(r), ""]
    parts += ["A kicker's week is mostly his team's, so the ranking among kickers is modest; the range, which "
              "is wide, is the honest part of the number.", ""]
    return "\n".join(parts).rstrip() + "\n"


def save_lines(scored_all: pd.DataFrame) -> Path:
    """The range lines on every out-of-sample miss, for live projections."""
    lines = ranges.fit(scored_all.assign(position="K"))
    return ranges.save(lines, f"{int(scored_all['season'].min())}-{int(scored_all['season'].max())}", lines_path())


def project(rows: pd.DataFrame, *, raw: Path | None = None) -> pd.DataFrame:
    """Live: ``rows`` (season, week, team, opponent, player_id) with projection,
    low, high and p_play - fitted on the seasons before the rows' season."""
    g = games(raw)
    season = int(rows["season"].mode().iloc[0])
    new = rows[["season", "week", "team", "opponent", "player_id"]].assign(
        season_type="REG", dk_points=np.nan, fg_att=np.nan, pat_att=np.nan, long_att=np.nan, name="")
    keys = new[["season", "week", "player_id"]]
    g = g.merge(keys, on=["season", "week", "player_id"], how="left", indicator=True)
    g = g[g["_merge"] == "left_only"].drop(columns="_merge")
    f = frame(pd.concat([g, new], ignore_index=True))
    done = f.dropna(subset=["target"])
    test = f.merge(keys, on=["season", "week", "player_id"], how="inner")
    got = predict(done[(done["season"] >= FIRST_TRAIN) & (done["season"] < season)], test)
    lines = ranges.load(lines_path())
    got = got.join(ranges.apply(got.assign(position="K"), lines))
    # The team's kicker is whoever kicked in its latest game; anyone else is unlikely to.
    last = done.sort_values(["season", "week"]).groupby("team").tail(1)
    latest = done.merge(last[["team", "season", "week"]], on=["team", "season", "week"])
    starters = set(latest["player_id"])
    got["p_play"] = np.where(got["player_id"].isin(starters), 0.98, 0.05)
    return got[["season", "week", "player_id", "model", "model_lo", "model_hi", "p_play"]]


def main() -> None:
    parser = argparse.ArgumentParser(description="DFS kicker model, walk-forward")
    parser.add_argument("--reconcile", action="store_true", help="check the scoring against DraftKings' averages")
    args = parser.parse_args()
    g = games()
    oos = walk_forward(frame(g))
    last_full = int(oos["season"].max())
    scored = score(oos[oos["season"] < last_full]) if last_full > FIRST_TEST else score(oos)
    season = nflverse.current_season()
    rec = reconcile(_fetch_pools(), g, season) if args.reconcile else None
    report_path().write_text(render(scored, rec, season))
    save_lines(oos.dropna(subset=["model", "target"]))
    LOG.info("wrote %s\n%s", report_path(), summary(scored).round(3).to_string(index=False))
    if rec is not None:
        LOG.info("scoring: %d of %d kickers agree", int(rec["agrees"].sum()), len(rec))


if __name__ == "__main__":
    main()
