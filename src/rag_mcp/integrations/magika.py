"""Magika file-type detection — wraps the Magika CLI binary.

Extracted from ``codebase_map.py`` in Phase 5. Owns the detection data
primitives (``FileEntry``, ``_EXCLUDED_DIRS``) so that ``codebase_map.py``
imports them from here rather than the reverse. Provides:
- ``FileEntry`` — dataclass for a single detected file
- ``_EXCLUDED_DIRS`` — directory names skipped during scanning
- ``_is_magika_available()`` — check if the Magika CLI is on $PATH
- ``scan_with_magika(path)`` — scan a directory and return typed file entries

``codebase_map.py`` re-exports ``_is_magika_available`` and ``scan_with_magika``
as thin wrappers so existing ``rag_mcp.codebase_map.*`` references (including
test patches) keep resolving.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from ..core.settings import get_default_effective_settings

logger = logging.getLogger(__name__)


# ── Detection data primitives (owned here, re-exported by codebase_map) ──
# Directories excluded from both Magika and suffix scanning.
_EXCLUDED_DIRS: set[str] = {
    ".git", "node_modules", "__pycache__", ".venv", ".pytest_cache",
    "dist", "build", ".opencode",
}


@dataclass
class FileEntry:
    """A single file detected by Magika or suffix fallback.

    Attributes:
        path: Relative path from the project root.
        group: Magika group (e.g., "code", "document", "config", "binary").
        label: Magika label (e.g., "typescript", "markdown", "yaml").
        is_text: Whether the file is text (vs binary).
        suffix: File extension including the dot (e.g., ".py").
    """

    path: str
    group: str
    label: str
    is_text: bool
    suffix: str


def _magika_binary() -> str:
    """Return the configured Magika binary name."""
    return get_default_effective_settings().magika_binary


def _is_magika_available() -> bool:
    """Check if the Magika CLI binary is on $PATH."""
    return shutil.which(_magika_binary()) is not None


def scan_with_magika(path: str) -> list:
    """Scan a directory using the Magika CLI binary.

    Runs ``magika -r <path> --jsonl`` and parses each JSONL line to extract
    ``output.group``, ``output.label``, ``output.is_text``, and ``path``.

    Args:
        path: Directory path to scan.

    Returns:
        List of ``FileEntry`` objects for each detected file.

    Raises:
        FileNotFoundError: If the Magika binary is not on $PATH.
        subprocess.CalledProcessError: If the Magika process fails.
    """
    if not _is_magika_available():
        raise FileNotFoundError(
            f"Magika CLI binary not found: {_magika_binary()}"
        )

    try:
        result = subprocess.run(
            [_magika_binary(), "-r", path, "--jsonl"],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        logger.warning(
            "Magika scan timed out after 30s, falling back to suffix detection"
        )
        raise FileNotFoundError("Magika scan timed out")

    entries: list[FileEntry] = []
    project_root = Path(path)
    for line in result.stdout.strip().splitlines():
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            logger.debug("Skipping unparseable Magika line: %s", line[:80])
            continue

        file_path = obj.get("path", "")
        output = obj.get("output", {})
        group = output.get("group", "unknown")
        label = output.get("label", "unknown")
        is_text = output.get("is_text", True)

        if any(part in _EXCLUDED_DIRS for part in Path(file_path).parts):
            continue

        try:
            rel_path = str(Path(file_path).relative_to(project_root))
        except ValueError:
            rel_path = file_path

        suffix = Path(file_path).suffix.lower()
        entries.append(
            FileEntry(
                path=rel_path,
                group=group,
                label=label,
                is_text=is_text,
                suffix=suffix,
            )
        )

    return entries
