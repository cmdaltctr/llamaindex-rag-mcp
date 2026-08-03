"""Hybrid category taxonomy (ADR-013).

Queries ChromaDB for existing categories across all collections, merges
them with seed categories from the keyword rules, and provides the
category-gathering machinery used by the LLM-based backends (ollama,
llamacpp, openrouter) to prefer reuse of existing labels.  Extracted
from the original ``metadata_extractor.py`` monolith as part of Phase 1.
"""

from __future__ import annotations

import logging
import threading

from ...chroma_utils import iter_collection_metadatas
from ...config import CHROMA_PERSIST_DIR
from ._common import _normalise_category, logger
from .keyword import _load_keyword_rules

# Cached ChromaDB client for category lookups (avoids re-opening the
# database on every file during batch ingestion).
_chroma_client = None
_chroma_client_lock = threading.Lock()


def _get_chroma_client():
    """Return a cached PersistentClient for category taxonomy queries.

    Lazily initialises on first call.  Reuses the same client across
    all ``_gather_existing_categories()`` calls within a process.

    Returns:
        A ``chromadb.PersistentClient`` instance.
    """
    global _chroma_client
    if _chroma_client is None:
        with _chroma_client_lock:
            if _chroma_client is None:
                import chromadb
                _chroma_client = chromadb.PersistentClient(
                    path=CHROMA_PERSIST_DIR
                )
    return _chroma_client


def _get_seed_categories() -> frozenset[str]:
    """Extract unique category names from the current keyword rules.

    These serve as the initial taxonomy when ChromaDB is empty (first run).
    The categories are normalised (lowercase) for consistent comparison.

    Returns:
        Frozen set of normalised seed category names.
    """
    rules = _load_keyword_rules()
    seen: set[str] = set()
    for rule in rules:
        cat = rule.get("category", "").lower()
        if cat:
            seen.add(cat)
    seen.add("uncategorised")
    return frozenset(seen)


def _collect_categories_from_collection(collection) -> set[str]:
    """Extract normalised category names from a single ChromaDB collection.

    Args:
        collection: A ChromaDB collection object.

    Returns:
        Set of normalised category strings (excluding "uncategorised").
    """
    categories: set[str] = set()
    for meta in iter_collection_metadatas(collection):
        if not isinstance(meta, dict):
            continue
        cat = meta.get("category")
        if cat and isinstance(cat, str):
            normalised = _normalise_category(cat)
            if normalised != "uncategorised":
                categories.add(normalised)
    return categories


def _gather_existing_categories() -> list[str]:
    """Query ChromaDB across all collections for unique category values.

    Fetches metadata from every collection in the persistent ChromaDB,
    extracts the ``"category"`` field from each entry, deduplicates,
    and normalises to lowercase.  Returns an empty list on failure
    (no crash — callers fall back to seed categories).

    Returns:
        List of unique, normalised category strings currently stored
        in ChromaDB.  Empty list if ChromaDB is unreachable or has no
        category metadata yet.
    """
    try:
        client = _get_chroma_client()

        categories: set[str] = set()
        for collection in client.list_collections():
            try:
                categories.update(_collect_categories_from_collection(collection))
            except Exception as col_exc:
                logger.debug(
                    "Skipping collection '%s' during category lookup: %s",
                    collection.name if hasattr(collection, "name") else "?",
                    col_exc,
                )
                continue

        result_list = sorted(categories)
        if result_list:
            logger.debug("Found %d existing categories in ChromaDB", len(result_list))
        return result_list

    except Exception as exc:
        logger.warning(
            "Failed to query ChromaDB for existing categories: %s — "
            "classification will use seed categories only",
            exc,
        )
        return []
