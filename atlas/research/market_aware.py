"""Phase 3: market-aware research.

The thesis has changed. Atlas is no longer trying to beat the closing line -
four phases established it cannot - so the market stops being a benchmark and
becomes the **prior**. The questions are now about disagreement policy: how
much to weight the market, how confident to be, when to stay silent.

Everything here is measurement. Nothing stakes, simulates or recommends.

Two conventions used throughout:

* **Margin** is home-oriented and the market's point estimate is
  ``market_margin = -closing_spread``. A blended prediction is
  ``w * market + (1 - w) * model``.
* **Probabilities** come from the blended point estimate and an
  out-of-sample residual standard deviation: the home side covers when the
  realised margin beats the market's number, so ``P(cover) = Phi(edge / sd)``
  where ``edge`` is the blend minus the market. The same construction gives
  ``P(over)`` on totals.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats

from atlas.research import signal_validation as sv
from atlas.util import get_logger

LOG = get_logger(__name__)

#: The market weights the brief asks for.
MARKET_WEIGHTS = (0.0, 0.10, 0.25, 0.50, 0.75, 0.90, 1.00)

#: Probability bins for the calibration study.
PROBABILITY_BINS = (0.50, 0.51, 0.52, 0.53, 0.54, 0.55, 0.56, 0.57, 0.58, 0.60, 1.01)

#: Disagreement buckets for the edge audit.
EDGE_BUCKETS = ((0, 1), (1, 2), (2, 4), (4, 6), (6, 8), (8, 10), (10, 1000))


@dataclass(frozen=True)
class Market:
    """One market's column names, so every track runs on both."""

    name: str
    features: tuple[str, ...]
    target: str
    line: str
    outcome: str
    opening: str


def margin_market(features: list[str]) -> Market:
    return Market("margin", tuple(features), "actual_margin", "market_margin",
                  "home_cover", "opening_margin")


def total_market(features: list[str]) -> Market:
    return Market("total", tuple(features), "actual_total", "closing_total",
                  "over_hit", "opening_total")


def prepare(df: pd.DataFrame) -> pd.DataFrame:
    """Add the opening-line columns in the same orientation as the closing ones."""
    out = df.copy()
    out["opening_margin"] = -pd.to_numeric(out["opening_spread"], errors="coerce")
    return out


# ---------------------------------------------------------------------------
# Walk-forward predictions and blending
# ---------------------------------------------------------------------------


def walk_forward(df: pd.DataFrame, market: Market) -> pd.DataFrame:
    """Out-of-sample model predictions, fitting only on prior seasons."""
    frames = []
    for fold in sv.walk_forward_folds():
        block = sv.fit_predict(
            df, list(market.features), market.target, fold.train_seasons, fold.test_seasons
        )
        if block.empty:
            continue
        block = block.copy()
        block["train_seasons"] = len(fold.train_seasons)
        # Residual sd from the training seasons only - it is a model parameter
        # like any other and must not be fitted on the games it scores.
        train = df[df["season"].isin(fold.train_seasons)]
        train_pred = sv.fit_predict(
            df, list(market.features), market.target,
            fold.train_seasons[:-1] or fold.train_seasons, fold.train_seasons[-1:],
        )
        block["model_sd"] = _residual_sd(train_pred, market) or _residual_sd(
            train.assign(prediction=train[market.line]), market
        )
        frames.append(block)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _residual_sd(scored: pd.DataFrame, market: Market) -> float | None:
    if scored.empty or "prediction" not in scored:
        return None
    resid = pd.to_numeric(scored[market.target], errors="coerce") - scored["prediction"]
    sd = float(resid.std(ddof=1))
    return sd if np.isfinite(sd) and sd > 0 else None


def blend(scored: pd.DataFrame, market: Market, weight: float) -> pd.Series:
    """``w`` on the market, ``1 - w`` on the model."""
    model = pd.to_numeric(scored["prediction"], errors="coerce")
    line = pd.to_numeric(scored[market.line], errors="coerce")
    return weight * line + (1 - weight) * model


def anchoring_curve(scored: pd.DataFrame, market: Market) -> pd.DataFrame:
    """Accuracy at every market weight the brief specifies."""
    truth = pd.to_numeric(scored[market.target], errors="coerce")
    rows = []
    for weight in MARKET_WEIGHTS:
        prediction = blend(scored, market, weight)
        mask = prediction.notna() & truth.notna()
        error = prediction[mask] - truth[mask]
        probs = to_probability(scored.loc[mask], market, weight)
        outcomes = pd.to_numeric(scored.loc[mask, market.outcome], errors="coerce")
        rows.append(
            {
                "market_weight": weight,
                "n": int(mask.sum()),
                "mae": float(error.abs().mean()),
                "rmse": float(np.sqrt((error**2).mean())),
                "bias": float(error.mean()),
                "residual_sd": float(error.std(ddof=1)),
                **calibration_scores(probs, outcomes),
            }
        )
    return pd.DataFrame(rows)


