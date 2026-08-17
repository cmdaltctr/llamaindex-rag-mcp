"""Vector-store registry contract (``vector-store-registry`` spec).

Mirrors ``test_registry_contract.py``: registered names resolve lazily
to their factories, unknown names fail with a KeyError listing the
registered names, and importing the registry imports no concrete store
module.  Additionally guards the compose dispatch boundary: no
``if/elif`` branch over store names and no module-top-level import of
a concrete store module in ``compose.py``.

Factory-construction tests are deliberately limited to import-string
resolution: building a real store needs full Settings resolution,
which belongs to composition-root tests, not the registry contract.
"""

from __future__ import annotations

import ast
import importlib
import re
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


def test_compose_does_not_branch_over_store_names() -> None:
    """``compose.py`` must not compare the store name against literals.

    The dispatch must be a registry lookup; an ``if/elif`` chain over
    store names is the pattern architecture invariant #10 forbids.
    """
    source = _COMPOSE_PY.read_text(encoding="utf-8")
    offenders = re.findall(r"==\s*[\"'](chroma|lancedb)[\"']", source)
    assert not offenders, (
        f"compose.py branches over vector-store names ({sorted(set(offenders))}); "
        "resolve the store through core/vectordb/registry.py instead."
    )


def test_compose_has_no_module_level_concrete_store_import() -> None:
    """``compose.py`` must not import a concrete store module at top level."""

    def _resolve(module: str, level: int) -> str:
        # compose.py is ``rag_mcp.compose``: level 1 reaches ``rag_mcp``.
        if level == 0:
            return module
        if level == 1:
            return f"rag_mcp.{module}" if module else "rag_mcp"
        return module  # No level-2+ package contains compose.py.

    tree = ast.parse(_COMPOSE_PY.read_text(encoding="utf-8"), filename=str(_COMPOSE_PY))
    imports: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.add(_resolve(node.module or "", node.level))

    offenders = imports & _CONCRETE_STORE_MODULES
    assert not offenders, (
        f"compose.py imports concrete store modules at module level: {sorted(offenders)}. "
        "Concrete stores must be resolved lazily through the registry."
    )
