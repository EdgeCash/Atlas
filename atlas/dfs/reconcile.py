"""Atlas's DraftKings scoring against DraftKings' own record, 2014-2021.

    python -m atlas.dfs.reconcile           # writes reports/dfs_scoring.md

The gate of step 1 (`docs/MODEL_PLAN_DFS.md`): on at least 99% of the
archive's player-weeks, the points Atlas computes from public stats agree
with the points DraftKings recorded, to within 0.1. A player the archive
lists at 0.00 who recorded no stat at all has no nflverse row; his 0 is
Atlas's 0 too, and counts as agreement.
"""

from __future__ import annotations

import argparse

import pandas as pd

from atlas import config
from atlas.dfs import players
from atlas.sources import rotoguru
from atlas.util import get_logger

LOG = get_logger(__name__)

GATE = 0.99
TOLERANCE = 0.1


def reconcile(raw=None) -> dict:
    raw = raw or config.paths().raw
    seasons = list(rotoguru.SEASONS)
    arch = players.archive(raw)
    games = players.offense_games(raw, seasons)
    off = players.match_archive(arch, games)
    off["diff"] = off["dk_computed"] - off["dk_points"]
    matched = off["player_id"].notna()
    off["agrees"] = (matched & (off["diff"].abs() <= TOLERANCE + 1e-9)) | (~matched & (off["dk_points"] == 0))

    dst = players.dst_games(raw, seasons)
    d = arch[arch["position"] == "Def"].merge(dst[["season", "week", "team", "dk_points"]].rename(
        columns={"dk_points": "dk_computed"}), left_on=["season", "week", "team_n"], right_on=["season", "week", "team"],
        how="left")
    d["diff"] = d["dk_computed"] - d["dk_points"]
    d["agrees"] = d["diff"].abs() <= TOLERANCE + 1e-9

    total = len(off) + len(d)
    agree = int(off["agrees"].sum() + d["agrees"].sum())
    return {"offense": off, "dst": d, "rate": agree / total, "total": total, "agree": agree}


def render(r: dict) -> str:
    from atlas.models.evaluate import markdown

    off, d = r["offense"], r["dst"]
    by_pos = pd.concat([off[["position", "agrees"]], d.assign(position="DST")[["position", "agrees"]]]) \
        .groupby("position")["agrees"].agg(["size", "mean"]).reset_index()
    by_pos = by_pos.rename(columns={"size": "player-weeks", "mean": "agree"})
    by_pos["agree"] = by_pos["agree"].map("{:.2%}".format)
    stages = off["stage"].value_counts().rename_axis("matched by").reset_index(name="player-weeks")
    stages["share"] = (stages["player-weeks"] / len(off)).map("{:.2%}".format)
    misses = pd.concat([off.loc[~off["agrees"] & off["player_id"].notna(), "diff"],
                        d.loc[~d["agrees"], "diff"]]).round(1).value_counts().head(10) \
        .rename_axis("computed minus recorded").reset_index(name="player-weeks")
    misses["computed minus recorded"] = misses["computed minus recorded"].map("{:+.1f}".format)
    unmatched_scoring = int(((off["player_id"].isna()) & (off["dk_points"] != 0)).sum())
    verdict = "passes" if r["rate"] >= GATE else "does not pass"
    by_points = off["stage"] == "points"
    strict = (r["agree"] - int(off.loc[by_points, "agrees"].sum())) / (r["total"] - int(by_points.sum()))
    parts = [
        "# DraftKings scoring, reconciled", "",
        f"Atlas computes DraftKings NFL Classic points from nflverse's public stats and play-by-play "
        f"(`atlas/dfs/scoring.py`) and checks them against the points DraftKings recorded, from RotoGuru's archive, "
        f"2014-2021 regular season. The gate of step 1 of `docs/MODEL_PLAN_DFS.md` is agreement to within "
        f"{TOLERANCE} on at least {GATE:.0%} of player-weeks.", "",
        f"**{r['agree']:,} of {r['total']:,} player-weeks agree: {r['rate']:.2%}. The gate {verdict}.**", "",
        f"The last matching stage finds a player by identical points, so its {int(by_points.sum())} rows agree by "
        f"construction. Leaving them out entirely, agreement is {strict:.2%}.", "",
        "## By position", "", markdown(by_pos), "",
        "Defenses are scored from play-by-play: sacks, takeaways, touchdowns, safeties, blocked kicks and points "
        "allowed. Three of DraftKings' rules were settled by the record rather than assumed: a blocked extra point "
        "counts as a blocked kick; points allowed leave out a touchdown scored against the team's own offense "
        "(a pick-six, at 6 points, not 7) and a safety its offense concedes. What still differs is mostly single "
        "sacks and recoveries, where DraftKings' stat corrections and the public play-by-play disagree.", "",
        "## How archive players were matched", "",
        "By the same name on the same team that week (position separating two teammates of one name); then by last "
        "name at the same position; then by identical points at the same position, which finds a player who changed "
        "his name. Unmatched players are the archive's rostered players who recorded no stat (0.00 on both sides) "
        f"- all but {unmatched_scoring} of them.", "", markdown(stages), "",
        "## Where computed and recorded points differ", "", markdown(misses), "",
    ]
    return "\n".join(parts).rstrip() + "\n"


def main() -> None:
    argparse.ArgumentParser(description="Reconcile Atlas's DraftKings scoring with DraftKings' record").parse_args()
    r = reconcile()
    out = config.paths().root / "reports" / "dfs_scoring.md"
    out.write_text(render(r))
    LOG.info("dfs scoring: %d of %d agree (%.2f%%) -> %s", r["agree"], r["total"], 100 * r["rate"], out)


if __name__ == "__main__":
    main()
