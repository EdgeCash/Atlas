"""The daily plays: the few wagers a day that pass a tested bar, logged once, graded on what they did.

    python -m atlas.owner.highfive          # the record, to the terminal (needs ATLAS_OWNER_KEY)

Begun as the "Daily High Five" (five wagers, five props, a parlay); the
backtest that followed (`reports/highfive_backtest.md`) killed the fixed five:
ranking by how far Atlas disagrees with the close selects nothing in
football, and NHL underdogs it liked lost. What survived is rule ``daily-v1``
(`docs/DAILY_PLAYS_PREREGISTRATION.md`), frozen before its record began:

* **NHL**: the side the market already favours, when Atlas (shrunk toward the
  market as the board shrinks it) still has positive expected value at the
  best takeable book. On 2013-22 Atlas's favourite-side picks hit 61% against
  a market fair of 58%; its underdog picks added nothing.
* **Football**: totals and spreads on Atlas's side of the line, ranked by the
  price edge at the best book against the consensus, when that edge is
  positive. The size of Atlas's disagreement is not the rank: it carries no
  signal.

At most :data:`MAX_PLAYS` a day, one a game, and usually one or two. Nothing
is padded. Each play is logged once, at the first run from 10:00 ET on its
day, into a sealed record (``tracking/owner_highfive/``), never revised, and
graded win, loss or push on the final score in units at the price logged.
Three labels ride with each play for the record to test, never as filters:
the model's hit rate over its last hundred results in that market (``form``),
the market's own probability of the side (``p_fair``), and whether an NHL
play falls in the first four weeks of its season (``early``: on 2013-22
Atlas's favourite-side picks in that window beat the market's probability by
5.7 points, a post-hoc slice registered as a label in
`docs/DAILY_PLAYS_PREREGISTRATION.md`). Shown only inside the owner page's
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
RULE = "daily-v1"
TAB = "Daily"
#: A ceiling, not a target: the bar decides how many there are.
MAX_PLAYS = 5
MIN_EV = 0.0
#: The form label: the model's hit rate over this many of its latest decided results in the market.
FORM_WINDOW = 100
FORM_BAR = 0.50
#: The early label: an NHL play inside this many days of its season's first puck drop (the walk-forward's
#: weeks 1-4, `atlas/models/nhl_projection.week_of`).
EARLY_DAYS = 28
#: The day's plays are logged at the first run at or after this hour, Eastern, on that day.
LOG_HOUR = 10
MIN_GRADED = 100
BY_DAY = 14
LATEST = 10

COLUMNS = ["pick_id", "rule", "rank", "day", "logged_at", "sport", "season", "week", "game_id", "kickoff", "game",
           "market", "side", "line", "book_id", "cost", "p", "p_fair", "ev", "basis", "form", "early", "outcome",
           "profit", "graded_at"]
#: Which calibration market a play's market is graded in (`tracking/calibration.csv`).
CALIBRATION_MARKET = {"spread": "margin", "total": "total", "moneyline": "moneyline"}


def path() -> Path:
    from atlas.live.store import tracking_dir

    return tracking_dir() / "owner_highfive"


def pick_id(game_id, market: str, side: str) -> str:
    return str(uuid.uuid5(NAMESPACE, f"{RULE}|{game_id}|{market}|{side}"))


# ---------------------------------------------------------------------------
# Choosing
# ---------------------------------------------------------------------------


def atlas_side(t: pd.DataFrame) -> pd.Series:
    """Is each leg's side the one Atlas's number favours? Totals against the leg's line; spreads by
    the side's own margin plus its handicap; the NHL by the shrunk probability the leg carries."""
    number = pd.to_numeric(t["atlas_number"], errors="coerce")
    line = pd.to_numeric(t["line"], errors="coerce")
    p_atlas = pd.to_numeric(t["p_atlas"], errors="coerce")
    nhl = t["sport"].astype(str) == "nhl"
    total = t["market"] == "total"
    over = t["side"] == "over"
    own = np.where(t["side"] == "home", number, -number)
    out = np.where(nhl, p_atlas > 0.5,
                   np.where(total, np.where(over, number > line, number < line), own + line > 0))
    return pd.Series(out & number.notna().to_numpy() | (nhl & p_atlas.notna()).to_numpy(), index=t.index)


