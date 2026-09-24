"""The owner page: this week's lineups, encrypted before they leave the runner.

    python -m atlas.dfs.owner           # the heavy refresh's DFS step

Step 6 of `docs/MODEL_PLAN_DFS.md`. The site is static and its repository
public, so nothing readable about the owner's lineups may be published or
committed. The heavy refresh:

1. rebuilds the DFS tables the run needs (they are not cached between runs):
   the player and defense games, the game environment, the week's news;
2. projects the upcoming Main slate and builds the owner's lineups
   (`atlas/dfs/slate.py`), written under ``data/dfs/`` - never committed;
3. encrypts them with a key derived from the ``ATLAS_OWNER_KEY`` secret
   (PBKDF2-SHA256, 600,000 iterations, a fresh salt; AES-256-GCM, a fresh
   nonce) and writes only the ciphertext to ``data/dfs/owner.enc.json``;
4. the site build puts that ciphertext in ``dfs/owner.html``, where the
   browser derives the same key from the typed passphrase and decrypts it
   locally (WebCrypto). The passphrase never leaves the device.

The step never fails the refresh. Without the secret it builds nothing; on
any error it records a short reason (no player, no number) that the page
shows in place of the lineups.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from atlas import config
from atlas.util import get_logger

LOG = get_logger(__name__)

SECRET = "ATLAS_OWNER_KEY"
ITERATIONS = 600_000                 # OWASP's 2023 figure for PBKDF2-SHA256
VERSION = 1


def enc_path() -> Path:
    return config.paths().root / "data" / "dfs" / "owner.enc.json"


def _key(passphrase: str, salt: bytes, iterations: int = ITERATIONS) -> bytes:
    # Surrounding whitespace is dropped on both sides: a secret pasted with a
    # trailing newline must still open on the iPad.
    return hashlib.pbkdf2_hmac("sha256", passphrase.strip().encode("utf-8"), salt, iterations, dklen=32)


def encrypt(plaintext: bytes, passphrase: str, *, iterations: int = ITERATIONS) -> dict:
    """AES-256-GCM under a PBKDF2 key; WebCrypto's layout (tag after the ciphertext)."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    if not passphrase or not passphrase.strip():
        raise ValueError("empty passphrase")
    salt, iv = secrets.token_bytes(16), secrets.token_bytes(12)
    ct = AESGCM(_key(passphrase, salt, iterations)).encrypt(iv, plaintext, None)
    b64 = lambda b: base64.b64encode(b).decode("ascii")  # noqa: E731
    return {"v": VERSION, "kdf": "PBKDF2-SHA256", "iterations": iterations, "cipher": "AES-256-GCM",
            "salt": b64(salt), "iv": b64(iv), "ct": b64(ct)}


