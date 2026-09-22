"""Phase 1C analyses. Every measurement is against the market residual.

Phase 1A and 1B established that team-quality metrics are fully priced. These
tracks look elsewhere: at who is playing (Track 1), at when the price forms
(Track 2), at roster and staff churn (Track 3), at the situation (Track 4), at
the games the market got most wrong (Track 5), and at an independent model's
published results (Track 6).

The output of each is a table of effects with error bars. The synthesis report
pools every p-value and applies one Benjamini-Hochberg correction across the
lot, because running sixty tests and reporting the three that cleared 0.05 is
how a research programme fools itself.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from atlas.research import models
from atlas.research import residual_tools as rt
from atlas.util import get_logger

LOG = get_logger(__name__)

RESIDUAL = rt.RESIDUAL_MARGIN
RESIDUAL_TOTAL = rt.RESIDUAL_TOTAL


# ===========================================================================
# Track 1 - quarterback value
# ===========================================================================

QB_EVENTS = [
    ("qb_change", "Different QB than last game"),
    ("new_starter", "First career start for this team"),
    ("first_year_player", "First season on any roster"),
    ("inexperienced_starter", "Fewer than 3 career starts"),
    ("backup_start", "Not the team's season-primary QB"),
    ("transfer_starter", "Previously on another team's roster"),
    ("returning_starter", "Started for this team last season"),
    ("committee_game", "No QB took 70% of attempts"),
    ("planned_change", "New QB who took ~every snap (decided pre-kickoff)"),
    ("in_game_rotation", "QB changed during the game"),
]


#: Each event in its pre-kickoff (lagged) form. The contemporaneous effect is
#: an upper bound contaminated by reverse causation; this is what is usable.
QB_LAGGED_EVENTS = [
    (f"prior_{event}", f"LAST GAME: {description.lower()}") for event, description in QB_EVENTS
]


def qb_event_effects(df: pd.DataFrame, events: list[tuple[str, str]] | None = None) -> pd.DataFrame:
    """Signed residual effect of each quarterback event.

    Signed means folded: an away-team event and a home-team event are the same
    phenomenon mirrored, so the fold doubles the sample. A positive value means
    the team with the event **underperformed** the closing line.
    """
    rows = []
    for event, description in (events or QB_EVENTS):
        column = f"{event}_signed"
        if column not in df.columns:
            continue
        result = rt.signed_effect(df, column, target=RESIDUAL, label=event)
        low, high = rt.bootstrap_ci(
            pd.to_numeric(df.loc[df[column].fillna(0) != 0, RESIDUAL], errors="coerce")
            * np.sign(df.loc[df[column].fillna(0) != 0, column])
        )
        rows.append({**result, "description": description, "ci_low": low, "ci_high": high})
    out = pd.DataFrame(rows)
    return out.sort_values("t", key=lambda s: s.abs(), ascending=False)


def qb_effect_by_segment(df: pd.DataFrame, event: str = "qb_change") -> pd.DataFrame:
    """Does the effect vary by conference, mismatch size or home/away?"""
    column = f"{event}_signed"
    sub = df[df[column].fillna(0) != 0].copy()
    if sub.empty:
        return pd.DataFrame()
    sub["signed_residual"] = pd.to_numeric(sub[RESIDUAL], errors="coerce") * np.sign(sub[column])

    # The event sits with one side; that side's conference is the relevant one.
    event_is_away = sub[column] > 0
    sub["event_conference"] = np.where(
        event_is_away, sub.get("away_conference"), sub.get("home_conference")
    )
    sub["event_side"] = np.where(event_is_away, "away", "home")
    sub["mismatch"] = pd.cut(
        sub["closing_spread"].abs(),
        [-0.1, 3, 7, 14, 24, 100],
        labels=["pick'em", "3-7", "7-14", "14-24", "24+"],
    )
    sub["event_team_role"] = np.where(
        (event_is_away & (sub["closing_spread"] > 0))
        | (~event_is_away & (sub["closing_spread"] < 0)),
        "favourite",
        "underdog",
    )

    frames = []
    for dimension in ("event_conference", "event_side", "mismatch", "event_team_role"):
        if dimension not in sub.columns:
            continue
        block = rt.effect_by_group(
            sub.rename(columns={"signed_residual": "_r"}),
            dimension,
            target="_r",
            outcome=None,
            min_games=40,
        )
        if not block.empty:
            block.insert(0, "dimension", dimension)
            frames.append(block)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def qb_market_pricing(df: pd.DataFrame, event: str = "qb_change") -> pd.DataFrame:
    """Does the line already move when a quarterback changes?

    If the market fully priced it, the open-to-close move would absorb the
    news and the residual would be flat. If it priced none of it, the line
    would not move at all. Measuring both separates "unknown to the market"
    from "known and underweighted".
    """
    column = f"{event}_signed"
    sub = df[df[column].fillna(0) != 0].dropna(subset=["spread_movement"]).copy()
    if sub.empty:
        return pd.DataFrame()
    sign = np.sign(sub[column])
    sub["signed_move"] = pd.to_numeric(sub["spread_movement"], errors="coerce") * sign
    sub["signed_residual"] = pd.to_numeric(sub[RESIDUAL], errors="coerce") * sign

    baseline = df[df[column].fillna(0) == 0].dropna(subset=["spread_movement"])
    rows = [
        {
            "measure": "line move toward the non-event side (points)",
            **rt._summarise(sub["signed_move"]),
        },
        {
            "measure": "line move, games with no event (control)",
            **rt._summarise(pd.to_numeric(baseline["spread_movement"], errors="coerce").abs()
                            * 0 + pd.to_numeric(baseline["spread_movement"], errors="coerce")),
        },
        {"measure": "residual after the move (points)", **rt._summarise(sub["signed_residual"])},
    ]
    # Split by whether the line moved at all: news the market saw versus news
    # it did not.
    moved = sub[sub["signed_move"].abs() >= 0.5]
    still = sub[sub["signed_move"].abs() < 0.5]
    rows.append({"measure": "residual | line moved >= 0.5", **rt._summarise(moved["signed_residual"])})
    rows.append({"measure": "residual | line barely moved", **rt._summarise(still["signed_residual"])})
    return pd.DataFrame(rows)


def qb_distribution(df: pd.DataFrame, event: str = "qb_change") -> pd.DataFrame:
    """Quantiles of the signed residual, so the shape is visible, not just the mean."""
    column = f"{event}_signed"
    sub = df[df[column].fillna(0) != 0]
    if sub.empty:
        return pd.DataFrame()
    signed = pd.to_numeric(sub[RESIDUAL], errors="coerce") * np.sign(sub[column])
    control = pd.to_numeric(df.loc[df[column].fillna(0) == 0, RESIDUAL], errors="coerce")
    quantiles = [0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95]
    return pd.DataFrame(
        {
            "quantile": quantiles,
            "event_games": [float(signed.quantile(q)) for q in quantiles],
            "control_games": [float(control.quantile(q)) for q in quantiles],
        }
    )


def qb_by_season(df: pd.DataFrame, event: str = "qb_change") -> pd.DataFrame:
    column = f"{event}_signed"
    sub = df[df[column].fillna(0) != 0].copy()
    sub["_r"] = pd.to_numeric(sub[RESIDUAL], errors="coerce") * np.sign(sub[column])
    return rt.effect_by_group(sub, "season", target="_r", outcome=None, min_games=20)


# ===========================================================================
# Track 2 - market timing
# ===========================================================================


def market_timing(df: pd.DataFrame) -> pd.DataFrame:
    """How much the number improves between open and close.

    Atlas has no timestamped line archive - no free source carries one, and
    CFBD exposes open and close only - so the intraday snapshots the brief
    asks for cannot be measured. What *is* measurable is the total information
    that arrives between the two, which bounds everything inside it.
    """
    rows = []
    for label, column, truth in (
        ("opening spread", "opening_spread", "actual_margin"),
        ("closing spread", "closing_spread", "actual_margin"),
    ):
        sub = df.dropna(subset=[column, truth, "opening_spread", "closing_spread"])
        error = pd.to_numeric(sub[truth], errors="coerce") + pd.to_numeric(sub[column], errors="coerce")
        rows.append({"line": label, "n": len(sub), "mae": float(error.abs().mean()),
                     "rmse": float(np.sqrt((error**2).mean()))})
    for label, column in (("opening total", "opening_total"), ("closing total", "closing_total")):
        sub = df.dropna(subset=[column, "actual_total", "opening_total", "closing_total"])
        error = pd.to_numeric(sub["actual_total"], errors="coerce") - pd.to_numeric(
            sub[column], errors="coerce"
        )
        rows.append({"line": label, "n": len(sub), "mae": float(error.abs().mean()),
                     "rmse": float(np.sqrt((error**2).mean()))})
    return pd.DataFrame(rows)


def movement_value(df: pd.DataFrame) -> pd.DataFrame:
    """Does the direction the line moved predict the residual?

    If the open-to-close move carried information the close still has not
    absorbed, following the move would beat the close. If the close is
    efficient, it should not.
    """
    rows = []
    for label, move, residual in (
        ("spread", "spread_movement", RESIDUAL),
        ("total", "total_movement", RESIDUAL_TOTAL),
    ):
        sub = df.dropna(subset=[move, residual]).copy()
        if sub.empty:
            continue
        sub["band"] = pd.cut(
            pd.to_numeric(sub[move], errors="coerce"),
            [-100, -3, -1, -0.01, 0.01, 1, 3, 100],
            labels=["<= -3", "-3..-1", "-1..0", "no move", "0..1", "1..3", ">= 3"],
        )
        block = rt.effect_by_group(sub, "band", target=residual, outcome=None, min_games=40)
        if not block.empty:
            block.insert(0, "market", label)
            rows.append(block)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def book_disagreement(df: pd.DataFrame) -> pd.DataFrame:
    """Is the market's own disagreement a signal about its error?"""
    rows = []
    for label, sd_col, residual in (
        ("spread", "closing_spread_sd", RESIDUAL),
        ("total", "closing_total_sd", RESIDUAL_TOTAL),
    ):
        if sd_col not in df.columns:
            continue
        sub = df.dropna(subset=[sd_col, residual]).copy()
        sub["band"] = pd.qcut(sub[sd_col], 4, labels=["tightest", "tight", "loose", "loosest"],
                              duplicates="drop")
        block = sub.groupby("band", observed=True).agg(
            games=(residual, "size"),
            mean_abs_residual=(residual, lambda s: float(s.abs().mean())),
            mean_residual=(residual, "mean"),
        ).reset_index()
        block.insert(0, "market", label)
        rows.append(block)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


