"""Pick'em: PrizePicks' standard lines priced on the books' props, slips optimised, logged once, graded."""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime

import pandas as pd
import pytest

from atlas.owner import pickem, sealed
from atlas.sources import bettingpros as bp

KEY = "correct horse battery staple"
NOW = datetime(2026, 9, 27, 14, 4, tzinfo=UTC)                 # Sunday 10:04 ET
KICK = pd.Timestamp("2026-09-27T17:00:00Z")
MARKET_IDS = {102: "passing-yards", 103: "rushing-yards", 104: "receiving-yards", 105: "receptions"}


def _q(event, key, player, market, book, side, line, cost, *, team="ATL", position="WR", kickoff=KICK):
    return {"captured_at": "2026-09-27T14:04:00+00:00", "sport": "nfl", "event_id": event, "market": market,
            "player_key": key, "player": player, "position": position, "team": team, "selection": side,
            "book_id": book, "line": line, "cost": cost, "updated": "2026-09-27 13:30:00", "main": True,
            "game_id": f"g{event}", "kickoff": kickoff, "day": "2026-09-27"}


def _prop(event, key, player, market, books: dict, pp=None, **kw):
    """Rows for one prop: each book's (line, over price, under price); PrizePicks' line, or ("more", line)
    for a line offered More only."""
    rows = []
    for book, (line, over, under) in books.items():
        rows += [_q(event, key, player, market, book, "over", line, over, **kw),
                 _q(event, key, player, market, book, "under", line, under, **kw)]
    if isinstance(pp, tuple):
        rows.append(_q(event, key, player, market, bp.PRIZEPICKS, "over", pp[1], -119, **kw))
    elif pp is not None:
        rows += [_q(event, key, player, market, bp.PRIZEPICKS, side, pp, -119, **kw) for side in ("over", "under")]
    return rows


def _slate_props() -> pd.DataFrame:
    rows = []
    # Four games, a pick in each; PrizePicks' line off the books' by a few yards or at a book's line.
    rows += _prop(101, "p1", "Drake London", "receiving-yards",
                  {12: (70.5, -115, -105), 10: (70.5, -110, -110), 49: (71.5, -110, -110),
                   0: (70.5, -500, 300), 36: (50.5, -110, -110)}, pp=62.5)
    rows += _prop(102, "p2", "Bijan Robinson", "rushing-yards",
                  {12: (80.5, -110, -110), 13: (80.5, -105, -115)}, pp=92.5, position="RB")
    rows += _prop(103, "p3", "Jordan Love", "passing-yards",
                  {12: (245.5, -110, -110), 10: (246.5, -115, -105), 38: (245.5, -102, 102)}, pp=229.5,
                  team="GB", position="QB")
    rows += _prop(104, "p4", "Jahan Dotson", "receptions", {12: (3.5, -140, 110), 18: (3.5, -145, 115)}, pp=3.5)
    # A second pick in the first game, a More-only line (a demon), and a line only one book prices.
    rows += _prop(101, "p5", "Bijan Robinson Jr.", "receptions", {12: (2.5, -160, 125), 19: (2.5, -150, 120)}, pp=2.5,
                  position="RB")
    rows += _prop(102, "p6", "Kyle Pitts", "receiving-yards", {12: (40.5, -110, -110), 10: (40.5, -110, -110)},
                  pp=("more", 55.5))
    rows += _prop(103, "p7", "Romeo Doubs", "receiving-yards", {12: (45.5, -110, -110)}, pp=45.5, team="GB")
    return pd.DataFrame(rows)


def _games(completed=False) -> pd.DataFrame:
    return pd.DataFrame([{"game_id": f"g{e}", "season": 2026, "week": 3, "kickoff": "2026-09-27T17:00Z",
                          "home_team": f"Home {e}", "away_team": f"Away {e}", "completed": completed}
                         for e in (101, 102, 103, 104)])


NAMES = {f"g{e}": f"Away {e} @ Home {e}" for e in (101, 102, 103, 104)}


# ---------------------------------------------------------------------------
# BettingPros' prop offers
# ---------------------------------------------------------------------------


def _line(line, cost, *, main=True, off=False, replaced=False, updated="2026-09-27 13:00:00"):
    return {"main": main, "active": True, "replaced": replaced, "is_off": off, "line": line, "cost": cost,
            "updated": updated, "best": False}


