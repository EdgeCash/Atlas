"""The owner's board: every game priced across every book, ranked by expected value.

    python -m atlas.owner.board             # this weekend's board, to the terminal (needs ATLAS_OWNER_KEY, BP_API_KEY)

For the owner's eyes only, and built on two things the research supports.
The market's price is not one number: with a dozen books the best line and
price on a side is worth one to two percent on its own, more than the model
adds. And Atlas's total, read through its own calibration against the line
(``total_over_shrink``, ``total_over_sd``), is a market-anchored probability
that says how much of a disagreement is real - about a third in 2026, a
tenth in some seasons - rather than a number to bet by itself.

So, per game and market:

* the **consensus** line and both prices (BettingPros' consensus book), and
  the opening line;
* every takeable book's current main line and price, each valued two ways:
  **price edge**, the expected value of that book's price under the
  consensus market read at that book's line (`atlas/live/probability.py`),
  and for totals **Atlas EV**, the expected value under Atlas's calibrated
  probability at that book's line;
* the **best side** by Atlas EV (totals) or price edge (spreads, where the
  model's market weight is 1.00 and it adds nothing), with the book;
* flags: steam (the consensus moved from the opener), off-market (a book a
  point or more from consensus), moved against Atlas, and the kickoff wind
  forecast.

**Picks** are the sides with positive expected value at the best available
price, ranked, capped, and logged once - the first board at which they
qualify - into a sealed record (``tracking/owner_board/``), then graded on
the score and on closing-line value against the consensus close. Everything
here is shown only inside the owner page's ciphertext; the multi-book lines
themselves are kept sealed (`atlas/owner/market.py`) and never published.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from scipy import stats

from atlas.live import probability
from atlas.owner import market as market_store
from atlas.owner import paper, sealed
from atlas.sources import bettingpros as bp
from atlas.util import get_logger

LOG = get_logger(__name__)

EASTERN = ZoneInfo("America/New_York")
PICK_NAMESPACE = uuid.UUID("7c2b1e4d-2f7a-4d0c-9c31-6f0e2a8b5d41")
PICK_COLUMNS = ["pick_id", "game_id", "event_id", "sport", "season", "week", "kickoff", "away_team", "home_team",
                "market", "side", "book_id", "line", "cost", "cons_line", "cons_cost", "open_line", "p_fair", "p_atlas",
                "ev_price", "ev_atlas", "atlas_number", "formed_at"]
#: Games this far ahead are on the board.
HORIZON = timedelta(days=8)
#: How close a BettingPros event's scheduled time must be to ESPN's kickoff to be the same game.
MATCH_WINDOW = pd.Timedelta(minutes=45)
#: A pick: positive expected value at the best price, by the measure the market allows.
MIN_EV = 0.0
MAX_PICKS = 8
#: Steam: the consensus moved this far from the opener. Off-market: a book this far from consensus.
STEAM = {"total": 1.5, "spread": 1.0}
OFF_MARKET = {"total": 1.0, "spread": 0.5}
MOVED_AGAINST = 2.0
MIN_GRADED = 50


# ---------------------------------------------------------------------------
# Matching BettingPros events to ESPN games
# ---------------------------------------------------------------------------


def norm(value) -> str:
    return re.sub(r"[^a-z]", "", str(value or "").lower().replace("st.", "state").replace("&", "and"))


def _mascot_fits(espn_name, mascot) -> bool:
    m = norm(mascot)
    return bool(m) and norm(espn_name).endswith(m)


def _school_fits(espn_name, school) -> bool:
    s = norm(school)
    return bool(s) and norm(espn_name).startswith(s[: max(4, len(s) - 1)])


def match_events(games: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    """``game_id`` to ``event_id`` for the games the API lists: the same sport, a kickoff within
    :data:`MATCH_WINDOW`, and both sides' mascots (else both schools) agreeing."""
    columns = ["game_id", "event_id"]
    if games.empty or events.empty:
        return pd.DataFrame(columns=columns)
    g = games.assign(kick=pd.to_datetime(games["kickoff"], utc=True, errors="coerce")).dropna(subset=["kick"])
    e = events.assign(sched=pd.to_datetime(events["scheduled"], utc=True, errors="coerce")).dropna(subset=["sched"])
    rows = []
    for ev in e.itertuples():
        near = g[(g["sport"] == ev.sport) & ((g["kick"] - ev.sched).abs() <= MATCH_WINDOW)]
        if near.empty:
            continue
        both = near[[_mascot_fits(h, ev.home_mascot) and _mascot_fits(a, ev.visitor_mascot)
                     for h, a in zip(near["home_team"], near["away_team"], strict=True)]]
        if len(both) > 1:
            both = both[[_school_fits(h, ev.home_school) and _school_fits(a, ev.visitor_school)
                         for h, a in zip(both["home_team"], both["away_team"], strict=True)]]
        if both.empty:
            both = near[[_school_fits(h, ev.home_school) and _school_fits(a, ev.visitor_school)
                         for h, a in zip(near["home_team"], near["away_team"], strict=True)]]
        if len(both) == 1:
            rows.append({"game_id": both["game_id"].iloc[0], "event_id": int(ev.event_id)})
    out = pd.DataFrame(rows, columns=columns)
    return out.drop_duplicates("game_id").drop_duplicates("event_id").reset_index(drop=True)


