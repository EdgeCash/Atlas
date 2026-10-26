"""The gold and silver 15-minute rule in practice (atlas/polymarket/metals.py): the clock, the model, the
windows read, the positions taken and graded, the owner page, and the worker waking for it."""

from __future__ import annotations

import math
import subprocess
from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from atlas.live.store import Store
from atlas.polymarket import metals, source, worker

END = datetime(2026, 10, 26, 13, 30, tzinfo=UTC)
NOW = END - timedelta(seconds=120)                       # two minutes left


def _event(metal="gold", bid=0.93, ask=0.95, beat=4000.0, end=END, status="MARKET_STATUS_OPEN", series=None):
    start = end - timedelta(minutes=15)
    stamp = end.strftime("%Y-%m-%d-%H%Mz")
    product = "cpausp" if metal == "gold" else "cpagsp"
    return {"slug": f"{metal}-updown-15m-{stamp}", "seriesSlug": series or f"{metal}-updown-15m",
            "markets": [{"slug": f"{product}-{metal}-updown-15m-{stamp}", "status": status, "active": True,
                         "closed": False, "feeCoefficient": 0.0695, "orderPriceMinTickSize": 0.01,
                         "bestBidQuote": {"value": f"{bid:.4f}", "currency": "USD"},
                         "bestAskQuote": {"value": f"{ask:.4f}", "currency": "USD"},
                         "assetPriceTerms": {"asset": {"symbol": metal}, "windowStart": start.isoformat(),
                                             "windowEnd": end.isoformat(),
                                             "priceToBeat": {"value": f"{beat}", "currency": "USD"}}}]}


def test_the_rule_wakes_for_each_windows_final_minutes_only():
    at = lambda seconds_left: END - timedelta(seconds=seconds_left)  # noqa: E731
    assert metals.next_poll(at(120)) == metals.POLL and metals.next_poll(at(300)) == metals.POLL
    assert metals.next_poll(at(301)) == pytest.approx(1.0)              # the stretch starts in a second
    assert metals.next_poll(at(800)) == pytest.approx(500.0)
    assert metals.next_poll(at(3)) == pytest.approx(3 + 900 - 300)      # past the last call: the next window's


def test_the_model_is_a_driftless_lognormal_on_the_last_hours_volatility():
    assert metals.p_up(4000.0, 4000.0, 1e-4, 120) == pytest.approx(0.5)
    sigma = 3.6e-5
    z = math.log(4004.0 / 4000.0) / (sigma * math.sqrt(120))
    assert metals.p_up(4004.0, 4000.0, sigma, 120) == pytest.approx(0.5 * (1 + math.erf(z / math.sqrt(2))))
    assert metals.p_up(4004.0, 4000.0, sigma, 120) > 0.99 and metals.p_up(3996.0, 4000.0, sigma, 120) < 0.01
    assert metals.p_up(4000.0, 4000.0, 0.0, 120) == 1.0 and math.isnan(metals.p_up(4000.0, 4000.0, 1e-4, 0))
    closes = [(1000.0 + 5 * i, 4000.0 * (1.0001 if i % 2 else 1.0)) for i in range(121)]
    r = math.log(1.0001)
    assert metals.volatility(closes) == pytest.approx(math.sqrt(r * r / 5.0))
    assert math.isnan(metals.volatility(closes[:30]))                   # under an hour's worth: no reading
    gappy = [(t + (7 if i == 50 else 0), p) for i, (t, p) in enumerate(closes)]
    assert metals.volatility(gappy) == pytest.approx(math.sqrt(r * r / 5.0))   # a gap is not a return


def test_only_open_metals_windows_in_their_final_stretch_are_read():
    events = [_event("gold"), _event("silver", beat=53.7), _event("gold", end=END + timedelta(minutes=15)),
              _event("gold", status="MARKET_STATUS_CLOSED"), _event("gold", series="gold-updown-1h"),
              {"slug": "usgas-day", "seriesSlug": "usgas", "markets": []}]
    found = metals.windows(events, NOW)
    assert [(w["metal"], w["left"]) for w in found] == [("gold", 120.0), ("silver", 120.0)]
    assert found[0]["ask"] == 0.95 and found[0]["bid"] == 0.93 and found[0]["fee_rate"] == 0.0695
    assert metals.windows(events, END - timedelta(seconds=metals.LAST_CALL)) == []


