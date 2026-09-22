"""Track 4: the season dashboard.

Read-only, self-contained, generated from the tracking tables on every run.
It answers six questions and no others: how many signals, how many primary,
how many graded, what the CLV beat rate is, what mean CLV is, and whether the
kill criteria are holding.

There is no betting information on this page because there is none in the
system. No stake, no price-implied return, no profit - the vocabulary is
signals, points of line, and the status of a pre-registered criterion.

Colour follows the data's job. The weekly CLV chart is **diverging** - a week
can move toward Atlas or away from it, and zero is a real midpoint - so it
uses the validated blue/red poles with a neutral grey at zero. The beat-rate
chart is a single sequential series against a fixed reference line. Criterion
status uses the reserved status palette and always ships an icon and a label,
so state is never carried by colour alone.
"""

from __future__ import annotations

import html
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from atlas import config
from atlas.live import drift as drifting
from atlas.live import quality
from atlas.live import scorecard as sc
from atlas.live.store import Store
from atlas.util import get_logger

LOG = get_logger(__name__)

#: Validated against the reference palette in both modes
#: (`node scripts/validate_palette.js "#2a78d6,#e34948" --mode light`, and the
#: dark steps against #1a1a19: all checks pass, worst adjacent CVD dE 19.2).
TOKENS_LIGHT = {
    "surface": "#fcfcfb", "panel": "#ffffff", "border": "#e3e2dd",
    "text": "#0b0b0b", "muted": "#52514e", "grid": "#e8e7e2",
    "pos": "#2a78d6", "neg": "#e34948", "zero": "#f0efec",
    "good": "#0ca30c", "warning": "#fab219", "critical": "#d03b3b",
}
TOKENS_DARK = {
    "surface": "#1a1a19", "panel": "#212120", "border": "#343431",
    "text": "#ffffff", "muted": "#c3c2b7", "grid": "#2f2f2c",
    "pos": "#3987e5", "neg": "#e66767", "zero": "#383835",
    "good": "#0ca30c", "warning": "#fab219", "critical": "#d03b3b",
}

ICONS = {"good": "✓", "warning": "!", "critical": "✕", "collecting": "…"}


def _fmt(value: object, digits: int = 3, dash: str = "—") -> str:
    number = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if number is None or not np.isfinite(number):
        return dash
    return f"{number:.{digits}f}"


def _pct(value: object, dash: str = "—") -> str:
    number = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if number is None or not np.isfinite(number):
        return dash
    return f"{number:.1%}"


def collect(store: Store | None = None) -> dict:
    store = store or Store.open()
    signals = store.read("signals")
    grades = store.read("grades")
    frame = sc.graded_frame(signals, grades)
    primary = signals[signals["selection"] == "primary"] if not signals.empty else signals
    stats = sc.by_selection(frame)
    primary_stats = (
        stats[stats["selection"] == "primary"].iloc[0].to_dict()
        if not stats.empty and (stats["selection"] == "primary").any()
        else {}
    )
    return {
        "signals": signals,
        "primary": primary,
        "frame": frame,
        "criteria": sc.kill_criteria(frame),
        "weekly": sc.scorecard(frame, by="week"),
        "stats": primary_stats,
        "exceptions": quality.exceptions(store),
        "alerts": drifting.monitor(store),
        "runs": store.read("runs"),
    }


# ---------------------------------------------------------------------------
# Marks
# ---------------------------------------------------------------------------


