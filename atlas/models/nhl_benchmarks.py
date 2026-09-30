"""The numbers the NHL model has to beat, walk-forward: naive, Elo, a goals-based Poisson team model, the market.

    python -m atlas.models.nhl_benchmarks     # reports/nhl_benchmarks.md

Step 2 of `docs/MODEL_PLAN_NHL.md`. Every forecast is P(the home side wins,
overtime and shootout included), made before puck drop from games already
played, and scored by Brier and log loss:

* **naive** - the home side's win rate over the seasons before;
* **Elo** - FiveThirtyEight's form (`atlas/models/elo.py`), its K, home
  advantage and summer reversion tuned on 2010-11 to 2016-17 by log loss;
* **goals-Poisson** - each team's goals for and against as exponentially
  weighted rates, regressed each summer, into a Poisson score grid; a tie
  after regulation is settled at the home side's measured overtime rate;
* **market** - the archive's closing moneyline without its margin
  (2010-11 to 2021-22).

The plan fits on 2010-11 to 2016-17, tunes on 2017-18 to 2019-20 and
reports 2020-21 on. Its success table is scored on the games the market
has a line for, 2010-22 pooled and 2021-22 alone.
"""

from __future__ import annotations

import argparse
import itertools
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import poisson

from atlas import config
from atlas.models import elo
from atlas.util import get_logger

LOG = get_logger(__name__)

FIT = range(2010, 2017)
TUNE = range(2017, 2020)
REPORT_FROM = 2020
#: The home side's share of overtimes and shootouts (plan §3: 51.0% and 51.6%, 2015-26).
OT_HOME = 0.51
MAX_GOALS = 12


def report_path(root: Path) -> Path:
    return root / "reports" / "nhl_benchmarks.md"


def brier(p, y) -> float:
    p, y = np.asarray(p, float), np.asarray(y, float)
    return float(np.mean((p - y) ** 2))


def log_loss(p, y) -> float:
    p = np.clip(np.asarray(p, float), 1e-6, 1 - 1e-6)
    y = np.asarray(y, float)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def home_won(games: pd.DataFrame) -> pd.Series:
    """1 when the home side won, overtime and shootout included (the NHL's final score says so)."""
    return (games["home_score"] > games["away_score"]).astype(float).where(games["completed"].astype(bool))


# ---------------------------------------------------------------------------
# Naive
# ---------------------------------------------------------------------------


def naive(games: pd.DataFrame) -> pd.Series:
    """The home win rate over every regular season before the game's (2010-11: the plan's 53.7%)."""
    y = home_won(games)
    reg = games["season_type"] == "regular"
    rate = y[reg].groupby(games.loc[reg, "season"]).agg(["sum", "count"])
    cum = rate.cumsum().shift(1)
    by_season = (cum["sum"] / cum["count"]).fillna(0.537)
    return games["season"].map(by_season).fillna(float(by_season.iloc[-1]) if len(by_season) else 0.537)


# ---------------------------------------------------------------------------
# Elo
# ---------------------------------------------------------------------------


def elo_forecast(games: pd.DataFrame, params: elo.Params) -> pd.Series:
    """P(home) from pregame Elo. A shootout is a win: the update reads the NHL's final margin."""
    g = games.assign(actual_margin=(games["home_score"] - games["away_score"]).where(games["completed"].astype(bool)),
                     neutral_site=0)
    e = elo.pregame(g, params)
    diff = e["home_elo"] - e["away_elo"] + params.home_field
    return 1.0 / (1.0 + 10.0 ** (-diff / 400.0))


def tune_elo(games: pd.DataFrame, seasons=FIT) -> elo.Params:
    y = home_won(games)
    mask = games["season"].isin(seasons) & games["season"].gt(min(seasons)) & y.notna()
    best, best_loss = None, np.inf
    for k, hfa, revert in itertools.product((4.0, 6.0, 8.0, 10.0, 12.0), (20.0, 30.0, 40.0, 50.0),
                                           (0.3, 0.5, 0.7)):
        p = elo.Params(k=k, home_field=hfa, mean=1505.0, revert=revert)
        loss = log_loss(elo_forecast(games, p)[mask], y[mask])
        if loss < best_loss:
            best, best_loss = p, loss
    return best


# ---------------------------------------------------------------------------
# Goals-based Poisson team model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PoissonParams:
    alpha: float = 0.04        # weight of each new game in a team's rate
    carry: float = 0.6         # share of a team's summer rating carried into the new season
    home: float = 1.04         # multiplicative home edge on goals


