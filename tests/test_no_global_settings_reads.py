"""No global settings singleton reads inside the production package.

Asserts that no module under ``src/omrg/`` imports the resolved
``settings`` singleton from ``omrg.config`` except the sanctioned
composition-root siblings: ``compose.py``, ``compose_answer.py`` and
``compose_engine.py``. Every other module must receive its configuration
as an injected ``EffectiveSettings`` parameter instead (PROPOSAL §6.3.1,
settings-dependency-injection spec).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_SRC_ROOT = Path(__file__).resolve().parent.parent / "src" / "omrg"

# Matches ``from ...config import settings`` / ``from ..config import settings``
# and the inline ``from ...config import settings`` inside functions.
_SETTINGS_IMPORT_RE = re.compile(
    r"^\s*from\s+\S*\.?config\s+import\s+.*\bsettings\b",
    re.MULTILINE,
)

# Composition-root siblings permitted to call ``get_settings()``.
_PERMITTED_FILES = {"compose.py", "compose_answer.py", "compose_engine.py"}

# Directories whose every file is scanned (no file inside is permitted).
_SCAN_DIRS = (_SRC_ROOT / "core", _SRC_ROOT / "integrations", _SRC_ROOT / "transports")


def _python_files() -> list[Path]:
    """Return every ``.py`` file under the scanned directories, plus top-level."""
    files: list[Path] = []
    # Top-level .py files (excluding __init__.py which has no settings reads).
    files.extend(p for p in _SRC_ROOT.glob("*.py") if "__pycache__" not in p.parts)
    # Recursively scan core/, integrations/, transports/.
    for root in _SCAN_DIRS:
        files.extend(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)
    return sorted(files)


def test_no_global_settings_reads_in_core_or_integrations() -> None:
    """No module outside the composition root may import the settings singleton."""
    assert _SRC_ROOT.is_dir(), f"configured source root is missing: {_SRC_ROOT}"
    for scan_dir in _SCAN_DIRS:
        assert scan_dir.is_dir(), f"configured scan directory is missing: {scan_dir}"
    hits: list[tuple[Path, int, str]] = []
    for path in _python_files():
        # Permit composition-root siblings to call get_settings().
        if path.name in _PERMITTED_FILES:
            continue
        text = path.read_text(encoding="utf-8")
        for match in _SETTINGS_IMPORT_RE.finditer(text):
            line_no = text[: match.start()].count("\n") + 1
            hits.append((path, line_no, match.group(0).strip()))

    if hits:
        lines = [
            f"  {path.relative_to(_SRC_ROOT.parent)}:{line_no}: {snippet}"
            for path, line_no, snippet in hits
        ]
        pytest.fail(f"{len(hits)} settings-singleton import(s) found:\n" + "\n".join(lines))
