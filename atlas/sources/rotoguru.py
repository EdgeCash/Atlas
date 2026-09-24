"""Historical DraftKings NFL salaries and points, from RotoGuru's archive.

    python -m atlas.sources.rotoguru              # 2014-2021, cached per season

Step 0 of `docs/MODEL_PLAN_DFS.md`. The DFS model is measured against
DraftKings' own salaries; DraftKings keeps no history, and this archive is
the free record of it: one row per player-week with DraftKings points and
salary, 2014 through 2021 (measured 24 September 2026: 350-440 players a
week; 2022 on is empty). It also carries DraftKings' own points, which step
1 uses to check Atlas's scoring rules.

Raw and gitignored like the rest of ``data/raw``; fetched once, politely -
one request a second, a season at a time, skipped when cached.
"""

from __future__ import annotations

import argparse
import io
import re
import time
from pathlib import Path

import pandas as pd

from atlas import config
from atlas.util import _guard_offline, get_logger, http_get, session, write_parquet

LOG = get_logger(__name__)

URL = "http://rotoguru1.com/cgi-bin/fyday.pl"
SEASONS = range(2014, 2022)
COLUMNS = {"Week": "week", "Year": "season", "GID": "gid", "Name": "name", "Pos": "position", "Team": "team",
           "h/a": "home_away", "Oppt": "opponent", "DK points": "dk_points", "DK salary": "dk_salary"}


def season_path(raw: Path, season: int) -> Path:
    return raw / "dfs" / f"rotoguru_dk_{season}.parquet"


def parse(page: str) -> pd.DataFrame:
    """The semicolon block of one archive page, or an empty frame."""
    match = re.search(r"(Week;Year;GID;.*?)</pre>", page, re.S)
    if not match:
        return pd.DataFrame(columns=list(COLUMNS.values()))
    frame = pd.read_csv(io.StringIO(match.group(1).strip()), sep=";")
    frame = frame.rename(columns=COLUMNS)[list(COLUMNS.values())]
    frame["dk_salary"] = pd.to_numeric(frame["dk_salary"], errors="coerce")
    frame["dk_points"] = pd.to_numeric(frame["dk_points"], errors="coerce")
    return frame.dropna(subset=["dk_salary"]).reset_index(drop=True)


def fetch_season(raw: Path, season: int, *, weeks: range = range(1, 19), pause: float = 1.0) -> Path | None:
    dest = season_path(raw, season)
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    sess = session()
    frames = []
    for week in weeks:
        params = {"week": week, "year": season, "game": "dk", "scsv": 1}
        _guard_offline(URL)
        frame = parse(http_get(URL, sess=sess, params=params, timeout=30).text)
        if not frame.empty:
            frames.append(frame)
        time.sleep(pause)
    if not frames:
        LOG.warning("rotoguru %s: no weeks", season)
        return None
    out = pd.concat(frames, ignore_index=True)
    write_parquet(out, dest)
    LOG.info("rotoguru %s: %d player-weeks over %d weeks", season, len(out), out["week"].nunique())
    return dest


def main() -> None:
    ap = argparse.ArgumentParser(description="Fetch RotoGuru's DraftKings NFL archive")
    ap.add_argument("--seasons", type=int, nargs="*", default=list(SEASONS))
    args = ap.parse_args()
    raw = config.paths().raw
    for season in args.seasons:
        fetch_season(raw, season)


if __name__ == "__main__":
    main()
