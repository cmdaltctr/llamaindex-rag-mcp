"""Magika file-type detection — wraps the Magika CLI binary.

Extracted from ``codebase_map.py`` in Phase 5. Owns the detection data
primitives (``FileEntry``, ``_EXCLUDED_DIRS``) so that ``codebase_map.py``
imports them from here rather than the reverse. Provides:
- ``FileEntry`` — dataclass for a single detected file
- ``_EXCLUDED_DIRS`` — directory names skipped during scanning
- ``_is_magika_available()`` — check if the Magika CLI is on $PATH
- ``scan_with_magika(path)`` — scan a directory and return typed file entries

``codebase_map.py`` re-exports ``_is_magika_available`` and ``scan_with_magika``
as thin wrappers so existing ``omrg.codebase_map.*`` references (including
test patches) keep resolving.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..core.settings import get_default_effective_settings

logger = logging.getLogger(__name__)


# ── Detection data primitives (owned here, re-exported by codebase_map) ──
# Directories excluded from both Magika and suffix scanning.
_EXCLUDED_DIRS: set[str] = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    ".pytest_cache",
    "dist",
    "build",
    ".opencode",
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


def _magika_binary(settings: Any | None = None) -> str:
    """Return the configured Magika binary name.

    Args:
        settings: Injected effective settings carrying ``magika_binary``.
            ``None`` keeps the legacy process-global resolution for
            entry points that resolve at their own boundary.

    Raises:
        RuntimeError: When *settings* is ``None`` and no process-global
            default is installed (direct-Engine processes; the caller
            should inject settings instead).
    """
    if settings is not None:
        return settings.magika_binary
    return get_default_effective_settings().magika_binary


def _is_magika_available(settings: Any | None = None) -> bool:
    """Check if the Magika CLI binary is on $PATH."""
    return shutil.which(_magika_binary(settings)) is not None


# Groups that stay readable even when the model marks ``is_text`` false
# (PDF documents; taxonomy rows such as Ada or BRF). Everything else
# with ``is_text=false`` is treated as binary at this boundary.
_READABLE_GROUPS = frozenset({"document", "code", "text"})


def _normalise_detected(group: str, label: str, is_text: bool) -> tuple[str, str]:
    """Apply the OMRG boundary rules to one validated Magika label.

    Binary boundary: a non-readable group outside ``document``, ``code``,
    and ``text`` becomes ``binary`` so the pipeline's existing
    ``content_type.startswith("binary")`` skip fires. The label and
    ``is_text`` are preserved, and readable false-text groups keep their
    group so documents such as PDF stay reachable by readers.

    Alias normalisation: only the two confirmed readable aliases
    ``text/markdown -> document/markdown`` and ``text/txt ->
    document/text`` are mapped, keeping suffix-map identity stable
    without a taxonomy framework.
    """
    if not is_text and group not in _READABLE_GROUPS:
        return "binary", label
    if is_text and group == "text":
        if label == "markdown":
            return "document", "markdown"
        if label == "txt":
            return "document", "text"
    return group, label


def _parse_magika_row(line: str) -> tuple[str, str, str, bool]:
    """Validate one Magika CLI JSONL row and return its entry fields.

    The Magika CLI emits one JSON object per line. A successful row nests
    the public label at ``result.value.output``; the sibling ``dl`` field
    holds raw model details that must never be read as the label.

    Returns:
        ``(path, group, label, is_text)`` with boundary normalisation
        already applied.

    Raises:
        ValueError: The row is not JSON, the status is not ``ok``, the
            successful envelope is malformed, or a required field is
            invalid (``group``/``label`` must be non-empty strings,
            ``is_text`` a boolean). One bad row invalidates the whole
            scan so production falls back to suffix detection instead
            of reporting partial results.
    """
    try:
        obj = json.loads(line)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Magika returned a non-JSON row: {line[:80]!r}") from exc

    result = obj.get("result") if isinstance(obj, dict) else None
    if not isinstance(result, dict) or result.get("status") != "ok":
        raise ValueError(f"Magika row status is not 'ok': {line[:80]!r}")

    value = result.get("value")
    output = value.get("output") if isinstance(value, dict) else None
    if not isinstance(output, dict):
        raise ValueError(f"Magika 'ok' row lacks result.value.output: {line[:80]!r}")

    group = output.get("group")
    label = output.get("label")
    is_text = output.get("is_text")
    if not isinstance(group, str) or not group:
        raise ValueError(f"Magika row has an invalid group: {line[:80]!r}")
    if not isinstance(label, str) or not label:
        raise ValueError(f"Magika row has an invalid label: {line[:80]!r}")
    if not isinstance(is_text, bool):
        raise ValueError(f"Magika row has a non-boolean is_text: {line[:80]!r}")

    file_path = obj.get("path", "")
    normalised_group, normalised_label = _normalise_detected(group, label, is_text)
    return file_path, normalised_group, normalised_label, is_text


def scan_with_magika(path: str, settings: Any | None = None) -> list:
    """Scan a directory using the Magika CLI binary.

    Runs ``magika -r <path> --jsonl`` and parses each JSONL line. Only
    rows with ``result.status == "ok"`` are accepted; the label is read
    from ``result.value.output`` and boundary-normalised. Any invalid
    row fails the whole scan with ``ValueError`` so the caller falls
    back to suffix detection instead of trusting partial results.

    Args:
        path: Directory path to scan.
        settings: Injected effective settings carrying ``magika_binary``;
            ``None`` keeps the legacy process-global resolution.

    Returns:
        List of ``FileEntry`` objects for each detected file.

    Raises:
        FileNotFoundError: If the Magika binary is not on $PATH or the
            scan times out.
        subprocess.CalledProcessError: If the Magika process fails.
        ValueError: If any CLI row is invalid (non-JSON, non-``ok``
            status, malformed envelope, or bad required field).
    """
    if not _is_magika_available(settings):
        raise FileNotFoundError(f"Magika CLI binary not found: {_magika_binary(settings)}")

    try:
        result = subprocess.run(  # noqa: S603
            [_magika_binary(settings), "-r", path, "--jsonl"],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        logger.warning("Magika scan timed out after 30s, falling back to suffix detection")
        raise FileNotFoundError("Magika scan timed out") from None

    entries: list[FileEntry] = []
    project_root = Path(path)
    for line in result.stdout.splitlines():
        if not line.strip():
            continue  # Blank JSONL lines are inert, not detector failures.

        file_path, group, label, is_text = _parse_magika_row(line)

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