def _offer(event, market_id, pid, name, books):
    """A prop offer in the API's shape: {book: ([over lines], [under lines])}."""
    return {"id": f"o{pid}{market_id}", "market_id": market_id, "event_id": event, "player_id": pid, "active": True,
            "participants": [{"id": pid, "name": name, "player": {"first_name": name.split()[0],
                                                                   "last_name": name.split()[-1], "position": "WR",
                                                                   "team": "ATL"}}],
            "selections": [{"selection": side, "label": side.title(), "books": [
                {"id": b, "lines": lines[i]} for b, lines in books.items()]} for i, side in enumerate(("over", "under"))]}


class _Client:
    """BettingPros' markets and prop offers, two pages of them, and a count of calls."""

    def __init__(self, offers=None):
        self.calls, self.seen = 0, []
        self.offers = offers

    def get(self, path, **params):
        self.calls += 1
        self.seen.append((path, params))
        if path == "/markets":
            return {"markets": [{"id": 1, "slug": "spread", "category": "game-odds"},
                                *({"id": i, "slug": s, "category": "player-props"} for i, s in MARKET_IDS.items()),
                                {"id": 999, "slug": "anytime-td", "category": "player-props"}]}
        assert path == "/offers"
        offers = self.offers if self.offers is not None else [
            _offer(101, 104, "p1", "Drake London", {12: ([_line(70.5, -115)], [_line(70.5, -105)]),
                                                    10: ([_line(70.5, -110)], [_line(70.5, -110)]),
                                                    37: ([_line(62.5, -119), _line(55.5, -119, main=False)],
                                                         [_line(62.5, -119)])})]
        page = int(params.get("page", 1))
        return {"_parameters": {"key": "SECRET-MUST-NOT-SURVIVE"}, "offers": offers if page == 1 else [],
                "_pagination": {"total_pages": 2}}


def test_prop_offers_are_parsed_to_each_books_current_line_per_side():
    offers = [_offer(101, 104, "p1", "Drake London", {
        12: ([_line(71.5, -110, replaced=True), _line(70.5, -115)], [_line(70.5, -105)]),
        10: ([_line(70.5, -110, off=True)], [_line(70.5, -110)]),                       # over gone off
        37: ([_line(62.5, -119), _line(55.5, -119, main=False)], [_line(62.5, -119)])}),  # a goblin beside it
        {**_offer(101, 999, "p9", "Someone Else", {12: ([_line(0.5, 150)], [_line(0.5, -200)])})}]  # not asked for
    got = bp.parse_props({"offers": offers}, "nfl", MARKET_IDS, "t")
    assert set(got["market"]) == {"receiving-yards"} and set(got["player"]) == {"Drake London"}
    dk = got[got["book_id"] == 12].set_index("selection")
    assert dk.loc["over", "line"] == 70.5 and dk.loc["over", "cost"] == -115              # the replaced line is not read
    assert len(got[got["book_id"] == 10]) == 1                                             # the off side is dropped
    pp = got[got["book_id"] == 37].set_index("selection")
    assert pp.loc["over", "line"] == 62.5 and pp.loc["under", "line"] == 62.5             # the main line, not the goblin


def test_props_are_fetched_a_dozen_events_a_request_every_page_and_counted(caplog):
    client = _Client()
    with caplog.at_level("INFO", logger="atlas.sources.bettingpros"):
        got = bp.props(client, "nfl", list(range(1, 15)), MARKET_IDS)
    offers = [p for path, p in client.seen if path == "/offers"]
    assert len(offers) == 4                                                    # two batches of events, two pages each
    assert offers[0]["market_id"] == "102:103:104:105" and offers[0]["limit"] == 50
    assert offers[0]["event_id"].count(":") == 11 and offers[2]["event_id"] == "13:14"
    assert len(got) == 2 * 6 and "_parameters" not in json.dumps(got.to_dict("records"), default=str)
    assert "cap cut" not in caplog.text
    with caplog.at_level("INFO", logger="atlas.sources.bettingpros"):
        capped = bp.props(_Client(), "nfl", list(range(1, 15)), MARKET_IDS, max_pages=3)
    assert "the 3-page cap cut the latest games" in caplog.text                  # the second batch's page two
    assert len(capped) == 2 * 6                                                # page three is the second batch's first
    assert bp.props(_Client(), "nfl", [], MARKET_IDS).empty and bp.props(_Client(), "nfl", [1], {}).empty


def test_the_prop_markets_are_found_by_slug():
    assert bp.prop_markets(_Client(), "nfl") == MARKET_IDS


