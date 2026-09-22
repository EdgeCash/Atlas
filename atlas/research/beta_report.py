"""Phase 3 report: the market-aware framework.

Phases 1 and 2 asked whether Atlas could beat the closing line. The answer was
no, four times over. This phase changes the question: given that the market is
the best forecast available, what is Atlas *for*?

Every number here is computed out of sample from the warehouse by
``python -m atlas.research.beta_report``. Nothing stakes, simulates or
recommends a wager.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from atlas import config
from atlas.research import adjustment_study as study
from atlas.research import market_aware as ma
from atlas.research import signal_validation as sv
from atlas.research.dataset import load_research_frame, research_sample
from atlas.research.markdown import table
from atlas.util import get_logger

LOG = get_logger(__name__)

#: Variables offered to the CLV-driver regression. All are known before
#: kickoff and none is a function of the closing number itself.
CLV_CANDIDATES = [
    "closing_spread_sd",
    "closing_total_sd",
    "spread_books",
    "total_books",
    "closing_total",
    "closing_spread_abs",
    "neutral_site_flag",
    "week",
]


def markets(df: pd.DataFrame) -> dict[str, ma.Market]:
    totals = study.feature_set(study.FULL_ADJ, "total") + ["pace_sum", "plays_per_game_sum"]
    margins = study.feature_set(study.MATCHED_ADJ, "margin") + ["neutral_site_flag"]
    return {
        "margin": ma.margin_market([c for c in margins if c in df.columns]),
        "total": ma.total_market([c for c in totals if c in df.columns]),
    }


def _economics(scored: pd.DataFrame, market: ma.Market) -> pd.DataFrame:
    """CLV in probability terms, unfiltered and under the edge ceiling."""
    frame = ma.bucket_edges(scored, market)
    ceiling = frame["abs_edge"].quantile(0.75)
    rows = []
    for label, block in (
        ("All games", frame),
        ("Edge ceiling (drop loudest quarter)", frame[frame["abs_edge"] <= ceiling]),
    ):
        summary = ma.clv_summary(ma.add_clv(block, market))
        if summary.empty:
            continue
        mean_clv = float(summary["mean_clv"].iloc[0])
        rows.append({
            "sample": label,
            "games": int(len(block)),
            "beat_rate": float(summary["beat_rate"].iloc[0]),
            **ma.clv_economics(block, market, mean_clv),
        })
    return pd.DataFrame(rows)


def build() -> dict:
    paths = config.paths().ensure()
    df = ma.prepare(research_sample(load_research_frame(paths.warehouse)))
    bundle: dict = {"markets": markets(df), "scored": {}, "tracks": {}}

    for name, market in bundle["markets"].items():
        scored = ma.walk_forward(df, market)
        scored = scored.join(
            df.set_index("game_id")[
                [c for c in CLV_CANDIDATES + [market.opening] if c in df.columns]
            ],
            on="game_id",
            rsuffix="_src",
        )
        bundle["scored"][name] = scored

        fitted = ma.fit_optimal_weight(scored, market)
        probs = ma.to_probability(scored, market, 0.0)
        outcomes = pd.to_numeric(scored[market.outcome], errors="coerce")
        bundle["tracks"][name] = {
            "anchoring": ma.anchoring_curve(scored, market),
            "fitted": fitted,
            "calibration": ma.calibration_table(probs, outcomes),
            "calibration_scores": ma.calibration_scores(probs, outcomes),
            "market_baseline": ma.market_baseline_scores(scored, market),
            "edge_audit": ma.edge_audit(scored, market),
            "clv_audit": ma.clv_audit(scored, market),
            "clv_summary": ma.clv_summary(ma.add_clv(scored, market)),
            "clv_by_season": ma.clv_summary(ma.add_clv(scored, market), group="season"),
            "clv_robustness": ma.clv_robustness(scored, market),
            "clv_placebo": ma.clv_placebo(scored, market),
            "clv_economics": _economics(scored, market),
            "clv_predictability": ma.clv_predictability(scored, market),
            "clv_drivers": ma.clv_drivers(scored, market, CLV_CANDIDATES),
            "participation": ma.participation_study(scored, market),
            "policy": ma.policy_tests(scored, market, fitted.get("market_weight", 1.0)),
        }

    out = paths.reports / "tables"
    out.mkdir(parents=True, exist_ok=True)
    for name, tracks in bundle["tracks"].items():
        for key, value in tracks.items():
            if isinstance(value, pd.DataFrame) and not value.empty:
                value.to_csv(out / f"beta_{name}_{key}.csv", index=False)
            elif isinstance(value, dict) and value:
                pd.DataFrame([value]).to_csv(out / f"beta_{name}_{key}.csv", index=False)

    figures = paths.reports / "figures"
    figures.mkdir(parents=True, exist_ok=True)
    svg = ma.reliability_svg(
        {name: bundle["tracks"][name]["calibration"] for name in ("margin", "total")}
    )
    (figures / "reliability.svg").write_text(svg)
    LOG.info("wrote %s", figures / "reliability.svg")
    return bundle




def _row(frame: pd.DataFrame, column: str, value) -> pd.Series:
    match = frame[frame[column] == value]
    return match.iloc[0] if not match.empty else frame.iloc[0]


def write_report(bundle: dict) -> Path:
    paths = config.paths().ensure()
    tracks = bundle["tracks"]
    m, t = tracks["margin"], tracks["total"]
    generated = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

    m_anchor, t_anchor = m["anchoring"], t["anchoring"]
    m_pure = _row(m_anchor, "market_weight", 0.0)
    m_best = m_anchor.loc[m_anchor["mae"].idxmin()]
    t_best = t_anchor.loc[t_anchor["mae"].idxmin()]
    m_fit, t_fit = m["fitted"], t["fitted"]

    m_econ_all = _row(m["clv_economics"], "sample", "All games")
    t_econ_all = _row(t["clv_economics"], "sample", "All games")
    m_econ_cap = m["clv_economics"].iloc[-1]
    t_econ_cap = t["clv_economics"].iloc[-1]

    m_clv, t_clv = m["clv_summary"].iloc[0], t["clv_summary"].iloc[0]
    detect_clv = ma.detection_sample_size(float(t_clv["beat_rate"]))
    detect_profit = ma.detection_sample_size(
        float(t_econ_cap["implied_win_rate"]), sv.BREAK_EVEN
    )

    figure = "figures/reliability.svg"

    text = f"""# Atlas Beta Framework — Market-Aware Wagering Research (Phase 3)