def fit_optimal_weight(scored: pd.DataFrame, market: Market) -> dict:
    """Regress the outcome on the market and the model, and read the split.

    This is the same construction Velocity used to find its MLB anchoring
    weight. It answers "what weight does the data want?" rather than "which of
    seven round numbers scored best", and it carries a standard error.
    """
    truth = pd.to_numeric(scored[market.target], errors="coerce")
    line = pd.to_numeric(scored[market.line], errors="coerce")
    model = pd.to_numeric(scored["prediction"], errors="coerce")
    mask = truth.notna() & line.notna() & model.notna()
    if mask.sum() < 200:
        return {}

    # actual - market = beta * (model - market) + noise. beta is the weight the
    # data wants on the MODEL, so the market weight is 1 - beta.
    x = (model[mask] - line[mask]).to_numpy()
    y = (truth[mask] - line[mask]).to_numpy()
    result = stats.linregress(x, y)
    return {
        "n": int(mask.sum()),
        "model_weight": float(result.slope),
        "model_weight_se": float(result.stderr),
        "market_weight": float(1 - result.slope),
        "t_vs_zero": float(result.slope / result.stderr) if result.stderr else np.nan,
        "t_vs_one": float((result.slope - 1) / result.stderr) if result.stderr else np.nan,
        "r_squared": float(result.rvalue**2),
    }


# ---------------------------------------------------------------------------
# Probabilities and calibration
# ---------------------------------------------------------------------------


def to_probability(scored: pd.DataFrame, market: Market, weight: float) -> pd.Series:
    """P(the side the blend favours wins), from the blend's distance to the line."""
    prediction = blend(scored, market, weight)
    line = pd.to_numeric(scored[market.line], errors="coerce")
    sd = pd.to_numeric(scored.get("model_sd"), errors="coerce")
    sd = sd.where(sd > 0, np.nan)
    edge = prediction - line
    return pd.Series(stats.norm.cdf(edge / sd), index=scored.index)


def confidence(probs: pd.Series) -> pd.Series:
    """The claimed probability of the side actually taken - always >= 0.5."""
    return probs.where(probs >= 0.5, 1 - probs)


def realised(probs: pd.Series, outcomes: pd.Series) -> pd.Series:
    """Did the side the model favoured actually win?"""
    return pd.Series(np.where(probs >= 0.5, outcomes, 1 - outcomes), index=probs.index)


def calibration_table(
    probs: pd.Series, outcomes: pd.Series, bins: tuple[float, ...] = PROBABILITY_BINS
) -> pd.DataFrame:
    """Claimed confidence versus realised rate, bucket by bucket."""
    conf = confidence(probs)
    won = realised(probs, outcomes)
    frame = pd.DataFrame({"confidence": conf, "won": won}).dropna()
    if frame.empty:
        return pd.DataFrame()
    frame["bucket"] = pd.cut(frame["confidence"], bins=list(bins), right=False)
    rows = []
    for bucket, block in frame.groupby("bucket", observed=True):
        n = len(block)
        if n < 20:
            continue
        claimed = float(block["confidence"].mean())
        actual = float(block["won"].mean())
        se = np.sqrt(0.25 / n)
        rows.append(
            {
                "bucket": f"{bucket.left:.2f}-{bucket.right:.2f}",
                "n": n,
                "claimed": claimed,
                "actual": actual,
                "gap": actual - claimed,
                "z": float((actual - claimed) / se),
            }
        )
    return pd.DataFrame(rows)


def calibration_scores(probs: pd.Series, outcomes: pd.Series) -> dict:
    """Brier score and expected calibration error."""
    frame = pd.DataFrame({"p": probs, "y": outcomes}).dropna()
    if len(frame) < 50:
        return {"brier": np.nan, "ece": np.nan, "log_loss": np.nan, "mean_confidence": np.nan}
    p = frame["p"].clip(1e-6, 1 - 1e-6)
    y = frame["y"]
    brier = float(((p - y) ** 2).mean())
    log_loss = float(-(y * np.log(p) + (1 - y) * np.log(1 - p)).mean())

    conf = confidence(frame["p"])
    won = realised(frame["p"], y)
    buckets = pd.cut(conf, bins=np.linspace(0.5, 1.0, 11), include_lowest=True)
    ece = 0.0
    for _, block in pd.DataFrame({"c": conf, "w": won, "b": buckets}).groupby(
        "b", observed=True
    ):
        if block.empty:
            continue
        ece += len(block) / len(frame) * abs(block["w"].mean() - block["c"].mean())
    return {
        "brier": brier,
        "ece": float(ece),
        "log_loss": log_loss,
        "mean_confidence": float(conf.mean()),
    }


