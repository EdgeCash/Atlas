"""The pick'em on NHL nights (docs/MODEL_PLAN_NHL.md, step 7): PrizePicks' NHL lines priced on the books' props
along each stat's measured count shape, filed by the ISO week of puck drop, and graded from ESPN's hockey box
score. Synthetic."""

from __future__ import annotations

import math
from datetime import UTC, datetime

import pandas as pd
import pytest

from atlas.live.probability import no_vig
from atlas.owner import pickem
from atlas.sources import bettingpros as bp
from atlas.sources import nhl

KEY = "correct horse battery staple"
NOW = datetime(2026, 10, 1, 14, 30, tzinfo=UTC)                 # 10:30 ET, a Thursday of eight games
KICK = pd.Timestamp("2026-10-01T23:00:00Z")


def _q(event, key, player, market, book, side, line, cost, *, team="CBJ", position="C"):
    return {"captured_at": "2026-10-01T14:30:00+00:00", "sport": "nhl", "event_id": event, "market": market,
            "player_key": key, "player": player, "position": position, "team": team, "selection": side,
            "book_id": book, "line": line, "cost": cost, "updated": "2026-10-01 14:00:00", "main": True,
            "game_id": f"g{event}", "kickoff": KICK, "day": "2026-10-01"}


def _prop(event, key, player, market, books: dict, pp, **kw):
    rows = []
    for book, (line, over, under) in books.items():
        rows += [_q(event, key, player, market, book, "over", line, over, **kw),
                 _q(event, key, player, market, book, "under", line, under, **kw)]
    rows += [_q(event, key, player, market, bp.PRIZEPICKS, side, pp, None, **kw) for side in ("over", "under")]
    return rows


def _props() -> pd.DataFrame:
    rows = []
    rows += _prop(1, "p1", "Adam Fantilli", "shots", {12: (2.5, -150, 120), 19: (2.5, -145, 115)}, pp=2.5)
    rows += _prop(2, "p2", "Elvis Merzlikins", "saves", {12: (27.5, -115, -105), 10: (28.5, -110, -110)}, pp=26.5,
                  position="G")
    rows += _prop(3, "p3", "Zach Werenski", "points", {12: (0.5, -160, 125), 19: (0.5, -155, 120)}, pp=0.5,
                  position="D")
    rows += _prop(4, "p4", "Rasmus Dahlin", "blocked-shots", {12: (1.5, -130, 100), 10: (1.5, -125, -105)}, pp=1.5,
                  team="BUF", position="D")
    return pd.DataFrame(rows)


def test_a_count_is_a_poisson_at_one_and_a_negative_binomial_above():
    lam = 0.7
    assert pickem._nb_cdf(1, lam, 1.0) == pytest.approx(math.exp(-lam) * (1 + lam))
    # Over-dispersed: more weight in both tails than the Poisson at the same mean.
    assert pickem._nb_cdf(0, 3.0, 1.08) > pickem._nb_cdf(0, 3.0, 1.0)
    assert pickem._nb_cdf(8, 3.0, 1.08) < pickem._nb_cdf(8, 3.0, 1.0)
    # Saves: a goalie at 26 goes over 26.5 about half the time, and a save either way moves it a few points.
    over, push = pickem.split("sv", 26.0, 26.5)
    assert push == 0.0 and 0.40 < over < 0.52
    c = pickem.centre_for("sv", 27.5, 0.5)
    lower, _ = pickem.split("sv", c, 26.5)
    assert 0.53 < lower < 0.58


def test_every_nhl_stat_is_a_count_with_the_spread_measured_for_it():
    assert pickem.COUNTS["sog"] == 1.08 and pickem.COUNTS["blk"] == 1.08 and pickem.COUNTS["hits"] == 1.18
    assert pickem.COUNTS["pts"] == pickem.COUNTS["g"] == pickem.COUNTS["a"] == 1.0 and pickem.COUNTS["sv"] == 1.9
    assert pickem.STATS["shots"] == pickem.STATS["shots-on-goal"] == "sog"
    assert pickem.max_move("sog", 2.5) == 1.0 and pickem.max_move("sv", 26.5) == 3.0
    assert set(pickem.SLUGS["nhl"]) <= set(pickem.STATS)


def test_prizepicks_nhl_lines_are_priced_at_the_books_line_or_moved_to_it():
    priced, counts = pickem.price(_props())
    assert counts == {"lines": 4, "more_only": 0, "unpriced": 0} and set(priced["sport"]) == {"nhl"}
    by = priced.set_index("player")
    # At the books' own line the fair value is the median of their vig-free prices, as it stands.
    shots = [no_vig(-150, 120), no_vig(-145, 115)]
    assert by.loc["Adam Fantilli", "p"] == pytest.approx(sum(shots) / 2) and by.loc["Adam Fantilli", "side"] == "over"
    # Saves: both books above PrizePicks' 26.5, one by a save, one by two; More is likelier at the lower line.
    assert by.loc["Elvis Merzlikins", "side"] == "over" and by.loc["Elvis Merzlikins", "p"] > no_vig(-115, -105)
    assert by.loc["Elvis Merzlikins", "book_line"] == pytest.approx(28.0)
    assert by.loc["Zach Werenski", "p_push"] == 0.0