# ---------------------------------------------------------------------------
# Capturing the market
# ---------------------------------------------------------------------------


def _sport_of(projections: pd.DataFrame) -> dict[str, str]:
    """Each projected game's sport. Rows written before the column existed are college (the site reads them
    the same way, `atlas/site/record.before_kickoff`)."""
    if projections.empty:
        return {}
    p = projections.assign(sport=projections["sport"].fillna("ncaaf").astype(str))
    if "refreshed_at" in p:
        p = p.sort_values("refreshed_at", kind="stable")
    return dict(zip(p["game_id"].astype(str), p["sport"], strict=True))


def upcoming(games: pd.DataFrame, projections: pd.DataFrame, now: datetime) -> pd.DataFrame:
    """ESPN's games kicking off inside the horizon, with their sport and week."""
    if games.empty:
        return games.iloc[0:0]
    sports = _sport_of(projections)
    g = games.assign(sport=games["game_id"].astype(str).map(sports))
    kick = pd.to_datetime(g["kickoff"], utc=True, errors="coerce")
    g = g[(kick > pd.Timestamp(now)) & (kick <= pd.Timestamp(now) + HORIZON) & g["sport"].notna()]
    return g.reset_index(drop=True)


def capture(client: bp.Client, games: pd.DataFrame, now: datetime) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Every book's current lines on the upcoming games: (lines with ``game_id``, matched events)."""
    lines, matched = [], []
    stamp = now.replace(microsecond=0).isoformat()
    for sport, part in games.groupby("sport"):
        weeks = sorted({(int(s), int(w)) for s, w in part[["season", "week"]].dropna().itertuples(index=False)})
        ev = pd.concat([bp.events(client, sport, s, w) for s, w in weeks], ignore_index=True) if weeks \
            else pd.DataFrame(columns=bp.EVENT_COLUMNS)
        pairs = match_events(part, ev.assign(sport=sport))
        if pairs.empty:
            LOG.warning("board: no %s game matched a BettingPros event", sport)
            continue
        found = bp.offers(client, sport, pairs["event_id"].tolist(), captured_at=stamp)
        found = found.merge(pairs, on="event_id", how="inner")
        lines.append(found)
        matched.append(ev.merge(pairs, on="event_id", how="inner"))
        LOG.info("board: %s: %d of %d games matched, %d lines", sport, len(pairs), len(part), len(found))
    empty_lines = pd.DataFrame(columns=[*bp.LINE_COLUMNS, "game_id"])
    empty_events = pd.DataFrame(columns=[*bp.EVENT_COLUMNS, "game_id"])
    return (pd.concat(lines, ignore_index=True) if lines else empty_lines,
            pd.concat(matched, ignore_index=True) if matched else empty_events)


# ---------------------------------------------------------------------------
# Pricing
# ---------------------------------------------------------------------------


def payout(cost: float) -> float:
    return paper.payout(float(cost))


def ev(p: float, cost: float) -> float:
    """Expected profit on one unit at American ``cost`` when the side wins with probability ``p``."""
    if p is None or not math.isfinite(p):
        return float("nan")
    return p * payout(cost) - (1.0 - p)


def atlas_over(atlas_total, shrink, over_sd, line) -> float:
    """Atlas's calibrated P(over ``line``): the share of its disagreement that turns out real, as a probability."""
    try:
        a, s, sd, ln = float(atlas_total), float(shrink), float(over_sd), float(line)
    except (TypeError, ValueError):
        return float("nan")
    if not all(math.isfinite(v) for v in (a, s, sd, ln)) or sd <= 0:
        return float("nan")
    return float(stats.norm.cdf(s * (a - ln) / sd))


def _opener(row) -> float:
    """The selection's opening line, unless a prediction market set it: those open early and oddly, and a
    "move" measured from them is not steam."""
    try:
        book = int(float(row["open_book"]))
    except (TypeError, ValueError):
        return float("nan")
    if book in bp.PREDICTION_MARKETS:
        return float("nan")
    return float(pd.to_numeric(row["open_line"], errors="coerce"))


