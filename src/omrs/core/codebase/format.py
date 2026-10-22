"""Rendering of a :class:`CodebaseMap` into agent-readable text.

Split out of ``codebase_map.py`` (task 8.5). Presentation only — no graph
construction or IO happens here.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .codebase_map import CodebaseMap, FileInventory

logger = logging.getLogger(__name__)


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


def format_codebase_map(codebase_map: CodebaseMap) -> str:
    """Format a complete codebase map as compact text (≤800 tokens).

    Produces sections for File Types, Code Communities, Document Communities,
    Cross-links, and Architectural Hubs. Communities with more than 4 files
    are truncated to show the top 4 plus "... and N more".

    Args:
        codebase_map: The codebase map to format.

    Returns:
        Compact text representation targeting 500–800 tokens.
    """
    sections: list[str] = []

    # File Types section
    sections.append(format_inventory(codebase_map.inventory))

    # Code Communities section
    if codebase_map.code_communities:
        lines = ["", "## Code Communities"]
        for i, comm in enumerate(codebase_map.code_communities):
            files = comm.get("files", [])
            file_count = comm.get("file_count", len(files))
            edge_count = comm.get("edge_count", 0)
            label = comm.get("label", f"Community {i + 1}")

            if len(files) > 4:
                shown = ", ".join(files[:4])
                lines.append(
                    f"- {label} ({file_count} files, {edge_count} edges): "
                    f"{shown}, ... and {len(files) - 4} more"
                )
            else:
                shown = ", ".join(files) if files else ""
                lines.append(f"- {label} ({file_count} files, {edge_count} edges): {shown}")
        sections.append("\n".join(lines))

    # Document Communities section
    if codebase_map.doc_communities:
        lines = ["", "## Document Communities"]
        for i, comm in enumerate(codebase_map.doc_communities):
            chunks = comm.get("chunks", [])
            chunk_count = comm.get("chunk_count", len(chunks))
            label = comm.get("label", f"Topic {i + 1}")
            category = comm.get("category", "")
            cat_str = f" [{category}]" if category else ""
            lines.append(f"- {label}{cat_str} ({chunk_count} chunks)")
        sections.append("\n".join(lines))

    # Cross-links section
    if codebase_map.cross_links:
        lines = ["", "## Cross-links"]
        for link in codebase_map.cross_links[:15]:
            lines.append(
                f"- {link.get('code', '?')} ↔ {link.get('doc', '?')} ({link.get('relation', '?')})"
            )
        if len(codebase_map.cross_links) > 15:
            lines.append(f"- ... and {len(codebase_map.cross_links) - 15} more")
        sections.append("\n".join(lines))

    # Hubs section
    if codebase_map.hubs:
        lines = ["", "## Architectural Hubs"]
        for hub in codebase_map.hubs[:10]:
            lines.append(f"- {hub.get('file', '?')} (imported by {hub.get('in_degree', 0)})")
        sections.append("\n".join(lines))

    return "\n".join(sections)
