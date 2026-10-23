"""Atlas's NBA player projections: points, rebounds, assists and threes, walk-forward (docs/MODEL_PLAN_NBA.md, step 7).

    python -m atlas.models.nba_props              # walk forward with the saved spec -> reports/nba_props.md
    python -m atlas.models.nba_props --tune       # tune the half-lives first, and save them
    python -m atlas.models.nba_props --publish    # the snapshot the pricing reads, as of now

A prop is a count: what a player records in a game. Each one is projected
as **minutes times a rate times the game**:

* **minutes**: his exponentially weighted minutes over the games he played
  (a night he did not dress is an absence, not a quiet night);
* **rate**: his exponentially weighted per-minute rate of the stat, shrunk
  toward his position's league rate by a prior worth :attr:`Spec.k_rate`
  minutes;
* **the game**: a Poisson layer fitted a season at a time on the three
  seasons before it, on the player's base expectation: home, the opponent's
  rate allowed of that stat, and the pace both teams play at.

The distribution around the expectation is a negative binomial whose
dispersion is fitted beside the layer (`atlas/models/nhl_props.py` holds
the shapes; they are the NHL's, reused). Scored walk-forward against a
Poisson on the player's season mean so far, at the common lines, by Brier
and log loss; the half-lives tuned once, on 2018-19 to 2020-21, by the
log-likelihood of the counts.

Nothing here reads a market. On Polymarket the projection is one input to a
contract's price beside the market's own, and the record decides how much
of it counts (`atlas/polymarket/props.py`).
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from atlas import config
from atlas.models.nhl_props import _ew, logpmf, p_over, poisson_fit
from atlas.util import get_logger

LOG = get_logger(__name__)

VERSION = "nba-props-v1"
STATS = ("points", "rebounds", "assists", "threes")
LINES = {"points": (9.5, 14.5, 19.5, 24.5), "rebounds": (3.5, 5.5, 7.5), "assists": (1.5, 3.5, 5.5),
         "threes": (0.5, 1.5, 2.5)}
WINDOW = 3
FIRST_REPORT = 2021
TUNE = (2018, 2019, 2020)
MIN_PRIOR = 5
#: A player is carried into the games ahead when his latest game is this recent.
ACTIVE_DAYS = 400
GRID = {"h_min": (5.0, 8.0, 15.0), "h_rate": (15.0, 30.0, 60.0), "k_rate": (100.0, 400.0, 1000.0),
        "h_team": (10.0, 20.0, 40.0)}


@dataclass(frozen=True)
class Spec:
    h_min: float = 8.0          # games: the minutes' half-life
    h_rate: float = 30.0        # games: the rates'
    k_rate: float = 400.0       # minutes of the position's rate as the prior on a player's
    h_team: float = 20.0        # games: the teams' pace and the opponents' rates allowed


def spec_path(root: Path) -> Path:
    return root / "reports" / "nba_props_spec.json"


def load_spec(root: Path) -> Spec:
    p = spec_path(root)
    if not p.exists():
        return Spec()
    raw = json.loads(p.read_text())
    return Spec(**{k: float(v) for k, v in raw.items() if k in Spec.__dataclass_fields__})


# ---------------------------------------------------------------------------
# The teams: pace, and what each allows
# ---------------------------------------------------------------------------


def team_frame(players: pd.DataFrame, team_games: pd.DataFrame) -> pd.DataFrame:
    """One row per team-game: possessions, and the stats the team's opponents recorded against it."""
    p = players[players["played"]]
    allowed = p.groupby(["game_id", "opponent_id"])[list(STATS)].sum().reset_index() \
        .rename(columns={"opponent_id": "team_id", **{s: f"allow_{s}" for s in STATS}})
    tg = team_games[["game_id", "season", "team_id", "possessions"]].copy()
    tg["game_id"] = pd.to_numeric(tg["game_id"], errors="coerce").astype("int64")
    date = players.drop_duplicates("game_id").set_index("game_id")["date"]
    out = tg.merge(allowed, on=["game_id", "team_id"], how="left")
    out["date"] = out["game_id"].map(date)
    out = out.dropna(subset=["date"])
    return out.sort_values(["team_id", "date", "game_id"]).reset_index(drop=True)


