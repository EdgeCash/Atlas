"""The prop ledger: every NHL PrizePicks line the pick'em prices, logged once a day and scored three ways.

The pick'em logs only its picks, the lines where the books' fair probability
clears 54%: exactly the lines PrizePicks set loosely, and so no test of
whether Atlas's player projections (`atlas/models/nhl_props.py`) beat a line
PrizePicks actually set. The ledger logs **every** standard NHL line on the
slate (More and Less both offered), pick or not, with the books' fair
probability of the likelier side, Atlas's probability of the same side where
it has the player, and the actual from ESPN's box score once the game is
final. Then, per stat, on the same lines: the Brier and log loss of fair, of
Atlas, and of 0.50 (the line as PrizePicks set it, a coin flip), the paired
difference with its 95% interval, and the hit rate of each one's side.

Two tests are pre-registered and judged from the same scores, each at its
own size and not before: saves (`docs/NHL_SAVES_PREREGISTRATION.md`), where
the walk-forward found a large edge over a season-mean baseline, at
:data:`SAVES_N` decided goalie lines; and shots on goal
(`docs/NHL_SHOTS_PREREGISTRATION.md`), where the edge was small and the
lines are many, at :data:`SHOTS_N`.
Logged at the first run from 10:00 ET, like the picks; sealed in
``tracking/owner_prop_ledger/`` by the ISO week of puck drop; shown only
inside the owner page's ciphertext, on the Pick'em tab.
"""

from __future__ import annotations

import json
import math
import uuid
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from atlas.owner import pickem, sealed
from atlas.util import get_logger

LOG = get_logger(__name__)

NAMESPACE = uuid.UUID("c47e9b02-1d3a-4f58-9e6b-7a2c0d5f8b14")
SPORT = "nhl"
COLUMNS = ["ledger_id", "day", "logged_at", "sport", "season", "week", "game_id", "kickoff", "game", "player_key",
           "player", "team", "position", "market", "side", "line", "p", "p_push", "books", "p_atlas", "actual",
           "outcome", "graded_at"]
#: The pre-registered tests: judged at the first count of decided lines with an Atlas probability, failed at
#: the second if Atlas is still no better than the coin flip. Shots need more: the edge expected is smaller.
SAVES_N, SAVES_FAIL_N = 300, 500
SHOTS_N, SHOTS_FAIL_N = 1000, 2000
TESTS = {"sv": ("Saves", SAVES_N, SAVES_FAIL_N), "sog": ("Shots on goal", SHOTS_N, SHOTS_FAIL_N)}
#: The bet-shaped bar: PrizePicks' two-pick Power break-even per pick.
BET_BAR = pickem.break_even("power", 2)
#: Stats by the pick'em's code (`pickem.STATS`), saves first, with the words shown for each.
ORDER = ("sv", "sog", "pts", "g", "a", "blk", "hits")
LABELS = {"sv": "saves", "sog": "shots on goal", "pts": "points", "g": "goals", "a": "assists",
          "blk": "blocked shots", "hits": "hits"}
SAVES = "sv"


def path() -> Path:
    from atlas.live.store import tracking_dir

    return tracking_dir() / "owner_prop_ledger"


def ledger_id(day, event_id, player_key, market) -> str:
    return str(uuid.uuid5(NAMESPACE, f"{day}|{event_id}|{player_key}|{market}"))


def load(passphrase: str, where: Path | None = None) -> pd.DataFrame:
    rows = sealed.load(where or path(), passphrase)
    return pd.DataFrame(rows, columns=COLUMNS) if rows else pd.DataFrame(columns=COLUMNS)


def seal(ledger: pd.DataFrame, passphrase: str, weeks: set, where: Path | None = None) -> list[Path]:
    where = where or path()
    out = []
    for season, week in sorted(weeks):
        part = ledger[(pd.to_numeric(ledger["season"]) == season) & (pd.to_numeric(ledger["week"]) == week)]
        rows = json.loads(part.reindex(columns=COLUMNS).to_json(orient="records"))
        names = [r.get(k) for r in rows for k in ("player", "game")]
        out.append(sealed.seal(rows, passphrase, sealed.week_file(where, season, week), names=names))
    return out


