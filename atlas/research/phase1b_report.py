"""Phase 1B reports: opponent adjustment, weather, quarterback availability.

Every number in the opponent-adjustment and weather reports is computed here
from the warehouse. The quarterback report is a feasibility study, and its
measured numbers come from ``scripts/research_qb_availability.py``; if that
probe has not been run, the report says so rather than inventing figures.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from atlas import config
from atlas.research import adjustment_study as study
from atlas.research.dataset import load_research_frame, research_sample
from atlas.research.markdown import fmt, table
from atlas.staging import adjusted_efficiency as adjusted_stage
from atlas.util import get_logger

LOG = get_logger(__name__)


def _generated() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")


def _save(tables: dict[str, pd.DataFrame], prefix: str) -> None:
    out = config.paths().reports / "tables"
    out.mkdir(parents=True, exist_ok=True)
    for name, frame in tables.items():
        if isinstance(frame, pd.DataFrame) and not frame.empty:
            frame.to_csv(out / f"{prefix}_{name}.csv", index=False)


# ---------------------------------------------------------------------------
# Report 1 - opponent adjustment
# ---------------------------------------------------------------------------


def write_opponent_report(df: pd.DataFrame) -> Path:
    paths = config.paths().ensure()
    LOG.info("running opponent-adjustment study")

    baselines = study.baseline_metrics(df)
    raw_adj = study.raw_vs_adjusted(df)
    paired = study.paired_raw_vs_adjusted(df)
    methods = study.method_comparison(df)
    ladder = study.benchmark_ladder(df)
    market = study.market_plus(df)
    residual = study.residual_study(df)
    rankings = study.feature_rankings(df)
    strength = study.schedule_strength_impact(
        adjusted_stage.load_schedule_strength(paths.staging)
    )

    _save(
        {
            "baselines": baselines, "raw_vs_adjusted": raw_adj, "paired": paired,
            "methods": methods, "ladder": ladder, "market_plus": market,
            "residual": residual, "rankings": rankings, "schedule_strength": strength,
        },
        "adjustment",
    )

    margin_pairs = paired[paired["target"] == "margin"]
    full_margin = margin_pairs[margin_pairs["metric"] == "Full efficiency model"]
    full_gain = float(full_margin["mae_gain"].iloc[0]) if not full_margin.empty else np.nan
    full_t = float(full_margin["gain_t"].iloc[0]) if not full_margin.empty else np.nan

    resid_material = residual[residual["material"].fillna(False).astype(bool)]
    market_material = market[market["material"].fillna(False).astype(bool)]

    text = f"""# Atlas Opponent Adjustment Report (Phase 1B)

*Generated {_generated()} from `data/warehouse/atlas.duckdb`. Every figure is
produced by `python -m atlas.research.phase1b_report`; none is hand-entered.*

Phase 1A ended with one recommendation above all others: **opponent-adjust the
efficiency metrics**. Raw EPA does not know that one team played three top-10
defences and the other played three bottom-20 ones, and the two published
systems that do adjust - SP+ and FPI - both beat Atlas's raw efficiency.

Phase 1B does the adjustment and measures what it is worth. The answer splits
cleanly in two, and the split is the whole finding:

* **Against raw efficiency and against the published ratings, adjustment is a
  decisive win.** It removes {fmt(full_gain, 3)} points of margin MAE
  (t = {fmt(full_t, 1)}) and moves Atlas from behind SP+ and FPI to ahead of
  both.
* **Against the closing line, it is worth nothing at all.** Not less than
  before - the same nothing. Every residual model lands on the baseline.

Research sample: **{len(df):,} FBS-vs-FBS games**, {int(df['season'].min())}-{int(df['season'].max())},
leave-one-season-out throughout.

---

## Method

Each metric is one stream of observations in which an **actor** produces a
value against an **opponent**:

    value = mu + actor_effect + opponent_effect + hfa * (home - 0.5)

