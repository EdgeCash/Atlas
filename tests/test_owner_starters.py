"""The availability reports' quarterbacks, captured daily, and the starter flag on each curated play."""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pandas as pd

from atlas.live.store import Store
from atlas.owner import plays, starters
from atlas.sources import availability

NOW = datetime(2026, 9, 26, 8, tzinfo=UTC)

PAYLOAD = {"2818": {"ReportType": "Update 1", "publishDate": "2026-09-24", "postedTime": "19:10:00",
                    "conferenceTimeZone": "CT", "conferenceImage": "data:image/png;base64,xx",
                    "games": [{"teamDisplayName": "Georgia", "rows": [
                        {"name": "QB #7 Gunner Stockton", "status": "Out", "exemptStatus": "NonExempt"},
                        {"name": "QB #25 Jake Bobo", "status": "Exempt", "exemptStatus": "Exempt"},
                        {"name": "RB #2 Somebody Else", "status": "Questionable", "exemptStatus": "NonExempt"}]},
                        {"teamDisplayName": "Oklahoma", "rows": [
                            {"name": "QB #10 John Mateer", "status": "Available", "exemptStatus": "NonExempt"}]}]}}


def test_the_reports_are_read_for_their_quarterbacks():
    got = availability.parse(PAYLOAD, "SEC", "2026-09-25T08:00:00+00:00")
    assert list(got["player"]) == ["Gunner Stockton", "Jake Bobo", "John Mateer"]           # no running back
    first = got.iloc[0]
    assert (first["team"], first["opponent"], first["number"], first["status"]) == ("Georgia", "Oklahoma", "7", "Out")
    assert first["report_type"] == "Update 1" and first["publish_date"] == "2026-09-24"


def test_a_capture_keeps_what_one_conference_gives_when_the_other_fails(tmp_path):
    store = Store.open(tmp_path)

    def fetcher(conference):
        if conference == "ACC":
            raise ConnectionError("down")
        return PAYLOAD

    assert availability.capture(store, now=NOW, fetcher=fetcher) == 3
    assert availability.capture(store, now=NOW, fetcher=fetcher) == 0          # a report re-read adds nothing
    assert set(store.read("availability")["conference"]) == {"SEC"}


def _box():
    return pd.DataFrame([
        {"event": "10", "home": 1, "name": "Gunner Stockton", "pass_att": 30, "pass_yds": 250},
        {"event": "10", "home": 0, "name": "Opp Passer", "pass_att": 20, "pass_yds": 150},
        {"event": "11", "home": 0, "name": "John Mateer", "pass_att": 35, "pass_yds": 300},
        {"event": "11", "home": 1, "name": "Other Passer", "pass_att": 25, "pass_yds": 200},
    ])


def _research():
    return pd.DataFrame({"game_id": [10, 11, 20], "home_team": ["Georgia", "Tulsa", "Georgia"],
                         "away_team": ["Austin Peay", "Oklahoma", "Oklahoma"], "season": 2026,
                         "kickoff": ["2026-09-19T16:00:00Z", "2026-09-19T20:00:00Z", "2026-09-26T19:30:00Z"],
                         "season_type": "regular", "actual_margin": [np.nan] * 3, "actual_total": [np.nan] * 3})


def test_each_teams_expected_starter_and_his_reported_status():
    report = availability.parse(PAYLOAD, "SEC", "2026-09-25T08:00:00+00:00")
    got = starters.for_games({"20": ("Georgia", "Oklahoma"), "30": ("Tulsa", "Rice")}, _box(), _research(),
                             report, NOW)
    assert got["20"] == ("Gunner Stockton", "Out", "John Mateer", "Available")
    assert got["30"] == ("Other Passer", "no report", None, "no report")
    assert starters.flagged("Out", "Available") and not starters.flagged("Available", "not listed")
    # A report captured after the moment asked about is not read; nor is last week's.
    assert starters.for_games({"20": ("Georgia", "Oklahoma")}, _box(), _research(), report,
                              datetime(2026, 9, 25, 7, tzinfo=UTC))["20"][1] == "no report"
    assert starters.for_games({"20": ("Georgia", "Oklahoma")}, _box(), _research(), report,
                              datetime(2026, 10, 3, 8, tzinfo=UTC))["20"][1] == "no report"


def test_a_play_carries_the_starter_flag_to_the_page():
    projections = pd.DataFrame([{"game_id": 20, "sport": "ncaaf", "season": 2026, "week": 4,
                                 "kickoff": "2026-09-26T19:30:00Z", "total_mean": 60.0, "model_version": "m",
                                 "refreshed_at": "2026-09-26T07:00:00+00:00"}])
    snapshots = pd.DataFrame([{"captured_at": "2026-09-26T07:00:00+00:00", "game_id": 20, "book": "DraftKings",
                               "market": "total", "line": 50.0, "price": -110.0, "other_price": -110.0,
                               "open_line": 50.0}])
    qbs = {"20": ("Gunner Stockton", "Out", "John Mateer", "Available")}
    got = plays.candidates(plays.RULE_V1, projections, snapshots, pd.DataFrame(), {"20": "regular"}, NOW, set(), qbs)
    assert got.loc[0, ["home_qb", "home_qb_status", "away_qb_status"]].tolist() == ["Gunner Stockton", "Out",
                                                                                   "Available"]
    g = plays.graded(got, pd.DataFrame(columns=["game_id", "final_margin", "final_total"]))
    section = plays.section(plays.RULE_V1, g, NOW, {"20": ("Georgia", "Oklahoma")})
    assert "Georgia QB Gunner Stockton: Out" in section["tables"][0]["rows"][0][0]
    assert any("starter flag" in n for n in section["notes"])


def test_a_report_is_read_in_the_zone_it_was_posted_in():
    a = pd.DataFrame({"publish_date": ["2026-09-24", "2026-09-24"], "posted_time": ["19:10:00", "20:00:00"],
                      "time_zone": ["CT", "ET"]})
    out = starters._published(a)
    assert out.iloc[0] == pd.Timestamp("2026-09-25T00:10:00Z")
    assert out.iloc[1] == pd.Timestamp("2026-09-25T00:00:00Z")
