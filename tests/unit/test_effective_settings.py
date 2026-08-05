"""Unit tests for the ``EffectiveSettings`` value object (task 4.6).

Covers:
- Frozen: mutation raises.
- Instance independence: two instances with different rerank_enabled
  don't share state.
- No upward imports: ``core/settings.py`` has no imports from config,
  compose, or sibling core modules.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from pydantic import ValidationError

from rag_mcp.core.settings import EffectiveSettings


def test_effective_settings_is_frozen() -> None:
    """Mutation of any attribute must raise."""
    settings = EffectiveSettings()
    with pytest.raises((ValidationError, TypeError)):
        settings.collection_name = "other"  # type: ignore[misc]


def test_two_instances_are_independent() -> None:
    """Two instances with different rerank_enabled must not share state."""
    a = EffectiveSettings()
    b = EffectiveSettings()
    # Modify b's retrieval block by constructing a new instance.
    from rag_mcp.core.settings import RetrievalBlock

    c = EffectiveSettings(
        retrieval=RetrievalBlock(rerank_enabled=True),
    )
    assert a.retrieval.rerank_enabled is False
    assert c.retrieval.rerank_enabled is True
    # a is unaffected by c's construction.
    assert a.retrieval.rerank_enabled is False


def test_backward_compat_properties() -> None:
    """Flat property aliases map to nested blocks."""
    from rag_mcp.core.settings import RetrievalBlock

    settings = EffectiveSettings(
        retrieval=RetrievalBlock(top_k=42, rerank_enabled=True, hybrid_enabled=True),
    )
    assert settings.top_k == 42
    assert settings.reranker_enabled is True
    assert settings.hybrid_enabled is True


def test_core_settings_has_no_upward_imports() -> None:
    """``core/settings.py`` must not import from config, compose, or core."""
    settings_path = (
        Path(__file__).resolve().parent.parent.parent
        / "src"
        / "rag_mcp"
        / "core"
        / "settings.py"
    )
    source = settings_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(settings_path))

    forbidden_prefixes = (
        "rag_mcp.config",
        "rag_mcp.compose",
        "rag_mcp.core",
    )
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith(forbidden_prefixes), (
                    f"core/settings.py imports {alias.name} — "
                    f"must be pure data with no upward imports"
                )
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                assert not node.module.startswith(forbidden_prefixes), (
                    f"core/settings.py imports from {node.module} — "
                    f"must be pure data with no upward imports"
                )