def decrypt(box: dict, passphrase: str) -> bytes:
    """The inverse, for tests and for checking a build."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    raw = lambda k: base64.b64decode(box[k])  # noqa: E731
    return AESGCM(_key(passphrase, raw("salt"), int(box["iterations"]))).decrypt(raw("iv"), raw("ct"), None)


def payload(out: Path, *, label: str = "Main", built_at: str | None = None) -> dict:
    """What the owner sees: the lineups, DraftKings' upload file, and the pool's projections."""
    lineups = pd.read_csv(out / "lineups.csv")
    pool = pd.read_csv(out / "projections.csv")
    starts = pd.to_datetime(pool["game_start"], utc=True, errors="coerce") if "game_start" in pool else None
    keep = ["name", "position", "team", "opponent", "salary", "status", "projection", "low", "high", "p_play"]
    pool = pool[[c for c in keep if c in pool]].copy()
    for c in ("projection", "low", "high"):
        pool[c] = pool[c].round(1)
    pool["p_play"] = pool["p_play"].round(2)
    return {
        "slate": label, "draft_group_id": int(out.name), "built_at": built_at or _now(),
        "first_kickoff": starts.min().isoformat() if starts is not None and starts.notna().any() else None,
        "lineups": [
            {"slots": g[["slot", "name", "team", "salary", "projection", "low", "high"]].round(1)
                .to_dict(orient="records"),
             "salary": int(g["salary"].sum()), "projection": round(float(g["projection"].sum()), 1)}
            for _, g in lineups.groupby("lineup", sort=True)
        ],
        "upload_csv": (out / "lineups_upload.csv").read_text(),
        "players": json.loads(pool.to_json(orient="records")),
    }


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write(box: dict | None, *, reason: str | None = None, path: Path | None = None) -> Path:
    """The ciphertext, or the reason there is none. Nothing else is ever written here."""
    path = path or enc_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {"built_at": _now(), "box": box, "reason": None if box else (reason or "not built")}
    path.write_text(json.dumps(record) + "\n")
    return path


def read(path: Path | None = None) -> dict | None:
    path = path or enc_path()
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def refresh(*, label: str = "Main", rebuild: bool = True) -> Path:
    """The heavy refresh's DFS step: the slate for everyone, the lineups for the owner. Never raises.

    The public projections (step 7) are built and recorded whether or not
    the owner key is set; only the sealed lineups need it."""
    passphrase = os.environ.get(SECRET, "")
    try:
        if rebuild:
            from atlas.dfs import context, environment, players

            _archive()
            players.build()
            environment.build()
            context.build()
        from atlas.dfs import slate

        out = slate.run(label)
    except Exception as error:  # noqa: BLE001 - the site must still build
        # The type only: a message could quote a player or a number.
        LOG.error("DFS slate not built: %s", type(error).__name__)
        reason = ("No upcoming slate is posted yet." if type(error).__name__ == "NoSlate"
                  else f"This refresh could not build the lineups ({type(error).__name__}).")
        return write(None, reason=reason)
    if not passphrase.strip():
        LOG.warning("no %s secret: the owner page is not built", SECRET)
        return write(None, reason="The owner key is not configured.")
    try:
        plain = json.dumps(payload(out, label=label), separators=(",", ":")).encode("utf-8")
        box = encrypt(plain, passphrase)
        _check_sealed(box, plain)
        LOG.info("owner page: %s slate encrypted (%d bytes of ciphertext)", label, len(box["ct"]))
        return write(box)
    except Exception as error:  # noqa: BLE001
        LOG.error("owner page not built: %s", type(error).__name__)
        return write(None, reason=f"This refresh could not build the lineups ({type(error).__name__}).")


def _archive() -> None:
    """RotoGuru's 2014-2021 archive, once per cache: it gives the player
    tables DraftKings' own points for those seasons, as the model was tested.
    Without it the tables fall back to Atlas's reconciled scoring (99.3% the
    same), so a failure here is logged and passed over."""
    from atlas.sources import rotoguru

    raw = config.paths().raw
    for season in rotoguru.SEASONS:
        try:
            rotoguru.fetch_season(raw, season)
        except Exception as error:  # noqa: BLE001 - an enrichment, not a requirement
            LOG.warning("rotoguru %s not fetched: %s", season, type(error).__name__)


def _check_sealed(box: dict, plain: bytes) -> None:
    """Belt and braces: no stretch of the plaintext appears in what is published."""
    published = json.dumps(box)
    data = json.loads(plain)
    names = {p["name"] for p in data["players"] if isinstance(p.get("name"), str) and len(p["name"]) > 4}
    leaked = [n for n in names if n in published]
    if leaked:
        raise RuntimeError("plaintext in the sealed payload")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build and encrypt the owner's DFS page payload")
    parser.add_argument("--label", default="Main")
    parser.add_argument("--no-rebuild", action="store_true", help="use the DFS tables already staged")
    args = parser.parse_args()
    refresh(label=args.label, rebuild=not args.no_rebuild)


if __name__ == "__main__":
    main()