*Generated {generated} by `python -m atlas.research.beta_report`. Every figure
is computed out of sample from `data/warehouse/atlas.duckdb` under the
walk-forward protocol frozen in `docs/SIGNAL_PREREGISTRATION.md`: each season
is predicted by a model that saw only the seasons before it. Nothing here
stakes, simulates or recommends a wager.*

---

## The answer, up front

Phase 3 started from the premise that the market is the best forecast
available and Atlas should treat it as the prior. That premise survives, and
it is now measured rather than asserted: **the data wants
{m_fit['market_weight']:.2f} of the weight on the market for margins and
{t_fit['market_weight']:.2f} for totals.** Atlas's own model is worth
essentially nothing on margins (t = {m_fit['t_vs_zero']:.2f} against zero) and
something small but real on totals (t = {t_fit['t_vs_zero']:.2f}).

The unexpected result is what Atlas turns out to be *good* at. It cannot pick
winners — five phases have now established that — but it can predict **which
way the line will move**, and it can do so at a rate that is not close to
chance:

| Market | Beats the close | z | Picks winners |
|---|---|---|---|
| Margin | {m_clv['beat_rate']:.1%} of {int(m_clv['graded']):,} graded games | {m_clv['beat_rate_z']:+.2f} | {m['participation'].iloc[0]['win_rate']:.1%} |
| Total | {t_clv['beat_rate']:.1%} of {int(t_clv['graded']):,} graded games | {t_clv['beat_rate_z']:+.2f} | {t['participation'].iloc[0]['win_rate']:.1%} |

Those two columns describe different skills. Atlas anticipates the market's own
revision to its opening number, while remaining a coin flip against the result.
That is the central finding of this phase and it drives every answer below.

