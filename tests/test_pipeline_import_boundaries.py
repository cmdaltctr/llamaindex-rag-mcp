"""Prove the pipeline and workspace import contracts fail on real violations.

OpenSpec change ``add-local-web-pipeline-workspace``, task 1.3 (design D4,
D7, D10; spec ``architecture-boundary-enforcement``). A forbidden contract
that names a module the code never imports passes for the wrong reason, so
these tests build a throwaway ``omrg`` tree, add one deliberate violation for
every forbidden module, and run ``lint-imports`` against the contract copied
from ``pyproject.toml``. The contract must be broken by each violation and
kept by the same tree without them.
"""

from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_LINT_IMPORTS = Path(sys.executable).parent / "lint-imports"

# Contract name -> module that carries the deliberate violations. The two
# core-wide contracts use a domain adapter location, because graph adapters
# live in their owning domain packages (design D4).
_NEW_CONTRACTS = {
    "pipeline-runner-independent-of-domains": "omrg.core.pipelines.violation",
    "workspace-services-independent-of-domains-and-web": "omrg.core.workspace.violation",
    "core-never-imports-transports": "omrg.core.retrieval.graph_adapter",
    "core-free-of-web-notebook-and-sqlite-runtimes": "omrg.core.retrieval.graph_adapter",
}

_WEB_AND_NOTEBOOK = {"fastapi", "starlette", "uvicorn", "marimo"}

# Minimum forbidden set per contract, from the boundary spec and design D4.
# A contract may forbid more; dropping any of these fails the test.
_REQUIRED_FORBIDDEN = {
    "pipeline-runner-independent-of-domains": {
        "omrg.core.ingestion",
        "omrg.core.retrieval",
        "omrg.core.answer",
        "omrg.core.providers",
        "omrg.transports",
        "subprocess",
        "sqlite3",
    }
    | _WEB_AND_NOTEBOOK,
    "workspace-services-independent-of-domains-and-web": {
        "omrg.core.ingestion",
        "omrg.core.retrieval",
        "omrg.core.answer",
        "omrg.transports",
    }
    | _WEB_AND_NOTEBOOK,
    "core-never-imports-transports": {"omrg.transports"},
    "core-free-of-web-notebook-and-sqlite-runtimes": _WEB_AND_NOTEBOOK | {"sqlite3"},
}

_REQUIRED_SOURCES = {
    "pipeline-runner-independent-of-domains": {"omrg.core.pipelines"},
    "workspace-services-independent-of-domains-and-web": {"omrg.core.workspace"},
    "core-never-imports-transports": {"omrg.core"},
    "core-free-of-web-notebook-and-sqlite-runtimes": {"omrg.core"},
}


def _contracts() -> dict[str, dict]:
    """Return the import-linter contracts in ``pyproject.toml`` by name."""
    with (_REPO_ROOT / "pyproject.toml").open("rb") as fh:
        config = tomllib.load(fh)
    return {c["name"]: c for c in config["tool"]["importlinter"]["contracts"]}


def _write_package(src: Path, dotted: str, body: str = "") -> None:
    """Create ``dotted`` as a package under ``src``, with parent packages."""
    parts = dotted.split(".")
    for i in range(1, len(parts) + 1):
        init = src.joinpath(*parts[:i], "__init__.py")
        init.parent.mkdir(parents=True, exist_ok=True)
        if not init.exists():
            init.write_text("", encoding="utf-8")
    src.joinpath(*parts, "__init__.py").write_text(body, encoding="utf-8")


def _write_config(path: Path, contract: dict) -> None:
    """Write ``contract`` alone as an INI import-linter configuration."""
    lines = [
        "[importlinter]",
        "root_package = omrg",
        "include_external_packages = True",
        "",
        "[importlinter:contract:under-test]",
        f"name = {contract['name']}",
        f"type = {contract['type']}",
    ]
    for key in ("source_modules", "forbidden_modules"):
        lines.append(f"{key} =")
        lines.extend(f"    {module}" for module in contract[key])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _lint(tmp_path: Path, contract: dict, violator: str, *, violate: bool):
    """Build a minimal tree for ``contract`` and run ``lint-imports`` on it."""
    src = tmp_path / "src"
    for module in contract["source_modules"] + contract["forbidden_modules"]:
        if module.startswith("omrg"):
            _write_package(src, module)
    body = ""
    if violate:
        body = "".join(f"import {m}\n" for m in contract["forbidden_modules"])
    _write_package(src, violator, body)
    config = tmp_path / ".importlinter"
    _write_config(config, contract)
    return subprocess.run(
        [str(_LINT_IMPORTS), "--config", str(config), "--no-cache"],
        cwd=tmp_path,
        env={"PYTHONPATH": str(src), "PATH": str(_LINT_IMPORTS.parent)},
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


@pytest.mark.parametrize("name", sorted(_NEW_CONTRACTS))
def test_contract_is_declared_strictly(name: str) -> None:
    """Each new contract exists, forbids imports, and has no silent ignores."""
    contract = _contracts()[name]
    assert contract["type"] == "forbidden"
    assert not contract.get("ignore_imports"), f"{name} must not ignore edges"
    assert contract.get("unmatched_ignore_imports_alerting") == "error"
    assert not contract.get("allow_indirect_imports", False)
    assert _REQUIRED_SOURCES[name] <= set(contract["source_modules"])
    missing = _REQUIRED_FORBIDDEN[name] - set(contract["forbidden_modules"])
    assert not missing, f"{name} no longer forbids {sorted(missing)}"


def test_business_contract_covers_new_packages() -> None:
    """The provider/transport business contract names both new packages."""
    sources = _contracts()["core-business-avoids-providers-transports"]["source_modules"]
    assert "omrg.core.pipelines" in sources
    assert "omrg.core.workspace" in sources


@pytest.mark.skipif(not _LINT_IMPORTS.exists(), reason="import-linter not installed")
@pytest.mark.parametrize(("name", "violator"), sorted(_NEW_CONTRACTS.items()))
def test_each_forbidden_import_breaks_contract(tmp_path: Path, name: str, violator: str) -> None:
    """Every forbidden module, imported on purpose, is reported as broken."""
    contract = _contracts()[name]
    result = _lint(tmp_path, contract, violator, violate=True)
    output = result.stdout + result.stderr
    assert result.returncode != 0, output
    for module in contract["forbidden_modules"]:
        assert f"is not allowed to import {module}:" in output, (module, output)
        assert f"{violator} -> {module}" in output, (module, output)


@pytest.mark.skipif(not _LINT_IMPORTS.exists(), reason="import-linter not installed")
@pytest.mark.parametrize(("name", "violator"), sorted(_NEW_CONTRACTS.items()))
def test_contract_kept_without_violation(tmp_path: Path, name: str, violator: str) -> None:
    """The same tree without the deliberate imports keeps the contract."""
    contract = _contracts()[name]
    result = _lint(tmp_path, contract, violator, violate=False)
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "1 kept, 0 broken" in output, output
