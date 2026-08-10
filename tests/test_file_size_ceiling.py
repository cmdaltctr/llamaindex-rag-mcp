"""Executable file-size ceiling.

Asserts that no Python file under ``src/rag_mcp/`` exceeds 500 lines, per
the architecture-v2 conformance target (PROPOSAL §5.1, AGENTS.md invariant).

This test is added as ``xfail(strict=True)`` in group 1 so the pre-fix
failure state is recorded in history. It is un-xfailed in group 8 (task 8.8)
once the five known oversized files are split.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_CEILING = 500
_SRC_ROOT = Path(__file__).resolve().parent.parent / "src" / "rag_mcp"


def _python_files() -> list[Path]:
    """Return every ``.py`` file under ``src/rag_mcp/`` excluding caches."""
    return sorted(p for p in _SRC_ROOT.rglob("*.py") if "__pycache__" not in p.parts)


def _line_count(path: Path) -> int:
    """Return the number of lines in *path*."""
    with path.open(encoding="utf-8") as fh:
        return sum(1 for _ in fh)


def test_no_file_exceeds_500_lines() -> None:
    """No file under ``src/rag_mcp/`` may exceed 500 lines."""
    offenders: list[tuple[Path, int]] = []
    for path in _python_files():
        count = _line_count(path)
        if count > _CEILING:
            offenders.append((path, count))

    if offenders:
        lines = [
            f"  {path.relative_to(_SRC_ROOT.parent)}: {count} lines" for path, count in offenders
        ]
        pytest.fail(
            f"{len(offenders)} file(s) exceed the {_CEILING}-line ceiling:\n" + "\n".join(lines)
        )