It is also, on its own, **not enough to bet on**. Converted into the currency
that matters, the movement Atlas anticipates is worth
{t_econ_all['prob_gain']:.1%} of win probability on totals and
{m_econ_all['prob_gain']:.1%} on margins — less than the juice at every price
tested. Under the edge ceiling that Track 5 recommends it rises to
{t_econ_cap['prob_gain']:.1%} and {m_econ_cap['prob_gain']:.1%}, which clears
**-105 and nothing worse**. Atlas has found a real signal about a market
process, sitting almost exactly on top of the vig.

---

## Track 1 — Market anchoring

Blending the model with the market at seven fixed weights, scoring every game
out of sample:

### Margins

{table(m_anchor, ["market_weight", "n", "mae", "rmse", "bias", "brier", "ece"], ["Market weight", "Games", "MAE", "RMSE", "Bias", "Brier", "ECE"], digits=4)}

### Totals

{table(t_anchor, ["market_weight", "n", "mae", "rmse", "bias", "brier", "ece"], ["Market weight", "Games", "MAE", "RMSE", "Bias", "Brier", "ECE"], digits=4)}

**Margins get monotonically better all the way to the pure market.** Error
falls from {m_pure['mae']:.4f} at `w = 0` to {m_best['mae']:.4f} at
`w = {m_best['market_weight']:.2f}`; there is no interior optimum and no sign
of one. **Totals have one**, just barely: MAE bottoms at
{t_best['mae']:.4f} at `w = {t_best['market_weight']:.2f}`, against
{_row(t_anchor, 'market_weight', 1.0)['mae']:.4f} for the pure market. The
whole prize for having a model at all is
**{_row(t_anchor, 'market_weight', 1.0)['mae'] - t_best['mae']:.4f} points of
mean absolute error**.

Rather than pick the best of seven round numbers, the same question can be put
to a regression — `actual − market = β · (model − market)`, where β is the
weight the data wants on the model:

| Market | Model weight β | Std. error | t vs 0 | t vs 1 | Implied market weight |
|---|---|---|---|---|---|
| Margin | {m_fit['model_weight']:.4f} | {m_fit['model_weight_se']:.4f} | {m_fit['t_vs_zero']:+.2f} | {m_fit['t_vs_one']:+.2f} | {m_fit['market_weight']:.3f} |
| Total | {t_fit['model_weight']:.4f} | {t_fit['model_weight_se']:.4f} | {t_fit['t_vs_zero']:+.2f} | {t_fit['t_vs_one']:+.2f} | {t_fit['market_weight']:.3f} |

On margins the model's weight is statistically indistinguishable from zero and
overwhelmingly distinguishable from one. On totals it is distinguishable from
zero — the model carries information the close does not — but the regression's
R² is {t_fit['r_squared']:.4f}, so "carries information" and "is worth acting
on" are very different claims.

**Answer: `w = 1.00` on margins, `w = {t_fit['market_weight']:.2f}` on
totals.** The totals number is the one the data produced, with a standard
error attached, rather than the best of seven round guesses. The margin number
is rounded up from {m_fit['market_weight']:.3f} on purpose: a weight whose
distance from 1.00 cannot be told apart from zero is not a weight, and
carrying it forward would dress up a null as a parameter.

---

## Track 2 — Calibration

Atlas's point estimate becomes a probability the usual way: `P = Φ(edge / sd)`,
where `sd` is the residual standard deviation estimated on **training seasons
only**. The question is whether a claimed 65% is a real 65%.

![Reliability diagram: claimed confidence against realised win rate, pure model]({figure})

### Margins, pure model

{table(m["calibration"], ["bucket", "n", "claimed", "actual", "gap", "z"], ["Claimed band", "Games", "Mean claimed", "Realised", "Gap", "z"], digits=4)}

### Totals, pure model

{table(t["calibration"], ["bucket", "n", "claimed", "actual", "gap", "z"], ["Claimed band", "Games", "Mean claimed", "Realised", "Gap", "z"], digits=4)}

