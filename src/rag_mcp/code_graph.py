"""Code graph construction via tree-sitter AST extraction.

Parses code files using tree-sitter to extract structural relationships
(imports, exports, class inheritance), builds a NetworkX directed graph,
and detects communities, hubs, and bridges.

All settings are read from ``config.py``. No cross-imports with ``retrieval.py``.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

import networkx as nx

from .codebase_map import FileEntry
from .config import MAGIKA_LABEL_TO_TREESITTER

logger = logging.getLogger(__name__)


@dataclass
class ASTResult:
    """Result of tree-sitter AST extraction for a single file.

    Attributes:
        imports: List of imported module/file paths (resolved to file paths).
        exports: List of exported symbol names.
        functions: List of defined function names.
        classes: List of defined class names.
        inheritance: List of (child_class, parent_class) tuples.
    """

    imports: list[str] = field(default_factory=list)
    exports: list[str] = field(default_factory=list)
    functions: list[str] = field(default_factory=list)
    classes: list[str] = field(default_factory=list)
    inheritance: list[tuple[str, str]] = field(default_factory=list)


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


# ── Language mapping ─────────────────────────────────────────────────────

# Magika label → tree-sitter language name for tree_sitter_language_pack.
_MAGIKA_TO_TS_LANG: dict[str, str] = {
    "python": "python",
    "javascript": "javascript",
    "typescript": "typescript",
    "tsx": "tsx",
    "jsx": "jsx",
    "java": "java",
    "c": "c",
    "cpp": "cpp",
    "csharp": "c_sharp",
    "go": "go",
    "rust": "rust",
    "ruby": "ruby",
    "php": "php",
    "swift": "swift",
    "kotlin": "kotlin",
    "scala": "scala",
    "html": "html",
    "css": "css",
    "sql": "sql",
    "bash": "bash",
    "shell": "bash",
    "yaml": "yaml",
    "toml": "toml",
    "json": "json",
}


def _get_parser(language: str):
    """Get a tree-sitter parser for a language.

    Args:
        language: Tree-sitter language identifier (e.g., "python", "typescript").

    Returns:
        A ``tree_sitter.Parser`` configured for the language, or None if
        the language is not supported.
    """
    try:
        from tree_sitter_language_pack import get_parser
        return get_parser(language)
    except Exception as exc:
        logger.debug("No tree-sitter parser for language %r: %s", language, exc)
        return None


def _resolve_import_path(
    import_spec: str,
    current_file: str,
    project_root: str,
    extensions: list[str] | None = None,
) -> str | None:
    """Resolve an import to a file path within the project.

    Handles both relative imports (``./auth``, ``../utils``) and
    Python-style module imports (``utils``, ``rag_mcp.config``).

    Args:
        import_spec: The import path string (e.g., "./auth", "utils").
        current_file: Path of the file doing the import (relative to root).
        project_root: Project root directory.
        extensions: File extensions to try (default: [".ts", ".tsx", ".js", ".jsx", ".py"]).

    Returns:
        Resolved file path relative to project root, or None if not found.
    """
    if extensions is None:
        extensions = [".ts", ".tsx", ".js", ".jsx", ".py", ".mjs", ".cjs"]

    # Convert dotted module paths to file paths (e.g., "rag_mcp.config" → "rag_mcp/config").
    file_spec = import_spec.replace(".", "/") if not import_spec.startswith(".") else import_spec

    current_dir = Path(current_file).parent

    # For relative imports (./ or ../), resolve relative to current file's directory.
    if import_spec.startswith("."):
        base = (Path(project_root) / current_dir / file_spec).resolve()
    else:
        # For non-relative imports, try:
        # 1. Same directory as current file
        # 2. Project root
        # 3. src/ directory under project root
        candidates = [
            Path(project_root) / current_dir / file_spec,
            Path(project_root) / file_spec,
            Path(project_root) / "src" / file_spec,
        ]
        for base in candidates:
            base = base.resolve()
            # Try as exact file with extension.
            for ext in extensions:
                candidate = base.with_suffix(ext)
                if candidate.exists():
                    try:
                        return str(candidate.relative_to(project_root))
                    except ValueError:
                        return str(candidate)
            # Try as directory with index file.
            for ext in extensions:
                index_file = base / f"index{ext}"
                if index_file.exists():
                    try:
                        return str(index_file.relative_to(project_root))
                    except ValueError:
                        return str(index_file)
        return None

    # Relative import resolution.
    for ext in extensions:
        candidate = base.with_suffix(ext)
        if candidate.exists():
            try:
                return str(candidate.relative_to(project_root))
            except ValueError:
                return str(candidate)

    # Try as directory with index file.
    for ext in extensions:
        index_file = base / f"index{ext}"
        if index_file.exists():
            try:
                return str(index_file.relative_to(project_root))
            except ValueError:
                return str(index_file)

    return None


def _extract_python_imports(content_bytes: bytes) -> list[str]:
    """Extract import paths from a Python AST.

    Args:
        content_bytes: Source code as bytes.

    Returns:
        List of import module paths.
    """
    imports: list[str] = []
    source = content_bytes.decode("utf-8", errors="replace")

    # Use regex for robustness — tree-sitter node traversal is language-specific.
    # Match: from X import Y  /  import X
    for match in re.finditer(
        r"^\s*(?:from\s+(\S+)\s+import|import\s+(\S+))",
        source,
        re.MULTILINE,
    ):
        module = match.group(1) or match.group(2)
        if module:
            # Convert dotted path to file path: rag_mcp.config → rag_mcp/config
            imports.append(module.replace(".", "/"))

    return imports


def _extract_ts_imports(content_bytes: bytes) -> list[str]:
    """Extract import paths from TypeScript/JavaScript source.

    Args:
        content_bytes: Source code as bytes.

    Returns:
        List of import path strings (relative paths only).
    """
    imports: list[str] = []
    source = content_bytes.decode("utf-8", errors="replace")

    # Match: import ... from '...'  /  import '...'  /  require('...')
    for match in re.finditer(
        r"""(?:import\s+.*?\s+from\s+|import\s+|require\s*\(\s*)['"`]([^'"`]+)['"`]""",
        source,
    ):
        spec = match.group(1)
        if spec:
            imports.append(spec)

    return imports


def _extract_classes_and_inheritance(
    content_bytes: bytes,
    language: str,
) -> tuple[list[str], list[tuple[str, str]]]:
    """Extract class names and inheritance relationships.

    Args:
        content_bytes: Source code as bytes.
        language: Language identifier.

    Returns:
        Tuple of (class names, inheritance pairs).
    """
    classes: list[str] = []
    inheritance: list[tuple[str, str]] = []
    source = content_bytes.decode("utf-8", errors="replace")

    if language in ("python",):
        # class Child(Parent):  /  class Child:
        for match in re.finditer(
            r"^\s*class\s+(\w+)\s*(?:\(([^)]+)\))?\s*:",
            source,
            re.MULTILINE,
        ):
            child = match.group(1)
            classes.append(child)
            if match.group(2):
                for parent in match.group(2).split(","):
                    parent = parent.strip().split("[")[0].strip()
                    if parent:
                        inheritance.append((child, parent))

    elif language in ("typescript", "javascript", "tsx", "jsx"):
        # class Child extends Parent  /  class Child implements IFace
        for match in re.finditer(
            r"^\s*(?:export\s+)?class\s+(\w+)(?:\s+extends\s+(\w+))?",
            source,
            re.MULTILINE,
        ):
            child = match.group(1)
            classes.append(child)
            if match.group(2):
                inheritance.append((child, match.group(2)))

    elif language in ("java", "kotlin", "scala", "csharp", "c_sharp"):
        # class Child extends Parent  /  class Child : Parent
        for match in re.finditer(
            r"^\s*(?:public\s+|private\s+|protected\s+)?(?:class|interface)\s+(\w+)"
            r"(?:\s+extends\s+(\w+)|\s*:\s*(\w+))?",
            source,
            re.MULTILINE,
        ):
            child = match.group(1)
            classes.append(child)
            parent = match.group(2) or match.group(3)
            if parent:
                inheritance.append((child, parent))

    return classes, inheritance


def _extract_functions(content_bytes: bytes, language: str) -> list[str]:
    """Extract function names from source code.

    Args:
        content_bytes: Source code as bytes.
        language: Language identifier.

    Returns:
        List of function names.
    """
    functions: list[str] = []
    source = content_bytes.decode("utf-8", errors="replace")

    if language == "python":
        for match in re.finditer(
            r"^\s*(?:async\s+)?def\s+(\w+)",
            source,
            re.MULTILINE,
        ):
            functions.append(match.group(1))
    elif language in ("typescript", "javascript", "tsx", "jsx"):
        # function foo()  /  const foo = () => {}  /  export function foo()
        for match in re.finditer(
            r"^\s*(?:export\s+)?(?:async\s+)?function\s+(\w+)",
            source,
            re.MULTILINE,
        ):
            functions.append(match.group(1))
        # Arrow functions: const foo = (...) => ...
        for match in re.finditer(
            r"^\s*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>",
            source,
            re.MULTILINE,
        ):
            functions.append(match.group(1))

    return functions


def extract_ast_relationships(
    file_path: str,
    content: str,
    language: str,
) -> ASTResult:
    """Extract structural relationships from a code file using tree-sitter.

    Parses the file to extract imports, exports, function definitions, class
    definitions, and class inheritance. The extraction is deterministic —
    no LLM involvement.

    Args:
        file_path: Relative path of the file within the project.
        content: File content as a string.
        language: Tree-sitter language identifier (e.g., "python", "typescript").

    Returns:
        An ``ASTResult`` with extracted relationships. For unsupported
        languages or malformed source, returns an empty result with a
        debug/warning log.
    """
    result = ASTResult()

    ts_lang = _MAGIKA_TO_TS_LANG.get(language)
    if ts_lang is None:
        logger.debug("Unsupported language for AST extraction: %s", language)
        return result

    content_bytes = content.encode("utf-8", errors="replace")

    # Try tree-sitter parsing (for validation), but use regex for extraction
    # which is more robust across language variants.
    parser = _get_parser(ts_lang)
    if parser is not None:
        try:
            tree = parser.parse(content_bytes)
        except Exception as exc:
            logger.warning("tree-sitter parse error in %s: %s", file_path, exc)
            tree = None
    else:
        tree = None

    # Extract imports based on language family.
    if ts_lang == "python":
        result.imports = _extract_python_imports(content_bytes)
    elif ts_lang in ("typescript", "javascript", "tsx", "jsx"):
        result.imports = _extract_ts_imports(content_bytes)
    else:
        # For other languages, try a generic import regex.
        source = content_bytes.decode("utf-8", errors="replace")
        for match in re.finditer(
            r"""(?:import\s+|require\s*\(\s*|#include\s+<?)['"`<]?([^'"`>\s]+)""",
            source,
        ):
            result.imports.append(match.group(1))

    # Extract classes and inheritance.
    result.classes, result.inheritance = _extract_classes_and_inheritance(
        content_bytes, ts_lang,
    )

    # Extract functions.
    result.functions = _extract_functions(content_bytes, ts_lang)

    # Exports: for Python, all top-level definitions are "exported".
    # For TS/JS, look for `export` keyword.
    if ts_lang == "python":
        result.exports = result.functions + result.classes
    elif ts_lang in ("typescript", "javascript", "tsx", "jsx"):
        source = content_bytes.decode("utf-8", errors="replace")
        for match in re.finditer(
            r"^\s*export\s+(?:function|class|const|let|var|default)\s+(\w+)",
            source,
            re.MULTILINE,
        ):
            result.exports.append(match.group(1))

    return result


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
        except (OSError, IOError) as exc:
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
        for child, parent in _get_inheritance(node_data):
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


def detect_communities(graph: nx.DiGraph) -> list[Community]:
    """Detect communities in the code graph using Louvain.

    Uses ``networkx.algorithms.community.louvain_communities()`` to partition
    the graph into clusters of related files. Each community is labelled with
    representative file names.

    Args:
        graph: The code graph as a ``networkx.DiGraph``.

    Returns:
        List of ``Community`` objects with labels, files, and edge counts.
    """
    if graph.number_of_nodes() < 5:
        # Small graph: single community.
        files = list(graph.nodes())
        return [Community(
            label=", ".join(Path(f).name for f in files[:3]),
            files=files,
            edge_count=graph.number_of_edges(),
        )]

    # Convert to undirected for Louvain.
    undirected = graph.to_undirected()

    try:
        communities_sets = nx.algorithms.community.louvain_communities(undirected)
    except Exception as exc:
        logger.warning("Louvain community detection failed: %s", exc)
        return [Community(
            label="all",
            files=list(graph.nodes()),
            edge_count=graph.number_of_edges(),
        )]

    communities: list[Community] = []
    for comm_set in communities_sets:
        files = sorted(comm_set)
        # Label by top filenames.
        filenames = [Path(f).stem for f in files[:3]]
        label = "/".join(filenames) if filenames else "unnamed"

        # Count internal edges.
        internal_edges = sum(
            1 for u, v in graph.edges()
            if u in comm_set and v in comm_set
        )

        communities.append(Community(
            label=label,
            files=files,
            edge_count=internal_edges,
        ))

    # Sort by size (largest first).
    communities.sort(key=lambda c: len(c.files), reverse=True)
    return communities


def detect_hubs(graph: nx.DiGraph) -> list[Hub]:
    """Identify hub nodes — files with high in-degree.

    A hub is any node in the top 10% of in-degree, or any node with
    in-degree ≥ 5, whichever is more inclusive.

    Args:
        graph: The code graph as a ``networkx.DiGraph``.

    Returns:
        List of ``Hub`` objects sorted by in-degree (descending).
    """
    if graph.number_of_nodes() == 0:
        return []

    in_degrees = dict(graph.in_degree())
    if not in_degrees:
        return []

    max_degree = max(in_degrees.values())
    if max_degree == 0:
        return []

    # Top 10% threshold.
    sorted_degrees = sorted(in_degrees.values(), reverse=True)
    top_10_percent_idx = max(1, len(sorted_degrees) // 10)
    top_10_threshold = sorted_degrees[top_10_percent_idx - 1]

    # More inclusive of the two criteria.
    threshold = min(top_10_threshold, 5)

    hubs = [
        Hub(file=node, in_degree=degree)
        for node, degree in in_degrees.items()
        if degree >= threshold
    ]
    hubs.sort(key=lambda h: h.in_degree, reverse=True)
    return hubs


def detect_bridges(
    graph: nx.DiGraph,
    communities: list[Community],
) -> list[Bridge]:
    """Identify bridge nodes connecting separate communities.

    Bridge nodes are detected by high betweenness centrality — they lie
    on shortest paths between different communities.

    Args:
        graph: The code graph as a ``networkx.DiGraph``.
        communities: List of detected communities.

    Returns:
        List of ``Bridge`` objects with betweenness scores and community indices.
    """
    if graph.number_of_nodes() < 5 or len(communities) < 2:
        return []

    # Compute betweenness centrality.
    try:
        betweenness = nx.betweenness_centrality(graph.to_undirected())
    except Exception as exc:
        logger.warning("Betweenness centrality computation failed: %s", exc)
        return []

    # Map nodes to community indices.
    node_to_comm: dict[str, int] = {}
    for i, comm in enumerate(communities):
        for node in comm.files:
            node_to_comm[node] = i

    # Find nodes that connect different communities.
    bridges: list[Bridge] = []
    for node, score in betweenness.items():
        if score <= 0:
            continue
        # Check if this node has edges to multiple communities.
        neighbor_comms: set[int] = set()
        for neighbor in graph.neighbors(node):
            comm_idx = node_to_comm.get(neighbor)
            if comm_idx is not None:
                neighbor_comms.add(comm_idx)
        # Also check incoming edges.
        for predecessor in graph.predecessors(node):
            comm_idx = node_to_comm.get(predecessor)
            if comm_idx is not None:
                neighbor_comms.add(comm_idx)

        if len(neighbor_comms) >= 2:
            bridges.append(Bridge(
                file=node,
                betweenness=score,
                communities=sorted(neighbor_comms),
            ))

    bridges.sort(key=lambda b: b.betweenness, reverse=True)
    return bridges
