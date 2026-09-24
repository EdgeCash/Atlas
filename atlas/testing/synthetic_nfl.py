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
        plays = []
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
                    "game_id": gid, "season": season, "game_type": "REG" if week <= WEEKS - 1 else "WC",
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
        pd.DataFrame([d for d in depth_rows if d["season"] == season]).to_parquet(nfl / f"depth_charts_{season}.parquet", index=False)
        pd.DataFrame([i for i in injury_rows if i["season"] == season]).to_parquet(nfl / f"injuries_{season}.parquet", index=False)
    pd.DataFrame(sched_rows).to_parquet(nfl / "schedules.parquet", index=False)
    return nfl