# ---------------------------------------------------------------------------
# Shapes and fair value
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("stat,line,p", [("rec_yds", 50.5, 0.5), ("pass_yds", 245.5, 0.55), ("rush_yds", 60.5, 0.45),
                                         ("rec", 4.5, 0.5), ("rec", 4.0, 0.52), ("rec_yds", 50.0, 0.48)])
def test_a_centre_puts_the_books_line_at_its_probability(stat, line, p):
    c = pickem.centre_for(stat, line, p)
    over, tie = pickem.split(stat, c, line)
    assert over / (1.0 - tie) == pytest.approx(p, abs=2e-3)
    lower, _ = pickem.split(stat, c, line - 3.0 if stat != "rec" else line - 1.0)
    assert lower > over                                                        # a lower line goes over more often


def test_moving_a_line_is_worth_what_the_stats_spread_says():
    c = pickem.centre_for("rec_yds", 70.5, 0.5)
    assert pickem.split("rec_yds", c, 62.5)[0] == pytest.approx(0.575, abs=0.02)       # eight yards: about 7 points
    c = pickem.centre_for("rec", 4.5, 0.5)
    over, tie = pickem.split("rec", c, 4.0)                                             # a whole number can tie
    assert over == pytest.approx(0.5, abs=1e-4) and tie == pytest.approx(0.18, abs=0.02)
    assert pickem.split("rec", c, 3.5)[0] == pytest.approx(0.68, abs=0.02)


def test_fair_value_is_the_median_of_the_books_moved_to_the_line_consensus_and_pickem_apps_left_out():
    props = _slate_props()
    london = props[props["player_key"] == "p1"]
    fair = pickem.fair_at(london, "rec_yds", 70.5)
    dk = 0.5454545 / (0.5454545 + 0.5122)                                       # -115 / -105, margin out
    hr = pickem.split("rec_yds", pickem.centre_for("rec_yds", 71.5, 0.5), 70.5)[0]
    assert fair["books"] == 3 and fair["p_over"] == pytest.approx(sorted([dk, 0.5, hr])[1], abs=1e-3)
    assert fair["book_line"] == 70.5 and fair["p_push"] == 0.0
    assert pickem.fair_at(props[props["player_key"] == "p7"], "rec_yds", 45.5) is None      # one book is not enough
    far = pd.DataFrame(_prop(101, "x", "X Y", "receiving-yards", {12: (70.5, -110, -110), 10: (100.5, -110, -110)}))
    assert pickem.fair_at(far, "rec_yds", 70.5) is None                                        # 30 yards off: not moved


def test_prizepicks_standard_lines_are_priced_and_more_only_lines_left_out():
    priced, counts = pickem.price(_slate_props())
    assert counts == {"lines": 7, "more_only": 1, "unpriced": 1}
    by = priced.set_index("player_key")
    assert by.loc["p1", "side"] == "over" and by.loc["p1", "p"] > 0.55                  # 62.5 under the books' 70.5
    assert by.loc["p2", "side"] == "under" and by.loc["p2", "p"] > 0.55                 # 92.5 over the books' 80.5
    assert by.loc["p3", "side"] == "over" and by.loc["p4", "side"] == "over"
    assert list(priced["p"]) == sorted(priced["p"], reverse=True)


# ---------------------------------------------------------------------------
# Payouts, slips, and the optimizer
# ---------------------------------------------------------------------------


def test_payouts_follow_the_entry_and_drop_ties_and_no_plays_to_the_next_size():
    t = pickem.PAYOUTS
    assert pickem.multiple("power", 3, 3, 0, t) == 5.0 and pickem.multiple("power", 3, 2, 0, t) == 0.0
    assert pickem.multiple("power", 3, 2, 1, t) == 3.0                              # a tie: a two-pick Power
    assert pickem.multiple("flex", 3, 2, 1, t) == 3.0                               # a Flex left with two: Power
    assert pickem.multiple("flex", 5, 3, 0, t) == 0.4 and pickem.multiple("flex", 6, 4, 1, t) == 2.0
    assert pickem.multiple("power", 2, 1, 1, t) == 1.0                              # one left: refunded
    logged = json.loads(json.dumps(t))                                                # string keys, as sealed
    assert pickem.multiple("flex", 6, 6, 0, logged) == 25.0


