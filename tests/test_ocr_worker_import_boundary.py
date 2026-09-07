"""Import boundary between OMRG and the Paddle packages (task 2.1b).

PaddleOCR, PaddleX, and PaddlePaddle live only in the isolated worker
project (``ocr-worker/``). These tests prove the boundary statically:

- no module under ``src/omrg/`` contains a Paddle import statement,
  module-level or lazy;
- the root ``pyproject.toml`` dependency declarations contain no
  Paddle distribution;
- the root ``uv.lock`` package list contains no Paddle distribution.

The worker project is intentionally exempt: importing Paddle inside
its own process is its purpose.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT / "src" / "omrg"

# Matches ``import paddle...`` and ``from paddle... import ...`` at any
# indentation, so lazy imports inside function bodies are covered too.
_PADDLE_IMPORT_RE = re.compile(r"^\s*(?:import|from)\s+paddle\w*", re.MULTILINE)

_PADDLE_DISTRIBUTIONS = frozenset({"paddleocr", "paddlex", "paddlepaddle"})


def _python_sources() -> list[Path]:
    """Return every Python file under ``src/omrg/``."""
    return sorted(p for p in SRC_ROOT.rglob("*.py") if "__pycache__" not in p.parts)


def test_no_paddle_import_in_omrg_source() -> None:
    """No ``src/omrg/`` file may contain a Paddle import, lazy or not."""
    violations: list[str] = []
    for path in _python_sources():
        source = path.read_text(encoding="utf-8")
        match = _PADDLE_IMPORT_RE.search(source)
        if match:
            line_no = source.count("\n", 0, match.start()) + 1
            violations.append(f"{path.relative_to(REPO_ROOT)}:{line_no}")
    assert not violations, (
        "Paddle import statements found in OMRG source (they belong only in "
        f"ocr-worker/): {', '.join(violations)}"
    )


def test_root_pyproject_declares_no_paddle_dependency() -> None:
    """Root dependency declarations must name no Paddle distribution."""
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    declared: set[str] = set()
    for requirement in pyproject["project"].get("dependencies", []):
        declared.add(_distribution_name(requirement))
    for group in pyproject["project"].get("optional-dependencies", {}).values():
        for requirement in group:
            declared.add(_distribution_name(requirement))
    offending = sorted(declared & _PADDLE_DISTRIBUTIONS)
    assert not offending, f"root pyproject.toml declares Paddle packages: {offending}"


def test_root_lockfile_contains_no_paddle_package() -> None:
    """The root ``uv.lock`` package list must contain no Paddle distribution."""
    lock = tomllib.loads((REPO_ROOT / "uv.lock").read_text(encoding="utf-8"))
    names = {_normalise(pkg["name"]) for pkg in lock.get("package", [])}
    offending = sorted(names & _PADDLE_DISTRIBUTIONS)
    assert not offending, f"root uv.lock resolves Paddle packages: {offending}"


def test_worker_lockfile_owns_the_paddle_packages() -> None:
    """The paddle packages must live in the worker-owned lock instead.

    This is the positive half of the boundary: the isolation is only
    meaningful if the worker lock actually carries what the main
    environment is forbidden from carrying.
    """
    worker_lock = REPO_ROOT / "ocr-worker" / "uv.lock"
    assert worker_lock.is_file(), "ocr-worker/uv.lock is missing; run `uv lock` there"
    lock = tomllib.loads(worker_lock.read_text(encoding="utf-8"))
    names = {_normalise(pkg["name"]) for pkg in lock.get("package", [])}
    present = sorted(names & _PADDLE_DISTRIBUTIONS)
    assert "paddleocr" in present, "worker lock is missing paddleocr"
    assert "paddlepaddle" in present, "worker lock is missing paddlepaddle"


def _distribution_name(requirement: str) -> str:
    """Extract the normalised distribution name from a requirement string."""
    return _normalise(re.split(r"[\[\s><=!~]", requirement.strip(), maxsplit=1)[0])


def _normalise(name: str) -> str:
    """Apply PEP 503 name normalisation (underscores become hyphens)."""
    return re.sub(r"[-_.]+", "-", name).lower()