def _diverging_bars(weekly: pd.DataFrame, *, width: int = 620, height: int = 200) -> str:
    """Mean CLV by week: a week can go either way, so zero is the baseline."""
    if weekly.empty:
        return _empty_plot(width, height, "No graded weeks yet")
    values = pd.to_numeric(weekly["mean_clv"], errors="coerce").fillna(0.0).to_numpy()
    labels = weekly["week"].astype(str).tolist()

    pad_l, pad_r, pad_t, pad_b = 52, 16, 14, 30
    plot_w, plot_h = width - pad_l - pad_r, height - pad_t - pad_b
    span = max(1.0, float(np.abs(values).max()) * 1.25)
    zero_y = pad_t + plot_h / 2
    # 2px of surface between adjacent bars, per the mark spec.
    slot = plot_w / max(len(values), 1)
    bar_w = max(6.0, min(46.0, slot - 8.0))

    parts = [f'<svg viewBox="0 0 {width} {height}" role="img" class="plot" '
             f'aria-label="Mean closing-line value in points of line, by week. '
             f'Bars above the axis mean the market moved toward Atlas.">']
    for tick in (-span, -span / 2, 0.0, span / 2, span):
        y = zero_y - tick / span * (plot_h / 2)
        parts.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{pad_l + plot_w}" '
                     f'y2="{y:.1f}" class="grid"/>')
        parts.append(f'<text x="{pad_l - 8}" y="{y + 4:.1f}" class="axis" '
                     f'text-anchor="end">{tick:+.1f}</text>')

    for i, (value, label) in enumerate(zip(values, labels, strict=False)):
        x = pad_l + i * slot + (slot - bar_w) / 2
        h = abs(value) / span * (plot_h / 2)
        y = zero_y - h if value >= 0 else zero_y
        fill = "var(--pos)" if value >= 0 else "var(--neg)"
        parts.append(
            f'<g class="mark"><title>Week {label}: {value:+.3f} points</title>'
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" '
            f'height="{max(h, 1.0):.1f}" rx="4" fill="{fill}"/>'
            f'<rect x="{x:.1f}" y="{pad_t}" width="{bar_w:.1f}" height="{plot_h}" '
            f'fill="transparent"/></g>'
        )
        parts.append(f'<text x="{x + bar_w / 2:.1f}" y="{pad_t + plot_h + 18}" '
                     f'class="axis" text-anchor="middle">{html.escape(label)}</text>')

    parts.append(f'<line x1="{pad_l}" y1="{zero_y:.1f}" x2="{pad_l + plot_w}" '
                 f'y2="{zero_y:.1f}" class="zero"/>')
    parts.append("</svg>")
    return "".join(parts)


def _rate_bars(weekly: pd.DataFrame, *, width: int = 620, height: int = 200) -> str:
    """Beat rate by week against the kill threshold."""
    if weekly.empty:
        return _empty_plot(width, height, "No graded weeks yet")
    values = pd.to_numeric(weekly["beat_rate"], errors="coerce").to_numpy()
    labels = weekly["week"].astype(str).tolist()

    pad_l, pad_r, pad_t, pad_b = 52, 16, 14, 30
    plot_w, plot_h = width - pad_l - pad_r, height - pad_t - pad_b
    lo, hi = 0.30, 0.80
    slot = plot_w / max(len(values), 1)
    bar_w = max(6.0, min(46.0, slot - 8.0))

    def y_of(v: float) -> float:
        return pad_t + plot_h - (min(max(v, lo), hi) - lo) / (hi - lo) * plot_h

    parts = [f'<svg viewBox="0 0 {width} {height}" role="img" class="plot" '
             f'aria-label="Weekly CLV beat rate against the 55% kill threshold.">']
    for tick in (0.30, 0.40, 0.50, 0.60, 0.70, 0.80):
        y = y_of(tick)
        parts.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{pad_l + plot_w}" '
                     f'y2="{y:.1f}" class="grid"/>')
        parts.append(f'<text x="{pad_l - 8}" y="{y + 4:.1f}" class="axis" '
                     f'text-anchor="end">{tick:.0%}</text>')

    for i, (value, label) in enumerate(zip(values, labels, strict=False)):
        if not np.isfinite(value):
            continue
        x = pad_l + i * slot + (slot - bar_w) / 2
        y = y_of(value)
        parts.append(
            f'<g class="mark"><title>Week {label}: {value:.1%} beat rate</title>'
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" '
            f'height="{max(pad_t + plot_h - y, 1.0):.1f}" rx="4" fill="var(--pos)"/>'
            f'<rect x="{x:.1f}" y="{pad_t}" width="{bar_w:.1f}" height="{plot_h}" '
            f'fill="transparent"/></g>'
        )
        parts.append(f'<text x="{x + bar_w / 2:.1f}" y="{pad_t + plot_h + 18}" '
                     f'class="axis" text-anchor="middle">{html.escape(label)}</text>')

    threshold_y = y_of(sc.KILL_BEAT_RATE)
    parts.append(f'<line x1="{pad_l}" y1="{threshold_y:.1f}" x2="{pad_l + plot_w}" '
                 f'y2="{threshold_y:.1f}" class="threshold"><title>Kill threshold '
                 f'{sc.KILL_BEAT_RATE:.0%}</title></line>')
    parts.append("</svg>")
    return "".join(parts)


