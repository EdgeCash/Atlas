"""The owner's NHL board: every book's moneyline, puck line and total priced by the model (MODEL_PLAN_NHL step 6).

For the owner's eyes only, like the football board (`atlas/owner/board.py`),
from the market the capture already seals every poll (`nhl_capture.py`) and
the numbers the heavy refresh publishes (``tracking/nhl_projections.csv``).
Per game, market, side and book:

* **fair**: the consensus book's two prices with the margin taken out, at the
  consensus line (a book at another line is left out: the grid could move it,
  but a price edge read off Atlas's own shape is Atlas's opinion wearing the
  market's clothes);
* **Atlas**: the grid's probability for that side at that line, pulled toward
  fair by the share of its disagreement that has turned out real. That share
  is fitted on the NHL's moneyline record against the closing line
  (``tracking/calibration.csv``): 0.46 of it, about half, over 11,764 games;
* **expected value** at the book's price, by each.

**Picks** are the sides with positive expected value by Atlas at the best
price, one per game on the result (the moneyline or the puck line: one team
either way is one opinion) and one on the total, the best :data:`MAX_PICKS`,
logged once, the
first board at which they qualify, into a sealed record
(``tracking/owner_nhl/``, one file per ISO week), and graded on the final
score (the NHL's, a shootout goal included, as the books settle) and against
the consensus close in win probability.

The same legs feed the day's parlays (`parlays.py`) and, on the game-winner
contract, the exchanges (`trading.py`).
"""

from __future__ import annotations

import json
import math
import uuid
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from atlas.live import probability
from atlas.owner import board, paper, sealed
from atlas.sources import bettingpros as bp
from atlas.util import get_logger

LOG = get_logger(__name__)

SPORT = "nhl"
NAMESPACE = uuid.UUID("8f1d2c3b-4a5e-4f60-9b7a-6c5d4e3f2a19")
MARKETS = ("moneyline", "spread", "total")
MIN_EV = 0.0
MAX_PICKS = 6
#: The share of Atlas's disagreement taken as real when the record is too thin to say.
DEFAULT_SHARE = 0.46
MIN_RECORD = 500
MIN_GRADED = 50
PICK_COLUMNS = ["pick_id", "game_id", "event_id", "kickoff", "away_team", "home_team", "home_abbr", "visitor_abbr",
                "market", "side", "book_id", "line", "cost", "cons_cost", "p_fair", "p_raw", "p_atlas", "ev_price",
                "ev_atlas", "formed_at"]
#: The NHL's legs carry the football board's columns, the grid's own probability, and BettingPros' team codes
#: (the matched events are only the games ahead, so a pick keeps its own codes to read the close by).
LEG_COLUMNS = [*board.LEG_COLUMNS, "p_raw", "home_abbr", "visitor_abbr"]


def path() -> Path:
    from atlas.live.store import tracking_dir

    return tracking_dir() / "owner_nhl"


def share(calibration: pd.DataFrame | None) -> float:
    """How much of Atlas's disagreement with the market has turned out real: least squares through the market
    on the NHL's moneyline record (realised minus market against claimed minus market), clipped to [0, 1]."""
    if calibration is None or calibration.empty:
        return DEFAULT_SHARE
    c = calibration[(calibration["sport"].astype(str) == SPORT) & (calibration["market"] == "moneyline")]
    c = c.dropna(subset=["abs_edge", "claimed", "won"])
    if len(c) < MIN_RECORD:
        return DEFAULT_SHARE
    claimed = pd.to_numeric(c["claimed"], errors="coerce")
    market = claimed - pd.to_numeric(c["abs_edge"], errors="coerce") / 100.0
    d = claimed - market
    denom = float((d * d).sum())
    if denom <= 0:
        return DEFAULT_SHARE
    return float(np.clip(((pd.to_numeric(c["won"], errors="coerce") - market) * d).sum() / denom, 0.0, 1.0))


