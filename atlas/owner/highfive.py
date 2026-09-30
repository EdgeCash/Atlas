"""High Five: the day's five best game wagers and five best props, logged once, and what they went.

    python -m atlas.owner.highfive          # the record, to the terminal (needs ATLAS_OWNER_KEY)

The Daily High Five is one decision a day. From the board's priced legs
(`atlas/owner/board.py`, the NHL's `atlas/owner/nhl_board.py`) and the
pick'em's priced props (`atlas/owner/pickem.py`), all sports together:

* **the five wagers**: the five best sides by expected value across spreads,
  moneylines and totals, at the book that pays best for each, at most one a
  game (two markets of one game are one opinion twice);
* **the five props**: the five likeliest sides of PrizePicks' standard lines
  by the books' fair probability (the pick'em's), at most one a player and two
  a game;
* **a five-leg parlay**, only on a day some one book has five positive-EV
  legs in five different games: the book where the five compound best. Most
  days there is none.

The point is the record of the plays, not the closing line. Each of the ten
(and the parlay) is logged once, at the first run from 10:00 ET on its day,
into a sealed record (``tracking/owner_highfive/`` and
``tracking/owner_highfive_parlays/``), never revised, and graded win, loss or
push on the final score (a prop on ESPN's box score), wagers and the parlay in
units at the price logged. Nothing here is shown outside the owner page's
ciphertext, under a tab the page's script does not name.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import uuid
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from atlas.owner import paper, parlays, pickem, sealed
from atlas.sources import bettingpros as bp
from atlas.util import get_logger

LOG = get_logger(__name__)

NAMESPACE = uuid.UUID("b3a1d7e2-6c4f-4b89-8d15-2f0e9a7c5b31")
TAB = "High Five"
#: Plays of each kind in a day's High Five, and in the parlay.
SIZE = 5
#: A prop must be at least this likely (the pick'em's floor); a wager must have positive expected value.
PROP_FLOOR = pickem.PICK_FLOOR
MIN_EV = 0.0
#: At most this many props from one game.
PER_GAME = 2
#: A kind's day is logged at the first run at or after this hour, Eastern, on that day.
LOG_HOUR = 10
BY_DAY = 14
LATEST = 10

COLUMNS = ["pick_id", "kind", "rank", "day", "logged_at", "sport", "season", "week", "game_id", "kickoff", "game",
           "market", "side", "line", "book_id", "cost", "p", "ev", "basis", "player_key", "player", "team", "books",
           "p_push", "actual", "outcome", "profit", "graded_at"]
WAGER, PROP = "wager", "prop"


def path() -> Path:
    from atlas.live.store import tracking_dir

    return tracking_dir() / "owner_highfive"


def parlay_path() -> Path:
    from atlas.live.store import tracking_dir

    return tracking_dir() / "owner_highfive_parlays"


def pick_id(kind: str, game_id, market: str, side: str, player_key="") -> str:
    return str(uuid.uuid5(NAMESPACE, f"{kind}|{game_id}|{market}|{side}|{player_key or ''}"))


# ---------------------------------------------------------------------------
# Choosing
# ---------------------------------------------------------------------------


def pick_wagers(legs: pd.DataFrame, now: datetime, size: int = SIZE) -> pd.DataFrame:
    """The day's best wagers: the board's positive-EV legs (Atlas EV on football totals and every NHL market,
    price edge on football spreads), the best price for each game's best side, best first. ``rank`` counts."""
    c = parlays.candidates(legs, now)
    if c.empty:
        return c.assign(rank=pd.Series(dtype=int), basis=pd.Series(dtype=str))
    c = c.sort_values(["score", "game_id", "market", "side"], ascending=[False, True, True, True], kind="stable")
    c = c.drop_duplicates("game_id", keep="first").head(size).reset_index(drop=True)
    c["rank"] = np.arange(1, len(c) + 1)
    c["basis"] = np.where(parlays.atlas_measured(c), "atlas", "market")
    return c


