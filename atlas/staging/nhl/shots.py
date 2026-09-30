"""Every shot attempt with its geometry and state, and the team-game totals built from them.

The play-by-play's coordinates are the rink's, not the shooter's: which net a
team attacks changes by period. From 2019-20 or so the feed says which end the
home side defends; before it, the side is read from where the team's own
attempts cluster in that period (nearly every attempt is taken in the
attacking half). The net is at x = +/-89, y = 0.

Features, all knowable at the moment of the shot:

* ``distance`` and ``angle`` (degrees off the goal line's normal; over 90 is
  behind the net);
* ``shot_type`` as recorded (a blocked attempt's type is often missing);
* ``rebound``: the team's own attempt within three seconds before;
* ``rush``: the event before it, within four seconds, was outside the
  attacking zone;
* ``strength`` from the shooter's side: ``5v5``, ``PP``, ``SH``, ``EV``
  (other even strength: 4v4, 3v3), ``EN`` (the net it shoots at is empty) and
  ``ENA`` (its own goalie pulled, the net it shoots at is not);
* ``score_diff`` from the shooter's side, before the shot.

A blocked attempt's owner has been the blocking team in some seasons and the
shooting team in others, so the shooting team is always the shooter's team in
that game, from the game logs.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

NET_X = 89.0
BLUE_LINE = 25.0
SHOT_EVENTS = ("goal", "shot-on-goal", "missed-shot", "blocked-shot")
UNBLOCKED = ("goal", "shot-on-goal", "missed-shot")
REBOUND_SECONDS = 3
RUSH_SECONDS = 4

#: The strength categories, from the shooting side.
STRENGTHS = ("5v5", "PP", "SH", "EV", "EN", "ENA")


def rosters(skaters: pd.DataFrame, goalies: pd.DataFrame, code: dict[str, str]) -> pd.DataFrame:
    """Each player's team in each game, by franchise code: (game_id, player_id) -> team."""
    parts = [f[["game_id", "player_id", "team"]] for f in (skaters, goalies) if len(f)]
    if not parts:
        return pd.DataFrame(columns=["game_id", "player_id", "team"])
    r = pd.concat(parts, ignore_index=True).dropna()
    r["team"] = r["team"].map(lambda c: code.get(c, c))
    return r.drop_duplicates(["game_id", "player_id"])


def situation(code: pd.Series) -> pd.DataFrame:
    """The four digits of a situation code: away goalie in net, away skaters, home skaters, home goalie."""
    s = code.astype("string").str.zfill(4)
    return pd.DataFrame({"away_g": pd.to_numeric(s.str[0], errors="coerce"),
                         "away_sk": pd.to_numeric(s.str[1], errors="coerce"),
                         "home_sk": pd.to_numeric(s.str[2], errors="coerce"),
                         "home_g": pd.to_numeric(s.str[3], errors="coerce")}, index=code.index)


def strength(own_sk, opp_sk, own_g, opp_g) -> np.ndarray:
    """The state from the shooting side. Skater counts exclude the goalie; a pulled goalie adds a skater."""
    own_sk, opp_sk = np.asarray(own_sk, dtype=float), np.asarray(opp_sk, dtype=float)
    own_g, opp_g = np.asarray(own_g, dtype=float), np.asarray(opp_g, dtype=float)
    out = np.full(own_sk.shape, "EV", dtype=object)
    # Skaters net of the extra attacker: a side with its goalie pulled counts one skater fewer here.
    own_eff = own_sk - (own_g == 0)
    opp_eff = opp_sk - (opp_g == 0)
    out[own_eff > opp_eff] = "PP"
    out[own_eff < opp_eff] = "SH"
    out[(own_eff == opp_eff) & (own_sk == 5) & (opp_sk == 5)] = "5v5"
    out[(own_g == 0) & (opp_g == 1)] = "ENA"
    out[opp_g == 0] = "EN"
    return out


def attacking_side(shots: pd.DataFrame, home_team: pd.Series) -> pd.Series:
    """+1 when the shooting team attacks the net at x = +89, -1 at x = -89."""
    home = shots["shooting_team"] == home_team
    defends = shots["home_defends"].astype("string").str.lower()
    # The home side attacks the end it does not defend; the away side the end the home side defends.
    from_feed = pd.Series(np.nan, index=shots.index)
    from_feed[defends == "right"] = np.where(home[defends == "right"], -1.0, 1.0)
    from_feed[defends == "left"] = np.where(home[defends == "left"], 1.0, -1.0)
    # Else where the team's attempts cluster that period, away from centre ice.
    x = pd.to_numeric(shots["x"], errors="coerce")
    far = x.where(x.abs() > BLUE_LINE)
    cluster = far.groupby([shots["game_id"], shots["period"], shots["shooting_team"]]).transform("median")
    inferred = np.sign(cluster)
    return from_feed.fillna(inferred).fillna(np.sign(x)).replace(0, 1.0)