def due(ledger: pd.DataFrame, day: str, now: datetime) -> bool:
    """The pick'em's moment: at or after 10:00 ET on the slate's day, nothing logged for it yet."""
    return pickem.due(ledger, day, now)


def log(ledger: pd.DataFrame, priced: pd.DataFrame, names: dict, now: datetime) -> tuple[pd.DataFrame, set]:
    """Every priced NHL standard line on the slate, at the line and probabilities shown; never revised.
    Returns the ledger and the (year, ISO week) files touched."""
    if priced.empty:
        return ledger, set()
    nhl = priced[priced["sport"].astype(str) == SPORT]
    if nhl.empty:
        return ledger, set()
    stamp = pickem._stamp(now)
    rows = []
    for r in nhl.itertuples():
        season, week = pickem.filed(SPORT, r.kickoff)
        rows.append({"ledger_id": ledger_id(r.day, r.event_id, r.player_key, r.market), "day": str(r.day),
                     "logged_at": stamp, "sport": SPORT, "season": season, "week": week, "game_id": str(r.game_id),
                     "kickoff": pickem._stamp(r.kickoff), "game": names.get(str(r.game_id), str(r.game_id)),
                     "player_key": str(r.player_key), "player": r.player, "team": r.team, "position": r.position,
                     "market": r.market, "side": r.side, "line": float(r.line), "p": round(float(r.p), 4),
                     "p_push": round(float(r.p_push), 4), "books": int(r.books),
                     "p_atlas": round(float(r.p_atlas), 4) if pd.notna(r.p_atlas) else None,
                     "actual": None, "outcome": None, "graded_at": None})
    new = pd.DataFrame(rows, columns=COLUMNS)
    if len(ledger):
        new = new[~new["ledger_id"].isin(set(ledger["ledger_id"]))]
    if new.empty:
        return ledger, set()
    weeks = {(int(a), int(b)) for a, b in new[["season", "week"]].drop_duplicates().itertuples(index=False)}
    parts = [ledger.reindex(columns=COLUMNS), new] if len(ledger) else [new]
    return pd.concat(parts, ignore_index=True).reindex(columns=COLUMNS), weeks


def grade(ledger: pd.DataFrame, games: pd.DataFrame, now: datetime, box=pickem.box_score) -> tuple[pd.DataFrame, set]:
    """Settle each open line whose game is final from the box score, as the picks are settled."""
    return pickem.grade(ledger, games, now, box)


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def _stat(market) -> str:
    return pickem.STATS.get(str(market), str(market))


def score(ledger: pd.DataFrame) -> pd.DataFrame:
    """Per stat, on the decided lines (a tie or a void says nothing): how many, the Brier and log loss of the
    books' fair probability, of Atlas's and of 0.50, the paired Brier difference Atlas minus fair with its 95%
    interval, and the hit rate of fair's side and of Atlas's. The Atlas columns are on the lines Atlas priced."""
    cols = ["stat", "lines", "with_atlas", "brier_fair", "brier_atlas", "brier_half", "logloss_fair", "logloss_atlas",
            "logloss_half", "diff", "diff_low", "diff_high", "hit_fair", "hit_atlas"]
    if ledger.empty:
        return pd.DataFrame(columns=cols)
    d = ledger[ledger["outcome"].isin(["win", "loss"])].copy()
    if d.empty:
        return pd.DataFrame(columns=cols)
    d["won"] = (d["outcome"] == "win").astype(float)
    d["p"] = pd.to_numeric(d["p"], errors="coerce").clip(1e-6, 1 - 1e-6)
    d["p_atlas"] = pd.to_numeric(d["p_atlas"], errors="coerce").clip(1e-6, 1 - 1e-6)
    d["stat"] = d["market"].map(_stat)
    rows = []
    ll = lambda p, y: -(y * np.log(p) + (1 - y) * np.log(1 - p))  # noqa: E731
    for stat, part in d.groupby("stat"):
        a = part[part["p_atlas"].notna()]
        row = {"stat": stat, "lines": len(part), "with_atlas": len(a),
               "brier_fair": float(((part["p"] - part["won"]) ** 2).mean()),
               "brier_half": 0.25, "logloss_fair": float(ll(part["p"], part["won"]).mean()),
               "logloss_half": float(math.log(2)), "hit_fair": float(part["won"].mean()),
               "brier_atlas": np.nan, "logloss_atlas": np.nan, "diff": np.nan, "diff_low": np.nan,
               "diff_high": np.nan, "hit_atlas": np.nan}
        if len(a):
            sq_a, sq_f = (a["p_atlas"] - a["won"]) ** 2, (a["p"] - a["won"]) ** 2
            diff = sq_a - sq_f
            half = 1.96 * float(diff.std(ddof=1)) / math.sqrt(len(a)) if len(a) > 1 else float("nan")
            # Atlas's side is the logged side where it gives that side the better chance, else the other.
            atlas_side_won = np.where(a["p_atlas"] >= 0.5, a["won"], 1 - a["won"])
            row.update({"brier_atlas": float(sq_a.mean()), "logloss_atlas": float(ll(a["p_atlas"], a["won"]).mean()),
                        "diff": float(diff.mean()), "diff_low": float(diff.mean() - half),
                        "diff_high": float(diff.mean() + half), "hit_atlas": float(atlas_side_won.mean())})
        rows.append(row)
    out = pd.DataFrame(rows, columns=cols)
    order = {s: i for i, s in enumerate(ORDER)}
    return out.assign(_o=out["stat"].map(lambda s: order.get(s, len(order)))).sort_values(["_o", "stat"]) \
        .drop(columns="_o").reset_index(drop=True)