def grid_probabilities(lh: np.ndarray, la: np.ndarray, ot_home: float = OT_HOME) -> np.ndarray:
    """P(home wins) from independent Poisson regulation goals, a tie settled at ``ot_home``."""
    k = np.arange(MAX_GOALS + 1)
    ph = poisson.pmf(k[None, :], lh[:, None])
    pa = poisson.pmf(k[None, :], la[:, None])
    cdf_a = np.cumsum(pa, axis=1)
    win = (ph[:, 1:] * cdf_a[:, :-1]).sum(axis=1)
    tie = (ph * pa).sum(axis=1)
    return win + ot_home * tie


def poisson_forecast(games: pd.DataFrame, params: PoissonParams) -> pd.DataFrame:
    """Walk-forward attack and defence rates (relative to the league) and each game's expected goals."""
    g = games.sort_values(["kickoff", "game_id"])
    att: dict = {}
    dfn: dict = {}
    league = 3.0
    out_h, out_a = np.full(len(g), np.nan), np.full(len(g), np.nan)
    last_season = None
    reg_h = pd.to_numeric(g["reg_home"], errors="coerce").to_numpy()
    reg_a = pd.to_numeric(g["reg_away"], errors="coerce").to_numpy()
    days = pd.to_datetime(g["kickoff"], utc=True).dt.date.to_numpy()
    seasons, homes, aways = g["season"].to_numpy(), g["home_team"].to_numpy(), g["away_team"].to_numpy()
    i = 0
    while i < len(g):
        j = i
        while j < len(g) and days[j] == days[i]:
            j += 1
        if seasons[i] != last_season:
            for t in att:
                att[t] = 1.0 + params.carry * (att[t] - 1.0)
                dfn[t] = 1.0 + params.carry * (dfn[t] - 1.0)
            last_season = seasons[i]
        for r in range(i, j):
            h, a = homes[r], aways[r]
            out_h[r] = league * att.get(h, 1.0) * dfn.get(a, 1.0) * params.home
            out_a[r] = league * att.get(a, 1.0) * dfn.get(h, 1.0) / params.home
        for r in range(i, j):
            if np.isnan(reg_h[r]):
                continue
            h, a = homes[r], aways[r]
            league = 0.998 * league + 0.002 * (reg_h[r] + reg_a[r]) / 2.0
            att[h] = (1 - params.alpha) * att.get(h, 1.0) + params.alpha * reg_h[r] / (league * dfn.get(a, 1.0))
            att[a] = (1 - params.alpha) * att.get(a, 1.0) + params.alpha * reg_a[r] / (league * dfn.get(h, 1.0))
            dfn[h] = (1 - params.alpha) * dfn.get(h, 1.0) + params.alpha * reg_a[r] / (league * att.get(a, 1.0))
            dfn[a] = (1 - params.alpha) * dfn.get(a, 1.0) + params.alpha * reg_h[r] / (league * att.get(h, 1.0))
        i = j
    out = pd.DataFrame({"lambda_home": out_h, "lambda_away": out_a}, index=g.index).reindex(games.index)
    out["p_home"] = grid_probabilities(out["lambda_home"].to_numpy(), out["lambda_away"].to_numpy())
    return out


def tune_poisson(games: pd.DataFrame, seasons=FIT) -> PoissonParams:
    y = home_won(games)
    mask = games["season"].isin(seasons) & games["season"].gt(min(seasons)) & y.notna()
    best, best_loss = None, np.inf
    for alpha, carry, home in itertools.product((0.02, 0.03, 0.05, 0.08), (0.4, 0.6, 0.8), (1.03, 1.045, 1.06)):
        p = PoissonParams(alpha=alpha, carry=carry, home=home)
        loss = log_loss(poisson_forecast(games, p)["p_home"][mask], y[mask])
        if loss < best_loss:
            best, best_loss = p, loss
    return best


# ---------------------------------------------------------------------------
# The market
# ---------------------------------------------------------------------------


def implied(ml) -> np.ndarray:
    """An American price's implied probability, margin included."""
    ml = np.asarray(ml, float)
    fav = ml < 0
    out = np.full(ml.shape, np.nan)
    out[fav] = -ml[fav] / (100.0 - ml[fav])
    out[~fav] = 100.0 / (ml[~fav] + 100.0)
    return out