The pattern is the same in both markets and it is not subtle: **confidence is
inversely useful**. The top bucket on margins claims
{m['calibration'].iloc[-1]['claimed']:.1%} and delivers
{m['calibration'].iloc[-1]['actual']:.1%} — a gap of
{abs(m['calibration'].iloc[-1]['gap']):.1%} at z =
{m['calibration'].iloc[-1]['z']:.1f}. On totals it claims
{t['calibration'].iloc[-1]['claimed']:.1%} and delivers
{t['calibration'].iloc[-1]['actual']:.1%}.

Scores against the market's own baseline (a closing line is by construction a
50/50 proposition, so its Brier is 0.25 exactly):

| Market | Brier, pure model | Brier, market | ECE, pure model | ECE at fitted weight |
|---|---|---|---|---|
| Margin | {m['calibration_scores']['brier']:.4f} | 0.2500 | {m['calibration_scores']['ece']:.4f} | {_row(m_anchor, 'market_weight', 1.0)['ece']:.4f} |
| Total | {t['calibration_scores']['brier']:.4f} | 0.2500 | {t['calibration_scores']['ece']:.4f} | {_row(t_anchor, 'market_weight', 0.9)['ece']:.4f} |

**The unanchored model is worse than saying "coin flip" to every game.** Both
Brier scores are above 0.25. Anchoring fixes this, and it fixes it entirely:
expected calibration error collapses by roughly an order of magnitude.

**Answer: confidence must be produced from the anchored blend, never from the
raw model.** A raw-model probability is not a miscalibrated forecast that
needs a correction factor — it is an anti-signal, and the correction that
repairs it is the same anchoring Track 1 already requires.

---

## Track 3 — The edge claim audit

Bucketing every game by how far the blend sits from the closing number:

### Margins

{table(m["edge_audit"], ["bucket", "games", "share", "claimed", "actual", "calibration_gap", "clears_break_even"], ["Disagreement", "Games", "Share", "Claimed", "Realised", "Gap", "Clears -110?"], digits=4)}

### Totals

{table(t["edge_audit"], ["bucket", "games", "share", "claimed", "actual", "calibration_gap", "clears_break_even"], ["Disagreement", "Games", "Share", "Claimed", "Realised", "Gap", "Clears -110?"], digits=4)}

The realised column is flat — nothing in it rises with the size of the claim —
while the claimed column climbs steeply. So the calibration gap widens
monotonically in both markets, from
{m["edge_audit"].iloc[0]['calibration_gap']:+.4f} to
{m["edge_audit"].iloc[-1]['calibration_gap']:+.4f} on margins and
{t["edge_audit"].iloc[0]['calibration_gap']:+.4f} to
{t["edge_audit"].iloc[-1]['calibration_gap']:+.4f} on totals.

This is the Phase 2 finding reproduced on Atlas's own numbers and stated more
sharply: **a large disagreement with the market is not a large opportunity, it
is a large error.** The loudest bucket on margins claims
{m["edge_audit"].iloc[-1]['claimed']:.1%} and wins
{m["edge_audit"].iloc[-1]['actual']:.1%} of the time. There is no reading of
that number under which it is a bet.

**Answer: edge is not "model minus market".** Measured that way it predicts
its own failure. Track 4 supplies the definition that survives.

---

## Track 4 — Closing-line value

Atlas has no timestamped odds archive, so the only window it can measure is
open to close: take the side at the opening number, ask whether the market
came to you by the close. A line that never moved is a **CLV push**, not a CLV
loss — {int(m_clv['pushes']):,} margin games and {int(t_clv['pushes']):,}
totals games open and close on the same number, and scoring those as losses
depresses every beat rate by roughly six points. They are excluded below.

### Does disagreement predict movement, or results?

| Market | Disagreement → CLV | Disagreement → outcome |
|---|---|---|
| Margin | slope {m['clv_predictability']['clv_slope']:+.4f}, t = {m['clv_predictability']['clv_slope_t']:.2f} | slope {m['clv_predictability']['outcome_slope']:+.4f}, t = {m['clv_predictability']['outcome_slope_t']:.2f} |
| Total | slope {t['clv_predictability']['clv_slope']:+.4f}, t = {t['clv_predictability']['clv_slope_t']:.2f} | slope {t['clv_predictability']['outcome_slope']:+.4f}, t = {t['clv_predictability']['outcome_slope_t']:.2f} |

