"""NBA player props on Polymarket: Atlas's projection beside the market's price, a record, and paper positions.

Polymarket lists, on each NBA game event, a ladder of player props (points,
rebounds, assists, threes, and thinner ones) as Yes/No contracts on "Name:
Stat O/U line". Every run:

1. **reads** them with the game markets (`prop_quotes`), matches each to
   the Atlas game (`atlas/polymarket/match.py`) and the player to Atlas's
   snapshot of him on one of the game's two teams (`atlas/models/nba_props.py`),
   and keeps each player-stat's main line in ``tracking/polymarket_props.csv``
   with Atlas's probability of the over as it stood;
2. **grades** the record: once a game is final, each kept prop against the
   box score and Polymarket's close, into ``tracking/prop_record.csv``, the
   record the share of Atlas's disagreement is fitted on;
3. **prices** every prop contract: the market's probability, Atlas's, and
   the fair one - the market pulled toward Atlas by that share, zero until
   the record says otherwise - then the fee, expected value and Kelly
   (`atlas/polymarket/pricing.py`);
4. **takes paper positions** by the same rule as the game markets, one per
   player-stat, in their own sealed record (``tracking/polymarket_prop_positions/``),
   graded on the box score (a player who did not play is a push) and
   against the close.

Nothing here buys anything.
"""

from __future__ import annotations

import math
import re
import unicodedata
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from atlas.live.store import SCHEMA
from atlas.polymarket import match, page, positions, pricing, source
from atlas.util import get_logger

LOG = get_logger(__name__)

SPORT = "nba"
#: Polymarket's ``sportsMarketType`` of each prop Atlas projects.
PROP_TYPES = {"points": "points", "rebounds": "rebounds", "assists": "assists", "threes": "threes"}
QUESTION = re.compile(r"^(?P<player>.+?):\s*(?P<stat>.+?)\s+O/U\s+(?P<line>\d+(?:\.\d+)?)\s*$")
PROP_COLUMNS = SCHEMA["polymarket_props"]
RECORD_COLUMNS = SCHEMA["prop_record"]
POSITION_COLUMNS = [*positions.COLUMNS, "player", "stat", "atlas_mean"]
TAB = "Props"
MAX_POSITIONS = 10
TOP_ROWS = 15


def path() -> Path:
    from atlas.live.store import tracking_dir

    return tracking_dir() / "polymarket_prop_positions"


# ---------------------------------------------------------------------------
# Reading the venue
# ---------------------------------------------------------------------------


