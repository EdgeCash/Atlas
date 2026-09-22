# Atlas Quarterback Availability Report (Phase 1B)

*Generated 2026-09-22 14:47 UTC. Research only - nothing here is implemented in the
warehouse. Measured sections come from `scripts/research_qb_availability.py`.*

## The distinction that decides everything

Two questions get called "QB availability" and they have opposite answers:

| Question | Meaning | Free, 2018-present? |
|---|---|---|
| **Retrospective** | Who actually took the snaps in a game already played? | **Yes, essentially complete** |
| **Pre-kickoff** | Who was expected to start, known *before* kickoff? | **No** |

The first is what a backtest needs to *measure* what a quarterback change is
worth. The second is what a live model needs to *use* one. Atlas can have the
first for free today. The second has no good free historical source, and that
is the binding constraint.

---

## Section 1 - Data sources

| Source | API key | Cost | History | Timing | Verdict |
|---|---|---|---|---|---|
| Play-by-play passer (cfbfastR / CFBD) | none | free | 2018-present | retrospective | works - who took the snaps |
| CFBD /games/players, /player/usage | free key | free | 2018-present | retrospective | works - same information |
| ESPN event rosters | none | free | 2018-present | retrospective | useless - starter/active flags never populated |
| ESPN depth charts | none | free | none | pre-kickoff | unavailable - HTTP 400 for college football |
| ESPN injuries endpoints | none | free | none | pre-kickoff | empty for college football |
| Commercial feeds (Rotowire, SportsDataIO, Sportradar) | required | paid | varies | pre-kickoff | the only real pre-kickoff option |
| News / beat-writer archives | none | free | 2018-present | pre-kickoff | unstructured - large extraction project |

Findings worth stating plainly, each verified by direct probe:

* **ESPN event rosters exist back to 2018** and carry `starter`, `active` and
  `didNotPlay` fields - all of which are unpopulated for college football.
  Checked on 2018 and 2023 games: zero entries flagged in either.
* **ESPN depth charts return HTTP 400** for college football. The endpoint
  exists for other leagues.
* **ESPN's injury endpoints return zero items** for college football players.
* The structural reason behind all three: **college football has no mandated
  injury report.** The NFL requires participation reporting; the NCAA does
  not. There is no authoritative pre-kickoff availability record to mirror,
  so no free archive of one exists.

---

## Section 2 - Availability and coverage

### Coverage of the retrospective source

| Season | Team-games | With a QB | Coverage | Clear starter (>=70% att.) | Distinct starters |
|---|---|---|---|---|---|
| 2018 | 1,466 | 1,462 | 0.997 | 0.916 | 237 |
| 2019 | 1,468 | 1,466 | 0.999 | 0.905 | 243 |
| 2020 | 1,016 | 968 | 0.953 | 0.897 | 220 |
| 2021 | 1,464 | 1,463 | 0.999 | 0.875 | 287 |
| 2022 | 1,468 | 1,468 | 1.000 | 0.879 | 297 |
| 2023 | 1,584 | 1,584 | 1.000 | 0.907 | 285 |
| 2024 | 1,596 | 1,596 | 1.000 | 0.899 | 281 |
| 2025 | 1,616 | 1,614 | 0.999 | 0.753 | 483 |
| 2026 | 314 | 314 | 1.000 | 0.608 | 194 |

Essentially complete. A "clear starter" is one who threw at least 70% of the
team's attempts; the rest are genuine committees or in-game changes.

### How often the starter changes

| Season | Team-games | Changes | Change rate |
|---|---|---|---|
| 2018 | 1,334 | 206 | 0.154 |
| 2019 | 1,336 | 207 | 0.155 |
| 2020 | 879 | 157 | 0.179 |
| 2021 | 1,334 | 269 | 0.202 |
| 2022 | 1,337 | 303 | 0.227 |
| 2023 | 1,451 | 252 | 0.174 |
| 2024 | 1,462 | 247 | 0.169 |
| 2025 | 1,480 | 431 | 0.291 |
| 2026 | 176 | 61 | 0.347 |

Roughly one team-game in six starts a different quarterback than the week
before, rising sharply in the most recent seasons.

### What a change is worth against the closing line

`qb_change_diff` is +1 when only the away team changed quarterback, -1 when
only the home team did, 0 otherwise. The target is the market residual,
`actual_margin - market_margin`.

