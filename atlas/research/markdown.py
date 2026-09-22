"""Markdown table rendering shared by the report generators.

Numbers in a research report have to survive being read quickly, so counts
never render as ``1234.000`` and a missing value never renders as ``nan``.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

#: Columns that are conceptually counts and should never render with decimals.
COUNT_COLUMNS = {
    "season", "games", "n", "n_features", "picks", "with_spread", "with_total",
    "with_efficiency", "with_fpi", "rank_standalone", "rank_over_market",
    "n_paired", "teams", "team_games", "with_qb", "changes", "settled",
    "opponents", "rank", "with_weather", "distinct_qbs", "n_prior_observations",
}


#: Columns rendered with %g - values like a 4-point threshold should read "4",
#: not "4.0000", but may legitimately be fractional.
COMPACT_COLUMNS = {"threshold", "price", "quantile"}


def fmt(value: float | None, digits: int = 3, dash: str = "n/a") -> str:
    if value is None or (isinstance(value, float) and not np.isfinite(value)):
        return dash
    return f"{value:.{digits}f}"


def table(df: pd.DataFrame, columns: list[str], headers: list[str], digits: int = 3) -> str:
    headers = [h.replace("|", "\\|") for h in headers]
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for _, row in df.iterrows():
        cells = []
        for col in columns:
            value = row.get(col)
            if isinstance(value, (bool, np.bool_)):
                cells.append("yes" if value else "no")
            elif isinstance(value, (int, np.integer)):
                cells.append(str(int(value)) if col in COMPACT_COLUMNS | {"season"}
                             else f"{int(value):,}")
            elif isinstance(value, (float, np.floating)):
                if not np.isfinite(value):
                    cells.append("n/a")
                elif col in COMPACT_COLUMNS:
                    cells.append(f"{value:g}")
                elif col in COUNT_COLUMNS:
                    cells.append(str(int(value)) if col == "season" else f"{int(round(value)):,}")
                else:
                    cells.append(fmt(float(value), digits))
            else:
                cells.append("" if value is None else str(value))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)
