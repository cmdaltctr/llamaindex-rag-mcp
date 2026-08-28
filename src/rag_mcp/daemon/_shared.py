"""Shared daemon aliases for canonical source-content hashing.

The hash implementation now lives in ``core.ingestion.hashing`` so daemon
change detection and ingestion persist exactly the same byte identity. The
historical private name remains exported for watcher/runner compatibility.
"""

from __future__ import annotations

from ..core.ingestion.hashing import sha256_file

_sha256_file = sha256_file
