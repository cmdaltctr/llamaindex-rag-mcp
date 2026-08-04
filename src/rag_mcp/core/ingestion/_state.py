"""Thread-safety primitives and shared state for the ingestion pipeline.

Holds the write lock, embed semaphore, collection generation counter,
and shutdown flag.  These are process-local singletons shared across
all ingestion submodules.  Extracted from the original ``ingestion.py``
monolith as part of Phase 1.
"""

from __future__ import annotations

import threading

from ...config import settings

# ── Thread-safety primitives ─────────────────────────────────────────────
write_lock = threading.Lock()
embed_semaphore = threading.BoundedSemaphore(value=settings.embed_concurrency)
collection_generations: dict[str, int] = {}

# ── Shutdown flag for graceful SIGINT handling ───────────────────────────
shutdown_requested = threading.Event()


def get_collection_generation(collection_name: str = "documents") -> int:
    """Return the process-local generation counter for a collection."""
    return collection_generations.get(collection_name, 0)


def bump_collection_generation(collection_name: str = "documents") -> None:
    """Advance BM25 cache generation; callers hold ``write_lock``."""
    collection_generations[collection_name] = (
        collection_generations.get(collection_name, 0) + 1
    )