def _empty_plot(width: int, height: int, message: str) -> str:
    return (
        f'<svg viewBox="0 0 {width} {height}" role="img" class="plot" '
        f'aria-label="{html.escape(message)}">'
        f'<text x="{width / 2}" y="{height / 2}" class="axis" text-anchor="middle">'
        f"{html.escape(message)}</text></svg>"
    )


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------


def _tile(label: str, value: str, note: str = "") -> str:
    return (
        f'<div class="tile"><div class="tile-label">{html.escape(label)}</div>'
        f'<div class="tile-value">{html.escape(value)}</div>'
        f'<div class="tile-note">{html.escape(note)}</div></div>'
    )


def _criterion_row(criterion: sc.Criterion) -> str:
    if not criterion.decided:
        state, icon = "collecting", ICONS["collecting"]
        word = "Collecting"
    elif criterion.passing:
        state, icon, word = "good", ICONS["good"], "Holding"
    else:
        state, icon, word = "critical", ICONS["critical"], "Breached"
    observed = (
        _pct(criterion.observed) if "rate" in criterion.name.lower()
        or "window" in criterion.name.lower() else _fmt(criterion.observed)
    )
    threshold = (
        _pct(criterion.threshold) if "rate" in criterion.name.lower()
        or "window" in criterion.name.lower() else _fmt(criterion.threshold, 2)
    )
    return (
        f'<tr><td><span class="pill {state}">{icon} {word}</span></td>'
        f"<td>{html.escape(criterion.name)}</td>"
        f'<td class="num">{observed}</td><td class="num">{threshold}</td>'
        f'<td class="num">{criterion.graded:,}</td>'
        f'<td class="muted">{html.escape(criterion.note)}</td></tr>'
    )