def pick_props(priced: pd.DataFrame | None, now: datetime, size: int = SIZE) -> pd.DataFrame:
    """The day's likeliest props: PrizePicks' standard lines, the likelier side of each, from the floor, not
    started; one a player, at most :data:`PER_GAME` a game; likeliest first."""
    if priced is None or priced.empty:
        return pd.DataFrame(columns=[*(priced.columns if priced is not None else pickem.PRICED_COLUMNS), "rank"])
    p = priced.copy()
    p["kickoff"] = pd.to_datetime(p["kickoff"], utc=True, errors="coerce")
    p = p[(p["kickoff"] > pd.Timestamp(now)) & (p["p"] >= PROP_FLOOR)]
    p = p.sort_values(["p", "books", "player_key", "market"], ascending=[False, False, True, True], kind="stable")
    p = p.drop_duplicates("player_key", keep="first")
    p = p[p.groupby("game_id").cumcount() < PER_GAME].head(size).reset_index(drop=True)
    p["rank"] = np.arange(1, len(p) + 1)
    return p


def pick_parlay(legs: pd.DataFrame, names: dict, now: datetime) -> pd.DataFrame:
    """The five-leg parlay, when there is one: the book whose five best legs (five different games) compound
    best. A parlay's expected value is the product of its legs' (1 + EV), so each book's best five are its
    five highest; empty when no book has five."""
    empty = pd.DataFrame(columns=[*parlays.COLUMNS, "oldest_quote"])
    cands = parlays.candidates(legs, now)
    if cands.empty:
        return empty
    table = parlays.combine(cands, names, now, max_legs=SIZE, per_book=SIZE, top=10_000)
    table = table[table["n_legs"] == SIZE] if len(table) else table
    if table.empty:
        return empty
    return table.sort_values(["ev", "book_id"], ascending=[False, True], kind="stable").head(1).reset_index(drop=True)


# ---------------------------------------------------------------------------
# The record
# ---------------------------------------------------------------------------


def load(passphrase: str, where: Path | None = None) -> pd.DataFrame:
    rows = sealed.load(where or path(), passphrase)
    return pd.DataFrame(rows, columns=COLUMNS) if rows else pd.DataFrame(columns=COLUMNS)


def seal(record: pd.DataFrame, passphrase: str, weeks: set, where: Path | None = None) -> list[Path]:
    where = where or path()
    out = []
    for season, week in sorted(weeks):
        part = record[(pd.to_numeric(record["season"]) == season) & (pd.to_numeric(record["week"]) == week)]
        rows = json.loads(part.reindex(columns=COLUMNS).to_json(orient="records"))
        names = [r.get(k) for r in rows for k in ("game", "player")]
        out.append(sealed.seal(rows, passphrase, sealed.week_file(where, season, week), names=names))
    return out


def due(record: pd.DataFrame, kind: str, day, now: datetime) -> bool:
    """Is this the run that logs ``kind`` for ``day``: at or after :data:`LOG_HOUR` Eastern on that day,
    and none of that kind logged for it yet."""
    from atlas.owner.board import EASTERN

    local = pd.Timestamp(now).tz_convert(EASTERN)
    if str(day) != local.strftime("%Y-%m-%d") or local.hour < LOG_HOUR:
        return False
    return not (len(record) and ((record["kind"] == kind) & (record["day"].astype(str) == str(day))).any())


def _filed(sport, game_id, kickoff, season, week, week_of: dict) -> tuple[int, int]:
    """Where a row is filed: the NHL by the ISO week of puck drop, football by its season and week."""
    if str(sport) != "nhl":
        for s, w in ((season, week), week_of.get(str(game_id), (None, None))):
            try:
                if s is not None and w is not None and math.isfinite(float(s)) and math.isfinite(float(w)):
                    return int(s), int(w)
            except (TypeError, ValueError):
                continue
    return pickem.filed(sport, kickoff)