def league_levels(teams: pd.DataFrame) -> pd.DataFrame:
    """The league's possessions and stats allowed per team-game, the season before."""
    g = teams.groupby("season")[["possessions", *[f"allow_{s}" for s in STATS]]].mean()
    first = g.iloc[[0]].copy()
    g.index = g.index + 1
    return pd.concat([first, g]).groupby(level=0).last()


def team_state(teams: pd.DataFrame, spec: Spec, *, prior: bool = True) -> pd.DataFrame:
    """Each team's weighted possessions and stats allowed per game, before each game (``prior``) or
    through it, as factors over the league's level the season before."""
    cols = ["possessions", *[f"allow_{s}" for s in STATS]]
    t = teams.assign(one=1.0)
    ew = _ew(t, "team_id", ["one", *cols], spec.h_team, prior=prior)
    lv = league_levels(teams)
    level = lv.reindex(teams["season"]).set_index(teams.index)
    out = pd.DataFrame(index=teams.index)
    n = ew["one"]
    for c in cols:
        # A team with no history is the league.
        per_game = (ew[c] + 10.0 * level[c]) / (n + 10.0)
        out[f"f_{c}"] = (per_game / level[c]).fillna(1.0)
    return out


# ---------------------------------------------------------------------------
# The players
# ---------------------------------------------------------------------------


def position_rates(p: pd.DataFrame) -> pd.DataFrame:
    """Per season and position, the league's per-minute rates the season before."""
    reg = p[p["played"] & (p["season_type"] == "regular")]
    g = reg.groupby(["season", "position"])
    out = pd.DataFrame({s: g[s].sum() / g["minutes"].sum() for s in STATS})
    out["minutes"] = g["minutes"].mean()
    out = out.reset_index()
    first = out[out["season"] == out["season"].min()].copy()
    out["season"] += 1
    return pd.concat([first, out], ignore_index=True).drop_duplicates(["season", "position"], keep="last")


def _state(p: pd.DataFrame, spec: Spec, *, prior: bool) -> pd.DataFrame:
    """Each player's expected minutes and per-minute rates: before each game (``prior``) or through it. Games
    he did not play carry no weight: the state passes through them unchanged."""
    played = p[p["played"]]
    t = _ew(played.assign(one=1.0), "player_id", ["one", "minutes"], spec.h_min, prior=prior)
    r = _ew(played.assign(one=1.0), "player_id", ["one", "minutes", *STATS], spec.h_rate, prior=prior)
    pr = p[["season", "position"]].merge(position_rates(p), on=["season", "position"], how="left").set_index(p.index)
    st = pd.DataFrame(index=played.index)
    st["n"] = r["one"]
    st["min_hat"] = t["minutes"] / t["one"].replace(0.0, np.nan)
    for s in STATS:
        st[f"{s}_rate"] = (r[s] + spec.k_rate * pr.loc[played.index, s]) / (r["minutes"] + spec.k_rate)
    # A game he did not play reads the state as it stood after his last one.
    out = st.reindex(p.index)
    out = out.groupby(p["player_id"]).ffill()
    out["n"] = out["n"].fillna(0.0)
    out["min_hat"] = out["min_hat"].fillna(0.8 * pr["minutes"])
    for s in STATS:
        out[f"{s}_rate"] = out[f"{s}_rate"].fillna(pr[s])
    return out


