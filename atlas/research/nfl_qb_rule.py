"""Pre-registered test: NFL totals in quarterback-change games.

    python -m atlas.research.nfl_qb_rule        # scores once, writes reports/nfl_qb_rule_test.md

Everything this scores is fixed in `docs/NFL_QB_RULE_PREREGISTRATION.md`,
committed before the first game was scored: the population (NFL regular
season, test seasons 2020-2025, the model's own walk-forward), the four
rules, the control, and the four criteria a rule must clear. Nothing here
is a parameter to tune; the constants are transcribed from that document
and a test pins them.

The flags are pre-kickoff by construction. The expected starter is the
depth chart's QB1 for the week, from the latest snapshot before kickoff,
unless the week's injury report lists him Out or Doubtful and a QB2 is
listed (`atlas.models.nfl_state.expected_starter`, unchanged). The previous
quarterback of record is the passer with the most dropbacks in the team's
previous game, which is over before this one starts.
"""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from atlas import config
from atlas.models import nfl_state as ns
from atlas.util import get_logger

LOG = get_logger(__name__)

#: docs/NFL_QB_RULE_PREREGISTRATION.md, "The criteria". Transcribed, never tuned.
TEST_SEASONS = (2020, 2021, 2022, 2023, 2024, 2025)
MIN_DECIDED = 100
BREAK_EVEN = 0.5238
Z = 2.24                        # 0.025 / 4 one-sided: four rules read, the best kept
SEASONS_ABOVE_HALF = 4


@dataclass(frozen=True)
class Rule:
    id: str
    label: str
    games: str                  # "change" | "injury" | "control"
    side: str                   # "atlas" | "under"


RULES = (
    Rule("Q1", "Change games, Atlas's side of the closing total", "change", "atlas"),
    Rule("Q2", "Change games, the under", "change", "under"),
    Rule("Q3", "QB1-out games, Atlas's side", "injury", "atlas"),
    Rule("Q4", "QB1-out games, the under", "injury", "under"),
)
CONTROL = Rule("control", "Neither change nor QB1-out, Atlas's side", "control", "atlas")


def flags(frame: pd.DataFrame) -> pd.DataFrame:
    """One row per game: ``change`` (either side's expected starter is not its previous quarterback of
    record), ``injury`` (either side's QB1 is listed Out or Doubtful), and each side's names for the report.

    ``frame`` is the NFL research frame, every game the warehouse has, so each team's previous game is
    found whether or not it carried a closing line. Only completed games can be a previous game.
    """
    if frame.empty:
        return pd.DataFrame(columns=["game_id", "change", "injury", "home_change", "away_change", "home_qb1_out",
                                     "away_qb1_out", "home_expected", "away_expected", "home_prev", "away_prev"])
    long = []
    for side in ("home", "away"):
        cols = {"game_id": frame["game_id"], "team_id": frame[f"{side}_team_id"],
                "kickoff": pd.to_datetime(frame["kickoff"], utc=True, errors="coerce"),
                "qb_of_record": frame.get(f"{side}_qb_id", pd.Series(pd.NA, index=frame.index)),
                "qb1": frame.get(f"{side}_qb1_id", pd.Series(pd.NA, index=frame.index)),
                "qb2": frame.get(f"{side}_qb2_id", pd.Series(pd.NA, index=frame.index)),
                "qb1_out": pd.to_numeric(frame.get(f"{side}_qb1_out", pd.Series(np.nan, index=frame.index)),
                                         errors="coerce"),
                "completed": frame["actual_total"].notna() if "actual_total" in frame else pd.Series(True, index=frame.index),
                "side": side}
        long.append(pd.DataFrame(cols))
    tg = pd.concat(long, ignore_index=True).dropna(subset=["team_id", "kickoff"]).sort_values(["team_id", "kickoff"])
    tg["expected"] = [ns.expected_starter(a, b, c) for a, b, c in zip(tg["qb1"], tg["qb2"], tg["qb1_out"], strict=True)]
    # The previous game's quarterback of record: the last completed game of the same team before this one.
    record = tg["qb_of_record"].where(tg["completed"].astype(bool))
    tg["prev"] = record.groupby(tg["team_id"]).shift(1)
    # A gap in the record (a game without a passer log) carries the last known one forward.
    tg["prev"] = tg.groupby("team_id")["prev"].ffill()
    known = tg["expected"].notna() & tg["prev"].notna()
    tg["change"] = known & (tg["expected"].astype("string") != tg["prev"].astype("string"))
    tg["injury"] = tg["qb1_out"] == 1.0
    out = frame[["game_id"]].copy()
    for side in ("home", "away"):
        s = tg[tg["side"] == side].set_index("game_id")
        out[f"{side}_change"] = out["game_id"].map(s["change"]).fillna(False).astype(bool)
        out[f"{side}_qb1_out"] = out["game_id"].map(s["injury"]).fillna(False).astype(bool)
        out[f"{side}_expected"] = out["game_id"].map(s["expected"])
        out[f"{side}_prev"] = out["game_id"].map(s["prev"])
    out["change"] = out["home_change"] | out["away_change"]
    out["injury"] = out["home_qb1_out"] | out["away_qb1_out"]
    return out.reset_index(drop=True)