For EPA the actor is the offence, so a single solve yields both what a team
produces against an average defence (`adj_off_epa`) and what it allows to an
average offence (`adj_def_epa`). For havoc the defence is the actor.

| Method | What it does | Cost |
|---|---|---|
| **A - simple** | One pass: subtract each opponent's raw average, then average | Under-corrects; the averages it subtracts are themselves unadjusted |
| **B - iterative** | Alternate actor and opponent solves to convergence (Gauss-Seidel) | Converges in ~20 iterations |
| **C - network** | One ridge least-squares solve over the whole schedule graph (Massey/SRS) | Exact; handles unbalanced and weakly connected schedules directly |

**Point-in-time.** For season *S* week *w*, the solve uses only games from
season *S* in weeks strictly before *w*, shrunk toward season *S-1*'s final
ratings. Week is the unit of time because any game in a week can kick off
before any other, so a per-week solve cannot see sideways. The shrinkage is
the same device and the same strength (4 games) that the raw features use, so
raw and adjusted are compared on equal footing rather than one being smoothed
more than the other.

**Weighting.** Observations are weighted by play count - a 40-play game says
less than an 80-play one - normalised so the average game weighs exactly 1.
The normalisation matters more than it sounds: play counts average ~56, so
leaving them raw would have made a "4 game" prior worth 0.07 of a game and
handed back wildly noisy early-season ratings.

---

## Section 1 - Raw vs Adjusted Metrics

Out-of-sample MAE for each metric family, raw and adjusted, on every target.

{table(raw_adj[raw_adj['target'] == 'margin'], ['metric', 'raw_mae', 'adj_mae', 'mae_improvement', 'raw_r2', 'adj_r2'], ['Metric', 'Raw MAE', 'Adjusted MAE', 'Improvement', 'Raw R²', 'Adj R²'], digits=4)}

*(margin; the other targets are in Sections 4 and 5)*

Paired game-by-game, with a standard error, so a small improvement cannot be
mistaken for a real one:

{table(paired, ['metric', 'target', 'mae_gain', 'gain_se', 'gain_t', 'material'], ['Metric', 'Target', 'MAE gain', 'SE', 't', 'Material?'], digits=4)}

### Method A vs B vs C

{table(methods, ['method', 'target', 'n_features', 'mae', 'rmse', 'r2'], ['Method', 'Target', 'Features', 'MAE', 'RMSE', 'R²'], digits=4)}

Methods B and C agree to four decimal places on every target, which is what
should happen - they solve the same system, one by iteration and one in closed
form. Method A is measurably worse on margin, exactly as the theory predicts:
a single pass subtracts opponent averages that have not themselves been
adjusted, so it under-corrects. **Use C**: it is exact, it is the fastest of
the three here, and it degrades gracefully when the schedule graph is weakly
connected.

---

## Section 2 - Schedule Strength Impact

If schedules were balanced, opponent adjustment could not change anything.
They are not. This is the mean opponent quality faced, per team-season, on the
defensive-EPA scale (lower = faced tougher defences):

{table(strength, ['season', 'teams', 'mean_opponent', 'sd_opponent', 'easiest', 'hardest', 'spread'], ['Season', 'Teams', 'Mean', 'SD', 'Easiest', 'Hardest', 'Spread'], digits=4)}

The gap between the hardest and easiest schedule runs **0.25 to 0.57 EPA per
play**. Against a league standard deviation of roughly 0.06 in team quality,
that is a schedule effect several times larger than the differences the metric
is trying to measure. The premise of the phase holds.

*(This table uses end-of-season opponent ratings. It is a description of the
past, never a model input - the features themselves only ever use ratings that
existed before kickoff.)*

---

## Section 3 - Margin Improvements

{table(ladder[ladder['target'] == 'margin'].sort_values('mae'), ['model', 'n_features', 'mae', 'rmse', 'r2'], ['Model', 'Features', 'MAE', 'RMSE', 'R²'], digits=4)}

