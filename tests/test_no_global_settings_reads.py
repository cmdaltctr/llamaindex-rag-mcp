"""No global settings singleton reads inside ``core/`` or ``integrations/``.

Asserts that no module under ``src/omrg/core/`` or
``src/omrg/integrations/`` imports the resolved ``settings`` singleton
from ``omrg.config``. Every such module must receive its configuration as
an injected ``EffectiveSettings`` parameter instead (PROPOSAL §6.3.1,
settings-dependency-injection spec).

This test is added as ``xfail(strict=True)`` in group 1 so the pre-fix
failure state is recorded in history. It is un-xfailed in group 5 (task 5.8)
once all 21 sites are threaded to dependency injection.
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

_SCAN_DIRS = (_SRC_ROOT / "core", _SRC_ROOT / "integrations")


def _python_files() -> list[Path]:
    """Return every ``.py`` file under the scanned directories."""
    files: list[Path] = []
    for root in _SCAN_DIRS:
        files.extend(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)
    return sorted(files)


def test_no_global_settings_reads_in_core_or_integrations() -> None:
    """No module under ``core/`` or ``integrations/`` may import the settings singleton."""
    assert _SRC_ROOT.is_dir(), f"configured source root is missing: {_SRC_ROOT}"
    for scan_dir in _SCAN_DIRS:
        assert scan_dir.is_dir(), f"configured scan directory is missing: {scan_dir}"
    hits: list[tuple[Path, int, str]] = []
    for path in _python_files():
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