def features(shots: pd.DataFrame, games: pd.DataFrame, roster: pd.DataFrame, code: dict[int, str]) -> pd.DataFrame:
    """Shot attempts with the shooting team, geometry, state and outcome. ``games`` is the staged games
    table (home and away by franchise code); ``code`` maps the NHL's team id to that code."""
    s = shots[shots["event"].isin(SHOT_EVENTS) & (shots["period_type"] != "SO")].copy()
    g = games.set_index("game_id")
    s["home_team"] = s["game_id"].map(g["home_team"])
    s["away_team"] = s["game_id"].map(g["away_team"])
    s = s.merge(roster.rename(columns={"player_id": "shooter_id", "team": "shooting_team"}),
                on=["game_id", "shooter_id"], how="left")
    # A shooter the logs do not have (rare): the event's owner.
    s["shooting_team"] = s["shooting_team"].fillna(s["team_id"].map(code))
    s = s[s["shooting_team"].notna() & ((s["shooting_team"] == s["home_team"]) | (s["shooting_team"] == s["away_team"]))]
    s["is_home"] = s["shooting_team"] == s["home_team"]
    side = attacking_side(s, s["home_team"])
    x = pd.to_numeric(s["x"], errors="coerce")
    y = pd.to_numeric(s["y"], errors="coerce")
    depth = NET_X - x * side                 # distance out from the goal line; negative behind the net
    s["distance"] = np.hypot(depth, y)
    s["angle"] = np.degrees(np.arctan2(y.abs(), depth))
    px = pd.to_numeric(s["prev_x"], errors="coerce")
    gap = pd.to_numeric(s["seconds"], errors="coerce") - pd.to_numeric(s["prev_seconds"], errors="coerce")
    prev_attempt = s["prev_event"].isin(SHOT_EVENTS)
    s["rebound"] = prev_attempt & (gap <= REBOUND_SECONDS) & (gap >= 0) & (s["prev_team_id"].map(code)
                                                                             == s["shooting_team"])
    # The event before was outside the attacking zone: farther from the goal line than the blue line is.
    s["rush"] = (gap <= RUSH_SECONDS) & (gap >= 0) & ((NET_X - px * side) > NET_X - BLUE_LINE)
    st = situation(s["situation"])
    own_sk = np.where(s["is_home"], st["home_sk"], st["away_sk"])
    opp_sk = np.where(s["is_home"], st["away_sk"], st["home_sk"])
    own_g = np.where(s["is_home"], st["home_g"], st["away_g"])
    opp_g = np.where(s["is_home"], st["away_g"], st["home_g"])
    s["strength"] = strength(own_sk, opp_sk, own_g, opp_g)
    s["score_diff"] = np.where(s["is_home"], s["home_score"] - s["away_score"], s["away_score"] - s["home_score"])
    s["goal"] = s["event"] == "goal"
    s["unblocked"] = s["event"].isin(UNBLOCKED)
    s["on_target"] = s["event"].isin(("goal", "shot-on-goal"))
    s["defending_team"] = np.where(s["is_home"], s["away_team"], s["home_team"])
    keep = ["game_id", "season", "event_id", "period", "seconds", "event", "shooting_team", "defending_team",
            "is_home", "shooter_id", "goalie_id", "shot_type", "distance", "angle", "rebound", "rush", "strength",
            "score_diff", "goal", "unblocked", "on_target"]
    return s[keep].reset_index(drop=True)


# ---------------------------------------------------------------------------
# Time on ice by strength, per team-game
# ---------------------------------------------------------------------------


def toi(strength_rows: pd.DataFrame, games: pd.DataFrame) -> pd.DataFrame:
    """Seconds per team-game in each state from that team's side: (game_id, team) x STRENGTHS."""
    if strength_rows.empty:
        return pd.DataFrame(columns=["game_id", "team", *[f"toi_{k}" for k in STRENGTHS]])
    st = situation(strength_rows["situation"])
    g = games.set_index("game_id")
    parts = []
    for home in (True, False):
        own_sk = st["home_sk"] if home else st["away_sk"]
        opp_sk = st["away_sk"] if home else st["home_sk"]
        own_g = st["home_g"] if home else st["away_g"]
        opp_g = st["away_g"] if home else st["home_g"]
        team = strength_rows["game_id"].map(g["home_team" if home else "away_team"])
        parts.append(pd.DataFrame({"game_id": strength_rows["game_id"], "team": team,
                                   "strength": strength(own_sk, opp_sk, own_g, opp_g),
                                   "seconds": strength_rows["seconds"]}))
    long = pd.concat(parts, ignore_index=True).dropna(subset=["team"])
    wide = long.pivot_table(index=["game_id", "team"], columns="strength", values="seconds", aggfunc="sum",
                            fill_value=0)
    wide = wide.reindex(columns=list(STRENGTHS), fill_value=0)
    wide.columns = [f"toi_{c}" for c in wide.columns]
    return wide.reset_index()