def key(name) -> str:
    """A player's name as a key: lowercased, accents and punctuation dropped, suffixes dropped."""
    text = unicodedata.normalize("NFKD", str(name or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower()
    text = re.sub(r"[.'’\-]", "", text)
    words = [w for w in text.split() if w not in ("jr", "sr", "ii", "iii", "iv")]
    return " ".join(words)


def prop_quotes(events: list[dict], league: source.League, captured_at) -> pd.DataFrame:
    """One row per side of every player prop Atlas projects, across the events, as of ``captured_at``."""
    stamp = pd.Timestamp(captured_at)
    stamp = (stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC"))
    stamp = stamp.replace(microsecond=0).isoformat()
    rows = []
    for event in events:
        away, home = source.teams(event, league)
        for m in event.get("markets") or []:
            stat = PROP_TYPES.get(m.get("sportsMarketType"))
            if stat is None or not m.get("active", True) or m.get("closed"):
                continue
            q = QUESTION.match(str(m.get("question") or ""))
            outcomes, prices, tokens = source._list(m.get("outcomes")), source._list(m.get("outcomePrices")), \
                source._list(m.get("clobTokenIds"))
            if q is None or len(outcomes) != 2 or len(tokens) != 2:
                continue
            first = str(outcomes[0]).strip().lower()
            if first not in ("yes", "over"):
                continue
            line = source._num(q.group("line"))
            if not math.isfinite(line):
                continue
            bid0, ask0 = source._round(source._num(m.get("bestBid"))), source._round(source._num(m.get("bestAsk")))
            bids = [bid0, source._round(1.0 - ask0) if math.isfinite(ask0) else float("nan")]
            asks = [ask0, source._round(1.0 - bid0) if math.isfinite(bid0) else float("nan")]
            mids = [source._round(source._num(prices[i])) if i < len(prices) else float("nan") for i in range(2)]
            last0 = source._round(source._num(m.get("lastTradePrice")))
            lasts = [last0, source._round(1.0 - last0) if math.isfinite(last0) else float("nan")]
            start = source._game_start(m, event)
            accepting = bool(m.get("acceptingOrders")) and bool(m.get("active", True)) and not bool(m.get("closed"))
            for i, side in enumerate(("over", "under")):
                rows.append({
                    "captured_at": stamp, "last_seen_at": stamp, "sport": league.sport, "game_id": None,
                    "event_id": str(event.get("id")), "event_slug": event.get("slug"),
                    "game_start": start.isoformat() if pd.notna(start) else None, "away": away, "home": home,
                    "player": q.group("player").strip(), "stat": stat, "market_id": str(m.get("id")),
                    "condition_id": m.get("conditionId"), "token_id": str(tokens[i]), "side": side, "line": line,
                    "bid": bids[i], "ask": asks[i], "mid": mids[i], "last": lasts[i],
                    "spread": source._round(source._num(m.get("spread"))),
                    "liquidity": source._num(m.get("liquidityNum", m.get("liquidity"))), "fee_rate": source.fee_rate(m),
                    "accepting": accepting, "p_atlas": float("nan"), "atlas_mean": float("nan"),
                })
    return pd.DataFrame(rows, columns=PROP_COLUMNS)


def main_lines(q: pd.DataFrame) -> pd.DataFrame:
    """What the record keeps of a player's stat: the line the market prices nearest to even, both sides."""
    if q.empty:
        return q
    mid = pd.to_numeric(q["mid"], errors="coerce")
    first = q["side"] == "over"
    off = (mid - 0.5).abs().where(first)
    keys = [q["event_id"], q["player"], q["stat"]]
    nearest = off.groupby(keys).transform("min")
    chosen = q["market_id"].where(first & (off == nearest))
    main = chosen.groupby(keys).transform("first")
    return q[(q["market_id"] == main).fillna(False)].reset_index(drop=True)


# ---------------------------------------------------------------------------
# Atlas's reading
# ---------------------------------------------------------------------------


def _players_by_team(snap: dict) -> dict[tuple[int, str], pd.Series]:
    out: dict[tuple[int, str], pd.Series] = {}
    for row in snap["players"].itertuples(index=False):
        try:
            out[(int(row.team_id), key(row.player))] = row
        except (TypeError, ValueError):
            continue
    return out


def expectations(q: pd.DataFrame, snap: dict | None) -> pd.DataFrame:
    """Each prop with Atlas's expectation of the stat and its probability of the side: the player found by
    name on one of the game's two teams in the snapshot; nan where he is not."""
    from atlas.models import nba_props

    out = q.copy()
    out["atlas_mean"] = np.nan
    out["p_atlas"] = np.nan
    if snap is None or out.empty or "home_team_id" not in out:
        return out
    by_team = _players_by_team(snap)
    cache: dict[tuple, dict] = {}
    means, probs = [], []
    for r in out.itertuples():
        mean_, p = float("nan"), float("nan")
        try:
            home_id, away_id = int(r.home_team_id), int(r.away_team_id)
        except (TypeError, ValueError):
            means.append(mean_)
            probs.append(p)
            continue
        k = key(r.player)
        for team_id, opp_id, home in ((home_id, away_id, True), (away_id, home_id, False)):
            row = by_team.get((team_id, k))
            if row is None:
                continue
            ck = (team_id, k, opp_id)
            if ck not in cache:
                cache[ck] = nba_props.expect(snap, row._asdict(), team_id, opp_id, home)
            mean_ = cache[ck].get(str(r.stat), float("nan"))
            if math.isfinite(mean_):
                p = nba_props.prob(mean_, float(r.line), str(r.side), nba_props.dispersion(snap, str(r.stat)))
            break
        means.append(mean_)
        probs.append(p)
    out["atlas_mean"], out["p_atlas"] = means, probs
    return out


# ---------------------------------------------------------------------------
# The record, and the share it gives
# ---------------------------------------------------------------------------


def results_frame(player_games: pd.DataFrame | None) -> pd.DataFrame:
    """What each player did in each game, keyed for a prop: (game id, the player's name key)."""
    cols = ["game_id", "player_key", "played", *PROP_TYPES.values()]
    if player_games is None or player_games.empty:
        return pd.DataFrame(columns=cols)
    from atlas.staging.nba import players as players_stage

    r = players_stage.results(player_games)
    r["player_key"] = r["player"].map(key)
    return r.drop_duplicates(["game_id", "player_key"], keep="last")[cols]


def _value(results: pd.DataFrame, game_id, player, stat) -> tuple[float, bool | None]:
    """(the stat the player recorded, whether he played); (nan, None) when the game is not in the results."""
    if results.empty:
        return float("nan"), None
    r = results[(results["game_id"].astype(str) == str(game_id)) & (results["player_key"] == key(player))]
    if r.empty:
        # The game is in the results (someone played) but he is not: he did not dress.
        return (float("nan"), False) if (results["game_id"].astype(str) == str(game_id)).any() else (float("nan"), None)
    row = r.iloc[0]
    return (float(row[stat]), bool(row["played"]))


def grade_record(kept: pd.DataFrame, graded: pd.DataFrame, results: pd.DataFrame, now: datetime) -> pd.DataFrame:
    """New rows for ``prop_record``: each kept over-side prop whose game has started and has a box score,
    not yet graded, with Atlas's probability of the over as kept, the close's, what the player recorded,
    and whether Atlas's side happened (a tie on a whole line, or a player who did not play, is one half)."""
    if kept.empty:
        return pd.DataFrame(columns=RECORD_COLUMNS)
    over = source.latest(kept[kept["side"] == "over"])
    over = over[over["game_id"].notna() & pd.to_numeric(over["p_atlas"], errors="coerce").notna()]
    done = set(graded["token_id"].astype(str)) if len(graded) else set()
    start = pd.to_datetime(over["game_start"], utc=True, errors="coerce")
    over = over[(start <= pd.Timestamp(now)) & ~over["token_id"].astype(str).isin(done)]
    rows = []
    for r in over.itertuples():
        value, played = _value(results, r.game_id, r.player, r.stat)
        if played is None:
            continue
        line, p_atlas = float(r.line), float(r.p_atlas)
        p_close = source.close(kept, r.token_id, r.game_start)
        if not played or not math.isfinite(value) or value == line:
            won = 0.5
        else:
            atlas_over = p_atlas >= 0.5
            won = float((value > line) == atlas_over)
        rows.append({"token_id": str(r.token_id), "game_id": str(r.game_id), "kickoff": r.game_start, "sport": SPORT,
                     "player": r.player, "stat": r.stat, "line": line, "p_atlas": round(p_atlas, 4),
                     "p_close": round(p_close, 4) if math.isfinite(p_close) else np.nan,
                     "value": value if math.isfinite(value) else np.nan, "played": bool(played), "won": won,
                     "graded_at": pd.Timestamp(now).strftime("%Y-%m-%dT%H:%M:%SZ")})
    return pd.DataFrame(rows, columns=RECORD_COLUMNS)


def calibration_rows(record: pd.DataFrame) -> pd.DataFrame:
    """The prop record in the calibration table's columns, the moneyline way: ``claimed`` is Atlas's
    probability for its side, ``abs_edge`` the gap in points of probability between it and the close's
    probability for that side (negative when the close was the more confident), ``won`` what happened."""
    cols = ["game_id", "sport", "season", "week", "season_type", "market", "abs_edge", "claimed", "won", "kickoff"]
    if record is None or record.empty:
        return pd.DataFrame(columns=cols)
    r = record.dropna(subset=["p_atlas", "p_close"])
    r = r[r["won"] != 0.5]
    p = pd.to_numeric(r["p_atlas"], errors="coerce")
    c = pd.to_numeric(r["p_close"], errors="coerce")
    over = p >= 0.5
    claimed = np.where(over, p, 1 - p)
    market = np.where(over, c, 1 - c)
    kick = pd.to_datetime(r["kickoff"], utc=True, errors="coerce")
    return pd.DataFrame({"game_id": r["game_id"].to_numpy(), "sport": SPORT,
                         "season": kick.dt.year.where(kick.dt.month >= 10, kick.dt.year - 1).to_numpy(),
                         "week": 0, "season_type": "regular", "market": "player",
                         "abs_edge": 100.0 * (claimed - market), "claimed": claimed,
                         "won": pd.to_numeric(r["won"], errors="coerce").to_numpy(), "kickoff": r["kickoff"].to_numpy()},
                        columns=cols)


# ---------------------------------------------------------------------------
# Pricing
# ---------------------------------------------------------------------------


def price(q: pd.DataFrame, calibration: pd.DataFrame | None) -> pd.DataFrame:
    """Every matched prop contract with Atlas's reading: the market's probability, Atlas's, the fair one by
    the record's share, the fee, the cost, expected value and Kelly, in the columns the positions read."""
    cols = ["p_market", "p_raw", "p_ladder", "share", "p", "fee", "cost", "ev", "kelly", "market", "prop_key", "label",
            "kickoff"]
    if q.empty or "game_id" not in q:
        return q.assign(**{c: pd.Series(dtype=float) for c in cols})
    t = q[q["game_id"].notna()].copy()
    if t.empty:
        return t.assign(**{c: pd.Series(dtype=float) for c in cols})
    k, _ = pricing.share(calibration, SPORT, "player")
    t["p_market"] = pricing.market_probs(t)
    t["p_raw"] = pd.to_numeric(t["p_atlas"], errors="coerce")
    t["p_ladder"] = np.nan
    t["share"] = k
    t["p"] = np.where(t["p_raw"].notna() & t["p_market"].notna(), t["p_market"] + k * (t["p_raw"] - t["p_market"]),
                      t["p_market"])
    ask = pd.to_numeric(t["ask"], errors="coerce")
    rate = pd.to_numeric(t["fee_rate"], errors="coerce").fillna(0.0)
    t["fee"] = [pricing.fee(a, f) for a, f in zip(ask, rate, strict=True)]
    t["cost"] = ask + t["fee"]
    ok = (ask > 0) & (ask < 1) & (t["cost"] < 1) & t["p"].notna()
    t["ev"] = np.where(ok, t["p"] / t["cost"] - 1.0, np.nan)
    t["kelly"] = np.where(ok, ((t["p"] - t["cost"]) / (1.0 - t["cost"])).clip(lower=0.0), np.nan)
    t["market"] = "player:" + t["stat"].astype(str)
    t["prop_key"] = t["game_id"].astype(str) + "|" + t["player"].map(key) + "|" + t["stat"].astype(str)
    if "label" not in t or t["label"].isna().all():
        t["label"] = t["away"].astype(str) + " @ " + t["home"].astype(str)
    if "kickoff" not in t or t["kickoff"].isna().all():
        t["kickoff"] = t["game_start"]
    return t.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Positions on props
# ---------------------------------------------------------------------------


def grade_positions(record: pd.DataFrame, results: pd.DataFrame, quotes: pd.DataFrame, now: datetime) -> pd.DataFrame:
    """Each position with its outcome from the box score (a player who did not play, or a tie on a whole
    line, is a push), its return, and Polymarket's close for the contract."""
    if record.empty:
        return record.assign(outcome=pd.Series(dtype=str), profit=pd.Series(dtype=float), pnl=pd.Series(dtype=float),
                             close=pd.Series(dtype=float), clv=pd.Series(dtype=float))
    r = record.copy()
    kick = pd.to_datetime(r["kickoff"], utc=True, errors="coerce")
    outcomes = []
    for x in r.itertuples():
        value, played = _value(results, x.game_id, x.player, x.stat)
        if played is None:
            outcomes.append("open")
        elif not played or not math.isfinite(value) or value == float(x.line):
            outcomes.append("push")
        else:
            over = value > float(x.line)
            outcomes.append("win" if over == (str(x.side) == "over") else "loss")
    r["outcome"] = outcomes
    cost = pd.to_numeric(r["cost"], errors="coerce")
    r["profit"] = np.select([r["outcome"] == "win", r["outcome"] == "loss"], [(1.0 - cost) / cost, -1.0], 0.0)
    r.loc[r["outcome"] == "open", "profit"] = np.nan
    r["pnl"] = pd.to_numeric(r["stake"], errors="coerce") * r["profit"]
    started = kick <= pd.Timestamp(now)
    r["close"] = [positions.closing(quotes, tok, k) if s else float("nan")
                  for tok, k, s in zip(r["token_id"], kick, started, strict=True)]
    r["clv"] = r["close"] - pd.to_numeric(r["ask"], errors="coerce")
    return r


# ---------------------------------------------------------------------------
# The owner page
# ---------------------------------------------------------------------------


def _contract(x) -> str:
    return f"{str(x.player)} {str(x.side)} {float(x.line):g} {str(x.stat)}"


def _atlas(x) -> str:
    m = pd.to_numeric(getattr(x, "atlas_mean", np.nan), errors="coerce")
    return f"Atlas {float(m):.1f}" if pd.notna(m) else "Atlas –"


def sections(priced: pd.DataFrame, chosen: pd.DataFrame, graded: pd.DataFrame, now: datetime,
             note: str | None = None) -> list[dict]:
    logged = set(graded["position_id"]) if len(graded) else set()
    day = pd.Timestamp(chosen["day"].iloc[0]).strftime("%a %b %-d") if len(chosen) else \
        pd.Timestamp(positions.day_of(now)).strftime("%a %b %-d")
    rows = [[[x.label, page._eastern(x.kickoff)], [_contract(x), _atlas(x)], page._price(x), page._edge(x),
             [f"{float(x.stake):.1%}", "logged" if x.position_id in logged else ""]]
            for x in chosen.itertuples()]
    out = [{"title": f"Prop positions for {day} ({len(rows)})", "tab": TAB,
            "tables": [{"title": "", "head": [*page.HEAD, "Stake"], "stack": True,
                        "rows": rows or [[f"Nothing clears {positions.MIN_EV:+.0%} after the fee.", "", "", "", ""]]}],
            "notes": [
                "Paper only. The same rule as the game markets, one position per player's stat, at most "
                f"{MAX_POSITIONS} a day; a player who does not play is a push.",
                "Fair is Polymarket's probability pulled toward Atlas's projection by the share of Atlas's "
                "disagreement the prop record has shown to be real: zero until the record says otherwise, so at "
                "first nothing here clears the fee. Atlas is minutes times a rate times the game "
                "(atlas/models/nba_props.py).",
                *([note] if note else [])]}]
    tables = []
    upcoming = priced[pd.to_datetime(priced["kickoff"], utc=True, errors="coerce") > pd.Timestamp(now)] \
        if len(priced) else priced
    if len(upcoming):
        with_atlas = upcoming[pd.to_numeric(upcoming["p_raw"], errors="coerce").notna()]
        ok = positions.eligible(with_atlas, now) if len(with_atlas) else pd.Series(dtype=bool)
        best = with_atlas.assign(takeable=ok).sort_values(["takeable", "ev"], ascending=[False, False]) \
            .drop_duplicates(["prop_key"], keep="first").sort_values("ev", ascending=False)
        rows = [[[x.label, page._eastern(x.kickoff)],
                 [_contract(x), _atlas(x) + ("" if x.takeable else " · not takeable")],
                 page._price(x), page._edge(x)] for x in best.itertuples()]
        tables.append({"title": f"Best {min(TOP_ROWS, len(rows))} of {len(rows)} player-stats by expected value",
                       "head": page.HEAD, "stack": True, "rows": rows[:TOP_ROWS]})
        if len(rows) > TOP_ROWS:
            tables.append({"title": f"The other {len(rows) - TOP_ROWS}", "fold": True, "stack": True,
                           "head": page.HEAD, "rows": rows[TOP_ROWS:]})
    counts = []
    if len(priced):
        for stat, part in priced.groupby(priced["stat"].astype(str)):
            over = part[part["side"] == "over"]
            counts.append([stat, str(len(over)), str(int(pd.to_numeric(over["p_raw"], errors="coerce").notna().sum())),
                           str(int((pd.to_numeric(over["liquidity"], errors="coerce") >= positions.MIN_LIQUIDITY).sum()))])
    tables.append({"title": "Prop contracts this run, by stat", "fold": True,
                   "head": ["Stat", "Contracts", "Atlas projects", f"Depth ≥ ${positions.MIN_LIQUIDITY:,.0f}"],
                   "rows": counts})
    out.append({"title": "Props board", "tab": TAB, "tables": tables, "notes": [
        "Each player's stat at the contract that pays best, whether or not it clears the bar. Atlas is the "
        "expectation of the stat; fair and market are probabilities of the side.",
        "Most prop books on Polymarket are thin: a contract is takeable only with depth and a tight spread, "
        "and the board says when it is not."]})
    if len(graded):
        done = graded[graded["outcome"].isin(["win", "loss", "push"])]
        decided = done[done["outcome"] != "push"]
        staked = float(pd.to_numeric(done["stake"], errors="coerce").sum()) if len(done) else 0.0
        pnl = float(done["pnl"].sum()) if len(done) else 0.0
        clv = pd.to_numeric(graded["clv"], errors="coerce")
        rows = [["Positions logged", str(len(graded))], ["Graded", str(len(done))],
                ["Won-lost-push", f"{int((decided['outcome'] == 'win').sum())}-{int((decided['outcome'] == 'loss').sum())}-"
                                  f"{int((done['outcome'] == 'push').sum())}"],
                ["Return on the bankroll", f"{pnl:+.2%}" if len(done) else "–"],
                ["Return per dollar staked", f"{pnl / staked:+.1%}" if staked else "–"],
                ["Bought below the close", f"{int((clv > 0).sum())} of {int(clv.notna().sum())}" if clv.notna().any() else "–"]]
        out.append({"title": "Prop record (paper)", "tab": TAB, "tables": [{"title": "", "head": ["", ""], "rows": rows}],
                    "notes": ["Graded from ESPN's box score as hoopR mirrors it, and against Polymarket's close."]})
    return out


def record_section(record: pd.DataFrame) -> dict | None:
    """What the graded prop record says so far: how often Atlas's side happened, by its confidence."""
    if record is None or record.empty:
        return None
    r = record[record["won"] != 0.5].copy()
    if r.empty:
        return None
    p = pd.to_numeric(r["p_atlas"], errors="coerce")
    r["claimed"] = np.where(p >= 0.5, p, 1 - p)
    rows = []
    for lo, hi in ((0.5, 0.55), (0.55, 0.6), (0.6, 0.7), (0.7, 1.01)):
        part = r[(r["claimed"] >= lo) & (r["claimed"] < hi)]
        if len(part):
            rows.append([f"{lo:.0%}–{min(hi, 1.0):.0%}", str(len(part)), f"{part['claimed'].mean():.1%}",
                         f"{pd.to_numeric(part['won']).mean():.1%}"])
    k, n = pricing.share(calibration_rows(record), SPORT, "player")
    return {"title": f"Prop record: {len(r)} graded", "tab": TAB,
            "tables": [{"title": "", "head": ["Atlas claimed", "props", "claimed", "happened"], "rows": rows}],
            "notes": [f"Every kept prop graded against the box score: what Atlas claimed for its side against how "
                      f"often it happened. The share of Atlas's disagreement with the close the pricing takes, fitted "
                      f"on {n} graded props: {k:.0%}."]}


# ---------------------------------------------------------------------------
# One run
# ---------------------------------------------------------------------------


def refresh(store, events: list[dict], pairs: pd.DataFrame, now: datetime, passphrase: str | None,
            *, snap: dict | None = None, player_games: pd.DataFrame | None = None) -> tuple[list[dict], dict]:
    """The props step of the Polymarket run: read, keep, grade, price, position. Returns (the owner page's
    sections, a coverage summary for the public report). Never raises."""
    from atlas.models import nba_props

    summary = {"contracts": 0, "projected": 0, "games": 0, "graded": 0}
    try:
        snap = snap or nba_props.load_state()
        if snap is None:
            LOG.info("props: no NBA props snapshot yet; nothing priced")
            return [{"title": "Props", "tab": TAB, "tables": [],
                     "notes": ["No NBA player snapshot yet: the next heavy refresh writes one."]}], summary
        q = prop_quotes(events, source.LEAGUES[SPORT], now)
        if len(pairs):
            q = match.attach(q, pairs[pairs["sport"].astype(str) == SPORT])
        else:
            q = q.assign(kickoff=None, label=None, home_team_id=None, away_team_id=None)
        q = expectations(q, snap)
        matched = q[q["game_id"].notna()]
        kept = main_lines(matched)
        record = store.read("polymarket_props")
        if len(kept):
            record, added = source.fold(record, kept.reindex(columns=PROP_COLUMNS), cols=PROP_COLUMNS)
            store.write("polymarket_props", record)
            LOG.info("props: %d prop contracts read, %d on matched games, %d kept, %d new rows", len(q), len(matched),
                     len(kept), added)
        if player_games is None:
            try:
                player_games, _ = nba_props.load_tables()
            except Exception as error:  # noqa: BLE001 - a poll without the warehouse grades nothing this run
                LOG.info("props: no player games to grade with (%s)", type(error).__name__)
        results = results_frame(player_games)
        graded_record = store.read("prop_record")
        new = grade_record(record, graded_record, results, now)
        if len(new):
            store.append_new_only("prop_record", new)
            graded_record = store.read("prop_record")
            LOG.info("props: %d props graded into the record (%d in all)", len(new), len(graded_record))
        calibration = calibration_rows(graded_record)
        priced = price(matched, calibration)
        summary = {"contracts": int(len(q) // 2), "projected": int(pd.to_numeric(priced["p_raw"], errors="coerce").notna().sum() // 2)
                   if len(priced) else 0, "games": int(matched["game_id"].nunique()) if len(matched) else 0,
                   "graded": int(len(graded_record))}
        if not passphrase:
            return [], summary
        chosen, graded = positions.run(priced, results, record, passphrase, now, where=path(), unit="prop_key",
                                       columns=POSITION_COLUMNS, grader=grade_positions)
        out = sections(priced, chosen, graded, now)
        rec = record_section(graded_record)
        return ([*out, rec] if rec else out), summary
    except Exception as error:  # noqa: BLE001 - the type only
        LOG.error("props not refreshed: %s", type(error).__name__)
        return [{"title": "Props", "tab": TAB, "tables": [],
                 "notes": [f"This run could not price the props ({type(error).__name__})."]}], summary
