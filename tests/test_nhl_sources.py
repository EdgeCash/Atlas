"""The NHL's raw cache (docs/MODEL_PLAN_NHL.md, step 0): the play-by-play trimmed to shots and time by
strength, the odds archive's two layouts, and ESPN's ids matched to the NHL's games. No network."""

from __future__ import annotations

from datetime import date

import pandas as pd

from atlas.sources import nhl


def _play(order, period, clock, kind, situation="1551", **details):
    return {"eventId": order, "sortOrder": order, "typeDescKey": kind, "timeInPeriod": clock,
            "situationCode": situation, "homeTeamDefendingSide": "right",
            "periodDescriptor": {"number": period, "periodType": {4: "OT", 5: "SO"}.get(period, "REG")},
            "details": details}


def _payload():
    plays = [
        _play(1, 1, "00:00", "period-start"),
        _play(2, 1, "00:10", "faceoff", xCoord=0, yCoord=0, eventOwnerTeamId=1),
        _play(3, 1, "00:12", "shot-on-goal", xCoord=-80, yCoord=5, shotType="wrist", shootingPlayerId=11,
              goalieInNetId=99, eventOwnerTeamId=1),
        _play(4, 1, "00:14", "goal", xCoord=-84, yCoord=2, shotType="tip-in", scoringPlayerId=12, goalieInNetId=99,
              eventOwnerTeamId=1, homeScore=1, awayScore=0),
        _play(5, 1, "05:00", "penalty", typeCode="MIN", duration=2, committedByPlayerId=21, drawnByPlayerId=12,
              eventOwnerTeamId=2),
        _play(6, 1, "05:30", "blocked-shot", situation="1451", xCoord=-60, yCoord=0, shootingPlayerId=13,
              blockingPlayerId=22, eventOwnerTeamId=1),
        _play(7, 1, "07:00", "missed-shot", xCoord=40, yCoord=10, shotType="slap", shootingPlayerId=23,
              eventOwnerTeamId=2),
        _play(8, 1, "20:00", "period-end"),
        _play(9, 4, "00:00", "period-start", situation="1331"),
        _play(10, 4, "01:00", "goal", situation="1331", xCoord=80, yCoord=0, shotType="snap", scoringPlayerId=24,
              goalieInNetId=98, eventOwnerTeamId=2, homeScore=1, awayScore=1),
        _play(11, 5, "00:00", "shot-on-goal", situation="0101", xCoord=80, yCoord=0, eventOwnerTeamId=1),
    ]
    return {"id": 2025020001, "gameType": 2, "plays": plays,
            "rosterSpots": [{"playerId": 11, "teamId": 1, "positionCode": "C", "firstName": {"default": "A"},
                             "lastName": {"default": "Skater"}}]}


def test_the_play_by_play_is_trimmed_to_shots_penalties_and_time_by_strength():
    shots, strength, spots = nhl.trim(_payload(), 2025)
    s = pd.DataFrame(shots)
    assert s["event"].tolist() == ["shot-on-goal", "goal", "penalty", "blocked-shot", "missed-shot", "goal"]
    goal = s.iloc[1]
    assert goal["shooter_id"] == 12 and goal["seconds"] == 14 and goal["home_score"] == 0     # the score before it
    assert goal["prev_event"] == "shot-on-goal" and goal["prev_seconds"] == 12                  # a rebound
    assert s.iloc[2][["penalty_type", "penalty_minutes", "shooter_id", "drawn_by_id"]].tolist() == ["MIN", 2, 21, 12]
    assert s.iloc[3]["blocker_id"] == 22 and s.iloc[3]["shooter_id"] == 13
    assert s.iloc[5]["seconds"] == 3660 and s.iloc[5]["home_score"] == 1                       # overtime's clock
    by = {r["situation"]: r["seconds"] for r in strength}
    # 5-on-5 until the power play shows at 5:30, 4-on-5 until 5-on-5 shows again at 7:00, then 3-on-3.
    assert by == {"1551": 330 + 780, "1451": 90, "1331": 60}
    assert spots == [{"season": 2025, "player_id": 11, "name": "A Skater", "position": "C", "team_id": 1}]


def test_the_shootout_is_not_play():
    shots, _, _ = nhl.trim(_payload(), 2025)
    assert all(r["period"] < 5 for r in shots)


