"""DraftKings NFL Classic scoring, from nflverse stats and play-by-play.

Every rule here is checked against DraftKings' own recorded points for
2014-2021 (RotoGuru's archive) by :mod:`atlas.dfs.reconcile`; the plan's
gate is agreement to within 0.1 on at least 99% of player-weeks. A rule the
record disagrees with is wrong here, not there.

Offense (a player's week):
    passing yards 0.04 a yard, +3 at 300; passing TD +4; interception -1;
    rushing and receiving yards 0.1 a yard, +3 at 100 each; rushing or
    receiving TD +6; reception +1; return TD +6; fumble lost -1 (any fumble,
    a return included); two-point conversion +2; offensive fumble-recovery
    TD +6.

Defense and special teams (a team's game):
    sack +1; interception +2; fumble recovery +2; return or defensive TD +6;
    safety +2; blocked kick (punt, field goal or extra point) +2; two-point
    or extra-point return +2; and a points-allowed band. Points allowed count
    only points scored while the defense or special teams were on the field:
    a pick-six or fumble return against the team's own offense comes off at
    6 points, a safety it concedes at 2 - both measured against the record.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

#: The four offensive positions a Classic lineup uses (a fullback plays RB).
OFFENSE = ("QB", "RB", "WR", "TE")
POSITION = {"FB": "RB", "HB": "RB"}

#: Points-allowed bands: (upper bound inclusive, points).
POINTS_ALLOWED = ((0, 10), (6, 7), (13, 4), (20, 1), (27, 0), (34, -1))
POINTS_ALLOWED_OVER = -4


def _col(frame: pd.DataFrame, name: str) -> pd.Series:
    return frame[name].fillna(0).astype(float) if name in frame else pd.Series(0.0, index=frame.index)


def offense_points(stats: pd.DataFrame) -> pd.Series:
    """DraftKings points for each row of nflverse's weekly player stats."""
    c = lambda name: _col(stats, name)  # noqa: E731
    fumbles = c("fumbles_lost_total") if "fumbles_lost_total" in stats else (
        c("rushing_fumbles_lost") + c("receiving_fumbles_lost") + c("sack_fumbles_lost"))
    return (
        0.04 * c("passing_yards") + 4 * c("passing_tds") - c("passing_interceptions") + 3 * (c("passing_yards") >= 300)
        + 0.1 * c("rushing_yards") + 6 * c("rushing_tds") + 3 * (c("rushing_yards") >= 100)
        + c("receptions") + 0.1 * c("receiving_yards") + 6 * c("receiving_tds") + 3 * (c("receiving_yards") >= 100)
        + 6 * c("special_teams_tds") - fumbles
        + 2 * (c("passing_2pt_conversions") + c("rushing_2pt_conversions") + c("receiving_2pt_conversions"))
        + 6 * c("fumble_recovery_tds")
    ).round(2)


def kicker_points(stats: pd.DataFrame) -> pd.Series:
    """DraftKings points for a kicker's game (Showdown; Classic has no kicker).

    A field goal of 0-39 yards is 3, 40-49 is 4, 50 or more is 5; an extra
    point is 1; a miss costs nothing. Checked against DraftKings' own
    points-per-game for the 2026 kickers in its Showdown pools
    (`atlas/dfs/kicker.py`, `reports/dfs_kickers.md`)."""
    c = lambda name: stats[name].fillna(0).astype(float) if name in stats else pd.Series(0.0, index=stats.index)  # noqa: E731
    short = c("fg_made_0_19") + c("fg_made_20_29") + c("fg_made_30_39")
    return (3 * short + 4 * c("fg_made_40_49") + 5 * (c("fg_made_50_59") + c("fg_made_60_")) + c("pat_made")).round(2)


def points_allowed_score(points_allowed: pd.Series) -> pd.Series:
    pa = points_allowed.astype(float)
    conditions = [pa <= bound for bound, _ in POINTS_ALLOWED]
    return pd.Series(np.select(conditions, [pts for _, pts in POINTS_ALLOWED], POINTS_ALLOWED_OVER), index=pa.index)