def form(calibration: pd.DataFrame | None, now: datetime, window: int = FORM_WINDOW) -> dict[tuple[str, str], float]:
    """The model's hit rate over its latest ``window`` decided results per (sport, calibration market),
    from games that kicked off before ``now``. Empty when the table is missing or thin."""
    if calibration is None or calibration.empty:
        return {}
    c = calibration.dropna(subset=["won"]).copy()
    c = c[c["won"] != 0.5]
    kick = pd.to_datetime(c["kickoff"], utc=True, format="ISO8601", errors="coerce")
    c = c[kick.notna() & (kick < pd.Timestamp(now))].assign(kick=kick).sort_values("kick")
    out = {}
    for (sport, market), part in c.groupby([c["sport"].fillna("ncaaf").astype(str), "market"]):
        if len(part) >= window:
            out[(sport, str(market))] = float((part["won"].tail(window) == 1.0).mean())
    return out


def openers(games: pd.DataFrame | None, nhl_projections: pd.DataFrame | None) -> tuple[dict, dict]:
    """What the early label needs: each NHL season's first puck drop the store knows of, and each NHL game's
    season, from the tracked games and the projections. A season the store has no games of has no opener,
    and its plays' label is unknown rather than guessed."""
    parts = []
    for t in (games, nhl_projections):
        if t is None or t.empty or not {"game_id", "season", "kickoff"} <= set(t.columns):
            continue
        part = t[t["sport"].astype(str) == "nhl"] if "sport" in t else t
        parts.append(part[["game_id", "season", "kickoff"]])
    if not parts:
        return {}, {}
    g = pd.concat(parts, ignore_index=True)
    g = g.assign(game_id=g["game_id"].astype(str), season=pd.to_numeric(g["season"], errors="coerce"),
                 kickoff=pd.to_datetime(g["kickoff"], utc=True, errors="coerce")).dropna()
    first = g.groupby("season")["kickoff"].min()
    return {int(s): k for s, k in first.items()}, dict(zip(g["game_id"], g["season"].astype(int), strict=True))


def early(t: pd.DataFrame, first: dict, season_of: dict) -> list:
    """The early label per leg: True inside :data:`EARLY_DAYS` of the NHL season's first puck drop, False
    after, None for football and for a game whose season or opener is unknown."""
    out = []
    for r in t.itertuples():
        season = season_of.get(str(r.game_id))
        if str(r.sport) != "nhl" or season is None or season not in first or pd.isna(r.kickoff):
            out.append(None)
            continue
        out.append(bool(pd.Timestamp(r.kickoff) < first[season] + pd.Timedelta(days=EARLY_DAYS)))
    return out


