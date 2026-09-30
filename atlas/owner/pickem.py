"""Pick'em: PrizePicks' lines priced against the sportsbooks' player props, and the best slips.

    python -m atlas.owner.pickem fit     # refit the yardage shapes from nflverse's weekly stats

PrizePicks sells a line, not a price. Pick More or Less on two to six players
and the payout is fixed by the entry: how many picks, and how many hit. The
sportsbooks sell the same player props at prices, and a price says how likely
a side is. So, from the BettingPros capture (`atlas/sources/bettingpros.py`):

* **fair value**: every sportsbook that quotes both sides of a player's prop
  gives a vig-free probability at its own line. A shape for the stat moves it
  to PrizePicks' line (below), and the median across books is the fair
  probability of More, of Less, and of landing exactly on a whole-number line.
  At least two books, or the prop is not priced.
* **picks**: on each PrizePicks standard line (it quotes More and Less at one
  line; a demon or a goblin is More only, pays by a mix PrizePicks does not
  publish, and is left out), the side the books make likelier, from games
  that have not started on the slate's day.
* **slips**: for each entry (Power: every pick must hit; Flex: partial pays)
  and each size, the slip that grows a bankroll fastest at full Kelly, from
  the best picks, never two from one game (the books price same-game
  correlations this does not model). Its expected value, the chance it
  returns more than the entry, and a quarter-Kelly stake.
* a sealed **record** (``tracking/owner_pickem/`` for the picks,
  ``tracking/owner_slips/`` for the slips): the day's picks and slips logged
  once, at the first run from 10:00 Eastern, like the parlays; each pick's
  fair probability followed to kickoff at its logged line (the close); graded
  from ESPN's box score once the game is final, a slip at the payouts logged
  with it.

Shapes. Moving a probability from one line to another needs the stat's
distribution around its expectation. Yardage: a player's yards in a game over
the player's season mean without that game, NFL regular seasons 2016-2025
(:func:`fit_ratios`): passing yards spread about 35% around the mean,
rushing and receiving yards about 70%, skewed right. Scaled so the book's
line sits at its probability, it gives the probability at any nearby line.
The spread is a little wider than the market's (a season mean knows less
than a price), which understates what a line difference is worth. Receptions:
a negative binomial, variance 1.1 times the mean. College uses the NFL
shapes. A book more than a quarter of its line (plus two yards) or a catch
and a half from PrizePicks is not moved that far and is left out.

The NHL (docs/MODEL_PLAN_NHL.md, step 7): every stat a count, with the
variance-to-mean ratios measured around a player's own mean in §3 of the plan
(regular seasons 2010-11 to 2025-26): shots on goal and blocked shots 1.08,
hits 1.18, points, goals and assists a Poisson (0.97), a goalie's saves 1.9
(1.98 around his own mean, 1.92 around a game-level expectation of shots
against, starters 2021-26: saves swing with the score and the pulled goalie,
not only the opponent). A book a goal, a point, a shot or a block from
PrizePicks' line is moved; saves three. Graded from ESPN's hockey box score
(`atlas/sources/nhl.py`), a shootout not counted, as the books settle it; the
NHL's rows are filed by the ISO week of puck drop.

Only inside the owner page's ciphertext, like the board. The payout table is
PrizePicks' standard one; a state with a different table changes
:data:`PAYOUTS`, and each logged slip keeps the table it was priced on.
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import re
import uuid
from datetime import datetime
from functools import cache
from pathlib import Path

import numpy as np
import pandas as pd

from atlas.owner import sealed
from atlas.sources import bettingpros as bp
from atlas.util import get_logger

LOG = get_logger(__name__)

NAMESPACE = uuid.UUID("5b0e7c3a-8d21-4f6e-a1c9-3e7d2b4f6a58")

#: The markets priced, the box-score column each settles on, and how the page names them.
STATS = {"passing-yards": "pass_yds", "rushing-yards": "rush_yds", "receiving-yards": "rec_yds", "receptions": "rec",
         "shots": "sog", "shots-on-goal": "sog", "points": "pts", "goals": "g", "assists": "a", "saves": "sv",
         "blocked-shots": "blk", "hits": "hits"}
LABELS = {"passing-yards": "pass yds", "rushing-yards": "rush yds", "receiving-yards": "rec yds",
          "receptions": "receptions", "shots": "shots on goal", "shots-on-goal": "shots on goal", "points": "points",
          "goals": "goals", "assists": "assists", "saves": "saves", "blocked-shots": "blocked shots", "hits": "hits"}
#: BettingPros' slugs asked for, per sport.
SLUGS = {"nfl": ("passing-yards", "rushing-yards", "receiving-yards", "receptions"),
         "ncaaf": ("passing-yards", "rushing-yards", "receiving-yards", "receptions"),
         "nhl": ("shots", "shots-on-goal", "points", "goals", "assists", "saves", "blocked-shots", "hits")}
#: Prop pages a sport may take in one run: the NHL's slate is up to sixteen games of six markets.
PAGES = {"nhl": 30}
#: The books whose two-sided prices make the fair value: sportsbooks and the two sports exchanges. Not the
#: consensus (an average of these), not a pick'em app, not a book the catalogue has not named.
FAIR_BOOKS = frozenset({10, 12, 13, 14, 18, 19, 24, 32, 33, 38, 43, 49, 60, 67})
MIN_BOOKS = 2
#: A pick is shown, and may go on a slip, from this fair probability.
PICK_FLOOR = 0.54
#: The best picks the optimizer combines, and the most slips shown.
POOL = 12
MAX_SLIPS = 9
KELLY_FRACTION = 0.25
#: The day's picks and slips are logged at the first run at or after this hour, Eastern.
LOG_HOUR = 10
MIN_GRADED = 50
TOP_ROWS = 10

#: PrizePicks' standard payouts, as a multiple of the entry: {entry: {picks: {hits: multiple}}}. A pick that
#: ties its line or whose player does not play drops out and the entry pays as the next size down; a Flex
#: entry left with two picks pays as a two-pick Power entry; one left with fewer than two is refunded.
PAYOUTS = {
    "power": {2: {2: 3.0}, 3: {3: 5.0}, 4: {4: 10.0}, 5: {5: 20.0}, 6: {6: 37.5}},
    "flex": {3: {3: 2.25, 2: 1.25}, 4: {4: 5.0, 3: 1.5}, 5: {5: 10.0, 4: 2.0, 3: 0.4},
             6: {6: 25.0, 5: 2.0, 4: 0.4}},
}

#: A yardage stat's game over the player's season mean without that game, NFL regular seasons 2016-2025:
#: its quantiles at :data:`QUANTILE_PROBS` (:func:`fit_ratios`).
QUANTILE_PROBS = (0.001, *[round(0.02 * i, 2) for i in range(1, 50)], 0.999)
RATIOS = {
    "pass_yds": (0.000, 0.231, 0.408, 0.492, 0.550, 0.597, 0.630, 0.656, 0.686, 0.708, 0.733, 0.753, 0.775, 0.797,
                 0.815, 0.835, 0.853, 0.870, 0.887, 0.905, 0.921, 0.935, 0.950, 0.966, 0.980, 0.996, 1.014, 1.029,
                 1.045, 1.060, 1.079, 1.095, 1.113, 1.130, 1.148, 1.164, 1.187, 1.206, 1.224, 1.247, 1.276, 1.302,
                 1.330, 1.362, 1.396, 1.430, 1.477, 1.531, 1.609, 1.746, 2.289),
    "rush_yds": (0.000, 0.000, 0.066, 0.126, 0.182, 0.225, 0.264, 0.302, 0.338, 0.374, 0.410, 0.447, 0.477, 0.510,
                 0.534, 0.565, 0.595, 0.629, 0.656, 0.683, 0.713, 0.748, 0.775, 0.808, 0.843, 0.873, 0.903, 0.932,
                 0.970, 1.003, 1.039, 1.074, 1.109, 1.145, 1.186, 1.229, 1.273, 1.317, 1.364, 1.409, 1.457, 1.521,
                 1.588, 1.665, 1.741, 1.840, 1.967, 2.118, 2.355, 2.715, 4.249),
    "rec_yds": (0.000, 0.000, 0.000, 0.000, 0.108, 0.159, 0.200, 0.240, 0.277, 0.315, 0.348, 0.385, 0.417, 0.450,
                0.482, 0.516, 0.547, 0.578, 0.610, 0.645, 0.680, 0.711, 0.740, 0.775, 0.808, 0.843, 0.879, 0.915,
                0.949, 0.987, 1.024, 1.066, 1.105, 1.145, 1.189, 1.235, 1.288, 1.343, 1.400, 1.456, 1.516, 1.589,
                1.662, 1.741, 1.835, 1.944, 2.073, 2.233, 2.478, 2.885, 4.680),
}
#: Receptions: a negative binomial with this variance-to-mean ratio.
REC_DISPERSION = 1.1
#: Every count stat's variance-to-mean ratio: a negative binomial above one, a Poisson at one.
COUNTS = {"rec": REC_DISPERSION, "sog": 1.08, "blk": 1.08, "hits": 1.18, "pts": 1.0, "g": 1.0, "a": 1.0, "sv": 1.9}
#: How far a book's line may sit from PrizePicks' on a count and still be moved to it.
COUNT_MOVES = {"rec": 1.5, "sv": 3.0}

PICK_COLUMNS = ["pick_id", "day", "logged_at", "sport", "season", "week", "game_id", "kickoff", "game", "player_key",
                "player", "team", "market", "side", "line", "p", "p_push", "books", "book_line", "close_line", "close_p",
                "close_at", "actual", "outcome", "graded_at"]
SLIP_COLUMNS = ["slip_id", "day", "logged_at", "season", "week", "kind", "n", "pick_ids", "payouts", "ev", "p_profit",
                "kelly", "growth", "first_kickoff", "last_kickoff"]
PRICED_COLUMNS = ["sport", "event_id", "game_id", "kickoff", "day", "player_key", "player", "team", "position", "market",
                  "line", "p_over", "p_under", "p_push", "books", "book_line", "side", "p", "updated"]


def picks_path() -> Path:
    from atlas.live.store import tracking_dir

    return tracking_dir() / "owner_pickem"


def slips_path() -> Path:
    from atlas.live.store import tracking_dir

    return tracking_dir() / "owner_slips"


# ---------------------------------------------------------------------------
# Shapes: a stat's distribution around the line a book prices
# ---------------------------------------------------------------------------


@cache
def _knots(stat: str) -> tuple[np.ndarray, np.ndarray]:
    """The ratio's distribution function as (values, probabilities), one knot per distinct value."""
    q, probs = np.asarray(RATIOS[stat]), np.asarray(QUANTILE_PROBS)
    values = np.unique(q)
    return values, np.array([probs[q == v].max() for v in values])


