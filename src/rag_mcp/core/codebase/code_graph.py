"""Code graph construction via tree-sitter AST extraction.

Parses code files using tree-sitter to extract structural relationships
(imports, exports, class inheritance), builds a NetworkX directed graph,
and detects communities, hubs, and bridges.

All settings are read from ``config.py``. No cross-imports with ``retrieval.py``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import networkx as nx

from .codebase_map import FileEntry

logger = logging.getLogger(__name__)


@dataclass
class Community:
    """A community of related files detected by Louvain.

    Attributes:
        label: Human-readable label (top filenames + shared keywords).
        files: List of file paths in the community.
        edge_count: Number of internal edges.
    """

    label: str
    files: list[str]
    edge_count: int = 0


@dataclass
class Hub:
    """A hub file with high in-degree.

    Attributes:
        file: File path.
        in_degree: Number of incoming edges (imported by N files).
    """

    file: str
    in_degree: int


@dataclass
class Bridge:
    """A bridge node connecting separate communities.

    Attributes:
        file: File path.
        betweenness: Betweenness centrality score.
        communities: List of community indices this node bridges.
    """

    file: str
    betweenness: float
    communities: list[int]


def build_code_graph(
    files: list[FileEntry],
    project_root: str,
) -> nx.DiGraph:
    """Build a NetworkX directed graph from code files.

    Each node represents a file with metadata (type, content_type, functions,
    imports). Each edge represents a structural relationship (import,
    inheritance) with metadata (relation, confidence).

    Args:
        files: List of ``FileEntry`` objects for code files.
        project_root: Project root directory path.

    Returns:
        A ``networkx.DiGraph`` with file nodes and relationship edges.
    """
    graph = nx.DiGraph()

    # Add nodes.
    for entry in files:
        file_path = Path(project_root) / entry.path
        content = ""
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            logger.warning("Could not read %s: %s", entry.path, exc)
            continue

        ast = extract_ast_relationships(entry.path, content, entry.label)

        graph.add_node(
            entry.path,
            type="file",
            content_type=f"{entry.group}/{entry.label}",
            functions=ast.functions,
            imports=ast.imports,
            classes=ast.classes,
            exports=ast.exports,
            inheritance=ast.inheritance,
        )

        # Add import edges.
        for imp in ast.imports:
            resolved = _resolve_import_path(imp, entry.path, project_root)
            if resolved is not None and resolved != entry.path:
                if resolved in {e.path for e in files}:
                    graph.add_edge(
                        entry.path,
                        resolved,
                        relation="import",
                        confidence="exact",
                    )

    # Add inheritance edges (class-to-class, within same file or cross-file).
    # These are stored as file-level edges with relation="inheritance".
    for node in graph.nodes():
        node_data = graph.nodes[node]
        for _child, parent in _get_inheritance(node_data):
            # Find which file contains the parent class.
            for other_node in graph.nodes():
                if other_node == node:
                    continue
                other_data = graph.nodes[other_node]
                if parent in other_data.get("classes", []):
                    if not graph.has_edge(node, other_node):
                        graph.add_edge(
                            node,
                            other_node,
                            relation="inheritance",
                            confidence="exact",
                        )

    return graph


def _get_inheritance(node_data: dict) -> list[tuple[str, str]]:
    """Extract inheritance pairs from node data.

    The ``inheritance`` list is stored on the node during ``build_code_graph``
    from the AST extraction result.
    """
    return node_data.get("inheritance", [])


# ── Re-exports ───────────────────────────────────────────────────────────
# AST extraction and community detection live in sibling modules after the
# task 8.4 split. Re-exported here so existing imports keep working and the
# public surface of the codebase-graph subsystem stays in one place.

from .ast_extract import (  # noqa: E402
    ASTResult,
    _resolve_import_path,
    extract_ast_relationships,
)
from .communities import (  # noqa: E402
    detect_bridges,
    detect_communities,
    detect_hubs,
)

__all__ = [
    "ASTResult",
    "Community",
    "Hub",
    "Bridge",
    "build_code_graph",
    "extract_ast_relationships",
    "detect_communities",
    "detect_hubs",
    "detect_bridges",
]