def pick_wagers(legs: pd.DataFrame, now: datetime, calibration: pd.DataFrame | None = None,
                cap: int = MAX_PLAYS, first: dict | None = None, season_of: dict | None = None) -> pd.DataFrame:
    """Rule ``daily-v1`` on today's legs (the Eastern day of ``now`` with games, else the next): NHL sides the
    market favours with positive Atlas EV, ranked by it; football sides on Atlas's side of the line with
    positive price edge, ranked by it; one a game at its best book; at most ``cap``. Empty columns when
    nothing passes."""
    extra = ["score", "p", "day", "rank", "basis", "form", "early"]
    if legs.empty:
        return legs.reindex(columns=[*legs.columns, *extra])
    t = legs.copy()
    t["kickoff"] = pd.to_datetime(t["kickoff"], utc=True, errors="coerce")
    t = t[t["kickoff"] > pd.Timestamp(now)]
    t = t[atlas_side(t)]
    nhl = t["sport"].astype(str) == "nhl"
    t = t[~nhl | (pd.to_numeric(t["p_fair"], errors="coerce") >= 0.5)]
    nhl = t["sport"].astype(str) == "nhl"
    t["score"] = np.where(nhl, pd.to_numeric(t["ev_atlas"], errors="coerce"), pd.to_numeric(t["ev_price"], errors="coerce"))
    t["p"] = np.where(nhl, t["p_atlas"], t["p_fair"])
    t["basis"] = np.where(nhl, "atlas", "price")
    t = t[(t["score"] > MIN_EV) & pd.to_numeric(t["p"], errors="coerce").between(0.05, 0.95)]
    if t.empty:
        return t.reindex(columns=[*legs.columns, *extra])
    t["day"] = t["kickoff"].map(parlays.day_of)
    today = parlays.day_of(now)
    day = today if (t["day"] == today).any() else t["day"].min()
    t = t[t["day"] == day].sort_values(["score", "game_id", "market", "side"], ascending=[False, True, True, True],
                                       kind="stable")
    t = t.drop_duplicates("game_id", keep="first").head(cap).reset_index(drop=True)
    t["rank"] = np.arange(1, len(t) + 1)
    f = form(calibration, now)
    t["form"] = [f.get((str(s), CALIBRATION_MARKET.get(str(m), str(m))), np.nan)
                 for s, m in zip(t["sport"], t["market"], strict=True)]
    t["early"] = early(t, first or {}, season_of or {})
    return t


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
        out.append(sealed.seal(rows, passphrase, sealed.week_file(where, season, week), names=[r.get("game") for r in rows]))
    return out


def due(record: pd.DataFrame, day, now: datetime) -> bool:
    """Is this the run that logs ``day``: at or after :data:`LOG_HOUR` Eastern on that day, and nothing
    logged for it yet."""
    from atlas.owner.board import EASTERN

    local = pd.Timestamp(now).tz_convert(EASTERN)
    if str(day) != local.strftime("%Y-%m-%d") or local.hour < LOG_HOUR:
        return False
    return not (len(record) and (record["day"].astype(str) == str(day)).any())


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


def rows_for(chosen: pd.DataFrame, names: dict, week_of: dict, stamp: str) -> list[dict]:
    rows = []
    for r in chosen.itertuples():
        season, week = _filed(r.sport, r.game_id, r.kickoff, r.season, r.week, week_of)
        rows.append({c: None for c in COLUMNS} | {
            "pick_id": pick_id(r.game_id, r.market, r.side), "rule": RULE, "rank": int(r.rank), "day": str(r.day),
            "logged_at": stamp, "sport": str(r.sport), "season": season, "week": week, "game_id": str(r.game_id),
            "kickoff": pickem._stamp(r.kickoff), "game": names.get(str(r.game_id), str(r.game_id)),
            "market": r.market, "side": r.side, "line": float(r.line), "book_id": int(r.book_id), "cost": float(r.cost),
            "p": round(float(r.p), 4), "p_fair": round(float(r.p_fair), 4) if pd.notna(r.p_fair) else None,
            "ev": round(float(r.score), 4), "basis": r.basis,
            "form": round(float(r.form), 4) if pd.notna(r.form) else None,
            "early": None if r.early is None or (isinstance(r.early, float) and np.isnan(r.early)) else bool(r.early)})
    return rows


def log(record: pd.DataFrame, chosen: pd.DataFrame, names: dict, games: pd.DataFrame,
        now: datetime) -> tuple[pd.DataFrame, set]:
    """The day's plays, once, at the lines and prices on the board now; a logged play is never revised.
    Returns the record and the (season, week) files touched."""
    if chosen.empty or not due(record, str(chosen["day"].iloc[0]), now):
        return record, set()
    week_of = {}
    if not games.empty:
        week_of = {str(g): (s, w) for g, s, w in zip(games["game_id"], games["season"], games["week"], strict=True)}
    new = pd.DataFrame(rows_for(chosen, names, week_of, pickem._stamp(now)), columns=COLUMNS)
    if len(record):
        new = new[~new["pick_id"].isin(set(record["pick_id"]))]
    if new.empty:
        return record, set()
    weeks = {(int(a), int(b)) for a, b in new[["season", "week"]].drop_duplicates().itertuples(index=False)}
    parts = [record.reindex(columns=COLUMNS), new] if len(record) else [new]
    return pd.concat(parts, ignore_index=True).reindex(columns=COLUMNS), weeks


