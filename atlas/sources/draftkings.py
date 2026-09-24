"""DraftKings NFL Classic slates and salaries, captured into the record.

    python -m atlas.sources.draftkings            # capture today's slates

Step 0 of `docs/MODEL_PLAN_DFS.md`. A salary is DraftKings' own number for
a player's week - the market the DFS model is measured against - and
DraftKings does not keep past slates, so a day not captured is a day lost.
The capture runs in the heavy refresh and writes to the committed tracking
store (``dfs_slates``, ``dfs_salaries``), which is also its backup.

Two public JSON endpoints, no key, undocumented:

* the lobby lists every current draft group (slate) - its contest type,
  games and start;
* a Classic group's draftables are its player pool with salaries.

Only Classic slates are kept (contest type 21: the $50,000 cap, QB / 2 RB /
3 WR / TE / FLEX / DST); showdown, snake and the other formats carry no
salary or a different game. The main slate is the Classic group DraftKings
leaves unlabeled; the rest carry a label ("Thu-Mon", "Early Only").

This module never fails the run. DraftKings may change or close these
endpoints at any time; a failed capture is logged and the site builds
without it (the plan's fallback is a manual CSV import).
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta

import pandas as pd

from atlas.util import _guard_offline, get_logger, http_get, session

LOG = get_logger(__name__)

LOBBY = "https://www.draftkings.com/lobby/getcontests?sport=NFL"
DRAFTABLES = "https://api.draftkings.com/draftgroups/v1/draftgroups/{group}/draftables"

#: DraftKings' contest type for NFL Classic.
CLASSIC = 21

#: Slates further out than this are skipped: their pools and salaries are
#: not final, and the week's capture will pick them up when they are.
HORIZON_DAYS = 8


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def classic_slates(lobby: dict, *, now: datetime | None = None, horizon_days: int = HORIZON_DAYS) -> pd.DataFrame:
    """The lobby's Classic draft groups starting within the horizon."""
    now = now or datetime.now(UTC)
    rows = []
    for group in lobby.get("DraftGroups", []) or []:
        if group.get("ContestTypeId") != CLASSIC:
            continue
        start = pd.to_datetime(group.get("StartDate"), utc=True, errors="coerce")
        if pd.isna(start) or start > pd.Timestamp(now) + timedelta(days=horizon_days):
            continue
        suffix = (group.get("ContestStartTimeSuffix") or "").strip().strip("()").strip()
        rows.append({
            "draft_group_id": int(group["DraftGroupId"]),
            "sport": "nfl",
            "label": suffix or "Main",
            "game_count": int(group.get("GameCount") or 0),
            "starts_at": start.isoformat(),
        })
    return pd.DataFrame(rows, columns=["draft_group_id", "sport", "label", "game_count", "starts_at"])


def player_pool(draftables: dict, group_id: int) -> pd.DataFrame:
    """One row per player in a Classic group: salary, position, team, game.

    DraftKings lists a player once per roster slot he fits (a running back
    appears again for FLEX); the salary is the same, so the first is kept.
    """
    rows = []
    for d in draftables.get("draftables", []) or []:
        if d.get("salary") is None or d.get("playerId") is None:
            continue
        game = d.get("competition") or {}
        rows.append({
            "draft_group_id": int(group_id),
            "player_id": int(d["playerId"]),
            "name": d.get("displayName"),
            "position": d.get("position"),
            "team": d.get("teamAbbreviation"),
            "salary": int(d["salary"]),
            "game": game.get("name"),
            "game_start": game.get("startTime"),
            # "None" is DraftKings' word for healthy; stored as empty.
            "status": "" if d.get("status") in (None, "None") else d.get("status"),
            "disabled": bool(d.get("isDisabled", False)),
        })
    frame = pd.DataFrame(rows, columns=["draft_group_id", "player_id", "name", "position", "team", "salary", "game",
                                        "game_start", "status", "disabled"])
    return frame.drop_duplicates(["draft_group_id", "player_id"], keep="first").reset_index(drop=True)


def capture(store=None, *, fetch=None, now: datetime | None = None) -> dict[str, int]:
    """Fetch the lobby and every Classic pool, and upsert them into the record.

    ``fetch(url) -> dict`` is injectable for tests. Returns counts; never raises.
    """
    if store is None:
        from atlas.live.store import Store

        store = Store.open()
    if fetch is None:
        sess = session()

        def fetch(url: str) -> dict:
            _guard_offline(url)
            return http_get(url, sess=sess, timeout=30).json()

    captured = _now() if now is None else now.replace(microsecond=0).isoformat()
    try:
        slates = classic_slates(fetch(LOBBY), now=now)
    except Exception as error:  # noqa: BLE001 - never fail the run
        LOG.warning("draftkings lobby unavailable: %s", error)
        return {"slates": 0, "players": 0}

    pools = []
    for group in slates["draft_group_id"]:
        try:
            pools.append(player_pool(fetch(DRAFTABLES.format(group=group)), group))
        except Exception as error:  # noqa: BLE001 - one slate must not cost the rest
            LOG.warning("draftkings group %s unavailable: %s", group, error)
    players = pd.concat(pools, ignore_index=True) if pools else pd.DataFrame()

    if not slates.empty:
        store.upsert("dfs_slates", slates.assign(captured_at=captured))
    if not players.empty:
        store.upsert("dfs_salaries", players.assign(captured_at=captured))
    LOG.info("draftkings: %d Classic slates, %d player salaries", len(slates), len(players))
    return {"slates": int(len(slates)), "players": int(len(players))}


def main() -> None:
    argparse.ArgumentParser(description="Capture DraftKings NFL Classic slates and salaries").parse_args()
    capture()


if __name__ == "__main__":
    main()
