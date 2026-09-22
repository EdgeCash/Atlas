"""Warehouse contracts: schema, outcome definitions, DuckDB, reproducibility."""

from __future__ import annotations

import json

import duckdb
import numpy as np
import pandas as pd
import pytest

from atlas.warehouse import schema


def test_every_required_column_is_present(synthetic_build):
    for table, df in synthetic_build["tables"].items():
        assert schema.check(table, df.columns) == [], f"{table} is missing columns"


def test_required_columns_come_first(synthetic_build):
    for table, df in synthetic_build["tables"].items():
        required = schema.REQUIRED[table]
        assert list(df.columns)[: len(required)] == required


def test_one_row_per_game_everywhere(synthetic_build):
    for table, df in synthetic_build["tables"].items():
        assert df["game_id"].is_unique, f"{table} has duplicate game_id"


def test_cover_definition(synthetic_build):
    tables = synthetic_build["tables"]
    merged = tables["outcomes"].merge(tables["market_lines"], on="game_id")
    live = merged.dropna(subset=["home_cover", "closing_spread"])
    ats = live["actual_margin"] + live["closing_spread"]
    assert ((ats > 0) == (live["home_cover"] == 1)).all()
    assert (ats == 0).sum() == 0 or live.loc[ats == 0, "home_cover"].isna().all()


def test_push_is_recorded_as_null_not_a_loss():
    from atlas.warehouse.build import _outcomes_table

    games = pd.DataFrame({"game_id": [1, 2, 3], "margin": [7, 7, 7],
                          "total_points": [50, 50, 50]})
    market = pd.DataFrame(
        {"game_id": [1, 2, 3], "closing_spread": [-7.0, -3.0, -10.0],
         "closing_total": [50.0, 45.0, 55.0]}
    )
    out = _outcomes_table(games, market).set_index("game_id")
    assert np.isnan(out.loc[1, "home_cover"])  # exact push
    assert out.loc[2, "home_cover"] == 1.0
    assert out.loc[3, "home_cover"] == 0.0
    assert np.isnan(out.loc[1, "over_hit"])  # exact push
    assert out.loc[2, "over_hit"] == 1.0
    assert out.loc[3, "over_hit"] == 0.0


def test_over_result_mirrors_outcomes(synthetic_build):
    tables = synthetic_build["tables"]
    merged = tables["games"][["game_id", "over_result"]].merge(
        tables["outcomes"][["game_id", "over_hit"]], on="game_id"
    )
    pd.testing.assert_series_equal(
        merged["over_result"], merged["over_hit"], check_names=False
    )


def test_efficiency_differences_are_consistent(synthetic_build):
    eff = synthetic_build["tables"]["efficiency_metrics"].dropna(
        subset=["home_off_epa", "away_off_epa"]
    )
    np.testing.assert_allclose(
        eff["off_epa_diff"], eff["home_off_epa"] - eff["away_off_epa"], rtol=1e-9
    )


def test_duckdb_exposes_every_table_and_the_research_view(synthetic_build):
    db = synthetic_build["paths"].duckdb
    con = duckdb.connect(str(db), read_only=True)
    try:
        names = {r[0] for r in con.execute("SHOW TABLES").fetchall()}
        assert set(schema.TABLES).issubset(names)
        n = con.execute("SELECT count(*) FROM research_games").fetchone()[0]
        assert n == len(synthetic_build["tables"]["games"])
    finally:
        con.close()


def test_manifest_records_the_build(synthetic_build):
    manifest = json.loads(
        (synthetic_build["paths"].warehouse / "MANIFEST.json").read_text()
    )
    assert manifest["seasons_present"]
    assert set(manifest["tables"]) == set(schema.TABLES)
    assert manifest["cfbd_enrichment"] in (True, False)


def test_rebuild_is_deterministic(synthetic_build):
    from atlas.warehouse import build as build_mod

    before = {k: v.copy() for k, v in synthetic_build["tables"].items()}
    after = build_mod.build([2019, 2020, 2021, 2022])
    for table in schema.TABLES:
        pd.testing.assert_frame_equal(
            before[table].reset_index(drop=True),
            after[table].reset_index(drop=True),
            check_dtype=False,
        )


def test_missing_required_column_is_a_hard_error():
    assert schema.check("games", ["game_id"]) != []
    with pytest.raises(KeyError):
        schema.check("not_a_table", [])


def test_research_view_carries_every_rating_column(synthetic_build):
    """New rating columns must reach the research view without a SQL edit."""
    ratings = synthetic_build["tables"]["ratings"]
    con = duckdb.connect(str(synthetic_build["paths"].duckdb), read_only=True)
    try:
        view_cols = {d[0] for d in con.execute("SELECT * FROM research_games LIMIT 0").description}
    finally:
        con.close()
    expected = set(ratings.columns) - {"game_id", "season", "home_team_id", "away_team_id"}
    assert expected.issubset(view_cols)
