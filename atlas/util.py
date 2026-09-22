"""Shared helpers: logging, HTTP with retries, and parquet IO."""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any

import pandas as pd
import requests

LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s | %(message)s"


def get_logger(name: str) -> logging.Logger:
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=os.environ.get("ATLAS_LOG_LEVEL", "INFO"),
            format=LOG_FORMAT,
            datefmt="%H:%M:%S",
        )
    return logging.getLogger(name)


LOG = get_logger(__name__)

USER_AGENT = "atlas-research/0.1 (+https://github.com/EdgeCash/Atlas)"

#: Statuses worth retrying. Everything else is an answer, not a hiccup.
RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


def session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT})
    return s


def http_get(
    url: str,
    *,
    sess: requests.Session | None = None,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 60,
    retries: int = 4,
    backoff: float = 2.0,
) -> requests.Response:
    """GET with exponential backoff. Raises on final failure."""
    sess = sess or session()
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            resp = sess.get(url, params=params, headers=headers, timeout=timeout)
            if resp.status_code in RETRYABLE_STATUS:
                raise requests.HTTPError(f"{resp.status_code} for {url}", response=resp)
            resp.raise_for_status()
            return resp
        except requests.HTTPError as exc:
            # A 401/403/404 is a settled answer, not a hiccup. Retrying it
            # wastes time and buries the real reason in the log.
            status = getattr(exc.response, "status_code", None)
            if status is not None and status not in RETRYABLE_STATUS:
                raise
            last = exc
            if attempt == retries:
                break
            _sleep_backoff(url, attempt, backoff, exc)
        except Exception as exc:  # noqa: BLE001 - transport errors are retried
            last = exc
            if attempt == retries:
                break
            _sleep_backoff(url, attempt, backoff, exc)
    raise RuntimeError(f"GET failed after {retries + 1} attempts: {url}") from last


def _sleep_backoff(url: str, attempt: int, backoff: float, exc: Exception) -> None:
    sleep = backoff**attempt
    LOG.warning("GET failed (%s), retry %d in %.0fs: %s", url, attempt + 1, sleep, exc)
    time.sleep(sleep)


def download(url: str, dest: Path, *, retries: int = 4, backoff: float = 2.0) -> Path:
    """Stream a (potentially large) file to disk, skipping if already present."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        LOG.debug("cached %s", dest.name)
        return dest
    tmp = dest.with_suffix(dest.suffix + ".part")
    sess = session()
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            with sess.get(url, stream=True, timeout=180) as r:
                r.raise_for_status()
                with open(tmp, "wb") as fh:
                    for chunk in r.iter_content(chunk_size=1 << 20):
                        fh.write(chunk)
            tmp.replace(dest)
            return dest
        except Exception as exc:  # noqa: BLE001 - retried below
            last = exc
            tmp.unlink(missing_ok=True)
            if attempt == retries:
                break
            time.sleep(backoff**attempt)
    raise RuntimeError(f"download failed: {url}") from last


def write_parquet(df: pd.DataFrame, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    LOG.info("wrote %s (%d rows, %d cols)", path.name, len(df), df.shape[1])
    return path


def read_parquet(path: Path, **kwargs: Any) -> pd.DataFrame:
    return pd.read_parquet(path, **kwargs)
