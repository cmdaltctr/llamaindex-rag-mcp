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
    """A model_copy overlay must not mutate the instance it was copied from.

    This is the property that matters for per-collection profiles: the
    resolver overlays profile levers onto a shared server-default base, and
    two collections resolving different profiles must not observe each
    other's values.  Asserting on two freshly-constructed defaults proves
    nothing, since frozen Pydantic models cannot share state anyway.
    """
    from rag_mcp.core.settings import RetrievalBlock

    base = EffectiveSettings(
        retrieval=RetrievalBlock(top_k=10, rerank_enabled=False)
    )
    overlaid = base.model_copy(
        update={"retrieval": base.retrieval.model_copy(
            update={"top_k": 20, "rerank_enabled": True}
        )}
    )

    assert overlaid.retrieval.top_k == 20
    assert overlaid.retrieval.rerank_enabled is True
    # The base must be untouched by the overlay.
    assert base.retrieval.top_k == 10
    assert base.retrieval.rerank_enabled is False


def test_overlay_preserves_non_lever_fields() -> None:
    """Overlaying profile levers must inherit every field the profile does not own.

    Guards the H-7 failure mode: building a fresh ``EffectiveSettings`` in the
    resolver instead of copying the server-default base silently reset
    cross-cutting fields (``chroma_persist_dir``, ``embed_model``, chunk sizes)
    to class defaults, discarding the operator's configuration.
    """
    from rag_mcp.core.settings import RetrievalBlock

    base = EffectiveSettings(
        chroma_persist_dir="/custom/path",
        embed_model="custom-model",
        collection_name="my_collection",
    )
    overlaid = base.model_copy(
        update={"retrieval": base.retrieval.model_copy(update={"top_k": 20})}
    )

    assert overlaid.retrieval.top_k == 20
    assert overlaid.chroma_persist_dir == "/custom/path"
    assert overlaid.embed_model == "custom-model"
    assert overlaid.collection_name == "my_collection"


def test_backward_compat_properties() -> None:
    """Flat property aliases map to nested blocks."""
    from rag_mcp.core.settings import RetrievalBlock

    settings = EffectiveSettings(
        retrieval=RetrievalBlock(top_k=42, rerank_enabled=True, hybrid_enabled=True),
    )
    assert settings.retrieval.top_k == 42
    assert settings.reranker_enabled is True
    assert settings.retrieval.hybrid_enabled is True


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
    # core/settings.py is rag_mcp.core.settings, so its package is rag_mcp.core.
    importer_package = "rag_mcp.core"

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith(forbidden_prefixes), (
                    f"core/settings.py imports {alias.name} — "
                    f"must be pure data with no upward imports"
                )
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                # Resolve relative imports; matching the raw node.module
                # would miss `from ..config import settings` entirely,
                # since that yields the bare string "config".
                parts = importer_package.split(".")
                if node.level > 1:
                    parts = parts[: -(node.level - 1)] or []
                base = ".".join(parts)
                resolved = f"{base}.{node.module}" if node.module else base
            else:
                resolved = node.module or ""
            assert not resolved.startswith(forbidden_prefixes), (
                f"core/settings.py imports from {resolved} "
                f"(source: level={node.level} module={node.module!r}) — "
                f"must be pure data with no upward imports"
            )