def test_a_book_too_far_from_prizepicks_is_not_moved():
    rows = _prop(5, "p5", "Kent Johnson", "shots", {12: (1.5, -200, 160), 19: (3.5, 150, -190)}, pp=2.5)
    priced, _ = pickem.price(pd.DataFrame(rows))
    assert len(priced) == 1                                   # a shot either way: both moved
    far = _prop(6, "p6", "Kirill Marchenko", "shots", {12: (4.5, 150, -190), 19: (4.5, 145, -185)}, pp=2.5)
    _, counts = pickem.price(pd.DataFrame(far))
    assert counts["unpriced"] == 1                            # two shots off: left out


def _summary():
    keys = ["blockedShots", "hits", "goals", "assists", "shotsTotal", "shotsMissed", "shootoutGoals"]
    goalie_keys = ["goalsAgainst", "shotsAgainst", "shootoutSaves", "saves", "savePct"]
    return {
        "header": {"competitions": [{"status": {"type": {"completed": True}}}]},
        "boxscore": {"players": [
            {"team": {"abbreviation": "CBJ"}, "statistics": [
                {"name": "forwards", "keys": keys, "athletes": [
                    {"athlete": {"displayName": "Adam Fantilli"}, "stats": ["0", "2", "1", "1", "4", "1", "1"]},
                    {"athlete": {"displayName": "Sebastian Aho"}, "stats": ["1", "0", "0", "0", "1", "0", "0"]}]},
                {"name": "defenses", "keys": keys, "athletes": [
                    {"athlete": {"displayName": "Zach Werenski"}, "stats": ["2", "1", "0", "1", "3", "2", "0"]}]},
                {"name": "goalies", "keys": goalie_keys, "athletes": [
                    {"athlete": {"displayName": "Elvis Merzlikins"}, "stats": ["2", "30", "2", "28", ".933"]}]}]},
            {"team": {"abbreviation": "NJ"}, "statistics": [
                {"name": "forwards", "keys": keys, "athletes": [
                    {"athlete": {"displayName": "Sebastian Aho"}, "stats": ["0", "1", "2", "0", "5", "0", "0"]}]}]},
        ]}}


def test_the_hockey_box_score_counts_points_and_leaves_the_shootout_out():
    box = nhl.espn_box(_summary())
    assert list(box.columns) == nhl.BOX_COLUMNS
    f = box[box["name"] == "Adam Fantilli"].iloc[0]
    assert (f["sog"], f["g"], f["a"], f["pts"], f["hits"]) == (4, 1, 1, 2, 2)
    g = box[box["position"] == "G"].iloc[0]
    assert g["sv"] == 28 and math.isnan(g["sog"])                          # two shootout saves not counted
    assert set(box.loc[box["name"] == "Sebastian Aho", "team"]) == {"CBJ", "NJD"}   # ESPN's NJ is the NHL's NJD


def test_nhl_picks_are_filed_by_the_iso_week_and_graded_from_the_hockey_box(tmp_path):
    priced, _ = pickem.price(_props())
    priced = priced.assign(p=0.6)                                         # every line a pick
    games = pd.DataFrame({"game_id": [f"g{e}" for e in (1, 2, 3, 4)], "season": 2026, "week": None,
                          "completed": False})
    names = {f"g{e}": "Sabres @ Jackets" for e in (1, 2, 3, 4)}
    picks, slips, weeks = pickem.log(pd.DataFrame(columns=pickem.PICK_COLUMNS),
                                     pd.DataFrame(columns=pickem.SLIP_COLUMNS), priced,
                                     pickem.optimize(priced).iloc[0:0], games, names, NOW)
    assert len(picks) == 4 and weeks == {(2026, 40)}
    assert pickem.filed("nhl", "2027-01-05T00:30:00Z") == (2027, 1)
    files = pickem.seal(picks, KEY, weeks, tmp_path, pickem.PICK_COLUMNS, list(picks["player"]))
    assert [f.name for f in files] == ["2026-40.enc.json"] and "Fantilli" not in files[0].read_text()

    done = games.assign(completed=True)
    graded, changed = pickem.grade(picks, done, NOW, fetch=lambda sport, gid: nhl.espn_box(_summary()))
    by = graded.set_index("player")
    assert changed == {(2026, 40)}
    assert (by.loc["Adam Fantilli", "actual"], by.loc["Adam Fantilli", "outcome"]) == (4.0, "win")
    assert (by.loc["Elvis Merzlikins", "actual"], by.loc["Elvis Merzlikins", "outcome"]) == (28.0, "win")
    assert (by.loc["Zach Werenski", "actual"], by.loc["Zach Werenski", "outcome"]) == (1.0, "win")
    assert by.loc["Rasmus Dahlin", "outcome"] == "void"                  # not in the box score: did not play


def test_two_players_of_one_name_are_told_apart_by_team():
    box = nhl.espn_box(_summary())
    assert pickem.find(box, "Sebastian Aho", "NJD")["blk"] == 0
    assert pickem.find(box, "Sebastian Aho", "CBJ")["blk"] == 1
    assert pickem.find(box, "Sebastian Aho") is None                      # without a team, neither
