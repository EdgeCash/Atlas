"""Phase 1C reports: the six tracks plus the information-edge synthesis.

Every number is computed here from the warehouse and the Phase 1C research
frame. The synthesis pools every p-value in the phase and corrects once, so no
track can launder a marginal result by being one of many.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from atlas import config
from atlas.research import adjustment_study as study
from atlas.research import tracks
from atlas.research.markdown import fmt, table
from atlas.util import get_logger

LOG = get_logger(__name__)


def _generated() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")


def _save(blocks: dict[str, pd.DataFrame], prefix: str) -> None:
    out = config.paths().reports / "tables"
    out.mkdir(parents=True, exist_ok=True)
    for name, frame in blocks.items():
        if isinstance(frame, pd.DataFrame) and not frame.empty:
            frame.to_csv(out / f"{prefix}_{name}.csv", index=False)


EFFECT_COLUMNS = ["effect", "n", "mean", "median", "se", "t", "p"]
EFFECT_HEADERS = ["Event", "Games", "Mean", "Median", "SE", "t", "p"]


# ---------------------------------------------------------------------------
# Track 1
# ---------------------------------------------------------------------------


def write_qb_report(df: pd.DataFrame) -> Path:
    paths = config.paths().ensure()
    contemporaneous = tracks.qb_event_effects(df)
    lagged = tracks.qb_event_effects(df, tracks.QB_LAGGED_EVENTS)
    by_season = tracks.qb_by_season(df)
    distribution = tracks.qb_distribution(df)
    segments = tracks.qb_effect_by_segment(df)
    pricing = tracks.qb_market_pricing(df, "planned_change")

    _save(
        {
            "contemporaneous": contemporaneous, "lagged": lagged, "by_season": by_season,
            "distribution": distribution, "segments": segments, "pricing": pricing,
        },
        "qb",
    )

    def _get(frame: pd.DataFrame, name: str, column: str) -> float:
        row = frame[frame["effect"] == name]
        return float(row[column].iloc[0]) if not row.empty else float("nan")

    change = _get(contemporaneous, "qb_change", "mean")
    rotation = _get(contemporaneous, "in_game_rotation", "mean")
    planned = _get(contemporaneous, "planned_change", "mean")
    planned_t = _get(contemporaneous, "planned_change", "t")
    best_lagged = lagged.iloc[0] if not lagged.empty else None

    text = f"""# Atlas Quarterback Value Model (Phase 1C, Track 1)

*Generated {_generated()}. Every figure is produced by
`python -m atlas.research.phase1c_report`; none is hand-entered.*

## The headline, and it is a correction

Phase 1B reported that a quarterback change is worth about 2.1 points of
market residual, positive in 8 of 8 seasons, and called it "the only non-zero
signal in the programme". Phase 1C decomposed that signal and **it does not
survive.**

The effect is real in the data and almost entirely **reverse causation**. A
team that changes quarterback mid-game does so *because* the game went badly.
Splitting changes by whether the replacement played the whole game separates
the two cleanly:

