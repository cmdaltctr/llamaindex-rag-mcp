"""Dependency-free constants and helpers shared by the daemon modules.

Holds :data:`MAX_FILE_SIZE` and :func:`_sha256_file` so neither
``watcher.py`` nor ``runner.py`` needs to import from the other for these
symbols.  This breaks the watcher↔runner import cycle that previously
made ``runner.py`` un-importable as a first entry point.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# 500 MB — matches the historical limit defined in watcher.py before the
# task 8.6 split.
MAX_FILE_SIZE = 500 * 1024 * 1024


def _sha256_file(path: Path) -> str:
    """Compute the SHA-256 hash of a file's contents.

    Args:
        path: Path to the file.

    Returns:
        Hex-encoded SHA-256 digest.

    Raises:
        FileNotFoundError: If the file does not exist.
        OSError: If the file cannot be read or exceeds
            :data:`MAX_FILE_SIZE`.
    """
    file_stat = path.stat()
    if file_stat.st_size > MAX_FILE_SIZE:
        raise OSError(
            f"File exceeds maximum size of {MAX_FILE_SIZE} bytes (got {file_stat.st_size} bytes)"
        )
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()
