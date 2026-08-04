"""Thread-safety primitives for the ingestion pipeline.

Holds the write lock, embed semaphore, and shutdown flag.  These are
process-local singletons shared across all ingestion submodules.
Extracted from the original ``ingestion.py`` monolith as part of Phase 1.

The collection generation counter formerly lived here; Phase 3 (ADR-034)
moved it into the :class:`VectorStore` instance so the store owns the
write→invalidate contract end-to-end.  Use ``store.get_generation()``
and ``store.bump_generation()`` instead.
"""

from __future__ import annotations

import threading

from ...config import settings

# ── Thread-safety primitives ─────────────────────────────────────────────
write_lock = threading.Lock()
embed_semaphore = threading.BoundedSemaphore(value=settings.embed_concurrency)

# ── Shutdown flag for graceful SIGINT handling ───────────────────────────
shutdown_requested = threading.Event()
