"""Import boundaries of the plugin packages (design D10).

The import-linter contract ``plugin-host-starts-no-processes`` in
``pyproject.toml`` now governs ``omrg.core.plugins``. This test keeps its
own direct-import check as a second guard. It also checks the process
launcher in ``integrations/`` against its own forbidden list.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src" / "omrg"
CORE_PLUGINS = sorted((SRC / "core" / "plugins").glob("*.py"))
LAUNCHER = SRC / "integrations" / "process_launcher.py"

CORE_FORBIDDEN = (
    "subprocess", "socket", "signal", "multiprocessing", "sqlite3", "fastapi", "starlette",
    "uvicorn", "marimo", "uv", "pip", "omrg.integrations", "omrg.transports",
    "omrg.core.providers", "omrg.core.ingestion", "omrg.core.retrieval", "omrg.core.answer",
)  # fmt: skip
LAUNCHER_FORBIDDEN = ("omrg", "marimo", "sqlite3", "fastapi", "starlette", "uvicorn")


def imported(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
        elif isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "import_module":
            names.add("<dynamic import>")
    return names


def violations(names: set[str], forbidden: tuple[str, ...]) -> list[str]:
    return sorted(
        name
        for name in names
        if name == "<dynamic import>"
        or any(name == bad or name.startswith(bad + ".") for bad in forbidden)
    )


def test_core_plugins_exist() -> None:
    assert {p.name for p in CORE_PLUGINS} >= {
        "__init__.py", "manifest.py", "registration.py", "editor.py",
    }  # fmt: skip


@pytest.mark.parametrize("path", CORE_PLUGINS, ids=lambda p: p.name)
def test_core_plugins_start_no_processes(path: Path) -> None:
    assert violations(imported(path), CORE_FORBIDDEN) == []


def test_process_launcher_is_an_integration_leaf() -> None:
    assert violations(imported(LAUNCHER), LAUNCHER_FORBIDDEN) == []


def test_checker_detects_a_forbidden_import(tmp_path: Path) -> None:
    sample = tmp_path / "bad.py"
    sample.write_text("import subprocess\nfrom omrg.integrations import x\n")
    assert violations(imported(sample), CORE_FORBIDDEN) == ["omrg.integrations", "subprocess"]


@pytest.mark.parametrize("path", [*CORE_PLUGINS, LAUNCHER], ids=lambda p: p.name)
def test_files_stay_below_the_size_ceiling(path: Path) -> None:
    assert len(path.read_text().splitlines()) <= 500
