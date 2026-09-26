"""The owner's curated plays: games a frozen rule selects, logged before kickoff and graded.

    python -m atlas.owner.plays refresh [--heavy]   # every run: log, grade, seal the owner page's plays box
    python -m atlas.owner.plays             # the records, to the terminal (needs ATLAS_OWNER_KEY)

A rule is fixed before the games it selects, and never tuned after: a change
is a new rule with a new id and a record that starts the day it is frozen.
Each play is logged once - at the first run at which its game qualifies, at
the line and price the book was quoting then - and is never revised or
removed, whatever the line or Atlas's number does afterwards.

**Rule v1** (``cfb-total-5-v1``, frozen 24 September 2026): college regular
season totals where the card model's total (`atlas/models/ncaaf_projection.py`,
``tracking/projections.csv``) is at least five points from the line the book
is quoting; Atlas's side, one flat unit.

**Rule v2** (``cfb-total-top5-v2``, frozen 25 September 2026): each week, at
the first run on its Saturday (Eastern), the five college regular-season
games still to kick off with the largest gap between Atlas's total and the
line the book is quoting; Atlas's side, one flat unit, one set per week. In
practice that run is the 04:00 ET rebuild, so its line is Friday night's.

**Rule v3** (``cfb-total-top5-sat10-v3``, frozen 26 September 2026): the same
five largest gaps, chosen at the first run (a poll, normally) at or after
10:00 ET on Saturday -
after the overnight moves and with every Saturday game still to kick off, so
the line is the Saturday morning market and the choosing time is fixed and
stated. v2 keeps running beside it: the same games chosen six hours apart
measure what the earlier line costs.

**Two histories.** Each rule's five-season walk-forward record as it stood
when the rule was frozen is carried in ``HISTORY`` unchanged, and labelled
for what it is: measured on an earlier version of the model, by a script that
is not in the repository. The record the page relies on is rebuilt on every
refresh from ``tracking/calibration.csv``, the current model's own walk-forward
against the closing total, so the history beside a rule always describes the
model that is choosing its plays (`rule_history`).

**Two gradings.** Every play is graded on the final score at the price taken,
and on closing-line value at the book it was logged at: where DraftKings
closed against the line taken, in points and in probability
(`atlas/live/probability.py`). A play that beats the close was a good play
whether or not it won, and on five plays a week that is the only question a
season can answer.

The plays are the owner's alone: sealed with the owner key, one file a week
in ``tracking/owner_plays/`` (`atlas/owner/sealed.py`), and shown only inside
the owner page's ciphertext. Their page payload is sealed separately from the
DFS lineups' (``data/owner/plays.enc.json``), by the plays step of every run,
heavy or poll, so a rebuild that fails does not decide the week's plays.
"""

from __future__ import annotations

import argparse
import json
import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from atlas import config
from atlas.owner import paper, sealed
from atlas.util import get_logger

LOG = get_logger(__name__)

EASTERN = ZoneInfo("America/New_York")
PLAY_NAMESPACE = uuid.UUID("5d0f3a51-8c1e-4e8b-9a52-0e3c6b7f2a10")
COLUMNS = ["play_id", "rule", "game_id", "season", "week", "kickoff", "away_team", "home_team", "book", "side",
           "line", "price", "atlas_total", "gap", "model_version", "formed_at", "open_line", "moved_against",
           "home_qb", "home_qb_status", "away_qb", "away_qb_status"]
#: The line movement flag: the total moved this many points against Atlas's
#: side between the book's opener and the close. Tested on the rules' history
#: before it was recorded (v1: 49.9% flagged against 55.6%, z -1.76; v2: 55.2%
#: against 59.4%, z -0.79): the direction expected of news the market has and
#: Atlas does not, but not significant. A label on each play, never a filter.
MOVED_AGAINST = 2.0
#: Graded plays before the record says anything at all.
MIN_GRADED = 100


@dataclass(frozen=True)
class Rule:
    id: str
    frozen: str
    label: str
    sport: str
    market: str
    threshold: float
    top_n: int = 0                    # a weekly rule: this many games, the largest gaps
    weekday: int | None = None        # and the Eastern weekday it chooses on (Monday 0)
    hour: int | None = None           # and the Eastern hour from which it chooses (any run before is not it)
    daily: bool = False               # chooses only at the daily rebuild, as its definition says; never at a poll


RULE_V1 = Rule(id="cfb-total-5-v1", frozen="2026-09-24", sport="ncaaf", market="total", threshold=5.0, daily=True,
               label="College totals, regular season: Atlas's total 5+ points from the line")
RULE_V2 = Rule(id="cfb-total-top5-v2", frozen="2026-09-25", sport="ncaaf", market="total", threshold=0.0,
               top_n=5, weekday=5, daily=True,
               label="College totals, regular season: each Saturday morning, the week's five largest gaps "
                     "between Atlas's total and the line")
