"""Git-commit-keyed cache for the codebase map.

Split out of ``codebase_map.py`` (task 8.5), which exceeded the 500-line
ceiling.

The cache key is the current git commit hash: a map is only reused while
the tree it described is unchanged. When the path is not a git repository
there is no key, so caching is disabled and the map is rebuilt on every
call (AGENTS.md gotcha #9).
"""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

from ..settings import get_default_effective_settings
from .codebase_map import CodebaseMap, FileInventory

logger = logging.getLogger(__name__)


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


def _load_cache(path: str) -> CodebaseMap | None:
    """Load a cached codebase map from disk.

    Cache files are stored at ``<project>/.opencode/codebase-graph.json``.
    The cache is keyed by git commit hash.

    Args:
        path: Project directory path.

    Returns:
        A ``CodebaseMap`` if the cache exists and the commit hash matches,
        otherwise None.
    """
    cache_dir = Path(path) / get_default_effective_settings().codebase_map_cache_dir
    cache_file = cache_dir / "codebase-graph.json"

    if not cache_file.exists():
        return None

    commit_hash = _get_git_commit_hash(path)
    if commit_hash is None:
        logger.info("Caching disabled — not a git repository")
        return None

    try:
        data = json.loads(cache_file.read_text())
        if data.get("commit_hash") == commit_hash:
            logger.debug("Codebase map cache hit (commit %s)", commit_hash[:8])
            return _codebase_map_from_dict(data)
    except (json.JSONDecodeError, KeyError) as exc:
        logger.warning("Cache file corrupt, rebuilding: %s", exc)

    return None


def _save_cache(path: str, codebase_map: CodebaseMap) -> None:
    """Save a codebase map to disk cache.

    Args:
        path: Project directory path.
        codebase_map: The codebase map to cache.
    """
    if codebase_map.commit_hash is None:
        return

    cache_dir = Path(path) / get_default_effective_settings().codebase_map_cache_dir
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / "codebase-graph.json"

    data = _codebase_map_to_dict(codebase_map)
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
