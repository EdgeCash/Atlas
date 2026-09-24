"""The statistical matchup: how two teams compare, before they meet.

Season-to-date box-score figures for every team, from the play-by-play the
warehouse already holds, with each team's rank - among FBS teams in college,
among the 32 in the NFL. They are computed from completed games only, so for
an upcoming game they are exactly what was knowable before kickoff, the same
rule as every other number on a card.

The card shows them paired, each offence against the defence it is about to
face, which is the question a reader is asking ("how do they match up"),
plus a few situational figures. Raw figures, not opponent-adjusted: the
drivers panel carries Atlas's adjusted view, and a reader comparing these to
the numbers they see elsewhere should find the same numbers.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from atlas import config
from atlas.util import get_logger

LOG = get_logger(__name__)


@dataclass(frozen=True)
class Stat:
    key: str
    label: str
    higher_is_better: bool | None      # None: neither (pace), so no edge and a "most" rank
    kind: str = "num"                  # "num" (one decimal), "pct", "rate" (two decimals)


#: Each offence against the defence it faces: (offence stat, defence stat).
PAIRS: tuple[tuple[Stat, Stat], ...] = (
    (Stat("points_for", "Points per game", True), Stat("points_against", "Points allowed", False)),
    (Stat("yards_per_play", "Yards per play", True, "rate"), Stat("yards_per_play_allowed", "Yards per play allowed", False, "rate")),
    (Stat("rush_yards", "Rushing yards per game", True), Stat("rush_yards_allowed", "Rushing yards allowed", False)),
    (Stat("pass_yards", "Passing yards per game", True), Stat("pass_yards_allowed", "Passing yards allowed", False)),
    (Stat("explosive", "20+ yard plays per game", True), Stat("explosive_allowed", "20+ yard plays allowed", False)),
    (Stat("sacks_allowed", "Sacks allowed per game", False), Stat("sacks", "Sacks per game", True)),
    (Stat("third_down", "Third-down conversions", True, "pct"), Stat("third_down_allowed", "Third downs allowed", False, "pct")),
    (Stat("red_zone", "Red-zone touchdowns", True, "pct"), Stat("red_zone_allowed", "Red-zone touchdowns allowed", False, "pct")),
)

#: The same figure for both teams.
SITUATIONAL: tuple[Stat, ...] = (
    Stat("turnover_margin", "Turnover margin per game", True),
    Stat("plays", "Plays per game", None),
    Stat("penalty_yards", "Penalty yards per game", False),     # NFL only: college play-by-play has no penalty yards
)

#: What a pair row is called on the card: the offence's figure, named plainly.
PAIR_LABELS = {
    "points_for": "Points per game", "yards_per_play": "Yards per play", "rush_yards": "Rushing yards per game",
    "pass_yards": "Passing yards per game", "explosive": "20+ yard plays per game",
    "sacks_allowed": "Sacks per game", "third_down": "Third-down conversion rate", "red_zone": "Red-zone touchdown rate",
}


@dataclass
class TeamLine:
    """One team's figures and ranks (1 = best; for pace, 1 = most plays)."""

    values: dict[str, float] = field(default_factory=dict)
    ranks: dict[str, int] = field(default_factory=dict)
    games: int = 0


@dataclass
class Matchup:
    away: TeamLine
    home: TeamLine
    teams: int                 # how many teams the ranks are among
    universe: str              # "FBS teams" / "NFL teams"
    through: str               # the last date the figures include, for the note


# ---------------------------------------------------------------------------
# Season-to-date tables
# ---------------------------------------------------------------------------


def _finish(off: pd.DataFrame, dfn: pd.DataFrame, points: pd.DataFrame, games: pd.Series) -> pd.DataFrame:
    """Per-game and rate figures from summed counts, one row per team."""
    t = off.join(dfn, how="outer").join(points, how="left").fillna(0.0)
    g = games.reindex(t.index).astype(float)
    t = t[g > 0]
    g = g[g > 0]
    out = pd.DataFrame(index=t.index)
    out["games"] = g
    out["points_for"] = t["pf"] / g
    out["points_against"] = t["pa"] / g
    out["yards_per_play"] = t["o_yards"] / t["o_plays"].replace(0, np.nan)
    out["yards_per_play_allowed"] = t["d_yards"] / t["d_plays"].replace(0, np.nan)
    out["rush_yards"] = t["o_rush"] / g
    out["rush_yards_allowed"] = t["d_rush"] / g
    out["pass_yards"] = t["o_pass"] / g
    out["pass_yards_allowed"] = t["d_pass"] / g
    out["explosive"] = t["o_expl"] / g
    out["explosive_allowed"] = t["d_expl"] / g
    out["sacks_allowed"] = t["o_sacks"] / g
    out["sacks"] = t["d_sacks"] / g
    out["third_down"] = t["o_3conv"] / t["o_3att"].replace(0, np.nan)
    out["third_down_allowed"] = t["d_3conv"] / t["d_3att"].replace(0, np.nan)
    out["red_zone"] = t["o_rztd"] / t["o_rz"].replace(0, np.nan)
    out["red_zone_allowed"] = t["d_rztd"] / t["d_rz"].replace(0, np.nan)
    out["turnover_margin"] = (t["d_take"] - t["o_give"]) / g
    out["plays"] = t["o_plays"] / g
    if "penalty_yds" in t:
        out["penalty_yards"] = t["penalty_yds"] / g
    return out