def verdict(scores: pd.DataFrame, stat: str = SAVES) -> str:
    """A pre-registered test (:data:`TESTS`), read from the scores: collecting, clears, not proven, or fails.
    The same three bars for each: beats fair with the paired interval below zero, beats the coin flip, and its
    side hits PrizePicks' two-pick break-even."""
    name, judged_at, fail_at = TESTS[stat]
    what = "goalie lines" if stat == SAVES else "lines"
    s = scores[scores["stat"] == stat]
    if s.empty or not s["with_atlas"].iloc[0]:
        return f"{name}: collecting, 0 of {judged_at} decided {what} with an Atlas probability."
    r = s.iloc[0]
    n = int(r["with_atlas"])
    if n < judged_at:
        return (f"{name}: collecting, {n} of {judged_at} decided {what} with an Atlas probability. Nothing is "
                "read before then.")
    better_than_fair = r["diff_high"] < 0
    better_than_half = r["brier_atlas"] < 0.25
    bet = r["hit_atlas"] >= BET_BAR
    if better_than_fair and better_than_half and bet:
        return (f"{name}: clears at {n}. Atlas's Brier {r['brier_atlas']:.4f} beats fair's {r['brier_fair']:.4f} "
                f"(paired 95% interval {r['diff_low']:+.4f} to {r['diff_high']:+.4f}) and the coin flip, and its "
                f"side hits {r['hit_atlas']:.1%} against a {BET_BAR:.1%} break-even.")
    if not better_than_fair or (n >= fail_at and not better_than_half):
        why = ("no better than fair's probability" if not better_than_fair else
               f"no better than the coin flip at {n}")
        return f"{name}: fails at {n}: Atlas's Brier {r['brier_atlas']:.4f} is {why}."
    return (f"{name}: not proven at {n}. Atlas's Brier {r['brier_atlas']:.4f} against fair's {r['brier_fair']:.4f} "
            f"and 0.25; its side hits {r['hit_atlas']:.1%} against a {BET_BAR:.1%} break-even. "
            + (f"Judged again at {fail_at}." if n < fail_at else ""))


# ---------------------------------------------------------------------------
# The owner page's view
# ---------------------------------------------------------------------------


def _f(x, fmt: str = "{:.4f}") -> str:
    try:
        return "–" if x is None or not math.isfinite(float(x)) else fmt.format(float(x))
    except (TypeError, ValueError):
        return "–"


