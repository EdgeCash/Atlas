"""The NHL's closing lines for the seasons the free archive does not reach, from BettingPros (MODEL_PLAN_NHL §2, §9).

    python -m atlas.owner.nhl_history      # the heavy refresh's step: backfill within budget, then the market row

The sportsbookreviewsonline archive stops on 27 November 2022, and Atlas's own capture began on 30 September
2026. The plan left the gap to the owner: buy The Odds API's history, or measure the BettingPros partner key's
depth first. The owner chose BettingPros (30 September 2026). So, a season at a time, newest first:

* **the events**: the season's NHL games as BettingPros lists them, a month at a time (a day at a time if the
  API does not honour a window), matched to the warehouse's games by puck drop and both teams;
* **the closes**: for each matched game and each of the moneyline, puck line and total, each kept book's last
  main pregame line: posted at or before puck drop and not from the live feed. The consensus, DraftKings and
  FanDuel are kept; the rest of the market is not needed for a benchmark and would only swell the record;
* **the depth**: a season whose games come back with no pregame line at all is where the key's history ends,
  and nothing older is asked for.

Everything BettingPros returns is sealed with the owner key (``tracking/owner_nhl_history/``, one file a
season) and never written in the clear; the log carries counts only. It resumes where it stopped, within
:data:`BUDGET` calls a run, against the key's 5,000 a day that the polls share.

Once there are closes, the **market row** the plan's §7 table was missing for the recent seasons is written
from them (``reports/nhl_market_recent.{md,json}``): per season, the Brier of the consensus close, of
DraftKings' and of Atlas on the same games. Aggregates only; never a line or a price.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from atlas.owner import sealed
from atlas.sources import bettingpros as bp
from atlas.util import get_logger

LOG = get_logger(__name__)

SPORT = "nhl"
#: The seasons to fill, newest first (the NHL's start year). 2022-23's first seven weeks are in the archive too.
SEASONS = (2025, 2024, 2023, 2022)
#: The books kept: the consensus, DraftKings, FanDuel.
KEPT = (bp.CONSENSUS, 12, 10)
MARKETS = ("moneyline", "spread", "total")
#: Calls a run may spend, and the pause after each offers call (the key allows five a second).
BUDGET = 500
PAUSE = 0.25
#: A BettingPros event and a warehouse game are the same game when their puck drops are this close.
MATCH = timedelta(hours=3)
#: BettingPros' team codes that are not the NHL's. Arizona's games sit under Utah in the warehouse.
CODES = {"NJ": "NJD", "SJ": "SJS", "TB": "TBL", "LA": "LAK", "LV": "VGK", "VEG": "VGK", "WAS": "WSH", "MON": "MTL",
         "CLB": "CBJ", "CLS": "CBJ", "NAS": "NSH", "ARI": "UTA", "PHX": "UTA", "UTAH": "UTA", "UTH": "UTA"}
COLUMNS = ["kind", "season", "event_id", "game_id", "scheduled", "market", "side", "book_id", "line", "cost",
           "updated", "open_line", "open_cost", "status", "events", "source", "rule"]
#: The rule the closes are taken by. 1 kept pregame-stamped lines only; 2 (from the first run's finding, 30
#: September 2026: 2025-26's lines all come back stamped after puck drop) falls back to the line as it came off
#: the board. A season marked done under an older rule with under half its games closed is asked again.
RULE = 2
REOPEN_BELOW = 0.5
#: A season's closes taken at the off count in the market row only when they score like pregame closes: an
#: in-game price knows the score and scores far better. The market's best pregame season since 2010 was 0.2256.
SANE_BRIER = 0.22


def path() -> Path:
    from atlas.live.store import tracking_dir

    return tracking_dir() / "owner_nhl_history"


def season_file(where: Path, season: int) -> Path:
    return where / f"closes-{int(season)}.enc.json"


def code(value) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    return CODES.get(value.upper(), value.upper())


def _ts(value) -> pd.Timestamp | None:
    t = pd.to_datetime(value, utc=True, errors="coerce")
    return None if pd.isna(t) else t


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------


def windows(season: int) -> list[tuple[str, str]]:
    """The season's months, October to June, as (first day, last day)."""
    out = []
    for year, month in [(season, m) for m in (10, 11, 12)] + [(season + 1, m) for m in range(1, 7)]:
        first = date(year, month, 1)
        last = (date(year + (month == 12), month % 12 + 1, 1) - timedelta(days=1))
        out.append((first.isoformat(), last.isoformat()))
    return out


