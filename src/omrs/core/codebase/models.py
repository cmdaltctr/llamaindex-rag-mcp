"""Shared data models for the codebase map and its cache.

``FileInventory`` and ``CodebaseMap`` live here so that ``cache.py`` and
``codebase_map.py`` can both import them without importing each other.
Before this module existed, importing ``cache`` first in a fresh process
failed with a circular import. ``codebase_map`` re-exports both classes,
so existing ``from omrs.core.codebase.codebase_map import CodebaseMap``
imports keep working.

This module holds data only. It has no settings, store, or I/O access.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ...integrations.magika import FileEntry


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
