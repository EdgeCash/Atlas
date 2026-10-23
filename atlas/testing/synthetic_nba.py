"""A tiny synthetic NBA raw tree for tests: hoopR's layout, no network, deterministic.

Eight franchises, a handful of weeks a season, the schedule and box scores
with the columns the NBA staging reads and nothing else, and the odds
archive's parsed table for every season but the last. Team strengths drive
the scores so the state has something real to recover.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from atlas.sources import nba

#: Eight current abbreviations and ESPN-like ids; a Seattle season exercises the franchise move.
TEAMS = [("BOS", 2), ("LAL", 13), ("GS", 9), ("OKC", 25), ("MIA", 14), ("DEN", 7), ("NY", 18), ("MIL", 15)]
NAMES = {"BOS": "Boston Celtics", "LAL": "Los Angeles Lakers", "GS": "Golden State Warriors",
         "OKC": "Oklahoma City Thunder", "SEA": "Seattle SuperSonics", "MIA": "Miami Heat", "DEN": "Denver Nuggets",
         "NY": "New York Knicks", "MIL": "Milwaukee Bucks"}
WEEKS = 8
GAMES_PER_WEEK = 2


def _abbr(code: str, season: int, first: int) -> str:
    return "SEA" if (code == "OKC" and season == first) else code


def write_synthetic_nba_raw(raw: Path, seasons: list[int], *, seed: int = 11) -> Path:
    rng = np.random.default_rng(seed)
    root = nba.nba_dir(raw)
    root.mkdir(parents=True, exist_ok=True)
    strength = {code: s for (code, _), s in zip(TEAMS, rng.normal(0, 5, len(TEAMS)), strict=True)}
    first, last = min(seasons), max(seasons)
    ids = dict(TEAMS)
    #: Six players a team: two starters who play a lot, two who play some, two reserves; one sits some nights.
    roster = {code: [(ids[code] * 100 + j, f"{code} Player {j}", "GFC"[j % 3], 34.0 - 4.5 * j) for j in range(6)]
              for code, _ in TEAMS}
    for season in seasons:
        sched, box, pbox, odds = [], [], [], []
        start = pd.Timestamp(f"{season}-10-22T23:30Z")
        gid = int(f"{season % 100}1000000")
        for week in range(1, WEEKS + 1):
            for night in range(GAMES_PER_WEEK):
                order = rng.permutation(len(TEAMS))
                tip = start + pd.Timedelta(days=7 * (week - 1) + 3 * night)
                for k in range(0, len(TEAMS), 2):
                    home, away = TEAMS[order[k]][0], TEAMS[order[k + 1]][0]
                    gid += 1
                    played = not (season == last and week == WEEKS)          # the last week is still to play
                    margin = strength[home] - strength[away] + 2.5 + rng.normal(0, 12)
                    total = 224 + rng.normal(0, 18)
                    hs, as_ = int(round((total + margin) / 2)), int(round((total - margin) / 2))
                    if hs == as_:
                        hs += 1
                    ha, aa = _abbr(home, season, first), _abbr(away, season, first)
                    sched.append({"id": gid, "date": tip.strftime("%Y-%m-%dT%H:%MZ"), "season": season + 1,
                                  "season_type": 2 if week < WEEKS else 3, "type_abbreviation": "STD",
                                  "status_type_name": "STATUS_FINAL" if played else "STATUS_SCHEDULED",
                                  "status_type_completed": played, "neutral_site": False,
                                  "home_id": ids[home], "home_abbreviation": ha, "home_display_name": NAMES[ha],
                                  "home_score": hs if played else None, "away_id": ids[away], "away_abbreviation": aa,
                                  "away_display_name": NAMES[aa], "away_score": as_ if played else None})
                    if played:
                        for team, abbr, pts, side in ((home, ha, hs, "home"), (away, aa, as_, "away")):
                            opp = away if side == "home" else home
                            for pid, name, pos, base_min in roster[team]:
                                dnp = rng.random() < 0.08
                                mins = 0.0 if dnp else max(4.0, base_min + rng.normal(0, 4))
                                rate = 0.55 + 0.1 * (strength[team] / 5.0)
                                pbox.append({"game_id": gid, "season": season + 1, "season_type": 2 if week < WEEKS else 3,
                                             "game_date": tip.strftime("%Y-%m-%d"), "athlete_id": pid,
                                             "athlete_display_name": name, "athlete_position_abbreviation": pos,
                                             "team_id": ids[team], "team_abbreviation": abbr,
                                             "opponent_team_id": ids[opp], "home_away": side,
                                             "minutes": round(mins), "points": 0 if dnp else rng.poisson(rate * mins),
                                             "rebounds": 0 if dnp else rng.poisson(0.2 * mins),
                                             "assists": 0 if dnp else rng.poisson(0.12 * mins),
                                             "three_point_field_goals_made": 0 if dnp else rng.poisson(0.05 * mins),
                                             "steals": 0 if dnp else rng.poisson(0.03 * mins),
                                             "blocks": 0 if dnp else rng.poisson(0.02 * mins),
                                             "field_goals_attempted": 0 if dnp else rng.poisson(0.4 * mins),
                                             "free_throws_attempted": 0 if dnp else rng.poisson(0.1 * mins),
                                             "turnovers": 0 if dnp else rng.poisson(0.06 * mins),
                                             "starter": pid % 100 < 2, "did_not_play": dnp, "active": not dnp})
                            box.append({"game_id": gid, "season": season + 1, "team_id": ids[team],
                                        "team_abbreviation": abbr, "team_home_away": side, "team_score": pts,
                                        "opponent_team_id": ids[away if side == "home" else home],
                                        "field_goals_attempted": 88, "free_throws_attempted": 22,
                                        "offensive_rebounds": 10, "total_turnovers": 14, "assists": 25,
                                        "three_point_field_goals_attempted": 35})
                    if season < last:
                        line = round((strength[home] - strength[away] + 2.5) * 2) / 2
                        odds.append({"season": season, "date": tip.tz_convert("America/New_York").strftime("%Y-%m-%d"),
                                     "away": aa, "home": ha, "away_final": float(as_), "home_final": float(hs),
                                     "opening_spread": -line, "opening_total": 224.5, "closing_spread": -line,
                                     "closing_total": 225.5, "away_ml_close": 120.0, "home_ml_close": -140.0})
        # An All-Star game rides along in the schedule, as it does upstream, and must be dropped.
        sched.append({"id": gid + 1, "date": f"{season + 1}-02-15T01:00Z", "season": season + 1, "season_type": 2,
                      "type_abbreviation": "ALLSTAR", "status_type_name": "STATUS_FINAL", "status_type_completed": True,
                      "neutral_site": True, "home_id": 999, "home_abbreviation": "EAST", "home_display_name": "East",
                      "home_score": 180, "away_id": 998, "away_abbreviation": "WEST", "away_display_name": "West",
                      "away_score": 175})
        pd.DataFrame(sched).to_parquet(nba.path(raw, "schedule", season), index=False)
        pd.DataFrame(box).to_parquet(nba.path(raw, "team_box", season), index=False)
        pd.DataFrame(pbox).to_parquet(nba.path(raw, "player_box", season), index=False)
        if odds:
            pd.DataFrame(odds).to_parquet(nba.path(raw, "odds", season), index=False)
    return raw
