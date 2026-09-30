"""The NHL's score grid: regulation, the empty net, overtime (docs/MODEL_PLAN_NHL.md §5).

Three layers, each fitted on the three seasons before the one it prices (the
first three seasons on themselves: the burn-in), because the game's ending
has moved - empty-net goals went from 0.30 a game in 2010-11 to 0.55 by
2024-25 as goalies were pulled earlier and more often:

1. **The first 55 minutes.** Each side's goals are Poisson on its expected
   regulation goals (the state model's, net of the empty net) times the
   fitted share of them scored before 55:00 (more than 55/60: the last
   minutes, the empty net aside, score less), with the level scores inflated
   by a fitted factor: independent Poisson under-states them (a trailing side
   presses, a leading one sits back).
2. **The last five minutes.** Where the goalie is pulled, and the game's
   shape with it. An empirical table, fitted from the play-by-play: given the
   margin at 55:00, the joint distribution of the goals each side adds
   before the horn - the leader's empty-netters, the trailer's six-on-five
   goals, and ordinary ones. This is what moves one-goal games to two and
   three, and it is fitted, not assumed.
3. **Overtime.** A game level after sixty minutes goes to three-on-three and
   then the shootout: its winner scores exactly one more goal (the NHL's
   final score counts the shootout's). The home side's chance of winning it
   is fitted on the expected-goals gap, near 51/49.

From the final grid: P(home) including overtime, the regulation three-way,
P(overtime), the puck line both ways, the totals, the most probable scores.
Totals and the puck line are settled on the NHL's final score, shootout goal
included, as the books settle them.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy.stats import poisson

N = 13                      # goals 0..12 a side
LATE_SECONDS = 55 * 60
MAX_LATE = 3                # goals a side may add in the last five minutes, in the table
MARGINS = range(-3, 4)      # the margin at 55:00, from the home side, clipped
FIRST = 2010
WINDOW = 3


@dataclass
class Season:
    """One season's fitted layers."""

    late: dict[int, np.ndarray]                  # margin -> (MAX_LATE+1, MAX_LATE+1) P(dh, da)
    tie: float = 0.0                             # inflation of level scores at 55:00
    early: float = LATE_SECONDS / 3600.0         # goals before 55:00 per expected regulation goal
    stretch: float = 1.0                         # the expected-goals gap, widened (or narrowed) to fit outcomes
    ot_intercept: float = 0.04
    ot_slope: float = 0.0
    trained: tuple[int, ...] = ()

    def to_json(self) -> dict:
        return {"late": {str(k): v.round(6).tolist() for k, v in self.late.items()}, "tie": self.tie, "early": self.early,
                "stretch": self.stretch,
                "ot_intercept": self.ot_intercept, "ot_slope": self.ot_slope, "trained": list(self.trained)}

    @classmethod
    def from_json(cls, raw: dict) -> Season:
        return cls(late={int(k): np.asarray(v, float) for k, v in raw["late"].items()}, tie=float(raw["tie"]),
                   early=float(raw.get("early", LATE_SECONDS / 3600.0)), stretch=float(raw.get("stretch", 1.0)),
                   ot_intercept=float(raw["ot_intercept"]), ot_slope=float(raw["ot_slope"]),
                   trained=tuple(raw.get("trained", ())))


@dataclass
class Layers:
    """Each season's layers; a season not fitted borrows the latest before it."""

    by_season: dict[int, Season] = field(default_factory=dict)

    def get(self, season: int) -> Season:
        if season in self.by_season:
            return self.by_season[season]
        earlier = [s for s in self.by_season if s <= season]
        return self.by_season[max(earlier)] if earlier else self.by_season[min(self.by_season)]

    def to_json(self) -> dict:
        return {str(k): v.to_json() for k, v in sorted(self.by_season.items())}

    @classmethod
    def from_json(cls, raw: dict) -> Layers:
        return cls({int(k): Season.from_json(v) for k, v in raw.items()})


def training(season: int) -> tuple[int, ...]:
    if season < FIRST + WINDOW:
        return tuple(range(FIRST, FIRST + WINDOW))
    return tuple(range(season - WINDOW, season))


# ---------------------------------------------------------------------------
# Fitting
# ---------------------------------------------------------------------------