def atlas_prob(pr, market: str, side: str, line: float) -> float:
    """The grid's probability for a side at a line; nan at a line the projection holds no reading at (a puck
    line other than 1.5, a total other than 4.5 to 7.5, a whole-goal total)."""
    try:
        if market == "moneyline":
            p = float(pr["p_home"])
            return p if side == "home" else 1.0 - p
        if market == "spread":
            # The side's own handicap: -1.5 wins by two or more; +1.5 anything but losing by two or more.
            if abs(abs(line) - 1.5) > 1e-9:
                return float("nan")
            home_by_two, away_by_two = float(pr["p_home_minus_1_5"]), float(pr["p_away_minus_1_5"])
            if side == "home":
                return home_by_two if line < 0 else 1.0 - away_by_two
            return away_by_two if line < 0 else 1.0 - home_by_two
        if market == "total":
            key = f"p_over_{line:.1f}"
            if key in pr and pd.notna(pr[key]):
                p = float(pr[key])
                return p if side == "over" else 1.0 - p
            return float("nan")
    except (TypeError, ValueError, KeyError):
        return float("nan")
    return float("nan")


def ev(p: float, cost: float) -> float:
    return board.ev(p, cost)


def _sides(part: pd.DataFrame, market: str, home: str | None, visitor: str | None) -> pd.Series:
    """home/away (or over/under) per row. A puck line's handicap does not say whose it is (the home side is
    as often +1.5 as -1.5), so, as on the moneyline, a team is known by its code, or as the other of a
    book's two quotes when one of them is known."""
    if market == "total":
        return part["selection"].where(part["selection"].isin(["over", "under"]))
    from atlas.owner import trading

    return trading.moneyline_sides(part, home, visitor)


def _codes(info) -> tuple[str | None, str | None]:
    if info is None:
        return None, None
    return str(info["home_abbr"]), str(info["visitor_abbr"])


def _stamp(kickoff) -> tuple[int, int]:
    """The ISO year and week of puck drop: what the NHL's rows are filed by in the weekly sealed records."""
    t = pd.Timestamp(kickoff)
    t = t.tz_localize("UTC") if t.tzinfo is None else t
    year, week, _ = t.isocalendar()
    return int(year), int(week)


def legs(lines: pd.DataFrame, events: pd.DataFrame, projections: pd.DataFrame, k: float,
         books=None) -> pd.DataFrame:
    """Every takeable book's price on every side of the NHL's three markets, valued, in the football board's
    leg columns: one row per game, market, side and book. ``books`` asks for those books instead (the
    exchanges). A moneyline's line is 0, as the exchanges' is; ``season`` and ``week`` are :func:`_stamp`'s."""
    cols = LEG_COLUMNS
    if lines.empty or projections.empty or events.empty or "sport" not in lines:
        return pd.DataFrame(columns=cols)
    proj = projections.sort_values("refreshed_at").drop_duplicates("game_id", keep="last")
    proj = proj.assign(game_id=proj["game_id"].astype(str)).set_index("game_id")
    ev_by = events.assign(game_id=events["game_id"].astype(str)).drop_duplicates("game_id").set_index("game_id")
    rows = []
    nhl = lines[lines["sport"].astype(str) == SPORT]
    for (game_id, market), part in nhl.assign(game_id=nhl["game_id"].astype(str)).groupby(["game_id", "market"]):
        if market not in MARKETS or game_id not in proj.index:
            continue
        pr = proj.loc[game_id]
        home, visitor = _codes(ev_by.loc[game_id] if game_id in ev_by.index else None)
        live = part[board.quotable(part, [bp.CONSENSUS, *(books or [])])] if books else part[
            bp.takeable(part) | (part["book_id"] == bp.CONSENSUS)]
        live = live.assign(side=_sides(live, market, home, visitor))
        cons = live[live["book_id"] == bp.CONSENSUS]
        pairs = (("over", "under") if market == "total" else ("home", "away"))
        c1, c2 = cons[cons["side"] == pairs[0]], cons[cons["side"] == pairs[1]]
        if c1.empty or c2.empty:
            continue
        p_first = probability.no_vig(float(c1["cost"].iloc[0]), float(c2["cost"].iloc[0]))
        if not math.isfinite(p_first):
            continue
        take = live[(live["book_id"] != bp.CONSENSUS) & live["side"].notna()]
        if books:
            take = take[take["book_id"].isin([int(b) for b in books])]
        year, week = _stamp(pr["kickoff"])
        for r in take.itertuples():
            first = r.side == pairs[0]
            cons_row = c1 if first else c2
            moneyline = market == "moneyline"
            cons_line = 0.0 if moneyline else float(cons_row["line"].iloc[0])
            line = 0.0 if moneyline else float(r.line)
            if not moneyline and not abs(line - cons_line) <= 1e-9:
                continue                                  # another line: the consensus says nothing there
            p_fair = p_first if first else 1.0 - p_first
            p_raw = atlas_prob(pr, market, r.side, line)
            p_atlas = p_fair + k * (p_raw - p_fair) if math.isfinite(p_raw) else float("nan")
            rows.append({
                "game_id": game_id, "event_id": int(r.event_id), "sport": SPORT, "season": year, "week": week,
                "kickoff": pr["kickoff"], "market": market, "side": r.side, "book_id": int(r.book_id), "line": line,
                "cost": float(r.cost), "updated": r.updated, "cons_line": cons_line,
                "cons_cost": float(cons_row["cost"].iloc[0]), "open_line": float("nan"), "move": float("nan"),
                "p_fair": p_fair, "p_atlas": p_atlas, "p_raw": p_raw, "ev_price": ev(p_fair, r.cost),
                "ev_atlas": ev(p_atlas, r.cost) if math.isfinite(p_atlas) else float("nan"),
                "atlas_number": float(pr["total_mean"]) if market == "total" else float(pr["p_home"]),
                "forecast_wind": float("nan"), "stadium_type": "indoor", "home_abbr": home, "visitor_abbr": visitor,
            })
    return pd.DataFrame(rows, columns=cols)