def test_a_slips_value_and_kelly_stake_are_exact_for_simple_cases():
    dist = pickem.returns([(0.6, 0.0), (0.6, 0.0)], "power", pickem.PAYOUTS)
    assert sum(q * m for q, m in dist) - 1.0 == pytest.approx(0.08)
    f, g = pickem.kelly(dist)
    assert f == pytest.approx(0.04, abs=1e-4)                                         # (b p - q) / b, b = 2
    assert g == pytest.approx(0.36 * math.log(1.08) + 0.64 * math.log(0.96), abs=1e-6)
    assert pickem.kelly(pickem.returns([(0.5, 0.0)] * 2, "power", pickem.PAYOUTS)) == (0.0, 0.0)
    assert pickem.break_even("power", 2) == pytest.approx(3 ** -0.5, abs=1e-4)
    assert 0.53 < pickem.break_even("flex", 6) < pickem.break_even("power", 6) < pickem.break_even("power", 2)


def test_the_optimizer_takes_the_best_picks_one_per_game():
    priced, _ = pickem.price(_slate_props())
    chosen = pickem.optimize(priced)
    assert len(chosen) and list(chosen["growth"]) == sorted(chosen["growth"], reverse=True)
    for s in chosen.itertuples():
        games = [priced.loc[k, "game_id"] for k in s.keys]
        assert len(games) == len(set(games)) == s.n and s.ev > 0 and 0 < s.kelly < 1
    two = chosen[(chosen["kind"] == "power") & (chosen["n"] == 2)]
    if len(two):
        best = priced[priced["p"] >= pickem.PICK_FLOOR].drop_duplicates("game_id").head(2)
        assert set(two.iloc[0]["keys"]) == set(best.index)
    assert pickem.optimize(priced.iloc[0:0]).empty


# ---------------------------------------------------------------------------
# The record
# ---------------------------------------------------------------------------


def test_the_day_is_logged_once_from_ten_eastern_sealed_and_followed_to_kickoff(tmp_path):
    priced, _ = pickem.price(_slate_props())
    chosen = pickem.optimize(priced)
    picks = pd.DataFrame(columns=pickem.PICK_COLUMNS)
    slips = pd.DataFrame(columns=pickem.SLIP_COLUMNS)
    assert not pickem.due(picks, "2026-09-27", datetime(2026, 9, 27, 13, 50, tzinfo=UTC))    # 9:50 ET
    assert pickem.due(picks, "2026-09-27", NOW)
    picks, slips, weeks = pickem.log(picks, slips, priced, chosen, _games(), NAMES, NOW)
    assert weeks == {(2026, 3)} and len(picks) == int((priced["p"] >= pickem.PICK_FLOOR).sum()) and len(slips) == len(chosen)
    assert not pickem.due(picks, "2026-09-27", NOW)
    again, _, none = pickem.log(picks, slips, priced, chosen, _games(), NAMES, NOW)
    assert none == set() and len(again) == len(picks)                                       # never twice
    names = [*picks["player"], *picks["game"]]
    pickem.seal(picks, KEY, weeks, tmp_path / "p", pickem.PICK_COLUMNS, names)
    pickem.seal(slips, KEY, weeks, tmp_path / "s", pickem.SLIP_COLUMNS, names)
    text = (tmp_path / "p" / "2026-03.enc.json").read_text()
    assert "Drake London" not in text and "62.5" not in text
    loaded = pickem.load(KEY, tmp_path / "p", pickem.PICK_COLUMNS)
    assert list(loaded["pick_id"]) == list(picks["pick_id"])
    assert json.loads(pickem.load(KEY, tmp_path / "s", pickem.SLIP_COLUMNS)["payouts"][0]) == json.loads(
        json.dumps(pickem.PAYOUTS))
    # The books move toward London's over before kickoff: the close follows at the logged line.
    moved = _slate_props()
    moved.loc[(moved["player_key"] == "p1") & (moved["book_id"].isin([10, 12, 49])) & (moved["selection"] == "over"),
              "cost"] = -140
    later = datetime(2026, 9, 27, 16, 30, tzinfo=UTC)
    followed, changed = pickem.follow(loaded, moved, later)
    london = followed[followed["player_key"] == "p1"].iloc[0]
    assert changed == {(2026, 3)} and london["close_p"] > london["p"] and london["close_line"] == 62.5
    after, nothing = pickem.follow(followed, _slate_props(), datetime(2026, 9, 27, 17, 5, tzinfo=UTC))
    assert nothing == set() and after.equals(followed)                                     # kicked off: closed