def market_baseline_scores(scored: pd.DataFrame, market: Market) -> dict:
    """The market's own Brier, treating the line as a 50/50 proposition.

    The closing line is, by construction, the market saying "this is a coin
    flip at this number". Its Brier is therefore 0.25 exactly, which is the
    bar any confidence claim has to clear.
    """
    outcomes = pd.to_numeric(scored[market.outcome], errors="coerce").dropna()
    return {"n": int(len(outcomes)), "brier": 0.25, "base_rate": float(outcomes.mean())}


# ---------------------------------------------------------------------------
# Closing-line value
# ---------------------------------------------------------------------------


def add_clv(scored: pd.DataFrame, market: Market, *, weight: float = 0.0) -> pd.DataFrame:
    """What the line did between open and close, from Atlas's side.

    Atlas has no timestamped archive, so the only CLV window it can measure is
    open-to-close. That is a real CLV measurement - "if Atlas had taken this
    side at the opening number, did the market come to it?" - and it is the
    whole window, so it bounds any shorter one inside it.

    Positive ``clv_points`` means the market moved toward Atlas's side.
    """
    out = scored.copy()
    prediction = blend(out, market, weight)
    open_line = pd.to_numeric(out[market.opening], errors="coerce")
    close_line = pd.to_numeric(out[market.line], errors="coerce")

    # The side Atlas would have taken at the opening number.
    out["side"] = np.sign(prediction - open_line)
    out["edge_at_open"] = (prediction - open_line).abs()
    out["clv_points"] = (close_line - open_line) * out["side"]
    out["line_moved"] = (close_line - open_line).abs() >= 0.5

    # A line that never moved is a CLV push, not a CLV loss: there was no
    # closing number to beat. 13% of margin games and 8% of totals games open
    # and close on the same number, so scoring them as losses drags every beat
    # rate roughly six points below its true value. They are graded NaN and
    # drop out of every mean below.
    out["clv_push"] = out["clv_points"] == 0
    out["clv_positive"] = np.where(out["clv_push"], np.nan, out["clv_points"] > 0)

    # Settled against the number actually taken. A bet struck at the opening
    # line settles at the opening line, not the closing one.
    truth = pd.to_numeric(out[market.target], errors="coerce")
    out["won_at_open"] = np.where(
        out["side"] > 0, (truth > open_line).astype(float),
        np.where(out["side"] < 0, (truth < open_line).astype(float), np.nan),
    )
    return out


#: Bucketing CLV by distance to the *closing* line while taking the side at
#: the *opening* line is a tautology, and a spectacular one: a model that sits
#: on the close necessarily points the way the line already moved, which read
#: as a 77% "CLV beat rate" before it was caught. Every CLV measurement below
#: buckets by ``edge_at_open`` for that reason.
CLV_BUCKET_COLUMN = "edge_at_open"


def clv_summary(scored: pd.DataFrame, *, group: str | None = None) -> pd.DataFrame:
    """Mean CLV and beat rate, overall or by group."""
    frame = scored.dropna(subset=["clv_points"])
    frame = frame[frame["side"] != 0]
    if frame.empty:
        return pd.DataFrame()

    def _block(block: pd.DataFrame) -> dict:
        n = len(block)
        mean = float(block["clv_points"].mean())
        se = float(block["clv_points"].std(ddof=1) / np.sqrt(n)) if n > 1 else np.nan
        graded = block["clv_positive"].dropna()
        beat = float(graded.mean()) if len(graded) else np.nan
        return {
            "n": n,
            "graded": int(len(graded)),
            "pushes": int(block["clv_push"].sum()),
            "mean_clv": mean,
            "se": se,
            "t": mean / se if se and se > 0 else np.nan,
            "beat_rate": beat,
            "beat_rate_z": (
                float((beat - 0.5) / np.sqrt(0.25 / len(graded))) if len(graded) else np.nan
            ),
        }

    if group is None:
        return pd.DataFrame([{"group": "all", **_block(frame)}])
    rows = []
    for name, block in frame.groupby(group, observed=True):
        if len(block) < 50:
            continue
        rows.append({"group": str(name), **_block(block)})
    return pd.DataFrame(rows)


def clv_economics(scored: pd.DataFrame, market: Market, mean_clv: float,
                  *, weight: float = 0.0) -> dict:
    """Convert points of closing-line value into win probability, and juice.

    Near the number the outcome distribution is locally flat, so one point of
    line is worth ``phi(0) / sd`` of win probability, where ``sd`` is the
    out-of-sample residual standard deviation. This is what turns a
    statistically overwhelming CLV result into an economic one - or fails to.
    """
    truth = pd.to_numeric(scored[market.target], errors="coerce")
    prediction = blend(scored, market, weight)
    resid = (truth - prediction).dropna()
    sd = float(resid.std(ddof=1))
    per_point = float(stats.norm.pdf(0.0) / sd)
    gain = per_point * mean_clv
    return {
        "residual_sd": sd,
        "prob_per_point": per_point,
        "mean_clv": mean_clv,
        "prob_gain": gain,
        "implied_win_rate": 0.5 + gain,
        **{
            f"clears_{price}": bool(0.5 + gain > breakeven)
            for price, (breakeven, _) in sv.JUICE.items()
        },
    }