def features(players: pd.DataFrame, team_games: pd.DataFrame, spec: Spec) -> pd.DataFrame:
    """Every player-game with what was known before it: the player's state, the teams' factors, home, and the
    season mean so far for the naive baseline."""
    p = players.sort_values(["player_id", "date", "game_id"], kind="stable").reset_index(drop=True)
    p = p.assign(position=p["position"].where(p["position"].isin(["G", "F", "C"]), "F"))
    p = pd.concat([p, _state(p, spec, prior=True)], axis=1)
    teams = team_frame(players, team_games)
    ts = pd.concat([teams[["game_id", "team_id"]], team_state(teams, spec, prior=True)], axis=1)
    own = ts.rename(columns={"team_id": "team_id", "f_possessions": "pace_own"})[["game_id", "team_id", "pace_own"]]
    opp = ts.rename(columns={"team_id": "opponent_id", "f_possessions": "pace_opp",
                             **{f"f_allow_{s}": f"opp_{s}" for s in STATS}})
    opp = opp[["game_id", "opponent_id", "pace_opp", *[f"opp_{s}" for s in STATS]]]
    p = p.merge(own, on=["game_id", "team_id"], how="left").merge(opp, on=["game_id", "opponent_id"], how="left")
    p["pace"] = ((p["pace_own"].fillna(1.0) + p["pace_opp"].fillna(1.0)) / 2.0).clip(0.7, 1.4)
    for s in STATS:
        p[f"opp_{s}"] = p[f"opp_{s}"].fillna(1.0).clip(0.6, 1.6)
        p[f"base_{s}"] = p["min_hat"] * p[f"{s}_rate"]
    p["home"] = p["is_home"].astype(float)
    # The season mean so far, played games only, for the naive baseline; and how many there were.
    played = p[p["played"]]
    cum = played.groupby(["player_id", "season"])[list(STATS)].cumsum() - played[list(STATS)]
    cnt = played.groupby(["player_id", "season"]).cumcount()
    for s in STATS:
        p.loc[played.index, f"naive_{s}"] = cum[s] / cnt.replace(0, np.nan)
    p.loc[played.index, "n_season"] = cnt.to_numpy(dtype=float)
    p["n_season"] = p["n_season"].fillna(0.0)
    return p


# ---------------------------------------------------------------------------
# The layer: the game around the base expectation
# ---------------------------------------------------------------------------


def design(frame: pd.DataFrame, stat: str) -> np.ndarray:
    return np.column_stack([np.ones(len(frame)), frame["home"].to_numpy(float),
                            np.log(frame[f"opp_{stat}"].to_numpy(float)), np.log(frame["pace"].to_numpy(float))])


def offset(frame: pd.DataFrame, stat: str) -> np.ndarray:
    return np.log(np.clip(frame[f"base_{stat}"].to_numpy(float), 1e-6, None))


def mean(frame: pd.DataFrame, stat: str, layer: dict) -> np.ndarray:
    beta = np.asarray(layer[stat]["beta"])
    return np.exp(np.clip(offset(frame, stat) + design(frame, stat) @ beta, -30, 30))


def fit_season(p: pd.DataFrame, season: int) -> dict:
    """The layer for ``season`` from the three seasons before it: each stat's coefficients and its dispersion
    about the fitted mean."""
    seasons = range(max(season - WINDOW, int(p["season"].min())), season)
    if not len(seasons):
        seasons = [season]
    train = p[p["season"].isin(list(seasons)) & (p["season_type"] == "regular") & p["played"] & (p["n"] >= 1)]
    out: dict = {}
    for stat in STATS:
        x, y = design(train, stat), train[stat].to_numpy(float)
        beta = poisson_fit(x, y, offset(train, stat))
        mu = np.exp(np.clip(offset(train, stat) + x @ beta, -30, 30))
        out[stat] = {"beta": beta.tolist(), "dispersion": float(max(1.0, ((y - mu) ** 2).sum() / mu.sum()))}
    return out


# ---------------------------------------------------------------------------
# The walk-forward
# ---------------------------------------------------------------------------