def side_of(row, market: str, home_abbr: str | None, visitor_abbr: str | None, cons_home_line: float | None) -> str | None:
    """Which side a line row is: ``over``/``under`` for a total; ``home``/``away`` for a spread, by the
    participant's abbreviation where it matches the event's, else by the sign of its handicap against the
    consensus home handicap (books spell the same team several ways). Unknown near a pick'em."""
    if market == "total":
        return row.selection if row.selection in ("over", "under") else None
    if home_abbr and row.participant == home_abbr:
        return "home"
    if visitor_abbr and row.participant == visitor_abbr:
        return "away"
    try:
        line, cons = float(row.line), float(cons_home_line)
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(line) and math.isfinite(cons)) or abs(cons) < 1.0 or line == 0:
        return None
    return "home" if (line > 0) == (cons > 0) else "away"


def _consensus(part: pd.DataFrame, market: str, home_abbr: str | None, visitor_abbr: str | None) -> dict | None:
    """The consensus book's line and both prices for one game and market, oriented: for a total the
    over's line; for a spread the home side's handicap."""
    c = part[part["book_id"] == bp.CONSENSUS]
    if c.empty:
        return None
    if market == "total":
        over, under = c[c["selection"] == "over"], c[c["selection"] == "under"]
        if over.empty or under.empty:
            return None
        return {"line": float(over["line"].iloc[0]), "first_cost": float(over["cost"].iloc[0]),
                "second_cost": float(under["cost"].iloc[0]), "open_line": _opener(over.iloc[0])}
    home = c[c["participant"] == home_abbr] if home_abbr else c.iloc[0:0]
    away = c[c["participant"] == visitor_abbr] if visitor_abbr else c.iloc[0:0]
    if home.empty and not away.empty:
        # The home side under another spelling: the row whose handicap is the away one's negative.
        home = c[(c["participant"] != visitor_abbr) & ((c["line"] + float(away["line"].iloc[0])).abs() <= 1.0)]
    if away.empty and not home.empty:
        away = c[(c["participant"] != home_abbr) & ((c["line"] + float(home["line"].iloc[0])).abs() <= 1.0)]
    if home.empty or away.empty:
        return None
    return {"line": float(home["line"].iloc[0]), "first_cost": float(home["cost"].iloc[0]),
            "second_cost": float(away["cost"].iloc[0]), "open_line": _opener(home.iloc[0])}


def edge_curve(calibration: pd.DataFrame | None, sport: str):
    """Atlas's side of the total against the close, as a function of the size of its disagreement: the
    current model's walk-forward hit rate over games at or beyond each gap (`tracking/calibration.csv`).
    This is what the model's disagreement has actually been worth, not what its in-season calibration
    claims. None when the table is missing or thin."""
    if calibration is None or calibration.empty:
        return None
    c = calibration
    if "sport" in c:
        c = c[c["sport"].fillna("ncaaf") == sport]
    c = c[(c["market"] == "total")]
    if "season_type" in c:
        c = c[c["season_type"] == "regular"]
    c = c.dropna(subset=["abs_edge", "won"])
    c = c[c["won"] != 0.5]
    if len(c) < 200:
        return None
    edges = c["abs_edge"].to_numpy(dtype=float)
    won = c["won"].to_numpy(dtype=float) == 1.0
    order = np.argsort(-edges)
    edges, won = edges[order], won[order]
    cum = np.cumsum(won) / np.arange(1, len(won) + 1)          # hit rate over games with a gap this large or larger
    steps = np.arange(0.0, 12.5, 0.5)
    rate = np.array([cum[edges >= g][-1] if (edges >= g).sum() >= 60 else np.nan for g in steps])
    # Beyond the largest well-populated gap the last reading holds; below the smallest, the pooled rate.
    rate = pd.Series(rate).ffill().bfill().to_numpy()

    def p(gap: float) -> float:
        i = min(int(abs(float(gap)) / 0.5), len(steps) - 1)
        return float(rate[i])
    return p