# ===========================================================================
# Track 3 - roster and staff continuity
# ===========================================================================


def coach_changes(raw: Path, seasons: list[int], teams: pd.DataFrame) -> pd.DataFrame:
    """Head-coach change per team-season, from the CFBD coaching records."""
    frames = []
    for season in seasons:
        path = raw / "cfbd" / f"coaches_{season}.parquet"
        if not path.exists():
            continue
        df = pd.read_parquet(path)
        if df.empty or "seasons" not in df.columns:
            continue
        for _, coach in df.iterrows():
            for entry in coach["seasons"]:
                if entry.get("year") != season:
                    continue
                frames.append(
                    {
                        "season": season,
                        "school": entry.get("school"),
                        "coach": f"{coach.get('firstName')} {coach.get('lastName')}",
                        "games": entry.get("games"),
                    }
                )
    if not frames:
        return pd.DataFrame()
    staff = pd.DataFrame(frames)
    # A team can list two coaches in a season (mid-season change); keep the
    # one who coached more games.
    staff = staff.sort_values(["season", "school", "games"], ascending=[True, True, False])
    primary = staff.groupby(["season", "school"], as_index=False).first()
    primary = primary.sort_values(["school", "season"])
    primary["prev_coach"] = primary.groupby("school")["coach"].shift(1)
    primary["head_coach_change"] = (
        primary["prev_coach"].notna() & (primary["coach"] != primary["prev_coach"])
    )
    primary["mid_season_change"] = primary["school"].map(
        staff.groupby(["season", "school"]).size().groupby("school").max()
    ).gt(1)

    names = teams.dropna(subset=["school"]).drop_duplicates(["season", "school"])
    return primary.merge(
        names[["season", "school", "team_id"]], on=["season", "school"], how="left"
    ).dropna(subset=["team_id"])


