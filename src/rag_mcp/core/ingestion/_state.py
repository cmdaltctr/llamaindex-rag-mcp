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

# ── Thread-safety primitives ─────────────────────────────────────────────
write_lock = threading.Lock()

# The embed limiter is built on first use from the injected concurrency, not
# snapshotted at import (ADR-033 Part 2).  It is cached per concurrency value
# so every caller in a process shares one limiter — the property that made
# the old module-level object correct — while a differently-configured value
# still gets its own.
_embed_semaphores: dict[int, threading.BoundedSemaphore] = {}
_embed_semaphores_lock = threading.Lock()


def get_embed_semaphore(concurrency: int) -> threading.BoundedSemaphore:
    """Return the shared embed limiter for *concurrency*, building it once."""
    with _embed_semaphores_lock:
        sem = _embed_semaphores.get(concurrency)
        if sem is None:
            sem = threading.BoundedSemaphore(value=concurrency)
            _embed_semaphores[concurrency] = sem
        return sem


def reset_embed_semaphores() -> None:
    """Clear the cached limiters (used by tests)."""
    with _embed_semaphores_lock:
        _embed_semaphores.clear()


# ── Shutdown flag for graceful SIGINT handling ───────────────────────────
shutdown_requested = threading.Event()