def ratio_cdf(stat: str, x: float) -> float:
    values, probs = _knots(stat)
    return float(np.interp(x, values, probs, left=0.0, right=1.0))


def _nb_cdf(k: int, mean: float, dispersion: float = REC_DISPERSION) -> float:
    """P(Y <= k) for a negative binomial with mean ``mean`` and variance ``dispersion`` times it; a Poisson
    at a dispersion of one or less."""
    if k < 0:
        return 0.0
    if dispersion <= 1.0:
        total, term = 0.0, math.exp(-mean)
        for j in range(int(k) + 1):
            if j > 0:
                term *= mean / j
            total += term
        return min(1.0, total)
    p = 1.0 / dispersion
    n = mean * p / (1.0 - p)
    log_base = n * math.log(p)
    total, log_pmf = 0.0, log_base
    for j in range(int(k) + 1):
        if j > 0:
            log_pmf += math.log((j - 1 + n) / j) + math.log(1.0 - p)
        total += math.exp(log_pmf)
    return min(1.0, total)


def split(stat: str, centre: float, line: float) -> tuple[float, float]:
    """(P over, P exactly on the line) for a stat whose distribution is set by ``centre``: the player's
    expectation for yards (the ratios scaled by it), the count's mean for a count."""
    whole = float(line).is_integer()
    if stat in COUNTS:
        d = COUNTS[stat]
        if whole:
            below = _nb_cdf(int(line) - 1, centre, d)
            at = _nb_cdf(int(line), centre, d)
            return 1.0 - at, at - below
        return 1.0 - _nb_cdf(math.floor(line), centre, d), 0.0
    if centre <= 0:
        return 0.0, 0.0
    if whole:
        lo, hi = ratio_cdf(stat, (line - 0.5) / centre), ratio_cdf(stat, (line + 0.5) / centre)
        return 1.0 - hi, hi - lo
    return 1.0 - ratio_cdf(stat, line / centre), 0.0


