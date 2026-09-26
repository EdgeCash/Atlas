"""Other models' numbers for upcoming games: FPI, Elo and SP+, for display.

    python -m atlas.sources.other_models      # the heavy refresh runs it; never fails the run

The "other models" panel on each card (`ATLAS_FEATURE_ROADMAP.md` §3) shows
what other public models say about the game, beside Atlas and without a
verdict. The warehouse cannot supply it honestly: it holds ESPN's projection
as first fetched and never refreshed, a schedule file downloaded once a
season, and SP+ only as the previous season's finals (on purpose - that is
what the model may use). So this fetches the current numbers each heavy
refresh, for upcoming games only, and never touches the model's inputs.

* **FPI** (both sports): ESPN's own predicted margin and win probability
  for the game, from its predictor endpoint, with ESPN's ``lastModified``.
* **Elo** (college): pre-game Elo from the current sportsdataverse schedule,
  as a home margin: ``(home - away) / 24 + 2.6`` for a true home game. The
  24 and 2.6 are the map the consensus test fitted on 2018-2020
  (`reports/consensus_test.md`); the card states them.
* **SP+** (college): the current season's SP+ ratings from CFBD, as a home
  margin: ``home - away + 2.5`` for a true home game, the rating difference
  being SP+'s own neutral-field margin. The card states that too.

Each is logged to ``tracking/other_models.csv``, one row per game and model,
and only while the game is still to kick off, so the row standing at kickoff
is the number published before it. That is also the forward record the owner
page's consensus label needs.
"""

from __future__ import annotations

import concurrent.futures as cf
import io
import sys
from datetime import UTC, datetime, timedelta

import pandas as pd

from atlas.sources import cfbd, espn
from atlas.sources import sportsdataverse as sdv
from atlas.util import get_logger, http_get, session

LOG = get_logger(__name__)

TABLE = "other_models"
HORIZON_DAYS = 8
#: Elo points per point of margin, and the home side's points, fitted on
#: 2018-2020 by the consensus test: margin = 0.0417 x Elo difference + 2.58.
ELO_POINTS = 24.0
ELO_HOME = 2.6
#: SP+ ratings are points against an average team, so their difference is a
#: neutral-field margin; this is the home side's points on top.
SP_HOME = 2.5

PREDICTOR = {
    "ncaaf": espn.CORE,
    "nfl": "https://sports.core.api.espn.com/v2/sports/football/leagues/nfl",
}


def _stats(block: dict) -> dict:
    return {s.get("name"): s.get("value") for s in (block or {}).get("statistics", [])}


def fpi_row(payload: dict) -> dict | None:
    """ESPN's predictor payload -> FPI's home margin and win probability."""
    home = _stats(payload.get("homeTeam"))
    margin, prob = home.get("teamPredPtDiff"), home.get("gameProjection")
    if margin is None and prob is None:
        return None
    return {"model": "fpi", "home_margin": None if margin is None else float(margin),
            "home_win_prob": None if prob is None else float(prob) / 100.0,
            "as_of": payload.get("lastModified"), "detail": None}


def elo_margin(home_elo: float, away_elo: float, neutral: bool) -> float:
    return (home_elo - away_elo) / ELO_POINTS + (0.0 if neutral else ELO_HOME)


def sp_margin(home_sp: float, away_sp: float, neutral: bool) -> float:
    return home_sp - away_sp + (0.0 if neutral else SP_HOME)


def upcoming(now: datetime, sport: str) -> dict[int, dict]:
    """ESPN's own list of the sport's games in the next week, keyed by ESPN id."""
    from atlas.site import meta

    games = meta.fetch(meta.days_ahead(HORIZON_DAYS), sport=sport)
    return {gid: g for gid, g in games.items()
            if (k := pd.to_datetime(g.get("kickoff"), utc=True, errors="coerce")) is not pd.NaT
            and now < k.to_pydatetime() <= now + timedelta(days=HORIZON_DAYS)}


def fetch_fpi(sport: str, game_ids: list[int]) -> dict[int, dict]:
    sess = session()

    def one(gid: int):
        url = f"{PREDICTOR[sport]}/events/{gid}/competitions/{gid}/predictor"
        try:
            return gid, fpi_row(http_get(url, sess=sess, retries=1, timeout=30).json())
        except Exception:  # noqa: BLE001 - no projection yet is expected
            return gid, None

    with cf.ThreadPoolExecutor(max_workers=8) as pool:
        return {gid: row for gid, row in pool.map(one, game_ids) if row}