def _table(frame: pd.DataFrame, columns: list[str], headers: list[str],
           formatters: dict | None = None) -> str:
    if frame is None or frame.empty:
        return '<p class="muted">Nothing recorded yet.</p>'
    formatters = formatters or {}
    head = "".join(f"<th>{html.escape(h)}</th>" for h in headers)
    rows = []
    for _, row in frame.iterrows():
        cells = []
        for column in columns:
            value = row.get(column)
            render = formatters.get(column)
            text = render(value) if render else (
                "—" if value is None or (isinstance(value, float) and not np.isfinite(value))
                else str(value)
            )
            cells.append(f'<td class="num">{html.escape(text)}</td>')
        rows.append("<tr>" + "".join(cells) + "</tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(rows)}</tbody></table>"


def _tokens(mapping: dict) -> str:
    return "".join(f"--{k}:{v};" for k, v in mapping.items())


def render(bundle: dict) -> str:
    signals, primary = bundle["signals"], bundle["primary"]
    stats, weekly = bundle["stats"], bundle["weekly"]
    criteria = bundle["criteria"]
    graded = int(criteria[0].graded)
    generated = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    seasons = sc.seasons_complete(signals)

    blocking = bundle["exceptions"]
    blocking = int((blocking["severity"] == "blocking").sum()) if not blocking.empty else 0
    firing = bundle["alerts"]
    firing = int((firing["severity"] != "ok").sum()) if not firing.empty else 0

    # A blocking exception outranks the criteria. A green headline sitting
    # beside "300 blocking exceptions" is exactly the accidental corruption
    # this phase exists to make impossible.
    if blocking:
        status, tone = "SUSPECT", "critical"
    elif not any(c.decided for c in criteria):
        status, tone = "COLLECTING", "warning"
    elif all(c.passing for c in criteria):
        status, tone = "PASSING", "good"
    else:
        status, tone = "FAILING", "critical"

    tiles = "".join([
        _tile("Signals", f"{len(signals):,}", "every opinion recorded"),
        _tile("Primary signals", f"{len(primary):,}", "the population under test"),
        _tile("Graded", f"{graded:,}",
              f"of {sc.MIN_GRADED_FOR_VERDICT:,} needed for a verdict"),
        _tile("CLV beat rate", _pct(stats.get("beat_rate")), "pushes excluded"),
        _tile("Mean CLV", _fmt(stats.get("mean_clv")), "points of line"),
        _tile("Seasons tracked", f"{seasons} of {sc.SEASONS_REQUIRED}",
              "success criterion"),
    ])

    weekly_table = _table(
        weekly,
        ["week", "signals", "graded", "pushes", "beat_rate", "mean_clv", "median_clv"],
        ["Week", "Signals", "Graded", "Pushes", "Beat rate", "Mean CLV", "Median CLV"],
        {
            "beat_rate": _pct, "mean_clv": _fmt, "median_clv": _fmt,
            "week": lambda v: _fmt(v, 0),
            "signals": lambda v: _fmt(v, 0), "graded": lambda v: _fmt(v, 0),
            "pushes": lambda v: _fmt(v, 0),
        },
    ) if not weekly.empty else '<p class="muted">No graded weeks yet.</p>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Atlas Season Dashboard</title>
<style>
  :root {{ color-scheme: light; {_tokens(TOKENS_LIGHT)} }}
  @media (prefers-color-scheme: dark) {{
    :root:not([data-theme="light"]) {{ color-scheme: dark; {_tokens(TOKENS_DARK)} }}
  }}
  :root[data-theme="dark"] {{ color-scheme: dark; {_tokens(TOKENS_DARK)} }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; padding: 32px 16px 64px; background: var(--surface); color: var(--text);
    font: 15px/1.55 system-ui, -apple-system, "Segoe UI", sans-serif;
  }}
  .wrap {{ max-width: 980px; margin: 0 auto; }}
  h1 {{ font-size: 24px; margin: 0 0 4px; letter-spacing: -0.01em; }}
  h2 {{ font-size: 15px; margin: 36px 0 12px; letter-spacing: 0.02em;
        text-transform: uppercase; color: var(--muted); }}
  .sub {{ color: var(--muted); font-size: 13px; margin: 0 0 20px; }}
  .banner {{ border: 1px solid var(--border); border-left: 3px solid var(--pos);
             background: var(--panel); padding: 12px 14px; border-radius: 8px;
             font-size: 13.5px; color: var(--muted); margin: 0 0 24px; }}
  .banner strong {{ color: var(--text); }}
  .status {{ display: inline-flex; align-items: center; white-space: nowrap;
             gap: 8px; font-weight: 650; font-size: 13px; padding: 5px 12px;
             border-radius: 999px; border: 1px solid var(--border); }}
  .status.good {{ color: var(--good); }}
  .status.warning {{ color: var(--muted); }}
  .status.critical {{ color: var(--critical); }}
  .tiles {{ display: grid; gap: 10px; grid-template-columns: repeat(auto-fit, minmax(148px, 1fr)); }}
  .tile {{ background: var(--panel); border: 1px solid var(--border);
           border-radius: 10px; padding: 14px 15px; }}
  .tile-label {{ font-size: 11.5px; text-transform: uppercase; letter-spacing: 0.04em;
                 color: var(--muted); }}
  .tile-value {{ font-size: 27px; font-weight: 640; letter-spacing: -0.02em;
                 margin: 5px 0 2px; font-variant-numeric: tabular-nums; }}
  .tile-note {{ font-size: 11.5px; color: var(--muted); }}
  .panel {{ background: var(--panel); border: 1px solid var(--border);
            border-radius: 10px; padding: 16px; }}
  .charts {{ display: grid; gap: 14px; grid-template-columns: 1fr; }}
  @media (min-width: 760px) {{ .charts {{ grid-template-columns: 1fr 1fr; }} }}
  .plot {{ width: 100%; height: auto; display: block; }}
  .plot-title {{ font-size: 13px; font-weight: 620; margin: 0 0 2px; }}
  .plot-note {{ font-size: 11.5px; color: var(--muted); margin: 0 0 10px; }}
  .grid {{ stroke: var(--grid); stroke-width: 1; }}
  .zero {{ stroke: var(--muted); stroke-width: 1.5; }}
  .threshold {{ stroke: var(--critical); stroke-width: 2; stroke-dasharray: 5 4; }}
  .axis {{ fill: var(--muted); font-size: 10.5px;
           font-family: system-ui, sans-serif; }}
  .mark rect:first-child {{ transition: opacity .12s ease; }}
  .mark:hover rect:first-child {{ opacity: .72; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px;
           font-variant-numeric: tabular-nums; }}
  th, td {{ text-align: left; padding: 7px 10px;
            border-bottom: 1px solid var(--border); }}
  th {{ font-size: 11.5px; text-transform: uppercase; letter-spacing: 0.03em;
        color: var(--muted); font-weight: 600; }}
  td.num {{ text-align: right; }}
  td.num:first-child, td.muted {{ text-align: left; }}
  .muted {{ color: var(--muted); font-size: 13px; }}
  .pill {{ display: inline-block; white-space: nowrap; font-size: 11.5px;
           font-weight: 640; padding: 2px 9px; border-radius: 999px;
           border: 1px solid currentColor; }}
  .pill.good {{ color: var(--good); }}
  .pill.critical {{ color: var(--critical); }}
  .pill.collecting {{ color: var(--muted); }}
  footer {{ margin-top: 40px; font-size: 12px; color: var(--muted); }}
