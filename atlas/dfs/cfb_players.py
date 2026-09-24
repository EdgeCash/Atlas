"""College DFS: the player-game table, and the baseline it has to beat.

    python -m atlas.dfs.cfb_players         # writes reports/dfs_cfb_benchmarks.md

Step 2 of `docs/MODEL_PLAN_DFS_CFB.md`. From ESPN's box scores
(`atlas/sources/espn_cfb.py`), one row per player-game with its DraftKings
points (`atlas/dfs/cfb.py`), his position, his shares of his team's
carries, receptions, receiving yards and passes, and point-in-time trends
of all of them - each row's history before its game, carried across
seasons and across a transfer (ESPN's athlete id stays with the player).

**Position.** College box scores carry none, and DraftKings lists tight
ends as receivers, so it is read from the player's season: a kicker kicks
and does little else; a quarterback throws; of the rest, a player who
carries more than he catches is a running back, and anyone else a receiver.
Live, DraftKings' own position is used.

**FBS.** Box scores include the FCS opponents FBS teams play once or twice a
season. A team-season with fewer than six games in the record is FCS; its
players' games still count toward their histories but are not scored.

**The baseline** is the NFL's (`atlas/dfs/benchmarks.py`): a player's recent
DraftKings points, pulled toward his position's average by an amount fitted
on the training seasons, walk-forward. There is no college salary archive,
so it is the only benchmark. Scored on each team's regulars by prior form -
its top quarterback, two running backs, three receivers and kicker.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from atlas import config
from atlas.dfs import benchmarks as bm
from atlas.dfs import cfb
from atlas.sources import espn_cfb
from atlas.util import get_logger, write_parquet

LOG = get_logger(__name__)

POSITIONS = ("QB", "RB", "WR", "K")
DEPTH = {"QB": 1, "RB": 2, "WR": 3, "K": 1}
FBS_GAMES = 6                       # a team-season with fewer games in the record is an FCS opponent
HALFLIFE = 4.0
FIRST_TEST = 2016
TRENDS = ("dk_points", "rush_share", "rec_share", "rec_yds_share", "pass_share", "rush_car", "rec", "pass_att",
          "rec_yds", "rush_yds")


def path() -> Path:
    return config.paths().staging / "cfb" / "dfs_cfb_player_games.parquet"


def positions(box: pd.DataFrame) -> pd.Series:
    """Each player-season's position, from what he did that season."""
    s = box.groupby(["season", "player_id"])[["pass_att", "rush_car", "rec", "fg_att", "xp_att"]].sum()
    s = s[(s > 0).any(axis=1)]
    kicks = s["fg_att"] + s["xp_att"]
    touches = s["pass_att"] + s["rush_car"] + s["rec"]
    pos = np.select(
        [(kicks > 0) & (touches <= 2), (s["pass_att"] >= 5) & (s["pass_att"] >= 0.5 * (s["rush_car"] + s["rec"])),
         s["rush_car"] >= s["rec"]],
        ["K", "QB", "RB"], "WR")
    return pd.Series(pos, index=s.index, name="position")


def games(box: pd.DataFrame) -> pd.DataFrame:
    """The player-game table: points, position, shares and FBS flag, before trends."""
    # Box scores list defenders, punters and returners too; a DraftKings
    # player's game is one where he threw, ran, caught or kicked (or scored on
    # a return).
    active = (box[["pass_att", "rush_car", "rec", "fg_att", "xp_att", "kr_td", "pr_td"]].fillna(0).sum(axis=1) > 0)
    g = box[active].copy()
    g["dk_points"] = cfb.points(g)
    g = g.merge(positions(box).reset_index(), on=["season", "player_id"], how="left")
    team = g.groupby(["event", "team"])[["rush_car", "rec", "rec_yds", "pass_att"]].transform("sum")
    for col, share in (("rush_car", "rush_share"), ("rec", "rec_share"), ("rec_yds", "rec_yds_share"),
                       ("pass_att", "pass_share")):
        g[share] = g[col] / team[col].replace(0, np.nan)
    counts = g.groupby(["season", "team"])["event"].transform("nunique")
    g["fbs"] = counts >= FBS_GAMES
    order = {"regular": 0, "postseason": 1}
    g["order"] = g["season"] * 1000 + g["season_type"].map(order).fillna(0) * 100 + g["week"].clip(upper=99)
    return g