def price(lines: pd.DataFrame, events: pd.DataFrame, projections: pd.DataFrame, shapes: dict,
          now: datetime, calibration: pd.DataFrame | None = None) -> pd.DataFrame:
    """One row per game, market and side: the consensus, the best book by the measure that applies, both
    expected values, Atlas's number and probability, and the flags."""
    columns = ["game_id", "event_id", "sport", "season", "week", "kickoff", "market", "side", "cons_line",
               "cons_cost", "open_line", "move", "best_book", "best_line", "best_cost", "p_fair", "p_atlas",
               "ev_price", "ev_atlas", "atlas_number", "books", "steam", "off_market", "moved_against",
               "forecast_wind", "stadium_type"]
    if lines.empty:
        return pd.DataFrame(columns=columns)
    p = projections.sort_values("refreshed_at").drop_duplicates("game_id", keep="last") if not projections.empty \
        else projections
    proj = p.assign(game_id=p["game_id"].astype(str)).set_index("game_id") if not p.empty else None
    ev_by_game = events.assign(game_id=events["game_id"].astype(str)).drop_duplicates("game_id").set_index("game_id")
    curves = {sport: edge_curve(calibration, sport) for sport in set(lines["sport"].astype(str))}
    rows = []
    for (game_id, market), part in lines.assign(game_id=lines["game_id"].astype(str)).groupby(["game_id", "market"]):
        info = ev_by_game.loc[game_id] if game_id in ev_by_game.index else None
        home_abbr = str(info["home_abbr"]) if info is not None else None
        visitor_abbr = str(info["visitor_abbr"]) if info is not None else None
        cons = _consensus(part, market, home_abbr, visitor_abbr)
        if cons is None:
            continue
        sport = str(part["sport"].iloc[0])
        shape = shapes.get((sport, "total" if market == "total" else "margin")) \
            or probability.default_shape(sport, "total" if market == "total" else "margin")
        cons_first, _ = probability.quoted_first(cons["first_cost"], cons["second_cost"])
        # A spread is quoted as the home handicap; the market's first side is the home margin, which
        # is above -handicap when the home side covers.
        cons_market_line = cons["line"] if market == "total" else -cons["line"]
        pr = proj.loc[game_id] if proj is not None and game_id in proj.index else None
        atlas_number = float(pr["total_mean"]) if pr is not None and market == "total" else (
            float(pr["margin_mean"]) if pr is not None else float("nan"))
        take = part[bp.takeable(part)]
        sides = [side_of(r, market, home_abbr, visitor_abbr, cons["line"]) for r in take.itertuples()]
        curve = curves.get(sport)
        for side in (("over", "under") if market == "total" else ("home", "away")):
            first = side in ("over", "home")
            cands = take[[sd == side for sd in sides]]
            best, best_score = None, -np.inf
            for r in cands.itertuples():
                line_market = float(r.line) if market == "total" else (-float(r.line) if first else float(r.line))
                p_first = probability.at_line(shape, cons_market_line, cons_first, line_market)
                p_fair = probability.side_prob(p_first, "over" if first else "under")
                e_price = ev(p_fair, r.cost)
                p_a = float("nan")
                if market == "total" and pr is not None and math.isfinite(atlas_number):
                    gap = atlas_number - float(r.line)
                    on_side = (gap > 0) == first          # is this side Atlas's side of this book's line?
                    if curve is not None:
                        hit = curve(gap)
                        p_a = hit if on_side else 1.0 - hit
                    else:
                        p_over = atlas_over(atlas_number, pr["total_over_shrink"], pr["total_over_sd"], r.line)
                        p_a = p_over if first else 1.0 - p_over
                e_atlas = ev(p_a, r.cost) if math.isfinite(p_a) else float("nan")
                score = e_atlas if (market == "total" and math.isfinite(e_atlas)) else e_price
                if math.isfinite(score) and score > best_score:
                    best, best_score = (r, p_fair, p_a, e_price, e_atlas), score
            if best is None:
                continue
            r, p_fair, p_a, e_price, e_atlas = best
            cons_side_line = cons["line"] if (market == "total" or first) else -cons["line"]
            best_side_line = float(r.line)
            better = (best_side_line - cons_side_line) * (-1.0 if side in ("over", "home") else 1.0) \
                if market == "total" else (best_side_line - cons_side_line)
            move = cons["line"] - cons["open_line"] if math.isfinite(cons["open_line"]) else float("nan")
            open_side_line = cons["open_line"] if (market == "total" or first) else -cons["open_line"]
            against = float("nan")
            if market == "total" and math.isfinite(move):
                against = -move if side == "over" else move
            rows.append({
                "game_id": game_id, "event_id": int(part["event_id"].iloc[0]), "sport": sport,
                "season": info["season"] if info is not None else None, "week": info["week"] if info is not None else None,
                "kickoff": info["scheduled"] if info is not None else None, "market": market, "side": side,
                "cons_line": cons_side_line, "cons_cost": cons["first_cost"] if first else cons["second_cost"],
                "open_line": open_side_line, "move": move, "best_book": int(r.book_id), "best_line": best_side_line,
                "best_cost": float(r.cost), "p_fair": p_fair, "p_atlas": p_a, "ev_price": e_price, "ev_atlas": e_atlas,
                "atlas_number": atlas_number, "books": int(cands["book_id"].nunique()),
                "steam": bool(math.isfinite(move) and abs(move) >= STEAM[market]),
                "off_market": bool(better >= OFF_MARKET[market]),
                "moved_against": against,
                "forecast_wind": float(info["forecast_wind"]) if info is not None and pd.notna(info["forecast_wind"]) else float("nan"),
                "stadium_type": info["stadium_type"] if info is not None else None,
            })
    return pd.DataFrame(rows, columns=columns)


