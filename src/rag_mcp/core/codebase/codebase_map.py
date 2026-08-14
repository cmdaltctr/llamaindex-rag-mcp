"""Codebase map generation — Magika file-type detection, graph assembly, and formatting.

This module provides the ``get_codebase_map`` functionality: scanning a project
directory for file types, building code and document graphs, detecting
communities and hubs, and formatting a compact text map for agent consumption.

All settings are read from ``config.py``. No cross-imports with ``retrieval.py``.
"""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from ...integrations.magika import _EXCLUDED_DIRS, FileEntry
from ..settings import get_default_effective_settings

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
# ``from rag_mcp.codebase_map import FileEntry`` consumers keep working.


@dataclass
class FileInventory:
    """Aggregated file-type inventory for a project.

    Attributes:
        entries: All file entries.
        type_counts: Mapping of "group/label" to count.
        binary_files: List of binary file paths.
        mismatches: List of (path, suffix_label, magika_label) tuples where
            Magika's detection differs from the file extension.
    """

    entries: list[FileEntry] = field(default_factory=list)
    type_counts: dict[str, int] = field(default_factory=dict)
    binary_files: list[str] = field(default_factory=list)
    mismatches: list[tuple[str, str, str]] = field(default_factory=list)


def _is_magika_available() -> bool:
    """Check if the Magika CLI binary is on $PATH.

    Thin delegation to ``integrations.magika``, which owns the check. Resolve
    the attribute on the module rather than binding it at import so patches
    applied to the owning module take effect here — the previous arrangement
    inverted this and required ``integrations.magika`` to import *back* into
    this module, creating the cycle removed in task 6.4.
    """
    from ...integrations import magika as _magika

    return _magika._is_magika_available()


def scan_with_magika(path: str) -> list[FileEntry]:
    """Scan a directory using the Magika CLI binary.

    Delegates to ``integrations.magika`` (extracted in Phase 5).
    """
    from ...integrations.magika import scan_with_magika as _scan

    return _scan(path)


def scan_with_suffix(path: str) -> list[FileEntry]:
    """Scan a directory using file suffix mapping as fallback.

    Uses ``Path.suffix`` to map files to group/label pairs. Files with
    unknown extensions are classified as ``("unknown", "unknown")``.

    Args:
        path: Directory path to scan.

    Returns:
        List of ``FileEntry`` objects for each detected file.
    """
    project_root = Path(path)
    entries: list[FileEntry] = []

    # Depth-limited traversal (replaces unbounded rglob).
    def _walk(directory: Path, current_depth: int) -> None:
        if current_depth > get_default_effective_settings().codebase_map_max_depth:
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
                suffix = child.suffix.lower()
                try:
                    rel_path = str(child.relative_to(project_root))
                except ValueError:
                    rel_path = str(child)

                if suffix in _BINARY_SUFFIXES:
                    group, label = "binary", suffix.lstrip(".")
                    is_text = False
                elif suffix in _SUFFIX_MAP:
                    group, label = _SUFFIX_MAP[suffix]
                    is_text = True
                else:
                    group, label = "unknown", "unknown"
                    is_text = True

                entries.append(
                    FileEntry(
                        path=rel_path, group=group, label=label, is_text=is_text, suffix=suffix
                    )
                )

    _walk(project_root, 0)

    return entries


def detect_file_types(path: str) -> FileInventory:
    """Detect file types in a project directory.

    Tries Magika CLI first, falls back to suffix-based detection if Magika
    is not installed. Detects mismatches between file extension and Magika's
    content-type detection.

    Args:
        path: Directory path to scan.

    Returns:
        A ``FileInventory`` with all file entries, type counts, binary files,
        and mismatches.
    """
    inventory = FileInventory()

    if _is_magika_available():
        try:
            entries = scan_with_magika(path)
            logger.debug("Magika detected %d files", len(entries))
        except (subprocess.CalledProcessError, FileNotFoundError) as exc:
            logger.warning("Magika scan failed (%s), falling back to suffix detection", exc)
            entries = scan_with_suffix(path)
    else:
        logger.warning("Magika CLI not installed; using suffix-based detection")
        entries = scan_with_suffix(path)

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
    if len(entries) > get_default_effective_settings().codebase_map_max_files:
        logger.warning(
            "File count %d exceeds CODEBASE_MAP_MAX_FILES=%d, truncating",
            len(entries),
            get_default_effective_settings().codebase_map_max_files,
        )
        entries = entries[: get_default_effective_settings().codebase_map_max_files]

    inventory.entries = entries
    return inventory


