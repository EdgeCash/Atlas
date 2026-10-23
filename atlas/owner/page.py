"""The owner page's one sealed box: Polymarket, the paper tracker and the readers, under the owner key.

    python -m atlas.owner.page          # rebuild the box from what the run already wrote (needs the key)

Built by the Polymarket step of every run (`atlas/polymarket/__main__.py`),
heavy or poll, into ``data/owner/page.enc.json``: ciphertext, or the reason
there is none. The site publishes the ciphertext and the script that opens it
(`atlas/site/assets/owner.js`); the plaintext exists only in the browser
that typed the passphrase.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

from atlas import config
from atlas.owner import crypto
from atlas.util import get_logger

LOG = get_logger(__name__)


def page_path() -> Path:
    return config.paths().root / "data" / "owner" / "page.enc.json"


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def write(box: dict | None, *, reason: str | None = None, where: Path | None = None) -> Path:
    """The box, or the reason there is none. Nothing else is ever written here."""
    where = where or page_path()
    where.parent.mkdir(parents=True, exist_ok=True)
    record = {"built_at": _now(), "box": box, "reason": None if box else (reason or "not built")}
    where.write_text(json.dumps(record) + "\n")
    return where


def read(where: Path | None = None) -> dict | None:
    where = where or page_path()
    if not where.exists():
        return None
    try:
        return json.loads(where.read_text())
    except (OSError, ValueError):
        return None


def check_sealed(box: dict, sections: list[dict]) -> None:
    """Belt and braces: no cell of any table appears in what is published."""
    published = json.dumps(box)
    for s in sections:
        for t in s.get("tables", []):
            for row in t.get("rows", []):
                for cell in row:
                    for part in (cell if isinstance(cell, list) else [cell]):
                        if isinstance(part, str) and len(part) > 4 and part in published:
                            raise RuntimeError("plaintext in the sealed payload")


def sections(polymarket: list[dict] | None = None) -> list[dict]:
    """Every section of the page: Polymarket's, then the paper tracker and the readers, each of which
    builds without the others and never raises."""
    out = list(polymarket or [])
    from atlas.owner import paper

    tracker = paper.build()
    if tracker:
        out.append({**tracker, "tab": tracker.get("tab", "More")})
    from atlas.ops import readers

    audience = readers.build()
    if audience:
        out.append({**audience, "tab": audience.get("tab", "More")})
    return [{k: v for k, v in s.items() if k != "record"} for s in out]


def refresh(*, now: datetime | None = None, heavy: bool = False, polymarket: list[dict] | None = None,
            reason: str | None = None, where: Path | None = None) -> Path:
    """Seal the page. Never raises: without the key it records why the box is empty."""
    passphrase = os.environ.get(crypto.SECRET, "")
    if not passphrase.strip():
        LOG.warning("no %s secret: the owner page is not built", crypto.SECRET)
        return write(None, reason="The owner key is not configured.", where=where)
    try:
        every = sections(polymarket)
        if reason:
            every.insert(0, {"title": "Polymarket", "tab": "Polymarket", "tables": [], "notes": [reason]})
        data = {"built_at": _now(), "heavy": bool(heavy), "sections": every}
        plain = json.dumps(crypto.clean(data), separators=(",", ":"), allow_nan=False).encode("utf-8")
        box = crypto.encrypt(plain, passphrase)
        check_sealed(box, every)
        LOG.info("owner page: %d sections sealed (%d bytes of ciphertext)", len(every), len(box["ct"]))
        return write(box, where=where)
    except Exception as error:  # noqa: BLE001 - the type only: a message could quote a team or a line
        LOG.error("owner page not built: %s", type(error).__name__)
        return write(None, reason=f"This run could not build the owner page ({type(error).__name__}).", where=where)


def main() -> None:
    import argparse

    argparse.ArgumentParser(description="The owner page's sealed box").parse_args()
    print(refresh())


if __name__ == "__main__":
    main()
