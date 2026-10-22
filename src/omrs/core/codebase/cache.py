"""Git-commit-keyed cache for the codebase map.

Split out of ``codebase_map.py`` (task 8.5), which exceeded the 500-line
ceiling.

The cache key is the current git commit hash: a map is only reused while
the tree it described is unchanged. When the path is not a git repository
there is no key, so caching is disabled and the map is rebuilt on every
call (AGENTS.md gotcha #9).

Owner context (design D5): a commit match alone is not enough. The document
communities depend on the supplied vector store and the map settings, so
two callers that share one cache directory could otherwise return each
other's map. Each record therefore carries an ``owner_context`` field next
to the unchanged map payload. A record is reused only when its commit AND
its owner context match the caller's. A missing, different, or unprovable
context is a safe miss: the map is rebuilt and the old file stays until a
successful build replaces it. Callers supply the cache directory and the
owner context explicitly; this module reads no default settings or store.
"""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Any

from .models import CodebaseMap, FileInventory

logger = logging.getLogger(__name__)

# Bump when the owner-context shape changes; older records then miss safely.
OWNER_CONTEXT_VERSION = 1

# The map reads document communities from this collection only.
DOCUMENT_COLLECTION = "documents"

# Settings fields that change the map output. The cache directory is not
# listed: it selects where the record lives, not what it contains.
_MAP_SETTING_FIELDS = (
    "magika_binary",
    "doc_similarity_threshold",
    "codebase_map_max_files",
    "codebase_map_max_depth",
    "community_algorithm",
    "community_seed",
)


def _get_git_commit_hash(path: str) -> str | None:
    """Get the current git commit hash for a project path.

    Args:
        path: Project directory path.

    Returns:
        The commit hash string, or None if not a git repository.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],  # noqa: S607
            capture_output=True,
            text=True,
            cwd=path,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except OSError:
        pass
    return None


def build_owner_context(settings: Any, store: Any | None) -> dict | None:
    """Build the owner context that a cache record must match.

    The context names the map-relevant settings values and the supplied
    store's durable identity for the documents collection. The store part
    uses ``VectorStore.get_data_version``: a tagged token that combines a
    persistent dataset identity with the data version, so it differs
    between stores and changes when documents change. A process-local
    identity (``cache_identity``) is not used because it proves nothing
    across processes.

    Args:
        settings: The supplied effective settings.
        store: The supplied vector store, or ``None`` for a store-less map.

    Returns:
        A JSON-compatible dict, or ``None`` when the store cannot give a
        durable identity. ``None`` disables persistent reuse for this call.
    """
    context: dict[str, Any] = {
        "version": OWNER_CONTEXT_VERSION,
        "settings": {name: getattr(settings, name) for name in _MAP_SETTING_FIELDS},
        "store": None,
    }
    if store is None:
        return context
    try:
        data_version = store.get_data_version(DOCUMENT_COLLECTION)
    except Exception as exc:
        logger.debug("Store data version unavailable (%s); cache reuse disabled", exc)
        return None
    if data_version is None:
        logger.debug("Store has no durable data version; cache reuse disabled")
        return None
    context["store"] = {
        "backend": f"{type(store).__module__}.{type(store).__qualname__}",
        "collection": DOCUMENT_COLLECTION,
        "data_version": str(data_version),
    }
    return context


def _cache_file(path: str, cache_dir: str) -> Path:
    """Return the cache file for *path* under the supplied *cache_dir*."""
    return Path(path) / cache_dir / "codebase-graph.json"


def _load_cache(
    path: str,
    *,
    cache_dir: str,
    owner_context: dict | None,
) -> CodebaseMap | None:
    """Load a cached codebase map from disk.

    Cache files are stored at ``<project>/<cache_dir>/codebase-graph.json``.
    A record is reused only when its git commit hash and its owner context
    both match. Any other record is a miss and is left on disk.

    Args:
        path: Project directory path.
        cache_dir: Cache directory, relative to *path*, from the supplied
            settings.
        owner_context: Context from :func:`build_owner_context`. ``None``
            means the context cannot be proven, so the cache is not read.

    Returns:
        A ``CodebaseMap`` on a proven hit, otherwise None.
    """
    cache_file = _cache_file(path, cache_dir)

    if not cache_file.exists():
        return None

    commit_hash = _get_git_commit_hash(path)
    if commit_hash is None:
        logger.info("Caching disabled — not a git repository")
        return None

    if owner_context is None:
        logger.debug("Codebase map cache skipped — owner context not provable")
        return None

    try:
        data = json.loads(cache_file.read_text())
        if data.get("commit_hash") != commit_hash:
            return None
        if data.get("owner_context") != owner_context:
            logger.debug("Codebase map cache miss — owner context differs or is absent")
            return None
        logger.debug("Codebase map cache hit (commit %s)", commit_hash[:8])
        return _codebase_map_from_dict(data)
    except (json.JSONDecodeError, KeyError) as exc:
        logger.warning("Cache file corrupt, rebuilding: %s", exc)

    return None


def _save_cache(
    path: str,
    codebase_map: CodebaseMap,
    *,
    cache_dir: str,
    owner_context: dict | None,
) -> None:
    """Save a codebase map to disk cache.

    Nothing is written for a non-git project or an unprovable owner
    context. An existing record for another owner is then kept.

    Args:
        path: Project directory path.
        codebase_map: The codebase map to cache.
        cache_dir: Cache directory, relative to *path*, from the supplied
            settings.
        owner_context: Context from :func:`build_owner_context`, stored in
            the record envelope beside the unchanged map payload.
    """
    if codebase_map.commit_hash is None or owner_context is None:
        return

    cache_file = _cache_file(path, cache_dir)
    cache_file.parent.mkdir(parents=True, exist_ok=True)

    data = _codebase_map_to_dict(codebase_map)
    data["owner_context"] = owner_context
    cache_file.write_text(json.dumps(data, indent=2))
    logger.debug("Codebase map cached (commit %s)", codebase_map.commit_hash[:8])


def _codebase_map_to_dict(m: CodebaseMap) -> dict:
    """Serialise a CodebaseMap to a JSON-compatible dict."""
    return {
        "commit_hash": m.commit_hash,
        "inventory": {
            "type_counts": m.inventory.type_counts,
            "binary_files": m.inventory.binary_files,
            "mismatches": m.inventory.mismatches,
        },
        "code_communities": m.code_communities,
        "doc_communities": m.doc_communities,
        "cross_links": m.cross_links,
        "hubs": m.hubs,
    }


def _codebase_map_from_dict(data: dict) -> CodebaseMap:
    """Deserialise a CodebaseMap from a dict."""
    inv_data = data.get("inventory", {})
    return CodebaseMap(
        inventory=FileInventory(
            type_counts=inv_data.get("type_counts", {}),
            binary_files=inv_data.get("binary_files", []),
            mismatches=[tuple(m) for m in inv_data.get("mismatches", [])],
        ),
        code_communities=data.get("code_communities", []),
        doc_communities=data.get("doc_communities", []),
        cross_links=data.get("cross_links", []),
        hubs=data.get("hubs", []),
        commit_hash=data.get("commit_hash"),
    )
