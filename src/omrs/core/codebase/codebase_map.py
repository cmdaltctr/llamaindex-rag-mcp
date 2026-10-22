"""Codebase map generation — Magika file-type detection, graph assembly, and formatting.

This module provides the ``get_codebase_map`` functionality: scanning a project
directory for file types, building code and document graphs, detecting
communities and hubs, and formatting a compact text map for agent consumption.

Settings and the vector store are supplied by the caller (design D3). The
map entry points take them as keyword arguments and forward them to
detection, community selection, the document graph, and the cache. No
function here reads the default store, and settings are resolved only at
the documented ``get_codebase_map_text`` entry boundary when a legacy
caller omits them. No cross-imports with ``core/retrieval``.
"""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ...integrations.magika import _EXCLUDED_DIRS, FileEntry
from ..settings import EffectiveSettings, resolve_effective_settings
from . import cache as _cache
from .models import CodebaseMap, FileInventory

if TYPE_CHECKING:
    from ..vectordb.base import VectorStore

logger = logging.getLogger(__name__)


# ── Suffix → group/label mapping for fallback detection ──────────────────
_SUFFIX_MAP: dict[str, tuple[str, str]] = {
    ".py": ("code", "python"),
    ".ts": ("code", "typescript"),
    ".tsx": ("code", "tsx"),
    ".js": ("code", "javascript"),
    ".jsx": ("code", "jsx"),
    ".mjs": ("code", "javascript"),
    ".cjs": ("code", "javascript"),
    ".java": ("code", "java"),
    ".c": ("code", "c"),
    ".cpp": ("code", "cpp"),
    ".cc": ("code", "cpp"),
    ".cxx": ("code", "cpp"),
    ".h": ("code", "c"),
    ".hpp": ("code", "cpp"),
    ".cs": ("code", "csharp"),
    ".go": ("code", "go"),
    ".rs": ("code", "rust"),
    ".rb": ("code", "ruby"),
    ".php": ("code", "php"),
    ".swift": ("code", "swift"),
    ".kt": ("code", "kotlin"),
    ".kts": ("code", "kotlin"),
    ".scala": ("code", "scala"),
    ".sh": ("code", "bash"),
    ".bash": ("code", "bash"),
    ".zsh": ("code", "bash"),
    ".sql": ("code", "sql"),
    ".html": ("code", "html"),
    ".htm": ("code", "html"),
    ".css": ("code", "css"),
    ".scss": ("code", "css"),
    ".less": ("code", "css"),
    ".md": ("document", "markdown"),
    ".markdown": ("document", "markdown"),
    ".rst": ("document", "rst"),
    ".txt": ("document", "text"),
    ".pdf": ("document", "pdf"),
    ".docx": ("document", "docx"),
    ".doc": ("document", "doc"),
    ".pptx": ("document", "pptx"),
    ".csv": ("document", "csv"),
    ".json": ("config", "json"),
    ".yaml": ("config", "yaml"),
    ".yml": ("config", "yaml"),
    ".toml": ("config", "toml"),
    ".ini": ("config", "ini"),
    ".cfg": ("config", "ini"),
    ".xml": ("config", "xml"),
    ".env": ("config", "env"),
}

# Extensions considered binary when using suffix fallback.
# Compact grouping is more readable for this data table.
# fmt: off
_BINARY_SUFFIXES: set[str] = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp", ".svg",
    ".tiff", ".tif", ".heic", ".heif",
    ".zip", ".tar", ".gz", ".bz2", ".7z", ".rar", ".xz",
    ".exe", ".dll", ".so", ".dylib", ".bin", ".o", ".a",
    ".mp3", ".mp4", ".avi", ".mov", ".wav", ".flv", ".mkv",
    ".woff", ".woff2", ".ttf", ".otf", ".eot",
    ".pyc", ".pyo", ".class", ".jar",
}
# fmt: on

# FileEntry and _EXCLUDED_DIRS are detection primitives owned by
# integrations.magika (extracted in Phase 5). They are imported at the
# top of this module and re-exported here so existing
# ``from omrs.codebase_map import FileEntry`` consumers keep working.