def test_a_side_the_spot_has_all_but_decided_is_taken_once_per_threshold_with_its_depth():
    reads = []

    def depth(slug, up, ask):
        reads.append((slug, up, ask))
        return 40.0, 120.0
    events = [_event("gold", bid=0.93, ask=0.95, beat=4000.0),                 # spot well above: Up
              _event("silver", bid=0.04, ask=0.06, beat=53.70)]                # spot well below: Down at 0.96
    spot = {"gold": (4004.0, 3.6e-5), "silver": (53.55, 7.8e-5)}.get
    record, added = metals.take(pd.DataFrame(), NOW, events=events, spot=spot, depth=depth)
    by = record.set_index(["metal", "threshold"])
    assert added == 6 and list(record.columns) == metals.COLUMNS
    assert set(record.loc[record["metal"] == "gold", "side"]) == {"up"} and set(record.loc[record["metal"] == "silver", "side"]) == {"down"}
    assert by.loc[("gold", 0.99), "ask"] == 0.95 and by.loc[("silver", 0.99), "ask"] == 0.96
    assert by.loc[("gold", 0.95), "cost"] == pytest.approx(0.95 + 0.0695 * 0.95 * 0.05)
    assert by.loc[("gold", 0.99), "shares_under_cap"] == 120.0 and by.loc[("gold", 0.99), "seconds_left"] == 120.0
    assert len(reads) == 2                                                    # one book read per side, not per threshold
    again, added = metals.take(record, NOW + timedelta(seconds=10), events=events, spot=spot, depth=depth)
    assert added == 0 and len(again) == 6                                     # once per side and threshold
    # Over the cap, or an edge of a cent or less over ask and fee: nothing.
    pricey = [_event("gold", bid=0.97, ask=0.98)]
    assert metals.take(pd.DataFrame(), NOW, events=pricey, spot=spot, depth=depth)[1] == 0
    close = {"gold": (4000.6, 3.6e-5)}.get                                    # model about 0.96 against 0.95 + fee
    assert metals.p_up(4000.6, 4000.0, 3.6e-5, 120) < 0.97
    assert metals.take(pd.DataFrame(), NOW, events=[_event("gold")], spot=close, depth=depth)[1] == 0
    no_vol = {"gold": (4004.0, float("nan"))}.get
    assert metals.take(pd.DataFrame(), NOW, events=[_event("gold")], spot=no_vol, depth=depth)[1] == 0


def test_the_book_is_read_past_the_cache_and_the_down_side_is_the_long_bids(monkeypatch):
    asked = []
    book = {"marketData": {"bids": [{"px": {"value": "0.0400"}, "qty": "30"}, {"px": {"value": "0.0300"}, "qty": "70"},
                                    {"px": {"value": "0.0100"}, "qty": "500"}],
                           "offers": [{"px": {"value": "0.9500"}, "qty": "12"}, {"px": {"value": "0.9700"}, "qty": "8"},
                                      {"px": {"value": "0.9900"}, "qty": "900"}]}}
    monkeypatch.setattr(source, "_get", lambda path, params=None, sess=None, **kw: asked.append((path, params)) or book)
    assert metals.book_depth("m1", True, 0.95) == (12.0, 20.0)
    assert metals.book_depth("m1", True, 0.97) == (20.0, 20.0)                 # at or under the ask, not only at it
    assert metals.book_depth("m1", True, 0.94) == (0.0, 20.0)                  # the quote is gone: nothing to fill
    assert metals.book_depth("m1", False, 0.96) == (30.0, 100.0)               # 1 - 0.04 and 1 - 0.03
    assert asked[0][0] == "/v1/markets/m1/book" and "fresh" in asked[0][1]