def grade(record: pd.DataFrame, finals: pd.DataFrame, now: datetime) -> tuple[pd.DataFrame, set]:
    """Settle every open play whose game is final, on the score at the price logged. Returns the record
    and the files that changed."""
    if record.empty:
        return record, set()
    record = record.copy()
    changed: set = set()
    stamp = pickem._stamp(now)
    for i in record.index[record["outcome"].isna()]:
        r = record.loc[i]
        result = parlays.leg_outcome({"game_id": r["game_id"], "market": r["market"], "side": r["side"],
                                      "line": r["line"]}, finals)
        if result == "open":
            continue
        profit = paper.payout(float(r["cost"])) if result == "win" else (-1.0 if result == "loss" else 0.0)
        record.loc[i, ["outcome", "profit", "graded_at"]] = [result, profit, stamp]
        changed.add((int(r["season"]), int(r["week"])))
    return record, changed


# ---------------------------------------------------------------------------
# The owner page's view
# ---------------------------------------------------------------------------


def _eastern(ts) -> str:
    from atlas.owner.board import _eastern as east

    return east(ts)


def _wlp(part: pd.DataFrame) -> tuple[int, int, int]:
    done = part[part["outcome"].isin(["win", "loss", "push"])] if len(part) else part
    n = lambda k: int((done["outcome"] == k).sum()) if len(done) else 0  # noqa: E731
    return n("win"), n("loss"), n("push")


def _wlp_text(part: pd.DataFrame) -> str:
    won, lost, pushed = _wlp(part)
    return f"{won}-{lost}-{pushed}"


def _record_rows(part: pd.DataFrame) -> list[str]:
    """Won-lost-push, hit rate with its 95% range and the mean probability logged, break-even at the prices
    taken, units and per play."""
    decided = part[part["outcome"].isin(["win", "loss"])] if len(part) else part
    done = part[part["outcome"].isin(["win", "loss", "push"])] if len(part) else part
    if not len(decided):
        return [_wlp_text(part), "–", "–", "–", "–"]
    wins = int((decided["outcome"] == "win").sum())
    lo, hi = paper.wilson(wins, len(decided))
    be = float(len(decided) / (1.0 + pd.to_numeric(decided["cost"], errors="coerce").map(paper.payout)).sum())
    units = float(pd.to_numeric(done["profit"], errors="coerce").sum())
    return [_wlp_text(part), f"{wins / len(decided):.1%} ({lo:.0%}–{hi:.0%})",
            f"{be:.1%} (logged at {pd.to_numeric(decided['p'], errors='coerce').mean():.1%})",
            paper._num(units), f"{units / len(done):+.1%}"]


def _side_word(side) -> str:
    return "Over" if side == "over" else "Under"


def _text(r) -> str:
    market, side, line, game = r["market"], r["side"], float(r["line"]), str(r["game"])
    if market == "total":
        return f"{_side_word(side)} {line:g}"
    away, home = game.split(" @ ", 1) if " @ " in game else ("Away", "Home")
    team = home if side == "home" else away
    return f"{team} ML" if market == "moneyline" else f"{team} {line:+g}"


def _status(r) -> str:
    out = r.get("outcome")
    if not isinstance(out, str):
        return "open"
    return f"{out} {float(r['profit']):+.2f}" if out in ("win", "loss", "push") else out


def _labels(r) -> str:
    out = []
    f = r.get("form")
    if f is not None and pd.notna(f):
        out.append(f"form {float(f):.0%}")
    pf = r.get("p_fair")
    if pf is not None and pd.notna(pf) and str(r.get("sport")) == "nhl":
        out.append(f"market {float(pf):.0%}")
    if r.get("early") is True:
        out.append("first month")
    return " · ".join(out)