# FileInventory and CodebaseMap live in ``models.py`` (design D4) and are
# re-exported here, so existing imports from this module keep working.


def _is_magika_available(settings: Any | None = None) -> bool:
    """Check if the Magika CLI binary is on $PATH.

    Thin delegation to ``integrations.magika``, which owns the check. Resolve
    the attribute on the module rather than binding it at import so patches
    applied to the owning module take effect here — the previous arrangement
    inverted this and required ``integrations.magika`` to import *back* into
    this module, creating the cycle removed in task 6.4. *settings* injects
    the binary name; ``None`` keeps the legacy global resolution.
    """
    from ...integrations import magika as _magika

    return _magika._is_magika_available(settings)


def scan_with_magika(path: str, settings: Any | None = None) -> list[FileEntry]:
    """Scan a directory using the Magika CLI binary.

    Delegates to ``integrations.magika`` (extracted in Phase 5).
    """
    from ...integrations.magika import scan_with_magika as _scan

    return _scan(path, settings)


def _classify_suffix(suffix: str) -> tuple[str, str, bool]:
    """Map a lowercase suffix to its ``(group, label, is_text)`` triple."""
    if suffix in _BINARY_SUFFIXES:
        return "binary", suffix.lstrip("."), False
    if suffix in _SUFFIX_MAP:
        return (*_SUFFIX_MAP[suffix], True)
    return "unknown", "unknown", True


def _entry(path: str, suffix: str) -> FileEntry:
    """Build one suffix-classified :class:`FileEntry`."""
    group, label, is_text = _classify_suffix(suffix)
    return FileEntry(path=path, group=group, label=label, is_text=is_text, suffix=suffix)


def scan_with_suffix(path: str, settings: Any | None = None) -> list[FileEntry]:
    """Scan a directory — or a single file — using suffix mapping.

    Unknown extensions classify as ``("unknown", "unknown")``. A single
    file yields one entry keyed ``"."`` (its path relative to itself),
    which is the key ``ingest_path_async`` looks up for direct file
    ingest. The directory walk cannot produce it: ``iterdir()`` on a
    file raises ``NotADirectoryError``, which the walk swallows.
    *settings* injects the depth/count limits; ``None`` keeps the
    legacy global resolution.
    """
    project_root = Path(path)
    entries: list[FileEntry] = []
    effective = resolve_effective_settings(settings)

    if project_root.is_file():
        return [_entry(".", project_root.suffix.lower())]

    # Depth-limited traversal (replaces unbounded rglob).
    def _walk(directory: Path, current_depth: int) -> None:
        if current_depth > effective.codebase_map_max_depth:
            return
        try:
            children = sorted(directory.iterdir())
        except OSError:
            return
        for child in children:
            if child.is_dir():
                if child.name in _EXCLUDED_DIRS:
                    continue
                _walk(child, current_depth + 1)
            elif child.is_file():
                try:
                    rel_path = str(child.relative_to(project_root))
                except ValueError:
                    rel_path = str(child)
                entries.append(_entry(rel_path, child.suffix.lower()))

    _walk(project_root, 0)

    return entries


