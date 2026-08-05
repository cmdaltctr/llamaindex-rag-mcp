"""Rendering of a :class:`CodebaseMap` into agent-readable text.

Split out of ``codebase_map.py`` (task 8.5). Presentation only — no graph
construction or IO happens here.
"""

from __future__ import annotations

import logging
from pathlib import Path

from .codebase_map import CodebaseMap, format_inventory

logger = logging.getLogger(__name__)


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
                lines.append(
                    f"- {label} ({file_count} files, {edge_count} edges): {shown}"
                )
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
                f"- {link.get('code', '?')} ↔ {link.get('doc', '?')} "
                f"({link.get('relation', '?')})"
            )
        if len(codebase_map.cross_links) > 15:
            lines.append(f"- ... and {len(codebase_map.cross_links) - 15} more")
        sections.append("\n".join(lines))

    # Hubs section
    if codebase_map.hubs:
        lines = ["", "## Architectural Hubs"]
        for hub in codebase_map.hubs[:10]:
            lines.append(
                f"- {hub.get('file', '?')} (imported by {hub.get('in_degree', 0)})"
            )
        sections.append("\n".join(lines))

    return "\n".join(sections)