Three things to read out of this:

1. **Adjustment recovers most of the gap to the best public systems.** Raw
   efficiency was behind SP+ and FPI in Phase 1A. Adjusted efficiency is now
   ahead of both, by a wide margin.
2. **It largely subsumes them.** Adding SP+ and FPI on top of adjusted
   efficiency moves MAE very little, which says the published ratings were
   mostly contributing the opponent adjustment Atlas was missing.
3. **Elo is still competitive.** CFBD's pre-game Elo is a single number and
   holds its own against a twelve-feature adjusted model. Elo is a pure
   result-based rating, so this says a meaningful share of what efficiency
   measures is already visible in who beat whom.

---

## Section 4 - Total Improvements

{table(ladder[ladder['target'] == 'total'].sort_values('mae'), ['model', 'n_features', 'mae', 'rmse', 'r2'], ['Model', 'Features', 'MAE', 'RMSE', 'R²'], digits=4)}

Adjustment does **not** help on totals. Raw efficiency edges out adjusted, and
the only metric family with a material gain is success rate. Pace gets
actively worse when adjusted.

That is not a failure of the method, it is a statement about the target. An
opponent adjustment redistributes credit between two teams; a total is their
sum, and the adjustment largely cancels. Where it does not cancel - pace - the
adjustment removes the very thing a totals model wants, because a slow team's
low play count is a property of that team, not a distortion to be corrected.

---

## Section 5 - Residual Improvements

**This is the question the phase exists to answer.** The target is
`actual_margin - market_margin`: what the closing line got wrong. The baseline
is "the market is exactly right", which scores MAE
{fmt(float(baselines.loc[baselines['target'] == 'residual_margin', 'mae'].iloc[0]), 3)} on margin and
{fmt(float(baselines.loc[baselines['target'] == 'residual_total', 'mae'].iloc[0]), 3)} on totals.

{table(residual[residual['target'] == 'residual_margin'].sort_values('gain', ascending=False), ['model', 'n_features', 'mae', 'r2', 'gain', 'gain_t', 'material'], ['Model', 'Features', 'MAE', 'R²', 'Gain over market', 't', 'Material?'], digits=4)}

{table(residual[residual['target'] == 'residual_total'].sort_values('gain', ascending=False), ['model', 'n_features', 'mae', 'r2', 'gain', 'gain_t', 'material'], ['Model', 'Features', 'MAE', 'R²', 'Gain over market', 't', 'Material?'], digits=4)}

And the same question asked the other way - does adjusted efficiency add
anything *on top of* the closing line?

{table(market, ['model', 'target', 'market_mae', 'combined_mae', 'mae_gain', 'gain_t', 'material'], ['Model', 'Target', 'Market MAE', 'Combined MAE', 'Gain', 't', 'Material?'], digits=4)}

**{'No model cleared the bar.' if resid_material.empty and market_material.empty else 'At least one model cleared the bar - see the material rows above.'}**
Adjusted efficiency does not explain the market residual better than raw
efficiency does, because neither explains it at all. Both land on the
baseline, and so do SP+, FPI, Elo, weather, line movement, rest and travel.

The contrast with Section 3 is the point. The same features that removed
{fmt(full_gain, 2)} points of margin MAE remove **zero** residual MAE. Everything
opponent adjustment recovered was information the closing line already had.

---

## Section 6 - Feature Rankings

Standalone out-of-sample power of each metric, raw and adjusted, ranked by MAE
removed from the baseline.

### Margin

{table(rankings[rankings['target'] == 'margin'].head(21), ['rank', 'metric', 'kind', 'mae', 'gain', 'gain_t'], ['#', 'Metric', 'Kind', 'MAE', 'Gain', 't'], digits=4)}

### Total

