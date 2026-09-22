"""Collector contracts. No network: the synthetic tree stands in for the feed."""

from __future__ import annotations

import pandas as pd
import pytest
import requests

from atlas.sources import cfbd, espn
from atlas.sources import sportsdataverse as sdv
from atlas.testing.synthetic import write_synthetic_raw
from atlas.util import http_get


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