def list_events(client: bp.Client, season: int, days: list[str], budget: int) -> tuple[pd.DataFrame, str]:
    """The season's events: a month at a time, or, where the API does not keep to a month's window, a day at a
    time over ``days`` (the warehouse's game days). Returns (events, how)."""
    parts, how = [], "month"
    for first, last in windows(season):
        if client.calls >= budget:
            break
        listed = bp._events(client.paged("/events", "events", sport=bp.SPORT_NAMES[SPORT], start=first, end=last),
                            SPORT)
        inside = listed[(listed["scheduled"] >= pd.Timestamp(first, tz="UTC"))
                        & (listed["scheduled"] < pd.Timestamp(last, tz="UTC") + pd.Timedelta(days=2))]
        if len(listed) and inside.empty:
            how = "day"                      # the window was not honoured: list the season a day at a time
            break
        parts.append(inside)
    if how == "day":
        parts = []
        for day in days:
            if client.calls >= budget:
                break
            parts.append(bp.events_on(client, SPORT, day))
    events = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=bp.EVENT_COLUMNS)
    return events.drop_duplicates("event_id").reset_index(drop=True), how


def match(games: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    """``event_id`` to the warehouse's ``game_id`` (and its puck drop): the same two teams, the puck drops within
    :data:`MATCH`."""
    cols = ["event_id", "game_id", "kickoff", "home", "away", "home_abbr", "visitor_abbr"]
    if games.empty or events.empty:
        return pd.DataFrame(columns=cols)
    g = games.assign(kick=pd.to_datetime(games["kickoff"], utc=True, errors="coerce")).dropna(subset=["kick"])
    by_home = {k: part for k, part in g.groupby("home_team")}
    rows = []
    for ev in events.itertuples():
        home, away = code(ev.home_abbr), code(ev.visitor_abbr)
        part = by_home.get(home)
        if part is None or ev.scheduled is pd.NaT or pd.isna(ev.scheduled):
            continue
        near = part[(part["away_team"] == away) & ((part["kick"] - ev.scheduled).abs() <= MATCH)]
        if len(near) == 1:
            r = near.iloc[0]
            rows.append({"event_id": int(ev.event_id), "game_id": int(r["game_id"]), "kickoff": r["kick"],
                         "home": home, "away": away, "home_abbr": ev.home_abbr, "visitor_abbr": ev.visitor_abbr})
    out = pd.DataFrame(rows, columns=cols)
    return out.drop_duplicates("event_id").drop_duplicates("game_id").reset_index(drop=True)


# ---------------------------------------------------------------------------
# Closes
# ---------------------------------------------------------------------------


def closing(lines: list[dict], start: pd.Timestamp) -> tuple[dict | None, str | None]:
    """A book's close and how it was known: ``pregame``, its last main line posted at or before ``start``; else
    ``at-off``, its last main line on the pregame market that nothing replaced, as it came off the board (the
    stamp then says when it came off, not when it was set). Never a line from the live feed."""
    stamped = [(t, ln) for ln in lines or [] if not ln.get("from_live") and (t := _ts(ln.get("updated"))) is not None]
    pre = [p for p in stamped if p[0] <= start]
    main = [p for p in pre if p[1].get("main")] or pre
    if main:
        return max(main, key=lambda p: p[0])[1], "pregame"
    off = [p for p in stamped if not p[1].get("replaced")]
    main = [p for p in off if p[1].get("main")] or off
    if main:
        return max(main, key=lambda p: p[0])[1], "at-off"
    return None, None


def parse_closes(body: dict, market: str, matched: pd.DataFrame, season: int) -> tuple[list[dict], dict]:
    """The kept books' closes on one market for the matched events in ``body``; and counts (books with lines only
    after puck drop, selections whose side is not known)."""
    info = matched.set_index("event_id")
    rows, counts = [], {"pregame": 0, "at-off": 0, "none": 0, "unsided": 0, "minutes": [], "lines": 0, "books": 0}
    for offer in body.get("offers") or []:
        try:
            event_id = int(offer.get("event_id"))
        except (TypeError, ValueError):
            continue
        if event_id not in info.index:
            continue
        ev = info.loc[event_id]
        for sel in offer.get("selections") or []:
            name = str(sel.get("selection") or "").lower()
            participant = sel.get("participant")
            if market == "total":
                side = name if name in ("over", "under") else None
            else:
                side = "home" if participant == ev["home_abbr"] else ("away" if participant == ev["visitor_abbr"]
                                                                      else None)
            if side is None:
                counts["unsided"] += 1
                continue
            opening = sel.get("opening_line") or {}
            for book in sel.get("books") or []:
                try:
                    book_id = int(book.get("id"))
                except (TypeError, ValueError):
                    continue
                if book_id not in KEPT:
                    continue
                lines = book.get("lines") or []
                close, source = closing(lines, ev["kickoff"])
                counts["lines"] += len(lines)
                counts["books"] += 1
                if close is None:
                    counts["none"] += 1
                    continue
                counts[source] += 1
                if source == "at-off":
                    counts["minutes"].append((_ts(close.get("updated")) - ev["kickoff"]).total_seconds() / 60.0)
                rows.append({"kind": "close", "season": int(season), "event_id": event_id, "game_id": int(ev["game_id"]),
                             "scheduled": ev["kickoff"].strftime("%Y-%m-%dT%H:%M:%SZ"), "market": market, "side": side,
                             "book_id": book_id,
                             "line": 0.0 if market == "moneyline" else _num(close.get("line")),
                             "cost": _num(close.get("cost")), "updated": str(close.get("updated") or ""),
                             "open_line": _num(opening.get("line")), "open_cost": _num(opening.get("cost")),
                             "source": source, "rule": RULE})
    return rows, counts


def _num(value) -> float | None:
    v = pd.to_numeric(value, errors="coerce")
    return None if pd.isna(v) else float(v)


# ---------------------------------------------------------------------------
# The record
# ---------------------------------------------------------------------------


def load(passphrase: str, where: Path | None = None) -> pd.DataFrame:
    rows = sealed.load(where or path(), passphrase)
    return pd.DataFrame(rows, columns=COLUMNS) if rows else pd.DataFrame(columns=COLUMNS)


def seal(record: pd.DataFrame, passphrase: str, seasons, where: Path | None = None) -> list[Path]:
    where = where or path()
    out = []
    for season in sorted({int(s) for s in seasons}):
        part = record[pd.to_numeric(record["season"]) == season]
        rows = json.loads(part.reindex(columns=COLUMNS).to_json(orient="records"))
        out.append(sealed.seal(rows, passphrase, season_file(where, season)))
    return out


def reopen(record: pd.DataFrame) -> tuple[pd.DataFrame, list[int]]:
    """Seasons marked done under an older rule with under :data:`REOPEN_BELOW` of their games closed by the
    consensus, taken out of the record to be asked again. Returns (the record, the seasons reopened)."""
    if record.empty:
        return record, []
    out = []
    for r in record[record["kind"] == "season"].itertuples():
        rule = pd.to_numeric(getattr(r, "rule", None), errors="coerce")
        if str(r.status) != "done" or (pd.notna(rule) and rule >= RULE):
            continue
        season = int(r.season)
        mine = record[pd.to_numeric(record["season"]) == season]
        asked = mine.loc[mine["kind"] == "tried", "event_id"].nunique()
        closed = mine.loc[(mine["kind"] == "close") & (pd.to_numeric(mine["book_id"]) == bp.CONSENSUS)
                          & (mine["market"] == "moneyline"), "event_id"].nunique()
        if asked and closed / asked < REOPEN_BELOW:
            out.append(season)
    if out:
        record = record[~pd.to_numeric(record["season"]).isin(out)].reset_index(drop=True)
    return record, out


def status(record: pd.DataFrame) -> dict[int, str]:
    s = record[record["kind"] == "season"]
    return {int(r.season): str(r.status) for r in s.itertuples()}


# ---------------------------------------------------------------------------
# The backfill
# ---------------------------------------------------------------------------


def backfill(client: bp.Client, games: pd.DataFrame, passphrase: str, *, where: Path | None = None,
             budget: int = BUDGET) -> tuple[pd.DataFrame, bool]:
    """Fill the seasons still open, newest first, within ``budget`` calls. Returns (the record, whether it
    changed). Counts only in the log."""
    from atlas.owner import nhl_capture

    record = load(passphrase, where)
    record, reopened = reopen(record)
    for season in reopened:
        LOG.info("nhl history: %d-%02d asked again under rule %d (under half its games had a consensus close)",
                 season, (season + 1) % 100, RULE)
    done = status(record)
    todo = [s for s in SEASONS if s not in done]
    if not todo:
        return record, False
    if "empty" in done.values():
        LOG.info("nhl history: the key's depth ends at %d; nothing older is asked for",
                 min(s for s, v in done.items() if v == "empty"))
        return record, False
    ids = nhl_capture.game_ids(nhl_capture.catalogue(client))
    if not ids:
        LOG.warning("nhl history: no NHL game markets in the catalogue")
        return record, False
    changed: set[int] = set(reopened)
    tried = set(record.loc[record["kind"] == "tried", "event_id"].dropna().astype(int)) if len(record) else set()
    new_rows: list[dict] = []
    for season in todo:
        if client.calls >= budget:
            break
        g = games[(pd.to_numeric(games["season"]) == season)]
        days = sorted(pd.to_datetime(g["kickoff"], utc=True).dt.tz_convert("America/New_York").dt.strftime(
            "%Y-%m-%d").unique())
        events, how = list_events(client, season, days, budget)
        pairs = match(g, events)
        open_ = pairs[~pairs["event_id"].isin(tried)]
        counts = {"pregame": 0, "at-off": 0, "none": 0, "unsided": 0, "minutes": [], "lines": 0, "books": 0}
        found = asked = 0
        finished = True
        for start in range(0, len(open_), bp.BATCH):
            if client.calls + len(MARKETS) > budget:
                finished = False
                break
            batch = open_.iloc[start:start + bp.BATCH]
            event_ids = ":".join(str(i) for i in batch["event_id"])
            for market in MARKETS:
                if market not in ids:
                    continue
                try:
                    body = client.get("/offers", sport=bp.SPORT_NAMES[SPORT], market_id=ids[market],
                                      event_id=event_ids, location=bp.LOCATION, limit=50)
                except Exception as error:  # noqa: BLE001 - the type only; the batch is tried again next run
                    LOG.warning("nhl history: %d %s batch not fetched (%s)", season, market, type(error).__name__)
                    finished = False
                    continue
                time.sleep(PAUSE)
                rows, c = parse_closes(body, market, batch, season)
                new_rows += rows
                found += len(rows)
                for k in counts:
                    counts[k] += c[k]
            new_rows += [{"kind": "tried", "season": season, "event_id": int(e), "game_id": int(gid)}
                         for e, gid in zip(batch["event_id"], batch["game_id"], strict=True)]
            asked += len(batch)
            changed.add(season)
        season_rows = [r for r in new_rows if r.get("season") == season and r["kind"] == "close"]
        with_close = len({r["event_id"] for r in season_rows if r["book_id"] == bp.CONSENSUS})
        mins = pd.Series(counts["minutes"], dtype=float)
        stamps = (f"stamped {mins.quantile(0.1):.0f}/{mins.median():.0f}/{mins.quantile(0.9):.0f} minutes after puck "
                  "drop (p10/median/p90)") if len(mins) else "none"
        LOG.info("nhl history: %d-%02d: %d events listed (%s windows), %d matched to %d warehouse games, %d asked "
                 "this run, %d closes kept, %d with a consensus close; book closes %d pregame, %d at the off (%s), "
                 "%d with no line; %.1f lines a book; %d selections unsided; %d calls so far", season,
                 (season + 1) % 100, len(events), how, len(pairs), len(g), asked, found, with_close,
                 counts["pregame"], counts["at-off"], stamps, counts["none"],
                 counts["lines"] / max(counts["books"], 1), counts["unsided"], client.calls)
        if finished:
            kept = record[(record["kind"] == "close") & (pd.to_numeric(record["season"]) == season)] if len(record) \
                else record
            any_close = len(season_rows) + len(kept) > 0
            new_rows.append({"kind": "season", "season": season, "status": "done" if any_close else "empty",
                             "events": int(len(pairs)), "rule": RULE})
            changed.add(season)
            if not any_close:
                LOG.info("nhl history: no line at all for %d-%02d: the key's depth ends after it", season,
                         (season + 1) % 100)
                break
    if new_rows:
        fresh = pd.DataFrame(new_rows).reindex(columns=COLUMNS)
        record = pd.concat([record.reindex(columns=COLUMNS), fresh], ignore_index=True) if len(record) else fresh
        seal(record, passphrase, changed, where)
    return record, bool(changed)


# ---------------------------------------------------------------------------
# The market row
# ---------------------------------------------------------------------------


def _no_vig(a, b) -> float:
    from atlas.live.probability import no_vig

    return no_vig(float(a), float(b)) if a is not None and b is not None else float("nan")


def home_probs(record: pd.DataFrame, book: int) -> pd.DataFrame:
    """Per game, the book's closing moneyline with its margin out: P(home), and ``at_off`` where either side's
    close was taken as it came off the board (rule 1's rows were all pregame)."""
    cols = ["game_id", "season", "p", "at_off"]
    c = record[(record["kind"] == "close") & (record["market"] == "moneyline")
               & (pd.to_numeric(record["book_id"]) == book)]
    if c.empty:
        return pd.DataFrame(columns=cols)
    source = c["source"] if "source" in c else pd.Series("pregame", index=c.index)
    c = c.assign(off=(source.astype("string").fillna("pregame") == "at-off").astype(int))
    wide = c.pivot_table(index=["game_id", "season"], columns="side", values="cost", aggfunc="last").reset_index()
    if not {"home", "away"} <= set(wide.columns):
        return pd.DataFrame(columns=cols)
    off = c.groupby("game_id")["off"].max()
    wide["p"] = [_no_vig(h, a) for h, a in zip(wide["home"], wide["away"], strict=True)]
    wide["at_off"] = wide["game_id"].map(off).fillna(0).astype(bool)
    return wide.dropna(subset=["p"])[cols]


def market_row(record: pd.DataFrame, atlas: pd.DataFrame) -> pd.DataFrame:
    """Per season, on the games with a consensus close and a result: the Brier of the consensus, of DraftKings
    (where it closed too) and of Atlas. ``atlas`` is the walked model: ``game_id``, ``p_home``, ``home_win``.
    A season's closes taken at the off count only when there are 30 or more and they score like pregame closes
    (:data:`SANE_BRIER`); otherwise they are left out and counted in ``left_out``."""
    cons = home_probs(record, bp.CONSENSUS).rename(columns={"p": "p_market"})
    dk = home_probs(record, 12)[["game_id", "p"]].rename(columns={"p": "p_dk"})
    f = cons.merge(atlas, on="game_id", how="inner").merge(dk, on="game_id", how="left")
    left_out: dict = {}
    keep = []
    for season, part in f.groupby("season"):
        off = part[part["at_off"]]
        brier = float(((off["p_market"] - off["home_win"]) ** 2).mean()) if len(off) else float("nan")
        sane = len(off) >= 30 and brier >= SANE_BRIER
        left_out[season] = (0 if sane else int(len(off)), brier)
        keep.append(part if sane else part[~part["at_off"]])
    f = pd.concat(keep, ignore_index=True) if keep else f.iloc[0:0]
    rows = []
    seasons = [(s, f[f["season"] == s]) for s in sorted(left_out)] + [("all", f)]
    for season, part in seasons:
        y = part["home_win"].to_numpy(float)
        dk_part = part.dropna(subset=["p_dk"])
        out, off_brier = (sum(v[0] for v in left_out.values()), float("nan")) if season == "all" \
            else left_out[season]
        rows.append({"season": season, "games": int(len(part)), "at_off": int(part["at_off"].sum()),
                     "left_out": int(out), "off_brier": off_brier,
                     "market": float(((part["p_market"] - y) ** 2).mean()) if len(part) else float("nan"),
                     "atlas": float(((part["p_home"] - y) ** 2).mean()) if len(part) else float("nan"),
                     "dk_games": int(len(dk_part)),
                     "draftkings": float(((dk_part["p_dk"] - dk_part["home_win"]) ** 2).mean())
                     if len(dk_part) else float("nan")})
    return pd.DataFrame(rows)


def walked_atlas(seasons) -> pd.DataFrame:
    """The stored game model's P(home wins) for every completed game of ``seasons``, walked forward unchanged."""
    from atlas.models import nhl_model, nhl_projection

    stored = nhl_projection.choices()
    if stored is None:
        return pd.DataFrame(columns=["game_id", "p_home", "home_win"])
    tables = nhl_model.load_tables()
    f, _, games = nhl_projection.walk(tables, stored)
    f = f.merge(games[["game_id", "season", "home_score", "away_score"]], on="game_id", how="left")
    f = f[f["season"].isin(list(seasons))]
    layers = nhl_projection.ensure_layers(stored, tables, f, games, sorted(f["season"].unique()))
    f = nhl_model.with_grid(f, layers)
    return pd.DataFrame({"game_id": f["game_id"].astype("int64"), "p_home": f["p_home"].astype(float),
                         "home_win": (f["home_score"] > f["away_score"]).astype(float)})


def write_report(row: pd.DataFrame, record: pd.DataFrame, root: Path) -> Path:
    done = status(record)
    (root / "reports" / "nhl_market_recent.json").write_text(json.dumps(
        {"seasons": {str(k): v for k, v in done.items()}, "rows": row.to_dict("records")}, indent=1,
        default=str) + "\n")
    lines = ["# The NHL's market row for the recent seasons", "",
             "`python -m atlas.owner.nhl_history`, in the heavy refresh. The closing moneyline from BettingPros "
             "(sealed in `tracking/owner_nhl_history/`, never in the clear), its margin taken out; the stored game "
             "model walked forward unchanged. Brier on P(home wins), overtime and the shootout included. Aggregates "
             "only.", "",
             "| Season | Games | Of which closed at the off | Consensus close | DraftKings close (games) | Atlas | "
             "Left out |", "|---|---|---|---|---|---|---|"]
    for r in row.itertuples():
        label = "2022-26 pooled" if r.season == "all" else f"{int(r.season)}-{(int(r.season) + 1) % 100:02d}"
        dk = f"{r.draftkings:.4f} ({r.dk_games:,})" if r.dk_games else "–"
        why = "" if r.season == "all" else (f" (Brier {r.off_brier:.4f}: not a pregame close)"
                                            if r.left_out >= 30 else " (too few to judge)")
        out = f"{r.left_out:,} closed at the off{why}" if r.left_out else "–"
        market, atlas = (f"{r.market:.4f}", f"{r.atlas:.4f}") if r.games else ("–", "–")
        lines.append(f"| {label} | {r.games:,} | {r.at_off:,} | {market} | {dk} | {atlas} | {out} |")
    lines += ["", "A close taken at the off is a book's last line on the pregame market as it came off the board, "
              "for games whose lines came back stamped after puck drop. Those count only when a season has 30 or more "
              f"and they score like pregame closes (Brier {SANE_BRIER} or worse): an in-game price knows the score.",
              "", "Seasons backfilled: " + (", ".join(f"{s}-{(s + 1) % 100:02d} {v}" for s, v in sorted(done.items()))
                                           or "none yet") + ".", ""]
    out = root / "reports" / "nhl_market_recent.md"
    out.write_text("\n".join(lines))
    return out


def main() -> None:
    argparse.ArgumentParser(description="The NHL's closing lines 2022-26 from BettingPros, and the market row").parse_args()
    from atlas import config
    from atlas.dfs import owner

    passphrase = os.environ.get(owner.SECRET, "").strip()
    client = bp.Client.from_env()
    if not passphrase or client is None:
        LOG.info("nhl history: BettingPros or the owner key is not configured; nothing to do")
        return
    try:
        from atlas.staging.nhl import build

        games = build.load("games")
        games = games[games["completed"].astype(bool)]
        record, changed = backfill(client, games, passphrase)
        root = config.paths().root
        report = root / "reports" / "nhl_market_recent.md"
        if (changed or not report.exists()) and (record["kind"] == "close").any():
            row = market_row(record, walked_atlas(SEASONS))
            write_report(row, record, root)
            LOG.info("nhl history: market row written for %d games", int(row.loc[row["season"] == "all", "games"].sum()))
    except Exception as error:  # noqa: BLE001 - the type and place only; never fails the heavy run
        from atlas.util import where

        LOG.warning("nhl history: stopped: %s at %s", type(error).__name__, where(error))


if __name__ == "__main__":
    main()