RULE_V3 = Rule(id="cfb-total-top5-sat10-v3", frozen="2026-09-26", sport="ncaaf", market="total", threshold=0.0,
               top_n=5, weekday=5, hour=10,
               label="College totals, regular season: each Saturday at the first poll from 10:00 ET, the weekend's "
                     "five largest gaps between Atlas's total and the line")
RULES = (RULE_V1, RULE_V2, RULE_V3)
#: The page's order: the rule that chooses the plays going forward first.
PAGE_ORDER = (RULE_V3, RULE_V1, RULE_V2)

#: Each rule's walk-forward history as measured before it was frozen (wins,
#: losses, pushes) against the lines named in ``HISTORY_COLUMNS``. Regular
#: season; the model fitted only on the seasons before each one. Measured on
#: an earlier version of the model by a script that is not in the repository:
#: carried unchanged as the figures the rule was frozen on, never as its
#: current history (that is `rule_history`).
HISTORY = {
    RULE_V1.id: {
        2021: ((146, 124, 4), (140, 143, 3)),
        2022: ((92, 94, 1), (116, 123, 4)),
        2023: ((80, 73, 2), (111, 101, 4)),
        2024: ((79, 42, 0), (92, 49, 1)),
        2025: ((56, 46, 0), (67, 44, 0)),
    },
    RULE_V2.id: {
        2021: ((34, 35, 2),),
        2022: ((43, 28, 0),),
        2023: ((35, 34, 2),),
        2024: ((52, 23, 1),),
        2025: ((44, 32, 0),),
    },
}
HISTORY_COLUMNS = {RULE_V1.id: ("Vs open", "Vs close"), RULE_V2.id: ("Vs close",)}
#: A weekly rule's weekend: the games from its choosing morning to this long after.
WEEKEND = pd.Timedelta(days=3)


def path() -> Path:
    from atlas.live.store import tracking_dir

    return tracking_dir() / "owner_plays"


def page_path() -> Path:
    """The owner page's plays box: ciphertext, rebuilt by every run, never committed."""
    return config.paths().root / "data" / "owner" / "plays.enc.json"


def play_id(rule: Rule, game_id) -> str:
    """One play per rule and game, ever."""
    return str(uuid.uuid5(PLAY_NAMESPACE, f"{rule.id}|{game_id}"))


def current_lines(snapshots: pd.DataFrame, market: str) -> pd.DataFrame:
    """The latest captured line and both prices per game."""
    s = snapshots[snapshots["market"] == market].copy()
    if s.empty:
        return pd.DataFrame(columns=["game_id", "book", "line", "price", "other_price", "open_line"])
    s["ts"] = pd.to_datetime(s["captured_at"], utc=True, errors="coerce")
    # tail(1), not last(): last() fills each column from its latest non-null
    # value separately, pairing one snapshot's line with another's price.
    last = s.sort_values("ts", kind="stable").groupby("game_id", as_index=False).tail(1)
    for c in ("other_price", "open_line"):
        if c not in last:
            last[c] = np.nan
    return last[["game_id", "book", "line", "price", "other_price", "open_line"]]


def chooses_now(rule: Rule, now: datetime, heavy: bool = True) -> bool:
    """Whether this run is one the rule chooses at: the daily rebuild for a daily rule (v1 and v2 were
    defined on it, and a poll is not it); for a weekly rule its weekday, and at or after its hour."""
    if rule.daily and not heavy:
        return False
    if not rule.top_n:
        return True
    local = now.astimezone(EASTERN)
    if local.weekday() != rule.weekday:
        return False
    return rule.hour is None or local.hour >= rule.hour