def _blank(kind: str, day: str, stamp: str) -> dict:
    return {c: None for c in COLUMNS} | {"kind": kind, "day": day, "logged_at": stamp}


def wager_rows(chosen: pd.DataFrame, names: dict, week_of: dict, stamp: str) -> list[dict]:
    rows = []
    for r in chosen.itertuples():
        season, week = _filed(r.sport, r.game_id, r.kickoff, r.season, r.week, week_of)
        rows.append(_blank(WAGER, str(r.day), stamp) | {
            "pick_id": pick_id(WAGER, r.game_id, r.market, r.side), "rank": int(r.rank), "sport": str(r.sport),
            "season": season, "week": week, "game_id": str(r.game_id), "kickoff": pickem._stamp(r.kickoff),
            "game": names.get(str(r.game_id), str(r.game_id)), "market": r.market, "side": r.side,
            "line": float(r.line), "book_id": int(r.book_id), "cost": float(r.cost), "p": round(float(r.p), 4),
            "ev": round(float(r.score), 4), "basis": r.basis})
    return rows


def prop_rows(chosen: pd.DataFrame, names: dict, week_of: dict, stamp: str) -> list[dict]:
    rows = []
    for r in chosen.itertuples():
        season, week = _filed(r.sport, r.game_id, r.kickoff, None, None, week_of)
        rows.append(_blank(PROP, str(r.day), stamp) | {
            "pick_id": pick_id(PROP, r.game_id, r.market, r.side, r.player_key), "rank": int(r.rank),
            "sport": str(r.sport), "season": season, "week": week, "game_id": str(r.game_id),
            "kickoff": pickem._stamp(r.kickoff), "game": names.get(str(r.game_id), str(r.game_id)),
            "market": r.market, "side": r.side, "line": float(r.line), "p": round(float(r.p), 4),
            "player_key": str(r.player_key), "player": r.player, "team": r.team, "books": int(r.books),
            "p_push": round(float(r.p_push), 4)})
    return rows


def log(record: pd.DataFrame, wagers: pd.DataFrame, props: pd.DataFrame, names: dict, games: pd.DataFrame,
        now: datetime) -> tuple[pd.DataFrame, set]:
    """Each kind's five, once a day, at the lines and prices on the board now; a logged play is never revised.
    Returns the record and the (season, week) files touched."""
    week_of = {}
    if not games.empty:
        week_of = {str(g): (s, w) for g, s, w in zip(games["game_id"], games["season"], games["week"], strict=True)}
    stamp = pickem._stamp(now)
    fresh: list[dict] = []
    for kind, chosen, make in ((WAGER, wagers, wager_rows), (PROP, props, prop_rows)):
        if chosen.empty:
            continue
        day = str(chosen["day"].iloc[0])
        if due(record, kind, day, now):
            fresh += make(chosen, names, week_of, stamp)
    if not fresh:
        return record, set()
    new = pd.DataFrame(fresh, columns=COLUMNS)
    if len(record):
        new = new[~new["pick_id"].isin(set(record["pick_id"]))]
    if new.empty:
        return record, set()
    weeks = {(int(a), int(b)) for a, b in new[["season", "week"]].drop_duplicates().itertuples(index=False)}
    parts = [record.reindex(columns=COLUMNS), new] if len(record) else [new]
    return pd.concat(parts, ignore_index=True).reindex(columns=COLUMNS), weeks


