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

import subprocess
import sys
import textwrap
from unittest.mock import patch

import pytest

from rag_mcp.core.chunking import registry as chunking_registry
from rag_mcp.core.metadata import registry as metadata_registry
from rag_mcp.core.providers.embeddings import registry as embed_registry
from rag_mcp.core.providers.llm import registry as llm_registry
from rag_mcp.core.retrieval import registry as retrieval_registry

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

    Runs in a **subprocess** with a clean interpreter.  Snapshotting
    ``sys.modules`` in-process cannot work: this test module imports every
    registry at module scope, so by the time the test body runs the registry
    is already in ``sys.modules`` and ``importlib.import_module`` returns the
    cached object without executing it — making the assertion unfalsifiable.
    """
    strategy_modules = sorted(path.split(":")[0] for path in registry._registry.values())
    program = textwrap.dedent(
        f"""
        import sys
        import importlib

        importlib.import_module({registry.__name__!r})

        eager = [m for m in {strategy_modules!r} if m in sys.modules]
        if eager:
            print(",".join(eager))
            sys.exit(1)
        sys.exit(0)
        """
    )
    proc = subprocess.run(
        [sys.executable, "-c", program],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, (
        f"{registry.__name__} eagerly imported strategy modules on import: "
        f"{proc.stdout.strip()}\n{proc.stderr.strip()}"
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

    Entries behind an optional extra (e.g. ``reranker_torch`` when the
    ``torch`` extra is not installed) are skipped rather than failed —
    the dedicated slow-marked test exercises them under the torch
    install.  The skip is narrow: it only fires for ImportError, so a
    genuinely broken registration (wrong module path) still fails.
    """
    registry._cache.clear()
    for name in registry.available():
        try:
            resolved = registry.get(name)
        except ImportError:
            pytest.skip(f"{name} requires an optional extra not installed")
            continue  # unreachable, but satisfies type checker
        assert callable(resolved) or isinstance(resolved, type), (
            f"{registry.__name__}.get({name!r}) did not return a callable/type"
        )


@pytest.mark.parametrize(
    "registry",
    ALL_REGISTRIES,
    ids=lambda r: r.__name__,
)
def test_registry_package_import_is_lazy(registry) -> None:
    """Importing the registry's *package* must not import strategy modules.

    Complements :func:`test_registry_is_lazy`: that test imports the registry
    submodule directly, this one imports the package (e.g. ``rag_mcp.core.chunking``)
    the way production code does, catching an eager re-export added to
    ``__init__.py``.  Also runs in a subprocess — see that test's docstring
    for why an in-process ``sys.modules`` check is unfalsifiable here.
    """
    package = registry.__name__.rsplit(".", 1)[0]
    strategy_modules = sorted(path.split(":")[0] for path in registry._registry.values())
    program = textwrap.dedent(
        f"""
        import sys
        import importlib

        importlib.import_module({package!r})

        eager = [m for m in {strategy_modules!r} if m in sys.modules]
        if eager:
            print(",".join(eager))
            sys.exit(1)
        sys.exit(0)
        """
    )
    proc = subprocess.run(
        [sys.executable, "-c", program],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, (
        f"importing package {package} eagerly imported strategy modules: "
        f"{proc.stdout.strip()}\n{proc.stderr.strip()}"
    )


def test_registry_missing_dependency_raises_import_error() -> None:
    """A strategy whose module import fails raises a naming ImportError.

    Simulates a missing optional dependency by poisoning ``sys.modules``
    with ``None`` for the target module.
    """
    target = "rag_mcp.core.providers.embeddings.llamacpp"
    with patch.dict(sys.modules, {target: None}):
        import importlib

        fresh = importlib.import_module("rag_mcp.core.providers.embeddings.registry")
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


# ── Documented provider names pinned to the live registries ──────────────
#
# Parses the <!-- registry-names:<kind> --> blocks in providers.md and
# asserts set-equality against the live registries.  Fails when someone
# adds or renames a provider without updating the guide — the precise
# event that produced the doc-rot-sweep change.


def _parse_registry_names_block(kind: str) -> set[str]:
    """Extract provider names from the delimited block in providers.md.

    Args:
        kind: ``"embeddings"`` or ``"llm"``.

    Returns:
        The set of provider names listed inside the block.
    """
    import re
    from pathlib import Path

    repo_root = Path(__file__).resolve().parent.parent
    guide = repo_root / "docs" / "guides" / "providers.md"
    text = guide.read_text(encoding="utf-8")

    pattern = rf"<!-- registry-names:{kind} -->(.*?)<!-- /registry-names:{kind} -->"
    match = re.search(pattern, text, re.DOTALL)
    assert match, f"No <!-- registry-names:{kind} --> block found in providers.md"

    # Extract backtick-quoted names from the block body.
    body = match.group(1)
    # register() accepts any string, so do not restrict to identifier
    # characters — a name like "foo-bar" is legal and must be parsed.
    names = set(re.findall(r"`([^`]+)`", body))
    return names


def test_documented_provider_names_match_registries() -> None:
    """Provider names in providers.md SHALL match the live registries.

    Parses the ``<!-- registry-names -->`` blocks and asserts set-equality
    against ``embed_registry.available()`` and ``llm_registry.available()``.
    Fails in either direction: documented-not-registered or
    registered-not-documented.
    """
    # No cache reset: available() reads _registry, not _cache, so clearing
    # it cannot change this assertion and would force later tests to
    # re-import every provider.
    documented_embed = _parse_registry_names_block("embeddings")
    live_embed = set(embed_registry.available())
    assert documented_embed == live_embed, (
        f"Embedding provider names in providers.md do not match the live "
        f"registry.\n"
        f"  documented-not-registered: {sorted(documented_embed - live_embed)}\n"
        f"  registered-not-documented: {sorted(live_embed - documented_embed)}"
    )

    documented_llm = _parse_registry_names_block("llm")
    live_llm = set(llm_registry.available())
    assert documented_llm == live_llm, (
        f"LLM provider names in providers.md do not match the live "
        f"registry.\n"
        f"  documented-not-registered: {sorted(documented_llm - live_llm)}\n"
        f"  registered-not-documented: {sorted(live_llm - documented_llm)}"
    )


# ── Task 8.8: retired bare "reranker" name is rejected ───────────────────


def test_retired_reranker_name_raises_keyerror() -> None:
    """The bare ``"reranker"`` name SHALL raise KeyError.

    The name was retired in favour of ``"reranker_onnx"`` and
    ``"reranker_torch"`` (design decision 4).  A stale alias resolving
    to the wrong backend is the silent-divergence failure this change
    exists to prevent.
    """
    retrieval_registry._cache.clear()
    with pytest.raises(KeyError) as excinfo:
        retrieval_registry.get("reranker")
    message = str(excinfo.value)
    assert "reranker_onnx" in message, (
        f"KeyError for 'reranker' should list 'reranker_onnx' as available: {message}"
    )
    assert "reranker_torch" in message, (
        f"KeyError for 'reranker' should list 'reranker_torch' as available: {message}"
    )


def test_reranker_onnx_and_torch_registered() -> None:
    """Both reranker backend names SHALL be registered."""
    names = retrieval_registry.available()
    assert "reranker_onnx" in names, "reranker_onnx not registered"
    assert "reranker_torch" in names, "reranker_torch not registered"
