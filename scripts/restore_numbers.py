"""Put back the Atlas numbers a refresh overwrote, from the tracking store's git history.

    python scripts/restore_numbers.py            # restore, write tracking/numbers.csv, show the replay
    python scripts/restore_numbers.py --check    # show what would be restored and the replay, write nothing

Until 30 September 2026 the numbers table was keyed by game, market and model
version only, and the version names the model, not the games it learned from:
each refresh that took in new results rewrote every upcoming game's number
under the same version, and the signals formed from the old numbers could no
longer be replayed (`atlas/live/reproduce.py`). Every version of the table is
in git. This reads them all, finds for each signal the number in effect when it
was formed, and adds the ones the current table lacks. Nothing already in the
table changes. Run it from a full clone (not a depth-1 checkout).
"""

from __future__ import annotations

import argparse
import io
import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PATH = "tracking/numbers.csv"


def history(path: str = PATH) -> list[pd.DataFrame]:
    """Every committed version of the table, newest first."""
    commits = subprocess.run(["git", "log", "--format=%H", "--", path], cwd=ROOT, capture_output=True, text=True,
                             check=True).stdout.split()
    out = []
    for commit in commits:
        text = subprocess.run(["git", "show", f"{commit}:{path}"], cwd=ROOT, capture_output=True, text=True).stdout
        if text.strip():
            out.append(pd.read_csv(io.StringIO(text)))
    return out


def main() -> int:
    from atlas.live import reproduce
    from atlas.live.store import Store

    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true", help="report only; write nothing")
    args = ap.parse_args()
    store = Store.open()
    current, signals = store.read("numbers"), store.read("signals")
    versions = history()
    restored = reproduce.restore(current, versions, signals)
    print(f"{len(versions)} versions of {PATH} in history; {len(restored) - len(current)} rows restored "
          f"to the {len(current)} there")
    if not args.check:
        store.write("numbers", restored)
    for period in reproduce.periods(store):
        replay = reproduce.replay_signals(store, period)
        print(f"  {period} signals: {replay.matched} of {replay.rows} reproduce ({replay.detail})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