def candidates(rule: Rule, projections: pd.DataFrame, snapshots: pd.DataFrame, games: pd.DataFrame,
               season_types: dict, now: datetime, logged_weeks: set | None = None,
               qbs: dict | None = None, heavy: bool = True) -> pd.DataFrame:
    """The games the rule selects at this run: not started, regular season, and far enough from the line
    - or, for a weekly rule at its choosing moment, the week's ``top_n`` largest gaps, once a week."""
    if not chooses_now(rule, now, heavy):
        return pd.DataFrame(columns=COLUMNS)
    p = projections[projections["sport"] == rule.sport].copy()
    if p.empty:
        return pd.DataFrame(columns=COLUMNS)
    p = p.sort_values("refreshed_at").drop_duplicates("game_id", keep="last")
    p["kickoff_ts"] = pd.to_datetime(p["kickoff"], utc=True, errors="coerce")
    p = p[p["kickoff_ts"] > pd.Timestamp(now)]
    # The rule was measured on the regular season; a game whose type is unknown is left out.
    p = p[p["game_id"].map(lambda g: season_types.get(str(g))) == "regular"]
    lines = current_lines(snapshots, rule.market)
    p = p.merge(lines, on="game_id", how="inner").dropna(subset=["line", "total_mean"])
    p["gap"] = p["total_mean"].astype(float) - p["line"].astype(float)
    if rule.top_n:
        p = p[p["kickoff_ts"] <= pd.Timestamp(now) + WEEKEND]
        if p.empty:
            return pd.DataFrame(columns=COLUMNS)
        season, week = (int(v) for v in p[["season", "week"]].mode().iloc[0])
        if (season, week) in (logged_weeks or set()):
            return pd.DataFrame(columns=COLUMNS)
        p = p[(p["season"] == season) & (p["week"] == week)]
        p = p.assign(size=p["gap"].abs()).sort_values(["size", "kickoff_ts"], ascending=[False, True])
        p = p.head(rule.top_n)
    else:
        p = p[p["gap"].abs() >= rule.threshold]
    if p.empty:
        return pd.DataFrame(columns=COLUMNS)
    over = p["gap"] > 0
    names = games.set_index("game_id")[["home_team", "away_team"]] if len(games) else None
    out = pd.DataFrame({
        "play_id": [play_id(rule, g) for g in p["game_id"]], "rule": rule.id, "game_id": p["game_id"],
        "season": p["season"], "week": p["week"], "kickoff": p["kickoff_ts"].dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "away_team": p["game_id"].map(names["away_team"]) if names is not None else None,
        "home_team": p["game_id"].map(names["home_team"]) if names is not None else None,
        "book": p["book"], "side": np.where(over, "over", "under"), "line": p["line"].astype(float),
        # The price of the side taken; none when the feed gave none (graded at -110, and said so).
        "price": np.where(over, p["price"], p["other_price"]).astype(float),
        "atlas_total": p["total_mean"].astype(float).round(1), "gap": p["gap"].round(1),
        "model_version": p["model_version"], "formed_at": now.replace(microsecond=0).isoformat(),
        # How far the line had already moved against Atlas's side from the opener, when logged.
        "open_line": pd.to_numeric(p["open_line"], errors="coerce"),
        "moved_against": (np.where(over, -1.0, 1.0)
                          * (p["line"].astype(float) - pd.to_numeric(p["open_line"], errors="coerce"))).round(1),
    })
    # Each side's expected quarterback and his status in the latest availability report (atlas/owner/starters.py).
    found = [(qbs or {}).get(str(g), (None, "unknown", None, "unknown")) for g in p["game_id"]]
    for i, col in enumerate(("home_qb", "home_qb_status", "away_qb", "away_qb_status")):
        out[col] = [f[i] for f in found]
    return out.reindex(columns=COLUMNS).reset_index(drop=True)


def log(record: pd.DataFrame, fresh: pd.DataFrame) -> tuple[pd.DataFrame, set]:
    """Add plays not yet logged; a logged play is never touched. Returns the record and the weeks written."""
    if fresh.empty:
        return record, set()
    new = fresh[~fresh["play_id"].isin(set(record["play_id"]))] if len(record) else fresh
    if new.empty:
        return record, set()
    weeks = {(int(a), int(b)) for a, b in new[["season", "week"]].drop_duplicates().itertuples(index=False)}
    parts = [record.reindex(columns=COLUMNS), new] if len(record) else [new]
    return pd.concat(parts, ignore_index=True).reindex(columns=COLUMNS), weeks


def load(passphrase: str, where: Path | None = None) -> pd.DataFrame:
    rows = sealed.load(where or path(), passphrase)
    return pd.DataFrame(rows, columns=COLUMNS) if rows else pd.DataFrame(columns=COLUMNS)


def seal(record: pd.DataFrame, passphrase: str, weeks: set, where: Path | None = None) -> list[Path]:
    where = where or path()
    out = []
    for season, week in sorted(weeks):
        part = record[(record["season"].astype(int) == season) & (record["week"].astype(int) == week)]
        rows = json.loads(part.reindex(columns=COLUMNS).to_json(orient="records"))
        names = [r.get(k) for r in rows for k in ("home_team", "away_team")]
        out.append(sealed.seal(rows, passphrase, sealed.week_file(where, season, week), names=names))
    return out


def closing_movement(record: pd.DataFrame, snapshots: pd.DataFrame, games: pd.DataFrame,
                     now: datetime | None = None) -> pd.Series:
    """Points the total moved against each play's side from the opener to its close (the last line before
    kickoff), by play id; empty until the game has started."""
    from atlas.live.grade import closing_lines

    if record.empty or snapshots.empty or games.empty:
        return pd.Series(dtype=float)
    closes = closing_lines(snapshots, games)
    closes = closes[closes["market"] == "total"].assign(game_id=lambda d: d["game_id"].astype(str))
    started = pd.to_datetime(games["kickoff"], utc=True, errors="coerce") <= pd.Timestamp(now or datetime.now(UTC))
    done = set(games.loc[started, "game_id"].astype(str))
    r = record.assign(game_id=record["game_id"].astype(str)).merge(
        closes[["game_id", "book", "close_line"]], on=["game_id", "book"], how="left")
    # A play logged before openers were recorded with it takes the book's opener from the line history.
    opener = current_lines(snapshots.assign(game_id=snapshots["game_id"].astype(str)), "total").set_index(
        "game_id")["open_line"]
    opened = pd.to_numeric(r["open_line"], errors="coerce").fillna(r["game_id"].map(opener))
    sign = np.where(r["side"] == "over", -1.0, 1.0)
    moved = sign * (r["close_line"].astype(float) - opened)
    return pd.Series(np.where(r["game_id"].isin(done), moved, np.nan), index=r["play_id"].to_numpy())