def score_at(goals: pd.DataFrame, games: pd.DataFrame, seconds: int = LATE_SECONDS) -> pd.DataFrame:
    """Each game's goals by side before ``seconds`` of regulation (the warehouse's ``goals`` table)."""
    g = games.set_index("game_id")
    goals = goals[goals["period"] <= 3].assign(home=lambda f: f["is_home"].astype(bool))
    early = goals[goals["seconds"] < seconds].groupby(["game_id", "home"]).size().unstack(fill_value=0)
    early = early.reindex(columns=[True, False], fill_value=0)
    out = pd.DataFrame({"h_at": early[True], "a_at": early[False]})
    return out.reindex(g.index).fillna(0).astype(int)


def _regular(games: pd.DataFrame, seasons) -> pd.DataFrame:
    return games[games["completed"].astype(bool) & games["season"].isin(seasons) & (games["season_type"] == "regular")]


def fit_late(at: pd.DataFrame, games: pd.DataFrame, seasons) -> dict[int, np.ndarray]:
    """P(home adds dh, away adds da in the last five minutes | the margin at 55:00)."""
    g = _regular(games, seasons).set_index("game_id").join(at, how="inner")
    dh = (g["reg_home"] - g["h_at"]).clip(0, MAX_LATE).astype(int)
    da = (g["reg_away"] - g["a_at"]).clip(0, MAX_LATE).astype(int)
    m = (g["h_at"] - g["a_at"]).clip(min(MARGINS), max(MARGINS))
    table = {}
    for margin in MARGINS:
        part = (m == margin)
        counts = np.ones((MAX_LATE + 1, MAX_LATE + 1)) * 0.5                   # a half-count floor
        np.add.at(counts, (dh[part].to_numpy(), da[part].to_numpy()), 1.0)
        table[margin] = counts / counts.sum()
    return table


def early_grid(lh: float, la: float, tie: float, early: float = LATE_SECONDS / 3600.0) -> np.ndarray:
    k = np.arange(N)
    out = np.outer(poisson.pmf(k, lh * early), poisson.pmf(k, la * early))
    out[np.diag_indices(N)] *= 1.0 + tie
    return out / out.sum()


def fit_early(at: pd.DataFrame, games: pd.DataFrame, lam: pd.DataFrame, seasons) -> float:
    """Goals before 55:00 per expected regulation goal (more than 55/60: the last minutes, the empty net
    aside, score less than the rest)."""
    g = _regular(games, seasons).set_index("game_id").join(at, how="inner").join(lam, how="inner")
    if g.empty:
        return LATE_SECONDS / 3600.0
    return float((g["h_at"].sum() + g["a_at"].sum()) / (g["lambda_home"].sum() + g["lambda_away"].sum()))


def fit_tie(at: pd.DataFrame, games: pd.DataFrame, lam: pd.DataFrame, seasons, early: float) -> float:
    """The inflation of level scores at 55:00 that makes the model's share of them the observed share."""
    g = _regular(games, seasons).set_index("game_id").join(at, how="inner").join(lam, how="inner")
    if g.empty:
        return 0.0
    observed = float((g["h_at"] == g["a_at"]).mean())
    k = np.arange(N)
    ph = poisson.pmf(k[None, :], g["lambda_home"].to_numpy()[:, None] * early)
    pa = poisson.pmf(k[None, :], g["lambda_away"].to_numpy()[:, None] * early)
    base = (ph * pa).sum(axis=1)

    def share(t: float) -> float:
        return float(np.mean(base * (1 + t) / (1 + t * base)))

    lo, hi = -0.5, 2.0
    for _ in range(50):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if share(mid) < observed else (lo, mid)
    return (lo + hi) / 2


def stretched(lh, la, s: float, edge=0.0):
    """The two sides' expected goals with the teams' gap times ``s`` and their sum kept. ``edge`` is the home
    side's home-ice goals: fitted on its own, it is taken out before the stretch and put back after."""
    lh, la, edge = np.asarray(lh, float) - np.asarray(edge, float), np.asarray(la, float), np.asarray(edge, float)
    mid, half = (lh + la) / 2.0, (lh - la) / 2.0
    return np.maximum(mid + s * half + edge, 0.05), np.maximum(mid - s * half, 0.05)


