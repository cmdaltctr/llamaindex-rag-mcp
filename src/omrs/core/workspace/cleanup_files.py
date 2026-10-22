"""Artefact file listing and removal for workspace cleanup.

Both functions work below one artefact root and never follow a symbolic
link. Listing uses ``lstat`` data. Removal opens each directory with
``O_NOFOLLOW`` and unlinks names relative to that directory handle, so a
directory that is swapped for a link after the preview is not entered.
"""

from __future__ import annotations

import contextlib
import os
import re
import stat
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

LINK_REASON = "symbolic link; cleanup does not follow it and leaves it in place"
_SEGMENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")
_NOFOLLOW_DIR = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_DIRECTORY", 0)


@dataclass(frozen=True)
class CleanupFile:
    """One artefact file a cleanup removes. ``ref`` is relative to the artefact root."""

    ref: str
    bytes: int
    modified_ns: int = field(repr=False)


@dataclass(frozen=True)
class CleanupSkip:
    """An item the cleanup leaves in place, and why."""

    item: str
    reason: str


def scan_run_files(
    root: Path, run_ids: Iterable[str]
) -> tuple[Mapping[str, tuple[CleanupFile, ...]], list[CleanupSkip]]:
    """List the regular files in each run directory without following links.

    Args:
        root: The artefact root (``<workspace>/artefacts``).
        run_ids: The runs whose directories to list.

    Returns:
        Files per run (sorted by reference) and the items left in place.
    """
    ids = list(run_ids)
    if root.is_symlink():
        return {}, [CleanupSkip("artefacts", LINK_REASON)] if ids else []
    files: dict[str, tuple[CleanupFile, ...]] = {}
    skipped: list[CleanupSkip] = []
    for run_id in ids:
        run_dir = root / run_id
        if not _SEGMENT.fullmatch(run_id) or not os.path.lexists(run_dir):
            continue
        if run_dir.is_symlink() or not run_dir.is_dir():
            reason = LINK_REASON if run_dir.is_symlink() else "not a directory; left in place"
            skipped.append(CleanupSkip(run_id, reason))
            continue
        found: list[CleanupFile] = []
        with os.scandir(run_dir) as entries:
            for entry in entries:
                ref = f"{run_id}/{entry.name}"
                info = entry.stat(follow_symlinks=False)
                if stat.S_ISREG(info.st_mode):
                    found.append(CleanupFile(ref, info.st_size, info.st_mtime_ns))
                else:
                    reason = LINK_REASON if entry.is_symlink() else "not a regular file; left"
                    skipped.append(CleanupSkip(ref, reason))
        files[run_id] = tuple(sorted(found, key=lambda f: f.ref))
    skipped.sort(key=lambda skip: skip.item)
    return files, skipped


def remove_run_files(
    root: Path, runs: Iterable[tuple[str, tuple[CleanupFile, ...]]]
) -> tuple[list[CleanupFile], list[CleanupSkip]]:
    """Unlink the listed files, then each run directory when it is empty.

    Args:
        root: The artefact root.
        runs: Pairs of run identifier and the files listed for it.

    Returns:
        The files removed and the files that could not be removed safely.
    """
    targets = list(runs)
    removed: list[CleanupFile] = []
    failed: list[CleanupSkip] = []
    if not targets or not os.path.lexists(root):
        return removed, failed
    try:
        root_fd = os.open(root, _NOFOLLOW_DIR)
    except OSError as exc:
        failed.extend(CleanupSkip(f.ref, str(exc)) for _, files in targets for f in files)
        return removed, failed
    try:
        for run_id, files in targets:
            _remove_run(root_fd, run_id, files, removed, failed)
    finally:
        os.close(root_fd)
    return removed, failed


def _remove_run(
    root_fd: int,
    run_id: str,
    files: tuple[CleanupFile, ...],
    removed: list[CleanupFile],
    failed: list[CleanupSkip],
) -> None:
    if files:
        try:
            run_fd = os.open(run_id, _NOFOLLOW_DIR, dir_fd=root_fd)
        except OSError as exc:
            failed.extend(CleanupSkip(f.ref, f"run directory not opened: {exc}") for f in files)
            return
        try:
            for file in files:
                name = file.ref.partition("/")[2]
                try:
                    info = os.stat(name, dir_fd=run_fd, follow_symlinks=False)
                    if not stat.S_ISREG(info.st_mode):
                        raise OSError("no longer a regular file")
                    os.unlink(name, dir_fd=run_fd)
                    removed.append(file)
                except OSError as exc:
                    failed.append(CleanupSkip(file.ref, str(exc)))
        finally:
            os.close(run_fd)
    # rmdir never follows a link. It fails when the directory is absent,
    # is a link, or still holds an item that cleanup left in place.
    with contextlib.suppress(OSError):
        os.rmdir(run_id, dir_fd=root_fd)
