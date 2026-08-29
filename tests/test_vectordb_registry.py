"""Vector-store registry contract (``vector-store-registry`` spec).

Mirrors ``test_registry_contract.py``: registered names resolve lazily
to their factories, unknown names fail with a KeyError listing the
registered names, and importing the registry imports no concrete store
module.  Additionally guards the compose dispatch boundary: no branch
over store names (equality, membership, or ``match``) and no
module-top-level import of a concrete store module in ``compose.py``.

Factory-construction tests are deliberately limited to import-string
resolution: building a real store needs full Settings resolution,
which belongs to composition-root tests, not the registry contract.
"""

from __future__ import annotations

import ast
import importlib
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

_SRC_ROOT = Path(__file__).resolve().parent.parent / "src"
_COMPOSE_PY = _SRC_ROOT / "rag_mcp" / "compose.py"

_FACTORY_MODULE = {
    "chroma": "rag_mcp.core.vectordb.chroma",
    "lancedb": "rag_mcp.core.vectordb.lancedb",
}
_CONCRETE_STORE_MODULES = frozenset(_FACTORY_MODULE.values())


def test_available_lists_both_backends() -> None:
    """The registry must expose exactly chroma and lancedb, sorted."""
    from rag_mcp.core.vectordb import registry

    assert registry.available() == ["chroma", "lancedb"]


@pytest.mark.parametrize("name", ["chroma", "lancedb"])
def test_registered_name_resolves_to_its_factory(name: str) -> None:
    """``get(name)`` must resolve to that module's ``build_vector_store_from_settings``."""
    from rag_mcp.core.vectordb import registry

    factory = registry.get(name)
    assert callable(factory)

    module = importlib.import_module(_FACTORY_MODULE[name])
    assert factory is module.build_vector_store_from_settings


@pytest.mark.parametrize("name", ["chroma", "lancedb"])
def test_get_caches_the_resolved_factory(name: str) -> None:
    """A second ``get`` must return the cached same object."""
    from rag_mcp.core.vectordb import registry

    assert registry.get(name) is registry.get(name)


def test_unknown_name_raises_key_error_listing_registered() -> None:
    """An unknown store name must fail with the registered names listed."""
    from rag_mcp.core.vectordb import registry

    with pytest.raises(KeyError) as excinfo:
        registry.get("nope")
    message = str(excinfo.value)
    assert "chroma" in message
    assert "lancedb" in message


def test_missing_backend_module_raises_import_error() -> None:
    """A backend whose module import fails raises a naming ImportError."""
    from unittest.mock import patch

    from rag_mcp.core.vectordb import registry

    registry._cache.clear()
    try:
        with patch(
            "importlib.import_module",
            side_effect=ImportError("simulated missing module"),
        ):
            with pytest.raises(ImportError, match="lancedb"):
                registry.get("lancedb")
    finally:
        registry._cache.clear()


def test_registry_is_lazy() -> None:
    """Importing the registry must not import any concrete store module.

    Runs in a subprocess with a clean interpreter, mirroring
    ``test_registry_contract.py::test_registry_is_lazy``: in-process
    ``sys.modules`` snapshots are unfalsifiable because the registry is
    already imported by the time the test body runs.
    """
    program = textwrap.dedent(
        """
        import importlib
        import sys

        importlib.import_module("rag_mcp.core.vectordb.registry")

        eager = [m for m in {concrete!r} if m in sys.modules]
        if eager:
            print(",".join(sorted(eager)))
            sys.exit(1)
        sys.exit(0)
        """
    ).format(concrete=sorted(_CONCRETE_STORE_MODULES))
    proc = subprocess.run(
        [sys.executable, "-c", program],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, (
        "rag_mcp.core.vectordb.registry eagerly imported concrete store "
        f"modules on import: {proc.stdout.strip()}"
    )


# ── compose.py dispatch boundary ──────────────────────────────────────

_STORE_NAMES = frozenset({"chroma", "lancedb"})


def _store_name_dispatch_offenders(source: str) -> list[str]:
    """Return store names branched on inside *source*, AST-based.

    A comparison or ``match`` pattern is a dispatch site when a store
    name literal participates anywhere in it — this catches ``==`` /
    ``!=``, membership tests (``in {"chroma", "lancedb"}``), and
    ``match`` arms, none of which the previous equality regex covered.
    """
    offenders: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, (ast.Compare, ast.Match)):
            for sub in ast.walk(node):
                if isinstance(sub, ast.Constant) and sub.value in _STORE_NAMES:
                    offenders.add(sub.value)
    return sorted(offenders)