def detect_file_types(path: str, settings: Any | None = None) -> FileInventory:
    """Detect file types in a project directory.

    Tries Magika CLI first, falls back to suffix-based detection if Magika
    is not installed. Detects mismatches between file extension and Magika's
    content-type detection. *settings* injects the binary name and the
    depth/count limits (the ingestion pipeline passes its resolved
    settings); ``None`` keeps the legacy global resolution.

    Args:
        path: Directory path to scan.

    Returns:
        A ``FileInventory`` with all file entries, type counts, binary files,
        and mismatches.
    """
    inventory = FileInventory()
    effective = resolve_effective_settings(settings)

    if _is_magika_available(settings):
        try:
            entries = scan_with_magika(path, settings)
            logger.debug("Magika detected %d files", len(entries))
        except (subprocess.CalledProcessError, FileNotFoundError, ValueError) as exc:
            logger.warning("Magika scan failed (%s), falling back to suffix detection", exc)
            entries = scan_with_suffix(path, settings)
    else:
        logger.warning("Magika CLI not installed; using suffix-based detection")
        entries = scan_with_suffix(path, settings)

    # Build type counts and detect mismatches.
    for entry in entries:
        type_key = f"{entry.group}/{entry.label}"
        inventory.type_counts[type_key] = inventory.type_counts.get(type_key, 0) + 1

        if not entry.is_text:
            inventory.binary_files.append(entry.path)

        # Detect mismatches: Magika label differs from suffix-based label.
        if entry.suffix in _SUFFIX_MAP:
            _, suffix_label = _SUFFIX_MAP[entry.suffix]
            if entry.label != suffix_label and entry.is_text:
                inventory.mismatches.append((entry.path, suffix_label, entry.label))

    # Enforce file count limit.
    if len(entries) > effective.codebase_map_max_files:
        logger.warning(
            "File count %d exceeds CODEBASE_MAP_MAX_FILES=%d, truncating",
            len(entries),
            effective.codebase_map_max_files,
        )
        entries = entries[: effective.codebase_map_max_files]

    inventory.entries = entries
    return inventory


# ── Graph assembly and map formatting (Section 5 tasks) ──────────────────


def build_codebase_map(
    path: str,
    *,
    settings: EffectiveSettings,
    store: VectorStore | None = None,
) -> CodebaseMap:
    """Build a complete codebase map for a project directory.

    Orchestrates Magika file-type detection, code graph construction,
    document graph construction, cross-link detection, and hub identification.

    Args:
        path: Project directory path.
        settings: Effective settings, forwarded to detection, community
            selection, and both document-graph builds.
        store: Vector store that holds the ``documents`` collection. ``None``
            builds a store-less map: inventory and code information only,
            with empty document communities. No default store is queried.

    Returns:
        A ``CodebaseMap`` with all components assembled.
    """
    effective = settings
    threshold = effective.doc_similarity_threshold
    inventory = detect_file_types(path, settings=effective)

    code_files = [e for e in inventory.entries if e.group == "code" and e.is_text]
    code_communities: list[dict] = []
    hubs: list[dict] = []

    if code_files:
        try:
            from .code_graph import build_code_graph, detect_communities, detect_hubs

            code_graph = build_code_graph(code_files, path)
            communities = detect_communities(code_graph, settings=effective)
            code_communities = [
                {
                    "label": c.label,
                    "files": c.files,
                    "file_count": len(c.files),
                    "edge_count": c.edge_count,
                }
                for c in communities
            ]
            hubs = [{"file": h.file, "in_degree": h.in_degree} for h in detect_hubs(code_graph)]
        except Exception as exc:
            logger.warning("Code graph construction failed: %s", exc)

    # Document graph
    doc_files = [e for e in inventory.entries if e.group == "document" and e.is_text]
    doc_communities: list[dict] = []
    cross_links: list[dict] = []

    # Open the document collection through the VectorStore abstraction.
    # This used to construct a chromadb.PersistentClient directly — the only
    # place in the codebase that bypassed the ABC, contradicting ADR-034 and
    # silently breaking under any non-Chroma store.
    collection = None
    if store is not None:
        try:
            from ..documents.doc_graph import CollectionView

            view = CollectionView(store, "documents")
            if view.count() == 0:
                logger.debug("Document collection is empty")
            else:
                collection = view
        except Exception as exc:
            logger.warning("Could not access the document collection for the graph: %s", exc)

    if doc_files:
        try:
            from ..documents.doc_graph import build_document_graph, detect_document_communities

            doc_graph = build_document_graph(collection, threshold=threshold)
            doc_comms = detect_document_communities(doc_graph, settings=effective)
            doc_communities = [
                {
                    "label": c.label,
                    "chunks": c.chunks,
                    "chunk_count": len(c.chunks),
                    "category": c.category,
                }
                for c in doc_comms
            ]
        except Exception as exc:
            logger.warning("Document graph construction failed: %s", exc)

    # Cross-links (only if both code and doc communities exist)
    if code_communities and doc_communities:
        try:
            from ..documents.doc_graph import build_document_graph, compute_cross_links

            dg = build_document_graph(collection, threshold=threshold)
            links = compute_cross_links(code_graph, dg)
            cross_links = [
                {"code": link.code, "doc": link.doc, "relation": link.relation} for link in links
            ]
        except Exception as exc:
            logger.warning("Cross-link detection failed: %s", exc)

    commit_hash = _cache._get_git_commit_hash(path)
    if commit_hash is None:
        logger.info("Caching disabled — not a git repository")

    return CodebaseMap(
        inventory=inventory,
        code_communities=code_communities,
        doc_communities=doc_communities,
        cross_links=cross_links,
        hubs=hubs,
        commit_hash=commit_hash,
    )