def test_picks_are_graded_from_the_box_score_and_slips_settle_on_them():
    priced, _ = pickem.price(_slate_props())
    picks, slips, _ = pickem.log(pd.DataFrame(columns=pickem.PICK_COLUMNS), pd.DataFrame(columns=pickem.SLIP_COLUMNS),
                                 priced, pickem.optimize(priced), _games(), NAMES, NOW)
    boxes = {"g101": pd.DataFrame([{"name": "Drake London", "rec_yds": 80.0, "rec": 7.0, "rush_yds": 0.0, "pass_yds": 0.0},
                                   {"name": "Bijan Robinson", "rec_yds": 10.0, "rec": 2.0, "rush_yds": 90.0,
                                    "pass_yds": 0.0}]),
             "g102": pd.DataFrame([{"name": "Bijan Robinson", "rec_yds": 0.0, "rec": 0.0, "rush_yds": 92.5,
                                    "pass_yds": 0.0}]),
             "g103": pd.DataFrame([{"name": "J. Love", "rec_yds": 0.0, "rec": 0.0, "rush_yds": 5.0, "pass_yds": 300.0}]),
             "g104": pd.DataFrame([{"name": "Someone Else", "rec_yds": 0.0, "rec": 0.0, "rush_yds": 0.0,
                                    "pass_yds": 0.0}])}
    fetched = []

    def fetch(sport, gid):
        fetched.append(gid)
        return boxes[gid]

    waiting, none = pickem.grade(picks, _games(completed=False), NOW, fetch)
    assert none == set() and fetched == [] and waiting["outcome"].isna().all()               # not final: not read
    graded, changed = pickem.grade(picks, _games(completed=True), NOW, fetch)
    assert changed == {(2026, 3)} and sorted(set(fetched)) == sorted(boxes)                 # one read a game
    by = graded.set_index("player_key")
    assert by.loc["p1", "outcome"] == "win" and by.loc["p1", "actual"] == 80.0
    assert by.loc["p5", "outcome"] == "loss"                                   # "Bijan Robinson Jr." found without the suffix
    assert by.loc["p3", "outcome"] == "win"                                    # "J. Love" by initial and last name
    assert by.loc["p4", "outcome"] == "void" and pd.isna(by.loc["p4", "actual"])            # not in the box score
    results = pickem.slip_results(slips, graded)
    assert set(results["result"]) <= {"win", "loss", "refund", "partial"}
    for s in results.itertuples():
        members = json.loads(s.pick_ids)
        got = graded.set_index("pick_id").loc[members, "outcome"].tolist()
        hits, dropped = got.count("win"), got.count("push") + got.count("void")
        assert s.multiple == pickem.multiple(s.kind, s.n, hits, dropped, pickem.PAYOUTS)


def test_ties_settle_as_a_push():
    assert pickem.settle("over", 92.5, 92.5) == "push" and pickem.settle("under", 92.5, 90) == "win"
    assert pickem.name_key("Michael Penix Jr.") == pickem.name_key("michael penix") == "michaelpenix"


# ---------------------------------------------------------------------------
# The step and the page
# ---------------------------------------------------------------------------


def _events() -> pd.DataFrame:
    return pd.DataFrame([{"event_id": e, "sport": "nfl", "scheduled": pd.Timestamp("2026-09-27 17:00", tz="UTC"),
                          "game_id": f"g{e}"} for e in (101, 102, 103, 104)]
                        + [{"event_id": 201, "sport": "nfl", "scheduled": pd.Timestamp("2026-09-28 00:20", tz="UTC"),
                            "game_id": "g201"},                                    # Sunday night: the same Eastern day
                           {"event_id": 301, "sport": "nfl", "scheduled": pd.Timestamp("2026-10-01 00:15", tz="UTC"),
                            "game_id": "g301"}])                                   # Thursday: not on this slate


def test_the_slate_is_the_days_games_not_yet_started():
    on = pickem.slate(_events(), NOW)
    assert list(on["event_id"]) == [101, 102, 103, 104, 201] and set(on["day"]) == {"2026-09-27"}
    monday = datetime(2026, 9, 28, 14, 0, tzinfo=UTC)
    assert list(pickem.slate(_events(), monday)["event_id"]) == [301]                     # the next day with games