def _module_level_concrete_imports(source: str) -> set[str]:
    """Return concrete store modules imported at module level in *source*.

    ``from X import Y`` aliases are expanded to their full module path,
    so ``from rag_mcp.core.vectordb import chroma`` is caught even
    though the ``from`` module alone names the parent package.
    """

    def _resolve(module: str, level: int) -> str:
        # compose.py is ``rag_mcp.compose``: level 1 reaches ``rag_mcp``.
        if level == 0:
            return module
        if level == 1:
            return f"rag_mcp.{module}" if module else "rag_mcp"
        return module  # No level-2+ package contains compose.py.

    tree = ast.parse(source)
    offenders: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in _CONCRETE_STORE_MODULES:
                    offenders.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            base = _resolve(node.module or "", node.level)
            if base in _CONCRETE_STORE_MODULES:
                offenders.add(base)
            for alias in node.names:
                full = f"{base}.{alias.name}" if base else alias.name
                if full in _CONCRETE_STORE_MODULES:
                    offenders.add(full)
    return offenders


def test_compose_does_not_branch_over_store_names() -> None:
    """``compose.py`` must not branch on store-name literals.

    The dispatch must be a registry lookup; an ``if/elif`` chain, a
    membership test, or a ``match`` over store names is the pattern
    architecture invariant #10 forbids.
    """
    source = _COMPOSE_PY.read_text(encoding="utf-8")
    offenders = _store_name_dispatch_offenders(source)
    assert not offenders, (
        f"compose.py branches over vector-store names ({offenders}); "
        "resolve the store through core/vectordb/registry.py instead."
    )


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ('if settings.vector_store == "chroma":\n    pass', ["chroma"]),
        ('if name != "lancedb":\n    pass', ["lancedb"]),
        ('if settings.vector_store in {"chroma", "lancedb"}:\n    pass', ["chroma", "lancedb"]),
        ('match settings.vector_store:\n    case "lancedb":\n        pass', ["lancedb"]),
        ("factory = registry.get(settings.vector_store)", []),
        ('if settings.chroma_mode != "cloud":\n    pass', []),
    ],
    ids=["equality", "inequality", "membership", "match-arm", "registry-lookup", "other-literal"],
)
def test_dispatch_detector_catches_every_branch_form(source: str, expected: list[str]) -> None:
    """Negative controls: the detector sees membership and match forms too."""
    assert _store_name_dispatch_offenders(source) == expected


def test_compose_has_no_module_level_concrete_store_import() -> None:
    """``compose.py`` must not import a concrete store module at top level."""
    source = _COMPOSE_PY.read_text(encoding="utf-8")
    offenders = _module_level_concrete_imports(source)
    assert not offenders, (
        f"compose.py imports concrete store modules at module level: {sorted(offenders)}. "
        "Concrete stores must be resolved lazily through the registry."
    )


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (
            "from rag_mcp.core.vectordb import chroma",
            {"rag_mcp.core.vectordb.chroma"},
        ),
        (
            "from rag_mcp.core.vectordb.chroma import build_chroma_vector_store",
            {"rag_mcp.core.vectordb.chroma"},
        ),
        ("from .core.vectordb import lancedb", {"rag_mcp.core.vectordb.lancedb"}),
        ("from rag_mcp.core.vectordb import registry", set()),
        ("import lancedb", set()),
        ("import rag_mcp.core.vectordb.chroma", {"rag_mcp.core.vectordb.chroma"}),
    ],
    ids=[
        "alias-import",
        "from-concrete",
        "relative-alias",
        "registry-import",
        "sdk-import",
        "dotted-import",
    ],
)
def test_import_detector_expands_aliases(source: str, expected: set[str]) -> None:
    """Negative controls: alias imports of concrete modules are caught."""
    assert _module_level_concrete_imports(source) == expected


# ── Cross-process write-safety metadata (storage-layout spec) ────────


@pytest.mark.parametrize("name", ["chroma", "lancedb"])
def test_no_backend_claims_cross_process_write_safety(name: str) -> None:
    """No backend may claim ``cross_process_writes_safe``.

    The collection-storage-layout contract states that a cross-process
    write-safety claim requires a two-process concurrent-write
    experiment; none exists for either backend, so ``describe(name)``
    must report ``False`` for both.
    """
    from rag_mcp.core.vectordb import registry

    assert registry.describe(name)["cross_process_writes_safe"] is False