def section(ledger: pd.DataFrame, now: datetime) -> list[dict]:
    from atlas.owner.board import _eastern

    scores = score(ledger)
    logged = len(ledger)
    decided = int(ledger["outcome"].isin(["win", "loss"]).sum()) if logged else 0
    rows = []
    for r in scores.itertuples():
        rows.append([[LABELS.get(r.stat, r.stat), f"{r.lines} decided · {r.with_atlas} with Atlas"],
                     [f"fair {_f(r.brier_fair)}", f"log loss {_f(r.logloss_fair)}"],
                     [f"Atlas {_f(r.brier_atlas)}", f"log loss {_f(r.logloss_atlas)}"],
                     [f"{_f(r.diff, '{:+.4f}')}", f"95% {_f(r.diff_low, '{:+.4f}')} to {_f(r.diff_high, '{:+.4f}')}"],
                     [f"fair's side {_f(r.hit_fair, '{:.1%}')}", f"Atlas's side {_f(r.hit_atlas, '{:.1%}')}"]])
    tables = [{"title": "Pre-registered verdicts", "head": ["Test", "Where it stands"],
               "rows": [[TESTS[stat][0], verdict(scores, stat)] for stat in TESTS]},
              {"title": "Every stat, on the same lines", "stack": True,
               "head": ["Stat", "Brier, fair", "Brier, Atlas", "Atlas − fair", "Hit rate"],
               "rows": rows or [["No NHL line graded yet.", "", "", "", ""]]}]
    notes = [
        f"Every standard NHL PrizePicks line on the slate (More and Less both offered), pick or not, logged once at "
        f"the first run from {pickem.LOG_HOUR}:00 ET at the line shown, with the books' fair probability of the "
        "likelier side and Atlas's probability of the same side where it has the player; graded from ESPN's box "
        f"score. {logged} lines logged, {decided} decided; a tie or a void is dropped from the scores.",
        "The question is whether Atlas's player projections beat a line PrizePicks actually set, which knows the "
        "matchup and the expected starter. Three forecasts are scored on the same lines: the books' fair probability, "
        "Atlas, and 0.50 (the line as a coin flip, Brier 0.25). The Atlas columns are on the lines Atlas priced; "
        "the difference is paired, line by line, with a normal 95% interval.",
        f"Two tests are pre-registered: saves (docs/NHL_SAVES_PREREGISTRATION.md), judged at {SAVES_N} decided goalie "
        f"lines with an Atlas probability, and shots on goal (docs/NHL_SHOTS_PREREGISTRATION.md), judged at {SHOTS_N} "
        f"lines because the edge expected is smaller and the lines are many. Each clears when Atlas's Brier beats "
        f"fair's with the paired interval below zero, beats 0.25, and Atlas's side hits {BET_BAR:.1%} or better, "
        f"PrizePicks' two-pick Power break-even; each fails when Atlas is no better than fair at its first count, or "
        f"no better than the coin flip at its second ({SAVES_FAIL_N} and {SHOTS_FAIL_N}). The other stats are shown "
        f"with no verdict registered. Built {_eastern(now)} ET.",
    ]
    return [{"title": "Prop ledger: Atlas against PrizePicks' lines", "tab": "Pick'em", "tables": tables,
             "notes": notes}]


def build(priced: pd.DataFrame, games: pd.DataFrame, names: dict, passphrase: str, now: datetime, *,
          where: Path | None = None, box=pickem.box_score, day: str | None = None) -> list[dict]:
    """Log the slate's NHL lines once a day, grade the open ones, and show the scores. Never raises."""
    try:
        where = where or path()
        ledger = load(passphrase, where)
        touched: set = set()
        if day and due(ledger, day, now):
            ledger, weeks = log(ledger, priced, names, now)
            touched |= weeks
            if weeks:
                LOG.info("prop ledger: %d NHL lines logged", int((ledger["day"].astype(str) == day).sum()))
        if len(ledger):
            ledger, graded = grade(ledger, games, now, box)
            touched |= graded
        if touched:
            seal(ledger, passphrase, touched, where)
        return section(ledger, now)
    except Exception as error:  # noqa: BLE001 - the type and the place: a message could quote a line
        from atlas.util import where as place

        LOG.error("prop ledger not built: %s at %s", type(error).__name__, place(error))
        return [{"title": "Prop ledger", "tab": "Pick'em",
                 "notes": [f"This run could not build the prop ledger ({type(error).__name__})."], "tables": []}]
