"""Collector contracts. No network: the synthetic tree stands in for the feed."""

from __future__ import annotations

from datetime import UTC

import numpy as np
import pandas as pd
import pytest
import requests

from atlas.sources import cfbd, espn
from atlas.sources import sportsdataverse as sdv
from atlas.testing.synthetic import write_synthetic_raw
from atlas.util import OfflineError, download, http_get


def test_synthetic_tree_matches_expected_source_paths(tmp_path):
    seasons = [2021, 2022]
    write_synthetic_raw(tmp_path / "raw", seasons)
    raw = tmp_path / "raw"
    for season in seasons:
        assert sdv.schedules_path(raw, season).exists()
        assert sdv.team_info_path(raw, season).exists()
        assert sdv.pbp_path(raw, season).exists()
        assert espn.predictor_path(raw, season).exists()
        assert espn.season_fpi_path(raw, season - 1).exists()
    assert sdv.odds_path(raw).exists()


def test_generator_is_deterministic(tmp_path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    write_synthetic_raw(a, [2021])
    write_synthetic_raw(b, [2021])
    left = pd.read_parquet(a / "schedules" / "schedules_2021.parquet")
    right = pd.read_parquet(b / "schedules" / "schedules_2021.parquet")
    pd.testing.assert_frame_equal(left, right)


def test_pbp_trimming_keeps_only_requested_columns(tmp_path):
    write_synthetic_raw(tmp_path / "raw", [2021])
    df = pd.read_parquet(sdv.pbp_path(tmp_path / "raw", 2021))
    assert set(df.columns).issubset(set(sdv.PBP_COLUMNS))
    for required in ("game_id", "EPA", "success", "pos_team", "def_pos_team"):
        assert required in df.columns


def test_cfbd_is_disabled_without_a_key(monkeypatch, tmp_path):
    monkeypatch.delenv("CFBD_API_KEY", raising=False)
    assert cfbd.available() is False
    assert cfbd.fetch_all(tmp_path, [2021]) == {}
    with pytest.raises(RuntimeError, match="CFBD_API_KEY"):
        cfbd._get("/ratings/sp", {"year": 2021})


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code), response=self)


def test_paid_tier_401_becomes_a_distinct_error():
    resp = _FakeResponse(
        401, {"message": "Unauthorized. This endpoint requires a Patreon subscription at Tier 1"}
    )
    with pytest.raises(cfbd.CfbdTierError):
        cfbd._raise_for_tier(resp, "/games/weather")


def test_a_plain_401_is_not_treated_as_a_tier_problem():
    cfbd._raise_for_tier(_FakeResponse(401, {"message": "Unauthorized"}), "/ratings/sp")


def test_settled_http_statuses_are_not_retried(monkeypatch):
    """A 401 must fail immediately; retrying it wastes a minute per season."""
    monkeypatch.delenv("ATLAS_OFFLINE", raising=False)
    calls = {"n": 0}

    class _Session:
        headers: dict = {}

        def get(self, *_a, **_k):
            calls["n"] += 1
            return _FakeResponse(401, {"message": "Unauthorized"})

    with pytest.raises(requests.HTTPError):
        http_get("https://example.invalid/x", sess=_Session(), retries=4)
    assert calls["n"] == 1


def test_retryable_statuses_are_retried(monkeypatch):
    monkeypatch.delenv("ATLAS_OFFLINE", raising=False)
    calls = {"n": 0}
    monkeypatch.setattr("atlas.util.time.sleep", lambda _s: None)

    class _Session:
        headers: dict = {}

        def get(self, *_a, **_k):
            calls["n"] += 1
            return _FakeResponse(503, {})

    with pytest.raises(RuntimeError):
        http_get("https://example.invalid/x", sess=_Session(), retries=2)
    assert calls["n"] == 3


def test_status_file_records_why_a_dataset_is_missing(tmp_path):
    cfbd.record_status(tmp_path, "weather", "needs a paid tier")
    assert cfbd.unavailable_reason(tmp_path, "weather") == "needs a paid tier"
    assert cfbd.unavailable_reason(tmp_path, "sp_plus") is None


