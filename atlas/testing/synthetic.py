"""Generate a deterministic synthetic league in the raw-source file layout.

The point is not realism, it is *shape*: the files written here have the same
columns, dtypes and quirks as the published sources, so the staging, warehouse
and research code under test is the real code, not a stub. The generator is
seeded, so two runs produce byte-identical files and the whole pipeline can be
asserted to be reproducible.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

TEAM_COUNT = 16
GAMES_PER_TEAM = 12
BASE_GAME_ID = 900_000_000


def _teams(seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    ids = np.arange(1, TEAM_COUNT + 1) * 7
    return pd.DataFrame(
        {
            "team_id": ids,
            "school": [f"Team {i:02d}" for i in range(TEAM_COUNT)],
            "abbreviation": [f"T{i:02d}" for i in range(TEAM_COUNT)],
            "conference": ["Synth North"] * (TEAM_COUNT // 2)
            + ["Synth South"] * (TEAM_COUNT - TEAM_COUNT // 2),
            "classification": ["fbs"] * TEAM_COUNT,
            "venue_id": ids * 3,
            "venue_name": [f"Stadium {i:02d}" for i in range(TEAM_COUNT)],
            "city": ["Somewhere"] * TEAM_COUNT,
            "state": ["ZZ"] * TEAM_COUNT,
            "latitude": 30.0 + rng.uniform(0, 12, TEAM_COUNT).round(4),
            "longitude": -100.0 + rng.uniform(0, 25, TEAM_COUNT).round(4),
            "elevation": rng.uniform(5, 1500, TEAM_COUNT).round(1),
            "dome": [False] * TEAM_COUNT,
            "strength": rng.normal(0, 9, TEAM_COUNT).round(3),
        }
    )


def _schedule(teams: pd.DataFrame, season: int, rng: np.random.Generator) -> pd.DataFrame:
    ids = teams["team_id"].to_numpy()
    rows = []
    game_no = 0
    for week in range(1, GAMES_PER_TEAM + 1):
        order = rng.permutation(ids)
        for i in range(0, len(order) - 1, 2):
            home, away = int(order[i]), int(order[i + 1])
            rows.append({"season": season, "week": week, "home_id": home, "away_id": away,
                         "game_no": game_no})
            game_no += 1
    sched = pd.DataFrame(rows)
    sched["game_id"] = BASE_GAME_ID + season * 10_000 + sched["game_no"]
    strength = teams.set_index("team_id")["strength"]
    sched["home_strength"] = sched["home_id"].map(strength)
    sched["away_strength"] = sched["away_id"].map(strength)

    expected = sched["home_strength"] - sched["away_strength"] + 2.5
    noise = rng.normal(0, 13, len(sched))
    margin = np.round(expected + noise)
    total = np.round(np.clip(52 + rng.normal(0, 11, len(sched)), 14, 100))
    sched["home_points"] = np.clip((total + margin) / 2, 0, None).round()
    sched["away_points"] = np.clip(total - sched["home_points"], 0, None).round()

    kickoff = pd.to_datetime(f"{season}-09-01T18:00:00Z") + pd.to_timedelta(
        (sched["week"] - 1) * 7, unit="D"
    ) + pd.to_timedelta(sched["game_no"] % 3, unit="h")
    sched["start_date"] = kickoff.dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")

    venue = teams.set_index("team_id")["venue_id"]
    name = teams.set_index("team_id")["school"]
    sched["venue_id"] = sched["home_id"].map(venue).astype(float)
    sched["venue"] = sched["home_id"].map(teams.set_index("team_id")["venue_name"])
    sched["home_team"] = sched["home_id"].map(name)
    sched["away_team"] = sched["away_id"].map(name)
    sched["season_type"] = "regular"
    sched["completed"] = True
    sched["neutral_site"] = False
    sched["conference_game"] = False
    sched["home_division"] = "fbs"
    sched["away_division"] = "fbs"
    sched["home_conference"] = "Synth North"
    sched["away_conference"] = "Synth South"
    sched["home_pregame_elo"] = (1500 + sched["home_strength"] * 20).round()
    sched["away_pregame_elo"] = (1500 + sched["away_strength"] * 20).round()
    sched["attendance"] = 50000.0
    return sched


def _odds(sched: pd.DataFrame, teams: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    abbr = teams.set_index("team_id")["abbreviation"]
    rows = []
    for _, g in sched.iterrows():
        true_spread = -(g["home_strength"] - g["away_strength"] + 2.5)
        close = np.round((true_spread + rng.normal(0, 1.5)) * 2) / 2
        open_ = close + np.round(rng.normal(0, 1) * 2) / 2
        total_close = float(np.round((52 + rng.normal(0, 3)) * 2) / 2)
        total_open = total_close + np.round(rng.normal(0, 1) * 2) / 2
        for book in ("Book A", "Book B"):
            common = {
                "id": float(g["game_id"]),
                "game_id": float(g["game_id"]),
                "season": float(g["season"]),
                "game_desc": f"{g['away_team']}@{g['home_team']}",
                "date_time": g["start_date"],
                "book": book,
                "season_type": "regular",
                "week": float(g["week"]),
                "home_team_id": float(g["home_id"]),
                "away_team_id": float(g["away_id"]),
            }
            rows.append({**common, "market_type": "spread", "abbr": abbr[g["home_id"]],
                         "lines": close, "odds": -110.0,
                         "opening_lines": open_, "opening_odds": -110.0})
            rows.append({**common, "market_type": "spread", "abbr": abbr[g["away_id"]],
                         "lines": -close, "odds": -110.0,
                         "opening_lines": -open_, "opening_odds": -110.0})
            rows.append({**common, "market_type": "total", "abbr": "over",
                         "lines": total_close, "odds": -110.0,
                         "opening_lines": total_open, "opening_odds": -110.0})
            rows.append({**common, "market_type": "total", "abbr": "under",
                         "lines": total_close, "odds": -110.0,
                         "opening_lines": total_open, "opening_odds": -110.0})
            rows.append({**common, "market_type": "money_line", "abbr": abbr[g["home_id"]],
                         "lines": np.nan, "odds": -150.0,
                         "opening_lines": np.nan, "opening_odds": -140.0})
            rows.append({**common, "market_type": "money_line", "abbr": abbr[g["away_id"]],
                         "lines": np.nan, "odds": 130.0,
                         "opening_lines": np.nan, "opening_odds": 120.0})
    return pd.DataFrame(rows)


def _play_by_play(sched: pd.DataFrame, teams: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    name = teams.set_index("team_id")["school"]
    rows = []
    for _, g in sched.iterrows():
        for offense_id, defense_id in ((g["home_id"], g["away_id"]), (g["away_id"], g["home_id"])):
            skill = float(teams.set_index("team_id")["strength"][offense_id]) / 20.0
            for drive in range(1, 9):
                start = float(rng.integers(55, 90))
                ytg = start
                drive_points = float(rng.choice([0, 3, 7], p=[0.5, 0.2, 0.3]))
                for play in range(6):
                    is_pass = bool(rng.integers(0, 2))
                    epa = float(rng.normal(skill, 1.1))
                    success = float(epa > 0)
                    ytg = max(1.0, ytg - float(rng.integers(0, 14)))
                    rows.append(
                        {
                            "game_id": int(g["game_id"]),
                            "year": int(g["season"]),
                            "season": int(g["season"]),
                            "week": int(g["week"]),
                            "season_type": "regular",
                            "start_date": g["start_date"],
                            "pos_team": name[offense_id],
                            "def_pos_team": name[defense_id],
                            "home": g["home_team"],
                            "away": g["away_team"],
                            "home_team_id": int(g["home_id"]),
                            "away_team_id": int(g["away_id"]),
                            "neutral_site": False,
                            "completed": True,
                            "spread": np.nan,
                            "formatted_spread": "",
                            "over_under": np.nan,
                            "EPA": epa,
                            "success": success,
                            "rush": float(not is_pass),
                            "pass": float(is_pass),
                            "yards_gained": float(rng.integers(-3, 20)),
                            "down": float(1 + play % 4),
                            "distance": 10.0,
                            "yards_to_goal": ytg,
                            "period": int(1 + drive // 3),
                            "TimeSecsRem": float(3600 - drive * 400 - play * 30),
                            "play_type": "Pass Reception" if is_pass else "Rush",
                            "penalty_no_play": False,
                            "kickoff_play": 0.0,
                            "punt_play": 0.0,
                            "fg_inds": 0.0,
                            "sack": float(is_pass and rng.random() < 0.06),
                            "int": float(is_pass and rng.random() < 0.03),
                            "turnover": 0.0,
                            "fumble_vec": 0.0,
                            "stuffed_run": float(not is_pass and rng.random() < 0.15),
                            "pass_breakup_player_name": "Someone" if rng.random() < 0.05 else None,
                            "fumble_forced_player_name": None,
                            "score_diff": float(rng.integers(-10, 11)),
                            "scoring_opp": float(ytg <= 40),
                            "rz_play": float(ytg <= 20),
                            "drive_id": float(int(g["game_id"]) * 100 + drive),
                            "drive_start_yards_to_goal": start,
                            "drive_pts": drive_points,
                            "drive_number": float(drive if offense_id == g["home_id"] else drive + 50),
                            "drive_time_minutes_elapsed": 2.0,
                            "drive_time_seconds_elapsed": 30.0,
                        }
                    )
    return pd.DataFrame(rows)


def write_synthetic_raw(
    raw: Path, seasons: list[int], *, seed: int = 1234
) -> dict[str, list[Path]]:
    """Write a complete synthetic raw tree and return the paths written."""
    raw = Path(raw)
    rng = np.random.default_rng(seed)
    teams = _teams(seed)
    written: dict[str, list[Path]] = {k: [] for k in
                                      ("schedules", "team_info", "pbp", "espn_fpi",
                                       "espn_predictor", "odds")}

    odds_frames = []
    # FPI needs the season before the first modelled season.
    for season in [min(seasons) - 1, *seasons]:
        sched = _schedule(teams, season, rng)
        if season in seasons:
            cols = [
                "game_id", "season", "week", "season_type", "start_date", "completed",
                "neutral_site", "conference_game", "attendance", "venue_id", "venue",
                "home_id", "home_team", "home_division", "home_conference", "home_points",
                "home_pregame_elo", "away_id", "away_team", "away_division",
                "away_conference", "away_points", "away_pregame_elo",
            ]
            path = raw / "schedules" / f"schedules_{season}.parquet"
            path.parent.mkdir(parents=True, exist_ok=True)
            sched[cols].to_parquet(path, index=False)
            written["schedules"].append(path)

            ti = raw / "team_info" / f"team_info_{season}.parquet"
            ti.parent.mkdir(parents=True, exist_ok=True)
            teams.drop(columns=["strength"]).to_parquet(ti, index=False)
            written["team_info"].append(ti)

            pbp_path = raw / "pbp" / f"pbp_{season}.parquet"
            pbp_path.parent.mkdir(parents=True, exist_ok=True)
            _play_by_play(sched, teams, rng).to_parquet(pbp_path, index=False)
            written["pbp"].append(pbp_path)

            pred_path = raw / "espn_predictor" / f"predictor_{season}.parquet"
            pred_path.parent.mkdir(parents=True, exist_ok=True)
            prob = 1 / (1 + np.exp(-(sched["home_strength"] - sched["away_strength"] + 2.5) / 9))
            pd.DataFrame(
                {
                    "game_id": sched["game_id"].astype("int64"),
                    "season": season,
                    "fpi_home_win_prob": prob.round(4),
                    "fpi_away_win_prob": (1 - prob).round(4),
                }
            ).to_parquet(pred_path, index=False)
            written["espn_predictor"].append(pred_path)

            odds_frames.append(_odds(sched, teams, rng))

        fpi_path = raw / "espn_fpi" / f"fpi_{season}.parquet"
        fpi_path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(
            {
                "season": season,
                "team_id": teams["team_id"],
                "team": teams["school"],
                "fpi": (teams["strength"] + rng.normal(0, 1.5, len(teams))).round(3),
                "fpirank": np.arange(1, len(teams) + 1),
            }
        ).to_parquet(fpi_path, index=False)
        written["espn_fpi"].append(fpi_path)

    odds_path = raw / "odds" / "cfb_line_odds.parquet"
    odds_path.parent.mkdir(parents=True, exist_ok=True)
    pd.concat(odds_frames, ignore_index=True).to_parquet(odds_path, index=False)
    written["odds"].append(odds_path)
    return written