def closing_value(record: pd.DataFrame, snapshots: pd.DataFrame, games: pd.DataFrame,
                  shapes: pd.DataFrame | None = None, now: datetime | None = None) -> pd.DataFrame:
    """Each play against its book's close: ``close_line``, ``clv_points`` (positive when the market moved
    toward the side taken after the play was logged) and ``clv_prob`` (the same in win probability, read
    through the prices at both ends), by play id. Empty until the game has started."""
    from atlas.live import probability
    from atlas.live.grade import closing_lines

    columns = ["play_id", "close_line", "clv_points", "clv_result", "clv_prob", "prob_assumed"]
    if record.empty or snapshots.empty or games.empty:
        return pd.DataFrame(columns=columns).set_index("play_id")
    snaps = snapshots.assign(game_id=snapshots["game_id"].astype(str))
    kicked = games.assign(game_id=games["game_id"].astype(str))
    started = pd.to_datetime(kicked["kickoff"], utc=True, errors="coerce") <= pd.Timestamp(now or datetime.now(UTC))
    done = set(kicked.loc[started, "game_id"])
    r = record.assign(game_id=record["game_id"].astype(str))
    r = r[r["game_id"].isin(done)]
    if r.empty:
        return pd.DataFrame(columns=columns).set_index("play_id")
    closes = closing_lines(snaps, kicked)
    closes = closes[closes["market"] == "total"].assign(game_id=lambda d: d["game_id"].astype(str))
    r = r.merge(closes[["game_id", "book", "close_line"]], on=["game_id", "book"], how="left")
    sign = np.where(r["side"] == "over", 1.0, -1.0)
    r["clv_points"] = (r["close_line"].astype(float) - r["line"].astype(float)) * sign
    r["clv_result"] = np.select([r["clv_points"].isna(), r["clv_points"] > 0, r["clv_points"] < 0],
                                [None, "beat", "lost"], "push")
    # In probability, the tracker's way: the entry market is the last quote at or before the play was
    # logged, the close the last before kickoff, each read through its own two prices.
    like = pd.DataFrame({"signal_id": r["play_id"], "game_id": r["game_id"], "book": r["book"], "market": "total",
                         "created_at": r["formed_at"], "entry_line": r["line"].astype(float),
                         "direction": r["side"]})
    prob = probability.clv_prob(like, snaps, kicked, probability.load_shapes(shapes),
                                dict.fromkeys(r["game_id"], "ncaaf"))
    r = r.merge(prob.rename(columns={"signal_id": "play_id"})[["play_id", "clv_prob", "prob_assumed"]],
                on="play_id", how="left")
    return r.set_index("play_id")[columns[1:]]


def graded(record: pd.DataFrame, finals: pd.DataFrame, moved_at_close: pd.Series | None = None,
           value: pd.DataFrame | None = None) -> pd.DataFrame:
    """Each play with its outcome (``open`` until the game is final), units won or lost, the line movement
    against its side at the close where the game has started, and its closing-line value."""
    if record.empty:
        return record.assign(outcome=pd.Series(dtype=str), profit=pd.Series(dtype=float),
                             price_assumed=pd.Series(dtype=bool), moved_at_close=pd.Series(dtype=float),
                             close_line=pd.Series(dtype=float), clv=pd.Series(dtype=float),
                             clv_result=pd.Series(dtype=str), clv_prob=pd.Series(dtype=float))
    r = record.assign(game_id=record["game_id"].astype(str)).merge(finals, on="game_id", how="left")
    r["moved_at_close"] = r["play_id"].map(moved_at_close) if moved_at_close is not None else np.nan
    sign = np.where(r["side"] == "over", 1.0, -1.0)
    edge = (r["final_total"].astype(float) - r["line"].astype(float)) * sign
    r["outcome"] = np.select([np.isnan(edge), edge > 0, edge < 0], ["open", "win", "loss"], "push")
    price = pd.to_numeric(r["price"], errors="coerce")
    r["price_assumed"] = price.isna()
    r["price"] = price.fillna(paper.DEFAULT_PRICE)
    r["profit"] = np.select([r["outcome"] == "win", r["outcome"] == "loss"], [r["price"].map(paper.payout), -1.0],
                            0.0)
    for col, src in (("close_line", "close_line"), ("clv", "clv_points"), ("clv_result", "clv_result"),
                     ("clv_prob", "clv_prob")):
        r[col] = r["play_id"].map(value[src]) if value is not None and src in value else np.nan
    return r


