"""Merge this run's tracking store with the one already on the branch, table by table.

    python scripts/merge_tracking.py FETCH_HEAD        # after `git fetch origin main`

Two runs that overlap (a poll under the daily rebuild: three rebuilds lost on
26 September 2026) both commit ``tracking/``. The second's ``git pull --rebase``
then fails on the CSVs, because each appended different rows to the same
sorted files, and the whole run's work is lost with the commit that never
happens. Line-level git cannot merge them; the store can. Every table is
keyed (`atlas.live.store.KEYS`), so each is rewritten as the branch's rows
with this run's upserted over them, the way `Store.upsert` writes. Both runs'
captures survive.

The sealed owner records (``tracking/owner_*``: one file per week, rewritten
whole) are merged the same way when the owner key is in the environment
(``ATLAS_OWNER_KEY``): each week's file that both runs rewrote becomes the
branch's rows with this run's laid over them by the record's key, resealed.
Without the key this run's file stands, and the other run's rows for that
week are lost with it; the workflow prints which.

Everything else a run writes (the reports, the freshness stamp, the
manifests) is regenerated whole by every run, and publish.yml lets this
run's stand. Exit 0 when everything merged, non-zero when a file could not
be read; nothing readable from a sealed record is printed either way.
"""

from __future__ import annotations

import io
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

#: The sealed records and what identifies a row in each.
SEALED: dict[str, list[str]] = {
    "owner_plays": ["play_id"],
    "owner_board": ["pick_id"],
    "owner_market": ["sport", "event_id", "market", "selection", "book_id", "captured_at"],
}


def remote_text(ref: str, path: str) -> str | None:
    """The file at ``ref``, or None when the branch has no such file."""
    result = subprocess.run(["git", "show", f"{ref}:{path}"], cwd=ROOT, capture_output=True, text=True,
                            check=False)
    return result.stdout if result.returncode == 0 else None


def remote_files(ref: str, directory: str) -> list[str]:
    """The paths under ``directory`` at ``ref``."""
    result = subprocess.run(["git", "ls-tree", "--name-only", ref, "--", f"{directory}/"], cwd=ROOT,
                            capture_output=True, text=True, check=False)
    return [line for line in result.stdout.splitlines() if line] if result.returncode == 0 else []


def merge_table(table: str, ours: pd.DataFrame, theirs: pd.DataFrame | None) -> pd.DataFrame:
    """The branch's rows with this run's upserted over them, by the table's keys."""
    from atlas.live.store import KEYS, SCHEMA

    columns = SCHEMA[table]
    ours = ours.reindex(columns=columns)
    if theirs is None or theirs.empty:
        return ours
    theirs = theirs.reindex(columns=columns)
    combined = pd.concat([theirs, ours], ignore_index=True)
    return combined.drop_duplicates(subset=KEYS[table], keep="last")


def merge_rows(theirs: list[dict], ours: list[dict], keys: list[str]) -> list[dict]:
    """The branch's rows in their order, each replaced by this run's row of the same key where
    there is one, then this run's new rows in their order."""
    ident = lambda row: tuple(row.get(k) for k in keys)  # noqa: E731
    mine = {ident(row): row for row in ours}
    out = [mine.pop(ident(row), row) for row in theirs]
    out.extend(row for row in ours if ident(row) in mine)
    return out


def merge_store(ref: str, tracking: Path | None = None,
                remote: Callable[[str], str | None] | None = None) -> list[str]:
    """Merge every CSV table this run wrote with the branch's. Returns the tables merged."""
    from atlas.live.store import SCHEMA, Store

    tracking = tracking or ROOT / "tracking"
    remote = remote or (lambda path: remote_text(ref, path))
    store = Store.open(tracking)
    merged = []
    for table in SCHEMA:
        if not (tracking / f"{table}.csv").exists():
            continue
        text = remote(f"tracking/{table}.csv")
        theirs = pd.read_csv(io.StringIO(text)) if text else None
        store.write(table, merge_table(table, store.read(table), theirs))
        merged.append(table)
    return merged


def merge_sealed(ref: str, passphrase: str, tracking: Path | None = None,
                 remote: Callable[[str], str | None] | None = None,
                 listing: Callable[[str], list[str]] | None = None) -> list[str]:
    """Merge every sealed weekly file that both this run and the branch rewrote. Returns their
    paths. A file only one side has needs no merge: this run's stands, the branch's arrives
    with the branch."""
    from atlas.owner import sealed

    tracking = tracking or ROOT / "tracking"
    remote = remote or (lambda path: remote_text(ref, path))
    listing = listing or (lambda directory: remote_files(ref, directory))
    merged = []
    for name, keys in SEALED.items():
        where = tracking / name
        if not where.exists():
            continue
        theirs_files = set(listing(f"tracking/{name}"))
        for f in sorted(where.glob("*.enc.json")):
            path = f"tracking/{name}/{f.name}"
            if path not in theirs_files:
                continue
            text = remote(path)
            if not text:
                continue
            ours = sealed.open_text(f.read_text(), passphrase)
            theirs = sealed.open_text(text, passphrase)
            rows = merge_rows(theirs, ours, keys)
            if rows != ours:
                sealed.seal(rows, passphrase, f)
            merged.append(path)
    return merged


def main() -> int:
    from atlas.dfs import owner

    ref = sys.argv[1] if len(sys.argv) > 1 else "origin/main"
    try:
        tables = merge_store(ref)
        print(f"merge_tracking: {len(tables)} tables merged with {ref}: {', '.join(tables)}")
        passphrase = os.environ.get(owner.SECRET, "").strip()
        if passphrase:
            files = merge_sealed(ref, passphrase)
            print(f"merge_tracking: {len(files)} sealed files merged: {', '.join(files) or '-'}")
        else:
            print(f"merge_tracking: {owner.SECRET} not set; this run's sealed records stand as written")
    except Exception as error:  # noqa: BLE001 - the workflow reads the exit code
        print(f"merge_tracking: failed: {type(error).__name__}: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