</style>
</head>
<body>
<div class="wrap">
  <h1>Atlas Season Dashboard</h1>
  <p class="sub">Generated {generated} · read-only · rebuilt from
     <code>tracking/</code> on every tracker run</p>

  <div class="banner">
    <strong>Atlas generates opinions. Atlas does not generate bets.</strong>
    There is no stake, price-implied return, profit or wagering information on
    this page, because there is none in the system. Everything below is
    measured in signals and points of line.
  </div>

  <p><span class="status {tone}">{ICONS.get(tone, "")} {status}</span>
     <span class="muted">&nbsp;{graded:,} graded of
     {sc.MIN_GRADED_FOR_VERDICT:,} needed · {blocking} blocking data-quality
     exception(s) · {firing} monitor alert(s) firing</span></p>

  <h2>Season</h2>
  <div class="tiles">{tiles}</div>

  <h2>Kill criteria</h2>
  <div class="panel">
    <table>
      <thead><tr><th>Status</th><th>Criterion</th><th>Observed</th>
      <th>Threshold</th><th>Graded</th><th>Requirement</th></tr></thead>
      <tbody>{"".join(_criterion_row(c) for c in criteria)}</tbody>
    </table>
    <p class="muted" style="margin-bottom:0">Frozen in
      <code>reports/atlas_gamma_assessment.md</code> before any live signal
      existed. Checked, never tuned.</p>
  </div>

  <h2>By week</h2>
  <div class="charts">
    <div class="panel">
      <p class="plot-title">Mean CLV, points of line</p>
      <p class="plot-note">Above the axis, the market moved toward Atlas.</p>
      {_diverging_bars(weekly)}
    </div>
    <div class="panel">
      <p class="plot-title">CLV beat rate</p>
      <p class="plot-note">Pushes excluded. Dashed line is the kill threshold.</p>
      {_rate_bars(weekly)}
    </div>
  </div>

  <h2>The same data, as a table</h2>
  <div class="panel">{weekly_table}</div>

  <footer>
    Source: <code>tracking/signals.csv</code>, <code>tracking/grades.csv</code>.
    Full report: <code>reports/live_clv_tracking.md</code>.
    Operations manual: <code>reports/atlas_operations_manual.md</code>.
  </footer>
</div>
</body>
</html>
"""


def write(bundle: dict | None = None, store: Store | None = None) -> Path:
    store = store or Store.open()
    bundle = bundle or collect(store)
    out = config.paths().ensure().reports / "dashboard.html"
    out.write_text(render(bundle))
    LOG.info("wrote %s", out)
    return out