def grade(record: pd.DataFrame, finals: pd.DataFrame, games: pd.DataFrame, now: datetime,
          box=pickem.box_score) -> tuple[pd.DataFrame, set]:
    """Settle every open play whose game is final: wagers on the final score at the price logged, props on
    ESPN's box score (a player who did not play is void). Returns the record and the files that changed."""
    if record.empty:
        return record, set()
    record = record.copy()
    changed: set = set()
    stamp = pickem._stamp(now)
    for i in record.index[(record["kind"] == WAGER) & record["outcome"].isna()]:
        r = record.loc[i]
        result = parlays.leg_outcome({"game_id": r["game_id"], "market": r["market"], "side": r["side"],
                                      "line": r["line"]}, finals)
        if result == "open":
            continue
        profit = paper.payout(float(r["cost"])) if result == "win" else (-1.0 if result == "loss" else 0.0)
        record.loc[i, ["outcome", "profit", "graded_at"]] = [result, profit, stamp]
        changed.add((int(r["season"]), int(r["week"])))
    props = record[record["kind"] == PROP]
    if len(props):
        settled, weeks = pickem.grade(props, games, now, box)
        if weeks:
            cols = ["actual", "outcome", "graded_at"]
            record.loc[settled.index, cols] = settled[cols]
            changed |= weeks
    return record, changed


# ---------------------------------------------------------------------------
# The owner page's view
# ---------------------------------------------------------------------------


def _eastern(ts) -> str:
    from atlas.owner.board import _eastern as east

    return east(ts)


def _wlp(part: pd.DataFrame) -> tuple[int, int, int, int]:
    done = part[part["outcome"].isin(["win", "loss", "push", "void"])] if len(part) else part
    n = lambda k: int((done["outcome"] == k).sum()) if len(done) else 0  # noqa: E731
    return n("win"), n("loss"), n("push"), n("void")


def _wlp_text(part: pd.DataFrame) -> str:
    won, lost, pushed, void = _wlp(part)
    return f"{won}-{lost}-{pushed}" + (f" ({void} void)" if void else "")


def _hit(part: pd.DataFrame) -> str:
    """Hit rate over decided plays, with the mean probability the plays were logged at beside it."""
    decided = part[part["outcome"].isin(["win", "loss"])] if len(part) else part
    if not len(decided):
        return "–"
    rate = float((decided["outcome"] == "win").mean())
    expected = float(pd.to_numeric(decided["p"], errors="coerce").mean())
    return f"{rate:.1%} (expected {expected:.1%})"


def _units(part: pd.DataFrame) -> str:
    done = part[part["outcome"].isin(["win", "loss", "push"])] if len(part) else part
    if not len(done):
        return "–"
    u = float(pd.to_numeric(done["profit"], errors="coerce").sum())
    return f"{paper._num(u)} ({u / len(done):+.1%} a play)"


def _side_word(side) -> str:
    return "Over" if side == "over" else "Under"


def _wager_text(r) -> str:
    market, side, line, game = r["market"], r["side"], float(r["line"]), str(r["game"])
    if market == "total":
        return f"{_side_word(side)} {line:g}"
    away, home = game.split(" @ ", 1) if " @ " in game else ("Away", "Home")
    team = home if side == "home" else away
    return f"{team} ML" if market == "moneyline" else f"{team} {line:+g}"


def _prop_text(r) -> str:
    return f"{_side_word(r['side'])} {float(r['line']):g} {pickem.LABELS.get(r['market'], r['market'])}"


def _status(r) -> str:
    out = r.get("outcome")
    if not isinstance(out, str):
        return "open"
    if r["kind"] == PROP and out in ("win", "loss", "push") and r.get("actual") is not None \
            and pd.notna(r.get("actual")):
        return f"{out} ({float(r['actual']):g})"
    if r["kind"] == WAGER and out in ("win", "loss", "push"):
        return f"{out} {float(r['profit']):+.2f}"
    return out


