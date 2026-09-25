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


@dataclass(frozen=True)
class Roster:
    """A Classic lineup's shape: how many players, how many at each position,
    the upload file's slots in order, and which positions each flexible slot
    takes (in the order they are filled - the narrowest first)."""
    size: int
    bounds: dict
    slots: tuple
    flex: tuple                   # ((slot name, positions), ...)


#: NFL Classic: QB, 2 RB, 3 WR, TE, FLEX (RB/WR/TE), DST.
NFL_CLASSIC = Roster(ROSTER, SLOTS, tuple(UPLOAD_SLOTS), (("FLEX", FLEX),))
#: College Classic: QB, 2 RB, 3 WR, FLEX (RB/WR) and S-FLEX (QB/RB/WR); no
#: tight end slot (DraftKings lists them as receivers) and no defense.
CFB_CLASSIC = Roster(8, {"QB": (1, 2), "RB": (2, 4), "WR": (3, 5)},
                     ("QB", "RB", "RB", "WR", "WR", "WR", "FLEX", "S-FLEX"),
                     (("FLEX", ("RB", "WR")), ("S-FLEX", ("QB", "RB", "WR"))))


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
    roster: Roster = NFL_CLASSIC


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
    size = opts.roster.size
    add(p["salary"].to_numpy(dtype=float), 0, opts.cap)
    add(np.ones(n), size, size)
    for position, (least, most) in opts.roster.bounds.items():
        add((pos == position).astype(float), least, most)
    add(~np.isin(pos, list(opts.roster.bounds)), 0, 0)          # no one the roster has no slot for
    teams = p["team"].to_numpy()
    for team in np.unique(teams):
        add((teams == team).astype(float), 0, opts.max_per_team)
    # DraftKings: players from at least two games - so never all nine from one.
    games = _games(p)
    for game in np.unique(games):
        add((games == game).astype(float), 0, size - 1)
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
        add(np.isin(ids, list(lineup)).astype(float), 0, size - opts.min_unique)
    lower = np.isin(ids, list(opts.locks)).astype(float)
    upper = np.where(np.isin(ids, list(opts.excludes) + list(banned)), 0.0, 1.0)
    if (lower > upper).any():
        raise Infeasible("a locked player is also excluded or at his exposure limit")
    return np.array(rows), np.array(lo), np.array(hi), Bounds(lower, upper)


def _games(p: pd.DataFrame) -> np.ndarray:
    """Each player's game, named by its two teams in order."""
    return np.array([" v ".join(sorted((str(t), str(o)))) for t, o in zip(p["team"], p["opponent"], strict=True)])


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
        try:
            A, lo, hi, bounds = _program(p, opts, earlier, banned)
        except Infeasible:
            # A locked player at his exposure cap: the lineups already built stand.
            if not lineups:
                raise
            break
        res = milp(-p["projection"].to_numpy(dtype=float), constraints=LinearConstraint(A, lo, hi),
                   integrality=np.ones(len(p)), bounds=bounds)
        if res.status != 0 or res.x is None:
            if not lineups:
                raise Infeasible(res.message)
            break
        chosen = p[np.round(res.x).astype(int) == 1]
        lineup = assign_slots(chosen, opts.roster)
        lineups.append(lineup)
        earlier.append(set(chosen["id"]))
        for pid in chosen["id"]:
            used[pid] = used.get(pid, 0) + 1
    return lineups


def assign_slots(chosen: pd.DataFrame, roster: Roster = NFL_CLASSIC) -> pd.DataFrame:
    """The lineup in DraftKings' slot order. Each position's fixed slots take
    its earliest kickoffs; the flexible slots take what is left - the latest
    to kick off, which keeps the most room for DraftKings' late swap."""
    chosen = chosen.copy()
    start = chosen["game_start"] if "game_start" in chosen else pd.Series("", index=chosen.index)
    chosen["_start"] = start.fillna("").astype(str)
    chosen = chosen.sort_values(["_start", "projection"], ascending=[True, False])
    fixed = {slot: roster.slots.count(slot) for slot in dict.fromkeys(roster.slots)
             if slot not in {name for name, _ in roster.flex}}
    placed: dict[str, list] = {}
    left = chosen
    for slot, count in fixed.items():
        take = left[left["position"] == slot].head(count)
        placed[slot] = [row for _, row in take.iterrows()]
        left = left.drop(take.index)
    for name, eligible in roster.flex:
        take = left[left["position"].isin(eligible)].tail(roster.slots.count(name))
        placed[name] = [row for _, row in take.iterrows()]
        left = left.drop(take.index)
    rows = []
    for slot in roster.slots:
        if not placed.get(slot):
            raise ValueError(f"not a Classic lineup: no player for {slot}")
        rows.append(placed[slot].pop(0).copy())
        rows[-1]["slot"] = slot
    if len(left):
        raise ValueError("not a Classic lineup: players left over")
    return pd.DataFrame(rows).drop(columns="_start").reset_index(drop=True)