def walk(players: pd.DataFrame, team_games: pd.DataFrame, spec: Spec, seasons) -> tuple[pd.DataFrame, dict]:
    """Atlas's expectation for every regular-season player-game of ``seasons``, each from its own layer."""
    f = features(players, team_games, spec)
    layers, parts = {}, []
    for season in seasons:
        layer = fit_season(f, season)
        layers[season] = layer
        rows = f[(f["season"] == season) & (f["season_type"] == "regular") & f["played"]].copy()
        for stat in STATS:
            rows[f"mu_{stat}"] = mean(rows, stat, layer)
        parts.append(rows)
    return (pd.concat(parts, ignore_index=True) if parts else f.iloc[0:0]), layers


def score(rows: pd.DataFrame, layers: dict) -> pd.DataFrame:
    """Per stat and line, on player-games with :data:`MIN_PRIOR` games of the season behind them: Brier and log
    loss of P(over) by Atlas and by a Poisson on the season mean so far, and each one's mean against the rate
    observed; and the mean absolute error of each expectation."""
    out = []
    for stat, lines in LINES.items():
        f = rows[(rows["n_season"] >= MIN_PRIOR) & rows[f"naive_{stat}"].notna()]
        if f.empty:
            continue
        y_val = f[stat].to_numpy(float)
        mae = {"atlas": float(np.abs(y_val - f[f"mu_{stat}"].to_numpy(float)).mean()),
               "naive": float(np.abs(y_val - f[f"naive_{stat}"].to_numpy(float)).mean())}
        for line in lines:
            y = (y_val > line).astype(float)
            p_atlas = np.empty(len(f))
            for season in f["season"].unique():
                m = (f["season"] == season).to_numpy()
                p_atlas[m] = p_over(f[f"mu_{stat}"].to_numpy(float)[m], line, layers[season][stat]["dispersion"])
            p_naive = p_over(f[f"naive_{stat}"].to_numpy(float), line, 1.0)
            row = {"stat": stat, "line": line, "n": int(len(f)), "observed": float(y.mean()),
                   "mae_atlas": mae["atlas"], "mae_naive": mae["naive"]}
            for name, p in (("atlas", p_atlas), ("naive", p_naive)):
                q = np.clip(p, 1e-6, 1 - 1e-6)
                row[f"brier_{name}"] = float(((p - y) ** 2).mean())
                row[f"logloss_{name}"] = float(-(y * np.log(q) + (1 - y) * np.log(1 - q)).mean())
                row[f"mean_{name}"] = float(p.mean())
            out.append(row)
    return pd.DataFrame(out)


def loglik(rows: pd.DataFrame, layers: dict) -> float:
    total, n = 0.0, 0
    for stat in STATS:
        f = rows[rows["n_season"] >= MIN_PRIOR]
        for season in f["season"].unique():
            m = (f["season"] == season).to_numpy()
            ll = logpmf(f[stat].to_numpy(float)[m], f[f"mu_{stat}"].to_numpy(float)[m],
                        layers[season][stat]["dispersion"])
            total += float(np.sum(ll))
            n += int(m.sum())
    return total / max(n, 1)


def tune(players: pd.DataFrame, team_games: pd.DataFrame, base: Spec | None = None) -> tuple[Spec, list[dict]]:
    """One coordinate at a time over :data:`GRID`, on the tuning seasons' log-likelihood."""
    spec, trials = base or Spec(), []
    for name, values in GRID.items():
        best = None
        for v in values:
            trial = replace(spec, **{name: v})
            rows, layers = walk(players, team_games, trial, TUNE)
            ll = loglik(rows, layers)
            trials.append({**asdict(trial), "loglik": ll})
            LOG.info("nba props tune: %s=%g loglik %.5f", name, v, ll)
            if best is None or ll > best[0]:
                best = (ll, trial)
        spec = best[1]
    return spec, trials


# ---------------------------------------------------------------------------
# The games ahead
# ---------------------------------------------------------------------------

PLAYER_STATE = ["player_id", "player", "position", "team_id", "team_abbr", "date", "n_season", "min_hat",
                *[f"{s}_rate" for s in STATS]]