def _rows_for(kind: str, shown: pd.DataFrame, provisional: bool) -> list[list]:
    rows = []
    for r in shown.to_dict("records"):
        status = "not logged yet" if provisional else _status(r)
        kick = _eastern(r["kickoff"])
        if kind == WAGER:
            basis = "Atlas's probability" if r["basis"] == "atlas" else "price vs the consensus"
            rows.append([str(int(r["rank"])), [str(r["game"]), kick],
                         [f"{_wager_text(r)} ({float(r['cost']):+.0f})", bp.book_name(r["book_id"])],
                         [f"EV {float(r['ev']):+.1%}", f"P {float(r['p']):.0%} · {basis}"], status])
        else:
            rows.append([str(int(r["rank"])), [str(r["player"]), f"{r['game']} · {kick}"], _prop_text(r),
                         [f"P {float(r['p']):.0%}", f"{int(r['books'])} books"], status])
    return rows


def _live_frame(kind: str, chosen: pd.DataFrame, names: dict) -> pd.DataFrame:
    """The day's live candidates in the record's shape, for the page before they are logged."""
    if chosen.empty:
        return pd.DataFrame(columns=COLUMNS)
    made = wager_rows(chosen, names, {}, "") if kind == WAGER else prop_rows(chosen, names, {}, "")
    return pd.DataFrame(made, columns=COLUMNS)


def _day_label(day) -> str:
    return pd.Timestamp(str(day)).strftime("%a %b %-d")


def _by_day(record: pd.DataFrame, tickets: pd.DataFrame) -> list[list]:
    days = set(record["day"].astype(str)) if len(record) else set()
    if len(tickets):
        days |= set(tickets["day"].astype(str))
    rows = []
    for day in sorted(days, reverse=True)[:BY_DAY]:
        part = record[record["day"].astype(str) == day] if len(record) else record
        w, p = part[part["kind"] == WAGER], part[part["kind"] == PROP]
        t = tickets[tickets["day"].astype(str) == day] if len(tickets) else tickets
        ticket = "–" if t.empty else (t["outcome"].iloc[0] if isinstance(t["outcome"].iloc[0], str) else "open")
        if ticket in ("win", "loss", "push") and pd.notna(t["profit"].iloc[0]):
            ticket = f"{ticket} {float(t['profit'].iloc[0]):+.2f}"
        rows.append([_day_label(day), _wlp_text(w) if len(w) else "–", _wlp_text(p) if len(p) else "–",
                     _wlp_text(part) if len(part) else "–", ticket])
    return rows