def market(games: pd.DataFrame, odds: pd.DataFrame) -> pd.Series:
    """The closing moneyline's P(home) without its margin, where the archive has both prices."""
    o = odds.dropna(subset=["home_ml_close", "away_ml_close"]).drop_duplicates("game_id").set_index("game_id")
    ph, pa = implied(o["home_ml_close"]), implied(o["away_ml_close"])
    p = pd.Series(ph / (ph + pa), index=o.index)
    return games["game_id"].map(p)


# ---------------------------------------------------------------------------
# The table
# ---------------------------------------------------------------------------


def forecasts(games: pd.DataFrame, odds: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    g = games[games["season_type"].isin(["regular", "postseason"])].sort_values(["kickoff", "game_id"]).reset_index(
        drop=True)
    elo_params = tune_elo(g)
    pois_params = tune_poisson(g)
    out = g[["game_id", "season", "season_type", "kickoff", "home_team", "away_team", "completed"]].copy()
    out["y"] = home_won(g)
    out["naive"] = naive(g)
    out["elo"] = elo_forecast(g, elo_params)
    pf = poisson_forecast(g, pois_params)
    out["poisson"] = pf["p_home"]
    out["lambda_home"], out["lambda_away"] = pf["lambda_home"], pf["lambda_away"]
    out["market"] = market(g, odds) if len(odds) else np.nan
    return out, {"elo": elo_params, "poisson": pois_params}


ORDER = ("naive", "elo", "poisson", "market")


def score(f: pd.DataFrame, mask: pd.Series) -> dict:
    part = f[mask & f["y"].notna()]
    return {m: (brier(part[m], part["y"]), log_loss(part[m], part["y"]), len(part)) for m in ORDER
            if part[m].notna().all() and len(part)}


def table(f: pd.DataFrame) -> list[tuple[str, dict]]:
    reg = f["season_type"] == "regular"
    has_market = f["market"].notna()
    # The plan's success table counts every game with a closing line, the playoffs included.
    rows = [("Pooled 2010-22, games with a closing line", score(f, has_market & f["season"].between(2010, 2021))),
            ("2021-22, games with a closing line", score(f, has_market & (f["season"] == 2021))),
            ("Tuning window 2017-20, all games", score(f, reg & f["season"].isin(TUNE))),
            (f"Reported {REPORT_FROM}-26, all games (no market beyond 2021-22)",
             score(f.assign(market=np.nan), reg & (f["season"] >= REPORT_FROM) & (f["season"] <= 2025)))]
    for s in range(REPORT_FROM, 2026):
        rows.append((f"{s}-{str(s + 1)[-2:]}", score(f.assign(market=np.where(f["season"] <= 2021, f["market"], np.nan))
                                                      if s > 2021 else f, reg & (f["season"] == s)
                                                      & (has_market if s <= 2021 else True))))
    return rows


def write_report(f: pd.DataFrame, params: dict, root: Path) -> Path:
    lines = ["# NHL benchmarks (step 2)", "",
             "Generated by `python -m atlas.models.nhl_benchmarks`. P(home wins, overtime and shootout included), "
             "made before puck drop from games already played. Brier, then log loss, then games; lower is better.",
             "", f"Elo tuned on 2010-11 to 2016-17: K {params['elo'].k:g}, home advantage {params['elo'].home_field:g} "
             f"Elo points, {params['elo'].revert:.0%} of the way back to the mean each summer. Goals-Poisson tuned on "
             f"the same seasons: each game {params['poisson'].alpha:g} of a team's rate, {params['poisson'].carry:.0%} "
             f"carried over a summer, home goals x{params['poisson'].home:g}.", "",
             "| Window | " + " | ".join(ORDER) + " |", "|---|" + "---|" * len(ORDER)]
    for label, s in table(f):
        cells = [f"{s[m][0]:.4f} / {s[m][1]:.4f} ({s[m][2]:,})" if m in s else "—" for m in ORDER]
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    out = report_path(root)
    out.write_text("\n".join(lines) + "\n")
    return out


def main() -> None:
    argparse.ArgumentParser(description="Score the NHL benchmarks walk-forward").parse_args()
    from atlas.staging.nhl import build as nhl_build

    games = nhl_build.load("games")
    odds = nhl_build.load("odds")
    f, params = forecasts(games, odds)
    print(write_report(f, params, config.paths().root))


if __name__ == "__main__":
    main()
