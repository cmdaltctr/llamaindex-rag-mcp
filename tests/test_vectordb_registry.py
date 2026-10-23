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
import importlib.util
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

_SRC_ROOT = Path(__file__).resolve().parent.parent / "src"
_COMPOSE_PY = _SRC_ROOT / "omrs" / "compose.py"

_FACTORY_MODULE = {
    "chroma": "omrs.core.vectordb.chroma.store",
    "lancedb": "omrs.core.vectordb.lancedb.store",
}
# The backend folders: each folder and every module below it is concrete (D9).
_CONCRETE_STORE_MODULES = frozenset({"omrs.core.vectordb.chroma", "omrs.core.vectordb.lancedb"})
# Importing the registry must load neither a backend folder nor its store module.
_LAZY_MODULES = sorted(_CONCRETE_STORE_MODULES | set(_FACTORY_MODULE.values()))


def test_available_lists_both_backends() -> None:
    """The registry must expose exactly chroma and lancedb, sorted."""
    from omrs.core.vectordb import registry

    assert registry.available() == ["chroma", "lancedb"]


@pytest.mark.parametrize("name", ["chroma", "lancedb"])
def test_registered_name_resolves_to_its_factory(name: str) -> None:
    """``get(name)`` must resolve to that module's ``build_vector_store_from_settings``."""
    from omrs.core.vectordb import registry

    factory = registry.get(name)
    assert callable(factory)

    module = importlib.import_module(_FACTORY_MODULE[name])
    assert factory is module.build_vector_store_from_settings


@pytest.mark.parametrize("name", ["chroma", "lancedb"])
def test_get_caches_the_resolved_factory(name: str) -> None:
    """A second ``get`` must return the cached same object."""
    from omrs.core.vectordb import registry

    assert registry.get(name) is registry.get(name)


def test_unknown_name_raises_key_error_listing_registered() -> None:
    """An unknown store name must fail with the registered names listed."""
    from omrs.core.vectordb import registry

    with pytest.raises(KeyError) as excinfo:
        registry.get("nope")
    message = str(excinfo.value)
    assert "chroma" in message
    assert "lancedb" in message


def test_missing_backend_module_raises_import_error() -> None:
    """A backend whose module import fails raises a naming ImportError."""
    from unittest.mock import patch

    from omrs.core.vectordb import registry

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

        importlib.import_module("omrs.core.vectordb.registry")

        eager = [m for m in {concrete!r} if m in sys.modules]
        if eager:
            print(",".join(sorted(eager)))
            sys.exit(1)
        sys.exit(0)
        """
    ).format(concrete=_LAZY_MODULES)
    proc = subprocess.run(
        [sys.executable, "-c", program],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, (
        "omrs.core.vectordb.registry eagerly imported concrete store "
        f"modules on import: {proc.stdout.strip()}"
    )


# ── Registry import strings resolve (design D10) ──────────────────────


def _import_string_problem(import_string: str) -> str | None:
    """Return why a ``module:attr`` string does not resolve, or ``None``.

    Finds the module file with ``find_spec`` and parses it, so the check
    imports no backend module and runs without the ``chroma`` extra.  The
    attribute must be a top-level function, class or assignment.
    """
    module_path, _, attr = import_string.partition(":")
    try:
        spec = importlib.util.find_spec(module_path)
    except (ImportError, ValueError):
        spec = None
    if spec is None or not spec.origin or not spec.origin.endswith(".py"):
        return f"{import_string!r}: module {module_path!r} not found"
    tree = ast.parse(Path(spec.origin).read_text(encoding="utf-8"))
    defined: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defined.add(node.name)
        elif isinstance(node, ast.Assign):
            defined.update(t.id for t in node.targets if isinstance(t, ast.Name))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            defined.add(node.target.id)
    if attr not in defined:
        return f"{import_string!r}: {module_path!r} has no top-level {attr!r}"
    return None


def _registry_import_strings() -> list[tuple[str, str, str]]:
    """Return ``(backend, field, import string)`` for every registered string."""
    from omrs.core.vectordb import registry

    strings: list[tuple[str, str, str]] = []
    for name in registry.available():
        strings.append((name, "factory", registry._registry[name]))
        meta = registry.describe(name)
        for field in ("native_sparse_probe", "summary"):
            if meta[field]:
                strings.append((name, field, meta[field]))
    return strings


@pytest.mark.parametrize(
    ("backend", "field", "import_string"),
    _registry_import_strings(),
    ids=lambda value: str(value),
)
def test_registry_import_string_resolves(backend: str, field: str, import_string: str) -> None:
    """Every registry string names a module and a top-level attribute that exist."""
    assert _import_string_problem(import_string) is None, (
        f"{backend} {field} string does not resolve"
    )


@pytest.mark.parametrize(
    ("import_string", "expected"),
    [
        ("omrs.core.vectordb.no_such_module:factory", "no_such_module"),
        ("omrs.core.vectordb.registry:no_such_attribute", "no_such_attribute"),
    ],
    ids=["missing-module", "missing-attribute"],
)
def test_import_string_check_names_the_bad_string(import_string: str, expected: str) -> None:
    """Negative controls: a bad string fails and the message names it."""
    problem = _import_string_problem(import_string)
    assert problem is not None
    assert import_string in problem
    assert expected in problem


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
    so ``from omrs.core.vectordb import chroma`` is caught even
    though the ``from`` module alone names the parent package.
    """

    def _resolve(module: str, level: int) -> str:
        # compose.py is ``omrs.compose``: level 1 reaches ``omrs``.
        if level == 0:
            return module
        if level == 1:
            return f"omrs.{module}" if module else "omrs"
        return module  # No level-2+ package contains compose.py.

    def _is_concrete(module: str) -> bool:
        # A backend folder and every module below it is concrete (design D9).
        return module in _CONCRETE_STORE_MODULES or module.startswith(
            tuple(f"{concrete}." for concrete in _CONCRETE_STORE_MODULES)
        )

    tree = ast.parse(source)
    offenders: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _is_concrete(alias.name):
                    offenders.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            base = _resolve(node.module or "", node.level)
            if _is_concrete(base):
                offenders.add(base)
                continue
            for alias in node.names:
                full = f"{base}.{alias.name}" if base else alias.name
                if _is_concrete(full):
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
            "from omrs.core.vectordb import chroma",
            {"omrs.core.vectordb.chroma"},
        ),
        (
            "from omrs.core.vectordb.chroma import store",
            {"omrs.core.vectordb.chroma"},
        ),
        ("from .core.vectordb import lancedb", {"omrs.core.vectordb.lancedb"}),
        ("from omrs.core.vectordb import registry", set()),
        ("import lancedb", set()),
        ("import omrs.core.vectordb.chroma", {"omrs.core.vectordb.chroma"}),
        (
            "from omrs.core.vectordb.chroma.store import build_chroma_vector_store",
            {"omrs.core.vectordb.chroma.store"},
        ),
        ("from .core.vectordb.lancedb import store", {"omrs.core.vectordb.lancedb"}),
    ],
    ids=[
        "alias-import",
        "from-concrete",
        "relative-alias",
        "registry-import",
        "sdk-import",
        "dotted-import",
        "from-backend-submodule",
        "relative-backend-folder",
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
    from omrs.core.vectordb import registry

    assert registry.describe(name)["cross_process_writes_safe"] is False
