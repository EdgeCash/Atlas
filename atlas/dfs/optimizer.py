"""DraftKings NFL Classic lineups: an integer program over a slate's pool.

Step 5 of `docs/MODEL_PLAN_DFS.md`. The problem is small and exact: choose
nine players - a quarterback, two running backs, three receivers, a tight
end, a FLEX (running back, receiver or tight end) and a defense - under the
$50,000 cap, each player once, maximizing projected points. SciPy's
``milp`` (HiGHS) solves it to optimality in well under a second.

Options, each a constraint in the same program:

* ``locks`` / ``excludes`` - players that must / must not appear;
* ``no_defense_vs_offense`` - a defense never faces its own lineup's offense;
* ``qb_stack`` - a quarterback brings at least this many of his own
  receivers and tight ends; ``bring_back`` - and one from the other side;
* ``max_per_team`` - at most this many players from one team (defense included);
* several lineups at once: ``n`` lineups, each at least ``min_unique``
  players different from every earlier one, no player in more than
  ``max_exposure`` of them.

What it maximizes is stated plainly: projected points. Nothing more.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy.optimize import Bounds, LinearConstraint, milp

SALARY_CAP = 50_000
ROSTER = 9
#: (position, minimum, maximum) - FLEX is the room between the minimums and nine.
SLOTS = {"QB": (1, 1), "RB": (2, 3), "WR": (3, 4), "TE": (1, 2), "DST": (1, 1)}
FLEX = ("RB", "WR", "TE")
#: DraftKings' upload file: its header, in slot order.
UPLOAD_SLOTS = ["QB", "RB", "RB", "WR", "WR", "WR", "TE", "FLEX", "DST"]
PASS_CATCHERS = ("WR", "TE")


@dataclass
class Options:
    locks: list = field(default_factory=list)
    excludes: list = field(default_factory=list)
    no_defense_vs_offense: bool = True
    qb_stack: int = 0
    bring_back: bool = False
    max_per_team: int = 8
    n: int = 1
    min_unique: int = 1
    max_exposure: float = 1.0
    cap: int = SALARY_CAP


class Infeasible(ValueError):
    """No lineup satisfies the options on this pool."""


def _check_pool(pool: pd.DataFrame) -> pd.DataFrame:
    need = {"id", "position", "salary", "team", "opponent", "projection"}
    missing = need - set(pool.columns)
    if missing:
        raise ValueError(f"pool lacks {sorted(missing)}")
    p = pool.dropna(subset=["projection", "salary"]).reset_index(drop=True)
    if p["id"].duplicated().any():
        raise ValueError("a player appears twice in the pool")
    return p


def _program(p: pd.DataFrame, opts: Options, earlier: list[set], banned: set):
    """The constraint rows and variable bounds for one lineup."""
    n = len(p)
    rows, lo, hi = [], [], []

    def add(coef, low, high):
        rows.append(coef)
        lo.append(low)
        hi.append(high)

    pos = p["position"].to_numpy()
    add(p["salary"].to_numpy(dtype=float), 0, opts.cap)
    add(np.ones(n), ROSTER, ROSTER)
    for position, (least, most) in SLOTS.items():
        add((pos == position).astype(float), least, most)
    teams = p["team"].to_numpy()
    for team in np.unique(teams):
        add((teams == team).astype(float), 0, opts.max_per_team)
    offense = pos != "DST"
    if opts.no_defense_vs_offense:
        # A defense d rules out every offensive player on the team it faces:
        # sum(those players) + 8 x_d <= 8.
        for i in np.flatnonzero(~offense):
            facing = (teams == p.at[i, "opponent"]) & offense
            if facing.any():
                coef = facing.astype(float)
                coef[i] = ROSTER - 1
                add(coef, 0, ROSTER - 1)
    if opts.qb_stack or opts.bring_back:
        catchers = np.isin(pos, PASS_CATCHERS)
        for i in np.flatnonzero(pos == "QB"):
            if opts.qb_stack:
                coef = ((teams == teams[i]) & catchers).astype(float)
                coef[i] = -opts.qb_stack
                add(coef, 0, np.inf)
            if opts.bring_back:
                coef = ((teams == p.at[i, "opponent"]) & offense & (pos != "QB")).astype(float)
                coef[i] = -1
                add(coef, 0, np.inf)
    ids = p["id"].to_numpy()
    for lineup in earlier:
        add(np.isin(ids, list(lineup)).astype(float), 0, ROSTER - opts.min_unique)
    lower = np.isin(ids, list(opts.locks)).astype(float)
    upper = np.where(np.isin(ids, list(opts.excludes) + list(banned)), 0.0, 1.0)
    if (lower > upper).any():
        raise Infeasible("a locked player is also excluded or at his exposure limit")
    return np.array(rows), np.array(lo), np.array(hi), Bounds(lower, upper)


def optimize(pool: pd.DataFrame, opts: Options | None = None) -> list[pd.DataFrame]:
    """``opts.n`` lineups, best first, each a frame of the pool's rows in upload slot order.

    ``pool`` needs ``id``, ``position`` (QB/RB/WR/TE/DST), ``salary``,
    ``team``, ``opponent`` and ``projection``. Raises :class:`Infeasible`
    when no lineup fits.
    """
    opts = opts or Options()
    p = _check_pool(pool)
    cap_each = max(1, math.floor(opts.max_exposure * opts.n + 1e-9))
    used: dict = {}
    lineups: list[pd.DataFrame] = []
    earlier: list[set] = []
    for _ in range(opts.n):
        banned = {pid for pid, count in used.items() if count >= cap_each}
        A, lo, hi, bounds = _program(p, opts, earlier, banned)
        res = milp(-p["projection"].to_numpy(dtype=float), constraints=LinearConstraint(A, lo, hi),
                   integrality=np.ones(len(p)), bounds=bounds)
        if res.status != 0 or res.x is None:
            if not lineups:
                raise Infeasible(res.message)
            break
        chosen = p[np.round(res.x).astype(int) == 1]
        lineup = assign_slots(chosen)
        lineups.append(lineup)
        earlier.append(set(chosen["id"]))
        for pid in chosen["id"]:
            used[pid] = used.get(pid, 0) + 1
    return lineups


def assign_slots(chosen: pd.DataFrame) -> pd.DataFrame:
    """Nine players in DraftKings' slot order. The FLEX is the extra player
    at whichever position has one - the latest to kick off where there is a
    choice, which keeps the most room for DraftKings' late swap."""
    chosen = chosen.copy()
    start = chosen["game_start"] if "game_start" in chosen else pd.Series("", index=chosen.index)
    chosen["_start"] = start.fillna("").astype(str)
    slots = []
    flex = None
    for position in FLEX:
        g = chosen[chosen["position"] == position].sort_values(["_start", "projection"], ascending=[True, False])
        least = SLOTS[position][0]
        if len(g) > least:
            flex = g.iloc[-1:]
            g = g.iloc[:-1]
        slots.append((position, g))
    out = [chosen[chosen["position"] == "QB"].assign(slot="QB")]
    for position, g in slots:
        out.append(g.assign(slot=position))
    if flex is not None:
        out.append(flex.assign(slot="FLEX"))
    out.append(chosen[chosen["position"] == "DST"].assign(slot="DST"))
    lineup = pd.concat(out).drop(columns="_start").reset_index(drop=True)
    if list(lineup["slot"]) != UPLOAD_SLOTS:
        raise ValueError(f"not a Classic lineup: {list(lineup['slot'])}")
    return lineup


