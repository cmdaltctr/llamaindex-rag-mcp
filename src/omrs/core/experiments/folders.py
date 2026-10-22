"""Experiment folders below an approved root (design D4).

A folder is a plain directory below an approved experiment root. The web
workspace groups experiment contexts under their parent folders and
creates folders from the browser. Creation runs after the same checks the
registry applies to a workspace: no absolute path, no ``..`` part, no
link, and a depth limit. The path text is checked first, then the file
system. A refused request creates nothing.

This module starts no process and imports no web package. Creating a
directory is its only write.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from .contexts import OUTPUT_DIR_NAME, ExperimentContext
from .errors import ExperimentPathError

#: Most path segments below a root (``a/b/c/d`` is four).
MAX_FOLDER_DEPTH = 4
#: Longest single segment.
MAX_SEGMENT_LENGTH = 80
#: Most folders the tree lists. Registered contexts are always listed.
MAX_TREE_NODES = 500

# Starts with a letter or digit, ends with a letter, digit, ``_`` or ``-``;
# letters, digits, ``.``, ``_``, ``-`` and a single space between.
_SEGMENT = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9._ -]{0,78}[A-Za-z0-9_-])?")


def _invalid(message: str) -> ExperimentPathError:
    return ExperimentPathError("invalid_name", message)


def split_folder_path(path: str) -> tuple[str, ...]:
    """Validate a relative folder path and return its segments.

    Args:
        path: A path below an approved root, with ``/`` between segments.

    Returns:
        The validated segments.

    Raises:
        ExperimentPathError: ``not_relative``, ``traversal``, ``too_deep``
            or ``invalid_name``.
    """
    if path.startswith(("/", "\\")) or Path(path).is_absolute():
        raise ExperimentPathError("not_relative", "Give the folder as a path below the root.")
    parts = path.split("/")
    if ".." in parts:
        raise ExperimentPathError("traversal", "The folder path must not contain '..' parts.")
    if len(parts) > MAX_FOLDER_DEPTH:
        raise ExperimentPathError(
            "too_deep", f"A folder path can have at most {MAX_FOLDER_DEPTH} levels."
        )
    for part in parts:
        if not _SEGMENT.fullmatch(part) or part == OUTPUT_DIR_NAME:
            raise _invalid(
                "Use letters, digits, '.', '_', '-' and single spaces in a folder name "
                f"(1 to {MAX_SEGMENT_LENGTH} characters, not 'output')."
            )
    return tuple(parts)


def _select_root(roots: Sequence[Path], root: str | Path | None) -> Path:
    if not roots:
        raise ExperimentPathError("root_unknown", "No experiment root is approved.")
    if root is None:
        if len(roots) > 1:
            raise ExperimentPathError(
                "root_required", "Name the approved root: more than one root is approved."
            )
        return roots[0]
    match = next((item for item in roots if str(item) == str(root)), None)
    if match is None:
        raise ExperimentPathError("root_unknown", "That directory is not an approved root.")
    return match


def create_folder(roots: Sequence[Path], path: str, *, root: str | Path | None = None) -> Path:
    """Create a folder below an approved root.

    Args:
        roots: Canonical approved roots.
        path: Relative folder path (see :func:`split_folder_path`).
        root: The approved root, as listed by the registry. May be omitted
            when exactly one root is approved.

    Returns:
        The new directory.

    Raises:
        ExperimentPathError: The path or root is refused, a path part is a
            link or a file, or the folder exists. Nothing is created then.
    """
    parts = split_folder_path(path)
    base = _select_root(roots, root)
    if base.is_symlink() or not base.is_dir():
        raise ExperimentPathError("root_unknown", "The approved root is no longer a directory.")
    current = base
    for part in parts:
        current = current / part
        if current.is_symlink():
            raise ExperimentPathError(
                "symlink_escape", "A folder path part is a symbolic link; it is not followed."
            )
        if current.exists() and not current.is_dir():
            raise ExperimentPathError("not_a_directory", "A folder path part is a file.")
    try:
        current.mkdir(parents=True)
    except FileExistsError:
        raise ExperimentPathError("exists", "That folder already exists.") from None
    if not current.resolve(strict=True).is_relative_to(base):
        raise ExperimentPathError(
            "symlink_escape", "The new folder does not resolve below the approved root."
        )
    return current


def _scan(base: Path, skip: frozenset[Path]) -> list[tuple[str, ...]]:
    """Return the relative parts of every listable directory, parents first."""
    found: list[tuple[str, ...]] = []
    stack: list[tuple[Path, tuple[str, ...]]] = [(base, ())]
    while stack and len(found) < MAX_TREE_NODES:
        directory, parts = stack.pop()
        if len(parts) >= MAX_FOLDER_DEPTH:
            continue
        try:
            with os.scandir(directory) as entries:
                names = sorted(
                    entry.name
                    for entry in entries
                    if entry.is_dir(follow_symlinks=False)
                    and not entry.name.startswith(".")
                    and entry.name != OUTPUT_DIR_NAME
                )
        except OSError:
            continue
        children = []
        for name in names:
            if len(found) >= MAX_TREE_NODES:
                break
            found.append((*parts, name))
            if directory / name not in skip:
                children.append((directory / name, (*parts, name)))
        stack.extend(reversed(children))
    return found


def folder_tree(root: Path, contexts: Iterable[ExperimentContext]) -> list[dict[str, Any]]:
    """Return the folder tree of one approved root.

    A directory that holds a context workspace is a leaf: its ``output``
    directory and anything below are not listed. A folder with no context
    and no children is listed as an empty folder. Hidden directories,
    links and levels below :data:`MAX_FOLDER_DEPTH` are not scanned, but an
    active context is always listed, whatever its depth.

    Args:
        root: A canonical approved root.
        contexts: Every context of the registry (other roots are ignored).

    Returns:
        Nodes ``{name, path, workspace, context_id, children}`` sorted by
        name. ``path`` is relative to *root*; ``context_id`` is the active
        context registered at exactly that directory, else ``None``.
    """
    own = [item for item in contexts if item.root == root]
    skip = frozenset(item.workspace for item in own)
    active = {
        item.workspace.relative_to(root).parts: item.context_id for item in own if item.active
    }
    paths = set(_scan(root, skip))
    for parts in active:
        paths.update(parts[:index] for index in range(1, len(parts) + 1))
    nodes: dict[tuple[str, ...], dict[str, Any]] = {}
    top: list[dict[str, Any]] = []
    for parts in sorted(paths):
        node = {
            "name": parts[-1],
            "path": "/".join(parts),
            "workspace": str(root.joinpath(*parts)),
            "context_id": active.get(parts),
            "children": [],
        }
        nodes[parts] = node
        (nodes[parts[:-1]]["children"] if len(parts) > 1 else top).append(node)
    return top