def test_offline_mode_blocks_every_network_call(monkeypatch, tmp_path):
    """The suite must fail loudly rather than quietly downloading real data."""
    monkeypatch.setenv("ATLAS_OFFLINE", "1")
    with pytest.raises(OfflineError):
        http_get("https://example.invalid/x")
    with pytest.raises(OfflineError):
        download("https://example.invalid/x", tmp_path / "x.parquet")


def test_offline_mode_still_serves_cached_files(monkeypatch, tmp_path):
    monkeypatch.setenv("ATLAS_OFFLINE", "1")
    cached = tmp_path / "cached.bin"
    cached.write_bytes(b"already here")
    assert download("https://example.invalid/x", cached) == cached


# ---------------------------------------------------------------------------
# nflverse (NFL plan, step 0)
# ---------------------------------------------------------------------------


def _fake_nflverse(monkeypatch, calls: list[str]):
    """Stand in for the release downloads: a tiny parquet per file, logged."""
    from atlas.sources import nflverse

    def fake_download(url, dest, **_):
        if dest.exists() and dest.stat().st_size > 0:      # the real helper serves the cache
            return dest
        calls.append(url)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if "play_by_play" in url:
            frame = pd.DataFrame({"play_id": [1, 2], "game_id": ["2024_01_A_B"] * 2, "epa": [0.1, -0.2],
                                  "desc": ["a long description"] * 2, "season": [2024, 2024]})
        else:
            frame = pd.DataFrame({"season": [2024], "week": [1]})
        frame.to_parquet(dest, index=False)
        return dest

    monkeypatch.setattr(nflverse, "download", fake_download)
    return nflverse


def test_nflverse_trims_play_by_play_and_drops_the_full_file(monkeypatch, tmp_path):
    calls: list[str] = []
    nflverse = _fake_nflverse(monkeypatch, calls)
    path = nflverse.fetch_play_by_play(tmp_path, 2024)
    df = pd.read_parquet(path)
    assert set(df.columns) == {"play_id", "game_id", "epa", "season"}     # desc is not kept
    assert not (tmp_path / "nfl" / "_full_play_by_play_2024.parquet").exists()
    assert nflverse.fetch_play_by_play(tmp_path, 2024) == path and len(calls) == 1   # cached
    nflverse.fetch_play_by_play(tmp_path, 2024, refresh=True)
    assert len(calls) == 2                                                  # refreshed on request


def test_nflverse_fetch_all_refreshes_only_the_current_season(monkeypatch, tmp_path):
    calls: list[str] = []
    nflverse = _fake_nflverse(monkeypatch, calls)
    got = nflverse.fetch_all(tmp_path, [2011, 2024], current=2024)
    assert len(got["schedules"]) == 1
    assert len(got["pbp"]) == 2 and len(got["injuries"]) == 2
    assert len(got["snap_counts"]) == 1                                     # snaps start in 2012
    first = len(calls)
    nflverse.fetch_all(tmp_path, [2011, 2024], current=2024)
    refetched = calls[first:]
    # The season in progress, and the two single files refreshed every run:
    # the schedule and the master player list.
    assert all("2024" in u or "games.parquet" in u or "players.parquet" in u for u in refetched)
    assert not any("2011" in u for u in refetched)


def test_nflverse_one_failure_does_not_stop_the_rest(monkeypatch, tmp_path):
    calls: list[str] = []
    nflverse = _fake_nflverse(monkeypatch, calls)
    real = nflverse.download

    def flaky(url, dest, **kw):
        if "injuries_2024" in url:
            raise RuntimeError("release not cut yet")
        return real(url, dest, **kw)

    monkeypatch.setattr(nflverse, "download", flaky)
    got = nflverse.fetch_all(tmp_path, [2024], current=2024)
    assert got["injuries"] == [] and len(got["pbp"]) == 1