def get_codebase_map_text(
    path: str = ".",
    refresh: bool = False,
    *,
    settings: EffectiveSettings | None = None,
    store: VectorStore | None = None,
) -> str:
    """Get a formatted codebase map for a project, with caching.

    This is the main entry point called by the MCP tool handler. It checks
    the cache first (unless ``refresh=True``), builds the map on cache miss,
    and returns the formatted text.

    This is the documented settings entry boundary: when *settings* is
    omitted, it resolves the composition-root default once through
    ``resolve_effective_settings``. Explicit settings bypass that lookup.
    The store is never resolved here; ``None`` means a store-less map.

    A cached map is reused only when the git commit and the owner context
    (map settings plus the store's durable data version) both match.
    Otherwise the map is rebuilt; see ``cache.py``.

    Args:
        path: Project directory path (default current directory).
        refresh: If True, rebuild the map regardless of cache state.
        settings: Effective settings for detection, communities, document
            thresholds, and the cache directory.
        store: Vector store holding the ``documents`` collection, or
            ``None`` for a store-less map.

    Returns:
        Formatted codebase map text string. On error, returns a JSON string
        with ``{"status": "error", "message": "..."}``.
    """
    try:
        path_obj = Path(path).expanduser().resolve()
        if not path_obj.exists():
            return json.dumps(
                {
                    "status": "error",
                    "message": f"Path not found: {path}",
                }
            )

        if not path_obj.is_dir():
            return json.dumps(
                {
                    "status": "error",
                    "message": f"Path is not a directory: {path}",
                }
            )

        # Path boundary validation — reject paths outside the project root.
        try:
            path_obj.relative_to(Path.cwd())
        except ValueError:
            return json.dumps(
                {
                    "status": "error",
                    "message": f"Path resolves outside the project root: {path}",
                }
            )

        effective = resolve_effective_settings(settings)
        cache_dir = effective.codebase_map_cache_dir
        owner_context = _cache.build_owner_context(effective, store)

        # Check cache (unless refresh is requested)
        if not refresh:
            cached = _cache._load_cache(
                str(path_obj), cache_dir=cache_dir, owner_context=owner_context
            )
            if cached is not None:
                return format_codebase_map(cached)

        # Build fresh map
        codebase_map = build_codebase_map(str(path_obj), settings=effective, store=store)
        _cache._save_cache(
            str(path_obj), codebase_map, cache_dir=cache_dir, owner_context=owner_context
        )

        return format_codebase_map(codebase_map)

    except Exception as exc:
        logger.exception("get_codebase_map failed: %s: %s", type(exc).__name__, exc)
        return json.dumps(
            {
                "status": "error",
                "message": f"{type(exc).__name__}: {exc}",
            }
        )


# ── Re-exports ───────────────────────────────────────────────────────────
# Caching and rendering live in sibling modules after the task 8.5 split.
# Re-exported so existing imports keep working. The functions above call
# the cache through its module, so patches on ``cache.*`` take effect
# (AGENTS.md gotcha 8b: patch targets follow the function).

from .cache import (  # noqa: E402,F401
    _get_git_commit_hash,
    _load_cache,
    _save_cache,
)
from .format import format_codebase_map, format_inventory  # noqa: E402,F401
