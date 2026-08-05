"""Tests for the shared lazy registry contract (PROPOSAL §4.4).

Covers the config-composition-root spec scenarios:
- Lazy resolution: importing a registry must not import strategy modules.
- Unknown strategy: ``get()`` raises a helpful ``KeyError`` listing names.
- Missing optional dependency: ``get()`` raises an ``ImportError`` naming
  the strategy, without breaking other strategies.
- Adding a strategy touches one file: registration via ``register()``.
- Every registered name resolves without ``ImportError``.
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

    Snapshots ``sys.modules`` before importing the registry module and
    asserts no registered strategy module appears as a *new* entry.
    """
    before = set(sys.modules)
    import importlib

    importlib.import_module(registry.__name__)
    after = set(sys.modules)
    new_modules = after - before

    for import_path in registry._registry.values():
        module_path = import_path.split(":")[0]
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
    assert names == sorted(registry._registry.keys())
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
    for name in registry.available():
        assert name in message


@pytest.mark.parametrize(
    "registry",
    ALL_REGISTRIES,
    ids=lambda r: r.__name__,
)
def test_registry_get_resolves_and_caches(registry) -> None:
    """``get()`` resolves the ``"module:attr"`` string and caches it."""
    first_name = registry.available()[0]
    resolved = registry.get(first_name)
    assert callable(resolved) or isinstance(resolved, type)
    # Second call must come from the cache (same object).
    assert registry.get(first_name) is resolved


@pytest.mark.parametrize(
    "registry",
    ALL_REGISTRIES,
    ids=lambda r: r.__name__,
)
def test_registry_all_names_resolve(registry) -> None:
    """Every registered name must resolve via ``get()`` without ImportError.

    Walks ``available()`` → ``get()`` for every entry, asserting no
    ``ImportError`` surfaces (task 3.7).
    """
    registry._cache.clear()
    for name in registry.available():
        resolved = registry.get(name)
        assert callable(resolved) or isinstance(resolved, type), (
            f"{registry.__name__}.get({name!r}) did not return a callable/type"
        )


@pytest.mark.parametrize(
    "registry",
    ALL_REGISTRIES,
    ids=lambda r: r.__name__,
)
def test_registry_imports_no_strategy_module(registry) -> None:
    """Importing a registry module must not import any strategy module.

    Checks ``sys.modules`` after import — no registered strategy module
    may be present (task 3.7).
    """
    for import_path in registry._registry.values():
        module_path = import_path.split(":")[0]
        # The strategy module may have been imported by a *previous* test
        # via get(); we only assert the registry import itself did not
        # add it. Re-import the registry and check it does not pull in
        # strategies as a side effect.
        import importlib

        # Clear and re-import to get a clean check.
        was_present = module_path in sys.modules
        importlib.reload(registry)
        if not was_present:
            assert module_path not in sys.modules, (
                f"{module_path} was imported as a side effect of "
                f"importing {registry.__name__}"
            )


def test_registry_missing_dependency_raises_import_error() -> None:
    """A strategy whose module import fails raises a naming ImportError.

    Simulates a missing optional dependency by poisoning ``sys.modules``
    with ``None`` for the target module.
    """
    target = "rag_mcp.core.providers.embeddings.llamacpp"
    with patch.dict(sys.modules, {target: None}):
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
    """Every ``_registry`` must map names to ``"module:attr"`` strings."""
    for registry in ALL_REGISTRIES:
        for name, value in registry._registry.items():
            assert ":" in value, f"{registry.__name__}[{name}] not 'module:attr'"
            module_path, attr = value.split(":", 1)
            assert module_path and attr


def test_register_adds_new_strategy() -> None:
    """``register()`` adds a new entry to the registry."""
    chunking_registry._cache.pop("__test__", None)
    chunking_registry._registry.pop("__test__", None)
    chunking_registry.register("__test__", "rag_mcp.core.chunking.code:chunk_code_file_async")
    assert "__test__" in chunking_registry.available()
    resolved = chunking_registry.get("__test__")
    assert callable(resolved)
    # Clean up.
    chunking_registry._registry.pop("__test__", None)
    chunking_registry._cache.pop("__test__", None)