def continuity_effects(df: pd.DataFrame) -> pd.DataFrame:
    """Residual effect of roster and staff churn variables."""
    rows = []
    signed_flags = [
        ("head_coach_change_signed", "New head coach", True),
        ("qb_change_signed", "QB change (reference)", False),
    ]
    for column, label, pre_kickoff in signed_flags:
        if column in df.columns and (df[column].fillna(0) != 0).sum() >= 50:
            rows.append(
                {**rt.signed_effect(df, column, target=RESIDUAL, label=label),
                 "pre_kickoff": pre_kickoff}
            )

    continuous = [
        ("returning_production_diff", "Returning production edge", True),
        ("recruiting_rank_diff", "Recruiting edge", True),
        ("talent_diff", "Roster talent edge", True),
        ("transfer_starter_signed", "Transfer QB", False),
        ("qb_continuity_diff", "QB continuity edge (today's starter - post-hoc)", False),
        ("prior_qb_continuity_diff", "QB continuity edge (last game's - pre-kickoff)", True),
        ("roster_churn_diff", "Roster churn edge", True),
    ]
    for column, label, pre_kickoff in continuous:
        if column not in df.columns:
            continue
        sub = df.dropna(subset=[column, RESIDUAL])
        if len(sub) < 200:
            continue
        rows.append({"effect": label, **_correlation_test(sub[column], sub[RESIDUAL]),
                     "pre_kickoff": pre_kickoff})
    return pd.DataFrame(rows)


