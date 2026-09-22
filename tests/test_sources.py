"""Collector contracts. No network: the synthetic tree stands in for the feed."""

from __future__ import annotations

import pandas as pd
import pytest

from atlas.sources import cfbd, espn
from atlas.sources import sportsdataverse as sdv
from atlas.testing.synthetic import write_synthetic_raw


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