def rule_history(rule: Rule, calibration: pd.DataFrame | None) -> tuple[dict[int, tuple[int, int, int]], str]:
    """The rule's record on the current model's walk-forward against the closing total
    (``tracking/calibration.csv``, rewritten by every heavy refresh): wins, losses, pushes by season, and a
    note on what the rows are. A weekly rule takes each week's largest gaps among the games on its weekday
    where the table carries kickoffs, and among all of the week's games where it does not yet."""
    if calibration is None or calibration.empty:
        return {}, "no walk-forward table yet"
    c = calibration.copy()
    if "sport" in c:
        c = c[c["sport"].fillna("ncaaf") == rule.sport]
    c = c[(c["market"] == rule.market)]
    if "season_type" in c:
        c = c[c["season_type"] == "regular"]
    c = c.dropna(subset=["abs_edge", "won"])
    if c.empty:
        return {}, "no walk-forward table yet"
    note = "regular season, against the closing total"
    if rule.top_n:
        kick = pd.to_datetime(c["kickoff"], utc=True, errors="coerce") if "kickoff" in c else None
        if kick is not None and kick.notna().any() and rule.weekday is not None:
            c = c[kick.dt.tz_convert(EASTERN).dt.weekday == rule.weekday]
            note += "; each week's largest gaps among Saturday games"
        else:
            note += "; each week's largest gaps among every day's games (no kickoffs in the table yet)"
        c = c.sort_values("abs_edge", ascending=False, kind="stable").groupby(["season", "week"]).head(rule.top_n)
    else:
        c = c[c["abs_edge"] >= rule.threshold]
    out = {}
    for season, part in c.groupby("season"):
        won = part["won"].astype(float)
        out[int(season)] = (int((won == 1.0).sum()), int((won == 0.0).sum()), int((won == 0.5).sum()))
    return out, note


def _eastern(ts: str) -> str:
    t = pd.Timestamp(ts)
    t = t.tz_localize("UTC") if t.tzinfo is None else t
    return t.tz_convert(EASTERN).strftime("%a %-I:%M %p")


def _team(name) -> str:
    return str(name).split(" ")[-1] if isinstance(name, str) and name else "?"


def _game(row, schools: dict | None = None) -> str:
    """"Away @ Home" by school name where the warehouse has it: a mascot alone is ambiguous (two Cowboys)."""
    known = (schools or {}).get(str(row.game_id))
    if known:
        return f"{known[1]} @ {known[0]}"
    return f"{_team(row.away_team)} @ {_team(row.home_team)}"


def _starter_note(x, schools: dict | None = None) -> str:
    """" · Georgia QB Gunner Stockton: Out" for a starter the report does not expect to play."""
    from atlas.owner import starters

    known = (schools or {}).get(str(x.game_id))
    notes = []
    for side, i in (("home", 0), ("away", 1)):
        qb, st = getattr(x, f"{side}_qb", None), getattr(x, f"{side}_qb_status", None)
        if str(st) in starters.OUT:
            team = known[i] if known else _team(getattr(x, f"{side}_team", None))
            notes.append(f" · {team} QB {qb}: {st}")
    return "".join(notes)


def _moved_note(moved, when: str) -> str:
    """" · line moved 2.5 against" when the flag is up; nothing otherwise."""
    try:
        m = float(moved)
    except (TypeError, ValueError):
        return ""
    return f" · line moved {m:g} against {when}" if m >= MOVED_AGAINST else ""


def _clv_note(x) -> str:
    """" · closed 47.5, CLV +1.0" once the game has started and the book closed."""
    try:
        close, clv = float(x.close_line), float(x.clv)
    except (TypeError, ValueError, AttributeError):
        return ""
    if np.isnan(close) or np.isnan(clv):
        return ""
    return f" · closed {close:g}, CLV {clv:+g}"


def verdict(r: dict) -> str:
    # Decided results: a push is graded but says nothing about the win rate.
    decided = r.get("decided", r["graded"])
    if decided < MIN_GRADED:
        return (f"Collecting: {decided} decided. Fewer than {MIN_GRADED} say nothing; proving a rule that "
                "truly wins 54% takes about 2,400.")
    return paper.verdict({**r, "decided": max(decided, paper.MIN_GRADED)})


def _closing_table(g: pd.DataFrame) -> dict | None:
    """The plays against their book's close: the grading that says whether they were good plays."""
    if "clv_result" not in g:
        return None
    done = g[g["clv_result"].isin(["beat", "push", "lost"])]
    if done.empty:
        return None
    counts = done["clv_result"].value_counts()
    beat, push, lost = (int(counts.get(k, 0)) for k in ("beat", "push", "lost"))
    decided = beat + lost
    clv = pd.to_numeric(done["clv"], errors="coerce")
    prob = pd.to_numeric(done["clv_prob"], errors="coerce")
    rows = [["Beat-push-lost the close", f"{beat}-{push}-{lost}"],
            ["Beat rate", paper._pct(beat / decided) if decided else "–"],
            ["Mean CLV, points", paper._num(clv.mean(), "{:+.2f}")],
            ["Mean CLV, win probability", paper._num(prob.mean(), "{:+.1%}") if prob.notna().any() else "–"]]
    return {"title": f"Against the close ({len(done)} plays whose book has closed)", "head": ["", ""], "rows": rows}


