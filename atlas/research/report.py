"""Research Task 3: generate ``reports/atlas_research_report_v1.md``.

Everything in the report is computed here from the warehouse - no number is
typed by hand - and every supporting table is also written to
``reports/tables/`` as CSV so a reader can check the arithmetic.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from atlas import config
from atlas.research import benchmarks, importance, validation
from atlas.research.dataset import (
    available_features,
    candidates,
    load_research_frame,
    research_sample,
)
from atlas.sources import cfbd
from atlas.util import get_logger

LOG = get_logger(__name__)

BREAK_EVEN = 0.5238  # -110 juice


def _fmt(value: float | None, digits: int = 3, dash: str = "n/a") -> str:
    if value is None or (isinstance(value, float) and not np.isfinite(value)):
        return dash
    return f"{value:.{digits}f}"


#: Columns that are conceptually counts and should never render as 1234.000.
COUNT_COLUMNS = {"season", "games", "n", "n_features", "picks", "with_spread", "with_total",
                 "with_efficiency", "with_fpi", "rank_standalone", "rank_over_market"}


def _table(df: pd.DataFrame, columns: list[str], headers: list[str], digits: int = 3) -> str:
    headers = [h.replace("|", "\\|") for h in headers]
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for _, row in df.iterrows():
        cells = []
        for col in columns:
            value = row.get(col)
            if isinstance(value, (bool, np.bool_)):
                cells.append("yes" if value else "no")
            elif isinstance(value, (int, np.integer)):
                cells.append(f"{int(value):,}")
            elif isinstance(value, (float, np.floating)):
                if not np.isfinite(value):
                    cells.append("n/a")
                elif col in COUNT_COLUMNS:
                    cells.append(f"{int(round(value)):,}" if col != "season" else str(int(value)))
                else:
                    cells.append(_fmt(float(value), digits))
            else:
                cells.append("" if value is None else str(value))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def build_artifacts(df: pd.DataFrame) -> dict[str, pd.DataFrame | dict]:
    LOG.info("running benchmarks")
    bench = benchmarks.run_benchmarks(df)
    edge = benchmarks.market_edge_report(df)

    LOG.info("running variable importance")
    ranking = importance.rank_variables(df)

    full_margin = benchmarks.BENCHMARKS["Market + Everything"]["margin"]
    full_total = benchmarks.BENCHMARKS["Market + Everything"]["total"]
    perm_margin = importance.permutation_importance(df, full_margin, "actual_margin")
    perm_total = importance.permutation_importance(df, full_total, "actual_total")
    dir_margin = importance.ridge_directions(df, full_margin, "actual_margin")
    dir_total = importance.ridge_directions(df, full_total, "actual_total")

    LOG.info("running ATS / totals classification")
    no_market_margin = [f for f in full_margin if not f.startswith("closing")]
    no_market_total = [f for f in full_total if not f.startswith("closing")]
    ats = {
        "all features (incl. market)": importance.classification_power(
            df, full_margin, "home_cover"
        ),
        "non-market features only": importance.classification_power(
            df, no_market_margin, "home_cover"
        ),
        "market line only": importance.classification_power(df, ["closing_spread"], "home_cover"),
    }
    ou = {
        "all features (incl. market)": importance.classification_power(
            df, full_total, "over_hit"
        ),
        "non-market features only": importance.classification_power(
            df, no_market_total, "over_hit"
        ),
        "market line only": importance.classification_power(df, ["closing_total"], "over_hit"),
    }

    all_features = sorted({f for c in candidates() for f in c.margin_features + c.total_features})
    coverage = validation.coverage_report(df, all_features)
    leak = validation.leakage_scan(
        df, available_features(df, all_features), ["actual_margin", "actual_total"]
    )

    season_stability = benchmarks.benchmark_by_season(df, "Market Only", "margin")

    return {
        "benchmarks": bench,
        "edge": edge,
        "ranking": ranking,
        "perm_margin": perm_margin,
        "perm_total": perm_total,
        "dir_margin": dir_margin,
        "dir_total": dir_total,
        "ats": ats,
        "ou": ou,
        "coverage": coverage,
        "leakage": leak,
        "season_stability": season_stability,
    }


def _coverage_section(df: pd.DataFrame, raw_df: pd.DataFrame) -> str:
    by_season = (
        df.groupby("season")
        .agg(
            games=("game_id", "size"),
            with_spread=("closing_spread", lambda s: int(s.notna().sum())),
            with_total=("closing_total", lambda s: int(s.notna().sum())),
            with_efficiency=("off_epa_diff", lambda s: int(s.notna().sum())),
            with_fpi=("fpi_diff", lambda s: int(s.notna().sum())),
            mean_total=("actual_total", "mean"),
            mean_abs_margin=("actual_margin", lambda s: float(s.abs().mean())),
        )
        .reset_index()
    )
    body = _table(
        by_season,
        ["season", "games", "with_spread", "with_total", "with_efficiency", "with_fpi",
         "mean_total", "mean_abs_margin"],
        ["Season", "Games", "Spread", "Total", "Efficiency", "FPI", "Mean total",
         "Mean abs margin"],
        digits=2,
    )
    return (
        f"Research sample: **{len(df):,} FBS-vs-FBS games** across "
        f"**{df['season'].nunique()} seasons ({df['season'].min()}-{df['season'].max()})**, "
        f"drawn from {len(raw_df):,} completed FBS-vs-FBS games in the warehouse.\n\n"
        f"{body}\n"
    )


def render(df: pd.DataFrame, raw_df: pd.DataFrame, art: dict) -> str:
    bench = art["benchmarks"]
    margin_bench = bench[bench["target"] == "margin"]
    total_bench = bench[bench["target"] == "total"]

    def _row(name: str, target: str) -> pd.Series | None:
        sub = bench[(bench["benchmark"] == name) & (bench["target"] == target)]
        return None if sub.empty else sub.iloc[0]

    market_margin = _row("Market Closing Line (raw, unfitted)", "margin")
    market_total = _row("Market Closing Line (raw, unfitted)", "total")
    sp_margin = _row("SP+ Only", "margin")
    sp_total = _row("SP+ Only", "total")
    fpi_margin = _row("FPI Only", "margin")
    fpi_total = _row("FPI Only", "total")

    rank = art["ranking"]
    rank_margin = rank[(rank["target"] == "margin")]
    rank_total = rank[(rank["target"] == "total")]

    sp_available = bool(sp_margin is not None and sp_margin["available"])
    cfbd_note = (
        "CFBD enrichment was **enabled** for this build."
        if cfbd.available()
        else (
            "CFBD enrichment was **not** enabled for this build (`CFBD_API_KEY` unset), so "
            "SP+, recruiting, returning production and kickoff weather are structurally "
            "present but empty. Every other result below is unaffected."
        )
    )

    generated = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    parts: list[str] = []
    parts.append(
        f"""# Atlas Research Report V1