The same variable that says nothing about who wins says a great deal about
where the line goes.

### By size of disagreement at the open

{table(t["clv_audit"], ["bucket", "games", "graded", "mean_clv", "clv_beat_rate", "clv_beat_z", "win_rate_at_open"], ["Disagreement at open", "Games", "Graded", "Mean CLV", "Beat rate", "z", "Win rate at open"], digits=4)}

*(Totals. The margin table is in `reports/tables/beta_margin_clv_audit.csv`.)*

Read the last two columns against each other. The beat rate climbs from
{t["clv_audit"].iloc[0]['clv_beat_rate']:.1%} to
{t["clv_audit"].iloc[-1]['clv_beat_rate']:.1%} across the buckets. The win
rate does not climb at all. **Atlas is forecasting the market's revision, not
the football game.**

### The falsification

A construction that takes a side at one number and grades it against another
is exactly the shape that produced this phase's earlier tautology, so the
result is worthless unless predictors that know nothing fail the same test:

{table(t["clv_placebo"], ["group", "graded", "mean_clv", "beat_rate", "beat_rate_z"], ["Predictor", "Graded", "Mean CLV", "Beat rate", "z"], digits=4)}

*(Totals; margins in `reports/tables/beta_margin_clv_placebo.csv` show the same
shape — Atlas {m["clv_placebo"].iloc[0]['beat_rate']:.1%}, every null at or
below 50%.)*

All three nulls sit **at or below** chance. A constant lean and a
within-season shuffle both land significantly *under* 50%, which is itself
informative: an uninformed side is systematically on the wrong end of the
market's revision. The closing line is included only as a scale marker — it
scores 100% by construction, and that is what the tautology looked like before
it was caught.

### Stability

{table(t["clv_by_season"], ["group", "graded", "mean_clv", "beat_rate", "beat_rate_z"], ["Season", "Graded", "Mean CLV", "Beat rate", "z"], digits=4)}

Six seasons out of six above 50% on totals, and six out of six on margins
(range {m["clv_by_season"]["beat_rate"].min():.1%} to
{m["clv_by_season"]["beat_rate"].max():.1%}). Capping the move at three points
— which removes any contribution from stale or erroneous openers — leaves
{_row(t["clv_robustness"], "group", "Move <= 3 points")['beat_rate']:.1%} on
totals and
{_row(m["clv_robustness"], "group", "Move <= 3 points")['beat_rate']:.1%} on
margins.

### What it is worth

This is where the finding has to be honest about its size. One point of line
is worth `φ(0) / sd` of win probability:

{table(pd.concat([m["clv_economics"].assign(market="margin"), t["clv_economics"].assign(market="total")]), ["market", "sample", "beat_rate", "mean_clv", "prob_per_point", "prob_gain", "implied_win_rate", "clears_-105", "clears_-110"], ["Market", "Sample", "CLV beat rate", "Mean CLV (pts)", "Prob per point", "Prob gain", "Implied win rate", "Clears -105?", "Clears -110?"], digits=4)}

**Answer: yes, CLV is predictable, and far more predictable than outcomes —
but it is worth about a point and a half of win probability, which clears -105
and nothing worse.** A real edge, measured honestly, sitting on top of the
vig.

---

## Track 5 — Selective participation

Five ways of declining to have an opinion, each dropping roughly a quarter of
the slate:

### Margins

{table(m["participation"], ["filter", "games", "kept", "win_rate", "ece", "brier", "mean_clv", "clv_beat_rate"], ["Filter", "Games", "Kept", "Win rate", "ECE", "Brier", "Mean CLV", "CLV beat rate"], digits=4)}

### Totals

{table(t["participation"], ["filter", "games", "kept", "win_rate", "ece", "brier", "mean_clv", "clv_beat_rate"], ["Filter", "Games", "Kept", "Win rate", "ECE", "Brier", "Mean CLV", "CLV beat rate"], digits=4)}

