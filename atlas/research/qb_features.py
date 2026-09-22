"""Track 1: quarterback events, classified.

Phase 1B found that *a quarterback change* moves the market residual by about
2 points. That is one blunt flag covering several different things: a backup
coming in for an injured starter, a freshman taking over a rebuild, a
transfer's first start, a committee. Phase 1C separates them, because they
almost certainly are not worth the same.

Every event here is built from the retrospective quarterback of record, so
**none of it is point-in-time** and none of it belongs in the warehouse. What
it measures is the value of knowing, before kickoff, something the
retrospective record tells us after it.

Event vocabulary
----------------

``returning_starter``
    This quarterback started for this team in the previous season.
``new_starter``
    First start for this team, ever, in the window Atlas covers.
``first_year_player``
    First season this quarterback appears on any roster Atlas can see, with
    four seasons of lead-in so 2018 is not structurally "everyone's first".
    This replaces the class-year flag the brief asked for: the roster mirror's
    ``year`` field is **static** - across 5,415 consecutive-season pairs it
    incremented exactly zero times - so it cannot identify a freshman.
``inexperienced_starter``
    Fewer than three career starts anywhere, before this game.
``transfer_starter``
    On another team's roster in a previous season.
``backup_start``
    Not this team's most-used quarterback so far this season.
``qb_change``
    Different quarterback of record than the team's previous game.
``qb_continuity``
    Share of this team's games so far started by this quarterback.
``planned_change``
    A different quarterback than last game who then took ~every snap. If the
    replacement plays the whole game, the decision was made before kickoff -
    so this is the subset of changes a pre-kickoff observer could have known.
``in_game_rotation``
    The quarterback changed *during* this game. Largely caused by the game
    rather than causing it, and the control that makes the rest interpretable.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from atlas.sources import qb_of_record, rosters
from atlas.staging import games as games_stage
from atlas.util import get_logger

LOG = get_logger(__name__)

EVENT_COLUMNS = [
    "qb_change",
    "new_starter",
    "returning_starter",
    "first_year_player",
    "inexperienced_starter",
    "transfer_starter",
    "backup_start",
    "committee_game",
    "planned_change",
    "in_game_rotation",
]

#: Seasons fetched purely as lead-in, so "first season seen" means something
#: in 2018. They are never part of the research sample.
ROSTER_LOOKBACK = 4

#: Career starts below which a quarterback counts as inexperienced.
INEXPERIENCE_THRESHOLD = 3


def _normalise_name(series: pd.Series) -> pd.Series:
    return (
        series.astype("string")
        .str.normalize("NFKD")
        .str.encode("ascii", "ignore")
        .str.decode("ascii")
        .str.replace(r"[^A-Za-z ]", "", regex=True)
        .str.lower()
        .str.strip()
        .str.replace(r"\s+", " ", regex=True)
    )


def build_team_game_events(raw: Path, staging: Path, seasons: list[int]) -> pd.DataFrame:
    """One row per team-game with every quarterback event flagged."""
    qbs = qb_of_record.load(raw, seasons)
    if qbs.empty:
        LOG.warning("no quarterback-of-record data; run atlas.sources.qb_of_record first")
        return pd.DataFrame()

    games = games_stage.load(staging)
    fbs = games[(games["home_division"] == "fbs") & (games["away_division"] == "fbs")]["game_id"]
    long = games_stage.load_long(staging)
    long = long[long["game_id"].isin(fbs)]

    frame = long[
        ["game_id", "season", "week", "kickoff", "team_id", "team", "opponent_id", "is_home"]
    ].merge(
        qbs[["game_id", "team_id", "qb", "qb_share", "qb_attempts", "passers_used"]],
        on=["game_id", "team_id"],
        how="left",
    )
    frame["qb_key"] = _normalise_name(frame["qb"])
    frame = frame.sort_values(["team_id", "season", "kickoff", "game_id"]).reset_index(drop=True)

    grouped = frame.groupby(["team_id", "season"], sort=False)
    frame["prev_qb"] = grouped["qb_key"].shift(1)
    frame["game_number"] = grouped.cumcount() + 1

    frame["qb_change"] = (
        frame["qb_key"].notna() & frame["prev_qb"].notna() & (frame["qb_key"] != frame["prev_qb"])
    )
    frame["committee_game"] = frame["qb_share"].fillna(1.0) < 0.7
    # A replacement who took essentially every snap was named before kickoff;
    # a quarterback who split snaps was pulled during the game. Separating the
    # two separates information from reverse causation.
    frame["planned_change"] = frame["qb_change"] & frame["qb_share"].fillna(0) >= 0.9
    frame["planned_change"] = frame["qb_change"] & (frame["qb_share"].fillna(0) >= 0.9)
    frame["in_game_rotation"] = frame["qb_share"].fillna(1.0) < 0.85

    frame = _add_history_flags(frame)
    frame = _add_roster_flags(raw, frame, seasons)
    frame = _add_experience(frame)
    frame = _add_continuity(frame)
    frame = _add_lagged_events(frame)

    for column in EVENT_COLUMNS:
        if column not in frame.columns:
            frame[column] = False
        frame[column] = frame[column].fillna(False).astype(bool)
    for column in LAGGED_COLUMNS:
        if column in frame.columns:
            frame[column] = frame[column].fillna(False).astype(bool)
    return frame


def _add_history_flags(frame: pd.DataFrame) -> pd.DataFrame:
    """Has this quarterback started for this team before, and when?"""
    known = frame.dropna(subset=["qb_key"]).copy()
    # Two different counters, easy to conflate and wrong if you do: "has this
    # quarterback ever started here" spans seasons, "how settled is the job
    # right now" must not.
    known["starts_before"] = known.groupby(["team_id", "qb_key"], sort=False).cumcount()
    known["starts_before_season"] = known.groupby(
        ["team_id", "season", "qb_key"], sort=False
    ).cumcount()
    frame = frame.merge(
        known[["game_id", "team_id", "starts_before", "starts_before_season"]],
        on=["game_id", "team_id"],
        how="left",
    )
    frame["new_starter"] = frame["starts_before"].eq(0) & frame["qb_key"].notna()

    # Did this quarterback start for this team in the previous season?
    season_starts = (
        known.groupby(["team_id", "qb_key", "season"], as_index=False)
        .size()
        .rename(columns={"size": "starts"})
    )
    season_starts["season"] = season_starts["season"] + 1
    season_starts = season_starts.rename(columns={"starts": "starts_last_season"})
    frame = frame.merge(
        season_starts[["team_id", "qb_key", "season", "starts_last_season"]],
        on=["team_id", "qb_key", "season"],
        how="left",
    )
    frame["returning_starter"] = frame["starts_last_season"].fillna(0) > 0

    # A backup start: not the team's most-used quarterback so far this season.
    season_usage = (
        known.groupby(["team_id", "season", "qb_key"], as_index=False)["qb_attempts"]
        .sum()
        .sort_values(["team_id", "season", "qb_attempts"], ascending=[True, True, False])
    )
    primary = season_usage.groupby(["team_id", "season"], as_index=False).first()
    primary = primary.rename(columns={"qb_key": "primary_qb"})[
        ["team_id", "season", "primary_qb"]
    ]
    frame = frame.merge(primary, on=["team_id", "season"], how="left")
    frame["backup_start"] = (
        frame["qb_key"].notna()
        & frame["primary_qb"].notna()
        & (frame["qb_key"] != frame["primary_qb"])
    )
    return frame


def _add_roster_flags(raw: Path, frame: pd.DataFrame, seasons: list[int]) -> pd.DataFrame:
    """Experience and transfer status, from roster *membership*.

    Deliberately not from the roster's ``year`` column: that field is static
    per player (it never increments between seasons), so it cannot say who is
    a freshman. Membership across seasons can, and it is the same evidence a
    transfer flag needs anyway.
    """
    lookback = list(range(min(seasons) - ROSTER_LOOKBACK, min(seasons)))
    roster = rosters.load(raw, [*lookback, *seasons], position="QB")
    if roster.empty:
        LOG.warning("no roster data; experience and transfer flags will be empty")
        frame["first_year_player"] = False
        frame["transfer_starter"] = False
        return frame

    roster = roster.copy()
    roster["qb_key"] = _normalise_name(roster["player"])
    roster = roster.dropna(subset=["qb_key"])

    first_seen = (
        roster.groupby("qb_key", as_index=False)["season"].min()
        .rename(columns={"season": "first_roster_season"})
    )
    frame = frame.merge(first_seen, on="qb_key", how="left")
    frame["first_year_player"] = frame["season"].eq(frame["first_roster_season"])

    # A transfer appears on a *different* team's roster in an earlier season.
    history = (
        roster.dropna(subset=["qb_key", "team"])[["qb_key", "team", "season"]]
        .drop_duplicates()
        .rename(columns={"team": "prior_team", "season": "prior_season"})
    )
    current = frame[["game_id", "team_id", "season", "team", "qb_key"]].dropna(subset=["qb_key"])
    merged = current.merge(history, on="qb_key", how="left")
    merged = merged[merged["prior_season"] < merged["season"]]
    transferred = (
        merged.assign(is_transfer=merged["prior_team"] != merged["team"])
        .groupby(["game_id", "team_id"], as_index=False)["is_transfer"]
        .max()
        .rename(columns={"is_transfer": "transfer_starter"})
    )
    frame = frame.merge(transferred, on=["game_id", "team_id"], how="left")
    return frame


def _add_experience(frame: pd.DataFrame) -> pd.DataFrame:
    """Career starts before this game, anywhere - transfers keep their history."""
    known = frame["qb_key"].notna()
    ordered = frame.sort_values(["qb_key", "kickoff", "game_id"])
    career = ordered.groupby("qb_key", sort=False).cumcount()
    frame["career_starts_before"] = career.reindex(frame.index)
    frame.loc[~known, "career_starts_before"] = np.nan
    frame["inexperienced_starter"] = frame["career_starts_before"] < INEXPERIENCE_THRESHOLD
    return frame


def _add_continuity(frame: pd.DataFrame) -> pd.DataFrame:
    """How settled the position has been for this team, before this game."""
    known = frame["qb_key"].notna()
    # Distinct starters used so far. Counting first appearances and taking a
    # running sum is both faster and correct on string keys, where an
    # expanding nunique is neither.
    first_appearance = (~frame.duplicated(["team_id", "season", "qb_key"])) & known
    frame["distinct_starters_to_date"] = (
        first_appearance.astype(int).groupby([frame["team_id"], frame["season"]]).cumsum()
    )
    frame["distinct_starters_before"] = (
        frame.groupby(["team_id", "season"], sort=False)["distinct_starters_to_date"]
        .shift(1)
        .fillna(0)
    )
    starts_before = frame["starts_before_season"].fillna(0)
    prior_games = frame["game_number"] - 1
    frame["qb_continuity"] = np.where(
        prior_games > 0,
        np.clip(starts_before / prior_games.replace(0, np.nan), 0, 1),
        np.nan,
    )
    frame.loc[~known, "qb_continuity"] = np.nan
    return frame


#: The same events as they stood *before* kickoff: what happened in the team's
#: previous game. These are genuinely point-in-time and could become features;
#: the contemporaneous versions could not.
LAGGED_COLUMNS = [f"prior_{c}" for c in EVENT_COLUMNS]


def _add_lagged_events(frame: pd.DataFrame) -> pd.DataFrame:
    """Last game's quarterback situation.

    This distinction carries the whole track. A contemporaneous "committee"
    flag is partly *caused by* the result - a team being blown out empties its
    bench, a team winning by forty rests its starter - so a large residual
    effect there may be reverse causation rather than information. The lagged
    version cannot be caused by a game that has not happened yet, so whatever
    effect survives in it is real, usable information.
    """
    grouped = frame.groupby(["team_id", "season"], sort=False)
    for column in EVENT_COLUMNS:
        frame[f"prior_{column}"] = grouped[column].shift(1)
    frame["prior_qb_share"] = grouped["qb_share"].shift(1)
    # Continuity as it stood before this game: it uses the *previous* game's
    # starter, so it needs no knowledge of today's line-up at all.
    frame["prior_qb_continuity"] = grouped["qb_continuity"].shift(1)
    frame["prior_passers_used"] = grouped["passers_used"].shift(1)
    return frame


def to_matchup(events: pd.DataFrame, research: pd.DataFrame) -> pd.DataFrame:
    """Attach the team-game events onto the research frame, per side and signed.

    A home-team event and an away-team event are the same phenomenon mirrored,
    so each flag also gets a signed column: +1 when the event sits with the
    away team (which, if the event is bad for that team, should push the
    residual toward the home side).
    """
    keep = ["game_id", "team_id", *EVENT_COLUMNS, *LAGGED_COLUMNS, "qb_continuity",
            "distinct_starters_before", "career_starts_before", "qb_share", "passers_used",
            "prior_qb_share", "prior_qb_continuity"]
    slim = events[[c for c in keep if c in events.columns]]

    home = slim.rename(columns={"team_id": "home_team_id"})
    home = home.rename(columns={c: f"home_{c}" for c in home.columns if c != "game_id"
                                and c != "home_team_id"})
    away = slim.rename(columns={"team_id": "away_team_id"})
    away = away.rename(columns={c: f"away_{c}" for c in away.columns if c != "game_id"
                                and c != "away_team_id"})

    out = research.merge(home, on=["game_id", "home_team_id"], how="left")
    out = out.merge(away, on=["game_id", "away_team_id"], how="left")

    out = out.copy()
    for column in [*EVENT_COLUMNS, *LAGGED_COLUMNS]:
        h = out[f"home_{column}"].fillna(False).astype(int)
        a = out[f"away_{column}"].fillna(False).astype(int)
        out[f"{column}_signed"] = a - h
        out[f"{column}_either"] = (h + a) > 0
    for column in ("qb_continuity", "prior_qb_continuity", "distinct_starters_before",
                   "career_starts_before"):
        if f"home_{column}" in out and f"away_{column}" in out:
            out[f"{column}_diff"] = out[f"home_{column}"] - out[f"away_{column}"]
    return out
