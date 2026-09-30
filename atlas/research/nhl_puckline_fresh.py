"""The puck line's fresh test on 2023-26, scored once as docs/NHL_PUCKLINE_FRESH_PREREGISTRATION.md fixed it.

The heavy refresh calls :func:`run` the first time 2023-24, 2024-25 and 2025-26 are all backfilled under rule 2
(`atlas/owner/nhl_history.py`); the report it writes (``reports/nhl_puckline_fresh.{md,json}``) marks it scored,
and it is never scored again. Every constant below is the registration's.

From the sealed BettingPros closes: the market's probability of a side is the consensus close at +/-1.5 with its
margin out; the price is DraftKings' close for that side at the same handicap, else FanDuel's. Atlas's
probability is the stored game model's, walked forward unchanged. A game is a bet when Atlas rates its side
at least 5 points above the market. Aggregates only in the report: never a line or a price.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from atlas.live.probability import no_vig
from atlas.owner import nhl_history as hist
from atlas.util import get_logger

LOG = get_logger(__name__)

SEASONS = (2023, 2024, 2025)
THRESHOLD = 5.0
PRICE_BOOKS = (12, 10)                       # DraftKings, else FanDuel
MIN_GAMES = 300
MIN_BETS = 150
SHADE = 5.0
RESAMPLES = 10_000
SEED = 2026
ALPHA = 0.05


def report_path(root: Path) -> Path:
    return root / "reports" / "nhl_puckline_fresh.md"


def json_path(root: Path) -> Path:
    return root / "reports" / "nhl_puckline_fresh.json"


def ready(record: pd.DataFrame) -> bool:
    """All three seasons backfilled under rule 2 (or later)."""
    if record.empty:
        return False
    s = record[record["kind"] == "season"]
    done = {int(r.season) for r in s.itertuples()
            if str(r.status) == "done" and pd.to_numeric(r.rule, errors="coerce") >= hist.RULE}
    return set(SEASONS) <= done


def due(record: pd.DataFrame, root: Path) -> bool:
    """Scored once: when the seasons are all in and no report exists."""
    return ready(record) and not json_path(root).exists()


def payout(price: float) -> float:
    return price / 100.0 if price > 0 else 100.0 / -price


def shade(price: float, cents: float = SHADE) -> float:
    if price > 0:
        worse = price - cents
        return worse if worse >= 100 else -(200.0 - worse)
    return price - cents


def candidates(record: pd.DataFrame, walked: pd.DataFrame) -> pd.DataFrame:
    """One row per game of the three seasons with a consensus close at +/-1.5, a price at DraftKings or FanDuel
    and a result: Atlas's side, both probabilities of it, the disagreement, the price and how it settled, and
    whether any of its closes was taken at the off."""
    cols = ["game_id", "season", "side", "p_atlas", "p_market", "disagreement", "price", "book_id", "covered",
            "at_off"]
    c = record[(record["kind"] == "close") & (record["market"] == "spread")
               & pd.to_numeric(record["season"]).isin(SEASONS)].copy()
    if c.empty or walked.empty:
        return pd.DataFrame(columns=cols)
    c["book_id"] = pd.to_numeric(c["book_id"])
    c["line"] = pd.to_numeric(c["line"], errors="coerce")
    c["cost"] = pd.to_numeric(c["cost"], errors="coerce")
    c["off"] = c["source"].astype("string").fillna("pregame") == "at-off" if "source" in c else False
    w = walked.set_index("game_id")
    rows = []
    for game_id, part in c.groupby("game_id"):
        if int(game_id) not in w.index:
            continue
        cons = part[part["book_id"] == hist.bp.CONSENSUS]
        home, away = cons[cons["side"] == "home"], cons[cons["side"] == "away"]
        if home.empty or away.empty:
            continue
        hl = float(home["line"].iloc[0])
        if abs(abs(hl) - 1.5) > 1e-9 or abs(float(away["line"].iloc[0]) + hl) > 1e-9:
            continue
        pm_home = no_vig(float(home["cost"].iloc[0]), float(away["cost"].iloc[0]))
        if not math.isfinite(pm_home):
            continue
        g = w.loc[int(game_id)]
        pa_home = float(g["p_home_minus_1_5"]) if hl < 0 else 1.0 - float(g["p_away_minus_1_5"])
        is_home = pa_home >= pm_home
        side, side_line = ("home", hl) if is_home else ("away", -hl)
        price, book, off = None, None, bool(part.loc[cons.index, "off"].any())
        for b in PRICE_BOOKS:
            q = part[(part["book_id"] == b) & (part["side"] == side) & ((part["line"] - side_line).abs() < 1e-9)]
            if len(q) and pd.notna(q["cost"].iloc[0]):
                price, book = float(q["cost"].iloc[0]), b
                off = off or bool(q["off"].iloc[0])
                break
        if price is None:
            continue
        home_covers = float(g["margin"]) + hl > 0
        rows.append({"game_id": int(game_id), "season": int(part["season"].iloc[0]), "side": side,
                     "p_atlas": pa_home if is_home else 1.0 - pa_home,
                     "p_market": pm_home if is_home else 1.0 - pm_home,
                     "disagreement": 100.0 * ((pa_home - pm_home) if is_home else (pm_home - pa_home)),
                     "price": price, "book_id": book, "covered": home_covers == is_home, "at_off": off})
    return pd.DataFrame(rows, columns=cols)


def testable(cands: pd.DataFrame, record: pd.DataFrame, walked: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """The games the registration lets in: a season's closes at the off only where its moneyline closes at the off
    pass the market row's check; a season with fewer than :data:`MIN_GAMES` left, out. Returns (games, per
    season {games, at_off_left_out, excluded})."""
    cons = hist.home_probs(record, hist.bp.CONSENSUS).rename(columns={"p": "p_market"})
    checked = hist.at_off_check(cons.merge(walked[["game_id", "home_win"]], on="game_id", how="inner"))
    keep, notes = [], {}
    for season in SEASONS:
        part = cands[cands["season"] == season]
        ok = checked.get(season, (False, 0, float("nan")))[0]
        dropped = 0 if ok else int(part["at_off"].sum())
        part = part if ok else part[~part["at_off"]]
        excluded = len(part) < MIN_GAMES
        notes[season] = {"games": int(len(part)), "at_off_left_out": dropped, "excluded": bool(excluded)}
        if not excluded:
            keep.append(part)
    games = pd.concat(keep, ignore_index=True) if keep else cands.iloc[0:0]
    return games, notes


def bootstrap_lower(x: np.ndarray) -> float:
    if len(x) == 0:
        return float("nan")
    rng = np.random.default_rng(SEED)
    means = np.array([x[rng.integers(0, len(x), len(x))].mean() for _ in range(RESAMPLES)])
    return float(np.quantile(means, ALPHA / 2.0))


def score(games: pd.DataFrame, notes: dict) -> dict:
    bets = games[games["disagreement"] >= THRESHOLD].copy()
    bets["units"] = [payout(p) if c else -1.0 for p, c in zip(bets["price"], bets["covered"], strict=True)]
    bets["units_shaded"] = [payout(shade(p)) if c else -1.0 for p, c in zip(bets["price"], bets["covered"],
                                                                           strict=True)]
    beat = bets["covered"].astype(float).to_numpy() - bets["p_market"].to_numpy(float)
    scored = [s for s in SEASONS if not notes[s]["excluded"]]
    per = {s: {"bets": int((bets["season"] == s).sum()), "units": float(bets.loc[bets["season"] == s, "units"].sum())}
           for s in scored}
    up = sum(1 for s in scored if per[s]["units"] > 0)
    need = 2 if len(scored) == 3 else len(scored)
    result = {"threshold": THRESHOLD, "bets": int(len(bets)), "units": float(bets["units"].sum()),
              "per_bet": float(bets["units"].mean()) if len(bets) else float("nan"),
              "beat_market": float(beat.mean()) if len(beat) else float("nan"),
              "beat_lower": bootstrap_lower(beat), "units_shaded": float(bets["units_shaded"].sum()),
              "seasons_scored": scored, "seasons_up": up, "per_season": per, "notes": notes,
              "draftkings_share": float((bets["book_id"] == 12).mean()) if len(bets) else float("nan")}
    result["c1_units"] = result["units"] > 0
    result["c2_beats_market"] = bool(result["beat_lower"] > 0)
    result["c3_seasons"] = bool(scored) and up >= need
    result["c4_shaded"] = result["units_shaded"] > 0
    result["c5_bets"] = result["bets"] >= MIN_BETS
    result["real"] = all(result[k] for k in ("c1_units", "c2_beats_market", "c3_seasons", "c4_shaded", "c5_bets"))
    return result


def write(result: dict, root: Path) -> Path:
    json_path(root).write_text(json.dumps(result, indent=1, default=str) + "\n")
    yes = lambda ok: "yes" if ok else "**no**"  # noqa: E731
    lines = ["# NHL puck line: the fresh test on 2023-26", "",
             "Scored once by the heavy refresh, as `docs/NHL_PUCKLINE_FRESH_PREREGISTRATION.md` fixed it: the first "
             "test's puck-line rule at a 5-point threshold, the stored game model walked forward unchanged, the "
             "BettingPros consensus close at ±1.5 as the market (sealed, never in the clear), DraftKings' price "
             "(else FanDuel's). Aggregates only.", "",
             "| Criterion | Result | Met |", "|---|---|---|",
             f"| 1. Positive units | {result['units']:+.1f} on {result['bets']} bets ({result['per_bet']:+.1%} a bet) | "
             f"{yes(result['c1_units'])} |",
             f"| 2. Won minus the market's probability, 95% lower bound above zero | {result['beat_market']:+.1%} "
             f"(lower bound {result['beat_lower']:+.1%}) | {yes(result['c2_beats_market'])} |",
             f"| 3. Seasons up | {result['seasons_up']} of {len(result['seasons_scored'])} | {yes(result['c3_seasons'])} |",
             f"| 4. Positive units five cents worse | {result['units_shaded']:+.1f} | {yes(result['c4_shaded'])} |",
             f"| 5. At least {MIN_BETS} bets | {result['bets']} | {yes(result['c5_bets'])} |", "",
             ("**The puck line is real by the registration's bar.**" if result["real"] else
              "**The puck line does not clear its bar. There is no curated NHL play.**"), "",
             "| Season | Games tested | Bets | Units | Closes at the off left out | Scored |", "|---|---|---|---|---|---|"]
    for s in SEASONS:
        n = result["notes"][s]
        p = result["per_season"].get(s, {"bets": 0, "units": 0.0})
        lines.append(f"| {s}-{(s + 1) % 100:02d} | {n['games']} | {p['bets']} | {p['units']:+.1f} | "
                     f"{n['at_off_left_out']} | {'no (under 300 games)' if n['excluded'] else 'yes'} |")
    lines.append("")
    report_path(root).write_text("\n".join(lines))
    return report_path(root)


def run(record: pd.DataFrame, walked: pd.DataFrame, root: Path) -> Path | None:
    """Score the test once, if it is due. Never raises into the heavy run's step (the caller catches)."""
    if not due(record, root):
        return None
    games, notes = testable(candidates(record, walked), record, walked)
    result = score(games, notes)
    out = write(result, root)
    LOG.info("nhl puck line fresh test: %d bets, %s", result["bets"], "real" if result["real"] else "not real")
    return out