def _row(*cells):
    return "<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>"


def test_the_odds_archive_reads_both_layouts():
    narrow = ("<table>" + _row("Date", "Rot", "VH", "Team", "1st", "2nd", "3rd", "Final", "Open", "Close", "OpenOU",
                               "CloseOU")
              + _row("1007", "1", "V", "Carolina", "1", "3", "0", "4", "-105", "100", "5.5", "105", "5.5", "110")
              + _row("1007", "2", "H", "Minnesota", "0", "1", "2", "3", "-115", "-120", "5.5", "-125", "5.5", "-130")
              + _row("0102", "3", "V", "Phoenix", "1", "0", "0", "1", "pk", "105", "5", "-110", "5.5", "100")
              + _row("0102", "4", "H", "NY Rangers", "0", "0", "2", "2", "-120", "-125", "5", "-110", "5.5", "-120")
              + "</table>")
    games = nhl.parse_odds(narrow, 2010)
    assert games[["date", "away", "home"]].values.tolist() == [["2010-10-07", "CAR", "MIN"],
                                                               ["2011-01-02", "PHX", "NYR"]]
    first = games.iloc[0]
    assert first["home_ml_close"] == -120 and first["away_ml_close"] == 100 and pd.isna(first["home_pl"])
    assert first["total_close"] == 5.5 and first["over_close"] == 110 and first["under_close"] == -130
    assert games.iloc[1]["away_ml_open"] == 100                                               # pick'em is even
    wide = ("<table>" + _row("1012", "1", "V", "Pittsburgh", "0", "2", "4", "6", "120", "220", "1.5", "-120", "6",
                             "-120", "5.5", "-130")
            + _row("1012", "2", "H", "TampaBay", "0", "0", "2", "2", "-140", "-250", "-1.5", "100", "6", "100", "5.5",
                   "110") + "</table>")
    g = nhl.parse_odds(wide, 2021).iloc[0]
    assert (g["home"], g["away"], g["home_final"], g["away_final"]) == ("TBL", "PIT", 2, 6)
    assert (g["home_pl"], g["home_pl_price"], g["away_pl_price"]) == (-1.5, 100, -120)
    assert (g["total_open"], g["total_close"], g["over_close"], g["under_close"]) == (6, 5.5, -130, 110)
    assert nhl.odds_slug(2020) == "2021" and nhl.odds_slug(2021) == "2021-22"


def test_espn_ids_are_matched_by_date_and_teams_through_relocations():
    teams = pd.DataFrame({"team_id": [53, 14, 26, 59], "code": ["ARI", "TBL", "LAK", "UTA"],
                          "name": ["Arizona Coyotes", "Tampa Bay Lightning", "Los Angeles Kings", "Utah Hockey Club"]})
    games = pd.DataFrame({"game_id": [1, 2], "date": ["2024-01-05", "2024-01-06"], "home_id": [14, 26],
                          "away_id": [53, 59], "state": [7, 7]})
    events = pd.DataFrame([
        {"espn_id": 401, "espn_date": "2024-01-05", "start": "x", "home": "TBL", "away": "UTA"},    # ARI then, UTA now
        {"espn_id": 402, "espn_date": "2024-01-07", "start": "x", "home": "LAK", "away": "UTA"},    # a late game
        {"espn_id": 403, "espn_date": "2024-01-07", "start": "x", "home": "LAK", "away": "TBL"},    # not the NHL's
    ])
    out = nhl.match_espn(games, teams, events).set_index("espn_id")["game_id"]
    assert out[401] == 1 and out[402] == 2 and pd.isna(out[403])
    assert nhl.ESPN_CODES["NJ"] == "NJD" and nhl.franchise("ATL") == "WPG" and nhl.franchise("PHX") == "UTA"


def test_seasons_and_month_windows():
    assert nhl.season_id(2025) == "20252026"
    assert nhl.current_season(date(2026, 9, 30)) == 2026 and nhl.current_season(date(2027, 4, 1)) == 2026
    windows = nhl.months(2025)
    assert windows[0] == ("2025-09-01", "2025-10-01") and windows[3] == ("2025-12-01", "2026-01-01")
    assert windows[-1] == ("2026-07-01", "2026-08-01")