def section(rule: Rule, g: pd.DataFrame, now: datetime, schools: dict | None = None,
            calibration: pd.DataFrame | None = None) -> dict:
    """The owner page's view of one rule, every word in the ciphertext."""
    upcoming = g[(g["outcome"] == "open")
                 & (pd.to_datetime(g["kickoff"], utc=True) > pd.Timestamp(now))].sort_values("kickoff")
    clv = pd.to_numeric(g["clv"], errors="coerce") if "clv" in g else pd.Series(np.nan, index=g.index)
    rec = paper.record(g.assign(clv=clv))
    tables = []
    if len(upcoming):
        chosen = ""
        if rule.top_n and upcoming["formed_at"].notna().any():
            chosen = f", chosen {_eastern(str(upcoming['formed_at'].iloc[0]))} ET"
        tables.append({"title": f"This week: {len(upcoming)} play{'s' if len(upcoming) != 1 else ''}{chosen}",
                       "head": ["Game", "Play"],
                       "rows": [[f"{_game(x, schools)} · {_eastern(x.kickoff)} · Atlas {x.atlas_total:.1f}"
                                 + _moved_note(x.moved_against, "so far") + _starter_note(x, schools),
                                 f"{x.side} {x.line:g} ({'-110?' if x.price_assumed else f'{x.price:+.0f}'})"]
                                for x in upcoming.itertuples()]})
    else:
        tables.append({"title": "This week", "head": ["", ""],
                       "rows": [["No game qualifies right now.", ""]]})
    tables.append({"title": "Live record", "head": ["", ""], "rows": [
        ["Graded", str(rec["graded"])], ["Won-lost-push", f"{rec['wins']}-{rec['losses']}-{rec['pushes']}"],
        ["Win rate", paper._pct(rec["win_rate"])],
        ["95% range", f"{paper._pct(rec['low'])}–{paper._pct(rec['high'])}" if rec["wins"] + rec["losses"] else "–"],
        ["Break-even at the prices taken", paper._pct(rec["break_even"])],
        ["Units", paper._num(rec["units"])], ["Per play", paper._num(rec["roi"], "{:+.1%}")]]})
    closing = _closing_table(g)
    if closing:
        tables.append(closing)
    moved = pd.to_numeric(g["moved_at_close"], errors="coerce") if "moved_at_close" in g else pd.Series(
        np.nan, index=g.index)
    graded_ = g[g["outcome"] != "open"]
    if len(graded_):
        flagged = graded_[moved.loc[graded_.index] >= MOVED_AGAINST]
        rest = graded_[~(moved.loc[graded_.index] >= MOVED_AGAINST)]

        def line(part):
            r = paper.record(part.assign(clv=np.nan))
            return f"{r['wins']}-{r['losses']}-{r['pushes']} ({paper._pct(r['win_rate'])})"
        tables.append({"title": f"Split by the line movement flag ({MOVED_AGAINST:g}+ against by the close)",
                       "head": ["", "Record"], "rows": [["Line moved against Atlas", line(flagged)],
                                                        ["Everything else", line(rest)]]})
        from atlas.owner import starters

        out_flag = graded_.apply(lambda x: starters.flagged(x.get("home_qb_status"), x.get("away_qb_status")), axis=1)
        known = graded_.apply(lambda x: any(str(x.get(c)) not in ("no report", "unknown", "nan", "None")
                                            for c in ("home_qb_status", "away_qb_status")), axis=1)
        tables.append({"title": "Split by the starter flag (a starter reported Out or Doubtful when logged)",
                       "head": ["", "Record"],
                       "rows": [["A starter reported out", line(graded_[out_flag])],
                                ["Starters reported available", line(graded_[known & ~out_flag])],
                                ["No report (not SEC or ACC, or not a conference game)", line(graded_[~known])]]})
    done = g[g["outcome"] != "open"].sort_values("kickoff", ascending=False).head(15)
    if len(done):
        tables.append({"title": "Latest graded", "head": ["Game", "Play", "Result"],
                       "rows": [[_game(x, schools) + _moved_note(x.moved_at_close, "by the close")
                                 + _starter_note(x, schools) + _clv_note(x),
                                 f"{x.side} {x.line:g}", f"{x.outcome} {x.profit:+.2f}"]
                                for x in done.itertuples()]})

    def cell(w, l_, p):
        n = w + l_
        return f"{w / n:.1%} of {n}" if n else "–"
    current, how = rule_history(rule, calibration)
    if current:
        rows = [[str(season), cell(*wlp)] for season, wlp in sorted(current.items())]
        rows.append(["All", cell(*(sum(v[i] for v in current.values()) for i in range(3)))])
        tables.append({"title": "History, current model (walk-forward, rebuilt on every refresh)",
                       "head": ["Season", "Vs close"], "rows": rows})
    hist, heads = HISTORY.get(rule.id, {}), HISTORY_COLUMNS.get(rule.id, ())
    if hist:
        rows = [[str(season), *(cell(*c) for c in cols)] for season, cols in sorted(hist.items())]
        totals = [[sum(v[j][i] for v in hist.values()) for i in range(3)] for j in range(len(heads))]
        rows.append(["All", *(cell(*t) for t in totals)])
        tables.append({"title": "History before the freeze (as frozen; an earlier model, not reproducible)",
                       "head": ["Season", *heads], "rows": rows})
    if not rule.top_n:
        logged = ("Each play is logged once, the first daily rebuild (04:00 ET) at which its game qualifies, at the "
                  "line and price the book was quoting then, and never changed or removed.")
    elif rule.hour is None:
        logged = ("The week's plays are chosen once, at the daily rebuild on its Saturday (04:00 ET, so the line "
                  "is Friday night's), at the lines and prices then, and never changed or removed. Thursday and "
                  "Friday games are not in it.")
    else:
        logged = (f"The weekend's plays are chosen once, at the first run at or after {rule.hour}:00 ET on "
                  "Saturday (a poll, normally), at the lines and prices then, and never changed or removed. "
                  "Thursday and Friday games are not in it.")
    notes = [
        f"Rule {rule.id}, frozen {rule.frozen}: {rule.label}. Atlas's side, one flat unit. Never tuned: a change "
        "is a new rule with its own record from the day it is frozen.",
        logged + " A price the feed did not give is graded at -110 and marked.",
        verdict(rec),
        "Break-even at -110 is 52.4%. Every play is also graded against its book's close: CLV is the points the "
        "closing total sat past the line taken, on Atlas's side (and the same in win probability, read through the "
        "prices at both ends). A play that beats the close was a good play whether or not it won; on five plays a "
        "week that is the record a season can actually read.",
        f"The current-model history is the rule applied to the walk-forward in tracking/calibration.csv ({how}), "
        "rebuilt on every refresh so it always describes the model choosing the plays. The figures the rule was "
        "frozen on were measured on an earlier version of the model by a script that is not in the repository; "
        "they are shown as frozen and not relied on.",
        "The starter flag marks a play where either team's expected quarterback (last game's quarterback of "
        "record) was Out or Doubtful in its conference's latest availability report when the play was logged. "
        "Only SEC and ACC conference games have a report Atlas reads. A label, recorded to be tested, not a filter.",
        f"The line movement flag marks a play whose total moved {MOVED_AGAINST:g} or more points against Atlas's "
        "side from the opener - news the market may have and Atlas does not. In the frozen history flagged plays "
        "won less (v1 49.9% against 55.6%; v2 55.2% against 59.4%) but not beyond noise, so it is a label, not a "
        "filter.",
    ]
    short = rule.id.rsplit("-", 1)[-1]
    title = f"Curated plays, rule {short}" + (" (the plays going forward)" if rule is RULE_V3 else "")
    return {"title": title, "notes": notes, "tables": tables, "record": rec}


