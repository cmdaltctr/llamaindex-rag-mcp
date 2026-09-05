"""Safety contract generator for non-destructive profile changes.

When a user requests a profile change on a collection, the system surfaces
a safety contract before mutating.  The contract states honestly:

* Existing chunks are NOT re-chunked or re-embedded.
* Query-time levers (reranker, top_k, hybrid) apply immediately.
* Ingest-time levers (taxonomy mode, chunking fallback) apply only to
  future ingests.
* The ``--force`` re-ingest path exists for genuine re-chunking.

The contract is transport-agnostic.  The CLI prints it and prompts
interactively; the MCP transport returns it as a preview object and
mutates only on re-invocation with ``confirm=True`` (spec M6, design D4).
"""

from __future__ import annotations

from typing import Any

from ..vectordb import get_default_store
from ..vectordb.base import VectorStore
from .resolver import ProfileResolver


def generate_safety_contract(
    collection_name: str,
    new_profile: str,
    store: VectorStore | None = None,
    resolver: ProfileResolver | None = None,
) -> dict[str, Any]:
    """Generate the safety contract for a profile change.

    Args:
        collection_name: The target collection.
        new_profile: The operational profile to switch to
            (``documents`` or ``codebase``).
        store: Optional :class:`VectorStore` (defaults to process-wide).
        resolver: Optional :class:`ProfileResolver` (defaults to a fresh
            instance).

    Returns:
        A dict with keys:
            * ``collection`` — the collection name.
            * ``chunk_count`` — current chunk count (0 if empty/new).
            * ``old_profile`` — the current profile name (or ``None`` if
              untagged).
            * ``new_profile`` — the requested profile name.
            * ``lever_impacts`` — list of per-lever impact statements.
            * ``reingest_pointer`` — instructions for the ``--force`` path.
    """
    resolved_store = store if store is not None else get_default_store()
    resolved_resolver = resolver if resolver is not None else ProfileResolver(store=resolved_store)

    chunk_count = 0
    try:
        chunk_count = resolved_store.count(collection_name)
    except Exception:  # noqa: S110
        pass

    # Read the current profile tag.
    old_profile: str | None = None
    try:
        meta = resolved_store.get_collection_metadata(collection_name)
        if isinstance(meta, dict):
            tag = meta.get("profile")
            if isinstance(tag, str) and tag:
                old_profile = tag
    except Exception:  # noqa: S110
        pass

    # Load both profiles' effective settings for comparison.
    old_effective = None
    if old_profile and old_profile in ("documents", "codebase"):
        try:
            old_effective = resolved_resolver._load_effective(old_profile)
        except Exception:  # noqa: S110
            pass

    try:
        new_effective = resolved_resolver._load_effective(new_profile)
    except Exception:
        new_effective = None

    lever_impacts = _build_lever_impacts(old_effective, new_effective)

    return {
        "collection": collection_name,
        "chunk_count": chunk_count,
        "old_profile": old_profile,
        "new_profile": new_profile,
        "lever_impacts": lever_impacts,
        "reingest_pointer": (
            "Existing chunks are NOT re-chunked. To re-chunk with the new "
            "profile's strategy, delete the collection and re-ingest: "
            "`omrg ingest <path> --collection <name>` after "
            "`delete_documents(collection=<name>)`."
        ),
    }


def _build_lever_impacts(
    old: Any | None,
    new: Any | None,
) -> list[dict[str, str]]:
    """Build per-lever impact statements comparing old and new profiles.

    Args:
        old: The old :class:`EffectiveSettings` (or ``None`` if untagged).
        new: The new :class:`EffectiveSettings` (or ``None`` if load failed).

    Returns:
        List of ``{"lever": ..., "timing": ..., "change": ...}`` dicts.
        Timing is ``"query-time"`` (applies immediately) or ``"ingest-time"``
        (applies to future ingests only).
    """
    if new is None:
        return []

    impacts: list[dict[str, str]] = []

    # Query-time levers — apply immediately after the change.
    impacts.append(
        _lever_impact(
            "reranker_enabled",
            old.reranker_enabled if old else None,
            new.reranker_enabled,
            "query-time",
        )
    )
    impacts.append(
        _lever_impact(
            "top_k",
            old.top_k if old else None,
            new.top_k,
            "query-time",
        )
    )
    impacts.append(
        _lever_impact(
            "hybrid_enabled",
            old.hybrid_enabled if old else None,
            new.hybrid_enabled,
            "query-time",
        )
    )

    # Ingest-time levers — apply only to future ingests.
    impacts.append(
        _lever_impact(
            "chunk_strategy_fallback",
            old.chunk_strategy_fallback if old else None,
            new.chunk_strategy_fallback,
            "ingest-time",
        )
    )
    impacts.append(
        _lever_impact(
            "metadata_taxonomy_mode",
            old.metadata_taxonomy_mode if old else None,
            new.metadata_taxonomy_mode,
            "ingest-time",
        )
    )

    return impacts


def _lever_impact(
    lever: str,
    old_value: Any,
    new_value: Any,
    timing: str,
) -> dict[str, str]:
    """Format a single lever impact statement."""
    if old_value is None:
        change = f"not set → {new_value}"
    elif old_value == new_value:
        change = f"{old_value} (unchanged)"
    else:
        change = f"{old_value} → {new_value}"
    return {
        "lever": lever,
        "timing": timing,
        "change": change,
    }


def apply_profile_change(
    collection_name: str,
    new_profile: str,
    store: VectorStore | None = None,
) -> dict[str, Any]:
    """Apply a profile change — O(1) collection metadata update.

    This is the mutation that ``confirm=True`` triggers.  It updates only
    the collection's metadata dict; no chunks, embeddings, or content are
    touched.

    Args:
        collection_name: The target collection.
        new_profile: The operational profile name (``documents`` or
            ``codebase``).
        store: Optional :class:`VectorStore`.

    Returns:
        A dict confirming the change with ``status``, ``collection``,
        ``profile``, and ``chunk_count_unchanged``.
    """
    resolved_store = store if store is not None else get_default_store()

    if new_profile not in ("documents", "codebase"):
        raise ValueError(
            f"Cannot apply profile {new_profile!r} — only 'documents' and "
            f"'codebase' are operational profiles."
        )

    # Verify the collection exists before updating — do not silently create
    # an empty collection from a typo'd name.
    if not resolved_store.collection_exists(collection_name):
        raise ValueError(
            f"Collection {collection_name!r} does not exist. "
            f"Create it first by ingesting documents into it."
        )

    resolved_store.update_collection_metadata(collection_name, {"profile": new_profile})

    chunk_count = 0
    try:
        chunk_count = resolved_store.count(collection_name)
    except Exception:  # noqa: S110
        pass

    return {
        "status": "ok",
        "collection": collection_name,
        "profile": new_profile,
        "chunk_count_unchanged": chunk_count,
    }