def centre_for(stat: str, line: float, p_over: float) -> float | None:
    """The centre at which the stat goes over ``line`` with probability ``p_over``, a tie on a
    whole-number line set aside (the book refunds it). None when no centre does."""
    if stat not in COUNTS and not float(line).is_integer():
        q = float(np.interp(1.0 - p_over, QUANTILE_PROBS, RATIOS[stat]))
        return float(line) / q if q > 0 else None

    def gap(c: float) -> float:
        over, at = split(stat, c, line)
        return over / max(1e-9, 1.0 - at) - p_over

    scale = max(1.0, float(line))
    lo, hi = (0.01, max(40.0, 3.0 * scale)) if stat in COUNTS else (0.05 * scale, 25.0 * scale)
    g_lo, g_hi = gap(lo), gap(hi)
    if not (g_lo < 0 < g_hi):
        return None
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if gap(mid) < 0:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-4 * scale:
            break
    return 0.5 * (lo + hi)


def max_move(stat: str, line: float) -> float:
    """How far a book's line may sit from PrizePicks' and still be moved to it."""
    if stat in COUNTS:
        return COUNT_MOVES.get(stat, 1.0)
    return 0.25 * abs(float(line)) + 2.0


def fair_at(quotes, stat: str, line: float) -> dict | None:
    """The fair probabilities at ``line`` from the books' two-sided quotes on one prop (a frame or its
    records): each book's vig-free probability of over at its line, moved to ``line``; the median across
    books."""
    from atlas.live.probability import no_vig

    rows = quotes.to_dict("records") if isinstance(quotes, pd.DataFrame) else quotes
    sides: dict[int, dict[str, tuple[float, float]]] = {}
    for q in rows:
        book, cost = int(q["book_id"]), q["cost"]
        if book not in FAIR_BOOKS or cost is None or not math.isfinite(float(cost)) or not 100 <= abs(float(cost)) < 5000:
            continue
        sides.setdefault(book, {}).setdefault(str(q["selection"]), (float(q["line"]), float(cost)))
    overs, pushes, lines = [], [], []
    for quoted in sides.values():
        if "over" not in quoted or "under" not in quoted or quoted["over"][0] != quoted["under"][0]:
            continue
        at = quoted["over"][0]
        p = no_vig(quoted["over"][1], quoted["under"][1])
        if not (math.isfinite(p) and 0.03 < p < 0.97) or abs(float(line) - at) > max_move(stat, at):
            continue
        if at == float(line) and not float(line).is_integer():
            o, t = p, 0.0                     # the book's own line: its probability as it stands
        else:
            c = centre_for(stat, at, p)
            if c is None:
                continue
            o, t = split(stat, c, line)
        overs.append(o)
        pushes.append(t)
        lines.append(at)
    if len(overs) < MIN_BOOKS:
        return None
    over, push = float(np.median(overs)), float(np.median(pushes))
    return {"p_over": over, "p_under": max(0.0, 1.0 - over - push), "p_push": push, "books": len(overs),
            "book_line": float(np.median(lines))}


def _standard(rows: list[dict]) -> tuple[float, str] | None:
    over = [r for r in rows if r["selection"] == "over"]
    under = [r for r in rows if r["selection"] == "under"]
    if not over or not under or float(over[0]["line"]) != float(under[0]["line"]):
        return None
    return float(over[0]["line"]), str(over[0]["updated"] or "")


# ---------------------------------------------------------------------------
# Pricing PrizePicks' lines
# ---------------------------------------------------------------------------


def day_of(ts) -> str:
    from atlas.owner.parlays import day_of as _day

    return _day(ts)


def slate(events: pd.DataFrame, now: datetime) -> pd.DataFrame:
    """The events on the slate: not started, on the Eastern day of ``now`` when it has any, else the next day
    with games; soonest first."""
    if events.empty or "game_id" not in events:
        return events.iloc[0:0]
    e = events.assign(kickoff=pd.to_datetime(events["scheduled"], utc=True, errors="coerce"))
    e = e[e["kickoff"] > pd.Timestamp(now)].copy()
    if e.empty:
        return e
    e["day"] = e["kickoff"].map(day_of)
    today = day_of(now)
    day = today if (e["day"] == today).any() else e["day"].min()
    return e[e["day"] == day].sort_values("kickoff").drop_duplicates("event_id").reset_index(drop=True)


def standard(pp) -> tuple[float, str] | None:
    """PrizePicks' standard line on a prop (a frame or its records), and when it was updated: More and Less
    at one line. A line offered More only (a demon or a goblin) is not standard."""
    return _standard(pp.to_dict("records") if isinstance(pp, pd.DataFrame) else pp)


def _groups(props: pd.DataFrame, keys: list[str]) -> dict[tuple, list[dict]]:
    """The props' rows as records, by ``keys``, in one pass."""
    out: dict[tuple, list[dict]] = {}
    for r in props.to_dict("records"):
        out.setdefault(tuple(r[k] for k in keys), []).append(r)
    return out


