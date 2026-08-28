"""Every package under src/rag_mcp must be covered by an import-linter contract.

Task 10.4. Review finding: the `core-business-avoids-providers-transports`
contract covered only four packages, so `core.vectordb`, `core.profiles`,
`core.providers`, `daemon` and `integrations` had their boundaries
unenforced — no violation existed, but nothing would have caught one.

This test fails when a new package is added without deciding which contract
governs it, making that a conscious choice rather than an oversight.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SRC = _REPO_ROOT / "src" / "rag_mcp"


def _packages() -> set[str]:
    """Return every importable package under src/rag_mcp, dotted."""
    found = {"rag_mcp"}
    for init in _SRC.rglob("__init__.py"):
        if "__pycache__" in str(init):
            continue
        rel = init.parent.relative_to(_SRC.parent)
        found.add(".".join(rel.parts))
    return found


def _contract_modules() -> set[str]:
    """Return every module named by any import-linter contract."""
    with (_REPO_ROOT / "pyproject.toml").open("rb") as fh:
        config = tomllib.load(fh)
    contracts = config["tool"]["importlinter"]["contracts"]
    named: set[str] = set()
    for contract in contracts:
        for key in ("source_modules", "forbidden_modules", "modules", "layers"):
            for entry in contract.get(key, []) or []:
                named.add(str(entry).strip())
    return named


def _is_covered(package: str, named: set[str]) -> bool:
    """A package is covered if it, or any ancestor, is named by a contract."""
    parts = package.split(".")
    for i in range(len(parts), 0, -1):
        if ".".join(parts[:i]) in named:
            return True
    return False


@pytest.mark.parametrize("package", sorted(_packages()))
def test_package_is_covered_by_a_contract(package: str) -> None:
    """Each package must be named by, or nested under, a contract module."""
    named = _contract_modules()
    assert _is_covered(package, named), (
        f"Package {package!r} is not covered by any import-linter contract. "
        f"Add it to an existing contract's source_modules, or write a new "
        f"contract stating the boundary it must respect."
    )


def test_contracts_are_actually_declared() -> None:
    """Guard the guard: a typo'd config would make the test above vacuous."""
    named = _contract_modules()
    assert len(named) > 5, "expected several contract modules, found few"
    assert any(m.startswith("rag_mcp") for m in named)