def snapshot(players: pd.DataFrame, team_games: pd.DataFrame, now, spec: Spec | None = None) -> dict:
    """Everything a game ahead needs, as it stands after the latest game: each active player's minutes and
    rates on the team he last played for, each team's pace and rates allowed, and the season's layer."""
    spec = spec or Spec()
    t = pd.Timestamp(now)
    t = t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")
    season = t.year if t.month >= 10 else t.year - 1
    f = features(players, team_games, spec)
    layer = fit_season(f, season)
    p = players.sort_values(["player_id", "date", "game_id"], kind="stable").reset_index(drop=True)
    p = p.assign(position=p["position"].where(p["position"].isin(["G", "F", "C"]), "F"))
    after = pd.concat([p, _state(p, spec, prior=False)], axis=1)
    played = after[after["played"]]
    season_n = played[played["season"] == season].groupby("player_id").size()
    latest = after.groupby("player_id", sort=False).tail(1).copy()
    latest["n_season"] = latest["player_id"].map(season_n).fillna(0.0)
    recent = pd.to_datetime(latest["date"]) >= (t.tz_localize(None) - pd.Timedelta(days=ACTIVE_DAYS))
    latest = latest[recent & (latest["n"] > 0)]
    teams = team_frame(players, team_games)
    ts = pd.concat([teams[["team_id", "season"]], team_state(teams, spec, prior=False)], axis=1)
    team_now = ts.groupby("team_id", sort=False).tail(1)
    return {"version": VERSION, "season": int(season), "built_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
            "players": latest[PLAYER_STATE].reset_index(drop=True),
            "teams": team_now[["team_id", "f_possessions", *[f"f_allow_{s}" for s in STATS]]].reset_index(drop=True),
            "layer": layer, "spec": asdict(spec)}


#: ESPN's injury statuses, lowercased: the chance the player takes the court, and the share of his usual
#: minutes he plays when he does. Stated, not fitted: no archive of reports exists to walk forward on, so
#: the capture (atlas/sources/nba_availability.py) is building one. Polymarket US settles a player who does
#: not take the court at the last fair market price, so the chance of not playing goes to the market's own
#: price (:func:`prob_available`); a venue that resolves him as No sends it to the under in full.
AVAILABILITY = {"out": (0.03, 1.0), "day-to-day": (0.55, 0.9)}
#: A listed player's minutes go to his teammates in the rotation, in proportion to theirs, up to a cap.
ROTATION_MINUTES = 8.0
MAX_MINUTES = 38.0


