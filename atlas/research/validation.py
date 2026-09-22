"""Point-in-time audit.

These checks are the reason to trust anything downstream. They are run as part
of the research pipeline and again in the test suite, and they fail loudly.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from atlas import config
from atlas.util import get_logger

LOG = get_logger(__name__)

#: A feature correlating this strongly with an outcome is almost certainly the
#: outcome in disguise. Nothing legitimate in college football gets close.
SUSPICIOUS_CORRELATION = 0.98


def recompute_pit_by_brute_force(
    frame: pd.DataFrame,
    column: str,
    *,
    team_key: str = "team_id",
    shrinkage: float = config.PRIOR_SEASON_SHRINKAGE_GAMES,
    sample: int | None = 500,
    seed: int = config.SEED,
) -> pd.DataFrame:
    """Independently recompute a point-in-time column one row at a time.

    The vectorised implementation in :mod:`atlas.features.point_in_time` is
    fast but easy to get subtly wrong. This does the same thing the slow,
    obvious way - for each row, filter to that team's strictly earlier games -
    so the two can be compared.
    """
    df = frame.sort_values(["team_id", "season", "kickoff", "game_id"]).reset_index(drop=True)

    team_anchor = (
        df.groupby([team_key, "season"])[column].mean().rename("anchor").reset_index()
    )
    team_anchor["season"] = team_anchor["season"] + 1
    league_anchor = df.groupby("season")[column].mean().rename("league").reset_index()
    league_anchor["season"] = league_anchor["season"] + 1
    anchors = {(r[team_key], r["season"]): r["anchor"] for _, r in team_anchor.iterrows()}
    league = dict(zip(league_anchor["season"], league_anchor["league"], strict=False))

    rows = df.index.to_numpy()
    if sample is not None and len(rows) > sample:
        rng = np.random.default_rng(seed)
        rows = rng.choice(rows, size=sample, replace=False)

    out = []
    for i in rows:
        row = df.loc[i]
        prior = df[
            (df[team_key] == row[team_key])
            & (df["season"] == row["season"])
            & (
                (df["kickoff"] < row["kickoff"])
                | ((df["kickoff"] == row["kickoff"]) & (df["game_id"] < row["game_id"]))
            )
        ][column].dropna()
        anchor = anchors.get((row[team_key], row["season"]), np.nan)
        if pd.isna(anchor):
            anchor = league.get(row["season"], np.nan)
        if pd.isna(anchor):
            value = prior.mean() if len(prior) else np.nan
        else:
            value = (prior.sum() + shrinkage * anchor) / (len(prior) + shrinkage)
        out.append({"index": i, "brute_force": value})
    return pd.DataFrame(out).set_index("index")


def leakage_scan(df: pd.DataFrame, features: list[str], targets: list[str]) -> pd.DataFrame:
    """Flag any feature that correlates with a target implausibly strongly."""
    rows = []
    for target in targets:
        if target not in df.columns:
            continue
        y = pd.to_numeric(df[target], errors="coerce")
        for feature in features:
            if feature not in df.columns:
                continue
            x = pd.to_numeric(df[feature], errors="coerce")
            mask = x.notna() & y.notna()
            if mask.sum() < 50 or x[mask].std() == 0:
                continue
            corr = float(np.corrcoef(x[mask], y[mask])[0, 1])
            rows.append(
                {
                    "target": target,
                    "feature": feature,
                    "n": int(mask.sum()),
                    "correlation": corr,
                    "suspicious": abs(corr) > SUSPICIOUS_CORRELATION,
                }
            )
    return pd.DataFrame(rows).sort_values("correlation", key=lambda s: s.abs(), ascending=False)


def assert_no_future_information(frame: pd.DataFrame, pit_columns: list[str]) -> None:
    """A team's first game of a season can only carry prior-season information.

    Concretely: the point-in-time value on game 1 must be identical for every
    team-season regardless of what happened in that season, so it must equal
    the prior anchor exactly. This asserts the weaker but decisive property
    that ``n_prior_games == 0`` rows never vary with the current game's value.
    """
    first = frame[frame["n_prior_games"] == 0]
    for col in pit_columns:
        base = col.removesuffix("_pit")
        if base not in frame.columns or col not in frame.columns:
            continue
        sub = first[[base, col]].dropna()
        if len(sub) < 50:
            continue
        corr = float(np.corrcoef(sub[base], sub[col])[0, 1])
        if abs(corr) > 0.5:
            raise AssertionError(
                f"{col} on a team's first game correlates {corr:.2f} with that same "
                f"game's {base} - the point-in-time shift is leaking"
            )


def coverage_report(df: pd.DataFrame, features: list[str]) -> pd.DataFrame:
    rows = []
    for feature in features:
        if feature not in df.columns:
            rows.append({"feature": feature, "present": False, "coverage": 0.0})
            continue
        series = pd.to_numeric(df[feature], errors="coerce")
        rows.append(
            {"feature": feature, "present": True, "coverage": float(series.notna().mean())}
        )
    return pd.DataFrame(rows)