def _correlation_test(x: pd.Series, y: pd.Series) -> dict:
    from scipy import stats

    x = pd.to_numeric(x, errors="coerce")
    y = pd.to_numeric(y, errors="coerce")
    mask = x.notna() & y.notna()
    n = int(mask.sum())
    if n < 50 or x[mask].std() == 0:
        return {"n": n, "mean": np.nan, "t": np.nan, "p": np.nan}
    r, p = stats.pearsonr(x[mask], y[mask])
    slope = r * y[mask].std() / x[mask].std()
    t = r * np.sqrt((n - 2) / max(1e-12, 1 - r**2))
    return {"n": n, "mean": float(slope), "correlation": float(r), "t": float(t), "p": float(p)}


def roster_churn(raw: Path, seasons: list[int], teams: pd.DataFrame) -> pd.DataFrame:
    """Share of a team's roster that was not there the previous season."""
    from atlas.sources import rosters

    roster = rosters.load(raw, [min(seasons) - 1, *seasons])
    if roster.empty:
        return pd.DataFrame()
    roster = roster.dropna(subset=["athlete_id", "team"])
    roster["athlete_id"] = roster["athlete_id"].astype("int64")

    previous = roster.copy()
    previous["season"] = previous["season"] + 1
    previous = previous[["season", "team", "athlete_id"]].assign(was_here=True)

    merged = roster.merge(previous, on=["season", "team", "athlete_id"], how="left")
    merged["was_here"] = merged["was_here"].fillna(False)
    churn = (
        merged.groupby(["season", "team"], as_index=False)["was_here"]
        .mean()
        .rename(columns={"was_here": "returning_share"})
    )
    churn["roster_churn"] = 1 - churn["returning_share"]

    names = teams.dropna(subset=["school"]).drop_duplicates(["season", "school"])
    return churn.merge(
        names[["season", "school", "team_id"]],
        left_on=["season", "team"],
        right_on=["season", "school"],
        how="left",
    ).dropna(subset=["team_id"])


# ===========================================================================
# Track 4 - special situations
# ===========================================================================


def build_situations(df: pd.DataFrame, raw: Path, seasons: list[int]) -> pd.DataFrame:
    """Attach situational flags to the research frame.

    All of these are knowable from the schedule before kickoff, so unlike the
    quarterback track these *could* become features. Whether they should is
    what the residual test decides.
    """
    out = df.copy()

    for side in ("home", "away"):
        rest = pd.to_numeric(out.get(f"{side}_days_rest"), errors="coerce")
        out[f"{side}_bye"] = rest >= 13
        out[f"{side}_short_rest"] = rest <= 5
    out["bye_signed"] = out["away_bye"].fillna(False).astype(int) - out["home_bye"].fillna(
        False
    ).astype(int)
    out["short_rest_signed"] = out["away_short_rest"].fillna(False).astype(int) - out[
        "home_short_rest"
    ].fillna(False).astype(int)

    travel = pd.to_numeric(out.get("travel_distance"), errors="coerce")
    out["major_travel"] = travel >= 1500
    out["travel_band"] = pd.cut(
        travel, [-1, 200, 500, 1000, 1500, 10000],
        labels=["<200mi", "200-500", "500-1000", "1000-1500", "1500+"],
    )

    out = _add_rankings(out, raw, seasons)
    out = _add_rivalry_and_revenge(out)

    out["conference_game_flag"] = out.get("conference_game", False)
    return out


