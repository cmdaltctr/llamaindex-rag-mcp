"""Folder layout guards (organise-backend-folders, design D8).

Vector-store backends live in one folder each below ``core/vectordb/``, and
HTTP route groups live in ``transports/api/routes/``.  These checks read
files and syntax trees only, so they need neither the ``web`` nor the
``chroma`` extra and run in every CI job.  A backend file at the
``core/vectordb/`` root, a route file at the ``transports/api/`` root, a
stale relative import, or a package ``__init__.py`` that imports something
fails here.
"""

from __future__ import annotations

import ast
import importlib
import subprocess
import sys
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parents[2] / "src"
_OMRG = _SRC / "omrg"
_VECTORDB = _OMRG / "core" / "vectordb"

#: Modules shared by every backend (design D3).  Backend code goes in a folder.
_VECTORDB_ROOT_MODULES = {
    "__init__.py",
    "base.py",
    "identity.py",
    "legacy.py",
    "naming.py",
    "registry.py",
    "score.py",
    "summary.py",
    "validation.py",
}
_VECTORDB_BACKEND_FOLDERS = {"chroma", "lancedb"}

_API = _OMRG / "transports" / "api"
_API_ROUTES = _API / "routes"

#: Folders whose relative imports must all resolve (design D6).
_RESOLVED_IMPORT_ROOTS = [_VECTORDB, _API]

#: Packages that hold code but re-export nothing (design D4).
_IMPORT_FREE_PACKAGES = [
    _VECTORDB / "chroma",
    _VECTORDB / "lancedb",
    _API_ROUTES,
]


def _python_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def _module_file(dotted: str) -> Path | None:
    """Return the file of ``omrg`` module *dotted*, or ``None`` when absent."""
    base = _SRC.joinpath(*dotted.split("."))
    for candidate in (base.with_suffix(".py"), base / "__init__.py"):
        if candidate.is_file():
            return candidate
    return None


def _package_of(path: Path) -> list[str]:
    """Return the dotted package parts that contain *path*."""
    return list(path.relative_to(_SRC).parts[:-1])


def _defined_names(path: Path) -> set[str]:
    """Return every name a module binds or exports anywhere in its syntax tree.

    Names listed in ``__all__`` count, because a package can serve them through
    a lazy module ``__getattr__`` (PEP 562), as ``omrg.__version__`` does.
    """
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets
        ):
            names.update(
                c.value
                for c in ast.walk(node.value)
                if isinstance(c, ast.Constant) and isinstance(c.value, str)
            )
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            names.add(node.id)
        elif isinstance(node, ast.alias):
            names.add((node.asname or node.name).split(".")[0])
    return names


