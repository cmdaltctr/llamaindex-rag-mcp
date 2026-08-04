"""Magika file-type detection — wraps the Magika CLI binary.

Extracted from ``codebase_map.py`` in Phase 5. Provides:
- ``_is_magika_available()`` — check if the Magika CLI is on $PATH
- ``scan_with_magika(path)`` — scan a directory and return typed file entries

The functions are re-imported by ``codebase_map.py`` so existing
``rag_mcp.codebase_map._is_magika_available`` references (including test
patches) keep resolving.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path

from ..config import settings

logger = logging.getLogger(__name__)


def _is_magika_available() -> bool:
    """Check if the Magika CLI binary is on $PATH."""
    return shutil.which(settings.magika_binary) is not None


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
    # Late binding: look up _is_magika_available, FileEntry, and
    # _EXCLUDED_DIRS from codebase_map so test patches on that module
    # propagate correctly.
    from ..codebase_map import FileEntry, _EXCLUDED_DIRS

    # Use the module-level _is_magika_available from integrations.magika
    # by default, but allow codebase_map's re-imported reference to be
    # patched by tests.
    import rag_mcp.codebase_map as _cbm

    if not _cbm._is_magika_available():
        raise FileNotFoundError(
            f"Magika CLI binary not found: {settings.magika_binary}"
        )

    try:
        result = subprocess.run(
            [settings.magika_binary, "-r", path, "--jsonl"],
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
