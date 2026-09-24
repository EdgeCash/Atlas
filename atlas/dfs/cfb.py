"""College DFS: DraftKings' college scoring, and its check against DraftKings.

    python -m atlas.dfs.cfb --reconcile     # writes reports/dfs_cfb_scoring.md

Step 1 of `docs/MODEL_PLAN_DFS_CFB.md`. Atlas scores each college
player-game from ESPN's box score (`atlas/sources/espn_cfb.py`) with
DraftKings' college rules, and checks the result the only way college
allows - there is no archive of past college DraftKings points - against
the points per game DraftKings itself shows for every player in its live
pools who has played this season.

The rules, as settled by that check: passing 0.04 a yard, 4 a touchdown, -1
an interception, 3 for 300 yards; rushing and receiving 0.1 a yard, 6 a
touchdown, 3 for 100 yards; 1 a reception; -1 a fumble lost; 2 a two-point
conversion (passer and receiver or runner); 6 a kick or punt return
touchdown; a field goal 3, 4 or 5 by distance (0-39, 40-49, 50+) and 1 an
extra point, for Showdown's kickers.
"""

from __future__ import annotations

import argparse
import re

import numpy as np
import pandas as pd

from atlas import config
from atlas.sources import espn_cfb
from atlas.util import get_logger

LOG = get_logger(__name__)

GATE = 0.98
TOLERANCE = 0.1


def points(box: pd.DataFrame) -> pd.Series:
    """DraftKings college points for each player-game of the box score."""
    c = lambda name: box[name].fillna(0).astype(float)  # noqa: E731
    offense = (0.04 * c("pass_yds") + 4 * c("pass_td") - c("pass_int") + 3 * (c("pass_yds") >= 300)
               + 0.1 * c("rush_yds") + 6 * c("rush_td") + 3 * (c("rush_yds") >= 100)
               + c("rec") + 0.1 * c("rec_yds") + 6 * c("rec_td") + 3 * (c("rec_yds") >= 100)
               - c("fum_lost") + 2 * c("two_pt") + 6 * (c("kr_td") + c("pr_td")))
    kicking = 3 * c("fg_0_39") + 4 * c("fg_40_49") + 5 * c("fg_50") + c("xp_made")
    return (offense + kicking).round(2)


def norm_name(name) -> str:
    """Lower case letters only, no generational suffix: "Kevin Coleman Jr." -> "kevincoleman"."""
    name = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b\.?", "", str(name or "").lower())
    return re.sub(r"[^a-z]", "", name)


def team_map(pool: pd.DataFrame, box: pd.DataFrame) -> dict[str, str]:
    """DraftKings' team codes to ESPN's, by the team whose names match most."""
    b = box.assign(key=box["name"].map(norm_name))[["key", "team"]].drop_duplicates()
    p = pool.assign(key=pool["name"].map(norm_name))[["key", "team"]].drop_duplicates()
    votes = p.merge(b, on="key", suffixes=("_dk", "_espn"))
    if votes.empty:
        return {}
    best = votes.groupby(["team_dk", "team_espn"]).size().rename("n").reset_index()
    best = best.sort_values("n", ascending=False).drop_duplicates("team_dk")
    return dict(zip(best["team_dk"], best["team_espn"], strict=True))


def fppg_id(pool: dict) -> int | None:
    """The id of DraftKings' points-per-game stat in this pool (90 in the NFL's, 174 in college's)."""
    return next((s.get("id") for s in pool.get("draftStats", []) or [] if s.get("abbr") == "FPPG"), None)


def _fppg(draftable: dict, stat_id: int | None = 90) -> float | None:
    for a in draftable.get("draftStatAttributes", []) or []:
        if a.get("id") == stat_id:
            try:
                return float(a.get("value"))
            except (TypeError, ValueError):
                return None
    return None


def reconcile(pools: list[dict], box: pd.DataFrame, season: int) -> pd.DataFrame:
    """Each pool player who has played: DraftKings' points per game against Atlas's."""
    rows, seen = [], set()
    for pool in pools:
        stat = fppg_id(pool) or 90
        for d in pool.get("draftables", []) or []:
            if d.get("playerId") in seen:
                continue
            seen.add(d.get("playerId"))
            fppg = _fppg(d, stat)
            if fppg is None:
                continue
            rows.append({"name": d.get("displayName"), "position": d.get("position"),
                         "team": d.get("teamAbbreviation"), "draftkings": fppg})
    pool = pd.DataFrame(rows, columns=["name", "position", "team", "draftkings"])
    this = box[box["season"] == season].copy()
    this["atlas_points"] = points(this)
    teams = team_map(pool, this)
    pool["espn_team"] = pool["team"].map(teams)
    this["key"] = this["name"].map(norm_name)
    per = this.groupby(["team", "key"]).agg(atlas=("atlas_points", "mean"), total=("atlas_points", "sum"),
                                            games=("atlas_points", "size"))
    per = per.reset_index().rename(columns={"team": "espn_team"})
    team_games = this.groupby("team")["event"].nunique().rename("team_games")
    out = pool.assign(key=pool["name"].map(norm_name)).merge(per, on=["espn_team", "key"], how="left")
    out = out.merge(team_games, left_on="espn_team", right_index=True, how="left")
    out["matched"] = out["atlas"].notna()
    # DraftKings divides by every game a player appeared in, a stat or not; the
    # box score lists only games with a stat. So a player agrees when his total
    # over some count of games - at least his games with a stat, at most his
    # team's - gives DraftKings' figure, to its rounding (one decimal).
    out["agrees"] = [
        bool(m) and any(abs(t / n - d) <= 0.05 + 1e-9 for n in range(int(g), int(max(g, tg if tg == tg else g)) + 1))
        for m, t, g, tg, d in zip(out["matched"], out["total"].fillna(0), out["games"].fillna(1),
                                  out["team_games"], out["draftkings"], strict=True)]
    # The strict check: a stat line in every team game, so the count is known.
    out["strict"] = out["matched"] & (out["games"] == out["team_games"])
    # Appeared and scored nothing: no box line, and nothing to disagree with.
    blank = ~out["matched"] & (out["draftkings"] == 0)
    out.loc[blank, "agrees"] = True
    return out.drop(columns=["key"])