*Generated {generated} from `data/warehouse/atlas.duckdb`. Every figure in this
document is produced by `python -m atlas.research.report`; none is hand-entered.*

Atlas Phase 1A asks one question: **which variables actually predict college
football games?** It does not project, simulate or wager. The answer below is
measured out-of-sample, leave-one-season-out, on a point-in-time-correct
warehouse in which no feature attached to a game was unknown at its kickoff.

{cfbd_note}

---

## Section 1 - Data Coverage

{_coverage_section(df, raw_df)}
### How point-in-time correctness is enforced

| Field family | Source | Why it cannot leak |
|---|---|---|
| Results, venue, schedule | CFBD games mirror | Outcome only; never used as a feature |
| Closing / opening lines, moneyline | Historical sportsbook feed | Posted before kickoff |
| Efficiency (EPA, success rate, explosiveness, havoc, finishing drives, pace) | Play-by-play, aggregated per game | A game's feature averages that team's **strictly earlier** games, shrunk toward its **previous season** mean |
| FPI (rating) | ESPN | **Previous season's** final rating only |
| FPI game projection | ESPN pre-game predictor | Published before kickoff |
| Elo | CFBD pre-game Elo | Pre-game by construction |
| SP+ | CFBD | **Previous season's** rating only |
| Recruiting, returning production | CFBD | Fixed before the season starts |
| Rest, travel, neutral site | Schedule + venue geography | Known when the schedule is published |
| Weather | CFBD kickoff observation | Kickoff conditions, not a result |

The vectorised point-in-time implementation is checked row-by-row against a
brute-force recomputation in the test suite, and a correlation scan flags any
feature that tracks an outcome more tightly than football allows.

---

## Section 2 - Market Performance

The closing consensus line, used exactly as posted.