def _unresolved_imports(path: Path) -> list[str]:
    """Return imports in *path* that name a module or name that does not exist.

    Walks the whole tree, so an import inside a function is checked too.  A
    normal import of the file would miss it until the function runs.
    """
    problems: list[str] = []
    package = _package_of(path)
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("omrg.") and _module_file(alias.name) is None:
                    problems.append(f"line {node.lineno}: import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                anchor = package[: len(package) - (node.level - 1)]
                target = ".".join([*anchor, *(node.module.split(".") if node.module else [])])
            elif node.module and node.module.startswith("omrg."):
                target = node.module
            else:
                continue
            target_file = _module_file(target)
            if target_file is None:
                problems.append(f"line {node.lineno}: from {'.' * node.level}{node.module or ''}")
                continue
            if node.module is not None:
                continue
            # ``from . import name``: the name is a sibling module or a name in the package.
            for alias in node.names:
                if _module_file(f"{target}.{alias.name}") is None and alias.name not in (
                    _defined_names(target_file)
                ):
                    dots = "." * node.level
                    problems.append(f"line {node.lineno}: from {dots} import {alias.name}")
    return problems


# ── core/vectordb/ ───────────────────────────────────────────────────


def test_vectordb_root_holds_only_shared_modules() -> None:
    """Backend code lives in ``lancedb/`` or ``chroma/``, not at the root."""
    root_modules = {p.name for p in _VECTORDB.glob("*.py")}
    assert root_modules == _VECTORDB_ROOT_MODULES, (
        f"unexpected: {sorted(root_modules - _VECTORDB_ROOT_MODULES)}; "
        f"missing: {sorted(_VECTORDB_ROOT_MODULES - root_modules)}. "
        "Put backend code in its backend folder."
    )
    folders = {p.name for p in _VECTORDB.iterdir() if p.is_dir() and p.name != "__pycache__"}
    assert folders == _VECTORDB_BACKEND_FOLDERS


@pytest.mark.parametrize(
    "package", _IMPORT_FREE_PACKAGES, ids=lambda package: str(package.relative_to(_OMRG))
)
def test_package_marker_imports_nothing(package: Path) -> None:
    """A backend or routes ``__init__.py`` holds a docstring only (no re-export shim)."""
    marker = package / "__init__.py"
    assert marker.is_file(), f"{marker.relative_to(_SRC)} does not exist"
    imports = [
        node
        for node in ast.walk(ast.parse(marker.read_text(encoding="utf-8")))
        if isinstance(node, (ast.Import, ast.ImportFrom))
    ]
    assert not imports, f"{marker.relative_to(_SRC)} must not import anything"


@pytest.mark.parametrize(
    "root", _RESOLVED_IMPORT_ROOTS, ids=lambda root: str(root.relative_to(_OMRG))
)
def test_every_import_in_moved_folders_resolves(root: Path) -> None:
    """Each relative or ``omrg.`` import, also inside a function, names a real module."""
    findings = [
        f"  {path.relative_to(_SRC)} {problem}"
        for path in _python_files(root)
        for problem in _unresolved_imports(path)
    ]
    assert not findings, "Imports that do not resolve:\n" + "\n".join(findings)


def test_unresolved_import_check_catches_function_level_imports() -> None:
    """Negative control: a bad import inside a function is reported."""
    module = _VECTORDB / "_layout_probe.py"
    module.write_text(
        "def late():\n    from .no_such_sibling import thing\n    return thing\n",
        encoding="utf-8",
    )
    try:
        problems = _unresolved_imports(module)
    finally:
        module.unlink()
    assert problems == ["line 2: from .no_such_sibling"]


def test_lancedb_folder_does_not_shadow_the_sdk() -> None:
    """``import lancedb`` in ``lancedb/store.py`` finds the SDK, not the folder (design D2)."""
    store = importlib.import_module("omrg.core.vectordb.lancedb.store")
    sdk = store.lancedb
    assert sdk.__name__ == "lancedb"
    assert Path(sdk.__file__).resolve().is_relative_to(_OMRG) is False


def test_chroma_paged_import_does_not_load_chromadb() -> None:
    """Importing ``chroma/paged.py`` must not load the optional SDK.

    A subprocess is needed because the chroma-extra job may already hold
    ``chromadb`` in ``sys.modules``.
    """
    program = (
        "import sys\n"
        "import omrg.core.vectordb.chroma.paged\n"
        "loaded = sorted(m for m in sys.modules if m.split('.')[0] == 'chromadb')\n"
        "print(','.join(loaded))\n"
        "sys.exit(1 if loaded else 0)\n"
    )
    proc = subprocess.run([sys.executable, "-c", program], capture_output=True, text=True)
    assert proc.returncode == 0, (
        f"chroma/paged.py import failed or loaded chromadb:\n{proc.stdout}{proc.stderr}"
    )


# ── transports/api/ ──────────────────────────────────────────────────


def _defines_router(path: Path) -> bool:
    """Return whether *path* calls ``APIRouter(...)`` anywhere."""
    return any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "APIRouter"
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
    )


def test_api_root_defines_no_router() -> None:
    """Route groups live in ``routes/``; no module at the API root builds a router."""
    offenders = [p.name for p in sorted(_API.glob("*.py")) if _defines_router(p)]
    assert not offenders, f"Move these route modules into api/routes/: {offenders}"


def test_app_registers_the_router_of_every_route_module() -> None:
    """``app.py`` imports ``router`` from each ``routes/`` module that builds one."""
    route_modules = sorted(
        p.stem for p in _API_ROUTES.glob("*.py") if p.stem != "__init__" and _defines_router(p)
    )
    assert route_modules, "no route modules found under api/routes/"
    imported = {
        node.module.removeprefix("routes.")
        for node in ast.walk(ast.parse((_API / "app.py").read_text(encoding="utf-8")))
        if isinstance(node, ast.ImportFrom)
        and node.level == 1
        and node.module
        and node.module.startswith("routes.")
        and any(alias.name == "router" for alias in node.names)
    }
    assert imported == set(route_modules), (
        f"app.py misses: {sorted(set(route_modules) - imported)}; "
        f"imports unknown: {sorted(imported - set(route_modules))}"
    )