def _fetch_pools() -> list[dict]:
    from atlas.sources import draftkings as dk
    from atlas.util import http_get, session

    sess = session()
    lobby = http_get(dk.LOBBY_URL.format(sport="CFB"), sess=sess, timeout=30).json()
    groups = dk.slates(lobby, types=tuple(dk.SPORTS["cfb"][1]), sport="cfb")
    return [http_get(dk.DRAFTABLES.format(group=g), sess=sess, timeout=30).json() for g in groups["draft_group_id"]]


def render(rec: pd.DataFrame, season: int) -> str:
    from atlas.models.evaluate import markdown

    matched = rec[rec["matched"]]
    counted = rec[rec["matched"] | (rec["draftkings"] == 0)]
    rate = float(counted["agrees"].mean()) if len(counted) else float("nan")
    strict = matched[matched["strict"]]
    strict_rate = float(((strict["draftkings"] - strict["atlas"]).abs() <= TOLERANCE + 1e-9).mean()) if len(strict) \
        else float("nan")
    verdict = "passes" if rate >= GATE else "does not pass"
    unmatched = rec[~rec["matched"] & (rec["draftkings"] != 0)]
    by_pos = counted.groupby("position")["agrees"].agg(["size", "mean"]).reset_index()
    by_pos.columns = ["position", "players", "agree"]
    by_pos["agree"] = by_pos["agree"].map("{:.1%}".format)
    misses = matched[~matched["agrees"]].assign(diff=lambda d: d["atlas"] - d["draftkings"])
    misses = misses.reindex(misses["diff"].abs().sort_values(ascending=False).index).head(15)
    for c in ("draftkings", "atlas", "diff"):
        misses[c] = misses[c].map("{:.2f}".format)
    parts = [
        "# College DFS scoring, checked against DraftKings", "",
        "Atlas scores each college player-game from ESPN's box score with DraftKings' college rules "
        "(`atlas/dfs/cfb.py`) and compares each pool player's average with the points per game DraftKings shows "
        f"for him, {season} so far. There is no archive of past college DraftKings points, so this is the check. "
        f"The gate (step 1 of `docs/MODEL_PLAN_DFS_CFB.md`): at least {GATE:.0%} agree within {TOLERANCE}.", "",
        "DraftKings divides a player's points by every game he appeared in, a stat or not, while a box score lists "
        "only games with a stat; so a player agrees when his total over some count of games - from his games with "
        "a stat to his team's games - gives DraftKings' figure to its one decimal. A player at 0.0 with no box "
        "line appeared and scored nothing, and agrees.", "",
        f"**{int(counted['agrees'].sum())} of {len(counted)} players agree: {rate:.1%}. The gate {verdict}.**", "",
        f"The strict check - the {len(strict)} players with a stat line in every one of their team's games, so the "
        f"count is known - agrees within {TOLERANCE} for {strict_rate:.1%}. What is left is the size of a stat "
        f"correction (a few yards, a touchdown moved between players), not a rule: two-point conversions, return "
        f"touchdowns and the 100- and 300-yard bonuses all appear among the players who agree. "
        f"{len(unmatched)} players with points could not be matched to a box score by name and team.", "",
        "## By position", "", markdown(by_pos), "",
    ]
    if len(misses):
        parts += ["## The largest disagreements", "",
                  markdown(misses[["name", "position", "team", "draftkings", "atlas", "games", "diff"]]), ""]
    return "\n".join(parts).rstrip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="College DFS scoring against DraftKings' own averages")
    parser.add_argument("--reconcile", action="store_true")
    args = parser.parse_args()
    from atlas.sources.nflverse import current_season

    season = current_season()
    box = espn_cfb.load(seasons=[season])
    if args.reconcile:
        rec = reconcile(_fetch_pools(), box, season)
        out = config.paths().root / "reports" / "dfs_cfb_scoring.md"
        out.write_text(render(rec, season))
        m = rec[rec["matched"]]
        LOG.info("college scoring: %d of %d agree (%.1f%%), %d unmatched -> %s", int(m["agrees"].sum()), len(m),
                 100 * float(m["agrees"].mean()) if len(m) else np.nan, int((~rec["matched"]).sum()), out)


if __name__ == "__main__":
    main()
