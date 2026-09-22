"""Track 1: generating opinions.

An Atlas signal is a number and a direction, nothing else. It carries no
stake, no confidence in dollars and no expected profit, because Phase 4
established that the edge does not clear standard juice and this system exists
to find out whether that changes - not to act as though it already has.

Two numbers are recorded for every signal and they are not the same thing:

``open_line``   what the book opened on. Comparable to the historical study.
``entry_line``  what the book was quoting when Atlas formed the opinion.

CLV is graded against ``entry_line``, because that is the number that was
actually available. Grading against the opener would credit Atlas with
movement that happened before it spoke, which is exactly the failure mode
Gamma's third kill criterion is about.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime

import numpy as np
import pandas as pd

from atlas.live.audit import signal_uuid
from atlas.research import beta_report as beta
from atlas.research import market_aware as ma
from atlas.research import signal_validation as sv
from atlas.research.dataset import add_derived_features, load_research_frame, research_sample
from atlas.util import get_logger

LOG = get_logger(__name__)

#: Signals at or above the historical 90th percentile of disagreement at the
#: open are the ones Gamma's recommendation says to track. Below it the signal
#: is still recorded - silence is data too - but it does not count toward the
#: kill criteria.
PRIMARY_QUANTILE = 0.90

#: Phase 4, Track 6: margin signals in weeks 1-4 beat the close 51.2% of the
#: time (z = 0.98). They are recorded and excluded from the primary set.
MARGIN_MIN_WEEK = 5

#: The market Gamma's recommendation is built around.
PRIMARY_MARKET = "total"


@dataclass(frozen=True)
class Model:
    """A fitted Atlas number-maker for one market."""

    market: ma.Market
    features: tuple[str, ...]
    train_seasons: tuple[int, ...]
    threshold: float

    @property
    def version(self) -> str:
        """Identifies exactly what produced a number.

        A signal whose model cannot be identified afterwards is an anecdote,
        so the version travels with every row.
        """
        payload = "|".join([
            self.market.name,
            ",".join(self.features),
            ",".join(str(s) for s in self.train_seasons),
            f"{self.threshold:.4f}",
        ])
        return hashlib.sha256(payload.encode()).hexdigest()[:12]


def _threshold(frame: pd.DataFrame, market: ma.Market) -> float:
    """The historical 90th percentile of |model - opening line|.

    Taken from history, never from the current slate: "the loudest 10% of this
    week's six games" is not a selection rule, it is a rounding error.
    """
    scored = ma.walk_forward(frame, market)
    if scored.empty:
        return float("inf")
    opening = pd.to_numeric(scored[market.opening], errors="coerce")
    edge = (scored["prediction"] - opening).abs().dropna()
    return float(edge.quantile(PRIMARY_QUANTILE)) if len(edge) else float("inf")


def build_models(frame: pd.DataFrame | None = None) -> dict[str, Model]:
    """Fit one model per market on every completed season in the warehouse."""
    full = add_derived_features(frame) if frame is not None else load_research_frame()
    sample = research_sample(ma.prepare(full))
    models = {}
    for name, market in beta.markets(sample).items():
        features = tuple(sv.available_features(sample, list(market.features)))
        seasons = tuple(sorted(sample["season"].unique()))
        models[name] = Model(
            market=market,
            features=features,
            train_seasons=seasons,
            threshold=_threshold(sample, market),
        )
        LOG.info(
            "model %s: %d features, seasons %s-%s, threshold %.2f",
            name, len(features), seasons[0], seasons[-1], models[name].threshold,
        )
    return models


def atlas_numbers(models: dict[str, Model], frame: pd.DataFrame | None = None) -> pd.DataFrame:
    """Predict every scheduled game in the warehouse, one row per market."""
    full = add_derived_features(frame) if frame is not None else load_research_frame()
    full = ma.prepare(full)
    played = research_sample(full)
    scheduled = full[full["actual_margin"].isna()].copy()
    if scheduled.empty:
        LOG.warning("no scheduled games in the warehouse - rebuild with --include-scheduled")
        return pd.DataFrame()

    combined = pd.concat([played, scheduled], ignore_index=True)
    rows = []
    for name, model in models.items():
        prediction = _fit_and_predict(combined, model, len(played))
        if prediction is None:
            continue
        block = scheduled[["game_id", "season", "week"]].copy()
        block["prediction"] = prediction
        block["market"] = name
        block["model_version"] = model.version
        block["threshold"] = model.threshold
        rows.append(block.dropna(subset=["prediction"]))
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def _fit_and_predict(combined: pd.DataFrame, model: Model, n_played: int):
    """Fit on completed games, predict the scheduled ones.

    ``signal_validation.fit_predict`` selects its test rows by season *and*
    requires a finite target, which a game that has not been played does not
    have. The fit is otherwise identical - the same feature matrix, the same
    ridge pipeline - so this reuses both rather than defining a second model.
    """
    feats = sv.available_features(combined, list(model.features))
    if not feats:
        return None
    matrix, used = sv.feature_matrix(combined, feats)
    if not used:
        return None
    target = pd.to_numeric(combined[model.market.target], errors="coerce").to_numpy(float)
    train = np.isfinite(target)
    train[n_played:] = False
    if train.sum() < 200:
        return None
    pipeline = sv._model()
    pipeline.fit(matrix[train], target[train])
    return pipeline.predict(matrix[n_played:])


def form_signals(numbers: pd.DataFrame, quotes: pd.DataFrame,
                 *, run_id: str = "") -> pd.DataFrame:
    """Pair each Atlas number with the number a book is quoting right now."""
    if numbers.empty or quotes.empty:
        return pd.DataFrame()

    live = quotes[quotes["status"] == "STATUS_SCHEDULED"].copy()
    live = live.dropna(subset=["line"])
    merged = live.merge(numbers, on=["game_id", "market"], how="inner", suffixes=("", "_n"))
    if merged.empty:
        return pd.DataFrame()

    created = datetime.now(UTC).replace(microsecond=0).isoformat()
    merged["created_at"] = created
    merged["run_id"] = run_id
    merged["atlas_number"] = merged["prediction"].astype(float)
    merged["entry_line"] = merged["line"].astype(float)
    merged["entry_price"] = merged["price"]
    merged["disagreement"] = merged["atlas_number"] - merged["entry_line"]

    merged["direction"] = np.where(
        merged["market"] == "total",
        np.where(merged["disagreement"] > 0, "over", "under"),
        np.where(merged["disagreement"] > 0, "home", "away"),
    )
    merged["selection"] = [
        _selection(row) for row in merged.itertuples(index=False)
    ]
    merged["signal_id"] = [
        _signal_id(row) for row in merged.itertuples(index=False)
    ]
    merged["season"] = merged["season_n"] if "season_n" in merged else merged["season"]
    merged["week"] = merged["week_n"] if "week_n" in merged else merged["week"]
    return merged[merged["disagreement"] != 0]


def _selection(row) -> str:
    """Which population a signal belongs to.

    ``primary`` is the set Gamma's kill criteria are evaluated on. Everything
    else is recorded and reported separately: a tracker that only keeps the
    signals it likes cannot be audited.
    """
    edge = abs(float(row.disagreement))
    if edge < float(row.threshold):
        return "observed"
    if row.market == PRIMARY_MARKET:
        return "primary"
    week = getattr(row, "week", None)
    if week is not None and not pd.isna(week) and int(week) < MARGIN_MIN_WEEK:
        return "observed"
    return "secondary"


def _signal_id(row) -> str:
    """One opinion per game, market and book - and no more, ever.

    See :func:`atlas.live.audit.signal_uuid` for why the id is a deterministic
    UUID rather than a random one.
    """
    return signal_uuid(row.game_id, row.market, row.book)