def test_nflverse_current_season_turns_over_in_august():
    from datetime import datetime

    from atlas.sources import nflverse

    assert nflverse.current_season(datetime(2026, 9, 24)) == 2026
    assert nflverse.current_season(datetime(2026, 2, 8)) == 2025
    assert nflverse.current_season(datetime(2026, 8, 1)) == 2026


def test_nflverse_is_offline_safe(monkeypatch, tmp_path):
    from atlas.sources import nflverse

    monkeypatch.setenv("ATLAS_OFFLINE", "1")
    with pytest.raises(OfflineError):
        nflverse.fetch_schedules(tmp_path)


# ---------------------------------------------------------------------------
# sportsdataverse: the season in progress is fetched again, every other is cached
# ---------------------------------------------------------------------------


def _fake_sdv(monkeypatch, calls: list[str]):
    from atlas.sources import sportsdataverse as sdv

    def fake_download(url, dest, **_):
        if dest.exists() and dest.stat().st_size > 0:      # the real helper serves the cache
            return dest
        calls.append(url)
        dest.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame({"game_id": [1], "season": [2026], "EPA": [0.1]}).to_parquet(dest, index=False)
        return dest

    monkeypatch.setattr(sdv, "download", fake_download)
    return sdv


def test_college_files_are_cached_unless_refreshed(monkeypatch, tmp_path):
    """A schedule fetched in week 3 carried week 3's results all season: the
    filter behind every college projection assimilated the same games at every
    refresh. ``refresh`` is how the season in progress gains its results."""
    calls: list[str] = []
    sdv = _fake_sdv(monkeypatch, calls)
    path = sdv.fetch_schedules(tmp_path, 2026)
    assert sdv.fetch_schedules(tmp_path, 2026) == path and len(calls) == 1          # cached
    sdv.fetch_schedules(tmp_path, 2026, refresh=True)
    assert len(calls) == 2                                                          # fetched again
    sdv.fetch_odds(tmp_path)
    sdv.fetch_odds(tmp_path)
    sdv.fetch_odds(tmp_path, refresh=True)
    assert len(calls) == 4
    sdv.fetch_play_by_play(tmp_path, 2026)
    sdv.fetch_play_by_play(tmp_path, 2026)
    assert len(calls) == 5
    sdv.fetch_play_by_play(tmp_path, 2026, refresh=True)
    assert len(calls) == 6


def test_college_current_season_turns_over_in_august():
    from datetime import datetime

    from atlas.sources import sportsdataverse as sdv

    assert sdv.current_season(datetime(2026, 9, 26)) == 2026
    assert sdv.current_season(datetime(2027, 1, 12)) == 2026
    assert sdv.current_season(datetime(2026, 8, 1)) == 2026


def test_ingest_refreshes_only_the_season_in_progress(monkeypatch, tmp_path):
    from atlas import ingest

    monkeypatch.setenv("ATLAS_DATA_DIR", str(tmp_path))
    seen: list[tuple] = []
    monkeypatch.setattr(ingest.sdv, "fetch_odds", lambda raw, refresh=False: seen.append(("odds", None, refresh)))
    monkeypatch.setattr(ingest.sdv, "fetch_schedules",
                        lambda raw, season, refresh=False: seen.append(("schedules", season, refresh)))
    monkeypatch.setattr(ingest.sdv, "fetch_team_info",
                        lambda raw, season, refresh=False: seen.append(("team_info", season, refresh)))
    monkeypatch.setattr(ingest.sdv, "fetch_play_by_play",
                        lambda raw, season, refresh=False: seen.append(("pbp", season, refresh)))
    monkeypatch.setattr(ingest.espn, "fetch_season_fpi", lambda raw, season: None)
    monkeypatch.setattr(ingest.rosters, "fetch", lambda raw, season: None)
    manifest = ingest.ingest([2024, 2026], with_pbp=True, with_predictors=False, with_cfbd=False, current=2026)
    assert manifest["current_season"] == 2026
    assert ("schedules", 2026, True) in seen and ("schedules", 2024, False) in seen
    assert ("team_info", 2026, True) in seen and ("team_info", 2024, False) in seen
    assert ("pbp", 2026, True) in seen and ("pbp", 2024, False) in seen
    assert ("odds", None, True) in seen                                             # one file, every season