def picks(board: pd.DataFrame) -> pd.DataFrame:
    """The sides worth taking now: positive expected value at the best price by the measure that applies
    (Atlas EV on totals, price edge on spreads), best first, at most :data:`MAX_PICKS`."""
    if board.empty:
        return board
    b = board.copy()
    b["score"] = np.where(b["market"] == "total", b["ev_atlas"].fillna(-np.inf), b["ev_price"].fillna(-np.inf))
    b = b[b["score"] > MIN_EV].sort_values("score", ascending=False)
    # One side per game and market: the better side of a market cannot both be value.
    b = b.drop_duplicates(["game_id", "market"], keep="first")
    return b.head(MAX_PICKS).drop(columns="score").reset_index(drop=True)


# ---------------------------------------------------------------------------
# The picks record
# ---------------------------------------------------------------------------


def picks_path() -> Path:
    from atlas.live.store import tracking_dir

    return tracking_dir() / "owner_board"


def pick_id(game_id, market: str, side: str) -> str:
    return str(uuid.uuid5(PICK_NAMESPACE, f"{game_id}|{market}|{side}"))


def load_picks(passphrase: str, where: Path | None = None) -> pd.DataFrame:
    rows = sealed.load(where or picks_path(), passphrase)
    return pd.DataFrame(rows, columns=PICK_COLUMNS) if rows else pd.DataFrame(columns=PICK_COLUMNS)


def log_picks(record: pd.DataFrame, chosen: pd.DataFrame, games: pd.DataFrame, now: datetime) -> tuple[pd.DataFrame, set]:
    """Add the picks not yet logged, at the book, line and price on the board now; a logged pick is never
    revised. Returns the record and the (season, week) files touched."""
    if chosen.empty:
        return record, set()
    names = games.assign(game_id=games["game_id"].astype(str)).drop_duplicates("game_id").set_index("game_id")
    fresh = pd.DataFrame({
        "pick_id": [pick_id(g, m, s) for g, m, s in zip(chosen["game_id"], chosen["market"], chosen["side"], strict=True)],
        "game_id": chosen["game_id"].astype(str), "event_id": chosen["event_id"], "sport": chosen["sport"],
        "season": chosen["season"], "week": chosen["week"],
        "kickoff": pd.to_datetime(chosen["kickoff"], utc=True).dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "away_team": chosen["game_id"].astype(str).map(names["away_team"]) if "away_team" in names else None,
        "home_team": chosen["game_id"].astype(str).map(names["home_team"]) if "home_team" in names else None,
        "market": chosen["market"], "side": chosen["side"], "book_id": chosen["best_book"], "line": chosen["best_line"],
        "cost": chosen["best_cost"], "cons_line": chosen["cons_line"], "cons_cost": chosen["cons_cost"],
        "open_line": chosen["open_line"], "p_fair": chosen["p_fair"].round(4), "p_atlas": chosen["p_atlas"].round(4),
        "ev_price": chosen["ev_price"].round(4), "ev_atlas": chosen["ev_atlas"].round(4),
        "atlas_number": chosen["atlas_number"].round(2), "formed_at": now.replace(microsecond=0).isoformat(),
    })
    new = fresh[~fresh["pick_id"].isin(set(record["pick_id"]))] if len(record) else fresh
    if new.empty:
        return record, set()
    weeks = {(int(a), int(b)) for a, b in new[["season", "week"]].dropna().drop_duplicates().itertuples(index=False)}
    parts = [record.reindex(columns=PICK_COLUMNS), new] if len(record) else [new]
    return pd.concat(parts, ignore_index=True).reindex(columns=PICK_COLUMNS), weeks


def seal_picks(record: pd.DataFrame, passphrase: str, weeks: set, where: Path | None = None) -> list[Path]:
    where = where or picks_path()
    out = []
    for season, week in sorted(weeks):
        part = record[(pd.to_numeric(record["season"]) == season) & (pd.to_numeric(record["week"]) == week)]
        rows = json.loads(part.reindex(columns=PICK_COLUMNS).to_json(orient="records"))
        names = [r.get(k) for r in rows for k in ("home_team", "away_team")]
        out.append(sealed.seal(rows, passphrase, sealed.week_file(where, season, week), names=names))
    return out