def quotes(lines: pd.DataFrame, events: pd.DataFrame, projections: pd.DataFrame, k: float) -> pd.DataFrame:
    """The exchanges' quotes on the NHL, valued as :func:`legs` values a book's, in `trading.py`'s columns.
    Never raises."""
    from atlas.owner import trading

    try:
        return legs(lines, events, projections, k, books=list(trading.VENUES)).reindex(columns=trading.QUOTE_COLUMNS)
    except Exception as error:  # noqa: BLE001 - the type only: a message could quote a price
        from atlas.util import where as place

        LOG.error("nhl exchange quotes not read: %s at %s", type(error).__name__, place(error))
        return pd.DataFrame(columns=trading.QUOTE_COLUMNS)


def best(table: pd.DataFrame) -> pd.DataFrame:
    """One row per game, market and side: the book that pays best by Atlas (by the price edge where Atlas has
    no reading)."""
    if table.empty:
        return table
    t = table.assign(score=table["ev_atlas"].fillna(table["ev_price"]))
    t = t.sort_values("score", ascending=False).drop_duplicates(["game_id", "market", "side"], keep="first")
    books = table.groupby(["game_id", "market", "side"])["book_id"].nunique().rename("books")
    return t.merge(books, on=["game_id", "market", "side"], how="left").reset_index(drop=True)


def picks(priced: pd.DataFrame) -> pd.DataFrame:
    """Positive expected value by Atlas at the best price, best first: per game, one on the result (a moneyline
    and a puck line are both a view of who wins) and one on the total."""
    if priced.empty:
        return priced
    p = priced[priced["ev_atlas"] > MIN_EV].sort_values("ev_atlas", ascending=False)
    p = p.assign(_view=np.where(p["market"] == "total", "total", "result"))
    p = p.drop_duplicates(["game_id", "_view"], keep="first").drop(columns="_view")
    return p.head(MAX_PICKS).reset_index(drop=True)


# ---------------------------------------------------------------------------
# The record
# ---------------------------------------------------------------------------


def pick_id(game_id, market: str, side: str) -> str:
    return str(uuid.uuid5(NAMESPACE, f"{game_id}|{market}|{side}"))


def load(passphrase: str, where: Path | None = None) -> pd.DataFrame:
    rows = sealed.load(where or path(), passphrase)
    return pd.DataFrame(rows, columns=PICK_COLUMNS) if rows else pd.DataFrame(columns=PICK_COLUMNS)


