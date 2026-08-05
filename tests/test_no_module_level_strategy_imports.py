"""Assert dispatch modules have no module-level strategy imports.

Verifies that ``core/ingestion/chunker.py``, ``core/metadata/extractor.py``,
and ``core/retrieval/pipeline.py`` contain no module-level import of a
concrete strategy module — strategies must be resolved through the registry
at dispatch time (task 3.8, config-composition-root spec).
"""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest

_SRC_ROOT = Path(__file__).resolve().parent.parent / "src" / "rag_mcp"


def _module_top_level_imports(module_path: Path) -> set[str]:
    """Return the set of module names imported at the top level of *module_path*.

    Only top-level (module body) ``Import`` and ``ImportFrom`` nodes are
    collected — imports inside function/class bodies are excluded.
    """
    source = module_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(module_path))
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module.split(".")[0])
                # Also record the full dotted path for precise matching.
                names.add(node.module)
    return names


# The concrete strategy modules that must NOT appear as top-level imports.
_FORBIDDEN_STRATEGY_MODULES = {
    "rag_mcp.core.chunking.code",
    "rag_mcp.core.chunking.markdown",
    "rag_mcp.core.chunking.sentence",
    "rag_mcp.core.chunking.config_file",
    "rag_mcp.core.metadata.keyword",
    "rag_mcp.core.metadata.ollama",
    "rag_mcp.core.metadata.llamaindex",
    "rag_mcp.core.metadata.llamacpp",
    "rag_mcp.core.retrieval.dense",
    "rag_mcp.core.retrieval.fusion",
    "rag_mcp.core.retrieval.policy",
    "rag_mcp.core.retrieval.reranker",
    "rag_mcp.core.retrieval.sparse",
}


@pytest.mark.parametrize(
    "rel_path",
    [
        "core/ingestion/chunker.py",
        "core/metadata/extractor.py",
        "core/retrieval/pipeline.py",
    ],
)
def test_no_module_level_strategy_import(rel_path: str) -> None:
    """The dispatch module must not import concrete strategies at top level."""
    module_path = _SRC_ROOT / rel_path
    imports = _module_top_level_imports(module_path)

    # Check both the short form (e.g. "rag_mcp") and full dotted paths.
    offenders = imports & _FORBIDDEN_STRATEGY_MODULES
    assert not offenders, (
        f"{rel_path} has module-level imports of concrete strategy modules: "
        f"{sorted(offenders)}. Strategies must be resolved through the "
        f"registry at dispatch time."
    )