def _add_rankings(df: pd.DataFrame, raw: Path, seasons: list[int]) -> pd.DataFrame:
    """Top-10 and ranked-matchup flags from the AP poll.

    Polls are published during the week, so the *previous* week's poll is the
    one that existed before kickoff. Using the current week's would leak.
    """
    frames = []
    for season in seasons:
        path = raw / "cfbd" / f"rankings_{season}.parquet"
        if path.exists():
            frames.append(pd.read_parquet(path))
    if not frames:
        df["home_top10"] = False
        df["away_top10"] = False
        df["top10_matchup"] = False
        return df

    polls = pd.concat(frames, ignore_index=True)
    polls = polls[polls["poll"] == "AP Top 25"].dropna(subset=["team", "rank", "week"])
    polls["week"] = pd.to_numeric(polls["week"], errors="coerce") + 1  # usable the week after
    polls = polls.dropna(subset=["week"])
    polls["week"] = polls["week"].astype(int)
    polls = polls.drop_duplicates(["season", "week", "team"])

    for side in ("home", "away"):
        ranks = polls.rename(columns={"team": f"{side}_team", "rank": f"{side}_rank"})
        df = df.merge(
            ranks[["season", "week", f"{side}_team", f"{side}_rank"]],
            on=["season", "week", f"{side}_team"],
            how="left",
        )
        df[f"{side}_top10"] = pd.to_numeric(df[f"{side}_rank"], errors="coerce") <= 10
        df[f"{side}_ranked"] = df[f"{side}_rank"].notna()
    df["top10_matchup"] = df["home_top10"] & df["away_top10"]
    df["ranked_matchup"] = df["home_ranked"] & df["away_ranked"]
    df["top10_signed"] = df["away_top10"].astype(int) - df["home_top10"].astype(int)
    return df


def _add_rivalry_and_revenge(df: pd.DataFrame) -> pd.DataFrame:
    """Rivalry as a repeat fixture; revenge as a rematch after a loss.

    There is no free authoritative rivalry list, so "rivalry" is defined
    structurally: a pairing that recurs in most seasons of the sample. That
    captures the annual conference and trophy games and misses one-off
    grudges, which is the honest trade.
    """
    pair = df[["home_team_id", "away_team_id"]].apply(
        lambda r: tuple(sorted((int(r.iloc[0]), int(r.iloc[1])))), axis=1
    )
    df["pairing"] = pair
    seasons_played = df.groupby("pairing")["season"].nunique()
    total_seasons = df["season"].nunique()
    df["rivalry"] = df["pairing"].map(seasons_played).ge(max(3, total_seasons - 2))

    # Revenge: these two met before and the team now at home lost that meeting.
    history = df[["pairing", "season", "week", "home_team_id", "margin"]].copy()
    history = history.sort_values(["pairing", "season", "week"])
    history["prev_home"] = history.groupby("pairing")["home_team_id"].shift(1)
    history["prev_margin"] = history.groupby("pairing")["margin"].shift(1)
    history["prev_loser"] = np.where(
        history["prev_margin"] < 0, history["prev_home"], np.nan
    )
    df = df.merge(
        history[["pairing", "season", "week", "prev_loser", "prev_margin"]].drop_duplicates(
            ["pairing", "season", "week"]
        ),
        on=["pairing", "season", "week"],
        how="left",
    )
    df["home_revenge"] = df["prev_loser"].eq(df["home_team_id"])
    df["away_revenge"] = df["prev_loser"].notna() & ~df["home_revenge"] & df["prev_margin"].notna()
    df["revenge_signed"] = df["away_revenge"].astype(int) - df["home_revenge"].astype(int)
    df["blowout_revenge"] = (
        (df["prev_margin"].abs() >= 21) & (df["home_revenge"] | df["away_revenge"])
    )

    # Postseason games following a conference championship week.
    df["postseason"] = df.get("season_type", "regular").eq("postseason")
    return df


SITUATION_FLAGS = [
    ("bye_signed", "Coming off a bye (13+ days)"),
    ("short_rest_signed", "Short rest (<= 5 days)"),
    ("revenge_signed", "Revenge spot (lost the last meeting)"),
    ("top10_signed", "Team is AP top 10"),
]

SITUATION_GROUPS = [
    ("travel_band", "Travel distance"),
    ("rivalry", "Recurring rivalry fixture"),
    ("top10_matchup", "Top-10 vs top-10"),
    ("ranked_matchup", "Ranked vs ranked"),
    ("postseason", "Bowl / postseason"),
    ("blowout_revenge", "Rematch after a 21+ point loss"),
    ("conference_game_flag", "Conference game"),
]