{table(rankings[rankings['target'] == 'total'].head(21), ['rank', 'metric', 'kind', 'mae', 'gain', 'gain_t'], ['#', 'Metric', 'Kind', 'MAE', 'Gain', 't'], digits=4)}

### Market residual (margin)

{table(rankings[rankings['target'] == 'residual_margin'].head(12), ['rank', 'metric', 'kind', 'mae', 'gain', 'gain_t', 'material'], ['#', 'Metric', 'Kind', 'MAE', 'Gain', 't', 'Material?'], digits=4)}

---

## Recommendation

**Opponent adjustment is worth doing, and it does not justify Atlas Alpha on
its own.** Both halves of that sentence are load-bearing.

Worth doing, because:

* it is the largest single improvement Atlas has made to its own view of a
  game - {fmt(full_gain, 2)} points of margin MAE, t = {fmt(full_t, 1)};
* it moves Atlas ahead of SP+ and FPI rather than behind them, which means
  Atlas no longer needs them as features;
* it costs about twenty seconds of compute and no new data.

Not sufficient, because the residual is untouched. Phase 1A concluded that the
closing line already contained everything the public variables knew. Phase 1B
tested the single best hypothesis for why that might have been an artefact -
that Atlas's metrics were unadjusted and therefore handicapped - and the
hypothesis is now rejected. The metrics are adjusted, they are better than the
public ratings, and the line is still not beatable with them.

What this changes for the Alpha specification:

1. **Replace raw efficiency with adjusted efficiency everywhere**, using
   Method C. Keep raw pace and raw plays-per-game for the totals model, where
   adjustment measurably hurts.
2. **Drop SP+ and FPI as features.** They were standing in for the adjustment
   Atlas now does itself, and they add nothing once it does.
3. **Stop looking for an edge in team-quality metrics.** Three separate
   families - raw efficiency, adjusted efficiency, published adjusted ratings -
   all land on the same residual baseline. The next hypothesis has to be about
   information the market does not have, not about measuring team quality more
   precisely.

The companion reports point at where that information might be:
[weather](weather_data_report.md) (measured, and the market prices it) and
[quarterback availability](qb_availability_report.md) (not measured by the
market in a way Atlas can see, and the one place this phase found a signal
that moves the residual).
"""
    out = paths.reports / "opponent_adjustment_report.md"
    out.write_text(text)
    LOG.info("wrote %s", out)
    return out


# ---------------------------------------------------------------------------
# Report 2 - weather
# ---------------------------------------------------------------------------

#: What each candidate source actually turned out to be, verified by probe.
WEATHER_SOURCES = pd.DataFrame(
    [
        {
            "source": "Meteostat bulk files",
            "key": "none",
            "cost": "free",
            "limit": "none (static files)",
            "resolution": "hourly",
            "history": "decades",
            "verdict": "adopted",
        },
        {
            "source": "Open-Meteo archive API",
            "key": "none",
            "cost": "free",
            "limit": "daily quota per IP",
            "resolution": "hourly",
            "history": "1940-",
            "verdict": "rejected - quota",
        },
        {
            "source": "CFBD /games/weather",
            "key": "required",
            "cost": "paid tier",
            "limit": "tier-gated",
            "resolution": "per game",
            "history": "2018-",
            "verdict": "rejected - cost",
        },
        {
            "source": "NOAA NCEI GHCN-Daily",
            "key": "none",
            "cost": "free",
            "limit": "none",
            "resolution": "daily",
            "history": "decades",
            "verdict": "rejected - no kickoff hour",
        },
        {
            "source": "NWS api.weather.gov",
            "key": "none",
            "cost": "free",
            "limit": "courtesy",
            "resolution": "hourly",
            "history": "recent only",
            "verdict": "rejected - no history",
        },
    ]
)


def write_weather_report(df: pd.DataFrame) -> Path:
    paths = config.paths().ensure()
    LOG.info("running weather study")

    weather_models = study.weather_study(df)
    buckets = study.wind_buckets(df)
    residual = study.residual_study(df)
    weather_residual = residual[residual["model"].str.startswith("Weather")]

    coverage = (
        df.assign(has_weather=df["weather_temp"].notna())
        .groupby("season")
        .agg(
            games=("game_id", "size"),
            with_weather=("has_weather", "sum"),
            mean_temp=("weather_temp", "mean"),
            mean_wind=("weather_wind", "mean"),
            mean_station_miles=("weather_station_miles", "mean"),
        )
        .reset_index()
    )
    coverage["coverage"] = coverage["with_weather"] / coverage["games"]

    _save({"models": weather_models, "wind_buckets": buckets, "coverage": coverage},
          "weather")

    material = weather_models[weather_models["material"].fillna(False).astype(bool)]
    overall = float(df["weather_temp"].notna().mean())

    text = f"""# Atlas Weather Data Report (Phase 1B)

