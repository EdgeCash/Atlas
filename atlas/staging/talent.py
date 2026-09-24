"""Roster talent and programme context: recruiting, returning production, the
head coach and the programme's long-run SP+.

All four are pre-season facts - recruiting classes sign in February, returning
production is fixed once the roster is set, a head coach's hire date is public
before week 1, and the programme mean uses only seasons already played - so the
**same** season's value is point-in-time safe, unlike SP+/FPI.

All come only from CFBD. Without ``CFBD_API_KEY`` the columns exist but are
null, and the research report says so rather than quietly dropping the
variables.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from atlas.sources import cfbd
from atlas.staging import teams as teams_stage
from atlas.util import get_logger, write_parquet

LOG = get_logger(__name__)


def build_talent(raw: Path, staging: Path, games: pd.DataFrame, teams: pd.DataFrame) -> pd.DataFrame:
    seasons = sorted(games["season"].unique())
    out = games[["game_id", "season", "home_team_id", "away_team_id"]].copy()

    recruiting = _season_table(raw, teams, seasons, "recruiting", value_col="rank")
    out = _attach(out, recruiting, "recruiting_rank")

    talent = _season_table(raw, teams, seasons, "talent", value_col="talent")
    out = _attach(out, talent, "talent")

    returning = _season_table(raw, teams, seasons, "returning", value_col="percentPPA")
    out = _attach(out, returning, "returning_production")

    out = _attach(out, _coach_table(raw, teams, seasons), "new_coach")
    out = _attach(out, _program_table(raw, teams, seasons), "sp_program_mean")
    portal = _portal_table(raw, teams, seasons)
    out = _attach(out, portal[["season", "team_id", "value"]], "portal_in")
    out = _attach(out, portal[["season", "team_id", "out"]].rename(columns={"out": "value"}), "portal_out")

    empty = [
        name
        for name, col in (
            ("recruiting", "recruiting_rank_diff"),
            ("talent", "talent_diff"),
            ("returning production", "returning_production_diff"),
            ("coaches", "new_coach_diff"),
            ("SP+ history", "sp_program_mean_diff"),
            ("transfer portal", "portal_in_diff"),
        )
        if out[col].isna().all()
    ]
    if empty:
        hint = "" if cfbd.available() else " (set CFBD_API_KEY)"
        LOG.warning("CFBD-only and null: %s%s", ", ".join(empty), hint)

    write_parquet(out, staging / "talent.parquet")
    return out


def _season_table(
    raw: Path, teams: pd.DataFrame, seasons: list[int], name: str, *, value_col: str
) -> pd.DataFrame:
    resolve = teams_stage.name_resolver(teams)
    frames = []
    for season in seasons:
        path = raw / "cfbd" / f"{name}_{season}.parquet"
        if not path.exists():
            continue
        df = pd.read_parquet(path)
        if df.empty or value_col not in df.columns or "team" not in df.columns:
            continue
        df = df.dropna(subset=["team"])
        df["team_id"] = resolve(season, df["team"])
        df = df.dropna(subset=["team_id"])
        frames.append(
            pd.DataFrame(
                {
                    "season": season,
                    "team_id": df["team_id"].astype("int64"),
                    "value": pd.to_numeric(df[value_col], errors="coerce"),
                }
            )
        )
    if not frames:
        return pd.DataFrame(columns=["season", "team_id", "value"])
    return pd.concat(frames, ignore_index=True).dropna(subset=["value"])


#: A head coach hired on or after 1 September of the previous year opens the
#: season in their first year. An interim who took over mid-season and kept
#: the job is therefore "new" in the following season, not the one they
#: inherited.
NEW_COACH_FROM = "{}-09-01"
#: The season is taken to have opened by mid-August: a coach hired after that
#: replaced someone during the season and never opened it.
SEASON_OPENS = "{}-08-15"


def _coach_table(raw: Path, teams: pd.DataFrame, seasons: list[int]) -> pd.DataFrame:
    """``1.0`` where the team opens the season under a new head coach.

    The opening coach is the one on the season's staff list who was hired
    before the season began. A mid-season replacement is a fact about games
    already played, so it never sets the flag for that season.
    """
    resolve = teams_stage.name_resolver(teams)
    frames = []
    for season in seasons:
        path = raw / "cfbd" / f"coaches_{season}.parquet"
        if not path.exists():
            continue
        df = pd.read_parquet(path)
        if df.empty or "seasons" not in df.columns or "hireDate" not in df.columns:
            continue
        df = df.explode("seasons").dropna(subset=["seasons"]).reset_index(drop=True)
        stints = pd.json_normalize(df["seasons"].tolist())
        if "school" not in stints.columns or "year" not in stints.columns:
            continue
        df = pd.concat([df.drop(columns="seasons"), stints], axis=1)
        df = df[df["year"] == season].dropna(subset=["school"]).copy()
        df["hire"] = pd.to_datetime(df["hireDate"], errors="coerce", utc=True).dt.tz_localize(None)
        df["opened"] = df["hire"].isna() | (df["hire"] <= pd.Timestamp(SEASON_OPENS.format(season)))
        df = (df.sort_values(["school", "opened", "hire"], ascending=[True, False, True])
                .drop_duplicates("school"))
        df["team_id"] = resolve(season, df["school"])
        df = df.dropna(subset=["team_id"])
        new = (df["hire"] >= pd.Timestamp(NEW_COACH_FROM.format(season - 1))).astype(float)
        frames.append(pd.DataFrame({"season": season, "team_id": df["team_id"].astype("int64"),
                                    "value": new.to_numpy()}))
    if not frames:
        return pd.DataFrame(columns=["season", "team_id", "value"])
    return pd.concat(frames, ignore_index=True)


def _program_table(raw: Path, teams: pd.DataFrame, seasons: list[int]) -> pd.DataFrame:
    """Mean SP+ over every season before this one.

    What the programme is, as opposed to what last year's team was: the
    prior regresses a team toward this rather than toward the league mean,
    and a new coach's team harder. Only seasons already played count.
    """
    resolve = teams_stage.name_resolver(teams)
    history = []
    for path in sorted((raw / "cfbd").glob("sp_plus_*.parquet")):
        year = int(path.stem.rsplit("_", 1)[1])
        if year >= max(seasons):
            continue
        df = pd.read_parquet(path)
        if df.empty or "team" not in df.columns or "rating" not in df.columns:
            continue
        df = df.dropna(subset=["team"])
        df["team_id"] = resolve(year, df["team"])
        df = df.dropna(subset=["team_id"])
        history.append(pd.DataFrame({"year": year, "team_id": df["team_id"].astype("int64"),
                                     "rating": pd.to_numeric(df["rating"], errors="coerce")}))
    if not history:
        return pd.DataFrame(columns=["season", "team_id", "value"])
    history = pd.concat(history, ignore_index=True).dropna(subset=["rating"])
    frames = []
    for season in seasons:
        past = history[history["year"] < season]
        if past.empty:
            continue
        mean = past.groupby("team_id")["rating"].mean()
        frames.append(pd.DataFrame({"season": season, "team_id": mean.index.to_numpy(dtype="int64"),
                                    "value": mean.to_numpy()}))
    if not frames:
        return pd.DataFrame(columns=["season", "team_id", "value"])
    return pd.concat(frames, ignore_index=True)


#: A transfer's weight is his 247 composite rating where CFBD has one; where
#: it has only stars, the typical rating for that many; where neither, the
#: floor - most unrated transfers come up from FCS or below.
STAR_RATING = {2: 0.78, 3: 0.84, 4: 0.90, 5: 0.97}
UNRATED_TRANSFER = 0.75
#: The portal opened at its current scale in 2021; CFBD has nothing before.
#: Earlier seasons get zero on both sides - no transfers, not unknown ones -
#: so the prior can be fitted across the boundary.
PORTAL_FIRST_SEASON = 2021


def _portal_table(raw: Path, teams: pd.DataFrame, seasons: list[int]) -> pd.DataFrame:
    """Quality-weighted transfers in (``value``) and out (``out``) per team-season.

    Both are pre-season facts: the portal's windows close before the season.
    Incoming quality is the new information; outgoing is largely what
    returning production already measures.
    """
    resolve = teams_stage.name_resolver(teams)
    files = {s: raw / "cfbd" / f"portal_{s}.parquet" for s in seasons}
    loaded = {s: pd.read_parquet(p) for s, p in files.items() if p.exists()}
    if not any("origin" in df.columns and not df.empty for df in loaded.values()):
        return pd.DataFrame(columns=["season", "team_id", "value", "out"])   # no portal data at all: nothing to stage
    frames = []
    for season in seasons:
        df = loaded.get(season, pd.DataFrame())
        if df.empty or "origin" not in df.columns:
            if season >= PORTAL_FIRST_SEASON:
                continue                                   # no file yet: unknown, not zero
            ids = teams.loc[teams["season"] == season, "team_id"].dropna().astype("int64").unique()
            frames.append(pd.DataFrame({"season": season, "team_id": ids, "value": 0.0, "out": 0.0}))
            continue
        weight = pd.to_numeric(df.get("rating"), errors="coerce")
        weight = weight.fillna(pd.to_numeric(df.get("stars"), errors="coerce").map(STAR_RATING)).fillna(UNRATED_TRANSFER)
        dest = resolve(season, df["destination"].astype("string"))
        origin = resolve(season, df["origin"].astype("string"))
        incoming = weight.groupby(dest).sum()
        outgoing = weight.groupby(origin).sum()
        table = pd.DataFrame({"value": incoming, "out": outgoing}).fillna(0.0)
        table.index.name = "team_id"
        table = table.reset_index()
        table["team_id"] = table["team_id"].astype("int64")
        frames.append(table.assign(season=season)[["season", "team_id", "value", "out"]])
    if not frames:
        return pd.DataFrame(columns=["season", "team_id", "value", "out"])
    return pd.concat(frames, ignore_index=True)


def _attach(out: pd.DataFrame, table: pd.DataFrame, name: str) -> pd.DataFrame:
    if table.empty:
        out[f"home_{name}"] = pd.NA
        out[f"away_{name}"] = pd.NA
        out[f"{name}_diff"] = pd.NA
        return out
    home = table.rename(columns={"team_id": "home_team_id", "value": f"home_{name}"})
    away = table.rename(columns={"team_id": "away_team_id", "value": f"away_{name}"})
    out = out.merge(home, on=["season", "home_team_id"], how="left")
    out = out.merge(away, on=["season", "away_team_id"], how="left")
    # For a rank, "home minus away" is inverted so that positive always means
    # the home side is the stronger one.
    if name.endswith("rank"):
        out[f"{name}_diff"] = out[f"away_{name}"] - out[f"home_{name}"]
    else:
        out[f"{name}_diff"] = out[f"home_{name}"] - out[f"away_{name}"]
    return out


def load(staging: Path) -> pd.DataFrame:
    return pd.read_parquet(staging / "talent.parquet")
