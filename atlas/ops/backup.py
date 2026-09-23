"""Backing up the live record, and proving the backup is readable.

The tracking store is the one thing in Atlas that cannot be rebuilt. The
warehouse can be re-ingested from public mirrors, the site can be rebuilt from
the warehouse, and the social cards can be re-rasterised - but a signal is an
opinion published at a moment, and a moment does not come back. If
``tracking/signals.csv`` is lost, seven seasons of research still stand and
the live record starts again from zero.

So this module does two things, and the second matters more than the first:
it copies, and then it **reads the copy back and checks it**. A backup nobody
has restored is a hypothesis.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from atlas import config
from atlas.live.store import SCHEMA, Store, tracking_dir
from atlas.util import get_logger

LOG = get_logger(__name__)

#: Tables that cannot be recomputed from anything else. `games` and `numbers`
#: are derivable from the warehouse and a refresh, but they are small and
#: including them makes a restore one step instead of three.
CRITICAL = ("signals", "grades", "snapshots")


def root() -> Path:
    return config.paths().data / "backups"


@dataclass(frozen=True)
class Manifest:
    """What a backup contains, and what it should hash to."""

    created_at: str
    tables: dict[str, dict]

    @property
    def rows(self) -> int:
        return sum(t["rows"] for t in self.tables.values())

    def to_dict(self) -> dict:
        return {"created_at": self.created_at, "tables": self.tables}


def _digest(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            sha.update(chunk)
    return sha.hexdigest()


def create(destination: Path | None = None, *, source: Path | None = None) -> Path:
    """One timestamped, gzipped copy of every tracking table, with a manifest.

    Gzipped because a CSV of line snapshots compresses to about a tenth, and
    a year of backups should not need thinking about.
    """
    source = source or tracking_dir()
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out = (destination or root()) / stamp
    out.mkdir(parents=True, exist_ok=True)

    tables: dict[str, dict] = {}
    for table in SCHEMA:
        origin = source / f"{table}.csv"
        target = out / f"{table}.csv.gz"
        if origin.exists():
            with origin.open("rb") as src, gzip.open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
            frame = pd.read_csv(origin)
        elif table in CRITICAL:
            # A table that has legitimately never been written - `grades`
            # before the first game finishes - is backed up as its header
            # rather than skipped. A restore then produces a complete store
            # instead of one missing a file, and verification has something
            # real to check rather than a special case to tolerate.
            frame = pd.DataFrame(columns=SCHEMA[table])
            with gzip.open(target, "wt", newline="") as dst:
                frame.to_csv(dst, index=False)
            LOG.info("backup: %s is empty, stored as a header", table)
        else:
            LOG.info("backup: %s absent and not critical, skipped", table)
            continue
        tables[table] = {
            "rows": int(len(frame)),
            "columns": int(frame.shape[1]),
            "sha256": _digest(target),
            "bytes": target.stat().st_size,
            "critical": table in CRITICAL,
        }

    manifest = Manifest(created_at=datetime.now(UTC).isoformat(), tables=tables)
    (out / "MANIFEST.json").write_text(
        json.dumps(manifest.to_dict(), indent=2, sort_keys=True))
    LOG.info("backup: %s — %d tables, %d rows, %.1f KB", out.name,
             len(tables), manifest.rows,
             sum(t["bytes"] for t in tables.values()) / 1024)
    return out


def verify(backup: Path) -> list[str]:
    """Read the backup back. Returns a list of problems; empty means good.

    Three checks, in increasing order of what they would catch:

    1. the manifest exists and names the critical tables,
    2. every file hashes to what the manifest says,
    3. **every table parses back into a DataFrame with the expected
       columns** - which is the only one that proves the bytes are usable
       rather than merely present.
    """
    problems: list[str] = []
    manifest_path = backup / "MANIFEST.json"
    if not manifest_path.exists():
        return [f"{backup.name}: no MANIFEST.json"]

    manifest = json.loads(manifest_path.read_text())
    tables = manifest.get("tables", {})

    for table in CRITICAL:
        if table not in tables:
            problems.append(f"{backup.name}: critical table {table!r} not in the backup")

    for table, meta in tables.items():
        path = backup / f"{table}.csv.gz"
        if not path.exists():
            problems.append(f"{backup.name}: {table} listed but the file is missing")
            continue
        if _digest(path) != meta["sha256"]:
            problems.append(f"{backup.name}: {table} does not match its checksum")
            continue
        try:
            frame = pd.read_csv(path, compression="gzip")
        except (OSError, ValueError, pd.errors.ParserError) as exc:
            problems.append(f"{backup.name}: {table} will not parse — {exc}")
            continue
        if len(frame) != meta["rows"]:
            problems.append(
                f"{backup.name}: {table} restored {len(frame)} rows, "
                f"manifest says {meta['rows']}")
        expected = set(SCHEMA.get(table, []))
        missing = expected - set(frame.columns)
        if missing and len(frame):
            problems.append(f"{backup.name}: {table} is missing columns {sorted(missing)}")
    return problems


def restore(backup: Path, destination: Path) -> dict[str, int]:
    """Write a backup back out as plain CSV. Never targets the live store.

    Restoring over a running tracker is a decision an operator makes with
    their own hands; this writes somewhere else and leaves the swap to them.
    """
    if destination.resolve() == tracking_dir().resolve():
        raise ValueError(
            "refusing to restore over the live tracking store — restore "
            "somewhere else and move it deliberately")
    destination.mkdir(parents=True, exist_ok=True)
    written = {}
    for path in sorted(backup.glob("*.csv.gz")):
        table = path.name.removesuffix(".csv.gz")
        frame = pd.read_csv(path, compression="gzip")
        frame.to_csv(destination / f"{table}.csv", index=False)
        written[table] = len(frame)
    LOG.info("restored %d tables into %s", len(written), destination)
    return written


def prune(keep: int = 30, *, at: Path | None = None) -> list[Path]:
    """Keep the most recent ``keep`` backups. Daily, that is a month."""
    backups = sorted((at or root()).glob("*T*Z"), reverse=True)
    removed = []
    for old in backups[keep:]:
        shutil.rmtree(old)
        removed.append(old)
    if removed:
        LOG.info("pruned %d old backups", len(removed))
    return removed


def latest(at: Path | None = None) -> Path | None:
    backups = sorted((at or root()).glob("*T*Z"), reverse=True)
    return backups[0] if backups else None


def summary(at: Path | None = None) -> str:
    backups = sorted((at or root()).glob("*T*Z"), reverse=True)
    if not backups:
        return "no backups"
    lines = [f"{len(backups)} backups"]
    for backup in backups[:5]:
        manifest = backup / "MANIFEST.json"
        if not manifest.exists():
            lines.append(f"  {backup.name}  (no manifest)")
            continue
        data = json.loads(manifest.read_text())
        rows = sum(t["rows"] for t in data["tables"].values())
        size = sum(t["bytes"] for t in data["tables"].values())
        lines.append(f"  {backup.name}  {rows:>7,} rows  {size / 1024:6.1f} KB")
    # A store that is not being backed up looks identical to one that is,
    # until the day it matters.
    live = Store.open()
    try:
        signals = len(live.read("signals"))
        lines.append(f"  live store: {signals:,} signals")
    except (FileNotFoundError, OSError):
        lines.append("  live store: unreadable")
    return "\n".join(lines)