#: Placebo predictors for :func:`clv_placebo`. Each destroys the model's
#: game-specific information while keeping something else about it.
PLACEBO_SEED = 20180101


def clv_placebo(scored: pd.DataFrame, market: Market, *, seed: int = PLACEBO_SEED
                ) -> pd.DataFrame:
    """Does a model with no information also 'beat the close'?

    Taking a side at the opening number and grading it against the close is
    exactly the shape of construction that produced the Phase 3 tautology, so
    the CLV result is only worth anything if a predictor that knows nothing
    fails the same test. Three nulls are run:

    * a **constant** at the sample mean - tests whether a standing lean to one
      side of the market is enough;
    * **predictions shuffled within season** - keeps the model's distribution
      and its season, destroys the link to the game;
    * the **opening line plus noise** - a side chosen by a coin flip whose
      magnitude matches nothing.

    A real signal beats all three. The closing line itself is included as a
    scale marker: it scores 100% by construction, which is what the
    tautology looked like.
    """
    rng = np.random.default_rng(seed)
    target = pd.to_numeric(scored[market.target], errors="coerce")
    opening = pd.to_numeric(scored[market.opening], errors="coerce")
    closing = pd.to_numeric(scored[market.line], errors="coerce")

    variants: list[tuple[str, pd.Series]] = [
        ("Atlas model", pd.to_numeric(scored["prediction"], errors="coerce")),
        (f"Constant ({target.mean():.1f})", pd.Series(target.mean(), index=scored.index)),
        (
            "Predictions shuffled within season",
            scored.groupby("season")["prediction"].transform(
                lambda s: pd.Series(rng.permutation(s.to_numpy()), index=s.index)
            ),
        ),
        (
            "Opening line + N(0,1)",
            opening + rng.normal(0.0, 1.0, len(scored)),
        ),
        ("Closing line (known tautology)", closing),
    ]

    rows = []
    for label, prediction in variants:
        block = scored.copy()
        block["prediction"] = prediction
        summary = clv_summary(add_clv(block, market))
        if summary.empty:
            continue
        row = summary.iloc[0].to_dict()
        row["group"] = label
        row["is_null"] = label not in ("Atlas model",)
        rows.append(row)
    return pd.DataFrame(rows)


def clv_robustness(scored: pd.DataFrame, market: Market, *, weight: float = 0.0,
                   move_cap: float = 3.0) -> pd.DataFrame:
    """Stress the CLV finding against the ways it could be an artefact.

    ``mean_clv`` multiplies the size of the move by the side taken, and both
    the side and the size are measured against the same opening number. If an
    opening line is simply wrong, the model is far from it *and* the market
    moves a long way from it, in the same direction - one bad opener inflates
    both variables together. The sign-only ``beat_rate`` is immune to that,
    and capping the move tests it directly.
    """
    frame = add_clv(scored, market, weight=weight)
    frame = frame[frame["side"] != 0].dropna(subset=["clv_points"])
    if frame.empty:
        return pd.DataFrame()

    open_line = pd.to_numeric(frame[market.opening], errors="coerce")
    close_line = pd.to_numeric(frame[market.line], errors="coerce")
    move = (close_line - open_line).abs()

    cuts = {
        "All games": pd.Series(True, index=frame.index),
        f"Move <= {move_cap:g} points": move <= move_cap,
        "Line moved at all": frame["line_moved"],
        "Regular season only": pd.to_numeric(
            frame.get("week", pd.Series(np.nan, index=frame.index)), errors="coerce"
        ).between(2, 15),
    }
    rows = []
    for label, mask in cuts.items():
        block = frame[mask.fillna(False)]
        if len(block) < 200:
            continue
        summary = clv_summary(block)
        if summary.empty:
            continue
        row = summary.iloc[0].to_dict()
        row["group"] = label
        rows.append(row)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Track 3 - edge audit
# ---------------------------------------------------------------------------


def bucket_edges(scored: pd.DataFrame, market: Market, *, weight: float = 0.0) -> pd.DataFrame:
    """Label each game by how far the model sits from the market."""
    out = scored.copy()
    prediction = blend(out, market, weight)
    line = pd.to_numeric(out[market.line], errors="coerce")
    out["edge"] = prediction - line
    out["abs_edge"] = out["edge"].abs()
    labels = [f"{lo}-{hi}" if hi < 1000 else f"{lo}+" for lo, hi in EDGE_BUCKETS]
    edges = [lo for lo, _ in EDGE_BUCKETS] + [EDGE_BUCKETS[-1][1]]
    out["edge_bucket"] = pd.cut(out["abs_edge"], bins=edges, labels=labels, right=False)
    return out


