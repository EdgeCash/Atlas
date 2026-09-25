"""The owner's curated plays: games a frozen rule selects, logged before kickoff and graded.

    python -m atlas.owner.plays             # this week's plays and the record (needs ATLAS_OWNER_KEY)

A rule is fixed before the games it selects, and never tuned after: a change
is a new rule with a new id and a record that starts the day it is frozen.
Each play is logged once - the first heavy refresh at which its game
qualifies, at the line and price the book was quoting then - and is never
revised or removed, whatever the line or Atlas's number does afterwards.

**Rule v1** (``cfb-total-5-v1``, frozen 24 September 2026): college regular
season totals where the card model's total (`atlas/models/ncaaf_projection.py`,
``tracking/projections.csv``) is at least five points from the line the book
is quoting; Atlas's side, one flat unit. Its walk-forward history, measured
before it was frozen and carried here unchanged (``HISTORY``), is 53-54% over
five seasons, uneven by season, against 52.4% needed at -110: a lead, not a
proven edge. At a true 54% it takes about 2,400 plays to show; the record
says only what its numbers support.

**Rule v2** (``cfb-total-top5-v2``, frozen 25 September 2026): each week, at
the first heavy refresh on its Saturday (Eastern), the five college
regular-season games still to kick off with the largest gap between Atlas's
total and the line the book is quoting; Atlas's side, one flat unit, one set
per week. Measured before it was frozen as each week's top five against the
closing total: 208-152-5, 57.8%, its 95% range 52.6-62.8% - the one of ten
weekly variants tried that cleared break-even on its range, so possibly the
lucky one, and uneven by season. Its live test differs from that history in
two stated ways: Thursday and Friday games are not in it, and the line is the
Saturday morning one rather than the close.

The plays are the owner's alone: sealed with the owner key, one file a week
in ``tracking/owner_plays/`` (`atlas/owner/sealed.py`), and shown only inside
the owner page's ciphertext.
"""

from __future__ import annotations

import argparse
import json
import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from atlas.owner import paper, sealed
from atlas.util import get_logger

LOG = get_logger(__name__)

EASTERN = ZoneInfo("America/New_York")
PLAY_NAMESPACE = uuid.UUID("5d0f3a51-8c1e-4e8b-9a52-0e3c6b7f2a10")
COLUMNS = ["play_id", "rule", "game_id", "season", "week", "kickoff", "away_team", "home_team", "book", "side",
           "line", "price", "atlas_total", "gap", "model_version", "formed_at"]
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


RULE_V1 = Rule(id="cfb-total-5-v1", frozen="2026-09-24", sport="ncaaf", market="total", threshold=5.0,
               label="College totals, regular season: Atlas's total 5+ points from the line")
RULE_V2 = Rule(id="cfb-total-top5-v2", frozen="2026-09-25", sport="ncaaf", market="total", threshold=0.0,
               top_n=5, weekday=5,
               label="College totals, regular season: each Saturday morning, the week's five largest gaps "
                     "between Atlas's total and the line")
RULES = (RULE_V1, RULE_V2)

#: Each rule's walk-forward history as measured before it was frozen (wins,
#: losses, pushes) against the lines named in ``HISTORY_COLUMNS``. Regular
#: season; the model fitted only on the seasons before each one.
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


def play_id(rule: Rule, game_id) -> str:
    """One play per rule and game, ever."""
    return str(uuid.uuid5(PLAY_NAMESPACE, f"{rule.id}|{game_id}"))


def current_lines(snapshots: pd.DataFrame, market: str) -> pd.DataFrame:
    """The latest captured line and both prices per game."""
    s = snapshots[snapshots["market"] == market].copy()
    if s.empty:
        return pd.DataFrame(columns=["game_id", "book", "line", "price", "other_price"])
    s["ts"] = pd.to_datetime(s["captured_at"], utc=True, errors="coerce")
    last = s.sort_values("ts").groupby("game_id", as_index=False).last()
    if "other_price" not in last:
        last["other_price"] = np.nan
    return last[["game_id", "book", "line", "price", "other_price"]]


def candidates(rule: Rule, projections: pd.DataFrame, snapshots: pd.DataFrame, games: pd.DataFrame,
               season_types: dict, now: datetime, logged_weeks: set | None = None) -> pd.DataFrame:
    """The games the rule selects right now: not started, regular season, and far enough from the line
    - or, for a weekly rule on its choosing morning, the week's ``top_n`` largest gaps, once a week."""
    if rule.top_n and now.astimezone(EASTERN).weekday() != rule.weekday:
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
    })
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


def graded(record: pd.DataFrame, finals: pd.DataFrame) -> pd.DataFrame:
    """Each play with its outcome (``open`` until the game is final) and units won or lost."""
    if record.empty:
        return record.assign(outcome=pd.Series(dtype=str), profit=pd.Series(dtype=float),
                             price_assumed=pd.Series(dtype=bool))
    r = record.assign(game_id=record["game_id"].astype(str)).merge(finals, on="game_id", how="left")
    sign = np.where(r["side"] == "over", 1.0, -1.0)
    edge = (r["final_total"].astype(float) - r["line"].astype(float)) * sign
    r["outcome"] = np.select([np.isnan(edge), edge > 0, edge < 0], ["open", "win", "loss"], "push")
    price = pd.to_numeric(r["price"], errors="coerce")
    r["price_assumed"] = price.isna()
    r["price"] = price.fillna(paper.DEFAULT_PRICE)
    r["profit"] = np.select([r["outcome"] == "win", r["outcome"] == "loss"], [r["price"].map(paper.payout), -1.0],
                            0.0)
    r["clv"] = np.nan
    return r


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