def _quarterbacks(schools: dict, research: pd.DataFrame | None, store, now: datetime) -> dict:
    """The upcoming games' expected starters and their reported statuses; none when a source is missing."""
    try:
        from atlas.owner import starters
        from atlas.sources import espn_cfb

        if research is None or research.empty:
            return {}
        season = int(research["season"].max())
        upcoming = research[pd.to_datetime(research["kickoff"], utc=True, errors="coerce") > pd.Timestamp(now)]
        wanted = {str(g): schools[str(g)] for g in upcoming["game_id"] if str(g) in schools}
        return starters.for_games(wanted, espn_cfb.load(seasons=[season]), research, store.read("availability"), now)
    except Exception as error:  # noqa: BLE001 - the plays are logged without it
        LOG.info("curated plays: starters not read (%s)", type(error).__name__)
        return {}


def build(passphrase: str, *, store=None, research: pd.DataFrame | None = None, now: datetime | None = None,
          where: Path | None = None, heavy: bool = True) -> list[dict]:
    """Log this run's plays, grade the record, and return the owner page's sections, one per rule
    (`PAGE_ORDER`). ``heavy`` says whether this is the daily rebuild, which the daily rules choose at, or a
    poll. Never raises."""
    now = now or datetime.now(UTC)
    try:
        record = load(passphrase, where)
    except sealed.Unreadable as error:
        LOG.error("curated plays: the owner key does not open them (%s); left as they are", error)
        return [{"title": "Curated plays", "notes": ["The plays could not be opened with this key."], "tables": []}]
    try:
        if store is None:
            from atlas.live.store import Store

            store = Store.open()
        if research is None:
            try:
                from atlas.research.dataset import load_research_frame

                research = load_research_frame()
            except Exception as error:  # noqa: BLE001
                LOG.info("curated plays: no warehouse (%s)", type(error).__name__)
        season_types = ({str(k): v for k, v in zip(research["game_id"], research["season_type"], strict=True)}
                        if research is not None and "season_type" in research else {})
        games = store.read("games")
        schools = ({str(k): (h, a) for k, h, a in zip(research["game_id"], research["home_team"], research["away_team"],
                                                     strict=True)}
                   if research is not None and {"home_team", "away_team"} <= set(research.columns) else {})
        qbs = _quarterbacks(schools, research, store, now)
        for rule in RULES:
            mine = record[record["rule"] == rule.id] if len(record) else record
            weeks_logged = {(int(a), int(b)) for a, b in mine[["season", "week"]].itertuples(index=False)} \
                if len(mine) else set()
            fresh = candidates(rule, store.read("projections"), store.read("snapshots"), games, season_types, now,
                               weeks_logged, qbs, heavy)
            before = len(record)
            record, weeks = log(record, fresh)
            if weeks:
                seal(record, passphrase, weeks, where)
                LOG.info("curated plays: %s logged %d new", rule.id, len(record) - before)
        snapshots = store.read("snapshots")
        g = graded(record, paper.results(research, games), closing_movement(record, snapshots, games, now),
                   closing_value(record, snapshots, games, store.read("market_shape"), now))
        calibration = store.read("calibration")
        return [section(rule, g[g["rule"] == rule.id], now, schools, calibration) for rule in PAGE_ORDER]
    except Exception as error:  # noqa: BLE001
        LOG.error("curated plays not built: %s", type(error).__name__)
        return []


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_page(box: dict | None, *, reason: str | None = None, where: Path | None = None) -> Path:
    """The plays box, or the reason there is none. Nothing else is ever written here."""
    where = where or page_path()
    where.parent.mkdir(parents=True, exist_ok=True)
    record = {"built_at": _now(), "box": box, "reason": None if box else (reason or "not built")}
    where.write_text(json.dumps(record) + "\n")
    return where