def grade_picks(record: pd.DataFrame, finals: pd.DataFrame, closes: pd.DataFrame, events: pd.DataFrame,
                shapes: dict) -> pd.DataFrame:
    """Each pick with its outcome and units at the price taken, and its closing-line value against the
    consensus close (the consensus book's last line before kickoff, from the sealed market record)."""
    if record.empty:
        return record.assign(outcome=pd.Series(dtype=str), profit=pd.Series(dtype=float),
                             close_line=pd.Series(dtype=float), clv=pd.Series(dtype=float),
                             clv_prob=pd.Series(dtype=float), clv_result=pd.Series(dtype=str))
    r = record.assign(game_id=record["game_id"].astype(str)).merge(finals, on="game_id", how="left")
    home = events.assign(game_id=events["game_id"].astype(str)).drop_duplicates("game_id").set_index("game_id")["home_abbr"] \
        if not events.empty else pd.Series(dtype=str)
    line = pd.to_numeric(r["line"], errors="coerce")
    total_edge = (r["final_total"] - line) * np.where(r["side"] == "over", 1.0, -1.0)
    # A spread pick's line is the side's own handicap: it covers when its margin plus the handicap is positive.
    own_margin = np.where(r["side"] == "home", r["final_margin"], -r["final_margin"])
    spread_edge = own_margin + line
    edge = np.where(r["market"] == "total", total_edge, spread_edge).astype(float)
    r["outcome"] = np.select([np.isnan(edge), edge > 0, edge < 0], ["open", "win", "loss"], "push")
    cost = pd.to_numeric(r["cost"], errors="coerce").fillna(paper.DEFAULT_PRICE)
    r["profit"] = np.select([r["outcome"] == "win", r["outcome"] == "loss"], [cost.map(payout), -1.0], 0.0)
    r["close_line"], r["clv"], r["clv_prob"], r["clv_result"] = np.nan, np.nan, np.nan, None
    if closes.empty:
        return r
    c = closes[closes["book_id"] == bp.CONSENSUS].assign(game_id=closes["game_id"].astype(str))
    for i, pk in r.iterrows():
        part = c[(c["game_id"] == pk["game_id"]) & (c["market"] == pk["market"])]
        if part.empty:
            continue
        if pk["market"] == "total":
            first, second = part[part["selection"] == "over"], part[part["selection"] == "under"]
        else:
            h = home.get(pk["game_id"])
            first = part[part["participant"] == h]
            second = part[(part["participant"] != h) & part["participant"].notna()]
            if not first.empty:
                second = second[(second["line"] + float(first["line"].iloc[0])).abs() <= 1.0]
        if first.empty or second.empty:
            continue
        is_first = pk["side"] in ("over", "home")
        close_side_line = float(first["line"].iloc[0]) if (pk["market"] == "total" or is_first) else float(second["line"].iloc[0])
        r.at[i, "close_line"] = close_side_line
        # Points the close sat past the line taken, on the pick's side.
        if pk["market"] == "total":
            clv = (close_side_line - float(pk["line"])) * (1.0 if is_first else -1.0)
        else:
            clv = close_side_line - float(pk["line"])          # more handicap for the same side is value
        r.at[i, "clv"] = clv
        shape = shapes.get((pk["sport"], "total" if pk["market"] == "total" else "margin")) \
            or probability.default_shape(pk["sport"], "total" if pk["market"] == "total" else "margin")
        close_first, _ = probability.quoted_first(float(first["cost"].iloc[0]), float(second["cost"].iloc[0]))
        cons_market_line = float(first["line"].iloc[0]) if pk["market"] == "total" else -float(first["line"].iloc[0])
        taken_market_line = float(pk["line"]) if pk["market"] == "total" else (-float(pk["line"]) if is_first else float(pk["line"]))
        p_close = probability.side_prob(probability.at_line(shape, cons_market_line, close_first, taken_market_line),
                                        "over" if is_first else "under")
        r.at[i, "clv_prob"] = p_close - float(pk["p_fair"]) if pd.notna(pk["p_fair"]) else np.nan
        r.at[i, "clv_result"] = "beat" if clv > 0 else ("lost" if clv < 0 else "push")
    return r


# ---------------------------------------------------------------------------
# The owner page's view
# ---------------------------------------------------------------------------


def _eastern(ts) -> str:
    t = pd.Timestamp(ts)
    t = t.tz_localize("UTC") if t.tzinfo is None else t
    return t.tz_convert(EASTERN).strftime("%a %-I:%M %p")


def _game(row, names: dict) -> str:
    return names.get(str(row.game_id), str(row.game_id))


def _pct(x) -> str:
    return paper._pct(x)


def _ev(x) -> str:
    return "–" if x is None or not math.isfinite(x) else f"{x:+.1%}"


def _line(x, market: str) -> str:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return "–"
    return f"{v:g}" if market == "total" else f"{v:+g}"


def _flags(row) -> str:
    out = []
    if row.steam:
        out.append(f"steam {row.move:+g}")
    if row.off_market:
        out.append("off-market")
    try:
        if math.isfinite(row.moved_against) and row.moved_against >= MOVED_AGAINST:
            out.append(f"moved {row.moved_against:g} against Atlas")
    except (TypeError, ValueError):
        pass
    try:
        if math.isfinite(row.forecast_wind) and row.forecast_wind >= 15 and str(row.stadium_type) not in ("dome", "indoor"):
            out.append(f"wind {row.forecast_wind:.0f} mph")
    except (TypeError, ValueError):
        pass
    return ", ".join(out)


