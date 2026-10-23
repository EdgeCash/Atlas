"""The owner key: what seals the owner page and the owner's records, and what opens them.

AES-256-GCM under a PBKDF2-SHA256 key, in WebCrypto's layout (the tag after
the ciphertext), so the browser can open with the same passphrase what this
sealed (`atlas/site/assets/owner.js`). The passphrase is the
``ATLAS_OWNER_KEY`` secret; nothing readable is ever written anywhere that
is kept.
"""

from __future__ import annotations

import base64
import hashlib
import secrets

SECRET = "ATLAS_OWNER_KEY"
ITERATIONS = 600_000                 # OWASP's 2023 figure for PBKDF2-SHA256
VERSION = 1


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


def clean(value):
    """Strict JSON for the browser: a missing number is null, never NaN."""
    if isinstance(value, float) and value != value:
        return None
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items()}
    if isinstance(value, list):
        return [clean(v) for v in value]
    return value