def p_home_fast(lh, la, layer: Season) -> np.ndarray:
    """P(home wins) for many games at once: the early margin (Poisson, level scores inflated) convolved
    with the last five minutes' change in margin, a level game settled by the overtime model. The same
    number :func:`summary` reads from the full grid, without building it."""
    lh, la = np.asarray(lh, float), np.asarray(la, float)
    k = np.arange(N)
    ph = poisson.pmf(k[None, :], lh[:, None] * layer.early)
    pa = poisson.pmf(k[None, :], la[:, None] * layer.early)
    joint = ph[:, :, None] * pa[:, None, :]
    idx = np.arange(N)
    joint[:, idx, idx] *= 1.0 + layer.tie
    joint /= joint.sum(axis=(1, 2), keepdims=True)
    diff = (idx[:, None] - idx[None, :]).ravel() + (N - 1)
    early = np.zeros((len(lh), 2 * N - 1))
    for j in range(2 * N - 1):
        early[:, j] = joint.reshape(len(lh), -1)[:, diff == j].sum(axis=1)
    # The last five minutes' change in margin, given the margin: a distribution over -MAX_LATE..MAX_LATE.
    change = {}
    for m, table in layer.late.items():
        d = np.zeros(2 * MAX_LATE + 1)
        for dh in range(MAX_LATE + 1):
            for da in range(MAX_LATE + 1):
                d[dh - da + MAX_LATE] += table[dh, da]
        change[m] = d
    win = np.zeros(len(lh))
    level = np.zeros(len(lh))
    for j in range(2 * N - 1):
        m = j - (N - 1)
        d = change[int(np.clip(m, min(MARGINS), max(MARGINS)))]
        for c in range(2 * MAX_LATE + 1):
            final_m = m + c - MAX_LATE
            if final_m > 0:
                win += early[:, j] * d[c]
            elif final_m == 0:
                level += early[:, j] * d[c]
    ot = 1.0 / (1.0 + np.exp(-(layer.ot_intercept + layer.ot_slope * (lh - la))))
    return win + ot * level


def fit_stretch(games: pd.DataFrame, lam: pd.DataFrame, seasons, layer: Season) -> float:
    """The widening of the teams' expected-goals gap that maximises the likelihood of who won over
    ``seasons``, through the season's own late-game and overtime layers."""
    g = _regular(games, seasons).set_index("game_id").join(lam, how="inner")
    if len(g) < 200:
        return 1.0
    y = (g["home_score"] > g["away_score"]).to_numpy(float)
    edge = g["home_edge"] if "home_edge" in g else 0.0
    best, best_ll = 1.0, -np.inf
    for s in np.arange(0.8, 2.01, 0.05):
        lh, la = stretched(g["lambda_home"], g["lambda_away"], s, edge)
        p = np.clip(p_home_fast(lh, la, layer), 1e-6, 1 - 1e-6)
        ll = float(np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))
        if ll > best_ll:
            best, best_ll = float(s), ll
    return best


def fit_overtime(games: pd.DataFrame, lam: pd.DataFrame, seasons) -> tuple[float, float]:
    """Logistic P(home wins overtime or the shootout) on the expected-goals gap (home minus away)."""
    from sklearn.linear_model import LogisticRegression

    g = _regular(games, seasons)
    g = g[g["decision"].isin(["OT", "SO"])].set_index("game_id").join(lam, how="inner")
    if len(g) < 50:
        return 0.04, 0.0
    x = (g["lambda_home"] - g["lambda_away"]).to_numpy(float).reshape(-1, 1)
    y = (g["home_score"] > g["away_score"]).to_numpy(int)
    model = LogisticRegression(C=1.0).fit(x, y)
    return float(model.intercept_[0]), float(model.coef_[0][0])


