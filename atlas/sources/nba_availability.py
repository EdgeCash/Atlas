"""ESPN's NBA injury report, captured every run: who is out, who is a game-time decision.

    python -m atlas.sources.nba_availability        # capture the current report into tracking/

ESPN publishes one public feed of every team's current injuries
(``site.api.espn.com/.../basketball/nba/injuries``): each listed player with
a status (Out, Day-To-Day), the fantasy status behind it (OUT, GTD), the
injury, when it was reported and the expected return. The player's ESPN id
is in his player-card link, and hoopR's player ids are ESPN's, so the
snapshot's player is found by id, and by name on the team when the link is
missing.

Only the current report is public, so a status not captured is gone: every
Polymarket run takes it (one request) and folds it into
``tracking/nba_availability.csv``, one row per player, report time and
status, first seen when. That record is what a study of availability's
effect on the game model will need: there is no archive to walk forward on
today, which is why the constants in :data:`atlas.models.nba_props.AVAILABILITY`
are stated rather than fitted.

A failure is logged and passed over: the run never depends on it.
"""

from __future__ import annotations

import argparse
import re
from datetime import UTC, datetime

import pandas as pd
import requests

from atlas.live.store import SCHEMA
from atlas.util import get_logger, offline

LOG = get_logger(__name__)

ENDPOINT = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries"
#: ESPN's injury feeds by sport: the NBA's, and the NFL's for the football props.
ENDPOINTS = {"nba": ENDPOINT, "nfl": "https://site.api.espn.com/apis/site/v2/sports/football/nfl/injuries"}
USER_AGENT = "Atlas sports research (github.com/EdgeCash/Atlas; one request a run)"
COLUMNS = SCHEMA["nba_availability"]
#: ".../nba/player/_/id/4712863/mouhamed-gueye" -> 4712863
PLAYER_ID = re.compile(r"/id/(\d+)")
NOTE_CHARS = 160


def fetch(sess: requests.Session | None = None, sport: str = "nba") -> dict:
    sess = sess or requests.Session()
    r = sess.get(ENDPOINTS[sport], headers={"User-Agent": USER_AGENT}, timeout=30)
    r.raise_for_status()
    return r.json()


def _player_id(athlete: dict) -> int | None:
    raw = athlete.get("id")
    if raw is not None and str(raw).isdigit():
        return int(raw)
    for link in athlete.get("links") or []:
        m = PLAYER_ID.search(str(link.get("href") or ""))
        if m:
            return int(m.group(1))
    return None


def parse(payload: dict, captured_at) -> pd.DataFrame:
    """Every listed player across the teams, as of ``captured_at``."""
    stamp = pd.Timestamp(captured_at)
    stamp = stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC")
    stamp = stamp.replace(microsecond=0).isoformat()
    rows = []
    for team in (payload or {}).get("injuries") or []:
        team_id = team.get("id")
        for entry in team.get("injuries") or []:
            athlete = entry.get("athlete") or {}
            details = entry.get("details") or {}
            fantasy = (details.get("fantasyStatus") or {}).get("abbreviation")
            injury = " ".join(str(details[k]) for k in ("side", "type", "detail") if details.get(k)
                              and str(details[k]).lower() != "not specified")
            rows.append({
                "captured_at": stamp, "reported_at": entry.get("date"),
                "team_id": int(team_id) if str(team_id).isdigit() else None, "team": team.get("displayName"),
                "team_abbr": (athlete.get("team") or {}).get("abbreviation"),
                "player_id": _player_id(athlete), "player": athlete.get("displayName"),
                "position": (athlete.get("position") or {}).get("abbreviation"),
                "status": entry.get("status"), "fantasy": fantasy, "injury": injury or None,
                "return_date": details.get("returnDate"),
                "note": str(entry.get("shortComment") or "")[:NOTE_CHARS] or None,
            })
    out = pd.DataFrame(rows, columns=COLUMNS)
    return out[out["player"].notna() & out["status"].notna()].reset_index(drop=True)


def capture(store=None, now: datetime | None = None, sess: requests.Session | None = None,
            sport: str = "nba") -> pd.DataFrame:
    """The current report for ``sport``, folded into the store (``{sport}_availability``) when one is
    given. Offline, or on any failure, an empty frame: the run prices as if nobody were listed, and says
    so in the log."""
    now = now or datetime.now(UTC)
    if offline():
        return pd.DataFrame(columns=COLUMNS)
    try:
        report = parse(fetch(sess, sport), now)
    except Exception as error:  # noqa: BLE001 - the type only
        LOG.warning("%s availability: not captured (%s)", sport, type(error).__name__)
        return pd.DataFrame(columns=COLUMNS)
    if store is not None and len(report):
        added = store.append_new_only(f"{sport}_availability", report)
        LOG.info("%s availability: %d listed (%d out), %d new rows in the record", sport, len(report),
                 int((report["status"].str.lower() == "out").sum()), added)
    return report


def main(argv: list[str] | None = None) -> int:
    from atlas.live.store import Store

    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--sport", choices=sorted(ENDPOINTS), default="nba")
    args = parser.parse_args(argv)
    report = capture(Store.open(), sport=args.sport)
    print(report[["team", "player", "status", "fantasy", "injury", "return_date"]].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