def totals_walk_forward(frame: pd.DataFrame, *, choices=None, passers: pd.DataFrame | None = None,
                        players: pd.DataFrame | None = None) -> pd.DataFrame:
    """The NFL model's total against the closing total, one row per test-season game: Atlas's ``side``
    (over when its mean is above the line, under below; none when equal) and ``over`` (1 over, 0 under,
    0.5 push). The same walk-forward the card's grade is built from (`atlas.models.nfl_projection.history`)."""
    from atlas.models import nfl_total as nt

    scored, _, _ = nt.run(frame, first_test_season=min(TEST_SEASONS), choices=choices, passers=passers,
                          players=players)
    tot = scored[scored["model"] == "total"].dropna(subset=["over", "line", "mean"]).copy()
    tot = tot[tot["season_type"] == "regular"] if "season_type" in tot else tot
    tot = tot[tot["season"].isin(TEST_SEASONS)]
    mean, line = tot["mean"].to_numpy(dtype=float), tot["line"].to_numpy(dtype=float)
    tot["side"] = np.select([mean > line, mean < line], ["over", "under"], None)
    return tot[["game_id", "season", "week", "mean", "line", "over", "side"]].reset_index(drop=True)


def wilson_low(wins: int, n: int, z: float = Z) -> float:
    if n == 0:
        return float("nan")
    p = wins / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return centre - half


def select(rows: pd.DataFrame, rule: Rule) -> pd.DataFrame:
    """The games a rule takes and the side it takes, from the scored rows joined to their flags."""
    if rule.games == "change":
        picked = rows[rows["change"]]
    elif rule.games == "injury":
        picked = rows[rows["injury"]]
    else:
        picked = rows[~rows["change"] & ~rows["injury"]]
    if rule.side == "atlas":
        picked = picked[picked["side"].notna()]
        side = picked["side"].astype(str)
    else:
        side = pd.Series("under", index=picked.index)
    return picked.assign(taken=side)


def grade(picked: pd.DataFrame) -> pd.DataFrame:
    """``won`` per game: 1, 0, or 0.5 for a push."""
    over = picked["over"].to_numpy(dtype=float)
    taken_over = (picked["taken"] == "over").to_numpy()
    won = np.where(over == 0.5, 0.5, np.where(taken_over, over == 1.0, over == 0.0).astype(float))
    return picked.assign(won=won)


def record(graded: pd.DataFrame) -> dict:
    """Pooled and by-season counts, the win rate, its lower bound, and the verdict against the criteria."""
    by_season = {}
    for season, part in graded.groupby("season"):
        w, l_, p = int((part["won"] == 1).sum()), int((part["won"] == 0).sum()), int((part["won"] == 0.5).sum())
        by_season[int(season)] = {"wins": w, "losses": l_, "pushes": p,
                                  "rate": w / (w + l_) if w + l_ else float("nan")}
    wins = int((graded["won"] == 1).sum())
    losses = int((graded["won"] == 0).sum())
    pushes = int((graded["won"] == 0.5).sum())
    decided = wins + losses
    rate = wins / decided if decided else float("nan")
    low = wilson_low(wins, decided)
    above = sum(1 for s in by_season.values() if s["rate"] == s["rate"] and s["rate"] > 0.5)
    checks = {
        f"at least {MIN_DECIDED} decided": decided >= MIN_DECIDED,
        f"win rate above {BREAK_EVEN:.2%}": bool(decided) and rate > BREAK_EVEN,
        f"Wilson lower bound (z = {Z}) above 50%": bool(decided) and low > 0.5,
        f"above 50% in at least {SEASONS_ABOVE_HALF} of {len(TEST_SEASONS)} seasons": above >= SEASONS_ABOVE_HALF,
    }
    if all(checks.values()):
        verdict = "PASSES"
    elif checks[f"at least {MIN_DECIDED} decided"] and checks[f"win rate above {BREAK_EVEN:.2%}"] \
            and checks[f"above 50% in at least {SEASONS_ABOVE_HALF} of {len(TEST_SEASONS)} seasons"]:
        verdict = "a lead, not a result"
    else:
        verdict = "not shown"
    return {"wins": wins, "losses": losses, "pushes": pushes, "decided": decided, "rate": rate, "low": low,
            "seasons_above_half": above, "by_season": by_season, "checks": checks, "verdict": verdict}


