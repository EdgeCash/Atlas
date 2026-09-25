"""The owner's paper tracker: the live signals graded as flat paper wagers, owner page only."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from atlas.dfs import owner
from atlas.owner import paper


def _signal(sid, game, market, direction, line, *, price=-110.0, selection="primary", book="DraftKings",
            created="2026-09-22T12:00:00+00:00", side="own"):
    return {"signal_id": sid, "created_at": created, "game_id": game, "season": 2026, "week": 4, "market": market,
            "book": book, "open_line": line, "entry_line": line, "entry_price": price, "atlas_number": 0.0,
            "disagreement": 0.0, "direction": direction, "selection": selection, "model_version": "x",
            "entry_price_side": direction if side == "own" else side}


def test_prices_pay_and_break_even_as_the_odds_say():
    assert paper.payout(-110) == pytest.approx(100 / 110) and paper.payout(150) == pytest.approx(1.5)
    assert paper.break_even(-110) == pytest.approx(0.5238, abs=1e-4)
    assert paper.payout(float("nan")) == paper.payout(-110)                 # no price: the standard one


def test_one_wager_per_game_graded_on_the_final_score():
    signals = pd.DataFrame([
        _signal("a", 1, "total", "under", 53.5),
        _signal("a2", 1, "total", "under", 53.5, book="Draft Kings", created="2026-09-23T12:00:00+00:00"),
        _signal("b", 2, "total", "over", 44.5, price=-120),
        _signal("c", 3, "total", "over", 50.0),
        _signal("d", 4, "margin", "home", 7.0, selection="secondary"),
        _signal("e", 5, "total", "over", 60.5),                                # not played yet
    ])
    finals = paper.results(
        pd.DataFrame({"game_id": [1, 2, 3], "actual_margin": [3.0, -7.0, 0.0], "actual_total": [41.0, 44.0, 50.0]}),
        pd.DataFrame({"game_id": [4], "completed": ["True"], "home_score": [24.0], "away_score": [14.0]}))
    grades = pd.DataFrame({"signal_id": ["a", "b"], "clv_points": [1.0, -0.5]})
    w = paper.wagers(signals, finals, grades).set_index("signal_id")
    assert list(w.index) == ["a", "b", "c", "d", "e"]                         # the book-name twin is dropped
    assert w["outcome"].to_dict() == {"a": "win", "b": "loss", "c": "push", "d": "win", "e": "open"}
    assert w.loc["a", "profit"] == pytest.approx(100 / 110) and w.loc["b", "profit"] == -1.0
    assert w.loc["c", "profit"] == 0.0 and w.loc["a", "clv"] == 1.0

    r = paper.record(w.reset_index().query("selection == 'primary'"))
    assert (r["graded"], r["wins"], r["losses"], r["pushes"], r["open"]) == (3, 1, 1, 1, 1)
    assert r["win_rate"] == 0.5 and r["units"] == pytest.approx(100 / 110 - 1)
    # Flat stakes: one win at 100/110 pays for 100/110 of a loss, so break-even
    # is n / sum(1 + payout) - not the mean of the two prices' break-evens.
    assert r["break_even"] == pytest.approx(2 / ((1 + 100 / 110) + (1 + 100 / 120)))
    assert r["decided"] == 2
    assert "Collecting" in paper.verdict(r)


def test_the_verdict_needs_the_full_sample_and_the_interval():
    base = {"graded": paper.MIN_GRADED, "units": 10.0, "break_even": 0.524}
    assert paper.verdict({**base, "win_rate": 0.60, "low": 0.53}).startswith("Clears")
    assert paper.verdict({**base, "win_rate": 0.56, "low": 0.47}).startswith("Not proven")
    assert paper.verdict({**base, "win_rate": 0.50, "low": 0.41}).startswith("Fails")


def test_the_tracker_rides_only_inside_the_ciphertext(tmp_path, monkeypatch):
    """Every word of the tracker is in the sealed payload; the page's public script names none of it."""
    from atlas.dfs import slate
    from atlas.live.store import Store

    store = Store.open(tmp_path)
    store.write("signals", pd.DataFrame([_signal("a", 1, "total", "under", 53.5)]))
    monkeypatch.setenv(owner.SECRET, "horse battery")
    monkeypatch.setenv("ATLAS_TRACKING_DIR", str(tmp_path))
    monkeypatch.setattr(owner, "enc_path", lambda: tmp_path / "owner.enc.json")

    def none():
        raise slate.NoSlate("none")

    monkeypatch.setattr(slate, "run_all", none)
    monkeypatch.setattr("atlas.research.dataset.load_research_frame", lambda: pd.DataFrame(
        {"game_id": [1], "actual_margin": [3.0], "actual_total": [41.0]}))
    owner.refresh(rebuild=False)
    sealed = owner.read(tmp_path / "owner.enc.json")
    assert sealed["box"] is not None                                          # no slate, still opens
    data = json.loads(owner.decrypt(sealed["box"], "horse battery"))
    assert data["slates"] == [] and data["note"] == "No upcoming slate is posted yet."
    assert [s["title"] for s in data["sections"]] == ["Curated plays, rule v1", "Curated plays, rule v2",
                                                      "Paper tracker"]
    tracker = data["sections"][2]
    assert "record" not in tracker
    rows = {r[0]: r[1] for r in tracker["tables"][0]["rows"]}
    assert rows["Won-lost-push"] == "1-0-0" and rows["Graded"] == "1"
    assert "Paper" not in json.dumps(sealed)

    script = (Path(owner.__file__).resolve().parents[1] / "site" / "assets" / "owner.js").read_text().lower()
    for word in ("paper", "wager", "units", "stake", "profit", "break-even", "roi"):
        assert word not in script, word


def test_a_price_counts_only_for_the_side_it_belongs_to():
    signals = pd.DataFrame([
        _signal("u", 1, "total", "under", 50.0, price=+150, side=None),     # before both prices: the over's
        _signal("o", 2, "total", "over", 50.0, price=+150),
    ])
    finals = paper.results(pd.DataFrame({"game_id": [1, 2], "actual_margin": [0.0, 0.0],
                                         "actual_total": [40.0, 60.0]}), pd.DataFrame())
    w = paper.wagers(signals, finals).set_index("signal_id")
    assert w.loc["u", "profit"] == pytest.approx(100 / 110) and bool(w.loc["u", "price_assumed"])
    assert w.loc["o", "profit"] == pytest.approx(1.5) and not bool(w.loc["o", "price_assumed"])


def test_an_older_home_or_over_signal_keeps_its_recorded_price():
    """Before both prices were captured, entry_price was the home side's or
    the over's: the price of a home or over signal, not of an away or under."""
    signals = pd.DataFrame([
        _signal("o", 1, "total", "over", 50.5, price=-125, side=None),
        _signal("u", 2, "total", "under", 50.5, price=-125, side=None),
    ])
    finals = paper.results(pd.DataFrame({"game_id": [1, 2], "actual_margin": [3.0, 3.0],
                                         "actual_total": [55.0, 55.0]}), pd.DataFrame(columns=["game_id"]))
    w = paper.wagers(signals, finals).set_index("signal_id")
    assert w.loc["o", "price"] == -125 and not w.loc["o", "price_assumed"]
    assert w.loc["u", "price"] == paper.DEFAULT_PRICE and w.loc["u", "price_assumed"]
