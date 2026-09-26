"""Other models' numbers for the card: fetched fresh, logged before kickoff, shown without a verdict."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from atlas.live.store import Store
from atlas.site import data, render
from atlas.sources import other_models as om

NOW = datetime(2026, 9, 26, 3, 0, tzinfo=UTC)


def _payload(margin=13.062, prob=82.24, when="2026-09-25T11:00Z"):
    stat = [{"name": "gameProjection", "value": prob}, {"name": "teamPredPtDiff", "value": margin},
            {"name": "matchupQuality", "value": 86.6}]
    return {"lastModified": when, "homeTeam": {"statistics": stat}}


def test_fpi_is_espns_own_margin_and_chance():
    row = om.fpi_row(_payload())
    assert row["home_margin"] == pytest.approx(13.062)
    assert row["home_win_prob"] == pytest.approx(0.8224)
    assert row["as_of"] == "2026-09-25T11:00Z" and row["model"] == "fpi"
    assert om.fpi_row({"homeTeam": {"statistics": []}}) is None


def test_elo_and_sp_plus_become_home_margins_with_home_points_only_at_home():
    assert om.elo_margin(1863, 1721, neutral=False) == pytest.approx(142 / 24 + 2.6)
    assert om.elo_margin(1863, 1721, neutral=True) == pytest.approx(142 / 24)
    assert om.elo_margin(1700, 1748, neutral=False) == pytest.approx(0.6)        # 48 Elo = 2 points
    assert om.sp_margin(20.0, 5.0, neutral=False) == pytest.approx(17.5)
    assert om.sp_margin(5.0, 20.0, neutral=True) == pytest.approx(-15.0)


def _schedule():
    return pd.DataFrame([
        {"game_id": 1, "home_team": "Alabama", "away_team": "Georgia", "neutral_site": False,
         "home_pregame_elo": 1863.0, "away_pregame_elo": 1721.0},
        {"game_id": 2, "home_team": "Army", "away_team": "Navy", "neutral_site": True,
         "home_pregame_elo": 1500.0, "away_pregame_elo": 1548.0},
        {"game_id": 3, "home_team": "Iowa", "away_team": "Utah", "neutral_site": False,
         "home_pregame_elo": None, "away_pregame_elo": 1600.0},
        {"game_id": 99, "home_team": "Texas", "away_team": "Rice", "neutral_site": False,
         "home_pregame_elo": 1700.0, "away_pregame_elo": 1400.0},
    ])


def test_college_rows_join_elo_by_game_and_sp_plus_by_team_name():
    sp = pd.DataFrame({"team": ["Alabama", "Georgia", "Army", "Navy"], "rating": [25.0, 20.0, -3.0, 1.0]})
    rows = om.college_rows(_schedule(), sp, {1, 2, 3}, "t")
    by = {(r["game_id"], r["model"]): r for r in rows}
    assert by[(1, "elo")]["home_margin"] == pytest.approx(142 / 24 + 2.6)
    assert by[(1, "sp_plus")]["home_margin"] == pytest.approx(7.5)
    assert by[(2, "sp_plus")]["home_margin"] == pytest.approx(-4.0)            # neutral: no home points
    assert "neutral site" in by[(2, "elo")]["detail"]
    assert (3, "elo") not in by                                                 # a missing rating is no number
    assert not any(r["game_id"] == 99 for r in rows)                           # not an upcoming game
    assert om.college_rows(_schedule(), None, {1}, "t") == [by[(1, "elo")]]    # no SP+ without CFBD


def test_one_source_failing_never_costs_the_others(monkeypatch):
    kick = (NOW + timedelta(days=1)).isoformat()
    monkeypatch.setattr(om, "upcoming", lambda now, sport: {1: {"kickoff": kick}} if sport == "ncaaf" else {})
    monkeypatch.setattr(om, "fetch_fpi", lambda sport, ids: {1: om.fpi_row(_payload())})

    def broken(season):
        raise RuntimeError("schedule down")

    monkeypatch.setattr(om, "current_schedule", broken)
    rows = om.collect(NOW)
    assert list(rows["model"]) == ["fpi"]
    assert rows.iloc[0]["sport"] == "ncaaf" and rows.iloc[0]["kickoff"] == kick
    assert rows.iloc[0]["fetched_at"] == NOW.isoformat()


def test_main_records_and_never_fails(monkeypatch, tmp_path):
    monkeypatch.setenv("ATLAS_TRACKING_DIR", str(tmp_path))
    kick = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    monkeypatch.setattr(om, "upcoming", lambda now, sport: {7: {"kickoff": kick}} if sport == "nfl" else {})
    monkeypatch.setattr(om, "fetch_fpi", lambda sport, ids: {7: om.fpi_row(_payload(margin=-3.5, prob=38.0))})
    assert om.main() == 0
    t = Store.open().read(om.TABLE)
    assert len(t) == 1 and t.iloc[0]["sport"] == "nfl" and t.iloc[0]["home_margin"] == pytest.approx(-3.5)

    def explode(now):
        raise RuntimeError("everything is down")

    monkeypatch.setattr(om, "collect", explode)
    assert om.main() == 0


def test_a_card_reads_its_game_in_a_fixed_order(tmp_path, monkeypatch):
    monkeypatch.setenv("ATLAS_TRACKING_DIR", str(tmp_path))
    store = Store.open()
    store.upsert(om.TABLE, pd.DataFrame([
        {"sport": "ncaaf", "game_id": 1, "kickoff": "k", "model": m, "home_margin": 1.0, "home_win_prob": None,
         "as_of": "a", "fetched_at": "f", "detail": None} for m in ("elo", "fpi", "sp_plus")]))
    rows = data.other_models_by_game(store, "ncaaf")[1]
    assert [r["model"] for r in rows] == ["fpi", "sp_plus", "elo"]
    assert rows[0]["home_win_prob"] is None                                   # NaN read back as None
    assert data.other_models_by_game(store, "nfl") == {}


def _card_with(models):
    from test_site import _card

    card = _card()
    card.other_models = models
    return card


def test_the_panel_shows_each_model_beside_atlas_and_the_market(tmp_path):
    from test_site import _page

    from scripts.audit_site import audit

    card = _card_with([
        {"model": "fpi", "home_margin": -9.4, "home_win_prob": 0.24, "as_of": "2026-09-25T11:00Z"},
        {"model": "sp_plus", "home_margin": 3.1, "home_win_prob": None, "as_of": "2026-09-26T08:12:00+00:00"},
        {"model": "elo", "home_margin": 0.0, "home_win_prob": None, "as_of": "2026-09-26T08:12:00+00:00"},
    ])
    panel = render._open_other_models(card)
    away, home = card.away.abbr, card.home.abbr
    assert f"{away} by 9.4" in panel and "76%" in panel                       # the favoured side's chance
    assert f"{home} by 3.1" in panel and "Even" in panel
    assert "Sep 25" in panel and "<b>Atlas</b>" in panel and "Market" in panel
    assert "None of these is an input to Atlas" in panel
    page = _page(card)
    assert "Other models" in page
    (tmp_path / "ncaaf").mkdir()
    (tmp_path / "ncaaf" / "card.html").write_text(page)
    blocking, _ = audit(tmp_path)
    assert blocking["forbidden vocabulary"] == [] and blocking["a named side"] == []


def test_no_numbers_no_panel():
    assert render._open_other_models(_card_with([])) == ""