def verdict(r: dict) -> str:
    if r["graded"] < MIN_GRADED:
        return (f"Collecting: {r['graded']} graded. Fewer than {MIN_GRADED} say nothing; proving a rule that "
                "truly wins 54% takes about 2,400.")
    return paper.verdict({**r, "graded": max(r["graded"], paper.MIN_GRADED)})


def section(rule: Rule, g: pd.DataFrame, now: datetime, schools: dict | None = None) -> dict:
    """The owner page's view of one rule, every word in the ciphertext."""
    upcoming = g[(g["outcome"] == "open")
                 & (pd.to_datetime(g["kickoff"], utc=True) > pd.Timestamp(now))].sort_values("kickoff")
    rec = paper.record(g.assign(clv=np.nan))
    tables = []
    if len(upcoming):
        tables.append({"title": f"This week: {len(upcoming)} play{'s' if len(upcoming) != 1 else ''}",
                       "head": ["Game", "Play"],
                       "rows": [[f"{_game(x, schools)} · {_eastern(x.kickoff)} · Atlas {x.atlas_total:.1f}",
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
    done = g[g["outcome"] != "open"].sort_values("kickoff", ascending=False).head(15)
    if len(done):
        tables.append({"title": "Latest graded", "head": ["Game", "Play", "Result"],
                       "rows": [[_game(x, schools), f"{x.side} {x.line:g}", f"{x.outcome} {x.profit:+.2f}"]
                                for x in done.itertuples()]})
    hist, heads = HISTORY.get(rule.id, {}), HISTORY_COLUMNS.get(rule.id, ())
    if hist:
        def cell(w, l_, p):
            n = w + l_
            return f"{w / n:.1%} of {n}" if n else "–"
        rows = [[str(season), *(cell(*c) for c in cols)] for season, cols in sorted(hist.items())]
        totals = [[sum(v[j][i] for v in hist.values()) for i in range(3)] for j in range(len(heads))]
        rows.append(["All", *(cell(*t) for t in totals)])
        tables.append({"title": "History before the freeze (walk-forward; pushes left out)",
                       "head": ["Season", *heads], "rows": rows})
    logged = ("Each play is logged once, the first morning its game qualifies, at the line and price the book "
              "was quoting then, and never changed or removed.") if not rule.top_n else (
        "The week's plays are chosen once, at the first refresh on its Saturday morning, at the lines and prices "
        "then, and never changed or removed. Thursday and Friday games are not in it.")
    caveat = ("The history below is what the rule was frozen on: a lead, uneven by season, not a proven edge."
              if not rule.top_n else
              "The history below is what the rule was frozen on, against the closing total: the one of ten weekly "
              "variants tried that cleared break-even, so possibly the lucky one, and uneven by season.")
    notes = [
        f"Rule {rule.id}, frozen {rule.frozen}: {rule.label}. Atlas's side, one flat unit. Never tuned: a change "
        "is a new rule with its own record from the day it is frozen.",
        logged + " A price the feed did not give is graded at -110 and marked.",
        verdict(rec),
        "Break-even at -110 is 52.4%. " + caveat,
    ]
    short = rule.id.rsplit("-", 1)[-1]
    return {"title": f"Curated plays, rule {short}", "notes": notes, "tables": tables, "record": rec}


def build(passphrase: str, *, store=None, research: pd.DataFrame | None = None, now: datetime | None = None,
          where: Path | None = None) -> list[dict]:
    """Log today's plays, grade the record, and return the owner page's sections, one per rule. Never raises."""
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
        for rule in RULES:
            mine = record[record["rule"] == rule.id] if len(record) else record
            weeks_logged = {(int(a), int(b)) for a, b in mine[["season", "week"]].itertuples(index=False)} \
                if len(mine) else set()
            fresh = candidates(rule, store.read("projections"), store.read("snapshots"), games, season_types, now,
                               weeks_logged)
            before = len(record)
            record, weeks = log(record, fresh)
            if weeks:
                seal(record, passphrase, weeks, where)
                LOG.info("curated plays: %s logged %d new", rule.id, len(record) - before)
        g = graded(record, paper.results(research, games))
        schools = ({str(k): (h, a) for k, h, a in zip(research["game_id"], research["home_team"], research["away_team"],
                                                     strict=True)}
                   if research is not None and {"home_team", "away_team"} <= set(research.columns) else {})
        return [section(rule, g[g["rule"] == rule.id], now, schools) for rule in RULES]
    except Exception as error:  # noqa: BLE001
        LOG.error("curated plays not built: %s", type(error).__name__)
        return []


def main() -> None:
    argparse.ArgumentParser(description="The owner's curated plays").parse_args()
    from atlas.dfs import owner

    passphrase = os.environ.get(owner.SECRET, "")
    if not passphrase.strip():
        raise SystemExit(f"{owner.SECRET} is not set")
    for s in build(passphrase):
        print(s["title"], json.dumps(s.get("record", s.get("notes")), indent=1, default=str))


if __name__ == "__main__":
    main()