def dst_events(pbp: pd.DataFrame) -> pd.DataFrame:
    """Each team's defensive and special-teams events per game, from play-by-play.

    One row per (game_id, team). ``allowed`` is the opponent's points scored
    while this team's defense or special teams were on the field: the
    opponent's final score less its touchdowns (and their tries) scored on
    this team's offensive plays.
    """
    p = pbp.copy()
    flag = lambda name: p[name].fillna(0).astype(float) == 1 if name in p else pd.Series(False, index=p.index)  # noqa: E731
    games = p.groupby("game_id").agg(season=("season", "first"), week=("week", "first"),
                                     season_type=("season_type", "first"),
                                     home=("home_team", "first"), away=("away_team", "first"),
                                     home_score=("total_home_score", "max"), away_score=("total_away_score", "max"))
    rows = []
    for side, other in (("home", "away"), ("away", "home")):
        g = games.rename(columns={side: "team", other: "opponent"})
        g["opp_score"] = games[f"{other}_score"]
        rows.append(g[["season", "week", "season_type", "team", "opponent", "opp_score"]].reset_index())
    teams = pd.concat(rows, ignore_index=True)

    td_team = p["td_team"] if "td_team" in p else pd.Series(None, index=p.index)
    recovered_by = p["fumble_recovery_1_team"] if "fumble_recovery_1_team" in p else pd.Series(None, index=p.index)
    events = {
        "sacks": p[flag("sack")].groupby(["game_id", "defteam"]).size(),
        "interceptions": p[flag("interception")].groupby(["game_id", "defteam"]).size(),
        # A lost fumble recovered by the team: its defense, or its kicking unit on a muffed return.
        "fumble_recoveries": p[flag("fumble_lost") & recovered_by.notna()]
        .groupby(["game_id", recovered_by[flag("fumble_lost") & recovered_by.notna()]]).size(),
    }
    # The team's touchdowns that its offense did not score: a defensive or
    # special-teams score on the opponent's play, or the team's own return
    # (on a kickoff or punt the returning team is posteam).
    own_return = flag("return_touchdown") & td_team.notna() & (td_team == p["posteam"])
    not_offense = flag("touchdown") & td_team.notna() & (td_team != p["posteam"])
    scored = own_return | not_offense
    events["tds"] = p[scored].groupby(["game_id", td_team[scored]]).size()
    # The opponent's touchdowns on the team's own passing or running plays (a
    # pick-six, a fumble return): scored against its offense, so not the
    # defense's to allow. A return against its kicking or punting unit is
    # special teams, the DST's, and stays in.
    against_offense = not_offense & p["play_type"].isin(["pass", "run"])
    events["offense_conceded_tds"] = p[against_offense].groupby(["game_id", "posteam"]).size()
    events["safeties"] = p[flag("safety")].groupby(["game_id", "defteam"]).size()
    # A safety taken by the team's own offense: 2 points the opponent scored
    # with the defense off the field.
    events["offense_conceded_safeties"] = p[flag("safety") & p["play_type"].isin(["pass", "run"])] \
        .groupby(["game_id", "posteam"]).size()
    # Punts, field goals and extra points: the record counts all three.
    blocked = flag("punt_blocked") | (p.get("field_goal_result") == "blocked") | (p.get("extra_point_result") == "blocked")
    events["blocked_kicks"] = p[blocked].groupby(["game_id", "defteam"]).size()
    events["conversion_returns"] = p[flag("defensive_two_point_conv") | flag("defensive_extra_point_conv")] \
        .groupby(["game_id", "defteam"]).size()

    out = teams.set_index(["game_id", "team"])
    for name, series in events.items():
        series = series.copy()
        series.index = series.index.set_names(["game_id", "team"])
        out[name] = series.reindex(out.index).fillna(0).astype(int)
    # Each conceded touchdown takes its try with it: 7 on average, but the
    # record says which; points_allowed() tests both.
    return out.reset_index()


def points_allowed(events: pd.DataFrame, *, try_points: int = 6) -> pd.Series:
    """The opponent's points while the defense was on the field."""
    conceded_safeties = events["offense_conceded_safeties"] if "offense_conceded_safeties" in events else 0
    return (events["opp_score"] - try_points * events["offense_conceded_tds"] - 2 * conceded_safeties).clip(lower=0)


def dst_points(events: pd.DataFrame, *, try_points: int = 6) -> pd.Series:
    """DraftKings points for each team-game of :func:`dst_events`."""
    c = lambda name: events[name].astype(float)  # noqa: E731
    return (c("sacks") + 2 * c("interceptions") + 2 * c("fumble_recoveries") + 6 * c("tds") + 2 * c("safeties")
            + 2 * c("blocked_kicks") + 2 * c("conversion_returns")
            + points_allowed_score(points_allowed(events, try_points=try_points))).round(2)
