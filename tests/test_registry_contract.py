"""Tests for the shared lazy registry contract (PROPOSAL §4.4).

Covers the config-composition-root spec scenarios:
- Lazy resolution: importing a registry must not import strategy modules.
- Unknown strategy: ``get()`` raises a helpful ``KeyError`` listing names.
- Missing optional dependency: ``get()`` raises an ``ImportError`` naming
  the strategy, without breaking other strategies.
- Adding a strategy touches one file: registration is a single line in
  ``REGISTRY``.
"""

from __future__ import annotations

import sys
from unittest.mock import patch

import pytest

from rag_mcp.core.chunking import registry as chunking_registry
from rag_mcp.core.metadata import registry as metadata_registry
from rag_mcp.core.retrieval import registry as retrieval_registry
from rag_mcp.core.providers.embeddings import registry as embed_registry
from rag_mcp.core.providers.llm import registry as llm_registry

ALL_REGISTRIES = [
    chunking_registry,
    retrieval_registry,
    metadata_registry,
    embed_registry,
    llm_registry,
]


@pytest.mark.parametrize(
    "registry",
    ALL_REGISTRIES,
    ids=lambda r: r.__name__,
)
def test_registry_is_lazy(registry) -> None:
    """Importing a registry must not import any strategy module.

    Order-independent: snapshots ``sys.modules`` before importing the
    registry module and asserts no registered strategy module appears
    as a *new* entry (strategies already imported by earlier tests are
    ignored).
    """
    before = set(sys.modules)
    import importlib

    importlib.import_module(registry.__name__)
    after = set(sys.modules)
    new_modules = after - before

    for name in registry.REGISTRY.values():
        module_path = name.split(":")[0]
        assert module_path not in new_modules, (
            f"{module_path} was imported eagerly by {registry.__name__}"
        )


@pytest.mark.parametrize(
    "registry",
    ALL_REGISTRIES,
    ids=lambda r: r.__name__,
)
def test_registry_available_lists_sorted_names(registry) -> None:
    """``available()`` must return the sorted registered names."""
    names = registry.available()
    assert names == sorted(registry.REGISTRY.keys())
    assert names, "registry must register at least one strategy"


@pytest.mark.parametrize(
    "registry",
    ALL_REGISTRIES,
    ids=lambda r: r.__name__,
)
def test_registry_unknown_name_raises_helpful_keyerror(registry) -> None:
    """``get()`` with an unknown name must raise KeyError listing names."""
    with pytest.raises(KeyError) as excinfo:
        registry.get("no-such-strategy")
    message = str(excinfo.value)
    assert "Available" in message
    for name in registry.REGISTRY:
        assert name in message


@pytest.mark.parametrize(
    "registry",
    ALL_REGISTRIES,
    ids=lambda r: r.__name__,
)
def test_registry_get_resolves_and_caches(registry) -> None:
    """``get()`` resolves the ``"module:attr"`` string and caches it."""
    first_name = next(iter(registry.REGISTRY))
    resolved = registry.get(first_name)
    assert callable(resolved) or isinstance(resolved, type)
    # Second call must come from the cache (same object).
    assert registry.get(first_name) is resolved


def test_registry_missing_dependency_raises_import_error() -> None:
    """A strategy whose module import fails raises a naming ImportError.

    Simulates a missing optional dependency by poisoning ``sys.modules``
    with ``None`` for the target module (Python raises ImportError on
    import of a module whose ``sys.modules`` entry is ``None``).
    """
    # Choose the llamacpp embedding provider — it guards an optional
    # dependency (llama-index-embeddings-openai).
    target = "rag_mcp.core.providers.embeddings.llamacpp"
    with patch.dict(sys.modules, {target: None}):
        # Force a cache miss by using a fresh registry module.
        import importlib

        fresh = importlib.import_module(
            "rag_mcp.core.providers.embeddings.registry"
        )
        fresh._cache.clear()
        with pytest.raises(ImportError) as excinfo:
            fresh.get("llamacpp")
        assert "llamacpp" in str(excinfo.value)


def test_registry_missing_module_raises_import_error() -> None:
    """A fully missing strategy module raises a naming ImportError."""
    import importlib

    fresh = importlib.import_module("rag_mcp.core.retrieval.registry")
    fresh._cache.clear()
    with patch(
        "importlib.import_module",
        side_effect=ImportError("simulated missing module"),
    ):
        with pytest.raises(ImportError) as excinfo:
            fresh.get("dense")
        assert "dense" in str(excinfo.value)


def test_all_registries_follow_dict_of_import_strings() -> None:
    """Every REGISTRY must map names to ``"module:attr"`` strings."""
    for registry in ALL_REGISTRIES:
        for name, value in registry.REGISTRY.items():
            assert ":" in value, f"{registry.__name__}[{name}] not 'module:attr'"
            module_path, attr = value.split(":", 1)
            assert module_path and attr