def valid(lineup: pd.DataFrame, opts: Options | None = None) -> list[str]:
    """Every rule the lineup breaks; empty when it is legal under ``opts``."""
    opts = opts or Options()
    problems = []
    if len(lineup) != ROSTER:
        problems.append(f"{len(lineup)} players")
    if lineup["id"].duplicated().any():
        problems.append("a player twice")
    if lineup["salary"].sum() > opts.cap:
        problems.append(f"salary {lineup['salary'].sum()}")
    counts = lineup["position"].value_counts()
    for position, (least, most) in SLOTS.items():
        if not least <= counts.get(position, 0) <= most:
            problems.append(f"{counts.get(position, 0)} {position}")
    if lineup["team"].value_counts().max() > opts.max_per_team:
        problems.append("too many from one team")
    if opts.no_defense_vs_offense:
        for _, d in lineup[lineup["position"] == "DST"].iterrows():
            if ((lineup["team"] == d["opponent"]) & (lineup["position"] != "DST")).any():
                problems.append(f"{d['team']} defense faces its own offense")
    for qb in lineup[lineup["position"] == "QB"].itertuples():
        mates = lineup[(lineup["team"] == qb.team) & lineup["position"].isin(PASS_CATCHERS)]
        if len(mates) < opts.qb_stack:
            problems.append("quarterback stack short")
        if opts.bring_back and not ((lineup["team"] == qb.opponent) & ~lineup["position"].isin(["QB", "DST"])).any():
            problems.append("no bring-back")
    if not set(opts.locks) <= set(lineup["id"]):
        problems.append("a lock is missing")
    if set(opts.excludes) & set(lineup["id"]):
        problems.append("an excluded player")
    return problems


def upload_csv(lineups: list[pd.DataFrame], id_column: str = "draftable_id") -> str:
    """DraftKings' upload file: the slot header, then one row of ids per lineup."""
    lines = [",".join(UPLOAD_SLOTS)]
    for lineup in lineups:
        lines.append(",".join(str(int(v)) for v in lineup[id_column]))
    return "\n".join(lines) + "\n"