def fit(goals: pd.DataFrame, games: pd.DataFrame, lam: pd.DataFrame, seasons) -> Layers:
    """Each season's layers from the three before it. ``lam`` holds each game's pre-game expected regulation
    goals (``lambda_home``, ``lambda_away``), indexed by ``game_id``."""
    at = score_at(goals, games[games["completed"].astype(bool)])
    out = {}
    for season in sorted(set(int(s) for s in seasons)):
        train = training(season)
        if not set(train) & set(games["season"].unique()):
            continue
        icpt, slope = fit_overtime(games, lam, train)
        early = fit_early(at, games, lam, train)
        tie = fit_tie(at, games, lam, train, early)
        layer = Season(late=fit_late(at, games, train), tie=tie, early=early, ot_intercept=icpt, ot_slope=slope,
                       trained=train)
        layer.stretch = fit_stretch(games, lam, train, layer)
        out[season] = layer
    return Layers(out)


# ---------------------------------------------------------------------------
# The grid
# ---------------------------------------------------------------------------


def regulation(lh: float, la: float, layer: Season) -> np.ndarray:
    """P(regulation ends home h, away a), an N x N matrix."""
    early = early_grid(lh, la, layer.tie, layer.early)
    out = np.zeros((N, N))
    for h in range(N):
        for a in range(N):
            p = early[h, a]
            if p < 1e-12:
                continue
            table = layer.late[int(np.clip(h - a, min(MARGINS), max(MARGINS)))]
            hi, ai = min(MAX_LATE, N - 1 - h), min(MAX_LATE, N - 1 - a)
            out[h:h + hi + 1, a:a + ai + 1] += p * table[:hi + 1, :ai + 1]
    return out / out.sum()


def p_overtime_home(lh: float, la: float, layer: Season) -> float:
    return float(1.0 / (1.0 + np.exp(-(layer.ot_intercept + layer.ot_slope * (lh - la)))))


def final(reg: np.ndarray, p_ot_home: float) -> np.ndarray:
    """The final score: a level game goes to overtime, and its winner scores one more."""
    out = reg.copy()
    tie = np.diag(reg).copy()
    np.fill_diagonal(out, 0.0)
    idx = np.arange(N - 1)
    out[idx + 1, idx] += p_ot_home * tie[:-1]
    out[idx, idx + 1] += (1.0 - p_ot_home) * tie[:-1]
    return out


def summary(lh: float, la: float, layer: Season, lines=(5.5, 6.5), edge: float = 0.0) -> dict:
    """What a card and the board read from one game's grid. ``edge`` is the home side's home-ice goals."""
    sh, sa = stretched(lh, la, layer.stretch, edge)
    lh, la = float(sh), float(sa)
    reg = regulation(lh, la, layer)
    p_ot = p_overtime_home(lh, la, layer)
    fin = final(reg, p_ot)
    h, a = np.meshgrid(np.arange(N), np.arange(N), indexing="ij")
    margin, total = h - a, h + a
    out = {
        "lambda_home": lh, "lambda_away": la,
        "p_home": float(fin[margin > 0].sum()),
        "p_reg_home": float(reg[margin > 0].sum()), "p_reg_away": float(reg[margin < 0].sum()),
        "p_ot": float(np.trace(reg)), "p_ot_home": p_ot,
        "home_mean": float((fin * h).sum()), "away_mean": float((fin * a).sum()),
        "p_home_minus_1_5": float(fin[margin >= 2].sum()), "p_away_minus_1_5": float(fin[margin <= -2].sum()),
    }
    out["total_mean"] = out["home_mean"] + out["away_mean"]
    for line in lines:
        out[f"p_over_{line}"] = float(fin[total > line].sum())
    flat = np.argsort(fin, axis=None)[::-1][:3]
    out["top"] = [(int(i // N), int(i % N), float(fin.flat[i])) for i in flat]
    out["grid"] = fin
    return out


def total_cdf(fin: np.ndarray) -> np.ndarray:
    """P(total <= t) for t = 0 .. 2N-2."""
    h, a = np.meshgrid(np.arange(N), np.arange(N), indexing="ij")
    return np.cumsum(np.bincount((h + a).ravel(), weights=fin.ravel(), minlength=2 * N - 1))


def margin_cdf(fin: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(margins, P(margin <= m)) from the home side."""
    h, a = np.meshgrid(np.arange(N), np.arange(N), indexing="ij")
    m = (h - a).ravel() + (N - 1)
    pmf = np.bincount(m, weights=fin.ravel(), minlength=2 * N - 1)
    return np.arange(-(N - 1), N), np.cumsum(pmf)