def format_inventory(inventory: FileInventory) -> str:
    """Format a file inventory as compact text.

    Produces a summary with type counts, glob patterns, binary warnings, and
    mismatch warnings. Targeting ~200 tokens for this section.

    Args:
        inventory: The file inventory to format.

    Returns:
        Compact text representation of the inventory.
    """
    lines: list[str] = ["## File Types"]

    # Sort by count descending.
    sorted_types = sorted(inventory.type_counts.items(), key=lambda x: -x[1])
    for type_key, count in sorted_types:
        # Collect representative glob patterns for this type.
        group, label = type_key.split("/", 1)
        matching = [e for e in inventory.entries if e.group == group and e.label == label]
        suffixes = sorted({e.suffix for e in matching if e.suffix})
        glob_str = ", ".join(f"*{s}" for s in suffixes[:4])
        lines.append(f"- {type_key}: {count} files ({glob_str})")

    if inventory.binary_files:
        lines.append("")
        lines.append("### Binary files")
        for f in inventory.binary_files[:10]:
            # Find the label for this file.
            entry = next((e for e in inventory.entries if e.path == f), None)
            label = entry.label if entry else "unknown"
            lines.append(f"- ⚠ BINARY: {f} ({label})")
        if len(inventory.binary_files) > 10:
            lines.append(f"- ... and {len(inventory.binary_files) - 10} more")

    if inventory.mismatches:
        lines.append("")
        lines.append("### Type mismatches")
        for path, _suffix_label, magika_label in inventory.mismatches[:10]:
            lines.append(f"- ⚠ MISMATCH: {path} → detected as {magika_label}")
        if len(inventory.mismatches) > 10:
            lines.append(f"- ... and {len(inventory.mismatches) - 10} more")

    return "\n".join(lines)


# ── Graph assembly and map formatting (Section 5 tasks) ──────────────────


@dataclass
class CodebaseMap:
    """Complete codebase map combining file inventory, graphs, and communities.

    Attributes:
        inventory: File-type inventory from Magika/suffix detection.
        code_communities: List of code communities from the code graph.
        doc_communities: List of document communities from the document graph.
        cross_links: List of cross-links between code and document communities.
        hubs: List of hub files (high in-degree).
        commit_hash: Git commit hash for cache keying (or None).
    """

    inventory: FileInventory = field(default_factory=FileInventory)
    code_communities: list[dict] = field(default_factory=list)
    doc_communities: list[dict] = field(default_factory=list)
    cross_links: list[dict] = field(default_factory=list)
    hubs: list[dict] = field(default_factory=list)
    commit_hash: str | None = None


def build_codebase_map(path: str) -> CodebaseMap:
    """Build a complete codebase map for a project directory.

    Orchestrates Magika file-type detection, code graph construction,
    document graph construction, cross-link detection, and hub identification.

    Args:
        path: Project directory path.

    Returns:
        A ``CodebaseMap`` with all components assembled.
    """
    # File inventory
    inventory = detect_file_types(path)

    # Resolve settings once at this boundary and thread the instance into
    # the community detectors below — neither detector performs a global
    # settings lookup of its own (settings-dependency-injection contract).
    effective = get_default_effective_settings()

    # Code graph
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
    try:
        from ..documents.doc_graph import CollectionView
        from ..vectordb import get_default_store

        view = CollectionView(get_default_store(), "documents")
        if view.count() == 0:
            logger.debug("Document collection is empty")
        else:
            collection = view
    except Exception as exc:
        logger.warning("Could not access the document collection for the graph: %s", exc)

    if doc_files:
        try:
            from ..documents.doc_graph import build_document_graph, detect_document_communities

            doc_graph = build_document_graph(collection)
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
            from ..documents.doc_graph import compute_cross_links

            dg = build_document_graph(collection)
            links = compute_cross_links(code_graph, dg)
            cross_links = [
                {"code": link.code, "doc": link.doc, "relation": link.relation} for link in links
            ]
        except Exception as exc:
            logger.warning("Cross-link detection failed: %s", exc)

    commit_hash = _get_git_commit_hash(path)
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


def get_codebase_map_text(path: str = ".", refresh: bool = False) -> str:
    """Get a formatted codebase map for a project, with caching.

    This is the main entry point called by the MCP tool handler. It checks
    the cache first (unless ``refresh=True``), builds the map on cache miss,
    and returns the formatted text.

    Args:
        path: Project directory path (default current directory).
        refresh: If True, rebuild the map regardless of cache state.

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

        # Check cache (unless refresh is requested)
        if not refresh:
            cached = _load_cache(str(path_obj))
            if cached is not None:
                return format_codebase_map(cached)

        # Build fresh map
        codebase_map = build_codebase_map(str(path_obj))
        _save_cache(str(path_obj), codebase_map)

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
# Re-exported so existing imports and test monkeypatch targets keep working.

from .cache import (  # noqa: E402
    _get_git_commit_hash,
    _load_cache,
    _save_cache,
)
from .format import format_codebase_map  # noqa: E402
