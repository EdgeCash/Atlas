#!/usr/bin/env python3
"""Build the warehouse twice from identical synthetic sources and diff it.

"Database generation must be reproducible" is a property, not a hope, so CI
asserts it: two independent builds must produce byte-identical parquet files
for every warehouse table.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from atlas.testing.synthetic import write_synthetic_raw  # noqa: E402
from atlas.warehouse import schema  # noqa: E402

SEASONS = [2019, 2020, 2021, 2022]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_once(base: Path) -> dict[str, str]:
    write_synthetic_raw(base / "raw", SEASONS)
    os.environ["ATLAS_DATA_DIR"] = str(base)
    # Re-import so the path override is picked up cleanly on each pass.
    for module in [m for m in list(sys.modules) if m.startswith("atlas")]:
        if module != "atlas.testing.synthetic":
            sys.modules.pop(module, None)
    from atlas.warehouse import build as build_mod

    build_mod.build(SEASONS)
    warehouse = base / "warehouse"
    return {t: digest(warehouse / f"{t}.parquet") for t in schema.TABLES}


def main() -> int:
    first = Path(tempfile.mkdtemp(prefix="atlas_repro_a_"))
    second = Path(tempfile.mkdtemp(prefix="atlas_repro_b_"))
    try:
        a = build_once(first)
        b = build_once(second)
    finally:
        shutil.rmtree(first, ignore_errors=True)
        shutil.rmtree(second, ignore_errors=True)

    failures = [t for t in schema.TABLES if a[t] != b[t]]
    for table in schema.TABLES:
        mark = "FAIL" if table in failures else "ok"
        print(f"{mark:4}  {table:20} {a[table][:16]}")
    if failures:
        print(f"\nnot reproducible: {', '.join(failures)}")
        return 1
    print("\nall warehouse tables are byte-identical across builds")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