def valid(lineup: pd.DataFrame, opts: Options | None = None) -> list[str]:
    """Every rule the lineup breaks; empty when it is legal under ``opts``."""
    opts = opts or Options()
    problems = []
    if len(lineup) != opts.roster.size:
        problems.append(f"{len(lineup)} players")
    if lineup["id"].duplicated().any():
        problems.append("a player twice")
    if lineup["salary"].sum() > opts.cap:
        problems.append(f"salary {lineup['salary'].sum()}")
    counts = lineup["position"].value_counts()
    for position, (least, most) in opts.roster.bounds.items():
        if not least <= counts.get(position, 0) <= most:
            problems.append(f"{counts.get(position, 0)} {position}")
    if "slot" in lineup and list(lineup["slot"]) != list(opts.roster.slots):
        problems.append(f"slots {list(lineup['slot'])}")
    for name, eligible in opts.roster.flex:
        if "slot" in lineup and not lineup.loc[lineup["slot"] == name, "position"].isin(eligible).all():
            problems.append(f"{name} holds a position it cannot")
    if lineup["team"].value_counts().max() > opts.max_per_team:
        problems.append("too many from one team")
    if len(set(_games(lineup))) < 2:
        problems.append("one game only")
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


# ---------------------------------------------------------------------------
# Showdown Captain Mode and Tiers
# ---------------------------------------------------------------------------

SHOWDOWN_SLOTS = ["CPT", "FLEX", "FLEX", "FLEX", "FLEX", "FLEX"]
SHOWDOWN_SIZE = 6
CAPTAIN = 1.5                      # the Captain's points and salary
TIER_COUNT = 6
TIER_SLOTS = [f"T{i}" for i in range(1, TIER_COUNT + 1)]


class _Rows:
    """Constraint rows for one program: ``lo <= coef @ x <= hi``."""

    def __init__(self):
        self.rows, self.lo, self.hi = [], [], []

    def add(self, coef, low, high) -> None:
        self.rows.append(np.asarray(coef, dtype=float))
        self.lo.append(low)
        self.hi.append(high)

    def solve(self, objective: np.ndarray, lower: np.ndarray, upper: np.ndarray):
        res = milp(-objective, constraints=LinearConstraint(np.array(self.rows), self.lo, self.hi),
                   integrality=np.ones(len(objective)), bounds=Bounds(lower, upper))
        return None if res.status != 0 or res.x is None else np.round(res.x).astype(int)


def showdown(pool: pd.DataFrame, opts: Options | None = None, *, flex_label: str = "FLEX") -> list[pd.DataFrame]:
    """Showdown Captain Mode: one game, a Captain and five FLEX under the cap.

    The Captain scores 1.5 times his points and costs his Captain salary
    (``cpt_salary``, DraftKings' own, 1.5 times his FLEX ``salary``). Every
    position may play either slot, kickers and defenses included; a player
    plays one slot at most; DraftKings requires players from both teams.
    ``opts`` uses the same locks, excludes, n, min_unique and max_exposure.
    """
    opts = opts or Options()
    p = pool.dropna(subset=["projection", "salary", "cpt_salary"]).reset_index(drop=True)
    n = len(p)
    ids = p["id"].to_numpy()
    proj = p["projection"].to_numpy(dtype=float)
    objective = np.r_[CAPTAIN * proj, proj]                        # [captain_i..., flex_i...]
    cap_each = max(1, math.floor(opts.max_exposure * opts.n + 1e-9))
    used: dict = {}
    lineups, earlier = [], []
    for _ in range(opts.n):
        c = _Rows()
        add = c.add
        add(np.r_[np.ones(n), np.zeros(n)], 1, 1)
        add(np.r_[np.zeros(n), np.ones(n)], SHOWDOWN_SIZE - 1, SHOWDOWN_SIZE - 1)
        add(np.r_[p["cpt_salary"].to_numpy(dtype=float), p["salary"].to_numpy(dtype=float)], 0, opts.cap)
        for i in range(n):
            coef = np.zeros(2 * n)
            coef[i] = coef[n + i] = 1
            add(coef, 0, 1)
        teams = p["team"].to_numpy()
        for team in np.unique(teams):
            m = (teams == team).astype(float)
            add(np.r_[m, m], 0, SHOWDOWN_SIZE - 1)             # both teams: never all six from one
        for lineup in earlier:
            m = np.isin(ids, list(lineup)).astype(float)
            add(np.r_[m, m], 0, SHOWDOWN_SIZE - opts.min_unique)
        banned = {pid for pid, count in used.items() if count >= cap_each}
        for pid in opts.locks:
            m = (ids == pid).astype(float)
            add(np.r_[m, m], 1, 1)
        upper = np.where(np.isin(ids, list(opts.excludes) + list(banned)), 0.0, 1.0)
        if set(opts.locks) & (set(opts.excludes) | banned):
            if not lineups:
                raise Infeasible("a locked player is also excluded or at his exposure limit")
            break
        x = c.solve(objective, np.zeros(2 * n), np.r_[upper, upper])
        if x is None:
            if not lineups:
                raise Infeasible("no Showdown lineup fits")
            break
        cpt = p[x[:n] == 1].assign(slot="CPT")
        cpt = cpt.assign(salary=cpt["cpt_salary"], projection=CAPTAIN * cpt["projection"],
                         draftable_id=cpt["cpt_draftable_id"])
        for col in ("low", "high"):                        # his range scales with his points
            if col in cpt:
                cpt[col] = CAPTAIN * cpt[col]
        flex = p[x[n:] == 1].sort_values("projection", ascending=False).assign(slot=flex_label)
        lineup = pd.concat([cpt, flex]).reset_index(drop=True)
        lineups.append(lineup)
        earlier.append(set(lineup["id"]))
        for pid in lineup["id"]:
            used[pid] = used.get(pid, 0) + 1
    return lineups