def edge_audit(scored: pd.DataFrame, market: Market, *, weight: float = 0.0) -> pd.DataFrame:
    """Performance and calibration by disagreement size, measured at the close.

    Phase 2 found the curve is not monotone - the loudest disagreements are
    the worst. This puts numbers on each band so a ceiling can be set from
    evidence rather than instinct.

    CLV is deliberately **not** in this table: it belongs to a bet struck at
    the opening line, and mixing the two windows is how the tautology in
    :data:`CLV_BUCKET_COLUMN` arises. See :func:`clv_audit`.
    """
    frame = bucket_edges(scored, market, weight=weight)
    probs = to_probability(frame, market, weight)
    outcomes = pd.to_numeric(frame[market.outcome], errors="coerce")
    frame["claimed"] = confidence(probs)
    frame["won"] = realised(probs, outcomes)

    rows = []
    for bucket, block in frame.groupby("edge_bucket", observed=True):
        scored_block = block.dropna(subset=["won"])
        n = len(scored_block)
        if n < 30:
            continue
        actual = float(scored_block["won"].mean())
        claimed = float(scored_block["claimed"].mean())
        rows.append(
            {
                "bucket": str(bucket),
                "games": n,
                "share": n / len(frame),
                "claimed": claimed,
                "actual": actual,
                "calibration_gap": actual - claimed,
                "z": float((actual - 0.5) / np.sqrt(0.25 / n)),
                "clears_break_even": bool(actual > sv.BREAK_EVEN),
            }
        )
    return pd.DataFrame(rows)