def log(record: pd.DataFrame, chosen: pd.DataFrame, names: dict, now: datetime) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Add the picks not yet logged, at the book, line and price on the board now; a logged pick is never revised.
    Returns the record and the rows added."""
    if chosen.empty:
        return record, chosen.iloc[0:0]
    label = [names.get(str(g), " @ ").split(" @ ", 1) for g in chosen["game_id"]]
    fresh = pd.DataFrame({
        "pick_id": [pick_id(g, m, s) for g, m, s in zip(chosen["game_id"], chosen["market"], chosen["side"], strict=True)],
        "game_id": chosen["game_id"].astype(str), "event_id": chosen["event_id"],
        "kickoff": pd.to_datetime(chosen["kickoff"], utc=True).dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "away_team": [a for a, _ in label], "home_team": [h for _, h in label],
        "home_abbr": chosen["home_abbr"], "visitor_abbr": chosen["visitor_abbr"], "market": chosen["market"],
        "side": chosen["side"], "book_id": chosen["book_id"], "line": chosen["line"],
        "cost": chosen["cost"], "cons_cost": chosen["cons_cost"], "p_fair": chosen["p_fair"].round(4),
        "p_raw": chosen["p_raw"].round(4), "p_atlas": chosen["p_atlas"].round(4),
        "ev_price": chosen["ev_price"].round(4), "ev_atlas": chosen["ev_atlas"].round(4),
        "formed_at": now.replace(microsecond=0).isoformat(),
    })
    new = fresh[~fresh["pick_id"].isin(set(record["pick_id"]))] if len(record) else fresh
    if new.empty:
        return record, new
    parts = [record.reindex(columns=PICK_COLUMNS), new] if len(record) else [new]
    return pd.concat(parts, ignore_index=True).reindex(columns=PICK_COLUMNS), new


def week_file(where: Path, kickoff) -> Path:
    t = pd.Timestamp(kickoff)
    t = t.tz_localize("UTC") if t.tzinfo is None else t
    year, week, _ = t.isocalendar()
    return where / f"nhl-{int(year)}-W{int(week):02d}.enc.json"


def seal(record: pd.DataFrame, passphrase: str, added: pd.DataFrame, where: Path | None = None) -> list[Path]:
    where = where or path()
    files = {week_file(where, k) for k in added["kickoff"]}
    out = []
    for f in sorted(files):
        part = record[[week_file(where, k) == f for k in record["kickoff"]]]
        rows = json.loads(part.reindex(columns=PICK_COLUMNS).to_json(orient="records"))
        out.append(sealed.seal(rows, passphrase, f, names=[r.get(k) for r in rows for k in ("home_team", "away_team")]))
    return out


def outcome(market: str, side: str, line: float, margin: float, total: float) -> str:
    """win, loss, push or open on the final score (a shootout goal included, as the books settle)."""
    if not (math.isfinite(margin) and math.isfinite(total)):
        return "open"
    if market == "total":
        edge = (total - line) * (1.0 if side == "over" else -1.0)
    else:
        own = margin if side == "home" else -margin
        edge = own + (line if market == "spread" else 0.0)
    return "win" if edge > 0 else ("loss" if edge < 0 else "push")


def close_prob(pick, closes: pd.DataFrame) -> float:
    """The consensus close, its margin out, for the side of a pick (or an exchange position: anything with
    ``game_id``, ``market``, ``side``, ``line``, ``home_abbr`` and ``visitor_abbr``) at its line; nan at
    another line."""
    c = closes[(closes["book_id"] == bp.CONSENSUS) & (closes["game_id"].astype(str) == str(pick.game_id))
               & (closes["market"] == pick.market)]
    if c.empty:
        return float("nan")
    code = lambda v: str(v) if isinstance(v, str) and v else None  # noqa: E731
    c = c.assign(side=_sides(c, pick.market, code(pick.home_abbr), code(pick.visitor_abbr)))
    pairs = ("over", "under") if pick.market == "total" else ("home", "away")
    a, b = c[c["side"] == pairs[0]], c[c["side"] == pairs[1]]
    if a.empty or b.empty:
        return float("nan")
    mine = a if pick.side == pairs[0] else b
    if pick.market != "moneyline" and abs(float(mine["line"].iloc[0]) - float(pick.line)) > 1e-9:
        return float("nan")
    p = probability.no_vig(float(a["cost"].iloc[0]), float(b["cost"].iloc[0]))
    return p if pick.side == pairs[0] else 1.0 - p


def grade(record: pd.DataFrame, finals: pd.DataFrame, closes: pd.DataFrame) -> pd.DataFrame:
    if record.empty:
        return record.assign(outcome=pd.Series(dtype=str), profit=pd.Series(dtype=float),
                             clv_prob=pd.Series(dtype=float))
    r = record.assign(game_id=record["game_id"].astype(str)).merge(
        finals.assign(game_id=finals["game_id"].astype(str)), on="game_id", how="left")
    r["outcome"] = [outcome(m, s, float(ln), float(mg), float(tt)) for m, s, ln, mg, tt in
                    zip(r["market"], r["side"], r["line"], r["final_margin"], r["final_total"], strict=True)]
    cost = pd.to_numeric(r["cost"], errors="coerce")
    r["profit"] = np.select([r["outcome"] == "win", r["outcome"] == "loss"], [cost.map(board.payout), -1.0], 0.0)
    r.loc[r["outcome"] == "open", "profit"] = np.nan
    r["clv_prob"] = [close_prob(x, closes) - float(x.p_fair) if not closes.empty else np.nan
                     for x in r.itertuples()]
    return r


# ---------------------------------------------------------------------------
# The owner page's view
# ---------------------------------------------------------------------------

HEAD = ["Game", "Side", "Consensus", "Edge"]


def label(market: str, side: str, line, game: str) -> str:
    """"Flyers to win", "Flyers -1.5", "Over 6.5"."""
    away, home = game.split(" @ ", 1) if " @ " in game else ("Away", "Home")
    team = home if side == "home" else away
    if market == "moneyline":
        return f"{team} to win"
    if market == "spread":
        return f"{team} {float(line):+g}"
    return f"{str(side).capitalize()} {float(line):g}"


def _row(x, names: dict) -> list:
    game = names.get(str(x.game_id), str(x.game_id))
    return [[game, board._eastern(x.kickoff)],
            [f"{label(x.market, x.side, x.line, game)} ({x.cost:+.0f})",
             bp.book_name(x.book_id) + (f" · {int(x.books)} book{'s' if int(x.books) != 1 else ''}"
                                        if board._finite(getattr(x, "books", None)) else "")],
            [f"{x.cons_cost:+.0f}", f"fair {paper._pct(x.p_fair)}"],
            [f"EV {board._ev(x.ev_atlas)}", f"Atlas {paper._pct(x.p_atlas)} (grid {paper._pct(x.p_raw)})"]]


def sections(priced: pd.DataFrame, chosen: pd.DataFrame, graded: pd.DataFrame, names: dict, now: datetime,
             k: float, unpriced: int = 0) -> list[dict]:
    """The NHL on the Board tab: the picks, the board by market, and the record. Nothing on a day with no NHL
    game priced and no record; a word when ``unpriced`` games have lines and no projection to price them."""
    if priced.empty:
        out = [] if not unpriced else [{"title": "NHL board", "tab": "Board", "tables": [], "notes": [
            f"{unpriced} NHL game{'s have' if unpriced != 1 else ' has'} lines and no Atlas projection to price "
            "them: the heavy refresh has not published one (tracking/nhl_projections.csv)."]}]
        return out + _record(graded, names)
    notes = [
        "Every NHL game in the next day and a half across every book BettingPros quotes, the consensus with its "
        "margin taken out as fair, and Atlas's probability from the score grid pulled toward fair by the share of "
        f"its disagreement that has turned out real on the NHL's record against the closing line ({k:.2f}). A book "
        "at a line other than the consensus's is left out.",
        f"Picks: positive expected value by Atlas at the best price, per game one on the result (moneyline or puck "
        f"line) and one on the total, at most {MAX_PICKS}, logged the first time they qualify and graded on the final "
        "score, a shootout goal included.",
    ]
    out = [{"title": f"NHL picks now ({len(chosen)})", "tab": "Board", "notes": notes,
            "tables": [{"title": "", "head": HEAD, "stack": True,
                        "rows": [_row(x, names) for x in chosen.itertuples()] or
                        [["Nothing clears zero at any book right now.", "", "", ""]]}]}]
    upcoming = priced[pd.to_datetime(priced["kickoff"], utc=True, errors="coerce") > pd.Timestamp(now)] \
        if len(priced) else priced
    tables = []
    for market, title in (("moneyline", "Moneylines"), ("spread", "Puck lines"), ("total", "Totals")):
        m = upcoming[upcoming["market"] == market] if len(upcoming) else upcoming
        if m.empty:
            continue
        m = m.assign(score=m["ev_atlas"].fillna(m["ev_price"])).sort_values("score", ascending=False)
        m = m.drop_duplicates("game_id", keep="first")
        tables.append({"title": f"{title}: each game's better side", "fold": market != "moneyline", "head": HEAD,
                       "stack": True, "rows": [_row(x, names) for x in m.itertuples()]})
    if tables:
        out.append({"title": "NHL board", "tab": "Board", "tables": tables, "notes": [
            "Each game's better side in each market at the book that pays best, whether or not it clears zero."]})
    return out + _record(graded, names)


def _record(graded: pd.DataFrame, names: dict) -> list[dict]:
    out = []
    if len(graded):
        done = graded[graded["outcome"].isin(["win", "loss", "push"])]
        clv = pd.to_numeric(graded["clv_prob"], errors="coerce")
        units = float(done["profit"].sum()) if len(done) else 0.0
        rows = [["Picks logged", str(len(graded))], ["Graded", str(len(done))],
                ["Won-lost-push", f"{int((done['outcome'] == 'win').sum())}-{int((done['outcome'] == 'loss').sum())}-"
                                  f"{int((done['outcome'] == 'push').sum())}"],
                ["Units", f"{units:+.2f}" if len(done) else "–"],
                ["Per pick", f"{units / len(done):+.1%}" if len(done) else "–"],
                ["Beat the consensus close", f"{int((clv > 0).sum())} of {int(clv.notna().sum())}" if clv.notna().any() else "–"],
                ["Mean CLV, win probability", f"{clv.mean():+.1%}" if clv.notna().any() else "–"]]
        tables = [{"title": "", "head": ["", ""], "rows": rows}]
        latest = done.sort_values("kickoff", ascending=False).head(12)
        if len(latest):
            tables.append({"title": "Latest graded picks", "fold": True, "stack": True,
                           "head": ["Game", "Pick", "Result"],
                           "rows": [[names.get(str(x.game_id), str(x.game_id)),
                                     [f"{label(x.market, x.side, x.line, names.get(str(x.game_id), ''))} "
                                      f"({float(x.cost):+.0f})", bp.book_name(x.book_id)],
                                     [f"{x.outcome} {x.profit:+.2f}",
                                      f"close {x.clv_prob:+.1%}" if pd.notna(x.clv_prob) else ""]]
                                    for x in latest.itertuples()]})
        out.append({"title": "NHL board record", "tab": "Board", "tables": tables,
                    "notes": [f"Nothing is read from fewer than {MIN_GRADED} graded."]})
    return out


def build(lines: pd.DataFrame, events: pd.DataFrame, projections: pd.DataFrame, calibration: pd.DataFrame | None,
          finals: pd.DataFrame, closes: pd.DataFrame, names: dict, passphrase: str, now: datetime,
          where: Path | None = None) -> tuple[list[dict], pd.DataFrame, float]:
    """The NHL priced, its picks logged once and graded, and its sections. Returns (sections, the legs for the
    parlays, the share of disagreement used). Never raises."""
    empty = pd.DataFrame(columns=LEG_COLUMNS)
    try:
        k = share(calibration)
        table = legs(lines, events, projections, k)
        priced = best(table)
        chosen = picks(priced)
        record = load(passphrase, where)
        record, added = log(record, chosen, names, now)
        if not added.empty:
            seal(record, passphrase, added, where)
            LOG.info("nhl board: %d picks logged", len(added))
        graded = grade(record, finals, closes)
        listed = set(lines.loc[lines["sport"].astype(str) == SPORT, "game_id"].astype(str)) \
            if len(lines) and "sport" in lines else set()
        unpriced = len(listed - set(table["game_id"].astype(str)))
        LOG.info("nhl board: %d legs, %d sides priced, %d picks now (share %.2f); %d games with lines unpriced",
                 len(table), len(priced), len(chosen), k, unpriced)
        return sections(priced, chosen, graded, names, now, k, unpriced if table.empty else 0), table, k
    except Exception as error:  # noqa: BLE001 - the type only: a message could quote a line
        from atlas.util import where as place

        LOG.error("nhl board not built: %s at %s", type(error).__name__, place(error))
        return [{"title": "NHL board", "tab": "Board",
                 "notes": [f"This run could not build the NHL board ({type(error).__name__})."], "tables": []}], \
            empty, DEFAULT_SHARE