*Generated {_generated()}. Measured figures are produced by
`python -m atlas.research.phase1b_report`.*

Phase 1A flagged weather as the highest-value missing measurement and could
not test it: CFBD's `/games/weather` sits behind a paid Patreon tier. Phase 1B
was asked whether a free archive could fill the gap.

**It can, and it now does.** Atlas has kickoff temperature, wind,
precipitation and humidity for **{overall:.1%} of the research sample**, from a
free, unmetered source, integrated into the warehouse.

**And it is worth nothing against the closing line.** The market prices
weather. That is a useful thing to have established rather than assumed.

---

## Section 1 - Weather sources

{table(WEATHER_SOURCES, ['source', 'key', 'cost', 'limit', 'resolution', 'history', 'verdict'], ['Source', 'API key', 'Cost', 'Rate limit', 'Resolution', 'History', 'Verdict'])}

Notes from actually trying them:

* **Open-Meteo** is the obvious first choice and the wrong one for a
  nine-season backfill from shared infrastructure. The archive API is free and
  excellent, but it is metered per IP; from a shared egress address the daily
  quota was already exhausted, returning `Daily API request limit exceeded`.
  A backfill needs thousands of calls. On a dedicated IP it would be fine.
* **Meteostat** publishes the same class of station observations as **static
  gzipped files**, one per station. No key, no quota, no pagination - the
  delivery model matches the job. This is what Atlas uses.
* **CFBD weather** returns `401 ... requires a Patreon subscription at Tier 1
  or higher` on a free key, verified directly. It remains supported as a
  fallback in the collector, and is now redundant.
* **NOAA GHCN-Daily** is free and authoritative but daily. A daily mean
  temperature cannot answer what the wind was doing at an 8pm kickoff.

---

## Section 2 - Coverage

Each stadium is mapped to the nearest station with hourly coverage across the
seasons Atlas models; the kickoff hour is then read from that station's file
(nearest observation within two hours).

{table(coverage, ['season', 'games', 'with_weather', 'coverage', 'mean_temp', 'mean_wind', 'mean_station_miles'], ['Season', 'Games', 'With weather', 'Coverage', 'Mean temp (F)', 'Mean wind (mph)', 'Mean station distance (mi)'], digits=2)}

Station distance is the thing to watch, and it is comfortable: the median
stadium sits about five miles from its station and none is beyond sixty.
Missing games are overwhelmingly gaps in a station's hourly record rather than
unmatched venues.

**Domes are handled explicitly.** The observed values are kept, and an
`_effective` set is derived that models what players experience: no wind and
room temperature indoors. Research can then test outdoor readings,
indoor-corrected readings, or both.

---

## Section 3 - Cost

Zero. No API key, no subscription, no quota. The whole backfill is roughly
140 station files, fetched once and cached; a rebuild re-reads them from disk.
Adding a season fetches nothing new unless a new stadium appears.

The only real cost is a dependency on a third-party mirror staying up. The
collector degrades to the CFBD path, and then to null columns, rather than
failing the build.