def _side_sums(plays: pd.DataFrame, drives: pd.DataFrame, team_col: str, prefix: str) -> pd.DataFrame:
    """Counts for one side of the ball: ``team_col`` is posteam (offence) or defteam (defence)."""
    by = plays.groupby(team_col)
    sums = pd.DataFrame({
        f"{prefix}_plays": by.size(),
        f"{prefix}_yards": by["yards_gained"].sum(),
        f"{prefix}_rush": plays[plays["is_rush"]].groupby(team_col)["yards_gained"].sum(),
        f"{prefix}_pass": plays[plays["is_pass"]].groupby(team_col)["yards_gained"].sum(),
        f"{prefix}_expl": plays[plays["yards_gained"] >= 20].groupby(team_col).size(),
        f"{prefix}_sacks": plays[plays["is_sack"]].groupby(team_col).size(),
        f"{prefix}_3att": plays[plays["down"] == 3].groupby(team_col).size(),
        f"{prefix}_3conv": plays[(plays["down"] == 3) & plays["converted"]].groupby(team_col).size(),
    })
    d = drives.groupby(team_col)
    sums[f"{prefix}_rz"] = d["reached_rz"].sum()
    sums[f"{prefix}_rztd"] = drives[drives["reached_rz"]].groupby(team_col)["td"].sum()
    return sums.fillna(0.0)


def _points(results: pd.DataFrame) -> pd.DataFrame:
    """Points for and against per team, from final scores."""
    home = results.rename(columns={"home": "team", "home_pts": "pf", "away_pts": "pa"})[["team", "pf", "pa"]]
    away = results.rename(columns={"away": "team", "away_pts": "pf", "home_pts": "pa"})[["team", "pf", "pa"]]
    return pd.concat([home, away]).groupby("team")[["pf", "pa"]].sum()


def college_table(season: int, raw=None) -> pd.DataFrame:
    """Season-to-date figures for every FBS team, from cfbfastR play-by-play."""
    raw = raw or config.paths().raw
    pbp = pd.read_parquet(raw / "pbp" / f"pbp_{season}.parquet")
    sched = pd.read_parquet(raw / "schedules" / f"schedules_{season}.parquet")
    done = sched[sched["home_points"].notna() & sched["away_points"].notna()].copy()
    fbs = set(done.loc[done["home_division"] == "fbs", "home_team"]) | set(done.loc[done["away_division"] == "fbs", "away_team"])
    pbp = pbp[pbp["game_id"].isin(done["game_id"])]

    scrim = pbp[((pbp["rush"] == 1) | (pbp["pass"] == 1)) & ~pbp["penalty_no_play"].astype(bool)].copy()
    scrim = scrim.rename(columns={"pos_team": "posteam", "def_pos_team": "defteam"})
    scrim["is_sack"] = scrim["sack"] == 1
    # The NCAA's convention, so the figures match what readers see elsewhere:
    # a sack is a rushing play and its yards are rushing yards.
    scrim["is_rush"] = (scrim["rush"] == 1) | scrim["is_sack"]
    scrim["is_pass"] = (scrim["pass"] == 1) & ~scrim["is_sack"]
    scrim["converted"] = scrim["yards_gained"] >= scrim["distance"]

    drives = (pbp.rename(columns={"pos_team": "posteam", "def_pos_team": "defteam"})
                 .dropna(subset=["drive_id"])
                 .groupby("drive_id")
                 .agg(posteam=("posteam", "first"), defteam=("defteam", "first"),
                      reached_rz=("yards_to_goal", lambda y: bool((y <= 20).any())),
                      td=("drive_pts", lambda p: bool((p >= 6).any()))))

    give_plays = pbp[(pbp["int"] == 1) | pbp["play_type"].isin(["Fumble Recovery (Opponent)", "Fumble Return Touchdown"])]
    off = _side_sums(scrim, drives, "posteam", "o")
    dfn = _side_sums(scrim, drives, "defteam", "d")
    off["o_give"] = give_plays.groupby("pos_team").size()
    dfn["d_take"] = give_plays.groupby("def_pos_team").size()

    points = _points(done.rename(columns={"home_team": "home", "away_team": "away",
                                          "home_points": "home_pts", "away_points": "away_pts"}))
    games = pd.concat([done["home_team"], done["away_team"]]).value_counts()
    table = _finish(off, dfn, points, games)
    return table[table.index.isin(fbs)]