def evaluate(scored: pd.DataFrame, game_flags: pd.DataFrame) -> dict[str, dict]:
    """Every rule and the control on the scored games."""
    rows = scored.merge(game_flags, on="game_id", how="left")
    for c in ("change", "injury"):
        rows[c] = rows[c].fillna(False).astype(bool)
    return {rule.id: {"rule": rule, **record(grade(select(rows, rule)))} for rule in (*RULES, CONTROL)}


def _pct(x: float) -> str:
    return "–" if x is None or not math.isfinite(x) else f"{x:.1%}"


def report(results: dict[str, dict], game_flags: pd.DataFrame, scored: pd.DataFrame) -> str:
    lines = ["# NFL quarterback rule: the pre-registered test", "",
             "`atlas/research/nfl_qb_rule.py`, scored once against `docs/NFL_QB_RULE_PREREGISTRATION.md`. "
             f"NFL regular season, test seasons {TEST_SEASONS[0]}-{TEST_SEASONS[-1]}, the NFL model's own walk-forward "
             "against the closing total. A rule passes only if it clears all four criteria fixed in advance; "
             "anything else is not shown.", "", "## Verdict", ""]
    for rid, r in results.items():
        if rid == "control":
            continue
        lines.append(f"- **{rid}, {r['rule'].label}: {r['verdict']}** - {r['wins']}-{r['losses']}-{r['pushes']}, "
                     f"{_pct(r['rate'])} of {r['decided']}, lower bound {_pct(r['low'])}, above 50% in "
                     f"{r['seasons_above_half']} of {len(TEST_SEASONS)} seasons.")
    c = results["control"]
    lines += ["", f"Control ({c['rule'].label}): {c['wins']}-{c['losses']}-{c['pushes']}, {_pct(c['rate'])} of "
              f"{c['decided']}.", "", "## The population", ""]
    flagged = scored.merge(game_flags, on="game_id", how="left")
    lines += ["| season | games with a closing total | change games | QB1-out games |", "|---|---|---|---|"]
    for season, part in flagged.groupby("season"):
        lines.append(f"| {int(season)} | {len(part)} | {int(part['change'].fillna(False).sum())} | "
                     f"{int(part['injury'].fillna(False).sum())} |")
    lines.append(f"| all | {len(flagged)} | {int(flagged['change'].fillna(False).sum())} | "
                 f"{int(flagged['injury'].fillna(False).sum())} |")
    lines += ["", "## Each rule, by season", ""]
    for rid, r in results.items():
        lines += [f"### {rid}: {r['rule'].label}", "", "| season | won-lost-push | win rate |", "|---|---|---|"]
        for season, s in sorted(r["by_season"].items()):
            lines.append(f"| {season} | {s['wins']}-{s['losses']}-{s['pushes']} | {_pct(s['rate'])} |")
        lines.append(f"| all | {r['wins']}-{r['losses']}-{r['pushes']} | {_pct(r['rate'])} |")
        lines += ["", "| criterion | met |", "|---|---|"]
        for name, ok in r["checks"].items():
            lines.append(f"| {name} | {'yes' if ok else 'no'} |")
        lines.append("")
    lines += ["## What was not tested", "",
              "Line movement (nflverse publishes the closing total only, so no opener and no CLV), a gap threshold "
              "on Atlas's side, Questionable as out, and spreads: each is named in the pre-registration as outside "
              "this test, and adding one after seeing these numbers would be tuning.", ""]
    return "\n".join(lines)


def run(paths=None) -> tuple[dict[str, dict], str]:
    """Score once from the NFL warehouse; return the results and the report text."""
    from atlas.models import nfl_projection as npj
    from atlas.research.nfl_dataset import load_nfl_frame, research_sample

    paths = paths or config.paths()
    full = load_nfl_frame(paths.warehouse)
    game_flags = flags(full)
    sample = research_sample(full)
    scored = totals_walk_forward(sample, choices=ns.load_choices(ns.choices_path(paths.root)),
                                 passers=npj._passers(paths), players=npj._players(paths))
    results = evaluate(scored, game_flags)
    for rid, r in results.items():
        LOG.info("%s: %s %d-%d-%d (%s)", rid, r["verdict"], r["wins"], r["losses"], r["pushes"], _pct(r["rate"]))
    return results, report(results, game_flags, scored)


def main() -> None:
    argparse.ArgumentParser(description="Score the pre-registered NFL quarterback rule test once").parse_args()
    paths = config.paths()
    _, text = run(paths)
    out = paths.reports / "nfl_qb_rule_test.md"
    out.write_text(text)
    print(text)
    LOG.info("wrote %s", out)


if __name__ == "__main__":
    main()