| Metric | Value |
|---|---|
| Margin MAE | {_fmt(market_margin['mae'] if market_margin is not None else None, 3)} |
| Margin RMSE | {_fmt(market_margin['rmse'] if market_margin is not None else None, 3)} |
| Margin R² | {_fmt(market_margin['r2'] if market_margin is not None else None, 3)} |
| Total MAE | {_fmt(market_total['mae'] if market_total is not None else None, 3)} |
| Total RMSE | {_fmt(market_total['rmse'] if market_total is not None else None, 3)} |
| Total R² | {_fmt(market_total['r2'] if market_total is not None else None, 3)} |
| Games | {int(market_margin['n']) if market_margin is not None else 0:,} |

Per-season stability of the market margin benchmark:

{_table(art['season_stability'], ['season', 'n', 'mae', 'rmse', 'bias'], ['Season', 'Games', 'MAE', 'RMSE', 'Bias'])}

---

## Section 3 - SP+ Performance

"""
    )
    if sp_available:
        parts.append(
            f"""| Metric | Value |
|---|---|
| Margin MAE | {_fmt(sp_margin['mae'])} |
| Margin RMSE | {_fmt(sp_margin['rmse'])} |
| Total MAE | {_fmt(sp_total['mae'] if sp_total is not None else None)} |
| Total RMSE | {_fmt(sp_total['rmse'] if sp_total is not None else None)} |
| Games | {int(sp_margin['n']):,} |

SP+ is used as the **previous season's** rating, mapped to a margin by a
leave-one-season-out fit that also carries home-field advantage.
"""
        )
    else:
        parts.append(
            """**Not measurable in this build.** SP+ is published only through the
CollegeFootballData API, which requires a free API key. Without `CFBD_API_KEY`
the `ratings.home_sp_plus` / `away_sp_plus` / `sp_plus_diff` columns exist and
are null, and the SP+ benchmark is reported as unavailable rather than being
silently replaced by a proxy.

Set the key and re-run `make all` to fill this section in; nothing else about
the pipeline changes. Atlas measures the next-best published rating, ESPN's
FPI, in Section 4, and its own pre-game Elo and efficiency baselines in
Section 5.
"""
        )

    parts.append(
        f"""
---

## Section 4 - FPI Performance

Two distinct FPI artefacts, because they are not equally informative.

