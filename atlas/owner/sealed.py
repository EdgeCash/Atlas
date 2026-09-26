"""Records only the owner can read.

Each is a directory of files, one per week, each compressed and sealed with
the owner key the way the owner page is (`atlas/dfs/owner.py`: PBKDF2 and
AES-256-GCM). Committed with the tracking store, which is their backup; a
week's file is rewritten only while that week has something new, so the
repository grows by a small file a week. Nothing readable is written
anywhere that is kept.
"""

from __future__ import annotations

import gzip
import json
from collections.abc import Iterable
from pathlib import Path


class Unreadable(Exception):
    """A record exists but the key does not open it."""


def week_file(where: Path, season, week) -> Path:
    return where / f"{int(season)}-{int(week):02d}.enc.json"


def open_text(text: str, passphrase: str) -> list[dict]:
    """The rows of one sealed file, given its text."""
    from atlas.dfs import owner

    try:
        plain = gzip.decompress(owner.decrypt(json.loads(text), passphrase))
    except Exception as error:  # noqa: BLE001 - the type only: never the content
        raise Unreadable(type(error).__name__) from None
    return json.loads(plain)["rows"]


def load(where: Path, passphrase: str) -> list[dict]:
    """Every row of every week, opened; none when there is no record yet."""
    rows: list[dict] = []
    for f in sorted(where.glob("*.enc.json")) if where.exists() else []:
        rows.extend(open_text(f.read_text(), passphrase))
    return rows


def seal(rows: list[dict], passphrase: str, path: Path, *, names: Iterable = ()) -> Path:
    """One week's rows, compressed and sealed. ``names`` are strings that must
    not survive into the file in the clear - a check, since they cannot."""
    from atlas.dfs import owner

    plain = json.dumps({"rows": rows}, separators=(",", ":"), allow_nan=False).encode("utf-8")
    packed = gzip.compress(plain, mtime=0)
    box = owner.encrypt(packed, passphrase)
    published = json.dumps(box)
    if owner.decrypt(box, passphrase) != packed or any(
            isinstance(n, str) and len(n) > 4 and n in published for n in names):
        raise RuntimeError("the record did not seal")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(published + "\n")
    return path
