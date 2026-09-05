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


# ── Stale rag_mcp / rag-mcp reference gate (task 7.5) ─────────────────


# Directories exempt from the stale-reference gate: historical records
# that legitimately cite the old package name.
_EXEMPT_DIRS: list[Path] = [
    _REPO_ROOT / "docs" / "adr",
    _REPO_ROOT / "docs" / "tdr",
    _REPO_ROOT / "openspec" / "changes" / "archive",
    _REPO_ROOT / "CHANGELOG.md",
]

# Files exempt from the stale-reference gate: v3 legacy-watcher migration
# code and its tests must literally name the removed ``rag-mcp`` executable
# and ``com.rag-mcp.watch.`` label prefix to discover and migrate a v2-era
# LaunchAgent (design.md Decision 3), and the packaging regression tests
# must name it to assert its absence (task 1.3). Neither is stale residue —
# both are deliberate, functioning references to the removed name.
_LEGACY_MIGRATION_EXEMPT: list[Path] = [
    _REPO_ROOT / "src" / "omrg" / "transports" / "cli" / "_launchagent.py",
    _REPO_ROOT / "tests" / "unit" / "test_launchagent.py",
    _REPO_ROOT / "tests" / "test_install_login_watcher.py",
    _REPO_ROOT / "tests" / "test_package_metadata.py",
]

# Match the stale Python import path ``rag_mcp`` and the standalone
# ``rag-mcp`` console-command/distribution name in live source and
# documentation.  The unchanged GitHub repository identifier
# ``llamaindex-rag-mcp`` is exempted via a negative lookbehind rather than
# omitted entirely, so a bare ``rag-mcp`` next to unrelated text still
# fails the guard.
_STALE_RE = re.compile(r"\brag_mcp\b|(?<!llamaindex-)\brag-mcp\b")

# Files to scan for stale references — live source, tests, and operator docs.
_STALE_SCAN_GLOBS: list[str] = [
    "src/omrg/**/*.py",
    "tests/**/*.py",
    "docs/guides/**/*.md",
    "README.md",
    "AGENTS.md",
    "pyproject.toml",
]


def _is_exempt(path: Path) -> bool:
    """Return True when the path is a historical record or legacy-migration file."""
    for exempt in _EXEMPT_DIRS:
        if exempt.is_dir():
            if exempt in path.parents or path == exempt:
                return True
        elif path == exempt:
            return True
    return path in _LEGACY_MIGRATION_EXEMPT


def test_no_stale_rag_mcp_references_in_live_surface() -> None:
    """No live source, test or operator doc references ``rag_mcp`` or ``rag-mcp``.

    Historical records (ADRs, TDRs, archived OpenSpec changes, released
    changelogs) are exempt — they describe the past and must not be
    rewritten. Legacy-watcher migration code and its tests, plus the
    packaging regression tests asserting the name's absence, are exempt via
    :data:`_LEGACY_MIGRATION_EXEMPT` — they are deliberate, functioning
    references, not residue. The unchanged GitHub repository identifier
    ``llamaindex-rag-mcp`` is exempted by the matcher itself, not either
    list.
    """
    findings: list[str] = []
    for glob_pat in _STALE_SCAN_GLOBS:
        for path in _REPO_ROOT.glob(glob_pat):
            if _is_exempt(path):
                continue
            # Skip this test file itself — it legitimately mentions rag_mcp.
            if path.name == "test_docs_references.py":
                continue
            text = path.read_text(encoding="utf-8")
            for lineno, line in enumerate(text.splitlines(), start=1):
                for match in _STALE_RE.finditer(line):
                    rel = path.relative_to(_REPO_ROOT)
                    findings.append(f"  {rel}:{lineno}  {match.group()}: {line.strip()}")

    if findings:
        pytest.fail("Stale rag_mcp/rag-mcp references in live surface:\n" + "\n".join(findings))