def with_trends(g: pd.DataFrame, *, halflife: float = HALFLIFE) -> pd.DataFrame:
    g = g.sort_values(["player_id", "order"]).copy()
    by = g.groupby("player_id", sort=False)
    g["games_before"] = by.cumcount()
    for col in TRENDS:
        g[f"{col}_trend"] = by[col].transform(lambda s: s.shift(1).ewm(halflife=halflife, ignore_na=True).mean())
    return g.sort_values(["order", "team", "player_id"]).reset_index(drop=True)


def build(raw: Path | None = None) -> pd.DataFrame:
    box = espn_cfb.load(raw)
    table = with_trends(games(box))
    write_parquet(table, path())
    LOG.info("college player-games: %d rows, %d players, seasons %s", len(table), table["player_id"].nunique(),
             sorted(table["season"].unique().tolist()))
    return table


# ---------------------------------------------------------------------------
# The baseline, walk-forward
# ---------------------------------------------------------------------------


def frame(table: pd.DataFrame) -> pd.DataFrame:
    """Scored rows: FBS player-games with a position, the target his DraftKings points."""
    f = table[table["fbs"] & table["position"].isin(POSITIONS)].copy()
    return f.assign(target=f["dk_points"], dk_salary=np.nan)


def walk_forward(f: pd.DataFrame, *, first_test: int = FIRST_TEST) -> pd.DataFrame:
    parts = []
    for season in sorted(int(s) for s in f["season"].unique()):
        if season < first_test:
            continue
        # The NFL's benchmark fit; with no salaries its salary columns stay empty.
        parts.append(bm.predict(f[f["season"] == season], bm.fit(f[f["season"] < season])))
    return pd.concat(parts, ignore_index=True)


def regulars(scored: pd.DataFrame, pred: str = "baseline") -> pd.DataFrame:
    """Each team's top players at each position that game, by prior form."""
    s = scored.copy()
    s["depth"] = s.groupby(["event", "team", "position"])[pred].rank(ascending=False, method="first")
    return s[s["depth"] <= s["position"].map(DEPTH)]


def render(scored: pd.DataFrame) -> str:
    from atlas.models.evaluate import markdown

    regs = regulars(scored).assign(week=lambda d: d["order"])        # rank within each week's games

    def fmt(t):
        t = t.copy()
        for c in ("mae", "crps", "rank corr"):
            t[c] = t[c].map("{:.3f}".format)
        return t

    seasons = f"{int(scored['season'].min())}-{int(scored['season'].max())}"
    parts = [
        "# College DFS baseline", "",
        "The number the college player model has to beat (`atlas/dfs/cfb_players.py`, step 2 of "
        "`docs/MODEL_PLAN_DFS_CFB.md`): each player's recent DraftKings points, pulled toward his position's "
        "average by an amount fitted on the seasons before, walk-forward. There is no college salary archive, so "
        "it is the only benchmark. Scored on FBS players' games where the player recorded a stat.", "",
        f"## Each team's regulars, {seasons}", "",
        "Its top quarterback, two running backs, three receivers (tight ends included, as DraftKings lists them) "
        "and kicker by prior form.", "",
        markdown(fmt(bm.summarise(regs, ("baseline",), ["position"]))), "",
        "## By season", "", markdown(fmt(bm.summarise(regs, ("baseline",), ["season"]))), "",
        "## Everyone who recorded a stat", "",
        markdown(fmt(bm.summarise(scored.assign(week=scored["order"]), ("baseline",), ["position"]))), "",
    ]
    return "\n".join(parts).rstrip() + "\n"


def main() -> None:
    argparse.ArgumentParser(description="College DFS player-games and the baseline, walk-forward").parse_args()
    table = build()
    scored = walk_forward(frame(table))
    out = config.paths().root / "reports" / "dfs_cfb_benchmarks.md"
    out.write_text(render(scored))
    LOG.info("wrote %s", out)


if __name__ == "__main__":
    main()
