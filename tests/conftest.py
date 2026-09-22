"""Shared fixtures: a fully synthetic Atlas build, with no network access."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

SEASONS = [2019, 2020, 2021, 2022]


@pytest.fixture(scope="session")
def synthetic_build(tmp_path_factory) -> dict:
    """Run ingest-free staging + warehouse against a synthetic raw tree."""
    from atlas.testing.synthetic import write_synthetic_raw

    base = tmp_path_factory.mktemp("atlas_data")
    write_synthetic_raw(base / "raw", SEASONS)

    os.environ["ATLAS_DATA_DIR"] = str(base)
    from atlas import config
    from atlas.warehouse import build as build_mod

    paths = config.paths().ensure()
    tables = build_mod.build(SEASONS)
    return {"paths": paths, "tables": tables, "base": Path(base)}


@pytest.fixture(scope="session")
def research_frame(synthetic_build):
    from atlas.research.dataset import load_research_frame, research_sample

    return research_sample(load_research_frame(synthetic_build["paths"].warehouse))