def price(props: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Every PrizePicks standard line on the slate with its fair probabilities: (priced, counts)."""
    counts = {"lines": 0, "more_only": 0, "unpriced": 0}
    if props.empty:
        return pd.DataFrame(columns=PRICED_COLUMNS), counts
    rows = []
    for (event_id, player_key, market), part in _groups(props, ["event_id", "player_key", "market"]).items():
        pp = [r for r in part if r["book_id"] == bp.PRIZEPICKS]
        if not pp or market not in STATS:
            continue
        counts["lines"] += 1
        std = _standard(pp)
        if std is None:
            counts["more_only"] += 1
            continue
        line, updated = std
        fair = fair_at(part, STATS[market], line)
        if fair is None:
            counts["unpriced"] += 1
            continue
        first = part[0]
        side = "over" if fair["p_over"] >= fair["p_under"] else "under"
        rows.append({"sport": first["sport"], "event_id": int(event_id), "game_id": str(first["game_id"]),
                     "kickoff": first["kickoff"], "day": first["day"], "player_key": str(player_key),
                     "player": first["player"], "team": first["team"], "position": first["position"], "market": market,
                     "line": line, **fair, "side": side, "p": fair["p_" + side], "updated": updated})
    out = pd.DataFrame(rows, columns=PRICED_COLUMNS)
    return out.sort_values("p", ascending=False).reset_index(drop=True), counts


# ---------------------------------------------------------------------------
# Slips
# ---------------------------------------------------------------------------


def multiple(kind: str, n: int, hits: int, dropped: int, payouts: dict) -> float:
    """What an entry of ``n`` picks returns, as a multiple of the entry, with ``hits`` of the picks that
    stood won and ``dropped`` ties or players who did not play."""
    left = n - dropped
    if left < 2:
        return 1.0
    table = _table(payouts, kind).get(left)
    if table is None:
        table = _table(payouts, "power").get(left, {})
    return float(table.get(hits, 0.0))


def _table(payouts: dict, kind: str) -> dict:
    """A payout table with whole-number keys (a logged table comes back from JSON with string keys)."""
    return {int(n): {int(h): float(m) for h, m in t.items()} for n, t in (payouts.get(kind) or {}).items()}


def outcomes(picks: list[tuple[float, float]]) -> dict[tuple[int, int], float]:
    """{(hits, dropped): probability} for independent picks given as (P hit, P tie)."""
    dist = {(0, 0): 1.0}
    for win, tie in picks:
        lose = max(0.0, 1.0 - win - tie)
        nxt: dict[tuple[int, int], float] = {}
        for (h, d), q in dist.items():
            for key, w in (((h + 1, d), win), ((h, d + 1), tie), ((h, d), lose)):
                if w > 0:
                    nxt[key] = nxt.get(key, 0.0) + q * w
        dist = nxt
    return dist


def returns(picks: list[tuple[float, float]], kind: str, payouts: dict) -> list[tuple[float, float]]:
    """[(probability, multiple)] over a slip's outcomes."""
    n = len(picks)
    return [(q, multiple(kind, n, h, d, payouts)) for (h, d), q in outcomes(picks).items()]


def kelly(dist: list[tuple[float, float]]) -> tuple[float, float]:
    """(the bankroll fraction that maximises expected log growth, that growth) for one slip."""
    ev = sum(q * m for q, m in dist) - 1.0
    if ev <= 0:
        return 0.0, 0.0

    def growth(f: float) -> float:
        return sum(q * math.log(max(1e-12, 1.0 + f * (m - 1.0))) for q, m in dist)

    lo, hi = 0.0, 0.999
    for _ in range(80):                       # golden-section search on a concave function
        a, b = lo + 0.382 * (hi - lo), lo + 0.618 * (hi - lo)
        if growth(a) < growth(b):
            lo = a
        else:
            hi = b
    f = 0.5 * (lo + hi)
    return f, growth(f)


def slip_id(kind: str, pick_ids: list[str]) -> str:
    return str(uuid.uuid5(NAMESPACE, f"slip|{kind}|{'|'.join(sorted(pick_ids))}"))


def pick_id(day: str, event_id, player_key, market: str, side: str) -> str:
    return str(uuid.uuid5(NAMESPACE, f"pick|{day}|{event_id}|{player_key}|{market}|{side}"))


def optimize(priced: pd.DataFrame, payouts: dict | None = None, *, pool: int = POOL) -> pd.DataFrame:
    """For each entry and size, the slip of the best picks (one per game) that grows a bankroll fastest at
    full Kelly; those with positive expected value, fastest first."""
    payouts = payouts or PAYOUTS
    cols = ["kind", "n", "keys", "ev", "p_profit", "kelly", "growth"]
    picks = priced[priced["p"] >= PICK_FLOOR] if not priced.empty else priced
    if picks.empty:
        return pd.DataFrame(columns=cols)
    # The pool: the best picks, at most two from a game so a slip can always reach across games.
    ranked = picks.sort_values("p", ascending=False)
    rows = list(ranked[ranked.groupby("game_id").cumcount() < 2].head(pool).itertuples())
    out = []
    for kind in ("power", "flex"):
        for n in sorted(_table(payouts, kind)):
            scored = []
            for combo in itertools.combinations(rows, n):
                if len({r.game_id for r in combo}) < n:
                    continue
                dist = returns([(float(r.p), float(r.p_push)) for r in combo], kind, payouts)
                ev = sum(q * m for q, m in dist) - 1.0
                if ev > 0:
                    scored.append((ev, combo, dist))
            best = None
            # Growth is dearer to compute than EV and nearly always ranks the same: the best few by EV decide.
            for ev, combo, dist in sorted(scored, key=lambda x: -x[0])[:5]:
                f, g = kelly(dist)
                if f > 0 and (best is None or g > best["growth"]):
                    best = {"kind": kind, "n": n, "keys": [r.Index for r in combo], "ev": ev,
                            "p_profit": sum(q for q, m in dist if m > 1.0), "kelly": f, "growth": g}
            if best is not None:
                out.append(best)
    table = pd.DataFrame(out, columns=cols)
    return table.sort_values("growth", ascending=False).head(MAX_SLIPS).reset_index(drop=True)


def break_even(kind: str, n: int, payouts: dict | None = None) -> float:
    """The hit rate every pick needs for the entry to return its cost, no ties."""
    payouts = payouts or PAYOUTS
    lo, hi = 0.3, 0.95
    for _ in range(50):
        mid = 0.5 * (lo + hi)
        ev = sum(q * m for q, m in returns([(mid, 0.0)] * n, kind, payouts)) - 1.0
        lo, hi = (mid, hi) if ev < 0 else (lo, mid)
    return 0.5 * (lo + hi)


# ---------------------------------------------------------------------------
# The record
# ---------------------------------------------------------------------------


def load(passphrase: str, where: Path, columns: list[str]) -> pd.DataFrame:
    rows = sealed.load(where, passphrase)
    return pd.DataFrame(rows, columns=columns) if rows else pd.DataFrame(columns=columns)


def seal(record: pd.DataFrame, passphrase: str, weeks: set, where: Path, columns: list[str],
         names: list[str]) -> list[Path]:
    out = []
    for season, week in sorted(weeks):
        part = record[(pd.to_numeric(record["season"]) == season) & (pd.to_numeric(record["week"]) == week)]
        rows = json.loads(part.reindex(columns=columns).to_json(orient="records"))
        out.append(sealed.seal(rows, passphrase, sealed.week_file(where, season, week), names=names))
    return out


def _weeks(rows: pd.DataFrame) -> set:
    return {(int(a), int(b)) for a, b in rows[["season", "week"]].dropna().drop_duplicates().itertuples(index=False)}


def due(picks: pd.DataFrame, day: str, now: datetime) -> bool:
    """Is this the run that logs the day: at or after :data:`LOG_HOUR` Eastern on the slate's day, and
    nothing logged for that day yet."""
    from atlas.owner.board import EASTERN

    local = pd.Timestamp(now).tz_convert(EASTERN)
    if day != local.strftime("%Y-%m-%d") or local.hour < LOG_HOUR:
        return False
    return not (len(picks) and (picks["day"].astype(str) == day).any())


def filed(sport, kickoff) -> tuple[int, int]:
    """Where an NHL row is filed: the ISO year and week of puck drop (the NHL has no weeks)."""
    t = pd.Timestamp(kickoff)
    t = t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")
    year, week, _ = t.isocalendar()
    return int(year), int(week)


def _stamp(ts) -> str:
    t = pd.Timestamp(ts)
    t = t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def log(picks: pd.DataFrame, slips: pd.DataFrame, priced: pd.DataFrame, chosen: pd.DataFrame, games: pd.DataFrame,
        names: dict, now: datetime) -> tuple[pd.DataFrame, pd.DataFrame, set]:
    """The day's picks (every one from the floor) and slips, at the lines and probabilities shown; never
    revised. Returns the records and the weeks touched."""
    eligible = priced[priced["p"] >= PICK_FLOOR]
    if eligible.empty:
        return picks, slips, set()
    week_of = {}
    if not games.empty:
        week_of = {str(g): (s, w) for g, s, w in zip(games["game_id"], games["season"], games["week"], strict=True)}
    stamp = _stamp(now)
    rows, ids = [], {}
    for r in eligible.itertuples():
        nhl = str(r.sport) == "nhl"
        season, week = filed(r.sport, r.kickoff) if nhl else week_of.get(str(r.game_id), (None, None))
        if season is None or pd.isna(season) or week is None or pd.isna(week):
            continue
        pid = pick_id(r.day, r.event_id, r.player_key, r.market, r.side)
        ids[r.Index] = pid
        rows.append({"pick_id": pid, "day": r.day, "logged_at": stamp, "sport": r.sport, "season": int(season),
                     "week": int(week), "game_id": str(r.game_id), "kickoff": _stamp(r.kickoff),
                     "game": names.get(str(r.game_id), str(r.game_id)), "player_key": str(r.player_key),
                     "player": r.player, "team": r.team, "market": r.market, "side": r.side, "line": float(r.line),
                     "p": round(float(r.p), 4), "p_push": round(float(r.p_push), 4), "books": int(r.books),
                     "book_line": float(r.book_line), "close_line": float(r.line), "close_p": round(float(r.p), 4),
                     "close_at": stamp, "actual": None, "outcome": None, "graded_at": None})
    fresh = pd.DataFrame(rows, columns=PICK_COLUMNS)
    new_picks = fresh[~fresh["pick_id"].isin(set(picks["pick_id"]))] if len(picks) else fresh
    slip_rows = []
    table = json.dumps(PAYOUTS)
    for s in chosen.itertuples():
        members = [ids[k] for k in s.keys if k in ids]
        if len(members) != len(s.keys):
            continue
        part = fresh[fresh["pick_id"].isin(members)]
        kicks = pd.to_datetime(part["kickoff"], utc=True)
        first = part.iloc[0]
        slip_rows.append({"slip_id": slip_id(s.kind, members), "day": first["day"], "logged_at": stamp,
                          "season": int(first["season"]), "week": int(first["week"]), "kind": s.kind, "n": int(s.n),
                          "pick_ids": json.dumps(members), "payouts": table, "ev": round(float(s.ev), 4),
                          "p_profit": round(float(s.p_profit), 4), "kelly": round(float(s.kelly), 4),
                          "growth": round(float(s.growth), 5), "first_kickoff": _stamp(kicks.min()),
                          "last_kickoff": _stamp(kicks.max())})
    new_slips = pd.DataFrame(slip_rows, columns=SLIP_COLUMNS)
    if len(slips):
        new_slips = new_slips[~new_slips["slip_id"].isin(set(slips["slip_id"]))]
    weeks = _weeks(new_picks) | _weeks(new_slips)
    picks = pd.concat([picks, new_picks], ignore_index=True) if len(picks) else new_picks
    slips = pd.concat([slips, new_slips], ignore_index=True) if len(slips) else new_slips
    return picks.reindex(columns=PICK_COLUMNS), slips.reindex(columns=SLIP_COLUMNS), weeks


def follow(picks: pd.DataFrame, props: pd.DataFrame, now: datetime) -> tuple[pd.DataFrame, set]:
    """Each logged pick whose game has not started, its fair probability now at its logged line: the close,
    once kickoff comes. Returns the record and the weeks that changed."""
    if picks.empty or props.empty:
        return picks, set()
    kick = pd.to_datetime(picks["kickoff"], utc=True, errors="coerce")
    live = picks.index[(kick > pd.Timestamp(now)) & picks["outcome"].isna()]
    if not len(live):
        return picks, set()
    groups = {(str(k[0]), str(k[1])): g for k, g in _groups(props, ["player_key", "market"]).items()}
    picks = picks.copy()
    changed = set()
    for i in live:
        r = picks.loc[i]
        quotes = groups.get((str(r["player_key"]), str(r["market"])))
        if quotes is None:
            continue
        fair = fair_at(quotes, STATS[r["market"]], float(r["line"]))
        if fair is None:
            continue
        p = round(fair["p_" + r["side"]], 4)
        std = _standard([q for q in quotes if q["book_id"] == bp.PRIZEPICKS])
        line = std[0] if std else r["close_line"]
        if p != r["close_p"] or line != r["close_line"]:
            picks.loc[i, ["close_p", "close_line", "close_at"]] = [p, line, _stamp(now)]
            changed.add((int(r["season"]), int(r["week"])))
    return picks, changed


# ---------------------------------------------------------------------------
# Grading from ESPN's box score
# ---------------------------------------------------------------------------

SUMMARY = {"nfl": "https://site.api.espn.com/apis/site/v2/sports/football/nfl/summary?event={event}",
           "ncaaf": "https://site.api.espn.com/apis/site/v2/sports/football/college-football/summary?event={event}",
           "nhl": "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/summary?event={event}"}


def box_score(sport: str, game_id: str) -> pd.DataFrame | None:
    """The game's player box score when ESPN calls it final; None before then or when it cannot be read."""
    from atlas.sources import espn_cfb
    from atlas.util import http_get

    body = http_get(SUMMARY[sport].format(event=game_id), timeout=30, retries=2).json()
    status = ((((body.get("header") or {}).get("competitions") or [{}])[0].get("status") or {}).get("type") or {})
    if not status.get("completed"):
        return None
    if sport == "nhl":
        from atlas.sources import nhl

        return nhl.espn_box(body)
    return espn_cfb.parse(body, 0, 0, "")


def name_key(name) -> str:
    """Lower case, letters only, no generational suffix: "Michael Penix Jr." -> "michaelpenix"."""
    text = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b\.?", "", str(name or "").lower())
    return re.sub(r"[^a-z]", "", text)


def find(box: pd.DataFrame, player: str, team=None) -> pd.Series | None:
    """The player's line in the box score: by full name, else by first initial and last name when only
    one player fits; two of one name (the NHL has two Sebastian Ahos) told apart by team when it is known."""
    keys = box["name"].map(name_key)
    hit = box[keys == name_key(player)]
    if len(hit) > 1 and isinstance(team, str) and team and "team" in box:
        hit = hit[hit["team"].astype(str) == team]
    if len(hit) == 1:
        return hit.iloc[0]
    words = [w for w in re.sub(r"\b(jr|sr|ii|iii|iv|v)\b\.?", "", str(player).lower()).split() if w]
    if len(words) < 2:
        return None
    first, last = words[0][0], re.sub(r"[^a-z]", "", words[-1])
    loose = box[[(n.split()[0][:1].lower() == first and name_key(n.split()[-1]) == last) if isinstance(n, str) and n.split()
                 else False for n in box["name"]]]
    return loose.iloc[0] if len(loose) == 1 else None


def settle(side: str, line: float, actual: float) -> str:
    edge = (actual - line) * (1.0 if side == "over" else -1.0)
    return "win" if edge > 0 else ("loss" if edge < 0 else "push")


def grade(picks: pd.DataFrame, games: pd.DataFrame, now: datetime, fetch=box_score) -> tuple[pd.DataFrame, set]:
    """Settle each open pick whose game is final: its stat from the box score; a player not in it is void
    (did not play, as PrizePicks voids them). A game ESPN has not finalised waits for the next run."""
    if picks.empty:
        return picks, set()
    done = set()
    if not games.empty and "completed" in games:
        done = set(games.loc[games["completed"].fillna(False).astype(bool), "game_id"].astype(str))
    open_ = picks.index[picks["outcome"].isna() & picks["game_id"].astype(str).isin(done)]
    if not len(open_):
        return picks, set()
    picks = picks.copy()
    boxes: dict[str, pd.DataFrame | None] = {}
    changed = set()
    for i in open_:
        r = picks.loc[i]
        gid = str(r["game_id"])
        if gid not in boxes:
            try:
                boxes[gid] = fetch(str(r["sport"]), gid)
            except Exception as error:  # noqa: BLE001 - tried again next run
                LOG.info("pickem: box score not read (%s)", type(error).__name__)
                boxes[gid] = None
        box = boxes[gid]
        if box is None or box.empty:
            continue
        row = find(box, r["player"], r.get("team"))
        actual = float(pd.to_numeric(row.get(STATS[r["market"]]), errors="coerce")) if row is not None else float("nan")
        if not math.isfinite(actual):
            actual, outcome = None, "void"          # not in the box score (or no such stat for him): did not play
        else:
            outcome = settle(r["side"], float(r["line"]), actual)
        picks.loc[i, ["actual", "outcome", "graded_at"]] = [actual, outcome, _stamp(now)]
        changed.add((int(r["season"]), int(r["week"])))
    return picks, changed


def slip_results(slips: pd.DataFrame, picks: pd.DataFrame) -> pd.DataFrame:
    """Each slip's outcome from its picks: open while any is; else the multiple its payouts give, with ties
    and voids dropped."""
    outcome = dict(zip(picks["pick_id"], picks["outcome"], strict=True)) if len(picks) else {}
    results, multiples = [], []
    for s in slips.itertuples():
        members = json.loads(s.pick_ids or "[]")
        got = [outcome.get(m) for m in members]
        if any(g is None or (isinstance(g, float) and math.isnan(g)) for g in got):
            results.append("open")
            multiples.append(float("nan"))
            continue
        hits = sum(1 for g in got if g == "win")
        dropped = sum(1 for g in got if g in ("push", "void"))
        m = multiple(s.kind, int(s.n), hits, dropped, json.loads(s.payouts))
        multiples.append(m)
        results.append("win" if m > 1.0 else ("refund" if m == 1.0 else ("partial" if m > 0 else "loss")))
    return slips.assign(result=results, multiple=multiples)


# ---------------------------------------------------------------------------
# The owner page's view
# ---------------------------------------------------------------------------


def _side_word(side: str) -> str:
    return "More" if side == "over" else "Less"


def _pick_text(r) -> str:
    return f"{r['player']} {_side_word(r['side'])} {float(r['line']):g} {LABELS.get(r['market'], r['market'])}"


def _entry(kind: str, n: int, payouts: dict) -> list[str]:
    table = _table(payouts, kind)[n]
    pays = " / ".join(f"{m:g}×" for _, m in sorted(table.items(), reverse=True))
    return [f"{n}-pick {kind.capitalize()}", f"pays {pays}" + (" (all hit)" if kind == "power" else " (by hits)")]


def _num(x, fmt: str) -> str:
    return "–" if x is None or not math.isfinite(float(x)) else fmt.format(float(x))


def sections(priced: pd.DataFrame, chosen: pd.DataFrame, picks: pd.DataFrame, slips: pd.DataFrame, counts: dict,
             names: dict, now: datetime, day: str | None) -> list[dict]:
    from atlas.owner.board import _eastern

    tab = "Pick'em"
    logged = set(picks["pick_id"]) if len(picks) else set()
    logged_slips = set(slips["slip_id"]) if len(slips) else set()
    label = pd.Timestamp(day).strftime("%a %b %-d") if day else pd.Timestamp(day_of(now)).strftime("%a %b %-d")
    rows = []
    for s in chosen.itertuples():
        members = [priced.loc[k] for k in s.keys]
        ids = [pick_id(m["day"], m["event_id"], m["player_key"], m["market"], m["side"]) for m in members]
        mark = " · logged" if slip_id(s.kind, ids) in logged_slips else ""
        rows.append([_entry(s.kind, int(s.n), PAYOUTS),
                     [f"{_pick_text(m)} · {m['p']:.0%}" for m in members],
                     [f"EV {s.ev:+.1%}", f"P(profit) {s.p_profit:.0%} · ¼-Kelly {KELLY_FRACTION * s.kelly:.1%}{mark}"]])
    slip_card = {"title": f"Slips for {label} ({len(rows)})", "tab": tab, "tables": [
        {"title": "", "stack": True, "head": ["Entry", "Picks", "Value"],
         "rows": rows or [["No slip clears zero today.", "", ""]]}], "notes": [
        "For each entry and size, the slip that grows a bankroll fastest: the best picks by fair probability, never "
        "two from one game. EV is the expected return on the entry; P(profit) the chance it pays more than the entry. "
        "The stake is a quarter of Kelly for that slip alone: the slips share picks, so take one, not all.",
        "Break-even hit rate per pick: " + ", ".join(
            f"{k.capitalize()} {n} {break_even(k, n):.1%}" for k in ("power", "flex") for n in sorted(_table(PAYOUTS, k)))
        + ". Payouts are PrizePicks' standard table; confirm them in the app for your state.",
        f"The day's picks from {PICK_FLOOR:.0%} and its slips are logged once, at the first run from {LOG_HOUR}:00 ET, "
        f"at the lines shown then (marked logged). Built {_eastern(now)} ET."]}

    board = priced[priced["p"] >= PICK_FLOOR] if len(priced) else priced

    def pick_row(r) -> list:
        pid = pick_id(r["day"], r["event_id"], r["player_key"], r["market"], r["side"])
        who = " · ".join(x for x in (r["team"], r["position"]) if isinstance(x, str) and x)
        tie = f"tie {r['p_push']:.0%}" if r["p_push"] >= 0.005 else ""
        return [[r["player"], f"{who} · {names.get(str(r['game_id']), '')} · {_eastern(r['kickoff'])}"],
                [f"{_side_word(r['side'])} {float(r['line']):g} {LABELS.get(r['market'], r['market'])}",
                 "logged" if pid in logged else ""],
                [f"books' line {float(r['book_line']):g}", f"{int(r['books'])} books"],
                [f"{r['p']:.1%}", tie]]

    head = ["Player", "Pick", "Market", "Fair"]
    top = [pick_row(r) for _, r in board.head(TOP_ROWS).iterrows()]
    rest = [pick_row(r) for _, r in board.iloc[TOP_ROWS:].iterrows()]
    tables = [{"title": f"Best {len(top)} of {len(board)} picks from {PICK_FLOOR:.0%}", "stack": True, "head": head,
               "rows": top or [[f"No PrizePicks line reaches {PICK_FLOOR:.0%} right now.", "", "", ""]]}]
    if rest:
        tables.append({"title": f"The other {len(rest)} picks", "fold": True, "stack": True, "head": head, "rows": rest})
    board_card = {"title": "Pick board", "tab": tab, "tables": tables, "notes": [
        f"Every PrizePicks standard line on the slate's games: {counts.get('lines', 0)} lines this run, "
        f"{counts.get('more_only', 0)} offered More only (demons and goblins, left out: they pay by a mix PrizePicks "
        f"does not publish), {counts.get('unpriced', 0)} with fewer than {MIN_BOOKS} books to price them.",
        "Fair is the probability of the side shown: each sportsbook's price on both sides, its margin taken out, "
        "moved from its line to PrizePicks' along the stat's spread (yards scaled from ten NFL seasons of games "
        "around a player's mean; receptions and every NHL stat a count, at the spread measured for it), the median "
        "across books. The books' line is the median of theirs. A tie on a whole-number line drops the pick from "
        "the entry, as PrizePicks settles it. The NHL is priced on PrizePicks' standard payout table too: confirm it "
        "in the app."]}
    out = [slip_card, board_card]

    if len(picks):
        done = picks[picks["outcome"].notna()]
        decided = done[done["outcome"].isin(["win", "loss"])]
        wins = int((done["outcome"] == "win").sum())
        losses = int((done["outcome"] == "loss").sum())
        pushes = int((done["outcome"] == "push").sum())
        voids = int((done["outcome"] == "void").sum())
        started = picks[pd.to_datetime(picks["kickoff"], utc=True, errors="coerce") <= pd.Timestamp(now)]
        moved = pd.to_numeric(started["close_p"], errors="coerce") - pd.to_numeric(started["p"], errors="coerce")
        rows = [["Picks logged", str(len(picks))], ["Graded", str(len(done))],
                ["Won-lost-tie-void", f"{wins}-{losses}-{pushes}-{voids}"],
                ["Hit rate (fair when logged)",
                 f"{wins / len(decided):.1%} ({pd.to_numeric(decided['p']).mean():.1%})" if len(decided) else "–"],
                ["Closed toward the pick", f"{int((moved > 0).sum())} of {int(moved.notna().sum())}, "
                 f"{_num(moved.mean(), '{:+.1%}')} fair probability on average" if moved.notna().any() else "–"]]
        graded = slip_results(slips, picks) if len(slips) else slips.assign(result=[], multiple=[])
        settled = graded[graded["result"] != "open"] if len(graded) else graded
        if len(slips):
            back = pd.to_numeric(settled["multiple"], errors="coerce")
            rows += [["Slips logged", str(len(slips))], ["Slips settled", str(len(settled))],
                     ["Returned per entry", _num(back.mean() - 1.0, "{:+.1%}") if len(settled) else "–"]]
        tables = [{"title": "", "head": ["", ""], "rows": rows}]
        latest = done.sort_values("kickoff", ascending=False).head(12)
        if len(latest):
            tables.append({"title": "Latest graded picks", "fold": True, "stack": True, "head": ["Pick", "Result"],
                           "rows": [[[_pick_text(x), f"{x['game']} · fair {float(x['p']):.0%}"],
                                     [f"{x['outcome']}" + ("" if pd.isna(x["actual"]) else f", {float(x['actual']):g}"),
                                      f"closed {float(x['close_p']):.0%}" if pd.notna(x["close_p"]) else ""]]
                                    for _, x in latest.iterrows()]})
        out.append({"title": "Pick'em record", "tab": tab, "tables": tables, "notes": [
            "Each pick is logged once, at the line and fair probability shown at the logging run, followed to kickoff "
            "at that line (the close: did the books move toward it?), and graded from ESPN's box score once the game "
            "is final. A player not in the box score is void. Slips settle on their picks at the payouts logged with "
            f"them. Nothing is read from fewer than {MIN_GRADED} graded picks."]})
    return out


# ---------------------------------------------------------------------------
# The step
# ---------------------------------------------------------------------------


def _describe(sport: str, props: pd.DataFrame, events: int) -> str:
    """A log line: counts only, never a line or a price."""
    if props.empty:
        return f"pickem: {sport}: no prop lines on {events} slate events"
    lines = props.drop_duplicates(["event_id", "player_key", "market", "book_id"])
    pp = int((lines["book_id"] == bp.PRIZEPICKS).sum())
    fair = lines[lines["book_id"].isin(FAIR_BOOKS)]
    top = fair["book_id"].value_counts().head(6)
    return (f"pickem: {sport}: {lines[['event_id', 'player_key', 'market']].drop_duplicates().shape[0]} props on "
            f"{lines['event_id'].nunique()} of {events} slate events, PrizePicks on {pp}; books: "
            + ", ".join(f"{bp.book_name(b)} {c}" for b, c in top.items()))


def summary(counts: dict, priced: pd.DataFrame, chosen: pd.DataFrame, day: str | None) -> str:
    """The run's pick'em in one log line, counts only: what the tab shows."""
    picks = int((priced["p"] >= PICK_FLOOR).sum()) if len(priced) else 0
    kinds = ", ".join(f"{k} {int(n)}" for k, n in chosen["kind"].value_counts().sort_index().items()) if len(chosen) \
        else "none"
    return (f"pickem: slate {day or 'none'}: {counts.get('lines', 0)} PrizePicks lines, {counts.get('more_only', 0)} "
            f"More only, {counts.get('unpriced', 0)} unpriced, {len(priced)} priced, {picks} picks from "
            f"{PICK_FLOOR:.0%} on {priced.loc[priced['p'] >= PICK_FLOOR, 'game_id'].nunique() if picks else 0} games, "
            f"{len(chosen)} slips ({kinds})")


def fetch(client, events: pd.DataFrame, now: datetime) -> pd.DataFrame:
    """The slate's player props, every book, with each event's game and kickoff."""
    on = slate(events, now)
    parts = []
    for sport, part in on.groupby("sport"):
        try:
            slug_of = bp.prop_markets(client, str(sport), SLUGS.get(str(sport), bp.PROP_SLUGS))
            got = bp.props(client, str(sport), part["event_id"].astype(int).tolist(), slug_of,
                           max_pages=PAGES.get(str(sport), bp.PROP_PAGES))
        except Exception as error:  # noqa: BLE001 - the type and the place only
            from atlas.util import where

            LOG.warning("pickem: %s props not fetched: %s at %s", sport, type(error).__name__, where(error))
            continue
        LOG.info(_describe(str(sport), got, len(part)))
        parts.append(got.merge(part[["event_id", "game_id", "kickoff", "day"]], on="event_id", how="inner"))
    if not parts:
        return pd.DataFrame(columns=[*bp.PROP_COLUMNS, "game_id", "kickoff", "day"])
    return pd.concat(parts, ignore_index=True)


def build(client, events: pd.DataFrame, games: pd.DataFrame, names: dict, passphrase: str, now: datetime, *,
          picks_where: Path | None = None, slips_where: Path | None = None, box=box_score) -> list[dict]:
    """The day's pick'em: priced, optimised, logged once, followed, graded, shown. Never raises."""
    try:
        picks_where, slips_where = picks_where or picks_path(), slips_where or slips_path()
        props = fetch(client, events, now)
        priced, counts = price(props)
        chosen = optimize(priced)
        day = str(priced["day"].iloc[0]) if len(priced) else None
        LOG.info(summary(counts, priced, chosen, day))
        picks = load(passphrase, picks_where, PICK_COLUMNS)
        slips = load(passphrase, slips_where, SLIP_COLUMNS)
        touched: set = set()
        if day and due(picks, day, now):
            picks, slips, weeks = log(picks, slips, priced, chosen, games, names, now)
            touched |= weeks
            if weeks:
                LOG.info("pickem: %d picks and %d slips logged", int((picks["day"] == day).sum()),
                         int((slips["day"] == day).sum()) if len(slips) else 0)
        picks, closed = follow(picks, props, now)
        picks, graded = grade(picks, games, now, box)
        touched |= closed | graded
        if touched:
            names_ = [*picks["player"].dropna().astype(str), *picks["game"].dropna().astype(str)]
            seal(picks, passphrase, touched, picks_where, PICK_COLUMNS, names_)
            if len(slips):
                seal(slips, passphrase, touched & _weeks(slips), slips_where, SLIP_COLUMNS, names_)
        return sections(priced, chosen, picks, slips, counts, names, now, day)
    except Exception as error:  # noqa: BLE001 - the type and the place: a message could quote a line
        from atlas.util import where

        LOG.error("pickem not built: %s at %s", type(error).__name__, where(error))
        return [{"title": "Pick'em", "tab": "Pick'em",
                 "notes": [f"This run could not build the pick'em ({type(error).__name__})."], "tables": []}]


# ---------------------------------------------------------------------------
# Refitting the shapes
# ---------------------------------------------------------------------------


def fit_ratios(raw: Path, seasons: range = range(2016, 2026)) -> dict[str, list[float]]:
    """Each yardage stat's game over the player's season mean without that game, regular seasons, player-
    seasons of eight or more games with a mean from a floor typical of a prop line: its quantiles."""
    from atlas.sources import nflverse

    cols = ["season", "season_type", "player_id", "position", "passing_yards", "rushing_yards", "receiving_yards"]
    frames = [pd.read_parquet(nflverse.player_stats_path(raw, s), columns=cols) for s in seasons
              if nflverse.player_stats_path(raw, s).exists()]
    st = pd.concat(frames, ignore_index=True)
    st = st[st["season_type"] == "REG"]
    spec = {"pass_yds": ("passing_yards", "QB", 150), "rush_yds": ("rushing_yards", None, 30),
            "rec_yds": ("receiving_yards", None, 25)}
    out = {}
    for key, (stat, position, floor) in spec.items():
        d = st[["season", "player_id", stat, "position"]].dropna()
        if position:
            d = d[d["position"] == position]
        g = d.groupby(["season", "player_id"])[stat]
        n, total = g.transform("count"), g.transform("sum")
        d = d.assign(n=n, loo=(total - d[stat]) / (n - 1))
        d = d[(d["n"] >= 8) & (d["loo"] >= floor)]
        out[key] = [round(float(v), 3) for v in np.quantile((d[stat] / d["loo"]).clip(lower=0), QUANTILE_PROBS)]
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Pick'em shapes")
    ap.add_argument("command", choices=["fit"])
    ap.parse_args()
    from atlas import config

    for key, q in fit_ratios(config.paths().raw).items():
        print(key, q)


if __name__ == "__main__":
    main()