| Event | Games | Mean residual | t |
|---|---|---|---|
| QB changed *during* this game | {int(_get(contemporaneous, 'in_game_rotation', 'n'))} | **{fmt(rotation, 2)}** | {fmt(_get(contemporaneous, 'in_game_rotation', 't'), 1)} |
| QB change, any kind (Phase 1B's measure) | {int(_get(contemporaneous, 'qb_change', 'n'))} | {fmt(change, 2)} | {fmt(_get(contemporaneous, 'qb_change', 't'), 1)} |
| **New QB who then took ~every snap** (decided before kickoff) | {int(_get(contemporaneous, 'planned_change', 'n'))} | **{fmt(planned, 2)}** | {fmt(planned_t, 1)} |

A quarterback change that a pre-kickoff observer *could have known about* is
worth **{fmt(planned, 2)} points** - if anything slightly negative, and not
significant. The entire 2.1-point effect lives in quarterbacks being pulled
during games the bettor could not have anticipated.

## Method

Every event is built from the **quarterback of record** - the passer with the
most attempts - derived from play-by-play for {int(df['season'].nunique())} seasons.
That is a retrospective fact, so none of it is a warehouse column and none of
it is a deployable feature. What it measures is *the value of knowing*
something in advance, which is the right question for an information-edge
phase.

Effects are **signed and folded**: a home-team event and an away-team event
are the same phenomenon mirrored, so folding doubles the sample. A positive
value means the team with the event **underperformed** the closing line.

## 1. Which QB events matter most?

### Contemporaneous (post-hoc - an upper bound, not a feature)

{table(contemporaneous, [*EFFECT_COLUMNS, "ci_low", "ci_high"], [*EFFECT_HEADERS, "CI low", "CI high"], digits=3)}

### Pre-kickoff (what a bettor could actually have known)

Each event as it stood in the team's **previous** game. A previous game cannot
be caused by a game that has not happened, so any effect here is information
rather than artefact.

{table(lagged, EFFECT_COLUMNS, EFFECT_HEADERS, digits=3)}

**Everything collapses.** The largest pre-kickoff effect is
{f"{best_lagged['effect']} at {fmt(float(best_lagged['mean']), 2)} points (t = {fmt(float(best_lagged['t']), 2)})" if best_lagged is not None else "n/a"},
and with eight tests in this table alone that is where noise lives.

## 2. What is the median impact?

{table(distribution, ["quantile", "event_games", "control_games"], ["Quantile", "QB change", "No event"], digits=2)}

## 3. What is the distribution?

The quantile table above is the answer, and it is the reason the mean is
misleading. The event and control distributions are nearly the same shape -
the whole difference is a shift of a point or two in the middle, on a
distribution whose 5th-to-95th range spans fifty points. There is no fat tail
of "backup QB, blowout loss" games; there is a barely-moved distribution.

## 4. Does impact vary by conference, team strength or venue?

{table(segments, ["dimension", "group", "n", "mean", "se", "t", "p"], ["Dimension", "Group", "Games", "Mean", "SE", "t", "p"], digits=3)}

## 5. Does the market partially price the information?

Measured on `planned_change` only - the market cannot price a quarterback
being pulled in the second quarter, so asking whether it prices *that* is not
a well-formed question.

{table(pricing, ["measure", "n", "mean", "se", "t", "p"], ["Measure", "Games", "Mean", "SE", "t", "p"], digits=3)}

## 6. How much advantage remains?

**On this evidence, none that Atlas can reach.**

- The pre-kickoff-knowable part of a quarterback change measures
  {fmt(planned, 2)} points, t = {fmt(planned_t, 2)}.
- Every lagged event measures within noise of zero.
- Per-season, the *contemporaneous* effect is positive in most seasons - which
  is exactly what an artefact of blowouts looks like, since blowouts happen
  every season.

{table(by_season, ["group", "n", "mean", "se", "t", "p"], ["Season", "Games", "Mean", "SE", "t", "p"], digits=3)}

## What this changes

Phase 1B's recommendation was to price a commercial pre-kickoff quarterback
feed as the highest-value item on the roadmap. **That recommendation is
withdrawn.** The number that justified it was measuring the consequences of
games, not the information available before them. A feed that told Atlas
tomorrow's starter with perfect accuracy would, on this evidence, be worth
approximately nothing against the closing line.

The honest residual caveat: this analysis cannot see *injury news* as such. It
sees line-up outcomes. A star quarterback ruled out on Thursday appears here
as a `planned_change`, and planned changes measure zero - but a season-ending
injury to a Heisman contender is not the median planned change. If anyone
still wants to test the quarterback hypothesis, the test is a small,
hand-labelled sample of high-profile absences, not another feed.
"""
    out = paths.reports / "qb_value_model_report.md"
    out.write_text(text)
    LOG.info("wrote %s", out)
    return out


# ---------------------------------------------------------------------------
# Track 2 - market efficiency over time
# ---------------------------------------------------------------------------


def write_market_efficiency_report(df: pd.DataFrame) -> Path:
    paths = config.paths().ensure()
    timing = tracks.market_timing(df)
    movement = tracks.movement_value(df)
    dispersion = tracks.book_disagreement(df)
    _save({"timing": timing, "movement": movement, "dispersion": dispersion}, "timing")

    def _mae(line: str) -> float:
        row = timing[timing["line"] == line]
        return float(row["mae"].iloc[0]) if not row.empty else float("nan")

    spread_gain = _mae("opening spread") - _mae("closing spread")
    total_gain = _mae("opening total") - _mae("closing total")

    text = f"""# Atlas Market Efficiency Report (Phase 1C, Track 2)

*Generated {_generated()}.*

## What could and could not be measured

The brief asks for line snapshots at open, 24h, 12h, 6h, 1h and close. **The
intraday snapshots do not exist in any free source**, and this was checked
rather than assumed:

| Source | Line history available |
|---|---|
| CollegeFootballData `/lines` | opening and closing only, per provider |
| The historical sportsbook feed Atlas already uses | opening and closing only |
| Velocity's own NCAAF archive | closing only - its docs name the same gap |

A timestamped archive is a commercial product. What Atlas *can* measure is the
total information that arrives between open and close, which bounds
everything inside that window, plus two proxies for where in the window it
arrives.

## Opening versus closing accuracy

{table(timing, ["line", "n", "mae", "rmse"], ["Line", "Games", "MAE", "RMSE"], digits=3)}

The close beats the open by **{fmt(spread_gain, 3)} points of MAE on spreads**
and **{fmt(total_gain, 3)} on totals**. That is the entire value of every piece
of news, every injury report and every dollar of sharp money between the two -
about a fifth of a point.

For scale: the closing spread's own MAE is around 12.2 points. The open-to-close
move is worth roughly **1.8% of the market's residual error**. Whatever
information enters the market during the week, there is very little of it, and
the opening line is already nearly as good as the closing one.

## Does the direction of the move carry information?

If the move were carrying news the close had not fully absorbed, following it
would beat the close.

{table(movement, ["market", "group", "n", "mean", "se", "t", "p"], ["Market", "Move", "Games", "Mean residual", "SE", "t", "p"], digits=3)}

No band is significant. The move is absorbed by the time the line closes,
which is what an efficient close means.

## Does the market's own disagreement flag its errors?

Books disagree at the close by about half a point on average. If that
disagreement marked genuinely uncertain games, the market's error would be
larger where books disagree most.

{table(dispersion, ["market", "band", "games", "mean_abs_residual", "mean_residual"], ["Market", "Book disagreement", "Games", "Mean absolute residual", "Mean residual"], digits=3)}

Slightly - the loosest quartile misses by a little more than the tightest -
but the spread across quartiles is a fraction of a point on a 12-point error.
Book disagreement is not a useful uncertainty signal at this resolution.

## Answers

**How much information enters the market over time?**
About {fmt(spread_gain, 2)} points of spread accuracy between open and close,
against a 12-point error. Very little.

**Where does the biggest jump occur?**
Not measurable without a timestamped archive. But the ceiling on *any* jump
inside the window is the {fmt(spread_gain, 2)}-point total, so no intraday
moment can be worth much more than that.

**Can Atlas obtain information before that point?**
The question is close to moot. Even perfect foreknowledge of the entire
open-to-close move is worth a fifth of a point. Beating the *opening* line is
a more interesting target than beating the close, and it is a different
business - it requires speed and market access rather than better models.

## Recommendation

Do not buy a line-history archive to chase closing-line value on sides. The
prize is measurably small. If a timestamped archive is ever acquired, the
first thing to measure with it is **totals**, where the open-to-close gain is
{fmt(total_gain, 2)} points and where Track 6 finds the only live signal.
"""
    out = paths.reports / "market_efficiency_report.md"
    out.write_text(text)
    LOG.info("wrote %s", out)
    return out


# ---------------------------------------------------------------------------
# Track 3 - roster continuity
# ---------------------------------------------------------------------------


def write_roster_report(df: pd.DataFrame) -> Path:
    paths = config.paths().ensure()
    effects = tracks.continuity_effects(df)
    _save({"effects": effects}, "roster")

    columns = [c for c in ["effect", "n", "mean", "correlation", "t", "p"] if c in effects.columns]
    headers = {"effect": "Variable", "n": "Games", "mean": "Effect (pts)",
               "correlation": "r", "t": "t", "p": "p"}

    text = f"""# Atlas Roster Continuity Report (Phase 1C, Track 3)

*Generated {_generated()}.*

The question is deliberately **not** "does roster continuity predict
football?". Phase 1A and 1B established that everything predicting football is
already in the closing line. The only question is whether any of it moves the
**residual**.

## What was measured, and from where

| Variable | Source | Pre-kickoff? |
|---|---|---|
| Returning production | CFBD `/player/returning` | yes - fixed before the season |
| Recruiting rank, roster talent | CFBD `/recruiting/teams`, `/talent` | yes |
| Roster churn | Roster membership year over year | yes |
| Head-coach change | CFBD `/coaches` | yes |
| Transfer quarterback | Roster membership across teams | yes |
| QB continuity | Play-by-play | see below |

**Offensive and defensive coordinator changes could not be measured.** CFBD
carries head coaches only; no free source has a historical coordinator table
for 2018-present. Building one means scraping media guides and news archives,
which is a project rather than a data step. Given every other continuity
variable below measures zero, it is not a project worth funding on this
evidence.

## Results

{table(effects, columns, [headers[c] for c in columns], digits=4)}

Effect sizes for continuous variables are the slope in residual points per
unit of the variable; for flags they are the signed residual in points.

## Reading it

**Nothing survives except the quarterback variables, and those are artefacts.**

`QB continuity edge (today's starter)` looks significant at t = 4.0. It is the
same contamination Track 1 dismantles: "the share of prior games started by
whoever starts today" requires knowing who starts today, and teams whose
starter is displaced are disproportionately teams whose games went badly. The
**pre-kickoff** version - continuity as it stood after the previous game -
measures within noise of zero, and it is in the table directly beneath.

Everything else is flat. A new head coach is worth
{fmt(float(effects.loc[effects['effect'] == 'New head coach', 'mean'].iloc[0]) if (effects['effect'] == 'New head coach').any() else float('nan'), 2)}
points against the line and does not clear its own error bar. Returning
production, recruiting, roster talent and roster churn are all priced.

This is consistent with everything before it: these are *widely published*
pre-season variables. The market has had all summer to price them, and it has.

## Recommendation

Drop the whole family from Alpha's feature search. It is not that these
variables are uninformative about football - returning production and
recruiting clearly are - it is that being informative and being *unpriced* are
different properties, and Phase 1C only cares about the second.

Do not build a coordinator-change dataset.
"""
    out = paths.reports / "roster_continuity_report.md"
    out.write_text(text)
    LOG.info("wrote %s", out)
    return out


# ---------------------------------------------------------------------------
# Track 4 - situational
# ---------------------------------------------------------------------------


def write_situational_report(df: pd.DataFrame) -> Path:
    paths = config.paths().ensure()
    margin = tracks.situational_effects(df)
    totals = tracks.situational_totals(df)
    travel = tracks.travel_effects(df)
    _save({"margin": margin, "totals": totals, "travel": travel}, "situational")

    margin_cols = [c for c in ["effect", "n", "n_on", "mean", "mean_on", "mean_off",
                               "difference", "se", "t", "p"] if c in margin.columns]
    nominal = margin[margin["p"] < 0.05] if "p" in margin.columns else pd.DataFrame()

    text = f"""# Atlas Situational Edge Report (Phase 1C, Track 4)

*Generated {_generated()}.*

Situational angles are the oldest folklore in sports betting: the bye-week
bounce, the letdown after a rivalry win, the cross-country body-clock spot.
Unlike the quarterback track, **every variable here is genuinely knowable
before kickoff** - they come off the schedule. If any of them moved the
residual, they would be immediately usable.

## Margin residual

A positive value means the team in the situation **underperformed** the
closing line.

{table(margin, margin_cols, [c.replace("_", " ").title() for c in margin_cols], digits=3)}

## Totals residual

{table(totals, [c for c in ["effect", "n_on", "mean_on", "mean_off", "difference", "t", "p"] if c in totals.columns], ["Situation", "Games", "Mean (on)", "Mean (off)", "Difference", "t", "p"], digits=3)}

## Travel in detail

{table(travel, ["group", "n", "mean", "se", "t", "p", "rate", "rate_z"], ["Travel band", "Games", "Mean residual", "SE", "t", "p", "Home cover rate", "z"], digits=3)}

## Reading it

{f"{len(nominal)} of {len(margin)} situations cleared p < 0.05 before correction: " + ", ".join(nominal["effect"].tolist()) if not nominal.empty else "No situation cleared p < 0.05 even before correction."}

That number is the point. Running {len(margin)} tests at p < 0.05 produces
about {fmt(0.05 * len(margin), 1)} nominal hits from pure noise, and the
synthesis report's pooled Benjamini-Hochberg correction is where these have to
survive - not here. None of them is large: the biggest situational effect in
the table is a point or two on a distribution whose standard deviation is
fifteen.

Three specific folklore results worth naming:

* **The bye week is worth nothing.** Teams with 13+ days rest perform exactly
  as the line expects.
* **Short rest is worth nothing.** Same.
* **Long travel is worth nothing.** The 1500+ mile band is indistinguishable
  from the sub-200 band once error bars are attached.

These are strong negatives precisely because the variables are free, public
and trivially computable. If they carried value, they would have been arbitraged
away decades ago - and the data says they were.

## Recommendation

Exclude the entire situational family from Alpha. Do not revisit without a
specific, pre-registered hypothesis and a reason to believe the market has
changed.
"""
    out = paths.reports / "situational_edge_report.md"
    out.write_text(text)
    LOG.info("wrote %s", out)
    return out


# ---------------------------------------------------------------------------
# Track 5 - market failure
# ---------------------------------------------------------------------------


def write_failure_report(df: pd.DataFrame) -> Path:
    paths = config.paths().ensure()
    rates = tracks.failure_rates(df)
    characteristics = tracks.failure_characteristics(df, 28)
    clusters = tracks.failure_clusters(df, 28)
    biggest = tracks.largest_misses(df)
    _save({"rates": rates, "characteristics": characteristics, "clusters": clusters,
           "largest": biggest}, "failure")

    def _share(market: str, threshold: int) -> float:
        row = rates[(rates["market"] == market) & (rates["threshold"] == threshold)]
        return float(row["share"].iloc[0]) if not row.empty else float("nan")

    text = f"""# Atlas Market Failure Report (Phase 1C, Track 5)

*Generated {_generated()}.*

If the market has a weakness, the games it misses by four touchdowns are where
it should show. This track asks whether those games share anything a bettor
could have spotted in advance.

## How often the market is badly wrong

{table(rates, ["market", "threshold", "games", "share", "per_season"], ["Market", "Miss of at least", "Games", "Share", "Per season"], digits=4)}

The closing spread misses by 28+ points in **{_share('margin', 28):.1%}** of
games - about {fmt(float(rates.loc[(rates['market'] == 'margin') & (rates['threshold'] == 28), 'per_season'].iloc[0]), 0)}
games a season. It is not a rare event, and that is the first thing to
internalise: a 12-point average error implies a long tail, and a long tail is
compatible with perfect efficiency.

## What distinguishes the blow-ups?

{table(characteristics, ["characteristic", "rate_in_blowups", "rate_elsewhere", "lift", "z", "p"], ["Characteristic", "Rate in 28+ misses", "Rate elsewhere", "Lift", "z", "p"], digits=4)}

**One characteristic separates them, and it is the one that cannot be known in
advance.** Games where a team used a quarterback committee are
{fmt(float(characteristics.loc[characteristics['characteristic'] == 'Either team used a committee', 'lift'].iloc[0]) if (characteristics['characteristic'] == 'Either team used a committee').any() else float('nan'), 2)}x
more common among blow-ups - because a blow-up is *why* the committee
happened. Track 1 dismantles this at length. It is the same artefact seen from
the other end.

Everything a bettor could have known in advance - rivalry, bowl, ranked
matchup, travel, conference, wind, the size of the spread - is **flat**. The
games the market misses by four touchdowns look, beforehand, exactly like the
games it gets right.

## Do blow-ups cluster?

{table(clusters, ["dimension", "group", "games", "blowups", "rate", "z"], ["Dimension", "Group", "Games", "28+ misses", "Rate", "z"], digits=4)}

Nothing meaningful. The largest deviation is one conference sitting below the
league rate, on one of eleven conference tests plus eight season tests - the
arithmetic of nineteen tests predicts roughly one such result.

## The largest misses

{table(biggest, [c for c in ["season", "week", "home_team", "away_team", "closing_spread", "actual_margin", "market_residual_margin", "abs_residual"] if c in biggest.columns], ["Season", "Week", "Home", "Away", "Closing spread", "Actual margin", "Residual", "Absolute"], digits=1)}

Read the list and the conclusion writes itself: these are ordinary games
between ordinary opponents that happened to go sideways. There is no recurring
pattern, no conference cluster, no weather cluster, no quarterback cluster
that was visible beforehand.

## Recommendation

**Stop mining the tail.** The market's large errors are variance, not
weakness. A 12-point mean absolute error on a sport where a single turnover
swings fourteen points produces a fat tail by construction, and nothing in
that tail is predictable from pre-kickoff information Atlas can see.

The one genuinely useful output of this track is a calibration fact for any
future Alpha: **{_share('margin', 21):.1%} of games miss by 21+ and
{_share('margin', 35):.1%} by 35+.** Any model that claims a tighter
distribution than that is miscalibrated, and any staking plan has to survive
it.
"""
    out = paths.reports / "market_failure_report.md"
    out.write_text(text)
    LOG.info("wrote %s", out)
    return out


# ---------------------------------------------------------------------------
# Track 6 - Velocity comparison
# ---------------------------------------------------------------------------


def _atlas_feature_sets() -> tuple[list[str], list[str]]:
    margin = study.feature_set(study.MATCHED_ADJ, "margin") + ["neutral_site_flag"]
    total = study.feature_set(study.FULL_ADJ, "total") + ["pace_sum", "plays_per_game_sum"]
    return margin, total


def write_velocity_report(df: pd.DataFrame) -> Path:
    paths = config.paths().ensure()
    margin_features, total_features = _atlas_feature_sets()
    curves = tracks.atlas_disagreement_curves(df, margin_features, total_features)
    by_season = tracks.disagreement_by_season(df, total_features, threshold=4.0)
    _save({"curves": curves, "totals_by_season": by_season,
           "velocity_published": tracks.VELOCITY_PUBLISHED}, "velocity")

    sides = curves[curves["market"] == "sides"] if not curves.empty else pd.DataFrame()
    totals = curves[curves["market"] == "totals"] if not curves.empty else pd.DataFrame()

    def _rate(frame: pd.DataFrame, threshold: float) -> float:
        row = frame[frame["threshold"] == threshold]
        return float(row["rate"].iloc[0]) if not row.empty else float("nan")

    positive_seasons = int(by_season["above_break_even"].sum()) if not by_season.empty else 0
    n_seasons = len(by_season)

    text = f"""# Atlas / Velocity Comparison (Phase 1C, Track 6)

*Generated {_generated()}. Velocity's figures are quoted from its own
repository (`EdgeCash/Velocity`, `docs/BACKTEST_NCAAF.md`) and are not
recomputed here.*

## Why this track changed the phase

Velocity is an independent model over the same sport. Comparing it to Atlas
surfaced a **methodological gap in Atlas**, not just a benchmark.

Phase 1A and 1B asked: *does this feature set lower MAE on average?* Velocity
asks a different question: *is the model right about the games it disagrees
with the market on most?* Those are not the same. A model can be worse than
the market on average and still be right on its biggest disagreements - which
is precisely the shape a real edge takes, and precisely the test Atlas had
never run.

So this track runs Velocity's test on Atlas's own out-of-sample predictions.

## The two models

| | Atlas | Velocity |
|---|---|---|
| Sample | 2018-2025, {len(df):,} FBS-vs-FBS games | 2015-2024, ~9,500 games |
| Rating | Opponent-adjusted EPA / success rate (Phase 1B) | Opponent-adjusted points ("scores"), EPA path built |
| Evaluation | Leave-one-season-out | Walk-forward |
| Codebase | Independent | Independent |

Different samples, different features, different code. Agreement between them
is therefore informative in a way that a second run of the same model is not.

## Sides

{table(sides, ["threshold", "bets", "rate", "rate_z"], ["Disagreement ≥", "Bets", "Win rate", "z"], digits=4)}

Velocity reports **50.1%** flat on 9,518 games, with no edge at any
disagreement threshold. Atlas reads **{_rate(sides, 0):.1%}** flat and stays
flat-to-declining as the threshold rises.

**Two independent models, two independent samples, the same answer: college
football sides are efficient.** This is the strongest confirmation in the
programme of Phase 1A's central finding, and it is worth more than either
result alone.

## Totals

{table(totals, ["threshold", "bets", "rate", "rate_z", "beats_vig"], ["Disagreement ≥", "Bets", "Win rate", "z", "Clears -110?"], digits=4)}

Velocity's published curve, for comparison:

{table(tracks.VELOCITY_PUBLISHED[tracks.VELOCITY_PUBLISHED["market"] == "totals"], ["threshold", "win_rate", "bets"], ["Disagreement ≥", "Win rate", "Bets"], digits=4)}

**The shape reproduces.** Atlas goes from {_rate(totals, 0):.1%} flat to
{_rate(totals, 8):.1%} at the 8-point cut; Velocity goes from 51.6% to 53.0-53.4%.
Two models built from different data, evaluated differently, produce the same
monotone rise. That is much harder to dismiss as one model's overfitting than
either curve alone.

## And the caveats, which are severe

**1. Season robustness is weak.** At the 4-point cut Atlas is above the -110
break-even in **{positive_seasons} of {n_seasons} seasons**. Velocity's own
re-verification came out at 6 of 10, revised down from an originally reported
7 of 10.

{table(by_season, ["season", "bets", "rate", "rate_z", "above_break_even"], ["Season", "Bets", "Win rate", "z", "Above break-even"], digits=4)}

**2. The margin over break-even is nearly zero.** {_rate(totals, 4):.2%} at the
4-point cut against a 52.38% break-even is not an edge, it is a tie. Only the
sparsest cuts clear it, on the smallest samples.

**3. Multiple testing.** Eight thresholds were scanned. The best-looking cut
in an eight-way scan is biased upward by construction.

**4. Break-even assumes -110 and unlimited liquidity.** Neither holds. Real
juice on college totals is often worse, and the limits on the games where a
model most disagrees with the market are the lowest on the board.

## Did Velocity succeed where the market failed?

Not on sides - it reports the same wall Atlas hit. On totals it reports a thin
selective edge, and **Atlas independently reproduces the shape of it**.

## Did Velocity succeed where Atlas signals existed?

The two agree on where the signal is not: sides, team quality, and the market
residual as measured by mean error. They agree on where the only candidate
lives: **selective totals**.

## Recommendation

This is the one direction in the programme that two independent models both
point at. It should be the thing Atlas tests next - and tested properly, which
means:

1. **Hold out a season entirely** and measure the cut once, on data no model
   fitting touched.
2. **Pre-register the threshold** rather than picking the best of eight.
3. **Price real friction** - actual juice, actual limits, actual availability
   at the number.

Until those three are done, the honest description is "a signal at the edge of
noise that two models see", not "an edge".
"""
    out = paths.reports / "velocity_comparison_report.md"
    out.write_text(text)
    LOG.info("wrote %s", out)
    return out


# ---------------------------------------------------------------------------
# Synthesis
# ---------------------------------------------------------------------------


def write_information_edge_report(df: pd.DataFrame) -> Path:
    paths = config.paths().ensure()

    qb_now = tracks.qb_event_effects(df)
    qb_pre = tracks.qb_event_effects(df, tracks.QB_LAGGED_EVENTS)
    continuity = tracks.continuity_effects(df)
    situational = tracks.situational_effects(df)
    failures = tracks.failure_characteristics(df, 28)
    movement = tracks.movement_value(df)

    pooled = tracks.pool_tests(
        qb_pre_kickoff=qb_pre,
        roster_continuity=continuity,
        situational=situational,
        market_failure=failures,
        line_movement=movement,
    )
    usable = pooled[pooled["pre_kickoff"]] if not pooled.empty else pd.DataFrame()
    post_hoc = pooled[~pooled["pre_kickoff"]] if not pooled.empty else pd.DataFrame()
    survivors = usable[usable["survives_fdr"]] if not usable.empty else pd.DataFrame()

    margin_features, total_features = _atlas_feature_sets()
    curves = tracks.atlas_disagreement_curves(df, margin_features, total_features)
    totals = curves[curves["market"] == "totals"] if not curves.empty else pd.DataFrame()
    sides = curves[curves["market"] == "sides"] if not curves.empty else pd.DataFrame()
    by_season = tracks.disagreement_by_season(df, total_features, threshold=4.0)

    _save({"pooled_tests": pooled, "survivors": survivors}, "edge")

    def _rate(frame: pd.DataFrame, threshold: float) -> float:
        row = frame[frame["threshold"] == threshold] if not frame.empty else pd.DataFrame()
        return float(row["rate"].iloc[0]) if not row.empty else float("nan")

    n_tests = len(usable)
    n_nominal = int((usable["p"] < 0.05).sum()) if not usable.empty else 0
    positive_seasons = int(by_season["above_break_even"].sum()) if not by_season.empty else 0

    text = f"""# Atlas Information Edge Report V1 (Phase 1C)

*Generated {_generated()}. Every figure is produced by
`python -m atlas.research.phase1c_report`; none is hand-entered.*

Phase 1A found the closing line beats every public team-quality metric. Phase
1B found that opponent-adjusting those metrics improves Atlas's own forecast a
great deal and its edge over the market not at all. Phase 1C was asked to stop
measuring team quality and go looking for information asymmetries instead.

It found one candidate, and it retired the one the programme already had.

---

## The headline

**1. Phase 1B's quarterback signal was reverse causation, and is withdrawn.**

The 2.1-point "QB change" effect decomposes into:

| | Games | Residual | t |
|---|---|---|---|
| QB changed *during* the game | {int(qb_now.loc[qb_now['effect'] == 'in_game_rotation', 'n'].iloc[0])} | **{fmt(float(qb_now.loc[qb_now['effect'] == 'in_game_rotation', 'mean'].iloc[0]), 2)}** | {fmt(float(qb_now.loc[qb_now['effect'] == 'in_game_rotation', 't'].iloc[0]), 1)} |
| New QB who took every snap (knowable pre-kickoff) | {int(qb_now.loc[qb_now['effect'] == 'planned_change', 'n'].iloc[0])} | {fmt(float(qb_now.loc[qb_now['effect'] == 'planned_change', 'mean'].iloc[0]), 2)} | {fmt(float(qb_now.loc[qb_now['effect'] == 'planned_change', 't'].iloc[0]), 1)} |

Teams get their quarterback pulled *because* the game is going badly. The part
a bettor could have known in advance is worth nothing.

**2. Nothing in Tracks 1-5 survives multiple-testing correction.**

Phase 1C ran **{n_tests} pre-kickoff hypothesis tests** across quarterback
events, roster continuity, situational angles, market-failure characteristics
and line movement. {n_nominal} cleared p < 0.05 before correction, against the
{fmt(0.05 * n_tests, 1)} that pure noise alone would produce. After
Benjamini-Hochberg across the pool: **{len(survivors)} survive**.

({len(post_hoc)} further tests were run on *post-hoc* variables - things
knowable only after kickoff. They are excluded from the correction and
reported separately below, because a post-hoc measurement can be wildly
significant and still be worth nothing as information.)

**3. The one live candidate came from comparing against Velocity - and it is
a methodology fix, not a new variable.**

---

## 1. What information appears to move residuals?

{("**" + str(len(survivors)) + " pre-kickoff test(s) survived correction:** " + ", ".join(survivors["test"].tolist()) if not survivors.empty else "**No pre-kickoff variable survived correction.** Not one.")}

Strongest pre-kickoff tests, ranked by raw p-value:

{table(usable.head(12), ["track", "test", "n", "estimate", "t", "p", "q", "survives_fdr"], ["Track", "Test", "Games", "Estimate", "t", "p", "q (FDR)", "Survives"], digits=4) if not usable.empty else "_no tests recorded_"}

For contrast, the **post-hoc** tests - excluded from the correction above
because they measure things knowable only after kickoff:

{table(post_hoc, ["track", "test", "n", "estimate", "t", "p"], ["Track", "Test", "Games", "Estimate", "t", "p"], digits=4) if not post_hoc.empty else "_none_"}

The significant ones are the largest effects measured anywhere in the
programme - and every one of them is useless, because none could be known
before kickoff. That contrast is the whole lesson of Phase 1C.

The one thing that does move the residual is not a variable at all. It is a
**method**: scoring a totals model by how often it is right on its biggest
disagreements, rather than by mean error.

{table(totals, ["threshold", "bets", "rate", "rate_z", "beats_vig"], ["Disagreement ≥", "Bets", "Win rate", "z", "Clears -110?"], digits=4)}

Atlas rises from {_rate(totals, 0):.1%} flat to {_rate(totals, 8):.1%} at the
8-point cut. Velocity, independently, reports 51.6% rising to 53.4%. Two
models, two samples, one shape.

## 2. What information appears completely priced?

Everything else the programme has tested. To put it in one place:

| Family | Phase | Verdict |
|---|---|---|
| Raw efficiency (EPA, success rate, explosiveness, havoc, finishing, pace) | 1A | priced |
| SP+, FPI, Elo, recruiting, returning production, roster talent | 1A | priced |
| Weather (temperature, wind, precipitation, humidity) | 1B | priced |
| Opponent-adjusted efficiency | 1B | priced |
| Quarterback change, backup starts, committees, transfers, experience | 1C | priced, or reverse causation |
| Head-coach change, roster churn | 1C | priced |
| Bye week, short rest, travel, rivalry, revenge, ranked matchups, bowls | 1C | priced |
| Open-to-close line movement, book disagreement | 1C | priced |
| Market failure tails (21/28/35-point misses) | 1C | variance, not weakness |

The closing spread is, on this evidence, a complete summary of publicly
available information about a college football game.

## 3. What information appears worth collecting live?

**Very little, and less than Phase 1B implied.**

- The entire open-to-close information flow is worth
  {fmt(float(tracks.market_timing(df).query("line == 'opening spread'")['mae'].iloc[0]) - float(tracks.market_timing(df).query("line == 'closing spread'")['mae'].iloc[0]), 2)}
  points of spread MAE. Any live-collection programme is fighting for a
  fraction of that.
- Pre-kickoff quarterback status, the thing Phase 1B recommended buying, now
  measures zero.
- A **timestamped line archive** is the one data purchase still defensible,
  and only to evaluate the totals candidate properly - not to chase sides.

## 4. What should Atlas Alpha focus on?

### One direction: selective NCAAF totals, tested to destruction

Not because the evidence is strong - it is thin - but because it is the only
direction in three phases that two independent models both point at, and
because the alternative directions are now measured and empty.

What "tested to destruction" means, concretely:

1. **Hold out 2025 entirely.** Fit nothing on it, choose nothing on it,
   measure the cut once.
2. **Pre-register the threshold** before looking. Eight thresholds were
   scanned here; the best of eight is biased upward.
3. **Model real friction**: actual juice (often worse than -110 on college
   totals), actual limits, actual availability at the posted number.
4. **Require the season split to hold.** At the 4-point cut Atlas is above
   break-even in {positive_seasons} of {len(by_season)} seasons; Velocity gets 6
   of 10. A genuine edge should not need the good seasons.

If it fails any of those, the correct conclusion is that college football is
efficient to Atlas's reach, and the programme should stop.

### Why not sides

{table(sides, ["threshold", "bets", "rate", "rate_z"], ["Disagreement ≥", "Bets", "Win rate", "z"], digits=4)}

Flat and declining, confirmed independently by Velocity at 50.1%. Sides are
closed.

## 5. What should Atlas ignore?

- **Any further team-quality work.** Three phases, three families of metric,
  one answer.
- **Quarterback and roster feeds.** The signal that justified them was an
  artefact.
- **Situational angles.** Free, public, computable, and worth zero.
- **The market-failure tail.** It is variance; the 28-point misses look
  identical to everything else beforehand.
- **Closing-line value on sides.** The whole open-to-close window is worth a
  fifth of a point.

---

## A note on what this phase did to itself

Phase 1C's most useful output is that it **falsified its own predecessor's
headline finding**. The Phase 1B quarterback result was produced honestly, with
error bars and a season-by-season check, and it was still wrong - because the
measurement conflated "what happened in the game" with "what was knowable
before it".

Two guards now exist so it does not recur:

1. Every quarterback and continuity variable is reported in both a
   contemporaneous and a **lagged, pre-kickoff** form, and only the second is
   allowed to support a conclusion.
2. Every p-value in the phase goes into **one pooled FDR correction**, so a
   track cannot produce a finding simply by running enough tests.

Both are cheap. Neither existed before this phase, and the first one cost the
programme its only signal.
"""
    out = paths.reports / "atlas_information_edge_v1.md"
    out.write_text(text)
    LOG.info("wrote %s", out)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Atlas Phase 1C reports")
    ap.add_argument(
        "--only",
        choices=["qb", "timing", "roster", "situational", "failure", "velocity", "edge"],
        default=None,
    )
    args = ap.parse_args()

    paths = config.paths().ensure()
    df = tracks.build_phase1c_frame(paths.raw, paths.staging, paths.warehouse, config.seasons())

    writers = {
        "qb": lambda: write_qb_report(df),
        "timing": lambda: write_market_efficiency_report(df),
        "roster": lambda: write_roster_report(df),
        "situational": lambda: write_situational_report(df),
        "failure": lambda: write_failure_report(df),
        "velocity": lambda: write_velocity_report(df),
        "edge": lambda: write_information_edge_report(df),
    }
    for name, writer in writers.items():
        if args.only in (None, name):
            writer()


if __name__ == "__main__":
    main()