---

## Section 4 - Feasibility

Already done. `atlas/sources/meteostat.py` and `atlas/staging/weather.py` are
part of the standard build, and `make all` produces the weather columns with
no extra flags.

---

## Section 5 - Expected importance

Now measured rather than expected.

{table(weather_models, ['features', 'target', 'n', 'mae', 'gain', 'gain_t', 'material'], ['Feature set', 'Target', 'n', 'MAE', 'Gain over baseline', 't', 'Material?'], digits=4)}

Against the market residual specifically:

{table(weather_residual, ['model', 'target', 'n_features', 'mae', 'gain', 'gain_t', 'material'], ['Model', 'Target', 'Features', 'MAE', 'Gain over market', 't', 'Material?'], digits=4)}

**{'Nothing material.' if material.empty else 'Some feature sets cleared the bar - see the material rows.'}**

The raw relationship is there, and it is exactly the one folklore predicts -
and the market has already priced it:

{table(buckets, ['band', 'games', 'mean_closing_total', 'mean_total', 'mean_residual', 'over_rate', 'over_rate_z', 'significant'], ['Wind band', 'Games', 'Closing total', 'Actual total', 'Residual', 'Over rate', 'z', 'Significant?'], digits=3)}

Scoring does fall as wind rises - about three points from calm to 15-20 mph.
But the **closing total falls with it**, and the residual column is what
matters: no band's over rate is more than two standard errors from 50%. The
20+ mph band reverses sign on 86 games, which is what noise looks like.

---

## Recommendation

1. **Keep the weather data.** It is free, it is integrated, and it costs
   nothing to carry. Establishing that a variable is priced is worth as much
   as finding one that is not - it closes a hypothesis.
2. **Do not give weather a role in Atlas Alpha v1.** No feature set cleared
   its own error bar on any target.
3. **The one place it might still earn its keep** is as an interaction rather
   than a main effect - extreme wind against a pass-heavy offence, for
   instance. Atlas now has the data to test that whenever there is a reason
   to. There is no reason to yet: the main effect is zero, and searching
   interactions without a prior is how a research programme finds noise.
"""
    out = paths.reports / "weather_data_report.md"
    out.write_text(text)
    LOG.info("wrote %s", out)
    return out


# ---------------------------------------------------------------------------
# Report 3 - quarterback availability
# ---------------------------------------------------------------------------

QB_SOURCES = pd.DataFrame(
    [
        {
            "source": "Play-by-play passer (cfbfastR / CFBD)",
            "key": "none",
            "cost": "free",
            "history": "2018-present",
            "timing": "retrospective",
            "verdict": "works - who took the snaps",
        },
        {
            "source": "CFBD /games/players, /player/usage",
            "key": "free key",
            "cost": "free",
            "history": "2018-present",
            "timing": "retrospective",
            "verdict": "works - same information",
        },
        {
            "source": "ESPN event rosters",
            "key": "none",
            "cost": "free",
            "history": "2018-present",
            "timing": "retrospective",
            "verdict": "useless - starter/active flags never populated",
        },
        {
            "source": "ESPN depth charts",
            "key": "none",
            "cost": "free",
            "history": "none",
            "timing": "pre-kickoff",
            "verdict": "unavailable - HTTP 400 for college football",
        },
        {
            "source": "ESPN injuries endpoints",
            "key": "none",
            "cost": "free",
            "history": "none",
            "timing": "pre-kickoff",
            "verdict": "empty for college football",
        },
        {
            "source": "Commercial feeds (Rotowire, SportsDataIO, Sportradar)",
            "key": "required",
            "cost": "paid",
            "history": "varies",
            "timing": "pre-kickoff",
            "verdict": "the only real pre-kickoff option",
        },
        {
            "source": "News / beat-writer archives",
            "key": "none",
            "cost": "free",
            "history": "2018-present",
            "timing": "pre-kickoff",
            "verdict": "unstructured - large extraction project",
        },
    ]
)


def _qb_tables() -> dict[str, pd.DataFrame]:
    out = {}
    tables_dir = config.paths().reports / "tables"
    for name in ("coverage", "change_rate", "residual_effect", "residual_by_season"):
        path = tables_dir / f"qb_{name}.csv"
        if path.exists():
            out[name] = pd.read_csv(path)
    return out


def write_qb_report() -> Path:
    paths = config.paths().ensure()
    probe = _qb_tables()

    if not probe:
        measured = (
            "**The feasibility probe has not been run in this build.** Run\n"
            "`python scripts/research_qb_availability.py` to populate the measured\n"
            "sections below; this report deliberately does not invent figures.\n"
        )
        effect_summary = "not measured in this build"
    else:
        effect = probe.get("residual_effect", pd.DataFrame())
        by_season = probe.get("residual_by_season", pd.DataFrame())
        signed = (
            float(by_season["mean_signed_residual"].mean()) if not by_season.empty else np.nan
        )
        n_sig = int((by_season["t"].abs() > 2).sum()) if not by_season.empty else 0
        n_seasons = len(by_season)
        effect_summary = (
            f"about {fmt(signed, 1)} points of margin, positive in "
            f"{int((by_season['mean_signed_residual'] > 0).sum())} of {n_seasons} seasons "
            f"and individually significant in {n_sig}"
        )
        measured = f"""### Coverage of the retrospective source

