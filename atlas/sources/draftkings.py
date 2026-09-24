"""DraftKings slates and salaries - NFL Classic, Showdown and Tiers; college Classic and Showdown.

    python -m atlas.sources.draftkings            # capture today's slates

Step 0 of `docs/MODEL_PLAN_DFS.md`. A salary is DraftKings' own number for
a player's week - the market the DFS model is measured against - and
DraftKings does not keep past slates, so a day not captured is a day lost.
The capture runs in the heavy refresh and writes to the committed tracking
store (``dfs_slates``, ``dfs_salaries``), which is also its backup.

Two public JSON endpoints, no key, undocumented:

* the lobby lists every current draft group (slate) - its contest type,
  games and start;
* a group's draftables are its player pool with salaries.

Three formats are kept: Classic (contest type 21: the $50,000 cap, QB / 2 RB
/ 3 WR / TE / FLEX / DST), Showdown Captain Mode (96: one game, a Captain at
1.5 times salary and points and five FLEX, kickers included) and Tiers (51:
one player from each of six tiers, no salary). The main slate is the Classic
group DraftKings leaves unlabeled; the rest carry a label.

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

LOBBY_URL = "https://www.draftkings.com/lobby/getcontests?sport={sport}"
LOBBY = LOBBY_URL.format(sport="NFL")
DRAFTABLES = "https://api.draftkings.com/draftgroups/v1/draftgroups/{group}/draftables"

#: DraftKings' contest types for the NFL formats Atlas builds for: the
#: salary-cap games and Tiers. Snake and Best Ball are drafts against other
#: people, the in-game Showdowns open mid-game, Madden is a video game and
#: Single Stat is not a lineup, so none of those is captured.
CLASSIC, SHOWDOWN, TIERS = 21, 96, 51
GAME_TYPES = {CLASSIC: "Classic", SHOWDOWN: "Showdown", TIERS: "Tiers"}
#: College (DraftKings' "CFB"): Classic (94: QB / 2 RB / 3 WR / FLEX /
#: SUPERFLEX, no tight end or defense) and Showdown (95: a Captain and five
#: UTIL, kickers included). Captured from the start of the college DFS work
#: (`docs/MODEL_PLAN_DFS_CFB.md`, step 0): DraftKings keeps no history.
CFB_CLASSIC, CFB_SHOWDOWN = 94, 95
SPORTS = {
    "nfl": ("NFL", GAME_TYPES),
    "cfb": ("CFB", {CFB_CLASSIC: "Classic", CFB_SHOWDOWN: "Showdown"}),
}

#: Slates further out than this are skipped: their pools and salaries are
#: not final, and the week's capture will pick them up when they are.
HORIZON_DAYS = 8


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


SLATE_COLUMNS = ["draft_group_id", "sport", "label", "game_count", "starts_at", "game_type"]


def slates(lobby: dict, *, now: datetime | None = None, horizon_days: int = HORIZON_DAYS,
           types: tuple[int, ...] = tuple(GAME_TYPES), sport: str = "nfl") -> pd.DataFrame:
    """The lobby's draft groups of these contest types starting within the horizon.

    A Classic group's label is DraftKings' suffix ("Thu-Mon", "Early Only"),
    or "Main" for the one it leaves unlabeled; a Showdown's is its game
    ("ATL @ GB"); Tiers is "Tiers"."""
    now = now or datetime.now(UTC)
    names = SPORTS[sport][1]
    rows = []
    for group in lobby.get("DraftGroups", []) or []:
        kind = group.get("ContestTypeId")
        if kind not in types or kind not in names:
            continue
        start = pd.to_datetime(group.get("StartDate"), utc=True, errors="coerce")
        if pd.isna(start) or start > pd.Timestamp(now) + timedelta(days=horizon_days):
            continue
        suffix = (group.get("ContestStartTimeSuffix") or "").strip().strip("()").strip()
        kind_name = names[kind]
        label = {"Classic": suffix or "Main", "Showdown": suffix or "Showdown", "Tiers": "Tiers"}[kind_name]
        rows.append({
            "draft_group_id": int(group["DraftGroupId"]), "sport": sport, "label": label,
            "game_count": int(group.get("GameCount") or 0), "starts_at": start.isoformat(),
            "game_type": kind_name,
        })
    return pd.DataFrame(rows, columns=SLATE_COLUMNS)


def classic_slates(lobby: dict, *, now: datetime | None = None, horizon_days: int = HORIZON_DAYS) -> pd.DataFrame:
    """The lobby's Classic draft groups starting within the horizon."""
    return slates(lobby, now=now, horizon_days=horizon_days, types=(CLASSIC,)).drop(columns=["game_type"])