def situational_effects(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for column, label in SITUATION_FLAGS:
        if column in df.columns and (df[column].fillna(0) != 0).sum() >= 50:
            rows.append(rt.signed_effect(df, column, target=RESIDUAL, label=label))
    for column, label in SITUATION_GROUPS:
        if column not in df.columns:
            continue
        flags = df[column]
        if flags.dtype == bool or set(pd.unique(flags.dropna())) <= {True, False}:
            if flags.fillna(False).astype(bool).sum() < 50:
                continue
            rows.append(rt.binary_effect(df, column, target=RESIDUAL, label=label))
    return pd.DataFrame(rows)


def situational_totals(df: pd.DataFrame) -> pd.DataFrame:
    """The same situations, measured against the totals residual."""
    rows = []
    for column, label in SITUATION_GROUPS:
        if column not in df.columns:
            continue
        flags = df[column]
        if flags.dtype == bool or set(pd.unique(flags.dropna())) <= {True, False}:
            if flags.fillna(False).astype(bool).sum() < 50:
                continue
            rows.append(rt.binary_effect(df, column, target=RESIDUAL_TOTAL,
                                         outcome="over_hit", label=label))
    return pd.DataFrame(rows)


def travel_effects(df: pd.DataFrame) -> pd.DataFrame:
    return rt.effect_by_group(df, "travel_band", target=RESIDUAL, min_games=100)


# ===========================================================================
# Track 5 - market failure
# ===========================================================================

FAILURE_THRESHOLDS = (21, 28, 35)


def failure_rates(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for target, label in ((RESIDUAL, "margin"), (RESIDUAL_TOTAL, "total")):
        error = pd.to_numeric(df[target], errors="coerce").abs()
        for threshold in FAILURE_THRESHOLDS:
            hits = error >= threshold
            rows.append(
                {
                    "market": label,
                    "threshold": threshold,
                    "games": int(hits.sum()),
                    "share": float(hits.mean()),
                    "per_season": float(hits.sum() / df["season"].nunique()),
                }
            )
    return pd.DataFrame(rows)


def failure_characteristics(df: pd.DataFrame, threshold: int = 28) -> pd.DataFrame:
    """What distinguishes the games the market got most wrong?

    Each candidate is compared between blown games and the rest. A
    characteristic that is equally common in both explains nothing, however
    memorable the games are.
    """
    error = pd.to_numeric(df[RESIDUAL], errors="coerce").abs()
    blown = error >= threshold
    candidates = [
        ("qb_change_either", "Either team changed quarterback", False),
        ("backup_start_either", "Either team started a backup", False),
        ("committee_game_either", "Either team used a committee", False),
        ("rivalry", "Recurring rivalry fixture", True),
        ("postseason", "Bowl / postseason", True),
        ("top10_matchup", "Top-10 vs top-10", True),
        ("major_travel", "Visitor travelled 1500+ miles", True),
        ("conference_game_flag", "Conference game", True),
    ]
    rows = []
    for column, label, pre_kickoff in candidates:
        if column not in df.columns:
            continue
        flag = df[column].fillna(False).astype(bool)
        rate_blown = float(flag[blown].mean()) if blown.any() else np.nan
        rate_rest = float(flag[~blown].mean())
        n1, n2 = int(blown.sum()), int((~blown).sum())
        pooled = (flag[blown].sum() + flag[~blown].sum()) / (n1 + n2)
        se = np.sqrt(pooled * (1 - pooled) * (1 / max(n1, 1) + 1 / max(n2, 1)))
        z = (rate_blown - rate_rest) / se if se > 0 else np.nan
        from scipy import stats as _st

        rows.append(
            {
                "characteristic": label,
                "n": n1 + n2,
                "rate_in_blowups": rate_blown,
                "rate_elsewhere": rate_rest,
                "lift": rate_blown / rate_rest if rate_rest > 0 else np.nan,
                "z": z,
                "p": float(2 * _st.norm.sf(abs(z))) if np.isfinite(z) else np.nan,
                "pre_kickoff": pre_kickoff,
            }
        )
    for column, label in (
        ("closing_spread_abs", "Closing spread size"),
        ("weather_wind_effective", "Wind"),
        ("closing_total", "Closing total"),
    ):
        if column not in df.columns:
            continue
        x = pd.to_numeric(df[column], errors="coerce")
        rows.append(
            {
                "characteristic": f"{label} (mean)",
                "rate_in_blowups": float(x[blown].mean()),
                "rate_elsewhere": float(x[~blown].mean()),
                "lift": np.nan,
                "z": np.nan,
                "p": np.nan,
            }
        )
    return pd.DataFrame(rows)


def failure_clusters(df: pd.DataFrame, threshold: int = 28) -> pd.DataFrame:
    """Do blow-ups concentrate in particular conferences or seasons?"""
    error = pd.to_numeric(df[RESIDUAL], errors="coerce").abs()
    sub = df.assign(blown=error >= threshold)
    frames = []
    for dimension in ("home_conference", "season"):
        if dimension not in sub.columns:
            continue
        block = (
            sub.groupby(dimension, observed=True)
            .agg(games=("blown", "size"), blowups=("blown", "sum"))
            .reset_index()
            .rename(columns={dimension: "group"})
        )
        block = block[block["games"] >= 100]
        block["rate"] = block["blowups"] / block["games"]
        overall = float(sub["blown"].mean())
        block["z"] = (block["rate"] - overall) / np.sqrt(
            overall * (1 - overall) / block["games"]
        )
        block.insert(0, "dimension", dimension)
        frames.append(block)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def largest_misses(df: pd.DataFrame, n: int = 15) -> pd.DataFrame:
    columns = [
        "season", "week", "home_team", "away_team", "closing_spread",
        "actual_margin", RESIDUAL, "qb_change_either",
    ]
    available = [c for c in columns if c in df.columns]
    out = df.assign(abs_residual=pd.to_numeric(df[RESIDUAL], errors="coerce").abs())
    return out.nlargest(n, "abs_residual")[[*available, "abs_residual"]]


# ===========================================================================
# Track 6 - Velocity comparison
# ===========================================================================

#: Velocity's published NCAAF walk-forward results, from its own repository
#: (`docs/BACKTEST_NCAAF.md`, EdgeCash/Velocity). Recorded here so the
#: comparison is against stated numbers rather than a paraphrase. Velocity's
#: sample is 2015-2024 and CFBD-sourced; Atlas's is 2018-2025. They are
#: different samples measured by different code, which is exactly what makes
#: agreement informative.
VELOCITY_PUBLISHED = pd.DataFrame(
    [
        {"market": "sides", "threshold": 0, "win_rate": 0.501, "bets": 9518},
        {"market": "totals", "threshold": 0, "win_rate": 0.516, "bets": 9567},
        {"market": "totals", "threshold": 3, "win_rate": 0.523, "bets": 6605},
        {"market": "totals", "threshold": 4, "win_rate": 0.526, "bets": 5630},
        {"market": "totals", "threshold": 6, "win_rate": 0.534, "bets": 3894},
        {"market": "totals", "threshold": 8, "win_rate": 0.530, "bets": 2461},
    ]
)

VELOCITY_SEASON_ROBUSTNESS = "6 of 10 seasons above break-even at the 4-point cut"


def atlas_disagreement_curves(df: pd.DataFrame, margin_features: list[str],
                              total_features: list[str]) -> pd.DataFrame:
    """Run Velocity's test on Atlas's model.

    Phase 1A and 1B asked whether a feature set lowers MAE *on average*. That
    is not the same question as whether a model is right about the games it
    disagrees with the market on most - a model can be worse on average and
    still profitable on a selective cut. Atlas never ran that test; Velocity
    reports an edge from it. So run it here, on Atlas's own out-of-sample
    predictions, and see whether the shape reproduces.
    """
    from atlas.research.dataset import available_features

    frames = []
    for market, features, target, line, outcome in (
        ("sides", margin_features, "actual_margin", "market_margin", "home_cover"),
        ("totals", total_features, "actual_total", "closing_total", "over_hit"),
    ):
        feats = available_features(df, features)
        if not feats:
            continue
        fold = models.leave_one_season_out(df, feats, target)
        if fold.index is None or len(fold.index) == 0:
            continue
        scored = df.iloc[fold.index].copy()
        scored["atlas_prediction"] = fold.y_pred
        curve = rt.disagreement_curve(scored, "atlas_prediction", line, outcome)
        if curve.empty:
            continue
        curve.insert(0, "market", market)
        frames.append(curve)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def disagreement_by_season(df: pd.DataFrame, features: list[str], *, threshold: float = 4.0,
                           target: str = "actual_total", line: str = "closing_total",
                           outcome: str = "over_hit") -> pd.DataFrame:
    """Per-season robustness of a selective cut - the test that kills most edges."""
    from atlas.research.dataset import available_features

    feats = available_features(df, features)
    if not feats:
        return pd.DataFrame()
    fold = models.leave_one_season_out(df, feats, target)
    if fold.index is None or len(fold.index) == 0:
        return pd.DataFrame()
    scored = df.iloc[fold.index].copy()
    scored["atlas_prediction"] = fold.y_pred
    scored = scored.dropna(subset=[line, outcome])
    scored["edge"] = scored["atlas_prediction"] - scored[line]
    live = scored[scored["edge"].abs() >= threshold]
    if live.empty:
        return pd.DataFrame()
    truth = pd.to_numeric(live[outcome], errors="coerce")
    live = live.assign(hit=np.where(live["edge"] > 0, truth, 1 - truth))

    rows = []
    for season, block in live.groupby("season"):
        rate = rt._rate(block["hit"])
        rows.append({"season": int(season), "bets": len(block), **rate})
    out = pd.DataFrame(rows)
    out["above_break_even"] = out["rate"] > rt.BREAK_EVEN
    return out


# ===========================================================================
# Frame assembly
# ===========================================================================


def build_phase1c_frame(raw: Path, staging: Path, warehouse: Path,
                        seasons: list[int]) -> pd.DataFrame:
    """The research sample with every Phase 1C variable attached.

    Quarterback events, situational flags, coaching changes and roster churn
    all land on one frame so every track measures the same games.
    """
    from atlas.research import qb_features
    from atlas.research.dataset import load_research_frame, research_sample
    from atlas.staging import teams as teams_stage

    df = research_sample(load_research_frame(warehouse))
    events = qb_features.build_team_game_events(raw, staging, seasons)
    if not events.empty:
        df = qb_features.to_matchup(events, df)
    df = build_situations(df, raw, seasons)

    teams = teams_stage.load(staging)
    coaches = coach_changes(raw, seasons, teams)
    churn = roster_churn(raw, seasons, teams)
    for side in ("home", "away"):
        if not coaches.empty:
            block = coaches[["season", "team_id", "head_coach_change"]].rename(
                columns={"team_id": f"{side}_team_id",
                         "head_coach_change": f"{side}_hc_change"}
            )
            block[f"{side}_team_id"] = block[f"{side}_team_id"].astype("int64")
            df = df.merge(block, on=["season", f"{side}_team_id"], how="left")
        if not churn.empty:
            block = churn[["season", "team_id", "roster_churn"]].rename(
                columns={"team_id": f"{side}_team_id", "roster_churn": f"{side}_churn"}
            )
            block[f"{side}_team_id"] = block[f"{side}_team_id"].astype("int64")
            df = df.merge(block, on=["season", f"{side}_team_id"], how="left")

    if "home_hc_change" in df.columns:
        df["head_coach_change_signed"] = df["away_hc_change"].fillna(False).astype(int) - df[
            "home_hc_change"
        ].fillna(False).astype(int)
    if "home_churn" in df.columns:
        df["roster_churn_diff"] = df["home_churn"] - df["away_churn"]
    return df.copy()


def _first_finite(row: pd.Series, keys: tuple[str, ...]) -> float:
    """First key present and non-null. Different effect tables name counts
    differently, and a blank column is worse than a merged one."""
    for key in keys:
        value = row.get(key, np.nan)
        if pd.notna(value):
            return float(value)
    return np.nan


def pool_tests(**blocks: pd.DataFrame) -> pd.DataFrame:
    """Gather every p-value in the phase and correct once, together.

    Fifty tests at p < 0.05 produce two or three "findings" from pure noise.
    Pooling them and applying Benjamini-Hochberg is the difference between a
    research programme and a fishing expedition.

    Tests a block marks ``pre_kickoff=False`` are carried but flagged: a
    post-hoc measurement can be highly significant and still be worthless as
    information, so it must never sit unlabelled beside a usable one.
    """
    rows = []
    for track, block in blocks.items():
        if block is None or block.empty or "p" not in block.columns:
            continue
        label_col = next(
            (c for c in ("effect", "characteristic", "model", "group", "measure")
             if c in block.columns),
            None,
        )
        for _, row in block.iterrows():
            if not np.isfinite(row.get("p", np.nan)):
                continue
            rows.append(
                {
                    "track": track,
                    "test": str(row[label_col]) if label_col else "",
                    "n": _first_finite(row, ("n", "n_on", "games", "bets")),
                    "estimate": row.get("mean", row.get("difference", np.nan)),
                    "t": row.get("t", row.get("z", np.nan)),
                    "p": float(row["p"]),
                    "pre_kickoff": bool(row.get("pre_kickoff", True)),
                }
            )
    pooled = pd.DataFrame(rows)
    if pooled.empty:
        return pooled
    # Correct across the usable tests only. Including post-hoc measurements
    # would both inflate the correction and let an artefact appear as a
    # survivor.
    usable = pooled["pre_kickoff"]
    adjusted = rt.fdr_adjust(pooled.loc[usable, "p"])
    pooled["q"] = np.nan
    pooled["survives_fdr"] = False
    pooled.loc[usable, "q"] = adjusted["q"].to_numpy()
    pooled.loc[usable, "survives_fdr"] = adjusted["survives_fdr"].to_numpy()
    return pooled.sort_values(["pre_kickoff", "p"], ascending=[False, True]).reset_index(
        drop=True
    )
