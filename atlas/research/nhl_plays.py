"""Step 9's test: the three rules docs/NHL_PLAYS_PREREGISTRATION.md fixed before any was scored, scored once.

    python -m atlas.research.nhl_plays     # reports/nhl_plays.{md,json}

Every constant below is the registration's, and none may change after the first run: a changed model or rule
is a new registration. The stored game model (``reports/nhl_model.json``) is walked forward unchanged; each game's
closing moneyline, total and puck line come from the archive; for each rule and test season the threshold is
chosen on the seasons before it only; the deciding seasons are 2020-21 to 2022-23, the descriptive 2014-15 to
2019-20.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from atlas import config
from atlas.live.probability import no_vig
from atlas.util import get_logger

LOG = get_logger(__name__)

RULES = ("M", "T", "P")
NAMES = {"M": "moneyline", "T": "total", "P": "puck line"}
GRID = (2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0)
MIN_TRAIN = 300
FIRST = 2013
DESCRIPTIVE = tuple(range(2014, 2020))
DECIDING = (2020, 2021, 2022)
MIN_BETS = 150
SHADE = 5.0
RESAMPLES = 10_000
SEED = 2026
ALPHA = 0.05 / 3
CANDIDATE_COLUMNS = ["game_id", "season", "rule", "side", "p_atlas", "p_market", "disagreement", "price", "outcome"]


def json_path(root: Path) -> Path:
    return root / "reports" / "nhl_plays.json"


def report_path(root: Path) -> Path:
    return root / "reports" / "nhl_plays.md"


# ---------------------------------------------------------------------------
# Prices and outcomes
# ---------------------------------------------------------------------------


def payout(price: float) -> float:
    """Profit on one unit at an American price."""
    return price / 100.0 if price > 0 else 100.0 / -price


def units(price: float, outcome: str) -> float:
    return {"win": payout(price), "loss": -1.0}.get(outcome, 0.0)


def shade(price: float, cents: float = SHADE) -> float:
    """The price ``cents`` worse, across even money the way a book's ladder runs (+102 five worse is -103)."""
    if price > 0:
        worse = price - cents
        return worse if worse >= 100 else -(200.0 - worse)
    return price - cents


# ---------------------------------------------------------------------------
# The candidates: each game's side of Atlas's disagreement in each market
# ---------------------------------------------------------------------------


def _total_probs(tcdf, line: float) -> tuple[float, float, float]:
    """(P over, P under, P push) at ``line`` from P(total <= t)."""
    cdf = np.asarray(tcdf, dtype=float)
    at = lambda t: float(cdf[min(max(int(t), 0), len(cdf) - 1)]) if t >= 0 else 0.0  # noqa: E731
    if float(line).is_integer():
        push = at(line) - at(line - 1)
        return 1.0 - at(line), at(line - 1), push
    return 1.0 - at(math.floor(line)), at(math.floor(line)), 0.0


def candidates(f: pd.DataFrame) -> pd.DataFrame:
    """One row per game and rule with the prices it needs: Atlas's side, both probabilities of it, the
    disagreement in points, the closing price of the side and how the side settled. ``f`` is the walked model
    with the grid (``p_home``, ``p_home_minus_1_5``, ``p_away_minus_1_5``, ``_tcdf``), the archive's closes and
    the final score."""
    rows = []
    for g in f.rename(columns={"_tcdf": "tcdf"}).itertuples():   # a leading underscore is lost there
        margin, total = float(g.home_score) - float(g.away_score), float(g.home_score) + float(g.away_score)
        base = {"game_id": g.game_id, "season": int(g.season)}
        # M: the moneyline, overtime and the shootout included.
        pm = no_vig(g.home_ml_close, g.away_ml_close)
        if math.isfinite(pm):
            home = float(g.p_home) >= pm
            rows.append({**base, "rule": "M", "side": "home" if home else "away",
                         "p_atlas": float(g.p_home) if home else 1.0 - float(g.p_home),
                         "p_market": pm if home else 1.0 - pm,
                         "price": float(g.home_ml_close if home else g.away_ml_close),
                         "outcome": "win" if (margin > 0) == home else "loss"})
        # T: the total at its closing line, a push set aside on both sides.
        pt = no_vig(g.over_close, g.under_close)
        if math.isfinite(pt) and pd.notna(g.total_close):
            line = float(g.total_close)
            over, under, push = _total_probs(g.tcdf, line)
            p_over = over / max(1e-9, 1.0 - push)
            is_over = p_over >= pt
            edge = (total - line) * (1.0 if is_over else -1.0)
            rows.append({**base, "rule": "T", "side": "over" if is_over else "under",
                         "p_atlas": p_over if is_over else 1.0 - p_over, "p_market": pt if is_over else 1.0 - pt,
                         "price": float(g.over_close if is_over else g.under_close),
                         "outcome": "win" if edge > 0 else ("loss" if edge < 0 else "push")})
        # P: the puck line, the home side's handicap as closed.
        pp = no_vig(g.home_pl_price, g.away_pl_price)
        if math.isfinite(pp) and pd.notna(g.home_pl) and abs(abs(float(g.home_pl)) - 1.5) < 1e-9:
            hl = float(g.home_pl)
            p_home_covers = float(g.p_home_minus_1_5) if hl < 0 else 1.0 - float(g.p_away_minus_1_5)
            home = p_home_covers >= pp
            covers = margin + hl > 0
            rows.append({**base, "rule": "P", "side": "home" if home else "away",
                         "p_atlas": p_home_covers if home else 1.0 - p_home_covers,
                         "p_market": pp if home else 1.0 - pp,
                         "price": float(g.home_pl_price if home else g.away_pl_price),
                         "outcome": "win" if covers == home else "loss"})
    out = pd.DataFrame(rows, columns=[c for c in CANDIDATE_COLUMNS if c != "disagreement"])
    out["disagreement"] = 100.0 * (out["p_atlas"] - out["p_market"])
    out["units"] = [units(p, o) for p, o in zip(out["price"], out["outcome"], strict=True)]
    out["units_shaded"] = [units(shade(p), o) for p, o in zip(out["price"], out["outcome"], strict=True)]
    return out.reindex(columns=[*CANDIDATE_COLUMNS, "units", "units_shaded"])


