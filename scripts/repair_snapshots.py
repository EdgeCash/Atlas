"""One-off: rebuild tracking/snapshots.csv from its own git history.

Until the store moved to append-on-change, every sighting of an unchanged
quote rewrote that row's ``captured_at``. The stored history therefore records
when each quote was last seen, not when it first appeared, and a line that
went A -> B -> A kept only the second A.

Every poll commits the table, so git holds each sighting. This reads every
committed version, takes each distinct (quote, captured_at) row as one
sighting, and folds them oldest first through the same append-on-change rule
the poller now uses. Grades are cleared so the next poll regrades every
started game against the repaired history.

    python scripts/repair_snapshots.py            # dry run: print the diff in rows
    python scripts/repair_snapshots.py --write    # rewrite snapshots.csv and grades.csv
"""

from __future__ import annotations

import argparse
import io
import subprocess

import pandas as pd

from atlas.live.books import canonical
from atlas.live.store import SCHEMA, Store, changes

PATH = "tracking/snapshots.csv"


def versions() -> list[pd.DataFrame]:
    commits = subprocess.run(["git", "log", "--format=%H", "--", PATH],
                             capture_output=True, text=True, check=True).stdout.split()
    out = []
    for commit in commits:
        text = subprocess.run(["git", "show", f"{commit}:{PATH}"],
                              capture_output=True, text=True, check=True).stdout
        out.append(pd.read_csv(io.StringIO(text)))
    return out


def rebuild(frames: list[pd.DataFrame]) -> pd.DataFrame:
    sightings = pd.concat([f.reindex(columns=SCHEMA["snapshots"]) for f in frames], ignore_index=True)
    sightings["book"] = sightings["book"].map(canonical)
    sightings = sightings.drop_duplicates(["game_id", "book", "market", "line", "price", "captured_at"],
                                          keep="first")
    # A sighting's last look is its own capture: last_seen_at is recomputed by the fold.
    sightings["last_seen_at"] = sightings["captured_at"]
    history, _ = changes(pd.DataFrame(columns=SCHEMA["snapshots"]), sightings)
    return history


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    store = Store.open()
    before = store.read("snapshots")
    after = rebuild([before, *versions()])
    print(f"snapshots: {len(before)} rows stored, {len(after)} after the rebuild")
    if args.write:
        store.write("snapshots", after)
        grades = store.read("grades")
        store.write("grades", grades.iloc[0:0])
        print(f"grades: {len(grades)} cleared; the next poll regrades them")


if __name__ == "__main__":
    main()