def sections(chosen_w: pd.DataFrame, chosen_p: pd.DataFrame, ticket: pd.DataFrame, record: pd.DataFrame,
             tickets: pd.DataFrame, names: dict, now: datetime) -> list[dict]:
    """The High Five tab: today's ten and the parlay, then the record, then how it works."""
    live = {WAGER: chosen_w, PROP: chosen_p}
    today = parlays.day_of(now)
    cards = []
    for kind, title, head in ((WAGER, "Top five game wagers", ["#", "Game", "Bet", "Edge", "Result"]),
                              (PROP, "Top five props", ["#", "Player", "Prop", "Edge", "Result"])):
        # Today's logged five while it is today; else the live candidates, for the day they are for.
        mine = record[(record["kind"] == kind) & (record["day"].astype(str) == today)] if len(record) else record
        provisional = not len(mine)
        day = today if not provisional else (str(live[kind]["day"].iloc[0]) if len(live[kind]) else None)
        shown = _live_frame(kind, live[kind], names) if provisional else mine.sort_values("rank")
        if provisional and not len(shown):
            what = "wager with positive expected value" if kind == WAGER else f"prop at {PROP_FLOOR:.0%} or better"
            rows = [[f"No {what} on the board yet.", "", "", "", ""]]
        else:
            rows = _rows_for(kind, shown, provisional)
        label = f"{title}, {_day_label(day)}" if day else title
        if provisional and len(shown):
            label += f": provisional, locks at the first run from {LOG_HOUR}:00 ET"
        cards.append({"title": label, "head": head, "rows": rows, "stack": True})
    # The parlay: today's logged one, else the live one, else why there is none.
    mine = tickets[tickets["day"].astype(str) == today] if len(tickets) else tickets
    shown = mine if len(mine) else ticket
    t_day = str(shown["day"].iloc[0]) if len(shown) else None
    if len(shown):
        r = shown.iloc[0]
        result = r["outcome"] if "outcome" in shown and isinstance(r["outcome"], str) else (
            "open" if len(mine) else "not logged yet")
        if result in ("win", "loss", "push") and pd.notna(r["profit"]):
            result = f"{result} {float(r['profit']):+.2f} ({r['legs_result']})"
        prows = [[[bp.book_name(r["book_id"]), f"{r['american']:+.0f} ({r['dec_odds']:.2f}×)"],
                  " / ".join(parlays._leg_text(lg) for lg in json.loads(r["legs"])),
                  [f"P(hit) {float(r['p_hit']):.1%}", f"EV {float(r['ev']):+.1%}"], result]]
    else:
        prows = [["No book has five positive-expected-value legs in five different games today.", "", "", ""]]
    cards.append({"title": "Five-leg parlay" + (f", {_day_label(t_day)}" if t_day else ""),
                  "head": ["Book · odds", "Legs", "Chance · EV", "Result"], "rows": prows, "stack": True})

    tables = [*cards]
    wag = record[record["kind"] == WAGER] if len(record) else record
    prp = record[record["kind"] == PROP] if len(record) else record
    every = record
    days = lambda part: str(part["day"].nunique()) if len(part) else "0"  # noqa: E731
    tables.append({"title": "The record: what the plays did",
                   "head": ["", "Wagers", "Props", "All plays"],
                   "rows": [["Days logged", days(wag), days(prp), days(every)],
                            ["Plays logged", str(len(wag)), str(len(prp)), str(len(every))],
                            ["Won-lost-push", _wlp_text(wag), _wlp_text(prp), _wlp_text(every)],
                            ["Hit rate", _hit(wag), _hit(prp), _hit(every)],
                            ["Units at the price logged", _units(wag), "no price", "–"]]})
    if len(tickets):
        n = len(tickets)
        won, lost, pushed, _ = _wlp(tickets)
        tables.append({"title": "The five-leg parlays", "head": ["", ""],
                       "rows": [["Logged", str(n)], ["Won-lost-push", f"{won}-{lost}-{pushed}"],
                                ["Units at the odds logged", _units(tickets)]]})
    by_day = _by_day(record, tickets)
    if by_day:
        tables.append({"title": "Day by day", "head": ["Day", "Wagers", "Props", "All ten", "Parlay"],
                       "rows": by_day, "stack": True})
    graded = record[record["outcome"].isin(["win", "loss", "push", "void"])] if len(record) else record
    if len(graded):
        latest = graded.sort_values(["kickoff", "kind", "rank"], ascending=[False, True, True]).head(LATEST)
        rows = []
        for r in latest.to_dict("records"):
            what = _wager_text(r) if r["kind"] == WAGER else f"{r['player']} {_prop_text(r)}"
            rows.append([_day_label(r["day"]), r["kind"], [what, str(r["game"])], _status(r)])
        tables.append({"title": "Latest graded plays", "head": ["Day", "Kind", "Play", "Result"], "rows": rows,
                       "stack": True})
    notes = [
        "The Daily High Five is ten plays and, on some days, a parlay, chosen once a day. Five are game wagers "
        "(spread, moneyline, total) and five are props, from every sport on the board at once, and the record is "
        "what those plays did, win or lose, not whether the line later moved toward them.",
        "Wagers are ranked by expected value at the best price any takeable book quotes. Football totals and every "
        "NHL market are valued on Atlas's probability (the board's calibrated one); football spreads have only the "
        "price edge against the consensus, since Atlas adds nothing there. These are different kinds of claim on "
        "one scale: the row says which it is. At most one wager a game. A day with fewer than five positive-EV "
        "wagers logs fewer than five.",
        f"Props are PrizePicks' standard lines (More and Less both offered), ranked by the likelier side's fair "
        f"probability (the median of the books quoting, moved to PrizePicks' line; the pick'em's own), from "
        f"{PROP_FLOOR:.0%}. At most one prop a player and {PER_GAME} a game. A tie on a whole-number line is a "
        "push; a player who did not play is void and drops out of the count. PrizePicks pays by slip, not by "
        "pick, so a prop has no units, only a hit rate against the probability it was logged at.",
        f"The parlay is logged only when one sportsbook has {SIZE} positive-EV legs in {SIZE} different games "
        f"(never the same game): its {SIZE} best. Its expected value is the product of the legs' (1 + EV), so it is "
        "positive by construction whenever it exists; it compounds the model's errors as it compounds the edges, "
        "and the record is the test. A pushed leg drops out and the odds reduce, as the books settle it.",
        f"Each kind is logged once, at the first run from {LOG_HOUR}:00 ET on its day, at the line and price shown, "
        f"sealed and never revised; before then the tables are live and marked provisional. Built {_eastern(now)} ET. "
        "Nothing is read from a few days: a hit rate on fewer than a hundred plays is noise either way.",
    ]
    return [{"title": "Daily High Five", "tab": TAB, "notes": notes, "tables": tables}]