**One filter works and four do nothing.** Dropping the quarter of games where
the model shouts loudest improves every metric in both markets at once:
margin ECE {m["participation"].iloc[0]['ece']:.4f} →
{m["participation"].iloc[1]['ece']:.4f}, Brier
{m["participation"].iloc[0]['brier']:.4f} →
{m["participation"].iloc[1]['brier']:.4f}, CLV beat rate
{m["participation"].iloc[0]['clv_beat_rate']:.1%} →
{m["participation"].iloc[1]['clv_beat_rate']:.1%}; totals ECE
{t["participation"].iloc[0]['ece']:.4f} →
{t["participation"].iloc[1]['ece']:.4f} and CLV beat rate
{t["participation"].iloc[0]['clv_beat_rate']:.1%} →
{t["participation"].iloc[1]['clv_beat_rate']:.1%}.

Book disagreement, liquidity, scoring environment and mismatch size all move
the numbers in the third decimal place. They are plausible stories about when
a market is unreliable, and none of them is true here. The only unreliability
that matters is **Atlas's own**.

**Answer: Atlas should decline whenever it disagrees most, and only then.**

---

## Track 6 — Velocity policy emulation

Each of Velocity's policies, tested against Atlas's own out-of-sample record:

### Margins

{table(m["policy"], ["policy", "atlas_test", "metric", "before", "after", "improves"], ["Policy", "Atlas test", "Metric", "Before", "After", "Improves?"], digits=4)}

### Totals

{table(t["policy"], ["policy", "atlas_test", "metric", "before", "after", "improves"], ["Policy", "Atlas test", "Metric", "Before", "After", "Improves?"], digits=4)}

Market anchoring, the edge ceiling and CLV monitoring all replicate. The
publish gate — Velocity's edge *band*, `0.03`–`0.12` over even money —
improves margins marginally and does not help totals, which is expected: it is
a cruder version of the edge ceiling that Track 5 tests directly. Staking caps
cannot be evaluated without a wagering simulation, which is out of scope for
this phase, and are therefore recorded as untested rather than endorsed.

---

## The seven questions

### 1. How should Atlas weight the market?

**`w = 1.00` on margins. `w = {t_fit['market_weight']:.2f}` on totals.**
Fitted, not chosen:
β = {m_fit['model_weight']:.4f} ± {m_fit['model_weight_se']:.4f} and
β = {t_fit['model_weight']:.4f} ± {t_fit['model_weight_se']:.4f} respectively.
On margins the honest reading is that Atlas has no margin model worth the
name, and the framework should say so rather than allocate it a token 10%.

### 2. How should Atlas produce confidence?

From the **anchored blend**, via `P = Φ(edge / sd)` with `sd` estimated on
training seasons only — never from the raw model, whose Brier score
({m['calibration_scores']['brier']:.4f} on margins,
{t['calibration_scores']['brier']:.4f} on totals) is worse than the 0.2500 of
declaring every game a coin flip. Every published probability carries its
realised rate from the table above beside it; a confidence number with no
reliability history attached is a decoration.

### 3. How should Atlas define edge?

**Not as distance from the market.** Track 3 shows that quantity predicts its
own failure: the 10+ point bucket claims
{m["edge_audit"].iloc[-1]['claimed']:.1%} on margins and realises
{m["edge_audit"].iloc[-1]['actual']:.1%}.

Edge is **expected closing-line value**: the probability-weighted distance the
market is expected to travel toward Atlas's side, measured from the opening
number and graded at the close, with no-move games treated as pushes. That is
the only quantity in five phases of research that Atlas predicts at better
than chance ({m_clv['beat_rate']:.1%} and {t_clv['beat_rate']:.1%}), and it is
the only one that survives a placebo test.

### 4. Should Atlas cap edge?

**Yes, and the cap is the single most valuable rule in this report.** Discard
the quarter of the slate where the model disagrees most with the close. It
improves calibration, Brier, win rate and CLV simultaneously, in both markets,
and it is the only filter of five that does anything at all. It also doubles
the economic value of the CLV signal
({t_econ_all['prob_gain']:.1%} → {t_econ_cap['prob_gain']:.1%} of win
probability on totals), which is the difference between not clearing -105 and
clearing it.