def _rows(shown: pd.DataFrame, provisional: bool) -> list[list]:
    rows = []
    for r in shown.to_dict("records"):
        basis = "Atlas, market favourite" if r["basis"] == "atlas" else "price vs consensus, Atlas's side"
        rows.append([str(int(r["rank"])), [str(r["game"]), _eastern(r["kickoff"])],
                     [f"{_text(r)} ({float(r['cost']):+.0f})", bp.book_name(r["book_id"])],
                     [f"EV {float(r['ev']):+.1%}", f"P {float(r['p']):.0%} · {basis}"],
                     [("not logged yet" if provisional else _status(r)), _labels(r)]])
    return rows


def _day_label(day) -> str:
    return pd.Timestamp(str(day)).strftime("%a %b %-d")


def sections(chosen: pd.DataFrame, record: pd.DataFrame, names: dict, now: datetime) -> list[dict]:
    """The Daily tab: today's plays, the record, its pre-registered splits, day by day, the latest graded."""
    today = parlays.day_of(now)
    mine = record[record["day"].astype(str) == today] if len(record) else record
    provisional = not len(mine)
    if provisional:
        shown = pd.DataFrame(rows_for(chosen, names, {}, ""), columns=COLUMNS) if len(chosen) else chosen
        day = str(chosen["day"].iloc[0]) if len(chosen) else None
    else:
        shown, day = mine.sort_values("rank"), today
    head = ["#", "Game", "Bet", "Edge", "Result"]
    if len(shown):
        rows = _rows(shown, provisional)
    else:
        rows = [["No play passes the bar on the board yet.", "", "", "", ""]]
    title = f"Plays for {_day_label(day)}" if day else "Plays"
    if provisional and len(shown):
        title += f": provisional, locks at the first run from {LOG_HOUR}:00 ET"
    tables = [{"title": title, "head": head, "rows": rows, "stack": True}]
    if len(record):
        splits = [("All plays", record), ("NHL, Atlas's favourite", record[record["basis"] == "atlas"]),
                  ("Football, price edge", record[record["basis"] == "price"])]
        f = pd.to_numeric(record["form"], errors="coerce")
        splits += [(f"Form at or above {FORM_BAR:.0%} when logged", record[f >= FORM_BAR]),
                   (f"Form below {FORM_BAR:.0%}", record[f < FORM_BAR])]
        e = record["early"] if "early" in record else pd.Series(None, index=record.index)
        splits += [("NHL, first four weeks of the season", record[e.eq(True)]),
                   ("NHL, from the fifth week", record[e.eq(False)])]
        days = int(record["day"].nunique())
        tables.append({"title": f"The record ({days} {'day' if days == 1 else 'days'}, {len(record)} plays)",
                       "head": ["", "W-L-P", "Hit rate (95%)", "Break-even (logged P)", "Units", "Per play"],
                       "rows": [[name, *_record_rows(part)] for name, part in splits if len(part)], "stack": True})
        by_day = []
        for d in sorted(set(record["day"].astype(str)), reverse=True)[:BY_DAY]:
            part = record[record["day"].astype(str) == d]
            done = part[part["outcome"].isin(["win", "loss", "push"])]
            by_day.append([_day_label(d), str(len(part)), _wlp_text(part),
                           paper._num(float(pd.to_numeric(done["profit"], errors="coerce").sum())) if len(done) else "–"])
        tables.append({"title": "Day by day", "head": ["Day", "Plays", "W-L-P", "Units"], "rows": by_day, "stack": True})
        graded = record[record["outcome"].isin(["win", "loss", "push"])]
        if len(graded):
            latest = graded.sort_values(["kickoff", "rank"], ascending=[False, True]).head(LATEST)
            tables.append({"title": "Latest graded plays", "head": ["Day", "Play", "Price", "Result"],
                           "rows": [[_day_label(r["day"]), [_text(r), str(r["game"])],
                                     [f"{float(r['cost']):+.0f}", bp.book_name(r["book_id"])], _status(r)]
                                    for r in latest.to_dict("records")], "stack": True})
    notes = [
        f"Rule {RULE}, frozen 30 September 2026 (docs/DAILY_PLAYS_PREREGISTRATION.md). The few plays a day that pass "
        "a bar the backtest supported, however few: nothing is padded to a number, and a day with none logs none.",
        "NHL: the side the market already favours, when Atlas, shrunk toward the market as the board shrinks it, "
        "still has positive expected value at the best takeable book; ranked by that. On 2013-22 Atlas's "
        "favourite-side picks hit 61% against a market fair of 58%, and its underdog picks added nothing "
        "(reports/highfive_backtest.md).",
        "Football: totals and spreads on Atlas's side of the line, ranked by the price edge at the best book against "
        "the consensus, when it is positive. The size of Atlas's disagreement is not the rank: by quintile it "
        "carries no signal, so the shopping edge is what is being bet. Untested historically; this record is the test.",
        f"Each play is logged once, at the first run from {LOG_HOUR}:00 ET on its day, at the line and price shown, "
        f"and graded win, loss or push on the final score in units at that price. Labels, not filters: the model's hit "
        f"rate over its last {FORM_WINDOW} decided results in that market when the play was logged (form), the "
        f"market's probability of the side, and whether an NHL play fell inside the first {EARLY_DAYS} days of its "
        f"season (on 2013-22 Atlas's favourites in that window beat the market's probability by 5.7 points, a slice "
        f"found after the fact and registered as a label). Nothing is read from fewer than {MIN_GRADED} decided plays. "
        f"Built {_eastern(now)} ET.",
    ]
    return [{"title": "Daily plays", "tab": TAB, "notes": notes, "tables": tables}]


