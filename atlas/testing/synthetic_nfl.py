"""A tiny synthetic nflverse tree for tests: no network, deterministic.

Eight franchises, a handful of weeks a season, play-by-play with the columns
the NFL staging reads and nothing else. Team strengths drive both the
scores and the EPA so the staging has something real to recover.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

#: Eight current codes; the first season spells the Raiders "OAK" so the
#: franchise map is exercised.
CODES = ["KC", "BUF", "LV", "DEN", "PHI", "DAL", "SF", "SEA"]
WEEKS = 10
#: Each team's skill players for the player weeks (`stats_player`): (first name, position, share of the
#: team's pass attempts as targets, share of its rush attempts, yards a catch, yards a carry). A kicker is
#: written too, for the staging to drop. The first receiver's share leans with the team's index, so the
#: shares differ between teams and the model has something to recover.
ROSTER = [("Quinn", "QB", 0.0, 0.08, 0.0, 5.0), ("Rex", "RB", 0.10, 0.62, 7.0, 4.4), ("Ray", "RB", 0.05, 0.30, 6.0, 4.0),
          ("Wes", "WR", 0.27, 0.0, 13.5, 0.0), ("Will", "WR", 0.18, 0.0, 12.0, 0.0), ("Walt", "WR", 0.12, 0.0, 11.0, 0.0),
          ("Ted", "TE", 0.15, 0.0, 10.5, 0.0), ("Kip", "K", 0.0, 0.0, 0.0, 0.0)]


def player_name(first: str, team: str) -> str:
    return f"{first} {team.title()}"


def _code(code: str, season: int, first: int) -> str:
    return "OAK" if (code == "LV" and season == first) else code


def write_synthetic_nfl_raw(raw: Path, seasons: list[int], *, seed: int = 7) -> Path:
    rng = np.random.default_rng(seed)
    nfl = raw / "nfl"
    nfl.mkdir(parents=True, exist_ok=True)
    strength = dict(zip(CODES, rng.normal(0, 6, len(CODES)), strict=True))
    first = min(seasons)
    sched_rows, depth_rows, injury_rows = [], [], []
    for season in seasons:
        plays, weeks = [], []
        for week in range(1, WEEKS + 1):
            order = rng.permutation(len(CODES))
            for k in range(0, len(CODES), 2):
                home, away = CODES[order[k]], CODES[order[k + 1]]
                margin = strength[home] - strength[away] + 2.0 + rng.normal(0, 13)
                total = 45 + rng.normal(0, 12)
                hs, as_ = max(0, round((total + margin) / 2)), max(0, round((total - margin) / 2))
                gid = f"{season}_{week:02d}_{_code(away, season, first)}_{_code(home, season, first)}"
                played = not (season == max(seasons) and week == WEEKS)   # the last week is still to play
                sched_rows.append({
                    "game_id": gid, "espn": 401_000_000 + season * 1000 + week * 10 + k // 2,
                    "season": season, "game_type": "REG" if week <= WEEKS - 1 else "WC",
                    "week": week, "gameday": f"{season}-09-{7 + week:02d}", "gametime": "13:00",
                    "away_team": _code(away, season, first), "home_team": _code(home, season, first),
                    "away_score": as_ if played else None, "home_score": hs if played else None,
                    "location": "Neutral" if (week == 2 and k == 0) else "Home",
                    "result": (hs - as_) if played else None, "total": (hs + as_) if played else None,
                    "overtime": 0, "away_rest": 7, "home_rest": 7 if week != 3 else 10,
                    "away_moneyline": 120, "home_moneyline": -140,
                    "spread_line": round((strength[home] - strength[away] + 1.5) * 2) / 2, "total_line": 44.5,
                    "div_game": 0, "roof": "dome" if home == "DAL" else "outdoors", "surface": "grass",
                    "temp": 65, "wind": 5, "away_qb_id": f"qb-{away}", "home_qb_id": f"qb-{home}",
                    "away_qb_name": f"QB {away}", "home_qb_name": f"QB {home}", "away_coach": "A", "home_coach": "H",
                    "referee": "R", "stadium": f"{home} Field",
                })
                for team in (home, away):
                    depth_rows.append({"season": season, "club_code": _code(team, season, first), "week": float(week),
                                       "game_type": "REG", "position": "QB", "depth_team": "1",
                                       "gsis_id": f"qb-{team}", "full_name": f"QB {team}"})
                    if week == 4 and team == home:
                        injury_rows.append({"season": season, "team": _code(team, season, first), "week": week,
                                            "gsis_id": f"qb-{team}", "position": "QB", "report_status": "Out"})
                if not played:
                    continue
                weeks.extend(_player_weeks(rng, season, week, gid, home, away, sched_rows[-1], first))
                # ~40 plays a side, EPA around the strength gap; a garbage-time tail in the fourth quarter
                pid = 0
                for off, de in ((home, away), (away, home)):
                    for drive in range(1, 6):
                        for _ in range(8):
                            pid += 1
                            gt = drive == 5
                            plays.append({
                                "play_id": pid, "game_id": gid, "week": week, "game_date": f"{season}-09-{7 + week:02d}",
                                "posteam": _code(off, season, first), "defteam": _code(de, season, first),
                                "home_team": _code(home, season, first), "rush": int(rng.random() < 0.45),
                                "pass": 0, "play_type": "run", "epa": (strength[off] - strength[de]) / 40 + rng.normal(0, 1) + (5.0 if gt else 0.0),
                                "success": int(rng.random() < 0.45), "score_differential": 30 if gt else rng.integers(-10, 10),
                                "qtr": 4 if gt else rng.integers(1, 4), "sack": 0, "interception": int(rng.random() < 0.03),
                                "fumble_lost": 0, "fixed_drive": drive if off == home else drive + 5,
                                "fixed_drive_result": rng.choice(["Punt", "Touchdown", "Field goal", "Turnover"]),
                                "drive_inside20": int(drive % 2 == 0), "drive_ended_with_score": int(drive % 2 == 0),
                                "home_score": hs, "away_score": as_, "drive_time_of_possession": "2:30",
                                "qb_dropback": 1, "passer_player_id": f"qb-{off}" if drive < 5 else f"qb2-{off}",
                                "passer_player_name": f"QB {off}", "qb_epa": rng.normal(0.1, 1), "cpoe": rng.normal(0, 5),
                            })
                            p = plays[-1]
                            if p["rush"] == 0:
                                p["pass"], p["play_type"] = 1, "pass"
        pd.DataFrame(plays).to_parquet(nfl / f"pbp_{season}.parquet", index=False)
        pd.DataFrame(weeks).to_parquet(nfl / f"stats_player_{season}.parquet", index=False)
        pd.DataFrame([d for d in depth_rows if d["season"] == season]).to_parquet(nfl / f"depth_charts_{season}.parquet", index=False)
        pd.DataFrame([i for i in injury_rows if i["season"] == season]).to_parquet(nfl / f"injuries_{season}.parquet", index=False)
    pd.DataFrame(sched_rows).to_parquet(nfl / "schedules.parquet", index=False)
    return nfl


def _player_weeks(rng, season: int, week: int, gid: str, home: str, away: str, game: dict, first: int) -> list[dict]:
    """Both teams' player box scores for one game, in nflverse's ``stats_player`` columns. A team throws in
    proportion to the total the line implies for it, so the game layer has a real effect to find."""
    rows = []
    for team, opp in ((home, away), (away, home)):
        code, opp_code = _code(team, season, first), _code(opp, season, first)
        spread = game["spread_line"] if team == home else -game["spread_line"]
        tilt = ((game["total_line"] + spread) / 2.0) / (game["total_line"] / 2.0)
        pass_attempts = int(rng.poisson(33 * tilt))
        rush_attempts = int(rng.poisson(26))
        lean = 0.02 * (CODES.index(team) - 3.5)
        team_rows = []
        for j, (name, pos, t_share, c_share, ypc_catch, ypc_carry) in enumerate(ROSTER):
            share = t_share + (lean if j == 3 else -lean / 3 if j in (4, 5, 6) else 0.0)
            targets = int(rng.binomial(pass_attempts, max(share, 0.0))) if share > 0 else 0
            receptions = int(rng.binomial(targets, 0.65)) if targets else 0
            rec_yards = int(max(0, round(receptions * ypc_catch + rng.normal(0, 4 * np.sqrt(receptions + 1)))))
            rec_tds = int(rng.binomial(receptions, 0.07)) if receptions else 0
            carries = int(rng.binomial(rush_attempts, c_share)) if c_share > 0 else 0
            rush_yards = int(max(0, round(carries * ypc_carry + rng.normal(0, 3 * np.sqrt(carries + 1)))))
            rush_tds = int(rng.binomial(carries, 0.04)) if carries else 0
            team_rows.append({
                "player_id": f"00-{team}-{pos}{j}", "player_name": f"{name[0]}.{code}", "player_display_name": player_name(name, team),
                "position": pos, "position_group": pos, "season": season, "week": week,
                "season_type": "REG" if week <= WEEKS - 1 else "POST", "game_id": gid, "team": code,
                "opponent_team": opp_code, "completions": 0, "attempts": 0, "passing_yards": 0, "passing_tds": 0,
                "carries": carries, "rushing_yards": rush_yards, "rushing_tds": rush_tds, "receptions": receptions,
                "targets": targets, "receiving_yards": rec_yards, "receiving_tds": rec_tds})
        qb = team_rows[0]
        qb["attempts"] = pass_attempts
        qb["completions"] = sum(r["receptions"] for r in team_rows)
        qb["passing_yards"] = sum(r["receiving_yards"] for r in team_rows)
        qb["passing_tds"] = sum(r["receiving_tds"] for r in team_rows)
        rows.extend(team_rows)
    return rows