# ---------------------------------------------------------------------------
# The step
# ---------------------------------------------------------------------------


def build(legs: pd.DataFrame, priced: pd.DataFrame | None, finals: pd.DataFrame, games: pd.DataFrame, names: dict,
          passphrase: str, now: datetime, *, where: Path | None = None, parlays_where: Path | None = None,
          box=pickem.box_score) -> list[dict]:
    """Choose, log once, grade and show the day's High Five. Never raises."""
    try:
        where, parlays_where = where or path(), parlays_where or parlay_path()
        wagers = pick_wagers(legs, now)
        props = pick_props(priced, now)
        ticket = pick_parlay(legs, names, now)
        record = load(passphrase, where)
        record, weeks = log(record, wagers, props, names, games, now)
        if weeks:
            LOG.info("highfive: logged %d plays", int(sum(record["logged_at"] == pickem._stamp(now))))
        record, settled = grade(record, finals, games, now, box)
        if weeks | settled:
            seal(record, passphrase, weeks | settled, where)
        tickets = parlays.load(passphrase, parlays_where)
        if parlays.due(tickets, ticket, now):
            tickets, tweeks = parlays.log(tickets, ticket)
            if tweeks:
                parlays.seal(tickets, passphrase, tweeks, parlays_where)
                LOG.info("highfive: a five-leg parlay logged")
        tickets = parlays.grade(tickets, finals) if len(tickets) else tickets.assign(
            outcome=pd.Series(dtype=str), profit=pd.Series(dtype=float), legs_result=pd.Series(dtype=str))
        return sections(wagers, props, ticket, record, tickets, names, now)
    except Exception as error:  # noqa: BLE001 - the type only: a message could quote a line
        from atlas.util import where as place

        LOG.error("highfive not built: %s at %s", type(error).__name__, place(error))
        return [{"title": "Daily High Five", "tab": TAB,
                 "notes": [f"This run could not build the High Five ({type(error).__name__})."], "tables": []}]


def main() -> None:
    argparse.ArgumentParser(description="The High Five's record").parse_args()
    from atlas.dfs import owner

    passphrase = os.environ.get(owner.SECRET, "")
    if not passphrase.strip():
        raise SystemExit(f"{owner.SECRET} is not set")
    record = load(passphrase)
    tickets = parlays.load(passphrase, parlay_path())
    print(f"{len(record)} plays and {len(tickets)} parlays logged")
    if len(record):
        for kind in (WAGER, PROP):
            part = record[record["kind"] == kind]
            print(f"{kind}: {_wlp_text(part)}, hit rate {_hit(part)}, units {_units(part)}")
        print(f"all: {_wlp_text(record)}")


if __name__ == "__main__":
    main()
