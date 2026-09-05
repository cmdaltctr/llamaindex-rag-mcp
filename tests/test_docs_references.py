"""Guard test: documentation file-path references SHALL resolve.

Every ``src/omrg/**.py`` path cited in operator-facing documentation
(``docs/guides/`` and ``tests/TEST_README.md``) must exist on disk.
Historical records (``docs/adr/``) are excluded — they legitimately cite
paths that no longer exist, because they describe the past.

See ``openspec/changes/doc-rot-sweep/`` design.md Decision 4: this is a
narrow, exact-match oracle with ~0% false positives by construction.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent

# Operator-facing paths to scan.  ADRs are excluded — they are historical
# records that legitimately cite moved paths.
_SCAN_PATHS: list[Path] = [
    _REPO_ROOT / "tests" / "TEST_README.md",
]
_SCAN_DIRS: list[Path] = [
    _REPO_ROOT / "docs" / "guides",
]

# Match src/omrg/...py paths in documentation.  Path components may
# contain hyphens (e.g. ``providers/llama-cpp.py``) as well as word
# characters, so the class includes ``-`` alongside ``\w``, ``/``, ``.``.
_SRC_PATH_RE = re.compile(r"src/omrg/[\w./-]+\.py")


def _scan_files() -> list[Path]:
    """Return every file to scan."""
    files = [p for p in _SCAN_PATHS if p.exists()]
    for dir_path in _SCAN_DIRS:
        if dir_path.is_dir():
            files.extend(sorted(dir_path.rglob("*.md")))
    return files


def test_documented_src_paths_exist() -> None:
    """Every ``src/omrg/**.py`` path in operator docs must exist.

    A path either resolves or it does not — there is no judgement and no
    suppression mechanism needed.  A guide that cites a moved file fails
    this check rather than misleading a contributor.
    """
    findings: list[str] = []
    for file_path in _scan_files():
        text = file_path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), start=1):
            for match in _SRC_PATH_RE.finditer(line):
                cited = match.group()
                resolved = _REPO_ROOT / cited
                if not resolved.exists():
                    rel = file_path.relative_to(_REPO_ROOT)
                    findings.append(f"  {rel}:{lineno}  {cited}")

    if findings:
        pytest.fail(
            "Documentation cites src/omrg/ paths that do not exist:\n" + "\n".join(findings)
        )