def valid_showdown(lineup: pd.DataFrame, opts: Options | None = None, *, flex_label: str = "FLEX") -> list[str]:
    opts = opts or Options()
    problems = []
    if list(lineup["slot"]) != ["CPT"] + [flex_label] * (SHOWDOWN_SIZE - 1):
        problems.append(f"slots {list(lineup['slot'])}")
    if lineup["id"].duplicated().any():
        problems.append("a player twice")
    if lineup["salary"].sum() > opts.cap:
        problems.append(f"salary {lineup['salary'].sum()}")
    if lineup["team"].nunique() < 2:
        problems.append("one team only")
    return problems


def tiers(pool: pd.DataFrame, opts: Options | None = None) -> list[pd.DataFrame]:
    """Tiers: one player from each tier, no salary, players from at least two games."""
    opts = opts or Options()
    p = pool.dropna(subset=["projection", "tier"]).reset_index(drop=True)
    ids = p["id"].to_numpy()
    tier = p["tier"].astype(int).to_numpy()
    games = _games(p)
    cap_each = max(1, math.floor(opts.max_exposure * opts.n + 1e-9))
    used: dict = {}
    lineups, earlier = [], []
    for _ in range(opts.n):
        c = _Rows()
        for t in range(1, TIER_COUNT + 1):
            c.add(tier == t, 1, 1)
        for game in np.unique(games):
            c.add(games == game, 0, TIER_COUNT - 1)            # at least two games
        for lineup in earlier:
            c.add(np.isin(ids, list(lineup)), 0, TIER_COUNT - opts.min_unique)
        banned = {pid for pid, count in used.items() if count >= cap_each}
        lower = np.isin(ids, list(opts.locks)).astype(float)
        upper = np.where(np.isin(ids, list(opts.excludes) + list(banned)), 0.0, 1.0)
        if (lower > upper).any():
            if not lineups:
                raise Infeasible("a locked player is also excluded or at his exposure limit")
            break
        x = c.solve(p["projection"].to_numpy(dtype=float), lower, upper)
        if x is None:
            if not lineups:
                raise Infeasible("no Tiers lineup fits")
            break
        lineup = p[x == 1].sort_values("tier").assign(slot=lambda d: "T" + d["tier"].astype(int).astype(str))
        lineups.append(lineup.reset_index(drop=True))
        earlier.append(set(lineup["id"]))
        for pid in lineup["id"]:
            used[pid] = used.get(pid, 0) + 1
    return lineups


def valid_tiers(lineup: pd.DataFrame) -> list[str]:
    problems = []
    if list(lineup["slot"]) != TIER_SLOTS:
        problems.append(f"slots {list(lineup['slot'])}")
    if len(set(_games(lineup))) < 2:
        problems.append("one game only")
    return problems


#: Each sport's Showdown slot name beside the Captain: DraftKings calls it
#: FLEX in the NFL and UTIL in college.
SHOWDOWN_FLEX = {"nfl": "FLEX", "cfb": "UTIL"}


def upload(lineups: list[pd.DataFrame], game_type: str = "Classic", sport: str = "nfl") -> str:
    """DraftKings' upload file for any format, either sport."""
    header = {
        ("nfl", "Classic"): UPLOAD_SLOTS, ("nfl", "Showdown"): SHOWDOWN_SLOTS, ("nfl", "Tiers"): TIER_SLOTS,
        ("cfb", "Classic"): list(CFB_CLASSIC.slots), ("cfb", "Showdown"): ["CPT"] + ["UTIL"] * (SHOWDOWN_SIZE - 1),
    }[(sport, game_type)]
    lines = [",".join(header)]
    for lineup in lineups:
        lines.append(",".join(str(int(v)) for v in lineup["draftable_id"]))
    return "\n".join(lines) + "\n"