# ---------------------------------------------------------------------------
# The walk-forward
# ---------------------------------------------------------------------------


def choose(train: pd.DataFrame) -> float | None:
    """The threshold on :data:`GRID` with the most units at the closing price among those with at least
    :data:`MIN_TRAIN` bets; ties to the lower. None when none has enough."""
    best = None
    for t in GRID:
        bets = train[train["disagreement"] >= t]
        if len(bets) < MIN_TRAIN:
            continue
        total = float(bets["units"].sum())
        if best is None or total > best[1] + 1e-12:
            best = (t, total)
    return best[0] if best else None


def walk(cands: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Each rule's bets in each test season at the threshold chosen on the seasons before it. Returns (bets,
    thresholds)."""
    bets, chosen = [], []
    for rule in RULES:
        c = cands[cands["rule"] == rule]
        for season in (*DESCRIPTIVE, *DECIDING):
            t = choose(c[(c["season"] >= FIRST) & (c["season"] < season)])
            chosen.append({"rule": rule, "season": season, "threshold": t})
            if t is not None:
                bets.append(c[(c["season"] == season) & (c["disagreement"] >= t)].assign(threshold=t))
    b = pd.concat(bets, ignore_index=True) if bets else pd.DataFrame(columns=[*CANDIDATE_COLUMNS, "threshold"])
    return b, pd.DataFrame(chosen)


def bootstrap_lower(x: np.ndarray, alpha: float = ALPHA, resamples: int = RESAMPLES, seed: int = SEED) -> float:
    """The lower end of the two-sided 1 - ``alpha`` bootstrap interval of the mean."""
    x = np.asarray(x, dtype=float)
    if len(x) == 0:
        return float("nan")
    rng = np.random.default_rng(seed)
    means = np.array([x[rng.integers(0, len(x), len(x))].mean() for _ in range(resamples)])
    return float(np.quantile(means, alpha / 2.0))


def verdict(bets: pd.DataFrame) -> pd.DataFrame:
    """Each rule against the five criteria and the descriptive check."""
    rows = []
    for rule in RULES:
        b = bets[bets["rule"] == rule]
        deciding = b[b["season"].isin(DECIDING)]
        described = b[b["season"].isin(DESCRIPTIVE)]
        decided = deciding[deciding["outcome"] != "push"]
        beat = (decided["outcome"] == "win").astype(float).to_numpy() - decided["p_market"].to_numpy(float)
        per = deciding.groupby("season")["units"].sum()
        row = {"rule": rule, "market": NAMES[rule], "bets": int(len(deciding)),
               "units": float(deciding["units"].sum()),
               "per_bet": float(deciding["units"].mean()) if len(deciding) else float("nan"),
               "beat_market": float(beat.mean()) if len(beat) else float("nan"),
               "beat_lower": bootstrap_lower(beat) if len(beat) else float("nan"),
               "seasons_up": int((per > 0).sum()), "units_shaded": float(deciding["units_shaded"].sum()),
               "descriptive_bets": int(len(described)), "descriptive_units": float(described["units"].sum())}
        row["c1_units"] = row["units"] > 0
        row["c2_beats_market"] = bool(row["beat_lower"] > 0)
        row["c3_seasons"] = row["seasons_up"] >= 2
        row["c4_shaded"] = row["units_shaded"] > 0
        row["c5_bets"] = row["bets"] >= MIN_BETS
        row["descriptive_ok"] = row["descriptive_units"] >= 0
        row["real"] = all(row[k] for k in ("c1_units", "c2_beats_market", "c3_seasons", "c4_shaded", "c5_bets",
                                            "descriptive_ok"))
        rows.append(row)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# The frozen model walked, and the archive
# ---------------------------------------------------------------------------


def walked() -> pd.DataFrame:
    """The stored game model walked through every completed game, with its grid, the archive's closes and the
    final score."""
    from atlas.models import nhl_grid as grid
    from atlas.models import nhl_model, nhl_projection

    stored = nhl_projection.choices()
    if stored is None:
        raise SystemExit("no reports/nhl_model.json: run `make nhl-model` first")
    tables = nhl_model.load_tables()
    f, _, games = nhl_projection.walk(tables, stored)
    layers = grid.Layers.from_json(stored["layers"])
    f = f.merge(games[["game_id", "season", "season_type", "home_score", "away_score"]], on="game_id", how="left")
    f = f[f["season"].isin([s for s in layers.by_season if s >= FIRST])]
    f = nhl_model.with_grid(f, layers)
    odds = tables["odds"].dropna(subset=["game_id"])
    cols = ["game_id", "home_ml_close", "away_ml_close", "total_close", "over_close", "under_close", "home_pl",
            "home_pl_price", "away_pl_price"]
    return f.merge(odds[cols].assign(game_id=odds["game_id"].astype("int64")), on="game_id", how="inner")


def write_report(v: pd.DataFrame, bets: pd.DataFrame, chosen: pd.DataFrame, root: Path) -> Path:
    per = bets.groupby(["rule", "season"]).agg(bets=("units", "size"), units=("units", "sum"),
                                               threshold=("threshold", "first")).reset_index()
    json_path(root).write_text(json.dumps({"verdict": v.to_dict("records"), "by_season": per.to_dict("records"),
                                           "thresholds": chosen.to_dict("records")}, indent=1, default=str) + "\n")
    yes = lambda b: "yes" if b else "**no**"  # noqa: E731
    lines = ["# NHL curated plays: the pre-registered test (step 9)", "",
             "`python -m atlas.research.nhl_plays`, scoring `docs/NHL_PLAYS_PREREGISTRATION.md` once: the stored game "
             "model walked forward unchanged, each game's closing line from the archive, each threshold chosen on the "
             "seasons before the one it is used in. Deciding seasons 2020-21 to 2022-23 (the archive's part of it); "
             "descriptive 2014-15 to 2019-20.", "",
             "## The verdict", "",
             "| Rule | Bets | Units | Per bet | Won minus the market's P (98.3% lower bound) | Seasons up | "
             "Units five cents worse | 2014-20 units | Real |", "|---|---|---|---|---|---|---|---|---|"]
    for r in v.itertuples():
        lines.append(f"| {r.rule}, {r.market} | {r.bets}{'' if r.c5_bets else ' (**too few**)'} | "
                     f"{r.units:+.1f}{'' if r.c1_units else ' (**not positive**)'} | {r.per_bet:+.1%} | "
                     f"{r.beat_market:+.1%} ({r.beat_lower:+.1%}){'' if r.c2_beats_market else ' **not above zero**'} | "
                     f"{r.seasons_up} of 3 | {r.units_shaded:+.1f} | {r.descriptive_units:+.1f} "
                     f"({r.descriptive_bets} bets) | {yes(r.real)} |")
    real = v[v["real"]]
    lines += ["", ("**Real: " + ", ".join(f"{r.rule} ({r.market})" for r in real.itertuples()) + ".**") if len(real)
              else "**No rule clears its bar. There are no curated NHL plays.** The owner board's NHL picks (step 6) "
                   "are a different thing and stand on their own record.", "",
              "## By season", "", "| Rule | Season | Threshold | Bets | Units |", "|---|---|---|---|---|"]
    for r in per.itertuples():
        mark = "" if r.season in DECIDING else " (descriptive)"
        lines.append(f"| {r.rule} | {r.season}-{(r.season + 1) % 100:02d}{mark} | {r.threshold:g} | {r.bets} | "
                     f"{r.units:+.1f} |")
    lines.append("")
    report_path(root).write_text("\n".join(lines))
    return report_path(root)


def main() -> None:
    argparse.ArgumentParser(description="Step 9: the pre-registered NHL rules, scored once").parse_args()
    cands = candidates(walked())
    bets, chosen = walk(cands)
    v = verdict(bets)
    print(v.to_string())
    print(write_report(v, bets, chosen, config.paths().root))


if __name__ == "__main__":
    main()
