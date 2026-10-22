"""Hybrid category taxonomy (ADR-013).

Queries the supplied vector store for existing categories across all
collections, merges them with seed categories from the keyword rules, and
provides the category-gathering machinery used by the LLM-based backends
(ollama, llamacpp, openrouter) to prefer reuse of existing labels.

This module is a leaf: it receives resolved settings and the owning store
from its caller.  It never reads a process-default store or default
settings.  Without a store, classification is seed-only
(``repair-modular-core-boundaries`` design D2).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ._common import _normalise_category, logger
from .keyword import _load_keyword_rules

if TYPE_CHECKING:
    from ..settings import EffectiveSettings
    from ..vectordb.base import VectorStore


def _get_seed_categories(settings: EffectiveSettings) -> frozenset[str]:
    """Extract unique category names from the configured keyword rules.

    These serve as the initial taxonomy when the store is empty (first run)
    or when no store is supplied.  The categories are normalised
    (lowercase) for consistent comparison.

    Args:
        settings: Resolved settings that carry the keyword rules.

    Returns:
        Frozen set of normalised seed category names.
    """
    rules = _load_keyword_rules(settings)
    seen: set[str] = set()
    for rule in rules:
        cat = rule.get("category", "").lower()
        if cat:
            seen.add(cat)
    seen.add("uncategorised")
    return frozenset(seen)


def _collect_categories_from_collection(store: VectorStore, collection_name: str) -> set[str]:
    """Extract normalised category names from a single collection.

    Args:
        store: A :class:`VectorStore` instance.
        collection_name: Name of the collection to scan.

    Returns:
        Set of normalised category strings (excluding "uncategorised").
    """
    categories: set[str] = set()
    for meta in store.iter_metadatas(collection_name):
        if not isinstance(meta, dict):
            continue
        cat = meta.get("category")
        if cat and isinstance(cat, str):
            normalised = _normalise_category(cat)
            if normalised != "uncategorised":
                categories.add(normalised)
    return categories


def _gather_existing_categories(*, store: VectorStore | None = None) -> list[str]:
    """Query the supplied store across all collections for unique category values.

    Fetches metadata from every collection in *store*, extracts the
    ``"category"`` field from each entry, deduplicates, and normalises to
    lowercase.  Returns an empty list on failure (no crash — callers fall
    back to seed categories).

    Args:
        store: The owning :class:`VectorStore`.  ``None`` means standalone
            classification: no lookup, no warning, seed categories only.

    Returns:
        List of unique, normalised category strings currently stored in the
        supplied store.  Empty list if no store is supplied, the store is
        unreachable, or it has no category metadata yet.
    """
    if store is None:
        return []
    try:
        categories: set[str] = set()
        for collection_name in store.list_collections():
            try:
                categories.update(_collect_categories_from_collection(store, collection_name))
            except Exception as col_exc:
                logger.debug(
                    "Skipping collection '%s' during category lookup: %s",
                    collection_name,
                    col_exc,
                )
                continue

        result_list = sorted(categories)
        if result_list:
            logger.debug("Found %d existing categories in vector store", len(result_list))
        return result_list

    except Exception as exc:
        logger.warning(
            "Failed to query vector store for existing categories: %s — "
            "classification will use seed categories only",
            exc,
        )
        return []