def sections(board: pd.DataFrame, chosen: pd.DataFrame, graded: pd.DataFrame, names: dict, now: datetime,
             calls: int) -> list[dict]:
    """The board as the owner page shows it: picks, the totals board, the spreads board, the record."""
    upcoming = board[pd.to_datetime(board["kickoff"], utc=True, errors="coerce") > pd.Timestamp(now)] if not board.empty else board
    pick_rows = [[f"{_game(x, names)} · {_eastern(x.kickoff)}",
                  f"{x.side} {_line(x.best_line, x.market)} ({x.best_cost:+.0f}) at {bp.book_name(x.best_book)}",
                  f"cons {_line(x.cons_line, x.market)} ({x.cons_cost:+.0f}) · Atlas {x.atlas_number:.1f}",
                  f"{_ev(x.ev_atlas if x.market == 'total' else x.ev_price)} · P {_pct(x.p_atlas if x.market == 'total' else x.p_fair)}"
                  + (f" · {_flags(x)}" if _flags(x) else "")]
                 for x in chosen.itertuples()] if not chosen.empty else []
    tables = [{"title": f"Picks now: {len(pick_rows)} with positive expected value at the best price",
               "head": ["Game", "Side (price) at book", "Consensus · Atlas", "EV · P · flags"],
               "rows": pick_rows or [["Nothing clears zero at any book right now.", "", "", ""]]}]
    for market, label in (("total", "Totals"), ("spread", "Spreads")):
        m = upcoming[upcoming["market"] == market].copy()
        if m.empty:
            continue
        m["score"] = m["ev_atlas"].fillna(m["ev_price"]) if market == "total" else m["ev_price"]
        m = m.sort_values(["kickoff", "score"], ascending=[True, False]).drop_duplicates(["game_id"], keep="first")
        head = ["Game", "Consensus (open)", "Best side (book)", "Atlas · P" if market == "total" else "Price edge", "Flags"]
        rows = []
        for x in m.itertuples():
            if market == "total":
                value = f"{x.atlas_number:.1f} · P({x.side}) {_pct(x.p_atlas)} · EV {_ev(x.ev_atlas)}"
            else:
                value = f"EV {_ev(x.ev_price)} · fair {_pct(x.p_fair)}"
            rows.append([f"{_game(x, names)} · {_eastern(x.kickoff)}",
                         f"{_line(x.cons_line, market)} ({_line(x.open_line, market)})",
                         f"{x.side} {_line(x.best_line, market)} ({x.best_cost:+.0f}) {bp.book_name(x.best_book)} · {x.books} books",
                         value, _flags(x)])
        tables.append({"title": f"{label} board: every game, its better side at the best price", "head": head, "rows": rows})
    rec = paper.record(graded.assign(clv=pd.to_numeric(graded["clv"], errors="coerce"),
                                     price=pd.to_numeric(graded["cost"], errors="coerce"))) if len(graded) else None
    if rec:
        done = graded[graded["clv_result"].isin(["beat", "push", "lost"])] if "clv_result" in graded else graded.iloc[0:0]
        counts = done["clv_result"].value_counts() if len(done) else {}
        rows = [["Picks logged", str(len(graded))], ["Graded", str(rec["graded"])],
                ["Won-lost-push", f"{rec['wins']}-{rec['losses']}-{rec['pushes']}"], ["Win rate", _pct(rec["win_rate"])],
                ["Units", paper._num(rec["units"])], ["Per pick", paper._num(rec["roi"], "{:+.1%}")],
                ["Beat-push-lost the consensus close",
                 f"{int(counts.get('beat', 0))}-{int(counts.get('push', 0))}-{int(counts.get('lost', 0))}" if len(done) else "–"],
                ["Mean CLV, points", paper._num(pd.to_numeric(done["clv"], errors="coerce").mean(), "{:+.2f}") if len(done) else "–"],
                ["Mean CLV, win probability", paper._num(pd.to_numeric(done["clv_prob"], errors="coerce").mean(), "{:+.1%}") if len(done) else "–"]]
        tables.append({"title": "Board record (every pick, at the book, line and price shown when it first qualified)",
                       "head": ["", ""], "rows": rows})
        latest = graded[graded["outcome"] != "open"].sort_values("kickoff", ascending=False).head(12)
        if len(latest):
            tables.append({"title": "Latest graded picks", "head": ["Game", "Pick", "Result"],
                           "rows": [[_game(x, names), f"{x.side} {_line(x.line, x.market)} ({float(x.cost):+.0f}) {bp.book_name(x.book_id)}",
                                     f"{x.outcome} {x.profit:+.2f}" + (f" · closed {_line(x.close_line, x.market)}, CLV {x.clv:+g}" if pd.notna(x.clv) else "")]
                                    for x in latest.itertuples()]})
    notes = [
        "The board prices every upcoming game across every book BettingPros quotes (the consensus and prediction "
        "markets are shown as reference, never taken). Price edge is the expected value of a book's price under the "
        "consensus market read at that book's line. On totals, Atlas EV is the expected value under Atlas's own "
        "calibrated probability at that line: its total read through the share of a disagreement that turns out "
        "real (about a third in 2026). Spreads carry price edge only: the model's market weight there is 1.00.",
        f"Picks are the sides above {MIN_EV:.0%} expected value at the best price, one per game and market, at most "
        f"{MAX_PICKS}. Each is logged once, at the book, line and price on the board the first time it qualifies, and "
        f"graded on the score and against the consensus close. Nothing is read from fewer than {MIN_GRADED} graded.",
        f"Steam: the consensus has moved {STEAM['total']:g}+ (totals) or {STEAM['spread']:g}+ (spreads) points from its "
        f"opener. Off-market: the best book sits {OFF_MARKET['total']:g}+ or {OFF_MARKET['spread']:g}+ points off the "
        "consensus. Wind is BettingPros' kickoff forecast, shown from 15 mph outdoors.",
        f"Built {_eastern(now)} ET from {calls} API calls. Lines are licensed to the owner: they live only inside this "
        "ciphertext and in the sealed market record, never on a public page.",
    ]
    return [{"title": "The board", "notes": notes, "tables": tables}]