# ---------------------------------------------------------------------------
# The step
# ---------------------------------------------------------------------------


def build(legs: pd.DataFrame, finals: pd.DataFrame, games: pd.DataFrame, names: dict, passphrase: str,
          now: datetime, *, calibration: pd.DataFrame | None = None, nhl_projections: pd.DataFrame | None = None,
          where: Path | None = None) -> list[dict]:
    """Choose, log once, grade and show the day's plays. Never raises."""
    try:
        where = where or path()
        first, season_of = openers(games, nhl_projections)
        chosen = pick_wagers(legs, now, calibration, first=first, season_of=season_of)
        record = load(passphrase, where)
        record, weeks = log(record, chosen, names, games, now)
        if weeks:
            LOG.info("daily plays: %d logged", len(chosen))
        record, settled = grade(record, finals, now)
        if weeks | settled:
            seal(record, passphrase, weeks | settled, where)
        return sections(chosen, record, names, now)
    except Exception as error:  # noqa: BLE001 - the type only: a message could quote a line
        from atlas.util import where as place

        LOG.error("daily plays not built: %s at %s", type(error).__name__, place(error))
        return [{"title": "Daily plays", "tab": TAB,
                 "notes": [f"This run could not build the daily plays ({type(error).__name__})."], "tables": []}]


def main() -> None:
    argparse.ArgumentParser(description="The daily plays' record").parse_args()
    from atlas.dfs import owner

    passphrase = os.environ.get(owner.SECRET, "")
    if not passphrase.strip():
        raise SystemExit(f"{owner.SECRET} is not set")
    record = load(passphrase)
    print(f"{len(record)} plays logged over {record['day'].nunique() if len(record) else 0} days")
    for name, part in (("all", record), ("nhl", record[record["basis"] == "atlas"] if len(record) else record),
                       ("football", record[record["basis"] == "price"] if len(record) else record)):
        if len(part):
            print(name, dict(zip(["W-L-P", "hit", "break-even", "units", "per play"], _record_rows(part), strict=True)))


if __name__ == "__main__":
    main()
