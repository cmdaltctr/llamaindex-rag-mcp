"""Per-backend storage summaries (task 2.6, design D5).

``compose.storage_summary`` historically hardcoded Chroma text. The
summary now belongs to the SELECTED store: each backend provides a
one-line description of its mode/location, resolved through the
vector-store registry metadata so no store-name branch appears in the
composition root.
"""

from __future__ import annotations

import importlib
from typing import Any


def chroma_storage_summary(settings: Any) -> str:
    """Return a one-line Chroma storage description for startup logging.

    Includes the deployment mode and, in cloud mode, the tenant and
    database identifiers.  The API key is never included — not even a
    prefix.
    """
    if settings.chroma_mode != "cloud":
        return "chroma mode=local"
    parts = ["chroma mode=cloud"]
    if settings.chroma_cloud_tenant:
        parts.append(f"tenant={settings.chroma_cloud_tenant}")
    if settings.chroma_cloud_database:
        parts.append(f"database={settings.chroma_cloud_database}")
    return " ".join(parts)


def lancedb_storage_summary(settings: Any) -> str:
    """Return a one-line LanceDB storage description for startup logging.

    Names the parent directory so the operator sees where data lives.
    """
    return f"lancedb uri={settings.lancedb_uri}"


def storage_summary(settings: Any) -> str:
    """Return a one-line storage description for the SELECTED backend.

    Dispatches through the vector-store registry's per-entry ``summary``
    metadata so no store-name branch appears in the caller. The API key
    and cloud credentials are never included. *settings* is required —
    the composition root resolves the default (core never reads a
    settings singleton).
    """
    from . import registry as vectordb_registry

    ref = vectordb_registry.describe(settings.vector_store).get("summary")
    if not ref:
        return f"{settings.vector_store} storage configured"
    module_path, attr = ref.split(":", 1)
    summary_fn = getattr(importlib.import_module(module_path), attr)
    return summary_fn(settings)
