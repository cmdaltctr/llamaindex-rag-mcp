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

from collections.abc import Mapping
from typing import Any

from ..pipelines.levers import apply_levers
from ..vectordb import get_default_store
from ..vectordb.base import VectorStore
from .catalogue import SLOT_CONTRACTS, ProfileCatalogue, no_workspace_message
from .resolver import OPERATIONAL_PROFILES, ProfileResolver

#: Query levers that the Search graph's prepare node can set. A test checks this
#: against the ``retrieve.prepare_query`` descriptor.
_PREPARE_QUERY_LEVERS: tuple[tuple[str, str], ...] = (
    ("top_k", "retrieval.top_k"),
    ("rerank", "retrieval.rerank_enabled"),
)

_USER_PROFILE_NOTES: tuple[str, ...] = (
    "Search and answers follow the profile's Search and Answer pipelines at once.",
    "Sources indexed by a different Ingest graph are processed again on their next "
    "ingestion. Nothing is re-ingested now.",
)


def _base_profile(profile: str | None, catalogue: ProfileCatalogue | None) -> str | None:
    """Return the built-in profile whose settings ``profile`` uses, if known."""
    if profile is None:
        return None
    if profile in OPERATIONAL_PROFILES:
        return profile
    record = catalogue.get_profile(profile) if catalogue is not None else None
    return str(record["base_profile"]) if record else None


def _effective(
    profile: str | None, catalogue: ProfileCatalogue | None, resolver: ProfileResolver
) -> Any | None:
    """Return the settings a collection on ``profile`` searches with, if known.

    A user profile starts from its base profile. Its saved Search graph then
    decides what runs, so the graph is laid over the base settings.
    """
    base = _base_profile(profile, catalogue)
    if base is None:
        return None
    try:
        effective = resolver._load_effective(base)
    except Exception:
        return None
    if profile in OPERATIONAL_PROFILES or catalogue is None:
        return effective
    return _apply_search_graph(effective, catalogue.slot_document(str(profile), "search"))


def _apply_search_graph(effective: Any, document: Mapping[str, Any] | None) -> Any:
    """Lay a Search graph's levers and shape over ``effective``.

    Graph-wide overrides and prepare-node values set top_k and the reranker
    lever. An enabled sparse node turns hybrid retrieval on. The reranker runs
    only when its lever is on and an enabled rerank node is present.
    """
    if not document or not document.get("nodes"):
        return effective
    nodes = [node for node in document["nodes"] if node.get("enabled", True)]
    values: dict[str, Any] = dict(document.get("overrides") or {})
    for node in nodes:
        if node.get("operation") == "retrieve.prepare_query":
            params = node.get("params") or {}
            values.update({lever: params[p] for p, lever in _PREPARE_QUERY_LEVERS if p in params})
    settings = apply_levers(effective, values)
    operations = {node.get("operation") for node in nodes}
    return apply_levers(
        settings,
        {
            "retrieval.hybrid_enabled": "retrieve.sparse" in operations,
            "retrieval.rerank_enabled": settings.reranker_enabled and "select.rerank" in operations,
        },
    )


def _pipeline_summary(profile: str, catalogue: ProfileCatalogue) -> list[dict[str, Any]]:
    """Name a user profile's three pipelines with their current revision numbers."""
    summary: list[dict[str, Any]] = []
    for slot in SLOT_CONTRACTS:
        revision = catalogue.slot_revision(profile, slot.slot)
        number = revision["revision_number"] if revision else None
        summary.append({"slot": slot.slot, "title": slot.title, "revision_number": number})
    return summary