def read_page(where: Path | None = None) -> dict | None:
    where = where or page_path()
    if not where.exists():
        return None
    try:
        return json.loads(where.read_text())
    except (OSError, ValueError):
        return None


def _check_sealed(box: dict, sections: list[dict]) -> None:
    """Belt and braces: no cell of any table appears in what is published."""
    published = json.dumps(box)
    for s in sections:
        for t in s.get("tables", []):
            for row in t.get("rows", []):
                for cell in row:
                    if isinstance(cell, str) and len(cell) > 4 and cell in published:
                        raise RuntimeError("plaintext in the sealed payload")


def refresh(*, now: datetime | None = None, where: Path | None = None, heavy: bool = False) -> Path:
    """The plays step of every run, heavy or poll: log, grade, and seal the owner page's plays box.
    Never raises, and never fails the run: without the key it records why the box is empty."""
    from atlas.dfs import owner

    passphrase = os.environ.get(owner.SECRET, "")
    if not passphrase.strip():
        LOG.warning("no %s secret: the curated plays are not logged", owner.SECRET)
        return write_page(None, reason="The owner key is not configured.", where=where)
    try:
        sections = build(passphrase, now=now, heavy=heavy)
        if not sections:
            return write_page(None, reason="This run could not build the curated plays.", where=where)
        # The owner's board rides in the same box: every book's line on every game, priced (atlas/owner/board.py).
        # It is built only when BettingPros is configured and never takes the plays down with it.
        from atlas.owner import board

        sections = [*board.build(passphrase, now=now), *sections]
        data = {"built_at": _now(), "sections": [{k: v for k, v in s.items() if k != "record"} for s in sections]}
        plain = json.dumps(owner._clean(data), separators=(",", ":"), allow_nan=False).encode("utf-8")
        box = owner.encrypt(plain, passphrase)
        _check_sealed(box, sections)
        LOG.info("curated plays: %d sections sealed (%d bytes of ciphertext)", len(sections), len(box["ct"]))
        return write_page(box, where=where)
    except Exception as error:  # noqa: BLE001 - the type only: a message could quote a team or a line
        LOG.error("curated plays page not built: %s", type(error).__name__)
        return write_page(None, reason=f"This run could not build the curated plays ({type(error).__name__}).",
                          where=where)


def main() -> None:
    ap = argparse.ArgumentParser(description="The owner's curated plays")
    ap.add_argument("command", nargs="?", choices=["show", "refresh"], default="show",
                    help="refresh: log this run's plays and seal the owner page's plays box (never fails)")
    ap.add_argument("--heavy", action="store_true",
                    help="this is the daily rebuild: the rules defined on it (v1, v2) choose now")
    args = ap.parse_args()
    if args.command == "refresh":
        refresh(heavy=args.heavy)
        return
    from atlas.dfs import owner

    passphrase = os.environ.get(owner.SECRET, "")
    if not passphrase.strip():
        raise SystemExit(f"{owner.SECRET} is not set")
    for s in build(passphrase):
        print(s["title"], json.dumps(s.get("record", s.get("notes")), indent=1, default=str))


if __name__ == "__main__":
    main()