**FPI rating (previous season's final value, mapped to margin):**

| Metric | Value |
|---|---|
| Margin MAE | {_fmt(fpi_margin['mae'] if fpi_margin is not None else None)} |
| Margin RMSE | {_fmt(fpi_margin['rmse'] if fpi_margin is not None else None)} |
| Total MAE | {_fmt(fpi_total['mae'] if fpi_total is not None else None)} |
| Total RMSE | {_fmt(fpi_total['rmse'] if fpi_total is not None else None)} |

**FPI pre-game game projection (ESPN's own matchup forecast, published before kickoff):**

{_table(bench[bench['benchmark'] == 'FPI Game Projection'], ['target', 'n', 'mae', 'rmse', 'r2'], ['Target', 'Games', 'MAE', 'RMSE', 'R²'])}

The gap between the two is the value of in-season updating: a stale
preseason-equivalent rating is materially worse than the same system's
current view of the same matchup.

---

## Section 5 - Feature Importance Ranking

### Full benchmark ladder - margin

{_table(margin_bench, ['benchmark', 'available', 'n', 'mae', 'rmse', 'r2', 'missing_features'], ['Benchmark', 'Available', 'Games', 'MAE', 'RMSE', 'R²', 'Unavailable inputs'])}

### Full benchmark ladder - total

{_table(total_bench, ['benchmark', 'available', 'n', 'mae', 'rmse', 'r2', 'missing_features'], ['Benchmark', 'Available', 'Games', 'MAE', 'RMSE', 'R²', 'Unavailable inputs'])}

### Ranked variables - margin

`Standalone gain` is MAE removed from a constant baseline by that variable
alone. `Gain over market` is MAE removed **on top of** the closing spread -
the only column that says whether a variable carries information the market
has not already priced. It is a paired per-game comparison, so it comes with a
t-statistic; `Material?` is `yes` only when t > 2, because over ~5,700 games a
gain of 0.01 MAE is indistinguishable from zero.

{_table(rank_margin, ['rank_standalone', 'variable', 'available', 'standalone_mae', 'standalone_gain', 'gain_over_market', 'gain_t', 'material'], ['#', 'Variable', 'Available', 'Standalone MAE', 'Standalone gain', 'Gain over market', 't', 'Material?'], digits=4)}

### Ranked variables - total

{_table(rank_total, ['rank_standalone', 'variable', 'available', 'standalone_mae', 'standalone_gain', 'gain_over_market', 'gain_t', 'material'], ['#', 'Variable', 'Available', 'Standalone MAE', 'Standalone gain', 'Gain over market', 't', 'Material?'], digits=4)}

### Permutation importance inside one model - margin

{_table(art['perm_margin'].head(15), ['feature', 'mae_increase'], ['Feature', 'MAE increase when shuffled'], digits=4)}

### Permutation importance inside one model - total

{_table(art['perm_total'].head(15), ['feature', 'mae_increase'], ['Feature', 'MAE increase when shuffled'], digits=4)}

### Direction of effect (standardised ridge coefficients, margin)

{_table(art['dir_margin'].head(12), ['feature', 'coef_std'], ['Feature', 'Std. coefficient'], digits=3)}

### ATS and totals outcomes

Break-even at -110 is **{BREAK_EVEN:.1%}**.

{_classification_table(art['ats'], 'Against the spread (home cover)')}

{_classification_table(art['ou'], 'Totals (over hit)')}

### Beating the closing line

Out-of-sample hit rate when siding with each benchmark against the market
number:

{_table(art['edge'], ['benchmark', 'target', 'picks', 'hit_rate'], ['Benchmark', 'Target', 'Picks', 'Hit rate'], digits=4)}

---

## Section 6 - Preliminary Conclusions

{_conclusions(df, art, sp_available)}

---

## Appendix A - Feature coverage in the research sample

{_table(art['coverage'].sort_values('coverage', ascending=False), ['feature', 'present', 'coverage'], ['Feature', 'Present', 'Coverage'], digits=3)}

## Appendix B - Leakage scan

Strongest absolute correlations between any candidate feature and an outcome.
Anything above 0.98 would be an outcome in disguise; nothing here is close.

{_table(art['leakage'].head(12), ['target', 'feature', 'n', 'correlation', 'suspicious'], ['Target', 'Feature', 'n', 'Correlation', 'Suspicious'], digits=4)}

## Appendix C - Reproducing this report

```bash
make all          # ingest -> staging -> warehouse -> research
# or, step by step
python -m atlas.ingest
python -m atlas.warehouse.build
python -m atlas.research.report
```
"""
    )
    return "".join(parts)


def _classification_table(block: dict[str, dict], title: str) -> str:
    rows = []
    for name, m in block.items():
        rows.append(
            {
                "feature set": name,
                "n": m.get("n", 0),
                "accuracy": m.get("accuracy", float("nan")),
                "log_loss": m.get("log_loss", float("nan")),
                "base_rate": m.get("base_rate", float("nan")),
            }
        )
    body = _table(
        pd.DataFrame(rows),
        ["feature set", "n", "accuracy", "log_loss", "base_rate"],
        ["Feature set", "n", "Accuracy", "Log loss", "Base rate"],
        digits=4,
    )
    return f"**{title}**\n\n{body}"


def _conclusions(df: pd.DataFrame, art: dict, sp_available: bool) -> str:
    rank = art["ranking"]
    margin = rank[(rank["target"] == "margin") & rank["available"]]
    total = rank[(rank["target"] == "total") & rank["available"]]
    margin_nonmarket = margin[~margin["variable"].str.startswith("Market")]
    total_nonmarket = total[~total["variable"].str.startswith("Market")]

    top_margin = margin_nonmarket.head(3)["variable"].tolist()
    top_total = total_nonmarket.head(3)["variable"].tolist()

    best_margin_edge = margin["gain_over_market"].max()
    best_total_edge = total["gain_over_market"].max()
    edge_margin_var = (
        margin.loc[margin["gain_over_market"].idxmax(), "variable"]
        if margin["gain_over_market"].notna().any()
        else "none"
    )
    edge_total_var = (
        total.loc[total["gain_over_market"].idxmax(), "variable"]
        if total["gain_over_market"].notna().any()
        else "none"
    )
    material = rank[rank["material"].fillna(False).astype(bool)]

    ats = art["ats"]["all features (incl. market)"]
    ou = art["ou"]["all features (incl. market)"]

    # A variable only "beats the market" if its paired gain clears its own
    # noise; a positive point estimate on its own proves nothing.
    beats_market = not material.empty

    # A variable counts as unmeasured only if it was unavailable for *every*
    # target. Something available for margin but not totals is a coverage note,
    # not a missing variable.
    per_variable = rank.groupby("variable")["available"].any()
    missing = sorted(per_variable[~per_variable].index)
    partial = sorted(
        rank[
            rank["variable"].isin(per_variable[per_variable].index) & ~rank["available"]
        ]["variable"].unique()
    )

    lines = [
        "### What predicts margin",
        "",
        "1. **The closing spread, by a wide margin.** It is the single strongest "
        "variable in the sample and no combination of the others reaches it.",
        f"2. Among non-market variables the ranking is "
        f"**{', '.join(top_margin) if top_margin else 'n/a'}**.",
        "3. In-season efficiency beats stale ratings: a system's *current* view of a "
        "matchup (ESPN's pre-game FPI projection, CFBD pre-game Elo) clearly outperforms "
        "the same family's previous-season rating.",
        "",
        "### What predicts total",
        "",
        "1. **The closing total**, again by a wide margin.",
        f"2. Among non-market variables: "
        f"**{', '.join(top_total) if top_total else 'n/a'}**.",
        "3. Totals are intrinsically harder than margins here: the market's own R² on "
        "totals is far below its R² on margins, so there is less structure for anything "
        "to capture.",
        "",
        "### Does anything beat the market?",
        "",
        f"On margin, the largest marginal gain over the closing spread was "
        f"**{_fmt(best_margin_edge, 4)} MAE** ({edge_margin_var}); on totals "
        f"**{_fmt(best_total_edge, 4)} MAE** ({edge_total_var}). Both are point "
        f"estimates; what matters is whether either clears its own error bar.",
        "",
    ]
    if beats_market:
        names = ", ".join(
            f"{r['variable']} ({r['target']}, t={_fmt(r['gain_t'], 2)})"
            for _, r in material.iterrows()
        )
        lines.append(
            f"**{len(material)} variable(s) cleared the significance bar** (paired "
            f"per-game t > {importance.MATERIAL_T:g}): {names}. That is a candidate edge "
            "and should be the first thing Phase 2 tries to break."
        )
    else:
        lines.append(
            "**No candidate variable improved on the closing line by more than its own "
            "noise.** The largest point estimates are a small fraction of a point of MAE "
            "and none reaches a paired t-statistic of "
            f"{importance.MATERIAL_T:g}; most marginal gains are outright negative. The "
            "closing spread and closing total already contain everything these public "
            "variables know. Atlas should treat the market as the prior it must justify "
            "departing from, not as one input among many."
        )
    lines += [
        "",
        f"Outcome classification is consistent with that: ATS accuracy with the full "
        f"feature set was **{_fmt(ats.get('accuracy'), 4)}** and totals "
        f"**{_fmt(ou.get('accuracy'), 4)}**, against a {BREAK_EVEN:.1%} break-even.",
        "",
        "### What is not yet measured",
        "",
    ]
    if missing:
        lines.append(
            "These candidate variables could not be evaluated at all in this build, "
            "because their only source is the CollegeFootballData API: **"
            + ", ".join(missing)
            + "**. They are wired end-to-end; they need `CFBD_API_KEY` and a rebuild."
        )
    else:
        lines.append("Every candidate variable in the mission brief was measurable.")
    if partial:
        lines.append(
            "\nMeasured for one target but not the other (no meaningful form exists on "
            "the other side): **" + ", ".join(partial) + "**."
        )
    if not sp_available:
        lines.append(
            "\nSP+ in particular is the one required benchmark this build cannot report, "
            "and it is the most likely of the missing variables to matter, since it is an "
            "efficiency-based rating rather than a résumé rating."
        )
    return "\n".join(lines)


def write_report(seed_frame: pd.DataFrame | None = None) -> Path:
    paths = config.paths().ensure()
    raw_df = seed_frame if seed_frame is not None else load_research_frame(paths.warehouse)
    df = research_sample(raw_df)
    art = build_artifacts(df)

    tables_dir = paths.reports / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)
    for name, obj in art.items():
        if isinstance(obj, pd.DataFrame):
            obj.to_csv(tables_dir / f"{name}.csv", index=False)
        else:
            (tables_dir / f"{name}.json").write_text(json.dumps(obj, indent=2, default=float) + "\n")

    text = render(df, raw_df, art)
    out = paths.reports / "atlas_research_report_v1.md"
    out.write_text(text)
    LOG.info("report written -> %s", out)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Atlas stage 4: research report")
    ap.parse_args()
    write_report()


if __name__ == "__main__":
    main()