def _check_user_profile(
    collection_name: str, profile_id: str, catalogue: ProfileCatalogue | None
) -> None:
    """Refuse a profile id that a collection cannot use.

    Raises:
        ValueError: If the id is ``hybrid``, there is no catalogue, the id is
            unknown or deleted, or a pipeline of the profile has no saved graph.
    """
    if profile_id == "hybrid":
        raise ValueError(
            "Cannot apply profile 'hybrid': it is a mode selector, and only 'documents' and "
            "'codebase' are operational profiles. Use one of those or a workspace profile."
        )
    if catalogue is None:
        raise ValueError(no_workspace_message(collection_name, profile_id))
    record = catalogue.get_profile(profile_id)
    if record is None:
        raise ValueError(
            f"{profile_id!r} is not a profile. Use 'documents', 'codebase' or a profile "
            f"from the workspace."
        )
    if record.get("archived_at"):
        raise ValueError(f"The profile {profile_id!r} was deleted. Choose another profile.")
    missing = [
        s.title for s in SLOT_CONTRACTS if catalogue.slot_revision(profile_id, s.slot) is None
    ]
    if missing:
        raise ValueError(
            f"The profile {profile_id!r} is not ready: the {', '.join(missing)} "
            f"pipeline has no saved graph."
        )


def generate_safety_contract(
    collection_name: str,
    new_profile: str,
    store: VectorStore | None = None,
    resolver: ProfileResolver | None = None,
    catalogue: ProfileCatalogue | None = None,
) -> dict[str, Any]:
    """Generate the safety contract for a profile change.

    Args:
        collection_name: The target collection.
        new_profile: The profile to switch to: ``documents``, ``codebase`` or
            the id of a user profile.
        store: Optional :class:`VectorStore` (defaults to process-wide).
        resolver: Optional :class:`ProfileResolver` (defaults to a fresh
            instance).
        catalogue: Where user profiles are read. Defaults to the resolver's
            catalogue.

    Returns:
        A dict with keys:
            * ``collection`` — the collection name.
            * ``chunk_count`` — current chunk count (0 if empty/new).
            * ``old_profile`` — the current profile name (or ``None`` if
              untagged).
            * ``new_profile`` — the requested profile name.
            * ``lever_impacts`` — list of per-lever impact statements.
            * ``reingest_pointer`` — instructions for the ``--force`` path.
            * ``pipelines`` and ``notes`` — only for a user profile: the three
              pipelines with their current revision numbers, and what changes
              at once and at the next ingestion.
    """
    resolved_store = store if store is not None else get_default_store()
    resolved_resolver = resolver if resolver is not None else ProfileResolver(store=resolved_store)
    resolved_catalogue = catalogue if catalogue is not None else resolved_resolver.catalogue

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
    old_effective = _effective(old_profile, resolved_catalogue, resolved_resolver)
    new_effective = _effective(new_profile, resolved_catalogue, resolved_resolver)

    lever_impacts = _build_lever_impacts(old_effective, new_effective)

    contract: dict[str, Any] = {
        "collection": collection_name,
        "chunk_count": chunk_count,
        "old_profile": old_profile,
        "new_profile": new_profile,
        "lever_impacts": lever_impacts,
        "reingest_pointer": (
            "Existing chunks are NOT re-chunked. To re-chunk with the new "
            "profile's strategy, delete the collection and re-ingest: "
            "`omrs ingest <path> --collection <name>` after "
            "`delete_documents(collection=<name>)`."
        ),
    }
    if new_profile not in OPERATIONAL_PROFILES and resolved_catalogue is not None:
        contract["pipelines"] = _pipeline_summary(new_profile, resolved_catalogue)
        contract["notes"] = list(_USER_PROFILE_NOTES)
    return contract


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
    catalogue: ProfileCatalogue | None = None,
) -> dict[str, Any]:
    """Apply a profile change — O(1) collection metadata update.

    This is the mutation that ``confirm=True`` triggers.  It updates only
    the collection's metadata dict; no chunks, embeddings, or content are
    touched.

    Args:
        collection_name: The target collection.
        new_profile: ``documents``, ``codebase`` or the id of a ready user
            profile in the catalogue.
        store: Optional :class:`VectorStore`.
        catalogue: Where user profiles are read.

    Returns:
        A dict confirming the change with ``status``, ``collection``,
        ``profile``, and ``chunk_count_unchanged``.
    """
    resolved_store = store if store is not None else get_default_store()

    if new_profile not in OPERATIONAL_PROFILES:
        _check_user_profile(collection_name, new_profile, catalogue)

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