| QB change (away - home) | Games | Mean residual | Home cover rate | SE | t |
|---|---|---|---|---|---|
| -1.0000 | 734 | -2.5964 | 0.4412 | 0.5778 | -4.4937 |
| 0.0000 | 4,271 | 0.1681 | 0.5043 | 0.2352 | 0.7147 |
| 1.0000 | 773 | 1.7549 | 0.5464 | 0.5554 | 3.1597 |

| Season | Games | Signed residual | SE | t |
|---|---|---|---|---|
| 2018 | 166 | 2.524 | 1.245 | 2.027 |
| 2019 | 158 | 2.484 | 1.168 | 2.128 |
| 2020 | 135 | 0.170 | 1.480 | 0.115 |
| 2021 | 201 | 2.458 | 1.087 | 2.262 |
| 2022 | 217 | 1.142 | 1.073 | 1.064 |
| 2023 | 212 | 3.317 | 1.055 | 3.143 |
| 2024 | 193 | 2.361 | 1.165 | 2.027 |
| 2025 | 225 | 2.342 | 0.949 | 2.468 |


---

## Section 3 - Feasibility

**Retrospective: easy.** One derived column off play-by-play Atlas already
downloads. Roughly fifty lines, no new dependency, no new source. It is
deliberately *not* wired into the warehouse, because a column that is only
knowable after kickoff has no business sitting next to point-in-time features
where it could be picked up by accident.

**Pre-kickoff: hard, and only three routes exist.**

1. **Commercial feed.** Rotowire, SportsDataIO and Sportradar all sell
   college lineup and injury data with history. Cost is the only obstacle,
   and licence terms need checking for backtest use.
2. **News archive extraction.** Beat-writer reports and team announcements
   carry the information, unstructured. Recovering eight seasons means
   building a scraper plus an extraction pipeline and accepting imperfect
   recall - a project in its own right, not a data-collection step.
3. **Proxy from the market itself.** A large line move without a
   corresponding rating change often *is* the injury news. This is circular
   for finding an edge, but useful for labelling history.

A fourth option worth noting: **going forward, pre-kickoff status is easy to
capture** by recording announced starters weekly from free sources. That
builds a clean dataset from today onward and costs nothing, but it cannot
backfill 2018-2024.

---

## Section 4 - Expected value

This is the part that changes the Atlas roadmap.

Measured effect of a quarterback change on the market residual:
**about 2.1 points of margin, positive in 8 of 8 seasons and individually significant in 6**.

For scale: the closing line's own margin MAE is about 12.2 points, and Phase
1A and Phase 1B between them found **no** variable that moved the residual by
even 0.01 points. A two-point signed effect on roughly a quarter of
team-games is the first thing in either phase that is not zero.

Three caveats, all of which matter:

1. **This is not a point-in-time feature and must never be used as one.** It
   is derived from who actually started, which is known at kickoff at the
   earliest. Putting it in a backtest as-is would be look-ahead leakage of the
   most flattering kind.
2. **It is therefore an upper bound**, not an achievable edge. It measures the
   value of *perfect* pre-kickoff knowledge of a starter change. Real
   knowledge is partial, late, and shared with the market.
3. **Some of it is not the quarterback.** A change often follows an injury,
   a blowout, or a benching, each of which carries its own information. The
   effect is "a team whose quarterback situation changed", not "the backup is
   worth 2.3 points".

Even discounted for all three, this is the only measured signal in the
programme that points at something the closing line does not fully contain.

---

## Recommendation

1. **Do not implement anything in the warehouse now.** The retrospective
   column would be a leakage hazard sitting among point-in-time features, and
   it buys nothing until there is a pre-kickoff counterpart.
2. **Price a commercial pre-kickoff feed before writing any more model code.**
   It is now the highest-expected-value item on the roadmap, ahead of further
   metric engineering - Phase 1B just demonstrated that measuring team quality
   better does not move the residual.
3. **Start capturing announced starters weekly from today**, regardless of
   the commercial decision. It is nearly free and the archive only becomes
   valuable with age.
4. **Re-run this probe as a validation harness** once a pre-kickoff source
   exists: the retrospective series is the ground truth any pre-kickoff feed
   should be scored against.
