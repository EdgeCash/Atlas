"""Each team's expected quarterback, and what its conference's latest report says of him.

The expected starter is the team's quarterback of record in its last game
this season (the passer with the most attempts, from ESPN's box scores,
`atlas/models/ncaaf_qb.py`), which is known before kickoff. His status is the
one in the latest availability report captured for the team
(`atlas/sources/availability.py`, SEC and ACC conference games): a status
from the report, ``not listed`` when the team has a report that does not
name him (the reports list the players they must, not every player), or
``no report`` when there is none - a non-conference game, or a conference
that does not publish one Atlas can read.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd

from atlas.dfs import cfb

#: A starter with one of these is flagged: he is not expected to start.
OUT = ("Out", "Doubtful", "Out (1st Half)")
#: A report older than this is not the one for the coming game.
FRESH = timedelta(days=6)


def expected(box: pd.DataFrame, research: pd.DataFrame, now: datetime) -> dict[str, str]:
    """School (normalised) -> the name of its quarterback of record in its last game before ``now``."""
    if box.empty or research is None or research.empty:
        return {}
    b = box[box["pass_att"].fillna(0) > 0].sort_values(["pass_att", "pass_yds"])
    qb = b.groupby(["event", "home"], as_index=False).tail(1).assign(event=lambda d: d["event"].astype(str))
    games = research.assign(event=research["game_id"].astype(str))[["event", "home_team", "away_team", "kickoff"]]
    qb = qb.merge(games, on="event", how="inner")
    qb["school"] = [cfb.norm_name(h if home == 1 else a)
                    for h, a, home in zip(qb["home_team"], qb["away_team"], qb["home"], strict=True)]
    qb["kickoff"] = pd.to_datetime(qb["kickoff"], utc=True, errors="coerce")
    qb = qb[qb["kickoff"] < pd.Timestamp(now)].sort_values("kickoff")
    return dict(zip(qb["school"], qb["name"], strict=True))


def latest_reports(availability: pd.DataFrame, now: datetime) -> pd.DataFrame:
    """Each team's quarterback rows from its most recent report captured by ``now`` and not stale."""
    if availability.empty:
        return availability
    a = availability.copy()
    a["captured"] = pd.to_datetime(a["captured_at"], utc=True, errors="coerce")
    a["published"] = pd.to_datetime(a["publish_date"].astype(str) + " " + a["posted_time"].fillna("00:00:00").astype(str),
                                    errors="coerce").dt.tz_localize("UTC")
    a = a[(a["captured"] <= pd.Timestamp(now)) & (a["published"] >= pd.Timestamp(now) - FRESH)]
    if a.empty:
        return a
    a["school"] = a["team"].map(cfb.norm_name)
    newest = a.groupby("school")["published"].transform("max")
    return a[a["published"] == newest]


def status(school: str, expected_qbs: dict[str, str], reports: pd.DataFrame) -> tuple[str | None, str]:
    """(expected starter, his status) for one school."""
    key = cfb.norm_name(school)
    qb = expected_qbs.get(key)
    rows = reports[reports["school"] == key] if len(reports) else reports
    if rows is None or len(rows) == 0:
        return qb, "no report"
    if qb is None:
        return None, "no starter yet"
    hit = rows[rows["player"].map(cfb.norm_name) == cfb.norm_name(qb)]
    return qb, str(hit["status"].iloc[0]) if len(hit) else "not listed"


def for_games(games: dict[str, tuple[str, str]], box: pd.DataFrame, research: pd.DataFrame,
              availability: pd.DataFrame, now: datetime) -> dict[str, tuple]:
    """game id -> (home starter, his status, away starter, his status), for the games given as (home, away)."""
    qbs = expected(box, research, now)
    reports = latest_reports(availability, now)
    out = {}
    for gid, (home, away) in games.items():
        out[str(gid)] = (*status(home, qbs, reports), *status(away, qbs, reports))
    return out


def flagged(home_status, away_status) -> bool:
    return any(str(s) in OUT for s in (home_status, away_status))