def nfl_table(season: int, raw=None) -> pd.DataFrame:
    """Season-to-date figures for every NFL team, from nflverse play-by-play."""
    raw = raw or config.paths().raw
    pbp = pd.read_parquet(raw / "nfl" / f"pbp_{season}.parquet")
    sched = pd.read_parquet(raw / "nfl" / "schedules.parquet")
    done = sched[(sched["season"] == season) & sched["home_score"].notna() & sched["away_score"].notna()]
    pbp = pbp[pbp["game_id"].isin(done["game_id"])]

    scrim = pbp[pbp["play_type"].isin(["run", "pass"]) & (pbp["aborted_play"].fillna(0) == 0)].copy()
    scrim["is_sack"] = scrim["sack"].fillna(0) == 1
    # The NFL's convention: passing yards are net of sack yardage.
    scrim["is_rush"] = scrim["play_type"] == "run"
    scrim["is_pass"] = scrim["play_type"] == "pass"
    scrim["converted"] = scrim["third_down_converted"].fillna(0) == 1

    drives = (pbp.dropna(subset=["fixed_drive", "posteam"])
                 .groupby(["game_id", "fixed_drive"])
                 .agg(posteam=("posteam", "first"), defteam=("defteam", "first"),
                      reached_rz=("yardline_100", lambda y: bool((y <= 20).any())),
                      td=("fixed_drive_result", lambda r: bool((r == "Touchdown").any()))))

    give = pbp[(pbp["interception"].fillna(0) == 1) | (pbp["fumble_lost"].fillna(0) == 1)]
    off = _side_sums(scrim, drives, "posteam", "o")
    dfn = _side_sums(scrim, drives, "defteam", "d")
    off["o_give"] = give.groupby("posteam").size()
    dfn["d_take"] = give.groupby("defteam").size()
    pen = pbp[pbp["penalty"].fillna(0) == 1]
    off["penalty_yds"] = pen.groupby("penalty_team")["penalty_yards"].sum()

    points = _points(done.rename(columns={"home_team": "home", "away_team": "away",
                                          "home_score": "home_pts", "away_score": "away_pts"}))
    games = pd.concat([done["home_team"], done["away_team"]]).value_counts()
    return _finish(off, dfn, points, games)


def ranks(table: pd.DataFrame) -> pd.DataFrame:
    """1 = best on every figure (1 = most plays for pace), ties sharing the better rank."""
    stats = {s.key: s for pair in PAIRS for s in pair} | {s.key: s for s in SITUATIONAL}
    out = pd.DataFrame(index=table.index)
    for key, stat in stats.items():
        if key not in table:
            continue
        ascending = stat.higher_is_better is False
        out[key] = table[key].rank(ascending=ascending, method="min")
    return out


# ---------------------------------------------------------------------------
# Onto the cards
# ---------------------------------------------------------------------------


def attach(cards: list, frame: pd.DataFrame, sport: str, *, table: pd.DataFrame | None = None,
           through: str | None = None) -> int:
    """Give every card whose two teams have played this season a :class:`Matchup`.

    ``frame`` is the sport's research frame, the one place a card's ESPN game
    id meets the play-by-play's team names. Returns how many cards got one.
    """
    if not cards:
        return 0
    season = max(c.season for c in cards)
    if table is None:
        table = college_table(season) if sport == "ncaaf" else nfl_table(season)
    if table.empty:
        return 0
    rk = ranks(table)
    universe = "FBS teams" if sport == "ncaaf" else "NFL teams"
    key = "espn_id" if sport == "nfl" else "game_id"
    rows = frame.dropna(subset=[key]).assign(_id=lambda d: d[key].astype("int64")).set_index("_id")
    through = through or _through(sport, season)
    done = 0
    for card in cards:
        if card.game_id not in rows.index:
            continue
        row = rows.loc[card.game_id]
        if isinstance(row, pd.DataFrame):
            row = row.iloc[0]
        lines = []
        for side in ("away", "home"):
            team = row[f"{side}_team"]
            if team not in table.index:
                break
            values = {k: float(v) for k, v in table.loc[team].items() if k != "games" and pd.notna(v)}
            team_ranks = {k: int(v) for k, v in rk.loc[team].items() if pd.notna(v)}
            lines.append(TeamLine(values=values, ranks=team_ranks, games=int(table.loc[team, "games"])))
        if len(lines) == 2:
            card.matchup = Matchup(away=lines[0], home=lines[1], teams=len(table), universe=universe,
                                   through=through)
            done += 1
    LOG.info("matchup: %d of %d %s cards, %d teams ranked", done, len(cards), sport, len(table))
    return done


def _through(sport: str, season: int) -> str:
    """The date of the last completed game the figures include, as the card says it."""
    raw = config.paths().raw
    try:
        if sport == "ncaaf":
            s = pd.read_parquet(raw / "schedules" / f"schedules_{season}.parquet")
            s = s[s["home_points"].notna()]
            last = pd.to_datetime(s["start_date"], utc=True, errors="coerce").max() if "start_date" in s else None
        else:
            s = pd.read_parquet(raw / "nfl" / "schedules.parquet")
            s = s[(s["season"] == season) & s["home_score"].notna()]
            last = pd.to_datetime(s["gameday"], errors="coerce").max()
    except Exception:  # noqa: BLE001 - the note loses its date, nothing else
        return ""
    if last is None or pd.isna(last):
        return ""
    last = pd.Timestamp(last)
    if last.tzinfo is not None:
        last = last.tz_convert("America/New_York")
    return last.strftime("%-d %B")
