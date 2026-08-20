"""Shared helpers: logging setup and lightweight run-metadata utilities."""
from __future__ import annotations

import hashlib
import json
import logging
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


def get_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """Return a module logger with a single stdout handler (idempotent)."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)s | %(message)s", "%Y-%m-%d %H:%M:%S")
        )
        logger.addHandler(handler)
        logger.setLevel(level)
        logger.propagate = False
    return logger


@contextmanager
def timed_step(logger: logging.Logger, description: str) -> Iterator[None]:
    """Log start/end/duration and re-raise failures with context."""
    start = time.perf_counter()
    logger.info("START %s", description)
    try:
        yield
    except Exception:
        logger.exception("FAILED %s", description)
        raise
    else:
        elapsed = time.perf_counter() - start
        logger.info("DONE  %s (%.2fs)", description, elapsed)


def file_sha256(path: Path, chunk_size: int = 1 << 20) -> str:
    """Content hash used for simple data lineage tracking in run manifests."""
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()[:16]


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)