def clv_audit(scored: pd.DataFrame, market: Market, *, weight: float = 0.0) -> pd.DataFrame:
    """CLV and result by disagreement **at the opening line**.

    This is the bet a bettor could actually strike: take the side at the open,
    see whether the market comes to you by the close, and settle against the
    number you took.
    """
    frame = add_clv(scored, market, weight=weight)
    frame = frame[frame["side"] != 0].dropna(subset=["clv_points"])
    if frame.empty:
        return pd.DataFrame()
    labels = [f"{lo}-{hi}" if hi < 1000 else f"{lo}+" for lo, hi in EDGE_BUCKETS]
    edges = [lo for lo, _ in EDGE_BUCKETS] + [EDGE_BUCKETS[-1][1]]
    frame["bucket"] = pd.cut(frame[CLV_BUCKET_COLUMN], bins=edges, labels=labels, right=False)

    rows = []
    for bucket, block in frame.groupby("bucket", observed=True):
        n = len(block)
        if n < 30:
            continue
        graded = block["clv_positive"].dropna()
        if len(graded) < 30:
            continue
        beat = float(graded.mean())
        settled = block["won_at_open"].dropna()
        rows.append(
            {
                "bucket": str(bucket),
                "games": n,
                "share": n / len(frame),
                "graded": int(len(graded)),
                "mean_clv": float(block["clv_points"].mean()),
                "clv_se": float(block["clv_points"].std(ddof=1) / np.sqrt(n)),
                "clv_beat_rate": beat,
                "clv_beat_z": float((beat - 0.5) / np.sqrt(0.25 / len(graded))),
                "win_rate_at_open": float(settled.mean()) if len(settled) else np.nan,
                "settled": int(len(settled)),
            }
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Track 4 - can CLV be predicted better than outcomes?
# ---------------------------------------------------------------------------


def clv_predictability(scored: pd.DataFrame, market: Market, *, weight: float = 0.0) -> dict:
    """Compare how well Atlas's disagreement predicts CLV versus the result.

    A model can be useless at picking winners and still useful at picking
    which way a line will move, because line movement is a market process
    rather than a football one. If that were true it would be the most
    valuable thing Atlas has found, so it is worth testing directly.
    """
    frame = add_clv(scored, market, weight=weight)
    frame = frame[frame["side"] != 0].dropna(subset=["clv_points", "edge_at_open"])
    if len(frame) < 200:
        return {}

    outcomes = pd.to_numeric(frame[market.outcome], errors="coerce")
    probs = to_probability(frame, market, weight)
    won = realised(probs, outcomes)
    valid = won.notna()

    edge = frame["edge_at_open"]
    clv_fit = stats.linregress(edge, frame["clv_points"])
    outcome_fit = stats.linregress(edge[valid], won[valid])

    return {
        "n": int(len(frame)),
        "clv_slope": float(clv_fit.slope),
        "clv_slope_t": float(clv_fit.slope / clv_fit.stderr) if clv_fit.stderr else np.nan,
        "clv_r2": float(clv_fit.rvalue**2),
        "outcome_slope": float(outcome_fit.slope),
        "outcome_slope_t": (
            float(outcome_fit.slope / outcome_fit.stderr) if outcome_fit.stderr else np.nan
        ),
        "outcome_r2": float(outcome_fit.rvalue**2),
        "mean_clv": float(frame["clv_points"].mean()),
        "clv_beat_rate": float(frame["clv_positive"].mean()),
        "clv_beat_z": float(
            (frame["clv_positive"].mean() - 0.5)
            / np.sqrt(0.25 / int(frame["clv_positive"].notna().sum()))
        ),
    }


def clv_drivers(scored: pd.DataFrame, market: Market, candidates: list[str],
                *, weight: float = 0.0) -> pd.DataFrame:
    """Which variables predict closing-line value, ranked."""
    frame = add_clv(scored, market, weight=weight)
    frame = frame[frame["side"] != 0].dropna(subset=["clv_points"])
    rows = []
    for column in ["edge_at_open", *candidates]:
        if column not in frame.columns:
            continue
        x = pd.to_numeric(frame[column], errors="coerce")
        mask = x.notna()
        if mask.sum() < 200 or x[mask].std() == 0:
            continue
        fit = stats.linregress(x[mask], frame.loc[mask, "clv_points"])
        rows.append(
            {
                "variable": column,
                "n": int(mask.sum()),
                "slope": float(fit.slope),
                "t": float(fit.slope / fit.stderr) if fit.stderr else np.nan,
                "r_squared": float(fit.rvalue**2),
                "p": float(fit.pvalue),
            }
        )
    out = pd.DataFrame(rows)
    return out.sort_values("t", key=lambda s: s.abs(), ascending=False) if not out.empty else out


# ---------------------------------------------------------------------------
# Track 5 - selective participation
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Filter:
    """A rule for declining to have an opinion."""

    name: str
    column: str
    keep: str  # "low" or "high"
    quantile: float
    rationale: str


def participation_filters(market_name: str) -> list[Filter]:
    liquidity = "spread_books" if market_name == "margin" else "total_books"
    dispersion = "closing_spread_sd" if market_name == "margin" else "closing_total_sd"
    return [
        Filter("Edge ceiling (drop loudest quarter)", "abs_edge", "low", 0.75,
               "Phase 2 and Track 3: the biggest disagreements are the worst"),
        Filter("Book agreement (drop noisiest quarter)", dispersion, "low", 0.75,
               "books disagreeing is the market saying it is unsure"),
        Filter("Liquidity (drop thinnest quarter)", liquidity, "high", 0.25,
               "few books quoting is a thin, unreliable number"),
        Filter("Scoring environment (drop the wildest quarter)", "closing_total", "low", 0.75,
               "high-total games have the widest outcome distribution"),
        Filter("Mismatch (drop the biggest spreads)", "closing_spread_abs", "low", 0.75,
               "blowout-prone games have the fattest tails"),
    ]


def participation_study(
    scored: pd.DataFrame, market: Market, *, weight: float = 0.0
) -> pd.DataFrame:
    """Does declining to participate improve calibration, CLV or win rate?"""
    frame = bucket_edges(scored, market, weight=weight)
    frame = add_clv(frame, market, weight=weight)
    probs = to_probability(frame, market, weight)
    outcomes = pd.to_numeric(frame[market.outcome], errors="coerce")
    frame["won"] = realised(probs, outcomes)
    frame["prob"] = probs

    def _block(block: pd.DataFrame, label: str, kept: float) -> dict:
        settled = block.dropna(subset=["won"])
        clv = block[block["side"] != 0].dropna(subset=["clv_points"])
        scores = calibration_scores(block["prob"], pd.to_numeric(
            block[market.outcome], errors="coerce"))
        return {
            "filter": label,
            "games": int(len(block)),
            "kept": kept,
            "win_rate": float(settled["won"].mean()) if len(settled) else np.nan,
            "ece": scores["ece"],
            "brier": scores["brier"],
            "mean_clv": float(clv["clv_points"].mean()) if len(clv) else np.nan,
            "clv_beat_rate": float(clv["clv_positive"].mean()) if len(clv) else np.nan,
            "clv_graded": int(clv["clv_positive"].notna().sum()),
        }

    rows = [_block(frame, "No filter (all games)", 1.0)]
    for rule in participation_filters(market.name):
        if rule.column not in frame.columns:
            continue
        values = pd.to_numeric(frame[rule.column], errors="coerce")
        if values.notna().sum() < 500:
            continue
        cutoff = values.quantile(rule.quantile)
        mask = values <= cutoff if rule.keep == "low" else values >= cutoff
        block = frame[mask.fillna(False)]
        if len(block) < 300:
            continue
        rows.append(_block(block, rule.name, len(block) / len(frame)))
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Track 6 - Velocity policy emulation
# ---------------------------------------------------------------------------

#: Velocity's publish gate expressed in probability terms: an edge BAND, not a
#: floor. Below the lower bound there is no opinion; above the upper bound the
#: number is treated as a data-quality alarm rather than a bet.
PUBLISH_BAND = (0.03, 0.12)


def policy_tests(scored: pd.DataFrame, market: Market, fitted_weight: float) -> pd.DataFrame:
    """Each Velocity policy, applied to Atlas's own out-of-sample record."""
    rows = []

    raw = anchoring_curve(scored, market)
    pure = raw[raw["market_weight"] == 0.0].iloc[0]
    anchored_row = raw.iloc[(raw["market_weight"] - fitted_weight).abs().argmin()]
    rows.append(
        {
            "policy": "Market anchoring",
            "atlas_test": f"blend at w={anchored_row['market_weight']:.2f} vs pure model",
            "before": pure["ece"],
            "after": anchored_row["ece"],
            "metric": "expected calibration error",
            "improves": bool(anchored_row["ece"] < pure["ece"]),
        }
    )
    rows.append(
        {
            "policy": "Market anchoring",
            "atlas_test": f"blend at w={anchored_row['market_weight']:.2f} vs pure model",
            "before": pure["mae"],
            "after": anchored_row["mae"],
            "metric": "mean absolute error",
            "improves": bool(anchored_row["mae"] < pure["mae"]),
        }
    )

    audit = edge_audit(scored, market)
    if not audit.empty:
        loud = audit.iloc[-1]
        quiet = audit.iloc[0]
        rows.append(
            {
                "policy": "Edge ceiling",
                "atlas_test": f"calibration gap, {quiet['bucket']} vs {loud['bucket']} points",
                "before": quiet["calibration_gap"],
                "after": loud["calibration_gap"],
                "metric": "claimed minus realised",
                "improves": bool(abs(loud["calibration_gap"]) > abs(quiet["calibration_gap"])),
            }
        )

    frame = bucket_edges(scored, market)
    probs = to_probability(frame, market, 0.0)
    conf = confidence(probs)
    outcomes = pd.to_numeric(frame[market.outcome], errors="coerce")
    won = realised(probs, outcomes)
    band = (conf - 0.5).between(*PUBLISH_BAND)
    rows.append(
        {
            "policy": "Publish gate (edge band)",
            "atlas_test": f"confidence in {PUBLISH_BAND[0]:.2f}-{PUBLISH_BAND[1]:.2f} over 0.5",
            "before": float(won.dropna().mean()),
            "after": float(won[band].dropna().mean()),
            "metric": "win rate",
            "improves": bool(won[band].dropna().mean() > won.dropna().mean()),
        }
    )

    clv = clv_predictability(scored, market)
    if clv:
        rows.append(
            {
                "policy": "CLV monitoring",
                "atlas_test": "disagreement -> CLV vs disagreement -> outcome",
                "before": abs(clv["outcome_slope_t"]),
                "after": abs(clv["clv_slope_t"]),
                "metric": "|t| of the relationship",
                "improves": bool(abs(clv["clv_slope_t"]) > abs(clv["outcome_slope_t"])),
            }
        )

    rows.append(
        {
            "policy": "Staking caps",
            "atlas_test": "not testable without a wagering simulation (out of scope)",
            "before": np.nan,
            "after": np.nan,
            "metric": "n/a",
            "improves": None,
        }
    )
    return pd.DataFrame(rows)


def detection_sample_size(effect: float, baseline: float = 0.5) -> float:
    """Bets needed to detect a rate ``effect`` above ``baseline`` at 95%."""
    delta = abs(effect - baseline)
    if delta <= 0:
        return float("inf")
    return 0.25 * (1.96 / delta) ** 2


# ---------------------------------------------------------------------------
# Reliability diagram
# ---------------------------------------------------------------------------

#: Validated categorical slots 1 and 2 from the reference palette
#: (`node scripts/validate_palette.js "#2a78d6,#eb6834" --mode light`:
#: all checks pass, worst adjacent CVD dE 24.7).
SERIES_COLOURS = {"margin": "#2a78d6", "total": "#eb6834"}
SURFACE = "#fcfcfb"
TEXT_PRIMARY = "#0b0b0b"
TEXT_SECONDARY = "#52514e"
GRID = "#dcdcd8"


def reliability_svg(tables: dict[str, pd.DataFrame], *, width: int = 660,
                    height: int = 470) -> str:
    """A reliability diagram: claimed confidence against realised rate.

    The chart carries its own light surface so it reads the same in a light or
    dark markdown viewer, and every point is also in the table beside it - a
    static image in a report cannot offer a hover layer, so the table is the
    accessible view. Marker area is proportional to the games in each bucket,
    so the eye lands on the bins that carry the sample.
    """
    pad_l, pad_r, pad_t, pad_b = 66, 90, 52, 62
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b
    lo, hi = 0.44, 0.72

    def sx(v: float) -> float:
        return pad_l + (v - lo) / (hi - lo) * plot_w

    def sy(v: float) -> float:
        return pad_t + plot_h - (v - lo) / (hi - lo) * plot_h

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="Reliability diagram: Atlas claimed confidence against realised '
        f'win rate for margin and totals. Every point sits below the diagonal, and '
        f'the gap widens as claimed confidence rises.">',
        f'<rect width="{width}" height="{height}" fill="{SURFACE}"/>',
        f'<text x="{pad_l}" y="24" font-family="system-ui,sans-serif" font-size="15" '
        f'font-weight="600" fill="{TEXT_PRIMARY}">Atlas is overconfident, and it '
        f'worsens with confidence</text>',
        f'<text x="{pad_l}" y="41" font-family="system-ui,sans-serif" font-size="11.5" '
        f'fill="{TEXT_SECONDARY}">Pure model, no market anchoring. Points below the '
        f'diagonal claim more than they deliver.</text>',
    ]

    for tick in (0.45, 0.50, 0.55, 0.60, 0.65, 0.70):
        x, y = sx(tick), sy(tick)
        parts.append(
            f'<line x1="{pad_l}" y1="{y:.1f}" x2="{pad_l + plot_w}" y2="{y:.1f}" '
            f'stroke="{GRID}" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{pad_l - 10}" y="{y + 4:.1f}" text-anchor="end" '
            f'font-family="system-ui,sans-serif" font-size="11" fill="{TEXT_SECONDARY}">'
            f'{tick:.0%}</text>'
        )
        parts.append(
            f'<text x="{x:.1f}" y="{pad_t + plot_h + 18:.1f}" text-anchor="middle" '
            f'font-family="system-ui,sans-serif" font-size="11" fill="{TEXT_SECONDARY}">'
            f'{tick:.0%}</text>'
        )

    parts.append(
        f'<line x1="{sx(lo):.1f}" y1="{sy(lo):.1f}" x2="{sx(hi):.1f}" y2="{sy(hi):.1f}" '
        f'stroke="{TEXT_SECONDARY}" stroke-width="1.5" stroke-dasharray="5 4"/>'
    )
    parts.append(
        f'<text transform="translate({sx(0.585):.1f},{sy(0.600):.1f}) rotate(-45)" '
        f'font-family="system-ui,sans-serif" font-size="11" fill="{TEXT_SECONDARY}">'
        f'perfect calibration</text>'
    )

    legend_x = pad_l + 10
    for i, (name, table) in enumerate(tables.items()):
        colour = SERIES_COLOURS.get(name, "#1baf7a")
        biggest = float(table["n"].max()) if "n" in table and len(table) else 1.0
        points = []
        for _, row in table.iterrows():
            claimed, actual = float(row["claimed"]), float(row["actual"])
            if not (lo <= claimed <= hi):
                continue
            share = float(row.get("n", 1)) / biggest if biggest else 1.0
            points.append(
                (sx(claimed), sy(min(max(actual, lo), hi)), 4.0 + 7.0 * share**0.5)
            )
        if len(points) >= 2:
            path = " ".join(
                f'{"M" if j == 0 else "L"}{x:.1f},{y:.1f}'
                for j, (x, y, _) in enumerate(points)
            )
            parts.append(
                f'<path d="{path}" fill="none" stroke="{colour}" stroke-width="2" '
                f'stroke-linejoin="round" opacity="0.75"/>'
            )
        for x, y, r in points:
            parts.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="{colour}" '
                f'stroke="{SURFACE}" stroke-width="2"/>'
            )
        if points:
            lx, ly, lr = points[-1]
            parts.append(
                f'<text x="{lx + lr + 7:.1f}" y="{ly + 4:.1f}" '
                f'font-family="system-ui,sans-serif" font-size="11.5" font-weight="600" '
                f'fill="{TEXT_SECONDARY}">{name}</text>'
            )
        ly = pad_t + 12 + i * 18
        parts.append(
            f'<rect x="{legend_x}" y="{ly - 8}" width="10" height="10" rx="2" '
            f'fill="{colour}"/>'
        )
        parts.append(
            f'<text x="{legend_x + 16}" y="{ly + 1}" font-family="system-ui,sans-serif" '
            f'font-size="11.5" fill="{TEXT_SECONDARY}">{name}</text>'
        )

    parts.append(
        f'<text x="{pad_l + plot_w / 2:.1f}" y="{height - 30}" text-anchor="middle" '
        f'font-family="system-ui,sans-serif" font-size="12" fill="{TEXT_SECONDARY}">'
        f'Claimed confidence</text>'
    )
    parts.append(
        f'<text transform="translate(18,{pad_t + plot_h / 2:.1f}) rotate(-90)" '
        f'text-anchor="middle" font-family="system-ui,sans-serif" font-size="12" '
        f'fill="{TEXT_SECONDARY}">Realised win rate</text>'
    )
    parts.append(
        f'<text x="{pad_l}" y="{height - 10}" font-family="system-ui,sans-serif" '
        f'font-size="10.5" fill="{TEXT_SECONDARY}">Marker area is proportional to the '
        f'games in each bucket.</text>'
    )
    parts.append("</svg>")
    return "\n".join(parts)