def test_positions_are_graded_by_the_venues_settlement_and_a_dollar_order_is_shown(monkeypatch):
    monkeypatch.delenv("ATLAS_OFFLINE", raising=False)
    events = [_event("gold", bid=0.93, ask=0.95), _event("silver", bid=0.04, ask=0.06, beat=53.70)]
    spot = {"gold": (4004.0, 3.6e-5), "silver": (53.55, 7.8e-5)}.get
    record, _ = metals.take(pd.DataFrame(), NOW, events=events, spot=spot, depth=lambda *a: (1.0, 1.0))
    early, n = metals.grade(record, END + timedelta(seconds=30), fetch=lambda slug: 1.0)
    assert n == 0                                                             # a minute's grace after the window
    settled = {"cpausp-gold-updown-15m-2026-10-26-1330z": 1.0, "cpagsp-silver-updown-15m-2026-10-26-1330z": 1.0}
    graded, n = metals.grade(record, END + timedelta(minutes=2), fetch=settled.get)
    assert n == 6
    gold, silver = graded[graded["metal"] == "gold"], graded[graded["metal"] == "silver"]
    assert (gold["won"] == 1.0).all() and (gold["profit"] == 1.0 - gold["cost"]).all()
    assert (silver["payout"] == 0.0).all() and (silver["won"] == 0.0).all()      # Up settled: the Down side lost
    s = metals.summary(graded, ("metal",)).set_index("metal")
    assert s.loc["gold", "losses"] == 0 and s.loc["silver", "losses"] == 3
    # A dollar at 0.95 buys 1.0526 contracts; its fee (0.35¢) rounds to nothing, so a win makes 5.26¢.
    assert s.loc["gold", "dollar_orders"] == pytest.approx(3 * (1 / 0.95 - 1.0), abs=1e-9)
    assert s.loc["silver", "dollar_orders"] == pytest.approx(-3.0)
    sec = metals.section(graded, END + timedelta(minutes=2))
    assert sec["title"] == "Metals 15m, practice (6 of 6 settled)" and sec["tab"] == "Metals 15m"
    assert sec["tables"][0]["title"] == "By model threshold" and "nothing is ordered" in sec["notes"][0]
    assert metals.section(pd.DataFrame(), NOW)["tables"] == []


def test_a_step_writes_the_record_and_the_switch_turns_it_off(tmp_path, monkeypatch):
    monkeypatch.delenv("ATLAS_OFFLINE", raising=False)
    store = Store.open(tmp_path / "tracking")
    kw = {"events": [_event("gold")], "spot": {"gold": (4004.0, 3.6e-5)}.get, "depth": lambda *a: (5.0, 5.0),
          "fetch": lambda slug: 1.0}
    monkeypatch.setenv(metals.MODE, "off")
    assert metals.step(store, NOW, **kw) == {"added": 0, "graded": 0} and store.read(metals.TABLE).empty
    monkeypatch.delenv(metals.MODE)
    assert metals.step(store, NOW, **kw) == {"added": 3, "graded": 0}
    assert metals.step(store, END + timedelta(minutes=2), **{**kw, "events": []}) == {"added": 0, "graded": 3}
    assert (pd.to_numeric(store.read(metals.TABLE)["won"]) == 1.0).all()
    kw["spot"] = lambda metal: (_ for _ in ()).throw(RuntimeError("feed down"))
    assert metals.step(store, NOW + timedelta(minutes=15), **{**kw, "events": [_event("gold", end=END + timedelta(minutes=15))]}) \
        == {"added": 0, "graded": 0}                                          # never raises


def test_the_worker_wakes_for_the_final_minutes_between_its_ticks(tmp_path, monkeypatch):
    monkeypatch.delenv("ATLAS_OFFLINE", raising=False)
    monkeypatch.delenv(metals.MODE, raising=False)
    t = [(END - timedelta(seconds=400)).timestamp()]
    slept, steps = [], []
    monkeypatch.setattr(metals, "step", lambda store, now, sess=None: steps.append(now) or {"added": 0, "graded": 0})

    def sleep(s):
        slept.append(round(s, 3))
        t[0] += s
    reads = worker.rest(180, Store.open(tmp_path), clock=lambda: t[0], sleep=sleep)
    # 100 s to the final stretch, then reads every ten seconds until the three minutes are up.
    assert slept[0] == 100.0 and reads == len(steps) == 8 and sum(slept) == pytest.approx(180)
    monkeypatch.setenv(metals.MODE, "off")
    t[0], slept[:] = (END - timedelta(seconds=400)).timestamp(), []
    assert worker.rest(180, Store.open(tmp_path), clock=lambda: t[0], sleep=sleep) == 0 and slept == [180]