def current_schedule(season: int) -> pd.DataFrame:
    """The season's schedule as published now: downloaded fresh, never the cached copy."""
    url = f"{sdv.RAW_BASE}/schedules/parquet/cfb_schedules_{season}.parquet"
    return pd.read_parquet(io.BytesIO(http_get(url, sess=session(), timeout=120).content))


def college_rows(schedule: pd.DataFrame, sp: pd.DataFrame | None, game_ids: set[int],
                 when: str) -> list[dict]:
    """Elo and SP+ for each upcoming college game in the schedule."""
    s = schedule.assign(game_id=pd.to_numeric(schedule["game_id"], errors="coerce"))
    s = s[s["game_id"].isin(game_ids)]
    ratings = {} if sp is None or sp.empty else dict(zip(sp["team"], pd.to_numeric(sp["rating"], errors="coerce"),
                                                         strict=True))
    out = []
    for _, g in s.iterrows():
        neutral = bool(g.get("neutral_site"))
        he, ae = pd.to_numeric(g.get("home_pregame_elo"), errors="coerce"), pd.to_numeric(
            g.get("away_pregame_elo"), errors="coerce")
        if pd.notna(he) and pd.notna(ae):
            out.append({"game_id": int(g["game_id"]), "model": "elo", "home_margin": elo_margin(he, ae, neutral),
                        "home_win_prob": None, "as_of": when,
                        "detail": f"Elo {he:.0f} home, {ae:.0f} away" + (", neutral site" if neutral else "")})
        hs, as_ = ratings.get(g.get("home_team")), ratings.get(g.get("away_team"))
        if hs is not None and as_ is not None and pd.notna(hs) and pd.notna(as_):
            out.append({"game_id": int(g["game_id"]), "model": "sp_plus", "home_margin": sp_margin(hs, as_, neutral),
                        "home_win_prob": None, "as_of": when,
                        "detail": f"SP+ {hs:.1f} home, {as_:.1f} away" + (", neutral site" if neutral else "")})
    return out


def collect(now: datetime) -> pd.DataFrame:
    """Every model's number for every upcoming game it covers. Each source
    that fails is logged and skipped; the others still count."""
    fetched = now.isoformat()
    rows: list[dict] = []
    for sport in ("ncaaf", "nfl"):
        try:
            games = upcoming(now, sport)
        except Exception as error:  # noqa: BLE001
            LOG.warning("other models: no %s game list (%s)", sport, type(error).__name__)
            continue
        kick = {gid: g.get("kickoff") for gid, g in games.items()}

        def add(found: list[dict], sport=sport, kick=kick):
            rows.extend({**r, "sport": sport, "kickoff": kick[r["game_id"]], "fetched_at": fetched} for r in found)

        try:
            add([{**r, "game_id": gid} for gid, r in fetch_fpi(sport, list(games)).items()])
        except Exception as error:  # noqa: BLE001
            LOG.warning("other models: FPI failed for %s (%s)", sport, type(error).__name__)
        if sport != "ncaaf" or not games:
            continue
        season = max(pd.to_datetime(g["kickoff"], utc=True).year for g in games.values())
        try:
            schedule = current_schedule(season)
        except Exception as error:  # noqa: BLE001
            LOG.warning("other models: no current schedule (%s)", type(error).__name__)
            continue
        sp = None
        try:
            sp = pd.json_normalize(cfbd._get("/ratings/sp", {"year": season})) if cfbd.available() else None
        except Exception as error:  # noqa: BLE001
            LOG.warning("other models: no SP+ (%s)", type(error).__name__)
        add(college_rows(schedule, sp, set(games), fetched))
    return pd.DataFrame(rows)


def main() -> int:
    """Fetch and record. Never fails the heavy refresh."""
    try:
        from atlas.live.store import Store

        found = collect(datetime.now(UTC))
        Store.open().upsert(TABLE, found)
        by = found.groupby(["sport", "model"]).size().to_dict() if len(found) else {}
        LOG.info("other models: %d numbers recorded %s", len(found), by)
    except Exception as error:  # noqa: BLE001 - a missed fetch is logged, the site still builds
        LOG.error("other models not recorded: %s", type(error).__name__)
    return 0


if __name__ == "__main__":
    sys.exit(main())
