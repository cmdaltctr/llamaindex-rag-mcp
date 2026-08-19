"""Source-content hashing shared by ingestion and daemon change detection.

The ingestion pipeline and filesystem watcher must agree on the exact content
identity. Keeping the helper in ``core.ingestion`` avoids two subtly different
hash implementations and preserves the existing 500 MiB read ceiling.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

MAX_FILE_SIZE = 500 * 1024 * 1024


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of *path* while enforcing the file ceiling.

    Args:
        path: File whose bytes define the source-content identity.

    Returns:
        Hex-encoded SHA-256 digest.

    Raises:
        FileNotFoundError: If the file does not exist.
        OSError: If the file cannot be read or grows beyond
            :data:`MAX_FILE_SIZE` while being hashed.
    """
    hasher = hashlib.sha256()
    total_bytes = 0
    with path.open("rb") as handle:
        file_size = os.fstat(handle.fileno()).st_size
        if file_size > MAX_FILE_SIZE:
            raise OSError(
                f"File exceeds maximum size of {MAX_FILE_SIZE} bytes "
                f"(got {file_size} bytes)"
            )
        for chunk in iter(lambda: handle.read(8192), b""):
            total_bytes += len(chunk)
            if total_bytes > MAX_FILE_SIZE:
                raise OSError(
                    f"File exceeds maximum size of {MAX_FILE_SIZE} bytes during read "
                    f"(read {total_bytes} bytes)"
                )
            hasher.update(chunk)
    return hasher.hexdigest()
