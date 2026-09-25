"""The conferences' player availability reports: the quarterbacks, captured daily.

    python -m atlas.sources.availability        # capture the current reports into tracking/

Since 2025-26 the Power Four publish official availability reports before
conference games, because of legal wagering: statuses from Available to Out,
days ahead and on game day. The SEC's and the ACC's are served to their sites
by one embedded app (HD Intelligence), whose public report endpoint returns
each report's players with position, number, name and status. The Big Ten's
and the Big 12's are not reachable from here yet.

Only the current reports are public (the archive of past seasons needs a
login), so a report not captured on its day is gone: each heavy refresh
takes the current ones - one request a conference, once a day - and keeps
the quarterbacks in the tracking store, where they become a record that can
be tested (`atlas/owner/plays.py` reads them for the starter flag). The data
is the conferences' own, published to be public; the capture is kept to one
call a conference a day and says who it is.

A failure is logged and passed over: the refresh never depends on it.
"""

from __future__ import annotations

import argparse
import re
from datetime import UTC, datetime

import pandas as pd
import requests

from atlas.util import get_logger

LOG = get_logger(__name__)

ENDPOINT = "https://app.hdintelligence.com/api/get-publish-public"
CONFERENCES = ("SEC", "ACC")
USER_AGENT = "Atlas sports research (github.com/EdgeCash/Atlas; one request a conference a day)"
COLUMNS = ["captured_at", "conference", "report_id", "publish_date", "posted_time", "time_zone", "report_type",
           "team", "opponent", "number", "player", "status", "exempt"]
#: "QB #15 Jett Niu" -> position, number, name.
NAME = re.compile(r"^\s*([A-Z/]+)\s+#?(\d+)?\s*(.+?)\s*$")


def parse(payload: dict, conference: str, captured_at: str) -> pd.DataFrame:
    """The quarterbacks of every report in one conference's current set."""
    rows = []
    for report_id, report in (payload or {}).items():
        if not isinstance(report, dict):
            continue
        games = report.get("games") or []
        teams = [g.get("teamDisplayName") or g.get("teamName") for g in games]
        for i, g in enumerate(games):
            opponent = teams[1 - i] if len(teams) == 2 else None
            for r in g.get("rows") or []:
                m = NAME.match(str(r.get("name") or ""))
                if not m or m.group(1) != "QB":
                    continue
                # As the tracking store reads it back, so a report re-read matches its rows.
                rid = int(report_id) if str(report_id).isdigit() else str(report_id)
                rows.append({"captured_at": captured_at, "conference": conference, "report_id": rid,
                             "publish_date": report.get("publishDate"), "posted_time": report.get("postedTime"),
                             "time_zone": report.get("conferenceTimeZone"), "report_type": report.get("ReportType"),
                             "team": teams[i], "opponent": opponent, "number": m.group(2), "player": m.group(3),
                             "status": r.get("status"), "exempt": r.get("exemptStatus")})
    return pd.DataFrame(rows, columns=COLUMNS)


def fetch(conference: str, session: requests.Session | None = None) -> dict:
    s = session or requests.Session()
    r = s.post(ENDPOINT, json={"sport": "Football", "organization": conference, "conference": conference},
               headers={"User-Agent": USER_AGENT}, timeout=60)
    r.raise_for_status()
    return r.json()


def capture(store=None, *, now: datetime | None = None, fetcher=fetch) -> int:
    """Every conference's current reports into the store. Returns the new rows. Never raises."""
    if store is None:
        from atlas.live.store import Store

        store = Store.open()
    stamp = (now or datetime.now(UTC)).replace(microsecond=0).isoformat()
    parts = []
    for conference in CONFERENCES:
        try:
            parts.append(parse(fetcher(conference), conference, stamp))
        except Exception as error:  # noqa: BLE001 - one conference failing costs only its reports
            LOG.warning("availability %s not captured: %s", conference, type(error).__name__)
    rows = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=COLUMNS)
    if rows.empty:
        return 0
    added = store.upsert("availability", rows)
    LOG.info("availability: %d quarterback rows from %d reports, %d new", len(rows), rows["report_id"].nunique(),
             added)
    return added


def main() -> None:
    argparse.ArgumentParser(description="Capture the SEC and ACC availability reports' quarterbacks").parse_args()
    capture()


if __name__ == "__main__":
    main()