# ---------------------------------------------------------------------------
# Open-Meteo: the kickoff wind a scheduled game's total assumes
# ---------------------------------------------------------------------------


class _Forecast:
    """Stands in for http_get: one hourly series per point, logged."""

    def __init__(self, speeds_by_hour: dict[str, float]):
        self.calls: list[dict] = []
        self.speeds = speeds_by_hour

    def __call__(self, url, *, sess=None, params=None, timeout=30):
        self.calls.append(dict(params))
        assert params["wind_speed_unit"] == "mph" and params["timezone"] == "UTC"
        times = list(self.speeds)

        class R:
            def json(inner):
                return {"hourly": {"time": times, "wind_speed_10m": [self.speeds[t] for t in times]}}
        return R()


def test_kickoff_wind_is_the_hour_nearest_kickoff_and_zero_indoors():
    from datetime import datetime

    from atlas.sources import forecast

    now = datetime(2026, 9, 24, 12, tzinfo=UTC)
    http = _Forecast({"2026-09-26T15:00": 4.0, "2026-09-26T16:00": 14.5, "2026-09-26T17:00": 9.0})
    games = pd.DataFrame({"game_id": [1, 2, 3, 4],
                          "kickoff": ["2026-09-26T16:10:00Z", "2026-09-26T16:00:00Z", "2026-10-20T16:00:00Z",
                                      "2026-09-27T02:00:00Z"],
                          "venue_id": [10, 20, 10, 10], "venue_dome": [False, True, False, False]})
    venues = pd.DataFrame({"venue_id": [10, 20], "latitude": [33.95, 44.97], "longitude": [-83.37, -93.26],
                           "dome": [False, True]})
    got = forecast.kickoff_wind(games, venues, now, http=http).set_index("game_id")
    assert got.loc[1, "wind_mph"] == 14.5                      # nearest hour
    assert got.loc[2, "wind_mph"] == 0.0                       # a dome, no request made for it
    assert 3 not in got.index                                  # beyond the horizon
    assert 4 not in got.index                                  # no forecast hour within two hours
    assert len(http.calls) == 1 and http.calls[0]["latitude"] == 33.95       # one request per outdoor venue
    attached = forecast.attach(games.assign(weather_wind_effective=np.nan), venues, now, http=http)
    by = attached.set_index("game_id")
    assert by.loc[1, "weather_wind_effective"] == 14.5 and by.loc[1, "wind_mph"] == 14.5
    assert by.loc[2, "weather_wind_effective"] == 0.0
    assert np.isnan(by.loc[3, "weather_wind_effective"]) and np.isnan(by.loc[3, "wind_mph"])


def test_a_failed_forecast_leaves_the_projection_its_fallback():
    from datetime import datetime

    from atlas.sources import forecast

    def boom(url, **_):
        raise RuntimeError("open-meteo down")
    games = pd.DataFrame({"game_id": [1], "kickoff": ["2026-09-26T16:00:00Z"], "venue_id": [10]})
    venues = pd.DataFrame({"venue_id": [10], "latitude": [33.95], "longitude": [-83.37]})
    out = forecast.attach(games, venues, datetime(2026, 9, 24, tzinfo=UTC), http=boom)
    assert np.isnan(out["wind_mph"].iloc[0]) and "weather_wind_effective" not in out.columns or \
        np.isnan(out["weather_wind_effective"].iloc[0])


def test_forecast_is_offline_safe(monkeypatch):
    from datetime import datetime

    from atlas.sources import forecast

    monkeypatch.setenv("ATLAS_OFFLINE", "1")
    games = pd.DataFrame({"game_id": [1], "kickoff": ["2026-09-26T16:00:00Z"], "venue_id": [10]})
    venues = pd.DataFrame({"venue_id": [10], "latitude": [33.95], "longitude": [-83.37]})
    assert forecast.kickoff_wind(games, venues, datetime(2026, 9, 24, tzinfo=UTC)).empty   # logged, not raised