def test_the_pickem_step_logs_grades_and_shows_three_cards(tmp_path, monkeypatch):
    props = _slate_props().drop(columns=["game_id", "kickoff", "day"])
    monkeypatch.setattr(pickem, "fetch", lambda client, events, now: props.merge(
        pickem.slate(events, now)[["event_id", "game_id", "kickoff", "day"]], on="event_id") if len(pickem.slate(events, now))
        else props.iloc[0:0].assign(game_id=[], kickoff=[], day=[]))
    where = {"picks_where": tmp_path / "picks", "slips_where": tmp_path / "slips", "ledger_where": tmp_path / "ledger"}
    cards = pickem.build(None, _events(), _games(), NAMES, KEY, NOW, **where)
    assert [c["title"] for c in cards][:2] == [f"Slips for Sun Sep 27 ({len(cards[0]['tables'][0]['rows'])})", "Pick board"]
    assert {c["tab"] for c in cards} == {"Pick'em"} and all(c["notes"] for c in cards)
    slip = cards[0]["tables"][0]
    assert slip["head"] == ["Entry", "Picks", "Value"] and slip["rows"][0][2][1].endswith("· logged")
    assert slip["rows"][0][0][0].endswith(("Power", "Flex")) and isinstance(slip["rows"][0][1], list)
    board = cards[1]["tables"][0]
    assert board["head"] == ["Player", "Pick", "Market", "Fair"] and board["rows"][0][1][1] == "logged"
    assert "1 offered More only" in cards[1]["notes"][0]
    assert cards[2]["title"] == "Pick'em record"
    assert (tmp_path / "picks" / "2026-03.enc.json").exists() and (tmp_path / "slips" / "2026-03.enc.json").exists()
    # Monday: the games are final; the box scores grade the picks, and the record says so.
    box = pd.DataFrame([{"name": n, "rec_yds": 99.0, "rec": 9.0, "rush_yds": 10.0, "pass_yds": 400.0}
                        for n in ("Drake London", "Bijan Robinson", "Jordan Love", "Jahan Dotson")])
    monday = datetime(2026, 9, 28, 14, 0, tzinfo=UTC)
    cards = pickem.build(None, _events(), _games(completed=True), NAMES, KEY, monday, box=lambda s, g: box, **where)
    record_card = next(c for c in cards if c["title"] == "Pick'em record")
    record = dict(record_card["tables"][0]["rows"])
    assert record["Graded"] == record["Picks logged"] and record["Won-lost-tie-void"].count("-") == 3
    assert record_card["tables"][1]["title"] == "Latest graded picks"


def test_the_step_never_raises():
    def boom(*a, **k):
        raise RuntimeError("a message that could quote a line")

    cards = pickem.build(type("C", (), {"get": boom})(), _events(), _games(), NAMES, KEY, NOW,
                         picks_where=None, slips_where=None, box=boom)
    assert cards and cards[0]["tab"] == "Pick'em"


def test_a_sealed_pick_record_opens_only_with_the_key(tmp_path):
    priced, _ = pickem.price(_slate_props())
    picks, _, weeks = pickem.log(pd.DataFrame(columns=pickem.PICK_COLUMNS), pd.DataFrame(columns=pickem.SLIP_COLUMNS),
                                 priced, pickem.optimize(priced), _games(), NAMES, NOW)
    pickem.seal(picks, KEY, weeks, tmp_path, pickem.PICK_COLUMNS, list(picks["player"]))
    with pytest.raises(sealed.Unreadable):
        pickem.load("not the key", tmp_path, pickem.PICK_COLUMNS)


def test_the_run_logs_what_the_tab_shows_in_counts_only():
    priced, counts = pickem.price(_slate_props())
    chosen = pickem.optimize(priced)
    line = pickem.summary(counts, priced, chosen, "2026-09-27")
    picks = int((priced["p"] >= pickem.PICK_FLOOR).sum())
    assert line.startswith("pickem: slate 2026-09-27: 7 PrizePicks lines, 1 More only, 1 unpriced, 5 priced, ")
    assert f"{picks} picks from 54% on 4 games" in line and f"{len(chosen)} slips (" in line
    assert "flex" in line and "power" in line
    assert not any(ch in line for ch in ("62.5", "92.5", "London", "-110"))              # never a line, a name or a price
    empty = pickem.summary({}, priced.iloc[0:0], chosen.iloc[0:0], None)
    assert empty == "pickem: slate none: 0 PrizePicks lines, 0 More only, 0 unpriced, 0 priced, 0 picks from 54% on 0 games, 0 slips (none)"
    described = pickem._describe("nfl", _slate_props(), 5)
    assert "7 props on 4 of 5 slate events, PrizePicks on 7" in described and "62.5" not in described