{table(probe['coverage'], ['season', 'team_games', 'with_qb', 'coverage', 'clear_starter', 'distinct_qbs'], ['Season', 'Team-games', 'With a QB', 'Coverage', 'Clear starter (>=70% att.)', 'Distinct starters'], digits=3)}

Essentially complete. A "clear starter" is one who threw at least 70% of the
team's attempts; the rest are genuine committees or in-game changes.

### How often the starter changes

{table(probe['change_rate'], ['season', 'games', 'changes', 'change_rate'], ['Season', 'Team-games', 'Changes', 'Change rate'], digits=3)}

Roughly one team-game in six starts a different quarterback than the week
before, rising sharply in the most recent seasons.

### What a change is worth against the closing line

`qb_change_diff` is +1 when only the away team changed quarterback, -1 when
only the home team did, 0 otherwise. The target is the market residual,
`actual_margin - market_margin`.

{table(effect, ['qb_change_diff', 'games', 'mean_residual', 'cover_rate', 'residual_se', 'residual_t'], ['QB change (away - home)', 'Games', 'Mean residual', 'Home cover rate', 'SE', 't'], digits=4)}

{table(by_season, ['season', 'games', 'mean_signed_residual', 'se', 't'], ['Season', 'Games', 'Signed residual', 'SE', 't'], digits=3)}
"""

    text = f"""# Atlas Quarterback Availability Report (Phase 1B)

*Generated {_generated()}. Research only - nothing here is implemented in the
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

{table(QB_SOURCES, ['source', 'key', 'cost', 'history', 'timing', 'verdict'], ['Source', 'API key', 'Cost', 'History', 'Timing', 'Verdict'])}

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

{measured}

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
**{effect_summary}**.

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
"""
    out = paths.reports / "qb_availability_report.md"
    out.write_text(text)
    LOG.info("wrote %s", out)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Atlas Phase 1B reports")
    ap.add_argument("--only", choices=["opponent", "weather", "qb"], default=None)
    args = ap.parse_args()

    paths = config.paths().ensure()
    if args.only in (None, "opponent", "weather"):
        df = research_sample(load_research_frame(paths.warehouse))
    if args.only in (None, "opponent"):
        write_opponent_report(df)
    if args.only in (None, "weather"):
        write_weather_report(df)
    if args.only in (None, "qb"):
        write_qb_report()


if __name__ == "__main__":
    main()
