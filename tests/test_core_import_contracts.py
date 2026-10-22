"""Prove the core-level import contracts hold and break on real violations.

Spec ``architecture-boundary-enforcement`` (add-local-web-pipeline-workspace,
verification gaps A11 and B): core modules must not import top-level
``omrs`` modules, ingestion and retrieval must not import one another, and
core must not import a transport framework. Each test copies the real
``src/omrs`` tree, runs ``lint-imports`` with one contract taken from
``pyproject.toml``, and then adds one forbidden import to the copy.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
_SRC = _REPO / "src" / "omrs"
_LINT_IMPORTS = Path(sys.executable).parent / "lint-imports"

_TOP_LEVEL = "core-never-imports-top-level-modules"
_DOMAINS = "ingestion-and-retrieval-stay-independent"
_DOMAINS_REVERSE = "retrieval-stays-independent-of-ingestion"
_FRAMEWORKS = "core-free-of-transport-frameworks"

# The one sanctioned edge: an operation-owned OCR client under an enabled
# fallback (core/ingestion/pipeline.py imports omrs.capabilities lazily).
_SANCTIONED_TOP_LEVEL_EDGE = "omrs.core.ingestion.pipeline -> omrs.capabilities"


def _contracts() -> dict[str, dict]:
    """Return the import-linter contracts in ``pyproject.toml`` by name."""
    with (_REPO / "pyproject.toml").open("rb") as handle:
        config = tomllib.load(handle)
    return {c["name"]: c for c in config["tool"]["importlinter"]["contracts"]}


def _top_level_modules() -> set[str]:
    """Return the dotted names of the top-level ``src/omrs/*.py`` modules."""
    return {f"omrs.{path.stem}" for path in _SRC.glob("*.py") if path.stem != "__init__"}


def _write_config(path: Path, contract: dict) -> None:
    """Write ``contract`` alone as an INI import-linter configuration."""
    lines = [
        "[importlinter]",
        "root_package = omrs",
        "include_external_packages = True",
        "",
        "[importlinter:contract:under-test]",
        f"name = {contract['name']}",
        f"type = {contract['type']}",
    ]
    for key in ("source_modules", "forbidden_modules", "ignore_imports"):
        if contract.get(key):
            lines.append(f"{key} =")
            lines.extend(f"    {entry}" for entry in contract[key])
    if contract.get("allow_indirect_imports"):
        lines.append("allow_indirect_imports = True")
    alerting = contract.get("unmatched_ignore_imports_alerting")
    if alerting:
        lines.append(f"unmatched_ignore_imports_alerting = {alerting}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _lint(tmp_path: Path, contract: dict, *, append: dict[str, str] | None = None):
    """Copy the source tree, append violations, and lint one contract."""
    src = tmp_path / "src"
    shutil.copytree(_SRC, src / "omrs", ignore=shutil.ignore_patterns("__pycache__", "static"))
    for relative, line in (append or {}).items():
        target = src / "omrs" / relative
        target.write_text(target.read_text(encoding="utf-8") + f"\n{line}\n", encoding="utf-8")
    config = tmp_path / ".importlinter"
    _write_config(config, contract)
    return subprocess.run(
        [str(_LINT_IMPORTS), "--config", str(config), "--no-cache"],
        cwd=tmp_path,
        env={"PYTHONPATH": str(src), "PATH": str(_LINT_IMPORTS.parent)},
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )


def test_top_level_contract_forbids_every_top_level_module() -> None:
    """A new top-level module is forbidden to core without a contract edit."""
    contract = _contracts()[_TOP_LEVEL]
    assert contract["type"] == "forbidden"
    assert contract["source_modules"] == ["omrs.core"]
    assert set(contract["forbidden_modules"]) == _top_level_modules()
    assert contract["ignore_imports"] == [_SANCTIONED_TOP_LEVEL_EDGE]
    assert contract["unmatched_ignore_imports_alerting"] == "error"


def test_framework_and_domain_contracts_are_strict() -> None:
    """Neither contract may silence an edge."""
    frameworks = _contracts()[_FRAMEWORKS]
    assert frameworks["source_modules"] == ["omrs.core"]
    assert {"mcp", "typer", "click"} <= set(frameworks["forbidden_modules"])
    assert not frameworks.get("ignore_imports")
    pairs = {
        _DOMAINS: ("omrs.core.ingestion", "omrs.core.retrieval"),
        _DOMAINS_REVERSE: ("omrs.core.retrieval", "omrs.core.ingestion"),
    }
    for name, (source, forbidden) in pairs.items():
        contract = _contracts()[name]
        assert contract["source_modules"] == [source]
        assert contract["forbidden_modules"] == [forbidden]
        assert not contract.get("ignore_imports")


@pytest.mark.parametrize("name", [_TOP_LEVEL, _DOMAINS, _DOMAINS_REVERSE, _FRAMEWORKS])
def test_contract_is_kept_on_the_real_tree(tmp_path: Path, name: str) -> None:
    result = _lint(tmp_path, _contracts()[name])
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    ("name", "append", "edge"),
    [
        (
            _TOP_LEVEL,
            {"core/ingestion/sources.py": "import omrs.engine  # violation"},
            "omrs.core.ingestion.sources -> omrs.engine",
        ),
        (
            _TOP_LEVEL,
            {"core/codebase/codebase_map.py": "import omrs.capabilities  # violation"},
            "omrs.core.codebase.codebase_map -> omrs.capabilities",
        ),
        (
            _DOMAINS,
            {"core/ingestion/sources.py": "import omrs.core.retrieval.policy  # violation"},
            "omrs.core.ingestion.sources -> omrs.core.retrieval.policy",
        ),
        (
            _DOMAINS_REVERSE,
            {"core/retrieval/policy.py": "import omrs.core.ingestion.sources  # violation"},
            "omrs.core.retrieval.policy -> omrs.core.ingestion.sources",
        ),
        (
            _FRAMEWORKS,
            {"core/pipelines/__init__.py": "import typer  # violation"},
            "omrs.core.pipelines -> typer",
        ),
    ],
)
def test_contract_breaks_on_a_violation(
    tmp_path: Path, name: str, append: dict[str, str], edge: str
) -> None:
    """The sanctioned edge excuses only its own module, not other core modules."""
    result = _lint(tmp_path, _contracts()[name], append=append)
    assert result.returncode != 0
    assert "BROKEN" in result.stdout
    assert edge in result.stdout, result.stdout