# ---------------------------------------------------------------------------
# The step
# ---------------------------------------------------------------------------


def build(passphrase: str, *, store=None, research: pd.DataFrame | None = None, now: datetime | None = None,
          client: bp.Client | None = None, market_where: Path | None = None, picks_where: Path | None = None) -> list[dict]:
    """Capture the market, seal it, price the board, log and grade the picks, and return the section. Never
    raises; returns nothing when BettingPros is not configured."""
    now = now or datetime.now(UTC)
    client = client or bp.Client.from_env()
    if client is None:
        return []
    try:
        if store is None:
            from atlas.live.store import Store

            store = Store.open()
        games = store.read("games")
        projections = store.read("projections")
        shapes = probability.load_shapes(store.read("market_shape"))
        up = upcoming(games, projections, now)
        lines, events = capture(client, up, now) if not up.empty else (pd.DataFrame(columns=[*bp.LINE_COLUMNS, "game_id"]),
                                                                        pd.DataFrame(columns=[*bp.EVENT_COLUMNS, "game_id"]))
        record = market_store.load(passphrase, market_where)
        record, added = market_store.append(record, lines)
        if not added.empty:
            market_store.seal(record, passphrase, added, market_where)
        board = price(lines, events, projections, shapes, now, store.read("calibration"))
        chosen = picks(board)
        pick_record = load_picks(passphrase, picks_where)
        pick_record, weeks = log_picks(pick_record, chosen, games, now)
        if weeks:
            seal_picks(pick_record, passphrase, weeks, picks_where)
            LOG.info("board: %d picks logged", len(weeks))
        kickoffs = pd.to_datetime(games.set_index(games["game_id"].astype(str))["kickoff"], utc=True, errors="coerce")
        started = kickoffs[kickoffs <= pd.Timestamp(now)]
        closes = market_store.closing(record[record["game_id"].astype(str).isin(set(started.index))], started) \
            if not record.empty else record
        all_events = events if pick_record.empty else events
        graded = grade_picks(pick_record, paper.results(research, games), closes, all_events, shapes)
        names = {}
        if research is not None and {"game_id", "home_team", "away_team"} <= set(research.columns):
            names = {str(g): f"{a} @ {h}" for g, h, a in zip(research["game_id"], research["home_team"], research["away_team"],
                                                             strict=True)}
        for g in games.itertuples():
            names.setdefault(str(g.game_id), f"{str(g.away_team).split(' ')[-1]} @ {str(g.home_team).split(' ')[-1]}")
        return sections(board, chosen, graded, names, now, client.calls)
    except Exception as error:  # noqa: BLE001 - the type only: a message could quote a line
        LOG.error("board not built: %s", type(error).__name__)
        return [{"title": "The board", "notes": [f"This run could not build the board ({type(error).__name__})."],
                 "tables": []}]


def main() -> None:
    argparse.ArgumentParser(description="The owner's board").parse_args()
    from atlas.dfs import owner

    passphrase = os.environ.get(owner.SECRET, "")
    if not passphrase.strip():
        raise SystemExit(f"{owner.SECRET} is not set")
    for s in build(passphrase):
        print(s["title"])
        for n in s["notes"]:
            print(" ", n)
        for t in s["tables"]:
            print("\n", t["title"])
            for row in t["rows"]:
                print("   ", " | ".join(str(c) for c in row))


if __name__ == "__main__":
    main()
