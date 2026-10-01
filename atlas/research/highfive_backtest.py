"""The daily-plays backtest: what a top-N-a-day rule would have done on the walk-forward at the close.

    python -m atlas.research.highfive_backtest      # writes reports/highfive_backtest.md

Run once on 30 September 2026 to test the "Daily High Five" (the five best
wagers a day by expected value, every sport together) before its record began,
and the reason that rule was dropped for ``daily-v1``
(`docs/DAILY_PLAYS_PREREGISTRATION.md`). It reads ``tracking/calibration.csv``,
the current model's walk-forward against the closing line (football 2020-26,
the NHL 2013-22), so it changes when the model does.

What it can and cannot say. There is one price here, the close: -110 on
football, and on the NHL the market's fair probability with a 4.5% hold. The
live board's best-of-a-dozen-books price, and the choice at 10:00 ET rather
than the close, have no history and are not in it. Props have no history at
all. So it measures the model's side of the rule and nothing of the price's.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from atlas import config
from atlas.owner.board import edge_curve
from atlas.util import get_logger

LOG = get_logger(__name__)

DEC110 = 1.0 + 100.0 / 110.0
NHL_SHRINK = 0.46
NHL_HOLD = 0.045
FORM_WINDOW = 100
TOP = 5


def nfl_kickoffs() -> dict[str, str]:
    """NFL kickoffs from the nflverse schedule (the calibration rows carry none), by nflverse game id;
    empty when the schedule is not cached and cannot be fetched."""
    try:
        from atlas.sources import nflverse

        s = pd.read_parquet(nflverse.fetch_schedules(config.paths().raw, refresh=False))
    except Exception as error:  # noqa: BLE001 - the NFL is then left out and the report says so
        LOG.warning("nfl schedule not read (%s): NFL rows have no day and are left out", type(error).__name__)
        return {}
    k = pd.to_datetime(s["gameday"].astype(str) + " " + s["gametime"].fillna("13:00").astype(str), errors="coerce")
    k = k.dt.tz_localize("America/New_York", ambiguous="NaT", nonexistent="shift_forward").dt.tz_convert("UTC")
    return dict(zip(s["game_id"].astype(str), k.dt.strftime("%Y-%m-%dT%H:%M:%SZ"), strict=True))


def frame(calibration: pd.DataFrame, nfl: dict[str, str] | None = None) -> pd.DataFrame:
    """Every regular-season walk-forward row with a day, the market's fair probability of Atlas's side, the
    payout at the close, and the two valuations: ``p_A`` the model's own claim, ``p_B`` as the live board
    values a side (totals on the realised gap curve fitted to earlier seasons, the NHL shrunk toward the
    market by :data:`NHL_SHRINK`, spreads out)."""
    c = calibration[calibration["season_type"] == "regular"].dropna(subset=["abs_edge", "claimed", "won"]).copy()
    if nfl:
        c["kickoff"] = np.where(c["sport"] == "nfl", c["game_id"].astype(str).map(nfl), c["kickoff"])
    c["kick"] = pd.to_datetime(c["kickoff"], utc=True, format="ISO8601", errors="coerce")
    c = c.dropna(subset=["kick"]).sort_values("kick").reset_index(drop=True)
    c["day"] = c["kick"].dt.tz_convert("America/New_York").dt.strftime("%Y-%m-%d")
    fb = c["sport"] != "nhl"
    c["p_fair"] = np.where(fb, 0.5, c["claimed"] - c["abs_edge"] / 100)
    c["dec"] = np.where(fb, DEC110, 1.0 / (c["p_fair"] * (1 + NHL_HOLD)))
    c["p_A"] = c["claimed"]
    c["p_B"] = np.nan
    for sport in ("ncaaf", "nfl"):
        for season in sorted(c.loc[c["sport"] == sport, "season"].unique()):
            curve = edge_curve(c[(c["sport"] == sport) & (c["season"] < season)], sport)
            m = (c["sport"] == sport) & (c["season"] == season) & (c["market"] == "total")
            if curve is not None:
                c.loc[m, "p_B"] = [curve(g) for g in c.loc[m, "abs_edge"]]
    m = c["sport"] == "nhl"
    c.loc[m, "p_B"] = c.loc[m, "p_fair"] + NHL_SHRINK * (c.loc[m, "claimed"] - c.loc[m, "p_fair"])
    c["form"] = np.nan
    for _, part in c[c["won"] != 0.5].groupby(["sport", "market"]):
        c.loc[part.index, "form"] = (part["won"] == 1).astype(float).rolling(FORM_WINDOW, min_periods=FORM_WINDOW).mean().shift(1)
    return c


def wilson(wins: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return float("nan"), float("nan")
    p = wins / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return centre - half, centre + half


def top(c: pd.DataFrame, pcol: str, *, n: int = TOP, only_positive: bool = True, keep=None) -> pd.DataFrame:
    """The ``n`` best plays a day by expected value under ``pcol``, one a game, graded."""
    t = c.dropna(subset=[pcol]).copy()
    t["ev"] = t[pcol] * t["dec"] - 1
    if only_positive:
        t = t[t["ev"] > 0]
    if keep is not None:
        t = t[keep(t)]
    t = t.sort_values("ev", ascending=False, kind="stable").drop_duplicates(["day", "game_id"]).groupby("day").head(n)
    t["profit"] = np.where(t["won"] == 1, t["dec"] - 1, np.where(t["won"] == 0, -1.0, 0.0))
    return t


def summary(t: pd.DataFrame, pcol: str = "p_B") -> dict:
    d = t[t["won"] != 0.5]
    w = int((d["won"] == 1).sum())
    lo, hi = wilson(w, len(d))
    return {"plays": len(t), "days": int(t["day"].nunique()), "W-L": f"{w}-{len(d) - w}",
            "hit": f"{w / len(d):.1%}" if len(d) else "–", "95%": f"{lo:.0%}–{hi:.0%}" if len(d) else "–",
            "fair": f"{t['p_fair'].mean():.1%}" if len(t) else "–",
            "claimed": f"{d[pcol].mean():.1%}" if len(d) and pcol in d else "–",
            "units": f"{t['profit'].sum():+.0f}", "per play": f"{t['profit'].mean():+.1%}" if len(t) else "–"}


def quintiles(c: pd.DataFrame) -> pd.DataFrame:
    """Hit rate of Atlas's side by quintile of its disagreement with the close, per market."""
    d = c[c["won"] != 0.5]
    rows = {}
    for (sp, mk), part in d.groupby(["sport", "market"]):
        q = pd.qcut(part["abs_edge"].rank(method="first"), 5, labels=["1 (quietest)", "2", "3", "4", "5 (loudest)"])
        rows[f"{sp} {mk}"] = {str(k): f"{(v['won'] == 1).mean():.1%}" for k, v in part.groupby(q, observed=True)} | {
            "per quintile": len(part) // 5}
    return pd.DataFrame(rows).T


def phases(c: pd.DataFrame) -> pd.DataFrame:
    """The NHL favourite-side picks by phase of the season (weeks since the first puck drop): hit rate against
    the market's own probability, and units. The first-month row is the one registered as a label."""
    n = c[(c["sport"] == "nhl") & (c["won"] != 0.5) & (c["p_fair"] >= 0.5)].copy()
    n["phase"] = pd.cut(n["week"], [0, 4, 12, 20, 60], labels=["weeks 1-4", "weeks 5-12", "weeks 13-20", "week 21 on"])
    n["profit"] = np.where(n["won"] == 1, n["dec"] - 1, -1.0)
    rows = {}
    for k, p in n.groupby("phase", observed=True):
        w = int((p["won"] == 1).sum())
        lo, hi = wilson(w, len(p))
        edge = (p["won"] == 1).mean() - p["p_fair"].mean()
        rows[str(k)] = {"games": len(p), "hit": f"{w / len(p):.1%}", "95%": f"{lo:.0%}–{hi:.0%}",
                        "market fair": f"{p['p_fair'].mean():.1%}", "edge over fair": f"{100 * edge:+.1f} pt",
                        "units / 100": f"{100 * p['profit'].mean():+.1f}",
                        "seasons up": f"{int((p.groupby('season')['profit'].sum() > 0).sum())} of {p['season'].nunique()}"}
    return pd.DataFrame(rows).T


def _md(df: pd.DataFrame, index_name: str = "") -> str:
    cols = [index_name, *df.columns]
    lines = ["| " + " | ".join(str(c) for c in cols) + " |", "|" + "---|" * len(cols)]
    for idx, row in df.iterrows():
        lines.append("| " + " | ".join([str(idx), *(str(v) for v in row)]) + " |")
    return "\n".join(lines)


def _by(t: pd.DataFrame, keys: list[str], pcol: str) -> pd.DataFrame:
    return pd.DataFrame({" ".join(str(k) for k in key): summary(part, pcol) for key, part in t.groupby(keys)}).T


def report(c: pd.DataFrame, nfl_in: bool) -> str:
    fav = lambda t: (t["sport"] != "nhl") | (t["p_fair"] >= 0.5)  # noqa: E731
    variants = {
        "A. Model's own probability: spreads, totals, NHL": top(c, "p_A"),
        "B. As the live board values it: totals on the realised gap curve, NHL shrunk 0.46, no spreads": top(c, "p_B"),
        "B, padded to five every day": top(c, "p_B", only_positive=False),
        "B, NHL only on the side the market favours (daily-v1's NHL bar)": top(c, "p_B", keep=fav),
        "B, only when the market's last-100 form was 50% or better": top(c, "p_B", keep=lambda t: t["form"] >= 0.5),
        "B, only when it was below 50%": top(c, "p_B", keep=lambda t: t["form"] < 0.5),
    }
    nhl = c[(c["sport"] == "nhl") & (c["won"] != 0.5)].copy()
    nhl["side"] = np.where(nhl["p_fair"] >= 0.5, "Atlas's side is the favourite", "Atlas's side is the underdog")
    nhl["profit"] = np.where(nhl["won"] == 1, nhl["dec"] - 1, -1.0)
    sides = pd.DataFrame({k: {"games": len(p), "hit": f"{(p['won'] == 1).mean():.1%}", "market fair": f"{p['p_fair'].mean():.1%}",
                              "Atlas claimed": f"{p['claimed'].mean():.1%}", "units": f"{p['profit'].sum():+.0f}"}
                          for k, p in nhl.groupby("side")}).T
    n = c[c["sport"] == "nhl"].copy()
    n["ev"] = n["p_B"] * n["dec"] - 1
    atlas_fav = n[(n["ev"] > 0) & (n["p_fair"] >= 0.5)].sort_values("ev", ascending=False).groupby("day").head(TOP)
    chalk = n[n["p_fair"] >= 0.5].sort_values("p_fair", ascending=False).groupby("day").head(TOP)
    chalk = chalk[chalk["day"].isin(atlas_fav["day"])]
    for t in (atlas_fav, chalk):
        t["profit"] = np.where(t["won"] == 1, t["dec"] - 1, np.where(t["won"] == 0, -1.0, 0.0))
    control = pd.DataFrame({"Atlas-picked favourites": summary(atlas_fav), "The market's own top favourites, same days": summary(chalk)}).T
    base = c[c["won"] != 0.5].groupby(["sport", "market"]).apply(
        lambda d: pd.Series({"games": len(d), "hit": f"{(d['won'] == 1).mean():.1%}"}), include_groups=False)
    base.index = [" ".join(i) for i in base.index]
    out = ["# The daily-plays backtest", "",
           "`python -m atlas.research.highfive_backtest`. Top-N-a-day rules on `tracking/calibration.csv`, the current "
           "model's walk-forward against the closing line, every sport on one day together, one play a game, graded on "
           "the score. Run first on 30 September 2026 to test the Daily High Five before its record began; the reason it "
           "was dropped for rule `daily-v1` (`docs/DAILY_PLAYS_PREREGISTRATION.md`, `docs/DAILY_PLAYS.md`).", "",
           "**One price, the close.** -110 on football; on the NHL the market's fair probability with a "
           f"{NHL_HOLD:.1%} hold. The live board's best price across a dozen books, and choosing at 10:00 ET rather "
           "than the close, have no history and are not measured here. Props have no history at all." +
           ("" if nfl_in else " **The NFL is left out of this run: its schedule was not cached.**"), "",
           "## Every game at the close, Atlas's side", "", _md(base, "market"), "",
           "## Hit rate by how far Atlas disagrees with the close", "",
           "Quintiles of the disagreement within each market. Flat everywhere; the loudest NHL quintile is the worst. "
           "The size of Atlas's disagreement is not a ranking key.", "", _md(quintiles(c), "market"), "",
           "## The NHL by side", "",
           "When Atlas's side is the favourite it beats the market's own probability; when it is the underdog it "
           "overclaims and adds nothing.", "", _md(sides, "side"), "",
           f"The control: on the same days, the market's own top {TOP} favourites, no model.", "",
           _md(control, "rule"), "",
           "### The favourite side by phase of the season", "",
           "Weeks since the season's first puck drop. The first-month row was found after the fact, in the slicing "
           "that followed the backtest, and is registered as a label on the daily plays, never a filter "
           "(`docs/DAILY_PLAYS_PREREGISTRATION.md`).", "", _md(phases(c), "phase"), "",
           f"## Top {TOP} a day", ""]
    for name, t in variants.items():
        pcol = "p_A" if name.startswith("A") else "p_B"
        out += [f"### {name}", "", _md(pd.DataFrame({"all": summary(t, pcol)}).T, ""), "",
                _md(_by(t, ["sport", "market"], pcol), "market"), "",
                "<details><summary>By season</summary>", "", _md(_by(t, ["sport", "season"], pcol), "season"), "",
                "</details>", ""]
    out += ["## What it says", "",
            "- Ranking by expected value at the close and taking the loudest five lands at or below the base rate: "
            "the close is the close, and Atlas's biggest disagreements with it are slightly worse than its small ones.",
            "- Five positive-EV plays a day rarely exist at the close; the live valuation offers about 2.5. Padding to "
            "five costs about a point of hit rate.",
            "- The NHL favourite/underdog asymmetry is the one finding with a mechanism: the model overrates underdogs "
            "by about four points and prices favourites accurately. Restricting NHL plays to the market's favourite "
            "is `daily-v1`'s NHL bar; the Atlas-favourite picks beat the same days' chalk on units.",
            "- The form filter looked good and is not a rule: one of several things tried, driven by three NHL seasons, "
            "and it swings between NFL seasons. It is logged with each play as a label for the record to test.", ""]
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser(description="The daily-plays backtest")
    ap.add_argument("--out", type=Path, default=config.paths().root / "reports" / "highfive_backtest.md")
    args = ap.parse_args()
    from atlas.live.store import Store

    calibration = Store.open().read("calibration")
    nfl = nfl_kickoffs()
    c = frame(calibration, nfl)
    args.out.write_text(report(c, bool(nfl)))
    LOG.info("wrote %s (%d rows)", args.out, len(c))


if __name__ == "__main__":
    main()