def test_the_worker_merges_the_practice_record_with_the_branchs(tmp_path, monkeypatch):
    monkeypatch.delenv("ATLAS_OFFLINE", raising=False)
    monkeypatch.delenv(worker.BRANCH, raising=False)
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)
    roots = []
    for name in ("worker", "runs"):
        root = tmp_path / name
        subprocess.run(["git", "clone", "-q", str(remote), str(root)], check=True, capture_output=True)
        subprocess.run(["git", "checkout", "-q", "-B", "main"], cwd=root, check=True)
        roots.append(root)
    mine, runs = roots
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@example.com"]
    (runs / "README.md").write_text("atlas\n")
    subprocess.run([*git, "add", "-A"], cwd=runs, check=True)
    subprocess.run([*git, "commit", "-q", "-m", "first"], cwd=runs, check=True)
    subprocess.run(["git", "push", "-q", "origin", "HEAD:main"], cwd=runs, check=True, capture_output=True)
    subprocess.run(["git", "pull", "-q", "origin", "main"], cwd=mine, check=True, capture_output=True)
    spot = {"gold": (4004.0, 3.6e-5), "silver": (53.55, 7.8e-5)}.get
    gold, _ = metals.take(pd.DataFrame(), NOW, events=[_event("gold")], spot=spot, depth=lambda *a: (1.0, 1.0))
    silver, _ = metals.take(pd.DataFrame(), NOW, events=[_event("silver", bid=0.04, ask=0.06, beat=53.70)], spot=spot,
                            depth=lambda *a: (1.0, 1.0))
    Store.open(runs / "tracking").write(metals.TABLE, gold)
    subprocess.run([*git, "add", "-A"], cwd=runs, check=True)
    subprocess.run([*git, "commit", "-q", "-m", "a run's"], cwd=runs, check=True)
    subprocess.run(["git", "push", "-q", "origin", "HEAD:main"], cwd=runs, check=True, capture_output=True)
    Store.open(mine / "tracking").write(metals.TABLE, silver)
    assert worker.publish(mine, NOW) is True
    subprocess.run(["git", "pull", "-q", "origin", "main"], cwd=runs, check=True, capture_output=True)
    merged = Store.open(runs / "tracking").read(metals.TABLE)
    assert sorted(set(merged["metal"])) == ["gold", "silver"] and len(merged) == 6


def test_a_position_the_book_could_not_fill_is_kept_and_left_out_of_the_totals(tmp_path, monkeypatch):
    monkeypatch.delenv("ATLAS_OFFLINE", raising=False)
    spot = {"gold": (4004.0, 3.6e-5), "silver": (53.55, 7.8e-5)}.get
    books = {"cpausp-gold-updown-15m-2026-10-26-1330z": (21.0, 93.0),          # filled at the ask
             "cpagsp-silver-updown-15m-2026-10-26-1330z": (0.0, 0.0)}          # the quote was not in the book
    events = [_event("gold"), _event("silver", bid=0.04, ask=0.06, beat=53.70)]
    record, _ = metals.take(pd.DataFrame(), NOW, events=events, spot=spot, depth=lambda slug, up, ask: books[slug])
    assert record.groupby("metal")["fillable"].agg(set).to_dict() == {"gold": {True}, "silver": {False}}
    unread, _ = metals.take(pd.DataFrame(), NOW, events=[_event("gold")], spot=spot,
                            depth=lambda *a: (_ for _ in ()).throw(RuntimeError("book down")))
    assert unread["fillable"].isna().all()
    record = pd.concat([record, unread.assign(market_slug="other-gold")], ignore_index=True)
    graded, _ = metals.grade(record, END + timedelta(minutes=2), fetch=lambda slug: 0.0)   # Down won everywhere
    s = metals.summary(graded, ("metal",)).set_index("metal")
    assert (s.loc["gold", "taken"], s.loc["gold", "unread"], s.loc["gold", "settled"]) == (6, 3, 3)
    assert s.loc["gold", "losses"] == 3                                        # the three it could have filled lost
    assert (s.loc["silver", "taken"], s.loc["silver", "unfillable"], s.loc["silver", "settled"]) == (3, 3, 0)
    assert math.isnan(s.loc["silver", "dollar_orders"])                        # silver's wins never happened
    # Read back from the record's CSV, the flag still counts.
    store = Store.open(tmp_path)
    store.write(metals.TABLE, graded)
    again = metals.summary(store.read(metals.TABLE), ("metal",)).set_index("metal")
    assert again.loc["silver", "unfillable"] == 3 and again.loc["gold", "settled"] == 3
    rows = metals.section(graded, END + timedelta(minutes=2))["tables"][-1]["rows"]
    assert any(r[-1] == "won, unfillable" for r in rows)