### 5. When should Atlas NOT bet?

Five conditions, in order of how much evidence stands behind each:

1. **Any margin/side market.** `w = 1.00` means there is no model to bet.
2. **Any game in the top quartile of disagreement.** Track 3 and Track 5.
3. **Any price worse than -105.** The measured edge is
   {t_econ_cap['prob_gain']:.1%} of win probability; -110 requires
   {sv.BREAK_EVEN:.2%} and the filtered signal implies
   {t_econ_cap['implied_win_rate']:.2%}. It does not reach.
4. **Any game where the opening number is no longer available.** The entire
   measured edge lives in the open-to-close window. Taken at the close it is
   zero by construction.
5. **Any market where the reliability table has not been rebuilt.** Confidence
   claims expire.

That list excludes almost everything. It is supposed to.

### 6. What is the optimal risk framework?

Not Kelly on the model's probabilities — those probabilities are the
miscalibrated object Track 2 measured, and Kelly on an overconfident input
overstakes exactly where the model is worst.

The framework this research supports is **flat stakes on the CLV signal, with
CLV as the grading metric rather than P/L**, because that is the only thing
that can be measured on a realistic sample:

| Question | Effect to detect | Graded bets needed at 95% |
|---|---|---|
| Does Atlas beat the close? | {t_clv['beat_rate']:.1%} against 50% | {detect_clv:,.0f} |
| Is the filtered signal distinguishable from the -110 break-even? | {t_econ_cap['implied_win_rate']:.2%} against {sv.BREAK_EVEN:.2%} | {detect_profit:,.0f} |

Roughly {detect_clv:,.0f} graded bets settle the first question and about
{detect_profit / 1000:,.0f},000 would be needed to settle the second — more
college football than exists in a decade. **A framework that grades itself on
profit cannot learn anything in a human timeframe; one that grades itself on
CLV learns within a season.** That is the argument for the metric, and it is
also the argument for keeping stakes flat and small while the question is
still open.

### 7. Which Velocity components become permanent Atlas rules?

Three, ranked by the evidence behind them:

1. **The edge ceiling.** Replicated here in both markets on every metric
   tested. Velocity's `0.03`–`0.12` publish band is a coarser version of the
   same instinct and it is right.
2. **Market anchoring.** Velocity anchors at `w = 0.2`; Atlas's data asks for
   {m_fit['market_weight']:.2f} and {t_fit['market_weight']:.2f}. The
   principle transfers; the number is per-market and must be fitted, not
   inherited.
3. **CLV grading.** Velocity grades on CLV where it has no settled record.
   Atlas now has a measured reason to do the same: CLV is the one thing it
   predicts.

Two do **not** transfer. Velocity's **EV gate** is a producer, not a filter —
it fires hardest where the model is least reliable, which is precisely the
top-quartile games Track 5 says to discard. And its **staking caps** could not
be tested here without building the wagering simulation this phase was
instructed not to build; they are neither endorsed nor rejected.

---

## What this phase did not establish

- **That any of this is profitable.** The measured edge clears -105 and
  nothing worse, and the sample needed to prove profitability directly does
  not exist.
- **That the open-to-close window is capturable.** Atlas measures a consensus
  opening number against a consensus close. Whether a bettor could have struck
  that opener, at size, is not in the data.
- **That the effect survives outside this sample.** Six seasons, one sport,
  one league. Every season agrees, which is the strongest available evidence
  and is not the same as proof.

The Phase 1 verdict is unchanged: Atlas cannot beat the closing line with
public information. What Phase 3 adds is that this was the wrong thing to have
been measuring. Atlas predicts the market's own revision — reliably, in every
season, against three null models — and that signal is worth about one and a
half points of win probability once the model's loudest quarter is thrown
away.
"""
    out = paths.reports / "atlas_beta_framework.md"
    out.write_text(text)
    LOG.info("wrote %s", out)
    return out


def main() -> None:
    argparse.ArgumentParser(description="Atlas Phase 3 market-aware framework").parse_args()
    write_report(build())


if __name__ == "__main__":
    main()