POOL_COLUMNS = ["draft_group_id", "player_id", "draftable_id", "name", "position", "team", "salary", "game",
                "game_start", "status", "disabled", "cpt_salary", "cpt_draftable_id", "tier"]


def player_pool(draftables: dict, group_id: int) -> pd.DataFrame:
    """One row per player in a group: salary, position, team, game.

    DraftKings lists a player once per roster slot he fits, each listing
    with its own draftable id:

    * Classic: a running back again for FLEX, at the same salary. The first
      listing is kept - its draftable id is the one DraftKings' own salary
      file carries, and the upload file accepts it in any slot he fits.
    * Showdown: once as Captain (1.5 times the salary and the points) and
      once as FLEX. The FLEX listing is the row; the Captain's salary and
      draftable id ride along as ``cpt_salary`` and ``cpt_draftable_id``.
    * Tiers: no salary; each player sits in one tier, numbered from the
      lowest roster slot (T1) up.
    """
    listings: dict[int, list[dict]] = {}
    for d in draftables.get("draftables", []) or []:
        if d.get("playerId") is None:
            continue
        listings.setdefault(int(d["playerId"]), []).append(d)
    slots = sorted({d.get("rosterSlotId") for ds in listings.values() for d in ds if d.get("rosterSlotId") is not None})
    tiers = all(d.get("salary") is None for ds in listings.values() for d in ds) and len(slots) > 1
    rows = []
    for pid, ds in listings.items():
        priced = [d for d in ds if d.get("salary") is not None]
        if not priced and not tiers:
            continue
        cpt = None
        if len(priced) > 1 and len({d["salary"] for d in priced}) > 1:
            cpt = max(priced, key=lambda d: d["salary"])          # Showdown: the Captain costs 1.5x
            first = min(priced, key=lambda d: d["salary"])
        else:
            first = (priced or ds)[0]
        game = first.get("competition") or {}
        rows.append({
            "draft_group_id": int(group_id), "player_id": pid,
            "draftable_id": int(first["draftableId"]) if first.get("draftableId") is not None else None,
            "name": first.get("displayName"), "position": first.get("position"),
            "team": first.get("teamAbbreviation"),
            "salary": int(first["salary"]) if first.get("salary") is not None else None,
            "game": game.get("name"), "game_start": game.get("startTime"),
            # "None" is DraftKings' word for healthy; stored as empty.
            "status": "" if first.get("status") in (None, "None") else first.get("status"),
            "disabled": bool(first.get("isDisabled", False)),
            "cpt_salary": int(cpt["salary"]) if cpt is not None else None,
            "cpt_draftable_id": int(cpt["draftableId"]) if cpt is not None and cpt.get("draftableId") else None,
            "tier": slots.index(first.get("rosterSlotId")) + 1 if tiers and first.get("rosterSlotId") in slots else None,
        })
    return pd.DataFrame(rows, columns=POOL_COLUMNS).reset_index(drop=True)


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
    found = []
    for sport, (code, names) in SPORTS.items():
        try:
            found.append(slates(fetch(LOBBY_URL.format(sport=code)), now=now, types=tuple(names), sport=sport))
        except Exception as error:  # noqa: BLE001 - never fail the run
            LOG.warning("draftkings %s lobby unavailable: %s", code, error)
    groups = pd.concat(found, ignore_index=True) if found else pd.DataFrame(columns=SLATE_COLUMNS)
    if groups.empty:
        return {"slates": 0, "players": 0}

    pools = []
    for group in groups["draft_group_id"]:
        try:
            pools.append(player_pool(fetch(DRAFTABLES.format(group=group)), group))
        except Exception as error:  # noqa: BLE001 - one slate must not cost the rest
            LOG.warning("draftkings group %s unavailable: %s", group, error)
    players = pd.concat(pools, ignore_index=True) if pools else pd.DataFrame()

    if not groups.empty:
        store.upsert("dfs_slates", groups.assign(captured_at=captured))
    if not players.empty:
        store.upsert("dfs_salaries", players.assign(captured_at=captured))
    kinds = (groups["sport"] + " " + groups["game_type"]).value_counts().to_dict() if not groups.empty else {}
    LOG.info("draftkings: %d slates %s, %d player rows", len(groups), kinds, len(players))
    return {"slates": int(len(groups)), "players": int(len(players))}


def main() -> None:
    argparse.ArgumentParser(description="Capture DraftKings NFL and college slates and salaries").parse_args()
    capture()


if __name__ == "__main__":
    main()