def name_key(name) -> str:
    """A player's name as a key: lowercased, accents and punctuation dropped, suffixes dropped."""
    import re
    import unicodedata

    text = unicodedata.normalize("NFKD", str(name or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower()
    text = re.sub(r"[.'’\-]", "", text)
    words = [w for w in text.split() if w not in ("jr", "sr", "ii", "iii", "iv")]
    return " ".join(words)


def adjust(snap: dict, availability: pd.DataFrame | None) -> dict:
    """The snapshot with the injury report applied. Each player gets ``p_play``, his chance of taking the
    court, and ``status`` as listed; a listed player's ``min_hat`` is what he plays when he does, and the
    minutes the report takes from a team go to its unlisted rotation players in proportion to theirs. The
    snapshot given is not changed."""
    players = snap["players"].copy()
    players["p_play"] = 1.0
    players["status"] = ""
    if availability is None or len(availability) == 0 or players.empty:
        return {**snap, "players": players}
    by_id: dict[int, str] = {}
    by_name: dict[tuple[int, str], str] = {}
    for r in availability.itertuples(index=False):
        status = str(r.status or "").strip().lower()
        if status not in AVAILABILITY:
            continue
        if pd.notna(r.player_id):
            by_id[int(r.player_id)] = status
        if pd.notna(r.team_id):
            by_name[(int(r.team_id), name_key(r.player))] = status
    listed = []
    for i, row in players.iterrows():
        status = by_id.get(int(row["player_id"])) if pd.notna(row["player_id"]) else None
        if status is None:
            try:
                status = by_name.get((int(row["team_id"]), name_key(row["player"])))
            except (TypeError, ValueError):
                status = None
        if status:
            listed.append((i, status))
    if not listed:
        return {**snap, "players": players}
    lost = pd.Series(0.0, index=players.index)
    for i, status in listed:
        p_play, share = AVAILABILITY[status]
        usual = float(players.at[i, "min_hat"])
        players.at[i, "p_play"] = p_play
        players.at[i, "status"] = status
        players.at[i, "min_hat"] = usual * share
        # What the team is expected to be without, minutes a game.
        lost.at[i] = usual - p_play * usual * share
    for _team_id, idx in players.groupby("team_id").groups.items():
        missing = float(lost.loc[idx].sum())
        if missing <= 0:
            continue
        unlisted = [i for i in idx if players.at[i, "status"] == "" and players.at[i, "min_hat"] >= ROTATION_MINUTES]
        if not unlisted:
            continue
        base = players.loc[unlisted, "min_hat"].astype(float)
        extra = missing * base / base.sum()
        players.loc[unlisted, "min_hat"] = np.minimum(base + extra, MAX_MINUTES)
    return {**snap, "players": players}


def expect(snap: dict, player, team_id, opponent_id, home: bool) -> dict[str, float]:
    """Atlas's expectation of each stat for one player (a :data:`PLAYER_STATE` row) on ``team_id`` against
    ``opponent_id``; nan when a team is not known."""
    teams = snap["teams"].set_index("team_id")
    try:
        own, opp = teams.loc[int(team_id)], teams.loc[int(opponent_id)]
    except (KeyError, TypeError, ValueError):
        return dict.fromkeys(STATS, float("nan"))
    pace = float(np.clip((own["f_possessions"] + opp["f_possessions"]) / 2.0, 0.7, 1.4))
    f = pd.DataFrame([{"home": 1.0 if home else 0.0, "pace": pace,
                       **{f"opp_{s}": float(np.clip(opp[f"f_allow_{s}"], 0.6, 1.6)) for s in STATS},
                       **{f"base_{s}": float(player["min_hat"]) * float(player[f"{s}_rate"]) for s in STATS}}])
    return {s: float(mean(f, s, snap["layer"])[0]) for s in STATS}


def prob(mean_: float, line: float, side: str, dispersion: float) -> float:
    """Atlas's probability of ``side`` (over or under) at ``line``; a tie on a whole-number line is neither."""
    whole = float(line).is_integer()
    over = float(p_over([mean_], line, dispersion)[0])
    under = 1.0 - float(p_over([mean_], line - 1 if whole else line, dispersion)[0])
    return over if side == "over" else under


def prob_available(mean_: float, line: float, side: str, dispersion: float, p_play: float = 1.0,
                   settle: float | None = None) -> float:
    """:func:`prob` for a player who may not take the court: ``mean_`` is his expectation when he plays,
    ``p_play`` the chance he does. ``settle`` is what the venue pays the over when he does not: the market's
    own price where it settles at the last fair price (Polymarket US), None where it resolves him as No."""
    p_play = float(np.clip(p_play, 0.0, 1.0))
    over = p_play * prob(mean_, line, "over", dispersion)
    under = p_play * prob(mean_, line, "under", dispersion)
    if settle is None or not np.isfinite(settle):
        return over if side == "over" else under + (1.0 - p_play)
    settle = float(np.clip(settle, 0.0, 1.0))
    return over + (1.0 - p_play) * settle if side == "over" else under + (1.0 - p_play) * (1.0 - settle)


def dispersion(snap: dict, stat: str) -> float:
    return float(snap["layer"][stat]["dispersion"])


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------


def state_path(warehouse: Path | None = None) -> Path:
    return (warehouse or config.paths().warehouse) / "nba_props_state.json"


def save_state(snap: dict, where: Path | None = None) -> Path:
    where = where or state_path()
    where.parent.mkdir(parents=True, exist_ok=True)
    data = {**snap, "players": json.loads(snap["players"].to_json(orient="records", date_format="iso")),
            "teams": json.loads(snap["teams"].to_json(orient="records"))}
    where.write_text(json.dumps(data) + "\n")
    return where


def load_state(where: Path | None = None) -> dict | None:
    where = where or state_path()
    if not where.exists():
        return None
    raw = json.loads(where.read_text())
    return {**raw, "players": pd.DataFrame(raw["players"], columns=PLAYER_STATE),
            "teams": pd.DataFrame(raw["teams"])}


def load_tables(warehouse: Path | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    from atlas.research.nba_dataset import load_table

    return load_table("player_games", warehouse), load_table("team_games", warehouse)


def publish(now, *, root: Path | None = None, warehouse: Path | None = None) -> int:
    """The heavy refresh's step: the snapshot written where the pricing reads it. Returns the players in it."""
    root = root or config.paths().root
    players, team_games = load_tables(warehouse)
    snap = snapshot(players, team_games, now, load_spec(root))
    save_state(snap, state_path(warehouse))
    return len(snap["players"])


def render(table: pd.DataFrame, spec: Spec, seasons) -> str:
    lines = ["# NBA player projections, walk-forward", "",
             f"Regular season, {', '.join(f'{s}-{str(s + 1)[-2:]}' for s in seasons)}, player-games with at least "
             f"{MIN_PRIOR} games of the season behind them. Atlas is minutes times a rate times the game "
             f"(`atlas/models/nba_props.py`); the baseline is a Poisson on the player's season mean so far. "
             "Brier and log loss of P(over) at each line, and the mean absolute error of each expectation.", "",
             f"Half-lives: minutes {spec.h_min:g} games, rates {spec.h_rate:g} games with a prior of "
             f"{spec.k_rate:g} minutes of the position's rate, the teams {spec.h_team:g} games.", ""]
    if len(table):
        t = table.copy()
        for c in ("observed", "mean_atlas", "mean_naive"):
            t[c] = (100 * t[c]).round(1)
        for c in ("brier_atlas", "brier_naive", "logloss_atlas", "logloss_naive"):
            t[c] = t[c].round(4)
        for c in ("mae_atlas", "mae_naive"):
            t[c] = t[c].round(3)
        cols = ["stat", "line", "n", "observed", "mean_atlas", "mean_naive", "brier_atlas", "brier_naive",
                "logloss_atlas", "logloss_naive", "mae_atlas", "mae_naive"]
        head = "| " + " | ".join(cols) + " |\n|" + "|".join("---" for _ in cols) + "|"
        body = "\n".join("| " + " | ".join(str(v) for v in r) + " |" for r in t[cols].itertuples(index=False))
        lines += [head, body, ""]
        better = int((t["brier_atlas"] < t["brier_naive"]).sum())
        lines += [f"Atlas's Brier beats the season-mean Poisson's at {better} of {len(t)} stat-lines.", ""]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description="Atlas's NBA player projections")
    ap.add_argument("--tune", action="store_true", help="tune the half-lives on the tuning seasons first")
    ap.add_argument("--publish", action="store_true", help="write the snapshot the pricing reads, as of now")
    ap.add_argument("--first", type=int, default=FIRST_REPORT)
    args = ap.parse_args()
    paths = config.paths()
    players, team_games = load_tables()
    spec = load_spec(paths.root)
    if args.tune:
        spec, trials = tune(players, team_games, spec)
        spec_path(paths.root).write_text(json.dumps(asdict(spec), indent=1) + "\n")
        LOG.info("nba props: spec %s saved", asdict(spec))
    if args.publish:
        LOG.info("nba props: %d players in the snapshot", publish(datetime.now(UTC)))
        return
    last = int(players["season"].max())
    seasons = [s for s in range(args.first, last + 1) if (players["season"] == s).sum() > 5000]
    rows, layers = walk(players, team_games, spec, seasons)
    table = score(rows, layers)
    out = paths.reports / "nba_props.md"
    out.write_text(render(table, spec, seasons))
    LOG.info("wrote %s", out)


if __name__ == "__main__":
    main()
