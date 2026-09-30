"""The NHL's empirical profile, from the warehouse: `docs/MODEL_PLAN_NHL.md` §3, recomputed.

    python -m atlas.research.nhl_profile      # reports/nhl_profile.md

Step 1's test: the warehouse has to reproduce the plan's §3 before anything
is built on it. Every number the plan measured on 30 September 2026 from the
raw API calls is recomputed here from ``data/warehouse/nhl.duckdb``, beside
the plan's figure, so a difference is visible rather than silently carried.
Regular seasons only, 2010-11 to 2025-26.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from atlas import config
from atlas.util import get_logger

LOG = get_logger(__name__)

ERAS = {"2010-14": range(2010, 2014), "2014-20": range(2014, 2020), "2020-26": range(2020, 2026)}

#: §3 as the plan states it: (label, era or window, value).
PLAN = {
    "games": {"2010-14": 4410, "2014-20": 7314, "2020-26": 7428},
    "home_win": {"2010-14": 54.3, "2014-20": 54.4, "2020-26": 53.7},
    "home_win_reg": {"2010-14": 55.7, "2014-20": 55.5, "2020-26": 54.2},
    "ot": {"2010-14": 24.2, "2014-20": 23.1, "2020-26": 22.3},
    "so": {"2010-14": 13.7, "2014-20": 8.9, "2020-26": 7.3},
    "goals": {"2010-14": 5.37, "2014-20": 5.65, "2020-26": 6.13},
    "total_sd": {"2010-14": 2.22, "2014-20": 2.28, "2020-26": 2.32},
    "home_goals": {"2010-14": 2.82, "2014-20": 2.96, "2020-26": 3.18},
    "away_goals": {"2010-14": 2.54, "2014-20": 2.69, "2020-26": 2.95},
    "corr": {"2010-14": -0.05, "2014-20": -0.05, "2020-26": -0.11},
    "var_mean": {"2010-14": 0.97, "2014-20": 0.97, "2020-26": 0.99},
    "one_goal_reg": {"2010-14": 23.2, "2014-20": 21.4, "2020-26": 18.0},
    "two_goal": {"2010-14": 21.6, "2014-20": 20.9, "2020-26": 19.4},
    "three_plus": {"2010-14": 31.1, "2014-20": 34.6, "2020-26": 40.3},
}
PLAN_TOTALS = {3: 9.3, 4: 10.1, 5: 20.0, 6: 13.7, 7: 17.9, 8: 8.6, 9: 9.0, 10: 3.1}
PLAN_MARGINS = {-3: 10.5, -2: 9.3, -1: 15.6, 0: 7.3, 1: 17.3, 2: 10.1, 3: 13.0}


def report_path(root: Path) -> Path:
    return root / "reports" / "nhl_profile.md"


def regular(games: pd.DataFrame) -> pd.DataFrame:
    g = games[(games["season_type"] == "regular") & games["completed"].astype(bool)].copy()
    return g[g["season"] <= 2025]


def outcome_structure(games: pd.DataFrame) -> pd.DataFrame:
    rows = {}
    g = regular(games)
    for era, seasons in ERAS.items():
        e = g[g["season"].isin(seasons)]
        home_won = e["home_score"] > e["away_score"]
        reg = e[e["decision"] == "REG"]
        m = e["actual_margin"].abs()
        teams = pd.concat([e["home_goals"], e["away_goals"]])
        rows[era] = {
            "games": len(e), "home_win": 100 * home_won.mean(),
            "home_win_reg": 100 * (reg["home_score"] > reg["away_score"]).mean(),
            "ot": 100 * (e["decision"] != "REG").mean(), "so": 100 * (e["decision"] == "SO").mean(),
            "goals": e["actual_total"].mean(), "total_sd": e["actual_total"].std(),
            "home_goals": e["home_goals"].mean(), "away_goals": e["away_goals"].mean(),
            "corr": float(np.corrcoef(e["home_goals"], e["away_goals"])[0, 1]),
            "var_mean": teams.var() / teams.mean(),
            "one_goal_reg": 100 * ((e["decision"] == "REG") & (m == 1)).mean(),
            "two_goal": 100 * (m == 2).mean(), "three_plus": 100 * (m >= 3).mean(),
        }
    return pd.DataFrame(rows)


def home_by_season(games: pd.DataFrame) -> pd.Series:
    g = regular(games)
    return g.groupby("season").apply(lambda e: 100 * (e["home_score"] > e["away_score"]).mean(),
                                     include_groups=False)


def lattice(games: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    g = regular(games)
    g = g[g["season"].isin(ERAS["2020-26"])]
    totals = 100 * g["actual_total"].value_counts(normalize=True).sort_index()
    margins = 100 * g["actual_margin"].value_counts(normalize=True).sort_index()
    return totals, margins


def empty_net(games: pd.DataFrame, skaters: pd.DataFrame) -> dict:
    """Skater logs, 2022-23 to 2024-25: empty-net goals and how they shape the margin."""
    seasons = range(2022, 2025)
    g = regular(games)
    g = g[g["season"].isin(seasons)].set_index("game_id")
    sk = skaters[skaters["game_id"].isin(g.index)]
    en = sk.groupby(["game_id", "team"])["en_goals"].sum().reset_index()
    home = en.merge(g[["home_team"]].reset_index(), on="game_id")
    home = home[home["team"] == home["home_team"]].set_index("game_id")["en_goals"]
    total = en.groupby("game_id")["en_goals"].sum()
    g["en_home"] = home.reindex(g.index).fillna(0)
    g["en_total"] = total.reindex(g.index).fillna(0)
    g["en_away"] = g["en_total"] - g["en_home"]
    g["winner_en"] = np.where(g["actual_margin"] > 0, g["en_home"], g["en_away"])
    m = g["actual_margin"].abs()
    out = {"games": len(g), "per_game": g["en_total"].mean(), "share_with": (g["en_total"] > 0).mean()}
    for k in (1, 2, 3, 4):
        w = g[m == k]
        out[f"wins_by_{k}"] = (w["winner_en"] > 0).mean()
    two = g[(m == 2) & (g["winner_en"] > 0)]
    out["two_goal_with_en"] = len(two)
    out["two_goal_one_before"] = int((two["winner_en"] == 1).sum())
    return out


def overtime(games: pd.DataFrame) -> dict:
    g = regular(games)
    g = g[g["season"] >= 2015]
    ot, so = g[g["decision"] == "OT"], g[g["decision"] == "SO"]
    return {"ot_n": len(ot), "ot_home": (ot["home_score"] > ot["away_score"]).mean(),
            "so_n": len(so), "so_home": (so["home_score"] > so["away_score"]).mean()}


def rest(games: pd.DataFrame) -> pd.DataFrame:
    g = regular(games)
    rows = []
    both = g[(~g["home_b2b"]) & (~g["away_b2b"])]
    rows.append({"case": "both rested, home", "n": len(both), "win": (both["home_score"] > both["away_score"]).mean(),
                 "goals": both["actual_margin"].mean()})
    h = g[g["home_b2b"] & ~g["away_b2b"]]
    rows.append({"case": "home on the second night", "n": len(h), "win": (h["home_score"] > h["away_score"]).mean(),
                 "goals": h["actual_margin"].mean()})
    a = g[g["away_b2b"] & ~g["home_b2b"]]
    rows.append({"case": "away on the second night", "n": len(a), "win": (a["away_score"] > a["home_score"]).mean(),
                 "goals": -a["actual_margin"].mean()})
    return pd.DataFrame(rows)


#: Franchise-seasons followed by a move: the year-over-year pairs the plan did not make (it read teams
#: by their code at the time, so Atlanta-Winnipeg, Phoenix-Arizona and Arizona-Utah were never paired).
MOVED = {(2010, "WPG"), (2013, "UTA"), (2023, "UTA")}


def persistence(team_games: pd.DataFrame, games: pd.DataFrame) -> pd.DataFrame:
    """Split-half (the first half of a team's season against the second) and year-over-year correlations
    of team metrics, all situations; year over year pooled over every pair of consecutive seasons."""
    t = team_games[(team_games["season_type"] == "regular") & (team_games["season"] <= 2025)].copy()
    t["sf"] = t[[f"sog_{k}" for k in ("5v5", "PP", "SH", "EV", "EN", "ENA")]].sum(axis=1)
    t["sa"] = t[[f"soga_{k}" for k in ("5v5", "PP", "SH", "EV", "EN", "ENA")]].sum(axis=1)
    t = t.sort_values(["season", "team", "kickoff"])
    t["n"] = t.groupby(["season", "team"]).cumcount()
    t["odd"] = (t["n"] >= t.groupby(["season", "team"])["n"].transform("size") / 2).astype(int)

    def shares(f: pd.DataFrame) -> pd.DataFrame:
        a = f.agg(sf=("sf", "sum"), sa=("sa", "sum"), gf=("goals_for", "sum"), ga=("goals_against", "sum"))
        a["shot_share"] = a["sf"] / (a["sf"] + a["sa"])
        a["goal_share"] = a["gf"] / (a["gf"] + a["ga"])
        a["sh_pct"] = a["gf"] / a["sf"]
        a["sv_pct"] = 1 - a["ga"] / a["sa"]
        a["pdo"] = a["sh_pct"] + a["sv_pct"]
        return a

    halves = shares(t.groupby(["season", "team", "odd"]))
    rows = []
    for metric in ("shot_share", "goal_share", "sh_pct", "sv_pct", "pdo"):
        per = []
        for _, part in halves[metric].groupby(level="season"):
            w = part.unstack("odd")
            per.append(np.corrcoef(w[0], w[1])[0, 1])
        full = shares(t.groupby(["season", "team"]))[metric]
        pairs = [(v, full.get((s + 1, team))) for (s, team), v in full.items() if (s, team) not in MOVED]
        pairs = np.array([(a, b) for a, b in pairs if b is not None and np.isfinite(a) and np.isfinite(b)])
        rows.append({"metric": metric, "split_half": float(np.median(per)), "lo": float(np.min(per)),
                     "hi": float(np.max(per)), "yoy": _corr(pairs[:, 0], pairs[:, 1]) if len(pairs) else np.nan})
    return pd.DataFrame(rows)


def handover(team_games: pd.DataFrame) -> pd.DataFrame:
    """Correlation with the rest of the season's goal share: last season's, to-date shot share and goal share."""
    t = team_games[(team_games["season_type"] == "regular") & (team_games["season"] <= 2025)].copy()
    t["sf"] = t.filter(regex=r"^sog_").sum(axis=1)
    t["sa"] = t.filter(regex=r"^soga_").sum(axis=1)
    t = t.sort_values(["season", "team", "kickoff"])
    t["n"] = t.groupby(["season", "team"]).cumcount()
    season_share = t.groupby(["season", "team"]).apply(
        lambda f: f["goals_for"].sum() / (f["goals_for"].sum() + f["goals_against"].sum()), include_groups=False)
    rows = []
    for k in (0, 5, 10, 20, 40):
        before, after = t[t["n"] < k], t[t["n"] >= k]
        a = after.groupby(["season", "team"]).agg(gf=("goals_for", "sum"), ga=("goals_against", "sum"))
        rest_share = a["gf"] / (a["gf"] + a["ga"])
        prior = rest_share.index.map(lambda st: season_share.get((st[0] - 1, st[1]), np.nan))
        row = {"games": k, "prior": _corr(np.asarray(prior, float), rest_share.to_numpy())}
        if k:
            b = before.groupby(["season", "team"]).agg(sf=("sf", "sum"), sa=("sa", "sum"), gf=("goals_for", "sum"),
                                                       ga=("goals_against", "sum")).reindex(rest_share.index)
            row["shots"] = _corr((b["sf"] / (b["sf"] + b["sa"])).to_numpy(), rest_share.to_numpy())
            row["goals"] = _corr((b["gf"] / (b["gf"] + b["ga"])).to_numpy(), rest_share.to_numpy())
        rows.append(row)
    return pd.DataFrame(rows)


def _corr(a: np.ndarray, b: np.ndarray) -> float:
    ok = np.isfinite(a) & np.isfinite(b)
    return float(np.corrcoef(a[ok], b[ok])[0, 1]) if ok.sum() > 10 else float("nan")


def goaltenders(goalies: pd.DataFrame) -> dict:
    g = goalies[(goalies["season_type"] == "regular") & (goalies["season"] <= 2025)].copy()
    starts = g[g["started"] == 1]
    share = starts.groupby(["season", "team", "player_id"]).size()
    top = share.groupby(level=["season", "team"]).max() / share.groupby(level=["season", "team"]).sum()
    out = {era: 100 * float(top[top.index.get_level_values("season").isin(s)].median()) for era, s in ERAS.items()}
    # Save percentage for goalies with 40+ starts: odd/even-game reliability, year over year, spread.
    s = starts.sort_values(["season", "player_id", "kickoff"])
    s["n"] = s.groupby(["season", "player_id"]).cumcount()
    big = s.groupby(["season", "player_id"]).filter(lambda f: len(f) >= 40)
    halves = big.groupby(["season", "player_id", big["n"] % 2]).agg(sa=("shots_against", "sum"),
                                                                    ga=("goals_against", "sum"))
    sv = (1 - halves["ga"] / halves["sa"]).unstack()
    full = big.groupby(["season", "player_id"]).agg(sa=("shots_against", "sum"), ga=("goals_against", "sum"))
    sv_full = 1 - full["ga"] / full["sa"]
    nxt = sv_full.copy()
    nxt.index = pd.MultiIndex.from_arrays([nxt.index.get_level_values(0) - 1, nxt.index.get_level_values(1)])
    pair = pd.concat([sv_full, nxt], axis=1, join="inner").dropna()
    out.update(split_half=_corr(sv[0].to_numpy(), sv[1].to_numpy()), split_n=len(sv),
               yoy=_corr(pair.iloc[:, 0].to_numpy(), pair.iloc[:, 1].to_numpy()), yoy_n=len(pair),
               sd=float(100 * sv_full.std()))
    return out


def props(skaters: pd.DataFrame, goalies: pd.DataFrame, games: pd.DataFrame) -> dict:
    """Skater logs 2022-23 to 2024-25: odd/even reliability for players with 40+ games and dispersion."""
    reg_ids = set(games.loc[games["season_type"] == "regular", "game_id"])
    sk = skaters[skaters["game_id"].isin(reg_ids) & skaters["game_id"].astype(str).str[:4].astype(int).isin(
        range(2022, 2025))].copy()
    sk = sk.sort_values(["player_id", "game_id"])
    key = sk["game_id"].astype(str).str[:4]
    sk["season"] = key.astype(int)
    sk["n"] = sk.groupby(["season", "player_id"]).cumcount()
    many = sk.groupby(["season", "player_id"]).filter(lambda f: len(f) >= 40)
    out = {"player_games": len(sk)}
    for stat in ("shots", "toi", "points", "hits", "blocks"):
        h = many.groupby(["season", "player_id", many["n"] % 2])[stat].mean().unstack()
        out[f"rel_{stat}"] = _corr(h[0].to_numpy(), h[1].to_numpy())
        mean = many.groupby(["season", "player_id"])[stat].transform("mean")
        if stat != "toi":
            out[f"vm_{stat}"] = float(((many[stat] - mean) ** 2).mean() / many[stat].mean())
    # Shots over 2.5 by the player's season mean without the game itself, against Poisson on that mean.
    total = sk.groupby(["season", "player_id"])["shots"].transform("sum")
    count = sk.groupby(["season", "player_id"])["shots"].transform("size")
    mean = (total - sk["shots"]) / (count - 1)
    from scipy.stats import poisson

    for lo, hi in ((3.0, 3.5), (3.5, 4.0)):
        band = sk[(mean >= lo) & (mean < hi)]
        out[f"over_{lo}"] = float((band["shots"] > 2.5).mean())
        out[f"poisson_{lo}"] = float((1 - poisson.cdf(2, mean[band.index])).mean())
    g = goalies[(goalies["started"] == 1) & (goalies["season"].between(2021, 2025))
                & (goalies["season_type"] == "regular")]
    gm = g.groupby(["season", "player_id"])["saves"].transform("mean")
    out["saves_vm"] = float(((g["saves"] - gm) ** 2).mean() / g["saves"].mean())
    out["saves_sd"] = float(g["saves"].std())
    out["saves_mean"] = float(g["saves"].mean())
    return out


def market(games: pd.DataFrame, odds: pd.DataFrame) -> dict:
    """The closing moneyline's Brier on P(home) including overtime, against "the home side, always"."""
    g = games[games["completed"].astype(bool)].set_index("game_id")          # the playoffs too
    o = odds[odds["game_id"].isin(g.index) & odds["season"].between(2010, 2021)].copy()
    o = o.dropna(subset=["home_ml_close", "away_ml_close"])

    def prob(ml):
        from atlas.models.nhl_benchmarks import implied

        return implied(ml)

    ph, pa = prob(o["home_ml_close"]), prob(o["away_ml_close"])
    p = ph / (ph + pa)
    won = (g.loc[o["game_id"], "home_score"].to_numpy() > g.loc[o["game_id"], "away_score"].to_numpy()).astype(float)
    naive = won.mean()
    fav = np.maximum(p, 1 - p)
    margin = g.loc[o["game_id"], "actual_margin"].to_numpy()
    fav_by_two = np.where(p >= 0.5, margin >= 2, margin <= -2)
    band = (fav >= 0.65) & (fav < 0.70)
    early, late = o["season"].to_numpy() <= 2018, o["season"].to_numpy() >= 2019
    last = o["season"].to_numpy() == 2021
    return {"games": len(o), "market": float(np.mean((p - won) ** 2)),
            "naive": float(np.mean((naive - won) ** 2)), "market_2021": float(np.mean((p[last] - won[last]) ** 2)),
            "naive_2021": float(np.mean((won[last].mean() - won[last]) ** 2)),
            "fav2_2010_19": float(fav_by_two[band & early].mean()), "fav2_2019_22": float(fav_by_two[band & late].mean())}


def arena(team_games: pd.DataFrame, skaters: pd.DataFrame, games: pd.DataFrame) -> dict:
    """Total shots and hits in a team's home games over its road games, 2022-23 to 2024-25."""
    g = regular(games)
    g = g[g["season"].between(2022, 2024)]
    sk = skaters[skaters["game_id"].isin(g["game_id"])]
    per = sk.groupby("game_id").agg(shots=("shots", "sum"), hits=("hits", "sum"))
    g = g.set_index("game_id").join(per)
    out = {}
    for stat in ("shots", "hits"):
        home = g.groupby("home_team")[stat].mean()
        road = g.groupby("away_team")[stat].mean()
        ratio = (home / road).dropna()
        out[stat] = {"lo": (ratio.idxmin(), float(ratio.min())), "hi": (ratio.idxmax(), float(ratio.max())),
                     "sd": float(ratio.std())}
    return out


def _fmt(v, digits=1) -> str:
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f"{v:.{digits}f}"


def write(root: Path) -> Path:
    from atlas.staging.nhl import build as nhl_build

    games = nhl_build.load("games")
    team_games = nhl_build.load("team_games")
    goalies = nhl_build.load("goalie_games")
    skaters = nhl_build.load("skater_games")
    odds = nhl_build.load("odds")
    lines = ["# NHL empirical profile, recomputed from the warehouse (plan §3)", "",
             "Generated by `python -m atlas.research.nhl_profile` from `data/warehouse/nhl.duckdb`. Each figure is "
             "beside the plan's (`docs/MODEL_PLAN_NHL.md` §3, measured from the raw API on 30 September 2026). "
             "Regular seasons.", "", "## Outcome structure", "",
             "| | " + " | ".join(ERAS) + " |", "|---|" + "---|" * len(ERAS)]
    oc = outcome_structure(games)
    labels = {"games": ("Games", 0), "home_win": ("Home win % (incl. OT/SO)", 1),
              "home_win_reg": ("Home win % of regulation decisions", 1), "ot": ("Overtime %", 1),
              "so": ("Shootout %", 1), "goals": ("Goals per game", 2), "total_sd": ("Total, sd", 2),
              "home_goals": ("Home goals per game", 2), "away_goals": ("Away goals per game", 2),
              "corr": ("Home-away goals correlation", 2), "var_mean": ("Team goals var/mean", 2),
              "one_goal_reg": ("One-goal regulation games %", 1), "two_goal": ("Two-goal games %", 1),
              "three_plus": ("Three+ goal games %", 1)}
    for key, (label, d) in labels.items():
        cells = [f"{_fmt(oc.loc[key, era], d)} (plan {PLAN[key][era]})" for era in ERAS]
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    hs = home_by_season(games)
    lines += ["", f"Home win % by season: {hs.min():.1f} to {hs.max():.1f} (plan 51.9 to 56.8).", ""]
    totals, margins = lattice(games)
    lines += ["## The lattice, 2020-26", "", "| Total | Share % | Plan |", "|---|---|---|"]
    for k, v in PLAN_TOTALS.items():
        lines.append(f"| {k} | {totals.get(k, 0):.1f} | {v} |")
    lines += ["", "| Home margin | Share % | Plan |", "|---|---|---|"]
    for k, v in PLAN_MARGINS.items():
        lines.append(f"| {k:+d} | {margins.get(k, 0):.1f} | {v} |")
    en = empty_net(games, skaters)
    lines += ["", "## The empty net, 2022-23 to 2024-25", "",
              f"- Empty-net goals a game: {en['per_game']:.2f} (plan 0.36); games with one: {100 * en['share_with']:.0f}% "
              "(plan about a third).",
              f"- Wins by one, two, three, four that include one: {100 * en['wins_by_1']:.0f}%, "
              f"{100 * en['wins_by_2']:.0f}%, {100 * en['wins_by_3']:.0f}%, {100 * en['wins_by_4']:.0f}% "
              "(plan 2, 64, 63, 35).",
              f"- Two-goal wins with one empty-netter (one-goal games before it): {en['two_goal_one_before']} of "
              f"{en['two_goal_with_en']} (plan 497 of 506)."]
    ot = overtime(games)
    lines += ["", "## Overtime and the shootout, 2015-26", "",
              f"Home teams win {100 * ot['ot_home']:.1f}% of overtimes (n = {ot['ot_n']:,}; plan 51.0%, 2,013) and "
              f"{100 * ot['so_home']:.1f}% of shootouts (n = {ot['so_n']:,}; plan 51.6%, 1,022)."]
    r = rest(games)
    lines += ["", "## Rest", "", "| Case | n | Win % | Goals | Plan |", "|---|---|---|---|---|"]
    plan_rest = ["53.5%, +0.22", "46.8%, −0.09 (n = 1,048)", "40.8%, −0.50 (n = 3,296)"]
    for row, plan in zip(r.itertuples(), plan_rest, strict=True):
        lines.append(f"| {row.case} | {row.n:,} | {100 * row.win:.1f} | {row.goals:+.2f} | {plan} |")
    p = persistence(team_games, games)
    plan_p = {"shot_share": ("0.72 (0.45-0.86)", "0.65"), "goal_share": ("0.50 (0.15-0.80)", "0.55"),
              "sh_pct": ("0.30", "0.53"), "sv_pct": ("0.27", "0.48"), "pdo": ("0.30", "—")}
    lines += ["", "## Persistence", "", "First half of each team's season against the second; year over year pooled "
              "over consecutive seasons, relocations not paired.", "",
              "| Metric | Split-half (median season, range) | Year over year | Plan |",
              "|---|---|---|---|"]
    for row in p.itertuples():
        lines.append(f"| {row.metric} | {row.split_half:.2f} ({row.lo:.3f}-{row.hi:.2f}) | {_fmt(row.yoy, 3)} | "
                     f"{plan_p[row.metric][0]}, {plan_p[row.metric][1]} |")
    h = handover(team_games)
    plan_h = {0: "0.55", 5: "0.54 / 0.38 / 0.26", 10: "0.53 / 0.44 / 0.37", 20: "0.50 / 0.47 / 0.49",
              40: "0.42 / 0.45 / 0.51"}
    lines += ["", "## How fast in-season data overtakes the prior", "",
              "| Games | Last season's goal share | To-date shot share | To-date goal share | Plan |", "|---|---|---|---|---|"]
    for row in h.itertuples():
        lines.append(f"| {row.games} | {row.prior:.2f} | {_fmt(getattr(row, 'shots', np.nan), 2)} | "
                     f"{_fmt(getattr(row, 'goals', np.nan), 2)} | {plan_h[row.games]} |")
    gt = goaltenders(goalies)
    lines += ["", "## Goaltenders", "",
              f"- The #1's share of starts, median: {gt['2010-14']:.1f}%, {gt['2014-20']:.1f}%, {gt['2020-26']:.1f}% "
              "(plan 69.5, 64.6, 59.8).",
              f"- Save %, 40+ starts: odd/even reliability {gt['split_half']:.2f} ({gt['split_n']} goalie-seasons; plan "
              f"0.31, 391), year over year {gt['yoy']:.2f} ({gt['yoy_n']}; plan 0.44, 224), sd {gt['sd']:.2f} points "
              "(plan 1.07)."]
    pr = props(skaters, goalies, games)
    lines += ["", "## Player props, 2022-23 to 2024-25", "",
              f"{pr['player_games']:,} player-games (plan 141,653).", "",
              "| Stat | Odd/even reliability, 40+ games | Var/mean | Plan |", "|---|---|---|---|",
              f"| Shots | {pr['rel_shots']:.2f} | {pr['vm_shots']:.2f} | 0.91, 1.10 |",
              f"| Time on ice | {pr['rel_toi']:.2f} | — | 0.99 |",
              f"| Points | {pr['rel_points']:.2f} | {pr['vm_points']:.2f} | 0.85, 0.95 |",
              f"| Hits | {pr['rel_hits']:.2f} | {pr['vm_hits']:.2f} | 0.94, 1.20 |",
              f"| Blocks | {pr['rel_blocks']:.2f} | {pr['vm_blocks']:.2f} | 0.92, 1.12 |", "",
              "Players by their season mean without the game: at 3.0-3.5 shots a game, over 2.5 "
              f"{100 * pr['over_3.0']:.1f}% against Poisson's "
              f"{100 * pr['poisson_3.0']:.1f}% (plan 58.2 / 62.2); 3.5-4.0: {100 * pr['over_3.5']:.1f}% against "
              f"{100 * pr['poisson_3.5']:.1f}% (plan 65.0 / 71.9).", "",
              f"Goalie saves, starters 2021-26: var/mean {pr['saves_vm']:.2f}, sd {pr['saves_sd']:.1f} on a mean of "
              f"{pr['saves_mean']:.0f} (plan 2.11, 7.4, 26)."]
    ar = arena(team_games, skaters, games)
    lines += ["", "## The scorekeeper", "",
              f"Total shots, home games over road games: {ar['shots']['lo'][1]:.2f} ({ar['shots']['lo'][0]}) to "
              f"{ar['shots']['hi'][1]:.2f} ({ar['shots']['hi'][0]}), sd {ar['shots']['sd']:.3f} (plan 0.95 NJD to "
              f"1.07 FLA, sd 0.026). Hits: {ar['hits']['lo'][1]:.2f} ({ar['hits']['lo'][0]}) to "
              f"{ar['hits']['hi'][1]:.2f} ({ar['hits']['hi'][0]}), sd {ar['hits']['sd']:.2f} (plan 0.81 SJS to 1.30 TOR, "
              "sd 0.12)."]
    if len(odds):
        mk = market(games, odds)
        lines += ["", "## The market, 2010-11 to 2021-22", "",
                  f"Closing moneylines, {mk['games']:,} games, playoffs included (plan 14,866): Brier "
                  f"{mk['market']:.4f} against {mk['naive']:.4f} for the home side, always (plan 0.2385 / 0.2482); "
                  f"2021-22 alone {mk['market_2021']:.4f} against {mk['naive_2021']:.4f} (plan 0.2256 / 0.2483). "
                  "A closing favourite of "
                  f"65-70% won by two or more {100 * mk['fav2_2010_19']:.1f}% of the time in 2010-19 and "
                  f"{100 * mk['fav2_2019_22']:.1f}% in 2019-22 (plan 39.3 / 44.1)."]
    out = report_path(root)
    out.write_text("\n".join(lines) + "\n")
    return out


def main() -> None:
    argparse.ArgumentParser(description="Recompute the NHL plan's §3 from the warehouse").parse_args()
    print(write(config.paths().root))


if __name__ == "__main__":
    main()
